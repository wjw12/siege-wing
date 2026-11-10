# Siege Wing - soldier set generator (headless Blender 5.2)
#   blender.exe -b -P soldiers.py            -> build + export assets/models/soldiers.glb
#   blender.exe -b -P soldiers.py -- preview -> also render preview sheets to tools/blender/preview/sold_*.png
import bpy, math, sys, os, random
from mathutils import Vector, Matrix

ROOT = r"C:\Users\shaoy\game"
OUT = ROOT + r"\assets\models\soldiers.glb"
PREV = ROOT + r"\tools\blender\preview"
ARGS = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
DO_PREVIEW = 'preview' in ARGS
FPS = 24

X, Y, Z = Vector((1, 0, 0)), Vector((0, 1, 0)), Vector((0, 0, 1))

# ----------------------------------------------------------------------------- colours (sRGB)
STEEL = (.62, .64, .68); DSTEEL = (.36, .37, .41); SKIN = (.80, .60, .48); LEATH = (.38, .25, .15)
DLEATH = (.20, .14, .10); WOOD = (.47, .34, .21); TINT = (.93, .91, .87); HOSE = (.31, .27, .22)
GAMB = (.64, .57, .45); GOLD = (.88, .68, .22); HOOD = (.29, .33, .20); FUR = (.25, .19, .14)
IRON = (.20, .20, .22); ARROW = (.78, .68, .48); BLACK = (.05, .05, .05)


def sh(c, k):
    return tuple(min(1.0, v * k) for v in c)


def lin(c):
    return tuple((v / 12.92) if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in c)


# ----------------------------------------------------------------------------- mesh builder
class MB:
    def __init__(s):
        s.v = []; s.f = []; s.c = []; s.t = []; s.m = []; s.b = []

    def add(s, p, col, bone, tint=0.0, metal=0.0):
        s.v.append(tuple(p)); s.c.append(col); s.b.append(bone); s.t.append(tint); s.m.append(metal)
        return len(s.v) - 1

    def ring(s, c, u, v, ru, rv, n, phase, col, bone, tint=0.0, metal=0.0, fn=None):
        idx = []
        for i in range(n):
            a = phase + 2 * math.pi * i / n
            p = c + u * (ru * math.cos(a)) + v * (rv * math.sin(a))
            d = dict(col=col, bone=bone, tint=tint, metal=metal)
            if fn:
                d.update(fn(p) or {})
            idx.append(s.add(p, d['col'], d['bone'], d['tint'], d['metal']))
        return idx

    def bridge(s, a, b):
        n = len(a)
        for i in range(n):
            j = (i + 1) % n
            s.f.append((a[i], a[j], b[j], b[i]))

    def loft(s, rings, n, cap_bot=False, cap_top=False):
        """horizontal elliptical rings, ascending z: (z, rx, ry, bone, col, opts)"""
        phase = math.pi / 4 if n == 4 else (-math.pi / 2 if n == 3 else 0.0)
        k = 1.3 if n == 4 else (1.45 if n == 3 else 1.0)
        prev = first = None
        for r in rings:
            z, rx, ry, bone, col = r[:5]
            o = r[5] if len(r) > 5 else {}
            c = Vector((o.get('x', 0), o.get('y', 0), z))
            idx = s.ring(c, X, Y, rx * k, ry * k, n, phase, col, bone, o.get('tint', 0), o.get('metal', 0), o.get('fn'))
            if prev:
                s.bridge(prev, idx)
            else:
                first = idx
            prev = idx
        if cap_bot:
            s.f.append(tuple(reversed(first)))
        if cap_top:
            s.f.append(tuple(prev))

    def cyl(s, p0, p1, r0, r1, n, col, bone, tint=0.0, metal=0.0, cap0=False, cap1=False, up=None, col1=None):
        p0 = Vector(p0); p1 = Vector(p1)
        d = (p1 - p0).normalized()
        ref = Vector(up) if up is not None else (Z if abs(d.z) < 0.9 else X)
        u = (ref - d * ref.dot(d)).normalized()
        v = d.cross(u)
        r0 = r0 if isinstance(r0, tuple) else (r0, r0)
        a = s.ring(p0, u, v, r0[0], r0[1], n, 0.0, col, bone, tint, metal)
        if cap0:
            s.f.append(tuple(reversed(a)))
        if r1 == 0:
            ap = s.add(p1, col1 or col, bone, tint, metal)
            for i in range(n):
                s.f.append((a[i], a[(i + 1) % n], ap))
        else:
            r1 = r1 if isinstance(r1, tuple) else (r1, r1)
            b = s.ring(p1, u, v, r1[0], r1[1], n, 0.0, col1 or col, bone, tint, metal)
            s.bridge(a, b)
            if cap1:
                s.f.append(tuple(b))

    def tube(s, pts, r, n, col, bone, tint=0.0, metal=0.0, side=X):
        prev = None
        for i, p in enumerate(pts):
            p = Vector(p)
            t = (Vector(pts[min(i + 1, len(pts) - 1)]) - Vector(pts[max(i - 1, 0)])).normalized()
            u = Vector(side); v = t.cross(u)
            rr = r[i] if isinstance(r, (list, tuple)) else r
            idx = s.ring(p, u, v, rr, rr, n, 0.0, col, bone, tint, metal)
            if prev:
                s.bridge(prev, idx)
            prev = idx

    def box(s, c, size, col, bone, tint=0.0, metal=0.0, rot=None):
        c = Vector(c); h = Vector(size) * 0.5
        ids = []
        for i in range(8):
            o = Vector((h.x if i & 1 else -h.x, h.y if i & 2 else -h.y, h.z if i & 4 else -h.z))
            if rot is not None:
                o = rot @ o
            ids.append(s.add(c + o, col, bone, tint, metal))
        for q in ((1, 3, 7, 5), (0, 4, 6, 2), (2, 6, 7, 3), (0, 1, 5, 4), (4, 5, 7, 6), (0, 2, 3, 1)):
            s.f.append(tuple(ids[k] for k in q))

    def plate(s, pts, nrm, t, colf, colb, bone, tintf=0.0, metal=0.0, tintb=0.0):
        """two-sided flat polygon; pts CCW seen from the +nrm side"""
        nrm = Vector(nrm)
        f = [s.add(Vector(p) + nrm * (t / 2), colf, bone, tintf, metal) for p in pts]
        b = [s.add(Vector(p) - nrm * (t / 2), colb, bone, tintb, metal) for p in pts]
        s.f.append(tuple(f)); s.f.append(tuple(reversed(b)))

    def tris(s):
        return sum(len(f) - 2 for f in s.f)


# ----------------------------------------------------------------------------- body
def body(mb, lod, sp):
    nT = 8 if lod == 0 else 4
    nL = 6 if lod == 0 else 3
    nH = 8 if lod == 0 else 4
    bk = sp.get('bulk', 1.0) * 1.08
    tc, tt, tm = sp['torso']
    T = dict(tint=tt, metal=tm)
    if lod == 0:
        rings = [(0.90, .15 * bk, .105 * bk, 'Hips', sh(tc, .78), T), (1.05, .14 * bk, .098 * bk, 'Spine', sh(tc, .9), T),
                 (1.30, .175 * bk, .118 * bk, 'Chest', tc, T), (1.45, .195 * bk, .118 * bk, 'Chest', tc, T),
                 (1.53, .07, .065, 'Chest', sh(tc, .85), T)]
    else:
        rings = [(0.90, .15 * bk, .105 * bk, 'Hips', sh(tc, .78), T), (1.06, .14 * bk, .098 * bk, 'Spine', sh(tc, .9), T),
                 (1.43, .19 * bk, .118 * bk, 'Chest', tc, T), (1.53, .07, .065, 'Chest', sh(tc, .85), T)]
    mb.loft(rings, nT, cap_bot=True)

    sk = sp.get('skirt')
    if sk:
        zb, c, t, m = sk
        fnb = lambda p: {'bone': 'UpperLeg.L' if p.x > 0.06 else ('UpperLeg.R' if p.x < -0.06 else 'Hips')}
        O = dict(tint=t, metal=m)
        r = [(zb, .215 * bk, .17 * bk, 'Hips', sh(c, .70), dict(O, fn=fnb))]
        if lod == 0:
            r.append((0.90, .19 * bk, .142 * bk, 'Hips', sh(c, .84), O))
        r.append((1.08, .152 * bk, .110 * bk, 'Spine', sh(c, .95), O))
        mb.loft(r, nT)

    lc, lm = sp['leg']; sc, sm = sp['shin']; bc, bm = sp['boot']
    for side, sx in (('L', 1), ('R', -1)):
        x = .10 * sx
        UL = 'UpperLeg.' + side; LL = 'LowerLeg.' + side
        if lod == 0:
            mb.loft([(0.07, 0.055, 0.062, LL, sh(sc, .8), dict(x=x, metal=sm)),
                     (0.36, 0.074, 0.082, LL, sc, dict(x=x, y=.012, metal=sm)),
                     (0.50, 0.070, 0.074, LL, sc, dict(x=x, metal=sm)),
                     (0.93, 0.103, 0.110, UL, lc, dict(x=x, metal=lm))], nL)
            mb.box((x, -.055, .047), (.11, .26, .10), bc, 'Foot.' + side, metal=bm)
        else:
            mb.loft([(0.0, 0.060, 0.102, LL, sh(bc, .9), dict(x=x, y=-.03, metal=bm)),
                     (0.50, 0.070, 0.074, LL, sc, dict(x=x, metal=sm)),
                     (0.93, 0.103, 0.110, UL, lc, dict(x=x, metal=lm))], nL, cap_bot=True)

    ac, am = sp['arm']; fc, fm = sp['forearm']; hc, hm = sp['hand']
    for side, sx in (('L', 1), ('R', -1)):
        x = .238 * sx
        UA = 'UpperArm.' + side; LA = 'LowerArm.' + side
        if lod == 0:
            mb.loft([(0.93, 0.046, 0.049, LA, sh(fc, .85), dict(x=x + .005 * sx, metal=fm)),
                     (1.18, 0.061, 0.065, LA, fc, dict(x=x + .005 * sx, metal=fm)),
                     (1.33, 0.070, 0.074, UA, ac, dict(x=x, metal=am)),
                     (1.47, 0.079, 0.086, UA, ac, dict(x=x, metal=am))], nL, cap_top=True)
            mb.box((x + .005 * sx, 0, .865), (.07, .095, .115), hc, 'Hand.' + side, metal=hm)
        else:
            mb.loft([(0.84, 0.048, 0.054, LA, hc, dict(x=x, metal=hm)),
                     (1.18, 0.061, 0.065, LA, fc, dict(x=x, metal=fm)),
                     (1.47, 0.079, 0.086, UA, ac, dict(x=x, metal=am))], nL, cap_bot=True, cap_top=True)

    if not sp.get('no_head'):
        hb, hbm = sp.get('head_back', (SKIN, 0))
        fn = lambda p: ({'col': SKIN, 'metal': 0} if (p.y < -0.03 and p.z < 1.74) else {})
        if lod == 0:
            rr = [(1.50, .055, .06), (1.58, .086, .096), (1.68, .096, .106), (1.77, .086, .096)]
        else:
            rr = [(1.52, .06, .065), (1.63, .09, .10), (1.78, .08, .09)]
        mb.loft([(z, a, b, 'Head', hb, dict(metal=hbm, fn=fn)) for z, a, b in rr], nH, cap_top=True)


# ----------------------------------------------------------------------------- gear
def spear(mb, lod):
    x = -.23; z = .865
    if lod == 0:
        mb.cyl((x, 1.0, z), (x, -1.12, z), .019, .019, 4, WOOD, 'Hand.R', cap0=True)
        mb.cyl((x, -1.10, z), (x, -1.40, z), (.042, .014), 0, 4, STEEL, 'Hand.R', metal=1, cap0=True)
    else:
        mb.cyl((x, 1.0, z), (x, -1.15, z), .024, .024, 3, WOOD, 'Hand.R')
        mb.cyl((x, -1.15, z), (x, -1.40, z), .034, 0, 3, STEEL, 'Hand.R', metal=1)


def round_shield(mb, lod):
    c = Vector((.305, 0, 1.05)); n = 10 if lod == 0 else 6; R = .40
    B = 'LowerArm.L'
    pts = [c + Vector((0, R * math.cos(2 * math.pi * i / n), R * math.sin(2 * math.pi * i / n))) for i in range(n)]
    ring = [mb.add(p, sh(TINT, .88), B, 1, 0) for p in pts]
    ctr = mb.add(c + Vector((.06, 0, 0)), TINT, B, 1, 0)
    for i in range(n):
        mb.f.append((ring[i], ring[(i + 1) % n], ctr))
    back = [mb.add(p, sh(WOOD, .7), B, 0, 0) for p in pts]
    mb.f.append(tuple(reversed(back)))
    if lod == 0:
        mb.cyl(c + Vector((.04, 0, 0)), c + Vector((.12, 0, 0)), .075, 0, 6, STEEL, B, metal=1)


def heater_shield(mb, lod):
    cx, cy, cz = .305, 0.0, 1.05
    if lod == 0:
        o = [(-.30, -.24), (.05, -.25), (.25, -.16), (.38, 0), (.25, .16), (.05, .25), (-.30, .24)]
    else:
        o = [(-.30, -.24), (.10, -.25), (.38, 0), (.10, .25), (-.30, .24)]
    pts = [(cx, cy + a, cz + b) for a, b in o]
    mb.plate(pts, X, .02, TINT, sh(WOOD, .7), 'LowerArm.L', tintf=1)
    if lod == 0:  # steel rim boss strip
        mb.box((cx + .02, cy - .30, cz), (.02, .03, .50), STEEL, 'LowerArm.L', metal=1)


def sword(mb, lod):
    x = -.23; z = .865; B = 'Hand.R'
    if lod == 0:
        mb.cyl((x, .10, z), (x, -.10, z), .018, .018, 4, DLEATH, B, cap0=True)
        mb.box((x, .12, z), (.05, .05, .05), GOLD, B, metal=1)
        mb.box((x, -.105, z), (.03, .03, .24), STEEL, B, metal=1)
        mb.cyl((x, -.11, z), (x, -.90, z), (.036, .010), (.026, .008), 4, STEEL, B, metal=1, up=Z)
        mb.cyl((x, -.90, z), (x, -1.0, z), (.026, .008), 0, 4, STEEL, B, metal=1, up=Z)
    else:
        mb.cyl((x, .10, z), (x, -1.0, z), (.04, .016), 0, 3, STEEL, B, metal=1, up=Z)
        mb.box((x, -.105, z), (.03, .03, .22), STEEL, B, metal=1)


def bow(mb, lod):
    x = .235; z0 = .865; B = 'Hand.L'
    f = lambda s: Vector((x, .80 * s, z0 + .24 * s * s))
    if lod == 0:
        pts = [f(-1 + i / 3) for i in range(7)]
        mb.tube(pts, [.008, .013, .017, .02, .017, .013, .008], 3, sh(WOOD, 1.15), B)
        mb.cyl(f(-1), f(1), .004, .004, 3, (.85, .82, .7), B)
        mb.cyl((x + .022, 0, z0 + .22), (x + .022, 0, z0 - .50), .008, .008, 3, ARROW, B)
        mb.cyl((x + .022, 0, z0 - .50), (x + .022, 0, z0 - .58), .016, 0, 3, STEEL, B, metal=1)
    else:
        ss = [-1, -.5, 0, .5, 1]
        for a, b in zip(ss[:-1], ss[1:]):
            p0, p1 = f(a), f(b); w = Vector((0, 0, .05))
            # quad (p0, p1, p1+w, p0+w): e1=+Y, e2=+Z -> normal +X
            mb.plate([p0 - w * .5, p1 - w * .5, p1 + w * .5, p0 + w * .5], X, .012, WOOD, WOOD, B)


def quiver(mb, lod):
    if lod == 0:
        mb.cyl((-.13, .155, 1.0), (.05, .155, 1.50), .05, .055, 5, LEATH, 'Chest', cap0=True)
        mb.cyl((.05, .155, 1.50), (.085, .155, 1.60), .045, .05, 5, (.9, .88, .8), 'Chest', cap1=True)
    else:
        mb.cyl((-.13, .155, 1.0), (.08, .155, 1.58), .05, .05, 3, LEATH, 'Chest', cap1=True, col1=(.9, .88, .8))


def axe(mb, lod):
    x = -.23; z = .865; B = 'Hand.R'
    mb.cyl((x, .60, z), (x, -1.15, z), .022, .022, 4 if lod == 0 else 3, sh(WOOD, .7), B, cap0=True)
    mb.cyl((x, -1.13, z), (x, -1.32, z), .03, 0, 4, STEEL, B, metal=1)
    yc = -.95
    A = [(-.04, .02), (.04, .02), (.17, .22), (0, .27), (-.17, .22)]
    Bp = [(-.04, -.02), (-.17, -.22), (0, -.27), (.17, -.22), (.04, -.02)]
    for o in (A, Bp):
        mb.plate([(x, yc + a, z + b) for a, b in o], X, .016, STEEL, STEEL, B, metal=1)


def cape(mb, lod, col=TINT, tint=1):
    rows = [(1.50, .20, .130, 'Chest'), (1.15, .27, .175, 'Spine'), (0.72, .31, .215, 'Hips'), (0.30, .34, .235, 'Hips')]
    if lod:
        rows = [rows[0], rows[2], rows[3]]
    for sgn in (1, -1):
        grid = []
        for i, (z, w, y, bone) in enumerate(rows):
            k = 1.0 - .09 * i
            row = []
            for j, xx in enumerate((-w, 0, w)):
                yy = y + (.035 if j == 1 else 0) - (0 if sgn > 0 else .012)
                c = sh(col, k) if sgn > 0 else sh(col, .55 * k)
                row.append(mb.add((xx, yy, z), c, bone, tint, 0))
            grid.append(row)
        for i in range(len(rows) - 1):
            for j in range(2):
                lo, up = grid[i + 1], grid[i]  # lo = lower z
                q = (lo[j], up[j], up[j + 1], lo[j + 1])
                mb.f.append(q if sgn > 0 else tuple(reversed(q)))


# ----------------------------------------------------------------------------- types
def build_infantry(lod):
    mb = MB()
    body(mb, lod, dict(torso=(TINT, 1, 0), skirt=(0.66, TINT, 1, 0), leg=(HOSE, 0), shin=(LEATH, 0), boot=(DLEATH, 0),
                       arm=(GAMB, 0), forearm=(sh(GAMB, .9), 0), hand=(LEATH, 0), head_back=(STEEL, 1)))
    if lod == 0:
        # kettle helm with brim
        H = dict(metal=1)
        mb.loft([(1.725, .175, .185, 'Head', sh(STEEL, .85), H), (1.76, .108, .118, 'Head', STEEL, H),
                 (1.835, .075, .085, 'Head', STEEL, H), (1.865, .03, .035, 'Head', sh(STEEL, 1.1), H)], 8, cap_top=True, cap_bot=True)
        # belt + dagger + mail collar
        mb.loft([(1.035, .158, .114, 'Spine', DLEATH), (1.085, .158, .114, 'Spine', DLEATH)], 8)
        mb.box((.17, -.04, .93), (.035, .05, .22), DLEATH, 'Hips')
        mb.loft([(1.44, .215, .13, 'Chest', sh(STEEL, .8), dict(metal=1)), (1.53, .10, .09, 'Chest', STEEL, dict(metal=1))], 8)
    else:
        mb.cyl((0, 0, 1.72), (0, 0, 1.87), (.20, .21), 0, 4, STEEL, 'Head', metal=1)
    spear(mb, lod); round_shield(mb, lod)
    return mb


def build_archer(lod):
    mb = MB()
    TUN = (.42, .36, .24)
    body(mb, lod, dict(torso=(LEATH, 0, 0), skirt=(0.74, TUN, 0, 0), leg=(HOSE, 0), shin=(sh(HOSE, .8), 0), boot=(DLEATH, 0),
                       arm=(TUN, 0), forearm=(LEATH, 0), hand=(SKIN, 0), head_back=(HOOD, 0)))
    M = dict(tint=1)
    if lod == 0:
        mb.loft([(1.35, .275, .185, 'Chest', sh(TINT, .8), M), (1.47, .19, .135, 'Chest', sh(TINT, .92), M),
                 (1.56, .085, .085, 'Chest', TINT, M)], 8)
        mb.cyl((0, .02, 1.75), (0, .20, 1.70), .075, 0, 5, HOOD, 'Head')  # hood tail
        mb.loft([(1.035, .158, .114, 'Spine', DLEATH), (1.085, .158, .114, 'Spine', DLEATH)], 8)
    else:
        mb.loft([(1.36, .26, .18, 'Chest', sh(TINT, .8), M), (1.56, .085, .085, 'Chest', TINT, M)], 4)
    bow(mb, lod); quiver(mb, lod)
    return mb


def build_knight(lod):
    mb = MB()
    body(mb, lod, dict(torso=(TINT, 1, 0), skirt=(0.56, TINT, 1, 0), leg=(STEEL, 1), shin=(STEEL, 1), boot=(DSTEEL, 1),
                       arm=(STEEL, 1), forearm=(STEEL, 1), hand=(DSTEEL, 1), no_head=True, bulk=1.06))
    H = dict(metal=1)
    if lod == 0:
        mb.loft([(1.53, .10, .11, 'Head', sh(STEEL, .8), H), (1.69, .115, .125, 'Head', STEEL, H),
                 (1.82, .105, .115, 'Head', sh(STEEL, 1.05), H)], 8, cap_top=True)
        mb.box((0, -.122, 1.70), (.15, .02, .024), BLACK, 'Head')
        mb.cyl((0, 0, 1.81), (0, .05, 2.0), .035, .07, 5, TINT, 'Head', tint=1)
        mb.cyl((0, .05, 2.0), (0, .22, 1.92), .07, 0, 5, sh(TINT, .9), 'Head', tint=1)
        for side, sx in (('L', 1), ('R', -1)):
            O = dict(x=.24 * sx, metal=1)
            mb.loft([(1.41, .092, .098, 'UpperArm.' + side, sh(STEEL, .85), O), (1.49, .09, .095, 'UpperArm.' + side, STEEL, O),
                     (1.525, .04, .045, 'UpperArm.' + side, STEEL, O)], 6, cap_top=True)
        mb.loft([(1.035, .168, .122, 'Spine', DLEATH), (1.085, .168, .122, 'Spine', DLEATH)], 8)
        mb.cyl((.18, -.03, 1.02), (.27, .26, .45), .028, .02, 4, DLEATH, 'Hips', cap1=True)
    else:
        mb.loft([(1.53, .10, .11, 'Head', sh(STEEL, .8), H), (1.82, .105, .115, 'Head', STEEL, H)], 4, cap_top=True)
        mb.cyl((0, 0, 1.81), (0, .16, 1.98), .07, 0, 3, TINT, 'Head', tint=1)
    sword(mb, lod); heater_shield(mb, lod)
    return mb


def build_warlord(lod=0):
    mb = MB()
    PL = (.24, .24, .27)
    body(mb, lod, dict(torso=(PL, 0, 1), skirt=(0.58, sh(LEATH, .7), 0, 0), leg=(PL, 1), shin=(PL, 1), boot=(IRON, 1),
                       arm=(PL, 1), forearm=(PL, 1), hand=(IRON, 1), head_back=(PL, 1), bulk=1.22))
    H = dict(metal=1)
    # helm dome (open face)
    fn = lambda p: ({'col': SKIN, 'metal': 0} if (p.y < -0.05 and p.z < 1.70) else {})
    mb.loft([(1.60, .104, .114, 'Head', PL, dict(metal=1, fn=fn)), (1.74, .106, .116, 'Head', PL, H), (1.83, .07, .08, 'Head', PL, H),
             (1.87, .02, .02, 'Head', GOLD, H)], 8, cap_top=True)
    # crown
    n = 10
    a = mb.ring(Vector((0, 0, 1.735)), X, Y, .118, .128, n, 0, sh(GOLD, .85), 'Head', 0, 1)
    b = mb.ring(Vector((0, 0, 1.79)), X, Y, .125, .135, n, 0, GOLD, 'Head', 0, 1)
    for i in range(0, n, 2):
        v = mb.v[b[i]]; mb.v[b[i]] = (v[0] * 1.08, v[1] * 1.08, v[2] + .06)
    mb.bridge(a, b)
    mb.cyl((0, -.085, 1.585), (0, -.11, 1.44), (.07, .04), 0, 4, FUR, 'Head')  # beard
    # fur mantle + cape
    mb.loft([(1.33, .33, .225, 'Chest', sh(FUR, .8)), (1.47, .25, .185, 'Chest', FUR), (1.57, .095, .095, 'Chest', sh(FUR, 1.2))], 8)
    cape(mb, lod)
    # pauldrons with spikes
    for side, sx in (('L', 1), ('R', -1)):
        O = dict(x=.27 * sx, metal=1)
        mb.loft([(1.40, .105, .11, 'UpperArm.' + side, sh(PL, .85), O), (1.50, .10, .105, 'UpperArm.' + side, PL, O),
                 (1.545, .045, .05, 'UpperArm.' + side, PL, O)], 6, cap_top=True)
        mb.cyl((.29 * sx, 0, 1.53), (.40 * sx, 0, 1.66), .03, 0, 4, GOLD, 'UpperArm.' + side, metal=1)
    mb.loft([(1.03, .19, .135, 'Spine', GOLD, H), (1.09, .19, .135, 'Spine', GOLD, H)], 8)
    axe(mb, lod)
    return mb


TYPES = [('Infantry', build_infantry, 0), ('Archer', build_archer, 0), ('Knight', build_knight, 0), ('Warlord', build_warlord, 0),
         ('Infantry_LOD1', build_infantry, 1), ('Archer_LOD1', build_archer, 1), ('Knight_LOD1', build_knight, 1)]

# ----------------------------------------------------------------------------- rig
BONES = [
    ('Hips', (0, 0, .95), (0, 0, 1.08), None),
    ('Spine', (0, 0, 1.08), (0, 0, 1.28), 'Hips'),
    ('Chest', (0, 0, 1.28), (0, 0, 1.52), 'Spine'),
    ('Head', (0, 0, 1.52), (0, 0, 1.80), 'Chest'),
]
for side, sx in (('L', 1), ('R', -1)):
    BONES += [
        ('UpperArm.' + side, (.215 * sx, 0, 1.46), (.228 * sx, 0, 1.18), 'Chest'),
        ('LowerArm.' + side, (.228 * sx, 0, 1.18), (.23 * sx, 0, .93), 'UpperArm.' + side),
        ('Hand.' + side, (.23 * sx, 0, .93), (.23 * sx, 0, .81), 'LowerArm.' + side),
        ('UpperLeg.' + side, (.10 * sx, 0, .95), (.10 * sx, 0, .50), 'Hips'),
        ('LowerLeg.' + side, (.10 * sx, 0, .50), (.10 * sx, 0, .08), 'UpperLeg.' + side),
        ('Foot.' + side, (.10 * sx, 0, .08), (.10 * sx, -.17, .0), 'LowerLeg.' + side),
    ]
ALIAS = dict(hips='Hips', spine='Spine', chest='Chest', head='Head',
             uaL='UpperArm.L', laL='LowerArm.L', hL='Hand.L', uaR='UpperArm.R', laR='LowerArm.R', hR='Hand.R',
             ulL='UpperLeg.L', llL='LowerLeg.L', fL='Foot.L', ulR='UpperLeg.R', llR='LowerLeg.R', fR='Foot.R')
LIMB = {'UpperArm', 'LowerArm', 'Hand', 'UpperLeg', 'LowerLeg', 'Foot'}


def make_rig():
    arm = bpy.data.armatures.new('Rig')
    ob = bpy.data.objects.new('Rig', arm)
    bpy.context.scene.collection.objects.link(ob)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.mode_set(mode='EDIT')
    for name, head, tail, parent in BONES:
        eb = arm.edit_bones.new(name)
        eb.head = head; eb.tail = tail; eb.roll = 0
        if parent:
            eb.parent = arm.edit_bones[parent]
    bpy.ops.object.mode_set(mode='OBJECT')
    for pb in ob.pose.bones:
        pb.rotation_mode = 'QUATERNION'
    return ob


def sem_R(bone, fwd, out, tw):
    """semantic degrees -> armature-space delta rotation.
    limbs: fwd = swing forward, out = abduct away from body, tw = inward twist about limb axis
    trunk/head: fwd = bend forward, out = lean to left(+X), tw = turn left"""
    if bone.split('.')[0] in LIMB:
        s = 1 if bone.endswith('.R') else -1
        rx, ry, rz = -fwd, s * out, s * tw
    else:
        rx, ry, rz = fwd, out, tw
    return Matrix.Rotation(math.radians(rx), 3, 'X') @ Matrix.Rotation(math.radians(ry), 3, 'Y') @ Matrix.Rotation(math.radians(rz), 3, 'Z')


_prevq = {}


def apply_pose(rig, pose):
    for al, name in ALIAS.items():
        f, o, t = pose.get(al, (0, 0, 0))
        B = rig.data.bones[name].matrix_local.to_3x3()
        q = (B.inverted() @ sem_R(name, f, o, t) @ B).to_quaternion()
        pq = _prevq.get(name)
        if pq is not None and pq.dot(q) < 0:
            q.negate()
        _prevq[name] = q.copy()
        rig.pose.bones[name].rotation_quaternion = q
    B = rig.data.bones['Hips'].matrix_local.to_3x3()
    rig.pose.bones['Hips'].location = B.inverted() @ Vector(pose.get('loc', (0, 0, 0)))


# ----------------------------------------------------------------------------- poses / clips
def P(base=None, **kw):
    d = dict(base or {}); d.update(kw); return d


def D(base, **kw):
    d = dict(base)
    for k, v in kw.items():
        o = d.get(k, (0, 0, 0)); d[k] = tuple(a + b for a, b in zip(o, v))
    return d


def mix(a, b, k):
    d = {}
    for key in set(a) | set(b):
        x = a.get(key, (0, 0, 0)); y = b.get(key, (0, 0, 0))
        d[key] = tuple(p + (q - p) * k for p, q in zip(x, y))
    return d


def seq(keys, t):
    if t <= keys[0][0]:
        return keys[0][1]
    for (t0, p0), (t1, p1) in zip(keys[:-1], keys[1:]):
        if t <= t1:
            k = (t - t0) / (t1 - t0)
            k = k * k * (3 - 2 * k)
            return mix(p0, p1, k)
    return keys[-1][1]


def crouch(a, b, spread=4):
    """thigh fwd a, knee bend b -> leg entries + hips loc keeping feet planted"""
    ra, rb = math.radians(a), math.radians(b - a)
    dz = -(0.45 * (1 - math.cos(ra)) + 0.42 * (1 - math.cos(rb)))
    dy = 0.45 * math.sin(ra) - 0.42 * math.sin(rb)
    return dict(ulL=(a, spread, 0), ulR=(a, spread, 0), llL=(-b, 0, 0), llR=(-b, 0, 0), fL=(b - a, 0, 0), fR=(b - a, 0, 0), loc=(0, dy, dz))


S = math.sin; C = math.cos; TAU = 2 * math.pi
READY = dict(uaR=(5, 8, 0), laR=(85, 0, 0), uaL=(15, 10, 55), laL=(90, 0, 0), ulL=(0, 4, 0), ulR=(0, 4, 0))


def c_idle(t):
    p = TAU * t / 2.0
    return D(READY, chest=(1.5 * S(p), 0, 0), spine=(0, 1.5 * S(p), 0), head=(2 * S(p), 0, 9 * S(p)),
             loc=(.012 * S(p), 0, -.004 * (1 - C(2 * p))), uaR=(2 * S(p), 0, 0), laR=(-2 * S(p), 0, 0), uaL=(2 * C(p), 0, 0))


SHIELDUP = P(READY, **crouch(52, 95, 8), spine=(22, 0, 0), chest=(6, 0, 0), head=(12, 0, 0),
             uaL=(152, 12, 0), laL=(0, -92, 0), uaR=(25, 12, 0), laR=(75, 0, 0))


def c_shieldup(t):
    p = TAU * t / 1.0
    return D(SHIELDUP, uaL=(3 * S(p), 0, 0), laL=(0, 3 * S(2 * p), 0), spine=(1.5 * S(p), 0, 0), head=(0, 0, 6 * S(p)), uaR=(2 * C(p), 0, 0))


def c_walk(t):
    p = TAU * t / 1.0
    kL = 8 + 42 * max(0, C(p)); kR = 8 + 42 * max(0, C(p + math.pi))
    return D(READY, ulL=(26 * S(p), 0, 0), ulR=(-26 * S(p), 0, 0), llL=(-kL, 0, 0), llR=(-kR, 0, 0),
             fL=(kL * .4 - 8 * S(p), 0, 0), fR=(kR * .4 + 8 * S(p), 0, 0),
             loc=(0, 0, -.025 + .018 * C(2 * p)), spine=(4, 0, 0), chest=(0, 0, 5 * S(p)), hips=(0, 0, -4 * S(p)),
             uaR=(8 * S(p), 0, 0), uaL=(-6 * S(p), 0, 0), head=(0, 0, -2 * S(p)))


def c_run(t):
    p = TAU * t / 0.625
    kL = 18 + 78 * max(0, C(p)); kR = 18 + 78 * max(0, C(p + math.pi))
    base = P(READY, uaL=(10, 14, 25), laL=(80, 0, 0), uaR=(0, 12, 0), laR=(80, 0, 0))
    return D(base, ulL=(14 + 46 * S(p), 0, 0), ulR=(14 - 46 * S(p), 0, 0), llL=(-kL, 0, 0), llR=(-kR, 0, 0),
             fL=(kL * .35, 0, 0), fR=(kR * .35, 0, 0),
             loc=(0, 0, -.05 + .04 * C(2 * p)), hips=(8, 0, -7 * S(p)), spine=(12, 0, 0), chest=(4, 0, 12 * S(p)), head=(-12, 0, -5 * S(p)),
             uaR=(42 * S(p), 0, 0), uaL=(-42 * S(p), 0, 0), laR=(12 * S(p), 0, 0), laL=(-12 * S(p), 0, 0))


PANIC = P(READY, **crouch(32, 62, 9), spine=(24, 0, 0), chest=(8, 0, 0), head=(-34, 0, 0),
          uaR=(118, 28, 20), laR=(105, 0, 0), hR=(-40, 0, 0), uaL=(125, 30, 10), laL=(40, -70, 0))


def c_panic(t):
    p = TAU * t / 1.5
    return D(PANIC, spine=(7 * S(2 * p), 4 * S(p), 0), head=(8 * S(2 * p), 0, 30 * S(p)), chest=(0, 0, 8 * S(p)),
             uaR=(10 * S(3 * p), 6 * C(2 * p), 0), uaL=(9 * S(3 * p + 1), 5 * S(2 * p), 0), laR=(10 * C(3 * p), 0, 0),
             loc=(.02 * S(p), 0, -.025 * (1 - C(2 * p))))


NOCK = P(READY, uaL=(48, 12, 25), laL=(35, 0, 0), uaR=(35, 10, 45), laR=(85, 0, 0), head=(8, 0, 0))
DRAW = P(READY, spine=(-12, 0, 0), chest=(-4, 0, -22), head=(-22, 0, 18), uaL=(133, 6, 0), laL=(4, 0, 0),
         uaR=(-12, 96, 0), laR=(150, 0, 0), ulL=(14, 6, 0), ulR=(-12, 6, 0), llR=(-10, 0, 0), llL=(-6, 0, 0))
LOOSE = P(DRAW, uaR=(-25, 100, 0), laR=(70, 0, 0), uaL=(128, 6, 0))


def c_volley(t):
    return seq([(0, READY), (0.55, NOCK), (1.35, DRAW), (2.35, D(DRAW, spine=(-2, 0, 0), uaL=(2, 0, 0))), (2.45, LOOSE), (2.6, LOOSE), (3.0, READY)], t)


WIND = P(READY, chest=(-6, 0, -22), spine=(-6, 0, 0), uaR=(-25, 20, 0), laR=(115, 0, 0), ulL=(12, 5, 0), ulR=(-10, 5, 0), llR=(-12, 0, 0))
THRUST = P(READY, chest=(-4, 0, 16), spine=(-8, 0, 0), head=(-22, 0, 0), uaR=(142, 12, 0), laR=(12, 0, 0), hR=(-78, 0, 0),
           ulL=(16, 5, 0), ulR=(-14, 5, 0), llL=(-12, 0, 0))


def c_attack(t):
    sh_ = D(THRUST, uaR=(-9, 0, 0), laR=(14, 0, 0))
    return seq([(0, READY), (0.3, WIND), (0.5, THRUST), (0.65, sh_), (0.8, THRUST), (0.9, THRUST), (1.2, READY)], t)


CHEER = P(READY, spine=(-8, 0, 0), head=(-16, 0, 0), uaR=(150, 20, 0), laR=(45, 0, 0), hR=(-80, 0, 0),
          uaL=(118, 42, 0), laL=(55, 0, 0), ulL=(0, 9, 0), ulR=(0, 9, 0))


def c_cheer(t):
    p = TAU * t / 1.5
    q = 3 * p
    return D(CHEER, uaR=(12 * S(q), 0, 0), laR=(-28 * S(q), 0, 0), uaL=(10 * S(q + .6), 0, 0), laL=(-22 * S(q + .6), 0, 0),
             loc=(0, 0, -.02 + .02 * C(q)), ulL=(6 * (1 - C(q)), 0, 0), ulR=(6 * (1 - C(q)), 0, 0), llL=(-12 * (1 - C(q)), 0, 0), llR=(-12 * (1 - C(q)), 0, 0),
             fL=(6 * (1 - C(q)), 0, 0), fR=(6 * (1 - C(q)), 0, 0), head=(4 * S(q), 0, 10 * S(p)), chest=(0, 0, 6 * S(p)))


def c_thrown(t):
    p = TAU * t / 1.0
    return dict(spine=(-18 + 8 * S(p), 6 * C(p), 0), chest=(-10, 0, 10 * S(p)), head=(-20, 0, 12 * C(p)),
                hips=(10 * S(p), 8 * C(p), 0),
                uaL=(25 + 30 * S(p), 105 + 15 * C(p), 0), uaR=(25 - 30 * S(p), 100 - 15 * C(p), 0),
                laL=(35 + 25 * C(p), 0, 0), laR=(35 - 25 * C(p), 0, 0),
                ulL=(20 + 38 * S(p), 28, 0), ulR=(20 - 38 * S(p), 28, 0),
                llL=(-45 + 30 * C(p), 0, 0), llR=(-45 - 30 * C(p), 0, 0), fL=(-25, 0, 0), fR=(-25, 0, 0))


HIT = P(READY, chest=(-18, 0, 12), spine=(-12, 0, 0), head=(-28, 0, 0), uaR=(35, 45, 0), uaL=(35, 45, 20), laL=(60, 0, 0),
        ulL=(18, 5, 0), ulR=(10, 5, 0), llL=(-38, 0, 0), llR=(-30, 0, 0), loc=(0, .06, -.07))
FALL = P(hips=(-58, 0, 0), spine=(-10, 0, 0), head=(-20, 0, 0), uaR=(50, 85, 45), uaL=(50, 85, 45), laR=(40, 0, 0), laL=(40, 0, 0),
         ulL=(40, 10, 0), ulR=(20, 8, 0), llL=(-70, 0, 0), llR=(-45, 0, 0), loc=(0, .52, -.42))
DEAD = P(hips=(-90, 0, 0), head=(0, 0, 24), uaR=(0, 62, 90), uaL=(0, 72, 90), laR=(12, 0, 0), laL=(8, 0, 0),
         ulL=(0, 13, 0), ulR=(6, 7, 0), llR=(-16, 0, 0), fL=(-35, 0, 0), fR=(-35, 0, 0), loc=(0, .90, -.825))


def c_die(t):
    return seq([(0, READY), (0.18, HIT), (0.6, FALL), (0.9, D(DEAD, loc=(0, 0, .02))), (1.0, DEAD), (1.2, DEAD)], t)


def c_crank(t):
    p = TAU * t / 2.0
    base = P(**crouch(22, 40, 8), spine=(26, 0, 0), chest=(8, 0, 0), head=(-12, 0, 0))
    return D(base, uaR=(52 + 24 * S(p), 10, 10), laR=(48 + 30 * C(p), 0, 0), uaL=(52 + 24 * S(p), 10, 10), laL=(48 + 30 * C(p), 0, 0),
             spine=(7 * S(p), 0, 0), loc=(0, -.02 * S(p), -.02 * (1 + C(p))), hR=(-30, 0, 0))


CLIPS = [('Idle', 2.0, c_idle), ('ShieldUp', 1.0, c_shieldup), ('Walk', 1.0, c_walk), ('Run', 0.625, c_run), ('Panic', 1.5, c_panic),
         ('Volley', 3.0, c_volley), ('Attack', 1.2, c_attack), ('Cheer', 1.5, c_cheer), ('Thrown', 1.0, c_thrown), ('Die', 1.2, c_die),
         ('Crank', 2.0, c_crank)]
CLIPD = {n: (d, f) for n, d, f in CLIPS}


# ----------------------------------------------------------------------------- blender objects
def make_material(preview):
    m = bpy.data.materials.new('Soldier')
    m.use_nodes = True
    m.use_backface_culling = True
    nt = m.node_tree
    bsdf = nt.nodes['Principled BSDF']
    bsdf.inputs['Roughness'].default_value = 0.75
    ca = nt.nodes.new('ShaderNodeVertexColor'); ca.layer_name = 'Col'
    if not preview:
        nt.links.new(ca.outputs['Color'], bsdf.inputs['Base Color'])
        return m
    uv = nt.nodes.new('ShaderNodeUVMap'); uv.uv_map = 'UVMap'
    sep = nt.nodes.new('ShaderNodeSeparateXYZ'); nt.links.new(uv.outputs['UV'], sep.inputs[0])
    oi = nt.nodes.new('ShaderNodeObjectInfo')
    mx = nt.nodes.new('ShaderNodeMix'); mx.data_type = 'RGBA'; mx.blend_type = 'MIX'
    mx.inputs['A'].default_value = (1, 1, 1, 1)
    nt.links.new(sep.outputs['X'], mx.inputs['Factor']); nt.links.new(oi.outputs['Color'], mx.inputs['B'])
    mul = nt.nodes.new('ShaderNodeMix'); mul.data_type = 'RGBA'; mul.blend_type = 'MULTIPLY'; mul.inputs['Factor'].default_value = 1
    nt.links.new(ca.outputs['Color'], mul.inputs['A']); nt.links.new(mx.outputs['Result'], mul.inputs['B'])
    nt.links.new(mul.outputs['Result'], bsdf.inputs['Base Color'])
    inv = nt.nodes.new('ShaderNodeMath'); inv.operation = 'SUBTRACT'; inv.inputs[0].default_value = 1
    nt.links.new(sep.outputs['Y'], inv.inputs[1]); nt.links.new(inv.outputs[0], bsdf.inputs['Metallic'])
    rm = nt.nodes.new('ShaderNodeMapRange'); rm.inputs['To Min'].default_value = .8; rm.inputs['To Max'].default_value = .38
    nt.links.new(inv.outputs[0], rm.inputs['Value']); nt.links.new(rm.outputs['Result'], bsdf.inputs['Roughness'])
    return m


def make_object(name, mb, rig, mat):
    me = bpy.data.meshes.new(name)
    me.from_pydata(mb.v, [], mb.f)
    me.update()
    me.polygons.foreach_set('use_smooth', [True] * len(me.polygons))
    nrm = [v.normal.copy() for v in me.vertices]
    ca = me.color_attributes.new('Col', 'FLOAT_COLOR', 'CORNER')
    uvl = me.uv_layers.new(name='UVMap')
    for l in me.loops:
        i = l.vertex_index
        k = 0.74 + 0.26 * (nrm[i].z * 0.5 + 0.5)       # cheap sky-occlusion shading
        c = lin(sh(mb.c[i], k))
        ca.data[l.index].color = (c[0], c[1], c[2], 1.0)
        uvl.data[l.index].uv = (mb.t[i], 1.0 - mb.m[i])   # glTF exporter flips V -> exported V = metal mask
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    groups = {}
    for i, b in enumerate(mb.b):
        groups.setdefault(b, []).append(i)
    for b, idx in groups.items():
        ob.vertex_groups.new(name=b).add(idx, 1.0, 'REPLACE')
    me.materials.append(mat)
    ob.parent = rig
    mod = ob.modifiers.new('Armature', 'ARMATURE'); mod.object = rig
    return ob


def key_clips(rig):
    ad = rig.animation_data_create()
    for name, dur, fn in CLIPS:
        act = bpy.data.actions.new(name)
        ad.action = act
        _prevq.clear()
        n = round(dur * FPS)
        for f in range(n + 1):
            apply_pose(rig, fn(f / FPS))
            for pb in rig.pose.bones:
                pb.keyframe_insert('rotation_quaternion', frame=f)
            rig.pose.bones['Hips'].keyframe_insert('location', frame=f)
        slot = ad.action_slot if hasattr(ad, 'action_slot') else None
        ad.action = None
        tr = ad.nla_tracks.new(); tr.name = name
        st = tr.strips.new(name, 0, act)
        if slot is not None and hasattr(st, 'action_slot'):
            try:
                st.action_slot = slot
            except Exception as e:
                print('slot assign failed', e)
        print('clip', name, 'frames', n, 'strip', st.frame_start, st.frame_end)
    apply_pose(rig, {})


# ----------------------------------------------------------------------------- previews
def bake_copy(ob, rig, pose, loc, rot_z=0.0, color=(.7, .1, .1, 1), mat=None):
    _prevq.clear()
    apply_pose(rig, pose)
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg), preserve_all_data_layers=True, depsgraph=dg)
    c = bpy.data.objects.new('prev_' + ob.name, me)
    c.location = loc; c.rotation_euler = (0, 0, rot_z); c.color = color
    bpy.context.scene.collection.objects.link(c)
    return c


def setup_render(w, h):
    sc = bpy.context.scene
    for eng in ('BLENDER_EEVEE', 'BLENDER_EEVEE_NEXT'):
        try:
            sc.render.engine = eng; break
        except Exception:
            pass
    sc.render.resolution_x = w; sc.render.resolution_y = h; sc.render.resolution_percentage = 100
    sc.render.image_settings.file_format = 'PNG'
    try:
        sc.eevee.taa_render_samples = 24
    except Exception:
        pass
    sc.view_settings.view_transform = 'Standard'
    if not sc.world:
        sc.world = bpy.data.worlds.new('W')
    sc.world.use_nodes = True
    bg = sc.world.node_tree.nodes['Background']
    bg.inputs[0].default_value = (.55, .62, .72, 1); bg.inputs[1].default_value = 0.9
    if 'Sun' not in bpy.data.objects:
        sd = bpy.data.lights.new('Sun', 'SUN'); sd.energy = 3.5; sd.angle = 0.05
        so = bpy.data.objects.new('Sun', sd); sc.collection.objects.link(so)
        so.rotation_euler = (math.radians(50), 0, math.radians(-35))


def camera(pos, target, ortho=None, lens=50):
    cd = bpy.data.cameras.new('Cam'); co = bpy.data.objects.new('Cam', cd)
    bpy.context.scene.collection.objects.link(co)
    co.location = pos
    d = Vector(target) - Vector(pos)
    co.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
    if ortho:
        cd.type = 'ORTHO'; cd.ortho_scale = ortho
    else:
        cd.lens = lens
    cd.clip_end = 500
    bpy.context.scene.camera = co
    return co


def render(path):
    bpy.context.scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    print('rendered', path)


def clear_prev():
    for o in list(bpy.data.objects):
        if o.name.startswith('prev_') or o.name.startswith('Cam') or o.name.startswith('Ground'):
            bpy.data.objects.remove(o, do_unlink=True)


TINTS = [(.72, .08, .08, 1), (.10, .22, .62, 1), (.85, .68, .10, 1), (.10, .45, .18, 1), (.45, .12, .50, 1), (.9, .9, .9, 1), (.08, .08, .08, 1)]


def wall_sheet(path, cells, cols, rows, cw=2.5, chh=3.1, az=28, el=12, px=260):
    """cells: list of (obj, pose, col, row, tintcolor, rot_z)"""
    setup_render(int(cols * px), int(rows * px * chh / cw))
    a, e = math.radians(az), math.radians(el)
    dirv = Vector((math.sin(a) * math.cos(e), -math.cos(a) * math.cos(e), math.sin(e)))  # from target toward camera
    right = Vector((math.cos(a), math.sin(a), 0))
    up = dirv.cross(right) * -1
    up = right.cross(dirv) * -1 if up.z < 0 else up
    for ob, pose, c, r, tint, rz in cells:
        loc = right * (c * cw) - up * (r * chh)
        bake_copy(ob, rig, pose, loc, rz, tint)
    ctr = right * ((cols - 1) * cw / 2) - up * ((rows - 1) * chh / 2) + up * 1.05
    camera(ctr + dirv * 60, ctr, ortho=max(cols * cw, rows * chh * (cols * cw) / (rows * chh)))
    for o in OBJS.values():
        o.hide_render = True
    render(path)
    clear_prev()


def ground():
    me = bpy.data.meshes.new('Ground'); me.from_pydata([(-80, -80, 0), (80, -80, 0), (80, 80, 0), (-80, 80, 0)], [], [(0, 1, 2, 3)])
    g = bpy.data.objects.new('Ground', me); bpy.context.scene.collection.objects.link(g)
    m = bpy.data.materials.new('GroundM'); m.use_nodes = True
    m.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value = (.16, .2, .07, 1)
    m.node_tree.nodes['Principled BSDF'].inputs['Roughness'].default_value = 1
    me.materials.append(m)
    return g


def previews():
    os.makedirs(PREV, exist_ok=True)
    names = [t[0] for t in TYPES]
    # A: types front / back
    cells = []
    for i, n in enumerate(names):
        cells.append((OBJS[n], READY, i, 0, TINTS[i % 5], 0))
        cells.append((OBJS[n], READY, i, 1, TINTS[i % 5], math.radians(150)))
    wall_sheet(PREV + r"\sold_types.png", cells, len(names), 2, px=230)
    # B: animation sheets
    sheets = [
        ('anim1', [('Idle', 'Infantry'), ('ShieldUp', 'Infantry'), ('Walk', 'Infantry'), ('Run', 'Infantry')]),
        ('anim2', [('Panic', 'Infantry'), ('Cheer', 'Knight'), ('Attack', 'Infantry'), ('Thrown', 'Infantry')]),
        ('anim3', [('Die', 'Infantry'), ('Volley', 'Archer'), ('Crank', 'Infantry'), ('Die', 'Warlord')]),
        ('anim4', [('ShieldUp', 'Archer'), ('Run', 'Archer'), ('Attack', 'Knight'), ('Cheer', 'Warlord')]),
    ]
    special = {'Die': [0, .18, .4, .6, .85, 1.2], 'Volley': [0, .55, 1.35, 2.2, 2.5, 2.8], 'Attack': [0, .3, .5, .65, .9, 1.1]}
    for sname, rows in sheets:
        cells = []
        for r, (clip, typ) in enumerate(rows):
            dur, fn = CLIPD[clip]
            ts = special.get(clip, [dur * k / 6 for k in range(6)])
            for c, t in enumerate(ts):
                cells.append((OBJS[typ], fn(t), c, r, TINTS[r % 5], 0))
        wall_sheet(PREV + "\\sold_%s.png" % sname, cells, 6, len(rows), cw=2.7, px=250)
    # C: formation views
    random.seed(3)
    ground()
    for o in OBJS.values():
        o.hide_render = True
    # block of infantry idle / shield-up, archers behind, knights + warlord at the side, some fleeing and dead
    for ix in range(8):
        for iy in range(5):
            typ = 'Infantry' if iy < 4 else 'Archer'
            lodn = typ if (ix + iy) % 2 == 0 else typ + '_LOD1'
            if ix < 4:
                pose = c_idle(random.random() * 2)
            else:
                pose = c_shieldup(random.random()) if typ == 'Infantry' else c_volley(1.4 + random.random())
            bake_copy(OBJS[lodn], rig, pose, (ix * 1.25 - 5 + random.uniform(-.1, .1), iy * 1.3 - 2 + random.uniform(-.1, .1), 0), random.uniform(-.1, .1), TINTS[0])
    for i in range(4):
        bake_copy(OBJS['Knight'], rig, c_cheer(i * .3), (6.5 + (i % 2) * 1.3, -1 + (i // 2) * 1.4, 0), 0, TINTS[1])
    bake_copy(OBJS['Warlord'], rig, c_attack(.55), (7.2, -2.8, 0), 0, TINTS[4]).scale = (1.15, 1.15, 1.15)
    for i in range(4):
        bake_copy(OBJS['Infantry'], rig, c_run(i * .15), (-7.5 - i * .9, -3 + i * 1.2, 0), math.radians(100 + 20 * i), TINTS[2])
        bake_copy(OBJS['Infantry'], rig, DEAD, (-6.5 + i * 4.2, -5.0 - (i % 2), 0), i * 1.7, TINTS[2])
    bake_copy(OBJS['Infantry'], rig, c_thrown(.3), (0, -5.5, 2.2), 1.0, TINTS[3]).rotation_euler = (1.0, .5, 1)
    setup_render(1400, 800)
    camera((14, -30, 26), (0, -.5, .8), lens=110)
    render(PREV + r"\sold_heli.png")
    camera((3, -15, 2.6), (0.5, 0, 1.0), lens=55)
    render(PREV + r"\sold_close.png")
    clear_prev()
    for o in OBJS.values():
        o.hide_render = False


# ----------------------------------------------------------------------------- main
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.context.scene.render.fps = FPS
rig = make_rig()
mat = make_material(DO_PREVIEW)
OBJS = {}
for name, fn, lod in TYPES:
    mb = fn(lod)
    OBJS[name] = make_object(name, mb, rig, mat)
    print('MESH', name, 'verts', len(mb.v), 'tris', mb.tris())

if DO_PREVIEW:
    previews()
else:
    key_clips(rig)
    bpy.ops.export_scene.gltf(
        filepath=OUT, export_format='GLB', export_yup=True, export_apply=False,
        export_skins=True, export_animations=True, export_animation_mode='NLA_TRACKS',
        export_force_sampling=True, export_anim_slide_to_zero=True, export_optimize_animation_size=False,
        export_vertex_color='ACTIVE', export_all_vertex_colors=False, export_materials='EXPORT',
        export_draco_mesh_compression_enable=False, export_cameras=False, export_lights=False,
        export_def_bones=False, export_frame_range=False)
    print('EXPORTED', OUT)
