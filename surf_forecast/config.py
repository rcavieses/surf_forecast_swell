"""Configuración del spot. Ajusta estos valores con tus propias observaciones."""

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
SITE_FACTOR = 0.85

# Viento offshore = viento que sopla desde tierra hacia el mar.
OFFSHORE_WIND_DEG = (BEACH_NORMAL_DEG + 180) % 360

FORECAST_DAYS = 7
CACHE_MINUTES = 60
