# Procedural hull textures (albedo + normal) generated with numpy
import bpy, os, math
import numpy as np

FONT = {
 'S': ["111", "100", "111", "001", "111"], 'W': ["10001", "10001", "10101", "11011", "10001"],
 '0': ["111", "101", "101", "101", "111"], '1': ["010", "110", "010", "010", "111"],
 '4': ["101", "101", "111", "001", "001"], '7': ["111", "001", "010", "010", "010"],
 '-': ["000", "000", "111", "000", "000"], ' ': ["000"] * 5,
 '2': ["111", "001", "111", "100", "111"], '9': ["111", "101", "111", "001", "111"],
 'G': ["111", "100", "101", "101", "111"], 'R': ["110", "101", "110", "101", "101"],
 'A': ["010", "101", "111", "101", "101"], 'N': ["101", "111", "111", "101", "101"],
 'E': ["111", "100", "110", "100", "111"], 'D': ["110", "101", "101", "101", "110"],
}


def vnoise(H, W, fy, fx, rng):
    g = rng.random((fy, fx))
    ys = np.arange(H) / H * fy; xs = np.arange(W) / W * fx
    y0 = np.floor(ys).astype(int); ty = ys - y0; ty = ty * ty * (3 - 2 * ty); y1 = (y0 + 1) % fy
    x0 = np.floor(xs).astype(int); tx = xs - x0; tx = tx * tx * (3 - 2 * tx); x1 = (x0 + 1) % fx
    a = g[y0][:, x0]; b = g[y0][:, x1]; c = g[y1][:, x0]; d = g[y1][:, x1]
    tx = tx[None, :]; ty = ty[:, None]
    return (a * (1 - tx) + b * tx) * (1 - ty) + (c * (1 - tx) + d * tx) * ty


def fbm(H, W, fy, fx, octs, rng):
    out = np.zeros((H, W)); amp = 1.0; tot = 0
    for o in range(octs):
        out += amp * vnoise(H, W, max(1, fy * 2 ** o), max(1, fx * 2 ** o), rng); tot += amp; amp *= 0.5
    return out / tot


def blur(a, n=1):
    for _ in range(n):
        a = (a + np.roll(a, 1, 0) + np.roll(a, -1, 0) + np.roll(a, 1, 1) + np.roll(a, -1, 1)) / 5.0
    return a


def to_normal(Hh, k):
    Hs = blur(Hh, 1)
    dx = (np.roll(Hs, -1, 1) - np.roll(Hs, 1, 1)) * k
    dy = (np.roll(Hs, -1, 0) - np.roll(Hs, 1, 0)) * k
    nz = np.ones_like(dx)
    l = np.sqrt(dx * dx + dy * dy + 1)
    return np.stack([-dx / l * 0.5 + 0.5, -dy / l * 0.5 + 0.5, nz / l * 0.5 + 0.5], -1)


def save(name, arr, path, noncolor=False):
    H, W = arr.shape[:2]
    img = bpy.data.images.new(name, W, H, alpha=False)
    rgba = np.ones((H, W, 4), dtype=np.float32)
    rgba[..., :3] = np.clip(arr, 0, 1)
    img.pixels.foreach_set(rgba.ravel())
    img.filepath_raw = path; img.file_format = 'PNG'
    img.save()
    if noncolor:
        img.colorspace_settings.name = 'Non-Color'
    return img


OLIVE = np.array([0.335, 0.355, 0.245])
DGREEN = np.array([0.205, 0.245, 0.175])
BROWN = np.array([0.315, 0.28, 0.215])


def camo(H, W, rng, f=5):
    n1 = fbm(H, W, f, f, 3, rng); n2 = fbm(H, W, f, f, 3, rng)
    col = np.empty((H, W, 3)); col[:] = OLIVE
    m1 = np.clip((n1 - 0.54) / 0.015, 0, 1)[..., None]
    m2 = np.clip((n2 - 0.60) / 0.015, 0, 1)[..., None]
    col = col * (1 - m1) + DGREEN * m1
    col = col * (1 - m2) + BROWN * m2
    return col


def make_fuse(outdir, YMIN, YMAX, circ, S=2048):
    rng = np.random.default_rng(11)
    H = W = S; L = YMAX - YMIN
    py = lambda y: int((y - YMIN) / L * H)
    pu = lambda th: int((th % 360) / 360.0 * W)
    col = camo(H, W, rng, 6)
    Hh = np.zeros((H, W)); line = np.zeros((H, W)); riv = np.zeros((H, W))
    # ring stations
    ys = []; y = YMAX - 0.35
    while y > YMIN + 0.2:
        ys.append(y); y -= rng.uniform(0.5, 0.85)
    rows = [py(y) for y in ys]
    for r in rows:
        line[r:r + 2, :] = 1
        for dv in (-7, 8):
            cs = np.arange(0, W, 26)
            for du in range(-2, 3):
                riv[(r + dv) % H, (cs + du) % W] = 1
                riv[(r + dv + 1) % H, (cs + du) % W] = 1
    ths = [35, 80, 125, 165, 195, 235, 280, 325]
    rows2 = [0] + sorted(rows) + [H - 1]
    for k in range(len(rows2) - 1):
        r0, r1 = rows2[k], rows2[k + 1]
        for th in ths:
            if rng.random() < 0.72:
                c = pu(th + rng.uniform(-4, 4))
                line[r0:r1, c:c + 4] = 1
                rs = np.arange(r0 + 5, r1 - 3, 10)
                for dc in (-14, 16):
                    for du in range(-2, 3):
                        riv[rs, (c + dc + du) % W] = 1
                        riv[rs + 1, (c + dc + du) % W] = 1
        # access hatches
        if rng.random() < 0.6 and r1 - r0 > 60:
            th = rng.choice([105, 150, 210, 255, 60, 300])
            c0 = pu(th); hw = int(rng.uniform(50, 110)); hh = int(min(r1 - r0 - 30, rng.uniform(30, 60)))
            ra = r0 + 15; rb = ra + hh
            line[ra:ra + 2, c0:c0 + hw] = 1; line[rb:rb + 2, c0:c0 + hw] = 1
            line[ra:rb, c0:c0 + 3] = 1; line[ra:rb, c0 + hw:c0 + hw + 3] = 1
            for (rr, cc) in ((ra + 5, c0 + 10), (ra + 5, c0 + hw - 10), (rb - 5, c0 + 10), (rb - 5, c0 + hw - 10)):
                riv[rr - 1:rr + 2, cc - 4:cc + 5] = 1
    Hh -= line * 1.0
    Hh += riv * 0.7
    Hh += (fbm(H, W, 256, 256, 2, rng) - 0.5) * 0.12
    # anti-glare panel ahead of canopy
    vv = (np.arange(H) / H * L + YMIN)[:, None]; uu = (np.arange(W) / W * 360.0)[None, :]
    thd = np.minimum(uu, 360 - uu)
    ag = ((vv > 4.97) & (vv < 6.05) & (thd < 30)).astype(float)[..., None]
    col = col * (1 - ag) + np.array([0.07, 0.075, 0.07]) * ag
    # belly slightly lighter/greyer
    bel = np.clip((np.abs(uu - 180) - 0) / 40, 0, 1)
    bel = (1 - bel)[..., None] * np.ones((H, 1, 1))
    col = col * (1 - 0.35 * bel) + np.array([0.30, 0.31, 0.29]) * 0.35 * bel
    # grime & streaks
    g1 = fbm(H, W, 8, 8, 4, rng)
    streak = fbm(H, W, 300, 6, 2, rng)
    col *= (0.82 + 0.3 * g1)[..., None]
    col *= (1 - 0.22 * np.clip(streak - 0.45, 0, 1) * 2)[..., None]
    lb = blur(line, 3)
    col *= (1 - 0.55 * np.clip(lb * 2.2, 0, 1))[..., None]
    col *= (1 - 0.25 * riv)[..., None]
    # worn edges next to lines
    wear = np.clip(blur(line, 8) * 3 - lb * 2, 0, 1) * (fbm(H, W, 128, 128, 2, rng) > 0.55)
    col += 0.05 * wear[..., None]
    # exhaust soot on boom
    soot = np.clip(1 - np.abs(vv + 3.6) / 2.2, 0, 1) * np.clip(1 - np.abs(thd - 55) / 45, 0, 1)
    soot = soot * (0.5 + 0.8 * fbm(H, W, 12, 6, 3, rng))
    col *= (1 - 0.6 * np.clip(soot, 0, 1))[..., None]

    def stamp(text, yc, th, block_m, color, alpha=0.75, left=False):
        """glyph x along +v on right side (-v on left); glyph up toward top."""
        gl = [FONT.get(ch, FONT[' ']) for ch in text]
        tot = sum(len(g[0]) + 1 for g in gl) - 1
        x0 = 0
        for g in gl:
            gw = len(g[0]); xs0 = x0; x0 += gw + 1
            for gy in range(5):
                for gx in range(gw):
                    if g[gy][gx] != '1': continue
                    xm = (xs0 + gx - tot / 2) * block_m          # along fuselage
                    um = (2 - gy) * block_m                             # up
                    yy = yc + (-xm if left else xm)
                    ppm = W / max(0.3, circ(yy))
                    r0 = py(yy - block_m / 2); r1 = py(yy + block_m / 2)
                    if left:
                        cc = pu(th) + um * ppm
                    else:
                        cc = pu(th) - um * ppm
                    c0 = int(cc - block_m * ppm / 2); c1 = int(cc + block_m * ppm / 2)
                    col[r0:r1, c0:c1] = col[r0:r1, c0:c1] * (1 - alpha) + np.array(color) * alpha

    LV = (0.56, 0.57, 0.50)
    stamp("SW-07", -4.35, 95, 0.045, LV)
    stamp("SW-07", -4.35, 265, 0.045, LV, left=True)
    stamp("4411", -6.2, 92, 0.03, (0.08, 0.08, 0.07), 0.8)
    stamp("4411", -6.2, 268, 0.03, (0.08, 0.08, 0.07), 0.8, left=True)
    stamp("DANGER", -6.75, 95, 0.014, (0.75, 0.6, 0.1), 0.85)
    stamp("DANGER", -6.75, 265, 0.014, (0.75, 0.6, 0.1), 0.85, left=True)
    # emblem: double chevron, both sides
    for th, sgn in ((95, 1), (265, 1)):
        for k in range(2):
            for t in np.linspace(-1, 1, 160):
                yy = -3.25 + sgn * (k * 0.13 - abs(t) * 0.16)
                ppm = W / circ(yy)
                r = py(yy); c = int(pu(th) + t * 0.14 * ppm)
                col[r - 5:r + 5, c - 3:c + 4] = col[r - 5:r + 5, c - 3:c + 4] * 0.3 + np.array(LV) * 0.7
    # hazard band near tail rotor
    r0, r1 = py(-7.05), py(-6.93)
    rr = np.arange(r0, r1)[:, None]; cc = np.arange(W)[None, :]
    stripes = (((rr * 3 + cc) // 40) % 2).astype(float)[..., None]
    side = ((np.abs(uu - 90) < 60) | (np.abs(uu - 270) < 60)).astype(float)[..., None]
    band = np.array([0.72, 0.58, 0.08]) * stripes + np.array([0.06, 0.06, 0.06]) * (1 - stripes)
    col[r0:r1] = col[r0:r1] * (1 - 0.85 * side) + band * 0.85 * side
    nrm = to_normal(Hh, 1.6)
    a = save('fuse_col', col, os.path.join(outdir, 'heli_fuse_col.png'))
    b = save('fuse_nrm', nrm, os.path.join(outdir, 'heli_fuse_nrm.png'), True)
    return a, b


def make_generic(outdir, S=1024):
    """Tileable 2m x 2m panel texture."""
    rng = np.random.default_rng(5)
    H = W = S
    col = camo(H, W, rng, 3)
    line = np.zeros((H, W)); riv = np.zeros((H, W))
    step = S // 4      # 0.5 m
    for k in range(4):
        r = k * step + 8
        line[r:r + 3, :] = 1; line[:, r:r + 3] = 1
        cs = np.arange(12, W, 32)
        for d in (-9, 11):
            for du in range(-2, 3):
                for dv in range(-2, 3):
                    if abs(du) + abs(dv) > 3: continue
                    riv[(r + d + dv) % H, (cs + du) % W] = 1
                    riv[(cs + du) % H, (r + d + dv) % W] = 1
    Hh = -line + riv * 0.7 + (fbm(H, W, 128, 128, 2, rng) - 0.5) * 0.12
    g1 = fbm(H, W, 6, 6, 4, rng)
    col *= (0.84 + 0.28 * g1)[..., None]
    lb = blur(line, 3)
    col *= (1 - 0.36 * np.clip(lb * 2.2, 0, 1))[..., None]
    col *= (1 - 0.25 * riv)[..., None]
    nrm = to_normal(Hh, 1.6)
    a = save('gen_col', col, os.path.join(outdir, 'heli_gen_col.png'))
    b = save('gen_nrm', nrm, os.path.join(outdir, 'heli_gen_nrm.png'), True)
    return a, b
