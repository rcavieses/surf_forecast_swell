"""Registra lo que viste en el agua y ajusta el pronóstico con esas observaciones.

Uso:
    python observar.py agregar             # te pregunta los datos uno por uno
    python observar.py agregar --fecha 2026-10-21 --inicio 10 --fin 18 --min 1.2 --max 1.8 --sets 2 \
        --lado izquierda --viento "onshore 10-15h, calma, regresa 18h" --calidad 4 --notas "..."
    python observar.py listar              # sesiones registradas, numeradas
    python observar.py eliminar 2          # borra la sesión número 2 (pide confirmación)
    python observar.py comparar            # observaciones vs. pronóstico y factor sugerido
    python observar.py calibrar            # guarda el factor sugerido (data/calibracion.json)
    python observar.py calibrar --factor 0.8
    python observar.py calibrar --reset    # vuelve al SITE_FACTOR de config.py
"""

import argparse
import sys
from datetime import date

from surf_forecast import config
from surf_forecast import observaciones as obs
from surf_forecast.fechas import ahora

LADOS = ["izquierda", "derecha", "ambos", "cerrada"]


def _hhmm(value: str) -> str:
    h, _, m = value.strip().partition(":")
    return f"{int(h):02d}:{int(m or 0):02d}"


def _ask(label: str, default="", cast=str, required=False):
    while True:
        raw = input(f"{label}{f' [{default}]' if default != '' else ''}: ").strip() or str(default)
        if not raw and not required:
            return ""
        try:
            return cast(raw)
        except ValueError:
            print("  Valor no válido, intenta de nuevo.")


def _lado(value: str) -> str:
    value = value.strip().lower()
    match = [l for l in LADOS if l.startswith(value)] if value else [""]
    if len(match) != 1:
        raise ValueError(value)
    return match[0]


def _calidad(value: str) -> str:
    if value and not 1 <= int(value) <= 5:
        raise ValueError(value)
    return value


def cmd_agregar(a):
    interactive = a.min is None
    if interactive:
        print("Nueva observación (Enter acepta el valor entre corchetes).")
        a.fecha = _ask("Fecha (AAAA-MM-DD)", a.fecha, lambda v: date.fromisoformat(v).isoformat())
        a.inicio = _ask("Hora inicio (HH o HH:MM)", a.inicio or "08:00", _hhmm)
        a.fin = _ask("Hora fin", a.fin or "12:00", _hhmm)
        a.min = _ask("Altura mínima típica (m)", "", float, required=True)
        a.max = _ask("Altura máxima típica (m)", "", float, required=True)
        a.sets = _ask("Sets más grandes (m, opcional)", "", float)
        a.lado = _ask(f"Lado ({'/'.join(LADOS)}, opcional)", "", _lado)
        a.viento = _ask("Viento (texto libre, opcional)")
        a.calidad = _ask("Calidad 1-5 (opcional)", "", _calidad)
        a.notas = _ask("Notas (opcional)")
    elif a.max is None:
        sys.exit("Falta --max.")

    if a.max < a.min:
        a.min, a.max = a.max, a.min
    obs.add_observation({
        "fecha": a.fecha, "hora_inicio": _hhmm(a.inicio or "08:00"), "hora_fin": _hhmm(a.fin or "12:00"),
        "altura_min_m": a.min, "altura_max_m": a.max, "sets_m": a.sets if a.sets is not None else "",
        "lado": a.lado or "", "viento": a.viento or "", "calidad": a.calidad or "", "notas": a.notas or "",
    })
    print(f"Guardada en {obs.OBS_FILE}")
    cmd_comparar(a)


def _describe(o) -> str:
    extra = ", ".join(v for v in [f"sets {o['sets_m']} m" if o["sets_m"] else "", o["lado"],
                                  f"calidad {o['calidad']}" if o["calidad"] else "", o["notas"]] if v)
    return (f"{o['fecha']} {o['hora_inicio']}-{o['hora_fin']}: {o['altura_min_m']}-{o['altura_max_m']} m"
            + (f" ({extra})" if extra else ""))


def cmd_listar(_a):
    df = obs.load_observations()
    if df.empty:
        print("Todavía no hay observaciones.")
        return False
    for i, (_, o) in enumerate(df.iterrows(), start=1):
        print(f"{i:>3}. {_describe(o)}")
    return True


def cmd_eliminar(a):
    if a.numero is None:
        if not cmd_listar(a):
            return
        a.numero = _ask("\nNúmero a eliminar (Enter para cancelar)", "", int)
        if a.numero == "":
            print("Cancelado.")
            return
    df = obs.load_observations()
    if not 1 <= a.numero <= len(df):
        sys.exit(f"No existe la observación {a.numero} (hay {len(df)}). Usa `python observar.py listar`.")
    print(f"Se borrará: {_describe(df.iloc[a.numero - 1])}")
    if not a.si and input("¿Seguro? (s/N): ").strip().lower() not in ("s", "si", "sí"):
        print("Cancelado.")
        return
    obs.delete_observation(a.numero)
    print("Eliminada. Si ya habías calibrado, corre `python observar.py calibrar` para recalcular el factor.")


def cmd_comparar(_a):
    table = obs.compare()
    if table.empty:
        print("Todavía no hay observaciones. Agrega una con: python observar.py agregar")
        return None
    print(f"\n=== Observaciones vs. pronóstico (factor actual {config.SITE_FACTOR}) ===")
    # Una ficha por sesión (visto | pronóstico) para que se lea bien en la pantalla del teléfono.
    for _, r in table.fillna("").iterrows():
        print(f"\n{r['fecha']} {r['horas']}  (pronóstico emitido {r['emitido']})")
        for label, seen, fc in [("Altura", f"{r['visto_m']} m" + (f", sets {r['sets_m']} m" if r["sets_m"] else ""),
                                 f"{r.get('pronóstico_m', '')} m"),
                                ("Lado", r["lado"], r.get("lado_pron", "")),
                                ("Viento", r["viento_visto"], r.get("viento_pron", "")),
                                ("Calidad", r["calidad"], r.get("calif_pron", ""))]:
            print(f"  {label:<8} visto: {seen or '-':<28} pronóstico: {fc or '-'}")
        if r.get("marea"):
            print(f"  Marea    {r['marea']}")
        if r.get("factor_ideal") != "":
            print(f"  Factor ideal: {r['factor_ideal']}")
    bias = obs.rating_bias(table)
    if bias:
        b, nb = bias
        tendency = "subestima" if b > 0.4 else "sobreestima" if b < -0.4 else "acierta en"
        print(f"\nCalificación: en promedio diste {b:+.1f} estrellas vs. el pronóstico ({nb} {'sesiones' if nb != 1 else 'sesión'}): "
              f"el modelo {tendency} la calidad.")
    sug = obs.suggested_factor(table)
    if sug is None:
        print("\nNinguna observación tiene pronóstico guardado en data/historial/ para comparar.")
        return None
    factor, n = sug
    print(f"\nFactor sugerido: {factor} (mediana de {n} {'observaciones' if n != 1 else 'observación'}; actual {config.SITE_FACTOR})")
    if n < obs.MIN_OBS_CONFIABLE:
        print(f"Con menos de {obs.MIN_OBS_CONFIABLE} observaciones es solo orientativo.")
    return sug


def cmd_calibrar(a):
    if a.reset:
        if config.CALIB_FILE.exists():
            config.CALIB_FILE.unlink()
        print("Calibración borrada; se usa SITE_FACTOR de config.py.")
        return
    if a.factor is not None:
        factor, n = a.factor, 0
    else:
        sug = cmd_comparar(a)
        if sug is None:
            return
        factor, n = sug
    path = obs.save_calibration(factor, n)
    print(f"\nSITE_FACTOR {config.SITE_FACTOR} -> {factor} guardado en {path}")
    print("Corre `python pronostico.py` para regenerar el reporte con el nuevo factor.")


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")

    p = argparse.ArgumentParser(description="Observaciones y calibración del pronóstico")
    sub = p.add_subparsers(dest="cmd", required=True)

    ag = sub.add_parser("agregar", help="registrar una sesión")
    ag.add_argument("--fecha", default=ahora().date().isoformat())
    ag.add_argument("--inicio", help="hora de inicio, HH o HH:MM")
    ag.add_argument("--fin", help="hora de fin, HH o HH:MM")
    ag.add_argument("--min", type=float, help="altura mínima típica (m)")
    ag.add_argument("--max", type=float, help="altura máxima típica (m)")
    ag.add_argument("--sets", type=float, help="sets más grandes (m)")
    ag.add_argument("--lado", type=_lado, help="/".join(LADOS))
    ag.add_argument("--viento", help="texto libre")
    ag.add_argument("--calidad", type=_calidad, help="1-5")
    ag.add_argument("--notas")
    ag.set_defaults(func=cmd_agregar)

    sub.add_parser("listar", help="sesiones registradas, numeradas").set_defaults(func=cmd_listar)

    el = sub.add_parser("eliminar", help="borrar una sesión por su número")
    el.add_argument("numero", type=int, nargs="?", help="número que muestra `listar` (si falta, pregunta)")
    el.add_argument("--si", action="store_true", help="no pedir confirmación")
    el.set_defaults(func=cmd_eliminar)

    sub.add_parser("comparar", help="observaciones vs. pronóstico").set_defaults(func=cmd_comparar)

    ca = sub.add_parser("calibrar", help="guardar el factor de sitio")
    ca.add_argument("--factor", type=float, help="usar este factor en vez del sugerido")
    ca.add_argument("--reset", action="store_true", help="borrar la calibración")
    ca.set_defaults(func=cmd_calibrar)

    a = p.parse_args()
    a.func(a)


if __name__ == "__main__":
    main()
