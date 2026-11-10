# Siege Wing - soldier set generator (headless Blender 5.2)
#   blender.exe -b -P soldiers.py            -> build + export assets/models/soldiers.glb
#   blender.exe -b -P soldiers.py -- preview -> also render preview sheets to tools/blender/preview/sold_*.png
# Contract with src/crowd.js: 16-bone rig, every vertex rigidly bound to ONE bone, albedo in vertex colour,
# uv.x = heraldic-tint cloth mask, uv.y = variant mask + 0.5 * metal, meshes <Type> / <Type>_LOD1, clips in CLIPS.
# Variants: every soldier draws one of six "selections" sel = 0..5 (helmet = sel % 3, shield face = sel // 3), picked in the
# shader from a per-instance hash. floor(uv.y) is a bit mask: 0 = always drawn, otherwise bit sel must be set or the
# vertex is collapsed. HV(h) / SV(s) below give the masks for helmet h / shield face s.
#   blender.exe -b -P soldiers.py -- pv      -> variant sheet tools/blender/preview/sold_variants.png (no export)
import bpy, math, sys, os, random, json
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree

ROOT = r"C:\Users\shaoy\game"
OUT = ROOT + r"\assets\models\soldiers.glb"
PREV = ROOT + r"\tools\blender\preview"
STATS = ROOT + r"\tools\blender\soldiers_stats.json"
ARGS = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
DO_PREVIEW = 'preview' in ARGS
DO_PV = 'pv' in ARGS
FPS = 24

X, Y, Z = Vector((1, 0, 0)), Vector((0, 1, 0)), Vector((0, 0, 1))
PI = math.pi

# ----------------------------------------------------------------------------- colours (sRGB)
STEEL = (.66, .68, .72); DSTEEL = (.40, .41, .45); SKIN = (.82, .62, .50); LEATH = (.40, .26, .15)
DLEATH = (.19, .13, .09); WOOD = (.47, .34, .21); TINT = (.93, .91, .87); HOSE = (.45, .38, .29)
GAMB = (.70, .62, .47); GOLD = (.90, .70, .22); FUR = (.27, .20, .14); IRON = (.20, .20, .22)
ARROW = (.80, .70, .50); BLACK = (.04, .04, .04); MAIL = (.47, .48, .52); CREAM = (.86, .82, .70)
GHOSE = (.33, .37, .24); CRIMSON = (.58, .07, .07); FEATH = (.90, .88, .82); PLATE = (.26, .26, .30); BOOT = (.30, .20, .13)


def sh(c, k):
    return tuple(min(1.0, v * k) for v in c)


def lin(c):
    return tuple((v / 12.92) if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in c)


def HV(h):      # mask: helmet variant h (0..2) -> selections h and h + 3
    return 9 << h


SV = (7, 56)    # mask: shield face 0 -> selections 0..2, face 1 -> selections 3..5


def _k(n):      # radius factor that gives an n-gon the area of the circle it stands for
    return math.sqrt(PI / (n / 2 * math.sin(2 * PI / n)))


def _pw(c, e):
    return math.copysign(abs(c) ** e, c)


# ----------------------------------------------------------------------------- mesh builder
class MB:
    def __init__(s):
        s.v = []; s.c = []; s.t = []; s.m = []; s.b = []; s.k = []
        s.f = []; s.ff = []; s.fo = []; s.fk = []
        s.var = 0         # variant mask given to everything added while it is set (0 = always drawn)
        s.occ = True      # faces added while True occlude in the AO bake (gear is switched off)
        s.flat = False    # faces added while True are flat shaded

    def add(s, p, col, bone, tint=0.0, metal=0.0):
        s.v.append(tuple(p)); s.c.append(col); s.b.append(bone); s.t.append(tint); s.m.append(metal); s.k.append(s.var)
        return len(s.v) - 1

    def face(s, idx, flat=None):
        s.f.append(tuple(idx)); s.ff.append(s.flat if flat is None else flat); s.fo.append(s.occ); s.fk.append(s.var)

    def ring(s, c, u, v, ru, rv, n, phase, col, bone, tint=0.0, metal=0.0, fn=None, sq=1.0):
        idx = []
        for i in range(n):
            a = phase + 2 * PI * i / n
            ca, sa = math.cos(a), math.sin(a)
            if sq != 1.0:
                ca, sa = _pw(ca, sq), _pw(sa, sq)
            p = c + u * (ru * ca) + v * (rv * sa)
            d = dict(col=col, bone=bone, tint=tint, metal=metal)
            if fn:
                r = fn(i, p)
                if r:
                    p = r.get('p', p)
                    d.update({k: w for k, w in r.items() if k != 'p'})
            idx.append(s.add(p, d['col'], d['bone'], d['tint'], d['metal']))
        return idx

    def bridge(s, a, b, flip=False):
        n = len(a)
        for i in range(n):
            j = (i + 1) % n
            q = (a[i], a[j], b[j], b[i])
            s.face(tuple(reversed(q)) if flip else q)

    def strip(s, secs, n, u, v, bone=None, cap0=False, cap1=False, phase=0.0, flip=False, tint=0.0, metal=0.0, comp=True):
        """sections (centre, ru, rv, col[, opts]) advancing along u x v; opts: bone tint metal fn sq split"""
        k = _k(n) if comp else 1.0
        prev = first = None
        for sec in secs:
            c, ru, rv, col = sec[:4]
            o = sec[4] if len(sec) > 4 else {}
            idx = s.ring(Vector(c), u, v, ru * k, rv * k, n, phase, col, o.get('bone', bone), o.get('tint', tint),
                         o.get('metal', metal), o.get('fn'), o.get('sq', 1.0))
            if prev is not None and not o.get('split'):
                s.bridge(prev, idx, flip)
            if first is None:
                first = idx
            prev = idx
        if cap0:
            s.face(tuple(first) if flip else tuple(reversed(first)))
        if cap1:
            s.face(tuple(reversed(prev)) if flip else tuple(prev))

    def loft(s, rings, n, cap_bot=False, cap_top=False, phase=0.0, flip=False):
        """horizontal rings, ascending z: (z, rx, ry, bone, col[, opts]); opts also x, y"""
        secs = []
        for r in rings:
            z, rx, ry, bone, col = r[:5]
            o = dict(r[5]) if len(r) > 5 else {}
            o['bone'] = bone
            secs.append(((o.get('x', 0), o.get('y', 0), z), rx, ry, col, o))
        s.strip(secs, n, X, Y, None, cap_bot, cap_top, phase, flip)

    def cyl(s, p0, p1, r0, r1, n, col, bone, tint=0.0, metal=0.0, cap0=False, cap1=False, up=None, col1=None):
        p0 = Vector(p0); p1 = Vector(p1)
        d = (p1 - p0).normalized()
        ref = Vector(up) if up is not None else (Z if abs(d.z) < 0.9 else X)
        u = (ref - d * ref.dot(d)).normalized()
        v = d.cross(u)
        r0 = r0 if isinstance(r0, tuple) else (r0, r0)
        a = s.ring(p0, u, v, r0[0], r0[1], n, 0.0, col, bone, tint, metal)
        if cap0:
            s.face(tuple(reversed(a)))
        if r1 == 0:
            ap = s.add(p1, col1 or col, bone, tint, metal)
            for i in range(n):
                s.face((a[i], a[(i + 1) % n], ap))
        else:
            r1 = r1 if isinstance(r1, tuple) else (r1, r1)
            b = s.ring(p1, u, v, r1[0], r1[1], n, 0.0, col1 or col, bone, tint, metal)
            s.bridge(a, b)
            if cap1:
                s.face(tuple(b))

    def tube(s, pts, r, n, col, bone, tint=0.0, metal=0.0, side=X, cap0=False, cap1=False, cols=None):
        prev = first = None
        for i, p in enumerate(pts):
            p = Vector(p)
            t = (Vector(pts[min(i + 1, len(pts) - 1)]) - Vector(pts[max(i - 1, 0)])).normalized()
            u = Vector(side); v = t.cross(u)
            rr = r[i] if isinstance(r, (list, tuple)) else r
            idx = s.ring(p, u, v, rr, rr, n, 0.0, cols[i] if cols else col, bone, tint, metal)
            if prev:
                s.bridge(prev, idx)
            else:
                first = idx
            prev = idx
        if cap0:
            s.face(tuple(reversed(first)))
        if cap1:
            s.face(tuple(prev))

    def box(s, c, size, col, bone, tint=0.0, metal=0.0, rot=None):
        c = Vector(c); h = Vector(size) * 0.5
        ids = []
        for i in range(8):
            o = Vector((h.x if i & 1 else -h.x, h.y if i & 2 else -h.y, h.z if i & 4 else -h.z))
            if rot is not None:
                o = rot @ o
            ids.append(s.add(c + o, col, bone, tint, metal))
        for q in ((1, 3, 7, 5), (0, 4, 6, 2), (2, 6, 7, 3), (0, 1, 5, 4), (4, 5, 7, 6), (0, 2, 3, 1)):
            s.face(tuple(ids[k] for k in q))

    def poly(s, pts, col, bone, tint=0.0, metal=0.0, flip=False):
        ids = [s.add(Vector(p), col, bone, tint, metal) for p in pts]
        s.face(tuple(reversed(ids)) if flip else tuple(ids), flat=True)

    def plate(s, pts, nrm, t, colf, colb, bone, tintf=0.0, metal=0.0, tintb=0.0):
        """two-sided flat polygon; pts CCW seen from the +nrm side"""
        nrm = Vector(nrm)
        s.poly([Vector(p) + nrm * (t / 2) for p in pts], colf, bone, tintf, metal)
        s.poly([Vector(p) - nrm * (t / 2) for p in pts], colb, bone, tintb, metal, flip=True)

    def tris(s, sel=None):
        return sum(len(f) - 2 for f, k in zip(s.f, s.fk) if sel is None or k == 0 or (k >> sel) & 1)


# ----------------------------------------------------------------------------- body, LOD0
# spec keys: bulk, torso=(col,tint,metal), skirt=(zhem,col,tint,metal,flare), belt=(col,metal), quilt,
#            thigh/shin/boot/arm/forearm/hand=(col,metal), boot_z, cuff, wrap=(col,tint,metal), beard
def _hem(i, p):
    return {'bone': 'UpperLeg.L' if p.x > 0.05 else ('UpperLeg.R' if p.x < -0.05 else 'Hips')}


def _arm_x(sp):
    return .236 + (sp.get('bulk', 1.0) - 1) * .16


def torso(mb, sp, n=10):
    bk = sp.get('bulk', 1.0)
    tc, tt, tm = sp['torso']
    zh, sc, st, sm, fl = sp['skirt']
    bc, bm = sp.get('belt', (DLEATH, 0))
    qf = (lambda i, p: {'col': sh(tc, .80)} if i % 2 else None) if sp.get('quilt') else None
    T = dict(tint=tt, metal=tm, sq=.82, fn=qf)
    S = dict(tint=st, metal=sm, sq=.88)
    Bt = dict(metal=bm, sq=.88)
    mb.loft([
        (zh, .216 * bk * fl, .168 * bk * fl, 'Hips', sh(sc, .74), dict(S, fn=_hem)),
        (0.93, .182 * bk, .138 * bk, 'Hips', sh(sc, .92), S),
        (1.045, .140 * bk, .101 * bk, 'Spine', sc, S),
        (1.040, .149 * bk, .110 * bk, 'Spine', bc, dict(Bt, split=True)),
        (1.090, .149 * bk, .110 * bk, 'Spine', bc, Bt),
        (1.085, .139 * bk, .100 * bk, 'Spine', sh(tc, .92), dict(T, split=True)),
        (1.22, .150 * bk, .104 * bk, 'Spine', tc, T),
        (1.37, .178 * bk, .119 * bk, 'Chest', tc, dict(T, y=-.008)),
        (1.455, .180 * bk, .102 * bk, 'Chest', tc, T),
        (1.508, .088, .078, 'Chest', sh(tc, .95), dict(T, y=.004)),
    ], n)
    if not sp.get('no_buckle'):
        mb.box((0, -.113 * bk - .006, 1.065), (.045, .014, .04), GOLD if bm else STEEL, 'Spine', metal=1)


def legs(mb, sp, n=6):
    tc, tm = sp['thigh']; sc, sm = sp['shin']; bc, bm = sp['boot']
    bz = sp.get('boot_z', .34)
    for side, sx in (('L', 1), ('R', -1)):
        x = .10 * sx
        UL = 'UpperLeg.' + side; LL = 'LowerLeg.' + side; FT = 'Foot.' + side
        O = dict(x=x, metal=tm)
        mb.loft([(0.452, .046, .050, UL, sh(tc, .85), O), (0.50, .056, .060, UL, tc, O),
                 (0.72, .073, .079, UL, tc, O), (0.94, .078, .084, UL, tc, O)], n, cap_bot=True)
        Sb = dict(x=x, metal=bm); Ss = dict(x=x, metal=sm)
        mb.loft([(0.07, .037, .042, LL, sh(bc, .9), Sb), (0.20, .041, .047, LL, bc, dict(Sb, y=.006)),
                 (bz, .054, .061, LL, bc, dict(Sb, y=.012)),
                 (bz, .049, .056, LL, sc, dict(Ss, y=.012, split=True)),
                 (0.50, .054, .058, LL, sc, dict(Ss, y=-.006)), (0.548, .040, .042, LL, sc, dict(Ss, y=-.010))], n, cap_top=True)
        F = dict(metal=bm)
        mb.strip([((x, .068, .045), .033, .040, sh(bc, .8), F), ((x, .0, .060), .043, .058, bc, F),
                  ((x, -.11, .036), .047, .034, bc, F), ((x, -.195, .023), .034, .021, sh(bc, .9), F)],
                 n, X, Z, FT, cap0=True, cap1=True)


def arms(mb, sp, n=6):
    ac, am = sp['arm']; fc, fm = sp['forearm']; hc, hm = sp['hand']
    xa = _arm_x(sp)
    for side, sx in (('L', 1), ('R', -1)):
        x = xa * sx
        UA = 'UpperArm.' + side; LA = 'LowerArm.' + side; HA = 'Hand.' + side
        O = dict(x=x, metal=am)
        r = [(1.142, .030, .032, UA, sh(ac, .85), O), (1.19, .044, .047, UA, sh(ac, .95), O), (1.33, .053, .058, UA, ac, O)]
        if sp.get('sleeve'):     # the shoulder end of the arm wears the mantle's colour, so it reads as cloth when it lifts through
            sc_, st_ = sp['sleeve']
            Q = dict(x=x + .004 * sx, tint=st_, sq=.9)
            r += [(1.392, .056, .061, UA, ac, O), (1.386, .064, .070, UA, sh(sc_, .74), dict(Q, split=True)),
                  (1.458, .067, .073, UA, sh(sc_, .92), Q), (1.512, .042, .048, UA, sc_, dict(Q, x=x - .014 * sx))]
        else:
            r += [(1.455, .061, .067, UA, ac, O), (1.508, .036, .042, UA, ac, dict(O, x=x - .014 * sx))]
        mb.loft(r, n, cap_bot=True, cap_top=True)
        O = dict(x=x, metal=fm)
        mb.loft([(0.94, .033, .036, LA, sh(fc, .9), O), (1.10, .047, .050, LA, fc, O),
                 (1.185, .045, .047, LA, fc, O), (1.218, .027, .029, LA, fc, O)], n, cap_top=True)
        O = dict(x=x, metal=hm)
        r = [(0.80, .028, .036, HA, sh(hc, .85), O), (0.86, .039, .049, HA, hc, O), (0.928, .036, .042, HA, hc, O)]
        if sp.get('cuff'):
            r.append((0.995, .050, .054, HA, sh(hc, 1.1), O))
        mb.loft(r, n, cap_bot=True)


def head(mb, sp, n=8, top=False):
    wc, wt, wm = sp['wrap']
    W = dict(tint=wt, metal=wm)
    brd = sp.get('beard')

    def face(k):
        def fn(i, p):
            if i not in (0, 1, n - 1):
                return None
            c = SKIN
            if k == 0:
                c = brd or sh(SKIN, .9)
            if k == 2:
                c = sh(SKIN, .60) if i else sh(SKIN, .84)
            r = {'col': c, 'tint': 0, 'metal': 0}
            if k == 1 and i == 0:
                r['p'] = p + Vector((0, -.017, -.006))
            return r
        return fn
    mb.loft([(1.49, .052, .056, 'Chest', sh(wc, .8), W), (1.56, .047, .052, 'Head', wc, W)], 6)     # neck
    r = [(1.545, .046, .050, 'Head', sh(wc, .85), dict(W, y=.004)),
         (1.588, .064, .074, 'Head', wc, dict(W, y=-.010, fn=face(0))),
         (1.635, .075, .088, 'Head', wc, dict(W, y=-.008, fn=face(1))),
         (1.695, .079, .094, 'Head', wc, dict(W, y=-.004, fn=face(2))),
         (1.752, .076, .090, 'Head', wc, W)]
    if top:
        r.append((1.80, .050, .060, 'Head', wc, W))
    mb.loft(r, n, cap_top=top, phase=-PI / 2)


def body(mb, sp):
    torso(mb, sp); legs(mb, sp); arms(mb, sp)
    if 'wrap' in sp:
        head(mb, sp)


# ----------------------------------------------------------------------------- body, LOD1
def body1(mb, sp):
    bk = sp.get('bulk', 1.0)
    tc, tt, tm = sp['torso']
    zh, sc, st, sm, fl = sp['skirt']
    T = dict(tint=tt, metal=tm); S = dict(tint=st, metal=sm)
    mb.loft([(zh, .216 * bk * fl, .168 * bk * fl, 'Hips', sh(sc, .70), dict(S, fn=_hem)),
             (1.06, .143 * bk, .104 * bk, 'Spine', sh(sc, .62), S),
             (1.06, .143 * bk, .104 * bk, 'Spine', sh(tc, .78), dict(T, split=True)),
             (1.42, .182 * bk, .116 * bk, 'Chest', tc, T),
             (1.51, .085, .075, 'Chest', sh(tc, .9), T)], 6)
    tc_, tm_ = sp['thigh']; sc_, sm_ = sp['shin']; bc, bm = sp['boot']
    for side, sx in (('L', 1), ('R', -1)):
        x = .10 * sx
        mb.loft([(0.0, .042, .084, 'LowerLeg.' + side, sh(bc, 1.15), dict(x=x, y=-.045, metal=bm)),
                 (0.50, .052, .056, 'LowerLeg.' + side, sc_, dict(x=x, metal=sm_)),
                 (0.93, .080, .086, 'UpperLeg.' + side, tc_, dict(x=x, metal=tm_))], 4, cap_bot=True, phase=PI / 4)
    ac, am = sp['arm']; fc, fm = sp['forearm']; hc, hm = sp['hand']
    xa = _arm_x(sp)
    for side, sx in (('L', 1), ('R', -1)):
        x = xa * sx
        mb.loft([(0.81, .036, .042, 'LowerArm.' + side, hc, dict(x=x, metal=hm)),
                 (1.18, .046, .049, 'LowerArm.' + side, fc, dict(x=x, metal=fm)),
                 (1.49, .060, .066, 'UpperArm.' + side, ac, dict(x=x, metal=am))], 3, cap_bot=True, cap_top=True, phase=PI / 2)
    if 'wrap' in sp:
        wc, wt, wm = sp['wrap']
        W = dict(tint=wt, metal=wm)
        fa = lambda k: (lambda i, p: {'col': sh(SKIN, k), 'tint': 0, 'metal': 0} if i == 0 else None)
        mb.loft([(1.50, .052, .056, 'Head', sh(wc, .8), W), (1.60, .070, .082, 'Head', wc, dict(W, y=-.008, fn=fa(1.0))),
                 (1.73, .078, .092, 'Head', wc, dict(W, y=-.004, fn=fa(.7)))], 6, cap_top=True, phase=-PI / 2)


# ----------------------------------------------------------------------------- gear
GX, GZ = .236, .868      # grip point of the hands in the rest pose


def spear(mb, lod):
    x = -GX; z = GZ; B = 'Hand.R'
    mb.occ = False
    if lod == 0:
        mb.cyl((x, 1.0, z), (x, -1.13, z), .017, .016, 5, WOOD, B, cap0=True)
        mb.cyl((x, -1.10, z), (x, -1.17, z), .023, .019, 5, DSTEEL, B, metal=1, cap0=True)
        mb.flat = True
        mb.strip([((x, -1.16, z), .014, .012, STEEL), ((x, -1.25, z), .043, .011, STEEL), ((x, -1.43, z), .003, .003, sh(STEEL, 1.1))],
                 4, Z, -X, B, cap1=True, metal=1, comp=False)
        mb.flat = False
    else:
        mb.cyl((x, 1.0, z), (x, -1.15, z), .024, .024, 3, WOOD, B)
        mb.cyl((x, -1.15, z), (x, -1.43, z), .038, 0, 3, STEEL, B, metal=1)
    mb.occ = True


def round_shield(mb, lod):
    c = Vector((.305, 0, 1.05)); B = 'LowerArm.L'; R = .39
    mb.occ = False
    if lod == 0:
        n = 12
        RIM = (.50, .50, .52)
        mb.strip([(c, R, R, sh(WOOD, .6)), (c + X * .022, R, R, RIM, dict(metal=1)), (c + X * .030, R - .038, R - .038, sh(RIM, .9), dict(metal=1))],
                 n, Y, Z, B, comp=False)
        ri, ro = .085, R - .038
        for s in (0, 1):          # face 0: quarterly, face 1: tinted with a cream pale
            mb.var = SV[s]
            for i in range(n):
                a0, a1 = 2 * PI * i / n, 2 * PI * (i + 1) / n
                tinted = ((i // 3) % 2 == 0) if s == 0 else (i not in (2, 3, 8, 9))
                col = TINT if tinted else CREAM
                q = []
                for a, r, dx in ((a0, ro, .030), (a1, ro, .030), (a1, ri, .060), (a0, ri, .060)):
                    q.append(mb.add(c + Vector((dx, r * math.cos(a), r * math.sin(a))), sh(col, .92 if r == ro else 1.0), B, 1 if tinted else 0, 0))
                mb.face(q)
        mb.var = 0
        mb.strip([(c + X * .056, .095, .095, DSTEEL), (c + X * .092, .060, .060, STEEL), (c + X * .112, .018, .018, sh(STEEL, 1.1))],
                 6, Y, Z, B, cap1=True, metal=1, comp=False)
        mb.poly([c + Vector((0, R * math.cos(2 * PI * i / n), R * math.sin(2 * PI * i / n))) for i in range(n)], sh(WOOD, .62), B, flip=True)
    else:
        n = 8
        R -= .02
        P = lambda i: c + Vector((.02, R * math.cos(2 * PI * i / n), R * math.sin(2 * PI * i / n)))
        for s in (0, 1):
            mb.var = SV[s]
            for i in range(n):
                tinted = ((i // 2) % 2 == 0) if s == 0 else (i not in (1, 2, 5, 6))
                col = TINT if tinted else CREAM
                mb.poly([P(i), P(i + 1), c + X * .075], sh(col, .95), B, 1 if tinted else 0)
        mb.var = 0
        mb.poly([P(i) - X * .02 for i in range(n)], sh(WOOD, .62), B, flip=True)
    mb.occ = True


def heater_shield(mb, lod):
    cx, cy, cz = .335, 0.0, 1.05; B = 'LowerArm.L'
    mb.occ = False
    top, mid0 = -.32, -.15
    mid = mid0 + (.05 if lod == 0 else 0)
    if lod == 0:
        low = [(mid, .27), (.06, .265), (.24, .19), (.43, 0), (.24, -.19), (.06, -.265), (mid, -.27)]
    else:
        low = [(mid, .27), (.14, .25), (.43, 0), (.14, -.25), (mid, -.27)]
    P = lambda a, b, dx=0.0, k=1.0: (cx + dx, cy + a * k + (k - 1) * .04, cz + b * k)
    # face 0: chief (cream) + field (tint); +X is the face
    mb.var = SV[0]
    mb.poly([P(top, -.27, .012), P(mid0, -.27, .012), P(mid0, .27, .012), P(top, .27, .012)], CREAM, B)
    if lod == 0:
        mb.poly([P(mid0, -.27, .012), P(mid, -.27, .012), P(mid, .27, .012), P(mid0, .27, .012)], (.09, .09, .10), B)
    mb.poly([P(a, b, .012) for a, b in reversed(low)], TINT, B, 1)
    # face 1: per pale, tint / cream
    mb.var = SV[1]
    h = len(low) // 2
    mb.poly([P(top, 0, .012)] + [P(a, b, .012) for a, b in reversed(low[1:h + 1])] + [P(top, .27, .012)], TINT, B, 1)
    mb.poly([P(top, -.27, .012)] + [P(a, b, .012) for a, b in reversed(low[h:-1])] + [P(top, 0, .012)], CREAM, B)
    mb.var = 0
    outline = [(top, -.27)] + list(reversed(low)) + [(top, .27)]
    if lod == 0:
        mb.poly([P(a, b, 0, 1.07) for a, b in outline], (.50, .50, .52), B, 0, 1)
    mb.poly([P(a, b, -.012, 1.07 if lod == 0 else 1.0) for a, b in outline], sh(WOOD, .62), B, flip=True)
    mb.occ = True


def sword(mb, lod):
    x = -GX; z = GZ; B = 'Hand.R'
    mb.occ = False
    if lod == 0:
        mb.cyl((x, .10, z), (x, -.10, z), .017, .017, 5, DLEATH, B)
        mb.flat = True
        mb.strip([((x, .155, z), .008, .008, GOLD), ((x, .125, z), .030, .030, GOLD), ((x, .095, z), .012, .012, GOLD)],
                 4, Z, X, B, cap0=True, metal=1, comp=False, flip=True)
        mb.box((x, -.105, z), (.028, .028, .25), sh(GOLD, .9), B, metal=1)
        mb.strip([((x, -.115, z), .034, .009, STEEL), ((x, -.82, z), .026, .008, STEEL), ((x, -1.0, z), .003, .003, sh(STEEL, 1.1))],
                 4, Z, -X, B, cap1=True, metal=1, comp=False)
        mb.flat = False
    else:
        mb.flat = True
        mb.strip([((x, .12, z), .022, .014, DSTEEL), ((x, -.12, z), .045, .014, STEEL), ((x, -1.0, z), .004, .004, STEEL)],
                 4, Z, -X, B, cap0=True, metal=1, comp=False)
        mb.flat = False
    mb.occ = True


def bow(mb, lod):
    x = GX; z0 = GZ; B = 'Hand.L'
    f = lambda s: Vector((x, .82 * s, z0 + .26 * s * s - (.035 if abs(s) > .99 else 0)))
    mb.occ = False
    BW = (.56, .40, .22)
    if lod == 0:
        ss = [-1, -.9, -.6, -.25, 0, .25, .6, .9, 1]
        rr = [.007, .011, .016, .020, .023, .020, .016, .011, .007]
        cc = [sh(BW, 1.2), BW, BW, BW, DLEATH, BW, BW, BW, sh(BW, 1.2)]
        mb.tube([f(s) for s in ss], rr, 4, BW, B, cols=cc)
        g = lambda s: Vector((x, .82 * s, z0 + .26 - .035))
        mb.cyl(g(-1), g(1), .004, .004, 3, CREAM, B)
        mb.cyl((x + .024, 0, z0 + .22), (x + .024, 0, z0 - .50), .008, .008, 3, ARROW, B)
        mb.cyl((x + .024, 0, z0 - .50), (x + .024, 0, z0 - .59), .017, 0, 3, STEEL, B, metal=1)
    else:
        mb.tube([f(s) for s in (-1, -.45, .45, 1)], [.012, .028, .028, .012], 3, BW, B)
    mb.occ = True


def quiver(mb, lod):
    a = Vector((-.15, .150, 1.02)); b = Vector((.07, .158, 1.50)); d = (b - a).normalized()
    if lod == 0:
        mb.cyl(a, b, .042, .056, 6, LEATH, 'Chest', cap0=True, col1=sh(LEATH, 1.15))
        mb.cyl(b - d * .03, b + d * .012, .060, .060, 6, DLEATH, 'Chest', cap1=True)
        u = Vector((d.z, 0, -d.x)); w = Y
        for k in range(3):
            ang = k * PI / 3
            s = u * math.cos(ang) + w * math.sin(ang)
            p0 = b + d * .005; p1 = b + d * .135
            mb.plate([p0 - s * .034, p0 + s * .034, p1 + s * .046, p1 - s * .046], s.cross(d), .004,
                     FEATH if k != 1 else sh(FEATH, .7), sh(FEATH, .8), 'Chest')
        # baldric across the chest
        mb.tube([(.150, -.098, 1.47), (.05, -.135, 1.36), (-.07, -.128, 1.22), (-.150, -.085, 1.10)], .017, 3, DLEATH, 'Chest', side=Vector((.6, 0, .8)).normalized())
    else:
        mb.cyl(a, b + d * .10, .05, .055, 3, LEATH, 'Chest', cap1=True, col1=FEATH)


def axe(mb, lod):
    x = -GX; z = GZ; B = 'Hand.R'
    mb.occ = False
    mb.cyl((x, .62, z), (x, -1.16, z), .022, .021, 5, sh(WOOD, .65), B, cap0=True)
    mb.cyl((x, -1.12, z), (x, -1.38, z), .030, 0, 4, STEEL, B, metal=1)
    mb.cyl((x, -.80, z), (x, -1.12, z), .028, .028, 5, IRON, B, metal=1)
    yc = -.96
    arc = [(math.radians(a)) for a in (38, 62, 90, 118, 142)]
    up = [(.045, .025)] + [(.30 * math.cos(a), .30 * math.sin(a)) for a in arc] + [(-.045, .025)]
    for sgn in (1, -1):
        o = up if sgn > 0 else [(a, -b) for a, b in reversed(up)]
        mb.plate([(x, yc + a, z + b) for a, b in o], X, .02, STEEL, sh(STEEL, .9), B, metal=1)
    mb.occ = True


def cape(mb, col, tint=0, lining=None):
    rows = [(1.50, .185, .128, 'Chest'), (1.20, .27, .175, 'Spine'), (0.74, .32, .215, 'Hips'), (0.26, .37, .245, 'Hips')]
    us = (-1, -.5, 0, .5, 1)
    for sgn in (1, -1):
        grid = []
        for i, (z, w, y, bone) in enumerate(rows):
            k = 1.0 - .10 * i
            row = []
            for j, u in enumerate(us):
                yy = y - .075 * u * u + (.02 if j % 2 else 0) * (i > 0) - (0 if sgn > 0 else .012)
                c = sh(col, k * (1.0 if j % 2 == 0 else .82)) if sgn > 0 else sh(lining or col, .55 * k)
                row.append(mb.add((w * u, yy, z), c, bone, tint if sgn > 0 else 0, 0))
            grid.append(row)
        for i in range(len(rows) - 1):
            for j in range(len(us) - 1):
                lo, up = grid[i + 1], grid[i]
                q = (lo[j], up[j], up[j + 1], lo[j + 1])
                mb.face(q if sgn > 0 else tuple(reversed(q)))


# ----------------------------------------------------------------------------- helmets (Head bone)
def kettle_hat(mb):
    H = dict(metal=1)
    mb.loft([(1.712, .168, .180, 'Head', sh(STEEL, .9), H), (1.745, .100, .110, 'Head', sh(STEEL, .8), H),
             (1.745, .100, .110, 'Head', sh(STEEL, .9), dict(H, split=True)), (1.805, .090, .100, 'Head', STEEL, H),
             (1.858, .050, .056, 'Head', sh(STEEL, 1.08), H)], 8, cap_top=True, phase=-PI / 2)
    mb.loft([(1.706, .168, .180, 'Head', sh(DSTEEL, .95), H), (1.735, .092, .102, 'Head', sh(DSTEEL, .7), H)], 8, phase=-PI / 2, flip=True)


def nasal_helm(mb):
    H = dict(metal=1)
    mb.loft([(1.700, .093, .106, 'Head', DSTEEL, H), (1.722, .093, .106, 'Head', DSTEEL, H),
             (1.722, .090, .103, 'Head', STEEL, dict(H, split=True)), (1.775, .082, .094, 'Head', STEEL, H),
             (1.835, .054, .062, 'Head', STEEL, H), (1.882, .012, .014, 'Head', sh(STEEL, 1.1), H)], 8, cap_top=True, phase=-PI / 2)
    mb.box((0, -.113, 1.655), (.024, .012, .12), DSTEEL, 'Head', metal=1)


def great_helm(mb):
    def prow(i, p):
        return {'p': p + Vector((0, -.014, 0))} if i == 0 else None

    def slit(i, p):
        r = {'col': BLACK, 'metal': 0} if i in (0, 1, 7) else {}
        if i == 0:
            r['p'] = p + Vector((0, -.014, 0))
        return r
    P = dict(metal=1, fn=prow); H = dict(metal=1)
    mb.loft([(1.485, .098, .112, 'Head', sh(STEEL, .72), P), (1.60, .108, .124, 'Head', sh(STEEL, .95), P),
             (1.684, .109, .125, 'Head', STEEL, P),
             (1.684, .109, .125, 'Head', STEEL, dict(metal=1, fn=slit, split=True)), (1.708, .109, .125, 'Head', STEEL, dict(metal=1, fn=slit)),
             (1.708, .109, .125, 'Head', STEEL, dict(P, split=True)), (1.80, .102, .117, 'Head', sh(STEEL, 1.05), P),
             (1.80, .102, .117, 'Head', sh(STEEL, .95), dict(H, split=True)), (1.83, .050, .058, 'Head', STEEL, H)],
            8, cap_top=True, phase=-PI / 2)
    mb.box((0, -.148, 1.59), (.02, .014, .19), GOLD, 'Head', metal=1)


def bascinet(mb, col):
    H = dict(metal=1)
    mb.loft([(1.700, .095, .108, 'Head', sh(col, .8), H), (1.775, .088, .102, 'Head', col, dict(H, y=.008)),
             (1.85, .056, .066, 'Head', col, dict(H, y=.018)), (1.915, .012, .014, 'Head', GOLD, dict(H, y=.026))],
            8, cap_top=True, phase=-PI / 2)


def arming_cap(mb):
    """padded, quilted cap worn over the coif"""
    q = lambda i, p: {'col': sh(GAMB, .78)} if i % 2 else None
    mb.loft([(1.700, .088, .102, 'Head', sh(LEATH, 1.05), {}), (1.722, .088, .102, 'Head', sh(LEATH, 1.05), {}),
             (1.722, .086, .100, 'Head', GAMB, dict(fn=q, split=True)), (1.782, .078, .091, 'Head', sh(GAMB, 1.05), dict(fn=q)),
             (1.822, .046, .054, 'Head', sh(GAMB, 1.1), {})], 8, cap_top=True, phase=-PI / 2)


def chin_beard(mb, col):
    mb.cyl((0, -.064, 1.618), (0, -.092, 1.528), (.068, .042), 0, 5, col, 'Head', col1=sh(col, .85))


def hood_top(mb):
    """the archer's hood worn up, with a short liripipe"""
    M = dict(tint=1)
    mb.loft([(1.742, .081, .096, 'Head', sh(TINT, .9), M), (1.800, .068, .082, 'Head', TINT, dict(M, y=.006)),
             (1.838, .030, .038, 'Head', TINT, dict(M, y=.016))], 8, cap_top=True, phase=-PI / 2)
    mb.cyl((0, .060, 1.815), (0, .175, 1.660), .034, 0, 4, sh(TINT, .9), 'Head', tint=1, col1=sh(TINT, .7))


def brim_hat(mb):
    """felt bycocket: brim drawn to a point in front, turned up behind, feather on the side"""
    FELT = (.52, .38, .23)

    def brim(i, p):
        if i == 0:
            return {'p': p + Vector((0, -.060, -.012))}
        if i in (3, 4, 5):
            return {'p': p + Vector((0, -.022, .034))}
        return None
    mb.loft([(1.712, .142, .150, 'Head', sh(FELT, .82), dict(fn=brim)), (1.742, .094, .106, 'Head', sh(FELT, .7), {}),
             (1.742, .094, .106, 'Head', sh(FELT, .95), dict(split=True)), (1.812, .080, .092, 'Head', FELT, {}),
             (1.856, .040, .046, 'Head', sh(FELT, 1.12), {})], 8, cap_top=True, phase=-PI / 2)
    mb.loft([(1.706, .142, .150, 'Head', sh(FELT, .62), dict(fn=brim)), (1.735, .088, .100, 'Head', sh(FELT, .5), {})], 8, phase=-PI / 2, flip=True)
    mb.plate([(.088, .02, 1.77), (.100, .15, 1.90), (.094, .20, 1.905), (.090, .07, 1.775)], X, .004, FEATH, sh(FEATH, .8), 'Head')


def visor_bascinet(mb):
    """hounskull bascinet with mail aventail (stands in for the whole head, like the great helm)"""
    H = dict(metal=1)
    mb.loft([(1.462, .150, .126, 'Chest', sh(MAIL, .72), dict(sq=.88)), (1.535, .104, .110, 'Head', sh(MAIL, .9), {}),
             (1.622, .099, .113, 'Head', MAIL, {}),
             (1.606, .103, .117, 'Head', sh(STEEL, .78), dict(H, split=True)), (1.722, .104, .118, 'Head', STEEL, dict(H, y=.004)),
             (1.826, .072, .084, 'Head', sh(STEEL, 1.04), dict(H, y=.014)), (1.908, .012, .014, 'Head', sh(STEEL, 1.1), dict(H, y=.026))],
            8, cap_top=True, phase=-PI / 2)
    mb.cyl((0, -.078, 1.662), (0, -.232, 1.632), (.078, .070), 0, 6, sh(STEEL, .92), 'Head', metal=1, up=X, col1=sh(STEEL, 1.1))
    mb.box((0, -.112, 1.722), (.135, .02, .016), BLACK, 'Head')


def fan_crest(mb):
    """transverse fan crest in the company colour"""
    pts = [(.150 * math.cos(a), .012, 1.822 + .175 * math.sin(a)) for a in (math.radians(d) for d in (8, 40, 65, 90, 115, 140, 172))]
    pts = [(.085, .012, 1.815)] + pts + [(-.085, .012, 1.815)]
    mb.plate(pts, Y, .012, sh(TINT, .9), TINT, 'Head', tintf=1, tintb=1)


# ----------------------------------------------------------------------------- types
INF = dict(torso=(TINT, 1, 0), skirt=(0.66, TINT, 1, 0, 1.0), thigh=(HOSE, 0), shin=(HOSE, 0), boot=(BOOT, 0), boot_z=.36,
           arm=(MAIL, 0), forearm=(GAMB, 0), hand=(LEATH, 0), wrap=(MAIL, 0, 0))
ARC = dict(torso=(GAMB, 0, 0), skirt=(0.72, sh(GAMB, .88), 0, 0, .95), thigh=(GHOSE, 0), shin=(GHOSE, 0), boot=(LEATH, 0), boot_z=.30,
           arm=(GAMB, 0), forearm=(LEATH, 0), hand=(SKIN, 0), wrap=(TINT, 1, 0), quilt=True, sleeve=(TINT, 1))
KNI = dict(torso=(TINT, 1, 0), skirt=(0.55, TINT, 1, 0, 1.0), thigh=(STEEL, 1), shin=(STEEL, 1), boot=(DSTEEL, 1), boot_z=.30,
           arm=(STEEL, 1), forearm=(STEEL, 1), hand=(DSTEEL, 1), cuff=True, bulk=1.05, belt=(DLEATH, 0))
WAR = dict(torso=(PLATE, 0, 1), skirt=(0.60, PLATE, 0, 1, 1.0), thigh=(PLATE, 1), shin=(PLATE, 1), boot=(IRON, 1), boot_z=.30,
           arm=(PLATE, 1), forearm=(PLATE, 1), hand=(IRON, 1), cuff=True, bulk=1.13, belt=(GOLD, 1), wrap=(MAIL, 0, 0), beard=FUR)


def mail_hem(mb, sp, n=10):
    zh = sp['skirt'][0]; bk = sp.get('bulk', 1.0)
    S = dict(sq=.88, fn=_hem)
    mb.loft([(zh - .075, .208 * bk, .160 * bk, 'Hips', sh(MAIL, .75), S), (zh + .02, .209 * bk, .161 * bk, 'Hips', MAIL, S)], n)


def plate_bits(mb, sp, col, trim=None):
    """pauldrons, couters, poleyns: rigid shells that cover the joint seams"""
    xa = _arm_x(sp)
    for side, sx in (('L', 1), ('R', -1)):
        O = dict(x=(xa + .010) * sx, metal=1)
        UA = 'UpperArm.' + side
        mb.loft([(1.355, .068, .078, UA, trim or sh(col, .8), O), (1.445, .080, .086, UA, col, O),
                 (1.508, .058, .064, UA, col, dict(O, x=(xa - .004) * sx)), (1.535, .020, .022, UA, sh(col, 1.08), dict(O, x=(xa - .012) * sx))],
                6, cap_top=True)
        O = dict(x=xa * sx, y=.010, metal=1)
        mb.loft([(1.135, .030, .032, UA, sh(col, .85), O), (1.18, .054, .060, UA, col, O), (1.225, .030, .032, UA, col, O)],
                5, cap_bot=True, cap_top=True, phase=PI / 2)
        LL = 'LowerLeg.' + side
        O = dict(x=.10 * sx, y=-.020, metal=1)
        mb.loft([(0.455, .034, .034, LL, sh(col, .85), O), (0.515, .062, .064, LL, col, O), (0.575, .036, .036, LL, col, O)],
                5, cap_bot=True, cap_top=True, phase=-PI / 2)


def build_infantry(lod):
    mb = MB()
    if lod == 0:
        body(mb, INF)
        mail_hem(mb, INF)
        mb.var = HV(0); kettle_hat(mb)
        mb.var = HV(1); nasal_helm(mb)
        mb.var = HV(2); arming_cap(mb); chin_beard(mb, (.46, .33, .21))
        mb.var = 0
        # mail cowl over the shoulders
        mb.loft([(1.435, .200, .128, 'Chest', sh(MAIL, .85), dict(sq=.85)), (1.50, .120, .100, 'Chest', MAIL), (1.565, .068, .074, 'Chest', MAIL)], 8, phase=-PI / 2)
        # side-arm on the right hip
        mb.cyl((-.185, -.03, 1.03), (-.225, .17, .60), .024, .016, 4, DLEATH, 'Hips', cap1=True)
        mb.box((-.180, -.045, 1.07), (.03, .03, .10), DSTEEL, 'Hips', metal=1)
    else:
        body1(mb, INF)
        mb.var = HV(0); mb.cyl((0, 0, 1.715), (0, 0, 1.850), (.172, .184), 0, 6, sh(STEEL, .82), 'Head', metal=1, up=X, col1=STEEL)
        mb.var = HV(1); mb.cyl((0, 0, 1.705), (0, 0, 1.885), (.098, .110), 0, 6, sh(STEEL, .85), 'Head', metal=1, up=X, col1=STEEL)
        mb.var = HV(2); mb.cyl((0, 0, 1.700), (0, 0, 1.840), (.092, .106), 0, 6, sh(GAMB, .9), 'Head', up=X, col1=sh(GAMB, 1.1))
        mb.var = 0
    spear(mb, lod); round_shield(mb, lod)
    return mb


def build_archer(lod):
    mb = MB()
    M = dict(tint=1, sq=.9)
    if lod == 0:
        body(mb, ARC)
        mb.var = HV(0); nasal_helm(mb)
        mb.var = HV(1); hood_top(mb)
        mb.var = HV(2); brim_hat(mb)
        mb.var = 0
        mb.loft([(1.375, .232, .150, 'Chest', sh(TINT, .78), M), (1.465, .200, .128, 'Chest', sh(TINT, .92), M),
                 (1.565, .072, .078, 'Chest', TINT, M)], 10)
        mb.box((-.125, -.118, .985), (.085, .05, .10), LEATH, 'Hips')
    else:
        body1(mb, ARC)
        mb.loft([(1.375, .232, .150, 'Chest', sh(TINT, .78), M), (1.555, .075, .08, 'Chest', TINT, M)], 6)
        mb.var = HV(0); mb.cyl((0, 0, 1.705), (0, 0, 1.885), (.098, .110), 0, 6, sh(STEEL, .85), 'Head', metal=1, up=X, col1=STEEL)
        mb.var = HV(1); mb.cyl((0, .004, 1.715), (0, .014, 1.850), (.088, .102), 0, 6, sh(TINT, .9), 'Head', tint=1, up=X, col1=TINT)
        mb.var = HV(2); mb.cyl((0, -.02, 1.715), (0, 0, 1.860), (.140, .160), 0, 6, (.42, .30, .18), 'Head', up=X, col1=(.55, .40, .24))
        mb.var = 0
    bow(mb, lod); quiver(mb, lod)
    return mb


def build_knight(lod):
    mb = MB()
    if lod == 0:
        body(mb, KNI)
        mail_hem(mb, KNI)
        mb.var = HV(0) | HV(2); great_helm(mb)
        mb.var = HV(0)
        mb.tube([(0, .0, 1.815), (0, .02, 1.93), (0, .10, 1.995), (0, .21, 1.93)], [.02, .046, .05, .01], 5, TINT, 'Head', tint=1,
                cols=[sh(TINT, .8), TINT, TINT, sh(TINT, .85)], cap1=True)
        mb.var = HV(1); visor_bascinet(mb)
        mb.var = HV(2); fan_crest(mb)
        mb.var = 0
        plate_bits(mb, KNI, STEEL)
        mb.cyl((.185, -.03, 1.03), (.27, .27, .44), .028, .018, 4, DLEATH, 'Hips', cap1=True, col1=GOLD)
    else:
        body1(mb, KNI)
        H = dict(metal=1)
        mb.loft([(1.49, .100, .114, 'Head', sh(STEEL, .75), H), (1.81, .104, .118, 'Head', STEEL, H)], 6, cap_top=True, phase=-PI / 2)
        mb.var = HV(0); mb.cyl((0, 0, 1.80), (0, .17, 1.99), .07, 0, 3, TINT, 'Head', tint=1)
        mb.var = HV(1); mb.cyl((0, .01, 1.80), (0, .026, 1.915), (.062, .072), 0, 4, STEEL, 'Head', metal=1, up=X)
        mb.var = HV(2); mb.plate([(.15, .01, 1.80), (.09, .01, 1.97), (-.09, .01, 1.97), (-.15, .01, 1.80)], Y, .012, sh(TINT, .9), TINT, 'Head', tintf=1, tintb=1)
        mb.var = 0
    sword(mb, lod); heater_shield(mb, lod)
    return mb


def build_warlord(lod=0):
    mb = MB()
    sp = WAR
    body(mb, sp)
    # gold hem on the fauld, gold gorget ring
    bk = sp['bulk']
    mb.loft([(.585, .220 * bk, .172 * bk, 'Hips', sh(GOLD, .8), dict(metal=1, sq=.88, fn=_hem)),
             (.625, .219 * bk, .171 * bk, 'Hips', GOLD, dict(metal=1, sq=.88, fn=_hem))], 10)
    plate_bits(mb, sp, PLATE, trim=GOLD)
    bascinet(mb, PLATE)
    # mail aventail
    mb.loft([(1.455, .185, .135, 'Chest', sh(MAIL, .8)), (1.52, .115, .105, 'Chest', MAIL), (1.60, .085, .095, 'Head', MAIL)], 8, phase=-PI / 2)
    # crown
    n = 12
    a = mb.ring(Vector((0, .004, 1.705)), X, Y, .103, .116, n, 0, sh(GOLD, .85), 'Head', 0, 1)
    b = mb.ring(Vector((0, .006, 1.75)), X, Y, .100, .113, n, 0, GOLD, 'Head', 0, 1)
    for i in range(0, n, 2):
        v = mb.v[b[i]]; mb.v[b[i]] = (v[0] * 1.03, v[1] * 1.03, v[2] + .055)
    mb.bridge(a, b)
    # plume
    mb.tube([(0, .02, 1.90), (0, .03, 2.03), (0, .11, 2.12), (0, .24, 2.10), (0, .33, 1.98)], [.02, .052, .064, .052, .012], 5, CRIMSON, 'Head',
            cols=[sh(CRIMSON, .7), CRIMSON, sh(CRIMSON, 1.2), CRIMSON, sh(CRIMSON, .8)], cap1=True)
    mb.cyl((0, -.088, 1.605), (0, -.112, 1.455), (.066, .042), 0, 5, FUR, 'Head', col1=sh(FUR, .8))  # beard
    # fur mantle + cape
    tuft = lambda i, p: {'col': sh(FUR, .75 if i % 2 else 1.25)}
    mb.loft([(1.34, .315, .215, 'Chest', sh(FUR, .8), dict(fn=tuft, sq=.9)), (1.455, .255, .178, 'Chest', FUR, dict(fn=tuft, sq=.9)),
             (1.56, .105, .105, 'Chest', sh(FUR, 1.2))], 10)
    cape(mb, CRIMSON, 0, lining=FUR)
    xa = _arm_x(sp)
    for sx, side in ((1, 'L'), (-1, 'R')):
        mb.cyl(((xa + .02) * sx, 0, 1.525), ((xa + .13) * sx, 0, 1.655), .028, 0, 4, GOLD, 'UpperArm.' + side, metal=1)
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


def pose_mats(rig, pose):
    _prevq.clear(); apply_pose(rig, pose); bpy.context.view_layer.update()
    M = {b.name: (rig.pose.bones[b.name].matrix @ b.matrix_local.inverted()) for b in rig.data.bones}
    _prevq.clear(); apply_pose(rig, {}); bpy.context.view_layer.update()
    return M


def _hemi(n):
    out = []
    ga = PI * (3 - math.sqrt(5))
    for i in range(n):
        z = math.sqrt((i + .5) / n)          # cosine weighted
        r = math.sqrt(1 - z * z); a = ga * i
        out.append((r * math.cos(a), r * math.sin(a), z))
    return out


AO_DIRS = _hemi(40)
AO_R = 0.42
AO_K = 0.78


def bake_ao(mb, nrm, M):
    """per-vertex ambient occlusion in the READY pose (how the men stand most of the time)"""
    P = [M[b] @ Vector(v) for v, b in zip(mb.v, mb.b)]
    # a vertex is only shaded by faces that are drawn together with it (base faces, plus its own variant's)
    trees = {}
    for km in set(mb.k):
        polys = [f for f, o, fk in zip(mb.f, mb.fo, mb.fk) if o and (fk == 0 or (fk & km))]
        trees[km] = BVHTree.FromPolygons(P, polys, all_triangles=False, epsilon=0.0)
    ao = []
    for i, p in enumerate(P):
        bvh = trees[mb.k[i]]
        n = (M[mb.b[i]].to_3x3() @ nrm[i]).normalized()
        t = n.cross(Z if abs(n.z) < .9 else X).normalized(); b = n.cross(t)
        o = p + n * 0.012
        occ = 0.0
        for dx, dy, dz in AO_DIRS:
            d = t * dx + b * dy + n * dz
            hit = bvh.ray_cast(o, d, AO_R)
            if hit[0] is not None:
                occ += 1.0 - hit[3] / AO_R
        occ /= len(AO_DIRS)
        sky = 0.78 + 0.22 * (n.z * 0.5 + 0.5)
        gnd = 0.84 + 0.16 * min(1.0, max(0.0, p.z) / 0.55)
        c = mb.c[i]
        lo = 0.84 if (c[2] > 0 and abs(c[0] / c[2] - SKIN[0] / SKIN[2]) < .02 and abs(c[1] / c[2] - SKIN[1] / SKIN[2]) < .02) else 0.30
        ao.append(max(lo, (1.0 - AO_K * min(1.0, occ * 1.5)) * sky * gnd))
    return ao


def make_object(name, mb, rig, mat, sel=None):
    """sel: preview only - keep just the faces drawn for that selection"""
    keep = [sel is None or k == 0 or (k >> sel) & 1 for k in mb.fk]
    me = bpy.data.meshes.new(name)
    me.from_pydata(mb.v, [], [f for f, w in zip(mb.f, keep) if w])
    me.update()
    me.polygons.foreach_set('use_smooth', [not f for f, w in zip(mb.ff, keep) if w])
    nrm = [v.normal.copy() for v in me.vertices]
    ao = bake_ao(mb, nrm, AO_M)
    ca = me.color_attributes.new('Col', 'FLOAT_COLOR', 'CORNER')
    uvl = me.uv_layers.new(name='UVMap')
    for l in me.loops:
        i = l.vertex_index
        c = lin(sh(mb.c[i], ao[i]))
        ca.data[l.index].color = (c[0], c[1], c[2], 1.0)
        # glTF exporter flips V -> exported V = variant mask + 0.5 * metal (preview: plain metal mask)
        uvl.data[l.index].uv = (mb.t[i], 1.0 - (mb.m[i] if sel is not None else mb.k[i] + 0.5 * mb.m[i]))
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
AO_M = pose_mats(rig, READY)
mat = make_material(DO_PREVIEW or DO_PV)
OBJS = {}
STAT = {}
if DO_PV:
    cells = []
    for r, (tn, fn) in enumerate((('Infantry', build_infantry), ('Archer', build_archer), ('Knight', build_knight))):
        for lod in (0, 1):
            mb = fn(lod)
            for s in range(6):
                nm = '%s_%d_s%d' % (tn, lod, s)
                OBJS[nm] = make_object(nm, mb, rig, mat, sel=s)
                if lod == 0:
                    cells.append((OBJS[nm], READY, s, r * 2, TINTS[(r + s) % 5], 0))
                    cells.append((OBJS[nm], READY if r != 1 else DRAW, s, r * 2 + 1, TINTS[(r + s) % 5], math.radians(150 if r != 1 else 0)))
                elif s < 3:
                    cells.append((OBJS[nm], READY, 6 + s, r * 2, TINTS[(r + s) % 5], 0))
                else:
                    cells.append((OBJS[nm], READY, 3 + s, r * 2 + 1, TINTS[(r + s) % 5], math.radians(150)))
    os.makedirs(PREV, exist_ok=True)
    wall_sheet(PREV + r"\sold_variants.png", cells, 9, 6, px=250)
    raise SystemExit
for name, fn, lod in TYPES:
    mb = fn(lod)
    OBJS[name] = make_object(name, mb, rig, mat, sel=0 if DO_PREVIEW else None)
    STAT[name] = dict(verts=len(mb.v), tris=mb.tris(), tris_drawn=[mb.tris(s) for s in range(6)])
    print('MESH', name, 'verts', len(mb.v), 'tris', mb.tris(), 'drawn per selection', [mb.tris(s) for s in range(6)])
open(STATS, 'w').write(json.dumps(STAT, indent=1))

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
