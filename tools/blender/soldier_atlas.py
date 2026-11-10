# Siege Wing - soldier texture atlas (layout + procedural painter). Imported by soldiers.py (Blender's bundled numpy).
#   blender.exe -b -P soldiers.py -- atlas    -> repaint assets/textures/soldiers/atlas.png, then build the models
# The atlas multiplies the soldiers' vertex colour: texel = wanted factor / GAIN, so 1.0 (stored 0.8) is neutral.
# Alpha only matters on heraldic cloth (uv.x = 1): 1 = formation tint, 0 = the counter colour chosen in the shader.
# Layout (px, 2048 x 2048, y down):
#   y    0.. 192  16 face cells 128 wide (the shader shifts u by a per-soldier face index); each holds the face, a skin patch and a hair patch
#   y  192..1056  x < 1536: shield band, 8 cells 192 wide per row (u shifted by the formation's charge): round A, round B, heater A, heater B
#                 (192 high; the shader moves layout-B soldiers one row down) and the chest badge row (96 high)
#                 x >= 1536: warlord face, cape, tabard, surcoat, mantle
#   y 1056..2048  material tiles, 256 x 256 with an 8 px wrapped margin, periodic over a quarter of their width
import math
import numpy as np

AT = 2048
SS = 2
GAIN = 1.25
PI = math.pi
F32 = np.float32


class Chart:
    def __init__(s, name, x, y, w, h, fn=None, args=(), pad=8):
        s.name = name; s.x = x; s.y = y; s.w = w; s.h = h; s.fn = fn; s.args = args; s.pad = pad

    def uv(s, a, b):
        """interior coords (a right, b up, 0..1) -> atlas uv with v measured from the top"""
        return ((s.x + s.pad + a * (s.w - 2 * s.pad)) / AT, (s.y + s.pad + (1 - b) * (s.h - 2 * s.pad)) / AT)


# ----------------------------------------------------------------------------- helpers
def lin(c):
    return np.array([(v / 12.92) if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in c], F32)


def _h(ix, iy, seed):
    n = (ix.astype(np.int64) * 374761393 + iy.astype(np.int64) * 668265263 + seed * 974711 + 1013) & 0x7fffffff
    n = ((n ^ (n >> 13)) * 1274126177) & 0x7fffffff
    n = n ^ (n >> 16)
    return ((n & 0xffff) / 65535.0).astype(F32)


def vn(a, b, fx, fy, seed=0):
    """tileable value noise, fx x fy lattice cells over the unit square"""
    x = a * fx; y = b * fy
    x0 = np.floor(x); y0 = np.floor(y)
    tx = x - x0; ty = y - y0
    tx = tx * tx * (3 - 2 * tx); ty = ty * ty * (3 - 2 * ty)
    x0 = x0.astype(np.int64); y0 = y0.astype(np.int64)
    g = lambda i, j: _h(np.mod(i, fx), np.mod(j, fy), seed)
    return (g(x0, y0) * (1 - tx) + g(x0 + 1, y0) * tx) * (1 - ty) + (g(x0, y0 + 1) * (1 - tx) + g(x0 + 1, y0 + 1) * tx) * ty


def fbm(a, b, fx, fy, octs=3, seed=0):
    v = 0; amp = 1.0; tot = 0
    for k in range(octs):
        v = v + amp * vn(a, b, fx << k, fy << k, seed + 17 * k); tot += amp; amp *= 0.5
    return v / tot


def smooth(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)


def grey(v):
    return np.dstack([v, v, v]).astype(F32)


def mixc(c0, c1, k):
    return c0 * (1 - k[..., None]) + c1 * k[..., None]


def one(A):
    return np.ones_like(A)


def norm(v, target=1.0):
    return v * (target / float(v.mean()))


def sd_seg(x, y, ax, ay, bx, by, r0, r1=None):
    r1 = r0 if r1 is None else r1
    dx = bx - ax; dy = by - ay
    h = np.clip(((x - ax) * dx + (y - ay) * dy) / (dx * dx + dy * dy), 0, 1)
    return np.hypot(x - ax - dx * h, y - ay - dy * h) - (r0 + (r1 - r0) * h)


def sd_circ(x, y, cx, cy, r):
    return np.hypot(x - cx, y - cy) - r


def sd_ell(x, y, cx, cy, rx, ry):
    return (np.hypot((x - cx) / rx, (y - cy) / ry) - 1) * min(rx, ry)


def sd_box(x, y, cx, cy, hx, hy):
    return np.maximum(np.abs(x - cx) - hx, np.abs(y - cy) - hy)


def chain(x, y, pts, rr):
    d = None
    for (p0, p1, r0, r1) in zip(pts[:-1], pts[1:], rr[:-1], rr[1:]):
        s = sd_seg(x, y, p0[0], p0[1], p1[0], p1[1], r0, r1)
        d = s if d is None else np.minimum(d, s)
    return d


def U(parts):
    return np.minimum.reduce(parts)


def msk(d, aa):
    return np.clip(0.5 - d / aa, 0, 1)


# ----------------------------------------------------------------------------- heraldic charges (signed distance, y up, about +-1)
def c_cross(x, y):
    ax, ay = np.abs(x), np.abs(y)
    arm = lambda p, q: np.maximum(q - (.09 + .24 * p), p - .82)
    return np.minimum(arm(ay, ax), arm(ax, ay)) * .8


def c_lion(x, y):
    d = U([
        sd_seg(x, y, .12, -.38, -.12, .28, .15, .20),
        np.hypot(x + .08, y - .44) - (.23 + .035 * np.sin(9 * np.arctan2(y - .44, x + .08))),      # mane
        sd_circ(x, y, -.30, .63, .15),
        sd_seg(x, y, -.34, .66, -.55, .63, .07, .05),
        sd_seg(x, y, -.34, .50, -.50, .43, .04, .03),
        sd_seg(x, y, -.22, .78, -.15, .88, .045, .02),
        chain(x, y, [(-.20, .30), (-.48, .40), (-.66, .56)], [.075, .055, .065]),
        chain(x, y, [(-.16, .10), (-.46, .08), (-.70, .18)], [.075, .055, .065]),
        chain(x, y, [(.10, -.36), (-.08, -.60), (-.02, -.86), (-.24, -.90)], [.12, .07, .055, .055]),
        chain(x, y, [(.02, -.30), (-.34, -.44), (-.52, -.28)], [.10, .06, .06]),
        chain(x, y, [(.22, -.40), (.46, -.34), (.60, -.06), (.50, .22), (.62, .46), (.52, .66)], [.05, .04, .04, .04, .04, .04]),
        sd_ell(x, y, .50, .75, .08, .13),
        sd_seg(x, y, -.66, .56, -.80, .62, .03, .01), sd_seg(x, y, -.66, .56, -.78, .50, .03, .01),
        sd_seg(x, y, -.70, .18, -.84, .24, .03, .01), sd_seg(x, y, -.70, .18, -.82, .12, .03, .01),
    ])
    return np.maximum(d, -sd_circ(x, y, -.34, .68, .028))


def c_eagle(x, y):
    ax = np.abs(x)
    parts = [sd_ell(x, y, 0, -.08, .15, .30), sd_seg(x, y, 0, .2, 0, .46, .08, .07), sd_circ(x, y, -.02, .58, .10),
             sd_seg(x, y, -.08, .60, -.27, .52, .05, .012),
             chain(ax, y, [(.10, .20), (.40, .50), (.68, .76)], [.08, .07, .05])]
    for k, (wx, wy, l) in enumerate([(.24, .34, .55), (.36, .44, .68), (.48, .55, .80), (.60, .66, .86), (.72, .76, .76)]):
        parts.append(sd_seg(ax, y, wx, wy, wx + .07 + .035 * k, wy - l, .058, .012))
    parts += [sd_seg(ax, y, .08, -.30, .26, -.56, .05, .035), sd_seg(ax, y, .26, -.56, .40, -.63, .03, .008),
              sd_seg(ax, y, .26, -.56, .31, -.74, .03, .008), sd_seg(ax, y, .26, -.56, .15, -.71, .03, .008),
              sd_seg(x, y, 0, -.3, 0, -.82, .07, .10), sd_seg(ax, y, .02, -.35, .17, -.78, .05, .06)]
    return np.maximum(U(parts), -sd_circ(x, y, -.05, .60, .024))


def c_stag(x, y):
    ax = np.abs(x)
    d = U([sd_seg(x, y, 0, .02, 0, -.62, .20, .085), sd_seg(ax, y, .16, .06, .42, .15, .06, .03),
           chain(ax, y, [(.10, .16), (.27, .46), (.35, .70), (.27, .93)], [.05, .045, .04, .018]),
           sd_seg(ax, y, .20, .36, .46, .50, .04, .014), sd_seg(ax, y, .32, .60, .58, .79, .035, .014),
           sd_seg(ax, y, .12, .24, .02, .46, .035, .012)])
    return np.maximum(d, -np.minimum(sd_circ(ax, y, .09, -.12, .032), sd_ell(x, y, 0, -.60, .05, .028)))


def c_fleur(x, y):
    ax = np.abs(x)
    return U([sd_ell(x, y, 0, .30, .16, .56), chain(ax, y, [(.10, -.02), (.34, .32), (.56, .36), (.67, .14), (.57, -.04)], [.11, .10, .09, .07, .035]),
              sd_box(x, y, 0, -.16, .36, .065), sd_ell(x, y, 0, -.52, .09, .30), chain(ax, y, [(.08, -.26), (.26, -.50), (.41, -.57)], [.07, .06, .028])])


def c_tower(x, y):
    d = U([sd_box(x, y, 0, -.2, .36, .58), sd_box(x, y, 0, .44, .47, .08), sd_box(x, y, -.36, .63, .11, .12), sd_box(x, y, 0, .63, .11, .12),
           sd_box(x, y, .36, .63, .11, .12)])
    holes = U([sd_box(x, y, 0, -.63, .115, .16), sd_circ(x, y, 0, -.47, .115), sd_box(x, y, -.18, .06, .035, .11), sd_box(x, y, .18, .06, .035, .11),
               sd_box(x, y, 0, -.14, .36, .012), sd_box(x, y, 0, .22, .36, .012)])
    return np.maximum(d, -holes)


def c_arrows(x, y):
    parts = []
    for s in (1, -1):
        c, sn = math.cos(.72 * s), math.sin(.72 * s)
        u = x * c - y * sn; v = x * sn + y * c
        parts += [sd_box(u, v, 0, -.04, .035, .72),
                  np.maximum(np.abs(u) * 1.5 + (v - .62) - .27, .58 - v) * .6,
                  np.maximum(sd_box(u, v, 0, -.66, .13, .15), (np.abs(u) * .9 - (v + .86)) * .7)]
    return U(parts)


def c_chev(x, y):
    ax = np.abs(x)
    d = U([np.abs(y - (c - ax * .75)) - .105 for c in (.74, .24, -.26)])
    return np.maximum(d, ax - .82)


# atlas cell k <- charge. Cell order is the shader's formation hash (see soldiers.py CHARGE_CELLS / crowd.js); filled in by set_cells()
CHARGES = [c_cross, c_lion, c_eagle, c_stag, c_fleur, c_tower, c_arrows, c_chev]     # by heraldic index (crowd.js HERALD order)
CELL_OF = list(range(8))                                                              # heraldic index -> atlas cell


# ----------------------------------------------------------------------------- material tiles (periodic)
def p_white(A, B):
    return grey(one(A)), one(A)


def p_mail(A, B):
    N = 48
    x = A * N; y = B * N * 1.25
    best = np.zeros_like(A)
    for dy in (-1, 0, 1):
        row = np.floor(y) + dy
        xs = x + 0.5 * np.mod(row, 2)
        fx = xs - np.floor(xs) - .5
        fy = y - row - .5
        d = np.sqrt(fx * fx + (fy * .8) ** 2)
        ring = np.clip(1 - np.abs(d - .36) / .13, 0, 1)
        best = np.maximum(best, ring * (.7 + .6 * np.clip(fy * 1.1 + .5, 0, 1)))
    v = .56 + .7 * best
    v *= .88 + .24 * vn(A, B, 8, 8, 3)
    return grey(norm(v)), one(A)


def weave(A, B, seed, f=60):
    return (1 + .06 * np.sin(2 * PI * A * f) * np.sin(2 * PI * B * f)) * (.94 + .12 * vn(A, B, 64, 64, seed))


def p_gamb(A, B):
    c = A * 16; f = c - np.floor(c)
    v = .60 + .52 * np.sin(PI * f) ** .55
    st = (np.abs(f - .5) > .43) & (np.mod(B * 40, 1) < .55)
    v = np.where(st, v * .55, v)
    v *= .88 + .24 * fbm(A, B, 4, 16, 3, 5)
    v *= weave(A, B, 6)
    return grey(norm(v)), one(A)


def p_cloth(A, B):
    v = weave(A, B, 11) * (.86 + .28 * fbm(A, B, 8, 2, 3, 12))
    return grey(norm(v)), one(A)


def p_hose(A, B):
    v = (1 + .07 * np.sin(2 * PI * A * 48)) * (.84 + .32 * fbm(A, B, 4, 12, 3, 21)) * (.95 + .1 * vn(A, B, 64, 64, 22))
    return grey(norm(v)), one(A)


def p_leather(A, B):
    g = fbm(A, B, 32, 32, 3, 31)
    r = np.abs(fbm(A, B, 8, 8, 3, 32) - .5) * 2
    v = (.82 + .36 * g) * (1 - .42 * smooth(.10, .0, r))
    v *= 1 + .25 * smooth(.62, .8, fbm(A, B, 12, 12, 2, 33))
    st = (np.abs(np.mod(A * 4, 1) - .5) > .455) & (np.mod(B * 48, 1) < .5)      # a stitched seam every quarter
    v = np.where(st, v * 1.5, v)
    return grey(norm(v)), one(A)


def scratches(A, B, seed, n=26, bright=.28):
    rs = np.random.RandomState(seed)
    v = np.zeros_like(A)
    for k in range(n):
        x0, y0 = rs.rand(), rs.rand(); ang = rs.randn() * .5 + (PI / 2 if rs.rand() < .3 else 0); L = .03 + .12 * rs.rand()
        x1 = x0 + math.cos(ang) * L; y1 = y0 + math.sin(ang) * L
        a = np.mod(A - x0 + .5, 1) - .5 + x0; b = np.mod(B - y0 + .5, 1) - .5 + y0
        d = sd_seg(a, b, x0, y0, x1, y1, .0016)
        v = np.maximum(v, msk(d, .004) * (bright if rs.rand() < .7 else -bright))
    return v


def rivets(A, B, na, nb, ob=0.0, r=.011):
    fa = np.mod(A * na, 1) - .5; fb = np.mod(B * nb - ob, 1) - .5
    d = np.hypot(fa / na, fb / nb)
    return msk(d - r, .006), msk(np.abs(d - r) - .004, .005) * (fb < 0)


def p_plate(A, B):
    v = .9 + .2 * fbm(A, B, 4, 64, 3, 41)
    v *= .92 + .16 * fbm(A, B, 8, 8, 3, 42)
    g = np.abs(np.mod(B * 8, 1) - .5)                 # articulation lines every eighth
    v *= 1 - .5 * smooth(.47, .495, g)
    v *= 1 + .35 * smooth(.40, .46, g) * (np.mod(B * 8, 1) > .5)
    rv, sh_ = rivets(A, B, 16, 8, .12)
    v = v * (1 + .5 * rv) * (1 - .5 * sh_)
    v += scratches(A, B, 43)
    v *= 1 + .22 * smooth(.6, .78, fbm(A, B, 12, 12, 3, 44))
    return grey(norm(np.clip(v, .2, 2))), one(A)


def p_steel(A, B):
    """plain worked steel for blades, bosses and brims"""
    v = (.9 + .2 * fbm(A, B, 4, 64, 3, 46)) * (.9 + .2 * fbm(A, B, 8, 8, 3, 47))
    v += scratches(A, B, 48, 30, .2)
    v *= 1 + .2 * smooth(.6, .78, fbm(A, B, 12, 12, 3, 49))
    return grey(norm(np.clip(v, .2, 2))), one(A)


def p_helm(A, B):
    """skull: riveted brow band at the bottom, four riveted seams (front seam at a = .5)"""
    Bc = np.clip(B, 0, 1)
    v = .9 + .2 * fbm(A, Bc, 4, 48, 3, 51)
    v *= .9 + .2 * fbm(A, Bc, 8, 6, 3, 52)
    band = Bc < .2
    v *= np.where(band, .86, 1.0)
    v *= 1 - .45 * msk(np.abs(Bc - .2) - .008, .01)
    v *= 1 + .5 * smooth(.035, .0, Bc)                # worn bright edge
    rv, sh_ = rivets(A, Bc, 16, 1, -.4, .012)
    rv = rv * (Bc < .2); sh_ = sh_ * (Bc < .2)
    sa = np.abs(np.mod(A * 4, 1) - .5)
    seam = (sa > .44) & (Bc > .2)
    v *= np.where(seam, 1.12, 1.0)
    v *= 1 - .4 * msk(np.abs(sa - .44) - .006, .01) * (Bc > .2)
    fa = (sa - .5) / 4; fb = (np.mod(Bc * 7, 1) - .5) / 7
    r2 = msk(np.hypot(fa, fb) - .010, .006) * (Bc > .24)
    v = v * (1 + .5 * np.maximum(rv, r2)) * (1 - .4 * sh_)
    v += scratches(A, Bc, 53, 30)
    v *= .92 + .2 * Bc
    return grey(norm(np.clip(v, .2, 2))), one(A)


def p_gold(A, B):
    v = .86 + .28 * fbm(A, B, 24, 24, 2, 61)
    f = np.sin(2 * PI * (A * 8 + .25 * np.sin(2 * PI * B * 8)))
    v *= 1 - .3 * msk(np.abs(f) - .16, .1)
    v *= 1 + .3 * smooth(.6, .8, fbm(A, B, 8, 8, 2, 62))
    return grey(norm(v)), one(A)


def p_gilt(A, B):
    """blued plate with gilt engraving - full colour (the warlord's plate is white in vertex colour)"""
    steel = lin((.36, .38, .46)); gold = lin((.98, .76, .30))
    v = (.82 + .36 * fbm(A, B, 4, 48, 3, 71)) * (.85 + .3 * fbm(A, B, 8, 8, 3, 72))
    rgb = steel[None, None, :] * v[..., None]
    f1 = np.sin(2 * PI * (A * 4 + .22 * np.sin(2 * PI * B * 8)))
    f2 = np.sin(2 * PI * (B * 8 + .20 * np.sin(2 * PI * A * 8)))
    vine = np.maximum(msk(np.abs(f1) - .10, .08), msk(np.abs(f2 * f1 + .3 * np.sin(2 * PI * A * 16)) - .07, .08) * .8)
    leaf = msk(np.hypot(np.mod(A * 8, 1) - .5, (np.mod(B * 8 + .5 * np.floor(A * 8), 1) - .5) * 1.8) - .11, .06)
    g = np.abs(np.mod(B * 4, 1) - .5)
    bandm = smooth(.40, .43, g)
    orn = np.clip(np.maximum(vine * .9, leaf) * (1 - bandm) + bandm, 0, 1)
    gv = (.8 + .4 * fbm(A, B, 32, 32, 2, 73)) * (1 - .45 * msk(np.abs(g - .47) - .008, .01))
    rv, _ = rivets(A, B, 16, 4, .5, .010)
    gv = gv * (1 - .5 * rv * bandm)
    rgb = mixc(rgb, gold[None, None, :] * gv[..., None], orn)
    rgb *= (1 + scratches(A, B, 74, 16, .2))[..., None]
    return rgb, one(A)


def p_wood(A, B):
    w = vn(A, B, 4, 2, 81)
    v = 1 + .16 * np.sin(2 * PI * (A * 24 + 2.2 * w)) + .1 * (fbm(A, B, 64, 4, 2, 82) - .5) * 2
    v *= .9 + .2 * fbm(A, B, 4, 4, 2, 83)
    return grey(norm(v)), one(A)


def p_planks(A, B):
    c = A * 8; f = c - np.floor(c)
    w = vn(A, B, 8, 2, 85)
    v = 1 + .15 * np.sin(2 * PI * (A * 40 + 2.0 * w)) + .1 * (fbm(A, B, 64, 4, 2, 86) - .5) * 2
    v *= .85 + .3 * _h(np.floor(c).astype(np.int64) % 8, np.zeros_like(c, np.int64), 87)
    v *= 1 - .6 * smooth(.44, .5, np.abs(f - .5))
    return grey(norm(v)), one(A)


def p_fur(A, B):
    v = .55 + .9 * fbm(A, B, 64, 8, 2, 91) * (.6 + .8 * fbm(A, B, 12, 6, 2, 92))
    return grey(norm(v)), one(A)


def p_felt(A, B):
    v = (.86 + .28 * fbm(A, B, 32, 32, 3, 95)) * (.92 + .16 * fbm(A, B, 4, 4, 2, 96))
    return grey(norm(v)), one(A)


def p_feather(A, B):
    f = np.abs(np.mod(A * 4, 1) - .5)
    v = 1 + .14 * np.sin(2 * PI * (B * 40 + f * 30)) + .3 * smooth(.04, .0, f)
    return grey(norm(v)), one(A)


# ----------------------------------------------------------------------------- unique cloth charts
def p_tabard(A, B, hem, style):
    """a around the body (front at .25, seam under the right arm), b = height .50 .. 1.55 m"""
    Bc = np.clip(B, 0, 1)
    z = .5 + 1.05 * Bc
    v = weave(A, Bc, 101) * (.9 + .2 * fbm(A, Bc, 8, 2, 3, 102))
    sk = smooth(1.03, .92, z)
    v *= 1 - sk * .26 * (.5 + .5 * np.sin(2 * PI * (A * 12 + .7 * vn(A, Bc, 4, 3, 103))))
    v *= 1 - .22 * (1 - sk) * (fbm(A, Bc, 6, 10, 2, 104) - .5) * 2 * smooth(1.5, 1.3, z)
    v *= 1 - .32 * np.exp(-((z - 1.065) / .05) ** 2)
    v *= 1 - .3 * msk(np.abs(np.mod(A * 2, 1) - .5) - .492, .006)                 # side seams
    mud = np.clip(smooth(hem + .30, hem + .02, z) * fbm(A, Bc, 16, 8, 3, 105) * 1.1, 0, 1)
    rgb = mixc(grey(v), grey(v) * np.array([.72, .62, .50], F32), mud)
    aa = .006
    if style == 0:
        cnt = msk(np.abs(z - (hem + .075)) - .028, aa)
    else:
        tri = np.abs(np.mod(A * 16, 1) - .5) * 2
        cnt = msk(z - (hem + .045 + .10 * tri), aa)
    cnt = np.maximum(cnt, msk(1.468 - z, aa))                                      # collar
    cnt *= 1 - .6 * mud
    rgb = rgb * (1 - .25 * msk(np.abs(z - (hem + .075)) - .034, aa) * (1 - cnt) * (style == 0))[..., None]
    return norm(rgb, 1.0), 1 - cnt


def p_mantle(A, B):
    """hood / shoulder cape: cloth with a dagged counter-colour edge at the bottom"""
    Bc = np.clip(B, 0, 1)
    v = weave(A, Bc, 111) * (.88 + .24 * fbm(A, Bc, 8, 3, 3, 112))
    tri = np.abs(np.mod(A * 16, 1) - .5) * 2
    cnt = msk(Bc - (.07 + .12 * tri), .012)
    return grey(norm(v)), 1 - cnt


def p_cape(A, B):
    """warlord's cloak, full colour: crimson damask, gold border and lozenges"""
    Ac = np.clip(A, 0, 1); Bc = np.clip(B, 0, 1)
    crim = lin((.82, .13, .12)); gold = lin((.95, .72, .28))
    v = (.82 + .36 * fbm(Ac, Bc, 6, 3, 3, 121)) * weave(Ac, Bc, 122, 90)
    v *= .78 + .3 * np.abs(np.sin(PI * Ac * 4))                                    # deep folds along the columns
    u = Ac * 7; w = Bc * 12
    loz = np.abs(np.mod(u + w, 1) - .5) + np.abs(np.mod(u - w, 1) - .5)
    dam = msk(np.abs(loz - .5) - .05, .05)
    dot = msk(np.abs(np.mod(u + w, 1) - .5) + np.abs(np.mod(u - w, 1) - .5) - .13, .04) * (np.mod(np.floor(u + w) + np.floor(u - w), 2) < 1)
    rgb = crim[None, None, :] * (v * (1 + .35 * dam))[..., None]
    e = np.minimum(np.minimum(Ac, 1 - Ac) * .74, Bc * 1.24)                          # metres from the side / bottom edge
    border = msk(np.abs(e - .055) - .030, .006)
    line = msk(np.abs(e - .105) - .006, .005)
    gp = .75 + .5 * (np.sin(2 * PI * Ac * 40) * np.sin(2 * PI * Bc * 66) > 0)
    gm = np.clip(np.maximum(border, line) + dot * (e > .13), 0, 1)
    rgb = mixc(rgb, gold[None, None, :] * (gp * v)[..., None], gm)
    rgb *= (1 - .45 * smooth(.25, 0, Bc) * fbm(Ac, Bc, 12, 6, 2, 123))[..., None]
    return rgb, one(A)


# ----------------------------------------------------------------------------- shields / badges
def field(A, B, seed):
    v = (.9 + .2 * fbm(A, B, 6, 6, 3, seed)) * (1 - .12 * smooth(.42, .5, np.abs(np.mod(A * 5, 1) - .5)))
    v *= 1 - .4 * smooth(.74, .84, fbm(A, B, 20, 20, 2, seed + 1))                  # chipped paint
    v += scratches(A, B, seed + 2, 22, .22)
    return v


def p_shield(A, B, shape, hidx, layout):
    Ac = np.clip(A, -.04, 1.04); Bc = np.clip(B, -.04, 1.04)
    x = (Ac - .5) * 2 / .94; y = (Bc - .5) * 2 / .94
    v = field(Ac, Bc, 131 + hidx * 7 + shape * 3)
    if shape == 0:
        r = np.hypot(x, y)
        v *= 1 - .3 * smooth(.7, 1.0, r)
        s = .60; cx, cy = x / s, y / s
        bord = msk(np.abs(r - .86) - .035, .02)
    else:
        v *= 1 - .25 * smooth(.45, .75, np.abs(x)) - .15 * smooth(.6, 1, np.abs(y))
        s = .50; cx, cy = x / s, (y - .16) / s
        bord = np.zeros_like(A)
    aa = 2.6 / (176 * SS) / .94 * 2 / s
    d = CHARGES[hidx](cx, cy)
    m = msk(d, aa)
    edge = np.exp(-(d / (aa * 2.2)) ** 2)
    if layout == 0:
        cnt = np.maximum(m, bord)
    else:               # colours reversed: counter-colour field, tinted device, tinted bordure (round) or chief (heater)
        keep = bord if shape == 0 else msk(.70 - y, aa * s)
        cnt = (1 - m) * (1 - keep)
    rgb = grey(v * (1 - .45 * edge))
    return rgb, 1 - np.clip(cnt, 0, 1)


def p_badge(A, B, hidx):
    Ac = np.clip(A, 0, 1); Bc = np.clip(B, 0, 1)
    v = weave(Ac, Bc, 151) * (.9 + .2 * fbm(Ac, Bc, 8, 2, 3, 152))
    cx = (Ac - .5) * 176 / 35.0; cy = (Bc - .5) * 80 / 35.0
    aa = 2.6 / (35.0 * SS)
    d = CHARGES[hidx](cx, cy)
    return grey(v * (1 - .35 * np.exp(-(d / (aa * 2)) ** 2))), 1 - msk(d, aa)


# ----------------------------------------------------------------------------- faces
TONES = dict(pale=(.87, .70, .60), fair=(.84, .64, .52), ruddy=(.82, .58, .47), tan=(.76, .56, .42), olive=(.70, .54, .39),
             brown=(.56, .39, .28), dark=(.43, .29, .21))
HAIRS = dict(black=(.10, .085, .07), dbrown=(.21, .14, .09), brown=(.33, .22, .13), auburn=(.45, .22, .11), blond=(.66, .52, .29),
             grey=(.55, .54, .52))
FACES = [('fair', 'brown', 'stub', 0), ('pale', 'blond', 'none', 0), ('tan', 'black', 'moust', 0), ('ruddy', 'auburn', 'full', 0),
         ('fair', 'dbrown', 'none', 0), ('olive', 'black', 'stub', 0), ('pale', 'grey', 'full', 1), ('tan', 'brown', 'goat', 0),
         ('brown', 'black', 'none', 0), ('ruddy', 'blond', 'moust', 0), ('fair', 'black', 'full', 0), ('pale', 'auburn', 'stub', 0),
         ('dark', 'black', 'stub', 0), ('tan', 'dbrown', 'none', 0), ('olive', 'grey', 'moust', 1), ('fair', 'brown', 'goat', 0)]
FACE_B0 = 32.0 / 176.0          # the face proper fills b = FACE_B0 .. 1 (x +-70 mm, z 1565 .. 1745 mm); below it: skin patch | hair patch
SKIN_PT = (.22, .068); HAIR_PT = (.78, .068)


def p_face(A, B, tone, hair, beard, old, seed, scar=0, res=1.0):
    Ac = np.clip(A, 0, 1); Bc = np.clip(B, 0, 1)
    X = (Ac - .5) * 140.0; aX = np.abs(X)
    Z = 1565.0 + (Bc - FACE_B0) / (1 - FACE_B0) * 180.0
    skin = lin(TONES[tone]); hc = lin(HAIRS[hair])
    aa = 1.5 / res
    v = (1 - .16 * (aX / 70) ** 2.2) * (.95 + .1 * vn(Ac, Bc, 6, 8, seed))
    v *= 1 - .30 * smooth(1722, 1745, Z)                                          # shadow of the helmet rim
    v *= 1 - .20 * smooth(52, 68, aX)
    col = skin[None, None, :] * v[..., None]
    red = np.exp(-(((aX - 30) / 14) ** 2 + ((Z - 1630) / 12) ** 2)) * .5 + np.exp(-((X / 7) ** 2 + ((Z - 1640) / 9) ** 2)) * .45
    col *= 1 + red[..., None] * np.array([.08, -.10, -.12], F32)
    col *= (1 - .34 * np.exp(-(((aX - 22) / 15) ** 2 + ((Z - 1677) / 8) ** 2)))[..., None]          # eye sockets
    col *= (1 - .22 * np.exp(-(((aX - 9) / 3.5) ** 2)) * smooth(1632, 1640, Z) * smooth(1678, 1668, Z))[..., None]
    col *= (1 + .10 * np.exp(-((X / 3.2) ** 2)) * smooth(1634, 1642, Z) * smooth(1682, 1670, Z))[..., None]
    col *= (1 - .40 * np.exp(-((X / 11) ** 2 + ((Z - 1626.5) / 3.2) ** 2)))[..., None]              # under the nose
    col = mixc(col, skin * .2, msk(sd_ell(aX, Z, 5.5, 1631, 3.0, 1.7), aa) * .85)
    col *= (1 - (.16 + .12 * old) * msk(sd_seg(aX, Z, 10, 1632, 20, 1609, .7), aa * 1.5))[..., None]  # nasolabial fold
    # mouth
    mz = 1607.0 - (X / 15) ** 2 * 1.4
    lipu = msk(sd_ell(X, Z - mz, 0, 2.2, 13, 2.6), aa); lipl = msk(sd_ell(X, Z - mz, 0, -3.2, 11, 3.2), aa)
    col = mixc(col, skin * np.array([.80, .50, .48], F32), lipu * .8)
    col = mixc(col, skin * np.array([.95, .64, .62], F32), lipl * .75)
    col = mixc(col, skin * np.array([.28, .14, .13], F32), msk(np.hypot(np.maximum(aX - 14, 0), Z - mz) - 1.25, aa))
    col *= (1 - .25 * np.exp(-((X / 9) ** 2 + ((Z - mz + 8.5) / 2.5) ** 2)))[..., None]
    # eyes
    ex, ez = 22.0, 1672.0
    dx = aX - ex
    white = msk(sd_ell(dx, Z, 0, ez, 9.0, 4.0), aa)
    col = mixc(col, np.array([.60, .58, .54], F32) * np.ones_like(col), white)
    irc = lin((.20, .13, .08)) if hair in ('black', 'dbrown', 'brown') else lin((.26, .36, .44))
    col = mixc(col, irc * np.ones_like(col), msk(sd_circ(dx, Z, 0, ez + .3, 3.4), aa))
    col = mixc(col, np.zeros_like(col) + .01, msk(sd_circ(dx, Z, 0, ez + .3, 1.5), aa))
    lid = ez + 4.1 * np.sqrt(np.clip(1 - (dx / 10.2) ** 2, 0, 1))
    col = mixc(col, skin * .16, msk(np.abs(Z - lid) - 1.3, aa) * (np.abs(dx) < 10.2))
    col = mixc(col, skin * .55, msk(np.abs(Z - (ez - 3.4 * np.sqrt(np.clip(1 - (dx / 8.6) ** 2, 0, 1)))) - .45, aa) * (np.abs(dx) < 8.6) * .6)
    # hair
    hn = .65 + .7 * vn(Ac, Bc, 90, 22, seed + 5)
    hair_rgb = hc[None, None, :] * hn[..., None]
    bw = 2.4 + 1.2 * ((seed * 7) % 5) / 4.0
    brow = msk(sd_seg(aX, Z, 8.5, 1683.0 + ((seed * 3) % 4) * .6, 34, 1687.5, bw, 1.5), aa)
    col = mixc(col, hair_rgb, brow * .92)
    lips = np.maximum(lipu, lipl)
    fuzz = .55 + .9 * vn(Ac, Bc, 70, 60, seed + 9)
    jaw = 1611.0 + 30.0 * (aX / 60) ** 1.25
    moust = msk(sd_seg(aX, Z, 0, 1615.5, 21, 1607.5, 3.6, 1.8), aa * 1.5)
    if beard == 'stub':
        zone = np.clip(smooth(jaw + 6, jaw - 4, Z) + msk(sd_seg(aX, Z, 0, 1616, 20, 1608, 5, 3), aa * 3), 0, 1) * (1 - lips)
        col = mixc(col, col * .5 + hair_rgb * .22, zone * .8 * np.clip(fuzz, 0, 1))
    elif beard == 'moust':
        col = mixc(col, hair_rgb, moust * .95)
    elif beard == 'full':
        zone = np.clip(smooth(jaw + 5 * fuzz, jaw - 3, Z), 0, 1) * (1 - msk(sd_ell(X, Z, 0, 1605.5, 12, 4.4), aa * 2))
        col = mixc(col, hair_rgb, np.maximum(zone, moust) * .96)
    elif beard == 'goat':
        zone = msk(sd_ell(X, Z, 0, 1584 - 3 * fuzz, 16, 17), aa * 2) * (1 - lips)
        col = mixc(col, hair_rgb, np.maximum(zone, moust) * .95)
    if old:
        for zc in (1702.0, 1711.0):
            col *= (1 - .2 * msk(np.abs(Z - zc - 1.3 * np.sin(X / 9.0)) - .5, aa) * (aX < 38))[..., None]
        col *= (1 - .15 * msk(sd_seg(aX, Z, 31, 1672, 39, 1675, .5), aa))[..., None]
    if scar:
        col = mixc(col, skin * np.array([1.12, .80, .78], F32), msk(sd_seg(X, Z, 10, 1694, 31, 1636, .9), aa) * .8)
    col = mixc(col, hair_rgb, smooth(1738, 1742, Z) * .9)
    # patches under the face
    strip = Bc < 26.0 / 176.0
    col = np.where(strip[..., None], np.where((Ac < .5)[..., None], skin * .92, hc * 1.0) * np.ones_like(col), col)
    col = np.where(((Bc >= 26.0 / 176.0) & (Bc < FACE_B0))[..., None], skin[None, None, :] * np.ones_like(col), col)
    return col, one(A)


# ----------------------------------------------------------------------------- layout
CH = {}


def _add(name, x, y, w, h, fn=None, args=()):
    CH[name] = Chart(name, x, y, w, h, fn, args)
    return CH[name]


_add('face', 0, 0, 128, 192)
_add('shR', 0, 192, 192, 192)
_add('shH', 0, 576, 192, 192)
_add('badge', 0, 960, 192, 96)
_add('wface', 1536, 192, 256, 384, p_face, ('pale', 'black', 'full', 1, 77, 1, 2.0))
_add('cape', 1792, 192, 256, 512, p_cape)
_add('tabard', 1536, 576, 256, 256, p_tabard, (.66, 0))
_add('surcoat', 1792, 704, 256, 256, p_tabard, (.55, 1))
_add('mantle', 1536, 832, 256, 224, p_mantle)
_tiles = [('white', p_white), ('mail', p_mail), ('gamb', p_gamb), ('cloth', p_cloth), ('hose', p_hose), ('leather', p_leather), ('plate', p_plate),
          ('helm', p_helm), ('gilt', p_gilt), ('gold', p_gold), ('wood', p_wood), ('planks', p_planks), ('fur', p_fur), ('felt', p_felt),
          ('feather', p_feather), ('steel', p_steel)]
for _i, (_n, _f) in enumerate(_tiles):
    _add(_n, (_i % 8) * 256, 1056 + (_i // 8) * 256, 256, 256, _f)
WHITE_UV = CH['white'].uv(.5, .5)


def _render(img, x, y, w, h, pad, fn, args):
    W = w * SS; H = h * SS
    a = ((np.arange(W) + .5) / SS - pad) / (w - 2 * pad)
    b = 1 - ((np.arange(H) + .5) / SS - pad) / (h - 2 * pad)
    A, B = np.meshgrid(a.astype(F32), b.astype(F32))
    rgb, al = fn(A, B, *args)
    rgba = np.dstack([rgb, al]).astype(F32).reshape(h, SS, w, SS, 4).mean(axis=(1, 3))
    img[y:y + h, x:x + w] = rgba


def paint(path, save):
    """save(path, rgba_uint8_top_down) is supplied by the caller (bpy image writer)"""
    img = np.ones((AT, AT, 4), F32)
    for ch in CH.values():
        if ch.fn:
            _render(img, ch.x, ch.y, ch.w, ch.h, ch.pad, ch.fn, ch.args)
    for k, (tone, hair, beard, old) in enumerate(FACES):
        _render(img, k * 128, 0, 128, 192, 8, p_face, (tone, hair, beard, old, k + 1, 1 if k in (3, 12) else 0))
    for h in range(8):
        cx = CELL_OF[h] * 192
        for row, (shape, layout) in enumerate(((0, 0), (0, 1), (1, 0), (1, 1))):
            _render(img, cx, 192 + row * 192, 192, 192, 8, p_shield, (shape, h, layout))
        _render(img, cx, 960, 192, 96, 8, p_badge, (h,))
    rgb = np.clip(img[..., :3] / GAIN, 0, 1)
    rgb = np.where(rgb <= .0031308, rgb * 12.92, 1.055 * np.power(np.maximum(rgb, 1e-6), 1 / 2.4) - .055)
    out = np.dstack([rgb, np.clip(img[..., 3:], 0, 1)])
    save(path, out)
