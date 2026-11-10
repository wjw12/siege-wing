# Siege Wing props kit – procedural geometry helpers (Blender 5.2, headless)
import bpy, bmesh, math, random
from mathutils import Vector, Matrix, Euler
from mathutils.bvhtree import BVHTree
from mathutils import noise

V = Vector
PI = math.pi

MAT_DEFS = {
    #  name: (metallic, roughness, double_sided)
    'Wood':  (0.0, 0.85, False),
    'Iron':  (0.9, 0.5, False),
    'Cloth': (0.0, 0.95, True),
    'Stone': (0.0, 0.9, False),
    'Rope':  (0.0, 0.95, False),
    'Paint': (0.1, 0.55, False),
    'PadLightEmissive': (0.0, 0.3, False),
}
_mats = {}


def get_mat(name):
    if name in _mats:
        return _mats[name]
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes['Principled BSDF']
    met, rough, ds = MAT_DEFS[name]
    b.inputs['Metallic'].default_value = met
    b.inputs['Roughness'].default_value = rough
    m.use_backface_culling = not ds
    if name == 'PadLightEmissive':
        b.inputs['Base Color'].default_value = (1.0, 0.85, 0.5, 1)
        b.inputs['Emission Color'].default_value = (1.0, 0.8, 0.4, 1)
        b.inputs['Emission Strength'].default_value = 6.0
    else:
        a = nt.nodes.new('ShaderNodeVertexColor')
        a.layer_name = 'Col'
        nt.links.new(a.outputs['Color'], b.inputs['Base Color'])
    _mats[name] = m
    return m


class Part:
    def __init__(self, name, parent, pos, rot_x=0.0):
        self.name = name
        self.parent = parent
        self.pos = V(pos)
        self.rot_x = rot_x          # export-pose rotation about X (applied to the empty only)
        self.chunks = {}            # mat -> dict(v,f,c,s,t)
        self.empty_only = False


class Prop:
    def __init__(self, name):
        self.name = name
        self.parts = {}
        self.order = []
        self.cur = self.part(name, None, (0, 0, 0))

    def part(self, name, parent, pos, rot_x=0.0):
        p = Part(name, parent, pos, rot_x)
        self.parts[name] = p
        self.order.append(name)
        self.cur = p
        return p

    def use(self, name):
        self.cur = self.parts[name]

    def empty(self, name, pos, parent=None):
        cur = self.cur
        p = self.part(name, parent or cur.name, pos)
        p.empty_only = True
        self.cur = cur


P = None            # current prop
PROPS = []


def begin(name):
    global P
    P = Prop(name)
    PROPS.append(P)
    random.seed(hash(name) & 0xffff)
    return P


# ----------------------------------------------------------------------------- emit
def emit(verts, faces, mat, col, smooth=False, tint=0.0, jit=0.06, fcols=None, ftints=None, fix=True):
    if fix and mat != 'Cloth':
        bm = bmesh.new()
        bv = [bm.verts.new(v) for v in verts]
        keep = []
        for i, f in enumerate(faces):
            try:
                bf = bm.faces.new([bv[j] for j in f])
                keep.append((bf, i))
            except ValueError:
                pass
        bm.normal_update()
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
        bm.verts.index_update()
        nf, nfc, nft = [], [], []
        for bf, i in keep:
            nf.append(tuple(v.index for v in bf.verts))
            if fcols: nfc.append(fcols[i])
            if ftints: nft.append(ftints[i])
        faces = nf
        if fcols: fcols = nfc
        if ftints: ftints = nft
        bm.free()
    ch = P.cur.chunks.setdefault(mat, {'v': [], 'f': [], 'c': [], 's': [], 't': []})
    base = len(ch['v'])
    if mat == 'Wood' and jit == 0.06: jit = 0.11
    k = 1.0 + random.uniform(-jit, jit)
    for v in verts:
        ch['v'].append(V(v))
    for i, f in enumerate(faces):
        ch['f'].append(tuple(base + j for j in f))
        c = fcols[i] if fcols else col
        ch['c'].append((c[0] * k, c[1] * k, c[2] * k))
        ch['s'].append(smooth)
        ch['t'].append(ftints[i] if ftints else tint)


def frame(axis, up=None):
    """3x3 matrix whose Z column is axis."""
    z = V(axis).normalized()
    u = V(up) if up else (V((0, 0, 1)) if abs(z.z) < 0.95 else V((0, 1, 0)))
    x = u.cross(z).normalized()
    y = z.cross(x)
    return Matrix((x, y, z)).transposed()


def rot(rx=0, ry=0, rz=0):
    return Euler((math.radians(rx), math.radians(ry), math.radians(rz))).to_matrix()


# ----------------------------------------------------------------------------- primitives
def box(c, s, mat, col, r=None, bevel=0.0, **kw):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co = V((v.co.x * s[0], v.co.y * s[1], v.co.z * s[2]))
    if bevel > 0:
        bmesh.ops.bevel(bm, geom=bm.edges[:], offset=min(bevel, min(s) * 0.3), segments=1, affect='EDGES', profile=0.5)
    bm.verts.index_update()
    M = r if r is not None else Matrix.Identity(3)
    cv = V(c)
    verts = [M @ v.co + cv for v in bm.verts]
    faces = [tuple(v.index for v in f.verts) for f in bm.faces]
    bm.free()
    emit(verts, faces, mat, col, **kw)


def beam(p0, p1, w, h, mat, col, up=None, bevel=0.012, ext=0.0, **kw):
    """Rectangular timber from p0 to p1; w = width (local x), h = height (local 'up')."""
    p0, p1 = V(p0), V(p1)
    d = p1 - p0
    L = d.length
    d.normalize()
    u = V(up) if up else (V((0, 0, 1)) if abs(d.z) < 0.95 else V((0, 1, 0)))
    x = d.cross(u).normalized()
    z = x.cross(d)
    M = Matrix((x, d, z)).transposed()
    box((p0 + p1) / 2, (w, L + 2 * ext, h), mat, col, r=M, bevel=bevel, **kw)


def cyl(p0, p1, r0, mat, col, r1=None, seg=8, caps=True, smooth=True, **kw):
    p0, p1 = V(p0), V(p1)
    if r1 is None: r1 = r0
    M = frame(p1 - p0)
    verts, faces = [], []
    for i in range(seg):
        a = 2 * PI * i / seg
        d = M @ V((math.cos(a), math.sin(a), 0))
        verts.append(p0 + d * r0)
        verts.append(p1 + d * r1)
    for i in range(seg):
        j = (i + 1) % seg
        faces.append((2 * i, 2 * j, 2 * j + 1, 2 * i + 1))
    emit(verts, faces, mat, col, smooth=smooth, **kw)
    if caps:
        cv, cf = [], []
        if r0 > 1e-4:
            b = len(cv)
            cv += [verts[2 * i] for i in range(seg)]
            cf.append(tuple(range(b, b + seg)))
        if r1 > 1e-4:
            b = len(cv)
            cv += [verts[2 * i + 1] for i in range(seg)]
            cf.append(tuple(range(b, b + seg)))
        if cf:
            emit_caps(cv, cf, p0, p1, mat, col, **kw)


def emit_caps(cv, cf, p0, p1, mat, col, **kw):
    # caps are separate shells, so orient them explicitly (recalc can't)
    out = []
    for f in cf:
        c = sum((cv[i] for i in f), V()) / len(f)
        n = (cv[f[1]] - cv[f[0]]).cross(cv[f[2]] - cv[f[0]])
        want = (c - (p0 + p1) / 2)
        out.append(f if n.dot(want) >= 0 else tuple(reversed(f)))
    kw = dict(kw); kw['fix'] = False
    emit(cv, out, mat, col, smooth=False, **kw)


def cone(p0, p1, r0, mat, col, seg=8, **kw):
    cyl(p0, p1, r0, mat, col, r1=0.0005, seg=seg, **kw)


def lathe(profile, mat, col, origin=(0, 0, 0), axis=(0, 0, 1), seg=12, smooth=True, sx=1.0, sy=1.0,
          rfunc=None, closed=False, colf=None, tintf=None, arc=None, **kw):
    """Revolve (r,h) profile around axis. closed=True joins last profile point to first (torus-like)."""
    M = frame(axis)
    o = V(origin)
    n = len(profile)
    a0, a1 = arc if arc else (0.0, 2 * PI)
    full = arc is None
    cols = seg if full else seg + 1
    verts = []
    for i in range(cols):
        a = a0 + (a1 - a0) * i / seg
        for k, (r, h) in enumerate(profile):
            m = rfunc(a, k) if rfunc else 1.0
            verts.append(o + M @ V((math.cos(a) * r * m * sx, math.sin(a) * r * m * sy, h)))
    faces, fc, ft = [], [], []
    for i in range(seg):
        j = (i + 1) % cols if full else i + 1
        for k in range(n if closed else n - 1):
            k2 = (k + 1) % n
            faces.append((i * n + k, j * n + k, j * n + k2, i * n + k2))
            if colf: fc.append(colf(i, k))
            if tintf: ft.append(tintf(i, k))
    emit(verts, faces, mat, col, smooth=smooth, fcols=fc or None, ftints=ft or None, **kw)


def torus(c, axis, R, r, mat, col, seg=12, rseg=6, **kw):
    prof = [(R + r * math.cos(2 * PI * k / rseg), r * math.sin(2 * PI * k / rseg)) for k in range(rseg)]
    lathe(prof, mat, col, origin=c, axis=axis, seg=seg, closed=True, **kw)


def band(c, axis, R, w, mat, col, t=0.015, seg=12, **kw):
    """Flat iron hoop of outer radius R+t, width w centred at c."""
    prof = [(R - 0.01, -w / 2), (R + t, -w / 2), (R + t, w / 2), (R - 0.01, w / 2)]
    lathe(prof, mat, col, origin=c, axis=axis, seg=seg, smooth=False, **kw)


def tube(pts, r, mat, col, seg=5, caps=True, **kw):
    pts = [V(p) for p in pts]
    verts, faces = [], []
    n = len(pts)
    prev_x = None
    for i, p in enumerate(pts):
        d = (pts[min(i + 1, n - 1)] - pts[max(i - 1, 0)]).normalized()
        if prev_x is None:
            M = frame(d)
            x = M.col[0].copy()
        else:
            x = (prev_x - d * prev_x.dot(d)).normalized()
        y = d.cross(x)
        prev_x = x
        for k in range(seg):
            a = 2 * PI * k / seg
            verts.append(p + (x * math.cos(a) + y * math.sin(a)) * r)
    for i in range(n - 1):
        for k in range(seg):
            k2 = (k + 1) % seg
            faces.append((i * seg + k, i * seg + k2, (i + 1) * seg + k2, (i + 1) * seg + k))
    if caps:
        faces.append(tuple(range(seg)))
        faces.append(tuple(range((n - 1) * seg, n * seg)))
    emit(verts, faces, mat, col, smooth=True, **kw)


def rope(p0, p1, r, mat='Rope', col=(0.45, 0.37, 0.24), sag=0.0, n=1, seg=4, **kw):
    p0, p1 = V(p0), V(p1)
    if sag == 0 or n <= 1:
        tube([p0, p1], r, mat, col, seg=seg, **kw)
    else:
        pts = []
        for i in range(n + 1):
            t = i / n
            p = p0.lerp(p1, t)
            p.z -= sag * 4 * t * (1 - t)
            pts.append(p)
        tube(pts, r, mat, col, seg=seg, **kw)


def ico(c, r, mat, col, sub=1, amp=0.0, scale=(1, 1, 1), freq=1.5, smooth=False, seed=None, **kw):
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=sub + 1, radius=1.0)
    off = V((random.uniform(-50, 50), random.uniform(-50, 50), random.uniform(-50, 50))) if seed is None else V((seed, seed * 1.7, seed * 0.3))
    bm.verts.index_update()
    cv = V(c)
    verts = []
    for v in bm.verts:
        d = v.co.normalized()
        m = 1.0 + amp * noise.noise(d * freq + off) * 2.0
        verts.append(cv + V((d.x * scale[0], d.y * scale[1], d.z * scale[2])) * r * m)
    faces = [tuple(v.index for v in f.verts) for f in bm.faces]
    bm.free()
    emit(verts, faces, mat, col, smooth=smooth, **kw)


def grid(fn, nu, nv, mat, col, colf=None, tintf=None, skip=None, smooth=True, flip=False, **kw):
    """fn(u,v)->Vector with u,v in 0..1. Open sheet."""
    verts = [V(fn(i / nu, j / nv)) for i in range(nu + 1) for j in range(nv + 1)]
    faces, fc, ft = [], [], []
    for i in range(nu):
        for j in range(nv):
            if skip and skip(i, j): continue
            a = i * (nv + 1) + j
            faces.append((a + 1, a + nv + 2, a + nv + 1, a) if flip else (a, a + nv + 1, a + nv + 2, a + 1))
            if colf: fc.append(colf(i, j))
            if tintf: ft.append(tintf(i, j))
    emit(verts, faces, mat, col, smooth=smooth, fcols=fc or None, ftints=ft or None, **kw)


def poly(verts, mat, col, **kw):
    kw.setdefault('fix', False)
    emit([V(v) for v in verts], [tuple(range(len(verts)))], mat, col, **kw)


def wheel(c, axis, R, width, mat='Wood', col=(0.28, 0.19, 0.11), spokes=10, tire=True, hub_r=None, rim=None):
    c = V(c)
    M = frame(axis)
    rim = rim or R * 0.14
    hub_r = hub_r or R * 0.17
    lathe([(R - rim, -width / 2), (R, -width / 2), (R, width / 2), (R - rim, width / 2)], mat, col,
          origin=c, axis=axis, seg=max(12, spokes * 2), closed=True, smooth=False)
    if tire:
        band(c, axis, R, width * 1.04, 'Iron', (0.1, 0.1, 0.11), t=0.012, seg=max(12, spokes * 2))
    az = M.col[2]
    cyl(c - az * width * 0.9, c + az * width * 0.9, hub_r, mat, (col[0] * 0.8, col[1] * 0.8, col[2] * 0.8), seg=8)
    band(c - az * width * 0.75, axis, hub_r, 0.03, 'Iron', (0.1, 0.1, 0.11), seg=8)
    band(c + az * width * 0.75, axis, hub_r, 0.03, 'Iron', (0.1, 0.1, 0.11), seg=8)
    for i in range(spokes):
        a = 2 * PI * i / spokes
        d = M @ V((math.cos(a), math.sin(a), 0))
        beam(c + d * hub_r * 0.8, c + d * (R - rim * 0.8), width * 0.4, width * 0.4, mat, col, up=az, bevel=0)


def barrel(c, axis, h, r, col=(0.33, 0.22, 0.12), hoops=True):
    """c = base centre."""
    c = V(c)
    prof = [(r * 0.8, 0), (r * 0.93, h * 0.2), (r, h * 0.5), (r * 0.93, h * 0.8), (r * 0.8, h)]
    mult = [random.uniform(0.8, 1.15) for _ in range(12)]
    lathe(prof, 'Wood', col, origin=c, axis=axis, seg=12, colf=lambda i, k: tuple(x * mult[i] for x in col))
    M = frame(axis)
    az = M.col[2]
    for hh in (0.03, 0.97):
        pts = [c + az * h * hh + M @ V((math.cos(2 * PI * i / 12), math.sin(2 * PI * i / 12), 0)) * r * 0.8 for i in range(12)]
        f = [tuple(range(12))]
        emit_caps(pts, f, c + az * (h * hh + (0.2 if hh > .5 else -0.2)), c + az * h * 0.5, 'Wood', (col[0] * 0.85, col[1] * 0.85, col[2] * 0.85))
    if hoops:
        for hh, rr in ((0.08, 0.86), (0.3, 0.965), (0.7, 0.965), (0.92, 0.86)):
            band(c + az * h * hh, axis, r * rr, h * 0.05, 'Iron', (0.11, 0.1, 0.1), t=0.008)


def crate(c, s, r=None, col=(0.36, 0.26, 0.15), batt=(0.25, 0.17, 0.09), mat='Wood', bw=0.06):
    """Plank crate with corner battens. c = centre."""
    M = r if r is not None else Matrix.Identity(3)
    c = V(c)
    box(c, s, mat, col, r=M, bevel=0.008)
    hx, hy, hz = s[0] / 2, s[1] / 2, s[2] / 2
    t = 0.015
    for sx in (-1, 1):
        for sy in (-1, 1):
            box(c + M @ V((sx * (hx - bw / 2 + t), sy * (hy - bw / 2 + t), 0)), (bw, bw, s[2] + 2 * t), mat, batt, r=M, jit=0.1)
    for sz in (-1, 1):
        for sy in (-1, 1):
            box(c + M @ V((0, sy * (hy + t / 2), sz * (hz - bw / 2))), (s[0] - bw, t, bw), mat, batt, r=M, jit=0.1)
        for sx in (-1, 1):
            box(c + M @ V((sx * (hx + t / 2), 0, sz * (hz - bw / 2))), (t, s[1] - bw, bw), mat, batt, r=M, jit=0.1)


# ----------------------------------------------------------------------------- build Blender objects
_HEMI = []
random.seed(7)
for _i in range(14):
    u, vv = (_i + 0.5) / 14, (_i * 0.618034) % 1.0
    rr = math.sqrt(u)
    _HEMI.append(V((rr * math.cos(2 * PI * vv), rr * math.sin(2 * PI * vv), math.sqrt(1 - u))))


def _ao(prop):
    verts, polys = [], []
    for p in prop.parts.values():
        for ch in p.chunks.values():
            b = len(verts)
            verts += ch['v']
            polys += [tuple(b + i for i in f) for f in ch['f']]
    if not polys:
        return
    bvh = BVHTree.FromPolygons(verts, polys)
    zmin = min(v.z for v in verts)
    is_centered = zmin < -0.05   # props with origin at centre: no ground darkening
    MAXD = 1.0
    for p in prop.parts.values():
        for ch in p.chunks.values():
            vs, fs = ch['v'], ch['f']
            fn = []
            for f in fs:
                n = V()
                for i in range(len(f)):
                    a, b2 = vs[f[i]], vs[f[(i + 1) % len(f)]]
                    n += a.cross(b2)
                fn.append(n.normalized() if n.length > 1e-12 else V((0, 0, 1)))
            vn = {}
            for fi, f in enumerate(fs):
                if ch['s'][fi]:
                    for i in f:
                        vn[i] = vn.get(i, V()) + fn[fi]
            cache = {}
            loops = []
            for fi, f in enumerate(fs):
                lc = []
                for i in f:
                    if ch['s'][fi]:
                        key = i
                        n = vn[i].normalized() if vn[i].length > 1e-9 else fn[fi]
                    else:
                        key = (i, fi)
                        n = fn[fi]
                    if key not in cache:
                        o = vs[i] + n * 0.015
                        # pull the sample point slightly toward face centre to avoid edge self-hits
                        cc = sum((vs[j] for j in f), V()) / len(f)
                        o = o + (cc - vs[i]) * 0.08
                        q = n.to_track_quat('Z', 'Y')
                        occ = 0.0
                        for hdir in _HEMI:
                            d = q @ hdir
                            hit = bvh.ray_cast(o, d, MAXD)
                            if hit[0] is not None:
                                occ += 1.0 - hit[3] / MAXD
                        a = 1.0 - 0.8 * occ / len(_HEMI)
                        if not is_centered:
                            g = max(0.0, min(1.0, vs[i].z / 0.35))
                            a *= 0.72 + 0.28 * g
                        a *= 1.0 + 0.09 * noise.noise(vs[i] * 2.3) + 0.05 * noise.noise(vs[i] * 9.0)
                        cache[key] = a
                    lc.append(cache[key])
                loops.append(lc)
            ch['ao'] = loops


def build(prop):
    _ao(prop)
    objs = {}
    tris = 0
    for name in prop.order:
        p = prop.parts[name]
        e = bpy.data.objects.new(name, None)
        e.empty_display_size = 0.2
        bpy.context.scene.collection.objects.link(e)
        objs[name] = e
        if p.parent:
            e.parent = objs[p.parent]
            e.location = p.pos - prop.parts[p.parent].pos
        else:
            e.location = p.pos
        for mat, ch in p.chunks.items():
            me = bpy.data.meshes.new(f'{name}__{mat}')
            me.from_pydata([v - p.pos for v in ch['v']], [], ch['f'])
            me.polygons.foreach_set('use_smooth', ch['s'])
            ca = me.color_attributes.new('Col', 'FLOAT_COLOR', 'CORNER')
            uv = me.uv_layers.new(name='UVMap')
            li = 0
            for fi, f in enumerate(ch['f']):
                c = ch['c'][fi]
                t = ch['t'][fi]
                for k in range(len(f)):
                    a = ch['ao'][fi][k]
                    ca.data[li].color = (min(1, c[0] * a), min(1, c[1] * a), min(1, c[2] * a), 1.0)
                    uv.data[li].uv = (t, 0.0)
                    li += 1
                tris += len(f) - 2
            me.color_attributes.active_color = ca
            me.color_attributes.render_color_index = 0
            me.materials.append(get_mat(mat))
            me.update()
            o = bpy.data.objects.new(f'{name}__{mat}', me)
            bpy.context.scene.collection.objects.link(o)
            o.parent = e
    # export pose rotations (after parenting so geometry stays in rest frame)
    for name in prop.order:
        p = prop.parts[name]
        if p.rot_x:
            objs[name].rotation_euler = (p.rot_x, 0, 0)
    prop.tris = tris
    prop.root = objs[prop.name]
    return objs
