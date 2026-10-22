"""Descarga de datos de oleaje, viento y marea desde Open-Meteo (gratis, sin API key)."""

import json
import time
from pathlib import Path

import pandas as pd
import requests

from . import config

MARINE_URL = "https://marine-api.open-meteo.com/v1/marine"
WEATHER_URL = "https://api.open-meteo.com/v1/forecast"

MARINE_VARS = [
    "wave_height", "wave_period", "wave_direction",
    "swell_wave_height", "swell_wave_period", "swell_wave_peak_period", "swell_wave_direction",
    "secondary_swell_wave_height", "secondary_swell_wave_period", "secondary_swell_wave_direction",
    "wind_wave_height", "wind_wave_period", "wind_wave_direction",
    "sea_level_height_msl",
]
WEATHER_VARS = ["wind_speed_10m", "wind_direction_10m", "wind_gusts_10m"]

CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "cache"


def _get_json(url: str, params: dict, cache_name: str, use_cache: bool) -> dict:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = CACHE_DIR / f"{cache_name}.json"
    if use_cache and cache_file.exists():
        age_min = (time.time() - cache_file.stat().st_mtime) / 60
        if age_min < config.CACHE_MINUTES:
            return json.loads(cache_file.read_text(encoding="utf-8"))

    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    cache_file.write_text(json.dumps(data), encoding="utf-8")
    return data


def fetch_forecast(days: int = config.FORECAST_DAYS, use_cache: bool = True) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Regresa (horario, diario). El horario combina oleaje, viento y marea."""
    common = {
        "latitude": config.LATITUDE,
        "longitude": config.LONGITUDE,
        "timezone": config.TIMEZONE,
        "forecast_days": days,
    }
    marine = _get_json(MARINE_URL, {**common, "hourly": ",".join(MARINE_VARS)}, "marine", use_cache)
    weather = _get_json(
        WEATHER_URL,
        {**common, "hourly": ",".join(WEATHER_VARS), "daily": "sunrise,sunset", "wind_speed_unit": "kmh"},
        "weather",
        use_cache,
    )

    hourly = pd.DataFrame(marine["hourly"]).set_index("time")
    wind = pd.DataFrame(weather["hourly"]).set_index("time")
    hourly = hourly.join(wind, how="left")
    hourly.index = pd.to_datetime(hourly.index)

    daily = pd.DataFrame(weather["daily"])
    daily["time"] = pd.to_datetime(daily["time"]).dt.date
    daily["sunrise"] = pd.to_datetime(daily["sunrise"])
    daily["sunset"] = pd.to_datetime(daily["sunset"])
    return hourly, daily.set_index("time")
