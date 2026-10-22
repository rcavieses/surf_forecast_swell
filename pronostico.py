"""Pronóstico de surf para Playa Cerritos, BCS.

Uso:
    python pronostico.py              # terminal + reporte HTML (se abre en el navegador)
    python pronostico.py --no-open    # no abre el navegador
    python pronostico.py --dias 10    # hasta 16 días (menos precisión a largo plazo)
    python pronostico.py --refrescar  # ignora la caché y descarga de nuevo
"""

import argparse
import sys
import webbrowser
from datetime import datetime
from pathlib import Path

from surf_forecast import config
from surf_forecast.data import fetch_forecast
from surf_forecast.report import print_terminal, write_html
from surf_forecast.surf import compute_surf, daily_summary

ROOT = Path(__file__).resolve().parent


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    p = argparse.ArgumentParser(description=f"Pronóstico de surf – {config.SPOT_NAME}")
    p.add_argument("--dias", type=int, default=config.FORECAST_DAYS, help="días de pronóstico (1-16)")
    p.add_argument("--refrescar", action="store_true", help="ignorar caché")
    p.add_argument("--no-open", action="store_true", help="no abrir el reporte en el navegador")
    args = p.parse_args()

    hourly, daily = fetch_forecast(days=max(1, min(args.dias, 16)), use_cache=not args.refrescar)
    df = compute_surf(hourly)
    summary = daily_summary(df, daily)

    print_terminal(df, summary)

    # Historial para comparar después contra lo observado y calibrar SITE_FACTOR.
    hist_dir = ROOT / "data" / "historial"
    hist_dir.mkdir(parents=True, exist_ok=True)
    df.to_csv(hist_dir / f"pronostico_{datetime.now():%Y%m%d_%H%M}.csv")

    out = write_html(df, daily, summary, ROOT / "output" / "pronostico_cerritos.html")
    print(f"\nReporte: {out}")
    if not args.no_open:
        webbrowser.open(out.as_uri())


if __name__ == "__main__":
    main()
