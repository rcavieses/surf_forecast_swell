"""Genera el reporte HTML interactivo (Plotly) y la salida en terminal."""

from html import escape
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
from plotly.offline import get_plotlyjs
from plotly.subplots import make_subplots

from . import config
from .fechas import PLOTLY_LOCALE_JS, ahora, dia, dia_hora
from .surf import M_TO_FT, compass

RATING_COLORS = ["#9e9e9e", "#e57373", "#ffb74d", "#fff176", "#81c784", "#2e7d32"]
WIND_COLORS = {"offshore": "#2e7d32", "calma": "#66bb6a", "cruzado": "#ffa726", "onshore": "#e53935"}


def _night_shapes(fig, df: pd.DataFrame, daily: pd.DataFrame):
    start, end = df.index.min(), df.index.max()
    prev_sunset = start
    for _, row in daily.iterrows():
        if row["sunrise"] > prev_sunset:
            fig.add_vrect(x0=prev_sunset, x1=min(row["sunrise"], end), fillcolor="#263238",
                          opacity=0.12, line_width=0, layer="below")
        prev_sunset = row["sunset"]
    if prev_sunset < end:
        fig.add_vrect(x0=prev_sunset, x1=end, fillcolor="#263238", opacity=0.12, line_width=0, layer="below")


def build_figure(df: pd.DataFrame, daily: pd.DataFrame) -> go.Figure:
    fig = make_subplots(
        rows=4, cols=1, shared_xaxes=True, vertical_spacing=0.05,
        row_heights=[0.34, 0.26, 0.22, 0.18],
        subplot_titles=(
            "Altura de ola en la rompiente (pies) – color = calificación",
            "Swells mar adentro: altura (m) y periodo (s)",
            "Viento (km/h) – flecha indica hacia dónde sopla",
            "Nivel del mar / marea (m, modelo)",
        ),
        specs=[[{}], [{"secondary_y": True}], [{}], [{}]],
    )

    hover = [
        f"<b>{dia_hora(t)}</b><br>Surf: {r.surf_min_ft:.1f}-{r.surf_max_ft:.1f} ft "
        f"({r.surf_min_m:.1f}-{r.surf_max_m:.1f} m)<br>"
        f"{r.main_source}: {r.main_period:.0f}s {compass(r.main_direction)} · {r.lado}<br>"
        f"Viento: {r.wind_speed_10m:.0f} km/h {compass(r.wind_direction_10m)} ({r.wind_kind})<br>"
        f"Calificación: {r.rating_label}"
        for t, r in df.iterrows()
    ]
    fig.add_trace(go.Bar(
        x=df.index, y=df["surf_max_ft"] - df["surf_min_ft"], base=df["surf_min_ft"],
        marker_color=[RATING_COLORS[r] for r in df["rating"]], marker_line_width=0,
        hovertext=hover, hoverinfo="text", name="Surf", showlegend=False,
    ), row=1, col=1)
    if "surf_m_gfs" in df:
        # Mismo punto del rango (centro) para comparar ambos modelos.
        fig.add_trace(go.Scatter(
            x=df.index, y=df["surf_m_gfs"] * 0.95 * M_TO_FT, name="Modelo GFS (centro, ft)", mode="lines",
            line=dict(color="#37474f", width=1.5, dash="dot"),
            hovertemplate="GFS: %{y:.1f} ft<extra></extra>",
        ), row=1, col=1)

    for col, per, name, color in [
        ("swell_wave_height", "swell_wave_period", "Swell 1", "#1565c0"),
        ("secondary_swell_wave_height", "secondary_swell_wave_period", "Swell 2", "#00897b"),
        ("wind_wave_height", "wind_wave_period", "Mar de viento", "#8d6e63"),
    ]:
        fig.add_trace(go.Scatter(x=df.index, y=df[col], name=f"{name} (m)", line=dict(color=color, width=2)),
                      row=2, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df[per], name=f"{name} periodo (s)",
                                 line=dict(color=color, width=1, dash="dot")),
                      row=2, col=1, secondary_y=True)

    fig.add_trace(go.Scatter(x=df.index, y=df["wind_gusts_10m"], name="Rachas", line=dict(color="#bdbdbd", width=1),
                             fill=None), row=3, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df["wind_speed_10m"], name="Viento", line=dict(color="#546e7a", width=2)),
                  row=3, col=1)
    arrows = df.iloc[::3]
    fig.add_trace(go.Scatter(
        x=arrows.index, y=arrows["wind_speed_10m"], mode="markers", showlegend=False, hoverinfo="skip",
        marker=dict(symbol="arrow", size=11, angle=(arrows["wind_direction_10m"] + 180) % 360,
                    color=[WIND_COLORS[k] for k in arrows["wind_kind"]]),
    ), row=3, col=1)

    fig.add_trace(go.Scatter(x=df.index, y=df["sea_level_height_msl"], name="Marea",
                             line=dict(color="#0277bd", width=2), fill="tozeroy",
                             fillcolor="rgba(2,119,189,0.15)"), row=4, col=1)

    _night_shapes(fig, df, daily)
    fig.add_vline(x=ahora(), line_dash="dash", line_color="#d32f2f")
    fig.update_yaxes(title_text="ft", row=1, col=1, rangemode="tozero")
    fig.update_yaxes(title_text="m", row=2, col=1, rangemode="tozero")
    fig.update_yaxes(title_text="s", row=2, col=1, secondary_y=True, rangemode="tozero", showgrid=False)
    fig.update_yaxes(title_text="km/h", row=3, col=1, rangemode="tozero")
    fig.update_yaxes(title_text="m", row=4, col=1)
    fig.update_xaxes(tickformat="%a %d<br>%H:%M", dtick=12 * 3600 * 1000)
    fig.update_layout(height=1100, template="plotly_white", hovermode="closest",
                      legend=dict(orientation="h", y=-0.05), margin=dict(l=60, r=40, t=60, b=40), bargap=0.05)
    return fig


SUMMARY_COLUMNS = ["Día", "Surf", "Periodo", "Dir. swell", "Lado", "Mejores horas", "Viento 6-10h",
                   "Viento 13-17h", "Confianza", "Calificación"]

# En pantallas angostas: tabla -> tarjetas, y la gráfica se compacta (márgenes, ticks por día, sin zoom
# por arrastre para que el dedo pueda desplazar la página).
MOBILE_JS = """
(function () {
  var gd = document.getElementById('{plot_id}');
  var axes = ['xaxis', 'xaxis2', 'xaxis3', 'xaxis4'];
  var last = null;
  function fit() {
    var m = window.innerWidth < 700;
    if (m === last) return;
    last = m;
    var u = {
      height: m ? 950 : 1100, dragmode: m ? false : 'zoom', 'font.size': m ? 10 : 12,
      'margin.l': m ? 36 : 60, 'margin.r': m ? 8 : 40, 'margin.t': m ? 40 : 60,
      'legend.font.size': m ? 10 : 12, 'hoverlabel.font.size': m ? 11 : 13
    };
    axes.forEach(function (a) {
      u[a + '.dtick'] = m ? 86400000 : 43200000;
      u[a + '.tickformat'] = m ? '%a %d' : '%a %d<br>%H:%M';
    });
    (gd.layout.annotations || []).forEach(function (_, i) { u['annotations[' + i + '].font.size'] = m ? 11 : 16; });
    Plotly.relayout(gd, u);
  }
  fit();
  window.addEventListener('resize', fit);
})();
"""


def _summary_html(summary: pd.DataFrame) -> str:
    rows = []
    for day, r in summary.iterrows():
        color = RATING_COLORS[r["calif_max"]]
        cells = [
            dia(day), f"<b>{r['surf_ft']} ft</b> ({r['surf_m']} m)", f"{r['periodo_s']} s",
            r["dir_swell"], r["lado"], r["mejores_horas"], r["viento_mañana"], r["viento_tarde"], r["confianza"],
            f"{'★' * r['calif_max']}{'☆' * (5 - r['calif_max'])} {escape(r['calif'])}",
        ]
        tds = [f"<td data-label='{label}'><span>{cell}</span></td>" for label, cell in zip(SUMMARY_COLUMNS, cells)]
        tds[-1] = tds[-1].replace("<td ", f"<td style='background:{color}' ", 1)
        rows.append("<tr>" + "".join(tds) + "</tr>")
    return (
        "<table class='resumen'><thead><tr>" + "".join(f"<th>{c}</th>" for c in SUMMARY_COLUMNS)
        + "</tr></thead><tbody>" + "".join(rows) + "</tbody></table>"
    )


def _webcam_html() -> str:
    if not config.WEBCAM_EMBED_URL:
        return ""
    site = f"<a href='{escape(config.WEBCAM_CREDIT_URL)}' target='_blank' rel='noopener'>{escape(config.WEBCAM_CREDIT_NAME)}</a>"
    operator = (f"<a href='{escape(config.WEBCAM_OPERATOR_URL)}' target='_blank' rel='noopener'>"
                f"{escape(config.WEBCAM_OPERATOR_NAME)}</a>")
    return f"""<h2>Webcam en vivo</h2>
<div class="cam"><iframe src="{escape(config.WEBCAM_EMBED_URL)}" title="Webcam de {escape(config.SPOT_NAME)}"
 loading="lazy" allow="autoplay; fullscreen" allowfullscreen scrolling="no"></iframe></div>
<p class="credit">Webcam cortesía de {site} ({escape(config.WEBCAM_CREDIT_URL.split("//")[1].strip("/"))}),
operada por {operator}. Si no carga, ábrela en su sitio ↗ {site}.</p>"""


def _calibration_note() -> str:
    c = config.CALIBRATION
    if not c:
        return ", sin calibrar"
    n = c.get("n_obs", 0)
    origin = f"{n} {'observaciones' if n != 1 else 'observación'}" if n else "valor manual"
    return f", calibrado con {origin} el {c['actualizado'][:10]}"


def write_html(df: pd.DataFrame, daily: pd.DataFrame, summary: pd.DataFrame, path: Path) -> Path:
    fig = build_figure(df, daily)
    # Plotly va incrustado (el reporte funciona sin internet) con el idioma registrado antes de dibujar.
    chart = f"<script>{get_plotlyjs()}</script><script>{PLOTLY_LOCALE_JS}</script>" + fig.to_html(
        full_html=False, include_plotlyjs=False, post_script=MOBILE_JS,
        config={"responsive": True, "displaylogo": False, "scrollZoom": False, "locale": "es"})
    html = f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Surf {escape(config.SPOT_NAME)}</title>
<style>
 body {{ font-family: system-ui, Segoe UI, sans-serif; margin: 0 auto; max-width: 1300px; padding: 16px; color: #212121; background: #fafafa; }}
 h1 {{ margin-bottom: 0; }} .sub {{ color: #616161; margin-top: 4px; }}
 table {{ border-collapse: collapse; width: 100%; background: white; margin: 16px 0; font-size: 15px; }}
 th, td {{ padding: 8px 10px; border-bottom: 1px solid #e0e0e0; text-align: left; }}
 th {{ background: #eceff1; }}
 .note {{ font-size: 13px; color: #757575; }}
 /* 16:9 del video + ~36px de la barra inferior del reproductor */
 .cam {{ position: relative; width: 100%; max-width: 900px; padding-bottom: min(calc(56.25% + 36px), 542px); background: #000; border-radius: 8px; overflow: hidden; }}
 .cam iframe {{ position: absolute; inset: 0; width: 100%; height: 100%; border: 0; }}
 .credit {{ font-size: 13px; color: #616161; margin: 6px 0 16px; }}
 .credit a {{ color: #0277bd; }}
 @media (max-width: 700px) {{
  body {{ padding: 10px; }}
  h1 {{ font-size: 1.5rem; }} h2 {{ font-size: 1.15rem; }} .sub {{ font-size: 13px; }}
  table.resumen, table.resumen tbody, table.resumen tr, table.resumen td {{ display: block; width: 100%; box-sizing: border-box; }}
  table.resumen {{ background: none; font-size: 14px; }}
  table.resumen thead {{ display: none; }}
  table.resumen tr {{ background: white; border: 1px solid #e0e0e0; border-radius: 10px; margin-bottom: 10px; overflow: hidden; }}
  table.resumen td {{ display: flex; justify-content: space-between; gap: 12px; padding: 6px 12px; border-bottom: 1px solid #f0f0f0; text-align: right; }}
  table.resumen td::before {{ content: attr(data-label); font-weight: 600; color: #616161; text-align: left; }}
  table.resumen td:first-child {{ background: #eceff1; font-weight: 700; }}
  table.resumen td:first-child::before {{ content: none; }}
  table.resumen td:last-child {{ border-bottom: none; }}
 }}
</style></head><body>
<h1>🏄 {escape(config.SPOT_NAME)}</h1>
<p class="sub">Generado {dia_hora(ahora())} (hora local) · Datos: Open-Meteo (modelos de oleaje y viento) ·
Punto {config.LATITUDE}, {config.LONGITUDE} · Playa orientada a {config.BEACH_NORMAL_DEG}° ({compass(config.BEACH_NORMAL_DEG)})</p>
{_webcam_html()}
<h2>Resumen diario (horas de luz)</h2>
{_summary_html(summary)}
{chart}
<p class="note">La altura de surf es una estimación de la ola en la rompiente (Komar &amp; Gaughan) ajustada por la
orientación de la playa y un factor de sitio ({config.SITE_FACTOR}{_calibration_note()}). Registra lo que veas en el
agua con <code>python observar.py agregar</code> y ajusta el factor con <code>python observar.py calibrar</code>.
<b>Lado</b>: hacia dónde abre la ola según el ángulo del swell con la playa (los bancos de arena pueden cambiarlo).
<b>Confianza</b>: qué tanto coincide la altura con un segundo modelo (GFS, línea punteada).
Zonas sombreadas = noche.</p>
</body></html>"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")
    return path


def print_terminal(df: pd.DataFrame, summary: pd.DataFrame, step_hours: int = 3):
    print(f"\n=== {config.SPOT_NAME} – resumen diario (horas de luz) ===\n")
    print(summary.drop(columns="calif_max").set_axis(summary.index.map(dia)).to_string())

    now = ahora().floor("h")
    near = df[(df.index >= now) & (df.index < now + pd.Timedelta(hours=48))].iloc[::step_hours]
    near = near.set_axis(near.index.map(dia_hora))
    table = pd.DataFrame({
        "surf (ft)": [f"{a:.1f}-{b:.1f}" for a, b in zip(near["surf_min_ft"], near["surf_max_ft"])],
        "surf (m)": [f"{a:.1f}-{b:.1f}" for a, b in zip(near["surf_min_m"], near["surf_max_m"])],
        "periodo": near["main_period"].map(lambda v: f"{v:.0f}s"),
        "dir": near["main_direction"].map(compass),
        "lado": near["lado"],
        "viento": [f"{s:.0f} km/h {compass(d)}" for s, d in zip(near["wind_speed_10m"], near["wind_direction_10m"])],
        "tipo": near["wind_kind"],
        "marea": near["sea_level_height_msl"].map(lambda v: f"{v:+.2f} m"),
        "calif": near["rating"].map(lambda r: "★" * r + "·" * (5 - r)),
    }, index=near.index)
    print(f"\n=== Próximas 48 h (cada {step_hours} h) ===\n")
    print(table.to_string())
