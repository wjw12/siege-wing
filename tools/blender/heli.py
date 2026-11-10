# Siege Wing hero helicopter generator (original design). Run headless:
#   blender.exe -b -P heli.py [-- nopreview] [-- views=a,b] [-- noao]
import bpy, bmesh, sys, os, math, time, functools
import numpy as np
from mathutils import Vector, Matrix

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import importlib, heli_lib, heli_tex
importlib.reload(heli_lib); importlib.reload(heli_tex)
from heli_lib import *

ROOT = os.path.dirname(os.path.dirname(HERE))
OUT = os.path.join(ROOT, 'assets', 'models', 'heli.glb') if os.path.basename(HERE) == 'blender' else os.path.join(HERE, 'heli.glb')   # sandbox copies export next to themselves
PREV = os.path.join(HERE, 'preview'); TEXD = os.path.join(HERE, 'tex')
os.makedirs(PREV, exist_ok=True); os.makedirs(TEXD, exist_ok=True)
ARGS = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
T0 = time.time()

bpy.ops.wm.read_factory_settings(use_empty=True)
rad = math.radians
sin, cos, pi = math.sin, math.cos, math.pi

# ------------------------------------------------------------------ constants
YMAX, YMIN = 6.20, -8.40
YN = 5.80            # front of the fuselage loft (sensor turret sits ahead of it)
ROTOR_Z = 2.2
ROTOR_R = 7.3
GEAR_Z = -1.75
EYE = V(0, 1.91, 0.92)
TR_HUB = V(0.36, -8.35, 1.2)

# vertex tints (linear). 'Paint' is untextured white * tint; Hull/HullB are textured * tint.
T_W = (1, 1, 1)
T_OLIVE = (0.043, 0.049, 0.037)      # airframe paint (matches hull textures)
T_OLIVE2 = (0.030, 0.034, 0.027)     # darker trim / frames
T_OLIVE3 = (0.056, 0.062, 0.048)     # lighter replaced-panel tone
T_DARK = (0.016, 0.018, 0.017)
T_BLACK = (0.006, 0.006, 0.007)
T_RIV = (0.022, 0.025, 0.021)        # fastener heads
T_STEN = (0.20, 0.21, 0.185)         # low-vis light stencil grey
T_INT = (0.03, 0.032, 0.035)
T_INT2 = (0.055, 0.058, 0.06)
T_STEEL = (0.42, 0.42, 0.44)
T_STEELD = (0.20, 0.20, 0.21)
T_GUN = (0.09, 0.09, 0.10)
T_GUND = (0.045, 0.045, 0.05)
T_BURNT = (0.16, 0.12, 0.09)
T_SOOT = (0.03, 0.027, 0.025)
T_CHROME = (0.75, 0.75, 0.78)
T_HUB1 = (0.034, 0.035, 0.037)       # painted rotor-head parts
T_HUB2 = (0.017, 0.018, 0.019)
T_SUIT = (0.13, 0.125, 0.075)
T_VEST = (0.04, 0.05, 0.035)
T_HELM = (0.10, 0.11, 0.09)
T_FABRIC = (0.07, 0.075, 0.05)
T_YEL = (0.75, 0.52, 0.04)
T_YELD = (0.38, 0.27, 0.03)
T_RED = (0.35, 0.015, 0.012)
T_REDD = (0.22, 0.02, 0.015)
T_GRN = (0.01, 0.2, 0.04)
T_P9 = (0.9, 0.9, 0.9); T_P8 = (0.8, 0.8, 0.8); T_P7 = (0.7, 0.7, 0.7); T_P5 = (0.5, 0.5, 0.5)

# ------------------------------------------------------------------ materials
def mk_mat(name, base=(1, 1, 1), metal=0.0, rough=0.6, emit=None, emit_s=1.0, alpha=1.0, tex=None, nrm=None, orm=None, nstr=1.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes['Principled BSDF']
    b.inputs['Base Color'].default_value = (*base, 1)
    b.inputs['Metallic'].default_value = metal
    b.inputs['Roughness'].default_value = rough
    if emit:
        b.inputs['Emission Color'].default_value = (*emit, 1)
        b.inputs['Emission Strength'].default_value = emit_s
    if alpha < 1:
        b.inputs['Alpha'].default_value = alpha
        try: m.surface_render_method = 'BLENDED'
        except Exception: pass
        try: m.blend_method = 'BLEND'
        except Exception: pass
        m.use_backface_culling = False
    else:
        m.use_backface_culling = True
    if tex:
        t = nt.nodes.new('ShaderNodeTexImage'); t.image = tex; t.name = 'BaseTex'
        nt.links.new(t.outputs['Color'], b.inputs['Base Color'])
    if nrm:
        t = nt.nodes.new('ShaderNodeTexImage'); t.image = nrm
        nm = nt.nodes.new('ShaderNodeNormalMap'); nm.inputs['Strength'].default_value = nstr
        nt.links.new(t.outputs['Color'], nm.inputs['Color'])
        nt.links.new(nm.outputs['Normal'], b.inputs['Normal'])
    if orm:      # glTF packing: G = roughness, B = metallic
        t = nt.nodes.new('ShaderNodeTexImage'); t.image = orm
        sep = nt.nodes.new('ShaderNodeSeparateColor')
        nt.links.new(t.outputs['Color'], sep.inputs['Color'])
        nt.links.new(sep.outputs['Green'], b.inputs['Roughness'])
        nt.links.new(sep.outputs['Blue'], b.inputs['Metallic'])
    MATS[name] = m
    return m

# ------------------------------------------------------------------ fuselage sections
KEYS = [  # y, w, ztop, zbot, zmid, nt, nb
    (5.90, 0.31, -0.07, -0.62, -0.33, 3.6, 3.6),
    (5.80, 0.335, -0.05, -0.65, -0.33, 3.6, 3.6),
    (5.55, 0.415, 0.03, -0.74, -0.28, 3.3, 3.5),
    (5.25, 0.47, 0.10, -0.81, -0.22, 2.8, 3.3),
    (4.95, 0.50, 0.15, -0.84, -0.18, 2.5, 3.0),
    (4.40, 0.54, 0.56, -0.86, -0.12, 2.5, 3.2),
    (3.90, 0.56, 0.80, -0.86, -0.10, 2.5, 3.2),
    (3.15, 0.57, 0.86, -0.86, -0.10, 2.5, 3.2),
    (2.60, 0.58, 1.24, -0.86, -0.10, 2.6, 3.2),
    (1.90, 0.58, 1.29, -0.86, -0.10, 2.6, 3.2),
    (1.35, 0.58, 1.28, -0.86, -0.10, 2.8, 3.2),
    (0.60, 0.57, 1.32, -0.86, -0.10, 3.0, 3.2),
    (-0.60, 0.56, 1.30, -0.85, -0.10, 3.0, 3.2),
    (-1.60, 0.50, 1.10, -0.78, -0.05, 2.8, 3.0),
    (-2.50, 0.38, 0.70, -0.50, 0.05, 2.4, 2.6),
    (-3.30, 0.27, 0.42, -0.26, 0.08, 2.2, 2.2),
    (-5.00, 0.215, 0.32, -0.16, 0.08, 2.1, 2.1),
    (-7.40, 0.16, 0.24, -0.08, 0.08, 2.0, 2.0),
    (-8.00, 0.125, 0.22, -0.03, 0.09, 2.0, 2.0),
    (-8.40, 0.035, 0.15, 0.05, 0.10, 2.0, 2.0),
]
_K = np.array(sorted(KEYS))
_fy = np.arange(YMIN - 0.5, YMAX + 0.5, 0.01)
_fp = np.stack([np.interp(_fy, _K[:, 0], _K[:, c]) for c in range(1, 7)], 1)
ker = np.ones(21) / 21
for _ in range(2):
    pad = np.pad(_fp, ((10, 10), (0, 0)), mode='edge')
    _fp = np.stack([np.convolve(pad[:, c], ker, mode='valid') for c in range(6)], 1)

@functools.lru_cache(maxsize=None)
def _secp(y):
    return tuple(float(np.interp(y, _fy, _fp[:, c])) for c in range(6))

def sec_params(y):
    return list(_secp(round(float(y), 4)))

def sp(y, th, prm=None):
    w, zt, zb, zm, nt, nb = prm or _secp(round(float(y), 4))
    s, c = sin(th), cos(th)
    n = nt if c >= 0 else nb
    x = w * math.copysign(abs(s) ** (2 / n), s)
    if c >= 0: z = zm + (zt - zm) * c ** (2 / nt)
    else: z = zm - (zm - zb) * (-c) ** (2 / nb)
    return V(x, y, z)

def sn(y, th):
    e = 0.02
    a = sp(y, th + e) - sp(y, th - e); b = sp(y + e, th) - sp(y - e, th)
    n = a.cross(b).normalized()
    zm = sec_params(y)[3]
    if n.dot(sp(y, th) - V(0, y, zm)) < 0: n = -n
    return n

def spi(y, th, inset):
    return sp(y, th) - sn(y, th) * inset

def circ(y):
    pts = [sp(y, 2 * pi * k / 48) for k in range(48)]
    return sum((pts[k] - pts[k - 1]).length for k in range(48))

N = 48
JG = 10          # glass arc: j < JG or j >= N-JG   (|theta| < 75 deg)
THS = rad(75)
YG0, YG1 = 1.35, 4.95
Lf = YMAX - YMIN

def hfn(y, thd):
    """fuselage surface for P_patch: (y, theta in degrees) -> point, normal"""
    return sp(y, rad(thd)), sn(y, rad(thd))

def huv(y, thd):
    return ((thd % 360) / 360.0, (y - YMIN) / Lf)

def stations():
    ys = [round(YN - 0.05 * k, 3) for k in range(0, 17)]            # 5.8 .. 5.0
    ys += [round(4.95 - 0.05 * k, 3) for k in range(0, 73)]        # 4.95 .. 1.35
    y = 1.2
    while y > YMIN + 0.01:
        ys.append(round(y, 3)); y -= 0.15
    ys.append(YMIN)
    return ys

# ---- canopy shoulder line (flat-pane canopy) and the faceted spine fairing behind it
A0_TH = 38.0
_A0 = sp(4.95, rad(A0_TH))
CAN = [(4.95, _A0.x, _A0.z), (4.25, 0.42, 0.80), (3.15, 0.46, 0.845), (2.60, 0.43, 1.235), (1.35, 0.42, 1.30)]
SPINE = np.array([(-3.2, 0.12, 0.50), (-2.4, 0.24, 0.84), (-1.7, 0.36, 1.20), (-0.9, 0.42, 1.36), (0.9, 0.42, 1.36), (1.35, 0.42, 1.30)])

def sill(y, s=1):
    return sp(y, s * THS)

def shoulder(y, s=1):
    for k in range(len(CAN) - 1):
        (ya, xa, za), (yb, xb, zb) = CAN[k], CAN[k + 1]
        if yb - 1e-6 <= y <= ya + 1e-6:
            t = (ya - y) / (ya - yb)
            return V(s * (xa + (xb - xa) * t), y, za + (zb - za) * t)
    raise ValueError(y)

def spine_xz(y):
    return float(np.interp(y, SPINE[:, 0], SPINE[:, 1])), float(np.interp(y, SPINE[:, 0], SPINE[:, 2]))

def spine_pt(y, j):
    """Faceted upper-fuselage section (y <= 1.35): j in -JG..JG, blends into the round boom aft."""
    s = 1 if j >= 0 else -1; k = abs(j)
    xa, za = spine_xz(y)
    S = sp(y, THS); A = V(xa, y, za)
    if k <= 4:
        x = xa * k / 4 - (0.045 if k == 4 else 0)
        p = V(x, y, za + 0.025 * (1 - (x / xa) ** 2))
    elif k == 5:
        p = A + (S - A).normalized() * 0.055
    else:
        p = A + (S - A) * ((k - 5) / 5.0)
    w = min(1.0, max(0.0, (y + 3.2) / 0.9)); w = w * w * (3 - 2 * w)
    q = sp(y, 2 * pi * k / N)
    p = q + (p - q) * w
    p.x *= s
    return p

def spine_n(y, s=1):
    """outward normal of the canted spine side face"""
    xa, za = spine_xz(y); S = sp(y, THS); A = V(xa, y, za)
    d = (A - S); n = V(d.z, 0, -d.x).normalized()
    if n.x < 0: n = -n
    n.x *= s
    return n

def spine_side(y, t, s=1):
    """point on the spine side face, t=0 at sill .. 1 at shoulder"""
    xa, za = spine_xz(y); S = sp(y, THS); A = V(xa, y, za)
    p = S + (A - S) * t; p.x *= s
    return p

# ------------------------------------------------------------------ build parts
def build_fuselage():
    ys = stations()
    rings = []
    for y in ys:
        r = [sp(y, 2 * pi * j / N) for j in range(N)]
        if y <= YG0 + 1e-6 and y > -3.25:
            for j in range(-JG, JG + 1):
                r[j % N] = spine_pt(y, j)
        rings.append(r)
    c0 = sum(rings[0], V(0, 0, 0)) / N
    caps = []; cys = []
    for t in (0.985, 0.92, 0.78, 0.55, 0.28):
        k = math.sqrt(1 - t * t)
        caps.append([c0 + (p - c0) * (0.55 + 0.45 * k) + V(0, t * 0.09, 0) for p in rings[0]]); cys.append(YN + t * 0.09)
    c1 = sum(caps[0], V(0, 0, 0)) / N
    caps = [[c1 + (p - c1) * 0.02 for p in caps[0]]] + caps; cys = [cys[0]] + cys
    rings = caps + rings; ys = cys + ys
    uvfn = lambda i, j: (j / N, (ys[i] - YMIN) / Lf)
    def is_glass(i, j):
        return ys[i] <= YG1 + 1e-6 and ys[i + 1] >= YG0 - 1e-6 and (j < JG or j >= N - JG)
    hull = MB()
    P_loft(hull, rings, 'Hull', T_W, cap0=True, cap1=True, uvfn=uvfn,
           matfn=lambda i, j: None if is_glass(i, j) else 'Hull')

    # ---- interior tub (cockpit shell; contents live in heli_cockpit.py)
    tub = hull
    def floor_z(y):
        t = min(1, max(0, (y - 2.75) / 0.12))
        return -0.30 + (-0.68 + 0.30) * t
    tys = [y for y in ys if YG0 - 1e-6 <= y <= YG1 + 1e-6]
    trings = []
    for y in tys:
        r = []
        for j in range(JG, N - JG + 1):
            p = spi(y, 2 * pi * j / N, 0.035)
            p.z = max(p.z, floor_z(y))
            r.append(p)
        trings.append(r)
    P_loft(tub, trings, 'Paint', T_INT, closed=False, ref=V(0, 3, 0.3), inward=True)
    for y, nrm in ((YG0 + 0.03, 1), (YG1 - 0.03, -1)):
        pts = [spi(y, 2 * pi * j / N, 0.03) for j in range(N)]
        P_poly(tub, pts, 'Paint', T_INT, nrm=V(0, nrm, 0))
    # rear bulkhead of the flat-pane canopy (covers the faceted spine section)
    P_poly(tub, [spine_pt(YG0, j) + V(0, 0.004, 0) for j in range(-JG, JG + 1)], 'Paint', T_INT, nrm=V(0, 1, 0))
    build(hull, 'Body')


def build_canopy():
    """Flat-pane tandem canopy: glass (unique UV island per pane) + separate frame mesh."""
    ys = [round(4.95 - 0.05 * k, 3) for k in range(0, 73)]
    panes = []      # each pane: list of polygons (lists of Vector)
    for s in (-1, 1):
        # front quarter pane: fan from the 4.25 shoulder over sill + nose-ring arc
        C = shoulder(4.25, s)
        chain = [sill(y, s) for y in ys if 4.25 - 1e-6 <= y <= 4.95 + 1e-6][::-1]          # 4.25 -> 4.95
        chain += [sp(4.95, s * rad(a)) for a in (68, 61, 54, 46, A0_TH)]
        panes.append([[C, chain[k], chain[k + 1]] for k in range(len(chain) - 1)])
        for ya, yb in ((4.25, 3.15), (3.15, 1.35)):
            yy = [y for y in ys if yb - 1e-6 <= y <= ya + 1e-6]
            panes.append([[sill(yy[k], s), sill(yy[k + 1], s), shoulder(yy[k + 1], s), shoulder(yy[k], s)] for k in range(len(yy) - 1)])
    # gunner windshield (base follows the nose ring), roofs, pilot windshield
    ths = np.linspace(-A0_TH, A0_TH, 9)
    bot = [sp(4.95, rad(a)) for a in ths]
    L, R = shoulder(4.25, -1), shoulder(4.25, 1)
    top = [L + (R - L) * (k / 8) for k in range(9)]
    panes.append([[bot[k], bot[k + 1], top[k + 1], top[k]] for k in range(8)])
    for ya, yb in ((4.25, 3.15), (3.15, 2.60), (2.60, 1.35)):
        panes.append([[shoulder(ya, -1), shoulder(ya, 1), shoulder(yb, 1), shoulder(yb, -1)]])
    # ---- unique UV islands, uniform texel density, shelf packed into 0..1
    isl = []
    for polys in panes:
        nr = V(0, 0, 0)
        for poly in polys:
            c = sum(poly, V(0, 0, 0)) / len(poly)
            pn = V(0, 0, 0)
            for k in range(len(poly)):
                pn += (poly[k] - c).cross(poly[(k + 1) % len(poly)] - c)
            if pn.dot(c - V(0, c.y, 0.3)) < 0:
                poly.reverse(); pn = -pn
            nr += pn
        nr.normalize()
        e1 = (V(0, 1, 0) - nr * nr.y).normalized(); e2 = nr.cross(e1)
        uv = [[(p.dot(e1), p.dot(e2)) for p in poly] for poly in polys]
        us = [u for q in uv for u, v in q]; vs = [v for q in uv for u, v in q]
        isl.append(dict(polys=polys, uv=uv, u0=min(us), v0=min(vs), w=max(us) - min(us), h=max(vs) - min(vs)))
    M_ = 0.012        # margin (metres before scaling)
    def pack(scale, order):
        lim = 1.0 / scale
        x = M_; y = M_; rowh = 0; pos = {}
        for k in order:
            it = isl[k]
            if x + it['w'] + M_ > lim:
                x = M_; y += rowh + M_; rowh = 0
            pos[k] = (x, y); x += it['w'] + M_; rowh = max(rowh, it['h'])
        return pos, (y + rowh + M_) <= lim
    def best_scale(order):
        lo, hi = 0.05, 2.0
        for _ in range(24):
            mid = (lo + hi) / 2
            if pack(mid, order)[1]: lo = mid
            else: hi = mid
        return lo
    def rotate(it):
        it['uv'] = [[(v, -u) for u, v in q] for q in it['uv']]
        us = [u for q in it['uv'] for u, v in q]; vs = [v for q in it['uv'] for u, v in q]
        it.update(u0=min(us), v0=min(vs), w=max(us) - min(us), h=max(vs) - min(vs))
    import random as _rnd
    rr = _rnd.Random(3); best = (0, None, None)
    for trial in range(400):          # random rotations / orders, keep the densest shelf packing
        flips = [rr.random() < 0.5 for _ in isl] if trial else [False] * len(isl)
        for it, f in zip(isl, flips):
            if f: rotate(it)
        order = sorted(range(len(isl)), key=lambda k: -isl[k]['h'])
        if trial % 3 == 2: rr.shuffle(order)
        sc = best_scale(order)
        if sc > best[0]: best = (sc, flips, order)
        for it, f in zip(isl, flips):
            if f: rotate(it); rotate(it); rotate(it)
    lo, flips, order = best
    for it, f in zip(isl, flips):
        if f: rotate(it)
    pos, ok = pack(lo, order)
    glass = MB()
    for k, it in enumerate(isl):
        ox, oy = pos[k]
        for poly, uv in zip(it['polys'], it['uv']):
            ids = [glass.addv(p, T_W) for p in poly]
            glass.addf(ids, 'Glass', [((u - it['u0'] + ox) * lo, (v - it['v0'] + oy) * lo) for u, v in uv])
    build(glass, 'Canopy', parent='Body', smooth_angle=20)
    print('canopy uv scale %.3f uv/m, %d panes' % (lo, len(isl)))

    # ---- frame
    fr = MB(); TF = T_OLIVE2
    def member(a, b, n, w=0.045, to=0.014, ti=0.028, riv=True):
        P_sweep(fr, [a, b], [n, n], w, to, ti, 'Paint', TF)
        if riv:
            nn = Vector(n).normalized()
            P_rivets(fr, a + (b - a) * 0.06 + nn * to, b - (b - a) * 0.06 + nn * to, nn, 'Paint', T_RIV, step=0.09, r=0.005)
    def pane_n(a, b, c, s=0):
        n = (b - a).cross(c - a).normalized()
        if n.dot(a - V(0, a.y, 0.3)) < 0: n = -n
        return n
    for s in (-1, 1):
        yy = [y for y in ys]
        P_sweep(fr, [sill(y, s) for y in yy], [sn(y, s * THS) for y in yy], 0.075, 0.014, 0.03, 'Paint', TF)      # sill longeron
        for k in range(0, len(yy) - 1, 2):
            P_disc(fr, sill(yy[k], s) + sn(yy[k], s * THS) * 0.014, sn(yy[k], s * THS), 0.005, 'Paint', T_RIV)
        for k in range(len(CAN) - 1):          # shoulder longerons / windshield posts
            ya, yb = CAN[k][0], CAN[k + 1][0]
            a, b = shoulder(ya, s), shoulder(yb, s)
            ns = pane_n(sill(ya, s), sill(yb, s), b)
            n = (ns + (V(0, 0, 1) if k in (1, 3) else pane_n(shoulder(ya, -1), shoulder(ya, 1), shoulder(yb, 1)))).normalized()
            member(a, b, n, w=0.032 if k == 2 else 0.05)
        for y in (4.25, 3.15, 1.35):          # side posts
            a, b = sill(y, s), shoulder(y, s)
            n = V(s * (b.z - a.z), 0, -s * (b.x - a.x)).normalized()
            if n.x * s < 0: n = -n
            member(a, b, n, w=0.07 if y == 1.35 else 0.045)
    for k, y in enumerate((4.25, 3.15, 2.60, 1.35)):      # roof cross members
        a, b = shoulder(y, -1), shoulder(y, 1)
        if k == 0: n = (pane_n(shoulder(4.95, -1), shoulder(4.95, 1), b) + V(0, 0, 1)).normalized()
        elif k in (1, 2): n = (pane_n(shoulder(3.15, -1), shoulder(3.15, 1), shoulder(2.60, 1)) + V(0, 0, 1)).normalized()
        else: n = V(0, 0, 1)
        member(a, b, n, w=0.07 if y == 1.35 else 0.04)
    # nose-ring hoop at the windshield base
    ths_ = [rad(a) for a in np.arange(-75, 75.1, 3.75)]
    P_sweep(fr, [sp(4.945, t) for t in ths_], [sn(4.945, t) for t in ths_], 0.06, 0.014, 0.03, 'Paint', TF)
    # pilot roof centre rib (overhead, clear of the forward view)
    member(V(0, 2.60, 1.235), V(0, 1.35, 1.30), V(0, 0, 1), w=0.035)
    # crew door hinges along the right shoulder, handles + latches on the right side, emergency release left
    for (ya, yb) in ((4.1, 3.3), (2.45, 1.5)):
        for y in (ya, (ya + yb) / 2, yb):
            p = shoulder(y, 1)
            P_cyl(fr, p + V(0.012, -0.05, 0.012), p + V(0.012, 0.05, 0.012), 0.013, 'Metal', T_GUN, seg=8)
        ym = (ya + yb) / 2
        p = sill(ym, 1); n = sn(ym, THS)
        P_plate(fr, p + V(0, 0, 0.0), n, V(0, 1, 0), 0.03, 0.15, 0.03, 'Metal', T_GUN, 0.006)
        P_plate(fr, p + V(0, 0.16, 0), n, V(0, 1, 0), 0.04, 0.05, 0.02, 'Paint', T_YELD, 0.004)
    # windshield wipers (gunner + pilot), parked low
    for (a, b, n) in ((sp(4.95, rad(8)) , V(0.20, 4.42, 0.63), V(0, 0.65, 0.76)),):
        P_tube(fr, [a + n * 0.02, a + (b - a) * 0.5 + n * 0.03, b + n * 0.022], 0.006, 'Paint', T_BLACK, seg=5)
        P_plate(fr, b + n * 0.008, n, (b - a), 0.012, 0.3, 0.012, 'Paint', T_BLACK)
        P_cyl(fr, a, a + n * 0.03, 0.014, 'Metal', T_GUND, seg=8)
    build(fr, 'CanopyFrame', parent='Body')


def louvre(mb, c, n, up, w, h, count, depth=0.012, frame=True):
    """Recessed dark grille with slats; 'up' is the slat stacking direction."""
    R = basis(n, up); n = Vector(n).normalized()
    P_plate(mb, c, n, up, w, h, 0.004, 'Paint', T_BLACK)
    if frame:
        for sx, sy, fw, fh in ((0, h / 2, w + 0.02, 0.012), (0, -h / 2, w + 0.02, 0.012), (w / 2, 0, 0.012, h), (-w / 2, 0, 0.012, h)):
            P_box(mb, Vector(c) + R @ V(sx, sy, depth * 0.5), (fw, fh, depth), 'Paint', T_OLIVE2, rot=R)
    Rs = R @ Matrix.Rotation(rad(-35), 3, 'X')
    for k in range(count):
        yy = -h / 2 + (k + 0.5) * h / count
        P_box(mb, Vector(c) + R @ V(0, yy, depth * 0.5), (w - 0.006, h / count * 0.75, 0.003), 'Paint', T_OLIVE2, rot=Rs)


def handhold(mb, a, b, n, h=0.045, r=0.008, tint=T_GUN):
    a = Vector(a); b = Vector(b); n = Vector(n).normalized()
    P_tube(mb, [a, a + n * h * 0.8 + (b - a) * 0.04, a + n * h + (b - a) * 0.12, b + n * h - (b - a) * 0.12, b + n * h * 0.8 - (b - a) * 0.04, b], r, 'Metal', tint, seg=6)


def tiedown(mb, p, n, axis, R=0.028):
    P_torus(mb, Vector(p) + Vector(n).normalized() * R * 0.8, axis, R, 0.006, 'Metal', T_STEELD, seg=10, rseg=4)
    P_plate(mb, p, n, axis, 0.03, 0.05, 0.008, 'Metal', T_GUND, 0.002)


def blade_antenna(mb, p, n, fwd=(0, 1, 0), h=0.28, c=0.3, tint=T_DARK, sweep=0.12):
    p = Vector(p); n = Vector(n).normalized(); f = Vector(fwd).normalized(); side = n.cross(f).normalized()
    P_airfoil(mb, [(p + f * c * 0.5, -f, c, 0.09, side), (p + n * h + f * (c * 0.5 - sweep - c * 0.22), -f, c * 0.55, 0.09, side)], 'Paint', tint)
    P_plate(mb, p, n, f, 0.07, c * 1.15, 0.008, 'Paint', T_OLIVE2, 0.002)


def build_nose():
    mb = MB()
    TD = T_OLIVE2
    # ---- target sight turret on the blunt nose: collar, traversing drum, day / night apertures
    cc = V(0, 5.99, -0.39)
    P_revolve(mb, V(0, 5.84, -0.37), V(0, 1, 0), [(0, 0.29), (0.05, 0.29), (0.075, 0.25)], 'Paint', TD, seg=28, cap0=False)
    for k in range(12):
        a = k * pi / 6 + 0.26
        P_bolt(mb, V(0.268 * cos(a), 5.892, -0.37 + 0.268 * sin(a)), V(0, 1, 0), 0.011, 0.006, 'Metal', T_GUND)
    P_revolve(mb, cc - V(0.325, 0, 0), V(1, 0, 0), [(0, 0.11), (0.012, 0.185), (0.04, 0.205), (0.61, 0.205), (0.638, 0.185), (0.65, 0.11)], 'Paint', T_OLIVE, seg=32)
    for s in (-1, 1):
        P_revolve(mb, cc + V(s * 0.325, 0, 0), V(s, 0, 0), [(0, 0.1), (0.018, 0.09), (0.022, 0.05)], 'Paint', TD, seg=20, cap0=False)
        for k in range(8):
            a = k * pi / 4
            P_bolt(mb, cc + V(s * 0.322, 0.145 * cos(a), 0.145 * sin(a)), V(s, 0, 0), 0.009, 0.006, 'Metal', T_GUND)
    P_box(mb, cc + V(0, -0.02, 0), (0.035, 0.44, 0.44), 'Paint', TD, 0.008)                      # centre split fairing
    # night side (right): big aperture in a short barrel
    bc = cc + V(0.165, 0.06, 0.0)
    P_revolve(mb, bc, V(0, 1, 0), [(0, 0.15), (0.115, 0.15), (0.135, 0.132), (0.135, 0.118), (0.11, 0.116)], 'Paint', TD, seg=24, cap0=False, cap1=False)
    P_revolve(mb, bc, V(0, 1, 0), [(0.11, 0.117)], 'Lens', T_W, seg=24)
    # day side (left): faceted box with two flat windows + laser aperture
    dc = cc + V(-0.165, 0.085, 0.0)
    P_box(mb, dc, (0.275, 0.21, 0.33), 'Paint', TD, 0.03)
    for (dx, dz, w_, h_) in ((0.0, 0.065, 0.2, 0.13), (-0.045, -0.085, 0.1, 0.1)):
        P_plate(mb, dc + V(dx, 0.105, dz), V(0, 1, 0), V(0, 0, 1), w_ + 0.026, h_ + 0.026, 0.012, 'Paint', T_BLACK, 0.003)
        P_plate(mb, dc + V(dx, 0.117, dz), V(0, 1, 0), V(0, 0, 1), w_, h_, 0.002, 'Lens', T_W)
    P_revolve(mb, dc + V(0.06, 0.105, -0.085), V(0, 1, 0), [(0, 0.034), (0.014, 0.034), (0.014, 0.026)], 'Paint', T_BLACK, seg=12, cap0=False, cap1=False)
    P_revolve(mb, dc + V(0.06, 0.105, -0.085), V(0, 1, 0), [(0.012, 0.026)], 'Lens', T_W, seg=12)
    # ---- pilot night sensor above the nose: pedestal + boxy head with a single lens
    hz = sp(5.66, 0).z
    P_revolve(mb, V(0, 5.66, hz - 0.02), V(0, 0, 1), [(0, 0.13), (0.035, 0.12), (0.05, 0.085), (0.13, 0.085), (0.14, 0.1)], 'Paint', TD, seg=20, cap0=False)
    hc = V(0, 5.69, hz + 0.235)
    P_box(mb, hc, (0.24, 0.27, 0.2), 'Paint', T_OLIVE, 0.035)
    P_revolve(mb, hc + V(0, 0.11, 0.0), V(0, 1, 0), [(0, 0.092), (0.05, 0.092), (0.06, 0.08), (0.06, 0.07), (0.045, 0.068)], 'Paint', T_BLACK, seg=20, cap0=False, cap1=False)
    P_revolve(mb, hc + V(0, 0.11, 0.0), V(0, 1, 0), [(0.045, 0.069)], 'Lens', T_W, seg=20)
    for s in (-1, 1):
        P_revolve(mb, hc + V(s * 0.12, -0.02, 0), V(s, 0, 0), [(0, 0.06), (0.012, 0.055)], 'Paint', TD, seg=14, cap0=False)
        for k in range(4):
            a = k * pi / 2 + pi / 4
            P_bolt(mb, hc + V(s * 0.13, -0.02 + 0.04 * cos(a), 0.04 * sin(a)), V(s, 0, 0), 0.007, 0.004, 'Metal', T_GUND)
    # ---- air data: pitot probes on short pylons, static ports, OAT probe
    for s in (-1, 1):
        b0 = sp(5.42, s * rad(72)); n = sn(5.42, s * rad(72))
        P_airfoil(mb, [(b0 + V(0, 0.07, 0), V(0, -1, 0), 0.14, 0.2, V(0, 0, 1)), (b0 + n * 0.085 + V(0, 0.05, 0), V(0, -1, 0), 0.09, 0.2, V(0, 0, 1))], 'Paint', TD, n=5)
        P_tube(mb, [b0 + n * 0.085 + V(0, -0.03, 0), b0 + n * 0.085 + V(0, 0.2, 0), b0 + n * 0.085 + V(0, 0.34, 0)], 0.011, 'Metal', T_STEEL, seg=6, radii=[0.012, 0.012, 0.006])
        for dy in (0.0, 0.05):
            q = sp(5.1 + dy, s * rad(100)); P_disc(mb, q, sn(5.1 + dy, s * rad(100)), 0.012, 'Metal', T_STEELD, seg=8)
    q = sp(5.3, rad(-38)); n = sn(5.3, rad(-38))
    P_cyl(mb, q, q + n * 0.07, 0.008, 'Metal', T_STEEL, seg=6)
    # ---- radar / laser warning receivers (faceted blisters with dark apertures) at the nose quarters
    for s in (-1, 1):
        th = s * rad(98); q = sp(5.62, th); n = sn(5.62, th)
        P_plate(mb, q, n, V(0, 1, 0), 0.11, 0.16, 0.06, 'Paint', TD, 0.02)
        nf = (n + V(0, 0.9, 0)).normalized()
        P_disc(mb, q + n * 0.035 + V(0, 0.062, 0), nf, 0.03, 'Lens', T_W, seg=10, lift=0.012)
    # ---- lower wire cutter + landing/search light
    P_airfoil(mb, [(V(0, 5.3, -0.80), V(0, -1, 0), 0.26, 0.07, V(1, 0, 0)), (V(0, 5.46, -1.14), V(0, -1, 0), 0.07, 0.07, V(1, 0, 0))], 'Metal', T_GUN)
    P_box(mb, V(0, 5.19, -0.83), (0.07, 0.34, 0.03), 'Paint', TD, 0.008)
    lp = V(0.26, 5.05, -0.76); ld = V(0, 0.3, -1).normalized()
    P_revolve(mb, lp, ld, [(0, 0.085), (0.02, 0.085), (0.09, 0.08), (0.095, 0.066)], 'Paint', T_DARK, seg=16)
    P_revolve(mb, lp, ld, [(0.097, 0.066)], 'Lens', T_W, seg=16)
    P_torus(mb, lp + ld * 0.094, ld, 0.073, 0.007, 'Metal', T_GUND, seg=16, rseg=5)
    # ---- upper wire cutter on the canopy arch (overhead of the pilot's sight line)
    P_airfoil(mb, [(V(0, 2.66, 1.245), V(0, -1, 0), 0.26, 0.07, V(1, 0, 0)), (V(0, 2.86, 1.66), V(0, -1, 0), 0.07, 0.07, V(1, 0, 0))], 'Metal', T_GUN)
    P_box(mb, V(0, 2.5, 1.262), (0.06, 0.34, 0.02), 'Paint', TD, 0.006)
    # ---- nose deck: wash nozzles, hand-holds, tie-down under the chin
    for s in (-1, 1):
        q = sp(5.12, s * rad(20)); P_cyl(mb, q, q + sn(5.12, s * rad(20)) * 0.02, 0.012, 'Metal', T_GUND, seg=6)
        handhold(mb, sp(5.2, s * rad(52)), sp(5.45, s * rad(52)), sn(5.3, s * rad(52)))
    tiedown(mb, sp(5.6, pi), V(0, 0, -1), V(1, 0, 0))
    # ---- boarding aids on the right side: hand-holds under the sill, kick steps
    for y in (2.2, 3.55):
        th = rad(84)
        handhold(mb, sp(y - 0.13, th), sp(y + 0.13, th), sn(y, th))
    for y in (1.75, 3.0):
        th = rad(-84)
        handhold(mb, sp(y - 0.11, th), sp(y + 0.11, th), sn(y, th))
    build(mb, 'NoseDetail', parent='Body')
    empty('Light_Search', V(0.26, 5.08, -0.83), 'Body')
    # ---- detachable nose avionics doors (bulged) with the bay underneath
    bay = MB(); door = MB()
    us = list(np.linspace(5.02, 5.60, 7)); vs = list(np.linspace(58, 112, 8))
    P_patch(bay, hfn, us[1:-1], vs[1:-1], 0.003, 'Paint', T_BLACK)
    for (y, t, sy, sz) in ((5.15, 70, 0.13, 0.16), (5.33, 74, 0.16, 0.2), (5.33, 100, 0.2, 0.14), (5.5, 84, 0.1, 0.24), (5.14, 98, 0.12, 0.16)):
        p, n = hfn(y, t)
        P_plate(bay, p, n, V(0, 1, 0), sz, sy, 0.02, 'Metal', T_GUN if (int(y * 100) % 2) else T_STEELD, 0.005)
    P_tube(bay, [hfn(y, 87)[0] + hfn(y, 87)[1] * 0.012 for y in (5.08, 5.2, 5.4, 5.55)], 0.007, 'Paint', T_YELD, seg=5)
    P_patch(door, hfn, us, vs, 0.028, 'Hull', T_P9, skirt=0.0, uvfn=huv, skirt_tint=T_P5)
    for y in (5.12, 5.31, 5.5):
        for t in (58, 112):
            p, n = hfn(y, t)
            P_plate(door, p + n * 0.012, n, V(0, 1, 0), 0.05, 0.03, 0.022, 'Metal', T_GUND, 0.004)
    for y in us[1:-1]:
        for t in (62, 108):
            p, n = hfn(y, t); P_disc(door, p + n * 0.028, n, 0.006, 'Paint', T_RIV)
    st = MB(); st.merge(bay); st.merge(bay.mirrored())
    build(st, 'NoseBay', parent='Body')
    build(door, 'Part_NoseHatchR', parent='Body')
    build(door.mirrored(), 'Part_NoseHatchL', parent='Body')


def build_turret():
    piv = V(0, 4.35, -0.86)
    mb = MB()   # static mount on the belly
    P_revolve(mb, piv + V(0, 0, 0.08), V(0, 0, -1), [(0, 0.40), (0.07, 0.38), (0.10, 0.33), (0.115, 0.31)], 'Paint', T_OLIVE2, seg=28, cap0=False)
    for k in range(14):
        a = k * 2 * pi / 14
        P_bolt(mb, piv + V(0.355 * cos(a), 0.355 * sin(a), 0.0), V(0, 0, -1), 0.011, 0.012, 'Metal', T_GUND)
    # flexible ammunition chute from the fuselage magazine to the gun (static section)
    pts = bezier(V(0.30, 3.45, -0.80), V(0.36, 3.75, -1.0), V(0.34, 4.05, -1.04), V(0.27, 4.26, -1.0), 12)
    P_sweep(mb, pts, [V(0.35, 0, -1)] * len(pts), 0.12, 0.03, 0.03, 'Metal', T_GUND)
    for k in range(1, len(pts) - 1):
        t = (pts[k + 1] - pts[k - 1]).normalized()
        P_box(mb, pts[k], (0.134, 0.022, 0.074), 'Metal', T_GUN, rot=basis(V(0.35, 0, -1), t))
    P_box(mb, V(0.30, 3.42, -0.82), (0.2, 0.16, 0.1), 'Paint', T_OLIVE2, 0.02)
    # spent-case ejection chute + turret fairing skirt
    P_box(mb, V(-0.2, 4.0, -0.9), (0.12, 0.3, 0.07), 'Paint', T_OLIVE2, 0.015)
    build(mb, 'TurretMount', parent='Body')

    ty = MB()   # yawing part: turntable, cradle fork, elevation trunnions
    P_revolve(ty, piv + V(0, 0, -0.035), V(0, 0, -1), [(0, 0.3), (0.045, 0.3), (0.06, 0.27), (0.10, 0.2), (0.115, 0.12)], 'Metal', T_GUN, seg=28, cap0=False)
    for s in (-1, 1):
        rings = [chring(piv.y + yy, s * 0.135 - 0.022, s * 0.135 + 0.022, zb, -0.93, 0.008) for (yy, zb) in ((-0.24, -1.06), (-0.12, -1.23), (0.12, -1.23), (0.22, -1.12), (0.26, -1.0))]
        P_loft(ty, rings, 'Metal', T_GUN, cap0=True, cap1=True)
        P_cyl(ty, piv + V(s * 0.11, 0, -0.29), piv + V(s * 0.185, 0, -0.29), 0.055, 'Metal', T_STEELD, seg=14)
        P_cyl(ty, piv + V(s * 0.185, 0, -0.29), piv + V(s * 0.195, 0, -0.29), 0.03, 'Metal', T_STEEL, seg=10)
        for k in range(5):
            a = k * 2 * pi / 5
            P_bolt(ty, piv + V(s * 0.158, 0.04 * cos(a), -0.29 + 0.04 * sin(a)), V(s, 0, 0), 0.007, 0.006, 'Metal', T_STEEL)
    P_box(ty, piv + V(0, -0.2, -0.1), (0.3, 0.08, 0.1), 'Metal', T_GUN, 0.01)                  # fork bridge
    P_cyl(ty, piv + V(0.09, -0.2, -0.13), piv + V(0.09, -0.06, -0.27), 0.022, 'Metal', T_STEEL, seg=8)   # elevation actuator
    P_cyl(ty, piv + V(0.09, -0.21, -0.12), piv + V(0.09, -0.13, -0.2), 0.03, 'Metal', T_GUND, seg=8)
    build(ty, 'TurretYaw', origin=piv, parent='Body')

    gp = piv + V(0, 0, -0.29)
    g = MB()
    P_box(g, gp + V(0, -0.04, 0), (0.19, 0.6, 0.165), 'Metal', T_GUN, 0.016)                 # receiver
    P_box(g, gp + V(0, -0.04, 0.086), (0.15, 0.5, 0.012), 'Metal', T_GUND, 0.003)            # top cover
    for yy in (-0.24, -0.04, 0.16):
        for s in (-1, 1):
            P_bolt(g, gp + V(s * 0.05, yy, 0.092), V(0, 0, 1), 0.008, 0.005, 'Metal', T_STEELD)
    P_box(g, gp + V(0, -0.38, 0.01), (0.22, 0.14, 0.19), 'Metal', T_GUND, 0.02)              # drive motor housing
    P_cyl(g, gp + V(-0.06, -0.44, 0.0), gp + V(-0.06, -0.54, 0.0), 0.05, 'Metal', T_GUN, seg=12)
    P_box(g, gp + V(0.0, -0.24, 0.1), (0.17, 0.17, 0.035), 'Metal', T_GUND, 0.008)           # feed box
    P_revolve(g, gp + V(0, 0.26, 0), V(0, 1, 0),
              [(0, 0.075), (0.06, 0.075), (0.08, 0.06), (0.3, 0.06), (0.32, 0.048), (0.5, 0.046), (0.52, 0.034), (1.0, 0.03), (1.02, 0.036), (1.05, 0.036), (1.06, 0.05), (1.24, 0.052), (1.27, 0.04), (1.27, 0.022), (1.15, 0.02)],
              'Metal', T_GUN, seg=16, cap1=False)
    for k in range(8):   # barrel cooling flutes
        a = k * pi / 4
        P_box(g, gp + V(0.058 * cos(a), 0.45, 0.058 * sin(a)), (0.012, 0.2, 0.006), 'Metal', T_GUND, rot=Matrix.Rotation(-a, 3, 'Y'))
    for k in range(6):   # flash-suppressor slots (dark)
        a = k * pi / 3 + 0.3
        P_box(g, gp + V(0.0515 * cos(a), 1.41, 0.0515 * sin(a)), (0.004, 0.13, 0.018), 'Paint', T_BLACK, rot=Matrix.Rotation(-a, 3, 'Y'))
    for s in (-1, 1):    # recoil dampers either side of the barrel
        P_cyl(g, gp + V(s * 0.062, 0.26, -0.05), gp + V(s * 0.055, 0.5, -0.045), 0.02, 'Metal', T_STEELD, seg=8)
        P_cyl(g, gp + V(s * 0.055, 0.5, -0.045), gp + V(s * 0.05, 0.66, -0.04), 0.012, 'Metal', T_CHROME, seg=8)
    P_box(g, gp + V(0, 0.68, -0.02), (0.14, 0.03, 0.1), 'Metal', T_GUND, 0.006)               # barrel support yoke
    build(g, 'GunPitch', origin=gp, parent='TurretYaw')
    empty('Muzzle', gp + V(0, 1.53, 0), 'GunPitch')


def nacelle_side():
    """Right-hand engine nacelle; returns (static MB, cowl MB, exhaust point)."""
    mb = MB(); cowl = MB()
    cx, cz = 0.88, 0.52
    ka = np.array([(-2.3, 0.37, 0.33, 6.0), (-1.7, 0.37, 0.35, 5.5), (-1.2, 0.36, 0.375, 4.6), (0.6, 0.36, 0.375, 4.4),
                   (0.98, 0.345, 0.36, 4.2), (1.10, 0.305, 0.315, 3.6)])
    ys = [1.10, 1.04, 0.98, 0.8, 0.6, 0.45, 0.2, -0.1, -0.4, -0.7, -0.9, -1.1, -1.3, -1.5, -1.7, -2.0, -2.3]
    NN = 32
    def pt(y, j, off=0.0):
        a = float(np.interp(y, ka[:, 0], ka[:, 1])) + off; b = float(np.interp(y, ka[:, 0], ka[:, 2])) + off
        n = float(np.interp(y, ka[:, 0], ka[:, 3]))
        th = 2 * pi * j / NN
        s, c = sin(th), cos(th)
        return V(cx + a * math.copysign(abs(s) ** (2 / n), s), y, cz + b * math.copysign(abs(c) ** (2 / n), c))
    def nfn(y, j):
        p = pt(y, j); d1 = pt(y, j + 0.05) - pt(y, j - 0.05); d2 = pt(y + 0.02, j) - pt(y - 0.02, j)
        n = d1.cross(d2).normalized()
        if n.dot(p - V(cx, y, cz)) < 0: n = -n
        return p, n
    J0, J1 = 3, 13
    def is_cowl(i, j):
        return 0.45 >= ys[i] and ys[i + 1] >= -1.1 - 1e-6 and J0 <= j < J1
    def soot(y):
        t = min(1.0, max(0.0, (-1.5 - y) / 1.0)); c = 1.0 - 0.5 * t
        return (c, c * 0.985, c * 0.97)
    # oblique exhaust face
    nc = V(0.42, -0.82, 0.38).normalized(); Pc = V(cx + 0.10, -2.70, cz + 0.10)
    def cut(p):
        return V(p.x, Pc.y - (nc.x * (p.x - Pc.x) + nc.z * (p.z - Pc.z)) / nc.y, p.z)
    rings = [[pt(y, j) for j in range(NN)] for y in ys]
    rings.append([cut(p) for p in rings[-1]])
    yy_ = ys + [-2.7]
    P_loft(mb, rings, 'HullB', T_W, matfn=lambda i, j: None if (i < len(ys) - 1 and is_cowl(i, j)) else 'HullB',
           tintfn=lambda i, j: soot(yy_[i]))
    R1 = rings[-1]
    R2 = [Pc + (p - Pc) * 0.86 for p in R1]
    R3 = [Pc + (p - Pc) * 0.80 - nc * 0.035 for p in R1]
    R4 = [Pc + (p - Pc) * 0.74 - nc * 0.34 for p in R1]
    P_loft(mb, [R1, R2], 'Paint', T_SOOT, ref=Pc - nc * 2.0)
    P_loft(mb, [R2, R3, R4], 'Paint', T_SOOT, inward=True, ref=Pc - nc * 0.15, tintfn=lambda i, j: T_SOOT if i == 0 else T_BLACK)
    P_poly(mb, R4, 'Paint', T_BLACK, nrm=nc)
    eu = nc.cross(V(0, 0, 1)).normalized(); ev = eu.cross(nc).normalized()
    if eu.x < 0: eu = -eu
    Rv = Matrix((eu, ev, nc)).transposed()
    for u in (-0.105, 0.105):       # nozzle dividers -> three rectangular outlets
        P_box(mb, Pc + eu * u - nc * 0.19, (0.022, 0.5, 0.3), 'Paint', T_SOOT, rot=Rv)
    for u in (-0.21, 0.0, 0.21):    # finned mixer cores deep inside
        P_box(mb, Pc + eu * u - nc * 0.26, (0.14, 0.44, 0.04), 'Metal', T_GUND, 0.01, rot=Rv)
    for k in range(18):             # rim fasteners
        p = R1[(k * NN) // 18]; q = Pc + (p - Pc) * 0.93
        P_disc(mb, q, nc, 0.007, 'Metal', T_GUND)
    # suppressor stiffening strakes + heat-shield band
    for k, jj in enumerate((5.6, 8.0, 10.4)):
        a = pt(-1.45, jj, 0.0); b = pt(-2.25, jj, 0.0)
        P_box(mb, (a + b) / 2 + V(0.008, 0, 0), (0.02, 0.82, 0.022), 'HullB', T_P7, 0.004)
    for jj in (0.0, 2.0, -2.0):
        a = pt(-1.45, jj); b = pt(-2.2, jj)
        P_box(mb, (a + b) / 2 + V(0, 0, 0.006), (0.022, 0.76, 0.018), 'HullB', T_P7, 0.004)
    for y in (-1.38, 0.52):          # frame bands + fastener rings
        P_patch(mb, lambda u, v: nfn(u, v), [y - 0.03, y + 0.03], list(np.arange(-7, 17.01, 1.0)), 0.006, 'HullB', T_P8)
        for j in np.arange(-6.5, 17, 1.0):
            p, n = nfn(y, j); P_disc(mb, p + n * 0.006, n, 0.0055, 'Paint', T_RIV)
    # suppressor cooling-air louvres (top) and outer access door
    p, n = nfn(-1.75, 0.0)
    louvre(mb, p + n * 0.002, n, V(0, 1, 0), 0.34, 0.32, 7)
    P_patch(mb, lambda u, v: nfn(u, v), list(np.linspace(-2.1, -1.55, 4)), list(np.linspace(6.3, 9.7, 5)), 0.007, 'HullB', T_P7, skirt=0.0, skirt_tint=T_P5)
    for y in (-2.06, -1.59):
        for jj in (6.5, 8.0, 9.5):
            p, n = nfn(y, jj); P_disc(mb, p + n * 0.007, n, 0.007, 'Paint', T_RIV)
    # top access panel (raised) with quick-release fasteners
    us = list(np.linspace(-0.95, 0.3, 6)); vs = list(np.linspace(-2.4, 2.4, 7))
    P_patch(mb, lambda u, v: nfn(u, v), us, vs, 0.007, 'HullB', T_P9, skirt=0.0, skirt_tint=T_P5)
    for y in us:
        for jj in (-2.2, 2.2):
            p, n = nfn(y, jj); P_disc(mb, p + n * 0.007, n, 0.007, 'Paint', T_RIV)
    for jj in (-1.1, 0, 1.1):
        for y in (us[0] + 0.03, us[-1] - 0.03):
            p, n = nfn(y, jj); P_disc(mb, p + n * 0.007, n, 0.007, 'Paint', T_RIV)
    # ---- cowl door (detachable) with hinges, latches, louvres
    rings2 = [[pt(y, j, 0.007) for j in range(NN)] for y in ys]
    P_loft(cowl, rings2, 'HullB', T_P9, matfn=lambda i, j: 'HullB' if is_cowl(i, j) else None)
    ed = [(pt(y, J0, 0.007), pt(y, J0, 0.0)) for y in ys if -1.1 - 1e-6 <= y <= 0.45 + 1e-6]
    ed2 = [(pt(y, J1, 0.007), pt(y, J1, 0.0)) for y in ys if -1.1 - 1e-6 <= y <= 0.45 + 1e-6]
    top = [a for a, b in ed] + [pt(-1.1, j, 0.007) for j in range(J0 + 1, J1)] + [a for a, b in ed2][::-1] + [pt(0.45, j, 0.007) for j in range(J1 - 1, J0, -1)]
    bot = [b for a, b in ed] + [pt(-1.1, j, 0.0) for j in range(J0 + 1, J1)] + [b for a, b in ed2][::-1] + [pt(0.45, j, 0.0) for j in range(J1 - 1, J0, -1)]
    P_loft(cowl, [top, bot], 'HullB', T_P5, closed=True)
    for y in (0.25, -0.33, -0.9):
        p, n = nfn(y, J0 + 0.25); P_plate(cowl, p + n * 0.007, n, V(0, 1, 0), 0.03, 0.1, 0.014, 'Metal', T_GUND, 0.004)       # hinges (top)
        P_cyl(cowl, p + n * 0.02 + V(0, -0.05, 0), p + n * 0.02 + V(0, 0.05, 0), 0.008, 'Metal', T_GUN, seg=6)
        p, n = nfn(y, J1 - 0.3); P_plate(cowl, p + n * 0.007, n, V(0, 1, 0), 0.05, 0.035, 0.012, 'Metal', T_GUN, 0.003)        # latches (bottom)
    p, n = nfn(-0.62, 7.3)
    louvre(cowl, p + n * 0.008, n, V(0, 1, 0), 0.26, 0.4, 8)
    p, n = nfn(0.12, 9.0)
    P_plate(cowl, p + n * 0.007, n, V(0, 1, 0), 0.16, 0.24, 0.005, 'HullB', T_P7, 0.001)                                          # service door
    for dy in (-0.1, 0.1):
        for dj in (-0.55, 0.55):
            q, n2 = nfn(0.12 + dy, 9.0 + dj); P_disc(cowl, q + n2 * 0.012, n2, 0.006, 'Paint', T_RIV)
    for y in np.arange(-1.0, 0.41, 0.14):
        for jj in (J0 + 0.25, J1 - 0.25):
            q, n2 = nfn(y, jj); P_disc(cowl, q + n2 * 0.007, n2, 0.0055, 'Paint', T_RIV)
    # ---- engine bay under the cowl (dark) + engine core
    rings3 = [[pt(y, j, -0.07) for j in range(NN)] for y in ys]
    P_loft(mb, rings3, 'Paint', T_BLACK, matfn=lambda i, j: 'Paint' if is_cowl(i, j) else None)
    i0 = ys.index(0.45); i1 = ys.index(-1.1)
    for i in (i0, i1):   # bay end walls
        for j in range(J0, J1):
            dquad(mb, [pt(ys[i], j), pt(ys[i], j, -0.07), pt(ys[i], j + 1, -0.07), pt(ys[i], j + 1)], 'Paint', T_BLACK)
    for j in (J0, J1):   # bay side walls
        for i in range(i0, i1):
            dquad(mb, [pt(ys[i], j), pt(ys[i], j, -0.07), pt(ys[i + 1], j, -0.07), pt(ys[i + 1], j)], 'Paint', T_BLACK)
    ec = V(cx + 0.05, 0.42, cz)
    P_revolve(mb, ec, V(0, -1, 0), [(0, 0.19), (0.25, 0.235), (0.45, 0.235), (0.5, 0.19), (0.85, 0.19), (0.9, 0.245), (1.25, 0.245), (1.5, 0.21)], 'Metal', T_GUN, seg=18, cap0=False, cap1=False)
    for k in range(5):
        P_torus(mb, ec + V(0, -0.1 - k * 0.3, 0), V(0, 1, 0), 0.245 if k in (0, 3, 4) else 0.2, 0.014, 'Metal', T_STEELD, seg=18, rseg=5)
    P_tube(mb, [ec + V(0.24, -0.02, 0.1), ec + V(0.255, -0.5, 0.13), ec + V(0.25, -1.0, 0.1), ec + V(0.24, -1.4, 0.12)], 0.018, 'Metal', T_BURNT, seg=6)
    P_tube(mb, [ec + V(0.25, -0.1, -0.08), ec + V(0.26, -0.6, -0.12), ec + V(0.255, -1.2, -0.08)], 0.012, 'Metal', T_STEEL, seg=6)
    P_box(mb, ec + V(0.2, -0.62, -0.02), (0.1, 0.2, 0.16), 'Metal', T_GUND, 0.015)           # accessory gearbox
    P_cyl(mb, ec + V(0.22, -0.3, 0.0), ec + V(0.27, -0.3, 0.0), 0.05, 'Metal', T_STEELD, seg=10)
    # ---- intake: lip, duct, particle-separator bullet, struts
    ic = V(cx, 1.125, cz)
    P_loft(mb, [[ic + V(0.285 * sin(2 * pi * j / NN), 0, 0.285 * cos(2 * pi * j / NN)) for j in range(NN)], [pt(1.10, j) for j in range(NN)]], 'HullB', T_W, ref=V(cx, 0.5, cz))
    P_torus(mb, ic, V(0, 1, 0), 0.262, 0.032, 'Metal', T_GUN, seg=32, rseg=8)
    P_revolve(mb, ic, V(0, -1, 0), [(0, 0.26), (0.16, 0.225), (0.16, 0.0005)], 'Paint', T_BLACK, seg=32, cap0=False, cap1=False, flip=True)
    P_revolve(mb, ic + V(0, -0.2, 0), V(0, 1, 0), [(0, 0.12), (0.12, 0.115), (0.24, 0.07), (0.3, 0.02), (0.31, 0.0005)], 'Metal', T_GUND, seg=18, cap0=False, cap1=False)
    for k in range(7):
        a = k * 2 * pi / 7
        P_box(mb, ic + V(0.17 * cos(a), -0.1, 0.17 * sin(a)), (0.13, 0.05, 0.01), 'Metal', T_GUN, rot=Matrix.Rotation(-a, 3, 'Y'))
    for k in range(16):
        a = k * 2 * pi / 16
        p, n_ = nfn(0.93, k * 2 + 1); P_disc(mb, p, n_, 0.006, 'Paint', T_RIV)
    # ---- nose-gearbox fairing under the intake, drains, inboard pylon to the fuselage
    P_sphere(mb, V(cx - 0.1, 0.62, cz - 0.31), (0.17, 0.36, 0.13), 'HullB', T_W, seg=16, rings=8)
    for y in (0.1, -0.8):
        p = pt(y, 16.5); P_cyl(mb, p, p + V(0, -0.03, -0.07), 0.01, 'Metal', T_STEELD, seg=6)
    rings = [chring(y, 0.40, 0.72, 0.36 if abs(y) < 1.5 else 0.42, 0.84 if abs(y) < 1.5 else 0.74, 0.06) for y in (0.85, 0.7, -1.4, -1.75)]
    rings[0] = [V(p.x, 0.85, 0.6 + (p.z - 0.6) * 0.6) for p in rings[0]]
    P_loft(mb, rings, 'HullB', T_W, cap0=True, cap1=True)
    return mb, cowl, Pc + nc * 0.08


def build_nacelles():
    mb, cowl, ex = nacelle_side()
    st = MB(); st.merge(mb); st.merge(mb.mirrored())
    build(st, 'Nacelles', parent='Body')
    build(cowl, 'Part_CowlR', parent='Body')
    build(cowl.mirrored(), 'Part_CowlL', parent='Body')
    empty('Exhaust_R', ex, 'Body'); empty('Exhaust_L', V(-ex.x, ex.y, ex.z), 'Body')


def build_doghouse():
    mb = MB()
    DZ = 1.385
    # ---- mast base fairing, static mast, stationary swashplate + servo actuators
    P_revolve(mb, V(0, 0, 1.36), V(0, 0, 1), [(0, 0.43), (0.045, 0.42), (0.075, 0.36), (0.19, 0.2), (0.21, 0.15)], 'HullB', T_W, seg=24, cap0=False)
    for k in range(12):
        a = k * pi / 6
        P_bolt(mb, V(0.395 * cos(a), 0.395 * sin(a), 1.41), V(0, 0, 1), 0.011, 0.008, 'Metal', T_GUND)
    P_cyl(mb, V(0, 0, 1.5), V(0, 0, ROTOR_Z - 0.2), 0.085, 'Paint', T_HUB2, seg=16)
    P_revolve(mb, V(0, 0, 1.655), V(0, 0, 1), [(0, 0.12), (0.012, 0.27), (0.05, 0.27), (0.062, 0.12)], 'Paint', T_HUB1, seg=24)
    for k in range(3):
        a = k * 2 * pi / 3 + pi / 2
        e = V(cos(a), sin(a), 0)
        P_box(mb, e * 0.29 + V(0, 0, 1.685), (0.07, 0.05, 0.05), 'Paint', T_HUB1, 0.008, rot=Matrix.Rotation(a, 3, 'Z'))
        P_cyl(mb, e * 0.30 + V(0, 0, 1.42), e * 0.30 + V(0, 0, 1.57), 0.04, 'Paint', T_HUB2, seg=10)
        P_cyl(mb, e * 0.30 + V(0, 0, 1.57), e * 0.30 + V(0, 0, 1.68), 0.02, 'Metal', T_CHROME, seg=8)
        P_sphere(mb, e * 0.30 + V(0, 0, 1.685), 0.028, 'Metal', T_STEELD, seg=8, rings=5)
        P_tube(mb, [e * 0.30 + V(0, 0, 1.5) + V(-e.y, e.x, 0) * 0.04, e * 0.34 + V(-e.y, e.x, 0) * 0.07 + V(0, 0, 1.44), e * 0.36 + V(-e.y, e.x, 0) * 0.07 + V(0, 0, 1.39)], 0.008, 'Paint', T_BLACK, seg=5)
    # anti-rotation scissors (static)
    P_tube(mb, [V(-0.09, -0.2, 1.52), V(-0.1, -0.33, 1.6), V(-0.1, -0.27, 1.685)], 0.014, 'Metal', T_STEELD, seg=6)
    # ---- deck equipment
    # GPS / satcom dome and blade antenna ahead of the mast
    P_revolve(mb, V(0, 0.98, DZ - 0.01), V(0, 0, 1), [(0, 0.12), (0.02, 0.118), (0.045, 0.09), (0.058, 0.04)], 'Paint', T_OLIVE2, seg=16, cap0=False)
    blade_antenna(mb, V(0, 0.62, DZ - 0.005), V(0, 0, 1), h=0.2, c=0.2)
    for s in (-1, 1):
        P_plate(mb, V(s * 0.27, 0.85, DZ - 0.022), V(0, 0, 1), V(0, 1, 0), 0.15, 0.7, 0.006, 'Paint', T_BLACK)       # anti-slip walkway
        handhold(mb, V(s * 0.38, 1.15, DZ - 0.03), V(s * 0.38, 0.9, DZ - 0.03), V(s * 0.5, 0, 1))
        for y in (1.2, -0.85):
            tiedown(mb, V(s * 0.33, y, DZ - 0.022), V(0, 0, 1), V(1, 0, 0), 0.024)
    # oil-cooler exhaust grille behind the mast
    louvre(mb, V(0, -0.67, DZ - 0.004), V(0, 0, 1), V(0, 1, 0), 0.5, 0.32, 8)
    # IR jammer on the aft slope: pedestal + faceted lantern
    jz = spine_xz(-1.28)[1] + 0.02
    P_revolve(mb, V(0, -1.28, jz - 0.02), V(0, 0, 1), [(0, 0.1), (0.03, 0.09), (0.05, 0.06), (0.13, 0.06)], 'Paint', T_OLIVE2, seg=12, cap0=False)
    P_revolve(mb, V(0, -1.28, jz + 0.11), V(0, 0, 1), [(0, 0.085), (0.015, 0.105), (0.2, 0.105), (0.215, 0.085)], 'Lens', T_W, seg=8)
    for k in range(8):
        a = k * pi / 4 + pi / 8
        P_box(mb, V(0.106 * cos(a), -1.28 + 0.106 * sin(a), jz + 0.2175), (0.012, 0.012, 0.215), 'Paint', T_OLIVE2, rot=Matrix.Rotation(a, 3, 'Z'))
    P_revolve(mb, V(0, -1.28, jz + 0.325), V(0, 0, 1), [(0, 0.11), (0.02, 0.1), (0.03, 0.05)], 'Paint', T_OLIVE2, seg=12, cap0=False)
    # anti-collision beacon
    bz = spine_xz(-1.75)[1] + 0.005
    P_revolve(mb, V(0, -1.75, bz), V(0, 0, 1), [(0, 0.06), (0.02, 0.055), (0.03, 0.045)], 'Paint', T_DARK, seg=12, cap0=False)
    P_sphere(mb, V(0, -1.75, bz + 0.045), (0.042, 0.042, 0.04), 'Paint', T_RED, seg=12, rings=6)
    blade_antenna(mb, V(0, -2.55, spine_xz(-2.55)[1] + 0.01), V(0, 0.42, 1), h=0.3, c=0.32)
    # ---- spine sides: louvres, hand-holds, steps, APU exhaust, transmission cowls
    for s in (-1, 1):
        for (y, t, w_, h_, cnt) in ((0.98, 0.72, 0.3, 0.22, 6), (-1.25, 0.7, 0.26, 0.2, 5)):
            louvre(mb, spine_side(y, t, s), spine_n(y, s), V(0, 0, 1), w_, h_, cnt)
        handhold(mb, spine_side(0.55, 0.9, s), spine_side(0.25, 0.9, s), spine_n(0.4, s))
        handhold(mb, spine_side(-1.05, 0.88, s), spine_side(-1.4, 0.88, s), spine_n(-1.2, s))
        P_plate(mb, spine_side(1.12, 0.38, s), spine_n(1.12, s), V(0, 1, 0), 0.16, 0.2, 0.01, 'Paint', T_BLACK, 0.002)         # kick-in step
        for y in np.arange(-2.9, 1.3, 0.3):       # shoulder fastener line
            P_disc(mb, spine_side(y, 0.97, s), spine_n(y, s), 0.006, 'Paint', T_RIV)
    p = spine_side(-1.95, 0.55, 1); n = spine_n(-1.95, 1); d = (n + V(0, -0.8, 0.3)).normalized()
    P_revolve(mb, p - d * 0.03, d, [(0, 0.075), (0.11, 0.07), (0.115, 0.058), (0.02, 0.055)], 'Metal', T_BURNT, seg=14, cap0=False, cap1=False)
    P_disc(mb, p - d * 0.01, d, 0.056, 'Paint', T_BLACK, seg=14, lift=0.0)
    build(mb, 'TopDetail', parent='Body')
    empty('Light_Beacon', V(0, -1.75, bz + 0.045), 'Body')
    # ---- transmission cowls (detachable) + gearbox bay behind them
    bay = MB(); door = MB()
    def sfn(y, t): return spine_side(y, t, 1), spine_n(y, 1)
    us = list(np.linspace(-0.72, 0.6, 7)); vs = list(np.linspace(0.56, 0.93, 4))
    P_patch(bay, sfn, us[1:-1] if False else list(np.linspace(-0.69, 0.57, 5)), [0.58, 0.91], 0.003, 'Paint', T_BLACK)
    p, n = sfn(-0.05, 0.75)
    P_revolve(bay, p + n * 0.002, n, [(0, 0.15), (0.016, 0.14), (0.02, 0.08)], 'Metal', T_GUN, seg=16, cap0=False)
    for k in range(8):
        a = k * pi / 4
        q = p + basis(n) @ V(0.115 * cos(a), 0.115 * sin(a), 0.016); P_bolt(bay, q, n, 0.009, 0.005, 'Metal', T_STEEL)
    for (y, t, w_, h_) in ((0.36, 0.8, 0.2, 0.14), (-0.5, 0.7, 0.16, 0.2)):
        q, n2 = sfn(y, t); P_plate(bay, q, n2, V(0, 0, 1), w_, h_, 0.02, 'Metal', T_GUND, 0.005)
    P_tube(bay, [sfn(y, t)[0] + n * 0.012 for (y, t) in ((0.52, 0.62), (0.2, 0.6), (-0.3, 0.63), (-0.62, 0.6))], 0.008, 'Metal', T_STEEL, seg=5)
    P_tube(bay, [sfn(y, t)[0] + n * 0.012 for (y, t) in ((0.5, 0.88), (0.1, 0.9), (-0.6, 0.86))], 0.007, 'Paint', T_YELD, seg=5)
    P_patch(door, sfn, us, vs, 0.026, 'HullB', T_P9, skirt=0.0, skirt_tint=T_P5)
    for y in us:
        for t in (0.585, 0.905):
            q, n2 = sfn(y, t); P_disc(door, q + n2 * 0.026, n2, 0.0065, 'Paint', T_RIV)
    for y in (-0.45, 0.33):
        q, n2 = sfn(y, 0.56); P_plate(door, q + n2 * 0.02, n2, V(0, 0, 1), 0.1, 0.035, 0.012, 'Metal', T_GUND, 0.003)
    q, n2 = sfn(-0.05, 0.74)
    louvre(door, q + n2 * 0.027, n2, V(0, 0, 1), 0.34, 0.14, 4)
    st = MB(); st.merge(bay); st.merge(bay.mirrored())
    build(st, 'TransBay', parent='Body')
    build(door, 'Part_TransCowlR', parent='Body')
    build(door.mirrored(), 'Part_TransCowlL', parent='Body')


def stencil(mb, text, size, pos, n, up, tint=T_STEN, lift=0.003):
    n = Vector(n).normalized()
    M = Matrix.Translation(Vector(pos) + n * lift) @ basis(n, up).to_4x4()
    P_text(mb, text, size, M, 'Paint', tint)


def build_cheeks():
    X0 = 0.45
    def ck(y, x1, z0, z1, c):
        return [V(X0, y, z1 + 0.06), V(x1 - c, y, z1), V(x1, y, z1 - c), V(x1, y, z0 + c), V(x1 - c * 1.7, y, z0), V(X0, y, z0)]
    XO = 0.87; ZB, ZT = -0.80, -0.20
    def side():
        mb = MB(); door = MB()
        secs = [(4.66, 0.52, -0.60, -0.40, 0.02), (4.5, 0.68, -0.71, -0.29, 0.035), (4.25, 0.81, -0.775, -0.225, 0.045), (3.95, XO, ZB, ZT, 0.05),
                (2.0, XO, ZB, ZT, 0.05), (-0.25, XO, ZB, ZT, 0.05), (-0.75, 0.80, -0.77, -0.24, 0.045), (-1.1, 0.66, -0.69, -0.32, 0.035), (-1.32, 0.5, -0.6, -0.42, 0.02)]
        P_loft(mb, [ck(*s_) for s_ in secs], 'HullB', T_W, cap0=True, cap1=True)
        nx = V(1, 0, 0); upz = V(0, 0, 1)
        fz = (ZB + ZT) / 2
        # avionics bay under the detachable door
        P_plate(mb, V(XO, 2.6, fz), nx, upz, 1.04, 0.44, 0.003, 'Paint', T_BLACK)
        for k, (yy, zz, sy, sz) in enumerate(((2.22, -0.42, 0.22, 0.2), (2.52, -0.44, 0.26, 0.24), (2.88, -0.4, 0.3, 0.17), (2.9, -0.61, 0.3, 0.14), (2.25, -0.62, 0.2, 0.1), (2.55, -0.64, 0.24, 0.08))):
            P_plate(mb, V(XO + 0.003, yy, zz), nx, upz, sy, sz, 0.012, 'Metal', T_GUN if k % 2 else T_STEELD, 0.004)
            P_plate(mb, V(XO + 0.015, yy - sy * 0.3, zz), nx, upz, 0.02, sz * 0.5, 0.004, 'Paint', T_BLACK)
        P_tube(mb, [V(XO + 0.012, 2.12, -0.53), V(XO + 0.012, 2.5, -0.535), V(XO + 0.012, 3.06, -0.52)], 0.007, 'Paint', T_YELD, seg=5)
        P_tube(mb, [V(XO + 0.012, 2.12, -0.3), V(XO + 0.012, 2.7, -0.295), V(XO + 0.012, 3.06, -0.3)], 0.006, 'Metal', T_STEEL, seg=5)
        # door: raised plate, hinges on top, latches below, fasteners
        P_plate(door, V(XO, 2.6, fz), nx, upz, 1.08, 0.48, 0.02, 'HullB', T_P9, 0.005)
        for yy in (2.2, 2.6, 3.0):
            P_cyl(door, V(XO + 0.016, yy - 0.045, fz + 0.245), V(XO + 0.016, yy + 0.045, fz + 0.245), 0.011, 'Metal', T_GUN, seg=6)
            P_plate(door, V(XO + 0.02, yy, fz - 0.2), nx, upz, 0.035, 0.05, 0.008, 'Metal', T_GUND, 0.002)
        for yy in np.arange(2.12, 3.1, 0.12):
            for zz in (fz + 0.215, fz - 0.215):
                P_disc(door, V(XO + 0.02, yy, zz), nx, 0.006, 'Paint', T_RIV)
        P_plate(door, V(XO + 0.02, 2.6, fz + 0.06), nx, upz, 0.5, 0.012, 0.004, 'HullB', T_P7)       # stiffener
        # fixed panels (raised) fore and aft of the door
        for (yc, ln, hh) in ((3.55, 0.6, 0.44), (0.95, 0.9, 0.44), (-0.02, 0.42, 0.36)):
            P_plate(mb, V(XO, yc, fz), nx, upz, ln, hh, 0.006, 'HullB', T_P8 if yc > 3 else T_P9, 0.002)
            for sy in (-1, 1):
                for sz in (-1, 1):
                    P_disc(mb, V(XO + 0.006, yc + sy * (ln / 2 - 0.03), fz + sz * (hh / 2 - 0.03)), nx, 0.0065, 'Paint', T_RIV)
            for yy in np.arange(yc - ln / 2 + 0.12, yc + ln / 2 - 0.1, 0.1):
                for sz in (-1, 1):
                    P_disc(mb, V(XO + 0.006, yy, fz + sz * (hh / 2 - 0.03)), nx, 0.0055, 'Paint', T_RIV)
        louvre(mb, V(XO + 0.007, -0.02, fz), nx, V(0, 1, 0), 0.22, 0.26, 6)
        # edge fastener rows on the outer face
        for zz in (ZT - 0.075, ZB + 0.075):
            P_rivets(mb, V(XO, -0.2, zz), V(XO, 3.9, zz), nx, 'Paint', T_RIV, step=0.085, r=0.005)
        # canted top: anti-slip walkway, fuel filler, grounding point
        nt = V(0.06, 0, XO - 0.05 - X0).normalized()
        def tp(y, f): return V(X0 + (XO - 0.05 - X0) * f, y, ZT + 0.06 * (1 - f))
        P_plate(mb, tp(2.75, 0.62), nt, V(0, 1, 0), 0.17, 2.2, 0.005, 'Paint', T_BLACK)
        P_revolve(mb, tp(0.45, 0.6), nt, [(0, 0.06), (0.012, 0.055), (0.014, 0.04)], 'Paint', T_OLIVE2, seg=14, cap0=False)
        P_torus(mb, tp(0.45, 0.6) + nt * 0.004, nt, 0.068, 0.004, 'Paint', T_REDD, seg=16, rseg=4)
        # chamfer formation-light strip, boarding step bar, tie-down
        P_plate(mb, V(XO - 0.025, 3.6, ZT - 0.025), V(1, 0, 1), V(0, 1, 0), 0.03, 0.42, 0.005, 'FormLight', T_W)
        P_tube(mb, [V(XO - 0.03, 3.98, ZB + 0.05), V(XO + 0.07, 3.98, ZB + 0.02), V(XO + 0.07, 3.72, ZB + 0.02), V(XO - 0.03, 3.72, ZB + 0.05)], 0.012, 'Metal', T_GUN, seg=6)
        tiedown(mb, V(XO - 0.1, 0.2, ZB), V(0, 0, -1), V(0, 1, 0))
        return mb, door
    mb, door = side()
    st = MB(); st.merge(mb); st.merge(mb.mirrored())
    build(st, 'Cheeks', parent='Body')
    build(door, 'Part_DoorR', parent='Body')
    build(door.mirrored(), 'Part_DoorL', parent='Body')


def missile_mb():
    """Missile centred at origin pointing +Y."""
    mb = MB()
    tb = (0.036, 0.04, 0.033)
    R = 0.08
    P_revolve(mb, V(0, -0.80, 0), V(0, 1, 0), [(0, 0.05), (0.012, 0.066), (0.03, R), (1.36, R), (1.43, 0.074)], 'Paint', tb, seg=14,
              tints=[T_BLACK, T_DARK, tb, tb, tb])
    P_revolve(mb, V(0, -0.80, 0), V(0, 1, 0), [(0.0, 0.05), (0.03, 0.04)], 'Paint', T_BLACK, seg=14, cap0=False, flip=True)
    P_revolve(mb, V(0, 0.34, 0), V(0, 1, 0), [(0, R + 0.0015), (0.035, R + 0.0015)], 'Paint', T_YELD, seg=14, cap0=False, cap1=False)
    P_revolve(mb, V(0, -0.24, 0), V(0, 1, 0), [(0, R + 0.0015), (0.03, R + 0.0015)], 'Paint', (0.11, 0.05, 0.025), seg=14, cap0=False, cap1=False)
    P_revolve(mb, V(0, 0.61, 0), V(0, 1, 0), [(0, R + 0.002), (0.02, R + 0.002), (0.022, 0.075)], 'Metal', T_GUND, seg=14, cap0=False, cap1=False)
    P_revolve(mb, V(0, 0.63, 0), V(0, 1, 0), [(0, 0.074), (0.04, 0.07), (0.08, 0.056), (0.105, 0.034), (0.118, 0.0005)], 'Lens', T_W, seg=14, cap0=False, cap1=False)
    for k in range(4):
        a = pi / 4 + k * pi / 2
        e = V(cos(a), 0, sin(a))
        dquad(mb, [e * R + V(0, -0.52, 0), e * R + V(0, -0.76, 0), e * (R + 0.085) + V(0, -0.76, 0), e * (R + 0.085) + V(0, -0.64, 0)], 'Paint', tb)
        dquad(mb, [e * R + V(0, 0.3, 0), e * R + V(0, -0.05, 0), e * (R + 0.028) + V(0, -0.05, 0), e * (R + 0.028) + V(0, 0.22, 0)], 'Paint', tb)
    for yy in (-0.3, 0.25):      # launch shoes
        P_box(mb, V(0, yy, R + 0.008), (0.03, 0.07, 0.025), 'Metal', T_GUND, 0.004)
    return mb


WING_A = (V(0.45, 0.78, -0.12), 1.15, 0.14)       # root: LE point, chord, thickness
WING_B = (V(2.4, 0.62, -0.22), 0.85, 0.12)

def wsurf(u, xc, top=True):
    """point + normal on the right stub wing; u span 0..1, xc chord fraction"""
    le = WING_A[0].lerp(WING_B[0], u); c = WING_A[1] + (WING_B[1] - WING_A[1]) * u; th = WING_A[2] + (WING_B[2] - WING_A[2]) * u
    yt = 5 * th * (0.2969 * math.sqrt(xc) - 0.1260 * xc - 0.3516 * xc * xc + 0.2843 * xc ** 3 - 0.1036 * xc ** 4) * c
    sg = 1 if top else -1
    p = le + V(0, -xc * c, sg * yt)
    e = 0.01
    yt2 = 5 * th * (0.2969 * math.sqrt(xc + e) - 0.1260 * (xc + e) - 0.3516 * (xc + e) ** 2 + 0.2843 * (xc + e) ** 3 - 0.1036 * (xc + e) ** 4) * c
    d = V(0, -e * c, sg * (yt2 - yt)).normalized()
    sp_ = (WING_B[0] - WING_A[0]).normalized()
    n = sp_.cross(d).normalized()
    if n.z * sg < 0: n = -n
    return p, n


def build_wings():
    def side():
        mb = MB(); tip = MB()
        cd = V(0, -1, 0); up = V(0, 0, 1)
        P_airfoil(mb, [(WING_A[0], cd, WING_A[1], WING_A[2], up), (WING_B[0], cd, WING_B[1], WING_B[2], up)], 'HullB', T_W, n=11)
        # tip fairing with launcher rail + nav light (detachable)
        P_airfoil(tip, [(V(2.4, 0.62, -0.22), cd, 0.85, 0.12, up), (V(2.5, 0.59, -0.225), cd, 0.8, 0.12, up),
                        (V(2.57, 0.5, -0.23), cd, 0.62, 0.10, up), (V(2.6, 0.42, -0.23), cd, 0.46, 0.06, up)], 'HullB', T_P9, n=11)
        P_loft(tip, [chring(y, 2.575, 2.655, -0.275, -0.195, 0.015) for y in (0.82, 0.78, -0.5, -0.56)], 'Paint', T_OLIVE2, cap0=True, cap1=True)
        P_box(tip, V(2.615, 0.15, -0.292), (0.035, 1.1, 0.03), 'Metal', T_GUND, 0.006)
        P_sphere(tip, V(2.615, 0.825, -0.235), (0.026, 0.045, 0.026), 'Paint', T_GRN, seg=10, rings=6)
        P_box(mb, V(2.396, 0.2, -0.22), (0.008, 0.7, 0.07), 'Paint', T_BLACK)                           # exposed rib when the tip is gone
        # flap line, rib / spar fastener rows, access panels, walk strip, formation light
        for top in (True, False):
            a, na = wsurf(0.03, 0.72, top); b, nb = wsurf(0.99, 0.72, top)
            P_sweep(mb, [a, b], [na, nb], 0.014, 0.0015, 0.0, 'Paint', T_BLACK)
            for xc in (0.1, 0.4, 0.66):
                for u in np.arange(0.08, 0.99, 0.045):
                    p, n = wsurf(u, xc, top); P_disc(mb, p, n, 0.0055, 'Paint', T_RIV)
            for u in (0.24, 0.49, 0.74, 0.97):
                for xc in np.arange(0.14, 0.95, 0.07):
                    p, n = wsurf(u, xc, top); P_disc(mb, p, n, 0.0055, 'Paint', T_RIV)
        for (u, xc, w_, l_) in ((0.36, 0.25, 0.26, 0.2), (0.62, 0.54, 0.22, 0.16), (0.86, 0.26, 0.16, 0.2)):
            p, n = wsurf(u, xc); P_plate(mb, p, n, V(0, 1, 0), w_, l_, 0.005, 'HullB', T_P8, 0.0015)
            for sx in (-1, 1):
                for sy in (-1, 1):
                    P_disc(mb, p + V(sx * (w_ / 2 - 0.022), sy * (l_ / 2 - 0.022), 0) + n * 0.005, n, 0.006, 'Paint', T_RIV)
        p, n = wsurf(0.12, 0.42); P_plate(mb, p, n, V(0, 1, 0), 0.3, 0.6, 0.004, 'Paint', T_BLACK)
        p, n = wsurf(0.8, 0.86); P_plate(mb, p, n, V(0, 1, 0), 0.5, 0.03, 0.004, 'FormLight', T_W)
        p, n = wsurf(0.55, 0.12); P_revolve(mb, p - n * 0.004, n, [(0, 0.045), (0.01, 0.042), (0.012, 0.03)], 'Paint', T_OLIVE2, seg=12, cap0=False)
        p, n = wsurf(0.93, 0.5, False); tiedown(mb, p, n, V(0, 1, 0))
        # faceted wing root fairing
        rr = [chring(y, 0.42, x1, z0, z1, 0.045) for (y, x1, z0, z1) in ((0.98, 0.5, -0.17, -0.08), (0.8, 0.66, -0.22, -0.03), (0.3, 0.7, -0.25, -0.01), (-0.2, 0.68, -0.25, -0.03), (-0.55, 0.5, -0.22, -0.1))]
        P_loft(mb, rr, 'HullB', T_W, cap0=True, cap1=True)
        # pylons with ejector racks + sway braces
        for x in (1.4, 2.05):
            zt = wsurf((x - 0.45) / 1.95, 0.4, False)[0].z
            P_airfoil(mb, [(V(x, 0.66, zt + 0.05), cd, 0.9, 0.11, V(1, 0, 0)), (V(x, 0.58, -0.425), cd, 0.74, 0.11, V(1, 0, 0))], 'HullB', T_W, n=8)
            P_box(mb, V(x, 0.2, -0.445), (0.11, 0.78, 0.05), 'Paint', T_OLIVE2, 0.012)
            for yy in (0.52, 0.2, -0.12):
                for s in (-1, 1):
                    P_bolt(mb, V(x + s * 0.056, yy, -0.445), V(s, 0, 0), 0.01, 0.006, 'Metal', T_GUND)
        x = 1.4
        for yy in (0.47, -0.07):       # pod sway braces
            for s in (-1, 1):
                a = V(x + s * 0.05, yy, -0.455); b = V(x + s * 0.092, yy, -0.515)
                P_tube(mb, [a, b], 0.011, 'Metal', T_GUND, seg=6)
                P_plate(mb, b + V(-s * 0.004, 0, -0.012), V(s * 0.47, 0, 0.88), V(0, 1, 0), 0.04, 0.05, 0.01, 'Metal', T_GUN, 0.002)
            P_cyl(mb, V(x, yy + 0.1, -0.47), V(x, yy + 0.1, -0.5), 0.016, 'Metal', T_GUND, seg=8)        # suspension lugs
        # quad missile launcher: centre beam, two cross arms, four rails (missiles are separate nodes)
        x = 2.05
        P_loft(mb, [chring(y, x - 0.035, x + 0.035, -0.80, -0.465, 0.012) for y in (0.56, 0.5, -0.1, -0.18)], 'Paint', T_OLIVE2, cap0=True, cap1=True)
        mpos = []
        for z in (-0.62, -0.885):
            zr = z + 0.118
            for yy in (0.42, -0.02):
                P_box(mb, V(x, yy, zr + 0.012), (0.4, 0.07, 0.035), 'Paint', T_OLIVE2, 0.008)
            for dx in (-0.16, 0.16):
                P_loft(mb, [chring(y, x + dx - 0.024, x + dx + 0.024, zr - 0.03, zr + 0.02, 0.008) for y in (0.9, 0.86, -0.42, -0.47)], 'Metal', T_GUND, cap0=True, cap1=True)
                P_box(mb, V(x + dx, 0.2, zr - 0.033), (0.02, 1.2, 0.012), 'Metal', T_GUN)
                P_box(mb, V(x + dx, -0.4, zr + 0.005), (0.06, 0.1, 0.06), 'Paint', T_OLIVE2, 0.01)             # umbilical / hold-back
                P_tube(mb, [V(x + dx * 0.9, -0.36, zr + 0.03), V(x + dx * 0.5, -0.25, zr + 0.05), V(x + dx * 0.2, -0.12, zr + 0.03)], 0.007, 'Paint', T_BLACK, seg=5)
                mpos.append(V(x + dx, 0.22, z))
        mpos = [mpos[0], mpos[2], mpos[1], mpos[3]]      # 1,2 inner (upper, lower); 3,4 outer (upper, lower)
        return mb, tip, mpos
    mb, tip, mpos = side()
    st = MB(); st.merge(mb); st.merge(mb.mirrored())
    build(st, 'Wings', parent='Body')
    build(tip, 'Part_WingTipR', parent='Body')
    tl = tip.mirrored()
    tl.vc = [T_RED if c == T_GRN else c for c in tl.vc]
    build(tl, 'Part_WingTipL', parent='Body')
    empty('Light_Nav_R', V(2.62, 0.8, -0.23), 'Body'); empty('Light_Nav_L', V(-2.62, 0.8, -0.23), 'Body')
    # rocket pods (19 tube)
    def pod():
        mb = MB()
        c = V(1.4, 0.2, -0.69)
        tb = (0.034, 0.038, 0.031); R = 0.19
        P_revolve(mb, c + V(0, -1.08, 0), V(0, 1, 0), [(0, 0.075), (0.1, 0.11), (0.3, R - 0.012), (0.36, R), (1.82, R), (1.85, R - 0.006), (1.855, R - 0.02)], 'Paint', tb, seg=28, cap0=False, cap1=False)
        P_revolve(mb, c + V(0, -1.08, 0), V(0, 1, 0), [(0.0, 0.075), (0.05, 0.06), (0.05, 0.0005)], 'Paint', T_BLACK, seg=28, cap0=False, cap1=False, flip=True)
        P_revolve(mb, c + V(0, 0.772, 0), V(0, 1, 0), [(0.0, R - 0.02)], 'Paint', T_DARK, seg=28)           # front bulkhead
        for yy, w_ in ((0.5, 0.04), (-0.05, 0.04), (-0.62, 0.025)):
            P_revolve(mb, c + V(0, yy, 0), V(0, 1, 0), [(0, R + 0.004), (w_, R + 0.004)], 'Metal', T_GUND, seg=28, cap0=False, cap1=False)
        P_revolve(mb, c + V(0, 0.2, 0), V(0, 1, 0), [(0, R + 0.0015), (0.02, R + 0.0015)], 'Paint', T_YELD, seg=28, cap0=False, cap1=False)
        tubes = [(0, 0)] + [(0.075 * cos(k * pi / 3), 0.075 * sin(k * pi / 3)) for k in range(6)] + \
                [(0.143 * cos(k * pi / 6 + pi / 12), 0.143 * sin(k * pi / 6 + pi / 12)) for k in range(12)]
        for (tx, tz) in tubes:
            p = c + V(tx, 0.772, tz)
            P_revolve(mb, p, V(0, 1, 0), [(0, 0.034), (0.014, 0.034), (0.014, 0.029), (-0.06, 0.029)], 'Metal', T_STEELD, seg=10, cap0=False, cap1=False)
            P_revolve(mb, p, V(0, 1, 0), [(-0.06, 0.029)], 'Paint', T_BLACK, seg=10)
        for a_ in (-0.5, 0.5):       # lug fairings on top
            P_box(mb, c + V(0, 0.2 + a_ * 0.56, R + 0.004), (0.05, 0.12, 0.02), 'Metal', T_GUND, 0.005)
        P_tube(mb, [c + V(0.03, -0.55, R), c + V(0.04, -0.62, R + 0.04), c + V(0.02, -0.5, R + 0.07)], 0.008, 'Paint', T_BLACK, seg=5)
        return mb, c
    mb, c = pod()
    build(mb, 'PodR', origin=c, parent='Body')
    build(mb.mirrored(), 'PodL', origin=V(-c.x, c.y, c.z), parent='Body')
    empty('RocketR', c + V(0, 0.8, 0), 'PodR'); empty('RocketL', V(-c.x, c.y + 0.8, c.z), 'PodL')
    for k, p in enumerate(mpos):
        for s, nm in ((1, 'R'), (-1, 'L')):
            m = missile_mb()
            o = V(p.x * s, p.y, p.z)
            for v in m.v: v += o
            build(m, 'Missile_%s%d' % (nm, k + 1), origin=o, parent='Body')


def afs(A, B, u, xc, sg, up, cd=V(0, -1, 0)):
    """point + outward normal on a 2-section airfoil surface. A/B = (le, chord, thickness); sg=+1 'up' side."""
    le = A[0].lerp(B[0], u); c = A[1] + (B[1] - A[1]) * u; th = A[2] + (B[2] - A[2]) * u
    f = lambda x: 5 * th * (0.2969 * math.sqrt(x) - 0.1260 * x - 0.3516 * x * x + 0.2843 * x ** 3 - 0.1036 * x ** 4) * c
    up = Vector(up).normalized()
    p = le + cd * (xc * c) + up * (sg * f(xc))
    d = (cd * (0.01 * c) + up * (sg * (f(xc + 0.01) - f(xc)))).normalized()
    n = (B[0] - A[0]).normalized().cross(d).normalized()
    if n.dot(up) * sg < 0: n = -n
    return p, n


def wheel(mb, c, r, w, axis=V(1, 0, 0), seg=28, hub_tint=T_OLIVE2):
    """Tyre with tread grooves + dished rim, centred at c."""
    k = r / 0.28; a = Vector(axis)
    prof = [(0, 0.6 * r), (0.05 * w, 0.84 * r), (0.17 * w, 0.955 * r), (0.3 * w, r), (0.385 * w, r), (0.395 * w, r - 0.008), (0.435 * w, r - 0.008),
            (0.445 * w, r), (0.555 * w, r), (0.565 * w, r - 0.008), (0.605 * w, r - 0.008), (0.615 * w, r), (0.7 * w, r), (0.83 * w, 0.955 * r),
            (0.95 * w, 0.84 * r), (w, 0.6 * r)]
    P_revolve(mb, c - a * (w / 2), a, prof, 'Rubber', T_W, seg=seg, cap0=False, cap1=False)
    for sg in (-1, 1):
        o = c + a * (sg * w / 2)
        P_revolve(mb, o, a * sg, [(0, 0.6 * r), (-0.012, 0.56 * r), (-0.03, 0.5 * r), (-0.035, 0.24 * r), (0.0, 0.2 * r), (0.012, 0.1 * r)], 'Paint', hub_tint, seg=seg, cap0=False)
        for q in range(8):
            ang = q * pi / 4
            R = basis(a * sg)
            P_bolt(mb, o + R @ V(0.37 * r * cos(ang), 0.37 * r * sin(ang), -0.034), a * sg, 0.011 * k + 0.004, 0.008, 'Metal', T_STEELD)


FIN_A = (V(0, -7.05, 0.12), 1.30, 0.10); FIN_B = (V(0, -7.62, 1.2), 1.0, 0.105); FIN_C = (V(0, -7.9, 1.78), 0.82, 0.10)

def build_tail():
    mb = MB()
    cd = V(0, -1, 0); xr = V(1, 0, 0); up = V(0, 0, 1)
    FA, FB, FC = FIN_A, FIN_B, FIN_C
    P_airfoil(mb, [(FA[0], cd, FA[1], FA[2], xr), (FB[0], cd, FB[1], FB[2], xr), (FC[0], cd, FC[1], FC[2], xr)], 'HullB', T_W, n=11)
    # fin: fastener rows, raised panels, trailing-edge tab, formation strips, antennas
    for sg in (-1, 1):
        for (A, B) in ((FA, FB), (FB, FC)):
            for xc in (0.12, 0.42, 0.7):
                for u in np.arange(0.06, 0.97, 0.075):
                    p, n = afs(A, B, u, xc, sg, xr); P_disc(mb, p, n, 0.0055, 'Paint', T_RIV)
            for u in (0.33, 0.66):
                for xc in np.arange(0.16, 0.92, 0.065):
                    p, n = afs(A, B, u, xc, sg, xr); P_disc(mb, p, n, 0.0055, 'Paint', T_RIV)
        a, na = afs(FA, FB, 0.12, 0.76, sg, xr); b, nb = afs(FB, FC, 0.95, 0.76, sg, xr); m, nm_ = afs(FA, FB, 1.0, 0.76, sg, xr)
        P_sweep(mb, [a, m, b], [na, nm_, nb], 0.014, 0.0015, 0.0, 'Paint', T_BLACK)
        p, n = afs(FA, FB, 0.45, 0.3, sg, xr); P_plate(mb, p, n, up, 0.3, 0.26, 0.005, 'HullB', T_P8, 0.0015)
        for sx in (-1, 1):
            for sz in (-1, 1):
                P_disc(mb, p + V(0, sx * 0.125, sz * 0.105) + n * 0.005, n, 0.006, 'Paint', T_RIV)
        p, n = afs(FB, FC, 0.45, 0.55, sg, xr)
        P_plate(mb, p, n, V(0, -0.45, 1), 0.03, 0.42, 0.004, 'FormLight', T_W)
        if sg < 0:      # towel-rail antenna on the left of the fin
            a, na = afs(FA, FB, 0.3, 0.25, sg, xr); b, nb = afs(FA, FB, 0.8, 0.5, sg, xr)
            handhold(mb, a, b, na, h=0.06, r=0.007, tint=T_GUND)
    # tail rotor drive: shaft cover up the fin + gearbox housing on the right
    pts = [afs(FA, FB, u, 0.2 + 0.36 * u, 1, xr) for u in (0.1, 0.4, 0.7, 0.92)]
    P_sweep(mb, [p for p, n in pts], [n for p, n in pts], 0.11, 0.035, 0.01, 'HullB', T_P9)
    for p, n in pts[1:-1]:
        P_plate(mb, p + n * 0.035, n, up, 0.13, 0.03, 0.006, 'Metal', T_GUND, 0.002)
    gb = V(0.02, TR_HUB.y, TR_HUB.z)
    P_revolve(mb, gb, V(1, 0, 0), [(0, 0.2), (0.1, 0.19), (0.15, 0.14), (0.2, 0.12), (0.24, 0.075)], 'Metal', T_GUN, seg=18, cap0=False)
    for k in range(8):
        a = k * pi / 4
        P_bolt(mb, gb + V(0.1, 0.165 * cos(a), 0.165 * sin(a)), V(1, 0.3, 0), 0.01, 0.01, 'Metal', T_STEELD)
    P_box(mb, gb + V(0.06, 0.22, -0.12), (0.12, 0.3, 0.14), 'Metal', T_GUN, 0.03, rot=Matrix.Rotation(rad(28), 3, 'X'))
    P_cyl(mb, gb + V(0.1, 0.05, 0.19), gb + V(0.1, 0.05, 0.23), 0.025, 'Metal', T_STEELD, seg=8)            # oil filler
    P_revolve(mb, V(-0.02, TR_HUB.y, TR_HUB.z), V(-1, 0, 0), [(0, 0.15), (0.03, 0.14), (0.05, 0.09)], 'HullB', T_W, seg=16, cap0=False)
    # ventral fin with tail-wheel leg
    VA = (V(0, -7.05, 0.02), 1.02, 0.10); VB = (V(0, -7.5, -0.86), 0.52, 0.13)
    P_airfoil(mb, [(VA[0], cd, VA[1], VA[2], xr), (VB[0], cd, VB[1], VB[2], xr)], 'HullB', T_W, n=11, cap1=True)
    for sg in (-1, 1):
        for xc in (0.15, 0.6):
            for u in np.arange(0.1, 0.95, 0.09):
                p, n = afs(VA, VB, u, xc, sg, xr); P_disc(mb, p, n, 0.0055, 'Paint', T_RIV)
    wc = V(0, -8.0, GEAR_Z + 0.15)
    crown = V(0, -7.84, -1.24)
    P_cyl(mb, V(0, -7.72, -0.8), V(0, -7.79, -1.06), 0.042, 'Paint', T_OLIVE2, seg=12)
    P_cyl(mb, V(0, -7.79, -1.06), crown, 0.026, 'Metal', T_CHROME, seg=10)
    P_torus(mb, V(0, -7.79, -1.06), V(0, -0.26, -1), 0.043, 0.008, 'Metal', T_GUND, seg=12, rseg=5)
    P_box(mb, crown, (0.19, 0.09, 0.07), 'Metal', T_GUN, 0.015)
    for s in (-1, 1):
        P_loft(mb, [chring(y, s * 0.085 - 0.012, s * 0.085 + 0.012, z - 0.03, z + 0.03, 0.006) for (y, z) in ((-7.82, -1.24), (-7.93, -1.46), (-8.02, -1.61))], 'Metal', T_GUN, cap0=True, cap1=True)
        P_cyl(mb, wc + V(s * 0.07, 0, 0), wc + V(s * 0.105, 0, 0), 0.022, 'Metal', T_STEELD, seg=8)
    P_tube(mb, [V(0, -7.99, -0.78), V(0, -7.93, -1.05), crown + V(0, -0.03, 0.02)], 0.014, 'Metal', T_STEELD, seg=6)   # drag brace
    P_cyl(mb, crown + V(0.05, 0.05, 0.0), crown + V(0.05, 0.16, 0.14), 0.014, 'Metal', T_GUND, seg=6)                # shimmy damper
    wheel(mb, wc, 0.15, 0.1, seg=20, hub_tint=T_OLIVE2)
    tiedown(mb, V(0, -7.5, -0.87), V(0, 0, -1), V(1, 0, 0))
    # stabilator pivot stubs (visible when the stabilator is shot off) + actuator fairing
    for s in (-1, 1):
        P_cyl(mb, V(s * 0.1, -7.1, 0.04), V(s * 0.24, -7.1, 0.04), 0.035, 'Metal', T_GUND, seg=10)
        P_box(mb, V(s * 0.17, -7.12, 0.04), (0.02, 0.5, 0.07), 'Paint', T_BLACK, 0.006)
    P_box(mb, V(0, -7.35, 0.27), (0.1, 0.4, 0.07), 'HullB', T_P9, 0.025)
    # tail position light + fin-top cap seat
    P_sphere(mb, V(0, -8.385, 0.1), (0.03, 0.04, 0.03), 'Lens', T_W, seg=8, rings=5)
    P_box(mb, V(0, -8.3, 1.782), (0.04, 0.6, 0.012), 'Paint', T_BLACK)
    build(mb, 'Tail', parent='Body')
    # fin tip (detachable)
    ft = MB()
    P_airfoil(ft, [(V(0, -7.9, 1.78), cd, 0.82, 0.10, xr), (V(0, -8.0, 1.99), cd, 0.72, 0.10, xr), (V(0, -8.1, 2.09), cd, 0.58, 0.085, xr), (V(0, -8.2, 2.13), cd, 0.4, 0.05, xr)], 'HullB', T_P9, n=11)
    P_sphere(ft, V(0, -8.4, 2.15), (0.03, 0.045, 0.03), 'Paint', T_RED, seg=8, rings=5)
    P_cyl(ft, V(0, -8.05, 2.08), V(0, -8.3, 2.72), 0.006, 'Metal', T_GUND, seg=5)        # whip antenna
    P_cyl(ft, V(0, -8.05, 2.06), V(0, -8.07, 2.12), 0.014, 'Metal', T_GUND, seg=6)
    build(ft, 'Part_TailFin', parent='Body')
    # stabilator halves (detachable)
    st = MB()
    SA = (V(0.13, -6.74, 0.04), 0.86, 0.10); SB = (V(1.55, -6.96, 0.04), 0.56, 0.10)
    P_airfoil(st, [(SA[0], cd, SA[1], SA[2], up), (SB[0], cd, SB[1], SB[2], up), (V(1.62, -7.02, 0.04), cd, 0.44, 0.07, up)], 'HullB', T_W, n=11)
    for sg in (-1, 1):
        for xc in (0.12, 0.45, 0.72):
            for u in np.arange(0.06, 0.99, 0.055):
                p, n = afs(SA, SB, u, xc, sg, up); P_disc(st, p, n, 0.0055, 'Paint', T_RIV)
        for u in (0.3, 0.62, 0.94):
            for xc in np.arange(0.18, 0.92, 0.075):
                p, n = afs(SA, SB, u, xc, sg, up); P_disc(st, p, n, 0.0055, 'Paint', T_RIV)
    p, n = afs(SA, SB, 0.5, 0.35, 1, up); P_plate(st, p, n, V(0, 1, 0), 0.3, 0.16, 0.004, 'HullB', T_P8, 0.001)
    for u in (0.35, 0.6, 0.85, 0.98):     # static dischargers
        p, n = afs(SA, SB, u, 0.99, 1, up); P_cyl(st, p, p + V(0, -0.11, 0), 0.004, 'Paint', T_BLACK, seg=4)
    build(st, 'Part_StabR', parent='Body')
    build(st.mirrored(), 'Part_StabL', parent='Body')
    empty('Gear_Tail', V(0, -8.0, GEAR_Z), 'Body')
    empty('TailRotorHub', TR_HUB, 'Body')
    # ---- tail rotor: twin two-blade teetering rotors, scissor (X) arrangement
    tr = MB()
    H = TR_HUB
    tb = (0.02, 0.02, 0.022)
    P_cyl(tr, V(0.24, H.y, H.z), V(H.x + 0.2, H.y, H.z), 0.04, 'Metal', T_STEELD, seg=12)
    P_revolve(tr, V(H.x + 0.2, H.y, H.z), V(1, 0, 0), [(0, 0.055), (0.02, 0.05), (0.035, 0.02)], 'Paint', T_HUB2, seg=12, cap0=False)
    for pi_, (ang, xo) in enumerate(((rad(62.5), -0.035), (rad(117.5), 0.045))):
        e0 = V(0, cos(ang), sin(ang)); t0 = V(1, 0, 0).cross(e0)
        Rh = Matrix((e0, t0, V(1, 0, 0))).transposed()
        hc = V(H.x + xo, H.y, H.z)
        P_box(tr, hc, (0.44, 0.13, 0.065), 'Paint', T_HUB1, 0.015, rot=Rh)                 # teetering yoke
        P_cyl(tr, hc - t0 * 0.085, hc + t0 * 0.085, 0.022, 'Metal', T_STEEL, seg=8)       # teeter bolt
        for sgn in (-1, 1):
            e = e0 * sgn; t = V(1, 0, 0).cross(e)
            pch = rad(9)
            cdir = (-t * cos(pch) - V(1, 0, 0) * sin(pch)); upv = (V(1, 0, 0) * cos(pch) - t * sin(pch))
            secs = []; tints = []
            for r, c, th in ((0.2, 0.1, 0.5), (0.34, 0.24, 0.16), (0.5, 0.26, 0.12), (1.2, 0.26, 0.115), (1.215, 0.26, 0.115), (1.29, 0.24, 0.11), (1.32, 0.18, 0.09)):
                secs.append((hc + e * r + t * (c * 0.3), cdir, c, th, upv)); tints.append(T_YELD if r > 1.21 else tb)
            P_airfoil(tr, secs, 'Paint', tb, n=8, tints=tints)
            P_box(tr, hc + e * 0.27, (0.14, 0.11, 0.075), 'Paint', T_HUB2, 0.015, rot=Matrix((e, t, V(1, 0, 0))).transposed())   # blade grip
            for rr in (0.235, 0.305):
                P_cyl(tr, hc + e * rr - V(0.045, 0, 0), hc + e * rr + V(0.045, 0, 0), 0.014, 'Metal', T_STEEL, seg=6)
            # pitch horn + link to the pitch-change spider
            hn = hc + e * 0.25 + t * 0.1 + V(0.03, 0, 0)
            P_box(tr, hc + e * 0.25 + t * 0.07 + V(0.02, 0, 0), (0.04, 0.09, 0.03), 'Paint', T_HUB2, 0.006, rot=Matrix((e, t, V(1, 0, 0))).transposed())
            spd = V(H.x + 0.17, H.y, H.z) + (e * 0.11 + t * 0.1)
            P_cyl(tr, hn, spd, 0.008, 'Metal', T_STEEL, seg=6)
            P_cyl(tr, V(H.x + 0.17, H.y, H.z), spd, 0.014, 'Paint', T_HUB2, seg=6)
    build(tr, 'TailRotor', origin=H, parent='Body')


def build_gear():
    def side():
        mb = MB()
        ax = V(1.06, 1.55, GEAR_Z + 0.28)
        # trailing arm: pivot bracket on the sponson, tapered box beam to the axle
        pv = V(0.86, 2.36, -0.74)
        P_box(mb, pv + V(-0.03, 0, 0.0), (0.12, 0.2, 0.16), 'Paint', T_OLIVE2, 0.025)
        P_cyl(mb, pv + V(-0.05, 0, 0), pv + V(0.1, 0, 0), 0.05, 'Metal', T_GUND, seg=12)
        for k in range(5):
            a = k * 2 * pi / 5
            P_bolt(mb, pv + V(0.1, 0.03 * cos(a), 0.03 * sin(a)), V(1, 0, 0), 0.008, 0.006, 'Metal', T_STEELD)
        a0 = pv + V(0.05, 0, 0); a1 = V(0.93, 1.55, GEAR_Z + 0.28)
        d = (a1 - a0).normalized(); sd = V(1, 0, 0); nn = sd.cross(d).normalized()
        def rect(p, w, h):
            return [p + sd * w + nn * h, p - sd * w + nn * h, p - sd * w - nn * h, p + sd * w - nn * h]
        L = (a1 - a0).length
        P_loft(mb, [rect(a0 - d * 0.03, 0.036, 0.07), rect(a0 + d * 0.1, 0.04, 0.075), rect(a0 + d * (L - 0.14), 0.036, 0.055), rect(a1 + d * 0.06, 0.034, 0.05)], 'Paint', T_OLIVE2, cap0=True, cap1=True)
        for f in (0.2, 0.42, 0.64):         # lightening recess panels on the arm
            P_plate(mb, a0 + d * (L * f) + sd * 0.04, sd, d, 0.07, 0.16, 0.004, 'Paint', T_DARK, 0.001)
        P_cyl(mb, ax + V(-0.2, 0, 0), ax + V(0.03, 0, 0), 0.042, 'Metal', T_GUND, seg=12)          # axle
        # oleo shock strut from the arm to the sponson side
        lo = a0 + d * (L * 0.84) + nn * 0.03; hi = V(0.93, 1.43, -0.28)
        P_box(mb, hi + V(-0.04, 0, 0.0), (0.1, 0.16, 0.14), 'Paint', T_OLIVE2, 0.02)
        P_cyl(mb, hi + V(-0.03, 0, 0), hi + V(0.06, 0, 0), 0.03, 'Metal', T_GUND, seg=10)
        ds = (lo - hi).normalized(); Ls = (lo - hi).length
        P_cyl(mb, hi, hi + ds * (Ls * 0.6), 0.055, 'Paint', T_OLIVE2, seg=14)
        P_torus(mb, hi + ds * (Ls * 0.6), ds, 0.056, 0.01, 'Metal', T_GUND, seg=14, rseg=5)
        P_cyl(mb, hi + ds * (Ls * 0.6), lo, 0.034, 'Metal', T_CHROME, seg=12)
        P_sphere(mb, lo, 0.05, 'Metal', T_GUND, seg=10, rings=6)
        P_sphere(mb, hi, 0.06, 'Paint', T_OLIVE2, seg=10, rings=6)
        P_cyl(mb, hi + ds * 0.12 + V(0.055, 0, 0), hi + ds * 0.12 + V(0.075, 0, 0), 0.016, 'Metal', T_STEELD, seg=6)     # charging valve
        # wheel, brake, lines, step, tie-down
        wheel(mb, ax, 0.28, 0.2, hub_tint=T_OLIVE2)
        P_revolve(mb, ax + V(-0.105, 0, 0), V(-1, 0, 0), [(0, 0.15), (0.03, 0.15), (0.035, 0.1)], 'Metal', T_STEELD, seg=18, cap0=False)
        P_box(mb, ax + V(-0.125, 0.0, 0.11), (0.05, 0.1, 0.09), 'Metal', T_GUND, 0.012)
        P_tube(mb, [ax + V(-0.13, 0.0, 0.15), ax + V(-0.15, 0.1, 0.2), a0 + d * (L * 0.7) + nn * 0.085 - sd * 0.03, a0 + d * (L * 0.3) + nn * 0.09 - sd * 0.03, a0 + d * 0.06 + nn * 0.09 - sd * 0.03,
                    pv + V(-0.06, 0.03, 0.12)], 0.007, 'Paint', T_BLACK, seg=5)
        P_box(mb, a0 + d * (L * 0.52) + sd * 0.085, (0.1, 0.16, 0.012), 'Metal', T_GUN, 0.003, rot=basis(V(0, 0, 1), V(0, 1, 0)))     # crew step
        P_cyl(mb, a0 + d * (L * 0.52) + sd * 0.03, a0 + d * (L * 0.52) + sd * 0.09 - V(0, 0, 0.012), 0.01, 'Metal', T_GUND, seg=6)
        tiedown(mb, a0 + d * (L * 0.93) - nn * 0.05, -nn, V(1, 0, 0), 0.025)
        # wire deflector ahead of the leg
        P_tube(mb, [pv + V(0.02, 0.1, -0.02), pv + V(0.04, 0.32, -0.1), pv + V(0.04, 0.4, -0.2)], 0.01, 'Metal', T_GUND, seg=5)
        return mb
    mb = side()
    st = MB(); st.merge(mb); st.merge(mb.mirrored())
    build(st, 'Gear', parent='Body')
    empty('Gear_FR', V(1.06, 1.55, GEAR_Z), 'Body'); empty('Gear_FL', V(-1.06, 1.55, GEAR_Z), 'Body')


def build_rotor():
    mb = MB()
    C = V(0, 0, ROTOR_Z)
    Z = V(0, 0, 1)
    tb = (0.017, 0.018, 0.019)
    # rotating mast sleeve, swashplate (rotating ring), hub barrel, plates, cap
    P_revolve(mb, V(0, 0, 1.80), Z, [(0, 0.1), (0.02, 0.115), (0.24, 0.115), (0.27, 0.15), (0.3, 0.15)], 'Paint', T_HUB1, seg=20, cap0=False)
    P_revolve(mb, V(0, 0, 1.722), Z, [(0, 0.13), (0.008, 0.31), (0.05, 0.31), (0.058, 0.13)], 'Metal', T_STEELD, seg=28)
    P_torus(mb, V(0, 0, 1.75), Z, 0.31, 0.012, 'Paint', T_HUB2, seg=28, rseg=5)
    P_revolve(mb, C + V(0, 0, -0.11), Z, [(0, 0.15), (0.015, 0.17), (0.2, 0.17), (0.215, 0.15)], 'Paint', T_HUB1, seg=20)
    for k in range(10):
        a = k * pi / 5
        P_bolt(mb, C + V(0.125 * cos(a), 0.125 * sin(a), 0.105), Z, 0.012, 0.012, 'Metal', T_STEELD)
    P_revolve(mb, C + V(0, 0, 0.105), Z, [(0, 0.09), (0.05, 0.085), (0.06, 0.1), (0.14, 0.1), (0.17, 0.07), (0.18, 0.03)], 'Paint', T_OLIVE2, seg=18, cap0=False)
    P_cyl(mb, C + V(0, 0, 0.28), C + V(0, 0, 0.31), 0.016, 'Paint', T_HUB2, seg=6)
    for k in range(2):      # drive scissors mast -> swashplate
        a = k * pi + pi / 2
        e = V(cos(a), sin(a), 0); t = Z.cross(e)
        k0 = e * 0.125 + V(0, 0, 1.97); k1 = e * 0.3 + V(0, 0, 1.885); k2 = e * 0.29 + V(0, 0, 1.775)
        for sg in (-1, 1):
            P_tube(mb, [k0 + t * sg * 0.03, k1 + t * sg * 0.03], 0.013, 'Metal', T_STEELD, seg=6)
            P_tube(mb, [k1 + t * sg * 0.03, k2 + t * sg * 0.03], 0.013, 'Metal', T_STEELD, seg=6)
        P_cyl(mb, k1 - t * 0.045, k1 + t * 0.045, 0.018, 'Metal', T_STEEL, seg=8)
        P_box(mb, k0 - e * 0.01, (0.05, 0.09, 0.05), 'Paint', T_HUB1, 0.008, rot=Matrix((e, t, Z)).transposed())
    nb = 4
    for k in range(nb):
        a = k * 2 * pi / nb + pi / 4
        e = V(cos(a), sin(a), 0); t = Z.cross(e)
        R = Matrix((e, t, Z)).transposed()
        # hub plates (upper / lower arms) + laminated strap pack between
        for dz in (-0.085, 0.085):
            P_box(mb, C + e * 0.36 + V(0, 0, dz), (0.56, 0.2, 0.028), 'Paint', T_HUB1, 0.008, rot=R)
            for rr in (0.5, 0.6):
                for sg in (-1, 1):
                    P_bolt(mb, C + e * rr + t * (sg * 0.06) + V(0, 0, dz + (0.014 if dz > 0 else -0.014)), Z * (1 if dz > 0 else -1), 0.014, 0.012, 'Metal', T_STEELD)
        P_box(mb, C + e * 0.45, (0.62, 0.13, 0.05), 'Metal', T_STEELD, 0.006, rot=R)
        # pitch housing (octagonal sleeve)
        def oct(r, w, h):
            c_ = C + e * r; q = 0.3
            return [c_ + t * (w * x) + Z * (h * y) for x, y in ((1, q), (q, 1), (-q, 1), (-1, q), (-1, -q), (-q, -1), (q, -1), (1, -q))]
        P_loft(mb, [oct(0.62, 0.05, 0.04), oct(0.64, 0.115, 0.08), oct(0.8, 0.115, 0.08), oct(0.98, 0.1, 0.068), oct(1.0, 0.07, 0.05)], 'Paint', T_HUB1, cap0=True, cap1=True)
        for rr in (0.68, 0.9):
            P_loft(mb, [oct(rr, 0.124, 0.088), oct(rr + 0.03, 0.124, 0.088)], 'Metal', T_STEELD, cap0=True, cap1=True)
        # lead-lag dampers either side
        for sg in (-1, 1):
            d0 = C + e * 0.34 + t * (sg * 0.185); d1 = C + e * 1.0 + t * (sg * 0.15)
            dd = (d1 - d0)
            P_cyl(mb, d0, d0 + dd * 0.62, 0.036, 'Paint', T_HUB2, seg=10)
            P_cyl(mb, d0 + dd * 0.62, d1, 0.017, 'Metal', T_CHROME, seg=8)
            P_torus(mb, d0 + dd * 0.62, dd, 0.036, 0.006, 'Metal', T_STEELD, seg=10, rseg=4)
            P_box(mb, C + e * 0.34 + t * (sg * 0.14), (0.07, 0.12, 0.04), 'Paint', T_HUB1, 0.008, rot=R)
            P_box(mb, C + e * 1.0 + t * (sg * 0.12), (0.06, 0.1, 0.04), 'Paint', T_HUB1, 0.008, rot=R)
        # pitch horn + pitch link down to the swashplate
        horn = C + e * 0.40 - t * 0.26 + V(0, 0, -0.03)
        P_cyl(mb, C + e * 0.66 - t * 0.1 + V(0, 0, -0.02), horn, 0.024, 'Paint', T_HUB1, seg=8)
        hd = V(horn.x, horn.y, 0).normalized()
        sw = hd * 0.31 + V(0, 0, 1.775)
        P_cyl(mb, sw, horn, 0.015, 'Metal', T_STEEL, seg=8)
        P_sphere(mb, horn, 0.028, 'Paint', T_HUB2, seg=8, rings=5)
        P_sphere(mb, sw, 0.028, 'Paint', T_HUB2, seg=8, rings=5)
        P_box(mb, sw - V(0, 0, 0.02) - V(sw.x, sw.y, 0).normalized() * 0.03, (0.07, 0.05, 0.035), 'Paint', T_HUB2, 0.006, rot=Matrix.Rotation(math.atan2(sw.y, sw.x), 3, 'Z'))
        # blade attach fork with two retention bolts
        for dz in (-0.062, 0.062):
            P_box(mb, C + e * 1.14 + V(0, 0, dz), (0.36, 0.2, 0.024), 'Paint', T_HUB2, 0.006, rot=R)
        for rr in (1.08, 1.23):
            P_cyl(mb, C + e * rr + V(0, 0, -0.09), C + e * rr + V(0, 0, 0.09), 0.03, 'Metal', T_STEEL, seg=10)
            P_cyl(mb, C + e * rr + V(0, 0, 0.09), C + e * rr + V(0, 0, 0.105), 0.018, 'Metal', T_STEELD, seg=6)
        # blade
        secs = []; tints = []
        def station(r, c, th, sweep=0.0):
            p = rad(9.0 - 8.0 * r / ROTOR_R)
            cdir = (-t * cos(p) - Z * sin(p)); upv = (Z * cos(p) - t * sin(p))
            le = C + e * r + t * (c * 0.27 - sweep) + V(0, 0, -0.0045 * r * r)
            secs.append((le, cdir, c, th, upv)); tints.append(T_YELD if r > 7.12 else tb)
        station(1.0, 0.2, 0.42)
        station(1.3, 0.4, 0.2)
        station(1.62, 0.53, 0.12)
        for r in (2.4, 3.3, 4.2, 5.1, 6.0, 6.7):
            station(r, 0.53, 0.11)
        station(7.0, 0.46, 0.1, 0.1)
        station(7.11, 0.4, 0.1, 0.16); station(7.13, 0.39, 0.1, 0.175)
        station(ROTOR_R, 0.3, 0.085, 0.3)
        TLE = (0.075, 0.078, 0.082)       # leading-edge erosion strip
        rg = [airfoil_ring(*s_, n=9) for s_ in secs]
        P_loft(mb, rg, 'Paint', tb, closed=True, cap0=True, cap1=True,
               tintfn=lambda i, j: tints[i] if tints[i] != tb else (TLE if (j <= 1 or j == 15) and 2 <= i else tb))
        # trim tabs, root doubler, tip weight pocket, static wick
        for rr in (4.3, 5.0):
            P_box(mb, C + e * rr - t * 0.4 + V(0, 0, -0.0045 * rr * rr - 0.035), (0.5, 0.07, 0.005), 'Paint', T_HUB2, rot=R)
        P_cyl(mb, C + e * 7.28 - t * 0.52 + V(0, 0, -0.26), C + e * 7.3 - t * 0.62 + V(0, 0, -0.262), 0.004, 'Paint', T_BLACK, seg=4)
    build(mb, 'MainRotor', origin=C, parent='Body')


def build_hull_details():
    mb = MB()
    # ---- tail-rotor drive shaft cover along the boom top, with bearing hangers
    yy = list(np.arange(-7.25, -2.95, 0.15))
    rings = []
    for y in yy:
        z = sp(y, 0).z
        rings.append([V(-0.075, y, z - 0.03), V(-0.075, y, z + 0.03), V(-0.045, y, z + 0.062), V(0.045, y, z + 0.062), V(0.075, y, z + 0.03), V(0.075, y, z - 0.03)])
    P_loft(mb, rings, 'HullB', T_W, closed=True, cap0=True, cap1=True)
    for y in np.arange(-6.95, -3.1, 0.64):
        z = sp(y, 0).z
        P_loft(mb, [[V(x_, y + d, z + z_) for (x_, z_) in ((-0.09, -0.03), (-0.09, 0.035), (-0.052, 0.074), (0.052, 0.074), (0.09, 0.035), (0.09, -0.03))] for d in (-0.022, 0.022)], 'Metal', T_GUND, cap0=True, cap1=True)
        for s in (-1, 1):
            P_bolt(mb, V(s * 0.068, y, z + 0.056), V(s * 0.7, 0, 0.7), 0.008, 0.006, 'Metal', T_STEELD)
    for s in (-1, 1):
        # boom stringers
        for a_ in (48, 132):
            ys_ = list(np.arange(-7.0, -3.5, 0.25)); th = rad(a_) * s
            P_sweep(mb, [sp(y, th) for y in ys_], [sn(y, th) for y in ys_], 0.022, 0.012, 0.0, 'Paint', T_OLIVE)
        # countermeasure dispenser: mount, bucket, 5x3 cartridge faces
        c = V(s * 0.275, -5.3, 0.1)
        P_box(mb, c + V(-s * 0.05, 0, 0), (0.08, 0.5, 0.26), 'Paint', T_OLIVE2, 0.02)
        P_box(mb, c + V(s * 0.005, 0, 0), (0.1, 0.4, 0.22), 'Paint', T_OLIVE, 0.012)
        for i in range(5):
            for k in range(3):
                q = c + V(s * 0.055, -0.15 + i * 0.075, -0.07 + k * 0.07)
                P_plate(mb, q, V(s, 0, 0), V(0, 0, 1), 0.058, 0.054, 0.004, 'Paint', T_BLACK)
                P_disc(mb, q + V(s * 0.004, 0, 0), V(s, 0, 0), 0.016, 'Paint', (0.10, 0.09, 0.07), seg=8)
        for dy in (-0.215, 0.215):
            for dz in (-0.1, 0.1):
                P_bolt(mb, c + V(-s * 0.01, dy, dz), V(s, 0, 0), 0.009, 0.006, 'Metal', T_GUND)
        empty('FlareR' if s > 0 else 'FlareL', V(s * 0.35, -5.3, 0.1), 'Body')
        # formation light strip, exhaust heat shield plate, raised access panels + fasteners
        ys_ = list(np.arange(-5.95, -5.69, 0.05)); th = rad(90) * s
        P_sweep(mb, [sp(y, th) for y in ys_], [sn(y, th) for y in ys_], 0.035, 0.006, 0.0, 'FormLight', T_W)
        t0, t1 = (22, 82) if s > 0 else (278, 338)
        P_patch(mb, hfn, list(np.linspace(-4.1, -3.15, 6)), list(np.linspace(t0, t1, 7)), 0.006, 'Metal', T_SOOT, skirt=0.0)
        for y in np.linspace(-4.05, -3.2, 8):
            for t in (t0 + 3, t1 - 3):
                p, n = hfn(y, t); P_disc(mb, p + n * 0.006, n, 0.006, 'Metal', T_STEELD)
        for (ya, yb, ta, tb_) in ((-4.95, -4.5, 70, 112), (-7.15, -6.75, 62, 118), (-2.35, -1.75, 96, 128), (0.25, 0.95, 98, 122)):
            if s < 0: ta, tb_ = 360 - tb_, 360 - ta
            us = list(np.linspace(ya, yb, 4)); vs = list(np.linspace(ta, tb_, 5))
            P_patch(mb, hfn, us, vs, 0.005, 'Hull', T_P9, skirt=0.0, uvfn=huv, skirt_tint=T_P5)
            for y in us:
                for t in (ta + 2.5, tb_ - 2.5):
                    p, n = hfn(y, t); P_disc(mb, p + n * 0.005, n, 0.006, 'Paint', T_RIV)
        # bolt-on appliqué armour plates beside both crew stations
        for (ya, yb) in ((1.5, 2.95), (3.3, 4.55)):
            ta, tb_ = (79.5, 99) if s > 0 else (261, 280.5)
            us = list(np.linspace(ya, yb, 9)); vs = list(np.linspace(ta, tb_, 5))
            P_patch(mb, hfn, us, vs, 0.02, 'Hull', T_P8, skirt=0.0, uvfn=huv, skirt_tint=T_P5)
            for y in np.linspace(ya + 0.05, yb - 0.05, 8):
                for t in (ta + 2.2, tb_ - 2.2):
                    p, n = hfn(y, t); P_bolt(mb, p + n * 0.02, n, 0.011, 0.006, 'Paint', T_RIV)
            for t in np.linspace(ta + 2.2, tb_ - 2.2, 4)[1:-1]:
                for y in (ya + 0.05, yb - 0.05):
                    p, n = hfn(y, t); P_bolt(mb, p + n * 0.02, n, 0.011, 0.006, 'Paint', T_RIV)
        # boom tie-down / jacking pad
        tiedown(mb, sp(-6.6, s * rad(150)), sn(-6.6, s * rad(150)), V(0, 1, 0))
    hf = [(y, sp(y, rad(62)) + sn(y, rad(62)) * 0.085) for y in np.arange(-6.9, -3.55, 0.3)]
    P_tube(mb, [sp(-6.9, rad(62))] + [p for y, p in hf] + [sp(hf[-1][0] + 0.02, rad(62))], 0.008, 'Metal', T_GUND, seg=6)
    for y, p in hf[2:-1:3]:
        P_cyl(mb, sp(y, rad(62)), p, 0.007, 'Paint', T_OLIVE2, seg=6)
        P_cyl(mb, sp(y, rad(62)), sp(y, rad(62)) + sn(y, rad(62)) * 0.02, 0.014, 'Paint', T_OLIVE2, seg=6)
    # ---- belly: antennas, doppler panel, lights, drains
    for y, h_, c_ in ((2.95, 0.2, 0.26), (-1.9, 0.24, 0.3), (-4.4, 0.2, 0.24)):
        blade_antenna(mb, sp(y, pi), V(0, 0, -1), h=h_, c=c_)
    P_patch(mb, hfn, list(np.linspace(-1.2, -0.45, 4)), list(np.linspace(163, 197, 5)), 0.012, 'Hull', T_P7, skirt=0.0, uvfn=huv, skirt_tint=T_P5)
    for y in np.linspace(-1.17, -0.48, 6):
        for t in (165, 195):
            p, n = hfn(y, t); P_disc(mb, p + n * 0.012, n, 0.007, 'Paint', T_RIV)
    P_patch(mb, hfn, list(np.linspace(0.45, 1.35, 4)), list(np.linspace(160, 200, 5)), 0.005, 'Hull', T_P9, skirt=0.0, uvfn=huv, skirt_tint=T_P5)
    a = sp(-4.95, pi); b = sp(-5.75, pi)
    handhold(mb, a, b, V(0, 0, -1), h=0.07, r=0.007, tint=T_GUND)                        # towel-rail antenna
    p = sp(-2.7, pi)
    P_revolve(mb, p + V(0, 0, 0.01), V(0, 0, -1), [(0, 0.06), (0.025, 0.055), (0.035, 0.045)], 'Paint', T_DARK, seg=12, cap0=False)
    P_sphere(mb, p + V(0, 0, -0.04), (0.04, 0.04, 0.035), 'Paint', T_RED, seg=10, rings=6)
    for y, x in ((0.2, 0.2), (-0.3, -0.22), (-1.5, 0.15), (1.7, -0.12)):
        q = sp(y, pi) + V(x, 0, 0.01)
        P_cyl(mb, q, q + V(0, -0.02, -0.06), 0.009, 'Metal', T_STEELD, seg=6)
    for y in (3.3, -0.1):
        for s in (-1, 1):
            tiedown(mb, sp(y, pi) + V(s * 0.3, 0, 0.012), V(0, 0, -1), V(0, 1, 0), 0.024)
    # ground power receptacle (left) and fire-bottle discharge discs (right)
    p, n = hfn(0.75, 262); P_plate(mb, p, n, V(0, 1, 0), 0.14, 0.2, 0.008, 'Paint', T_OLIVE2, 0.002)
    for dy in (-0.07, 0.07):
        for dz in (-0.045, 0.045):
            P_disc(mb, p + n * 0.008 + V(0, dy, dz), n, 0.006, 'Paint', T_RIV)
    for y in (-1.3, -1.45):
        p, n = hfn(y, 104); P_disc(mb, p, n, 0.03, 'Paint', T_REDD, seg=12); P_disc(mb, p, n, 0.02, 'Paint', T_YELD, seg=10, lift=0.003)
    build(mb, 'HullDetail', parent='Body')
    # ---- detachable boom hatches with a cable bay beneath
    bay = MB(); door = MB()
    us = list(np.linspace(-6.4, -5.2 + 0.0, 2)); us = list(np.linspace(-6.55, -6.05, 5)); vs = list(np.linspace(66, 114, 6))
    P_patch(bay, hfn, us[:], vs[:], 0.003, 'Paint', T_BLACK)
    for t, tn in ((78, T_YELD), (90, T_STEELD), (101, T_GUN)):
        P_tube(bay, [hfn(y, t)[0] + hfn(y, t)[1] * 0.011 for y in us], 0.007, 'Paint' if tn == T_YELD else 'Metal', tn, seg=5)
    p, n = hfn(-6.3, 88); P_plate(bay, p, n, V(0, 1, 0), 0.1, 0.14, 0.014, 'Metal', T_GUND, 0.004)
    us2 = list(np.linspace(-6.58, -6.02, 5)); vs2 = list(np.linspace(63, 117, 6))
    P_patch(door, hfn, us2, vs2, 0.022, 'Hull', T_P9, skirt=0.0, uvfn=huv, skirt_tint=T_P5)
    for y in us2:
        for t in (66, 114):
            p, n = hfn(y, t); P_disc(door, p + n * 0.022, n, 0.006, 'Paint', T_RIV)
    for t in (76, 90, 104):
        for y in (-6.56, -6.04):
            p, n = hfn(y, t); P_disc(door, p + n * 0.022, n, 0.006, 'Paint', T_RIV)
    st = MB(); st.merge(bay); st.merge(bay.mirrored())
    build(st, 'BoomBay', parent='Body')
    build(door, 'Part_BoomHatchR', parent='Body')
    build(door.mirrored(), 'Part_BoomHatchL', parent='Body')


def build_markings():
    """Low-visibility stencils as thin geometry on flat faces (each side written separately so text is not mirrored)."""
    mb = MB()
    XO = 0.87
    for s in (-1, 1):
        nx = V(s, 0, 0); upz = V(0, 0, 1)
        f = XO + 0.001
        stencil(mb, 'AVIONICS BAY 2', 0.032, V(s * (f + 0.02), 2.6, -0.33), nx, upz)
        stencil(mb, 'NO PUSH', 0.028, V(s * (f + 0.02), 2.6, -0.66), nx, upz)
        stencil(mb, 'AVIONICS BAY 1', 0.03, V(s * (f + 0.006), 3.55, -0.36), nx, upz)
        stencil(mb, 'HYD SERVICE', 0.03, V(s * (f + 0.006), 0.95, -0.36), nx, upz)
        stencil(mb, 'CHECK PRESSURE BEFORE FLIGHT', 0.016, V(s * (f + 0.006), 0.95, -0.42), nx, upz)
        stencil(mb, 'STEP', 0.035, V(s * f, 3.85, -0.62), nx, upz)
        stencil(mb, 'SW-07', 0.11, V(s * f, 1.75, -0.5), nx, upz, tint=T_DARK)
        # fin: tail number + rotor warning
        p, n = afs(FIN_A, FIN_B, 0.52, 0.5, s, V(1, 0, 0))
        stencil(mb, '07', 0.2, p, n, upz, tint=T_DARK, lift=0.004)
        p, n = afs(FIN_B, FIN_C, 0.72, 0.42, s, V(1, 0, 0))
        stencil(mb, 'DANGER', 0.055, p, n, upz, tint=T_YELD, lift=0.004)
        # wings: no-step on the flap, hoist point
        p, n = wsurf(0.5, 0.86); p = V(p.x * s, p.y, p.z); n = V(n.x * s, n.y, n.z)
        stencil(mb, 'NO STEP', 0.05, p, n, V(-s, 0, 0))
        p, n = wsurf(0.28, 0.86); p = V(p.x * s, p.y, p.z); n = V(n.x * s, n.y, n.z)
        stencil(mb, 'NO STEP', 0.05, p, n, V(-s, 0, 0))
        p, n = wsurf(0.75, 0.08); p = V(p.x * s, p.y, p.z); n = V(n.x * s, n.y, n.z)
        stencil(mb, 'HOIST', 0.03, p, n, V(-s, 0, 0))
        # spine side
        stencil(mb, 'XMSN OIL', 0.03, spine_side(-0.05, 0.965, s) + spine_n(0, s) * 0.0, spine_n(0, s), upz)
        stencil(mb, 'HAND HOLD', 0.022, spine_side(0.4, 0.8, s), spine_n(0.4, s), upz)
    stencil(mb, 'WALKWAY', 0.04, V(0, 0.5, 1.412), V(0, 0, 1), V(0, 1, 0))
    build(mb, 'Markings', parent='Body')


# ------------------------------------------------------------------ cockpit (separate file, same namespace)
exec(compile(open(os.path.join(HERE, 'heli_cockpit.py'), encoding='utf-8').read(), 'heli_cockpit.py', 'exec'), globals())

# ------------------------------------------------------------------ main
def main():
    fc, fn, fo = heli_tex.make_fuse(TEXD, YMIN, YMAX, circ)
    gc, gn, go = heli_tex.make_generic(TEXD)
    print('textures', time.time() - T0)
    mk_mat('Hull', metal=0.1, rough=0.62, tex=fc, nrm=fn, orm=fo)
    mk_mat('HullB', metal=0.1, rough=0.62, tex=gc, nrm=gn, orm=go)
    mk_mat('Paint', rough=0.66)
    mk_mat('Metal', metal=0.9, rough=0.5)
    mk_mat('Rubber', base=(0.014, 0.014, 0.015), rough=0.92)
    mk_mat('Glass', base=(0.03, 0.05, 0.05), rough=0.04, alpha=0.28)
    mk_mat('Lens', base=(0.015, 0.02, 0.035), metal=0.6, rough=0.06)
    mk_mat('GaugeMark', base=(0.8, 0.85, 0.8), emit=(0.75, 0.9, 0.75), emit_s=0.6)
    mk_mat('Needle', base=(1.0, 0.45, 0.1), emit=(1.0, 0.4, 0.08), emit_s=1.0)
    mk_mat('FormLight', base=(0.16, 0.26, 0.15), emit=(0.35, 0.8, 0.3), emit_s=0.12)
    mk_mat('MFD_L', base=(0.01, 0.03, 0.02), rough=0.2, emit=(0.02, 0.12, 0.05), emit_s=1.0)
    mk_mat('MFD_R', base=(0.01, 0.03, 0.02), rough=0.2, emit=(0.02, 0.12, 0.05), emit_s=1.0)
    for nm, colr in (('Warn_Master', (0.9, 0.05, 0.03)), ('Warn_Engine', (0.9, 0.45, 0.03)), ('Warn_Tail', (0.9, 0.45, 0.03)),
                     ('Warn_Hyd', (0.9, 0.45, 0.03)), ('Warn_Rotor', (0.9, 0.05, 0.03))):
        mk_mat(nm, base=tuple(c * 0.25 for c in colr), rough=0.3, emit=colr, emit_s=0.15)

    cockpit_mats()
    build_fuselage()
    OBJS['Cockpit_'] = OBJS['Body']; WORLD['Cockpit_'] = WORLD['Body']
    build_canopy()
    build_nose(); build_turret(); build_nacelles(); build_doghouse(); build_cheeks()
    build_wings(); build_tail(); build_gear(); build_rotor(); build_hull_details(); build_markings()
    print('exterior', time.time() - T0)
    ext = 0
    for ob in bpy.data.objects:
        if ob.type == 'MESH':
            ob.data.calc_loop_triangles(); ext += len(ob.data.loop_triangles)
    build_cockpit()
    # re-parent MFDs under Cockpit
    for nm in ('MFD_L', 'MFD_R'):
        if nm in OBJS and 'Cockpit' in OBJS: OBJS[nm].parent = OBJS['Cockpit']
    del OBJS['Cockpit_']; del WORLD['Cockpit_']
    print('geometry', time.time() - T0)
    if 'noao' not in ARGS:
        bake_ao()
    print('ao', time.time() - T0)
    bpy.context.view_layer.update()
    tris = 0
    for ob in bpy.data.objects:
        if ob.type == 'MESH':
            ob.data.calc_loop_triangles(); tris += len(ob.data.loop_triangles)
    print('TRIS total', tris, 'exterior', ext)
    # ---- export
    kw = dict(filepath=OUT, export_format='GLB', export_apply=True, export_yup=True, export_normals=True,
              export_texcoords=True, export_materials='EXPORT', export_animations=False, export_extras=False,
              export_image_format='AUTO')
    try:
        bpy.ops.export_scene.gltf(export_vertex_color='ACTIVE', export_all_vertex_colors=False, **kw)
    except TypeError as e:
        print('export fallback', e)
        bpy.ops.export_scene.gltf(**kw)
    print('exported', OUT, os.path.getsize(OUT), time.time() - T0)
    open(os.path.join(HERE, 'heli_info.txt'), 'w').write('tris %d (exterior %d)\n' % (tris, ext))
    if 'nopreview' not in ARGS:
        import heli_preview
        importlib.reload(heli_preview)
        heli_preview.render(PREV, MATS, EYE, ARGS)
        print('preview', time.time() - T0)

main()
