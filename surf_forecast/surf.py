"""Convierte el oleaje mar adentro en altura de ola en la rompiente y calificación de surf."""

import numpy as np
import pandas as pd

from . import config

G = 9.81
M_TO_FT = 3.28084

RATING_LABELS = ["Flat", "Pobre", "Regular", "Bueno", "Muy bueno", "Épico"]


def angle_diff(a, b):
    """Diferencia angular absoluta en grados (0-180)."""
    d = np.abs((np.asarray(a, dtype=float) - b + 180) % 360 - 180)
    return d


def breaking_height(h0, period, direction, site_factor=None):
    """Altura de rompiente (m) de un componente de swell.

    Usa Komar & Gaughan (1973): Hb = 0.39 g^0.2 (T H0^2)^0.4, reducida por la
    oblicuidad del swell respecto a la playa y por el factor de calibración del sitio
    (config.SITE_FACTOR si no se indica otro).
    """
    if site_factor is None:
        site_factor = config.SITE_FACTOR
    h0 = np.nan_to_num(np.asarray(h0, dtype=float))
    period = np.nan_to_num(np.asarray(period, dtype=float))
    hb = 0.39 * G**0.2 * (period * h0**2) ** 0.4

    theta = np.minimum(angle_diff(direction, config.BEACH_NORMAL_DEG), config.EXPOSURE_HALF_WINDOW_DEG)
    exposure = np.sqrt(np.cos(np.radians(theta * 90 / config.EXPOSURE_HALF_WINDOW_DEG)).clip(0))
    exposure = np.nan_to_num(exposure)
    return hb * exposure * site_factor


def wind_quality(speed_kmh, direction):
    """Clasifica el viento: 'offshore', 'cruzado', 'onshore' o 'calma'."""
    theta = angle_diff(direction, config.OFFSHORE_WIND_DEG)
    kind = np.where(theta <= 45, "offshore", np.where(theta <= 110, "cruzado", "onshore"))
    return np.where(np.asarray(speed_kmh) < 6, "calma", kind)


def _rating(row) -> int:
    h = row["surf_m"]
    if h < 0.3:
        return 0
    score = np.interp(h, [0.3, 0.6, 1.0, 1.5, 2.2, 3.0], [1, 1.5, 2, 3, 3.8, 3.5])

    t = row["main_period"]
    if t >= 13:
        score += 1.0
    elif t >= 11:
        score += 0.5
    elif t < 8:
        score -= 1.0

    w, kind = row["wind_speed_10m"], row["wind_kind"]
    if kind in ("calma", "offshore") and w < 25:
        score += 0.5
    elif kind == "cruzado":
        score -= 0.3 + max(0.0, (w - 12) / 15)
    elif kind == "onshore":
        score -= 0.5 + max(0.0, (w - 8) / 10)

    return int(np.clip(round(score), 0, 5))


def _components(waves: pd.DataFrame, site_factor=None) -> pd.DataFrame:
    """Altura de rompiente de cada componente (swell 1, swell 2, mar de viento)."""
    return pd.DataFrame({
        f"hb_{name}": breaking_height(waves[f"{prefix}wave_height"], waves[f"{prefix}wave_period"],
                                      waves[f"{prefix}wave_direction"], site_factor)
        for name, prefix in [("primary", "swell_"), ("secondary", "secondary_swell_"), ("windsea", "wind_")]
    }, index=waves.index)


def surf_height(waves: pd.DataFrame, site_factor=None) -> pd.Series:
    """Altura de rompiente combinada (m). Los componentes se combinan por energía."""
    return np.sqrt((_components(waves, site_factor) ** 2).sum(axis=1))


def peel_side(direction):
    """Hacia dónde abre la ola, visto por el surfista, según el ángulo del swell con la playa.

    Mirando al mar desde la orilla, un swell que llega por la izquierda de la normal de la playa
    (menos grados) toca primero ese extremo y abre hacia la derecha de quien mira desde la arena:
    para el surfista, que mira hacia la orilla, eso es una izquierda.
    """
    d = (np.asarray(direction, dtype=float) - config.BEACH_NORMAL_DEG + 180) % 360 - 180
    return np.where(np.abs(d) < config.PEAK_ANGLE_DEG, "pico", np.where(d < 0, "izquierda", "derecha"))


def compute_surf(hourly: pd.DataFrame, site_factor=None) -> pd.DataFrame:
    df = hourly.copy()
    df[["hb_primary", "hb_secondary", "hb_windsea"]] = _components(df, site_factor)

    df["surf_m"] = np.sqrt(df["hb_primary"] ** 2 + df["hb_secondary"] ** 2 + df["hb_windsea"] ** 2)
    df["surf_min_m"] = df["surf_m"] * 0.75
    df["surf_max_m"] = df["surf_m"] * 1.15
    df["surf_min_ft"] = df["surf_min_m"] * M_TO_FT
    df["surf_max_ft"] = df["surf_max_m"] * M_TO_FT
    if "swell_wave_height_gfs" in df:
        gfs = df.filter(regex="wave_(height|period|direction)_gfs$").rename(columns=lambda c: c.removesuffix("_gfs"))
        df["surf_m_gfs"] = surf_height(gfs, site_factor)

    # Periodo y dirección del componente que más aporta a la rompiente.
    comps = df[["hb_primary", "hb_secondary", "hb_windsea"]].to_numpy()
    idx = np.nanargmax(np.nan_to_num(comps), axis=1)
    periods = df[["swell_wave_period", "secondary_swell_wave_period", "wind_wave_period"]].to_numpy()
    dirs = df[["swell_wave_direction", "secondary_swell_wave_direction", "wind_wave_direction"]].to_numpy()
    rows = np.arange(len(df))
    df["main_period"] = periods[rows, idx]
    df["main_direction"] = dirs[rows, idx]
    df["main_source"] = np.array(["Swell 1", "Swell 2", "Mar de viento"])[idx]
    df["lado"] = peel_side(df["main_direction"])

    df["wind_kind"] = wind_quality(df["wind_speed_10m"], df["wind_direction_10m"])
    df["rating"] = df.apply(_rating, axis=1)
    df["rating_label"] = df["rating"].map(lambda r: RATING_LABELS[r])
    return df


def compass(deg) -> str:
    if deg is None or pd.isna(deg):
        return "-"
    names = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSO", "SO", "OSO", "O", "ONO", "NO", "NNO"]
    return names[int((deg % 360) / 22.5 + 0.5) % 16]


def _windows(hours: pd.DatetimeIndex) -> str:
    """Agrupa horas consecutivas: [6,7,8,9,18,19] -> '06–09h · 18–19h'."""
    runs = []
    for t in hours:
        if runs and t - runs[-1][1] == pd.Timedelta(hours=1):
            runs[-1][1] = t
        else:
            runs.append([t, t])
    return " · ".join(f"{a:%H}h" if a == b else f"{a:%H}–{b:%H}h" for a, b in runs)


def _confidence(g: pd.DataFrame) -> str:
    """Qué tanto coinciden los dos modelos de oleaje en la altura del día."""
    if "surf_m_gfs" not in g or g["surf_m_gfs"].isna().all():
        return "-"
    a, b = g["surf_m"].mean(), g["surf_m_gfs"].mean()
    diff = abs(a - b) / max((a + b) / 2, 0.3)
    return "alta" if diff < 0.15 else "media" if diff < 0.30 else "baja"


def daily_summary(df: pd.DataFrame, daily: pd.DataFrame) -> pd.DataFrame:
    """Resumen por día usando solo horas de luz."""
    out = []
    for day, g in df.groupby(df.index.date):
        if day in daily.index:
            sr, ss = daily.loc[day, "sunrise"], daily.loc[day, "sunset"]
            g = g[(g.index >= sr.floor("h")) & (g.index <= ss)]
        if g.empty:
            continue
        top = int(g["rating"].max())
        best = g[g["rating"] == top]
        out.append({
            "fecha": day,
            "surf_ft": f"{g['surf_min_ft'].min():.0f}-{g['surf_max_ft'].max():.0f}",
            "surf_m": f"{g['surf_min_m'].min():.1f}-{g['surf_max_m'].max():.1f}",
            "periodo_s": round(g["main_period"].mean(), 1),
            "dir_swell": compass(best["main_direction"].median()),
            "lado": best["lado"].mode().iloc[0],
            "mejores_horas": _windows(best.index),
            "calif_max": top,
            "calif": RATING_LABELS[top],
            "confianza": _confidence(g),
            "viento_mañana": f"{g.between_time('06:00', '10:00')['wind_speed_10m'].mean():.0f} km/h",
            "viento_tarde": f"{g.between_time('13:00', '17:00')['wind_speed_10m'].mean():.0f} km/h",
        })
    return pd.DataFrame(out).set_index("fecha")
