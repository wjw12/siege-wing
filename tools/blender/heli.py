# Siege Wing hero helicopter generator (original design). Run headless:
#   blender.exe -b -P heli.py [-- nopreview]
import bpy, bmesh, sys, os, math, time
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
ROTOR_Z = 2.2
ROTOR_R = 7.3
GEAR_Z = -1.75
EYE = V(0, 1.91, 0.92)
TR_HUB = V(0.36, -8.35, 1.2)

T_W = (1, 1, 1)
T_OLIVE = (0.092, 0.104, 0.049)
T_OLIVE2 = (0.06, 0.07, 0.04)
T_DARK = (0.022, 0.024, 0.022)
T_BLACK = (0.006, 0.006, 0.007)
T_INT = (0.03, 0.032, 0.035)
T_INT2 = (0.055, 0.058, 0.06)
T_STEEL = (0.42, 0.42, 0.44)
T_GUN = (0.09, 0.09, 0.10)
T_BURNT = (0.16, 0.12, 0.09)
T_SUIT = (0.13, 0.125, 0.075)
T_VEST = (0.04, 0.05, 0.035)
T_HELM = (0.10, 0.11, 0.09)
T_FABRIC = (0.07, 0.075, 0.05)
T_YEL = (0.75, 0.52, 0.04)
T_RED = (0.6, 0.03, 0.02)
T_GRN = (0.03, 0.5, 0.08)

# ------------------------------------------------------------------ materials
def mk_mat(name, base=(1, 1, 1), metal=0.0, rough=0.6, emit=None, emit_s=1.0, alpha=1.0, tex=None, nrm=None):
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
        nm = nt.nodes.new('ShaderNodeNormalMap'); nm.inputs['Strength'].default_value = 1.0
        nt.links.new(t.outputs['Color'], nm.inputs['Color'])
        nt.links.new(nm.outputs['Normal'], b.inputs['Normal'])
    MATS[name] = m
    return m

# ------------------------------------------------------------------ fuselage sections
KEYS = [  # y, w, ztop, zbot, zmid, nt, nb
    (6.20, 0.10, -0.12, -0.44, -0.28, 2.0, 2.0),
    (6.00, 0.27, 0.00, -0.60, -0.28, 2.2, 2.2),
    (5.50, 0.41, 0.08, -0.76, -0.25, 2.4, 2.6),
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
    (-5.00, 0.21, 0.32, -0.16, 0.08, 2.1, 2.1),
    (-7.40, 0.15, 0.24, -0.08, 0.08, 2.0, 2.0),
    (-8.40, 0.09, 0.20, 0.00, 0.10, 2.0, 2.0),
]
_K = np.array(sorted(KEYS))
_fy = np.arange(YMIN - 0.5, YMAX + 0.5, 0.01)
_fp = np.stack([np.interp(_fy, _K[:, 0], _K[:, c]) for c in range(1, 7)], 1)
ker = np.ones(21) / 21
for _ in range(2):
    pad = np.pad(_fp, ((10, 10), (0, 0)), mode='edge')
    _fp = np.stack([np.convolve(pad[:, c], ker, mode='valid') for c in range(6)], 1)

def sec_params(y):
    return [float(np.interp(y, _fy, _fp[:, c])) for c in range(6)]

def sp(y, th, prm=None):
    w, zt, zb, zm, nt, nb = prm or sec_params(y)
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

def stations():
    ys = [round(YMAX - 0.1 * k, 3) for k in range(0, 13)]           # 6.2 .. 5.0
    ys += [round(4.95 - 0.05 * k, 3) for k in range(0, 73)]        # 4.95 .. 1.35
    y = 1.2
    while y > YMIN + 0.01:
        ys.append(round(y, 3)); y -= 0.15
    ys.append(YMIN)
    return ys

# ------------------------------------------------------------------ build parts
def build_fuselage():
    ys = stations()
    rings = [[sp(y, 2 * pi * j / N) for j in range(N)] for y in ys]
    c0 = sum(rings[0], V(0, 0, 0)) / N
    caps = []; cys = []
    for t in (0.97, 0.88, 0.72, 0.5, 0.25):
        k = math.sqrt(1 - t * t)
        caps.append([c0 + (p - c0) * k + V(0, t * 0.2, 0) for p in rings[0]]); cys.append(YMAX + t * 0.2)
    rings = caps + rings; ys = cys + ys
    Lf = YMAX - YMIN
    uvfn = lambda i, j: (j / N, (ys[i] - YMIN) / Lf)
    def is_glass(i, j):
        return ys[i] <= YG1 + 1e-6 and ys[i + 1] >= YG0 - 1e-6 and (j < JG or j >= N - JG)
    hull = MB()
    P_loft(hull, rings, 'Hull', T_W, cap0=True, cap1=True, uvfn=uvfn,
           matfn=lambda i, j: None if is_glass(i, j) else 'Hull')
    glass = MB()
    P_loft(glass, rings, 'Glass', T_W, uvfn=uvfn, matfn=lambda i, j: 'Glass' if is_glass(i, j) else None)

    # ---- canopy frames (hull mesh, painted dark olive)
    fr = hull
    def ring_frame(y, w=0.06, a0=-75, a1=75):
        ths = [rad(a) for a in np.arange(a0, a1 + 0.1, 2.5)]
        P_sweep(fr, [sp(y, t) for t in ths], [sn(y, t) for t in ths], w, 0.012, 0.03, 'Paint', T_OLIVE2)
    def long_frame(th, y0, y1, w=0.05):
        yy = list(np.arange(y0, y1 + 0.001, 0.05))
        P_sweep(fr, [sp(y, th) for y in yy], [sn(y, th) for y in yy], w, 0.012, 0.03, 'Paint', T_OLIVE2)
    for y, w_ in ((1.37, 0.06), (2.58, 0.042), (3.12, 0.042), (3.92, 0.05)):
        ring_frame(y, w_)
    ring_frame(4.93, 0.05)
    for s in (-1, 1):
        long_frame(s * THS, YG0, YG1, 0.07)
        long_frame(s * rad(37.5), 1.37, 2.58, 0.036)
        long_frame(s * rad(37.5), 3.12, 3.92, 0.036)
        long_frame(s * rad(30), 3.92, 4.93, 0.045)
    long_frame(0, 1.37, 2.58, 0.045)

    # ---- interior tub
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
        ids = [tub.addv(p, T_INT) for p in pts]
        # ring is clockwise seen from +Y (theta goes top -> +x); normal of ids order:
        c = sum(pts, V(0, 0, 0)) / N
        nr = V(0, 0, 0)
        for k in range(N): nr += (pts[k] - c).cross(pts[(k + 1) % N] - c)
        if nr.y * nrm < 0: ids.reverse()
        tub.addf(ids, 'Paint')

    # ---- drive-shaft cover along boom top + clamps
    yy = list(np.arange(-7.15, -2.7, 0.15))
    P_sweep(hull, [sp(y, 0) + V(0, 0, 0.0) for y in yy], [V(0, 0, 1)] * len(yy), 0.13, 0.05, 0.02, 'HullB', T_W)
    for y in np.arange(-6.9, -2.9, 0.62):
        P_box(hull, sp(y, 0) + V(0, 0, 0.03), (0.16, 0.035, 0.06), 'Metal', T_GUN, 0.006)
    # belly strakes / antenna
    for y, zoff in ((-3.6, 0), (2.4, 0)):
        p = sp(y, pi)
        P_airfoil(hull, [(p + V(0, 0.18, 0.02), V(0, -1, 0), 0.36, 0.10, V(1, 0, 0)),
                         (p + V(0, 0.08, -0.22), V(0, -1, 0), 0.2, 0.10, V(1, 0, 0))], 'Paint', T_DARK)
    p = sp(-4.3, 0)
    P_airfoil(hull, [(p + V(0, 0.15, 0.03), V(0, -1, 0), 0.3, 0.1, V(1, 0, 0)),
                     (p + V(0, 0.02, 0.3), V(0, -1, 0), 0.16, 0.1, V(1, 0, 0))], 'Paint', T_DARK)
    # formation light strips on fuselage sides
    for s in (-1, 1):
        yy = list(np.arange(-5.6, -4.9, 0.1))
        th = rad(90) * s
        P_sweep(hull, [sp(y, th) for y in yy], [sn(y, th) for y in yy], 0.035, 0.006, 0.0, 'FormLight', T_W)
    build(hull, 'Body')
    build(glass, 'Canopy', parent='Body')


def build_nose():
    mb = MB()
    # sensor ball under the nose
    c = V(0, 5.82, -0.74)
    P_revolve(mb, V(0, 5.82, -0.5), V(0, 0, -1), [(0, 0.2), (0.12, 0.2), (0.15, 0.16)], 'Paint', T_OLIVE2, seg=20, cap0=False)
    P_sphere(mb, c, 0.2, 'Paint', T_OLIVE2, seg=24, rings=14)
    for s_ in (-1, 1):
        P_cyl(mb, c + V(s_ * 0.2, 0, 0), c + V(s_ * 0.235, 0, 0), 0.09, 'Paint', T_DARK, seg=14)
    for x, r in ((-0.075, 0.07), (0.085, 0.055)):
        p = c + V(x, 0.165, 0.02)
        P_revolve(mb, p, V(0, 1, 0), [(0, r + 0.022), (0.035, r + 0.016), (0.035, r), (0.02, r * 0.95)], 'Paint', T_BLACK, seg=16, cap1=False)
        P_revolve(mb, p, V(0, 1, 0), [(0.02, r)], 'Lens', T_W, seg=16)
    # night-vision ball above nose
    P_cyl(mb, V(0, 5.72, 0.03), V(0, 5.72, 0.16), 0.09, 'Paint', T_OLIVE2, seg=14)
    P_sphere(mb, V(0, 5.72, 0.24), 0.15, 'Paint', T_OLIVE2, seg=18, rings=12)
    P_revolve(mb, V(0, 5.84, 0.24), V(0, 1, 0), [(0, 0.085), (0.03, 0.08)], 'Lens', T_W, seg=16)
    # pitot probes
    for s in (-1, 1):
        P_cyl(mb, V(s * 0.38, 5.55, -0.1), V(s * 0.44, 5.6, -0.1), 0.012, 'Metal', T_STEEL, seg=6)
        P_cyl(mb, V(s * 0.44, 5.56, -0.1), V(s * 0.44, 5.95, -0.1), 0.011, 'Metal', T_STEEL, seg=6)
    # lower wire cutter + search light
    P_airfoil(mb, [(V(0, 5.2, -0.78), V(0, -1, 0), 0.22, 0.08, V(1, 0, 0)),
                   (V(0, 5.34, -1.06), V(0, -1, 0), 0.06, 0.08, V(1, 0, 0))], 'Metal', T_GUN)
    P_revolve(mb, V(0.26, 5.05, -0.74), V(0, 0.3, -1), [(0, 0.07), (0.08, 0.075), (0.085, 0.06)], 'Paint', T_DARK, seg=14)
    P_revolve(mb, V(0.26, 5.05, -0.74), V(0, 0.3, -1), [(0.087, 0.06)], 'Lens', T_W, seg=14)
    # upper wire cutter over canopy step
    P_airfoil(mb, [(V(0, 2.75, 1.22), V(0, -1, 0), 0.24, 0.08, V(1, 0, 0)),
                   (V(0, 2.98, 1.58), V(0, -1, 0), 0.06, 0.08, V(1, 0, 0))], 'Metal', T_GUN)
    # windshield wiper
    th = rad(12)
    yy = [4.85, 4.6, 4.35]
    P_sweep(mb, [sp(y, th) for y in yy], [sn(y, th) for y in yy], 0.018, 0.03, -0.012, 'Paint', T_BLACK)
    # grab handles + steps left side
    for y in (2.3, 3.5):
        th = rad(-100)
        a = sp(y - 0.12, th); b = sp(y + 0.12, th); n = sn(y, th)
        P_cyl(mb, a, a + n * 0.05, 0.008, 'Metal', T_GUN, seg=6); P_cyl(mb, b, b + n * 0.05, 0.008, 'Metal', T_GUN, seg=6)
        P_cyl(mb, a + n * 0.05, b + n * 0.05, 0.008, 'Metal', T_GUN, seg=6)
    # canopy door handles/hinges (right side doors)
    for y in (2.0, 3.5):
        th = rad(78)
        P_box(mb, sp(y, th) + sn(y, th) * 0.012, (0.02, 0.12, 0.03), 'Metal', T_GUN, 0.004)
    build(mb, 'NoseDetail', parent='Body')
    empty('Light_Search', V(0.26, 5.08, -0.83), 'Body')


def build_turret():
    piv = V(0, 4.35, -0.86)
    mb = MB()   # static mount ring on belly
    P_revolve(mb, piv + V(0, 0, 0.06), V(0, 0, -1), [(0, 0.34), (0.06, 0.34), (0.09, 0.30)], 'Paint', T_OLIVE2, seg=24, cap0=False)
    # ammo feed chute from fuselage to turret (static, flexible look)
    pts = [V(0.24, 3.75, -0.84), V(0.27, 3.9, -0.93), V(0.25, 4.1, -0.98), V(0.2, 4.25, -0.98)]
    P_sweep(mb, pts, [V(0, 0, -1)] * 4, 0.11, 0.035, 0.035, 'Metal', T_GUN)
    build(mb, 'TurretMount', parent='Body')

    ty = MB()   # yawing part
    P_revolve(ty, piv + V(0, 0, -0.03), V(0, 0, -1), [(0, 0.29), (0.05, 0.29), (0.10, 0.22), (0.12, 0.14)], 'Metal', T_GUN, seg=24, cap0=False)
    for s in (-1, 1):   # cradle arms
        P_box(ty, piv + V(s * 0.15, 0.02, -0.22), (0.04, 0.34, 0.26), 'Metal', T_GUN, 0.01)
        P_cyl(ty, piv + V(s * 0.13, 0, -0.29), piv + V(s * 0.19, 0, -0.29), 0.05, 'Metal', T_STEEL, seg=12)
    build(ty, 'TurretYaw', origin=piv, parent='Body')

    gp = piv + V(0, 0, -0.29)
    g = MB()
    P_box(g, gp + V(0, -0.02, 0), (0.2, 0.62, 0.17), 'Metal', T_GUN, 0.015)             # receiver
    P_box(g, gp + V(0, -0.25, 0.02), (0.24, 0.2, 0.2), 'Metal', T_GUN, 0.015)           # motor housing
    P_box(g, gp + V(0.13, -0.05, 0.02), (0.08, 0.3, 0.12), 'Metal', T_GUN, 0.01)        # feed box
    P_revolve(g, gp + V(0, 0.29, 0), V(0, 1, 0),
              [(0, 0.07), (0.3, 0.07), (0.32, 0.05), (0.5, 0.05), (0.52, 0.036), (0.98, 0.032), (1.0, 0.046), (1.2, 0.046), (1.22, 0.03)],
              'Metal', T_GUN, seg=14)
    for k in range(6):   # muzzle brake slots (dark)
        a = k * pi / 3
        P_box(g, gp + V(0.047 * cos(a), 1.39, 0.047 * sin(a)), (0.012, 0.12, 0.012), 'Paint', T_BLACK, rot=Matrix.Rotation(-a, 3, 'Y'))
    P_cyl(g, gp + V(0, 0.3, -0.07), gp + V(0, 0.75, -0.06), 0.022, 'Metal', T_STEEL, seg=8)   # recoil buffer
    P_cyl(g, gp + V(0, 0.3, 0.075), gp + V(0, 0.62, 0.065), 0.018, 'Metal', T_STEEL, seg=8)
    build(g, 'GunPitch', origin=gp, parent='TurretYaw')
    empty('Muzzle', gp + V(0, 1.53, 0), 'GunPitch')


def nacelle_side():
    """Right-hand nacelle; returns (static MB, cowl MB)."""
    mb = MB(); cowl = MB()
    cx, cz = 0.86, 0.52
    keys = [(1.05, 0.27, 0.27), (0.85, 0.325, 0.335), (0.5, 0.36, 0.38), (-1.2, 0.36, 0.38), (-1.9, 0.31, 0.32), (-2.25, 0.26, 0.26)]
    ka = np.array(keys)
    ys = [1.05, 0.95, 0.85, 0.7, 0.55, 0.3, 0.0, -0.3, -0.6, -0.9, -1.1, -1.3, -1.6, -1.9, -2.1, -2.25]
    NN = 24
    def pt(y, j, off=0.0):
        a = float(np.interp(y, ka[::-1, 0], ka[::-1, 1])) + off; b = float(np.interp(y, ka[::-1, 0], ka[::-1, 2])) + off
        th = 2 * pi * j / NN
        s, c = sin(th), cos(th); n = 3.0
        return V(cx + a * math.copysign(abs(s) ** (2 / n), s), y, cz + b * math.copysign(abs(c) ** (2 / n), c))
    def is_cowl(i, j):
        return 0.55 >= ys[i] and ys[i + 1] >= -1.1 - 1e-6 and 2 <= j < 10
    rings = [[pt(y, j) for j in range(NN)] for y in ys]
    P_loft(mb, rings, 'HullB', T_W, matfn=lambda i, j: None if is_cowl(i, j) else 'HullB')
    rings2 = [[pt(y, j, 0.006) for j in range(NN)] for y in ys]
    P_loft(cowl, rings2, 'HullB', T_W, matfn=lambda i, j: 'HullB' if is_cowl(i, j) else None)
    # cowl latches
    for y in (0.3, -0.3, -0.9):
        P_box(cowl, pt(y, 2.2, 0.012), (0.03, 0.07, 0.012), 'Metal', T_GUN, 0.003)
        P_box(cowl, pt(y, 9.8, 0.012), (0.012, 0.07, 0.03), 'Metal', T_GUN, 0.003)
    # cowl louvres
    for k in range(5):
        P_box(cowl, pt(-0.55 - k * 0.09, 6, 0.008), (0.012, 0.03, 0.22), 'Paint', T_BLACK)
    # engine bay under the cowl (dark)
    rings3 = [[pt(y, j, -0.07) for j in range(NN)] for y in ys]
    P_loft(mb, rings3, 'Paint', T_BLACK, matfn=lambda i, j: 'Paint' if is_cowl(i, j) else None)
    for i in (4, 10):   # bay end walls
        ids = [mb.addv(pt(ys[i], j, -0.07 if k else 0), T_BLACK) for j in range(2, 11) for k in (0, 1)]
        for q in range(8):
            a, b, c, d = ids[q * 2], ids[q * 2 + 1], ids[q * 2 + 3], ids[q * 2 + 2]
            dquad(mb, [mb.v[q_] for q_ in (a, b, c, d)], 'Paint', T_BLACK)
    for j in (2, 10):   # bay side walls
        ids = [mb.addv(pt(ys[i], j, -0.07 if k else 0), T_BLACK) for i in range(4, 11) for k in (0, 1)]
        for q in range(6):
            a, b, c, d = ids[q * 2], ids[q * 2 + 1], ids[q * 2 + 3], ids[q * 2 + 2]
            dquad(mb, [mb.v[q_] for q_ in (a, b, c, d)], 'Paint', T_BLACK)
    # engine core visible when cowl is gone
    P_revolve(mb, V(cx + 0.06, 0.5, cz), V(0, -1, 0), [(0, 0.2), (0.3, 0.24), (0.5, 0.24), (0.55, 0.2), (0.9, 0.2), (0.95, 0.25), (1.3, 0.25), (1.55, 0.22)], 'Metal', T_GUN, seg=14, cap0=False, cap1=False)
    for k in range(4):
        y = 0.35 - k * 0.38
        P_torus(mb, V(cx + 0.06, y, cz), V(0, 1, 0), 0.25, 0.016, 'Metal', T_STEEL, seg=14, rseg=5)
    P_cyl(mb, V(cx + 0.3, 0.4, cz + 0.1), V(cx + 0.3, -0.95, cz + 0.14), 0.02, 'Metal', T_BURNT, seg=6)
    P_cyl(mb, V(cx + 0.31, 0.3, cz - 0.08), V(cx + 0.31, -0.7, cz - 0.1), 0.014, 'Metal', T_STEEL, seg=6)
    # intake
    P_torus(mb, V(cx, 1.05, cz), V(0, 1, 0), 0.262, 0.03, 'Metal', T_GUN, seg=24, rseg=8)
    P_revolve(mb, V(cx, 1.05, cz), V(0, -1, 0), [(0, 0.26), (0.12, 0.22), (0.12, 0.0005)], 'Paint', T_BLACK, seg=24, cap0=False, cap1=False, flip=True)
    P_revolve(mb, V(cx, 0.93, cz), V(0, 1, 0), [(0, 0.1), (0.1, 0.09), (0.19, 0.05), (0.23, 0.0005)], 'Metal', T_GUN, seg=14, cap0=False, cap1=False)
    for k in range(6):
        a = k * pi / 3
        P_box(mb, V(cx + 0.16 * cos(a), 0.96, cz + 0.16 * sin(a)), (0.15, 0.02, 0.012), 'Metal', T_GUN, rot=Matrix.Rotation(-a, 3, 'Y'))
    # exhaust duct (upturned, outward)
    path = [V(cx, -2.2, cz), V(cx + 0.03, -2.45, cz + 0.03), V(cx + 0.10, -2.7, cz + 0.11), V(cx + 0.2, -2.92, cz + 0.24)]
    er = []
    for k, p in enumerate(path):
        t = (path[min(k + 1, 3)] - path[max(k - 1, 0)]).normalized()
        R = rot_to(t); r = 0.265 - 0.012 * k
        er.append([p + R @ V(r * cos(2 * pi * q / 18), r * sin(2 * pi * q / 18), 0) for q in range(18)])
    P_loft(mb, er, 'Metal', T_BURNT)
    tl = (path[3] - path[2]).normalized()
    R = rot_to(tl)
    inner = [[p + R @ V(rr * cos(2 * pi * q / 18), rr * sin(2 * pi * q / 18), 0) for q in range(18)]
             for p, rr in ((path[3], 0.229), (path[3] - tl * 0.18, 0.2))]
    P_loft(mb, inner, 'Paint', T_BLACK, inward=True, ref=path[3] - tl * 0.09)
    dquad(mb, inner[1], 'Paint', T_BLACK)
    P_torus(mb, path[3], tl, 0.229, 0.014, 'Metal', T_BURNT, seg=18, rseg=6)
    # pylon fairing joining nacelle to fuselage + louvre grille on top
    P_box(mb, V(0.6, -0.45, 0.62), (0.3, 2.5, 0.42), 'HullB', T_W, 0.06, seg=2)
    for k in range(7):
        P_box(mb, V(cx, -1.35 - k * 0.07, cz + 0.385 - k * 0.004), (0.3, 0.025, 0.012), 'Paint', T_BLACK)
    return mb, cowl, path[3] + tl * 0.05


def build_nacelles():
    mb, cowl, ex = nacelle_side()
    st = MB(); st.merge(mb); st.merge(mb.mirrored())
    build(st, 'Nacelles', parent='Body')
    build(cowl, 'Part_CowlR', parent='Body')
    build(cowl.mirrored(), 'Part_CowlL', parent='Body')
    empty('Exhaust_R', ex, 'Body'); empty('Exhaust_L', V(-ex.x, ex.y, ex.z), 'Body')


def build_doghouse():
    mb = MB()
    # mast fairing + static mast + swashplate (non rotating half)
    P_revolve(mb, V(0, 0, 1.2), V(0, 0, 1), [(0, 0.46), (0.14, 0.4), (0.34, 0.26), (0.4, 0.17)], 'HullB', T_W, seg=20, cap0=False)
    P_cyl(mb, V(0, 0, 1.5), V(0, 0, ROTOR_Z - 0.1), 0.1, 'Metal', T_GUN, seg=14)
    P_revolve(mb, V(0, 0, 1.68), V(0, 0, 1), [(0, 0.14), (0.01, 0.28), (0.05, 0.28), (0.06, 0.14)], 'Metal', T_GUN, seg=20)
    for k in range(3):   # servo actuators
        a = k * 2 * pi / 3 + 0.5
        P_cyl(mb, V(0.22 * cos(a), 0.22 * sin(a), 1.42), V(0.23 * cos(a), 0.23 * sin(a), 1.69), 0.028, 'Metal', T_STEEL, seg=8)
        P_cyl(mb, V(0.22 * cos(a), 0.22 * sin(a), 1.36), V(0.22 * cos(a), 0.22 * sin(a), 1.58), 0.042, 'Metal', T_GUN, seg=8)
    # IR jammer drum behind mast
    P_cyl(mb, V(0, -1.05, 1.24), V(0, -1.05, 1.36), 0.07, 'Paint', T_OLIVE2, seg=10)
    P_revolve(mb, V(0, -1.05, 1.36), V(0, 0, 1), [(0, 0.09), (0.02, 0.12), (0.2, 0.12), (0.22, 0.09)], 'Lens', T_W, seg=10)
    # GPS dome, beacon
    P_sphere(mb, V(0, 0.75, 1.31), (0.1, 0.14, 0.05), 'Paint', T_OLIVE2, seg=12, rings=6)
    P_cyl(mb, V(0, -1.75, 1.05), V(0, -1.75, 1.12), 0.04, 'Paint', T_DARK, seg=10)
    P_sphere(mb, V(0, -1.75, 1.13), 0.045, 'Paint', T_RED, seg=10, rings=6)
    # doghouse side louvres
    for s in (-1, 1):
        for k in range(6):
            y = 0.45 - k * 0.08
            th = rad(25) * s
            P_box(mb, sp(y, th) + sn(y, th) * 0.004, (0.16, 0.03, 0.012), 'Paint', T_BLACK, rot=Matrix.Rotation(-th, 3, 'Y'))
    # flare dispensers on boom sides
    for s in (-1, 1):
        c = V(s * 0.27, -5.3, 0.1)
        P_box(mb, c, (0.12, 0.34, 0.2), 'Paint', T_OLIVE2, 0.015)
        for i in range(4):
            for k in range(3):
                P_box(mb, c + V(s * 0.062, -0.12 + i * 0.08, -0.06 + k * 0.06), (0.006, 0.05, 0.04), 'Paint', T_BLACK)
        empty('FlareR' if s > 0 else 'FlareL', c + V(s * 0.08, 0, 0), 'Body')
    for s in (-1, 1):
        # exhaust heat shields + boom stiffeners
        for a_ in (50, 128):
            yy = list(np.arange(-7.0, -4.5, 0.25)); th = rad(a_) * s
            P_sweep(mb, [sp(y, th) for y in yy], [sn(y, th) for y in yy], 0.02, 0.012, 0.0, 'HullB', T_W)
        # doghouse equipment
        P_box(mb, V(s * 0.24, -0.62, 1.29), (0.2, 0.5, 0.1), 'HullB', T_W, 0.025, seg=2)
        P_cyl(mb, V(s * 0.22, 0.5, 1.26), V(s * 0.22, 0.2, 1.3), 0.05, 'Metal', T_GUN, seg=10)
        P_box(mb, V(s * 0.3, 1.0, 1.2), (0.12, 0.3, 0.06), 'Paint', T_BLACK, 0.01)          # anti-slip step
        for k in range(3):       # tie-down rings / hand holds on deck
            P_torus(mb, V(s * 0.43, 0.6 - k * 0.9, 1.07 - k * 0.02), V(0, 1, 0), 0.03, 0.006, 'Metal', T_STEEL, seg=10, rseg=4)
    P_box(mb, V(0, -2.1, 0.93), (0.3, 0.5, 0.06), 'Paint', T_BLACK, 0.01)      # top grille
    for k in range(6):
        P_box(mb, V(0, -1.9 - k * 0.07, 0.965), (0.26, 0.02, 0.012), 'Metal', T_GUN)
    build(mb, 'TopDetail', parent='Body')
    empty('Light_Beacon', V(0, -1.75, 1.2), 'Body')


def build_cheeks():
    def side():
        mb = MB(); door = MB()
        keys = np.array([(4.55, 0.02, 0.05), (4.2, 0.2, 0.26), (3.4, 0.25, 0.31), (0.2, 0.25, 0.31), (-0.6, 0.2, 0.26), (-1.15, 0.02, 0.05)])
        ys = [4.55, 4.4, 4.2, 3.9, 3.4, 2.6, 1.8, 1.0, 0.2, -0.2, -0.6, -0.9, -1.15]
        rings = []
        for y in ys:
            a = float(np.interp(y, keys[::-1, 0], keys[::-1, 1])); b = float(np.interp(y, keys[::-1, 0], keys[::-1, 2]))
            r = []
            for j in range(20):
                th = 2 * pi * j / 20; s, c = sin(th), cos(th); n = 4.0
                r.append(V(0.6 + a * math.copysign(abs(s) ** (2 / n), s), y, -0.5 + b * math.copysign(abs(c) ** (2 / n), c)))
            rings.append(r)
        P_loft(mb, rings, 'HullB', T_W, cap0=True, cap1=True)
        # avionics bay (dark slab + boxes) under the door
        P_box(mb, V(0.851, 2.6, -0.5), (0.008, 1.02, 0.44), 'Paint', T_BLACK)
        for k, (yy, zz, sy, sz) in enumerate(((2.25, -0.42, 0.22, 0.2), (2.55, -0.45, 0.26, 0.26), (2.9, -0.4, 0.3, 0.18), (2.9, -0.61, 0.3, 0.14), (2.25, -0.62, 0.2, 0.1))):
            P_box(mb, V(0.857, yy, zz), (0.014, sy, sz), 'Metal', T_GUN if k % 2 else T_STEEL, 0.004)
        P_cyl(mb, V(0.86, 2.15, -0.52), V(0.86, 3.05, -0.52), 0.008, 'Paint', T_YEL, seg=5)
        P_box(door, V(0.868, 2.6, -0.5), (0.016, 1.06, 0.48), 'HullB', T_W, 0.006)
        for yy in (2.2, 3.0):
            P_box(door, V(0.878, yy, -0.3), (0.008, 0.06, 0.025), 'Metal', T_GUN, 0.002)
            P_box(door, V(0.878, yy, -0.7), (0.008, 0.04, 0.04), 'Metal', T_GUN, 0.002)
        # second (fixed) panel outlines + step + vents
        P_box(mb, V(0.852, 0.9, -0.5), (0.006, 0.9, 0.44), 'HullB', T_W, 0.002)
        for k in range(6):
            P_box(mb, V(0.853, -0.1 - k * 0.06, -0.45), (0.006, 0.025, 0.26), 'Paint', T_BLACK)
        P_box(mb, V(0.9, 3.55, -0.74), (0.12, 0.22, 0.02), 'Metal', T_GUN, 0.005)
        P_box(mb, V(0.9, 2.0, -0.2), (0.12, 0.3, 0.015), 'Paint', T_BLACK, 0.004)    # anti-slip walkway
        return mb, door
    mb, door = side()
    st = MB(); st.merge(mb); st.merge(mb.mirrored())
    build(st, 'Cheeks', parent='Body')
    build(door, 'Part_DoorR', parent='Body')
    build(door.mirrored(), 'Part_DoorL', parent='Body')


def missile_mb():
    """Missile centred at origin pointing +Y."""
    mb = MB()
    tb = (0.10, 0.11, 0.08)
    P_revolve(mb, V(0, -0.78, 0), V(0, 1, 0), [(0, 0.05), (0.03, 0.075), (1.36, 0.075), (1.43, 0.07)], 'Paint', tb, seg=12,
              tints=[T_BLACK, tb, tb, tb])
    P_revolve(mb, V(0, 0.33, 0), V(0, 1, 0), [(0, 0.0765), (0.05, 0.0765)], 'Paint', T_YEL, seg=12, cap0=False, cap1=False)
    P_revolve(mb, V(0, -0.2, 0), V(0, 1, 0), [(0, 0.0765), (0.04, 0.0765)], 'Paint', (0.25, 0.1, 0.04), seg=12, cap0=False, cap1=False)
    P_revolve(mb, V(0, 0.65, 0), V(0, 1, 0), [(0, 0.07), (0.05, 0.062), (0.09, 0.04), (0.105, 0.0005)], 'Lens', T_W, seg=12, cap0=False, cap1=False)
    for k in range(4):
        a = pi / 4 + k * pi / 2
        R = Matrix.Rotation(a, 3, 'Y')
        e = R @ V(1, 0, 0)
        P_box(mb, e * 0.115 + V(0, -0.62, 0), (0.09, 0.2, 0.008), 'Paint', tb, rot=R)
        P_box(mb, e * 0.1 + V(0, 0.2, 0), (0.06, 0.12, 0.006), 'Paint', tb, rot=R)
    return mb


def build_wings():
    def side():
        mb = MB(); tip = MB()
        cd = V(0, -1, 0); up = V(0, 0, 1)
        P_airfoil(mb, [(V(0.45, 0.78, -0.12), cd, 1.15, 0.14, up), (V(2.4, 0.62, -0.22), cd, 0.85, 0.12, up)], 'HullB', T_W, n=9)
        P_airfoil(tip, [(V(2.4, 0.62, -0.22), cd, 0.85, 0.12, up), (V(2.5, 0.58, -0.225), cd, 0.78, 0.12, up),
                        (V(2.6, 0.45, -0.23), cd, 0.55, 0.10, up), (V(2.64, 0.36, -0.23), cd, 0.36, 0.06, up)], 'HullB', T_W, n=9)
        P_cyl(tip, V(2.6, 0.75, -0.23), V(2.6, -0.45, -0.23), 0.035, 'Paint', T_OLIVE2, seg=10)      # tip rail
        P_sphere(tip, V(2.6, 0.75, -0.23), (0.035, 0.07, 0.035), 'Paint', T_GRN, seg=10, rings=6)       # nav light lens
        P_box(mb, V(2.395, 0.2, -0.22), (0.01, 0.7, 0.07), 'Paint', T_BLACK)                           # exposed rib
        P_box(mb, V(1.4, 0.2, -0.165), (0.5, 0.012, 0.012), 'Paint', T_BLACK)
        # wing root fairing
        P_box(mb, V(0.55, 0.2, -0.13), (0.22, 1.2, 0.2), 'HullB', T_W, 0.05, seg=2)
        # pylons
        for x, zt in ((1.4, -0.24), (2.05, -0.27)):
            P_airfoil(mb, [(V(x, 0.62, zt + 0.06), cd, 0.85, 0.09, V(1, 0, 0)), (V(x, 0.55, -0.47), cd, 0.7, 0.09, V(1, 0, 0))], 'Paint', T_OLIVE2)
            for yy in (0.4, -0.05):
                P_box(mb, V(x, yy, -0.475), (0.09, 0.08, 0.03), 'Metal', T_GUN, 0.006)
        # missile rack (quad launcher)
        x = 2.05
        P_box(mb, V(x, 0.15, -0.5), (0.42, 0.9, 0.05), 'Paint', T_OLIVE2, 0.012)
        P_box(mb, V(x, 0.15, -0.66), (0.05, 0.7, 0.3), 'Paint', T_OLIVE2, 0.012)
        P_box(mb, V(x, 0.15, -0.77), (0.42, 0.5, 0.04), 'Paint', T_OLIVE2, 0.01)
        mpos = []
        for dx in (-0.16, 0.16):
            for z in (-0.62, -0.885):
                P_box(mb, V(x + dx, 0.15, z + 0.092), (0.035, 1.15, 0.035), 'Metal', T_GUN, 0.006)
                mpos.append(V(x + dx, 0.22, z))
        return mb, tip, mpos
    mb, tip, mpos = side()
    st = MB(); st.merge(mb); st.merge(mb.mirrored())
    build(st, 'Wings', parent='Body')
    build(tip, 'Part_WingTipR', parent='Body')
    tl = tip.mirrored()
    tl.vc = [T_RED if c == T_GRN else c for c in tl.vc]
    build(tl, 'Part_WingTipL', parent='Body')
    empty('Light_Nav_R', V(2.62, 0.8, -0.23), 'Body'); empty('Light_Nav_L', V(-2.62, 0.8, -0.23), 'Body')
    # rocket pods
    def pod():
        mb = MB()
        c = V(1.4, 0.2, -0.69)
        tb = (0.075, 0.085, 0.05)
        P_revolve(mb, c + V(0, -1.05, 0), V(0, 1, 0), [(0, 0.06), (0.28, 0.2), (0.32, 0.21), (1.8, 0.21), (1.83, 0.2)], 'Paint', tb, seg=24)
        for yy in (0.55, -0.45):
            P_revolve(mb, c + V(0, yy, 0), V(0, 1, 0), [(0, 0.214), (0.035, 0.214)], 'Metal', T_GUN, seg=24, cap0=False, cap1=False)
        tubes = [(0, 0)] + [(0.082 * cos(k * pi / 3), 0.082 * sin(k * pi / 3)) for k in range(6)] + \
                [(0.158 * cos(k * pi / 6 + pi / 12), 0.158 * sin(k * pi / 6 + pi / 12)) for k in range(12)]
        for (tx, tz) in tubes:
            p = c + V(tx, 0.78, tz)
            P_revolve(mb, p, V(0, 1, 0), [(0, 0.033), (0.018, 0.033), (0.018, 0.027)], 'Metal', T_STEEL, seg=10, cap0=False, cap1=False)
            P_revolve(mb, p, V(0, 1, 0), [(0.006, 0.027)], 'Paint', T_BLACK, seg=10)
        return mb, c
    mb, c = pod()
    build(mb, 'PodR', origin=c, parent='Body')
    build(mb.mirrored(), 'PodL', origin=V(-c.x, c.y, c.z), parent='Body')
    empty('RocketR', c + V(0, 0.8, 0), 'PodR'); empty('RocketL', V(-c.x, c.y + 0.8, c.z), 'PodL')
    # missiles: 1,2 inner (upper, lower); 3,4 outer (upper, lower)
    for k, p in enumerate(mpos):
        for s, nm in ((1, 'R'), (-1, 'L')):
            m = missile_mb()
            o = V(p.x * s, p.y, p.z)
            for v in m.v: v += o
            build(m, 'Missile_%s%d' % (nm, k + 1), origin=o, parent='Body')


def build_tail():
    mb = MB()
    cd = V(0, -1, 0); xr = V(1, 0, 0)
    # vertical fin (static part)
    P_airfoil(mb, [(V(0, -7.25, 0.15), cd, 1.15, 0.11, xr), (V(0, -7.72, 1.2), cd, 0.9, 0.11, xr), (V(0, -7.97, 1.75), cd, 0.75, 0.10, xr)], 'HullB', T_W, n=9)
    # ventral fin + tail wheel
    P_airfoil(mb, [(V(0, -7.2, 0.02), cd, 1.05, 0.10, xr), (V(0, -7.72, -1.2), cd, 0.5, 0.12, xr)], 'HullB', T_W, n=9)
    wc = V(0, -8.0, GEAR_Z + 0.15)
    P_cyl(mb, V(0, -7.95, -1.15), V(0, -7.9, -1.42), 0.03, 'Metal', T_STEEL, seg=8)
    for s in (-1, 1):
        P_box(mb, V(s * 0.06, -7.95, -1.5), (0.014, 0.16, 0.2), 'Metal', T_GUN, 0.004, rot=Matrix.Rotation(rad(-25), 3, 'X'))
    P_revolve(mb, wc + V(-0.045, 0, 0), V(1, 0, 0), [(0, 0.08), (0.012, 0.135), (0.03, 0.15), (0.06, 0.15), (0.078, 0.135), (0.09, 0.08)], 'Paint', T_BLACK, seg=18)
    P_cyl(mb, wc + V(-0.07, 0, 0), wc + V(0.07, 0, 0), 0.02, 'Metal', T_STEEL, seg=8)
    # tail rotor gearbox fairing
    P_revolve(mb, V(0.0, TR_HUB.y, TR_HUB.z), V(1, 0, 0), [(0, 0.18), (0.1, 0.17), (0.2, 0.11), (0.24, 0.07)], 'HullB', T_W, seg=14, cap0=False)
    P_box(mb, V(0.02, TR_HUB.y + 0.35, TR_HUB.z - 0.1), (0.14, 0.6, 0.16), 'HullB', T_W, 0.04, seg=2, rot=Matrix.Rotation(rad(22), 3, 'X'))
    # stabilizer root stubs (dark, visible when stab is gone)
    for s in (-1, 1):
        P_box(mb, V(s * 0.17, -7.17, 0.06), (0.06, 0.5, 0.05), 'Paint', T_BLACK, 0.01)
    P_box(mb, V(0, -8.3, 1.76), (0.05, 0.55, 0.02), 'Paint', T_BLACK)
    # whip antenna + formation light on fin
    P_cyl(mb, V(0, -7.6, 0.95), V(0, -7.3, 1.75), 0.006, 'Metal', T_GUN, seg=5)
    for s in (-1, 1):
        P_box(mb, V(s * 0.043, -8.12, 1.5), (0.006, 0.05, 0.36), 'FormLight', T_W, rot=Matrix.Rotation(rad(24), 3, 'X'))
    # tail skid guard
    P_cyl(mb, V(0, -8.25, 0.1), V(0, -8.55, -0.35), 0.018, 'Metal', T_GUN, seg=6)
    build(mb, 'Tail', parent='Body')
    # fin tip (detachable)
    ft = MB()
    P_airfoil(ft, [(V(0, -7.97, 1.75), cd, 0.75, 0.10, xr), (V(0, -8.08, 2.0), cd, 0.66, 0.10, xr), (V(0, -8.2, 2.12), cd, 0.5, 0.08, xr), (V(0, -8.3, 2.16), cd, 0.3, 0.05, xr)], 'HullB', T_W, n=9)
    P_sphere(ft, V(0, -8.38, 2.17), 0.035, 'Paint', T_RED, seg=8, rings=5)
    build(ft, 'Part_TailFin', parent='Body')
    # stabilizers (detachable)
    st = MB()
    up = V(0, 0, 1)
    P_airfoil(st, [(V(0.15, -6.85, 0.06), cd, 0.7, 0.10, up), (V(1.5, -7.0, 0.06), cd, 0.46, 0.10, up)], 'HullB', T_W, n=8)
    P_airfoil(st, [(V(1.5, -6.96, -0.08), cd, 0.5, 0.10, xr), (V(1.5, -7.05, 0.3), cd, 0.34, 0.10, xr)], 'HullB', T_W, n=6)
    build(st, 'Part_StabR', parent='Body')
    build(st.mirrored(), 'Part_StabL', parent='Body')
    empty('Gear_Tail', V(0, -8.0, GEAR_Z), 'Body')
    empty('TailRotorHub', TR_HUB, 'Body')
    # ---- tail rotor
    tr = MB()
    H = TR_HUB
    P_revolve(tr, V(0.22, H.y, H.z), V(1, 0, 0), [(0, 0.05), (0.08, 0.05), (0.1, 0.09), (0.17, 0.09), (0.2, 0.05)], 'Metal', T_GUN, seg=12)
    tb = (0.03, 0.03, 0.032)
    for k in range(4):
        a = k * pi / 2 + pi / 4
        e = V(0, cos(a), sin(a)); t = V(1, 0, 0).cross(e)
        p = rad(8)
        cdir = (-t * cos(p) - V(1, 0, 0) * sin(p)); upv = (V(1, 0, 0) * cos(p) - t * sin(p))
        base = V(H.x, H.y, H.z)
        secs = []; tints = []
        for r, c, th in ((0.14, 0.08, 0.3), (0.3, 0.2, 0.14), (1.06, 0.2, 0.12), (1.08, 0.2, 0.12), (1.2, 0.14, 0.1)):
            secs.append((base + e * r + t * (c * 0.3), cdir, c, th, upv)); tints.append(T_YEL if r > 1.07 else tb)
        P_airfoil(tr, secs, 'Paint', tb, n=6, tints=tints)
        P_cyl(tr, base + e * 0.07, base + e * 0.2, 0.03, 'Metal', T_STEEL, seg=8)
    build(tr, 'TailRotor', origin=H, parent='Body')


def build_gear():
    def side():
        mb = MB()
        ax = V(1.06, 1.55, GEAR_Z + 0.28)
        P_cyl(mb, V(0.78, 1.0, -0.7), ax + V(-0.12, 0, 0), 0.05, 'Paint', T_OLIVE2, seg=10)
        P_sphere(mb, V(0.78, 1.0, -0.7), 0.075, 'Paint', T_OLIVE2, seg=10, rings=6)
        P_cyl(mb, V(0.84, 1.78, -0.3), V(0.9, 1.68, -0.9), 0.045, 'Paint', T_OLIVE2, seg=10)
        P_cyl(mb, V(0.9, 1.68, -0.9), ax + V(-0.12, 0.02, 0.06), 0.028, 'Metal', T_STEEL, seg=10)
        P_sphere(mb, V(0.84, 1.78, -0.3), 0.07, 'Paint', T_OLIVE2, seg=10, rings=6)
        P_cyl(mb, ax + V(-0.16, 0, 0), ax + V(0.02, 0, 0), 0.04, 'Metal', T_GUN, seg=10)
        # tyre + hub
        P_revolve(mb, ax + V(-0.1, 0, 0), V(1, 0, 0), [(0, 0.15), (0.015, 0.24), (0.05, 0.28), (0.15, 0.28), (0.185, 0.24), (0.2, 0.15)], 'Paint', T_BLACK, seg=24, cap0=False, cap1=False)
        P_revolve(mb, ax + V(-0.095, 0, 0), V(1, 0, 0), [(0, 0.15), (0.03, 0.14), (0.16, 0.14), (0.19, 0.15)], 'Metal', T_GUN, seg=24, cap0=False, cap1=False)
        P_revolve(mb, ax + V(0.065, 0, 0), V(1, 0, 0), [(0, 0.14), (0.02, 0.06), (0.03, 0.04)], 'Metal', T_STEEL, seg=12, cap0=False)
        P_revolve(mb, ax + V(-0.065, 0, 0), V(-1, 0, 0), [(0, 0.14), (0.02, 0.06)], 'Metal', T_STEEL, seg=12, cap0=False)
        # brake line
        P_cyl(mb, V(0.86, 1.7, -0.5), ax + V(-0.1, 0.05, 0.1), 0.008, 'Paint', T_BLACK, seg=5)
        return mb
    mb = side()
    st = MB(); st.merge(mb); st.merge(mb.mirrored())
    build(st, 'Gear', parent='Body')
    empty('Gear_FR', V(1.06, 1.55, GEAR_Z), 'Body'); empty('Gear_FL', V(-1.06, 1.55, GEAR_Z), 'Body')


def build_rotor():
    mb = MB()
    C = V(0, 0, ROTOR_Z)
    tb = (0.028, 0.028, 0.03)
    # rotating swashplate + mast top + hub
    P_revolve(mb, V(0, 0, 1.745), V(0, 0, 1), [(0, 0.13), (0.01, 0.3), (0.05, 0.3), (0.06, 0.13)], 'Metal', T_STEEL, seg=20)
    P_revolve(mb, C + V(0, 0, -0.16), V(0, 0, 1), [(0, 0.1), (0.04, 0.2), (0.24, 0.2), (0.3, 0.13), (0.34, 0.06)], 'Metal', T_GUN, seg=18)
    P_revolve(mb, C + V(0, 0, 0.18), V(0, 0, 1), [(0, 0.16), (0.03, 0.17), (0.07, 0.15), (0.1, 0.08)], 'Paint', T_OLIVE2, seg=18)
    nb = 4
    for k in range(nb):
        a = k * 2 * pi / nb + pi / 4
        e = V(cos(a), sin(a), 0); t = V(0, 0, 1).cross(e)
        R = Matrix((e, t, V(0, 0, 1))).transposed()
        # hub arm (flex beam), grip, damper, pitch horn + link
        P_box(mb, C + e * 0.45, (0.6, 0.16, 0.05), 'Metal', T_GUN, 0.012, rot=R)
        P_box(mb, C + e * 0.45 + V(0, 0, 0.07), (0.5, 0.12, 0.03), 'Metal', T_GUN, 0.01, rot=R)
        P_box(mb, C + e * 0.82, (0.3, 0.24, 0.14), 'Metal', T_STEEL, 0.03, rot=R, seg=2)
        P_cyl(mb, C + e * 0.74 + V(0, 0, -0.1), C + e * 0.74 + V(0, 0, 0.1), 0.035, 'Metal', T_GUN, seg=8)
        P_cyl(mb, C + e * 0.9 + V(0, 0, -0.1), C + e * 0.9 + V(0, 0, 0.1), 0.035, 'Metal', T_GUN, seg=8)
        P_cyl(mb, C + e * 0.3 - t * 0.16, C + e * 0.8 - t * 0.19, 0.03, 'Metal', T_STEEL, seg=8)       # lead-lag damper
        horn = C + e * 0.66 + t * 0.24 + V(0, 0, -0.02)
        P_box(mb, C + e * 0.66 + t * 0.17, (0.06, 0.16, 0.035), 'Metal', T_GUN, 0.008, rot=R)
        P_cyl(mb, V(0, 0, 1.79) + (e * 0.2 + t * 0.19).normalized() * 0.28, horn, 0.014, 'Metal', T_STEEL, seg=6)
        P_sphere(mb, horn, 0.025, 'Metal', T_GUN, seg=8, rings=5)
        # blade
        secs = []; tints = []
        def station(r, c, th, sweep=0.0):
            p = rad(9.0 - 8.0 * r / ROTOR_R)
            cdir = (-t * cos(p) - V(0, 0, 1) * sin(p)); upv = (V(0, 0, 1) * cos(p) - t * sin(p))
            le = C + e * r + t * (c * 0.27 - sweep) + V(0, 0, -0.0045 * r * r)
            secs.append((le, cdir, c, th, upv)); tints.append(T_YEL if r > 6.9 else tb)
        station(0.92, 0.2, 0.45)
        station(1.15, 0.36, 0.22)
        station(1.5, 0.5, 0.12)
        for r in (2.4, 3.3, 4.2, 5.1, 6.0, 6.6):
            station(r, 0.5, 0.11)
        station(6.89, 0.5, 0.11); station(6.91, 0.5, 0.11)
        station(7.1, 0.42, 0.1, 0.08)
        station(ROTOR_R, 0.26, 0.09, 0.24)
        P_airfoil(mb, secs, 'Paint', tb, n=7, tints=tints)
        # trim tab + leading edge strip
        P_box(mb, C + e * 4.6 - t * 0.37 + V(0, 0, -0.0045 * 4.6 ** 2 - 0.03), (0.6, 0.06, 0.006), 'Metal', T_GUN, rot=R)
    build(mb, 'MainRotor', origin=C, parent='Body')


# ------------------------------------------------------------------ cockpit (separate file, same namespace)
exec(compile(open(os.path.join(HERE, 'heli_cockpit.py'), encoding='utf-8').read(), 'heli_cockpit.py', 'exec'), globals())

# ------------------------------------------------------------------ main
def main():
    fc, fn = heli_tex.make_fuse(TEXD, YMIN, YMAX, circ)
    gc, gn = heli_tex.make_generic(TEXD)
    print('textures', time.time() - T0)
    mk_mat('Hull', metal=0.15, rough=0.58, tex=fc, nrm=fn)
    mk_mat('HullB', metal=0.15, rough=0.58, tex=gc, nrm=gn)
    mk_mat('Paint', rough=0.62)
    mk_mat('Metal', metal=0.9, rough=0.38)
    mk_mat('Glass', base=(0.03, 0.05, 0.05), rough=0.04, alpha=0.28)
    mk_mat('Lens', base=(0.015, 0.02, 0.035), metal=0.6, rough=0.06)
    mk_mat('GaugeMark', base=(0.8, 0.85, 0.8), emit=(0.75, 0.9, 0.75), emit_s=0.6)
    mk_mat('Needle', base=(1.0, 0.45, 0.1), emit=(1.0, 0.4, 0.08), emit_s=1.0)
    mk_mat('FormLight', base=(0.3, 0.5, 0.25), emit=(0.35, 0.8, 0.3), emit_s=0.5)
    mk_mat('MFD_L', base=(0.01, 0.03, 0.02), rough=0.2, emit=(0.02, 0.12, 0.05), emit_s=1.0)
    mk_mat('MFD_R', base=(0.01, 0.03, 0.02), rough=0.2, emit=(0.02, 0.12, 0.05), emit_s=1.0)
    for nm, colr in (('Warn_Master', (0.9, 0.05, 0.03)), ('Warn_Engine', (0.9, 0.45, 0.03)), ('Warn_Tail', (0.9, 0.45, 0.03)),
                     ('Warn_Hyd', (0.9, 0.45, 0.03)), ('Warn_Rotor', (0.9, 0.05, 0.03))):
        mk_mat(nm, base=tuple(c * 0.25 for c in colr), rough=0.3, emit=colr, emit_s=0.15)

    cockpit_mats()
    build_fuselage()
    OBJS['Cockpit_'] = OBJS['Body']; WORLD['Cockpit_'] = WORLD['Body']
    build_nose(); build_turret(); build_nacelles(); build_doghouse(); build_cheeks()
    build_wings(); build_tail(); build_gear(); build_rotor(); build_cockpit()
    # re-parent MFDs under Cockpit
    for nm in ('MFD_L', 'MFD_R'):
        OBJS[nm].parent = OBJS['Cockpit']
    del OBJS['Cockpit_']; del WORLD['Cockpit_']
    print('geometry', time.time() - T0)
    bake_ao()
    print('ao', time.time() - T0)
    bpy.context.view_layer.update()
    tris = 0
    for ob in bpy.data.objects:
        if ob.type == 'MESH':
            ob.data.calc_loop_triangles(); tris += len(ob.data.loop_triangles)
    print('TRIS', tris)
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
    open(os.path.join(HERE, 'heli_info.txt'), 'w').write('tris %d\n' % tris)
    if 'nopreview' not in ARGS:
        import heli_preview
        importlib.reload(heli_preview)
        heli_preview.render(PREV, MATS, EYE, ARGS)
        print('preview', time.time() - T0)

main()
