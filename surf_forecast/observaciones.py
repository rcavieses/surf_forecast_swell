"""Registro de observaciones en el agua y calibración del pronóstico contra ellas."""

import csv
import json
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from . import config
from .fechas import ahora
from .surf import compute_surf, surf_height

ROOT = Path(__file__).resolve().parent.parent
OBS_FILE = ROOT / "data" / "observaciones.csv"
HIST_DIR = ROOT / "data" / "historial"

LADOS = ["izquierda", "derecha", "ambos", "cerrada"]
# Escala ordinal del viento en el agua y su equivalente aproximado en el pronóstico (km/h, límite superior).
VIENTO_NIVELES = ["sin viento", "ligero", "moderado", "fuerte", "muy fuerte"]
VIENTO_DESCRIPCION = ["glassy, espejo", "apenas riza la superficie", "algo de viento, superficie algo picada",
                      "picado, cuesta remar", "casi imposible surfear"]
VIENTO_LIMITES_KMH = [5, 12, 20, 30]
COLUMNS = ["fecha", "hora_inicio", "hora_fin", "altura_min_m", "altura_max_m", "sets_m", "lado", "viento_nivel",
           "viento", "calidad", "notas"]
MIN_OBS_CONFIABLE = 3

# La rompiente pronosticada se publica como rango [0.75, 1.15] × surf_m; su punto medio es 0.95 × surf_m.
RANGE_MID = (0.75 + 1.15) / 2


def hhmm(value: str) -> str:
    """'7' -> '07:00', '7:30' -> '07:30'."""
    h, _, m = str(value).strip().partition(":")
    h, m = int(h), int(m or 0)
    if not (0 <= h <= 23 and 0 <= m <= 59):
        raise ValueError(value)
    return f"{h:02d}:{m:02d}"


def parse_lado(value: str) -> str:
    """Acepta abreviaturas ('izq' -> 'izquierda'); vacío = sin dato."""
    value = str(value).strip().lower()
    match = [l for l in LADOS if l.startswith(value)] if value else [""]
    if len(match) != 1:
        raise ValueError(value)
    return match[0]


def parse_viento_nivel(value) -> str:
    """'2', 'mod' o 'moderado' -> '2'; vacío = sin dato."""
    value = str(value).strip().lower()
    if not value:
        return ""
    if value.isdigit():
        if not 0 <= int(value) < len(VIENTO_NIVELES):
            raise ValueError(value)
        return value
    match = [i for i, n in enumerate(VIENTO_NIVELES) if n.startswith(value)]
    if len(match) != 1:
        raise ValueError(value)
    return str(match[0])


def viento_nivel_kmh(kmh: float) -> int:
    """Nivel de la escala que corresponde a una velocidad de viento pronosticada."""
    return int(np.searchsorted(VIENTO_LIMITES_KMH, kmh, side="right"))


def viento_nivel_texto(nivel) -> str:
    return "" if nivel in ("", None) else f"{int(nivel)} {VIENTO_NIVELES[int(nivel)]}"


def parse_calidad(value) -> str:
    value = str(value).strip()
    if value and not 1 <= int(value) <= 5:
        raise ValueError(value)
    return value


def build_observation(fecha, inicio, fin, altura_min, altura_max, sets="", lado="", viento_nivel="", viento="",
                      calidad="", notas="") -> dict:
    """Valida y normaliza una sesión. Lanza ValueError con un mensaje para mostrar al usuario."""
    def num(v, name, required=False):
        if v in ("", None):
            if required:
                raise ValueError(f"Falta {name}.")
            return ""
        try:
            x = float(v)
        except ValueError:
            raise ValueError(f"{name.capitalize()} no es un número: {v}") from None
        if not 0 <= x <= 15:
            raise ValueError(f"{name.capitalize()} fuera de rango (0-15 m): {v}")
        return x

    try:
        fecha = date.fromisoformat(str(fecha)).isoformat()
    except ValueError:
        raise ValueError(f"Fecha no válida: {fecha}") from None
    try:
        inicio, fin = hhmm(inicio), hhmm(fin)
    except ValueError:
        raise ValueError("Horas no válidas (usa HH o HH:MM).") from None
    if fin <= inicio:
        raise ValueError("La hora de fin debe ser después de la de inicio.")
    lo, hi = num(altura_min, "la altura mínima", True), num(altura_max, "la altura máxima", True)
    try:
        lado, viento_nivel, calidad = parse_lado(lado), parse_viento_nivel(viento_nivel), parse_calidad(calidad)
    except ValueError:
        raise ValueError("Lado, viento o calidad no válidos.") from None
    return {"fecha": fecha, "hora_inicio": inicio, "hora_fin": fin, "altura_min_m": min(lo, hi),
            "altura_max_m": max(lo, hi), "sets_m": num(sets, "los sets"), "lado": lado, "viento_nivel": viento_nivel,
            "viento": str(viento or "").strip(), "calidad": calidad, "notas": str(notas or "").strip()}


def load_observations() -> pd.DataFrame:
    if not OBS_FILE.exists():
        return pd.DataFrame(columns=COLUMNS)
    # reindex: los archivos de versiones anteriores no tienen todas las columnas (p. ej. viento_nivel).
    return pd.read_csv(OBS_FILE, dtype=str, keep_default_na=False).reindex(columns=COLUMNS, fill_value="")


def _write_all(records: list[dict]) -> None:
    # Saltos de línea \n en Windows y Termux para no ensuciar los diffs.
    OBS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with OBS_FILE.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, COLUMNS, lineterminator="\n")
        w.writeheader()
        w.writerows({c: r.get(c, "") for c in COLUMNS} for r in records)


def add_observation(obs: dict) -> None:
    # Se reescribe el archivo completo (es pequeño) para que siempre quede con las columnas actuales.
    _write_all(load_observations().to_dict("records") + [obs])


def delete_observation(number: int) -> dict:
    """Borra la observación número `number` (1 = la primera del archivo) y la devuelve."""
    df = load_observations()
    if not 1 <= number <= len(df):
        raise IndexError(f"No existe la sesión #{number} (hay {len(df)}).")
    removed = df.iloc[number - 1].to_dict()
    _write_all(df.drop(index=df.index[number - 1]).to_dict("records"))
    return removed


def _history_files():
    for p in sorted(HIST_DIR.glob("pronostico_*.csv*")):
        try:
            yield datetime.strptime(p.name.split(".")[0].removeprefix("pronostico_"), "%Y%m%d_%H%M"), p
        except ValueError:
            continue


def forecast_for(start: datetime, end: datetime):
    """Pronóstico que cubre la sesión: el último emitido antes de empezar (el que habrías consultado).

    Si no hay ninguno previo, usa el primero emitido después (hasta un día). Devuelve (emitido, horas) o
    (None, None).
    """
    files = [(i, p) for i, p in _history_files() if start - timedelta(days=16) <= i <= end + timedelta(days=1)]
    # Del más reciente previo hacia atrás y luego los posteriores en orden: casi siempre basta leer uno.
    ordered = sorted((f for f in files if f[0] <= start), reverse=True) + sorted(f for f in files if f[0] > start)
    for issued, path in ordered:
        hours = pd.read_csv(path, parse_dates=["time"], index_col="time").loc[start:end]
        if not hours.empty:
            return issued, hours
    return None, None


def compare() -> pd.DataFrame:
    """Una fila por observación con el pronóstico de esa ventana y el factor de sitio que lo habría igualado."""
    rows = []
    for _, o in load_observations().iterrows():
        start = datetime.strptime(f"{o['fecha']} {o['hora_inicio']}", "%Y-%m-%d %H:%M")
        end = datetime.strptime(f"{o['fecha']} {o['hora_fin']}", "%Y-%m-%d %H:%M")
        issued, hours = forecast_for(start, end)
        row = {"fecha": o["fecha"], "horas": f"{o['hora_inicio']}-{o['hora_fin']}",
               "visto_m": f"{o['altura_min_m']}-{o['altura_max_m']}", "sets_m": o["sets_m"], "lado": o["lado"],
               "viento_nivel": o["viento_nivel"], "viento_visto": o["viento"], "calidad": o["calidad"]}
        if hours is None:
            rows.append(row | {"emitido": "sin pronóstico"})
            continue
        # La altura se recalcula con factor 1 para que no dependa del factor vigente al emitirse; la
        # calificación y el lado, con el factor actual.
        raw = surf_height(hours, site_factor=1.0).mean()
        current = raw * config.SITE_FACTOR
        fc = compute_surf(hours)
        obs_mid = (float(o["altura_min_m"]) + float(o["altura_max_m"])) / 2
        tide = hours["sea_level_height_msl"]
        trend = tide.iloc[-1] - tide.iloc[0]
        rows.append(row | {
            "emitido": f"{issued:%d/%m %H:%M}",
            "pronóstico_m": f"{current * 0.75:.1f}-{current * 1.15:.1f}",
            "lado_pron": fc["lado"].mode().iloc[0],
            "viento_nivel_pron": viento_nivel_kmh(hours["wind_speed_10m"].mean()),
            "viento_pron": f"{hours['wind_speed_10m'].mean():.0f} km/h, {fc['wind_kind'].mode().iloc[0]}",
            "marea": f"{tide.min():+.2f} a {tide.max():+.2f} m, "
                     + ("subiendo" if trend > 0.05 else "bajando" if trend < -0.05 else "estable"),
            "calif_pron": int(fc["rating"].max()),
            "factor_ideal": round(obs_mid / (raw * RANGE_MID), 2),
        })
    return pd.DataFrame(rows)


def rating_bias(table: pd.DataFrame):
    """Promedio de (calidad que diste - calificación pronosticada). None si no hay pares."""
    if "calif_pron" not in table:
        return None
    pairs = table[["calidad", "calif_pron"]].replace("", np.nan).dropna()
    return (round(float((pairs["calidad"].astype(float) - pairs["calif_pron"]).mean()), 1), len(pairs)) \
        if len(pairs) else None


def suggested_factor(table: pd.DataFrame):
    """Mediana de los factores ideales (robusta a una observación rara). None si no hay datos."""
    if table.empty or "factor_ideal" not in table:
        return None
    factors = table["factor_ideal"].dropna()
    return (round(float(np.median(factors)), 2), len(factors)) if len(factors) else None


def save_calibration(factor: float, n_obs: int) -> Path:
    data = {"site_factor": factor, "n_obs": n_obs, "actualizado": f"{ahora():%Y-%m-%d %H:%M}"}
    config.CALIB_FILE.parent.mkdir(parents=True, exist_ok=True)
    config.CALIB_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    # También en memoria, para que un proceso que sigue corriendo (observar_web.py) use el nuevo factor.
    config.CALIBRATION, config.SITE_FACTOR = data, factor
    return config.CALIB_FILE


def reset_calibration() -> None:
    """Borra la calibración y vuelve al SITE_FACTOR de config.py."""
    if config.CALIB_FILE.exists():
        config.CALIB_FILE.unlink()
    config.CALIBRATION, config.SITE_FACTOR = None, config.DEFAULT_SITE_FACTOR
