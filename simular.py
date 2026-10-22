"""Simula cómo rompe el oleaje en Playa Cerritos (zona por zona) sobre la forma real de la costa.

Uso:
    python simular.py                                   # pronóstico: mejor hora de las próximas 24 h
    python simular.py --fecha 2026-10-23 --hora 8       # pronóstico de ese momento
    python simular.py --altura 1.5 --periodo 14 --direccion 300   # un swell inventado
    python simular.py --plantilla                       # mapa con cuadrícula para dibujar la batimetría

Salida: output/simulacion_playa.html (o output/plantilla_batimetria.html).
"""

import argparse
import sys
import webbrowser
from datetime import date
from pathlib import Path

import pandas as pd

from surf_forecast import reporte_playa as rp
from surf_forecast import simulacion as sim
from surf_forecast.data import fetch_forecast
from surf_forecast.fechas import ahora, dia_hora
from surf_forecast.surf import compute_surf

ROOT = Path(__file__).resolve().parent
COMPONENTES = [("Swell 1", "swell_"), ("Swell 2", "secondary_swell_"), ("Mar de viento", "wind_")]


def _momento(df: pd.DataFrame, fecha, hora) -> pd.Timestamp:
    if fecha:
        day = df[df.index.date == date.fromisoformat(fecha)]
        if day.empty:
            sys.exit(f"No hay pronóstico para {fecha}.")
        if hora is not None:
            return day.index[abs(day.index.hour - hora).argmin()]
        light = day.between_time("06:00", "18:00")
        return light["rating"].idxmax()
    nxt = df[(df.index >= ahora().floor("h")) & (df.index < ahora() + pd.Timedelta(hours=24))]
    light = nxt.between_time("06:00", "18:00")
    return (light if not light.empty else nxt)["rating"].idxmax()


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description="Simulación de oleaje en la playa")
    p.add_argument("--fecha", help="AAAA-MM-DD (por defecto, las próximas 24 h)")
    p.add_argument("--hora", type=int, help="hora local (por defecto, la mejor del día)")
    p.add_argument("--altura", type=float, help="swell manual: altura mar adentro (m)")
    p.add_argument("--periodo", type=float, help="swell manual: periodo (s)")
    p.add_argument("--direccion", type=float, help="swell manual: de dónde viene (grados)")
    p.add_argument("--plantilla", action="store_true", help="mapa con cuadrícula para dibujar la batimetría")
    p.add_argument("--no-open", action="store_true")
    a = p.parse_args()

    if a.plantilla:
        out = rp.write_html(ROOT / "output" / "plantilla_batimetria.html", "Plantilla para dibujar la batimetría",
                            [], None, rp.mapa(cuadricula=200),
                            extra_html="<p>Cuadrícula de 200 m: anota profundidades como «D7: 3 m» o dibuja las "
                                       "curvas sobre una captura. Las líneas blancas son la batimetría actual.</p>")
    else:
        simple = None
        if a.altura is not None:
            if a.periodo is None or a.direccion is None:
                sys.exit("Con --altura indica también --periodo y --direccion.")
            comps = [{"nombre": "Swell", "altura": a.altura, "periodo": a.periodo, "direccion": a.direccion}]
            title = f"Swell {a.altura:.1f} m · {a.periodo:.0f} s · {a.direccion:.0f}°"
        else:
            hourly, _daily = fetch_forecast()
            df = compute_surf(hourly)
            t = _momento(df, a.fecha, a.hora)
            r = df.loc[t]
            comps = [{"nombre": n, "altura": r[f"{pre}wave_height"], "periodo": r[f"{pre}wave_period"],
                      "direccion": r[f"{pre}wave_direction"]} for n, pre in COMPONENTES
                     if r[f"{pre}wave_height"] >= 0.1 and r[f"{pre}wave_period"] >= 4]
            simple = (r["surf_min_m"], r["surf_max_m"])
            title = f"Playa Cerritos · {dia_hora(t)}"
            print(f"Pronóstico {dia_hora(t)}: rompiente simple {simple[0]:.1f}-{simple[1]:.1f} m")
        results = []
        for c in comps:
            print(f"Simulando {c['nombre']}: {c['altura']:.1f} m, {c['periodo']:.0f} s, desde {c['direccion']:.0f}°…")
            res = sim.propagar(c["altura"], c["periodo"], c["direccion"])
            res["rompientes"]["componente"] = c["nombre"]
            results.append(res)
        perfil = sim.perfil_playa([r["rompientes"] for r in results])
        main_res = max(results, key=lambda r: r["entrada"]["altura"])
        fig = rp.mapa(pd.concat([r["rompientes"] for r in results]), main_res["trayectorias"])
        out = rp.write_html(ROOT / "output" / "simulacion_playa.html", title, comps, perfil, fig, simple)
        print()
        for lo, hi, n in rp.ZONAS:
            q = perfil[(perfil["s"] >= lo) & (perfil["s"] < hi) & (perfil["H"] > 0)]
            print(f"  {n:<14} " + (f"{q['H'].min():.1f}-{q['H'].max():.1f} m, {q['lado'].value_counts().idxmax()}"
                                  if not q.empty else "sombra"))
    print(f"\nReporte: {out}")
    if not a.no_open:
        webbrowser.open(out.as_uri())


if __name__ == "__main__":
    main()
