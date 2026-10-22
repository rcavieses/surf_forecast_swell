"""Fechas en español sin depender del idioma del sistema (Windows, Termux y GitHub Actions difieren)."""

import pandas as pd

from . import config

DIAS = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
DIAS_LARGOS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
MESES_LARGOS = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
                "noviembre", "diciembre"]


def ahora() -> pd.Timestamp:
    """Hora local del spot, sin zona (como los datos de Open-Meteo), sea cual sea la zona de la máquina."""
    return pd.Timestamp.now(tz=config.TIMEZONE).tz_localize(None)


def dia(t) -> str:
    """'Mié 21 oct'"""
    t = pd.Timestamp(t)
    return f"{DIAS[t.dayofweek]} {t.day} {MESES[t.month - 1]}"


def dia_hora(t) -> str:
    """'Mié 21 14:00'"""
    t = pd.Timestamp(t)
    return f"{DIAS[t.dayofweek]} {t.day} {t:%H:%M}"


# Para registrar el idioma en Plotly (ejes de fecha) sin descargar archivos de internet.
PLOTLY_LOCALE_JS = (
    "Plotly.register({moduleType: 'locale', name: 'es', dictionary: {}, format: {"
    f"days: {DIAS_LARGOS!r}, shortDays: {DIAS!r}, months: {MESES_LARGOS!r}, shortMonths: {MESES!r}, "
    "date: '%d/%m/%Y'}});"
)
