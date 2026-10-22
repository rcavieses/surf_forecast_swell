"""Simula cómo rompe el oleaje en Playa Cerritos (zona por zona) sobre la forma real de la costa.

Uso:
    python simular.py                                   # pronóstico: mejor hora de las próximas 24 h
    python simular.py --fecha 2026-10-23 --hora 8       # pronóstico de ese momento
    python simular.py --pronostico                      # hoy, mañana y pasado cada 3 h, con selector
    python simular.py --altura 1.5 --periodo 14 --direccion 300   # un swell inventado
    python simular.py --marea -0.8                      # forzar marea (m respecto a marea media)
    python simular.py --plantilla                       # mapa con cuadrícula para dibujar la batimetría

Salida: output/simulacion_playa.html, output/simulacion.html (--pronostico) u output/plantilla_batimetria.html.
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
HORAS_PRONOSTICO = [6, 9, 12, 15, 18]
DIAS_PRONOSTICO = 3  # hoy, mañana y pasado


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


def _marea_txt(marea: float, tendencia: str = "") -> str:
    return (f"{marea:+.2f} m respecto a marea media{tendencia}"
            + (" (baja)" if marea < -0.4 else " (alta)" if marea > 0.4 else " (media)"))


def simular_componentes(comps: list[dict], marea: float, verbose=True) -> dict:
    """Simula cada componente y las combina. Devuelve perfil, rompientes, trayectorias y altura típica."""
    results = []
    for c in comps:
        if verbose:
            print(f"  {c['nombre']}: {c['altura']:.1f} m, {c['periodo']:.0f} s, desde {c['direccion']:.0f}°")
        res = sim.propagar(c["altura"], c["periodo"], c["direccion"], marea=marea)
        res["rompientes"]["componente"] = c["nombre"]
        results.append(res)
    perfil = sim.perfil_playa([r["rompientes"] for r in results])
    breaks = pd.concat([r["rompientes"] for r in results]) if results else pd.DataFrame()
    main = max(results, key=lambda r: r["entrada"]["altura"]) if results else None
    ola = float(perfil.loc[perfil["H"] > 0, "H"].median()) if (perfil["H"] > 0).any() else None
    return {"perfil": perfil, "rompientes": breaks, "trayectorias": main["trayectorias"] if main else None,
            "ola": ola}


def escenario_pronostico(df: pd.DataFrame, t: pd.Timestamp, marea=None) -> dict:
    """Componentes de oleaje y marea del pronóstico en el momento t."""
    r = df.loc[t]
    comps = [{"nombre": n, "altura": r[f"{pre}wave_height"], "periodo": r[f"{pre}wave_period"],
              "direccion": r[f"{pre}wave_direction"]} for n, pre in COMPONENTES
             if r[f"{pre}wave_height"] >= 0.1 and r[f"{pre}wave_period"] >= 4]
    tendencia = ""
    if marea is None:
        # El nivel del modelo no está centrado en 0: se toma como marea media el promedio pronosticado.
        tide = df["sea_level_height_msl"]
        marea = float(tide.loc[t] - tide.mean())
        nxt = tide.shift(-1).loc[t]
        tendencia = "" if pd.isna(nxt) else ", subiendo" if nxt > tide.loc[t] else ", bajando"
    return {"t": t, "comps": comps, "marea": marea, "marea_txt": _marea_txt(marea, tendencia),
            "simple": (r["surf_min_m"], r["surf_max_m"]), "rating": int(r["rating"])}


def _imprimir_zonas(perfil: pd.DataFrame):
    for lo, hi, n in rp.ZONAS:
        q = perfil[(perfil["s"] >= lo) & (perfil["s"] < hi) & (perfil["H"] > 0)]
        print(f"  {n:<14} " + (f"{q['H'].min():.1f}-{q['H'].max():.1f} m, {q['lado'].value_counts().idxmax()}"
                              if not q.empty else "sombra"))


def pronostico(df: pd.DataFrame) -> Path:
    """Simula hoy, mañana y pasado a las HORAS_PRONOSTICO y genera la página con selector."""
    today = ahora().date()
    names = {0: "Hoy", 1: "Mañana", 2: "Pasado"}
    times = [t for t in df.index if t.hour in HORAS_PRONOSTICO and 0 <= (t.date() - today).days < DIAS_PRONOSTICO
             and t >= ahora().floor("h") - pd.Timedelta(hours=2)]
    escenarios = []
    for t in times:
        e = escenario_pronostico(df, t)
        print(f"{dia_hora(t)} · marea {e['marea']:+.2f} m")
        e.update(simular_componentes(e["comps"], e["marea"], verbose=False))
        e["etiqueta"] = (f"{names.get((t.date() - today).days, '')} {dia_hora(t)} · "
                         f"{'★' * e['rating']}{'☆' * (5 - e['rating'])}")
        escenarios.append(e)
    # Abre en la mejor hora de mañana (o del primer día disponible).
    tomorrow = [i for i, e in enumerate(escenarios) if (e["t"].date() - today).days == 1] or range(len(escenarios))
    inicial = max(tomorrow, key=lambda i: (escenarios[i]["rating"], -i))
    return rp.write_pronostico(ROOT / "output" / "simulacion.html", escenarios, inicial)


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description="Simulación de oleaje en la playa")
    p.add_argument("--fecha", help="AAAA-MM-DD (por defecto, las próximas 24 h)")
    p.add_argument("--hora", type=int, help="hora local (por defecto, la mejor del día)")
    p.add_argument("--pronostico", action="store_true",
                   help=f"hoy, mañana y pasado a las {', '.join(map(str, HORAS_PRONOSTICO))} h, con selector")
    p.add_argument("--altura", type=float, help="swell manual: altura mar adentro (m)")
    p.add_argument("--periodo", type=float, help="swell manual: periodo (s)")
    p.add_argument("--direccion", type=float, help="swell manual: de dónde viene (grados)")
    p.add_argument("--marea", type=float, help="nivel de marea en m respecto a marea media (p. ej. -0.8 = baja); "
                                               "por defecto, la del pronóstico")
    p.add_argument("--plantilla", action="store_true", help="mapa con cuadrícula para dibujar la batimetría")
    p.add_argument("--no-open", action="store_true")
    a = p.parse_args()

    if a.plantilla:
        out = rp.write_html(ROOT / "output" / "plantilla_batimetria.html", "Plantilla para dibujar la batimetría",
                            [], None, rp.mapa(cuadricula=200),
                            extra_html="<p>Cuadrícula de 200 m: anota profundidades como «D7: 3 m» o dibuja las "
                                       "curvas sobre una captura. Las líneas blancas son la batimetría actual.</p>")
    elif a.pronostico:
        hourly, _daily = fetch_forecast()
        out = pronostico(compute_surf(hourly))
    else:
        if a.altura is not None:
            if a.periodo is None or a.direccion is None:
                sys.exit("Con --altura indica también --periodo y --direccion.")
            marea = a.marea or 0.0
            e = {"comps": [{"nombre": "Swell", "altura": a.altura, "periodo": a.periodo, "direccion": a.direccion}],
                 "marea": marea, "marea_txt": _marea_txt(marea), "simple": None}
            title = f"Swell {a.altura:.1f} m · {a.periodo:.0f} s · {a.direccion:.0f}°"
        else:
            hourly, _daily = fetch_forecast()
            df = compute_surf(hourly)
            t = _momento(df, a.fecha, a.hora)
            e = escenario_pronostico(df, t, a.marea)
            title = f"Playa Cerritos · {dia_hora(t)}"
            print(f"Pronóstico {dia_hora(t)}: rompiente simple {e['simple'][0]:.1f}-{e['simple'][1]:.1f} m")
        print(f"Marea: {e['marea_txt']}\nSimulando…")
        e.update(simular_componentes(e["comps"], e["marea"]))
        kw = dict(marea=e["marea"], ola=e["ola"])
        fig = rp.mapa(e["rompientes"], e["trayectorias"], **kw)
        fig_punta = rp.mapa(e["rompientes"], e["trayectorias"], detalle=True, **kw)
        out = rp.write_html(ROOT / "output" / "simulacion_playa.html", title, e["comps"], e["perfil"], fig,
                            e["simple"], marea_txt=e["marea_txt"], fig_punta=fig_punta)
        print()
        _imprimir_zonas(e["perfil"])
    print(f"\nReporte: {out}")
    if not a.no_open:
        webbrowser.open(out.as_uri())


if __name__ == "__main__":
    main()
