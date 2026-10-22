"""Geometría de Playa Cerritos: línea de costa, batimetría (sintética o dibujada) e imagen satelital.

Coordenadas locales en metros: x hacia el este, y hacia el norte, con origen en la punta rocosa
(Hacienda Cerritos), donde termina la costa de roca y empieza la playa de arena hacia el SE.
"""

import hashlib
import json
import math
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
PLAYA_DIR = ROOT / "data" / "playa"
COSTA_FILE = PLAYA_DIR / "costa.json"              # de OpenStreetMap (© colaboradores de OSM, ODbL)
BATI_USUARIO_FILE = PLAYA_DIR / "batimetria_usuario.csv"
CACHE_DIR = ROOT / "data" / "cache"

ORIGEN = (23.3289, -110.1790)  # punta de Hacienda Cerritos (lat, lon)
DOMINIO = (-6000.0, 2000.0, -3500.0, 3000.0)  # x0, x1, y0, y1 (m)
RESOLUCION = 12.0  # m por celda

# Tramos de roca (de la imagen satelital), entre dos puntos de la costa: de Punta Pescadero al rincón
# interior de la punta de Hacienda Cerritos, donde empieza la arena. El resto es arena.
TRAMOS_ROCA = [((23.3378, -110.1854), (23.3300, -110.1777))]
ROCA_ALCANCE = 150.0  # m: distancia a la que se desvanece la pendiente de roca mar adentro
VERSION = 5  # súbelo al cambiar el cálculo, para invalidar la caché de la batimetría
# Perfil de equilibrio de Dean: h = A · d^(2/3) (d = distancia a la orilla, m). En la arena, A = 0.08 da los
# ~2.5 m a ~200 m de la orilla que observaste junto a la punta; la costa de roca cae más rápido.
# PROF_MAX limita la profundidad del dominio (fuera se asume constante).
A_PERFIL = {"arena": 0.08, "roca": 0.25}
USUARIO_ALCANCE = 40.0  # m: distancia a la que tus puntos dejan de mandar sobre el perfil sintético
PROF_MAX = 30.0

IMAGEN_ATRIBUCION = "Imagen satelital: Esri, Maxar, Earthstar Geographics · Costa: © OpenStreetMap"
_TILE_URL = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
_UA = {"User-Agent": "cerritos-surf-forecast (proyecto personal)"}


# ---------------------------------------------------------------- coordenadas

def a_local(lat, lon):
    lat, lon = np.asarray(lat, dtype=float), np.asarray(lon, dtype=float)
    return ((lon - ORIGEN[1]) * 111_320 * math.cos(math.radians(ORIGEN[0])), (lat - ORIGEN[0]) * 110_540)


def a_latlon(x, y):
    x, y = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    return ORIGEN[0] + y / 110_540, ORIGEN[1] + x / (111_320 * math.cos(math.radians(ORIGEN[0])))


# ---------------------------------------------------------------- línea de costa

def descargar_costa() -> Path:
    """Baja la línea de costa de OpenStreetMap (una vez; el archivo queda en el repo)."""
    lat0, lon0 = a_latlon(DOMINIO[0] - 2000, DOMINIO[2] - 2000)
    lat1, lon1 = a_latlon(DOMINIO[1] + 2000, DOMINIO[3] + 2000)
    query = (f'[out:json][timeout:60];way["natural"="coastline"]({lat0:.4f},{lon0:.4f},{lat1:.4f},{lon1:.4f});'
             "out geom;")
    req = urllib.request.Request("https://overpass-api.de/api/interpreter",
                                 data=("data=" + urllib.parse.quote(query)).encode(), headers=_UA)
    ways = json.loads(urllib.request.urlopen(req, timeout=90).read())["elements"]
    # Se unen los tramos por sus extremos y se ordena de norte a sur (OSM: la tierra queda a la izquierda).
    segs = [[(p["lat"], p["lon"]) for p in w["geometry"]] for w in ways]
    line = segs.pop(0)
    while segs:
        for i, s in enumerate(segs):
            if s[0] == line[-1]:
                line += s[1:]
            elif s[-1] == line[0]:
                line = s[:-1] + line
            else:
                continue
            segs.pop(i)
            break
        else:
            break
    if line[0][0] < line[-1][0]:
        line.reverse()
    PLAYA_DIR.mkdir(parents=True, exist_ok=True)
    COSTA_FILE.write_text(json.dumps({"fuente": "OpenStreetMap (ODbL)", "puntos": line}), encoding="utf-8")
    return COSTA_FILE


def costa() -> pd.DataFrame:
    """Línea de costa de norte a sur con x, y, tipo (roca/arena) y s (m a lo largo de la costa, 0 = la punta)."""
    if not COSTA_FILE.exists():
        descargar_costa()
    pts = np.array(json.loads(COSTA_FILE.read_text(encoding="utf-8"))["puntos"])
    x, y = a_local(pts[:, 0], pts[:, 1])
    df = pd.DataFrame({"lat": pts[:, 0], "lon": pts[:, 1], "x": x, "y": y})
    # Solo el tramo que importa para el dominio (OSM devuelve decenas de km de costa).
    m = 3000
    df = df[df["y"].between(DOMINIO[2] - m, DOMINIO[3] + m) & df["x"].between(DOMINIO[0] - m, DOMINIO[1] + m)]
    df = df.reset_index(drop=True)
    s = np.concatenate([[0], np.cumsum(np.hypot(np.diff(df["x"]), np.diff(df["y"])))])
    df["s"] = s - s[np.argmin(np.hypot(df["x"], df["y"]))]  # positivo hacia el sur (la playa)
    df["tipo"] = "arena"
    for a, b in TRAMOS_ROCA:
        sa, sb = (s_de(df, *p) for p in (a, b))
        df.loc[df["s"].between(min(sa, sb), max(sa, sb)), "tipo"] = "roca"
    return df


def s_de(c: pd.DataFrame, lat: float, lon: float) -> float:
    """Posición a lo largo de la costa (s) del vértice más cercano a un punto."""
    x, y = a_local(lat, lon)
    return float(c["s"].iloc[np.argmin(np.hypot(c["x"] - x, c["y"] - y))])


def _proyectar_en_costa(px, py, c: pd.DataFrame):
    """Para cada punto: distancia mínima a la costa, s del punto más cercano y distancia a la costa de roca."""
    ax, ay = c["x"].to_numpy()[:-1], c["y"].to_numpy()[:-1]
    bx, by = c["x"].to_numpy()[1:], c["y"].to_numpy()[1:]
    s0, ls = c["s"].to_numpy()[:-1], np.hypot(bx - ax, by - ay)
    rock = (c["tipo"].to_numpy()[:-1] == "roca") & (c["tipo"].to_numpy()[1:] == "roca")
    dist = np.full(px.shape, np.inf)
    dist_rock = np.full(px.shape, np.inf)
    s_near = np.zeros(px.shape)
    for i in range(len(ax)):  # por segmento: vectorizado sobre los puntos
        t = np.clip(((px - ax[i]) * (bx[i] - ax[i]) + (py - ay[i]) * (by[i] - ay[i])) / max(ls[i] ** 2, 1e-9), 0, 1)
        d = np.hypot(px - (ax[i] + t * (bx[i] - ax[i])), py - (ay[i] + t * (by[i] - ay[i])))
        better = d < dist
        dist[better], s_near[better] = d[better], s0[i] + t[better] * ls[i]
        if rock[i]:
            np.minimum(dist_rock, d, out=dist_rock)
    return dist, s_near, dist_rock


def _en_tierra(px, py, c: pd.DataFrame):
    """Polígono de tierra: la costa (norte a sur) cerrada por el este, fuera del dominio."""
    east = max(c["x"].max(), DOMINIO[1]) + 5000
    poly = np.vstack([c[["x", "y"]].to_numpy(), [[east, c["y"].iloc[-1]], [east, c["y"].iloc[0]]]])
    inside = np.zeros(px.shape, dtype=bool)
    xj, yj = poly[-1]
    for xi, yi in poly:  # regla par-impar
        cross = ((yi > py) != (yj > py)) & (px < (xj - xi) * (py - yi) / ((yj - yi) or 1e-12) + xi)
        inside ^= cross
        xj, yj = xi, yi
    return inside


# ---------------------------------------------------------------- batimetría

def _suavizar(h, veces=3):
    for _ in range(veces):
        p = np.pad(h, 1, mode="edge")
        h = (p[:-2, :-2] + p[:-2, 1:-1] + p[:-2, 2:] + p[1:-1, :-2] + p[1:-1, 1:-1] + p[1:-1, 2:]
             + p[2:, :-2] + p[2:, 1:-1] + p[2:, 2:]) / 9
    return h


def _gauss(h, sigma_celdas):
    """Suavizado gaussiano separable (bordes replicados)."""
    r = int(3 * sigma_celdas)
    k = np.exp(-0.5 * (np.arange(-r, r + 1) / sigma_celdas) ** 2)
    k /= k.sum()
    p = np.pad(h, r, mode="edge")
    p = np.apply_along_axis(lambda v: np.convolve(v, k, mode="valid"), 1, p)
    return np.apply_along_axis(lambda v: np.convolve(v, k, mode="valid"), 0, p)


def batimetria_usuario() -> pd.DataFrame | None:
    """Puntos de profundidad dibujados por ti: columnas lat, lon, profundidad_m (o x_m, y_m, profundidad_m)."""
    if not BATI_USUARIO_FILE.exists():
        return None
    df = pd.read_csv(BATI_USUARIO_FILE, comment="#")
    if {"lat", "lon"} <= set(df.columns):
        df["x_m"], df["y_m"] = a_local(df["lat"], df["lon"])
    return df[["x_m", "y_m", "profundidad_m"]].dropna()


def batimetria() -> dict:
    """Malla de profundidad (m, positiva en el agua, 0 en tierra). Se guarda en caché mientras no cambien
    la costa ni tus puntos."""
    key = hashlib.md5((COSTA_FILE.read_bytes() if COSTA_FILE.exists() else b"")
                      + (BATI_USUARIO_FILE.read_bytes() if BATI_USUARIO_FILE.exists() else b"")
                      + json.dumps([VERSION, DOMINIO, RESOLUCION, A_PERFIL, PROF_MAX, TRAMOS_ROCA, ROCA_ALCANCE,
                                    USUARIO_ALCANCE])
                      .encode()).hexdigest()[:12]
    cache = CACHE_DIR / f"batimetria_{key}.npz"
    if cache.exists():
        z = np.load(cache)
        return {k: z[k] for k in z.files}

    c = costa()
    xs = np.arange(DOMINIO[0], DOMINIO[1] + RESOLUCION, RESOLUCION)
    ys = np.arange(DOMINIO[2], DOMINIO[3] + RESOLUCION, RESOLUCION)
    X, Y = np.meshgrid(xs, ys)
    dist, s_near, dist_rock = _proyectar_en_costa(X, Y, c)
    land = _en_tierra(X, Y, c)
    # Pendiente de roca solo donde la costa más cercana es roca, desvaneciéndose mar adentro; el coeficiente
    # se suaviza para que la transición roca-arena no deje un pozo frente a la playa.
    w_rock = np.exp(-np.maximum(dist_rock - dist, 0) / 25) * np.exp(-dist / (4 * ROCA_ALCANCE))
    A = _suavizar(A_PERFIL["arena"] + (A_PERFIL["roca"] - A_PERFIL["arena"]) * w_rock, veces=12)
    h = np.minimum(A * dist ** (2 / 3), PROF_MAX)
    h = _suavizar(np.where(land, 0.0, h))
    # La distancia a la costa más cercana crea crestas y pozos artificiales frente a la punta; mar adentro
    # el fondo real es suave, así que ahí se usa una versión muy suavizada (σ ≈ 200 m).
    w_near = np.exp(-dist / 150)
    h = w_near * h + (1 - w_near) * _gauss(h, 200 / RESOLUCION)
    h[land] = 0.0

    user = batimetria_usuario()
    if user is not None and len(user):
        # Tus puntos mandan cerca de donde los pusiste (IDW); a más de ~USUARIO_ALCANCE queda el sintético.
        num = np.zeros_like(h)
        den = np.zeros_like(h)
        dmin = np.full(h.shape, np.inf)
        for ux, uy, uh in user.to_numpy():
            d = np.hypot(X - ux, Y - uy)
            w = 1 / np.maximum(d, RESOLUCION) ** 2
            num += w * uh
            den += w
            np.minimum(dmin, d, out=dmin)
        near = np.exp(-(dmin / USUARIO_ALCANCE) ** 2)
        h = np.where(land, 0.0, near * (num / den) + (1 - near) * h)

    out = {"x": xs, "y": ys, "h": h, "s": s_near, "tierra": land}
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(cache, **out)
    return out


# ---------------------------------------------------------------- imagen satelital

def _tile_xy(lat, lon, z):
    n = 2 ** z
    return (lon + 180) / 360 * n, (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n


def _tile_latlon(tx, ty, z):
    n = 2 ** z
    return math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * ty / n)))), tx / n * 360 - 180


def teselas(x0, x1, y0, y1, z) -> list[dict]:
    """Teselas de Esri World Imagery que cubren el rectángulo local (se guardan en data/cache, no en el repo)."""
    lat_s, lon_w = a_latlon(x0, y0)
    lat_n, lon_e = a_latlon(x1, y1)
    tx0, ty0 = _tile_xy(float(lat_n), float(lon_w), z)
    tx1, ty1 = _tile_xy(float(lat_s), float(lon_e), z)
    folder = CACHE_DIR / "teselas"
    folder.mkdir(parents=True, exist_ok=True)
    out = []
    for ty in range(int(ty0), int(ty1) + 1):
        for tx in range(int(tx0), int(tx1) + 1):
            f = folder / f"{z}_{tx}_{ty}.jpg"
            if not f.exists():
                req = urllib.request.Request(_TILE_URL.format(z=z, x=tx, y=ty), headers=_UA)
                f.write_bytes(urllib.request.urlopen(req, timeout=30).read())
            la_n, lo_w = _tile_latlon(tx, ty, z)
            la_s, lo_e = _tile_latlon(tx + 1, ty + 1, z)
            xw, yn = a_local(la_n, lo_w)
            xe, ys = a_local(la_s, lo_e)
            out.append({"archivo": f, "x0": float(xw), "x1": float(xe), "y0": float(ys), "y1": float(yn)})
    return out
