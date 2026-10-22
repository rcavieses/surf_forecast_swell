"""Genera el reporte HTML interactivo (Plotly) y la salida en terminal."""

from datetime import datetime
from html import escape
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from . import config
from .surf import compass

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
        f"<b>{t:%a %d %H:%M}</b><br>Surf: {r.surf_min_ft:.1f}-{r.surf_max_ft:.1f} ft "
        f"({r.surf_min_m:.1f}-{r.surf_max_m:.1f} m)<br>"
        f"{r.main_source}: {r.main_period:.0f}s {compass(r.main_direction)}<br>"
        f"Viento: {r.wind_speed_10m:.0f} km/h {compass(r.wind_direction_10m)} ({r.wind_kind})<br>"
        f"Calificación: {r.rating_label}"
        for t, r in df.iterrows()
    ]
    fig.add_trace(go.Bar(
        x=df.index, y=df["surf_max_ft"] - df["surf_min_ft"], base=df["surf_min_ft"],
        marker_color=[RATING_COLORS[r] for r in df["rating"]], marker_line_width=0,
        hovertext=hover, hoverinfo="text", name="Surf", showlegend=False,
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
    fig.add_vline(x=datetime.now(), line_dash="dash", line_color="#d32f2f")
    fig.update_yaxes(title_text="ft", row=1, col=1, rangemode="tozero")
    fig.update_yaxes(title_text="m", row=2, col=1, rangemode="tozero")
    fig.update_yaxes(title_text="s", row=2, col=1, secondary_y=True, rangemode="tozero", showgrid=False)
    fig.update_yaxes(title_text="km/h", row=3, col=1, rangemode="tozero")
    fig.update_yaxes(title_text="m", row=4, col=1)
    fig.update_xaxes(tickformat="%a %d\n%H:%M", dtick=6 * 3600 * 1000)
    fig.update_layout(height=1100, template="plotly_white", hovermode="closest",
                      legend=dict(orientation="h", y=-0.05), margin=dict(l=60, r=40, t=60, b=40), bargap=0.05)
    return fig


def _summary_html(summary: pd.DataFrame) -> str:
    rows = []
    for day, r in summary.iterrows():
        color = RATING_COLORS[r["calif_max"]]
        rows.append(
            f"<tr><td>{pd.Timestamp(day):%a %d %b}</td><td><b>{r['surf_ft']} ft</b> ({r['surf_m']} m)</td>"
            f"<td>{r['periodo_s']} s</td><td>{r['dir_swell']}</td><td>{r['mejor_hora']}</td>"
            f"<td>{r['viento_mañana']}</td><td>{r['viento_tarde']}</td>"
            f"<td style='background:{color}'>{'★' * r['calif_max']}{'☆' * (5 - r['calif_max'])} {escape(r['calif'])}</td></tr>"
        )
    return (
        "<table><thead><tr><th>Día</th><th>Surf</th><th>Periodo</th><th>Dir. swell</th><th>Mejor hora</th>"
        "<th>Viento 6-10h</th><th>Viento 13-17h</th><th>Calificación</th></tr></thead><tbody>"
        + "".join(rows) + "</tbody></table>"
    )


def write_html(df: pd.DataFrame, daily: pd.DataFrame, summary: pd.DataFrame, path: Path) -> Path:
    fig = build_figure(df, daily)
    chart = fig.to_html(full_html=False, include_plotlyjs=True)
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
</style></head><body>
<h1>🏄 {escape(config.SPOT_NAME)}</h1>
<p class="sub">Generado {datetime.now():%Y-%m-%d %H:%M} · Datos: Open-Meteo (modelos de oleaje y viento) ·
Punto {config.LATITUDE}, {config.LONGITUDE} · Playa orientada a {config.BEACH_NORMAL_DEG}° ({compass(config.BEACH_NORMAL_DEG)})</p>
<h2>Resumen diario (horas de luz)</h2>
{_summary_html(summary)}
{chart}
<p class="note">La altura de surf es una estimación de la ola en la rompiente (Komar &amp; Gaughan) ajustada por la
orientación de la playa y un factor de sitio ({config.SITE_FACTOR}). Calibra <code>SITE_FACTOR</code> en
<code>surf_forecast/config.py</code> comparando con lo que observes en el agua. Zonas sombreadas = noche.</p>
</body></html>"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")
    return path


def print_terminal(df: pd.DataFrame, summary: pd.DataFrame, step_hours: int = 3):
    print(f"\n=== {config.SPOT_NAME} – resumen diario (horas de luz) ===\n")
    print(summary.drop(columns="calif_max").to_string())

    now = pd.Timestamp.now().floor("h")
    near = df[(df.index >= now) & (df.index < now + pd.Timedelta(hours=48))].iloc[::step_hours]
    near = near.set_axis(near.index.strftime("%a %d %H:%M"))
    table = pd.DataFrame({
        "surf (ft)": [f"{a:.1f}-{b:.1f}" for a, b in zip(near["surf_min_ft"], near["surf_max_ft"])],
        "surf (m)": [f"{a:.1f}-{b:.1f}" for a, b in zip(near["surf_min_m"], near["surf_max_m"])],
        "periodo": near["main_period"].map(lambda v: f"{v:.0f}s"),
        "dir": near["main_direction"].map(compass),
        "viento": [f"{s:.0f} km/h {compass(d)}" for s, d in zip(near["wind_speed_10m"], near["wind_direction_10m"])],
        "tipo": near["wind_kind"],
        "marea": near["sea_level_height_msl"].map(lambda v: f"{v:+.2f} m"),
        "calif": near["rating"].map(lambda r: "★" * r + "·" * (5 - r)),
    }, index=near.index)
    print(f"\n=== Próximas 48 h (cada {step_hours} h) ===\n")
    print(table.to_string())
