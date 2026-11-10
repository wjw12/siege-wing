# Procedural hull textures (albedo + normal + occlusion/roughness/metal) generated with numpy
import bpy, os, math
import numpy as np

FONT = {
 'A': ["010", "101", "111", "101", "101"], 'B': ["110", "101", "110", "101", "110"], 'C': ["111", "100", "100", "100", "111"],
 'D': ["110", "101", "101", "101", "110"], 'E': ["111", "100", "110", "100", "111"], 'F': ["111", "100", "110", "100", "100"],
 'G': ["111", "100", "101", "101", "111"], 'H': ["101", "101", "111", "101", "101"], 'I': ["111", "010", "010", "010", "111"],
 'J': ["001", "001", "001", "101", "111"], 'K': ["101", "101", "110", "101", "101"], 'L': ["100", "100", "100", "100", "111"],
 'M': ["10001", "11011", "10101", "10001", "10001"], 'N': ["101", "111", "111", "101", "101"], 'O': ["111", "101", "101", "101", "111"],
 'P': ["111", "101", "111", "100", "100"], 'Q': ["111", "101", "101", "111", "001"], 'R': ["110", "101", "110", "101", "101"],
 'S': ["111", "100", "111", "001", "111"], 'T': ["111", "010", "010", "010", "010"], 'U': ["101", "101", "101", "101", "111"],
 'V': ["101", "101", "101", "101", "010"], 'W': ["10001", "10001", "10101", "11011", "10001"], 'X': ["101", "101", "010", "101", "101"],
 'Y': ["101", "101", "010", "010", "010"], 'Z': ["111", "001", "010", "100", "111"],
 '0': ["111", "101", "101", "101", "111"], '1': ["010", "110", "010", "010", "111"], '2': ["111", "001", "111", "100", "111"],
 '3': ["111", "001", "111", "001", "111"], '4': ["101", "101", "111", "001", "001"], '5': ["111", "100", "111", "001", "111"],
 '6': ["111", "100", "111", "101", "111"], '7': ["111", "001", "010", "010", "010"], '8': ["111", "101", "111", "101", "111"],
 '9': ["111", "101", "111", "001", "111"], '-': ["000", "000", "111", "000", "000"], ' ': ["00"] * 5, '.': ["0", "0", "0", "0", "1"],
 '>': ["100", "010", "001", "010", "100"], '<': ["001", "010", "100", "010", "001"], '/': ["001", "001", "010", "100", "100"],
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


def blur_v(a, n=1):      # along rows axis only (axis 0)
    for _ in range(n):
        a = (a + np.roll(a, 1, 0) + np.roll(a, -1, 0)) / 3.0
    return a


def blur_u(a, n=1):
    for _ in range(n):
        a = (a + np.roll(a, 1, 1) + np.roll(a, -1, 1)) / 3.0
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


# dark matte gunship paint (sRGB values)
BASE = np.array([0.238, 0.252, 0.218])
BASE_W = np.array([0.275, 0.283, 0.252])     # sun-faded / lighter batch
PRIMER = np.array([0.46, 0.47, 0.43])        # worn-through chips
DUST = np.array([0.40, 0.36, 0.30])
SOOT = np.array([0.045, 0.042, 0.04])
ANTIGLARE = np.array([0.075, 0.08, 0.078])
LOWVIS = np.array([0.075, 0.08, 0.075])      # black-ish low-visibility markings
NOTICE = np.array([0.46, 0.47, 0.42])        # small light-grey notices
WARN = np.array([0.56, 0.45, 0.10])


def paint_base(H, W, rng, f=5):
    """base coat with soft mottling between two tones"""
    n1 = fbm(H, W, f, f, 4, rng)
    m = np.clip((n1 - 0.35) / 0.4, 0, 1)[..., None]
    col = BASE * (1 - 0.45 * m) + BASE_W * 0.45 * m
    return col * np.ones((H, W, 1))


def lerp(col, c, m):
    m = np.clip(m, 0, 1)[..., None]
    return col * (1 - m) + np.asarray(c) * m


def make_fuse(outdir, YMIN, YMAX, circ, H=4096, W=1024):
    rng = np.random.default_rng(11)
    L = YMAX - YMIN
    py = lambda y: int((y - YMIN) / L * H)
    pu = lambda th: int((th % 360) / 360.0 * W)
    col = paint_base(H, W, rng, 7)
    vv = (np.arange(H) / H * L + YMIN)[:, None]            # fuselage station (m) per row
    uu = (np.arange(W) / W * 360.0)[None, :]               # theta (deg) per column; 0 top, 90 right, 180 belly
    thd = np.minimum(uu, 360 - uu)                         # 0 top .. 180 belly
    cy = np.array([circ(float(y)) for y in np.linspace(YMIN, YMAX, 147)])
    crow = np.interp(vv[:, 0], np.linspace(YMIN, YMAX, 147), cy)[:, None]      # circumference (m) per row
    um = (np.arange(W) / W)[None, :] * crow                # metres around from the top centre line
    line = np.zeros((H, W)); riv = np.zeros((H, W)); tone = np.ones((H, W))
    # ---- frames (ring seams) with double fastener rows
    ys = []; y = YMAX - 0.55
    while y > YMIN + 0.2:
        ys.append(y); y -= rng.uniform(0.45, 0.8)
    rivu = (np.mod(um, 0.055) < 0.012)
    for y0 in ys:
        d = np.abs(vv - y0)
        line[(d < 0.0055)[:, 0], :] = 1
        rr = (np.abs(d - 0.032) < 0.0056)
        riv = np.maximum(riv, (rr & rivu).astype(float))
    # ---- stringers / longitudinal seams per bay, random per-panel tone, access hatches
    ths = [18, 52, 88, 118, 150, 180, 210, 242, 272, 308, 342]
    bounds = sorted(ys) ; bounds = [YMIN - 0.1] + bounds + [YMAX + 0.1]
    rivv = (np.mod(vv, 0.055) < 0.0115)
    for k in range(len(bounds) - 1):
        r0, r1 = max(0, py(bounds[k])), min(H, py(bounds[k + 1]))
        if r1 <= r0: continue
        ymid = (bounds[k] + bounds[k + 1]) / 2
        cols = [0]
        for th in ths:
            if rng.random() < 0.7:
                c0 = pu(th + rng.uniform(-5, 5)); cols.append(c0)
                dm = (np.arange(W)[None, :] - c0) / W * crow[r0:r1]
                seg = line[r0:r1]; seg[np.abs(dm) < 0.0035] = 1
                rr = (np.abs(np.abs(dm) - 0.028) < 0.0056) & rivv[r0:r1]
                riv[r0:r1] = np.maximum(riv[r0:r1], rr.astype(float))
        cols = sorted(cols) + [W]
        for q in range(len(cols) - 1):
            tone[r0:r1, cols[q]:cols[q + 1]] = 1.0 + rng.uniform(-0.055, 0.055)
        if rng.random() < 0.75 and (bounds[k + 1] - bounds[k]) > 0.4:
            th = float(rng.choice([104, 140, 220, 256, 66, 294, 165, 195]))
            cm = float(np.interp(ymid, np.linspace(YMIN, YMAX, 147), cy))
            hw = rng.uniform(0.16, 0.34); hh = min(bounds[k + 1] - bounds[k] - 0.16, rng.uniform(0.2, 0.4))
            ya = bounds[k] + 0.08
            c0 = pu(th); c1 = c0 + int(hw / cm * W); ra, rb = py(ya), py(ya + hh)
            if rb > ra + 6 and c1 < W - 4:
                t_ = max(2, int(0.006 / cm * W))
                line[ra:ra + 2, c0:c1] = 1; line[rb:rb + 2, c0:c1] = 1
                line[ra:rb, c0:c0 + t_] = 1; line[ra:rb, c1:c1 + t_] = 1
                tone[ra:rb, c0:c1] = 1.0 + rng.uniform(-0.07, 0.07)
                rw = max(2, int(0.011 / cm * W)); ro = int(0.03 / cm * W)
                for (rr_, cc) in ((ra + 8, c0 + ro), (ra + 8, c1 - ro), (rb - 8, c0 + ro), (rb - 8, c1 - ro), ((ra + rb) // 2, c0 + ro), ((ra + rb) // 2, c1 - ro)):
                    riv[rr_ - 2:rr_ + 2, cc - rw // 2:cc + rw // 2 + 1] = 1
    col *= tone[..., None]
    # ---- markings (painted before weathering so grime sits on top)
    ag = ((vv > 4.99) & (vv < 5.84) & (thd < 31)).astype(float)
    col = lerp(col, ANTIGLARE, ag * 0.92)

    def stamp(text, yc, th, block_m, color, alpha=0.85, left=False):
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
                    um_ = (2 - gy) * block_m                             # up
                    yy = yc + (-xm if left else xm)
                    ppm = W / max(0.3, circ(yy))
                    r0 = py(yy - block_m / 2); r1 = max(r0 + 1, py(yy + block_m / 2))
                    cc = pu(th) + um_ * ppm if left else pu(th) - um_ * ppm
                    c0 = int(cc - block_m * ppm / 2); c1 = max(c0 + 1, int(cc + block_m * ppm / 2))
                    col[r0:r1, c0:c1] = col[r0:r1, c0:c1] * (1 - alpha) + np.array(color) * alpha

    stamp("SW-07", -4.3, 92, 0.05, LOWVIS)
    stamp("SW-07", -4.3, 268, 0.05, LOWVIS, left=True)
    stamp("441107", -6.25, 86, 0.02, LOWVIS, 0.8)
    stamp("441107", -6.25, 274, 0.02, LOWVIS, 0.8, left=True)
    stamp("DANGER", -6.72, 97, 0.016, WARN, 0.8)
    stamp("DANGER", -6.72, 263, 0.016, WARN, 0.8, left=True)
    stamp("TAIL ROTOR", -6.72, 113, 0.011, WARN, 0.75)
    stamp("TAIL ROTOR", -6.72, 247, 0.011, WARN, 0.75, left=True)
    stamp("HOIST", -3.35, 60, 0.012, NOTICE, 0.6); stamp("HOIST", -3.35, 300, 0.012, NOTICE, 0.6, left=True)
    stamp("NO STEP", -5.0, 30, 0.014, NOTICE, 0.6); stamp("NO STEP", -5.0, 330, 0.014, NOTICE, 0.6, left=True)
    stamp("JACK HERE", -2.0, 150, 0.012, NOTICE, 0.6); stamp("JACK HERE", -2.0, 210, 0.012, NOTICE, 0.6, left=True)
    stamp("RESCUE >", 4.45, 86, 0.016, WARN, 0.75); stamp("< RESCUE", 4.45, 274, 0.016, WARN, 0.75, left=True)
    stamp("GND PWR 28V", 0.75, 100, 0.01, NOTICE, 0.6); stamp("STATIC PORT", 5.1, 108, 0.008, NOTICE, 0.6)
    stamp("STATIC PORT", 5.1, 252, 0.008, NOTICE, 0.6, left=True)
    # unit emblem: low-vis double chevron on both sides of the boom root
    for th in (95, 265):
        for k in range(2):
            for t in np.linspace(-1, 1, 200):
                yy = -3.3 + (k * 0.13 - abs(t) * 0.16)
                ppm = W / circ(yy)
                r = py(yy); c = int(pu(th) + t * 0.14 * ppm)
                col[r - 7:r + 7, c - 2:c + 3] = col[r - 7:r + 7, c - 2:c + 3] * 0.2 + LOWVIS * 0.8
    # small hazard band ahead of the tail rotor (dull yellow / black)
    r0, r1 = py(-7.02), py(-6.95)
    rr = np.arange(r0, r1)[:, None]; cc = np.arange(W)[None, :]
    stripes = (((rr + cc * 2) // 22) % 2).astype(float)[..., None]
    side = ((np.abs(uu - 95) < 32) | (np.abs(uu - 265) < 32)).astype(float)[..., None]
    band = WARN * stripes + LOWVIS * (1 - stripes)
    col[r0:r1] = col[r0:r1] * (1 - 0.8 * side) + band * 0.8 * side
    # ---- weathering
    rough = np.full((H, W), 0.62); metal = np.full((H, W), 0.08)
    fine = fbm(H, W, 400, 400, 2, rng)
    g1 = fbm(H, W, 10, 10, 4, rng)
    col *= (0.86 + 0.26 * g1)[..., None]
    col *= (0.955 + 0.09 * fine)[..., None]
    rough += (g1 - 0.5) * 0.16 + (fine - 0.5) * 0.08
    # sun fade on top, dust low on the sides and belly
    fade = np.clip(1 - thd / 55.0, 0, 1) * (0.6 + 0.4 * fbm(H, W, 20, 6, 2, rng))
    col = lerp(col, BASE_W * 1.08, fade * 0.28)
    dust = np.clip((thd - 95) / 70.0, 0, 1) * (0.35 + 0.9 * fbm(H, W, 30, 12, 3, rng))
    col = lerp(col, DUST, dust * 0.30)
    rough += dust * 0.14
    # rain / fluid streaks running down the sides from seams
    sides = np.clip(1 - np.abs(thd - 100) / 75.0, 0, 1)
    def streaks(fine_f, gate_f, thr):
        s1 = np.clip(vnoise(H, W, fine_f, 3, rng) - 0.5, 0, 1) * 2.0
        gate = np.clip((fbm(H, W, gate_f, 3, 2, rng) - thr) * 7.0, 0, 1)
        return blur_v(s1 * gate, 2) * sides
    sm = streaks(330, 34, 0.56)
    col *= (1 - 0.3 * sm)[..., None]
    rough -= sm * 0.12
    st2 = streaks(260, 27, 0.58)
    col = lerp(col, DUST * 1.05, st2 * 0.22)
    # grime gathered in seams, around fasteners
    lb = blur(line, 3)
    halo = np.clip(blur(line, 10) * 5.0, 0, 1) * (0.4 + 0.6 * g1)
    col *= (1 - 0.30 * halo)[..., None]
    col *= (1 - 0.72 * np.clip(lb * 2.4, 0, 1))[..., None]
    rb = blur(riv, 1)
    col *= (1 - 0.34 * np.clip(rb * 2.0, 0, 1))[..., None]
    rough += np.clip(lb * 2.4, 0, 1) * 0.2
    # paint chipping at panel edges and on the nose / leading faces
    edge = np.clip(blur(line, 6) * 3.2 - lb * 2.6, 0, 1)
    nose = np.clip((vv - 5.35) / 0.5, 0, 1) * np.ones((1, W))
    chipn = fbm(H, W, 320, 320, 2, rng)
    chips = ((edge * 0.9 + nose * 0.5 + 0.02) * chipn > 0.42).astype(float) * (chipn > 0.56)
    chips = np.clip(blur(chips, 1) * 1.6, 0, 1)
    col = lerp(col, PRIMER, chips * 0.75)
    rough = rough * (1 - chips) + 0.42 * chips; metal = metal * (1 - chips) + 0.75 * chips
    # worn fastener heads (some bare)
    bare = riv * (fbm(H, W, 200, 200, 1, rng) > 0.62)
    col = lerp(col, PRIMER * 0.9, bare * 0.5)
    metal = np.maximum(metal, bare * 0.6)
    # exhaust soot along the boom behind the suppressors
    along = np.clip((-2.3 - vv) / 0.9, 0, 1) * np.clip((vv + 7.4) / 3.6, 0, 1)
    around = np.clip(1 - np.abs(thd - 58) / 62.0, 0, 1)
    soot = along * around * (0.45 + 0.9 * fbm(H, W, 14, 6, 3, rng))
    soot = np.clip(soot, 0, 1) ** 1.3
    col = lerp(col, SOOT, soot * 0.82)
    rough = rough * (1 - soot * 0.8) + 0.9 * soot * 0.8
    # oil / hydraulic staining under the engine and transmission bay
    oil = np.clip(1 - np.abs(vv + 0.9) / 1.6, 0, 1) * np.clip((thd - 120) / 40.0, 0, 1)
    oil = oil * np.clip(fbm(H, W, 60, 10, 3, rng) - 0.45, 0, 1) * 3.0
    col *= (1 - 0.45 * np.clip(oil, 0, 1))[..., None]
    rough -= np.clip(oil, 0, 1) * 0.3
    # ---- height -> normal
    Hh = -line * 1.2 + riv * 0.8 + (fine - 0.5) * 0.10 + (fbm(H, W, 46, 20, 2, rng) - 0.5) * 0.5 - chips * 0.15
    nrm = to_normal(Hh, 1.7)
    orm = np.stack([np.ones((H, W)), np.clip(rough, 0.2, 1.0), np.clip(metal, 0, 1)], -1)
    a = save('fuse_col', col, os.path.join(outdir, 'heli_fuse_col.png'))
    b = save('fuse_nrm', nrm, os.path.join(outdir, 'heli_fuse_nrm.png'), True)
    c = save('fuse_orm', orm, os.path.join(outdir, 'heli_fuse_orm.png'), True)
    return a, b, c


def make_generic(outdir, S=2048, TILE=4.0):
    """Tileable TILE x TILE metre panel texture (box projected)."""
    rng = np.random.default_rng(5)
    H = W = S; ppm = S / TILE
    col = paint_base(H, W, rng, 4)
    line = np.zeros((H, W)); riv = np.zeros((H, W)); tone = np.ones((H, W))
    hs = [0.22, 0.93, 1.71, 2.36, 3.18, 3.77]          # seam positions (m), irregular
    vs = [0.35, 1.12, 1.68, 2.52, 3.3]
    hp = [int(h * ppm) for h in hs]; vp = [int(v * ppm) for v in vs]
    step = int(0.055 * ppm); off = int(0.028 * ppm)
    cs = np.arange(step // 2, W, step)
    for r in hp:
        line[r:r + 2, :] = 1
        for d in (-off, off):
            for du in range(-2, 3):
                for dv in range(-2, 3):
                    if abs(du) + abs(dv) > 3: continue
                    riv[(r + d + dv) % H, (cs + du) % W] = 1
    for k, c in enumerate(vp):
        # vertical seams only span some of the horizontal bays -> irregular panel layout
        for q in range(len(hp)):
            if (k + q) % 3 == 0: continue
            r0 = hp[q]; r1 = hp[(q + 1) % len(hp)]
            rows = np.arange(r0, r1 if r1 > r0 else r1 + H) % H
            line[rows[:, None], (c + np.arange(2))[None, :] % W] = 1
            rs = rows[step // 2::step]
            for d in (-off, off):
                for du in range(-2, 3):
                    for dv in range(-2, 3):
                        if abs(du) + abs(dv) > 3: continue
                        riv[(rs + dv) % H, (c + d + du) % W] = 1
    hb = [0] + hp + [H]; vb = [0] + vp + [W]
    for i in range(len(hb) - 1):
        for j in range(len(vb) - 1):
            tone[hb[i]:hb[i + 1], vb[j]:vb[j + 1]] = 1.0 + rng.uniform(-0.045, 0.045)
    tone[:hp[0]] = tone[hp[-1] + 2:hp[-1] + 3]            # keep the wrap seamless
    tone[:, :vp[0]] = tone[:, vp[-1] + 3:vp[-1] + 4]
    col *= tone[..., None]
    rough = np.full((H, W), 0.62); metal = np.full((H, W), 0.08)
    fine = fbm(H, W, 400, 400, 2, rng)
    g1 = fbm(H, W, 9, 9, 4, rng)
    col *= (0.86 + 0.26 * g1)[..., None]
    col *= (0.955 + 0.09 * fine)[..., None]
    rough += (g1 - 0.5) * 0.16 + (fine - 0.5) * 0.08
    def streaks(fine_f, gate_f, thr):     # sparse streaks running along v (vertical on side faces)
        s1 = np.clip(vnoise(H, W, 3, fine_f, rng) - 0.5, 0, 1) * 2.0
        gate = np.clip((fbm(H, W, 3, gate_f, 2, rng) - thr) * 7.0, 0, 1)
        return blur_u(s1 * gate, 2)
    sm = streaks(180, 14, 0.56)
    col *= (1 - 0.26 * sm)[..., None]; rough -= sm * 0.1
    st2 = streaks(150, 11, 0.58)
    col = lerp(col, DUST, st2 * 0.18)
    dustn = np.clip(fbm(H, W, 7, 7, 3, rng) - 0.5, 0, 1) * 2.0
    col = lerp(col, DUST, dustn * 0.13); rough += dustn * 0.1
    lb = blur(line, 3)
    halo = np.clip(blur(line, 10) * 5.0, 0, 1) * (0.4 + 0.6 * g1)
    col *= (1 - 0.24 * halo)[..., None]
    col *= (1 - 0.6 * np.clip(lb * 2.4, 0, 1))[..., None]
    rb = blur(riv, 1)
    col *= (1 - 0.3 * np.clip(rb * 2.0, 0, 1))[..., None]
    rough += np.clip(lb * 2.4, 0, 1) * 0.2
    edge = np.clip(blur(line, 6) * 3.2 - lb * 2.6, 0, 1)
    chipn = fbm(H, W, 320, 320, 2, rng)
    chips = ((edge * 0.9 + 0.03) * chipn > 0.42).astype(float) * (chipn > 0.56)
    # random scuffs / scratches
    scr = np.zeros((H, W))
    for _ in range(90):
        r = int(rng.integers(0, H)); c = int(rng.integers(0, W)); ln = int(rng.integers(12, 70))
        if rng.random() < 0.5: scr[r, (c + np.arange(ln)) % W] = 1
        else: scr[(r + np.arange(ln)) % H, c] = 1
    chips = np.clip(blur(chips, 1) * 1.6 + scr * 0.5, 0, 1)
    col = lerp(col, PRIMER, chips * 0.7)
    rough = rough * (1 - chips) + 0.42 * chips; metal = metal * (1 - chips) + 0.7 * chips
    bare = riv * (fbm(H, W, 200, 200, 1, rng) > 0.62)
    col = lerp(col, PRIMER * 0.9, bare * 0.5); metal = np.maximum(metal, bare * 0.6)
    Hh = -line * 1.1 + riv * 0.8 + (fine - 0.5) * 0.10 + (fbm(H, W, 30, 30, 2, rng) - 0.5) * 0.45 - chips * 0.15
    nrm = to_normal(Hh, 1.7)
    orm = np.stack([np.ones((H, W)), np.clip(rough, 0.2, 1.0), np.clip(metal, 0, 1)], -1)
    a = save('gen_col', col, os.path.join(outdir, 'heli_gen_col.png'))
    b = save('gen_nrm', nrm, os.path.join(outdir, 'heli_gen_nrm.png'), True)
    c = save('gen_orm', orm, os.path.join(outdir, 'heli_gen_orm.png'), True)
    return a, b, c
