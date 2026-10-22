"""Configuración del spot. Ajusta estos valores con tus propias observaciones."""

import json
from pathlib import Path

SPOT_NAME = "Playa Cerritos, BCS"

# Punto de consulta del modelo de oleaje (un poco mar adentro para evitar
# celdas de tierra en la malla del modelo). Cerritos está en ~23.331, -110.178.
LATITUDE = 23.32
LONGITUDE = -110.20
TIMEZONE = "America/Mazatlan"

# Orientación de la playa: dirección (grados, "desde donde viene") hacia la que
# mira la playa. Cerritos mira al suroeste.
BEACH_NORMAL_DEG = 235

# Swells que llegan con más de este ángulo respecto a la normal de la playa
# se consideran bloqueados (no llegan a la playa).
EXPOSURE_HALF_WINDOW_DEG = 85

# Factor de calibración del sitio. Multiplica la altura de rompiente calculada.
# Si el pronóstico te sale sistemáticamente alto, bájalo (p. ej. 0.7);
# si sale bajo, súbelo (p. ej. 1.1).
# `python observar.py calibrar` lo calcula a partir de tus observaciones y lo guarda en
# data/calibracion.json, que tiene prioridad sobre este valor.
SITE_FACTOR = 0.85
CALIB_FILE = Path(__file__).resolve().parent.parent / "data" / "calibracion.json"
CALIBRATION = json.loads(CALIB_FILE.read_text(encoding="utf-8")) if CALIB_FILE.exists() else None
if CALIBRATION:
    SITE_FACTOR = CALIBRATION["site_factor"]

# Si el swell llega a menos de estos grados de la normal de la playa, las olas rompen en "pico"
# (abren a los dos lados); si no, se marcan como izquierda o derecha según de qué lado llegan.
PEAK_ANGLE_DEG = 10

# Segundo modelo de oleaje para estimar la confianza del pronóstico (el principal es el que
# Open-Meteo elige por defecto, Météo-France en esta zona). ECMWF no tiene datos en este punto.
COMPARISON_WAVE_MODEL = "ncep_gfswave016"

# Alertas (alerta.py): avisa si en los próximos ALERT_DAYS días hay calificación >= ALERT_MIN_RATING.
ALERT_MIN_RATING = 4
ALERT_DAYS = 3

# Viento offshore = viento que sopla desde tierra hacia el mar.
OFFSHORE_WIND_DEG = (BEACH_NORMAL_DEG + 180) % 360

# Webcam de la playa que se muestra en el reporte (WEBCAM_EMBED_URL = None para quitarla).
# La cámara es de Cerritos Surf Cam / Coastal Camera Network; el reporte enlaza a su sitio como crédito.
WEBCAM_EMBED_URL = "https://coastalcameranetwork.com/webcams/cerritos/beach-cam.php"
WEBCAM_CREDIT_NAME = "Cerritos Surf Cam"
WEBCAM_CREDIT_URL = "https://www.cerritossurfcam.com/"
WEBCAM_OPERATOR_NAME = "Coastal Camera Network"
WEBCAM_OPERATOR_URL = "https://coastalcameranetwork.com/"

FORECAST_DAYS = 7
CACHE_MINUTES = 60
