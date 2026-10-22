"""Avisa al teléfono (ntfy.sh) si en los próximos días viene un buen día de surf.

Uso:
    NTFY_TOPIC=mi-tema python alerta.py            # avisa si hay días >= config.ALERT_MIN_RATING
    NTFY_TOPIC=mi-tema python alerta.py --prueba   # manda un aviso de prueba con el resumen

Para recibirlos instala la app ntfy (Android/iOS) y suscríbete al mismo tema. REPORT_URL (opcional)
es el enlace que se abre al tocar la notificación.
"""

import argparse
import os
import sys

import pandas as pd
import requests

from surf_forecast import config
from surf_forecast.data import fetch_forecast
from surf_forecast.fechas import ahora, dia
from surf_forecast.surf import compute_surf, daily_summary


def _line(day, r) -> str:
    stars = "★" * r["calif_max"] + "☆" * (5 - r["calif_max"])
    return (f"{dia(day)} {stars}: {r['surf_ft']} ft ({r['surf_m']} m), {r['periodo_s']} s, {r['lado']}, "
            f"mejor {r['mejores_horas']}")


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description="Aviso de buenos días de surf")
    p.add_argument("--prueba", action="store_true", help="enviar aunque no haya días buenos")
    args = p.parse_args()

    topic = os.environ.get("NTFY_TOPIC")
    if not topic:
        sys.exit("Falta la variable de entorno NTFY_TOPIC.")

    hourly, daily = fetch_forecast()
    summary = daily_summary(compute_surf(hourly), daily)
    today = ahora().date()
    upcoming = summary[(summary.index > today) & (summary.index <= today + pd.Timedelta(days=config.ALERT_DAYS))]
    good = upcoming[upcoming["calif_max"] >= config.ALERT_MIN_RATING]

    if good.empty and not args.prueba:
        print("Sin días buenos en los próximos días; no se envía aviso.")
        return
    days = good if not good.empty else upcoming
    title = f"Surf {config.SPOT_NAME}: " + ("¡vienen buenas olas!" if not good.empty else "aviso de prueba")
    msg = {"topic": topic, "title": title, "message": "\n".join(_line(d, r) for d, r in days.iterrows()),
           "tags": ["ocean"], "priority": 4 if not good.empty else 3}
    if os.environ.get("REPORT_URL"):
        msg["click"] = os.environ["REPORT_URL"]
    requests.post("https://ntfy.sh/", json=msg, timeout=30).raise_for_status()
    print(f"Aviso enviado:\n{msg['message']}")


if __name__ == "__main__":
    main()
