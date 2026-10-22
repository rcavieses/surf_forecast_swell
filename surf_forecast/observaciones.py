"""Registro de observaciones en el agua y calibración del pronóstico contra ellas."""

import csv
import json
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from . import config
from .surf import compute_surf

ROOT = Path(__file__).resolve().parent.parent
OBS_FILE = ROOT / "data" / "observaciones.csv"
HIST_DIR = ROOT / "data" / "historial"

COLUMNS = ["fecha", "hora_inicio", "hora_fin", "altura_min_m", "altura_max_m", "sets_m", "lado", "viento",
           "calidad", "notas"]
MIN_OBS_CONFIABLE = 3

# La rompiente pronosticada se publica como rango [0.75, 1.15] × surf_m; su punto medio es 0.95 × surf_m.
RANGE_MID = (0.75 + 1.15) / 2


def load_observations() -> pd.DataFrame:
    if not OBS_FILE.exists():
        return pd.DataFrame(columns=COLUMNS)
    return pd.read_csv(OBS_FILE, dtype=str, keep_default_na=False)


def add_observation(obs: dict) -> None:
    OBS_FILE.parent.mkdir(parents=True, exist_ok=True)
    new = not OBS_FILE.exists()
    with OBS_FILE.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, COLUMNS)
        if new:
            w.writeheader()
        w.writerow({c: obs.get(c, "") for c in COLUMNS})


def _history_files():
    for p in sorted(HIST_DIR.glob("pronostico_*.csv")):
        try:
            yield datetime.strptime(p.stem.removeprefix("pronostico_"), "%Y%m%d_%H%M"), p
        except ValueError:
            continue


def forecast_for(start: datetime, end: datetime):
    """Pronóstico que cubre la sesión: el último emitido antes de empezar (el que habrías consultado).

    Si no hay ninguno previo, usa el primero emitido después (hasta un día). Devuelve (emitido, horas) o
    (None, None).
    """
    before, after = None, None
    for issued, path in _history_files():
        if issued < start - timedelta(days=16) or issued > end + timedelta(days=1):
            continue
        hours = pd.read_csv(path, parse_dates=["time"], index_col="time").loc[start:end]
        if hours.empty:
            continue
        if issued <= start:
            before = (issued, hours)
        elif after is None:
            after = (issued, hours)
    return before or after or (None, None)


def compare() -> pd.DataFrame:
    """Una fila por observación con el pronóstico de esa ventana y el factor de sitio que lo habría igualado."""
    rows = []
    for _, o in load_observations().iterrows():
        start = datetime.strptime(f"{o['fecha']} {o['hora_inicio']}", "%Y-%m-%d %H:%M")
        end = datetime.strptime(f"{o['fecha']} {o['hora_fin']}", "%Y-%m-%d %H:%M")
        issued, hours = forecast_for(start, end)
        row = {"fecha": o["fecha"], "horas": f"{o['hora_inicio']}-{o['hora_fin']}",
               "visto_m": f"{o['altura_min_m']}-{o['altura_max_m']}", "sets_m": o["sets_m"], "lado": o["lado"],
               "viento_visto": o["viento"]}
        if hours is None:
            rows.append(row | {"emitido": "sin pronóstico"})
            continue
        # Se recalcula con factor 1 para que la comparación no dependa del factor vigente al emitirse.
        raw = compute_surf(hours, site_factor=1.0)["surf_m"].mean()
        current = raw * config.SITE_FACTOR
        obs_mid = (float(o["altura_min_m"]) + float(o["altura_max_m"])) / 2
        rows.append(row | {
            "emitido": f"{issued:%d/%m %H:%M}",
            "pronóstico_m": f"{current * 0.75:.1f}-{current * 1.15:.1f}",
            "viento_pron": f"{hours['wind_speed_10m'].mean():.0f} km/h, {hours['wind_kind'].mode().iloc[0]}",
            "factor_ideal": round(obs_mid / (raw * RANGE_MID), 2),
        })
    return pd.DataFrame(rows)


def suggested_factor(table: pd.DataFrame):
    """Mediana de los factores ideales (robusta a una observación rara). None si no hay datos."""
    if table.empty or "factor_ideal" not in table:
        return None
    factors = table["factor_ideal"].dropna()
    return (round(float(np.median(factors)), 2), len(factors)) if len(factors) else None


def save_calibration(factor: float, n_obs: int) -> Path:
    data = {"site_factor": factor, "n_obs": n_obs, "actualizado": f"{datetime.now():%Y-%m-%d %H:%M}"}
    config.CALIB_FILE.parent.mkdir(parents=True, exist_ok=True)
    config.CALIB_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return config.CALIB_FILE
