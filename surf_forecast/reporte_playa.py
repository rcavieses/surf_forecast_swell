"""HTML de la simulación de la playa: mapa (satélite, batimetría, rayos, rompientes) y perfil a lo largo de la costa."""

import base64
from html import escape
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.offline import get_plotlyjs

from . import config
from .fechas import PLOTLY_LOCALE_JS, ahora, dia_hora
from .playa import IMAGEN_ATRIBUCION, BATI_USUARIO_FILE, batimetria, costa, teselas

# Zonas de la costa por posición s (m desde la punta; negativo = rocas al norte, positivo = playa al SE).
ZONAS = [(-1500, -150, "Rocas (norte)"), (-150, 300, "La Punta"), (300, 1200, "Playa norte"),
         (1200, 2200, "Playa centro"), (2200, 3000, "Playa sur")]
VISTA = (-900, 1100, -1900, 500)  # x0, x1, y0, y1 del mapa al abrir (la punta y la playa)
VISTA_PUNTA = (-120, 380, -230, 170)  # acercamiento a La Punta, donde está tu batimetría
LADO_COLOR = {"izquierda": "#1565c0", "derecha": "#ef6c00", "cierra": "#757575", "": "#bdbdbd"}


def zona(s: float) -> str:
    return next((n for a, b, n in ZONAS if a <= s < b), "")


def _imagenes(x0, x1, y0, y1, z):
    imgs = []
    for t in teselas(x0, x1, y0, y1, z):
        uri = "data:image/jpeg;base64," + base64.b64encode(Path(t["archivo"]).read_bytes()).decode()
        imgs.append(dict(source=uri, xref="x", yref="y", x=t["x0"], y=t["y1"], sizex=t["x1"] - t["x0"],
                         sizey=t["y1"] - t["y0"], sizing="stretch", layer="below"))
    return imgs


def expuesto_datos(marea: float, ola: float | None, vista, paso: int = 1):
    """Fondo descubierto por la marea (2) y fondo que aflora en el seno de la ola (1; ~0.35·H bajo el nivel
    medio). Devuelve x, y, z recortados a la vista (z con NaN donde no hay nada expuesto)."""
    b0 = batimetria()
    h = b0["h"] + marea
    x0, x1, y0, y1 = vista
    kx, ky = (b0["x"] >= x0) & (b0["x"] <= x1), (b0["y"] >= y0) & (b0["y"] <= y1)
    water = ~b0["tierra"]
    cat = np.full(h.shape, np.nan)
    if ola:
        cat[water & (h > 0) & (h < 0.35 * ola)] = 1
    cat[water & (h <= 0)] = 2
    return b0["x"][kx][::paso], b0["y"][ky][::paso], cat[np.ix_(ky, kx)][::paso, ::paso]


def _expuesto(fig, marea: float, ola: float | None, vista, siempre=False):
    x, y, cat = expuesto_datos(marea, ola, vista, paso=1 if vista == VISTA_PUNTA else 2)
    if np.isnan(cat).all() and not siempre:
        return
    fig.add_trace(go.Heatmap(
        x=x, y=y, z=cat, zmin=1, zmax=2, showscale=False, hoverongaps=False,
        colorscale=[[0, "rgba(255,193,7,0.55)"], [0.5, "rgba(255,193,7,0.55)"], [0.5, "rgba(229,57,53,0.7)"],
                    [1, "rgba(229,57,53,0.7)"]],
        hovertemplate="%{z:.0f}<extra>1 = aflora entre olas · 2 = descubierto</extra>", name="Fondo expuesto"))
    # Entradas de leyenda (un heatmap no tiene leyenda propia).
    for color, label in [("rgba(229,57,53,0.9)", "Descubierto por la marea"),
                         ("rgba(255,193,7,0.9)", "Aflora entre olas")]:
        fig.add_trace(go.Scatter(x=[None], y=[None], mode="markers", marker=dict(color=color, size=10,
                                 symbol="square"), name=label))


def rompientes_datos(r: pd.DataFrame, vista) -> dict:
    """Puntos de rompiente dentro de la vista, listos para dibujar (redondeados para que pesen poco)."""
    x0, x1, y0, y1 = vista
    r = r[r["x"].between(x0 - 50, x1 + 50) & r["y"].between(y0 - 50, y1 + 50)]
    return {"x": r["x"].round(0).tolist(), "y": r["y"].round(0).tolist(), "H": r["H"].round(2).tolist(),
            "text": [f"{zona(s)} · {comp}<br>{H:.1f} m en {hh:.1f} m de agua · {lado} ({ang:+.0f}°)"
                     for s, comp, H, hh, lado, ang in zip(r["s"], r["componente"], r["H"], r["h"], r["lado"],
                                                          r["angulo"])]}


def mapa(rompientes: pd.DataFrame | None = None, trayectorias=None, cuadricula: float | None = None,
         marea: float = 0.0, ola: float | None = None, detalle: bool = False, h_max: float | None = None,
         siempre: bool = False) -> go.Figure:
    """Mapa general de la costa o, con detalle=True, acercamiento a La Punta. Con siempre=True las capas de
    rompiente y fondo expuesto existen aunque estén vacías (para actualizarlas desde la página)."""
    """Mapa general de la costa o, con detalle=True, acercamiento a La Punta."""
    b = batimetria()
    vista = VISTA_PUNTA if detalle else VISTA
    # Malla recortada (y más gruesa en el mapa general): basta para dibujar curvas y pesa mucho menos.
    # Las curvas son de profundidad con la marea del momento.
    x0, x1, y0, y1 = vista
    margin, step = (100, 1) if detalle else (1500, 2)
    kx = (b["x"] >= x0 - margin) & (b["x"] <= x1 + margin)
    ky = (b["y"] >= y0 - margin) & (b["y"] <= y1 + margin)
    h = np.where(b["tierra"], np.nan, b["h"] + marea)[np.ix_(ky, kx)][::step, ::step].round(2)
    fig = go.Figure()
    _expuesto(fig, marea, ola, vista, siempre)
    levels = [(0.5, 3, 0.5)] if detalle else [(1, 5, 1), (10, 20, 10)]  # zona de rompiente y luego cada 10 m
    for start, end, size in levels:
        fig.add_trace(go.Contour(
            x=b["x"][kx][::step], y=b["y"][ky][::step], z=h, showscale=False, hoverinfo="skip", showlegend=False,
            contours=dict(coloring="lines", showlabels=True, start=start, end=end, size=size,
                          labelfont=dict(color="white", size=10)),
            line=dict(width=1), colorscale=[[0, "rgba(255,255,255,0.8)"], [1, "rgba(255,255,255,0.8)"]]))
    if trayectorias:
        xs, ys = [], []
        for path in trayectorias[::2 if detalle else 7]:
            if len(path) > 1:
                p = np.array(path).round(0)
                xs += list(p[:, 0]) + [None]
                ys += list(p[:, 1]) + [None]
        fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines", line=dict(color="rgba(255,255,255,0.35)", width=1),
                                 hoverinfo="skip", name="Rayos (swell principal)"))
    if (rompientes is not None and not rompientes.empty) or siempre:
        d = rompientes_datos(rompientes, vista) if rompientes is not None else {"x": [], "y": [], "H": [], "text": []}
        cmax = h_max or max(2.5, float(np.quantile(d["H"], 0.95)) if d["H"] else 2.5)
        fig.add_trace(go.Scatter(
            x=d["x"], y=d["y"], mode="markers", name="Rompiente", text=d["text"], hoverinfo="text",
            marker=dict(size=7, color=d["H"], colorscale="Turbo", cmin=0, cmax=cmax,
                        colorbar=dict(title="H (m)", thickness=12, len=0.6), line=dict(width=0))))
    c = costa()
    fig.add_trace(go.Scatter(x=c["x"], y=c["y"], mode="lines", line=dict(color="#ffeb3b", width=1.5),
                             hoverinfo="skip", name="Costa (OSM)"))
    if cuadricula:
        _cuadricula(fig, cuadricula)
    fig.update_layout(
        images=_imagenes(*vista, 18) if detalle else _imagenes(-6000, 2000, -3500, 3000, 15) + _imagenes(*VISTA, 16),
        template="plotly_dark", height=560 if detalle else 720, margin=dict(l=10, r=10, t=10, b=10),
        legend=dict(orientation="h", y=0.01, x=0.01, bgcolor="rgba(0,0,0,0.4)"),
        xaxis=dict(range=vista[:2], showgrid=False, zeroline=False, visible=False),
        yaxis=dict(range=vista[2:], showgrid=False, zeroline=False, visible=False, scaleanchor="x"),
        dragmode="pan",
    )
    return fig


def _cuadricula(fig, paso):
    """Cuadrícula con letras (columnas) y números (filas) para anotar profundidades a mano."""
    x0, x1, y0, y1 = VISTA
    cols = np.arange(np.ceil(x0 / paso) * paso, x1, paso)
    rows = np.arange(np.floor(y1 / paso) * paso, y0, -paso)
    for x in cols:
        fig.add_shape(type="line", x0=x, x1=x, y0=y0, y1=y1, line=dict(color="rgba(255,255,255,0.5)", width=1))
    for y in rows:
        fig.add_shape(type="line", x0=x0, x1=x1, y0=y, y1=y, line=dict(color="rgba(255,255,255,0.5)", width=1))
    for i, x in enumerate(cols[:-1]):
        fig.add_annotation(x=x + paso / 2, y=y1, text=chr(65 + i), showarrow=False, yanchor="top",
                           font=dict(color="white", size=14))
    for j, y in enumerate(rows[:-1]):
        fig.add_annotation(x=x0, y=y - paso / 2, text=str(j + 1), showarrow=False, xanchor="left",
                           font=dict(color="white", size=14))


def perfil(p: pd.DataFrame, simple: tuple[float, float] | None = None) -> go.Figure:
    fig = go.Figure()
    for lado, color in LADO_COLOR.items():
        q = p[(p["lado"] == lado) & (p["H"] > 0)]
        if not q.empty:
            fig.add_trace(go.Bar(x=q["s"], y=q["H"], name=lado or "sin dato", marker_color=color,
                                 hovertemplate="%{x:.0f} m: %{y:.1f} m<extra>" + (lado or "") + "</extra>"))
    if simple:
        fig.add_hrect(y0=simple[0], y1=simple[1], fillcolor="#43a047", opacity=0.15, line_width=0,
                      annotation_text="pronóstico simple", annotation_position="top left")
    for a, b, n in ZONAS:
        fig.add_vline(x=a, line=dict(color="#9e9e9e", width=1, dash="dot"))
        fig.add_annotation(x=(a + b) / 2, y=1.04, yref="paper", text=n, showarrow=False, font=dict(size=11))
    fig.update_layout(height=320, template="plotly_white", barmode="overlay", bargap=0.05,
                      margin=dict(l=50, r=10, t=40, b=40), legend=dict(orientation="h", y=-0.25),
                      xaxis_title="Distancia a lo largo de la costa desde la punta (m) — norte ← → sureste",
                      yaxis_title="Altura de rompiente (m)")
    return fig


def _resumen_zonas(p: pd.DataFrame) -> str:
    rows = []
    for a, b, n in ZONAS:
        q = p[(p["s"] >= a) & (p["s"] < b) & (p["H"] > 0)]
        if q.empty:
            rows.append(f"<tr><td>{n}</td><td colspan='2'>sin ola (sombra)</td></tr>")
            continue
        lado = q["lado"].value_counts().idxmax()
        rows.append(f"<tr><td>{n}</td><td>{q['H'].min():.1f}–{q['H'].max():.1f} m</td>"
                    f"<td><span style='color:{LADO_COLOR[lado]}'>●</span> {lado} "
                    f"({q['angulo'].median():+.0f}°)</td></tr>")
    return ("<table><thead><tr><th>Zona</th><th>Rompiente</th><th>Hacia dónde abre</th></tr></thead><tbody>"
            + "".join(rows) + "</tbody></table>")


def _nota() -> str:
    return f"""<p class="note"><b>Cómo leerlo:</b> cada punto es donde rompe un rayo de ola (color = altura). El lado
es hacia dónde abre la ola visto por el surfista, según el ángulo entre la ola y el fondo en la rompiente
(menos de 5° = cierra). Las profundidades incluyen la marea del momento (tus profundidades se toman a marea
media); en rojo, el fondo que la marea deja descubierto, y en amarillo el que aflora en el seno de la ola
(menos de ~0.35 veces la altura de rompiente bajo el nivel del agua). <b>Limitaciones:</b> la batimetría es
{"una mezcla de tus profundidades y " if BATI_USUARIO_FILE.exists() else ""}un perfil de equilibrio sintético
(Dean) que no conoce bancos de arena ni la forma real de la roca; no hay difracción, así que detrás de la punta
la ola real es algo mayor que la simulada. {escape(IMAGEN_ATRIBUCION)}.</p>"""


def _pagina(body: str, extra_css: str = "") -> str:
    return f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Simulación · {escape(config.SPOT_NAME)}</title>
<style>
 body {{ font-family: system-ui, Segoe UI, sans-serif; margin: 0 auto; max-width: 1200px; padding: 16px; color: #212121; background: #fafafa; }}
 h1 {{ margin-bottom: 0; }} .sub {{ color: #616161; margin-top: 4px; }}
 table {{ border-collapse: collapse; background: white; margin: 12px 0; font-size: 15px; }}
 th, td {{ padding: 6px 12px; border-bottom: 1px solid #e0e0e0; text-align: left; }} th {{ background: #eceff1; }}
 .note {{ font-size: 13px; color: #616161; }} .comp {{ margin: 8px 0; }}
 @media (max-width: 700px) {{ body {{ padding: 10px; }} table {{ font-size: 14px; width: 100%; }} }}
{extra_css}
</style>
<script>{get_plotlyjs()}</script><script>{PLOTLY_LOCALE_JS}</script></head><body>
{body}
</body></html>"""


def write_html(path: Path, titulo: str, componentes: list[dict], p: pd.DataFrame | None, fig_mapa: go.Figure,
               simple: tuple[float, float] | None = None, extra_html: str = "", marea_txt: str = "",
               fig_punta: go.Figure | None = None) -> Path:
    cfg = {"responsive": True, "displaylogo": False, "scrollZoom": True, "locale": "es"}
    comp_html = "".join(f"<li>{escape(c['nombre'])}: {c['altura']:.1f} m · {c['periodo']:.0f} s · "
                        f"desde {c['direccion']:.0f}°</li>" for c in componentes)
    body = [f"<h1>🏄 {escape(titulo)}</h1>",
            f"<p class='sub'>Simulación de oleaje sobre la playa · generada {dia_hora(ahora())}</p>"]
    if componentes:
        body.append(f"<ul class='comp'>{comp_html}"
                    + (f"<li>Marea: {escape(marea_txt)}</li>" if marea_txt else "") + "</ul>")
    if p is not None:
        body += [_resumen_zonas(p), "<h2>Altura y lado a lo largo de la costa</h2>",
                 perfil(p, simple).to_html(full_html=False, include_plotlyjs=False, config=cfg)]
    if fig_punta is not None:
        body += ["<h2>La Punta (acercamiento)</h2>",
                 fig_punta.to_html(full_html=False, include_plotlyjs=False, config=cfg)]
    body += ["<h2>Mapa</h2>", fig_mapa.to_html(full_html=False, include_plotlyjs=False, config=cfg), extra_html,
             _nota()]
    html = _pagina("".join(body))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")
    return path


# Al cambiar de momento solo se actualizan los datos (tabla, perfil, puntos de rompiente y fondo expuesto);
# las imágenes satelitales y las curvas de profundidad se cargan una vez.
PRONOSTICO_JS = """
(function () {
  const ESC = __ESC__, CFG = __CFG__;
  const sel = document.getElementById('momento');
  function capa(gd, name) { return gd.data.findIndex(t => t.name === name); }
  function show(i) {
    const e = ESC[i];
    sel.value = i;
    document.getElementById('info').innerHTML = e.info;
    document.getElementById('zonas').innerHTML = e.tabla;
    Plotly.react('perfil', e.perfil.data, e.perfil.layout, CFG);
    for (const [id, k] of [['mapa-punta', 'p'], ['mapa-general', 'g']]) {
      const gd = document.getElementById(id), d = e[k];
      Plotly.restyle(gd, {x: [d.x], y: [d.y], text: [d.text], 'marker.color': [d.H]}, [capa(gd, 'Rompiente')]);
      Plotly.restyle(gd, {z: [d.z]}, [capa(gd, 'Fondo expuesto')]);
    }
    try { history.replaceState(null, '', '#' + e.id); } catch (err) {}
  }
  sel.addEventListener('change', () => show(+sel.value));
  document.getElementById('prev').addEventListener('click', () => show(Math.max(0, +sel.value - 1)));
  document.getElementById('next').addEventListener('click', () => show(Math.min(ESC.length - 1, +sel.value + 1)));
  const fromHash = ESC.findIndex(e => '#' + e.id === location.hash);
  show(fromHash >= 0 ? fromHash : __INICIAL__);
})();
"""


def _z_json(z):
    return [[None if np.isnan(v) else int(v) for v in row] for row in z]


def write_pronostico(path: Path, escenarios: list[dict], inicial: int) -> Path:
    """Página con la simulación de varios momentos del pronóstico y un selector para pasar de uno a otro.

    Cada escenario: t, etiqueta, comps, marea, marea_txt, perfil, rompientes, ola, simple, rating.
    """
    import json
    cfg = {"responsive": True, "displaylogo": False, "scrollZoom": True, "locale": "es"}
    h_max = max(2.5, max(float(e["rompientes"]["H"].quantile(0.95)) for e in escenarios if not e["rompientes"].empty))
    e0 = escenarios[inicial]
    figs = {k: mapa(e0["rompientes"], None, marea=e0["marea"], ola=e0["ola"], detalle=(k == "p"), h_max=h_max,
                    siempre=True) for k in ("p", "g")}
    data = []
    for e in escenarios:
        comps = " · ".join(f"{c['nombre']} {c['altura']:.1f} m {c['periodo']:.0f} s desde {c['direccion']:.0f}°"
                           for c in e["comps"]) or "sin swell significativo"
        info = (f"<b>{escape(dia_hora(e['t']))}</b> · {'★' * e['rating']}{'☆' * (5 - e['rating'])} · "
                f"{escape(comps)} · Marea {escape(e['marea_txt'])}"
                + (f" · Pronóstico simple {e['simple'][0]:.1f}–{e['simple'][1]:.1f} m" if e["simple"] else ""))
        item = {"id": f"{e['t']:%Y%m%d-%H}", "info": info, "tabla": _resumen_zonas(e["perfil"]),
                "perfil": json.loads(perfil(e["perfil"], e["simple"]).to_json())}
        for k, vista in (("p", VISTA_PUNTA), ("g", VISTA)):
            d = rompientes_datos(e["rompientes"], vista)
            _x, _y, z = expuesto_datos(e["marea"], e["ola"], vista, paso=1 if k == "p" else 2)
            item[k] = {**d, "z": _z_json(z)}
        data.append(item)

    options = "".join(f"<option value='{i}'>{escape(e['etiqueta'])}</option>" for i, e in enumerate(escenarios))
    js = (PRONOSTICO_JS.replace("__ESC__", json.dumps(data, ensure_ascii=False, separators=(",", ":")))
          .replace("__CFG__", json.dumps(cfg)).replace("__INICIAL__", str(inicial)))
    body = f"""<h1>🏄 Simulación del pronóstico · {escape(config.SPOT_NAME)}</h1>
<p class="sub">Generada {dia_hora(ahora())} · <a href="./">volver al pronóstico</a></p>
<div class="selector"><button id="prev" aria-label="Anterior">◀</button>
<select id="momento" aria-label="Momento">{options}</select><button id="next" aria-label="Siguiente">▶</button></div>
<p id="info" class="comp"></p>
<div id="zonas"></div>
<h2>Altura y lado a lo largo de la costa</h2>
<div id="perfil" style="height:320px"></div>
<h2>La Punta (acercamiento)</h2>
{figs["p"].to_html(full_html=False, include_plotlyjs=False, config=cfg, div_id="mapa-punta")}
<h2>Mapa</h2>
{figs["g"].to_html(full_html=False, include_plotlyjs=False, config=cfg, div_id="mapa-general")}
{_nota()}
<script>{js}</script>"""
    css = """ .selector { display: flex; gap: 8px; align-items: center; margin: 12px 0; position: sticky; top: 0;
   background: #fafafa; padding: 6px 0; z-index: 10; }
 .selector select { font: inherit; padding: 8px; border-radius: 8px; border: 1px solid #bdbdbd; flex: 1; max-width: 420px; }
 .selector button { font: inherit; padding: 8px 14px; border-radius: 8px; border: 0; background: #0277bd; color: white; }"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_pagina(body, css), encoding="utf-8")
    return path
