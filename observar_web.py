"""Interfaz web para registrar sesiones y calibrar el pronóstico (misma lógica que observar.py).

Uso:
    python observar_web.py                  # abre http://localhost:8001 en el navegador
    python observar_web.py --puerto 8002 --no-open

En Termux: deja la terminal abierta, entra a http://localhost:8001 en Chrome y cierra con Ctrl+C.
Solo escucha en este equipo (127.0.0.1); no queda expuesta a la red.
"""

import argparse
import os
import subprocess
import sys
import webbrowser
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

import pandas as pd

from surf_forecast import config
from surf_forecast import observaciones as obs
from surf_forecast.fechas import ahora, dia

ROOT = Path(__file__).resolve().parent
FORM_FIELDS = ["fecha", "inicio", "fin", "altura_min", "altura_max", "sets", "lado", "viento_nivel", "viento",
               "calidad", "notas"]
last_sync = ""  # salida del último "Sincronizar con GitHub", para mostrarla en la página


# ---------------------------------------------------------------- acciones

def sync_github() -> tuple[bool, str]:
    """git add/commit de data/, pull --rebase y push. Devuelve (ok, salida)."""
    log = []

    def git(*args):
        # GIT_TERMINAL_PROMPT=0: sin credenciales, git falla en vez de quedarse esperando un usuario.
        r = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=120, env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})
        log.append(f"$ git {' '.join(args)}\n{(r.stdout + r.stderr).strip()}".strip())
        return r.returncode

    try:
        git("add", "-A", "data")
        if git("diff", "--cached", "--quiet") == 1 and git("commit", "-m", f"Observaciones {ahora():%Y-%m-%d %H:%M}"):
            return False, "\n\n".join(log)
        for args in (("pull", "--rebase", "--autostash"), ("push",)):
            if git(*args):
                if args == ("push",):
                    log.append("Si falta iniciar sesión en GitHub (Termux): "
                               "pkg install gh && gh auth login && gh auth setup-git")
                return False, "\n\n".join(log)
    except (OSError, subprocess.TimeoutExpired) as e:
        log.append(f"Error: {e}")
        return False, "\n\n".join(log)
    return True, "\n\n".join(log)


# ---------------------------------------------------------------- HTML

CSS = """
:root { --line: #e0e0e0; --muted: #616161; --accent: #0277bd; }
* { box-sizing: border-box; }
body { font-family: system-ui, Segoe UI, sans-serif; margin: 0 auto; max-width: 900px; padding: 16px; color: #212121;
       background: #fafafa; }
h1 { margin: 0; font-size: 1.6rem; } h2 { margin: 28px 0 10px; font-size: 1.2rem; }
a { color: var(--accent); }
.top { display: flex; justify-content: space-between; align-items: baseline; flex-wrap: wrap; gap: 8px; }
.panel { background: white; border: 1px solid var(--line); border-radius: 10px; padding: 14px; }
.msg { padding: 10px 14px; border-radius: 8px; margin: 12px 0; }
.ok { background: #e8f5e9; color: #1b5e20; } .error { background: #ffebee; color: #b71c1c; }
label { display: block; font-size: 13px; font-weight: 600; color: var(--muted); margin-bottom: 4px; }
input, textarea, select { width: 100%; font: inherit; padding: 9px 10px; border: 1px solid #bdbdbd; border-radius: 8px;
       background: white; }
textarea { min-height: 60px; }
.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 12px; margin-bottom: 12px; }
.choices { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 12px; }
.choices input { position: absolute; opacity: 0; width: 0; }
.choices span { display: inline-block; padding: 8px 12px; border: 1px solid #bdbdbd; border-radius: 20px;
       cursor: pointer; background: white; user-select: none; }
.choices input:checked + span { background: var(--accent); color: white; border-color: var(--accent); }
.choices input:focus-visible + span { outline: 2px solid var(--accent); outline-offset: 2px; }
button { font: inherit; padding: 10px 16px; border: 0; border-radius: 8px; background: var(--accent); color: white;
       cursor: pointer; }
button.secondary { background: #eceff1; color: #263238; } button.danger { background: none; color: #c62828; padding: 6px 0; }
.row { display: flex; gap: 8px; flex-wrap: wrap; align-items: end; }
.row > * { flex: 0 0 auto; }
.big { font-size: 1.8rem; font-weight: 700; }
.muted { color: var(--muted); font-size: 14px; }
.card { background: white; border: 1px solid var(--line); border-radius: 10px; margin-bottom: 12px; overflow: hidden; }
.card header { background: #eceff1; padding: 10px 14px; display: flex; justify-content: space-between; gap: 8px;
       flex-wrap: wrap; font-weight: 700; }
.card table { width: 100%; border-collapse: collapse; font-size: 14px; }
.card th, .card td { padding: 7px 14px; border-bottom: 1px solid #f0f0f0; text-align: left; vertical-align: top; }
.card th { color: var(--muted); font-weight: 600; width: 22%; }
.card thead th { font-size: 12px; text-transform: uppercase; letter-spacing: .03em; }
.card footer { padding: 8px 14px; display: flex; justify-content: space-between; align-items: center; gap: 8px;
       flex-wrap: wrap; font-size: 14px; }
pre { white-space: pre-wrap; font-size: 12px; background: #263238; color: #eceff1; padding: 10px; border-radius: 8px;
       max-height: 260px; overflow: auto; }
@media (max-width: 600px) { body { padding: 10px; } .card th, .card td { padding: 6px 10px; } }
"""


def _stars(n) -> str:
    try:
        n = int(float(n))
    except (TypeError, ValueError):
        return "-"
    return "★" * n + "☆" * (5 - n)


def _choices(name: str, options: list[tuple[str, str]], selected: str) -> str:
    return "<div class='choices'>" + "".join(
        f"<label><input type='radio' name='{name}' value='{escape(v)}'{' checked' if v == selected else ''}>"
        f"<span>{escape(text)}</span></label>" for v, text in options) + "</div>"


def _form(values: dict) -> str:
    v = {k: escape(str(values.get(k, ""))) for k in FORM_FIELDS}
    lados = [("", "sin dato")] + [(l, l) for l in obs.LADOS]
    calidades = [("", "sin dato")] + [(str(i), "★" * i) for i in range(1, 6)]
    vientos = [("", "sin dato")] + [(str(i), n) for i, n in enumerate(obs.VIENTO_NIVELES)]
    escala = " · ".join(f"<b>{escape(n)}</b>: {escape(d)}" for n, d in zip(obs.VIENTO_NIVELES, obs.VIENTO_DESCRIPCION))
    return f"""<form method="post" action="/agregar" class="panel">
<div class="grid">
 <div><label for="fecha">Fecha</label><input type="date" id="fecha" name="fecha" value="{v['fecha']}" required></div>
 <div><label for="inicio">Entré</label><input type="time" id="inicio" name="inicio" value="{v['inicio']}" required></div>
 <div><label for="fin">Salí</label><input type="time" id="fin" name="fin" value="{v['fin']}" required></div>
</div>
<div class="grid">
 <div><label for="altura_min">Altura mínima típica (m)</label>
  <input type="number" id="altura_min" name="altura_min" value="{v['altura_min']}" step="0.1" min="0" max="15"
   inputmode="decimal" required placeholder="1.2"></div>
 <div><label for="altura_max">Altura máxima típica (m)</label>
  <input type="number" id="altura_max" name="altura_max" value="{v['altura_max']}" step="0.1" min="0" max="15"
   inputmode="decimal" required placeholder="1.8"></div>
 <div><label for="sets">Sets más grandes (m)</label>
  <input type="number" id="sets" name="sets" value="{v['sets']}" step="0.1" min="0" max="15" inputmode="decimal"
   placeholder="opcional"></div>
</div>
<label>Lado</label>{_choices("lado", lados, values.get("lado", ""))}
<label>Calidad</label>{_choices("calidad", calidades, values.get("calidad", ""))}
<label>Viento</label>{_choices("viento_nivel", vientos, values.get("viento_nivel", ""))}
<p class="muted" style="margin-top:-6px">{escala}</p>
<div class="grid">
 <div><label for="viento">Detalle del viento</label><input id="viento" name="viento" value="{v['viento']}"
  placeholder="opcional, p. ej. onshore desde las 10"></div>
</div>
<label for="notas">Notas</label><textarea id="notas" name="notas" placeholder="marea, gente, bancos de arena…">{v['notas']}</textarea>
<p><button type="submit">Guardar sesión</button></p>
</form>"""


def _calibration(table: pd.DataFrame) -> str:
    c = config.CALIBRATION
    status = (f"calibrado el {escape(c['actualizado'][:10])} con "
              + (f"{c['n_obs']} {'sesiones' if c['n_obs'] != 1 else 'sesión'}" if c.get("n_obs") else "valor manual")
              if c else "sin calibrar (valor de config.py)")
    sug = obs.suggested_factor(table) if not table.empty else None
    if sug:
        factor, n = sug
        warn = (f" <span class='muted'>Con menos de {obs.MIN_OBS_CONFIABLE} sesiones es solo orientativo.</span>"
                if n < obs.MIN_OBS_CONFIABLE else "")
        suggestion = (f"<p>Sugerido por tus sesiones: <b>{factor}</b> (mediana de {n}).{warn}</p>"
                      f"<form method='post' action='/calibrar'><input type='hidden' name='accion' value='sugerido'>"
                      f"<button>Aplicar {factor}</button></form>")
    else:
        suggestion = "<p class='muted'>Todavía no hay sesiones con pronóstico guardado para sugerir un factor.</p>"
    bias = obs.rating_bias(table) if not table.empty else None
    bias_html = ""
    if bias:
        b, nb = bias
        tendency = "subestima" if b > 0.4 else "sobreestima" if b < -0.4 else "acierta en"
        bias_html = (f"<p>Calificación: en promedio diste <b>{b:+.1f}</b> estrellas frente al pronóstico "
                     f"({nb} {'sesiones' if nb != 1 else 'sesión'}); el modelo {tendency} la calidad.</p>")
    return f"""<div class="panel">
<p>Factor de sitio actual: <span class="big">{config.SITE_FACTOR}</span> <span class="muted">{status}</span></p>
{suggestion}{bias_html}
<form method="post" action="/calibrar" class="row" style="margin-top:12px">
 <div><label for="factor">Factor manual</label>
  <input type="number" id="factor" name="factor" step="0.01" min="0.2" max="2" inputmode="decimal"
   placeholder="0.80" style="width:120px" required></div>
 <input type="hidden" name="accion" value="manual"><button class="secondary">Usar este valor</button>
</form>
<form method="post" action="/calibrar" style="margin-top:8px"><input type="hidden" name="accion" value="reset">
 <button class="secondary">Volver al de config.py ({config.DEFAULT_SITE_FACTOR})</button></form>
<p class="muted">El nuevo factor se usa la próxima vez que se genere el pronóstico (en GitHub, después de sincronizar).</p>
</div>"""


def _sessions(observations: pd.DataFrame, table: pd.DataFrame) -> str:
    if observations.empty:
        return "<p class='muted'>Todavía no hay sesiones registradas.</p>"
    cards = []
    for i in range(len(observations) - 1, -1, -1):  # la más reciente primero
        o, r = observations.iloc[i], table.iloc[i].fillna("")
        num = i + 1
        sets = f", sets {escape(o['sets_m'])} m" if o["sets_m"] else ""
        rows = [
            ("Altura", f"{escape(o['altura_min_m'])}–{escape(o['altura_max_m'])} m{sets}",
             f"{escape(str(r.get('pronóstico_m', '')))} m" if r.get("pronóstico_m") else "-"),
            ("Lado", escape(o["lado"]) or "-", escape(str(r.get("lado_pron", ""))) or "-"),
            ("Viento", escape(" · ".join(x for x in [obs.viento_nivel_texto(o["viento_nivel"]), o["viento"]] if x))
             or "-",
             f"{escape(obs.viento_nivel_texto(r['viento_nivel_pron']))} ({escape(str(r['viento_pron']))})"
             if r.get("viento_pron") else "-"),
            ("Calidad", _stars(o["calidad"]) if o["calidad"] else "-",
             _stars(r.get("calif_pron")) if r.get("calif_pron") != "" else "-"),
        ]
        body = "".join(f"<tr><th>{a}</th><td>{b}</td><td>{c}</td></tr>" for a, b, c in rows)
        extra = []
        if r.get("marea"):
            extra.append(f"Marea: {escape(str(r['marea']))}")
        if r.get("factor_ideal") != "":
            extra.append(f"Factor ideal: <b>{r['factor_ideal']}</b>")
        if o["notas"]:
            extra.append(f"Notas: {escape(o['notas'])}")
        issued = r.get("emitido", "")
        cards.append(f"""<article class="card">
<header><span>#{num} · {escape(dia(o['fecha']))} · {escape(o['hora_inicio'])}–{escape(o['hora_fin'])}</span>
<span class="muted">pronóstico: {escape(str(issued))}</span></header>
<table><thead><tr><th></th><th>Visto</th><th>Pronóstico</th></tr></thead><tbody>{body}</tbody></table>
<footer><span>{' · '.join(extra)}</span>
<form method="post" action="/eliminar" onsubmit="return confirm('¿Eliminar la sesión #{num} del {escape(o['fecha'])}?')">
<input type="hidden" name="numero" value="{num}"><button class="danger">Eliminar</button></form></footer>
</article>""")
    return "".join(cards)


def render(ok: str = "", error: str = "", form: dict | None = None) -> str:
    now = ahora()
    end = now.floor("h")
    form = form or {"fecha": now.date().isoformat(), "inicio": f"{max(end.hour - 2, 0):02d}:00",
                    "fin": f"{max(end.hour, 1):02d}:00"}
    observations = obs.load_observations()
    table = obs.compare() if not observations.empty else pd.DataFrame()
    msg = (f"<div class='msg ok'>{escape(ok)}</div>" if ok else "") + \
          (f"<div class='msg error'>{escape(error)}</div>" if error else "")
    sync_out = f"<pre>{escape(last_sync)}</pre>" if last_sync else ""
    return f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Sesiones · {escape(config.SPOT_NAME)}</title><style>{CSS}</style></head><body>
<div class="top"><h1>🏄 Mis sesiones</h1>
<a href="{escape(config.REPORT_URL)}" target="_blank" rel="noopener">Ver pronóstico ↗</a></div>
<p class="muted">{escape(config.SPOT_NAME)} · registra lo que viste en el agua para ajustar el pronóstico.</p>
{msg}
<h2>Nueva sesión</h2>
{_form(form)}
<h2>Sesiones ({len(observations)})</h2>
{_sessions(observations, table)}
<h2>Calibración</h2>
{_calibration(table)}
<h2>GitHub</h2>
<div class="panel">
<p class="muted">Sube tus sesiones y la calibración, y baja los pronósticos guardados por GitHub Actions.</p>
<form method="post" action="/sincronizar"><button>Sincronizar con GitHub</button></form>
{sync_out}
</div>
</body></html>"""


# ---------------------------------------------------------------- servidor

class Handler(BaseHTTPRequestHandler):
    def _send(self, body: str, status: int = 200):
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _redirect(self, **params):
        self.send_response(303)
        self.send_header("Location", "/?" + urlencode(params))
        self.end_headers()

    def do_GET(self):
        url = urlparse(self.path)
        if url.path != "/":
            self._send("<p>No encontrado. <a href='/'>Volver</a></p>", 404)
            return
        q = {k: v[0] for k, v in parse_qs(url.query).items()}
        self._send(render(ok=q.get("ok", ""), error=q.get("error", "")))

    def do_POST(self):
        global last_sync
        length = int(self.headers.get("Content-Length", 0))
        form = {k: v[0] for k, v in parse_qs(self.rfile.read(length).decode("utf-8"), keep_blank_values=True).items()}
        path = urlparse(self.path).path
        try:
            if path == "/agregar":
                try:
                    o = obs.build_observation(*(form.get(k, "") for k in FORM_FIELDS))
                except ValueError as e:
                    # Se vuelve a mostrar el formulario con lo que ya habías escrito.
                    self._send(render(error=str(e), form=form), 400)
                    return
                obs.add_observation(o)
                self._redirect(ok=f"Sesión del {o['fecha']} guardada. No olvides sincronizar con GitHub.")
            elif path == "/eliminar":
                removed = obs.delete_observation(int(form.get("numero", 0)))
                self._redirect(ok=f"Sesión del {removed['fecha']} {removed['hora_inicio']} eliminada.")
            elif path == "/calibrar":
                action = form.get("accion")
                if action == "reset":
                    obs.reset_calibration()
                    self._redirect(ok=f"Calibración borrada; factor {config.SITE_FACTOR}.")
                elif action == "manual":
                    factor = float(form.get("factor", ""))
                    if not 0.2 <= factor <= 2:
                        raise ValueError("El factor debe estar entre 0.2 y 2.")
                    obs.save_calibration(round(factor, 2), 0)
                    self._redirect(ok=f"Factor de sitio fijado en {config.SITE_FACTOR}.")
                else:
                    sug = obs.suggested_factor(obs.compare())
                    if not sug:
                        raise ValueError("No hay sesiones con pronóstico para sugerir un factor.")
                    obs.save_calibration(*sug)
                    self._redirect(ok=f"Factor de sitio calibrado en {sug[0]} con {sug[1]} sesiones.")
            elif path == "/sincronizar":
                ok, last_sync = sync_github()
                if ok:
                    self._redirect(ok="Sincronizado con GitHub.")
                else:
                    self._redirect(error="La sincronización falló; revisa el detalle en la sección GitHub.")
            else:
                self._send("<p>No encontrado. <a href='/'>Volver</a></p>", 404)
        except (ValueError, IndexError) as e:
            self._redirect(error=str(e) or "Datos no válidos.")

    def log_message(self, fmt, *args):  # sin el log por petición en la terminal
        pass


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description="Interfaz web de observaciones")
    p.add_argument("--puerto", type=int, default=8001)
    p.add_argument("--no-open", action="store_true", help="no abrir el navegador")
    args = p.parse_args()

    server = ThreadingHTTPServer(("127.0.0.1", args.puerto), Handler)
    url = f"http://localhost:{args.puerto}/"
    print(f"Interfaz de sesiones en {url}  (Ctrl+C para cerrar)")
    if not args.no_open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nCerrado.")


if __name__ == "__main__":
    main()
