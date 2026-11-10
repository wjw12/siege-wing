# Siege Wing – siege engines, camp props, rearm-pad dressing.
# Run:  blender.exe -b -P props.py -- [preview]
import bpy, sys, os, math, json, random
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import importlib, props_lib
importlib.reload(props_lib)
from props_lib import *
from mathutils import Vector, Matrix


class _Cur:
    def __getattr__(self, n):
        return getattr(props_lib.P, n)


P = _Cur()
PROPS = props_lib.PROPS

ROOT = os.path.dirname(os.path.dirname(HERE))
OUT = os.path.join(ROOT, 'assets', 'models', 'props.glb')
PREV = os.path.join(HERE, 'preview')
os.makedirs(PREV, exist_ok=True)

WOOD = (0.30, 0.20, 0.12); WOOD_D = (0.19, 0.125, 0.075); WOOD_L = (0.43, 0.31, 0.19)
IRON = (0.115, 0.11, 0.115); RUST = (0.21, 0.125, 0.085)
ROPE = (0.47, 0.39, 0.25); CANVAS = (0.70, 0.64, 0.50); STONE = (0.40, 0.385, 0.36); HAY = (0.60, 0.48, 0.20)
OLIVE = (0.15, 0.18, 0.095); OLIVE_D = (0.10, 0.125, 0.07); TINTW = (0.92, 0.92, 0.92)
BLACK = (0.03, 0.03, 0.035); YELLOW = (0.75, 0.58, 0.08); RED = (0.6, 0.06, 0.04)
cos, sin, rad = math.cos, math.sin, math.radians
U = random.uniform


def mul(c, k): return (c[0] * k, c[1] * k, c[2] * k)


# =============================================================================== projectiles
def bolt_geo(c):
    c = V(c)
    cyl(c + V((0, 0.9, 0)), c + V((0, -0.66, 0)), 0.028, 'Wood', WOOD_L, seg=6)
    cone(c + V((0, -0.6, 0)), c + V((0, -0.9, 0)), 0.065, 'Iron', IRON, seg=4, smooth=False)
    cyl(c + V((0, -0.52, 0)), c + V((0, -0.62, 0)), 0.036, 'Iron', IRON, seg=6)
    for a in (90, 210, 330):
        M = rot(ry=a)
        box(c + M @ V((0.065, 0.7, 0)), (0.085, 0.3, 0.006), 'Wood', (0.5, 0.42, 0.3), r=M)


def p_bolt():
    begin('Bolt')
    bolt_geo((0, 0, 0))


def p_arrow():
    begin('Arrow')
    r = 0.012
    vs, fs = [], []
    for y in (0.4, -0.33):
        for a in (90, 210, 330):
            vs.append(V((cos(rad(a)) * r, y, sin(rad(a)) * r)))
    fs = [(0, 1, 4, 3), (1, 2, 5, 4), (2, 0, 3, 5)]
    emit(vs, fs, 'Wood', WOOD_L, fix=False, jit=0)
    hv = [V((cos(rad(a)) * 0.03, -0.3, sin(rad(a)) * 0.03)) for a in (90, 210, 330)] + [V((0, -0.4, 0))]
    emit(hv, [(0, 1, 3), (1, 2, 3), (2, 0, 3)], 'Wood', (0.09, 0.09, 0.1), fix=False, jit=0)
    for a in (0, 90):
        d = V((cos(rad(a)), 0, sin(rad(a)))) * 0.045
        q = [V((0, 0.4, 0)) - d, V((0, 0.4, 0)) + d, V((0, 0.22, 0)) + d * 0.6, V((0, 0.22, 0)) - d * 0.6]
        emit(q, [(0, 1, 2, 3)], 'Wood', (0.75, 0.72, 0.66), fix=False, jit=0)
        emit(q, [(3, 2, 1, 0)], 'Wood', (0.75, 0.72, 0.66), fix=False, jit=0)


def p_boulder():
    begin('Boulder')
    ico((0, 0, 0), 0.5, 'Stone', STONE, sub=2, amp=0.11, freq=2.4, smooth=True)


# =============================================================================== ballista
def p_ballista():
    begin('Ballista')
    for a in (45, 135):
        d = V((cos(rad(a)), sin(rad(a)), 0))
        beam(-d * 1.0 + V((0, 0, 0.1)), d * 1.0 + V((0, 0, 0.1)), 0.2, 0.2, 'Wood', WOOD_D, bevel=0.02)
    beam((0, 0, 0.18), (0, 0, 1.1), 0.24, 0.24, 'Wood', WOOD, bevel=0.02)
    for a in (45, 135, 225, 315):
        d = V((cos(rad(a)), sin(rad(a)), 0))
        beam(d * 0.8 + V((0, 0, 0.2)), d * 0.1 + V((0, 0, 0.9)), 0.1, 0.1, 'Wood', WOOD_L)
        cyl(d * 0.9 + V((0, 0, 0.19)), d * 0.9 + V((0, 0, 0.23)), 0.035, 'Iron', IRON, seg=6)
    band((0, 0, 1.02), (0, 0, 1), 0.175, 0.08, 'Iron', IRON, seg=8)
    cyl((0, 0, 1.1), (0, 0, 1.16), 0.3, 'Iron', IRON, seg=12)

    P.part('Ballista_Yaw', 'Ballista', (0, 0, 1.16))
    cyl((0, 0, 1.16), (0, 0, 1.22), 0.27, 'Wood', WOOD_D, seg=12)
    for sx in (-1, 1):
        beam((sx * 0.2, 0, 1.2), (sx * 0.2, 0, 1.66), 0.07, 0.22, 'Wood', WOOD, up=(0, 1, 0))
        beam((sx * 0.2, 0.3, 1.22), (sx * 0.2, 0.05, 1.5), 0.05, 0.06, 'Wood', WOOD_L, bevel=0)
        beam((sx * 0.2, -0.3, 1.22), (sx * 0.2, -0.05, 1.5), 0.05, 0.06, 'Wood', WOOD_L, bevel=0)
        cyl((sx * 0.24, 0, 1.55), (sx * 0.27, 0, 1.55), 0.05, 'Iron', IRON, seg=6)
    cyl((-0.25, 0, 1.55), (0.25, 0, 1.55), 0.028, 'Iron', IRON, seg=6)

    P.part('Ballista_Pitch', 'Ballista_Yaw', (0, 0, 1.55))
    zs = 1.6
    beam((0, 1.5, zs), (0, -1.5, zs), 0.2, 0.2, 'Wood', WOOD, bevel=0.02)
    box((0, -0.2, zs + 0.104), (0.07, 2.5, 0.012), 'Wood', WOOD_D)
    for y in (-0.9, -0.2, 0.5, 1.1):
        box((0, y, zs), (0.215, 0.05, 0.215), 'Iron', IRON)
    yf = -1.25
    for z in (zs - 0.3, zs + 0.3):
        beam((-0.9, yf, z), (0.9, yf, z), 0.28, 0.1, 'Wood', WOOD, bevel=0.015)
        for sx in (-1, 1):
            box((sx * 0.9, yf, z), (0.03, 0.29, 0.11), 'Iron', IRON)
    for sx in (-1, 1):
        for xx in (0.4, 0.84):
            beam((sx * xx, yf, zs - 0.25), (sx * xx, yf, zs + 0.25), 0.08, 0.26, 'Wood', WOOD_L, up=(0, 1, 0))
        xb = sx * 0.62
        cyl((xb, yf, zs - 0.36), (xb, yf, zs + 0.36), 0.085, 'Rope', ROPE, seg=8)
        for z in (zs - 0.38, zs + 0.38):
            cyl((xb, yf, z - 0.025), (xb, yf, z + 0.025), 0.12, 'Iron', IRON, seg=8)
            cyl((xb - 0.15, yf, z + (0.04 if z > zs else -0.04)), (xb + 0.15, yf, z + (0.04 if z > zs else -0.04)), 0.02, 'Iron', IRON, seg=5)
        # bow arm
        beam((xb, yf, zs), (sx * 1.1, yf + 0.28, zs), 0.1, 0.09, 'Wood', WOOD_D, bevel=0.01)
        beam((sx * 1.08, yf + 0.27, zs), (sx * 1.6, yf + 0.5, zs), 0.075, 0.07, 'Wood', WOOD_D, bevel=0.01)
        box((sx * 1.58, yf + 0.49, zs), (0.09, 0.09, 0.085), 'Iron', IRON, r=rot(rz=sx * -25))
        rope((sx * 1.6, yf + 0.5, zs + 0.01), (0, 0.56, zs + 0.13), 0.014, col=mul(ROPE, 0.8))
        beam((sx * 0.4, yf + 0.1, zs), (sx * 0.1, -0.55, zs), 0.06, 0.08, 'Wood', WOOD_L, bevel=0)
    box((0, 0.6, zs + 0.14), (0.1, 0.16, 0.07), 'Iron', IRON, bevel=0.01)
    # winch
    for sx in (-1, 1):
        box((sx * 0.14, 1.3, zs + 0.12), (0.05, 0.24, 0.3), 'Wood', WOOD_L, bevel=0.01)
        for a in range(4):
            d = V((0, cos(rad(a * 90 + 20)), sin(rad(a * 90 + 20))))
            c = V((sx * 0.3, 1.3, zs + 0.17))
            cyl(c, c + d * 0.24, 0.016, 'Wood', WOOD_L, seg=5)
    cyl((-0.33, 1.3, zs + 0.17), (0.33, 1.3, zs + 0.17), 0.055, 'Wood', WOOD_D, seg=8)
    cyl((-0.08, 1.3, zs + 0.17), (0.08, 1.3, zs + 0.17), 0.075, 'Rope', ROPE, seg=8)
    rope((0, 1.28, zs + 0.24), (0, 0.66, zs + 0.15), 0.012)
    beam((0, 1.45, zs), (0, 1.9, zs - 0.18), 0.06, 0.06, 'Wood', WOOD_L)

    P.part('Ballista_LoadedBolt', 'Ballista_Pitch', (0, -0.35, zs + 0.14))
    bolt_geo((0, -0.35, zs + 0.14))
    P.empty('Ballista_Bolt', (0, -1.25, zs + 0.14), 'Ballista_Pitch')


# =============================================================================== bombard
def p_bombard():
    begin('Bombard')
    for sx in (-1, 1):
        beam((sx * 0.5, 1.75, 0.16), (sx * 0.5, -1.5, 0.16), 0.3, 0.3, 'Wood', WOOD_D, bevel=0.025)
    for y in (1.4, 0.75, -0.5, -1.3):
        beam((-0.85, y, 0.41), (0.85, y, 0.41), 0.24, 0.2, 'Wood', WOOD, bevel=0.02)
    for i in range(4):
        beam((-0.8 + U(-0.04, 0.04), 2.0, 0.17 + i * 0.3), (0.8 + U(-0.04, 0.04), 2.0, 0.17 + i * 0.3), 0.36, 0.29, 'Wood', WOOD if i % 2 else WOOD_D, bevel=0.025)
    for sx in (-1, 1):
        beam((sx * 0.5, 2.15, 1.05), (sx * 0.5, 3.0, 0.05), 0.2, 0.2, 'Wood', WOOD_L, bevel=0.02)
        cyl((sx * 0.5, 3.12, -0.05), (sx * 0.56, 3.0, 0.45), 0.07, 'Wood', WOOD_D, seg=6)
        cyl((sx * 0.86, 2.0, 0), (sx * 0.86, 2.0, 1.35), 0.08, 'Wood', WOOD_D, seg=6)
        # trunnion posts
        beam((sx * 0.56, 0.2, 0.5), (sx * 0.56, 0.2, 1.08), 0.2, 0.36, 'Wood', WOOD, up=(0, 1, 0), bevel=0.02)
        box((sx * 0.56, 0.2, 1.1), (0.22, 0.24, 0.05), 'Iron', IRON)
        beam((sx * 0.56, 0.75, 0.5), (sx * 0.56, 0.38, 0.95), 0.12, 0.12, 'Wood', WOOD_L)
        beam((sx * 0.56, -0.5, 0.5), (sx * 0.56, 0.02, 0.95), 0.12, 0.12, 'Wood', WOOD_L)

    P.part('Bombard_Pitch', 'Bombard', (0, 0.2, 1.0))
    za = 1.04
    beam((0, 1.5, za - 0.38), (0, -1.15, za - 0.38), 0.5, 0.14, 'Wood', WOOD_D, bevel=0.02)
    for y in (1.1, 0.2, -0.8):
        beam((-0.36, y, za - 0.26), (0.36, y, za - 0.26), 0.14, 0.12, 'Wood', WOOD)
    org = V((0, 1.5, za)); ax = (0, -1, 0)
    prof = [(0.001, 0), (0.17, 0), (0.21, 0.05), (0.21, 0.85), (0.26, 0.9), (0.3, 0.95), (0.31, 2.6), (0.36, 2.7),
            (0.375, 2.84), (0.33, 2.86), (0.24, 2.86), (0.22, 2.3), (0.001, 2.3)]
    lathe(prof, 'Iron', IRON, origin=org, axis=ax, seg=16, colf=lambda i, k: mul(IRON, 1.0 + 0.13 * math.sin(i * 2.4)))
    for i, h in enumerate([1.02 + 0.185 * j for j in range(9)]):
        band(org + V(ax) * h, ax, 0.312, 0.075, 'Iron', RUST if i % 3 == 1 else mul(IRON, 1.25), t=0.028, seg=16)
    for h in (0.15, 0.45, 0.75):
        band(org + V(ax) * h, ax, 0.212, 0.07, 'Iron', mul(IRON, 1.25), t=0.025, seg=16)
    for h in (1.2, 2.3):
        torus(org + V(ax) * h + V((0, 0, 0.37)), (1, 0, 0), 0.07, 0.016, 'Iron', IRON, seg=8, rseg=4)
    cyl((-0.66, 0.2, 1.0), (0.66, 0.2, 1.0), 0.06, 'Iron', IRON, seg=8)
    for y in (0.9, -0.6):
        torus((0, y, za - 0.08), (0, 1, 0), 0.37, 0.022, 'Rope', ROPE, seg=12, rseg=4)
    box((0, 1.6, za - 0.05), (0.44, 0.2, 0.5), 'Wood', WOOD, bevel=0.02)
    P.empty('Bombard_Muzzle', (0, -1.36, za), 'Bombard_Pitch')

    P.use('Bombard')
    for (x, y, z) in [(1.2, -0.7, 0.19), (1.58, -0.7, 0.19), (1.2, -0.32, 0.19), (1.58, -0.32, 0.19), (1.39, -0.51, 0.47)]:
        ico((x, y, z), 0.2, 'Stone', STONE, sub=1, amp=0.03, smooth=True)
    barrel((-1.25, 0.7, 0), (0, 0, 1), 0.62, 0.23)
    lathe([(0.11, 0), (0.15, 0.3), (0.16, 0.3), (0.12, 0.0)], 'Wood', WOOD_L, origin=(-1.2, -0.3, 0), seg=8)
    cyl((-1.05, -1.5, 0.05), (-0.75, 1.3, 0.95), 0.025, 'Wood', WOOD_L, seg=5)
    cyl((-1.06, -1.6, 0.02), (-1.05, -1.4, 0.08), 0.07, 'Cloth', CANVAS, seg=6)


# =============================================================================== trebuchet
def p_trebuchet():
    begin('Trebuchet')
    AX = 8.0
    for sx in (-1, 1):
        x = sx * 1.6
        beam((x, -5.2, 0.23), (x, 5.2, 0.23), 0.45, 0.45, 'Wood', WOOD_D, bevel=0.03)
        for sy in (-1, 1):
            beam((x, sy * 3.4, 0.45), (x, sy * 0.22, AX - 0.1), 0.32, 0.38, 'Wood', WOOD, up=(1, 0, 0), bevel=0.025)
            box((x, sy * 3.3, 0.55), (0.36, 0.5, 0.06), 'Iron', IRON)
        beam((x, 0, 0.45), (x, 0, AX + 0.3), 0.4, 0.42, 'Wood', WOOD, up=(0, 1, 0), bevel=0.03)
        for z, ye in ((3.2, 2.45), (5.6, 1.45)):
            beam((x + sx * 0.3, -ye, z), (x + sx * 0.3, ye, z), 0.16, 0.3, 'Wood', WOOD_L, bevel=0.015)
            for sy in (-1, 1):
                box((x + sx * 0.39, sy * (ye - 0.2), z), (0.03, 0.08, 0.08), 'Iron', IRON)
        # cross bracing between tie levels
        beam((x - sx * 0.22, -2.2, 3.3), (x - sx * 0.22, 0, 5.5), 0.1, 0.22, 'Wood', WOOD_L, bevel=0)
        beam((x - sx * 0.22, 2.2, 3.3), (x - sx * 0.22, 0, 5.5), 0.1, 0.22, 'Wood', WOOD_L, bevel=0)
        # outrigger prop
        beam((sx * 3.8, 0, 0.45), (sx * 1.85, 0, 5.9), 0.28, 0.28, 'Wood', WOOD, bevel=0.02)
        box((x, 0, AX), (0.56, 0.62, 0.5), 'Wood', WOOD_D, bevel=0.03)
        box((x, 0, AX + 0.27), (0.6, 0.66, 0.05), 'Iron', IRON)
        box((x, 0, AX - 0.27), (0.6, 0.66, 0.05), 'Iron', IRON)
        band((sx * 1.95, 0, AX), (1, 0, 0), 0.2, 0.1, 'Iron', IRON, t=0.02, seg=10)
    beam((-4.1, 0, 0.21), (4.1, 0, 0.21), 0.4, 0.4, 'Wood', WOOD_D, bevel=0.03)
    for y in (-5.0, -3.4, 3.4, 5.0):
        beam((-2.0, y, 0.2), (2.0, y, 0.2), 0.36, 0.36, 'Wood', WOOD_D, bevel=0.03)
    for i in range(5):
        x = -0.6 + i * 0.3
        beam((x, -4.9, 0.47), (x, 4.9, 0.47), 0.27, 0.06, 'Wood', WOOD_L if i % 2 else WOOD, bevel=0.008, jit=0.15)
    for sx in (-1, 1):
        beam((sx * 0.78, -4.9, 0.53), (sx * 0.78, 4.9, 0.53), 0.06, 0.14, 'Wood', WOOD, bevel=0)
    cyl((-2.15, 0, AX), (2.15, 0, AX), 0.19, 'Wood', WOOD_D, seg=10)
    # ladder up the +x front leg
    def legp(z, off):
        t = (z - 0.45) / (AX - 0.55)
        return V((1.6 + 0.3, -3.4 + (3.4 - 0.22) * t + off, z))
    for off in (-0.25, 0.25):
        cyl(legp(0.3, off) + V((0.05, 0, 0)), legp(7.3, off) + V((0.05, 0, 0)), 0.035, 'Wood', WOOD_L, seg=5)
    for i in range(17):
        z = 0.7 + i * 0.4
        cyl(legp(z, -0.25) + V((0.05, 0, 0)), legp(z, 0.25) + V((0.05, 0, 0)), 0.022, 'Wood', WOOD_L, seg=4, caps=False)
    # winch with capstan wheels at rear
    yw, zw = 4.2, 1.25
    for sx in (-1, 1):
        beam((sx * 1.6, yw, 0.45), (sx * 1.6, yw, zw + 0.25), 0.3, 0.3, 'Wood', WOOD, up=(0, 1, 0), bevel=0.02)
        beam((sx * 1.6, yw + 0.9, 0.45), (sx * 1.6, yw + 0.1, zw), 0.14, 0.14, 'Wood', WOOD_L)
        wheel((sx * 2.1, yw, zw), (1, 0, 0), 1.05, 0.12, spokes=8, tire=False)
        for a in range(8):
            d = V((0, cos(rad(a * 45)), sin(rad(a * 45))))
            c = V((sx * 2.1, yw, zw))
            cyl(c + d * 1.0 + V((sx * -0.05, 0, 0)), c + d * 1.0 + V((sx * 0.22, 0, 0)), 0.025, 'Wood', WOOD_L, seg=5)
    cyl((-2.2, yw, zw), (2.2, yw, zw), 0.1, 'Wood', WOOD_D, seg=8)
    cyl((-0.5, yw, zw), (0.5, yw, zw), 0.17, 'Rope', ROPE, seg=10)
    rope((0, yw - 0.1, zw + 0.12), (0, 5.0, 0.6), 0.03)
    box((0, 5.0, 0.55), (0.3, 0.2, 0.2), 'Iron', IRON, bevel=0.02)
    # spare boulders
    for (x, y, r) in [(-2.9, -3.6, 0.42), (-3.5, -3.1, 0.38), (-2.9, -2.7, 0.4), (-3.1, -3.2, 0.36)]:
        ico((x, y, r * 0.85 if r != 0.36 else 0.95), r, 'Stone', STONE, sub=1, amp=0.12, smooth=True)

    # ---- arm (rest: horizontal, long end toward +Y Blender / -Z three)
    P.part('Treb_Arm', 'Trebuchet', (0, 0, AX), rot_x=rad(-50))
    beam((0, -2.7, AX), (0, 2.6, AX), 0.42, 0.5, 'Wood', WOOD, bevel=0.03)
    beam((0, 2.4, AX), (0, 5.6, AX), 0.34, 0.4, 'Wood', WOOD, bevel=0.025)
    beam((0, 5.4, AX), (0, 8.6, AX), 0.26, 0.3, 'Wood', WOOD, bevel=0.02)
    for sx in (-1, 1):
        beam((sx * 0.25, -1.6, AX), (sx * 0.25, 1.6, AX), 0.07, 0.62, 'Wood', WOOD_L, bevel=0.01)
        cyl((sx * 0.3, 0, AX), (sx * 0.45, 0, AX), 0.3, 'Iron', IRON, seg=10)
    for y, w, h in ((-2.3, 0.44, 0.52), (-1.2, 0.58, 0.64), (1.2, 0.58, 0.64), (2.5, 0.44, 0.52), (4.0, 0.36, 0.42),
                    (5.5, 0.36, 0.42), (7.0, 0.28, 0.32), (8.4, 0.28, 0.32)):
        box((0, y, AX), (w, 0.1, h), 'Iron', IRON if y != 4.0 else RUST)
    for y in (3.2, 6.2):
        for k in range(4):
            box((0, y + k * 0.045, AX), (0.37 if y < 5 else 0.29, 0.04, 0.43 if y < 5 else 0.33), 'Rope', ROPE)
    cyl((0, 8.55, AX), (0, 8.9, AX + 0.12), 0.03, 'Iron', IRON, seg=6)
    torus((0, 8.5, AX - 0.19), (1, 0, 0), 0.06, 0.016, 'Iron', IRON, seg=8, rseg=4)
    cyl((-0.98, -2.5, AX), (0.98, -2.5, AX), 0.065, 'Iron', IRON, seg=8)
    P.empty('Treb_Sling', (0, 8.8, AX + 0.08), 'Treb_Arm')

    # ---- counterweight (rest: hangs straight down)
    P.part('Treb_CW', 'Treb_Arm', (0, -2.5, AX), rot_x=rad(50))
    for sx in (-1, 1):
        beam((sx * 0.82, -2.5, AX + 0.15), (sx * 0.82, -2.5, AX - 1.5), 0.1, 0.34, 'Wood', WOOD_D, up=(0, 1, 0), bevel=0.015)
        box((sx * 0.82, -2.5, AX), (0.13, 0.4, 0.3), 'Iron', IRON)
        box((sx * 0.9, -2.5, AX - 1.9), (0.04, 0.2, 1.6), 'Iron', IRON)
    crate((0, -2.5, AX - 2.1), (1.7, 1.7, 1.6), col=WOOD, batt=WOOD_D, bw=0.16)
    for z in (AX - 2.65, AX - 1.55):
        box((0, -2.5, z), (1.78, 1.78, 0.09), 'Iron', IRON)
    for i in range(9):
        ico((U(-0.6, 0.6), -2.5 + U(-0.6, 0.6), AX - 1.28 + U(0, 0.1)), U(0.2, 0.3), 'Stone', STONE, sub=1, amp=0.15)

    # ---- sling (rest: hangs straight down along -Z; child of arm)
    tip = V((0, 8.8, AX + 0.08))
    P.part('Treb_SlingMesh', 'Treb_Arm', tip, rot_x=rad(-35))
    L = 4.2
    for sx in (-1, 1):
        rope(tip + V((sx * 0.03, 0, 0)), tip + V((sx * 0.3, 0, -L + 0.25)), 0.022, col=mul(ROPE, 0.85))
    grid(lambda u, v: tip + V(((u - 0.5) * 0.8, (v - 0.5) * 0.9, -L - 0.25 + 0.5 * (abs(u - 0.5) * 2) ** 2 + 0.3 * (abs(v - 0.5) * 2) ** 2)),
         4, 4, 'Cloth', (0.3, 0.2, 0.12))
    P.part('Treb_LoadedBoulder', 'Treb_SlingMesh', tip + V((0, 0, -L + 0.2)))
    ico(tip + V((0, 0, -L + 0.2)), 0.42, 'Stone', STONE, sub=1, amp=0.15, smooth=True)


# =============================================================================== tents
def p_tent_a():
    begin('Tent_A')
    W, L, H = 1.5, 2.0, 2.2
    nrm = V((H, 0, W)).normalized()
    for sx in (-1, 1):
        def fn(u, v, sx=sx):
            y = -L + 2 * L * u
            p = V((sx * W * v, y, H * (1 - v)))
            sag = 0.09 * math.sin(PI * v) * (0.55 + 0.45 * math.cos(u * PI * 4)) + 0.015 * math.sin(u * 37 + v * 5)
            n = V((sx * nrm.x, 0, nrm.z))
            p -= n * sag
            if v > 0.98: p.x += sx * 0.05 * math.sin(u * 23)
            return p
        grid(fn, 12, 6, 'Cloth', CANVAS, flip=(sx > 0), colf=lambda i, j: mul(CANVAS, 1.0 - 0.05 * j + U(-0.03, 0.03)))
    def back(u, v):
        return V(((u * 2 - 1) * W * (1 - v), L + 0.05 * math.sin(u * PI) * math.sin(v * PI), H * v))
    grid(back, 6, 5, 'Cloth', mul(CANVAS, 0.93), flip=True)
    for sx in (-1, 1):
        def front(u, v, sx=sx):
            xo = sx * W * (1 - v)
            xi = sx * 0.6 * (1 - v) ** 0.7
            x = xo + (xi - xo) * u
            return V((x, -L - 0.25 * u * (1 - v) - 0.03 * math.sin(u * 9), H * v))
        grid(front, 4, 5, 'Cloth', mul(CANVAS, 0.95), flip=(sx > 0))
    for sy in (-1, 1):
        cyl((0, sy * L, 0), (0, sy * L, H + 0.12), 0.04, 'Wood', WOOD_L, seg=6)
        rope((0, sy * L, H + 0.05), (0, sy * (L + 1.5), 0.02), 0.012)
        cyl((0, sy * (L + 1.55), -0.05), (0, sy * (L + 1.45), 0.18), 0.022, 'Wood', WOOD_D, seg=4)
        for sx in (-1, 1):
            rope((sx * W * 0.55, sy * 1.3, H * 0.45 + 0.03), (sx * 2.4, sy * 1.5, 0.02), 0.012)
            cyl((sx * 2.45, sy * 1.5, -0.05), (sx * 2.35, sy * 1.5, 0.18), 0.022, 'Wood', WOOD_D, seg=4)
    cyl((0, -L - 0.2, H), (0, L + 0.2, H), 0.035, 'Wood', WOOD_L, seg=6)
    box((0, 0, 0.012), (2.8, 3.9, 0.02), 'Cloth', (0.1, 0.085, 0.065))
    cyl((-0.5, -1.2, 0.1), (-0.5, 0.6, 0.1), 0.1, 'Cloth', (0.38, 0.22, 0.16), seg=6)


def p_tent_b():
    begin('Tent_B')
    R, HW, HP, RE = 3.5, 2.0, 5.0, 3.68
    NU = 48
    def stripe(i): return (i // 4) % 2
    def wall(u, v):
        a = u * 2 * PI
        r = R + 0.06 * math.sin(a * 24) * (0.3 + 0.7 * math.sin(v * PI * 0.5 + 0.3)) - 0.06 * math.sin(v * PI)
        return V((cos(a) * r, sin(a) * r, HW * (1 - v)))
    grid(wall, NU, 3, 'Cloth', CANVAS, flip=True, skip=lambda i, j: i in (35, 36),
         colf=lambda i, j: mul(TINTW if stripe(i) else CANVAS, 1 - 0.04 * j), tintf=lambda i, j: float(stripe(i)))
    def roof(u, v):
        a = u * 2 * PI
        r = RE * (1 - v) + 0.07 * v
        z = HW + (HP - HW) * (0.25 * v + 0.75 * v ** 1.6)
        z += 0.05 * math.cos(a * 12) * math.sin(v * PI)
        return V((cos(a) * r, sin(a) * r, z))
    grid(roof, NU, 6, 'Cloth', CANVAS, flip=True, colf=lambda i, j: (TINTW if stripe(i) else CANVAS),
         tintf=lambda i, j: float(stripe(i)))
    def val(u, v):
        a = u * 2 * PI
        r = RE + 0.02 + 0.06 * v + 0.02 * math.sin(a * 24)
        zb = HW - 0.42 + 0.17 * abs(math.sin(u * PI * 24))
        return V((cos(a) * r, sin(a) * r, HW + 0.02 + (zb - HW - 0.02) * v))
    grid(val, 96, 1, 'Cloth', CANVAS, flip=True, colf=lambda i, j: (CANVAS if stripe(i // 2) else TINTW),
         tintf=lambda i, j: 0.0 if stripe(i // 2) else 1.0)
    # door flaps
    for s in (-1, 1):
        a0 = 1.5 * PI + s * 0.131
        def flap(u, v, s=s, a0=a0):
            a = a0 + s * 0.09 * u
            r = R + 0.12 * math.sin(u * PI * 3) + 0.25 * math.sin(v * PI) * u
            return V((cos(a) * r, sin(a) * r, HW * (1 - v)))
        grid(flap, 4, 4, 'Cloth', mul(CANVAS, 0.9))
    # floor, pole, finial, pennant
    cyl((0, 0, 0), (0, 0, 0.02), R - 0.05, 'Cloth', (0.12, 0.08, 0.07), seg=24)
    box((0, -2.2, 0.03), (1.3, 2.4, 0.02), 'Cloth', (0.35, 0.08, 0.07))
    cyl((0, 0, 0), (0, 0, HP + 0.75), 0.07, 'Wood', WOOD_L, seg=8)
    ico((0, 0, HP + 0.8), 0.13, 'Iron', (0.75, 0.55, 0.18), sub=1, smooth=True)
    cone((0, 0, HP + 0.9), (0, 0, HP + 1.2), 0.04, 'Iron', (0.75, 0.55, 0.18), seg=6)
    def pen(u, v):
        return V((0.02 * math.sin(u * 9), 0.07 + u * 1.1, HP + 0.72 - 0.42 * v * (1 - u) - 0.12 * u * u + 0.04 * math.sin(u * 7)))
    grid(pen, 5, 1, 'Cloth', TINTW, tint=1.0)
    lathe([(0.3, HP - 0.12), (0.34, HP - 0.3), (0.3, HP - 0.3)], 'Cloth', TINTW, seg=12, tint=1.0, closed=True)
    for i in range(12):
        a = (i + 0.5) * 2 * PI / 12
        if abs(a - 1.5 * PI) < 0.3: continue
        d = V((cos(a), sin(a), 0))
        rope(d * RE + V((0, 0, HW)), d * 5.4 + V((0, 0, 0.03)), 0.014)
        cyl(d * 5.47 + V((0, 0, -0.05)), d * 5.36 + V((0, 0, 0.22)), 0.025, 'Wood', WOOD_D, seg=4)
        cyl(d * (R - 0.08), d * (R - 0.08) + V((0, 0, HW)), 0.03, 'Wood', WOOD_L, seg=4, caps=False)
    # furnishings seen through the door
    crate((0.9, -1.0, 0.25), (0.8, 0.5, 0.5))
    box((-0.3, 0.6, 0.45), (1.6, 0.8, 0.06), 'Wood', WOOD, bevel=0.01)
    for sx in (-1, 1):
        for sy in (-1, 1):
            beam((-0.3 + sx * 0.7, 0.6 + sy * 0.3, 0), (-0.3 + sx * 0.7, 0.6 + sy * 0.3, 0.42), 0.06, 0.06, 'Wood', WOOD_D, bevel=0)


# =============================================================================== camp
def sack(c, r=0.28, col=(0.55, 0.47, 0.32)):
    ico(c, r, 'Cloth', col, sub=1, amp=0.1, scale=(1.25, 0.85, 0.7), smooth=True, fix=True)


def p_cart():
    begin('Cart')
    ZB = 0.88
    for sx in (-1, 1):
        wheel((sx * 0.86, 0.1, 0.66), (1, 0, 0), 0.66, 0.09, spokes=10)
        beam((sx * 0.5, 1.25, ZB - 0.09), (sx * 0.5, -1.25, ZB - 0.09), 0.1, 0.12, 'Wood', WOOD_D)
        beam((sx * 0.5, -1.2, ZB - 0.09), (sx * 0.42, -3.1, ZB - 0.2), 0.08, 0.08, 'Wood', WOOD)
        for y in (-1.15, -0.4, 0.4, 1.15):
            beam((sx * 0.68, y, ZB), (sx * 0.72, y, ZB + 0.55), 0.06, 0.06, 'Wood', WOOD, bevel=0)
        for z in (0.22, 0.48):
            beam((sx * (0.685 + z * 0.06), -1.22, ZB + z), (sx * (0.685 + z * 0.06), 1.22, ZB + z), 0.035, 0.12, 'Wood', WOOD_L, bevel=0.006, jit=0.12)
    cyl((-0.98, 0.1, 0.66), (0.98, 0.1, 0.66), 0.05, 'Wood', WOOD_D, seg=6)
    for i in range(6):
        box((-0.575 + i * 0.23, 0, ZB), (0.22, 2.5, 0.045), 'Wood', WOOD_L if i % 2 else WOOD, bevel=0.006, jit=0.15)
    for y in (-1.22, 1.22):
        for z in (0.2, 0.42):
            beam((-0.7, y, ZB + z), (0.7, y, ZB + z), 0.035, 0.16, 'Wood', WOOD_L, bevel=0.006, jit=0.12)
    beam((-0.45, -3.0, ZB - 0.2), (0.45, -3.0, ZB - 0.2), 0.07, 0.07, 'Wood', WOOD)
    beam((0, -1.25, ZB - 0.1), (0, -1.5, 0), 0.08, 0.08, 'Wood', WOOD_D)
    beam((0, 1.2, ZB - 0.1), (0, 1.3, 0), 0.08, 0.08, 'Wood', WOOD_D)
    beam((-0.42, -2.9, ZB - 0.22), (-0.42, -2.95, 0), 0.06, 0.06, 'Wood', WOOD_D)
    beam((0.42, -2.9, ZB - 0.22), (0.42, -2.95, 0), 0.06, 0.06, 'Wood', WOOD_D)
    sack((-0.3, -0.7, ZB + 0.2)); sack((0.3, -0.75, ZB + 0.2), col=(0.5, 0.44, 0.3)); sack((0, -0.6, ZB + 0.5), 0.26)
    barrel((-0.32, 0.65, ZB + 0.33), (0, -1, 0), 0.75, 0.27)
    crate((0.3, 0.7, ZB + 0.27), (0.5, 0.7, 0.5))
    def tarp(u, v):
        return V((0.03 + u * 0.62, 0.3 + v * 0.85, ZB + 0.56 - 0.5 * max(0, u - 0.82) / 0.18 * 0.6 - 0.45 * max(0, abs(v - 0.5) - 0.42) / 0.08 + 0.02 * math.sin(u * 11 + v * 7)))
    grid(tarp, 6, 6, 'Cloth', (0.36, 0.33, 0.25))


def p_crates():
    begin('Crates')
    crate((0, 0, 0.35), (1.0, 0.75, 0.7))
    crate((0.95, 0.1, 0.27), (0.75, 0.6, 0.54), r=rot(rz=14), col=WOOD_L)
    crate((0.1, 0.02, 0.95), (0.7, 0.55, 0.5), r=rot(rz=-9), col=(0.33, 0.24, 0.15))
    crate((-0.2, -0.85, 0.22), (0.6, 0.45, 0.44), r=rot(rz=32))
    crate((0.75, -0.75, 0.3), (0.5, 0.5, 0.5), r=rot(rx=0, ry=31, rz=20), col=WOOD_L)
    for i in range(4):
        torus((-0.85, 0.15, 0.03 + i * 0.05), (0, 0, 1), 0.2 - i * 0.01, 0.028, 'Rope', ROPE, seg=10, rseg=4)
    sack((0.95, 0.1, 0.72), 0.26)
    sack((-0.75, -0.4, 0.17), 0.25, col=(0.5, 0.44, 0.3))


def p_barrels():
    begin('Barrels')
    barrel((0, 0, 0), (0, 0, 1), 0.9, 0.32)
    barrel((0.66, 0.1, 0), (0, 0, 1), 0.9, 0.32, col=(0.28, 0.18, 0.1))
    barrel((0.3, 0.62, 0), (0, 0, 1), 0.9, 0.32, col=(0.36, 0.25, 0.14))
    barrel((-0.35, 0.66, 0), (0, 0, 1), 0.72, 0.26)
    barrel((0.25, 0.3, 0.9), (0, 0, 1), 0.5, 0.2, col=(0.3, 0.2, 0.11))
    barrel((-0.95, -0.55, 0.31), (0.92, 0.39, 0), 0.9, 0.32, col=(0.3, 0.21, 0.13))
    for s in (-1, 1):
        box((-0.55 + s * 0.02, -0.38 - s * 0.42, 0.06), (0.14, 0.1, 0.12), 'Wood', WOOD_D, r=rot(rz=23))
    lathe([(0.12, 0), (0.16, 0.32), (0.175, 0.32), (0.13, 0.0)], 'Wood', WOOD_L, origin=(0.85, -0.55, 0), seg=8)
    band((0.85, -0.55, 0.25), (0, 0, 1), 0.155, 0.03, 'Iron', IRON, t=0.006, seg=8)


def round_shield(c, n, r=0.4):
    c = V(c)
    lathe([(0.001, 0.07), (r * 0.5, 0.05), (r, 0.0), (r, -0.025), (0.001, -0.025)], 'Paint', TINTW, origin=c, axis=n, seg=12,
          colf=lambda i, k: TINTW if k < 2 else WOOD, tintf=lambda i, k: 1.0 if k < 2 else 0.0)
    band(c - V(n).normalized() * 0.012, n, r, 0.03, 'Iron', IRON, t=0.008)
    ico(c + V(n).normalized() * 0.07, 0.075, 'Iron', mul(IRON, 1.5), sub=1, smooth=True)


def p_weaponrack():
    begin('WeaponRack')
    for sx in (-1, 1):
        x = sx * 1.2
        beam((x, -0.5, 0), (x, 0.03, 1.6), 0.08, 0.08, 'Wood', WOOD)
        beam((x, 0.5, 0), (x, -0.03, 1.6), 0.08, 0.08, 'Wood', WOOD)
        beam((x, -0.3, 0.6), (x, 0.3, 0.6), 0.05, 0.07, 'Wood', WOOD_L)
        for k in range(3):
            torus((x, 0, 1.47 + k * 0.03), (0, 0, 1), 0.07, 0.016, 'Rope', ROPE, seg=6, rseg=4)
    cyl((-1.4, 0, 1.52), (1.4, 0, 1.52), 0.04, 'Wood', WOOD_L, seg=6)
    beam((-1.3, -0.34, 0.55), (1.3, -0.34, 0.55), 0.06, 0.06, 'Wood', WOOD_L)
    for i in range(8):
        x = -1.0 + i * 0.285 + U(-0.03, 0.03)
        b = V((x + U(-0.05, 0.05), -0.82, 0))
        d = (V((x, -0.045, 1.56)) - b).normalized()
        L = U(2.3, 2.7)
        cyl(b, b + d * L, 0.019, 'Wood', WOOD_L, seg=5)
        cone(b + d * (L - 0.02), b + d * (L + 0.26), 0.04, 'Iron', mul(IRON, 1.6), seg=4, smooth=False)
        cyl(b + d * (L - 0.1), b + d * (L - 0.01), 0.026, 'Iron', IRON, seg=5)
    for i, x in enumerate((-0.82, -0.25, 0.3, 0.86)):
        round_shield((x, -0.52, 0.43), (0, -0.92, 0.38), r=0.41)
    # a couple of poleaxes on the back
    for x in (-0.5, 0.45):
        b = V((x, 0.8, 0)); d = (V((x, 0.045, 1.56)) - b).normalized()
        cyl(b, b + d * 2.1, 0.02, 'Wood', WOOD, seg=5)
        box(b + d * 1.98 + V((0.09, 0, 0)), (0.2, 0.015, 0.22), 'Iron', mul(IRON, 1.5))
        cone(b + d * 2.08, b + d * 2.35, 0.03, 'Iron', mul(IRON, 1.5), seg=4, smooth=False)


def p_campfire():
    begin('Campfire')
    for i in range(11):
        a = i * 2 * PI / 11 + U(-0.08, 0.08)
        r = U(0.13, 0.19)
        ico((cos(a) * 0.62, sin(a) * 0.62, r * 0.45), r, 'Stone', mul(STONE, U(0.8, 1.1)), sub=1, amp=0.18, scale=(1, 1, 0.75))
    lathe([(0.56, 0.0), (0.5, 0.035), (0.2, 0.06), (0.001, 0.07)], 'Stone', (0.06, 0.055, 0.05), seg=12)
    for i in range(7):
        a = i * 2 * PI / 7 + 0.2
        d = V((cos(a), sin(a), 0))
        cyl(d * 0.42 + V((0, 0, 0.05)), d * -0.06 + V((0, 0, 0.5)), 0.05, 'Wood', (0.07, 0.05, 0.04), seg=6, r1=0.04)
    for i in range(4):
        a = i * 2 * PI / 4 + 0.9
        d = V((cos(a), sin(a), 0)); t = V((-sin(a), cos(a), 0))
        cyl(d * 0.25 - t * 0.3 + V((0, 0, 0.09)), d * 0.25 + t * 0.3 + V((0, 0, 0.09)), 0.055, 'Wood', (0.09, 0.06, 0.045), seg=6)
    for sx in (-1, 1):
        cyl((sx * 0.92, 0, 0), (sx * 0.92, 0, 1.05), 0.035, 'Wood', WOOD, seg=6)
        for sy in (-1, 1):
            cyl((sx * 0.92, 0, 1.0), (sx * 0.92, sy * 0.09, 1.22), 0.022, 'Wood', WOOD, seg=5)
    cyl((-1.1, 0, 1.09), (1.1, 0, 1.09), 0.016, 'Iron', IRON, seg=5)
    rope((0, 0, 1.08), (0, 0, 0.85), 0.01, mat='Iron', col=IRON)
    lathe([(0.001, 0.56), (0.12, 0.58), (0.2, 0.68), (0.2, 0.83), (0.215, 0.85), (0.18, 0.85), (0.17, 0.7), (0.001, 0.64)], 'Iron', (0.06, 0.06, 0.06), seg=10)
    torus((0, 0, 0.87), (0, 1, 0), 0.19, 0.008, 'Iron', IRON, seg=8, rseg=3)
    # seats and woodpile
    cyl((-0.7, -1.55, 0.17), (0.6, -1.7, 0.17), 0.17, 'Wood', WOOD, seg=8)
    cyl((1.5, -0.5, 0.15), (1.75, 0.7, 0.15), 0.15, 'Wood', WOOD_D, seg=8)
    for i in range(6):
        row, k = (0, i) if i < 3 else ((1, i - 3) if i < 5 else (2, 0))
        y = 1.5 + k * 0.17 + row * 0.085
        cyl((-0.9, y, 0.08 + row * 0.145), (-0.1, y + U(-0.03, 0.03), 0.08 + row * 0.145), 0.08, 'Wood', mul(WOOD_L, U(0.8, 1.1)), seg=6)
    box((-1.15, 1.2, 0.25), (0.3, 0.3, 0.5), 'Wood', WOOD_D, bevel=0.03, r=rot(rz=20))
    cyl((-1.15, 1.2, 0.5), (-0.95, 1.05, 0.95), 0.018, 'Wood', WOOD_L, seg=5)
    box((-1.17, 1.22, 0.53), (0.02, 0.14, 0.1), 'Iron', IRON, r=rot(rz=35))


def p_bannerpole():
    begin('BannerPole')
    for a in (0, 90):
        d = V((cos(rad(a)), sin(rad(a)), 0))
        beam(-d * 0.6 + V((0, 0, 0.07)), d * 0.6 + V((0, 0, 0.07)), 0.14, 0.14, 'Wood', WOOD_D, bevel=0.015)
    for a in (0, 90, 180, 270):
        d = V((cos(rad(a)), sin(rad(a)), 0))
        beam(d * 0.5 + V((0, 0, 0.12)), d * 0.04 + V((0, 0, 0.75)), 0.07, 0.07, 'Wood', WOOD)
        ico(d.cross(V((0, 0, 1))) * 0.25 + d * 0.3 + V((0, 0, 0.1)), 0.15, 'Stone', STONE, sub=1, amp=0.15)
    cyl((0, 0, 0.1), (0, 0, 6.0), 0.065, 'Wood', WOOD_L, r1=0.042, seg=8)
    band((0, 0, 0.8), (0, 0, 1), 0.065, 0.06, 'Iron', IRON, seg=8)
    band((0, 0, 5.92), (0, 0, 1), 0.045, 0.08, 'Iron', (0.7, 0.52, 0.18), seg=8)
    cone((0, 0, 6.0), (0, 0, 6.38), 0.055, 'Iron', (0.7, 0.52, 0.18), seg=4, smooth=False)
    ico((0, 0, 6.02), 0.065, 'Iron', (0.7, 0.52, 0.18), sub=1, smooth=True)
    ZC = 5.55
    cyl((-0.75, -0.07, ZC), (0.75, -0.07, ZC), 0.028, 'Wood', WOOD_D, seg=6)
    for sx in (-1, 1):
        ico((sx * 0.77, -0.07, ZC), 0.05, 'Iron', (0.7, 0.52, 0.18), sub=1, smooth=True)
        rope((sx * 0.68, -0.07, ZC + 0.02), (0, -0.03, 5.9), 0.01)
    for k in range(3):
        torus((0, -0.03, ZC - 0.03 + k * 0.03), (0, 0, 1), 0.075, 0.014, 'Rope', ROPE, seg=6, rseg=4)
    P.empty('Banner_Attach', (0, -0.07, ZC))


def p_pavise():
    begin('Pavise')
    M = rot(rx=-13)
    W, H = 0.42, 1.5
    def shape(u, v):
        x = (u * 2 - 1) * W
        if v > 0.8:
            x *= math.sqrt(1 - 0.8 * ((v - 0.8) / 0.2) ** 2)
        y = -0.13 * (1 - (abs(u * 2 - 1)) ** 2) - 0.035 * math.exp(-((u - 0.5) * 9) ** 2)
        return x, y, v * H + 0.02
    def front(u, v):
        return M @ V(shape(u, v))
    def backf(u, v):
        x, y, z = shape(1 - u, v)
        e = 0.0 if (u < 1e-6 or u > 1 - 1e-6 or v < 1e-6 or v > 1 - 1e-6) else 0.035
        return M @ V((x, y + e, z))
    grid(front, 8, 10, 'Paint', TINTW, fix=False,
         colf=lambda i, j: mul(WOOD_D, 1.2) if (i in (0, 7) or j in (0, 9)) else TINTW,
         tintf=lambda i, j: 0.0 if (i in (0, 7) or j in (0, 9)) else 1.0)
    grid(backf, 8, 10, 'Wood', WOOD, fix=False)
    # iron rim studs + top cap
    for v in (0.06, 0.3, 0.55, 0.78):
        for u in (0.04, 0.96):
            x, y, z = shape(u, v)
            ico(M @ V((x, y - 0.01, z)), 0.022, 'Iron', mul(IRON, 1.5), sub=1)
    # brace bar and prop leg
    x, y, z = shape(0.5, 0.7)
    for vv in (0.25, 0.7):
        xa, ya, za = shape(0.12, vv); xb, yb, zb = shape(0.88, vv)
        beam(M @ V((xa, ya + 0.06, za)), M @ V((xb, yb + 0.06, zb)), 0.035, 0.07, 'Wood', WOOD_D, bevel=0)
    top = M @ V((0, y + 0.08, 1.05))
    beam(top, (0, 0.78, 0.0), 0.05, 0.05, 'Wood', WOOD_L)
    rope(M @ V((0, y + 0.08, 0.38)), (0, 0.5, 0.36), 0.01)
    for sx in (-1, 1):
        cone(M @ V((sx * 0.3, -0.03, 0.05)), M @ V((sx * 0.3, -0.03, -0.12)), 0.03, 'Iron', IRON, seg=4)


def p_firepot():
    begin('FirePot')
    for i in range(3):
        a = i * 2 * PI / 3 + 0.5
        d = V((cos(a), sin(a), 0))
        cyl(d * 0.55, d * 0.3 + V((0, 0, 0.82)), 0.024, 'Iron', IRON, seg=5)
        box(d * 0.56 + V((0, 0, 0.015)), (0.1, 0.1, 0.03), 'Iron', IRON, r=rot(rz=math.degrees(a)))
    torus((0, 0, 0.82), (0, 0, 1), 0.3, 0.022, 'Iron', IRON, seg=12, rseg=4)
    torus((0, 0, 0.3), (0, 0, 1), 0.45, 0.014, 'Iron', RUST, seg=12, rseg=4)
    prof = [(0.001, 0.66), (0.2, 0.69), (0.36, 0.82), (0.44, 1.02), (0.47, 1.08), (0.47, 1.11), (0.41, 1.11), (0.39, 1.0), (0.3, 0.86), (0.001, 0.8)]
    lathe(prof, 'Iron', IRON, seg=12, colf=lambda i, k: RUST if (i * 7 + k * 3) % 5 == 0 else mul(IRON, 0.8))
    for k in range(3):
        band((0, 0, 0.84 + k * 0.1), (0, 0, 1), 0.375 + k * 0.035, 0.02, 'Iron', mul(IRON, 1.3), t=0.012, seg=12)
    lathe([(0.4, 1.0), (0.2, 1.03), (0.001, 1.05)], 'Stone', (0.045, 0.035, 0.03), seg=12)
    for i in range(8):
        a = i * 2.4; r = 0.08 + 0.22 * (i % 3) / 2
        ico((cos(a) * r, sin(a) * r, 1.07 + U(0, 0.05)), U(0.07, 0.11), 'Stone', (0.09, 0.04, 0.03), sub=1, amp=0.2)
    for sx in (-1, 1):
        torus((sx * 0.5, 0, 1.0), (0, 1, 0), 0.07, 0.013, 'Iron', IRON, seg=8, rseg=4)
    P.empty('FirePot_Top', (0, 0, 1.12))


def p_palisade():
    begin('Palisade')
    n = 13
    for i in range(n):
        x = -1.86 + i * 0.31
        h = U(2.95, 3.35); r = U(0.14, 0.165)
        y = U(-0.03, 0.03)
        c = mul(WOOD, U(0.75, 1.15))
        cyl((x, y, -0.05), (x + U(-0.03, 0.03), y, h), r, 'Wood', c, r1=r * 0.92, seg=7, caps=False, jit=0)
        cone((x, y, h), (x + U(-0.03, 0.03), y, h + 0.5), r * 0.92, 'Wood', mul(WOOD_L, 1.1), seg=7, caps=False)
    for z in (0.95, 2.25):
        beam((-2.0, 0.22, z), (2.0, 0.22, z), 0.12, 0.16, 'Wood', WOOD_D, bevel=0.015)
        for i in range(0, n, 3):
            x = -1.86 + i * 0.31
            torus((x, 0.1, z), (1, 0, 0), 0.2, 0.016, 'Rope', ROPE, seg=8, rseg=3)
    for x in (-1.3, 1.3):
        beam((x, 0.3, 2.2), (x, 1.8, 0.0), 0.14, 0.14, 'Wood', WOOD, bevel=0.015)
        cyl((x, 1.85, -0.05), (x, 1.75, 0.35), 0.06, 'Wood', WOOD_D, seg=5)


def p_haystack():
    begin('Haystack')
    prof = [(1.55, 0), (1.75, 0.45), (1.7, 1.3), (1.3, 2.1), (0.7, 2.75), (0.25, 3.05), (0.001, 3.12)]
    lathe(prof, 'Rope', HAY, seg=16, rfunc=lambda a, k: 1 + 0.07 * math.sin(a * 5 + k * 1.7) + 0.04 * math.sin(a * 11 + k),
          colf=lambda i, k: mul(HAY, 0.8 + 0.25 * ((i * 5 + k * 3) % 4) / 3))
    cyl((0, 0, 2.9), (0.03, 0, 3.6), 0.04, 'Wood', WOOD_L, seg=5)
    for i in range(5):
        a = i * 1.3
        ico((cos(a) * 1.95, sin(a) * 1.95, 0.12), U(0.25, 0.4), 'Rope', mul(HAY, U(0.8, 1.05)), sub=1, amp=0.2, scale=(1.2, 1, 0.45))
    b = V((1.75, -2.5, 0)); t = V((1.3, -1.75, 1.75))
    cyl(b, t, 0.02, 'Wood', WOOD_L, seg=5)
    d = (t - b).normalized(); s = d.cross(V((0, 0, 1))).normalized()
    cyl(t - s * 0.12, t + s * 0.12, 0.012, 'Iron', IRON, seg=4)
    for k in (-1, 0, 1):
        cyl(t + s * 0.12 * k, t + s * 0.12 * k + d * 0.3, 0.01, 'Iron', IRON, seg=4)
    # ladder
    for sx in (-0.2, 0.2):
        cyl((-1.3 + sx, -2.2, 0), (-0.75 + sx, -1.3, 2.3), 0.03, 'Wood', WOOD, seg=5)
    for i in range(6):
        t0 = 0.12 + i * 0.15
        p = V((-1.3, -2.2, 0)).lerp(V((-0.75, -1.3, 2.3)), t0)
        cyl(p + V((-0.2, 0, 0)), p + V((0.2, 0, 0)), 0.02, 'Wood', WOOD_L, seg=4, caps=False)


def p_stakes():
    begin('Stakes')
    cyl((-1.9, 0, 0.78), (1.9, 0, 0.78), 0.11, 'Wood', WOOD_D, seg=8)
    for i in range(8):
        x = -1.6 + i * 0.457
        for s in (-1, 1):
            xx = x + s * 0.07
            b = V((xx, -s * 0.8, 0.0)); d = (V((xx, 0, 0.78)) - b).normalized()
            L = U(2.1, 2.35)
            c = mul(WOOD, U(0.8, 1.15))
            cyl(b, b + d * L, 0.055, 'Wood', c, seg=6, caps=False, jit=0)
            cone(b + d * L, b + d * (L + 0.3), 0.055, 'Wood', mul(WOOD_L, 1.15), seg=6, caps=False)
        torus((x, 0, 0.78), (1, 0, 0), 0.13, 0.018, 'Rope', ROPE, seg=8, rseg=3)
    for sx in (-1, 1):
        band((sx * 1.85, 0, 0.78), (1, 0, 0), 0.11, 0.05, 'Iron', IRON, seg=8)


# =============================================================================== modern pad dressing
def tire(c, R=0.52, w=0.34):
    prof = [(R * 0.56, -w / 2), (R * 0.9, -w / 2), (R, -w / 2 + 0.06), (R, w / 2 - 0.06), (R * 0.9, w / 2), (R * 0.56, w / 2)]
    lathe(prof, 'Paint', BLACK, origin=c, axis=(1, 0, 0), seg=12)
    c = V(c)
    lathe([(R * 0.57, -w * 0.3), (R * 0.5, -w * 0.18), (0.001, -w * 0.18)], 'Paint', OLIVE_D, origin=c, axis=(1, 0, 0), seg=12)
    lathe([(0.001, w * 0.18), (R * 0.5, w * 0.18), (R * 0.57, w * 0.3)], 'Paint', OLIVE_D, origin=c, axis=(1, 0, 0), seg=12)
    for s in (-1, 1):
        cyl(c + V((s * w * 0.18, 0, 0)), c + V((s * w * 0.3, 0, 0)), R * 0.2, 'Paint', OLIVE, seg=8)


def jerrycan(c, rz=0, col=OLIVE):
    M = rot(rz=rz); c = V(c)
    box(c + V((0, 0, 0.22)), (0.34, 0.16, 0.44), 'Paint', col, r=M, bevel=0.025)
    box(c + M @ V((0.04, 0, 0.47)), (0.2, 0.03, 0.05), 'Paint', mul(col, 0.7), r=M)
    cyl(c + M @ V((-0.11, 0, 0.44)), c + M @ V((-0.13, 0, 0.5)), 0.03, 'Paint', BLACK, seg=6)


def p_truck():
    begin('Pad_Truck')
    for y in (-2.35, 1.3, 2.6):
        for sx in (-1, 1):
            tire((sx * 1.03, y, 0.52))
        cyl((-1.0, y, 0.52), (1.0, y, 0.52), 0.08, 'Paint', BLACK, seg=6)
        box((0, y, 0.52), (0.4, 0.4, 0.34), 'Paint', BLACK, bevel=0.05)
    for sx in (-1, 1):
        beam((sx * 0.42, -3.3, 0.82), (sx * 0.42, 3.45, 0.82), 0.1, 0.2, 'Paint', BLACK, bevel=0)
    cyl((0, -2.3, 0.6), (0, 2.6, 0.6), 0.05, 'Paint', BLACK, seg=5)
    # cab
    box((0, -2.55, 1.2), (2.4, 1.7, 0.6), 'Paint', OLIVE, bevel=0.05, jit=0.02)
    cabv = [(-1.2, -3.4), (1.2, -3.4)]
    # upper cab with raked windshield (hand-built prism)
    y0, y1, yt = -3.4, -1.7, -3.1
    z0, z1 = 1.5, 2.45
    vs = [V((-1.2, y0, z0)), V((1.2, y0, z0)), V((1.2, y1, z0)), V((-1.2, y1, z0)),
          V((-1.12, yt, z1)), V((1.12, yt, z1)), V((1.12, y1, z1)), V((-1.12, y1, z1))]
    emit(vs, [(0, 1, 2, 3), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)], 'Paint', OLIVE, jit=0.02)
    GL = (0.02, 0.03, 0.04)
    # windshield (two panes) on the raked face
    def rk(x, t, off=0.012):
        y = y0 + (yt - y0) * t; z = z0 + (z1 - z0) * t
        n = V((0, -(z1 - z0), (yt - y0))).normalized()
        if n.y > 0: n = -n
        return V((x * (1 - 0.067 * t), y, z)) + n * off
    for sx in (-1, 1):
        q = [rk(sx * 0.06, 0.14), rk(sx * 1.08, 0.14), rk(sx * 1.08, 0.88), rk(sx * 0.06, 0.88)]
        if sx > 0: q.reverse()
        poly(q if sx < 0 else q, 'Paint', GL)
        poly(list(reversed(q)), 'Paint', GL)
        # side window + door seam + mirror + step
        box((sx * 1.175, -2.5, 2.0), (0.03, 0.95, 0.52), 'Paint', GL)
        box((sx * 1.205, -1.98, 1.55), (0.012, 0.02, 1.15), 'Paint', OLIVE_D)
        box((sx * 1.205, -3.02, 1.4), (0.012, 0.02, 0.85), 'Paint', OLIVE_D)
        box((sx * 1.215, -2.1, 1.62), (0.03, 0.14, 0.04), 'Paint', BLACK)
        box((sx * 1.38, -3.2, 2.1), (0.05, 0.1, 0.3), 'Paint', BLACK, bevel=0.01)
        cyl((sx * 1.2, -3.25, 2.25), (sx * 1.38, -3.2, 2.2), 0.012, 'Paint', BLACK, seg=4)
        box((sx * 1.22, -2.5, 0.72), (0.2, 0.5, 0.04), 'Paint', BLACK)
        # front fender arch
        box((sx * 1.03, -2.35, 1.1), (0.42, 1.3, 0.06), 'Paint', OLIVE_D, bevel=0.02)
        box((sx * 1.03, -1.72, 0.9), (0.42, 0.05, 0.4), 'Paint', BLACK)
        # headlights
        cyl((sx * 0.85, -3.42, 1.12), (sx * 0.85, -3.46, 1.12), 0.11, 'Paint', (0.8, 0.8, 0.7), seg=8)
        box((sx * 0.85, -3.43, 1.12), (0.3, 0.04, 0.3), 'Paint', OLIVE_D, bevel=0.02)
    for i in range(5):
        box((0, -3.415, 1.0 + i * 0.07), (0.9, 0.03, 0.035), 'Paint', BLACK)
    box((0, -3.52, 0.78), (2.44, 0.16, 0.24), 'Paint', BLACK, bevel=0.03)
    for sx in (-1, 1):
        torus((sx * 0.6, -3.62, 0.78), (1, 0, 0), 0.06, 0.018, 'Paint', OLIVE, seg=6, rseg=4)
    box((0, -2.3, 2.47), (0.7, 0.7, 0.05), 'Paint', OLIVE_D, bevel=0.01)
    cyl((0.9, -1.85, 2.45), (0.9, -1.85, 3.3), 0.012, 'Paint', BLACK, seg=4)
    box((0, -1.6, 1.75), (2.2, 0.12, 1.3), 'Paint', OLIVE_D, bevel=0.02)       # cab back wall / spare frame
    cyl((-0.75, -1.5, 1.2), (-0.75, -1.5, 3.0), 0.06, 'Paint', BLACK, seg=6)   # exhaust stack
    cyl((-0.75, -1.5, 2.2), (-0.75, -1.5, 2.8), 0.085, 'Paint', (0.2, 0.2, 0.2), seg=6)
    # tank subframe + elliptical tank
    box((0, 1.0, 1.0), (2.1, 4.8, 0.16), 'Paint', OLIVE_D, bevel=0.02)
    ZT = 1.92
    prof = [(0.001, 0), (0.6, 0.02), (0.9, 0.14), (0.98, 0.32), (0.98, 4.3), (0.9, 4.48), (0.6, 4.6), (0.001, 4.62)]
    lathe(prof, 'Paint', OLIVE, origin=(0, -1.32, ZT), axis=(0, 1, 0), seg=16, sx=1.18, sy=0.86, jit=0.02)
    for h in (0.5, 1.75, 3.0, 4.15):
        lathe([(0.975, -0.04), (1.0, -0.04), (1.0, 0.04), (0.975, 0.04)], 'Paint', OLIVE_D, origin=(0, -1.32 + h, ZT), axis=(0, 1, 0), seg=16, sx=1.18, sy=0.86, smooth=False)
    box((0, 1.0, ZT + 0.86), (0.7, 4.0, 0.04), 'Paint', BLACK)
    for y in (-0.2, 2.2):
        cyl((0, y, ZT + 0.84), (0, y, ZT + 0.98), 0.27, 'Paint', OLIVE_D, seg=10)
        box((0.2, y, ZT + 0.99), (0.2, 0.05, 0.03), 'Paint', BLACK)
    for sx in (-1, 1):
        for y in (-1.0, 3.0):
            cyl((sx * 0.35, y, ZT + 0.86), (sx * 0.35, y, ZT + 1.2), 0.012, 'Paint', BLACK, seg=4, caps=False)
        cyl((sx * 0.35, -1.0, ZT + 1.2), (sx * 0.35, 3.0, ZT + 1.2), 0.012, 'Paint', BLACK, seg=4, caps=False)
        box((sx * 1.05, -0.3, 1.02), (0.32, 1.5, 0.55), 'Paint', OLIVE, bevel=0.03)
        box((sx * 1.215, -0.3, 1.02), (0.012, 1.3, 0.4), 'Paint', OLIVE_D)
        box((sx * 1.03, 1.95, 1.12), (0.42, 2.5, 0.06), 'Paint', OLIVE_D, bevel=0.02)
        box((sx * 1.03, 3.22, 0.85), (0.42, 0.04, 0.5), 'Paint', BLACK)
        box((sx * 0.9, 3.47, 1.0), (0.22, 0.04, 0.12), 'Paint', RED)
    box((0, 3.48, 0.8), (2.3, 0.12, 0.18), 'Paint', BLACK, bevel=0.02)
    # rear pump cabinet + hose reel + ladder
    box((0, 3.33, 1.45), (1.5, 0.35, 0.75), 'Paint', OLIVE, bevel=0.03)
    torus((0.3, 3.53, 1.45), (0, 1, 0), 0.22, 0.07, 'Paint', BLACK, seg=10, rseg=5)
    cyl((0.3, 3.5, 1.45), (0.3, 3.58, 1.45), 0.1, 'Paint', (0.6, 0.6, 0.55), seg=8)
    box((-0.4, 3.52, 1.5), (0.4, 0.03, 0.4), 'Paint', (0.25, 0.25, 0.25))
    for i, c in enumerate((RED, YELLOW, (0.1, 0.5, 0.15))):
        box((-0.52 + i * 0.12, 3.54, 1.6), (0.05, 0.02, 0.05), 'Paint', c)
    for sx in (-0.2, 0.2):
        cyl((-0.75 + sx, 3.42, 1.05), (-0.75 + sx, 3.3, 2.75), 0.018, 'Paint', BLACK, seg=4, caps=False)
    for i in range(5):
        z = 1.25 + i * 0.32
        cyl((-0.95, 3.42 - (z - 1.05) * 0.07, z), (-0.55, 3.42 - (z - 1.05) * 0.07, z), 0.014, 'Paint', BLACK, seg=4, caps=False)
    cyl((1.25, 0.9, 1.0), (1.25, 0.9, 1.45), 0.07, 'Paint', RED, seg=8)
    cyl((1.25, 0.9, 1.45), (1.25, 0.9, 1.52), 0.03, 'Paint', BLACK, seg=6)
    box((0, -1.32 + 2.3, ZT), (2.33, 1.0, 0.16), 'Paint', YELLOW)    # hazard stripe wraps tank mid


def ammo_crate(c, s=(1.0, 0.42, 0.34), rz=0, stripe=YELLOW):
    M = rot(rz=rz); c = V(c)
    box(c, s, 'Paint', OLIVE, r=M, bevel=0.012, jit=0.08)
    box(c + V((0, 0, s[2] * 0.22)), (s[0] + 0.006, s[1] + 0.006, 0.012), 'Paint', OLIVE_D, r=M)
    box(c + M @ V((s[0] * 0.3, 0, 0)), (0.07, s[1] + 0.008, s[2] + 0.008), 'Paint', stripe, r=M)
    for sx in (-1, 1):
        box(c + M @ V((sx * (s[0] / 2 + 0.012), 0, 0.03)), (0.02, 0.16, 0.035), 'Rope', ROPE, r=M)
        for sy in (-1, 1):
            box(c + M @ V((sx * s[0] * 0.38, sy * (s[1] / 2 + 0.006), s[2] * 0.22)), (0.05, 0.012, 0.08), 'Iron', IRON, r=M)


def p_padcrates():
    begin('Pad_Crates')
    # pallet
    for y in (-0.5, 0, 0.5):
        box((0, y, 0.05), (1.2, 0.1, 0.1), 'Wood', WOOD_L)
    for i in range(6):
        box((-0.5 + i * 0.2, 0, 0.115), (0.14, 1.15, 0.025), 'Wood', WOOD_L, jit=0.15)
    for iz in range(3):
        for iy in range(2):
            if iz == 2 and iy == 1: continue
            ammo_crate((U(-0.02, 0.02), -0.26 + iy * 0.5, 0.3 + iz * 0.345), rz=U(-2, 2))
    ammo_crate((1.5, 0.3, 0.17), rz=24, stripe=RED)
    ammo_crate((1.55, 0.25, 0.515), rz=12, stripe=RED)
    # open rocket crate with 4 rockets
    c = V((0.2, -1.35, 0.0))
    box(c + V((0, 0, 0.03)), (1.7, 0.6, 0.06), 'Paint', OLIVE)
    for sy in (-1, 1):
        box(c + V((0, sy * 0.3, 0.14)), (1.7, 0.03, 0.28), 'Paint', OLIVE, jit=0.08)
    for sx in (-1, 1):
        box(c + V((sx * 0.85, 0, 0.14)), (0.03, 0.63, 0.28), 'Paint', OLIVE, jit=0.08)
    for i in range(4):
        y = c.y - 0.2 + i * 0.133
        cyl((c.x - 0.72, y, 0.115), (c.x + 0.5, y, 0.115), 0.036, 'Paint', (0.33, 0.35, 0.33), seg=8)
        cone((c.x + 0.5, y, 0.115), (c.x + 0.74, y, 0.115), 0.036, 'Paint', (0.12, 0.13, 0.12), seg=8)
        box((c.x + 0.3, y, 0.115), (0.03, 0.076, 0.076), 'Paint', YELLOW)
    box((c.x, c.y + 0.75, 0.2), (1.7, 0.63, 0.03), 'Paint', OLIVE, r=rot(rx=62))    # lid leaning
    # launch tube bundle (7 hex-packed) lying on trestles
    b = V((-1.5, 0.2, 0.42))
    for sx in (-1, 1):
        box(b + V((0, sx * 0.5, -0.27)), (0.6, 0.08, 0.3), 'Wood', WOOD)
    for (dx, dz) in [(0, 0)] + [(cos(rad(a)) * 0.125, sin(rad(a)) * 0.125) for a in range(0, 360, 60)]:
        p0 = b + V((dx, -0.8, dz)); p1 = b + V((dx, 0.8, dz))
        lathe([(0.045, 0), (0.06, 0), (0.06, 1.6), (0.045, 1.6)], 'Paint', OLIVE_D, origin=p0, axis=(0, 1, 0), seg=8, closed=True)
    for y in (-0.6, 0.6):
        band(b + V((0, y, 0)), (0, 1, 0), 0.19, 0.05, 'Paint', BLACK, seg=12)
    jerrycan((0.9, 0.95, 0), 15); jerrycan((1.3, 1.05, 0), -8)
    cyl((-0.75, -0.75, 0), (-0.75, -0.75, 0.48), 0.075, 'Paint', RED, seg=8)
    cyl((-0.75, -0.75, 0.48), (-0.75, -0.75, 0.56), 0.03, 'Paint', BLACK, seg=6)


def p_windsock():
    begin('Windsock')
    cyl((0, 0, 0), (0, 0, 0.05), 0.25, 'Paint', (0.3, 0.3, 0.3), seg=10)
    for i in range(4):
        d = V((cos(i * PI / 2 + 0.78), sin(i * PI / 2 + 0.78), 0))
        box(d * 0.18 + V((0, 0, 0.06)), (0.04, 0.04, 0.03), 'Iron', IRON)
        poly([d * 0.06 + V((0, 0, 0.05)), d * 0.2 + V((0, 0, 0.05)), d * 0.06 + V((0, 0, 0.35))], 'Paint', (0.3, 0.3, 0.3))
        poly([d * 0.06 + V((0, 0, 0.35)), d * 0.2 + V((0, 0, 0.05)), d * 0.06 + V((0, 0, 0.05))], 'Paint', (0.3, 0.3, 0.3))
    n = 6
    for i in range(n):
        z0, z1 = 0.05 + i * 5.95 / n, 0.05 + (i + 1) * 5.95 / n
        r0, r1 = 0.055 - 0.02 * i / n, 0.055 - 0.02 * (i + 1) / n
        cyl((0, 0, z0), (0, 0, z1), r0, 'Paint', (0.85, 0.1, 0.06) if i % 2 else (0.9, 0.9, 0.88), r1=r1, seg=8, caps=(i == n - 1), jit=0)
    ZT = 6.05
    P.part('Windsock_Sock', 'Windsock', (0, 0, ZT))
    cyl((0, 0, 5.98), (0, 0, ZT + 0.05), 0.045, 'Iron', IRON, seg=8)
    R0, R1, L = 0.42, 0.17, 2.5
    yh = -0.32
    torus((0, yh, ZT), (0, 1, 0), R0, 0.014, 'Iron', IRON, seg=12, rseg=4)
    for a in (90, 210, 330):
        cyl((0, 0, ZT), (cos(rad(a)) * R0, yh, ZT + sin(rad(a)) * R0), 0.01, 'Iron', IRON, seg=4, caps=False)
    def sock(u, v):
        a = u * 2 * PI
        r = R0 + (R1 - R0) * v
        droop = 0.55 * v * v
        return V((cos(a) * r, yh - L * v * (1 - 0.06 * v), ZT + sin(a) * r * (1 - 0.25 * v) - droop + 0.015 * math.sin(a * 3 + v * 9) * v))
    OR, WH = (0.92, 0.28, 0.04), (0.92, 0.9, 0.86)
    grid(sock, 12, 10, 'Cloth', OR, colf=lambda i, j: OR if (j // 2) % 2 == 0 else WH)


def p_padlight():
    begin('Pad_Light')
    cyl((0, 0, 0), (0, 0, 0.035), 0.15, 'Paint', YELLOW, seg=10)
    cyl((0, 0, 0.035), (0, 0, 0.15), 0.085, 'Paint', (0.07, 0.07, 0.07), seg=10)
    cyl((0, 0, 0.15), (0, 0, 0.17), 0.1, 'Paint', (0.07, 0.07, 0.07), seg=10)
    lathe([(0.075, 0.17), (0.07, 0.225), (0.045, 0.26), (0.001, 0.27)], 'PadLightEmissive', (1, 0.85, 0.5), seg=10)
    for i in range(4):
        a = i * PI / 2 + 0.4
        d = V((cos(a), sin(a), 0))
        tube([d * 0.095 + V((0, 0, 0.17)), d * 0.09 + V((0, 0, 0.24)), d * 0.05 + V((0, 0, 0.285)), V((0, 0, 0.295))], 0.006, 'Iron', IRON, seg=3)
    for i in range(3):
        a = i * 2 * PI / 3
        cyl((cos(a) * 0.12, sin(a) * 0.12, 0.035), (cos(a) * 0.12, sin(a) * 0.12, 0.05), 0.012, 'Iron', IRON, seg=5)


def p_generator():
    begin('Pad_Generator')
    for sx in (-1, 1):
        beam((sx * 0.38, -0.95, 0.06), (sx * 0.38, 0.95, 0.06), 0.1, 0.12, 'Paint', BLACK, bevel=0.015)
    box((0, 0, 0.66), (0.95, 1.75, 1.05), 'Paint', OLIVE, bevel=0.04, jit=0.02)
    for sx in (-1, 1):
        for i in range(7):
            box((sx * 0.478, 0.25, 0.4 + i * 0.075), (0.02, 0.8, 0.04), 'Paint', OLIVE_D, r=rot(ry=sx * 25))
        box((sx * 0.478, -0.5, 0.7), (0.012, 0.5, 0.75), 'Paint', OLIVE_D)
        box((sx * 0.49, -0.3, 0.7), (0.02, 0.03, 0.12), 'Paint', BLACK)
    box((0, -0.88, 0.85), (0.6, 0.02, 0.4), 'Paint', (0.05, 0.05, 0.05))
    for i, c in enumerate((RED, (0.1, 0.5, 0.15), YELLOW, (0.8, 0.8, 0.8))):
        box((-0.2 + i * 0.13, -0.895, 0.95), (0.05, 0.015, 0.05), 'Paint', c)
    box((0, -0.895, 0.78), (0.3, 0.015, 0.1), 'Paint', (0.3, 0.32, 0.3))
    cyl((0.25, 0.6, 1.18), (0.25, 0.6, 1.6), 0.045, 'Paint', (0.12, 0.11, 0.1), seg=6)
    box((0.25, 0.62, 1.62), (0.14, 0.14, 0.012), 'Paint', (0.12, 0.11, 0.1), r=rot(rx=25))
    cyl((-0.25, -0.5, 1.18), (-0.25, -0.5, 1.23), 0.07, 'Paint', YELLOW, seg=8)
    torus((0, 0, 1.2), (1, 0, 0), 0.07, 0.016, 'Paint', BLACK, seg=8, rseg=4)
    for k in range(3):
        torus((0.95, -0.6, 0.03 + k * 0.05), (0, 0, 1), 0.24, 0.025, 'Paint', (0.9, 0.45, 0.05), seg=10, rseg=4)
    jerrycan((-0.8, -0.5, 0), 80); jerrycan((-0.82, -0.1, 0), 95)
    # light mast with two floodlights
    cyl((0.0, 0.98, 0.1), (0.0, 0.98, 2.2), 0.045, 'Paint', (0.3, 0.3, 0.3), seg=6)
    cyl((0.0, 0.98, 2.2), (0.0, 0.98, 3.9), 0.03, 'Paint', (0.4, 0.4, 0.4), seg=6)
    cyl((-0.5, 0.98, 3.85), (0.5, 0.98, 3.85), 0.02, 'Paint', (0.3, 0.3, 0.3), seg=5)
    for sx in (-1, 1):
        M = rot(rx=-28, rz=sx * -15)
        c = V((sx * 0.45, 0.93, 3.98))
        box(c, (0.36, 0.14, 0.26), 'Paint', (0.07, 0.07, 0.07), r=M, bevel=0.015)
        box(c + M @ V((0, -0.075, 0)), (0.3, 0.012, 0.2), 'PadLightEmissive', (1, 0.85, 0.5), r=M)


BUILDERS = [p_ballista, p_bolt, p_bombard, p_trebuchet, p_boulder, p_arrow, p_tent_a, p_tent_b, p_cart, p_crates,
            p_barrels, p_weaponrack, p_campfire, p_bannerpole, p_pavise, p_firepot, p_palisade, p_haystack, p_stakes,
            p_truck, p_padcrates, p_windsock, p_padlight, p_generator]


# =============================================================================== main
def hierarchy(o):
    out = [o]
    for c in o.children:
        out += hierarchy(c)
    return out


def bbox(root):
    bpy.context.view_layer.update()
    mn = V((1e9, 1e9, 1e9)); mx = -mn
    for o in hierarchy(root):
        if o.type == 'MESH':
            for v in o.data.vertices:
                w = o.matrix_world @ v.co
                for i in range(3):
                    mn[i] = min(mn[i], w[i]); mx[i] = max(mx[i], w[i])
    return mn, mx


def main():
    args = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    only = [a for a in args if a not in ('preview',)]
    bpy.ops.wm.read_factory_settings(use_empty=True)
    stats = {}
    for fnb in BUILDERS:
        fnb()
        prop = PROPS[-1]
        if only and prop.name not in only:
            continue
        build(prop)
        mn, mx = bbox(prop.root)
        stats[prop.name] = {
            'tris': prop.tris,
            'bbox_min_blender': [round(x, 2) for x in mn], 'bbox_max_blender': [round(x, 2) for x in mx],
            'size_three_xyz': [round(mx.x - mn.x, 2), round(mx.z - mn.z, 2), round(mx.y - mn.y, 2)],
            'nodes': [n for n in prop.order],
            'materials': sorted({m for p in prop.parts.values() for m in p.chunks}),
        }
        print(prop.name, prop.tris, stats[prop.name]['size_three_xyz'])
    json.dump(stats, open(os.path.join(HERE, 'props_stats.json'), 'w'), indent=1)
    if not only:
        bpy.ops.object.select_all(action='SELECT')
        kw = dict(filepath=OUT, export_format='GLB', export_apply=True, export_yup=True, use_selection=True,
                  export_animations=False, export_materials='EXPORT', export_normals=True, export_texcoords=True)
        try:
            bpy.ops.export_scene.gltf(export_vertex_color='ACTIVE', export_all_vertex_colors=False, **kw)
        except TypeError as e:
            print('fallback export', e)
            bpy.ops.export_scene.gltf(**kw)
        print('exported', OUT, os.path.getsize(OUT))
    if 'preview' in args:
        preview([p for p in PROPS if not only or p.name in only], stats)


def preview(props, stats):
    import numpy as np
    sc = bpy.context.scene
    try:
        sc.render.engine = 'BLENDER_EEVEE'
    except Exception:
        sc.render.engine = 'BLENDER_EEVEE_NEXT'
    TW, TH = (640, 480) if len(props) > 3 else (1000, 750)
    sc.render.resolution_x, sc.render.resolution_y = TW, TH
    sc.render.film_transparent = False
    sc.view_settings.view_transform = 'Standard'
    w = bpy.data.worlds.new('W'); sc.world = w; w.use_nodes = True
    w.node_tree.nodes['Background'].inputs[0].default_value = (0.55, 0.65, 0.8, 1)
    w.node_tree.nodes['Background'].inputs[1].default_value = 0.45
    sun = bpy.data.objects.new('Sun', bpy.data.lights.new('Sun', 'SUN'))
    sun.data.energy = 3.0; sun.data.angle = 0.03
    sun.rotation_euler = (rad(55), 0, rad(-40))
    sc.collection.objects.link(sun)
    bpy.ops.mesh.primitive_plane_add(size=200)
    g = bpy.context.active_object
    gm = bpy.data.materials.new('G'); gm.use_nodes = True
    gm.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value = (0.2, 0.24, 0.12, 1)
    g.data.materials.append(gm)
    cam = bpy.data.objects.new('Cam', bpy.data.cameras.new('Cam'))
    cam.data.lens = 50
    sc.collection.objects.link(cam); sc.camera = cam
    roots = {p.name: p.root for p in props}
    tiles = []
    for p in props:
        for q in props:
            hide = q is not p
            for o in hierarchy(q.root):
                o.hide_render = hide
        mn, mx = bbox(p.root)
        centered = mn.z < -0.05
        g.location.z = mn.z if centered else 0
        c = (mn + mx) / 2
        rad_ = (mx - mn).length / 2
        views = [V((0.75, -1.0, 0.55))] if len(props) > 3 else [V((0.75, -1.0, 0.55)), V((-1.0, -0.15, 0.2)), V((-0.5, 1.0, 0.7))]
        for vi, d in enumerate(views):
            d = d.normalized()
            cam.location = c + d * rad_ * (3.6 if len(props) > 3 else 3.0)
            cam.rotation_euler = (c - cam.location).to_track_quat('-Z', 'Y').to_euler()
            fp = os.path.join(PREV, f'_tile_{p.name}_{vi}.png')
            sc.render.filepath = fp
            bpy.ops.render.render(write_still=True)
            tiles.append((p.name, fp))
    if len(props) <= 3:
        return
    # contact sheets 3x2
    per = 6
    for si in range(0, len(tiles), per):
        sheet = np.zeros((TH * 2, TW * 3, 4), dtype=np.float32)
        names = []
        for k, (name, fp) in enumerate(tiles[si:si + per]):
            img = bpy.data.images.load(fp)
            a = np.array(img.pixels[:], dtype=np.float32).reshape(TH, TW, 4)
            r, cidx = divmod(k, 3)
            sheet[TH * (1 - r):TH * (2 - r), TW * cidx:TW * (cidx + 1)] = a
            names.append(name)
            bpy.data.images.remove(img)
        out = bpy.data.images.new('sheet', TW * 3, TH * 2)
        out.pixels = sheet.ravel()
        out.filepath_raw = os.path.join(PREV, f'props_sheet{si // per + 1}.png')
        out.file_format = 'PNG'
        out.save()
        print('sheet', si // per + 1, names)
    for name, fp in tiles:
        if len(props) > 3:
            try: os.remove(fp)
            except OSError: pass


main()
