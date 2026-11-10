# Helper library for procedural modelling (Siege Wing helicopter). Blender 5.x
import bpy, bmesh, math, random
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree

MATS = {}
WORLD = {}      # name -> world matrix
OBJS = {}
TEXTURED = set()   # material names that want box-projected UVs
I4 = Matrix.Identity(4)


def V(*a):
    return Vector(a)


class MB:
    """Mesh builder accumulating world-space geometry."""
    def __init__(s):
        s.v = []; s.vc = []; s.f = []; s.fm = []; s.fuv = []

    def addv(s, p, tint):
        s.v.append(Vector(p)); s.vc.append(tuple(tint)); return len(s.v) - 1

    def addf(s, idx, mat, uv=None):
        s.f.append(tuple(idx)); s.fm.append(mat); s.fuv.append(uv)

    def add_bm(s, bm, M, mat, tint, flip=False):
        if M.determinant() < 0:
            flip = not flip
        base = len(s.v)
        for i, v in enumerate(bm.verts):
            v.index = i
            s.addv(M @ v.co, tint)
        for f in bm.faces:
            idx = [base + v.index for v in f.verts]
            if flip: idx.reverse()
            s.addf(idx, mat)
        bm.free()

    def mirrored(s):
        m = MB()
        m.v = [Vector((-p.x, p.y, p.z)) for p in s.v]
        m.vc = list(s.vc)
        m.f = [tuple(reversed(f)) for f in s.f]
        m.fm = list(s.fm)
        m.fuv = [None if u is None else list(reversed(u)) for u in s.fuv]
        return m

    def merge(s, o):
        b = len(s.v)
        s.v += o.v; s.vc += o.vc
        s.f += [tuple(i + b for i in f) for f in o.f]
        s.fm += o.fm; s.fuv += o.fuv


def rot_to(d):
    """3x3 matrix whose Z axis is d."""
    d = Vector(d).normalized()
    u = d.orthogonal().normalized()
    w = d.cross(u)
    return Matrix((u, w, d)).transposed()


def P_box(mb, c, size, mat, tint, bevel=0.0, rot=None, seg=1):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=Vector(size), verts=bm.verts)
    if bevel > 0:
        bmesh.ops.bevel(bm, geom=bm.edges[:], offset=bevel, segments=seg, affect='EDGES', profile=0.5)
    M = Matrix.Translation(Vector(c))
    if rot is not None:
        M = M @ rot.to_4x4()
    mb.add_bm(bm, M, mat, tint)


def P_revolve(mb, p0, axis, prof, mat, tint, seg=16, cap0=True, cap1=True, flip=False, tints=None):
    """prof: list of (distance along axis, radius). Outward normals when radius profile advances along axis."""
    p0 = Vector(p0); d = Vector(axis).normalized()
    u = d.orthogonal().normalized(); w = d.cross(u)
    rings = []
    for k, (t, r) in enumerate(prof):
        r = max(r, 0.0005)
        tn = tints[k] if tints else tint
        ring = []
        for i in range(seg):
            a = 2 * math.pi * i / seg
            ring.append(mb.addv(p0 + d * t + (u * math.cos(a) + w * math.sin(a)) * r, tn))
        rings.append(ring)
    for k in range(len(rings) - 1):
        A, B = rings[k], rings[k + 1]
        for i in range(seg):
            j = (i + 1) % seg
            f = (A[i], A[j], B[j], B[i])
            mb.addf(f[::-1] if flip else f, mat)
    if cap0 and len(rings) > 1:
        f = tuple(reversed(rings[0]))
        mb.addf(f[::-1] if flip else f, mat)
    if cap1:
        f = tuple(rings[-1])
        mb.addf(f[::-1] if flip else f, mat)


def P_cyl(mb, a, b, r0, mat, tint, r1=None, seg=14, cap0=True, cap1=True):
    a = Vector(a); b = Vector(b)
    L = (b - a).length
    P_revolve(mb, a, b - a, [(0, r0), (L, r0 if r1 is None else r1)], mat, tint, seg, cap0, cap1)


def P_sphere(mb, c, r, mat, tint, seg=16, rings=10, rot=None):
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=seg, v_segments=rings, radius=1.0)
    rv = Vector((r, r, r)) if isinstance(r, (int, float)) else Vector(r)
    M = Matrix.Translation(Vector(c))
    if rot is not None:
        M = M @ rot.to_4x4()
    M = M @ Matrix.Diagonal(rv).to_4x4()
    mb.add_bm(bm, M, mat, tint)


def P_torus(mb, c, axis, R, r, mat, tint, seg=24, rseg=8):
    c = Vector(c); d = Vector(axis).normalized()
    u = d.orthogonal().normalized(); w = d.cross(u)
    rings = []
    for i in range(seg):
        a = 2 * math.pi * i / seg
        e = u * math.cos(a) + w * math.sin(a)
        ring = []
        for k in range(rseg):
            b = 2 * math.pi * k / rseg
            ring.append(mb.addv(c + e * (R + r * math.cos(b)) + d * (r * math.sin(b)), tint))
        rings.append(ring)
    for i in range(seg):
        A, B = rings[i], rings[(i + 1) % seg]
        for k in range(rseg):
            k2 = (k + 1) % rseg
            mb.addf((A[k], A[k2], B[k2], B[k]), mat)


def P_loft(mb, rings, mat, tint, closed=True, cap0=False, cap1=False, ref=None, inward=False,
           matfn=None, uvfn=None, tintfn=None):
    """rings: list of lists of Vector (same count). Normals face away from ref (default centroid)."""
    n = len(rings[0]); m = len(rings)
    if ref is None:
        ref = Vector((0, 0, 0)); cnt = 0
        for r in rings:
            for p in r:
                ref += p; cnt += 1
        ref /= cnt
    ids = []
    for i, r in enumerate(rings):
        ids.append([mb.addv(p, tintfn(i, j) if tintfn else tint) for j, p in enumerate(r)])
    # orientation test: accumulate over all faces
    acc = 0.0
    nj = n if closed else n - 1
    for i in range(0, m - 1, max(1, (m - 1) // 6)):
        for j in range(0, nj, max(1, nj // 8)):
            j2 = (j + 1) % n
            a, b, c = rings[i][j], rings[i + 1][j], rings[i + 1][j2]
            nr = (b - a).cross(c - a)
            acc += nr.dot((a + b + c) / 3 - ref)
    flip = acc < 0
    if inward: flip = not flip
    for i in range(m - 1):
        for j in range(nj):
            j2 = (j + 1) % n
            mt = matfn(i, j) if matfn else mat
            if mt is None: continue
            f = [ids[i][j], ids[i + 1][j], ids[i + 1][j2], ids[i][j2]]
            uv = None
            if uvfn:
                uv = [uvfn(i, j), uvfn(i + 1, j), uvfn(i + 1, j + 1), uvfn(i, j + 1)]
            if flip:
                f.reverse()
                if uv: uv.reverse()
            mb.addf(f, mt, uv)
    for cap, idx in ((cap0, 0), (cap1, m - 1)):
        if cap:
            f = list(ids[idx])
            c = sum(rings[idx], Vector((0, 0, 0))) / n
            nr = Vector((0, 0, 0))
            for j in range(n):
                nr += (rings[idx][j] - c).cross(rings[idx][(j + 1) % n] - c)
            want = (c - ref)
            other = rings[1][0] - rings[0][0] if idx == 0 else rings[m - 2][0] - rings[m - 1][0]
            # cap normal should point away from the neighbouring ring
            if nr.dot(other) > 0: f.reverse()
            if inward: f.reverse()
            mb.addf(f, mat)


def P_sweep(mb, pts, nrm, w, t_out, t_in, mat, tint, closed=False):
    """Rectangular-profile strip following pts with surface normals nrm."""
    n = len(pts)
    rings = []
    for i in range(n):
        if closed:
            t = pts[(i + 1) % n] - pts[i - 1]
        else:
            t = pts[min(i + 1, n - 1)] - pts[max(i - 1, 0)]
        t.normalize()
        nn = Vector(nrm[i]).normalized()
        b = nn.cross(t).normalized()
        p = Vector(pts[i])
        rings.append([p - b * w / 2 + nn * t_out, p + b * w / 2 + nn * t_out,
                      p + b * w / 2 - nn * t_in, p - b * w / 2 - nn * t_in])
    if closed:
        rings.append(rings[0])
    P_loft(mb, rings, mat, tint, closed=True, cap0=not closed, cap1=not closed,
           ref=None)


def airfoil_ring(le, cd, c, th, up, n=7):
    le = Vector(le); cd = Vector(cd).normalized(); up = Vector(up).normalized()
    xs = [0.5 * (1 - math.cos(math.pi * i / (n - 1))) for i in range(n)]
    def yt(x):
        return 5 * th * (0.2969 * math.sqrt(x) - 0.1260 * x - 0.3516 * x * x + 0.2843 * x ** 3 - 0.1036 * x ** 4)
    ring = []
    for x in xs:                       # upper LE->TE
        ring.append(le + cd * (x * c) + up * (yt(x) * c))
    for x in reversed(xs[1:-1]):       # lower TE->LE
        ring.append(le + cd * (x * c) - up * (yt(x) * c))
    return ring


def P_airfoil(mb, secs, mat, tint, cap0=True, cap1=True, n=7, tints=None):
    rings = [airfoil_ring(*s, n=n) for s in secs]
    tf = (lambda i, j: tints[i]) if tints else None
    P_loft(mb, rings, mat, tint, closed=True, cap0=cap0, cap1=cap1, tintfn=tf)


_txt_cache = {}

def P_text(mb, text, size, M, mat, tint):
    """Text in local XY plane (x right, y up, normal +Z), centred, transformed by M."""
    key = (text, round(size, 5))
    if key not in _txt_cache:
        cu = bpy.data.curves.new('t', 'FONT')
        cu.body = text; cu.size = size; cu.align_x = 'CENTER'; cu.align_y = 'CENTER'
        cu.resolution_u = 1
        ob = bpy.data.objects.new('t', cu)
        bpy.context.scene.collection.objects.link(ob)
        dg = bpy.context.evaluated_depsgraph_get()
        me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
        vs = [v.co.copy() for v in me.vertices]
        fs = [tuple(p.vertices) for p in me.polygons]
        bpy.data.objects.remove(ob); bpy.data.curves.remove(cu); bpy.data.meshes.remove(me)
        _txt_cache[key] = (vs, fs)
    vs, fs = _txt_cache[key]
    base = len(mb.v)
    for v in vs:
        mb.addv(M @ v, tint)
    flip = M.determinant() < 0
    for f in fs:
        idx = [base + i for i in f]
        if flip: idx.reverse()
        mb.addf(idx, mat)


def limb(mb, a, b, r0, r1, mat, tint, seg=10):
    P_cyl(mb, a, b, r0, mat, tint, r1=r1, seg=seg, cap0=False, cap1=False)
    P_sphere(mb, a, r0, mat, tint, seg=seg, rings=6)
    P_sphere(mb, b, r1, mat, tint, seg=seg, rings=6)


def build(mb, name, origin=(0, 0, 0), rot=None, parent=None, smooth_angle=38, uvscale=0.5):
    Mw = Matrix.Translation(Vector(origin))
    if rot is not None:
        Mw = Mw @ rot.to_4x4()
    Mi = Mw.inverted()
    me = bpy.data.meshes.new(name)
    me.from_pydata([Mi @ v for v in mb.v], [], mb.f)
    used = []
    for m in mb.fm:
        if m not in used: used.append(m)
    for m in used:
        me.materials.append(MATS[m])
    uvl = me.uv_layers.new(name='UVMap')
    col = me.color_attributes.new('Col', 'FLOAT_COLOR', 'CORNER')
    for pi, poly in enumerate(me.polygons):
        poly.material_index = used.index(mb.fm[pi])
        poly.use_smooth = True
        fuv = mb.fuv[pi]
        if fuv is None:
            # box projection in world space
            pts = [mb.v[i] for i in mb.f[pi]]
            nr = Vector((0, 0, 0))
            for k in range(len(pts)):
                nr += (pts[k] - pts[0]).cross(pts[(k + 1) % len(pts)] - pts[0])
            ax = max(range(3), key=lambda k: abs(nr[k]))
            fuv = []
            for p in pts:
                if ax == 0: fuv.append((p.y * uvscale, p.z * uvscale))
                elif ax == 1: fuv.append((p.x * uvscale, p.z * uvscale))
                else: fuv.append((p.x * uvscale, p.y * uvscale))
        for k, li in enumerate(poly.loop_indices):
            uvl.data[li].uv = fuv[k]
            c = mb.vc[mb.f[pi][k]]
            col.data[li].color = (c[0], c[1], c[2], 1.0)
    me.color_attributes.active_color = col
    me.color_attributes.render_color_index = 0
    bm = bmesh.new(); bm.from_mesh(me)
    lim = math.radians(smooth_angle)
    for e in bm.edges:
        if len(e.link_faces) == 2:
            if e.calc_face_angle(0) > lim:
                e.smooth = False
    bm.to_mesh(me); bm.free()
    me.update()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    _place(ob, name, Mw, parent)
    return ob


def empty(name, pos, parent=None, rot=None, size=0.1):
    ob = bpy.data.objects.new(name, None)
    ob.empty_display_size = size
    bpy.context.scene.collection.objects.link(ob)
    Mw = Matrix.Translation(Vector(pos))
    if rot is not None:
        Mw = Mw @ rot.to_4x4()
    _place(ob, name, Mw, parent)
    return ob


def _place(ob, name, Mw, parent):
    WORLD[name] = Mw; OBJS[name] = ob
    if parent:
        ob.parent = OBJS[parent]
        ob.matrix_parent_inverse = I4
        ob.matrix_basis = WORLD[parent].inverted() @ Mw
    else:
        ob.matrix_basis = Mw


def bake_ao(skip_mats=('Glass',), samples=20, maxd=1.3, strength=0.85, floor=0.22):
    """Per-vertex raycast AO multiplied into the 'Col' attribute of all meshes."""
    verts = []; polys = []
    for name, ob in OBJS.items():
        if ob.type != 'MESH': continue
        me = ob.data; Mw = WORLD[name]
        base = len(verts)
        verts += [Mw @ v.co for v in me.vertices]
        for p in me.polygons:
            if me.materials[p.material_index].name in skip_mats: continue
            polys.append([base + i for i in p.vertices])
    bvh = BVHTree.FromPolygons(verts, polys, all_triangles=False)
    rnd = random.Random(7)
    dirs = []
    for k in range(samples):
        u1 = (k + 0.5) / samples; u2 = rnd.random()
        r = math.sqrt(u1); a = 2 * math.pi * (u2 + k * 0.618)
        dirs.append((r * math.cos(a), r * math.sin(a), math.sqrt(1 - u1)))
    for name, ob in OBJS.items():
        if ob.type != 'MESH': continue
        me = ob.data; Mw = WORLD[name]; R = Mw.to_3x3()
        ao = []
        for v in me.vertices:
            n = (R @ v.normal).normalized()
            p = Mw @ v.co + n * 0.012
            t = n.orthogonal().normalized(); b = n.cross(t)
            occ = 0.0
            for d in dirs:
                dv = t * d[0] + b * d[1] + n * d[2]
                hit = bvh.ray_cast(p, dv, maxd)
                if hit[0] is not None:
                    occ += 1.0 - (hit[3] / maxd) ** 0.7
            a = 1.0 - strength * occ / samples
            ao.append(max(floor, a))
        col = me.color_attributes['Col']
        for l in me.loops:
            c = col.data[l.index].color
            a = ao[l.vertex_index]
            col.data[l.index].color = (c[0] * a, c[1] * a, c[2] * a, 1.0)


def dquad(mb, pts, mat, tint):
    """Double-sided polygon with separate vertices per side."""
    a = [mb.addv(p, tint) for p in pts]; mb.addf(a, mat)
    b = [mb.addv(p, tint) for p in pts]; mb.addf(b[::-1], mat)
