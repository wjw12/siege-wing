# Siege Wing — village & nature kit generator (headless Blender 5.2)
# blender.exe -b -P village.py   ->  assets/models/village.glb
# Blender coords: Z up, fronts face -Y.  All albedo is in vertex colours (COLOR_0, incl. baked AO).
# TEXCOORD_0.x = wind sway weight (0 rigid .. 1 outer foliage), TEXCOORD_0.y = normalised height.
import bpy, bmesh, math, random, json, os
from mathutils import Vector, Matrix, noise
from mathutils.bvhtree import BVHTree

ROOT = r"C:\Users\shaoy\game"
OUT = ROOT + r"\assets\models\village.glb"
VEG_ONLY = os.environ.get('VILLAGE_VEG_ONLY')      # optional: path of a vegetation-only test export
pi = math.pi


def C(h):
    h = h.lstrip('#')
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    f = lambda c: c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    return (f(r), f(g), f(b))


def lerp(a, b, t): return a + (b - a) * t
def lerpc(a, b, t): return tuple(lerp(a[i], b[i], t) for i in range(3))
def mulc(a, k): return (a[0] * k, a[1] * k, a[2] * k)
def clamp(x, a=0.0, b=1.0): return max(a, min(b, x))
def hsh(*a): return random.Random(hash(tuple(int(x) for x in a)) & 0xffffffff).random()
def T(x, y, z): return Matrix.Translation((x, y, z))
def Rz(a): return Matrix.Rotation(a, 4, 'Z')
def Rx(a): return Matrix.Rotation(a, 4, 'X')
def Ry(a): return Matrix.Rotation(a, 4, 'Y')
I4 = Matrix.Identity(4)

_ico = {}
def ico_data(sub):
    if sub not in _ico:
        bm = bmesh.new()
        bmesh.ops.create_icosphere(bm, subdivisions=sub, radius=1.0)
        bm.verts.ensure_lookup_table()
        _ico[sub] = ([v.co.copy() for v in bm.verts], [[v.index for v in f.verts] for f in bm.faces])
        bm.free()
    return _ico[sub]


# palette (sRGB hex -> linear)
PLASTER = C('#cbbd9c'); PLASTER2 = C('#b9a47c')
TIMBER = C('#4a3524'); TIMBER_D = C('#2c2018'); TIMBER_L = C('#6e5438'); PLANK = C('#6a5138')
THATCH = C('#b99c5c'); THATCH_D = C('#8a7243'); THATCH_OLD = C('#9c8a60')
STONE = C('#8d857a'); STONE_W = C('#a39a8a'); STONE_D = C('#5f5a54')
SHINGLE = C('#6b5a4a'); SHINGLE2 = C('#7d6650')
BARK = C('#4b3b2c'); DARK = C('#15110e'); IRON = C('#2a2a2c')


class B:
    def __init__(s, name, seed=1, ground=0.0, ao_dist=2.5, ao_strength=0.62):
        s.name = name; s.v = []; s.w = []; s.f = []
        s.rng = random.Random(seed); s.seed = seed
        s.ground = ground; s.ao_dist = ao_dist; s.ao_strength = ao_strength
        s.children = []

    # ---------- low level
    def vert(s, p, w=0.0):
        s.v.append(Vector(p)); s.w.append(w); return len(s.v) - 1

    def vary(s, col, jit):
        if jit <= 0: return col
        k = 1 + s.rng.uniform(-jit, jit)
        return tuple(max(0, col[i] * k * (1 + s.rng.uniform(-jit, jit) * 0.3)) for i in range(3))

    def face(s, idx, mat, col, smooth=False, jit=0.0):
        if isinstance(col, list): cols = col
        else:
            c = s.vary(col, jit); cols = [c] * len(idx)
        s.f.append((list(idx), mat, smooth, [tuple(c) for c in cols]))

    def face_auto(s, idx, mat, col, ref, smooth=False, jit=0.0, direction=False):
        """orient so the normal points away from point ref (or along ref if direction)"""
        p = [s.v[i] for i in idx]
        n = Vector((0, 0, 0))
        for i in range(len(p)):
            a, b = p[i], p[(i + 1) % len(p)]
            n += Vector(((a.y - b.y) * (a.z + b.z), (a.z - b.z) * (a.x + b.x), (a.x - b.x) * (a.y + b.y)))
        cen = sum(p, Vector()) / len(p)
        d = Vector(ref) if direction else cen - Vector(ref)
        if n.dot(d) < 0:
            idx = list(reversed(idx))
            if isinstance(col, list): col = list(reversed(col))
        s.face(idx, mat, col, smooth, jit)

    # ---------- primitives
    def hexa(s, pts, mat, col, jit=0.0, skip=(), M=None, perface=False, wind=0.0):
        """pts: 4 bottom CCW (seen from top) + 4 top. skip subset of bottom,top,s0..s3"""
        M = M or I4
        ids = [s.vert(M @ Vector(p), wind) for p in pts]
        c = s.vary(col, jit)
        fs = {'bottom': (0, 3, 2, 1), 'top': (4, 5, 6, 7), 's0': (0, 1, 5, 4), 's1': (1, 2, 6, 5), 's2': (2, 3, 7, 6), 's3': (3, 0, 4, 7)}
        for k, q in fs.items():
            if k in skip: continue
            s.face([ids[i] for i in q], mat, s.vary(c, jit * 0.6) if perface else c)

    def box(s, lo, hi, mat, col, jit=0.0, skip=(), M=None, perface=False, taper=1.0, wind=0.0):
        cx, cy = (lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2
        tx = lambda x: cx + (x - cx) * taper
        ty = lambda y: cy + (y - cy) * taper
        p = [(lo[0], lo[1], lo[2]), (hi[0], lo[1], lo[2]), (hi[0], hi[1], lo[2]), (lo[0], hi[1], lo[2]),
             (tx(lo[0]), ty(lo[1]), hi[2]), (tx(hi[0]), ty(lo[1]), hi[2]), (tx(hi[0]), ty(hi[1]), hi[2]), (tx(lo[0]), ty(hi[1]), hi[2])]
        s.hexa(p, mat, col, jit, skip, M, perface, wind)

    def beam(s, p0, p1, w, h, mat, col, jit=0.0, up=(0, 0, 1), M=None, skip=(), wind=0.0):
        p0 = Vector(p0); p1 = Vector(p1); d = p1 - p0; L = d.length
        if L < 1e-6: return
        e1 = d / L; upv = Vector(up)
        e2 = upv.cross(e1)
        if e2.length < 1e-4: e2 = Vector((0, 1, 0)).cross(e1)
        if e2.length < 1e-4: e2 = Vector((1, 0, 0)).cross(e1)
        e2.normalize(); e3 = e1.cross(e2)
        P = lambda a, b, c: p0 + e1 * a + e2 * b + e3 * c
        pts = [P(0, -w / 2, -h / 2), P(L, -w / 2, -h / 2), P(L, w / 2, -h / 2), P(0, w / 2, -h / 2),
               P(0, -w / 2, h / 2), P(L, -w / 2, h / 2), P(L, w / 2, h / 2), P(0, w / 2, h / 2)]
        s.hexa(pts, mat, col, jit, skip, M, wind=wind)

    def cyl(s, p0, p1, r0, r1, n, mat, col, jit=0.0, caps=(False, True), smooth=False, wind=(0, 0), M=None, perface=False, twist=0.0):
        M = M or I4
        p0 = Vector(p0); p1 = Vector(p1); ax = (p1 - p0).normalized()
        e1 = ax.cross(Vector((0, 0, 1)))
        if e1.length < 1e-3: e1 = Vector((1, 0, 0))
        e1.normalize(); e2 = ax.cross(e1)
        a = [s.vert(M @ (p0 + (e1 * math.cos(2 * pi * i / n) + e2 * math.sin(2 * pi * i / n)) * r0), wind[0]) for i in range(n)]
        b = [s.vert(M @ (p1 + (e1 * math.cos(2 * pi * i / n + twist) + e2 * math.sin(2 * pi * i / n + twist)) * r1), wind[1]) for i in range(n)]
        c = s.vary(col, jit)
        for i in range(n):
            j = (i + 1) % n
            s.face([a[i], a[j], b[j], b[i]], mat, s.vary(c, jit) if perface else c, smooth)
        if caps[1]: s.face(b, mat, c)
        if caps[0]: s.face(list(reversed(a)), mat, c)
        return a, b

    def blob(s, c, r, sub, mat, colfn, disp=0.2, nscale=1.3, smooth=True, windfn=None, M=None, zmin=None):
        M = M or I4
        vs, fs = ico_data(sub)
        c = Vector(c); r = Vector((r, r, r)) if isinstance(r, (int, float)) else Vector(r)
        off = Vector((s.rng.uniform(-50, 50), s.rng.uniform(-50, 50), s.rng.uniform(-50, 50)))
        rot = Matrix.Rotation(s.rng.uniform(0, 6.28), 3, 'Z') @ Matrix.Rotation(s.rng.uniform(0, 6.28), 3, 'X')
        ids = []; cols = []
        for d in vs:
            d = rot @ d
            f = 1 + disp * noise.noise(d * nscale + off)
            p = c + Vector((d.x * r.x, d.y * r.y, d.z * r.z)) * f
            if zmin is not None and p.z < zmin: p.z = zmin
            p = M @ p
            ids.append(s.vert(p, windfn(p) if windfn else 0.0)); cols.append(colfn(p, d))
        for q in fs:
            cl = [cols[i] for i in q]
            if not smooth:
                a = (cl[0][0] + cl[1][0] + cl[2][0]) / 3, (cl[0][1] + cl[1][1] + cl[2][1]) / 3, (cl[0][2] + cl[1][2] + cl[2][2]) / 3
                cl = [a] * 3
            s.face([ids[i] for i in q], mat, cl, smooth)

    # ---------- wall-local helpers (M: x along wall, -y outward, z up)
    def panel(s, M, x0, x1, z0, z1, mat, col, cell=(1.0, 1.0), jit=0.05, vj=0.0, y=0.0, colfn=None):
        nx = max(1, round((x1 - x0) / cell[0])); nz = max(1, round((z1 - z0) / cell[1]))
        g = [[s.vert(M @ Vector((lerp(x0, x1, i / nx) + (s.rng.uniform(-vj, vj) if 0 < i < nx else 0),
                                 y - (s.rng.uniform(0, vj) if vj else 0),
                                 lerp(z0, z1, j / nz) + (s.rng.uniform(-vj, vj) if 0 < j < nz else 0)))) for j in range(nz + 1)] for i in range(nx + 1)]
        for i in range(nx):
            for j in range(nz):
                c = colfn(i, j, nx, nz) if colfn else col
                s.face([g[i][j], g[i + 1][j], g[i + 1][j + 1], g[i][j + 1]], mat, c, jit=jit)

    def gable_tri(s, M, W, z0, z1, mat, col, rows=3, jit=0.05, y=0.0):
        for r in range(rows):
            ta, tb = r / rows, (r + 1) / rows
            za, zb = lerp(z0, z1, ta), lerp(z0, z1, tb)
            wa, wb = W / 2 * (1 - ta), W / 2 * (1 - tb)
            for sg in (-1, 1):
                pts = [(min(0, sg * wa), za), (max(0, sg * wa), za), (max(0, sg * wb), zb), (min(0, sg * wb), zb)]
                if wb < 1e-6: pts = pts[:3] if sg > 0 else [pts[0], pts[1], pts[3]]
                s.face([s.vert(M @ Vector((p[0], y, p[1]))) for p in pts], mat, col, jit=jit)

    def wbox(s, M, x0, x1, z0, z1, out, mat, col, jit=0.0, inn=0.02, back=False, perface=False):
        p = [(x0, inn, z0), (x1, inn, z0), (x1, inn, z1), (x0, inn, z1), (x0, -out, z0), (x1, -out, z0), (x1, -out, z1), (x0, -out, z1)]
        s.hexa(p, mat, col, jit, () if back else ('bottom',), M, perface)

    def wbeam(s, M, a, b, w=0.16, out=0.05, mat='Timber', col=TIMBER, jit=0.12, y=0.0, ends=True):
        dx, dz = b[0] - a[0], b[1] - a[1]; L = math.hypot(dx, dz)
        if L < 1e-6: return
        nx, nz = -dz / L * w / 2, dx / L * w / 2
        q = [(a[0] - nx, a[1] - nz), (b[0] - nx, b[1] - nz), (b[0] + nx, b[1] + nz), (a[0] + nx, a[1] + nz)]
        p = [(x, y + 0.02, z) for x, z in q] + [(x, y - out, z) for x, z in q]
        s.hexa(p, mat, col, jit, ('bottom',) if ends else ('bottom', 's1', 's3'), M)

    def window(s, M, x, z, w=0.7, h=0.9, shutters=True, y=0.0):
        s.wbox(M, x - w / 2, x + w / 2, z, z + h, 0.03 - y, 'Timber', DARK)
        s.wbeam(M, (x - w / 2 - 0.1, z - 0.05), (x + w / 2 + 0.1, z - 0.05), 0.1, 0.09, y=y)
        s.wbeam(M, (x, z), (x, z + h), 0.05, 0.05, y=y, ends=False)
        if shutters:
            for sg in (-1, 1):
                s.wbox(M, x + sg * (w / 2 + 0.04), x + sg * (w / 2 + 0.04 + w * 0.48), z - 0.02, z + h + 0.02, 0.06 - y, 'Timber', PLANK, jit=0.15)

    def door(s, M, x, z, w=1.0, h=1.95, y=0.0, col=PLANK):
        n = max(2, round(w / 0.28))
        for i in range(n):
            s.wbox(M, x - w / 2 + i * w / n, x - w / 2 + (i + 1) * w / n, z, z + h, 0.04 - y, 'Timber', mulc(col, 0.75), jit=0.15)
        for a, b in (((x - w / 2 - 0.09, z), (x - w / 2 - 0.09, z + h + 0.1)), ((x + w / 2 + 0.09, z), (x + w / 2 + 0.09, z + h + 0.1)),
                     ((x - w / 2 - 0.2, z + h + 0.1), (x + w / 2 + 0.2, z + h + 0.1))):
            s.wbeam(M, a, b, 0.18, 0.1, y=y)
        s.wbeam(M, (x - w / 2 + 0.05, z + h * 0.25), (x + w / 2 - 0.05, z + h * 0.25), 0.1, 0.07 - y, col=IRON, y=0)
        s.wbeam(M, (x - w / 2 + 0.05, z + h * 0.75), (x + w / 2 - 0.05, z + h * 0.75), 0.1, 0.07 - y, col=IRON, y=0)

    def walls(s, L, D, cx=0.0, cy=0.0):
        """returns [(M, width)] front(-Y), right(+X), back(+Y), left(-X)"""
        return [(T(cx, cy - D / 2, 0), L), (T(cx + L / 2, cy, 0) @ Rz(pi / 2), D), (T(cx, cy + D / 2, 0) @ Rz(pi), L), (T(cx - L / 2, cy, 0) @ Rz(-pi / 2), D)]

    def wall_ring(s, L, D, z0, z1, mat, col, cell=(1.0, 1.0), jit=0.05, vj=0.0, cx=0.0, cy=0.0, colfn=None, sides=(0, 1, 2, 3)):
        ws = s.walls(L, D, cx, cy)
        for k in sides:
            M, W = ws[k]
            s.panel(M, -W / 2, W / 2, z0, z1, mat, col, cell, jit, vj, colfn=colfn)
        return ws

    def stone_box(s, lo, hi, cell=(0.6, 0.45), jit=0.16, col=STONE, top=True, vj=0.03, mat='Stone'):
        L, D = hi[0] - lo[0], hi[1] - lo[1]
        s.wall_ring(L, D, lo[2], hi[2], mat, col, cell, jit, vj, (lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2)
        if top:
            ids = [s.vert(p) for p in ((lo[0], lo[1], hi[2]), (hi[0], lo[1], hi[2]), (hi[0], hi[1], hi[2]), (lo[0], hi[1], hi[2]))]
            s.face(ids, mat, mulc(col, 0.9))

    def frame(s, M, W, z0, z1, studs=3, rail=True, braces=(), w=0.17, out=0.05, x0=None, x1=None):
        """timber framing on a wall rectangle; braces: list of (stud_bay, 'l'|'r'|'x')"""
        x0 = -W / 2 if x0 is None else x0; x1 = W / 2 if x1 is None else x1
        s.wbeam(M, (x0, z0 + w / 2), (x1, z0 + w / 2), w, out + 0.01, ends=False)
        s.wbeam(M, (x0, z1 - w / 2), (x1, z1 - w / 2), w, out + 0.01, ends=False)
        xs = [lerp(x0 + w / 2, x1 - w / 2, i / (studs + 1)) for i in range(studs + 2)]
        for x in xs: s.wbeam(M, (x, z0 + w), (x, z1 - w), w, out, ends=False)
        zm = (z0 + z1) / 2
        if rail: s.wbeam(M, (x0 + w, zm), (x1 - w, zm), w * 0.8, out - 0.01, ends=False)
        for bay, kind in braces:
            if bay >= len(xs) - 1: continue
            a, b = xs[bay] + w / 2, xs[bay + 1] - w / 2
            lo, hi = (z0 + w, zm - w * 0.4) if rail else (z0 + w, z1 - w)
            if kind in 'lx': s.wbeam(M, (a, lo), (b, hi), w * 0.7, out - 0.015, ends=False)
            if kind in 'rx': s.wbeam(M, (a, hi), (b, lo), w * 0.7, out - 0.015, ends=False)
        return xs

    # ---------- roofs
    def sheet(s, fn, nu, nv, t, mat, colfn, skip=(), smooth=False, tdir=(0, 0, -1), windfn=None, botmask=None, step=0.0):
        tdir = Vector(tdir)
        top = [[s.vert(fn(i, j)) for j in range(nv + 1)] for i in range(nu + 1)]
        bot = [[s.vert(s.v[top[i][j]] + tdir * t) for j in range(nv + 1)] for i in range(nu + 1)]
        lift = [[(s.vert(s.v[top[i][j]] - tdir * step) if (step and j > 0) else top[i][j]) for j in range(nv + 1)] for i in range(nu + 1)]
        under = [[(s.vert(s.v[top[i][j]].lerp(s.v[top[i][j - 1]], 0.3)) if (step and j > 0) else top[i][j]) for j in range(nv + 1)] for i in range(nu + 1)]
        allp = [s.v[top[i][j]] for i in range(nu + 1) for j in range(nv + 1)]
        cen = sum(allp, Vector()) / len(allp) + tdir * (t / 2)
        for i in range(nu):
            for j in range(nv):
                q = [under[i][j], under[i + 1][j], lift[i + 1][j + 1], lift[i][j + 1]]
                s.face_auto(q, mat, colfn(i, j, 'top'), -tdir, smooth, direction=True)
                if botmask is None or botmask(i, j):
                    qb = [bot[i][j], bot[i + 1][j], bot[i + 1][j + 1], bot[i][j + 1]]
                    s.face_auto(qb, mat, colfn(i, j, 'bot'), tdir, smooth, direction=True)
        edges = []
        if 'j0' not in skip: edges += [((i, 0), (i + 1, 0)) for i in range(nu)]
        if 'j1' not in skip: edges += [((i, nv), (i + 1, nv)) for i in range(nu)]
        if 'i0' not in skip: edges += [((0, j), (0, j + 1)) for j in range(nv)]
        if 'i1' not in skip: edges += [((nu, j), (nu, j + 1)) for j in range(nv)]
        for a, b in edges:
            tp = lift if a[1] == b[1] == nv else top
            q = [tp[a[0]][a[1]], tp[b[0]][b[1]], bot[b[0]][b[1]], bot[a[0]][a[1]]]
            s.face_auto(q, mat, colfn(a[0], a[1], 'edge'), cen)

    def gable_roof(s, M, L, W, z0, z1, mat='Thatch', col=THATCH, col2=THATCH_D, og=0.45, oe=0.55, t=0.32, nx=12, nr=5,
                   sag=0.2, rag=0.12, bulge=0.0, jit=0.08, vcap=None, lift=0.0, seed=0, band=0.08, sides=(1, -1)):
        rise = z1 - z0; half = W / 2
        vext = (half + oe) / half if vcap is None else vcap
        sd = s.seed * 7.31 + seed

        def uv(i, j):
            x = -L / 2 - og if i == 0 else (L / 2 + og if i == nx else lerp(-L / 2, L / 2, (i - 1) / (nx - 2)))
            if vcap is None: v = vext if j == nr else (j / (nr - 1))
            else: v = j / nr * vcap
            return x, v

        def mk(sg):
            def fn(i, j):
                x, v = uv(i, j); u = (x + L / 2 + og) / (L + 2 * og)
                y = sg * half * v; z = z1 - rise * v
                fade = max(0.0, 1 - v) if vcap is None else 1 - v
                z -= (sag * math.sin(pi * u) + sag * 0.45 * noise.noise(Vector((u * 3.1 + sd, 0.3, sd)))) * fade
                z += bulge * math.sin(pi * min(v / vext, 1))
                if vcap is None:
                    if j == nr:
                        r = hsh(i, 91, s.seed + seed) - 0.5
                        y += sg * r * rag; z -= r * rag * rise / half
                        z -= abs(noise.noise(Vector((u * 9 + sd, sg, 1.7)))) * rag * 0.8
                else:
                    if j == nr:
                        r = hsh(i, 17, s.seed + seed)
                        y += sg * r * 0.12; z -= r * 0.12 * rise / half
                if i in (0, nx) and j > 0: x += (hsh(j, i, 5 + s.seed) - 0.5) * rag
                return M @ Vector((x, y, z + lift))
            return fn

        def mkcol(sg):
            def vc(i, j):
                x, v = uv(i, j)
                n1 = noise.noise(Vector((x * 0.35 + sd, v * 1.3 * sg + 3.0, sd * 0.3)))
                n2 = noise.noise(Vector((x * 1.6 + sd, v * 0.6 + sg, 9.1)))
                c = lerpc(col, col2, clamp(0.42 + 0.7 * n1 + 0.3 * n2))
                return mulc(c, 0.84 + 0.2 * (1 - min(v, 1)))   # darker, wetter toward the eave

            def colfn(i, j, kind):
                if kind == 'bot': return mulc(col2, 0.4)
                if kind == 'edge': return s.vary(mulc(col2, 0.75), jit)
                k = (1 - band * (j % 2)) * (1 + s.rng.uniform(-jit, jit))
                if j == 0 and vcap is None: k *= 0.9
                return [mulc(vc(a, b), k) for a, b in ((i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1))]
            return colfn
        bm = (lambda i, j: j == nr - 1 or i == 0 or i == nx - 1) if vcap is None else None
        for sg in sides:
            s.sheet(mk(sg), nx, nr, t, mat, mkcol(sg), skip=('j0',), botmask=bm, step=(0.0 if vcap is not None else (0.09 if mat == 'Thatch' else 0.05)))

    def shed_roof(s, M, x0, x1, y0, y1, zh, zl, mat='Thatch', col=THATCH, col2=THATCH_D, t=0.22, nx=6, nr=3, rag=0.08, sag=0.08, jit=0.09, ov=0.25):
        """single slope: high edge at y0 (z=zh), low edge at y1 (z=zl), local coords of M"""
        def fn(i, j):
            u = i / nx; v = j / nr
            x = lerp(x0 - ov, x1 + ov, u); y = lerp(y0, y1, v); z = lerp(zh, zl, v) - sag * math.sin(pi * u) * v
            if j == nr:
                r = hsh(i, 33, s.seed) - 0.5; y += r * rag * (1 if y1 > y0 else -1); z -= abs(r) * rag
            return M @ Vector((x, y, z))

        def colfn(i, j, kind):
            if kind == 'bot': return mulc(col2, 0.45)
            c = lerpc(col, col2, clamp(0.5 + 0.9 * noise.noise(Vector((i * 0.7 + s.seed, j, 4.2)))))
            return s.vary(mulc(c, 1 - 0.07 * (j % 2)), jit)
        s.sheet(fn, nx, nr, t, mat, colfn, step=0.07 if mat == 'Thatch' else 0.045)

    def chimney(s, x, y, w, d, z0, z1, col=STONE):
        s.stone_box((x - w / 2, y - d / 2, z0), (x + w / 2, y + d / 2, z1), cell=(0.5, 0.5), col=col, top=False)
        s.stone_box((x - w / 2 - 0.08, y - d / 2 - 0.08, z1), (x + w / 2 + 0.08, y + d / 2 + 0.08, z1 + 0.2), cell=(1, 1), col=mulc(col, 0.85))
        s.box((x - w / 2 + 0.12, y - d / 2 + 0.12, z1 + 0.2), (x + w / 2 - 0.12, y + d / 2 - 0.12, z1 + 0.24), 'Stone', DARK, skip=('bottom',))

    def woodpile(s, M, x0, x1, z0, h, depth=0.6):
        n = max(2, round((x1 - x0) / 0.35)); rows = max(1, round(h / 0.3))
        for r in range(rows):
            for i in range(n):
                a = x0 + i * (x1 - x0) / n
                s.wbox(M, a + 0.01, a + (x1 - x0) / n - 0.01, z0 + r * h / rows, z0 + (r + 1) * h / rows - 0.02,
                       depth * s.rng.uniform(0.85, 1.0), 'Timber', lerpc(TIMBER_L, C('#9a7a50'), s.rng.random()), jit=0.2, back=False)

    # ---------- finish
    def bake_ao(s, n=14):
        if not s.f: return
        D = s.ao_dist
        bvh = BVHTree.FromPolygons([tuple(v) for v in s.v], [f[0] for f in s.f])
        rr = random.Random(5); dirs = []
        for k in range(n):
            u = (k + 0.5) / n; ph = 2 * pi * (k * 0.618034 + rr.random() * 0.05)
            r = math.sqrt(u); dirs.append(Vector((r * math.cos(ph), r * math.sin(ph), math.sqrt(1 - u))))
        ao = []
        vsum = {}; vcnt = {}
        for f in s.f:
            p = [s.v[i] for i in f[0]]
            nrm = Vector((0, 0, 0))
            for i in range(len(p)):
                a, b = p[i], p[(i + 1) % len(p)]
                nrm += Vector(((a.y - b.y) * (a.z + b.z), (a.z - b.z) * (a.x + b.x), (a.x - b.x) * (a.y + b.y)))
            if nrm.length < 1e-12:
                ao.append([1.0] * len(p)); continue
            nrm.normalize()
            t1 = nrm.cross(Vector((0, 0, 1)))
            if t1.length < 1e-3: t1 = Vector((1, 0, 0))
            t1.normalize(); t2 = nrm.cross(t1)
            wd = [t1 * d.x + t2 * d.y + nrm * d.z for d in dirs]
            cen = sum(p, Vector()) / len(p)
            res = []
            for k, v in enumerate(p):
                o = v + nrm * 0.04 + (cen - v) * 0.1
                occ = 0.0
                for d in wd:
                    hit = bvh.ray_cast(o, d, D)
                    dd = hit[3] if hit[0] is not None else None
                    if s.ground is not None and d.z < -1e-3:
                        tg = (s.ground - o.z) / d.z
                        if 0 < tg < D and (dd is None or tg < dd): dd = tg
                    if dd is not None: occ += 1 - dd / D
                a = 1 - occ / n
                res.append(a)
                if f[2]:
                    vi = f[0][k]; vsum[vi] = vsum.get(vi, 0) + a; vcnt[vi] = vcnt.get(vi, 0) + 1
            ao.append(res)
        for fi, f in enumerate(s.f):
            for k in range(len(f[0])):
                a = ao[fi][k]
                if f[2]: a = vsum[f[0][k]] / vcnt[f[0][k]]
                m = lerp(1 - s.ao_strength, 1.0, clamp(a) ** 1.3)
                f[3][k] = mulc(f[3][k], m)

    def tris(s): return sum(len(f[0]) - 2 for f in s.f)

    def build(s, parent=None, loc=(0, 0, 0)):
        s.bake_ao()
        me = bpy.data.meshes.new(s.name)
        me.from_pydata([tuple(v) for v in s.v], [], [f[0] for f in s.f])
        mats = []
        for f in s.f:
            if f[1] not in mats: mats.append(f[1])
        for m in mats: me.materials.append(MATS[m])
        zs = [v.z for v in s.v]; z0, z1 = min(zs), max(zs)
        ca = me.color_attributes.new('Col', 'FLOAT_COLOR', 'CORNER')
        uv = me.uv_layers.new(name='UVMap')
        for poly, f in zip(me.polygons, s.f):
            poly.material_index = mats.index(f[1]); poly.use_smooth = f[2]
            for k, li in enumerate(poly.loop_indices):
                c = f[3][k]; ca.data[li].color = (c[0], c[1], c[2], 1.0)
                vi = f[0][k]
                uv.data[li].uv = (s.w[vi], 1.0 - (s.v[vi].z - max(z0, 0)) / max(1e-6, z1 - max(z0, 0)))
        me.color_attributes.active_color = ca
        me.color_attributes.render_color_index = 0
        me.update()
        ob = bpy.data.objects.new(s.name, me)
        bpy.context.scene.collection.objects.link(ob)
        ob.location = loc
        if parent: ob.parent = parent
        STATS[s.name] = {'tris': s.tris(), 'mats': mats,
                         'bbox': [round(max(v[i] for v in s.v) - min(v[i] for v in s.v), 2) for i in range(3)]}
        for ch, cl in s.children: ch.build(ob, cl)
        return ob


MATS = {}; STATS = {}
def make_materials():
    spec = {'Plaster': 0.92, 'Timber': 0.82, 'Thatch': 0.95, 'Stone': 0.88, 'Shingle': 0.8, 'Bark': 0.9, 'Leaf': 0.72, 'Rock': 0.9}
    for name, rough in spec.items():
        m = bpy.data.materials.new(name); m.use_nodes = True
        nt = m.node_tree; bsdf = nt.nodes['Principled BSDF']
        bsdf.inputs['Roughness'].default_value = rough
        bsdf.inputs['Metallic'].default_value = 0.0
        a = nt.nodes.new('ShaderNodeVertexColor'); a.layer_name = 'Col'
        nt.links.new(a.outputs['Color'], bsdf.inputs['Base Color'])
        m.use_backface_culling = True
        MATS[name] = m


# =====================================================================================
#  BUILDINGS
# =====================================================================================
def plaster_fn(b, base=PLASTER, dirt=PLASTER2):
    def fn(i, j, nx, nz):
        t = j / max(1, nz - 1) if nz > 1 else 1
        return lerpc(dirt, base, clamp(0.35 + 0.65 * t + b.rng.uniform(-0.15, 0.15)))
    return fn


def house_a():
    b = B('House_A', 11)
    L, D, zf, zw, zr = 8.0, 6.0, 0.45, 2.35, 5.7
    b.wall_ring(L + 0.24, D + 0.24, 0, zf, 'Stone', STONE, (0.6, 0.45), 0.2, 0.03)
    ws = b.wall_ring(L, D, zf, zw, 'Plaster', PLASTER, (1.0, 0.95), 0.05, colfn=plaster_fn(b))
    for k in (1, 3): b.gable_tri(ws[k][0], D, zw, zr - 0.15, 'Plaster', PLASTER, 3)
    # timbers
    for k, (M, W) in enumerate(ws):
        b.frame(M, W, zf, zw, studs=3 if k % 2 == 0 else 2, rail=False, braces=[(0, 'l'), (3 if k % 2 == 0 else 2, 'r')])
    for k in (1, 3):
        M = ws[k][0]
        b.wbeam(M, (0, zw), (0, zr - 0.5), 0.17); b.wbeam(M, (-D / 4, zw + (zr - zw) * 0.45), (D / 4, zw + (zr - zw) * 0.45), 0.15)
        b.wbeam(M, (-D / 2 + 0.1, zw + 0.05), (-0.05, zr - 0.25), 0.16, 0.06); b.wbeam(M, (D / 2 - 0.1, zw + 0.05), (0.05, zr - 0.25), 0.16, 0.06)
    b.door(ws[0][0], -1.3, zf - 0.1, 0.95, 1.85)
    b.wbox(ws[0][0], -1.9, -0.7, 0.0, zf - 0.1, 0.5, 'Stone', STONE_W, 0.1, back=False)  # step
    b.window(ws[0][0], 1.5, 1.15, 0.7, 0.75); b.window(ws[0][0], -3.0, 1.2, 0.55, 0.65)
    b.window(ws[2][0], -1.6, 1.15, 0.7, 0.75); b.window(ws[2][0], 1.8, 1.2, 0.6, 0.7)
    b.window(ws[3][0], 0.0, 3.0, 0.5, 0.6, shutters=False)
    b.gable_roof(I4, L, D, zw + 0.1, zr, og=0.5, oe=0.5, t=0.36, nx=13, nr=6, sag=0.24, rag=0.16, bulge=0.1)
    b.gable_roof(I4, L + 0.2, D, zw + 0.1, zr, col=THATCH_OLD, col2=THATCH_D, og=0.5, t=0.14, nx=13, nr=1, sag=0.24, vcap=0.2, lift=0.09, bulge=0.0)
    b.chimney(L / 2 + 0.32, 0.6, 0.9, 1.1, 0, zr + 0.75)
    # lean-to wood shed on the left gable
    M = ws[3][0]
    b.shed_roof(M, -2.6, -0.2, 0.0, -1.7, 2.15, 1.45, nx=4, nr=2)
    for x in (-2.6, -0.2): b.wbeam(M, (x, 0), (x, 1.3), 0.13, 0.13, y=-1.5)
    b.woodpile(M, -2.5, -0.35, 0, 1.0, 0.7)
    # rain barrel + bench
    b.cyl((2.9, -D / 2 - 0.45, 0), (2.9, -D / 2 - 0.45, 0.9), 0.33, 0.36, 8, 'Timber', TIMBER_L, 0.1, perface=True)
    b.box((-0.2, -D / 2 - 0.5, 0.4), (1.0, -D / 2 - 0.15, 0.47), 'Timber', PLANK, 0.1)
    for x in (-0.1, 0.9): b.box((x - 0.05, -D / 2 - 0.45, 0), (x + 0.05, -D / 2 - 0.2, 0.4), 'Timber', TIMBER, 0.1)
    return b


def house_b():
    b = B('House_B', 23)
    L, D, zf, z1, z2, zr, jet = 10.0, 7.0, 0.55, 2.75, 5.35, 9.6, 0.45
    b.wall_ring(L + 0.24, D + 0.24, 0, zf, 'Stone', STONE, (0.6, 0.5), 0.2, 0.03)
    ws = b.wall_ring(L, D, zf, z1, 'Plaster', PLASTER, (1.0, 1.1), 0.05, colfn=plaster_fn(b))
    D2 = D + 2 * jet
    # jetty floor + joist ends
    b.box((-L / 2 - 0.08, -D2 / 2, z1 - 0.02), (L / 2 + 0.08, D2 / 2, z1 + 0.2), 'Timber', TIMBER, 0.1, skip=('top',))
    for i in range(11):
        x = -L / 2 + 0.2 + i * (L - 0.4) / 10
        for sg in (-1, 1):
            b.box((x - 0.09, sg * D / 2 - (0 if sg > 0 else jet + 0.06), z1 - 0.2), (x + 0.09, sg * D / 2 + (jet + 0.06 if sg > 0 else 0), z1 - 0.01), 'Timber', TIMBER_D, 0.12, skip=('top', 's2' if sg < 0 else 's0'))
    us = b.wall_ring(L, D2, z1 + 0.2, z2, 'Plaster', PLASTER, (1.0, 1.05), 0.05)
    for k in (1, 3): b.gable_tri(us[k][0], D2, z2, zr - 0.15, 'Plaster', PLASTER, 4)
    # ground floor framing
    for k, (M, W) in enumerate(ws):
        b.frame(M, W, zf, z1, studs=5 if k % 2 == 0 else 3, rail=False, braces=[(0, 'l'), (6 if k % 2 == 0 else 4, 'r')], w=0.2)
    # upper framing, dense
    for k, (M, W) in enumerate(us):
        n = 6 if k % 2 == 0 else 4
        b.frame(M, W, z1 + 0.2, z2, studs=n, rail=True, braces=[(0, 'x'), (n, 'x'), (n // 2, 'l'), (n // 2 + 1, 'r')], w=0.19)
    for k in (1, 3):
        M = us[k][0]; h = zr - z2
        b.wbeam(M, (0, z2), (0, zr - 0.5), 0.2)
        for f in (0.33, 0.62):
            hw = D2 / 2 * (1 - f) - 0.1
            b.wbeam(M, (-hw, z2 + h * f), (hw, z2 + h * f), 0.17)
        for sg in (-1, 1):
            b.wbeam(M, (sg * (D2 / 2 - 0.1), z2 + 0.05), (sg * 0.05, zr - 0.25), 0.2, 0.07)
            b.wbeam(M, (sg * D2 / 4, z2 + 0.1), (sg * D2 / 4, z2 + h * 0.33), 0.15)
            b.wbeam(M, (sg * D2 / 4, z2 + h * 0.33), (sg * 0.15, z2 + h * 0.62), 0.13)
        b.window(M, 0, z2 + h * 0.36, 0.6, 0.75, shutters=False)
    F, Bk = ws[0][0], ws[2][0]
    b.door(F, -2.4, zf - 0.1, 1.15, 2.0); b.wbox(F, -3.2, -1.6, 0, zf - 0.1, 0.6, 'Stone', STONE_W, 0.1, back=False)
    for x in (0.3, 2.2, 4.0): b.window(F, x, 1.3, 0.75, 0.9)
    b.window(F, -4.2, 1.3, 0.6, 0.9, shutters=False)
    for x in (-3.6, -1.2, 1.2, 3.6): b.window(us[0][0], x, z1 + 1.05, 0.72, 0.95)
    for x in (-3.4, 3.4): b.window(Bk, x, 1.3, 0.7, 0.85)
    for x in (-2.5, 2.5): b.window(us[2][0], x, z1 + 1.05, 0.72, 0.95)
    b.door(Bk, 1.7, zf - 0.1, 0.9, 1.9)
    b.window(ws[1][0], 0, 1.3, 0.7, 0.85); b.window(us[1][0], -1.5, z1 + 1.05, 0.7, 0.9); b.window(us[3][0], 1.5, z1 + 1.05, 0.7, 0.9)
    b.gable_roof(I4, L, D2, z2 + 0.1, zr, 'Shingle', SHINGLE, SHINGLE2, og=0.45, oe=0.5, t=0.16, nx=16, nr=8, sag=0.12, rag=0.05, jit=0.16, band=0.1)
    b.beam((-L / 2 - 0.5, 0, zr + 0.02), (L / 2 + 0.5, 0, zr - 0.02), 0.22, 0.14, 'Shingle', mulc(SHINGLE, 0.7))
    b.chimney(1.6, 0.9, 1.3, 1.0, z2, zr + 1.0)
    # side outshot (lean-to pantry) on right gable
    M = ws[1][0]
    b.panel(M, -2.6, 0.6, 0, 2.0, 'Plaster', PLASTER2, (0.8, 1.0), 0.06, y=-1.6)
    for x, a, c in ((-2.6, -1.6, 0), (0.6, -1.6, 0)):
        b.panel(M @ T(x, 0, 0) @ Rz(pi / 2 if x > 0 else -pi / 2), 0 if x < 0 else -1.6, 1.6 if x < 0 else 0, 0, 2.0, 'Plaster', PLASTER2, (0.8, 1.0), 0.06)
    b.shed_roof(M, -2.6, 0.6, 0.0, -1.95, 2.9, 1.95, 'Shingle', SHINGLE, SHINGLE2, t=0.12, nx=5, nr=4, rag=0.03, sag=0.03, jit=0.15)
    b.wbeam(M, (-2.6, 2.0), (0.6, 2.0), 0.15, 0.05, y=-1.6); b.wbeam(M, (-2.55, 0), (-2.55, 2.0), 0.15, 0.05, y=-1.6); b.wbeam(M, (0.55, 0), (0.55, 2.0), 0.15, 0.05, y=-1.6)
    # hanging sign
    b.beam((-3.6, -D2 / 2, z1 + 0.9), (-3.6, -D2 / 2 - 1.1, z1 + 0.9), 0.08, 0.08, 'Timber', IRON)
    b.box((-3.63, -D2 / 2 - 1.05, z1 + 0.15), (-3.57, -D2 / 2 - 0.35, z1 + 0.8), 'Timber', C('#7a2f22'), 0.05)
    return b


def house_c():
    b = B('House_C', 37)
    L, D, zf, zw, zr = 16.0, 7.5, 0.4, 3.0, 7.9
    b.wall_ring(L + 0.2, D + 0.2, 0, zf, 'Stone', STONE, (0.7, 0.4), 0.2, 0.03)
    plank = lambda i, j, nx, nz: lerpc(PLANK, TIMBER, b.rng.random() * 0.8)
    ws = b.wall_ring(L, D, zf, zw, 'Timber', PLANK, (0.42, 3.0), 0.12, colfn=plank)
    for k in (1, 3):
        M = ws[k][0]
        for r in range(4):  # planked gable, stepped rows
            ta, tb = r / 4, (r + 1) / 4; h = zr - 0.2 - zw
            wa = D / 2 * (1 - ta); wb = D / 2 * (1 - tb)
            n = max(1, round(wa * 2 / 0.6))
            for i in range(n):
                xa, xb = lerp(-wa, wa, i / n), lerp(-wa, wa, (i + 1) / n)
                za = zw + h * ta
                zt = lambda x: zw + h * (1 - abs(x) / (D / 2))
                ids = [b.vert(M @ Vector(p)) for p in ((xa, 0, za), (xb, 0, za), (xb, 0, min(zt(xb), zw + h * tb)), (xa, 0, min(zt(xa), zw + h * tb)))]
                b.face(ids, 'Timber', lerpc(PLANK, TIMBER, b.rng.random() * 0.8), jit=0.1)
            if r == 3:
                ids = [b.vert(M @ Vector(p)) for p in ((-wa, 0, zw + h * ta), (wa, 0, zw + h * ta), (0, 0, zw + h))]
        b.wbeam(M, (-D / 2, zw), (D / 2, zw), 0.2, 0.07)
        b.wbox(M, -0.5, 0.5, zw + 1.3, zw + 2.5, 0.05, 'Timber', TIMBER_D, 0.1)  # loft door
        b.wbeam(M, (-0.6, zw + 2.6), (0.6, zw + 2.6), 0.14, 0.5)                # hoist beam
    for k, (M, W) in enumerate(ws):
        n = 6 if k % 2 == 0 else 3
        for i in range(n + 1):
            x = lerp(-W / 2 + 0.1, W / 2 - 0.1, i / n)
            b.wbeam(M, (x, zf), (x, zw), 0.24, 0.08)
        b.wbeam(M, (-W / 2, zw - 0.1), (W / 2, zw - 0.1), 0.2, 0.09)
        b.wbeam(M, (-W / 2, zf + 0.1), (W / 2, zf + 0.1), 0.2, 0.09)
    F = ws[0][0]
    # big double doors with cross braces
    for sg in (-1, 1):
        x0, x1 = (0.04, 1.5) if sg > 0 else (-1.5, -0.04)
        b.wbox(F, x0, x1, 0.05, 2.4, 0.07, 'Timber', mulc(PLANK, 0.6), 0.1)
        b.wbeam(F, (x0 + 0.05, 0.2), (x1 - 0.05, 2.25), 0.14, 0.12, col=TIMBER_D); b.wbeam(F, (x0 + 0.05, 2.25), (x1 - 0.05, 0.2), 0.14, 0.12, col=TIMBER_D)
        b.wbeam(F, (x0, 0.15), (x1, 0.15), 0.14, 0.12, col=TIMBER_D); b.wbeam(F, (x0, 2.3), (x1, 2.3), 0.14, 0.12, col=TIMBER_D)
    b.wbeam(F, (-1.65, 0), (-1.65, 2.45), 0.26, 0.12); b.wbeam(F, (1.65, 0), (1.65, 2.45), 0.26, 0.12); b.wbeam(F, (-1.8, 2.55), (1.8, 2.55), 0.24, 0.13)
    b.wbox(F, -2.0, 2.0, 0, 0.12, 1.6, 'Stone', STONE_D, 0.1, back=False)  # ramp slab
    for x in (-5.5, 5.2): b.window(F, x, 1.4, 0.5, 0.5, shutters=False)
    b.door(F, -6.9, zf - 0.05, 0.85, 1.8)
    b.gable_roof(I4, L, D, zw + 0.1, zr, og=0.6, oe=0.5, t=0.4, nx=20, nr=7, sag=0.42, rag=0.2, bulge=0.14, col=THATCH_OLD, col2=THATCH_D)
    b.gable_roof(I4, L + 0.3, D, zw + 0.1, zr, col=THATCH, col2=THATCH_OLD, og=0.6, t=0.15, nx=20, nr=1, sag=0.42, vcap=0.17, lift=0.1)
    # byre lean-to on back
    Bk = ws[2][0]
    b.shed_roof(Bk, -6.5, 1.5, 0.3, -3.1, 3.2, 2.05, nx=8, nr=3, t=0.28, col=THATCH_OLD)
    for i in range(5):
        x = lerp(-6.5, 1.5, i / 4)
        b.wbeam(Bk, (x, 0), (x, 1.85), 0.16, 0.16, y=-2.8)
    b.wbeam(Bk, (-6.6, 1.85), (1.6, 1.85), 0.15, 0.16, y=-2.8)
    b.panel(Bk, -6.5, 1.5, 0, 1.0, 'Timber', PLANK, (0.42, 2), 0.14, y=-2.9, colfn=plank)
    # hay pile + cart-less clutter
    b.blob((4.5, -D / 2 - 1.6, 0.5), (1.7, 1.3, 1.1), 2, 'Thatch', lambda p, d: lerpc(THATCH_D, C('#b89c5c'), clamp(d.z * 0.6 + 0.5)), 0.25, 1.5, smooth=True, zmin=0.0)
    b.cyl((6.6, -D / 2 - 0.5, 0), (6.6, -D / 2 - 0.5, 0.85), 0.3, 0.33, 8, 'Timber', TIMBER_L, 0.1, perface=True)
    return b


def house_d():
    b = B('House_D', 41)
    L, D, zs, zw, zr = 8.0, 6.0, 1.3, 2.6, 5.5
    b.wall_ring(L + 0.16, D + 0.16, 0, zs, 'Stone', STONE, (0.55, 0.45), 0.22, 0.04)
    plank = lambda i, j, nx, nz: lerpc(PLANK, TIMBER_L, b.rng.random() * 0.7)
    ws = b.wall_ring(L, D, zs, zw, 'Timber', PLANK, (0.4, 2.0), 0.12, colfn=plank)
    for k in (1, 3):
        b.gable_tri(ws[k][0], D, zw, zr - 0.15, 'Timber', PLANK, 4, jit=0.14)
        b.wbeam(ws[k][0], (-D / 2, zw), (D / 2, zw), 0.2, 0.07)
        b.wbeam(ws[k][0], (0, zw), (0, zr - 0.4), 0.17, 0.06)
    for k, (M, W) in enumerate(ws):
        n = 4 if k % 2 == 0 else 3
        for i in range(n + 1):
            x = lerp(-W / 2 + 0.1, W / 2 - 0.1, i / n); b.wbeam(M, (x, zs), (x, zw), 0.2, 0.07)
        b.wbeam(M, (-W / 2, zs + 0.08), (W / 2, zs + 0.08), 0.18, 0.1)
    F = ws[0][0]
    b.door(F, -2.2, 0.0, 1.1, 2.0, y=-0.1); b.window(F, 1.0, 1.45, 0.8, 0.8, y=-0.02); b.window(ws[2][0], 0, 1.45, 0.8, 0.8)
    b.gable_roof(I4, L, D, zw + 0.1, zr, 'Shingle', SHINGLE2, SHINGLE, og=0.4, oe=0.55, t=0.15, nx=14, nr=8, sag=0.1, rag=0.05, jit=0.17, band=0.1)
    b.beam((-L / 2 - 0.45, 0, zr + 0.02), (L / 2 + 0.45, 0, zr), 0.2, 0.13, 'Shingle', mulc(SHINGLE, 0.7))
    # forge lean-to, open front, on right gable (+X)
    x0, x1 = L / 2, L / 2 + 4.0
    M = T(x0, 0, 0) @ Rz(pi / 2)   # local -y -> +X
    b.shed_roof(M, -D / 2 + 0.2, D / 2 - 0.2, 0.0, -4.3, 3.35, 2.25, 'Shingle', SHINGLE, SHINGLE2, t=0.13, nx=8, nr=5, rag=0.04, sag=0.05, jit=0.16)
    for y in (-D / 2 + 0.3, 0.2, D / 2 - 0.3):
        b.box((x1 - 0.1, y - 0.1, 0), (x1 + 0.1, y + 0.1, 2.35), 'Timber', TIMBER, 0.1)
        b.beam((x1, y, 1.7), (x1 - 0.7, y, 2.4), 0.1, 0.1, 'Timber', TIMBER, 0.1)
    b.beam((x1, -D / 2 + 0.1, 2.4), (x1, D / 2 - 0.1, 2.4), 0.16, 0.18, 'Timber', TIMBER, 0.1)
    b.panel(T(x0 + 2.0, D / 2 - 0.3, 0) @ Rz(pi), -2.0, 2.0, 0, 2.3, 'Timber', PLANK, (0.4, 3), 0.14, colfn=plank)  # back wall of lean-to
    # forge + chimney
    b.stone_box((x0 + 0.1, 0.6, 0), (x0 + 1.9, 2.3, 1.0), col=STONE_D)
    b.box((x0 + 0.4, 0.9, 1.0), (x0 + 1.6, 2.0, 1.04), 'Stone', C('#d8581c'), skip=('bottom',))  # coals
    b.chimney(x0 + 0.85, 1.75, 1.3, 1.1, 1.0, 7.0, col=STONE_D)
    # anvil on stump, quench barrel, woodpile, grindstone
    b.cyl((x0 + 2.6, -0.2, 0), (x0 + 2.6, -0.2, 0.55), 0.3, 0.28, 8, 'Timber', TIMBER_L, 0.1)
    b.box((x0 + 2.3, -0.33, 0.55), (x0 + 2.95, -0.07, 0.72), 'Stone', IRON); b.box((x0 + 2.45, -0.28, 0.72), (x0 + 3.05, -0.12, 0.8), 'Stone', IRON)
    b.cyl((x0 + 1.5, -1.9, 0), (x0 + 1.5, -1.9, 0.85), 0.34, 0.37, 8, 'Timber', TIMBER, 0.1, perface=True)
    b.woodpile(T(x0 + 2.0, D / 2 - 0.45, 0), -1.7, 1.2, 0, 1.2, 0.6)
    b.cyl((x0 + 3.3, -2.1, 0.6), (x0 + 3.3, -1.95, 0.6), 0.42, 0.42, 10, 'Stone', STONE_W, caps=(True, True))
    b.box((x0 + 3.0, -2.2, 0), (x0 + 3.6, -1.85, 0.25), 'Timber', TIMBER, 0.1)
    return b


def chapel():
    b = B('Chapel', 53, ao_dist=3.5)
    L, D, zw, zr = 11.0, 6.6, 5.2, 9.6          # nave x in [-3.5, 7.5]
    cx = 2.0
    sc = lambda i, j, nx, nz: lerpc(STONE, STONE_W, b.rng.random())
    ws = b.wall_ring(L, D, 0, zw, 'Stone', STONE, (0.95, 0.65), 0.14, 0.035, cx=cx, colfn=sc)
    b.wall_ring(L + 0.3, D + 0.3, 0, 0.7, 'Stone', STONE_D, (0.9, 0.7), 0.14, 0.03, cx=cx)
    b.gable_tri(ws[1][0], D, zw, zr - 0.1, 'Stone', STONE, 4, jit=0.12)
    b.gable_roof(T(cx, 0, 0), L, D, zw + 0.1, zr, 'Shingle', SHINGLE, C('#57493e'), og=0.3, oe=0.45, t=0.18, nx=16, nr=9, sag=0.06, rag=0.04, jit=0.17, band=0.1)
    b.beam((cx - L / 2 - 0.3, 0, zr + 0.03), (cx + L / 2 + 0.3, 0, zr + 0.03), 0.22, 0.14, 'Stone', STONE_D)
    # chancel (east)
    cl, cd, czw, czr = 4.2, 4.8, 4.0, 7.4; ccx = cx + L / 2 + cl / 2
    cw = b.wall_ring(cl, cd, 0, czw, 'Stone', STONE, (0.9, 0.65), 0.14, 0.035, cx=ccx, colfn=sc, sides=(0, 1, 2))
    b.gable_tri(cw[1][0], cd, czw, czr - 0.1, 'Stone', STONE, 3, jit=0.12)
    b.gable_roof(T(ccx, 0, 0), cl, cd, czw + 0.1, czr, 'Shingle', SHINGLE, C('#57493e'), og=0.3, oe=0.4, t=0.16, nx=7, nr=7, sag=0.04, rag=0.04, jit=0.17)
    # east window
    b.hexa([(-0.45, 0.02, 1.6), (0.45, 0.02, 1.6), (0.05, 0.02, 3.9), (-0.05, 0.02, 3.9), (-0.45, -0.05, 1.6), (0.45, -0.05, 1.6), (0.05, -0.05, 3.9), (-0.05, -0.05, 3.9)],
           'Stone', C('#1c2230'), skip=('bottom',), M=cw[1][0])
    # buttresses + lancets
    for k in (0, 2):
        M = ws[k][0]
        for i in range(4):
            x = lerp(-L / 2 + 0.5, L / 2 - 0.5, i / 3)
            b.hexa([(x - 0.4, 0, 0), (x + 0.4, 0, 0), (x + 0.4, 0, 4.4), (x - 0.4, 0, 4.4), (x - 0.4, -1.0, 0), (x + 0.4, -1.0, 0), (x + 0.4, -0.25, 4.0), (x - 0.4, -0.25, 4.0)],
                   'Stone', STONE_W, 0.12, ('bottom',), M, perface=True)
            b.wbox(M, x - 0.45, x + 0.45, 2.0, 2.2, 0.75, 'Stone', STONE_D, 0.1, back=False)
        for i in range(3):
            x = lerp(-L / 2 + 0.5, L / 2 - 0.5, (i + 0.5) / 3)
            if k == 0 and i == 0: continue
            b.hexa([(x - 0.3, 0.02, 1.9), (x + 0.3, 0.02, 1.9), (x + 0.03, 0.02, 4.3), (x - 0.03, 0.02, 4.3), (x - 0.3, -0.05, 1.9), (x + 0.3, -0.05, 1.9), (x + 0.03, -0.05, 4.3), (x - 0.03, -0.05, 4.3)],
                   'Stone', C('#1c2230'), skip=('bottom',), M=M)
            b.wbox(M, x - 0.42, x + 0.42, 1.72, 1.9, 0.1, 'Stone', STONE_W, 0.1)
    # south porch (door faces -Y)
    F = ws[0][0]; px = -L / 2 + 0.5 + (L - 1) / 6
    PM = F @ T(px, -1.9, 0)
    for sx in (-1.25, 1.25):
        b.stone_box((cx + px + sx - 0.2, -D / 2 - 1.9, 0), (cx + px + sx + 0.2, -D / 2, 2.4), cell=(0.6, 0.6), top=False)
    b.gable_roof(T(cx + px, -D / 2 - 0.95, 0) @ Rz(pi / 2), 2.1, 2.9, 2.4, 3.9, 'Shingle', SHINGLE, C('#57493e'), og=0.25, oe=0.3, t=0.14, nx=4, nr=4, sag=0.03, rag=0.03, jit=0.17)
    b.gable_tri(PM, 2.9, 2.4, 3.8, 'Timber', PLANK, 2, jit=0.12, y=0.1)
    b.wbeam(PM, (-1.45, 2.4), (1.45, 2.4), 0.2, 0.1, y=0.05)
    b.door(F, px, 0.0, 1.3, 2.3, y=-0.03, col=C('#4d3320'))
    b.hexa([(px - 0.75, 0.02, 2.3), (px + 0.75, 0.02, 2.3), (px + 0.05, 0.02, 3.1), (px - 0.05, 0.02, 3.1), (px - 0.75, -0.06, 2.3), (px + 0.75, -0.06, 2.3), (px + 0.05, -0.06, 3.1), (px - 0.05, -0.06, 3.1)],
           'Timber', C('#3a281a'), skip=('bottom',), M=F)
    # west tower
    tw, th = 4.4, 11.6; tx = cx - L / 2 - tw / 2 + 0.4
    tws = b.wall_ring(tw, tw, 0, th, 'Stone', STONE, (0.9, 0.68), 0.15, 0.035, cx=tx, colfn=sc)
    b.wall_ring(tw + 0.36, tw + 0.36, 0, 0.9, 'Stone', STONE_D, (0.9, 0.9), 0.14, 0.03, cx=tx)
    for z in (5.6, 8.0, th - 0.15):
        b.box((tx - tw / 2 - 0.1, -tw / 2 - 0.1, z), (tx + tw / 2 + 0.1, tw / 2 + 0.1, z + 0.22), 'Stone', STONE_W, 0.08)
    for M, W in tws:
        for sx in (-0.7, 0.7):  # paired belfry openings with louvres
            b.hexa([(sx - 0.42, 0.02, 8.6), (sx + 0.42, 0.02, 8.6), (sx + 0.04, 0.02, 10.9), (sx - 0.04, 0.02, 10.9), (sx - 0.42, -0.04, 8.6), (sx + 0.42, -0.04, 8.6), (sx + 0.04, -0.04, 10.9), (sx - 0.04, -0.04, 10.9)],
                   'Stone', C('#14110f'), skip=('bottom',), M=M)
            for z in (8.9, 9.4, 9.9): b.wbeam(M, (sx - 0.36, z), (sx + 0.36, z), 0.12, 0.08, col=TIMBER_D)
        b.wbox(M, -0.2, 0.2, 3.2, 4.6, 0.04, 'Stone', C('#14110f'))
        b.wbox(M, -0.14, 0.14, 6.3, 7.3, 0.04, 'Stone', C('#14110f'))
    for sx in (-1, 1):
        for sy in (-1, 1):  # corner buttresses
            x, y = tx + sx * tw / 2, sy * tw / 2
            b.box((x - 0.45, y - 0.45, 0), (x + 0.45, y + 0.45, 7.2), 'Stone', STONE_W, 0.12, skip=('bottom',), taper=0.6, perface=True)
    # spire (octagonal-ish broach: 4-sided with two rings)
    zs0, zs1 = th + 0.07, 16.2; hw = tw / 2 + 0.3
    n = 8; rings = []
    for z, r, tw8 in ((zs0, hw * 1.06, 0), (zs0 + 1.2, hw * 0.74, 1), (zs0 + 2.9, hw * 0.47, 1), (zs1, 0.04, 1)):
        ring = []
        for i in range(n):
            a = 2 * pi * (i + 0.5) / n
            rr = r / math.cos(pi / 4) if (tw8 == 0 and i % 2 == 0) else (r / math.cos(pi / 4) * (1 if i % 2 == 0 else 1) if tw8 == 0 else r / math.cos(pi / 8))
            if tw8 == 0:  # square base: 8 points on the square
                ang = a - pi / 8 if i % 2 == 0 else a + pi / 8
                c_, s_ = math.cos(a), math.sin(a)
                m = max(abs(c_), abs(s_)); px_, py_ = c_ / m * r, s_ / m * r
            else:
                px_, py_ = math.cos(a) * rr, math.sin(a) * rr
            ring.append(b.vert((tx + px_, py_, z)))
        rings.append(ring)
    for k in range(3):
        for i in range(n):
            j = (i + 1) % n
            c = lerpc(SHINGLE, C('#57493e'), b.rng.random())
            b.face_auto([rings[k][i], rings[k][j], rings[k + 1][j], rings[k + 1][i]], 'Shingle', c, (tx, 0, (zs0 + zs1) / 2 - 2), jit=0.12)
    b.face(list(reversed(rings[0])), 'Shingle', mulc(SHINGLE, 0.4))
    b.box((tx - 0.05, -0.05, zs1 - 0.2), (tx + 0.05, 0.05, zs1 + 1.15), 'Stone', IRON)
    b.box((tx - 0.05, -0.38, zs1 + 0.6), (tx + 0.05, 0.38, zs1 + 0.7), 'Stone', IRON)
    # low churchyard gravestones
    for i in range(5):
        x = cx + 1.5 + i * 1.3 + b.rng.uniform(-0.2, 0.2); y = -D / 2 - 3.2 - b.rng.uniform(0, 1.5)
        b.box((x - 0.25, y - 0.07, 0), (x + 0.25, y + 0.07, b.rng.uniform(0.6, 1.0)), 'Stone', STONE_W, 0.15, skip=('bottom',), M=T(x, y, 0) @ Rz(b.rng.uniform(-0.3, 0.3)) @ Ry(b.rng.uniform(-0.12, 0.12)) @ T(-x, -y, 0))
    return b


def windmill():
    b = B('Windmill', 61, ao_dist=3.0)
    # stone piers + trestle
    for a in range(4):
        ang = a * pi / 2 + pi / 4
        x, y = math.cos(ang) * 3.0, math.sin(ang) * 3.0
        b.stone_box((x - 0.5, y - 0.5, 0), (x + 0.5, y + 0.5, 0.7), cell=(0.5, 0.35), vj=0.03)
    for ang in (pi / 4, 3 * pi / 4):
        d = Vector((math.cos(ang), math.sin(ang), 0))
        b.beam(d * -3.3 + Vector((0, 0, 0.9)), d * 3.3 + Vector((0, 0, 0.9)), 0.42, 0.42, 'Timber', TIMBER, 0.1)
    b.box((-0.38, -0.38, 0.9), (0.38, 0.38, 4.6), 'Timber', TIMBER_D, 0.1, skip=('bottom',))
    for a in range(4):
        ang = a * pi / 2 + pi / 4
        d = Vector((math.cos(ang), math.sin(ang), 0))
        b.beam(d * 3.0 + Vector((0, 0, 1.1)), d * 0.3 + Vector((0, 0, 3.6)), 0.3, 0.3, 'Timber', TIMBER, 0.12)
    # buck (body): weatherboarded, slightly tapering
    bw, bd, z0, z1 = 3.3, 4.3, 3.3, 9.4
    board = lambda i, j, nx, nz: lerpc(PLANK, TIMBER_L, b.rng.random() * 0.9)
    ws = b.wall_ring(bw, bd, z0, z1, 'Timber', PLANK, (3.3, 0.36), 0.12, colfn=board)
    b.box((-bw / 2, -bd / 2, z0 - 0.25), (bw / 2, bd / 2, z0), 'Timber', TIMBER_D, 0.1)
    for sx in (-1, 1):
        for sy in (-1, 1):
            b.box((sx * bw / 2 - 0.12, sy * bd / 2 - 0.12, z0 - 0.25), (sx * bw / 2 + 0.12, sy * bd / 2 + 0.12, z1), 'Timber', TIMBER, 0.1)
    # roof: ridge along Y (front-back), curved-ish gable
    RM = Rz(pi / 2)
    b.gable_roof(RM, bd, bw, z1 + 0.1, z1 + 2.0, 'Shingle', SHINGLE2, SHINGLE, og=0.35, oe=0.3, t=0.14, nx=8, nr=6, sag=0.0, rag=0.03, jit=0.16, bulge=0.38)
    for k in (0, 2):
        b.gable_tri(ws[k][0], bw, z1, z1 + 1.9, 'Timber', PLANK, 3, jit=0.14)
    F, Bk = ws[0][0], ws[2][0]
    b.window(F, 0.9, 5.2, 0.5, 0.6, shutters=False); b.window(ws[1][0], 0, 7.4, 0.5, 0.6, shutters=False); b.window(ws[3][0], 0.4, 5.6, 0.5, 0.6, shutters=False)
    # back: door, porch, ladder, tail pole
    b.door(Bk, 0, z0 + 0.05, 0.9, 1.85)
    b.box((-0.9, bd / 2, z0 - 0.12), (0.9, bd / 2 + 1.0, z0), 'Timber', PLANK, 0.1)
    top = Vector((0, bd / 2 + 1.0, z0 - 0.06)); bot = Vector((0, bd / 2 + 4.3, 0.05))
    for sx in (-0.5, 0.5):
        b.beam(top + Vector((sx, 0, 0)), bot + Vector((sx, 0, 0)), 0.1, 0.16, 'Timber', TIMBER, 0.1)
    for i in range(1, 10):
        p = top.lerp(bot, i / 10)
        b.beam(p + Vector((-0.5, 0, 0)), p + Vector((0.5, 0, 0)), 0.14, 0.05, 'Timber', PLANK, 0.12)
    b.beam((0.0, bd / 2, z0 - 0.15), (0.0, bd / 2 + 6.6, 0.75), 0.24, 0.24, 'Timber', TIMBER_D, 0.1)   # tail pole
    b.cyl((0.0, bd / 2 + 6.5, 0.0), (0.0, bd / 2 + 6.5, 0.85), 0.12, 0.1, 6, 'Timber', TIMBER)
    # windshaft
    hub = (0.0, -bd / 2 - 0.75, 8.5)
    b.cyl((0, -bd / 2 + 0.2, 8.6), (0, -bd / 2 - 0.6, 8.5), 0.3, 0.26, 8, 'Timber', TIMBER_D, caps=(False, False))
    # sails (child, origin at hub, spin about local Y)
    sb = B('Mill_Sails', 62, ground=None, ao_dist=1.5, ao_strength=0.4)
    sb.cyl((0, 0.2, 0), (0, -0.3, 0), 0.34, 0.3, 8, 'Timber', TIMBER_D, caps=(True, True))
    for a in range(4):
        M = Ry(a * pi / 2 + 0.2)
        sb.beam((0, -0.1 - 0.06 * (a % 2), -0.2), (0, -0.1 - 0.06 * (a % 2), 6.1), 0.2, 0.18, 'Timber', TIMBER, 0.1, up=(0, 1, 0), M=M)
        tw = lambda z: -0.1 + (z - 1.2) * 0.05   # slight weather twist
        for x in (0.55, 1.0, 1.45):
            sb.beam((x, tw(1.2) - 0.1, 1.2), (x, tw(6.0) - 0.1, 6.0), 0.07, 0.06, 'Timber', TIMBER_L, 0.12, up=(0, 1, 0), M=M)
        for i in range(8):
            z = lerp(1.2, 6.0, i / 7)
            sb.beam((-0.25, tw(z) - 0.1, z), (1.5, tw(z) - 0.1, z), 0.07, 0.06, 'Timber', TIMBER_L, 0.12, up=(0, 1, 0), M=M)
        # canvas, partly reefed
        zc0, zc1 = (1.25, 5.95) if a % 2 == 0 else (2.6, 5.95)
        sb.box((0.12, -0.035, zc0), (1.46, -0.015, zc1), 'Plaster', C('#c9bfa6'), 0.06, M=M @ T(0, -0.1 + (zc0 + zc1) / 2 * 0.05 - 0.06, 0))
    b.children.append((sb, hub))
    return b


def bridge():
    b = B('Bridge', 71, ground=-1.2, ao_dist=3.0)
    half, hw = 9.0, 2.5
    deck = lambda x: 2.5 - 1.9 * (x / half) ** 2
    piers = [(-3.9, -2.7), (2.7, 3.9)]
    spans = [(-8.0, -3.9), (-2.7, 2.7), (3.9, 8.0)]
    BOT = -2.5

    def under(x, side=0):
        for a, c in spans:
            if a - 1e-6 <= x <= c + 1e-6:
                if (abs(x - a) < 1e-6 and side < 0) or (abs(x - c) < 1e-6 and side > 0): return BOT
                m, h = (a + c) / 2, (c - a) / 2
                rise = min(deck(m) - 0.75, h * 0.95) + 0.3
                return -0.3 + rise * math.sqrt(max(0, 1 - ((x - m) / h) ** 2))
        return BOT
    xs = set([-half, half])
    for a, c in spans:
        for i in range(9): xs.add(round(lerp(a, c, i / 8), 4))
    xs = sorted(xs)
    stone = lambda: lerpc(STONE, STONE_W, b.rng.random())
    for i in range(len(xs) - 1):
        xa, xb = xs[i], xs[i + 1]
        ua, ub = under(xa, +1 if any(abs(xa - s[1]) < 1e-6 for s in spans) else 0), under(xb, -1 if any(abs(xb - s[0]) < 1e-6 for s in spans) else 0)
        da, db = deck(xa), deck(xb)
        for sg in (-1, 1):
            y = sg * hw
            rows = 3
            for r in range(rows):
                ta, tb = r / rows, (r + 1) / rows
                ids = [b.vert(p) for p in ((xa, y, lerp(ua, da, ta)), (xb, y, lerp(ub, db, ta)), (xb, y, lerp(ub, db, tb)), (xa, y, lerp(ua, da, tb)))]
                b.face_auto(ids, 'Stone', stone(), (0, sg, 0), jit=0.24, direction=True)
        # soffit
        ids = [b.vert(p) for p in ((xa, -hw, ua), (xb, -hw, ub), (xb, hw, ub), (xa, hw, ua))]
        b.face_auto(ids, 'Stone', mulc(STONE_D, 0.8), (0, 0, -1), jit=0.1, direction=True)
        # deck, cobbles
        for k in range(3):
            ya, yb = lerp(-hw + 0.35, hw - 0.35, k / 3), lerp(-hw + 0.35, hw - 0.35, (k + 1) / 3)
            ids = [b.vert(p) for p in ((xa, ya, da), (xb, ya, db), (xb, yb, db), (xa, yb, da))]
            b.face(ids, 'Stone', lerpc(C('#7a7062'), C('#9a8e7a'), b.rng.random()), jit=0.12)
    # vertical pier faces where the soffit jumps
    for a, c in spans:
        for x, dirx in ((a, 1), (c, -1)):
            m, h = (a + c) / 2, (c - a) / 2
            ids = [b.vert(p) for p in ((x, -hw, BOT), (x, hw, BOT), (x, hw, -0.3), (x, -hw, -0.3))]
            b.face_auto(ids, 'Stone', STONE_D, (dirx, 0, 0), jit=0.1, direction=True)
    # parapets
    n = 18
    for i in range(n):
        xa, xb = lerp(-half, half, i / n), lerp(-half, half, (i + 1) / n)
        for sg in (-1, 1):
            y0, y1 = (hw - 0.38, hw + 0.04) if sg > 0 else (-hw - 0.04, -hw + 0.38)
            da, db = deck(xa) - 0.05, deck(xb) - 0.05
            b.hexa([(xa, y0, da), (xb, y0, db), (xb, y1, db), (xa, y1, da), (xa, y0, da + 0.95), (xb, y0, db + 0.95), (xb, y1, db + 0.95), (xa, y1, da + 0.95)],
                   'Stone', stone(), 0.14, ('bottom',) + (() if i == 0 else ('s3',)) + (() if i == n - 1 else ('s1',)), perface=True)
    # end posts + cutwaters
    for sx in (-1, 1):
        for sg in (-1, 1):
            x, y = sx * (half - 0.3), sg * (hw - 0.17)
            b.box((x - 0.4, y - 0.4, deck(half) - 0.6), (x + 0.4, y + 0.4, deck(half) + 1.3), 'Stone', STONE_W, 0.12, skip=('bottom',), perface=True)
    for a, c in piers:
        for sg in (-1, 1):
            y = sg * hw
            pts = [(a, y, BOT), (c, y, BOT), ((a + c) / 2, y + sg * 1.5, BOT), (a, y, 1.3), (c, y, 1.3), ((a + c) / 2, y + sg * 0.5, 1.3)]
            ids = [b.vert(p) for p in pts]
            cen = ((a + c) / 2, y + sg * 0.3, -0.5)
            b.face_auto([ids[1], ids[2], ids[5], ids[4]], 'Stone', stone(), cen, jit=0.12)
            b.face_auto([ids[2], ids[0], ids[3], ids[5]], 'Stone', stone(), cen, jit=0.12)
            b.face_auto([ids[3], ids[4], ids[5]], 'Stone', STONE_W, cen, jit=0.1)
    return b


def well():
    b = B('Well', 81, ao_dist=1.5)
    n = 12; ro, ri, h = 0.95, 0.68, 0.85
    ring = lambda r, z: [b.vert((math.cos(2 * pi * i / n) * r, math.sin(2 * pi * i / n) * r, z)) for i in range(n)]
    a, c, d, e, w = ring(ro + 0.05, 0), ring(ro, h), ring(ri, h), ring(ri, 0.25), None
    for i in range(n):
        j = (i + 1) % n
        b.face([a[i], a[j], c[j], c[i]], 'Stone', lerpc(STONE, STONE_W, b.rng.random()), jit=0.15)
        b.face([c[i], c[j], d[j], d[i]], 'Stone', STONE_W, jit=0.12)
        b.face([d[i], d[j], e[j], e[i]], 'Stone', STONE_D, jit=0.1)
    b.face(e, 'Stone', C('#10161a'))
    for sx in (-1, 1):
        b.box((sx * 1.05 - 0.08, -0.08, 0), (sx * 1.05 + 0.08, 0.08, 2.35), 'Timber', TIMBER, 0.1, skip=('bottom',))
        b.beam((sx * 1.05, 0, 1.9), (sx * 0.6, 0, 2.35), 0.07, 0.07, 'Timber', TIMBER, 0.1)
    b.cyl((-1.05, 0, 1.65), (1.05, 0, 1.65), 0.09, 0.09, 6, 'Timber', TIMBER_L, caps=(True, True))
    b.beam((1.13, 0, 1.65), (1.38, 0, 1.65), 0.04, 0.04, 'Stone', IRON); b.beam((1.38, 0, 1.65), (1.38, 0, 1.35), 0.04, 0.04, 'Stone', IRON)
    b.gable_roof(I4, 2.3, 1.5, 2.3, 3.05, 'Shingle', SHINGLE2, SHINGLE, og=0.15, oe=0.2, t=0.08, nx=5, nr=4, sag=0.02, rag=0.02, jit=0.16)
    b.cyl((0.45, -0.75, h), (0.45, -0.75, h + 0.32), 0.13, 0.16, 7, 'Timber', TIMBER_L, 0.1, caps=(True, True))
    b.beam((0.1, 0, 1.6), (0.1, 0, 0.9), 0.025, 0.025, 'Thatch', THATCH_D)
    return b


def fence():
    b = B('Fence', 83, ao_dist=0.8, ao_strength=0.45)
    xs = [-2.0 + i * 0.8 for i in range(6)]
    for i, x in enumerate(xs):
        h = 1.2 + b.rng.uniform(-0.08, 0.12)
        b.cyl((x, 0, 0), (x + b.rng.uniform(-0.03, 0.03), b.rng.uniform(-0.03, 0.03), h), 0.055, 0.04, 5, 'Timber', TIMBER, 0.15)
    for r in range(7):
        z = 0.14 + r * 0.14
        ph = 1 if r % 2 == 0 else -1
        for i in range(5):
            y0, y1 = ph * (0.06 if i % 2 == 0 else -0.06), ph * (-0.06 if i % 2 == 0 else 0.06)
            b.beam((xs[i], y0, z + b.rng.uniform(-0.01, 0.01)), (xs[i + 1], y1, z + b.rng.uniform(-0.01, 0.01)), 0.035, 0.11, 'Timber', lerpc(C('#6b5536'), C('#8a7350'), b.rng.random()), 0.15, skip=('s1', 's3'))
    return b


def stone_wall():
    b = B('StoneWall', 85, ao_dist=1.0)
    nx, nz = 9, 3
    for sg in (-1, 1):
        g = [[b.vert((lerp(-2, 2, i / nx) + (b.rng.uniform(-0.06, 0.06) if 0 < i < nx else 0), sg * (0.34 - 0.07 * j / nz + b.rng.uniform(-0.04, 0.04)),
                      lerp(0, 0.95, j / nz) + (b.rng.uniform(-0.05, 0.05) if 0 < j else 0))) for j in range(nz + 1)] for i in range(nx + 1)]
        for i in range(nx):
            for j in range(nz):
                b.face_auto([g[i][j], g[i + 1][j], g[i + 1][j + 1], g[i][j + 1]], 'Stone', lerpc(STONE, STONE_W, b.rng.random()), (0, sg, 0), jit=0.2, direction=True)
    for sx in (-1, 1):
        ids = [b.vert(p) for p in ((sx * 2, -0.34, 0), (sx * 2, 0.34, 0), (sx * 2, 0.27, 0.95), (sx * 2, -0.27, 0.95))]
        b.face_auto(ids, 'Stone', STONE, (sx, 0, 0), jit=0.15, direction=True)
    n = 8
    for i in range(n):
        xa, xb = lerp(-2, 2, i / n) + 0.015, lerp(-2, 2, (i + 1) / n) - 0.015
        h = 1.1 + b.rng.uniform(-0.05, 0.08); t = b.rng.uniform(-0.08, 0.08)
        b.hexa([(xa, -0.3, 0.9), (xb, -0.3, 0.9), (xb, 0.3, 0.9), (xa, 0.3, 0.9), (xa + t, -0.22, h), (xb + t, -0.22, h), (xb + t, 0.22, h), (xa + t, 0.22, h)],
               'Stone', lerpc(STONE_D, STONE_W, b.rng.random()), 0.15, ('bottom',), perface=True)
    return b


def dock():
    b = B('Dock', 87, ground=-1.0, ao_dist=1.5)
    W, L0, L1, zd = 2.2, 3.5, -3.5, 0.6   # runs along Y, shore end at +Y, water end at -Y
    n = 16
    for i in range(n):
        ya, yb = lerp(L1, L0, i / n) + 0.015, lerp(L1, L0, (i + 1) / n) - 0.015
        o = b.rng.uniform(-0.06, 0.06)
        b.box((-W / 2 + o, ya, zd - 0.06 + b.rng.uniform(-0.01, 0.01)), (W / 2 + o, yb, zd), 'Timber', lerpc(PLANK, C('#8b7a62'), b.rng.random()), 0.12)
    for sx in (-0.85, 0.85):
        b.beam((sx, L1, zd - 0.16), (sx, L0, zd - 0.16), 0.16, 0.2, 'Timber', TIMBER_D, 0.1)
    for i, y in enumerate((-3.3, -1.1, 1.1, 3.2)):
        for sx in (-1, 1):
            top = zd + (0.75 if (i == 0 or (i == 2 and sx < 0)) else 0.05)
            b.cyl((sx * 1.0, y, -2.2), (sx * 1.0, y, top), 0.13, 0.11, 6, 'Timber', TIMBER, 0.12)
        b.beam((-1.0, y, zd - 0.35), (1.0, y, zd - 0.35), 0.12, 0.14, 'Timber', TIMBER_D, 0.1)
    for sx in (-0.2, 0.2):  # ladder at water end
        b.beam((sx - 0.5, L1 - 0.08, -1.4), (sx - 0.5, L1 - 0.08, zd + 0.5), 0.06, 0.06, 'Timber', TIMBER, 0.1)
    for i in range(5):
        b.beam((-0.7, L1 - 0.08, -1.1 + i * 0.36), (-0.3, L1 - 0.08, -1.1 + i * 0.36), 0.05, 0.05, 'Timber', PLANK, 0.1)
    # crate + coil
    b.box((0.3, 1.6, zd), (0.95, 2.25, zd + 0.55), 'Timber', PLANK, 0.12, skip=('bottom',), perface=True)
    b.cyl((-0.55, -2.4, zd), (-0.55, -2.4, zd + 0.16), 0.3, 0.26, 8, 'Thatch', THATCH_D, 0.1)
    return b


# =====================================================================================
#  TREES & ROCKS
# =====================================================================================
PINE_TIP = C('#44602f'); PINE_IN = C('#1d3521'); PINE_UNDER = C('#0f1c12')
OAK_TOP = C('#55732a'); OAK_IN = C('#263f18'); OAK_SUN = C('#7d8f35')
BIRCH_TOP = C('#86a03a'); BIRCH_IN = C('#4a6a22')
ZUP = Vector((0, 0, 1))


def trunk(b, pts, radii, n, col=BARK, jit=0.12, H=10.0, capped=True, wind_top=0.12):
    """pts: list of points; tapered multi-segment trunk (LOD meshes)"""
    for i in range(len(pts) - 1):
        w0 = wind_top * (pts[i][2] / H) ** 2; w1 = wind_top * (pts[i + 1][2] / H) ** 2
        b.cyl(pts[i], pts[i + 1], radii[i], radii[i + 1], n, 'Bark', col, jit, caps=(False, capped and i == len(pts) - 2), wind=(w0, w1), perface=True)


def foliage_col(b, center, R, top, inner, sun, sundir=Vector((0.5, -0.3, 0.8)).normalized()):
    def fn(p, d):
        rel = (p - center)
        radial = clamp(rel.length / R)
        up = clamp(d.z * 0.5 + 0.5)
        c = lerpc(inner, top, clamp(0.25 + 0.5 * up + 0.35 * radial - 0.25))
        c = lerpc(c, sun, clamp(d.dot(sundir)) ** 2 * 0.35 * up)
        k = 1 + 0.12 * noise.noise(p * 0.9)
        return mulc(c, k)
    return fn


# ---------- far LODs (drawn by the thousand: all the reading comes from silhouette, authored normals and baked colour)
def pine_lod(name, H, R, tiers, seed, dims, bare=0.15, tint=1.0, tip=PINE_TIP, inn=PINE_IN, under=PINE_UNDER):
    """spruce stand-in: whorls of 3 drooping bough lobes (bright tips, dark creases between them and under the whorl above),
    each whorl turned and sized irregularly, a thin ragged leader and a 3-triangle stem"""
    b = VB(name, seed, ao_dist=3.0, ao_strength=0.5)
    rng = b.rng
    lean = Vector((rng.uniform(-0.35, 0.35), rng.uniform(-0.35, 0.35), 0))
    axis = lambda z: lean * (z / H) ** 2 + Vector((0, 0, z))
    r0 = 0.14 + H * 0.016
    span = H * (1 - bare); ph = rng.uniform(0, 2 * pi)
    def nfn(p, fn):
        a = axis(p.z); o = Vector((p.x - a.x, p.y - a.y, 0))
        o = o.normalized() if o.length > 1e-4 else Vector((fn.x, fn.y, 0))
        return (fn * 0.3 + (o * 0.75 + ZUP * 0.66).normalized() * 0.7).normalized()
    # stem: a 3-sided spike that disappears into the crown
    base = [b.vert((math.cos(2.1 * i) * r0 * 1.5, math.sin(2.1 * i) * r0 * 1.5, 0), 0.0) for i in range(3)]
    sa = b.vert(axis(H * 0.5), 0.1)
    bk = C('#4a3d30')
    for i in range(3):
        b.face_auto([base[i], base[(i + 1) % 3], sa], 'Bark', [mulc(bk, 0.7), mulc(bk, 0.7), mulc(bk, 0.9)], (0, 0, H * 0.2))
    for k in range(tiers):
        t = k / (tiers - 1)
        z_low = H * bare + span * 0.8 * t ** 0.92
        th = span / tiers * lerp(2.0, 1.5, t)
        z_high = min(H * 0.93, z_low + th)
        r = R * ((1 - t) ** 0.8 * 0.86 + 0.14) * rng.uniform(0.86, 1.14)
        if k == 0: r *= 0.9                                            # lowest whorl is a little thinner / dying back
        ph += pi / 3 + rng.uniform(-0.35, 0.35)
        off = Vector((rng.uniform(-1, 1), rng.uniform(-1, 1), 0)) * r * 0.12
        ax0 = axis(z_low) + off
        wz = (z_low / H) ** 1.5
        tipc = mulc(lerpc(inn, tip, 0.72 + 0.28 * t), tint * 1.0)
        crease = mulc(lerpc(under, inn, 0.55 + 0.3 * t), tint)
        top_in = mulc(lerpc(under, inn, 0.75 + 0.25 * t), tint)
        outer = []; oc = []
        short = rng.randrange(3) if rng.random() < 0.6 else -1         # one stunted bough on most whorls
        for i in range(6):
            a = ph + 2 * pi * i / 6 + rng.uniform(-0.16, 0.16)
            if i % 2 == 0:
                rr = r * rng.uniform(0.86, 1.16) * (0.66 if i // 2 == short else 1.0)
                zz = z_low - rr * rng.uniform(0.22, 0.42) * lerp(1.0, 0.5, t)
                oc.append(hue(mulc(tipc, rng.uniform(0.86, 1.16)), rng.uniform(-0.1, 0.12))); w = clamp(0.35 + 0.65 * wz)
            else:
                rr = r * rng.uniform(0.34, 0.5)
                zz = z_low + r * rng.uniform(0.1, 0.24)
                oc.append(crease); w = clamp(0.25 + 0.5 * wz)
            outer.append(b.vert(ax0 + Vector((math.cos(a) * rr, math.sin(a) * rr, zz - z_low)), w))
        apex = b.vert(axis(z_high), clamp(0.1 + 0.6 * (z_high / H) ** 2))
        for i in range(6):
            j = (i + 1) % 6
            b.card([outer[i], outer[j], apex], [oc[i], oc[j], top_in], None, nfn, (b.v[outer[i]] + b.v[outer[j]]) * 0.5 - ax0 + ZUP * r)
    # leader: thin crooked spike above the top whorl
    zl = H * 0.8; rl = R * 0.12
    lb = [b.vert(axis(zl) + Vector((math.cos(ph + 2.1 * i) * rl, math.sin(ph + 2.1 * i) * rl, 0)), 0.75) for i in range(3)]
    la = b.vert(axis(H) + Vector((rng.uniform(-0.25, 0.25), rng.uniform(-0.25, 0.25), 0)), 0.95)
    lc = mulc(lerpc(inn, tip, 0.9), tint * 1.1)
    for i in range(3):
        j = (i + 1) % 3
        b.card([lb[i], lb[j], la], [mulc(lc, 0.8), mulc(lc, 0.8), lc], None, nfn, (b.v[lb[i]] + b.v[lb[j]]) * 0.5 - axis(zl))
    b.fit(dims)
    return b


def _blob(b, c, rad, rng, colfn, nfn, wind, tilt=0.35, jit=0.16, nr=5):
    """closed leaf mass of 2 * nr triangles: an irregular rim with a crest and a belly point, turned and tipped at random so
    no two show the same outline. colfn(p, dir) colours a vertex from its position and its direction out of the mass;
    nfn supplies the blown-out normal."""
    az = rng.uniform(0, 2 * pi)
    e3 = (ZUP + Vector((rng.uniform(-1, 1), rng.uniform(-1, 1), 0)) * tilt).normalized()
    e1 = Vector((math.cos(az), math.sin(az), 0)); e1 = (e1 - e3 * e1.dot(e3)).normalized(); e2 = e3.cross(e1)
    ids = []
    for i in range(nr):
        a = 2 * pi * i / nr + rng.uniform(-0.22, 0.22)
        o = (e1 * math.cos(a) * rad.x + e2 * math.sin(a) * rad.y) * rng.uniform(1 - jit, 1 + jit) + e3 * rad.z * rng.uniform(-0.3, 0.15)
        ids.append(b.vert(c + o, wind(c + o)))
    for sg in (1, -1):
        o = e3 * sg * rad.z * rng.uniform(0.85, 1.1) + (e1 * rng.uniform(-0.3, 0.3) + e2 * rng.uniform(-0.3, 0.3)) * rad.x
        ids.append(b.vert(c + o, wind(c + o)))
    cols = [colfn(b.v[i], (b.v[i] - c).normalized()) for i in ids]
    for i in range(nr):
        j = (i + 1) % nr
        for cap in (nr, nr + 1):
            tri = [ids[i], ids[j], ids[cap]]
            b.card(tri, [cols[i], cols[j], cols[cap]], None, nfn, sum((b.v[t] for t in tri), Vector()) / 3 - c)


def oak_lod(name, H, R, seed, dims, cols=(OAK_TOP, OAK_IN, OAK_SUN), k=(1.0, 1.0, 1.0), nup=4, nlow=4):
    """broadleaf stand-in laid out like oak(): a bare bole to the fork at 0.3 H, then closed leaf masses where the big pads of the
    full tree sit (one over the leader, a ring on the shoulders, a staggered ring round the waist). Every mass takes most of its
    normal from the crown as a whole, so the crown shades as one soft body with a lumpy outline; colour runs from sunlit tops to
    the dark inside colour low in the crown; the masses themselves only show in the outline, their tints and the baked occlusion."""
    b = VB(name, seed, ao_dist=3.2, ao_strength=0.12)
    rng = b.rng
    lean = Vector((rng.uniform(-0.5, 0.5), rng.uniform(-0.5, 0.5), 0))
    cz = H * 0.6; rzu = H - cz; rzd = cz - H * 0.3
    crown = Vector((lean.x, lean.y, cz))
    fork = Vector((lean.x * 0.45, lean.y * 0.45, H * 0.3))
    r0 = 0.2 + H * 0.014
    def wind(p): return clamp(0.3 + 0.56 * (Vector((p.x - crown.x, p.y - crown.y, 0)).length / R) + 0.25 * (p.z / H) ** 2)
    def crownN(p):
        q = p - (crown - ZUP * rzd * 0.5)
        return Vector((q.x / R, q.y / R, q.z / (rzu + rzd * 0.5))).normalized()
    fc0 = crown_col(crown, R, rzu, rzd, *cols)
    fc = lambda p, d: tuple(c * k[i] for i, c in enumerate(fc0(p, d)))
    inner = tuple(c * k[i] for i, c in enumerate(cols[1]))
    # bole: 3-sided, flared at the root
    bk = C('#43362b')
    base = [b.vert((math.cos(2.1 * i) * r0 * 1.9, math.sin(2.1 * i) * r0 * 1.9, 0), 0.0) for i in range(3)]
    tk = fork.lerp(crown, 0.45)                                                          # bole top, hidden inside the lower masses
    mid = [b.vert(tk + Vector((math.cos(2.1 * i + 0.5) * r0 * 0.95, math.sin(2.1 * i + 0.5) * r0 * 0.95, 0)), 0.05) for i in range(3)]
    for i in range(3):
        j = (i + 1) % 3
        b.face_auto([base[i], base[j], mid[j], mid[i]], 'Bark', [mulc(bk, 0.6), mulc(bk, 0.6), mulc(bk, 0.95), mulc(bk, 0.95)], (tk.x * 0.5, tk.y * 0.5, tk.z * 0.5), smooth=True)
    ph = rng.uniform(0, 2 * pi)
    dirs = [((ZUP + rvec(rng) * 0.2).normalized(), 1.1, 0.66)]
    for i in range(nup):
        a = ph + 2 * pi * i / nup + rng.uniform(-0.3, 0.3); el = rng.uniform(0.3, 0.6)
        dirs.append((Vector((math.cos(a) * math.cos(el), math.sin(a) * math.cos(el), math.sin(el))), rng.uniform(0.95, 1.15), rng.uniform(0.56, 0.66)))
    for i in range(nlow):
        a = ph + 2 * pi * (i + 0.5) / nlow + rng.uniform(-0.3, 0.3); el = rng.uniform(-0.75, -0.3)
        dirs.append((Vector((math.cos(a) * math.cos(el), math.sin(a) * math.cos(el), math.sin(el))), rng.uniform(0.85, 1.2), rng.uniform(0.6, 0.72)))
    for bi, (d, size, f) in enumerate(dirs):
        rc = R * 0.47 * size
        c = crown + Vector((d.x * R, d.y * R, d.z * (rzu if d.z > 0 else rzd))) * f
        tint = rng.uniform(0.84, 1.18); hy = rng.uniform(-0.15, 0.2)
        def nfn(p, fn, c=c): return (crownN(p) * 0.8 + (p - c).normalized() * 0.06 + ZUP * 0.16).normalized()
        def colfn(p, dr, tint=tint, hy=hy):
            q = p - crown; q = Vector((q.x / R, q.y / R, q.z / (rzu if q.z > 0 else rzd)))
            q = q.normalized() if q.length > 1e-4 else ZUP
            ps = crown + Vector((q.x * R, q.y * R, q.z * (rzu if q.z > 0 else rzd)))             # colour as if on the crown's outer shell,
            lit = mulc(hue(fc(ps, crownN(p)), hy), tint)                                         # so a mass is not dark wherever it dips inward
            shade = 0.1 * clamp(-dr.z) + 0.5 * clamp((cz + 0.15 * rzu - (ps.z * 0.7 + p.z * 0.3)) / (rzd + 0.15 * rzu)) ** 1.5          # the crown's underside as a whole, not each mass's
            return lerpc(lit, mulc(inner, 0.85), clamp(shade))
        _blob(b, c, Vector((rc, rc * rng.uniform(0.85, 1.1), rc * rng.uniform(0.6, 0.74))), rng, colfn, nfn, wind, tilt=0.35)
    b.fit(dims)
    return b


def birch_lod(name, H, seed, dims):
    """slim, airy stand-in for birch(): white pole, small pale hanging leaf masses strung up it on alternating sides"""
    b = VB(name, seed, ao_dist=2.0, ao_strength=0.3)
    rng = b.rng
    lean = Vector((rng.uniform(-0.5, 0.5), rng.uniform(-0.5, 0.5), 0))
    ax = lambda z: lean * (z / H) ** 2 + Vector((0, 0, z))
    R = H * 0.17
    crown = ax(H * 0.66)
    def crownN(p):
        q = p - Vector((crown.x, crown.y, H * 0.5))
        return Vector((q.x / R, q.y / R, q.z / (H * 0.5))).normalized()
    fc = crown_col(crown, R * 1.25, H * 0.36, H * 0.34, BIRCH_TOP, BIRCH_IN, C('#a8b848'))
    def wind(p):
        a = ax(p.z); dd = math.hypot(p.x - a.x, p.y - a.y)
        return clamp(0.2 * (p.z / H) ** 2 + 0.28 * clamp(dd / R) + 0.3 * (p.z / H))
    white = C('#d6d2c2'); r0 = 0.14
    base = [b.vert((math.cos(2.1 * i) * r0, math.sin(2.1 * i) * r0, 0), 0.0) for i in range(3)]
    sa = b.vert(ax(H * 0.72), 0.3)
    for i in range(3):
        b.face_auto([base[i], base[(i + 1) % 3], sa], 'Bark', [mulc(white, 0.45), mulc(white, 0.45), mulc(white, 0.72)], (0, 0, H * 0.3))
    ph = rng.uniform(0, 2 * pi)
    spec = [(0.42, 0.95, 0.45), (0.55, 1.1, 0.4), (0.68, 1.05, 0.36), (0.81, 0.9, 0.25), (0.93, 0.55, 0.05)]     # height, size, offset from the pole
    for i, (t, size, off) in enumerate(spec):
        a = ph + i * 2.39996 + rng.uniform(-0.3, 0.3)
        dh = Vector((math.cos(a), math.sin(a), 0))
        c = ax(H * t) + dh * R * off
        tint = rng.uniform(0.92, 1.1); hy = rng.uniform(-0.03, 0.18)
        def nfn(p, fn, c=c): return (crownN(p) * 0.65 + (p - c).normalized() * 0.2 + ZUP * 0.15).normalized()
        def colfn(p, dr, tint=tint, hy=hy):
            q = p - crown; q = Vector((q.x, q.y, 0))
            q = q.normalized() if q.length > 1e-4 else Vector((1, 0, 0))
            lit = mulc(hue(fc(Vector((crown.x, crown.y, p.z)) + q * R * 1.25, dr), hy), tint * 0.6)
            return lerpc(lit, mulc(lerpc(BIRCH_IN, BIRCH_TOP, 0.3), 0.8), clamp(-0.35 * dr.z))
        _blob(b, c, Vector((R * 0.6 * size, R * 0.5 * size, H * 0.095 * size)), rng, colfn, nfn, wind, tilt=0.4, nr=4 if i < 4 else 3)
    b.fit(dims)
    return b


# ---------- detailed vegetation
class VB(B):
    """vegetation builder: smooth bark tubes, double-sided opaque leaf cards with authored (crown-blended) normals"""
    def __init__(s, name, seed=1, **k):
        super().__init__(name, seed, **k); s.cn = {}; s._bk = {}

    def nface(s, idx, mat, cols, nrms):
        s.cn[len(s.f)] = [tuple(n) for n in nrms]
        s.f.append((list(idx), mat, True, [tuple(c) for c in cols]))

    def card(s, idx, ctop, cbot, nfn, ref, double=False):
        """leaf card whose front faces ref (ctop colours); double adds a back side with cbot colours"""
        idx = list(idx); ctop = list(ctop); cbot = list(cbot or ctop)
        p = [s.v[i] for i in idx]
        fn = (p[1] - p[0]).cross(p[2] - p[0])
        if fn.length < 1e-9: return
        fn.normalize()
        if fn.dot(ref) < 0:
            idx.reverse(); ctop.reverse(); cbot.reverse(); fn = -fn
        s.nface(idx, 'Leaf', ctop, [nfn(s.v[i], fn) for i in idx])
        if not double: return
        bi = []
        for i in idx:
            if i not in s._bk: s._bk[i] = s.vert(s.v[i], s.w[i])
            bi.append(s._bk[i])
        s.nface(bi[::-1], 'Leaf', cbot[::-1], [nfn(s.v[i], -fn) for i in idx][::-1])

    def tube(s, pts, radii, n, colfn, winds, rmod=None, twist=0.0, mat='Bark', jit=0.07):
        pts = [Vector(p) for p in pts]; rings = []; e1 = None
        for i, p in enumerate(pts):
            t = (pts[min(i + 1, len(pts) - 1)] - pts[max(i - 1, 0)]).normalized()
            if e1 is None:
                e1 = t.cross(Vector((0, 1, 0)))
                if e1.length < 1e-3: e1 = t.cross(Vector((1, 0, 0)))
            else: e1 = e1 - t * e1.dot(t)
            e1.normalize(); e2 = t.cross(e1)
            ring = []
            for k in range(n):
                a = 2 * pi * k / n + twist * i
                r = radii[i] * (rmod(i, a) if rmod else 1.0)
                ring.append(s.vert(p + (e1 * math.cos(a) + e2 * math.sin(a)) * r, winds[i]))
            rings.append(ring)
        vc = {}
        def col(i):
            if i not in vc: vc[i] = s.vary(colfn(s.v[i]), jit)
            return vc[i]
        for i in range(len(rings) - 1):
            for k in range(n):
                j = (k + 1) % n
                q = [rings[i][k], rings[i][j], rings[i + 1][j], rings[i + 1][k]]
                s.face(q, mat, [col(x) for x in q], smooth=True)
        return rings

    def fit(s, dims):
        """scale about the trunk base so the bounding box equals dims exactly (keeps colliders / LOD swap valid)"""
        k = [dims[i] / (max(v[i] for v in s.v) - min(v[i] for v in s.v)) for i in range(3)]
        for v in s.v: v.x *= k[0]; v.y *= k[1]; v.z *= k[2]
        s.fitk = k

    def build(s, parent=None, loc=(0, 0, 0)):
        ob = super().build(parent, loc)
        me = ob.data
        nr = [tuple(c.vector) for c in me.corner_normals]
        for fi, poly in enumerate(me.polygons):
            c = s.cn.get(fi)
            if c:
                for k, li in enumerate(poly.loop_indices): nr[li] = c[k]
        me.normals_split_custom_set(nr)
        return ob


def hue(c, y):
    """y>0 warmer / yellower, y<0 cooler / bluer"""
    return (c[0] * (1 + 0.55 * y), c[1] * (1 + 0.12 * y), c[2] * (1 - 0.5 * y))


def bark_fn(b, dark, light, H, top=None, fine=3.0):
    off = Vector((b.rng.uniform(-40, 40), b.rng.uniform(-40, 40), b.rng.uniform(-40, 40)))
    def fn(p):
        n1 = noise.noise(Vector((p.x * fine, p.y * fine, p.z * 0.45)) + off)          # vertical fissures
        n2 = noise.noise(p * 1.1 + off)
        c = lerpc(dark, light, clamp(0.5 + 0.95 * n1 + 0.45 * n2))
        if top: c = lerpc(c, top, clamp(p.z / H) ** 1.5 * 0.8)
        return mulc(c, 0.72 + 0.28 * clamp(p.z / 1.6))                                   # damp, dark root collar
    return fn


def flare(amp, lobes, ph, rings=2):
    def rmod(i, a):
        if i >= rings: return 1.0
        k = (1.0, 0.35)[i] if rings == 2 else (1.0, 0.5, 0.15)[i]
        return 1.0 + k * amp * (0.55 + 0.45 * math.cos(lobes * a + ph)) + k * amp * 0.25 * math.cos((lobes + 2) * a - ph * 1.7)
    return rmod


def rvec(rng):
    while True:
        v = Vector((rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(-1, 1)))
        if 0.05 < v.length < 1: return v.normalized()


# ---------- conifers
def bough(b, p0, az, L, elev0, droop, W, cup, ctip, cin, cund, nfn, w0, w1, upturn=0.3, subs=0):
    """one spruce spray: a bent spine carrying a drooping, tent-shaped needle fan with forward-raked barbs and a sharp tip.
    The top is serrated; the underside is a cheaper un-notched hull (only ever seen from below). subs adds side sprays."""
    rng = b.rng
    dh = Vector((math.cos(az), math.sin(az), 0)); side = Vector((-dh.y, dh.x, 0))
    P = [Vector(p0)]; dirs = []
    for i in range(2):
        sm = (i + 0.5) / 2
        el = elev0 - droop * sm + upturn * clamp((sm - 0.55) / 0.45)
        d = dh * math.cos(el) + ZUP * math.sin(el)
        P.append(P[-1] + d * (L * (0.46, 0.54)[i])); dirs.append(d)
    wm = lerp(w0, w1, 0.38)
    ws = [w0, wm, w1]
    ids = [b.vert(q, ws[i]) for i, q in enumerate(P)]
    cs = [lerpc(cund, cin, 0.7), lerpc(cin, ctip, 0.35), mulc(ctip, 1.08)]
    cu = [lerpc(cund, cin, 0.35), lerpc(cund, cin, 0.8), lerpc(cin, ctip, 0.35)]
    for sg in (-1, 1):
        k1 = rng.uniform(0.85, 1.15); k2 = rng.uniform(0.8, 1.2)
        pts = [P[0] + side * sg * W * 0.16,                                                                       # n0
               P[0].lerp(P[1], 0.8) + side * sg * W * k1 - ZUP * cup * W * k1 + dirs[0] * L * rng.uniform(0.06, 0.16),   # t1 barb
               P[1] + dirs[1] * L * 0.04 + side * sg * W * 0.4 - ZUP * cup * W * 0.3,                             # n1 notch
               P[1].lerp(P[2], 0.36) + side * sg * W * 0.5 * k2 - ZUP * cup * W * 0.5 * k2 + dirs[1] * L * rng.uniform(0.03, 0.1)]  # t2 barb
        wv = [w0, clamp(wm * 1.1), wm, clamp(lerp(wm, w1, 0.6))]
        e = [b.vert(q, wv[i]) for i, q in enumerate(pts)]
        ct = [lerpc(cund, cin, 0.8), mulc(ctip, rng.uniform(0.92, 1.14)), lerpc(cin, ctip, 0.4), mulc(ctip, rng.uniform(0.95, 1.18))]
        cb = [lerpc(cund, cin, 0.4), lerpc(cin, ctip, 0.25), lerpc(cund, cin, 0.7), lerpc(cin, ctip, 0.3)]
        for tri in ((0, 'n0', 't1'), (0, 't1', 'n1'), (0, 'n1', 1), (1, 'n1', 't2'), (1, 't2', 2)):
            vi = []; vc = []
            for x in tri:
                if isinstance(x, int): vi.append(ids[x]); vc.append(cs[x])
                else:
                    j = ('n0', 't1', 'n1', 't2').index(x); vi.append(e[j]); vc.append(ct[j])
            b.card(vi, vc, vc, nfn, ZUP)
        for tri in ((0, 1, 1), (1, 1, 3), (1, 3, 2)):                                                             # underside hull
            vi = [b.vert(P[tri[0]], ws[tri[0]]), b.vert(pts[tri[1]], wv[tri[1]]), b.vert(pts[tri[2]], wv[tri[2]]) if tri[2] == 3 else b.vert(P[tri[2]], ws[tri[2]])]
            vc = [cu[tri[0]], cb[tri[1]], cb[3] if tri[2] == 3 else cu[tri[2]]]
            b.card(vi, vc, vc, nfn, -ZUP)
    for i in range(subs):
        sg = -1 if i % 2 == 0 else 1
        f = rng.uniform(0.3, 0.5)
        bough(b, P[0].lerp(P[1], f / 0.46 if f < 0.46 else 1.0), az + sg * rng.uniform(0.55, 0.8), L * rng.uniform(0.5, 0.64), elev0 - droop * 0.4, droop * 0.8,
              W * 0.66, cup, mulc(ctip, rng.uniform(0.92, 1.08)), cin, cund, nfn, lerp(w0, w1, 0.15), w1 * 0.92, upturn)
    return P


def pine(name, H, R, seed, dims, bare=0.16, tint=1.0, dz0=1.2, dz1=0.6, nb0=6.4, full=1.0, droop_k=1.0, lean_k=0.3, wk=0.3, sub_t=0.5):
    b = VB(name, seed, ao_dist=2.6, ao_strength=0.55)
    rng = b.rng
    lean = Vector((rng.uniform(-lean_k, lean_k), rng.uniform(-lean_k, lean_k), 0))
    axis = lambda z: lean * (z / H) ** 2 + Vector((0, 0, z))
    r0 = 0.1 + H * 0.016
    rad = lambda z: r0 * (1 - z / H) ** 0.85 + 0.012
    wtr = lambda z: 0.12 * (z / H) ** 2 + 0.5 * clamp((z / H - 0.72) / 0.28) ** 2
    zb = H * bare
    envf = lambda t: R * ((1 - t) ** 0.76) * (0.8 + 0.2 * clamp(t / 0.14)) + 0.25
    wtip = lambda z: clamp(0.33 + 0.67 * (z / H) ** 1.5)
    # trunk: flared base, bark-brown below the crown, greyer up the stem
    zs = [0, 0.45, 1.3, zb * 0.6, zb, lerp(zb, H, 0.2), lerp(zb, H, 0.42), lerp(zb, H, 0.64), lerp(zb, H, 0.84), H * 0.995]
    zs = sorted(set(round(z, 3) for z in zs))
    bark = bark_fn(b, C('#2a2420'), C('#5e5040'), H, top=C('#3c332b'))
    b.tube([axis(z) for z in zs], [rad(z) for z in zs], 7, bark, [wtr(z) for z in zs], rmod=flare(0.55, 3, rng.uniform(0, 6)), twist=0.25)
    # dead stubs / snags on the bare stem
    dead = bark_fn(b, C('#3b332b'), C('#756a5c'), H)
    nst = int(3 + bare * 22)
    for i in range(nst):
        z = lerp(H * 0.07, zb * 1.02, (i + rng.random()) / nst); a = rng.uniform(0, 2 * pi)
        L = rng.uniform(0.35, 1.0) * (1.6 if rng.random() < 0.3 else 1.0)
        d = Vector((math.cos(a), math.sin(a), rng.uniform(-0.45, 0.1))).normalized()
        p0 = axis(z); p1 = p0 + d * L * 0.6 + ZUP * 0.04; p2 = p0 + d * L - ZUP * L * 0.18
        b.tube([p0, p1, p2], [rad(z) * 0.3, 0.035, 0.012], 3, dead, [wtr(z)] * 3)
    # dark inner mass: shadowed core of branches so the crown never reads as hollow
    cz = [lerp(zb + 0.25, H * 0.86, i / 6) for i in range(7)]
    core_c = lambda p: mulc(lerpc(PINE_UNDER, PINE_IN, 0.35 + 0.4 * clamp((p.z - zb) / (H - zb))), tint)
    ck = rng.uniform(0, 6)
    b.tube([axis(z) for z in cz], [max(0.05, envf((z - zb) / (H - zb)) * (0.17 if 0 < i < 6 else 0.06)) for i, z in enumerate(cz)], 5, core_c,
           [lerp(wtr(z), wtip(z), 0.25) for z in cz], rmod=lambda i, a: 1 + 0.3 * math.cos(3 * a + ck + i * 1.7), twist=0.5, mat='Leaf', jit=0.1)
    # whorls of boughs: compound sprays low down, single sprays toward the top
    z = zb; ph = rng.uniform(0, 2 * pi)
    while z < H * 0.975:
        t = (z - zb) / (H - zb)
        env = envf(t)
        nb = max(4, round(lerp(nb0, 4.6, t) + rng.uniform(-0.6, 0.6)))
        ph += 2 * pi / nb * 0.5 + rng.uniform(-0.3, 0.3)
        tipc = mulc(lerpc(PINE_IN, PINE_TIP, 0.62 + 0.38 * t), tint)
        inc = mulc(lerpc(PINE_UNDER, PINE_IN, 0.6 + 0.3 * t), tint)
        und = mulc(lerpc(PINE_UNDER, PINE_IN, 0.35), tint)
        for i in range(nb):
            if rng.random() < 0.05: continue
            a = ph + 2 * pi * i / nb + rng.uniform(-0.25, 0.25)
            L = env * rng.uniform(0.62, 1.1) * (1.15 if rng.random() < 0.08 else 1.0)
            zz = z + rng.uniform(-0.55, 0.55) * lerp(dz0, dz1, t)
            el = lerp(-0.08, 0.55, t ** 1.5) + rng.uniform(-0.14, 0.14)
            dr = lerp(0.85, 0.5, t) * droop_k * rng.uniform(0.8, 1.2)
            p0 = axis(zz); ax = p0.copy()
            def nfn(p, fn, ax=ax, a=a):
                o = Vector((p.x - ax.x, p.y - ax.y, 0))
                o = o.normalized() if o.length > 1e-4 else Vector((math.cos(a), math.sin(a), 0))
                return (fn * 0.4 + (o * 0.9 + ZUP * 0.45).normalized() * 0.6).normalized()
            hy = rng.uniform(-0.12, 0.14)
            subs = 2 if (L > 1.9 and t < sub_t) else (1 if (L > 1.3 and t < sub_t + 0.2 and rng.random() < full) else 0)
            bough(b, p0, a, L, el, dr, clamp(wk * L, 0.24, 1.0), lerp(0.85, 0.6, t) * rng.uniform(0.75, 1.25),
                  b.vary(hue(tipc, hy), 0.09), hue(inc, hy), und, nfn, wtr(zz), wtip(zz), subs=subs)
        z += lerp(dz0, dz1, t) * rng.uniform(0.85, 1.18)
    # leader: a few upright needle fins around the tip
    top = axis(H * 0.91)
    for i in range(3):
        a = ph + 2 * pi * i / 3
        def nfn(p, fn, a=a): return (fn * 0.3 + Vector((math.cos(a) * 0.6, math.sin(a) * 0.6, 0.7)).normalized() * 0.7).normalized()
        bough(b, top + ZUP * 0.12 * i, a, H * 0.085, 1.3, 0.15, 0.2, 0.5, mulc(PINE_TIP, tint * 1.05), mulc(PINE_IN, tint), mulc(PINE_UNDER, tint), nfn, wtr(H * 0.9), 0.95, upturn=0.1)
    b.fit(dims)
    return b


# ---------- broadleaf
def tuft_core(b, c, rad, sub, colfn, nfn, wfn, crumple=0.22, zmin=None, disp=0.42):
    """crumpled, faceted foliage mass (closed, so it is solid from every side); lit with the soft crown normal"""
    rng = b.rng; n0 = len(b.f); v0 = len(b.v)
    b.blob(c, rad, sub, 'Leaf', colfn, disp, 1.5, smooth=True, windfn=wfn)
    for vi in range(v0, len(b.v)):
        b.v[vi][:] = Vector(c) + (b.v[vi] - Vector(c)) * rng.uniform(1 - crumple, 1 + crumple)
        if zmin is not None and b.v[vi].z < zmin: b.v[vi].z = zmin
    for fi in range(n0, len(b.f)):
        f = b.f[fi]; kk = rng.uniform(0.93, 1.07); f[3][:] = [mulc(cl_, kk) for cl_ in f[3]]
        pc = sum((b.v[i] for i in f[0]), Vector()) / 3
        b.cn[fi] = [tuple(nfn(b.v[i], (pc - Vector(c)).normalized())) for i in f[0]]
        b.f[fi] = (f[0], f[1], True, f[3])


def leaf(b, base, d, u, l, w, ct, cbs, cbk, nfn, wb, wt, double=False):
    """one pointed leaf (triangle) rooted at base, growing along u, facing d"""
    v = d.cross(u).normalized()
    ids = [b.vert(base - v * w * 0.5 - u * l * 0.1, wb), b.vert(base + v * w * 0.5 - u * l * 0.1, wb), b.vert(base + u * l, wt)]
    b.card(ids, [cbs, cbs, ct], [mulc(cbk, 0.8), mulc(cbk, 0.8), cbk], nfn, d, double)


def cluster(b, c, r, k, out, fc, crownN, wfn, tint=1.0, hy=0.0, droop=0.3, inner=OAK_IN, lk=0.42, core=0.8, sub=1, lift=0.5, double=False, wk=0.75,
            flat=0.85, belly=1.0):
    """leaf tuft / foliage pad: a dark crumpled core (flattened by flat) carrying k small pointed leaves that shingle outward
    on top and hang from its belly, so the mass reads as leaves from above and from the ground"""
    rng = b.rng; R3 = Matrix.Rotation(rng.uniform(0, 6.28), 3, 'Z')
    sc = Vector((1, 1, flat if core else 1.0))
    def nfn(p, fn):
        q = (p - c) / max(r, 1e-3); q.z /= sc.z
        return (fn * 0.2 + crownN(p) * 0.45 + q * 0.36 + ZUP * 0.08).normalized()
    if core:
        rc = r * core
        def cfn(p, d):
            base = lerpc(inner, hue(fc(p, d), hy), clamp(0.4 + 0.3 * d.z + 0.16 * d.dot(out)))      # lit top, shaded belly
            return mulc(base, tint * 0.86)
        v0 = len(b.v)
        tuft_core(b, c, (rc, rc * rng.uniform(0.82, 1.0), rc * flat), sub, cfn, nfn, wfn)
        for vi in range(v0, len(b.v)):                                  # flatter belly, like a cumulus
            if b.v[vi].z < c.z: b.v[vi].z = c.z + (b.v[vi].z - c.z) * belly
    for i in range(k):
        zf = 1 - 1.9 * (i + 0.5) / k; rr = math.sqrt(max(0, 1 - zf * zf)); a = i * 2.39996
        d = R3 @ Vector((rr * math.cos(a), rr * math.sin(a), zf))
        d = (d + out * 0.2 + rvec(rng) * 0.15).normalized()
        u = rvec(rng) + out * 0.3 - ZUP * droop
        u = u - d * u.dot(d)
        if u.length < 1e-3: continue
        u = (u.normalized() + d * lift * rng.uniform(0.1, 1.0)).normalized()   # tips lift away from the core
        fd = d; lk_ = 1.0 if d.z > -0.1 else 1.25
        base = c + Vector((d.x, d.y, d.z * sc.z * (belly if d.z < 0 else 1.0))) * r * (core * 0.96 if core else rng.uniform(0.1, 0.7))
        l = r * lk * lk_ * rng.uniform(0.75, 1.25); w = l * wk * rng.uniform(0.85, 1.25)
        tipp = base + u * l
        ct = mulc(hue(fc(tipp, d), hy + rng.uniform(-0.08, 0.08)), tint * rng.uniform(0.86, 1.14))
        if core and d.z < -0.1: ct = lerpc(ct, mulc(inner, 1.25), 0.5)                      # shaded belly leaves
        leaf(b, base, fd, u, l, w, ct, mulc(lerpc(inner, ct, 0.55), 0.9), mulc(lerpc(inner, ct, 0.6), 0.85), nfn, wfn(base), wfn(tipp), double)


def crown_col(center, rx, rzu, rzd, top, inner, sun, sundir=Vector((0.5, -0.3, 0.8)).normalized()):
    def fn(p, d):
        q = p - center
        q = Vector((q.x / rx, q.y / rx, q.z / (rzu if q.z > 0 else rzd)))
        radial = clamp(q.length)
        up = clamp(0.5 + 0.5 * q.z)
        c = lerpc(inner, top, clamp(0.08 + 0.42 * up + 0.5 * radial ** 2))
        qn = q.normalized() if q.length > 1e-4 else ZUP
        c = lerpc(c, sun, clamp((qn * 0.6 + d * 0.4).dot(sundir)) ** 2 * 0.4 * (0.4 + 0.6 * up))
        return mulc(c, 1 + 0.14 * noise.noise(p * 0.6))
    return fn


def oak(name, H, R, seed, dims, nlimb=4, nbig=8, nmed=13, nsmall=16, cols=(OAK_TOP, OAK_IN, OAK_SUN)):
    b = VB(name, seed, ao_dist=3.0, ao_strength=0.5)
    rng = b.rng
    lean = Vector((rng.uniform(-0.5, 0.5), rng.uniform(-0.5, 0.5), 0))
    cz = H * 0.6; rzu = H - cz; rzd = cz - H * 0.3
    crown = Vector((lean.x, lean.y, cz))
    fork = Vector((lean.x * 0.45, lean.y * 0.45, H * 0.3))
    r0 = 0.2 + H * 0.014
    def shell(d, f): return crown + Vector((d.x * R, d.y * R, d.z * (rzu if d.z > 0 else rzd))) * f
    def crownN(p):
        q = p - (crown - ZUP * rzd * 0.5)
        return Vector((q.x / R, q.y / R, q.z / (rzu + rzd * 0.5))).normalized()
    def wind(p):
        if p.z <= fork.z * 0.7: return 0.12 * (p.z / H) ** 2
        return clamp(0.12 * (p.z / H) ** 2 + 0.9 * clamp(max(0.0, (p - fork).length - 0.3 * fork.z) / (1.25 * R)) ** 1.25)
    fc = crown_col(crown, R, rzu, rzd, *cols)
    bark = bark_fn(b, C('#2a2320'), C('#5f5142'), H, fine=2.2)
    # trunk with root flare, continuing into a central leader
    tz = [0, 0.4, 1.1, fork.z * 0.62, fork.z]
    tp = [Vector((lean.x * 0.45 * (z / fork.z) ** 1.5, lean.y * 0.45 * (z / fork.z) ** 1.5, z)) for z in tz]
    ld = (ZUP + rvec(rng) * 0.3).normalized(); lend = shell(ld, 0.72)
    lmid = fork.lerp(lend, 0.5) + rvec(rng) * 0.4
    tp += [lmid, lend]
    b.tube(tp, [r0 * 1.45, r0 * 1.2, r0 * 1.02, r0 * 0.92, r0 * 0.86, r0 * 0.5, r0 * 0.2], 9, bark, [wind(p) for p in tp], rmod=flare(0.95, 4, rng.uniform(0, 6)), twist=0.12)
    # limbs leave the trunk at staggered heights, arc out and up; each carries secondaries and twigs
    def bez(p0, p1, p2, n):
        return [p0.lerp(p1, t).lerp(p1.lerp(p2, t), t) for t in (i / (n - 1) for i in range(n))]
    big = [(lend + ld * 0.3, ld)]; med = [(lmid, ld)]; ph = rng.uniform(0, 6.28)
    def secondary(p0, d, rl, f0=0.8, f1=0.92):
        d2 = (d + rvec(rng) * 0.8 + ZUP * 0.1).normalized()
        if d2.z < -0.2: d2.z = -0.2; d2.normalize()
        e2 = shell(d2, rng.uniform(f0, f1))
        pts = bez(p0, p0.lerp(e2, 0.5) + ZUP * 0.05 * H + rvec(rng) * 0.3, e2, 3)
        b.tube(pts, [rl, rl * 0.6, 0.03], 3, bark, [wind(p) for p in pts])
        med.append((e2, d2))
        d3 = (d2 + rvec(rng) * 0.9).normalized(); e3 = pts[1] + d3 * R * 0.3
        b.tube([pts[1], e3], [rl * 0.4, 0.02], 3, bark, [wind(pts[1]), wind(e3)])
        med.append((e3, d3))
    for i in range(nlimb):
        a = ph + 2 * pi * i / nlimb + rng.uniform(-0.35, 0.35); el = rng.uniform(0.25, 0.7)
        d = Vector((math.cos(a) * math.cos(el), math.sin(a) * math.cos(el), math.sin(el)))
        dh = Vector((math.cos(a), math.sin(a), 0))
        zst = fork.z * rng.uniform(0.8, 1.02)
        st = Vector((fork.x * (zst / fork.z) ** 1.5, fork.y * (zst / fork.z) ** 1.5, zst)) + dh * r0 * 0.2
        end = shell(d, rng.uniform(0.55, 0.68))
        ctrl = st + dh * (end - st).length * 0.42 + ZUP * (end.z - st.z) * 0.3 + rvec(rng) * 0.3
        pts = bez(st, ctrl, end, 5)
        rl = r0 * rng.uniform(0.5, 0.62)
        b.tube(pts, [rl, rl * 0.84, rl * 0.68, rl * 0.48, rl * 0.24], 5, bark, [wind(p) for p in pts], twist=0.2)
        big.append((end + d * 0.3, d))
        secondary(pts[1].lerp(pts[2], 0.5), d, rl * 0.42)
        secondary(pts[2].lerp(pts[3], 0.5), d, rl * 0.36)
        secondary(pts[3], d, rl * 0.3)
    secondary(lmid, ld, r0 * 0.25, 0.7, 0.9)
    # foliage pads: big masses on the limb ends, medium on the secondaries, small tufts clinging to the crown shell
    cl = []
    rb = R * 0.36
    def try_add(c, r, tol, kind):
        for c2, r2, _ in cl:
            if (c - c2).length < (r + r2) * tol: return False
        cl.append((c, r, kind)); return True
    def count(kind): return sum(1 for x in cl if x[2] == kind)
    for p, d in big: try_add(p, rb * rng.uniform(0.85, 1.12), 0.4, 2)
    tries = 0
    while count(2) < nbig and tries < 2000:
        tries += 1; d = rvec(rng)
        if d.z < 0.3: continue
        try_add(shell(d, rng.uniform(0.5, 0.72)), rb * rng.uniform(0.8, 1.1), 0.5, 2)
    rng.shuffle(med)
    for p, d in med:
        if count(1) >= nmed: break
        try_add(p + d * 0.2, rb * rng.uniform(0.58, 0.8), 0.45, 1)
    tries = 0
    while count(1) < nmed and tries < 3000:
        tries += 1; d = rvec(rng)
        if d.z < -0.3: continue
        r = rb * rng.uniform(0.58, 0.8)
        try_add(shell(d, rng.uniform(0.8, 0.95) - 0.5 * r / R), r, 0.5, 1)
    tries = 0; pads = [x for x in cl]
    while count(0) < nsmall and tries < 6000:                           # small tufts cling to the rims of the pads
        tries += 1; pc, pr, _ = rng.choice(pads); a = rng.uniform(0, 2 * pi)
        r = rb * rng.uniform(0.26, 0.4)
        c = pc + Vector((math.cos(a), math.sin(a), rng.uniform(-0.25, 0.3))) * (pr * 0.95)
        q = c - crown
        if Vector((q.x / R, q.y / R, q.z / (rzu if q.z > 0 else rzd))).length < 0.6: continue      # only on the outside of the crown
        try_add(c, r, 0.36, 0)
    for c, r, kind in cl:
        q = c - crown
        out = Vector((q.x / R, q.y / R, q.z / (rzu if q.z > 0 else rzd)))
        out = out.normalized() if out.length > 1e-3 else ZUP
        cluster(b, c, r, (15, 44, 64)[kind], out, fc, crownN, wind, tint=rng.uniform(0.82, 1.22), hy=rng.uniform(-0.15, 0.2),
                inner=cols[1], sub=2 if kind == 2 else 1, lk=(0.62, 0.38, 0.26)[kind], wk=0.9, core=0.86, flat=rng.uniform(0.62, 0.8) if kind else 0.85, belly=0.6 if kind else 0.85)
    b.fit(dims)
    return b


def birch(name, H, seed, dims):
    b = VB(name, seed, ao_dist=2.0, ao_strength=0.42)
    rng = b.rng
    lean = Vector((rng.uniform(-0.6, 0.6), rng.uniform(-0.6, 0.6), 0))
    ax = lambda z: lean * (z / H) ** 2 + Vector((0.12 * math.sin(z * 0.55), 0.1 * math.sin(z * 0.4 + 1.0), z))
    white = C('#d6d2c2'); scar = C('#3a3530')
    rad = lambda z: 0.19 * (1 - z / H) ** 0.9 + 0.014
    wtr = lambda z: 0.2 * (z / H) ** 2 + 0.45 * clamp((z / H - 0.7) / 0.3) ** 2
    off = rng.uniform(0, 50)
    def bark(p):
        band = noise.noise(Vector((p.x * 2.0 + off, p.y * 2.0, p.z * 2.6)))
        fleck = noise.noise(Vector((p.x * 7.0, p.y * 7.0 + off, p.z * 9.0)))
        k = clamp((band - 0.12) * 5.0) * 0.85 + clamp((fleck - 0.3) * 4.0) * 0.5
        c = lerpc(mulc(white, 0.92 + 0.1 * noise.noise(p * 0.7)), scar, clamp(k))
        c = lerpc(c, mulc(scar, 0.8), clamp(1 - p.z / 1.3) ** 1.5 * 0.85)                # rough dark butt
        return lerpc(c, C('#8a7f6a'), clamp((p.z / H - 0.72) / 0.28) * 0.6)               # twiggy brown top
    nz = 14
    zs = [H * 0.985 * (i / nz) ** 1.08 for i in range(nz + 1)]
    b.tube([ax(z) for z in zs], [rad(z) for z in zs], 6, bark, [wtr(z) for z in zs], rmod=flare(0.5, 3, rng.uniform(0, 6)), twist=0.35, jit=0.04)
    R = H * 0.17
    crown = ax(H * 0.66)
    def crownN(p):
        q = p - Vector((crown.x, crown.y, H * 0.5))
        return Vector((q.x / R, q.y / R, q.z / (H * 0.5))).normalized()
    fc0 = crown_col(crown, R * 1.25, H * 0.36, H * 0.34, BIRCH_TOP, BIRCH_IN, C('#a8b848'))
    twig = lambda p: lerpc(C('#4a3c2e'), C('#8a7c66'), clamp(0.5 + noise.noise(p * 2.0)))
    def wind(p):
        a = ax(p.z); dd = math.hypot(p.x - a.x, p.y - a.y)
        return clamp(wtr(p.z) + 0.28 * clamp(dd / R) + 0.3 * (p.z / H))
    nbr = 14; ph = rng.uniform(0, 6.28); cl = []
    for i in range(nbr):
        t = i / (nbr - 1)
        z = H * lerp(0.3, 0.9, t ** 0.9); a = ph + i * 2.39996 + rng.uniform(-0.3, 0.3)
        L = R * lerp(1.75, 0.7, t) * rng.uniform(0.8, 1.15)
        el = lerp(0.75, 1.1, t) + rng.uniform(-0.12, 0.12)                                  # fine, steeply upswept
        dh = Vector((math.cos(a), math.sin(a), 0))
        p0 = ax(z); p1 = p0 + (dh * math.cos(el) + ZUP * math.sin(el)) * L * 0.6
        p2 = p1 + (dh * math.cos(el * 0.55) + ZUP * math.sin(el * 0.55)) * L * 0.45
        p3 = p2 + dh * L * 0.22 - ZUP * L * 0.2                                             # weeping tip
        r = rad(z) * 0.42
        b.tube([p0, p1, p2, p3], [r, r * 0.6, r * 0.32, 0.01], 3, twig, [wtr(z), wind(p1), wind(p2), wind(p3)])
        for q, s in ((p1, 0.8), (p1.lerp(p2, 0.5), 0.95), (p2, 1.0), (p2.lerp(p3, 0.5) - ZUP * 0.3, 1.0), (p3 - ZUP * 0.45, 0.9)):
            cl.append((q + rvec(rng) * 0.3 + dh * rng.uniform(-0.1, 0.35), s, dh))
    for hz in (0.93, 0.985):
        cl.append((ax(H * hz), 0.85, ZUP))
    for c, s, dh in cl:
        r = R * 0.42 * s * rng.uniform(0.82, 1.2)
        out = (dh * 0.7 + ZUP * 0.3).normalized()
        cluster(b, c, r, 12, out, fc0, crownN, wind, tint=rng.uniform(0.9, 1.1), hy=rng.uniform(-0.05, 0.2), droop=1.1,
                inner=BIRCH_IN, lk=0.5, core=0.0, lift=0.15, double=True, wk=0.62)
    b.fit(dims)
    return b


def dead_tree(name, H, seed, dims):
    b = VB(name, seed, ao_dist=1.5, ao_strength=0.4)
    rng = b.rng
    lean = Vector((0.7, -0.3, 0))
    ax = lambda z: lean * (z / H) ** 2 + Vector((0, 0, z))
    bark = bark_fn(b, C('#3f372f'), C('#857a6b'), H, top=C('#9a9082'), fine=3.5)
    zt = H * 0.8
    zs = [0, 0.35, 1.0, zt * 0.3, zt * 0.48, zt * 0.66, zt * 0.84, zt]
    rad = lambda z: 0.33 * (1 - z / (H * 1.25)) ** 1.3
    rings = b.tube([ax(z) for z in zs], [rad(z) for z in zs], 7, bark, [0.06 * (z / H) ** 2 for z in zs], rmod=flare(0.75, 3, 1.3), twist=0.3, jit=0.1)
    # splintered, snapped top with a dark hollow
    top = rings[-1]; cen = ax(zt); spikes = []
    for k, vi in enumerate(top):
        p = b.v[vi]; hgt = rng.uniform(0.15, 0.5) * (2.6 if k in (1, 2) else 1.0)
        spikes.append(b.vert(p.lerp(cen, 0.35) + ZUP * hgt + lean * 0.02, 0.08))
    hollow = b.vert(cen - ZUP * 0.25, 0.05)
    for k in range(len(top)):
        j = (k + 1) % len(top)
        ca = bark(b.v[top[k]]); cs = mulc(C('#a39884'), rng.uniform(0.8, 1.1))
        b.face([top[k], top[j], spikes[k]], 'Bark', [ca, ca, cs])
        b.face([top[j], spikes[j], spikes[k]], 'Bark', [ca, cs, cs])
        b.face([spikes[k], spikes[j], hollow], 'Bark', [mulc(cs, 0.5), mulc(cs, 0.5), DARK])
    def limb(p0, d, L, r, depth, w0):
        d1 = (d + rvec(rng) * 0.3).normalized()
        p1 = p0 + d * L * 0.5; p2 = p1 + (d1 + ZUP * 0.25).normalized() * L * 0.5
        n = 5 if depth == 0 else (4 if depth == 1 else 3)
        w1 = w0 + 0.02; w2 = w0 + 0.05                                                      # dead wood stays nearly rigid
        b.tube([p0, p1, p2], [r, r * 0.72, r * (0.5 if depth < 2 else 0.12)], n, bark, [w0, w1, w2], jit=0.1)
        if depth >= 2: return
        for sgn in (-1, 1):                                                                 # fork
            dd = (d1 + ZUP * rng.uniform(0.1, 0.6) + d1.cross(ZUP).normalized() * sgn * rng.uniform(0.45, 0.9)).normalized()
            limb(p2, dd, L * rng.uniform(0.5, 0.72), r * 0.48, depth + 1, w2)
        if depth == 0:                                                                      # side spur from the elbow
            dd = (d + rvec(rng) * 0.9 + ZUP * 0.2).normalized()
            limb(p1, dd, L * rng.uniform(0.3, 0.45), r * 0.4, 2, w1)
    nb = 6
    for i in range(nb):
        z = H * (0.3 + 0.085 * i); a = i * 2.4 + rng.uniform(-0.3, 0.3)
        L = H * rng.uniform(0.2, 0.33) * (1 - 0.07 * i)
        d = Vector((math.cos(a), math.sin(a), rng.uniform(0.3, 0.75))).normalized()
        limb(ax(z), d, L, 0.13 * (1 - 0.08 * i), 0, 0.06 * (z / H) ** 2)
    for i in range(4):                                                                      # short snapped stubs low down
        z = H * rng.uniform(0.12, 0.3); a = rng.uniform(0, 6.28)
        d = Vector((math.cos(a), math.sin(a), rng.uniform(-0.1, 0.4))).normalized()
        p0 = ax(z); b.tube([p0, p0 + d * rng.uniform(0.35, 0.7)], [0.07, 0.03], 3, bark, [0.0, 0.03], jit=0.1)
    b.fit(dims)
    return b


def bush(name, seed, R, dims, cols=(C('#5b7430'), C('#2a4219'), C('#86923c')), ns=300):
    b = VB(name, seed, ao_dist=1.2, ao_strength=0.5)
    rng = b.rng
    c0 = Vector((0, 0, R * 0.42))
    fc = crown_col(c0, R * 1.1, R * 0.8, R * 0.5, *cols)
    wind = lambda p: clamp(0.3 + 0.6 * p.z / (R * 1.2))
    lobes = [(c0, Vector((R * 0.8, R * 0.72, R * 0.56))), (c0 + Vector((R * 0.66, R * 0.3, -R * 0.14)), Vector((R * 0.46, R * 0.46, R * 0.4))),
             (c0 + Vector((-R * 0.6, -R * 0.45, -R * 0.18)), Vector((R * 0.44, R * 0.44, R * 0.36)))]
    dark = lambda p, d: mulc(lerpc(cols[1], cols[0], 0.3 + 0.3 * clamp(d.z)), 0.8)
    def crownN(p):
        q = p - Vector((0, 0, -R * 0.1)); return Vector((q.x, q.y, q.z * 1.3)).normalized()
    cnf = lambda p, fn: (fn * 0.25 + crownN(p) * 0.75).normalized()
    tuft_core(b, lobes[0][0], lobes[0][1] * 0.86, 2, dark, cnf, wind, 0.12, zmin=0.0, disp=0.2)
    for c, r in lobes[1:]: tuft_core(b, c, r * 0.86, 1, dark, cnf, wind, 0.12, zmin=0.0, disp=0.2)
    for (c, r), sh in zip(lobes, (0.5, 0.26, 0.24)):
        n_ = round(ns * sh); R3 = Matrix.Rotation(rng.uniform(0, 6.28), 3, 'Z')
        def nfn(p, fn): return (fn * 0.25 + crownN(p) * 0.75).normalized()
        for i in range(n_):
            zf = 1 - 1.3 * (i + 0.5) / n_; rr = math.sqrt(max(0, 1 - zf * zf)); a = i * 2.39996
            d = (R3 @ Vector((rr * math.cos(a), rr * math.sin(a), zf)) + rvec(rng) * 0.15).normalized()
            base = c + Vector((d.x * r.x, d.y * r.y, d.z * r.z)) * 0.9
            if base.z < 0.06: base.z = 0.06
            u = rvec(rng) + ZUP * 0.5
            u = u - d * u.dot(d)
            if u.length < 1e-3: continue
            u = (u.normalized() + d * rng.uniform(0.15, 0.8)).normalized(); v = d.cross(u).normalized()
            l = R * rng.uniform(0.18, 0.32); w = l * rng.uniform(0.75, 1.1)
            tipp = base + u * l
            ct = mulc(hue(fc(tipp, d), rng.uniform(-0.1, 0.16)), rng.uniform(0.85, 1.15))
            cbs = mulc(lerpc(cols[1], ct, 0.55), 0.9)
            ids = [b.vert(q, wind(q)) for q in (base - v * w * 0.5, base + v * w * 0.5, tipp)]
            for vi in ids: b.v[vi].z = max(b.v[vi].z, 0.0)                                   # nothing below the ground plane
            b.card(ids, [cbs, cbs, ct], [cbs] * 3, nfn, d)
    twig = lambda p: lerpc(C('#3a2c20'), C('#6b5640'), clamp(0.5 + noise.noise(p * 3.0)))
    for i in range(5):                                                                      # a few bare twigs poking out
        a = i * 1.3 + rng.uniform(-0.3, 0.3); el = rng.uniform(0.5, 1.1)
        d = Vector((math.cos(a) * math.cos(el), math.sin(a) * math.cos(el), math.sin(el)))
        p0 = Vector((d.x * R * 0.15, d.y * R * 0.15, 0.02)); p1 = p0 + d * R * rng.uniform(0.95, 1.2)
        b.tube([p0, p0.lerp(p1, 0.55) + rvec(rng) * 0.06 * R, p1], [0.035 * R, 0.022 * R, 0.006], 3, twig, [0.0, wind(p1) * 0.5, wind(p1)], mat='Leaf')
    b.fit(dims)
    return b


ROCK = C('#857d72'); ROCK_L = C('#a29a8c'); ROCK_D = C('#5c564f'); MOSS = C('#5f6a3a')
def rock_col(b, moss=0.35):
    def fn(p, d):
        c = lerpc(ROCK_D, ROCK_L, clamp(0.5 + 0.7 * noise.noise(p * 0.8) + 0.25 * d.z))
        c = lerpc(c, MOSS, clamp(d.z - 0.55) * 2 * moss * clamp(0.5 + noise.noise(p * 0.5 + Vector((7, 0, 0)))))
        return c
    return fn


def rock(name, seed, parts, sub=2, strata=0.0):
    b = B(name, seed, ao_dist=2.0, ao_strength=0.5)
    fc = rock_col(b)
    for c, r in parts:
        n0 = len(b.v)
        b.blob(c, r, sub, 'Rock', fc, 0.6, 0.9, smooth=False, zmin=-0.05)
        if strata:
            for v in b.v[n0:]:
                q = round(v.z / strata) * strata
                v.z = lerp(v.z, q, 0.7)
                v.x += 0.25 * strata * math.sin(q * 3.1); v.y += 0.25 * strata * math.cos(q * 2.3)
    return b


# =====================================================================================
def main():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    make_materials()
    veg = lambda: [
        pine('Tree_Pine_A', 17.0, 3.3, 101, (6.36, 6.09, 17.0), wk=0.4),
        pine('Tree_Pine_B', 20.0, 2.7, 102, (4.88, 5.28, 20.0), bare=0.3, tint=0.92, dz0=1.3, dz1=0.62, nb0=5.4, full=0.6, droop_k=1.3, sub_t=0.4),
        oak('Tree_Oak_A', 12.5, 5.6, 111, (12.49, 12.17, 12.08), nlimb=4, nbig=9, nmed=19, nsmall=28),
        oak('Tree_Oak_B', 10.5, 5.0, 112, (10.99, 10.86, 9.9), nlimb=3, nbig=8, nmed=16, nsmall=24, cols=(C('#6a7a2c'), OAK_IN, C('#96963a'))),
        birch('Tree_Birch', 11.5, 121, (4.01, 3.83, 11.95)), dead_tree('Tree_Dead', 9.0, 131, (3.78, 3.07, 8.01)),
        bush('Bush_A', 141, 1.1, (2.54, 2.08, 1.29)), bush('Bush_B', 142, 0.8, (1.84, 1.54, 0.93), cols=(C('#6f7d33'), C('#324a1c'), C('#9a9a40'))),
        pine_lod('Tree_Pine_LOD', 17.5, 3.0, 5, 103, (5.1, 4.9, 17.5)), oak_lod('Tree_Oak_LOD', 11.5, 5.4, 113, (11.6, 11.2, 11.0), k=(0.6, 0.545, 0.63)),
        birch_lod('Tree_Birch_LOD', 11.5, 122, (4.01, 3.83, 11.95))]
    if VEG_ONLY:                                  # fast vegetation-only iteration build (does not touch village.glb / stats)
        builders = veg(); out = VEG_ONLY
    else:
        out = OUT
        builders = [house_a(), house_b(), house_c(), house_d(), chapel(), windmill(), bridge(), well(), fence(), stone_wall(), dock()] + veg() + [
            rock('Rock_A', 151, [((0, 0, 0.35), (0.75, 0.6, 0.55))]),
            rock('Rock_B', 152, [((0, 0, 0.7), (1.4, 1.1, 1.0)), ((1.1, 0.5, 0.35), (0.8, 0.7, 0.55))]),
            rock('Rock_C', 153, [((0, 0, 1.1), (2.1, 1.7, 1.5)), ((-1.6, 0.9, 0.6), (1.2, 1.0, 0.85))]),
            rock('Cliff_A', 154, [((0, 0, 2.2), (4.6, 2.6, 3.0)), ((2.8, 0.6, 1.4), (3.0, 2.2, 2.0)), ((-3.0, 0.3, 1.6), (2.6, 2.2, 2.2)),
                                  ((0.5, 1.4, 4.2), (2.8, 1.8, 1.9)), ((-1.0, -1.6, 0.9), (2.4, 1.6, 1.3))], strata=0.7)]
    for b in builders: b.build()
    kw = dict(filepath=out, export_format='GLB', export_yup=True, export_apply=True, export_texcoords=True, export_normals=True,
              export_materials='EXPORT', export_animations=False, export_draco_mesh_compression_enable=False)
    try:
        bpy.ops.export_scene.gltf(**kw, export_vertex_color='ACTIVE', export_all_vertex_colors=False)
    except TypeError as e:
        print('fallback export', e)
        bpy.ops.export_scene.gltf(**kw)
    if VEG_ONLY:
        print('VEG', {k: (v['tris'], v['bbox']) for k, v in STATS.items()})
    else:
        json.dump(STATS, open(ROOT + r"\tools\blender\village_stats.json", 'w'), indent=1)
    print('VILLAGE DONE', os.path.getsize(out))


main()
