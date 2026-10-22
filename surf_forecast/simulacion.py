"""Propagación del oleaje sobre la batimetría de la playa con trazado de rayos (óptica geométrica).

Cada rayo sigue un tramo de la cresta: se refracta hacia donde la ola es más lenta (lo bajo), su altura
cambia por asomeramiento (Ks) y por la separación entre rayos vecinos (Kr), y rompe cuando H >= γ·h.
No incluye difracción: detrás de la punta los rayos no llegan y esa zona aparece como sombra.
"""

import math

import numpy as np
import pandas as pd

from . import config
from .playa import PROF_MAX, _proyectar_en_costa, batimetria, costa

G = 9.81
GAMMA = 0.78   # índice de rompiente H/h
KR_MAX = 2.5   # límite a la concentración de energía donde los rayos se cruzan (cáusticas)
N_RAYOS = 700
DT = 1.0       # s por paso


def onda(h, periodo):
    """Celeridad c y celeridad de grupo cg (m/s) para profundidad h. Aproximación explícita de la
    relación de dispersión (Fenton y McKee, error < 1 %)."""
    h = np.maximum(h, 0.05)
    L0 = G * periodo ** 2 / (2 * math.pi)
    L = L0 * np.tanh((2 * math.pi * np.sqrt(h / G) / periodo) ** 1.5) ** (2 / 3)
    kh = 2 * math.pi * h / L
    c = L / periodo
    return c, c / 2 * (1 + 2 * kh / np.sinh(np.minimum(2 * kh, 50)))


def _muestrear(grid, xs, ys, px, py):
    """Interpolación bilineal de una malla en puntos (fuera de la malla se usa el borde)."""
    dx, dy = xs[1] - xs[0], ys[1] - ys[0]
    fx = np.clip((px - xs[0]) / dx, 0, len(xs) - 1.001)
    fy = np.clip((py - ys[0]) / dy, 0, len(ys) - 1.001)
    i, j = fy.astype(int), fx.astype(int)
    ty, tx = fy - i, fx - j
    return (grid[i, j] * (1 - tx) * (1 - ty) + grid[i, j + 1] * tx * (1 - ty)
            + grid[i + 1, j] * (1 - tx) * ty + grid[i + 1, j + 1] * tx * ty)


def profundidad(marea: float = 0.0) -> dict:
    """Batimetría con la marea aplicada (m respecto a marea media). Lo que queda a 0 o menos está descubierto."""
    b = batimetria()
    h = np.where(b["tierra"], 0.0, np.maximum(b["h"] + marea, 0.0))
    return {**b, "h": h}


def propagar(altura, periodo, direccion, marea=0.0, guardar_cada=4) -> dict:
    """Simula un tren de olas mar adentro (altura m, periodo s, dirección de donde viene en grados) con el
    nivel de marea indicado (m respecto a marea media).

    Devuelve las rompientes (DataFrame) y las trayectorias de los rayos (para dibujar).
    """
    b = profundidad(marea)
    xs, ys, h = b["x"], b["y"], b["h"]
    c_grid, cg_grid = onda(np.where(h > 0, h, 0.05), periodo)
    dcy, dcx = np.gradient(c_grid, ys, xs)
    cg0 = G * periodo / (4 * math.pi)  # celeridad de grupo en aguas profundas

    # Fuera de la malla la profundidad es PROF_MAX; de aguas profundas a esa profundidad se aplica Snell
    # con contornos rectos paralelos a la playa (normal = BEACH_NORMAL_DEG).
    c_ext, cg_ext = onda(np.array(PROF_MAX), periodo)
    rel = math.radians((direccion - config.BEACH_NORMAL_DEG + 180) % 360 - 180)  # ángulo con la normal
    c0 = G * periodo / (2 * math.pi)
    rel_ext = math.asin(max(-0.999, min(0.999, math.sin(rel) * float(c_ext) / c0)))
    from_ext = config.BEACH_NORMAL_DEG + math.degrees(rel_ext)
    kr_ext = math.sqrt(max(math.cos(rel), 1e-3) / math.cos(rel_ext))
    h_start = altura * math.sqrt(cg0 / float(cg_ext)) * kr_ext

    # Ángulo matemático de propagación (desde el este, antihorario); "de donde viene" -> hacia donde va.
    phi0 = math.radians(90 - (from_ext + 180))
    ux, uy = math.cos(phi0), math.sin(phi0)
    cx, cy = (xs[0] + xs[-1]) / 2, (ys[0] + ys[-1]) / 2
    R = 0.5 * math.hypot(xs[-1] - xs[0], ys[-1] - ys[0])
    t = np.linspace(-R, R, N_RAYOS)
    x = cx - ux * R * 1.02 - uy * t
    y = cy - uy * R * 1.02 + ux * t
    phi = np.full(N_RAYOS, phi0)
    b0 = t[1] - t[0]
    active = np.ones(N_RAYOS, dtype=bool)
    broke = []
    paths = [[] for _ in range(N_RAYOS)]
    idx = np.arange(N_RAYOS)

    for step in range(int(4 * R / (float(c_ext) * DT)) + 200):
        if not active.any():
            break
        a = idx[active]
        hx = _muestrear(h, xs, ys, x[a], y[a])
        inside = (x[a] >= xs[0]) & (x[a] <= xs[-1]) & (y[a] >= ys[0]) & (y[a] <= ys[-1])
        hx = np.where(inside, hx, PROF_MAX)
        c = np.where(inside, _muestrear(c_grid, xs, ys, x[a], y[a]), float(c_ext))
        cg = np.where(inside, _muestrear(cg_grid, xs, ys, x[a], y[a]), float(cg_ext))
        gx = np.where(inside, _muestrear(dcx, xs, ys, x[a], y[a]), 0.0)
        gy = np.where(inside, _muestrear(dcy, xs, ys, x[a], y[a]), 0.0)

        # Separación entre rayos activos vecinos (a lo largo del frente) -> coeficiente de refracción.
        pos = np.column_stack([x[a], y[a]])
        nxt = np.vstack([pos[1:], pos[-1:]])
        prv = np.vstack([pos[:1], pos[:-1]])
        gap = np.maximum(np.r_[a[1:], a[-1]] - np.r_[a[0], a[:-1]], 1)
        spacing = np.hypot(*(nxt - prv).T) / gap
        kr = np.minimum(np.sqrt(b0 / np.maximum(spacing, 1e-3)), KR_MAX) if len(a) > 2 else np.ones(len(a))
        H = h_start * np.sqrt(float(cg_ext) / cg) * kr

        if step % guardar_cada == 0:
            for k, i in enumerate(a):
                if inside[k]:
                    paths[i].append((x[i], y[i], H[k]))

        # Rompe (H >= γh) o llega a tierra/roca sin romper.
        breaking = inside & (H >= GAMMA * hx) & (hx > 0.1)
        landed = inside & (hx <= 0.1) & ~breaking
        for k in np.where(breaking)[0]:
            i = a[k]
            hgx = _muestrear(np.gradient(h, xs, axis=1), xs, ys, x[i], y[i])
            hgy = _muestrear(np.gradient(h, ys, axis=0), xs, ys, x[i], y[i])
            broke.append({"rayo": i, "x": x[i], "y": y[i], "H": H[k], "h": hx[k], "phi": phi[i],
                          "hx": float(hgx), "hy": float(hgy)})
        stop = breaking | landed | (~inside & (step > 10) & (((x[a] - cx) * ux + (y[a] - cy) * uy) > R))
        active[a[stop]] = False

        # Ecuaciones del rayo: dx/dt = c·(cos φ, sin φ); dφ/dt = sin φ·∂c/∂x − cos φ·∂c/∂y.
        go = ~stop
        ai = a[go]
        phi[ai] += (np.sin(phi[ai]) * gx[go] - np.cos(phi[ai]) * gy[go]) * DT
        x[ai] += c[go] * np.cos(phi[ai]) * DT
        y[ai] += c[go] * np.sin(phi[ai]) * DT

    return {"rompientes": _clasificar(pd.DataFrame(broke)), "trayectorias": paths,
            "entrada": {"altura": h_start, "direccion": from_ext}}


def _clasificar(br: pd.DataFrame) -> pd.DataFrame:
    """Añade posición a lo largo de la costa (s), distancia a la orilla y hacia dónde abre la ola."""
    if br.empty:
        return br
    c = costa()
    # Proyección sobre los tramos de costa (no sobre los vértices, que en la playa están a ~200 m).
    br["dist_orilla"], br["s"], _ = _proyectar_en_costa(br["x"].to_numpy(), br["y"].to_numpy(), c)
    br["tipo_costa"] = [c["tipo"].iloc[(c["s"] - s).abs().argmin()] for s in br["s"]]
    # Rumbo de propagación del rayo y de la normal hacia la orilla (−∇h, hacia lo bajo).
    prop = (90 - np.degrees(br["phi"])) % 360
    onshore = (90 - np.degrees(np.arctan2(-br["hy"], -br["hx"]))) % 360
    # δ < 0: la ola entra por la izquierda de la normal (mirando al mar) -> abre a la izquierda del surfista.
    br["angulo"] = (prop - onshore + 180) % 360 - 180
    br["lado"] = np.where(br["angulo"].abs() < 5, "cierra", np.where(br["angulo"] < 0, "izquierda", "derecha"))
    return br


def perfil_playa(rompientes: list[pd.DataFrame], tramo=50.0, s_min=-1500.0, s_max=3000.0) -> pd.DataFrame:
    """Combina varias componentes (swell 1, swell 2...) en tramos de costa: altura de rompiente combinada
    por energía y el lado según la componente que más aporta."""
    bins = np.arange(s_min, s_max + tramo, tramo)
    out = pd.DataFrame({"s": bins[:-1] + tramo / 2})
    energy = np.zeros(len(out))
    best_H = np.zeros(len(out))
    lado = np.full(len(out), "", dtype=object)
    angulo = np.full(len(out), np.nan)
    for br in rompientes:
        if br.empty:
            continue
        cut = pd.cut(br["s"], bins, labels=False)
        g = br.assign(b=cut).dropna(subset=["b"]).groupby("b")
        Hc = g["H"].quantile(0.9)  # las olas grandes del tramo (sets), no el promedio
        for b, Hb in Hc.items():
            b = int(b)
            energy[b] += Hb ** 2
            if Hb > best_H[b]:
                best_H[b] = Hb
                grp = g.get_group(b)
                lado[b] = grp["lado"].mode().iloc[0]
                angulo[b] = grp["angulo"].median()
    out["H"] = np.sqrt(energy)
    out["lado"] = lado
    out["angulo"] = angulo
    c = costa()
    out["tipo_costa"] = [c["tipo"].iloc[(c["s"] - s).abs().argmin()] for s in out["s"]]
    return out
