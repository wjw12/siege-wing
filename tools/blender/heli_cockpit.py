# Siege Wing helicopter — cockpit interior. exec'd by heli.py into its namespace (shares constants, heli_lib, mk_mat, OBJS...).
# cockpit_mats() is called from main() before geometry is built: declare cockpit-only materials there.
#
# Structure of this file
#   1. textures / materials / decal atlas (CkDecal: every flat panel face is painted into one 2048 atlas:
#      base colour + dim emissive legends + normal map, by the Plate class while the geometry is built)
#   2. primitives (frames, worn boxes, tubes, prisms) and panel widgets (toggles, knobs, keys, breakers, dials)
#   3. cockpit parts (main panel, coaming, consoles, walls, floor, seat, controls, crew, gunner station)
#   4. build_cockpit(): assembles + builds the named nodes the game animates
from math import floor, ceil, atan2, degrees, sqrt

CK = {}
ATLAS = 2048

# sRGB colours painted into the atlas
C_PLATE = (0.225, 0.23, 0.238)
C_PLATE2 = (0.17, 0.174, 0.18)
C_BLK = (0.07, 0.072, 0.075)
C_LEG = (0.84, 0.85, 0.82)
C_DIM = (0.55, 0.56, 0.55)
C_WEAR = (0.43, 0.44, 0.45)
C_YEL = (0.86, 0.66, 0.08)
C_RED = (0.72, 0.09, 0.06)
C_GRN = (0.25, 0.85, 0.35)
C_AMB = (1.0, 0.62, 0.12)
C_KEY = (0.50, 0.51, 0.50)
C_KEYD = (0.13, 0.133, 0.14)
C_FACE = (0.035, 0.035, 0.038)
# linear vertex tints
T_CKB = (0.034, 0.036, 0.039)
T_CKC = (0.043, 0.045, 0.049)
T_CKD = (0.02, 0.021, 0.023)
T_BEZ = (0.011, 0.011, 0.013)
T_KNOB = (0.014, 0.014, 0.016)
T_SIDE = (0.018, 0.018, 0.02)
T_KEYL = (0.2, 0.2, 0.205)
T_GLOVE = (0.035, 0.036, 0.03)
T_BOOT = (0.012, 0.011, 0.01)
T_STRAP = (0.03, 0.032, 0.028)
T_WALL = (0.05, 0.053, 0.05)


# ------------------------------------------------------------------ textures
def ck_vnoise(S, f, rng):
    g = rng.random((f, f))
    t = np.arange(S) / S * f
    i0 = np.floor(t).astype(int); tt = t - i0; tt = tt * tt * (3 - 2 * tt); i1 = (i0 + 1) % f
    a = g[i0][:, i0]; b = g[i0][:, i1]; c = g[i1][:, i0]; d = g[i1][:, i1]
    tx = tt[None, :]; ty = tt[:, None]
    return (a * (1 - tx) + b * tx) * (1 - ty) + (c * (1 - tx) + d * tx) * ty


def ck_fbm(S, f, octs, rng):
    out = np.zeros((S, S)); amp = 1.0; tot = 0
    for o in range(octs):
        out += amp * ck_vnoise(S, min(S, f * 2 ** o), rng); tot += amp; amp *= 0.5
    return out / tot


def ck_blur(a, n=1):
    for _ in range(n):
        a = (a + np.roll(a, 1, 0) + np.roll(a, -1, 0) + np.roll(a, 1, 1) + np.roll(a, -1, 1)) / 5.0
    return a


def ck_normal(Hh, k):
    dx = (np.roll(Hh, -1, 1) - np.roll(Hh, 1, 1)) * k
    dy = (np.roll(Hh, -1, 0) - np.roll(Hh, 1, 0)) * k
    l = np.sqrt(dx * dx + dy * dy + 1)
    return np.stack([-dx / l * 0.5 + 0.5, -dy / l * 0.5 + 0.5, 1 / l * 0.5 + 0.5], -1)


def ck_fill(img, arr, fname):
    H, W = arr.shape[:2]
    rgba = np.ones((H, W, 4), dtype=np.float32)
    rgba[..., :3] = np.clip(arr, 0, 1)
    img.pixels.foreach_set(rgba.ravel())
    img.filepath_raw = os.path.join(TEXD, fname); img.file_format = 'PNG'
    img.save()


def ck_img(name, arr, noncolor=False):
    img = bpy.data.images.new(name, arr.shape[1], arr.shape[0], alpha=False)
    if noncolor: img.colorspace_settings.name = 'Non-Color'
    ck_fill(img, arr, name + '.png')
    return img


def cockpit_mats():
    S = 512
    rng = np.random.default_rng(23)
    # powder-coat: near-white albedo (tinted by vertex colour) with mottling, speckle, dust; orange-peel normal
    mott = ck_fbm(S, 4, 4, rng)
    grain = rng.random((S, S))
    dust = ck_blur((rng.random((S, S)) > 0.9965).astype(float), 1) * 5
    scuff = np.clip(ck_fbm(S, 8, 3, rng) - 0.62, 0, 1) * 2.2 * (ck_vnoise(S, 128, rng) > 0.45)
    a = 0.82 + 0.12 * mott + 0.03 * (grain - 0.5) + np.clip(dust, 0, 1) * 0.12 + scuff * 0.08
    coat = np.stack([a, a, a * 1.02], -1)
    coat_n = ck_normal(ck_blur(grain, 2) * 1.0 + ck_vnoise(S, 128, rng) * 0.3, 0.55)
    ic = ck_img('ck_coat_col', coat); icn = ck_img('ck_coat_nrm', coat_n, True)
    # fabric weave
    n = 128
    x = np.arange(S)[None, :] / S * n; y = np.arange(S)[:, None] / S * n
    chk = ((np.floor(x) + np.floor(y)) % 2)
    hw = np.abs(np.sin(pi * x)) * chk + np.abs(np.sin(pi * y)) * (1 - chk)
    fa = 0.72 + 0.22 * hw + 0.08 * (ck_fbm(S, 8, 3, rng) - 0.5) + 0.05 * (rng.random((S, S)) - 0.5)
    fab = np.stack([fa, fa, fa], -1)
    fab_n = ck_normal(hw + 0.15 * rng.random((S, S)), 0.9)
    ifa = ck_img('ck_fabric_col', fab); ifn = ck_img('ck_fabric_nrm', fab_n, True)
    # hazard stripes
    Sh = 128
    xx = np.arange(Sh)[None, :]; yy = np.arange(Sh)[:, None]
    t = ((xx + yy) / Sh * 8) % 1.0
    m = np.clip((0.25 - np.abs(t - 0.5)) * Sh / 8 + 0.5, 0, 1)[..., None]
    haz = np.array(C_YEL) * m + np.array((0.06, 0.06, 0.06)) * (1 - m)
    ih = ck_img('ck_hazard', haz)

    mk_mat('CkCoat', rough=0.6, tex=ic, nrm=icn)
    mk_mat('CkFabric', rough=0.95, tex=ifa, nrm=ifn)
    mk_mat('CkHazard', rough=0.6, tex=ih)
    mk_mat('CkSatin', rough=0.5)
    mk_mat('CkRubber', rough=0.88)
    mk_mat('CkGlass', base=(0.02, 0.03, 0.03), rough=0.03, alpha=0.14)
    mk_mat('CkLitG', base=(0.02, 0.1, 0.04), rough=0.3, emit=(0.15, 1.0, 0.3), emit_s=1.0)
    mk_mat('CkLitA', base=(0.12, 0.07, 0.01), rough=0.3, emit=(1.0, 0.55, 0.08), emit_s=1.0)
    mk_mat('MFD_C', base=(0.01, 0.03, 0.02), rough=0.2, emit=(0.02, 0.12, 0.05), emit_s=1.0)
    for nm, colr in (('Warn_Fire', (0.9, 0.05, 0.03)), ('Warn_Weapons', (0.9, 0.45, 0.03)), ('Warn_Canopy', (0.9, 0.45, 0.03))):
        mk_mat(nm, base=tuple(c * 0.25 for c in colr), rough=0.3, emit=colr, emit_s=0.15)

    # decal atlas (filled while the geometry is built, written by ck_atlas_finish())
    A = ATLAS
    CK['col'] = np.empty((A, A, 3), np.float32); CK['col'][:] = C_PLATE
    CK['emi'] = np.zeros((A, A, 3), np.float32)
    CK['hgt'] = np.zeros((A, A), np.float32)
    CK['sky'] = np.zeros(A, np.int32)
    r2 = np.random.default_rng(5)
    CK['noise'] = ck_fbm(A, 16, 5, r2).astype(np.float32)
    CK['noise2'] = ck_vnoise(A, 512, r2).astype(np.float32)
    CK['im_col'] = bpy.data.images.new('ck_atlas_col', A, A, alpha=False)
    CK['im_emi'] = bpy.data.images.new('ck_atlas_emi', A, A, alpha=False)
    CK['im_nrm'] = bpy.data.images.new('ck_atlas_nrm', A, A, alpha=False)
    CK['im_nrm'].colorspace_settings.name = 'Non-Color'
    m = mk_mat('CkDecal', rough=0.55, tex=CK['im_col'], nrm=CK['im_nrm'])
    nt = m.node_tree; b = nt.nodes['Principled BSDF']
    t = nt.nodes.new('ShaderNodeTexImage'); t.image = CK['im_emi']
    nt.links.new(t.outputs['Color'], b.inputs['Emission Color'])
    b.inputs['Emission Strength'].default_value = 1.0


def ck_atlas_finish():
    ck_fill(CK['im_col'], CK['col'], 'ck_atlas_col.png')
    ck_fill(CK['im_emi'], CK['emi'], 'ck_atlas_emi.png')
    ck_fill(CK['im_nrm'], ck_normal(CK['hgt'], 1.4), 'ck_atlas_nrm.png')
    print('ck atlas used rows', int(CK['sky'].max()), 'of', ATLAS)


def ck_alloc(pw, ph, pad=3):
    """skyline packer; returns (x0, y0) of a pw x ph pixel rect."""
    sky = CK['sky']; A = ATLAS
    W = pw + 2 * pad; best = None
    for x in range(0, A - W, 8):
        top = int(sky[x:x + W].max())
        if best is None or top < best[1]: best = (x, top)
    if best is None or best[1] + ph + 2 * pad > A:
        print('CK ATLAS OVERFLOW', pw, ph); CK['overflow'] = True
        return 4, 4
    x, top = best
    sky[x:x + W] = top + ph + 2 * pad
    return x + pad, top + pad


# ------------------------------------------------------------------ text rasteriser (font outlines -> coverage masks)
_GL = {}; _TM = {}

def _font_mesh(body):
    cu = bpy.data.curves.new('g', 'FONT'); cu.body = body; cu.size = 1.0
    cu.align_x = 'LEFT'; cu.align_y = 'BOTTOM_BASELINE'; cu.resolution_u = 3
    ob = bpy.data.objects.new('g', cu); bpy.context.scene.collection.objects.link(ob)
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
    me.calc_loop_triangles()
    vs = np.array([(v.co.x, v.co.y) for v in me.vertices], np.float32).reshape(-1, 2)
    ts = np.array([tuple(t.vertices) for t in me.loop_triangles], np.int32).reshape(-1, 3)
    bpy.data.objects.remove(ob); bpy.data.curves.remove(cu); bpy.data.meshes.remove(me)
    return vs, ts


def _glyph(ch):
    if ch not in _GL:
        if 'HH' not in _GL:
            v, _t = _font_mesh('HH'); _GL['HH'] = float(v[:, 0].max() - v[:, 0].min())
        if ch == ' ':
            _GL[ch] = (np.zeros((0, 2), np.float32), np.zeros((0, 3), np.int32), 0.3)
        else:
            v3, _t = _font_mesh('H' + ch + 'H')
            adv = float(v3[:, 0].max() - v3[:, 0].min()) - _GL['HH']
            vs, ts = _font_mesh(ch)
            _GL[ch] = (vs, ts, adv)
    return _GL[ch]


def ck_text_mask(txt, px):
    """coverage mask of txt at em size px (pixels); the text centre (cap-height middle) is the array centre."""
    key = (txt, int(round(px * 4)))
    if key in _TM: return _TM[key]
    SS = 3; sc = px * SS
    pen = 0.0; items = []
    for ch in txt:
        vs, ts, adv = _glyph(ch); items.append((pen, vs, ts)); pen += adv * 1.04
    Wp = (int(ceil(pen * sc)) + 6) // SS * SS + SS
    Hh = int(ceil(0.78 * sc)) + 3
    Hp = (2 * Hh) // SS * SS + SS
    by = Hp / 2.0 - 0.36 * sc; bx = (Wp - pen * sc) / 2.0
    m = np.zeros((Hp, Wp), bool)
    for pen_, vs, ts in items:
        if len(ts) == 0: continue
        P = vs * sc + np.array((pen_ * sc + bx, by), np.float32)
        x0 = max(0, int(floor(P[:, 0].min()))); x1 = min(Wp, int(ceil(P[:, 0].max())) + 1)
        y0 = max(0, int(floor(P[:, 1].min()))); y1 = min(Hp, int(ceil(P[:, 1].max())) + 1)
        if x1 <= x0 or y1 <= y0: continue
        gx = (np.arange(x0, x1) + 0.5)[None, :, None]; gy = (np.arange(y0, y1) + 0.5)[:, None, None]
        a = P[ts[:, 0]]; b = P[ts[:, 1]]; c = P[ts[:, 2]]
        def edge(p, q):
            return (q[:, 0] - p[:, 0])[None, None, :] * (gy - p[:, 1][None, None, :]) - (q[:, 1] - p[:, 1])[None, None, :] * (gx - p[:, 0][None, None, :])
        e0 = edge(a, b); e1 = edge(b, c); e2 = edge(c, a)
        ins = ((e0 >= 0) & (e1 >= 0) & (e2 >= 0)) | ((e0 <= 0) & (e1 <= 0) & (e2 <= 0))
        m[y0:y1, x0:x1] |= ins.any(-1)
    Hd = Hp // SS; Wd = Wp // SS
    out = m.reshape(Hd, SS, Wd, SS).mean((1, 3)).astype(np.float32)
    _TM[key] = (out, pen * px)
    return _TM[key]


# ------------------------------------------------------------------ primitives
def Rtilt(a):
    """panel frame tilted back by a (0 = vertical facing -Y, 90deg = horizontal facing up, text reads from the tail)."""
    return Matrix(((1, 0, 0), (0, cos(a), sin(a)), (0, -sin(a), cos(a))))


def Raxes(right, up):
    right = Vector(right).normalized(); up = Vector(up).normalized()
    return Matrix((right, up.cross(right), up)).transposed()


class Fr:
    """panel frame: pt(u, v, d) = origin + right*u + up*v + normal*d."""
    def __init__(s, P, R):
        s.P = Vector(P); s.R = R.copy()
        s.n = R @ V(0, -1, 0); s.ex = R @ V(1, 0, 0); s.ey = R @ V(0, 0, 1)

    def pt(s, u, v, d=0.0):
        return s.P + s.R @ V(u, -d, v)

    def sub(s, u=0.0, v=0.0, d=0.0, yaw=0.0, tilt=0.0, roll=0.0):
        R = s.R
        if yaw: R = R @ Matrix.Rotation(-yaw, 3, 'Z')
        if tilt: R = R @ Matrix.Rotation(-tilt, 3, 'X')
        if roll: R = R @ Matrix.Rotation(roll, 3, 'Y')
        return Fr(s.pt(u, v, d), R)

    def box(s, mb, u, v, d, su, sv, sd, mat, tint, bevel=0.0, ang=0.0, wear=0.0):
        Rr = s.R @ Matrix.Rotation(ang, 3, 'Y') if ang else s.R
        if wear: wbox(mb, s.pt(u, v, d), (su, sd, sv), mat, tint, bevel or 0.002, rot=Rr, wear=wear)
        else: P_box(mb, s.pt(u, v, d), (su, sd, sv), mat, tint, bevel, rot=Rr)

    def rev(s, mb, u, v, d, prof, mat, tint, seg=12, **k):
        P_revolve(mb, s.pt(u, v, d), s.n, prof, mat, tint, seg=seg, **k)

    def text(s, mb, txt, size, u, v, d, mat='GaugeMark', tint=T_W):
        M = Matrix.Translation(s.pt(u, v, d)) @ (s.R @ Matrix(((1, 0, 0), (0, 0, -1), (0, 1, 0)))).to_4x4()
        P_text(mb, txt, size, M, mat, tint)


def ck_worn(t, k=1.0):
    return tuple(min(1.0, c + k * (c * 1.6 + 0.04)) for c in t)


def wbox(mb, c, size, mat, tint, bevel=0.003, rot=None, wear=1.0, inset=0.0035):
    """bevelled box whose flat faces are inset so the edges can carry a lighter 'worn' vertex colour."""
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=Vector(size), verts=bm.verts)
    bevel = min(bevel, min(size) * 0.3)
    bmesh.ops.bevel(bm, geom=bm.edges[:], offset=bevel, segments=1, affect='EDGES', profile=0.5)
    bm.faces.ensure_lookup_table()
    big = []
    for f in bm.faces:
        n = f.normal
        if max(abs(n.x), abs(n.y), abs(n.z)) > 0.999 and len(f.verts) == 4:
            ed = [e.calc_length() for e in f.edges]
            if min(ed) > inset * 3.2: big.append(f)
    if big:
        bmesh.ops.inset_individual(bm, faces=big, thickness=inset, depth=0.0)
    inner = set()
    for f in big:
        for v in f.verts: inner.add(v)
    M = Matrix.Translation(Vector(c))
    if rot is not None: M = M @ rot.to_4x4()
    tw = ck_worn(tint, wear)
    base = len(mb.v)
    for i, v in enumerate(bm.verts):
        v.index = i
        mb.addv(M @ v.co, tint if v in inner else tw)
    for f in bm.faces:
        mb.addf([base + v.index for v in f.verts], mat)
    bm.free()


def oquad(mb, pts, hint, mat, tint, uv=None):
    n = (pts[1] - pts[0]).cross(pts[2] - pts[0])
    ids = [mb.addv(p, tint) for p in pts]
    if n.dot(hint) < 0:
        ids.reverse()
        if uv: uv = list(reversed(uv))
    mb.addf(ids, mat, uv)


def CK_tube(mb, pts, r, mat, tint, seg=8, cap=True, tints=None, flat=None):
    """round tube along a polyline; r scalar or per-point list. flat=(dir, k) squashes the section along dir."""
    pts = [Vector(p) for p in pts]; n = len(pts)
    rr = list(r) if isinstance(r, (list, tuple)) else [r] * n
    u = None; rings = []
    for i in range(n):
        t = (pts[min(i + 1, n - 1)] - pts[max(i - 1, 0)]).normalized()
        if u is None: u = t.orthogonal().normalized()
        u = (u - t * u.dot(t)).normalized(); w = t.cross(u)
        ring = []
        for k in range(seg):
            a = 2 * pi * k / seg
            o = (u * cos(a) + w * sin(a)) * rr[i]
            if flat is not None:
                fd = Vector(flat[0]).normalized(); o = o - fd * o.dot(fd) * (1 - flat[1])
            ring.append(mb.addv(pts[i] + o, tints[i] if tints else tint))
        rings.append(ring)
    for i in range(n - 1):
        A, B = rings[i], rings[i + 1]
        for k in range(seg):
            j = (k + 1) % seg
            mb.addf((A[k], A[j], B[j], B[k]), mat)
    if cap:
        mb.addf(tuple(reversed(rings[0])), mat); mb.addf(tuple(rings[-1]), mat)


def ck_arc(a, b, c, n=5):
    """quadratic bezier a -> c with control b."""
    a = Vector(a); b = Vector(b); c = Vector(c)
    return [a * (1 - t) ** 2 + b * 2 * t * (1 - t) + c * t * t for t in [k / n for k in range(n + 1)]]


def ck_path(pts, n=4, rnd=0.35):
    """polyline with rounded corners."""
    pts = [Vector(p) for p in pts]; out = [pts[0]]
    for i in range(1, len(pts) - 1):
        a = pts[i] + (pts[i - 1] - pts[i]) * rnd; c = pts[i] + (pts[i + 1] - pts[i]) * rnd
        out += ck_arc(a, pts[i], c, n)
    out.append(pts[-1])
    return out


def prism(mb, poly, x0, x1, mat, tint, wear=0.0):
    """extrude a convex polygon given in (y, z) between x0 and x1. With wear, edges get a lighter rim (inset faces)."""
    bm = bmesh.new()
    a = [bm.verts.new((x0, y, z)) for y, z in poly]; b = [bm.verts.new((x1, y, z)) for y, z in poly]
    n = len(poly)
    bm.faces.new(a); bm.faces.new(list(reversed(b)))
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new((a[j], a[i], b[i], b[j]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    inner = set()
    if wear:
        bmesh.ops.bevel(bm, geom=bm.edges[:], offset=0.0025, segments=1, affect='EDGES', profile=0.5)
        big = [f for f in bm.faces if f.calc_area() > 0.0008]
        bmesh.ops.inset_individual(bm, faces=big, thickness=0.004, depth=0.0)
        for f in big:
            for v in f.verts: inner.add(v)
    tw = ck_worn(tint, wear) if wear else tint
    base = len(mb.v)
    for i, v in enumerate(bm.verts):
        v.index = i; mb.addv(v.co.copy(), tint if (v in inner or not wear) else tw)
    for f in bm.faces:
        mb.addf([base + v.index for v in f.verts], mat)
    bm.free()


def ck_hw(y, z, inset=0.042):
    """inner half-width of the tub/canopy at station y, height z."""
    lo, hi = 0.0, pi
    for _ in range(22):
        m = (lo + hi) / 2
        if spi(y, m, inset).z > z: lo = m
        else: hi = m
    return spi(y, lo, inset).x


# ------------------------------------------------------------------ decal plate + widgets
class Plate:
    """flat panel face painted into the decal atlas. Coordinates (u, v) in metres from the plate centre."""
    def __init__(s, mb, F, w, h, ppm=1600, col=C_PLATE, thick=0.003, hole=None, hole_d=0.006, cell=0.04,
                 share=None, side=T_SIDE, geo=True, edge=True, title=None):
        s.mb = mb; s.F = F; s.w = w; s.h = h; s.col = col
        if share is not None:
            s.ppm = share.ppm; s.x0, s.y0, s.pw, s.ph = share.x0, share.y0, share.pw, share.ph; s.ro = True
        else:
            s.ppm = ppm; s.pw = int(ceil(w * ppm)); s.ph = int(ceil(h * ppm)); s.ro = False
            s.x0, s.y0 = ck_alloc(s.pw, s.ph)
            if CK.get('overflow'): s.pw = s.ph = 8; s.ro = True
            pad = 3
            sl = (slice(s.y0 - pad, s.y0 + s.ph + pad), slice(s.x0 - pad, s.x0 + s.pw + pad))
            CK['col'][sl] = np.array(col, np.float32) * (0.88 + 0.24 * CK['noise'][sl][..., None])
            CK['emi'][sl] = 0; CK['hgt'][sl] = 0
            if edge:
                s.rect(0, 0, w - 0.0006, h - 0.0006, C_WEAR, r=0.0012, line=0.0012, hgt=-0.7, nz=0.42)
        if geo: s._geo(thick, hole, hole_d, cell, side)
        if title: s.text(title, 0, h / 2 - 0.0085, 0.0062)

    def uv(s, u, v):
        return ((s.x0 + (u + s.w / 2) * s.ppm) / ATLAS, (s.y0 + (v + s.h / 2) * s.ppm) / ATLAS)

    def _geo(s, thick, hole, hole_d, cell, side):
        mb = s.mb; F = s.F; w = s.w; h = s.h
        us = set(round(x, 6) for x in np.linspace(-w / 2, w / 2, max(1, int(round(w / cell))) + 1))
        vs = set(round(x, 6) for x in np.linspace(-h / 2, h / 2, max(1, int(round(h / cell))) + 1))
        if hole: us |= {hole[0], hole[2]}; vs |= {hole[1], hole[3]}
        us = sorted(us); vs = sorted(vs); ids = {}
        def vid(i, j):
            if (i, j) not in ids: ids[(i, j)] = mb.addv(F.pt(us[i], vs[j], 0), T_W)
            return ids[(i, j)]
        for i in range(len(us) - 1):
            for j in range(len(vs) - 1):
                cu = (us[i] + us[i + 1]) / 2; cv = (vs[j] + vs[j + 1]) / 2
                if hole and hole[0] < cu < hole[2] and hole[1] < cv < hole[3]: continue
                mb.addf([vid(i, j), vid(i + 1, j), vid(i + 1, j + 1), vid(i, j + 1)], 'CkDecal',
                        [s.uv(us[i], vs[j]), s.uv(us[i + 1], vs[j]), s.uv(us[i + 1], vs[j + 1]), s.uv(us[i], vs[j + 1])])
        if thick:
            a, b = w / 2, h / 2
            for (p, q, hint) in (((-a, -b), (a, -b), -F.ey), ((a, -b), (a, b), F.ex), ((a, b), (-a, b), F.ey), ((-a, b), (-a, -b), -F.ex)):
                oquad(mb, [F.pt(p[0], p[1], 0), F.pt(q[0], q[1], 0), F.pt(q[0], q[1], -thick), F.pt(p[0], p[1], -thick)], hint, 'CkSatin', side)
        if hole:
            a0, b0, a1, b1 = hole
            for (p, q, hint) in (((a0, b0), (a1, b0), F.ey), ((a1, b0), (a1, b1), -F.ex), ((a1, b1), (a0, b1), -F.ey), ((a0, b1), (a0, b0), F.ex)):
                oquad(mb, [F.pt(p[0], p[1], 0), F.pt(q[0], q[1], 0), F.pt(q[0], q[1], -hole_d), F.pt(p[0], p[1], -hole_d)], hint, 'CkSatin', T_BEZ)

    # ---- painting
    def _px(s, u0, v0, u1, v1):
        a = max(0, int(floor((u0 + s.w / 2) * s.ppm)) - 1); b = min(s.pw, int(ceil((u1 + s.w / 2) * s.ppm)) + 1)
        c = max(0, int(floor((v0 + s.h / 2) * s.ppm)) - 1); d = min(s.ph, int(ceil((v1 + s.h / 2) * s.ppm)) + 1)
        if a >= b or c >= d: return None
        xs = ((np.arange(a, b) + 0.5) / s.ppm - s.w / 2)[None, :]; ys = ((np.arange(c, d) + 0.5) / s.ppm - s.h / 2)[:, None]
        return (slice(s.y0 + c, s.y0 + d), slice(s.x0 + a, s.x0 + b)), xs, ys

    def _put(s, sl, a, col, emi=0.0, hgt=0.0, nz=None):
        a = a.astype(np.float32)
        if nz is not None: a = a * np.clip((CK['noise'][sl] - nz) * 6, 0.12, 1)
        a3 = a[..., None]; c = np.array(col, np.float32)
        CK['col'][sl] = CK['col'][sl] * (1 - a3) + c * a3
        CK['emi'][sl] = CK['emi'][sl] * (1 - a3) + c * (emi * a3)
        if hgt: CK['hgt'][sl] += a * hgt

    def _aa(s, d):
        return np.clip(0.5 - d * s.ppm, 0, 1)

    def rect(s, u, v, w, h, col, r=0.0, emi=0.0, hgt=0.0, line=0.0, alpha=1.0, nz=None):
        if s.ro: return
        g = s._px(u - w / 2 - 0.002, v - h / 2 - 0.002, u + w / 2 + 0.002, v + h / 2 + 0.002)
        if not g: return
        sl, xs, ys = g
        qx = np.abs(xs - u) - (w / 2 - r); qy = np.abs(ys - v) - (h / 2 - r)
        d = np.sqrt(np.maximum(qx, 0) ** 2 + np.maximum(qy, 0) ** 2) + np.minimum(np.maximum(qx, qy), 0) - r
        if line: d = np.abs(d) - line / 2
        s._put(sl, s._aa(d) * alpha, col, emi, hgt, nz)

    def disc(s, u, v, r, col, emi=0.0, hgt=0.0, line=0.0, alpha=1.0):
        if s.ro: return
        g = s._px(u - r - 0.002, v - r - 0.002, u + r + 0.002, v + r + 0.002)
        if not g: return
        sl, xs, ys = g
        d = np.sqrt((xs - u) ** 2 + (ys - v) ** 2) - r
        if line: d = np.abs(d) - line / 2
        s._put(sl, s._aa(d) * alpha, col, emi, hgt)

    def line(s, u0, v0, u1, v1, wd, col, emi=0.0, hgt=0.0):
        if s.ro: return
        g = s._px(min(u0, u1) - wd - 0.001, min(v0, v1) - wd - 0.001, max(u0, u1) + wd + 0.001, max(v0, v1) + wd + 0.001)
        if not g: return
        sl, xs, ys = g
        dx, dy = u1 - u0, v1 - v0; L2 = dx * dx + dy * dy + 1e-12
        t = np.clip(((xs - u0) * dx + (ys - v0) * dy) / L2, 0, 1)
        d = np.sqrt((xs - u0 - t * dx) ** 2 + (ys - v0 - t * dy) ** 2) - wd / 2
        s._put(sl, s._aa(d), col, emi, hgt)

    def arc(s, u, v, r, a0, a1, wd, col, emi=0.0):
        """angles in degrees clockwise from up."""
        if s.ro: return
        g = s._px(u - r - wd, v - r - wd, u + r + wd, v + r + wd)
        if not g: return
        sl, xs, ys = g
        rho = np.sqrt((xs - u) ** 2 + (ys - v) ** 2)
        ang = np.degrees(np.arctan2(xs - u, ys - v)) + np.zeros_like(rho)
        am = (a0 + a1) / 2; hwd = (a1 - a0) / 2
        da = np.abs(((ang - am + 180) % 360) - 180) - hwd
        d = np.maximum(np.abs(rho - r) - wd / 2, da * pi / 180 * rho)
        s._put(sl, s._aa(d), col, emi)

    def shadow(s, u, v, r, k=0.5):
        if s.ro: return
        g = s._px(u - r, v - r, u + r, v + r)
        if not g: return
        sl, xs, ys = g
        a = k * np.clip(1 - np.sqrt((xs - u) ** 2 + (ys - v) ** 2) / r, 0, 1) ** 1.3
        s._put(sl, a + 0 * xs, (0.0, 0.0, 0.0))

    def stripes(s, u, v, w, h, per=0.009, r=0.0, c0=C_YEL, c1=(0.05, 0.05, 0.05)):
        if s.ro: return
        s.rect(u, v, w, h, c1, r=r)
        g = s._px(u - w / 2, v - h / 2, u + w / 2, v + h / 2)
        if not g: return
        sl, xs, ys = g
        qx = np.abs(xs - u) - (w / 2 - r); qy = np.abs(ys - v) - (h / 2 - r)
        d = np.sqrt(np.maximum(qx, 0) ** 2 + np.maximum(qy, 0) ** 2) + np.minimum(np.maximum(qx, qy), 0) - r
        t = ((xs + ys) / per) % 1.0
        ds = (np.abs(t - 0.5) - 0.25) * per / 1.414
        s._put(sl, s._aa(d) * s._aa(ds), c0)

    def screw(s, u, v, r=0.0032, ang=None):
        if s.ro: return
        if ang is None: ang = (u * 977 + v * 613) % 3.1
        s.disc(u, v, r + 0.0008, (0.05, 0.05, 0.05), alpha=0.6)
        s.disc(u, v, r, (0.30, 0.31, 0.32), hgt=0.6)
        s.disc(u, v, r * 0.72, (0.2, 0.205, 0.21))
        s.line(u - r * 0.7 * cos(ang), v - r * 0.7 * sin(ang), u + r * 0.7 * cos(ang), v + r * 0.7 * sin(ang), 0.0009, (0.03, 0.03, 0.03), hgt=-0.8)

    def text(s, txt, u, v, size=0.0056, col=C_LEG, emi=0.22, rot=0, anchor='c', eng=0.3):
        if s.ro or not txt: return
        m, wd = ck_text_mask(txt, size * s.ppm)
        wm = wd / s.ppm
        if anchor == 'l': u += wm / 2
        elif anchor == 'r': u -= wm / 2
        if rot: m = np.rot90(m, -rot)
        Hm, Wm = m.shape
        x0 = int(round((u + s.w / 2) * s.ppm - Wm / 2)); y0 = int(round((v + s.h / 2) * s.ppm - Hm / 2))
        a0 = max(0, -x0); b0 = max(0, -y0); a1 = min(Wm, s.pw - x0); b1 = min(Hm, s.ph - y0)
        if a1 <= a0 or b1 <= b0: return
        sl = (slice(s.y0 + y0 + b0, s.y0 + y0 + b1), slice(s.x0 + x0 + a0, s.x0 + x0 + a1))
        s._put(sl, m[b0:b1, a0:a1], col, emi, -eng)

    def corners(s, inset=0.0065, r=0.0032):
        for a in (-1, 1):
            for b in (-1, 1):
                s.screw(a * (s.w / 2 - inset), b * (s.h / 2 - inset), r)

    def frame(s, u, v, w, h, label=None, col=C_LEG):
        """thin legend box grouping some controls, label breaking the top line."""
        s.rect(u, v, w, h, col, r=0.002, line=0.0007, emi=0.2)
        if label:
            wd = ck_text_mask(label, 0.0048 * s.ppm)[1] / s.ppm + 0.004
            g = s._px(u - wd / 2, v + h / 2 - 0.003, u + wd / 2, v + h / 2 + 0.003)
            if g and not s.ro:
                sl = g[0]; CK['col'][sl] = np.array(s.col, np.float32); CK['emi'][sl] = 0
            s.text(label, u, v + h / 2, 0.0048, col)

    # ---- 3D widgets (also paint their legends / contact shadows)
    def toggle(s, u, v, label=None, lo=None, pos=1, hi=None, lsize=0.0054):
        mb = s.mb; F = s.F
        s.shadow(u, v, 0.012)
        F.rev(mb, u, v, 0.0, [(0, 0.0058), (0.0024, 0.0058), (0.0034, 0.0040)], 'Metal', T_STEEL, seg=6, cap0=False)
        a = rad(24) * pos
        P_revolve(mb, F.pt(u, v, 0.003), F.n * cos(a) + F.ey * sin(a),
                  [(0, 0.0016), (0.0125, 0.0025), (0.0150, 0.0025), (0.0162, 0.0014)], 'Metal', (0.55, 0.55, 0.56), seg=6, cap0=False)
        if label: s.text(label, u, v + 0.0142, lsize)
        if hi: s.text(hi, u, v + 0.0128, 0.0045, C_DIM)
        if lo: s.text(lo, u, v - 0.0118, 0.0045, C_DIM)

    def guard(s, u, v, label=None, lo=None, col=T_RED, haz=False):
        mb = s.mb; F = s.F
        if haz: s.stripes(u, v - 0.001, 0.03, 0.036, per=0.007, r=0.002)
        s.toggle(u, v, None, lo, pos=-1)
        if label: s.text(label, u, v + 0.0215, 0.0054)
        for sx in (-1, 1):
            F.box(mb, u + sx * 0.0068, v + 0.002, 0.0105, 0.0013, 0.021, 0.015, 'Paint', col)
        F.box(mb, u, v + 0.003, 0.0185, 0.0149, 0.019, 0.0013, 'Paint', col, 0.0004)
        CK_tube(mb, [F.pt(u - 0.0085, v + 0.0135, 0.0035), F.pt(u + 0.0085, v + 0.0135, 0.0035)], 0.0022, 'Metal', T_GUN, seg=6)

    def knob(s, u, v, label=None, r=0.009, h=0.013, ticks=0, span=270, ang=0.0, col=T_KNOB, tl=None, ldv=None, lsize=0.0054, seg=10, skirt=True):
        mb = s.mb; F = s.F
        s.shadow(u, v, r * 1.9, 0.55)
        prof = [(0, r * 1.28), (0.0022, r * 1.28), (0.0034, r), (h - 0.0015, r * 0.9), (h, r * 0.74)] if skirt else \
               [(0, r), (h - 0.0015, r * 0.92), (h, r * 0.76)]
        F.rev(mb, u, v, 0.0, prof, 'CkSatin', col, seg=seg, cap0=False)
        a = rad(ang)
        F.box(mb, u + r * 0.52 * sin(a), v + r * 0.52 * cos(a), h + 0.0003, 0.0015, r * 0.75, 0.0008, 'GaugeMark', T_W, ang=a)
        for k in range(ticks):
            ta = rad(-span / 2 + span * k / max(1, ticks - 1))
            s.line(u + r * 1.5 * sin(ta), v + r * 1.5 * cos(ta), u + r * 1.85 * sin(ta), v + r * 1.85 * cos(ta), 0.0008, C_LEG, emi=0.22)
            if tl and k < len(tl) and tl[k]:
                s.text(tl[k], u + (r * 1.85 + 0.0045) * sin(ta), v + (r * 1.85 + 0.0038) * cos(ta), 0.0042, C_DIM)
        if label:
            s.text(label, u, v + (ldv if ldv is not None else (r * 1.9 + 0.0065 if ticks else r * 1.3 + 0.006)), lsize)

    def key(s, u, v, w, h, label=None, cap=C_KEY, ink=C_BLK, hgt=0.003, size=None, emi=0.0, r=0.0014):
        mb = s.mb; F = s.F
        s.rect(u, v, w + 0.0036, h + 0.0036, (0.025, 0.025, 0.025), r=r + 0.001, alpha=0.8)
        s.rect(u, v, w, h, cap, r=r)
        s.rect(u, v, w - 0.0014, h - 0.0014, tuple(min(1, c * 1.35 + 0.04) for c in cap), r=r, line=0.0007, alpha=0.6)
        if label:
            s.text(label, u, v, size or min(h * 0.6, w * 1.45 / max(1, len(label))), ink, emi=emi, eng=0)
        a, b = w / 2, h / 2
        tl_ = tuple((c ** 2.2) * 0.55 for c in cap)
        P4 = [(u - a, v - b), (u + a, v - b), (u + a, v + b), (u - a, v + b)]
        ids = [mb.addv(F.pt(p[0], p[1], hgt), T_W) for p in P4]
        mb.addf(ids, 'CkDecal', [s.uv(*p) for p in P4])
        for k in range(4):
            p, q = P4[k], P4[(k + 1) % 4]
            hint = F.ex * ((p[0] + q[0]) / 2 - u) + F.ey * ((p[1] + q[1]) / 2 - v)
            oquad(mb, [F.pt(p[0], p[1], hgt), F.pt(q[0], q[1], hgt), F.pt(q[0], q[1], 0), F.pt(p[0], p[1], 0)], hint, 'Paint', tl_)

    def lamp(s, u, v, label=None, mat='CkLitG', r=0.0038, lo=None):
        mb = s.mb; F = s.F
        s.shadow(u, v, r * 2.2, 0.4)
        F.rev(mb, u, v, 0.0, [(0, r * 1.35), (0.002, r * 1.35), (0.0026, r * 1.05)], 'Metal', T_GUN, seg=8, cap0=False, cap1=False)
        F.rev(mb, u, v, 0.0015, [(0, r), (0.0025, r * 0.9), (0.004, r * 0.5)], mat, T_W, seg=8, cap0=False)
        if label: s.text(label, u, v + r + 0.0068, 0.0048)
        if lo: s.text(lo, u, v - r - 0.006, 0.0045, C_DIM)

    def cb(s, u, v, label=None, out=False):
        mb = s.mb; F = s.F
        s.shadow(u, v, 0.009, 0.5)
        F.rev(mb, u, v, 0.0, [(0, 0.0054), (0.002, 0.0054), (0.0028, 0.0042)], 'CkSatin', T_KNOB, seg=8, cap0=False, cap1=False)
        h0 = 0.0028; hb = 0.004 if out else 0.0012
        F.rev(mb, u, v, h0, [(0, 0.0031), (hb, 0.0031)], 'Paint', (0.62, 0.62, 0.6), seg=8, cap0=False, cap1=False)
        F.rev(mb, u, v, h0 + hb, [(0, 0.0035), (0.0034, 0.0035), (0.0042, 0.0026)], 'CkSatin', T_KNOB, seg=8, cap0=False)
        if label: s.text(label, u, v - 0.0098, 0.0042, C_LEG)

    def bolt(s, u, v, r=0.0028):
        s.shadow(u, v, r * 2, 0.4)
        s.F.rev(s.mb, u, v, 0.0, [(0, r), (0.0012, r), (0.0017, r * 0.65)], 'Metal', T_GUN, seg=6, cap0=False)

    def slot(s, u, v, w, h):
        s.rect(u, v, w, h, (0.02, 0.02, 0.022), r=min(w, h) / 2, hgt=-1.0)
        s.rect(u, v, w + 0.0012, h + 0.0012, C_WEAR, r=min(w, h) / 2 + 0.0006, line=0.0006, alpha=0.5)


# ------------------------------------------------------------------ instruments
def ck_dial_art(P, r, nums, full=False, label=None, arcs=(), nsize=0.0092, sub=5, unit=None):
    P.disc(0, 0, r + 0.0018, C_FACE)
    for (b0, b1, col) in arcs:
        P.arc(0, 0, r - 0.0028, b0, b1, 0.003, col, emi=0.35)
    a0, a1 = (-180, 180) if full else (-135, 135)
    nmaj = len(nums) if full else len(nums) - 1
    steps = nmaj * sub
    WH = (0.92, 0.93, 0.9)
    for k in range(steps + (0 if full else 1)):
        a = rad(a0 + (a1 - a0) * k / steps)
        major = k % sub == 0
        ln = 0.0062 if major else 0.0034
        ro = r - 0.0012
        P.line(ro * sin(a), ro * cos(a), (ro - ln) * sin(a), (ro - ln) * cos(a), 0.0014 if major else 0.0008, WH, emi=0.5)
    for k, t in enumerate(nums):
        a = rad(360.0 * k / len(nums)) if full else rad(a0 + (a1 - a0) * k / (len(nums) - 1))
        rr = r - 0.0138
        P.text(t, rr * sin(a), rr * cos(a), nsize, WH, emi=0.5, eng=0)
    if label: P.text(label, 0, -r * 0.40, 0.0062, C_DIM, emi=0.3, eng=0)
    if unit: P.text(unit, 0, r * 0.36, 0.0048, C_DIM, emi=0.3, eng=0)


def ck_dial(mb, F, u, v, r, nums=(), share=None, **kw):
    """analog instrument: painted face recessed in a satin-black cup bezel under a glass disc."""
    Fd = F.sub(u, v, 0.002)
    P = Plate(mb, Fd, 2 * r + 0.006, 2 * r + 0.006, ppm=2700, col=C_FACE, geo=False, edge=False, share=share)
    if nums or kw: ck_dial_art(P, r, nums, **kw)
    n = 28; ids = []; uvs = []
    for k in range(n):
        a = 2 * pi * k / n; x = (r + 0.0012) * cos(a); y = (r + 0.0012) * sin(a)
        ids.append(mb.addv(Fd.pt(x, y, 0), T_W)); uvs.append(P.uv(x, y))
    mb.addf(ids, 'CkDecal', uvs)
    tw = ck_worn(T_BEZ, 1.2)
    F.rev(mb, u, v, 0.0, [(0, r + 0.0065), (0.0125, r + 0.0065), (0.015, r + 0.0045), (0.015, r + 0.0018), (0.0035, r + 0.0008)],
          'CkSatin', T_BEZ, seg=n, cap0=False, cap1=False, tints=[T_BEZ, tw, tw, tw, T_BEZ])
    F.rev(mb, u, v, 0.0066, [(0, 0.005), (0.0012, 0.0042)], 'CkSatin', T_BEZ, seg=10, cap0=False)        # hub cap over the needle pivot
    F.rev(mb, u, v, 0.0128, [(0, r + 0.0018)], 'CkGlass', T_W, seg=n)
    return P


def ck_needle(name, F, u, v, r, parent='Cockpit'):
    mb = MB(); d = 0.0058; L = r * 0.84
    ids = [mb.addv(F.pt(u + x, v + y, d), T_W) for x, y in ((-0.0028, -0.008), (0.0028, -0.008), (0.0010, L), (-0.0010, L))]
    mb.addf(ids, 'Needle')
    return build(mb, name, origin=F.pt(u, v, d), rot=F.R, parent=parent)


ADI_R = 0.05

def ck_adi(mb, F, u, v, r=0.035):
    """standby attitude indicator housing; returns the ball centre."""
    tw = ck_worn(T_BEZ, 1.2); n = 28
    F.rev(mb, u, v, 0.0, [(0, r + 0.0065), (0.0165, r + 0.0065), (0.019, r + 0.0045), (0.019, r + 0.0015), (0.003, r - 0.002)],
          'CkSatin', T_BEZ, seg=n, cap0=False, cap1=False, tints=[T_BEZ, tw, tw, tw, (0.004, 0.004, 0.004)])
    dz = 0.0166
    F.box(mb, u - 0.017, v, dz, 0.014, 0.0026, 0.0008, 'CkLitA', T_W)
    F.box(mb, u + 0.017, v, dz, 0.014, 0.0026, 0.0008, 'CkLitA', T_W)
    F.box(mb, u - 0.0105, v - 0.0025, dz, 0.0026, 0.0065, 0.0008, 'CkLitA', T_W)
    F.box(mb, u + 0.0105, v - 0.0025, dz, 0.0026, 0.0065, 0.0008, 'CkLitA', T_W)
    F.box(mb, u, v, dz, 0.0034, 0.0034, 0.0008, 'CkLitA', T_W)
    for a in (-60, -30, -20, -10, 0, 10, 20, 30, 60):       # roll scale
        ar = rad(a); rr = r - 0.0015
        F.box(mb, u + rr * sin(ar), v + rr * cos(ar), 0.011, 0.0012 if a % 30 else 0.002, 0.005, 0.0006, 'GaugeMark', T_W, ang=ar)
    F.rev(mb, u, v, 0.0178, [(0, r + 0.0015)], 'CkGlass', T_W, seg=n)
    return F.pt(u, v, 0.003 - sqrt(ADI_R ** 2 - (r - 0.002) ** 2))


def ck_horizon(c, F, parent='Cockpit'):
    hb = MB(); up = F.ey; R0 = ADI_R
    def lat(a): return (R0 * sin(a) + R0, R0 * cos(a))
    k = 0.62
    sky = (0.10 * k, 0.30 * k, 0.78 * k); gnd = (0.20 * k, 0.10 * k, 0.035 * k); wh = (0.8 * k, 0.8 * k, 0.8 * k)
    south = c - up * R0
    P_revolve(hb, south, up, [lat(rad(a)) for a in range(-90, -1, 11)] + [lat(rad(-0.7))], 'Paint', gnd, seg=24, cap0=False, cap1=False)
    P_revolve(hb, south, up, [lat(rad(-0.7)), lat(rad(0.7))], 'Paint', wh, seg=24, cap0=False, cap1=False)
    P_revolve(hb, south, up, [lat(rad(0.7))] + [lat(rad(a)) for a in range(13, 91, 11)], 'Paint', sky, seg=24, cap0=False, cap1=False)
    for a in (-30, -20, -10, 10, 20, 30):
        P_revolve(hb, south, up, [lat(rad(a - 0.35)), lat(rad(a + 0.35))], 'Paint', wh, seg=24, cap0=False, cap1=False)
    ob = build(hb, 'Horizon', origin=c, rot=F.R, parent=parent)
    del OBJS['Horizon']        # keep it out of the AO bake: baked shading would rotate with the ball
    return ob


def ck_mfd(mb, F, size, scr, prot, name, DEF, big=False, share=None, screen=None):
    """display unit: satin housing, decal bezel with push-keys, screen quad recessed in the window."""
    wbox(mb, F.pt(0, 0, (prot - 0.013) / 2), (size, prot - 0.005, size), 'CkSatin', T_BEZ, 0.003, rot=F.R, wear=1.3)   # top stays below the screen quad
    ps = size - 0.007; hs = scr / 2
    P = Plate(mb, F.sub(0, 0, prot), ps, ps, ppm=1850, col=C_BLK, hole=(-hs, -hs, hs, hs), hole_d=0.007, thick=0.0095, cell=0.05, share=share, side=ck_worn(T_BEZ, 0.6))
    P.rect(0, 0, scr + 0.004, scr + 0.004, (0.02, 0.02, 0.022), r=0.002, line=0.0022, hgt=-0.8)
    bo = (ps - scr) / 2; off = hs + bo / 2
    if not big:
        n = 6; pit = scr / n
        for i in range(n):
            t = (i - (n - 1) / 2) * pit
            for sg in (-1, 1):
                P.key(t, sg * off, 0.0175, 0.0115); P.line(t, sg * (hs + 0.0035), t, sg * (off - 0.0075), 0.0008, C_LEG, emi=0.25)
                P.key(sg * off, t, 0.0115, 0.0175); P.line(sg * (hs + 0.0035), t, sg * (off - 0.0075), t, 0.0008, C_LEG, emi=0.25)
        P.knob(-off, off, None, r=0.0062, h=0.009, ang=-40, seg=8)
        P.knob(off, off, None, r=0.0062, h=0.009, ang=30, seg=8)
        P.screw(-off, -off, 0.003); P.screw(off, -off, 0.003)
    else:
        n = 5; pit = scr / n
        top = ('TGT', 'NAV', 'WPN', 'SYS', 'MAP'); lf = ('Z+', 'Z-', 'FOV', 'TRK', 'LAS'); rt = ('BRT', 'CON', 'SYM', 'DCL', 'FRZ')
        for i in range(n):
            t = (i - (n - 1) / 2) * pit
            P.key(t, off, 0.031, 0.0135, top[i], hgt=0.004)
            P.key(t, -off, 0.027, 0.0135, None, cap=(0.62, 0.63, 0.61), hgt=0.004)
            P.key(-off, -t, 0.0145, 0.027, lf[i], hgt=0.004, size=0.0056)
            P.key(off, -t, 0.0145, 0.027, rt[i], hgt=0.004, size=0.0056)
        P.knob(off, off, None, r=0.0065, h=0.011, ang=-50, seg=10, skirt=False)
        P.knob(-off, off, None, r=0.0065, h=0.011, ang=20, seg=10, skirt=False)
        P.screw(-off, -off, 0.0034); P.screw(off, -off, 0.0034)
    if name:
        DEF.append(('mfd', name, F.sub(0, 0, prot - 0.007), hs))
    else:
        Fs = F.sub(0, 0, prot - 0.007); P4 = ((-hs, -hs), (hs, -hs), (hs, hs), (-hs, hs))
        mb.addf([mb.addv(Fs.pt(a, b, 0), T_W) for a, b in P4], 'CkDecal', [screen.uv(a * screen.w / scr, b * screen.h / scr) for a, b in P4])
    return P


def ck_caution(mb, F, lamps, DEF, w=0.225, h=0.047):
    """annunciator housing with 4 separately named lamps (own materials, toggled by the game)."""
    d = 0.014
    wbox(mb, F.pt(0, 0, (d - 0.005) / 2), (w + 0.004, d + 0.004, h + 0.004), 'CkSatin', T_BEZ, 0.003, rot=F.R, wear=1.3)
    P = Plate(mb, F.sub(0, 0, d), w, h, ppm=1850, col=C_BLK, thick=0.001, cell=0.06)
    lw = 0.050; pit = 0.0545
    for k, (nm, lab) in enumerate(lamps):
        u = (k - 1.5) * pit
        P.rect(u, 0, lw + 0.003, 0.033, (0.015, 0.015, 0.015), r=0.002, hgt=-0.8)
        F.text(mb, lab, 0.0128 if len(lab) <= 4 else (0.0112 if len(lab) == 5 else 0.0098), u, 0.0, d + 0.0057, mat='Paint', tint=T_BLACK)
        DEF.append(('warn', nm, F.sub(0, 0, d), u, lw))
    P.screw(-w / 2 + 0.004, h / 2 - 0.004, 0.0022); P.screw(w / 2 - 0.004, h / 2 - 0.004, 0.0022)
    P.screw(-w / 2 + 0.004, -h / 2 + 0.004, 0.0022); P.screw(w / 2 - 0.004, -h / 2 + 0.004, 0.0022)


# ------------------------------------------------------------------ main instrument panel
PA = rad(15)
RP = Rtilt(PA)
PP = V(0, 2.70, 0.55)
WING_U = 0.215
WING_YAW = rad(14)

def ck_main_panel(mb, DEF):
    FC = Fr(PP, RP)
    # ---- centre section: board, centre display, standby instruments
    wbox(mb, FC.pt(0, 0.0195, -0.012), (0.432, 0.02, 0.361), 'CkCoat', T_CKB, 0.003, rot=FC.R, wear=1.0)
    ck_mfd(mb, FC.sub(0, 0.069, 0), 0.262, 0.21, 0.032, 'MFD_C', DEF, big=True)
    FB = FC.sub(0, -0.112, 0.004)
    PB = Plate(mb, FB, 0.428, 0.087, ppm=1850)
    r1 = 0.035; r2 = 0.033; dv = 0.004
    def flange(P, u, v, s_=0.079, knob=None):
        P.rect(u, v, s_, s_, C_PLATE2, r=0.008); P.rect(u, v, s_, s_, C_WEAR, r=0.008, line=0.0008, alpha=0.5, hgt=-0.5)
        for a in (-1, 1):
            for b in (-1, 1):
                if knob and a > 0 and b < 0: P.knob(u + a * (s_ / 2 - 0.0065), v + b * (s_ / 2 - 0.0065), None, r=0.005, h=0.009, seg=8, ang=knob, skirt=False)
                else: P.screw(u + a * (s_ / 2 - 0.0055), v + b * (s_ / 2 - 0.0055), 0.0024)
    G = {}
    row = (('Needle_VS', -0.175), ('Needle_Speed', -0.0875), (None, 0.0), ('Needle_Alt', 0.0875), ('Needle_RPM', 0.175))
    for nm, u in row: flange(PB, u, dv, 0.083, knob=40 if nm is None else (130 if nm == 'Needle_Alt' else None))
    RED = (0.85, 0.1, 0.06); GRN = (0.2, 0.7, 0.25); YEL = (0.9, 0.75, 0.1)
    ck_dial(mb, FB, -0.175, dv, r1, ['-2', '-1', '0', '1', '2'], label='VS', sub=5)
    CK['dial_kts'] = ck_dial(mb, FB, -0.0875, dv, r1, ['0', '4', '8', '12', '16', '20'], label='KTS', unit='x10', arcs=((-135, 54, GRN), (54, 108, YEL), (108, 135, RED)))
    ck_dial(mb, FB, 0.0875, dv, r1, ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9'], full=True, label='ALT', sub=5, nsize=0.0085)
    ck_dial(mb, FB, 0.175, dv, r1, ['0', '2', '4', '6', '8', '10'], label='RPM', unit='%x10', arcs=((54, 100, GRN), (100, 135, RED)))
    for nm, u in row:
        if nm: G[nm] = (FB, u, dv, r1)
    hc = ck_adi(mb, FB, 0.0, dv, r1)
    # gauge columns flanking the centre display
    for s in (-1, 1):
        Fc = FC.sub(s * 0.175, 0.066, 0.004)
        Pc = Plate(mb, Fc, 0.078, 0.268, ppm=1850)
        v0, v1_, v2 = -0.0905, -0.006, 0.0795
        for vv in (v0, v1_):
            flange(Pc, 0, vv, 0.076)
        if s < 0:
            ck_dial(mb, Fc, 0, v0, r2, ['N', '3', '6', 'E', '12', '15', 'S', '21', '24', 'W', '30', '33'], full=True, sub=3, nsize=0.0068)
            Fc.box(mb, 0, v0 + 0.012, 0.0075, 0.003, 0.02, 0.0008, 'GaugeMark', T_W)        # lubber line
            ck_dial(mb, Fc, 0, v1_, r2, ['0', '1', '2', '3', '4'], label='G', arcs=((-135, 90, GRN), (90, 135, RED)))
            Fc.box(mb, -0.008, v1_ - 0.006, 0.0075, 0.0022, 0.024, 0.0008, 'GaugeMark', T_W, ang=rad(-52))
            # HUD control head in the top slot
            Pc.frame(0, v2 + 0.002, 0.068, 0.084, 'HUD')
            Pc.knob(0, v2 + 0.014, 'BRT', r=0.0085, h=0.012, ticks=5, ang=40)
            Pc.toggle(-0.016, v2 - 0.022, 'SYM', None, lsize=0.0048); Pc.toggle(0.016, v2 - 0.022, 'NVS', None, pos=-1, lsize=0.0048)
        else:
            ck_dial(mb, Fc, 0, v0, r2, ['0', '2', '4', '6', '8', '10'], label='TQ', unit='%x10', arcs=((-135, 81, GRN), (81, 108, YEL), (108, 135, RED)))
            ck_dial(mb, Fc, 0, v1_, r2, ['0', '2', '4', '6', '8'], label='TEMP', unit='C x100', arcs=((-67, 67, GRN), (67, 101, YEL), (101, 135, RED)))
            flange(Pc, 0, v2, 0.076)
            ck_dial(mb, Fc, 0, v2, r2, ['E', '', '1/2', '', 'F'], label='FUEL', arcs=((-135, -108, RED),), nsize=0.0075)
            Fc.box(mb, 0.0065, v2 + 0.0065, 0.0075, 0.0022, 0.024, 0.0008, 'GaugeMark', T_W, ang=rad(45))
            G['Needle_Torque'] = (Fc, 0, v0, r2); G['Needle_Temp'] = (Fc, 0, v1_, r2)
    DEF.append(('needles', G)); DEF.append(('horizon', hc, FB))
    # ---- canted wings: side displays, caution strips, lower control strips
    for s in (-1, 1):
        FW = FC.sub(s * WING_U, 0, 0, yaw=s * WING_YAW)
        wbox(mb, FW.pt(s * 0.1285, 0.0, -0.012), (0.257, 0.02, 0.40), 'CkCoat', T_CKB, 0.003, rot=FW.R, wear=1.0)
        CK['mfd_plate'] = ck_mfd(mb, FW.sub(s * 0.13, 0.02, 0), 0.25, 0.2, 0.03, 'MFD_L' if s < 0 else 'MFD_R', DEF, share=CK.get('mfd_plate'))
        lamps = (('Warn_Master', 'MASTER'), ('Warn_Fire', 'FIRE'), ('Warn_Engine', 'ENG'), ('Warn_Rotor', 'ROTOR')) if s < 0 else \
                (('Warn_Tail', 'TAIL'), ('Warn_Hyd', 'HYD'), ('Warn_Weapons', 'WPN'), ('Warn_Canopy', 'CANOPY'))
        ck_caution(mb, FW.sub(s * 0.118, 0.1745, 0), lamps, DEF)
        FL = FW.sub(s * 0.13, -0.1555, 0.006)
        wbox(mb, FW.pt(s * 0.13, -0.1555, -0.001), (0.25, 0.011, 0.087), 'CkCoat', T_CKC, 0.002, rot=FW.R, wear=1.0)
        PL = Plate(mb, FL, 0.246, 0.083, ppm=1850, thick=0.001)
        PL.corners(0.0055, 0.0026)
        if s < 0:
            PL.text('ARMAMENT', -0.118, 0.034, 0.0052, anchor='l')
            PL.guard(-0.094, -0.006, 'MASTER', 'SAFE', haz=True)
            PL.lamp(-0.062, 0.008, 'ARMED', 'CkLitA'); PL.lamp(-0.062, -0.02, None, 'CkLitG', lo='SAFE')
            for k, t in enumerate(('GUN', 'RKT', 'MSL')):
                PL.key(-0.028 + k * 0.03, -0.008, 0.026, 0.02, t, cap=C_KEYD, ink=C_GRN, emi=0.9, size=0.0075)
            PL.frame(0.002, -0.006, 0.096, 0.036, 'SELECT')
            PL.knob(0.076, -0.01, 'BURST', r=0.0085, ticks=5, tl=('1', '', '', '', 'C'), ang=-30)
            PL.toggle(0.108, -0.008, 'LASER', 'OFF')
        else:
            PL.rect(-0.05, 0.0, 0.132, 0.058, (0.01, 0.01, 0.012), r=0.003, hgt=-1.0)
            PL.rect(-0.05, 0.0, 0.132, 0.058, C_WEAR, r=0.003, line=0.0008, alpha=0.5)
            for k, t in enumerate(('V1 124.500   FM 38.25', 'TGT 04  BRG 217  3.4', 'FUEL 1180   T+06:42')):
                PL.text(t, -0.111, 0.018 - k * 0.018, 0.0074, C_AMB, emi=1.0, anchor='l', eng=0)
            PL.knob(0.045, -0.006, 'CHAN', r=0.0085, ticks=7, ang=45)
            PL.key(0.094, 0.014, 0.03, 0.015, 'SWAP', cap=C_KEYD, ink=C_LEG, emi=0.3)
            PL.key(0.094, -0.008, 0.03, 0.015, 'ENT', cap=C_KEYD, ink=C_LEG, emi=0.3)
            PL.key(0.094, -0.03, 0.03, 0.015, 'CLR', cap=C_KEYD, ink=C_LEG, emi=0.3)
        # outboard hand-hold on the panel edge
        hx = s * 0.262
        pts = [FW.pt(hx, 0.10, -0.01), FW.pt(hx, 0.10, 0.03), FW.pt(hx, -0.06, 0.03), FW.pt(hx, -0.06, -0.01)]
        CK_tube(mb, ck_path(pts, 3, 0.25), 0.007, 'CkRubber', T_KNOB, seg=6)
    return FC


def ck_coaming(mb):
    """glareshield following the canopy section, padded lip, instrument shroud behind the panel, HUD projector."""
    def ylip(x): return 2.60 - 0.075 * (x / 0.44) ** 2
    nx = 12; fs = (0.0, 0.035, 0.15, 0.4, 0.7, 1.0); YF = 3.0
    rings = []
    for k, f in enumerate(fs):
        top = []; bot = []
        for i in range(nx + 1):
            t = -1 + 2 * i / nx
            yl = ylip(t * 0.44); zl = 0.92 - 0.163 * (yl - 1.91)
            y = yl + f * (YF - yl); z = zl - 0.23 * (y - yl)
            hw = min(0.447, ck_hw(y, z) - 0.004 - 0.012 * f)
            th = 0.026 if k else 0.012
            zt = z if k else z - 0.007
            top.append(V(t * hw, y, zt)); bot.append(V(t * hw, y, zt - th))
        rings.append(top + bot[::-1])
    tc = (0.012, 0.012, 0.013)
    P_loft(mb, rings, 'CkRubber', tc, closed=True, cap0=True, cap1=True, tintfn=lambda i, j: ck_worn(tc, 0.9) if i == 1 else tc)
    # defog outlets + sensor box on the glareshield top (seen from outside through the canopy)
    for sx in (-1, 1):
        y = 2.84; z = 0.92 - 0.163 * (2.60 - 1.91) - 0.23 * (y - 2.60)
        Rv = Matrix.Rotation(atan2(-0.23, 1.0), 3, 'X')
        P_box(mb, V(sx * 0.2, y, z + 0.004), (0.16, 0.05, 0.012), 'CkSatin', T_BEZ, 0.003, rot=Rv)
        for k in range(6):
            P_box(mb, V(sx * 0.2 - 0.06 + k * 0.024, y, z + 0.011), (0.014, 0.036, 0.003), 'Paint', T_BLACK, rot=Rv)
    # shroud behind the instrument faces
    FC = Fr(PP, RP)
    rs = []
    for d in (-0.028, -0.11, -0.19, -0.27):
        r = []
        for (u, v) in ((-0.5, -0.2), (0.5, -0.2), (0.5, 0.215), (-0.5, 0.215)):
            p = FC.pt(u, v, d)
            hw = min(0.47 if v < 0 else 0.445, ck_hw(p.y, p.z) - 0.02)
            p.x = hw * (1 if u > 0 else -1); r.append(p)
        rs.append(r)
    P_loft(mb, rs, 'CkCoat', T_CKD, closed=True, cap0=True, cap1=True)
    # HUD projector + combiner frame
    wbox(mb, V(0, 2.628, 0.789), (0.13, 0.10, 0.03), 'CkSatin', T_BEZ, 0.006, wear=1.2)
    P_revolve(mb, V(0, 2.60, 0.80), V(0, -0.5, 1), [(0, 0.028), (0.006, 0.028), (0.006, 0.022)], 'CkSatin', T_BEZ, seg=14, cap0=False, cap1=False)
    P_revolve(mb, V(0, 2.60, 0.80), V(0, -0.5, 1), [(0.004, 0.022)], 'Lens', T_W, seg=14)
    for s in (-1, 1):
        CK_tube(mb, ck_path([V(s * 0.06, 2.60, 0.79), V(s * 0.092, 2.535, 0.83), V(s * 0.092, 2.512, 0.875)], 3, 0.3), 0.005, 'Metal', T_GUN, seg=6)
        P_box(mb, V(s * 0.089, 2.511, 0.878), (0.008, 0.01, 0.07), 'Metal', T_GUN, 0.002, rot=Matrix.Rotation(rad(-18), 3, 'X'))
    P_box(mb, V(0, 2.522, 0.846), (0.19, 0.008, 0.008), 'Metal', T_GUN, 0.002)


# ------------------------------------------------------------------ console panel modules (each fills one Plate)
def ckp_start(P):
    P.guard(-0.046, 0.0, 'APU', 'OFF', haz=True)
    P.toggle(-0.012, 0.0, 'IGN', 'OFF'); P.toggle(0.018, 0.0, 'ENG 1', 'OFF'); P.toggle(0.048, 0.0, 'ENG 2', 'OFF', pos=-1)
    P.lamp(-0.012, -0.034, None, 'CkLitG', lo=None); P.lamp(0.018, -0.034, None, 'CkLitG'); P.lamp(0.048, -0.034, None, 'CkLitA')
    P.text('READY', -0.046, -0.034, 0.0048)

def ckp_power(P):
    mb = P.mb; F = P.F
    for k, u in enumerate((-0.03, 0.006)):
        P.slot(u, 0.0, 0.009, 0.15)
        t = 0.03 if k == 0 else 0.018
        base = F.pt(u, t, 0.0); top = F.pt(u, t + 0.02, 0.062)
        CK_tube(mb, [base, top], 0.0065, 'Metal', T_GUN, seg=6, flat=(F.ex, 0.4))
        CK_tube(mb, [top - F.ex * 0.017, top + F.ex * 0.017], 0.011, 'CkSatin', T_KNOB, seg=10)
        CK_tube(mb, [top + F.ex * 0.0172, top + F.ex * 0.0195], 0.0112, 'Paint', T_RED if k == 0 else T_YEL, seg=10)
        P.text(str(k + 1), u, -0.086, 0.007)
    for t, v in (('MAX', 0.068), ('FLT', 0.034), ('IDLE', -0.02), ('OFF', -0.066)):
        P.line(0.016, v, 0.024, v, 0.0009, C_LEG, emi=0.22); P.text(t, 0.027, v, 0.0052, anchor='l')
    P.line(0.02, -0.066, 0.02, 0.068, 0.0007, C_LEG, emi=0.2)
    P.knob(-0.056, -0.062, 'FRICT', r=0.0095, h=0.014, ang=70)
    P.guard(-0.056, 0.04, 'RTR BRK', 'OFF')
    P.toggle(0.054, -0.062, 'GOV', 'MAN', hi=None)

def ckp_emerg(P):
    P.stripes(0, P.h / 2 - 0.0085, P.w - 0.008, 0.008); P.stripes(0, -P.h / 2 + 0.0075, P.w - 0.008, 0.008)
    P.text('EMERGENCY', 0, 0.036, 0.006, C_YEL)
    P.guard(-0.044, -0.004, 'HYD 2', None, col=T_YEL); P.guard(-0.008, -0.004, 'FUEL CUT'); P.guard(0.028, -0.004, 'BEACON', None, col=T_YEL)
    P.key(0.058, -0.004, 0.018, 0.018, 'ZERO', cap=(0.55, 0.1, 0.07), ink=C_LEG, size=0.0046)

def ckp_light(P):
    for k, t in enumerate(('PANEL', 'CONSOLE', 'FLOOD')):
        P.knob(-0.044 + k * 0.044, 0.03, t, r=0.0095, ticks=7, ang=-100 + k * 70)
    P.toggle(-0.048, -0.04, 'NAV', 'OFF'); P.toggle(-0.016, -0.04, 'FORM', 'OFF', pos=-1); P.toggle(0.016, -0.04, 'STROBE', 'OFF'); P.toggle(0.048, -0.04, 'SRCH', 'STOW', pos=-1)
    P.frame(0, -0.039, 0.134, 0.048, 'EXTERIOR')

def ckp_fuel(P):
    P.knob(-0.036, 0.012, 'TANK SEL', r=0.012, h=0.015, ticks=4, span=180, tl=('L', 'BOTH', 'R', 'OFF'), ang=-30)
    P.toggle(0.02, 0.022, 'BOOST 1', 'OFF'); P.toggle(0.05, 0.022, 'BOOST 2', 'OFF')
    P.toggle(0.02, -0.03, 'XFER', 'AUTO', pos=-1); P.guard(0.05, -0.03, 'DUMP', None, col=T_YEL)
    P.lamp(-0.052, -0.044, None, 'CkLitA', lo=None); P.text('LOW PRESS', -0.022, -0.044, 0.0046)

def ckp_env(P):
    P.knob(-0.038, 0.004, 'CABIN TEMP', r=0.011, ticks=7, ang=20)
    P.knob(0.008, 0.004, 'FLOW', r=0.009, ticks=5, ang=-60)
    P.toggle(0.046, 0.012, 'ECS', 'OFF'); P.toggle(0.046, -0.03, 'DEFOG', 'OFF', pos=-1)

def ckp_comm(P):
    names = (('V1', 'V2', 'UHF', 'FM'), ('ICS', 'NAV', 'ADF', 'MKR'), ('SAT', 'DL', 'RWR', 'AUX'))
    for j, row in enumerate(names):
        for k, t in enumerate(row):
            P.knob(-0.051 + k * 0.034, 0.072 - j * 0.038, t, r=0.007, h=0.012, ang=(k * 77 + j * 51) % 240 - 120, skirt=False, ldv=0.0125, seg=8, lsize=0.0048)
    P.knob(-0.034, -0.062, 'XMIT', r=0.011, ticks=5, tl=('1', '2', '3', '4', '5'), ang=-67)
    P.toggle(0.014, -0.058, 'HOT MIC', 'OFF'); P.toggle(0.048, -0.058, 'SQL', 'OFF', pos=-1)
    P.line(-0.066, -0.029, 0.066, -0.029, 0.0007, C_LEG, emi=0.2)

def ckp_iff(P):
    P.knob(-0.038, 0.0, 'MODE', r=0.011, ticks=4, span=180, tl=('OFF', 'STBY', 'NORM', 'EMER'), ang=30)
    for k, t in enumerate(('M1', 'M2', 'M3', 'MC')):
        P.toggle(0.0 + k * 0.02, 0.016, t, None, pos=1 if k % 2 else -1, lsize=0.0046)
    P.key(0.03, -0.03, 0.05, 0.016, 'IDENT', cap=C_KEYD, ink=C_LEG, emi=0.3)

def ckp_ice(P):
    P.toggle(-0.05, 0.012, 'PITOT', 'OFF'); P.toggle(-0.02, 0.012, 'ENG A/I', 'OFF', pos=-1); P.toggle(0.01, 0.012, 'BLADE', 'OFF')
    P.knob(0.046, 0.0, 'WIPER', r=0.0095, ticks=4, span=180, tl=('PARK', 'OFF', 'LO', 'HI'), ang=-30)
    P.lamp(-0.05, -0.04, None, 'CkLitA'); P.text('ICE DET', -0.022, -0.04, 0.0048)

def ckp_cmds(P):
    for k, (t, n) in enumerate((('FLARE', '30'), ('CHAFF', '06'))):
        u = -0.042 + k * 0.04
        P.rect(u, 0.026, 0.028, 0.016, (0.01, 0.01, 0.012), r=0.002, hgt=-1); P.text(n, u, 0.026, 0.011, C_AMB, emi=1.0, eng=0)
        P.toggle(u, -0.014, t, 'OFF')
    P.knob(0.03, 0.02, 'PROG', r=0.009, ticks=4, tl=('1', '2', '3', '4'), ang=-45)
    P.guard(0.05, -0.024, 'JETT', None, haz=True)

def ckp_keypad(P):
    w = P.w
    P.text('DATA ENTRY', 0, P.h / 2 - 0.0085, 0.0058)
    P.rect(0, 0.105, w - 0.024, 0.028, (0.008, 0.012, 0.01), r=0.002, hgt=-1)
    P.rect(0, 0.105, w - 0.024, 0.028, C_WEAR, r=0.002, line=0.0008, alpha=0.5)
    P.text('>WPT 04  N47 12.6_', -w / 2 + 0.017, 0.105, 0.0078, C_GRN, emi=1.0, anchor='l', eng=0)
    keys = list('ABCDEFGHIJKLMNOPQRSTUVWXYZ') + list('1234567890') + ['CLR', 'SPC', '.', '-', 'BKS', 'ENT']
    cols = 6; pit = 0.0215; pv = 0.0235
    for i, t in enumerate(keys):
        c = i % cols; r = i // cols
        lite = t.isdigit()
        P.key((c - (cols - 1) / 2) * pit, 0.074 - r * pv, 0.0175, 0.0185, t, cap=C_KEY if lite else C_KEYD, ink=C_BLK if lite else C_LEG,
              emi=0.0 if lite else 0.3, size=0.0095 if len(t) == 1 else 0.0056, hgt=0.0035)
    P.corners(0.005, 0.0024)

def ckp_afcs(P):
    P.text('AFCS', 0, P.h / 2 - 0.0085, 0.0058)
    for k, t in enumerate(('ATT', 'ALT', 'HDG', 'SAS')):
        P.key(-0.045 + k * 0.03, 0.1, 0.025, 0.02, t, cap=C_KEYD, ink=C_GRN if k != 1 else C_DIM, emi=0.9 if k != 1 else 0.2, size=0.0075)
    P.knob(-0.036, 0.05, 'TRIM', r=0.011, ticks=7, ang=0); P.toggle(0.012, 0.055, 'FORCE', 'OFF'); P.toggle(0.046, 0.055, 'YAW', 'OFF', pos=-1)
    P.line(-0.066, 0.02, 0.066, 0.02, 0.0007, C_LEG, emi=0.2)
    P.text('STORES', 0, 0.01, 0.0058)
    for k in range(4):
        P.toggle(-0.045 + k * 0.03, -0.022, 'STN %d' % (k + 1), None, pos=1 if k in (0, 3) else -1, lsize=0.0046)
        P.lamp(-0.045 + k * 0.03, -0.046, None, 'CkLitG' if k != 2 else 'CkLitA', r=0.003)
    P.stripes(0, -0.098, P.w - 0.02, 0.05, per=0.008, r=0.003)
    P.rect(0, -0.098, P.w - 0.034, 0.036, P.col, r=0.002)
    P.guard(-0.03, -0.1, 'JETT ALL', None); P.knob(0.03, -0.1, 'SEL', r=0.009, ticks=5, ang=45)
    P.corners(0.005, 0.0024)

CK_LEFT = (('ENG START', 0.13, ckp_start), ('POWER', 0.22, ckp_power), (None, 0.115, ckp_emerg), ('INTERIOR LT', 0.17, ckp_light), ('FUEL', 0.15, ckp_fuel))
CK_RIGHT = (('ENV CONTROL', 0.13, ckp_env), ('COMM', 0.235, ckp_comm), ('IFF', 0.12, ckp_iff), ('ANTI-ICE', 0.13, ckp_ice), ('COUNTERMEASURES', 0.17, ckp_cmds))
CON_Z = 0.2265; CON_X0 = 0.33; CON_X1 = 0.535; CON_Y0 = 1.47; CON_Y1 = 2.30; RAMP_Y = 2.585; RAMP_Z = 0.343

def ck_stack(mb, Ft, y, specs, shared, PW=0.146):
    plates = []
    for k, (title, L, fn) in enumerate(specs):
        P = Plate(mb, Ft.sub(0, y + L / 2, 0), PW, L, share=shared[k] if shared else None)
        if title: P.text(title, 0, L / 2 - 0.008, 0.0058)
        for a in (-1, 1):
            P.screw(a * (PW / 2 - 0.0045), L / 2 - 0.0045, 0.0024); P.screw(a * (PW / 2 - 0.0045), -L / 2 + 0.0045, 0.0024)
        fn(P); plates.append(P)
        y += L + 0.005
    return plates


def ck_console(mb, s, shared=None):
    """side console: body, stack of panel modules on top, ramp panel rising to the instrument panel. Returns plates."""
    x0, x1 = (CON_X0, CON_X1) if s > 0 else (-CON_X1, -CON_X0)
    prism(mb, [(CON_Y0, -0.30), (CON_Y0, CON_Z), (CON_Y1, CON_Z), (RAMP_Y, RAMP_Z), (2.72, RAMP_Z), (2.72, -0.30)], x0, x1, 'CkCoat', T_CKC, wear=1.0)
    xc = s * 0.43; PW = 0.146
    Ft = Fr(V(xc, 0, CON_Z + 0.003), Rtilt(rad(90)))
    plates = ck_stack(mb, Ft, CON_Y0 + 0.006, CK_LEFT if s < 0 else CK_RIGHT, shared, PW)
    # rails either side of the panel stack
    for a in (-1, 1):
        P_box(mb, V(xc + a * (PW / 2 + 0.006), (CON_Y0 + CON_Y1) / 2, CON_Z + 0.002), (0.006, CON_Y1 - CON_Y0 - 0.01, 0.004), 'Metal', T_GUN, 0.001)
    # ramp
    beta = atan2(RAMP_Z - CON_Z, RAMP_Y - CON_Y1); L = sqrt((RAMP_Z - CON_Z) ** 2 + (RAMP_Y - CON_Y1) ** 2)
    Fm = Fr(V(xc, (CON_Y1 + RAMP_Y) / 2, (CON_Z + RAMP_Z) / 2), Rtilt(rad(90) - beta)).sub(0, 0, 0.003)
    P = Plate(mb, Fm, PW, L - 0.012, share=shared[-1] if shared else None)
    (ckp_keypad if s < 0 else ckp_afcs)(P); plates.append(P)
    return plates


def ck_pedestal(mb):
    """centre pedestal between the pilot's shins: slanted control face under the panel."""
    prism(mb, [(2.74, -0.30), (2.42, -0.30), (2.42, 0.02), (2.615, 0.33), (2.74, 0.33)], -0.082, 0.082, 'CkCoat', T_CKC, wear=1.0)
    beta = atan2(0.31, 0.195); L = sqrt(0.31 ** 2 + 0.195 ** 2)
    F = Fr(V(0, 2.5175, 0.175), Rtilt(rad(90) - beta)).sub(0, 0, 0.003)
    P = Plate(mb, F, 0.15, L - 0.014)
    P.corners(0.005, 0.0024)
    P.text('FLT CONTROL', 0, P.h / 2 - 0.0085, 0.0058)
    P.knob(-0.045, 0.125, 'PEDAL ADJ', r=0.011, h=0.016, ang=120)
    P.toggle(0.0, 0.128, 'TRIM', 'REL'); P.toggle(0.03, 0.128, 'SAS', 'OFF', pos=-1); P.toggle(0.058, 0.128, 'HYD', 'OFF')
    P.line(-0.068, 0.098, 0.068, 0.098, 0.0007, C_LEG, emi=0.2)
    # park brake T-handle (hazard) + rotor brake lever
    P.text('PARK BRAKE', -0.036, 0.086, 0.0052); P.text('PULL', -0.036, 0.026, 0.0046, C_DIM)
    P.disc(-0.036, 0.056, 0.012, (0.03, 0.03, 0.03), hgt=-0.6)
    c = F.pt(-0.036, 0.056, 0.0)
    CK_tube(mb, [c, c + F.n * 0.034], 0.005, 'Metal', T_STEEL, seg=8)
    CK_tube(mb, [c + F.n * 0.034 - F.ex * 0.028, c + F.n * 0.034 + F.ex * 0.028], 0.0085, 'CkHazard', T_W, seg=10)
    P.text('FUEL SHUTOFF', 0.034, 0.086, 0.0052)
    for k, u in enumerate((0.018, 0.05)):
        P.slot(u, 0.05, 0.008, 0.05)
        c = F.pt(u, 0.062, 0.0)
        CK_tube(mb, [c, c + F.n * 0.03 + F.ey * 0.006], 0.0035, 'Metal', T_STEEL, seg=6)
        P_sphere(mb, c + F.n * 0.034 + F.ey * 0.007, 0.0095, 'Paint', T_RED, seg=10, rings=6)
        P.text(str(k + 1), u, 0.018, 0.0055)
    P.line(-0.068, 0.006, 0.068, 0.006, 0.0007, C_LEG, emi=0.2)
    for k, t in enumerate(('PITOT', 'STAB', 'TAIL WHL')):
        P.toggle(-0.044 + k * 0.044, -0.03, t, 'OFF' if k < 2 else 'LOCK', pos=1 if k != 1 else -1)
    P.frame(0, -0.03, 0.138, 0.052, None)
    P.knob(-0.034, -0.1, 'RAD ALT', r=0.011, ticks=7, ang=-20); P.knob(0.034, -0.1, 'BRG', r=0.011, ticks=7, ang=80)
    P.lamp(0.0, -0.095, None, 'CkLitG', r=0.003)
    P.stripes(0, -P.h / 2 + 0.008, P.w - 0.012, 0.007)


CK_CB = ['FCS 1', 'FCS 2', 'HYD', 'FUEL', 'IGN', 'APU', 'NAV', 'COM 1', 'COM 2', 'IFF', 'MFD 1', 'MFD 2', 'MFD 3', 'HUD', 'GUN', 'RKT',
         'MSL', 'CMDS', 'SENS', 'NVS', 'LSR', 'ICS', 'LTS', 'PITOT', 'WIPE', 'ECS', 'TRIM', 'SAS', 'ENG 1', 'ENG 2', 'ROTR', 'XFER',
         'BATT', 'GEN 1', 'GEN 2', 'INV', 'EXT', 'UTIL', 'DTU', 'CLK', 'STBY', 'WARN', 'FIRE', 'ELT', 'ANT', 'DL', 'RWR', 'SPR']

def ck_cbpanel(mb, F, w, h, n, k0, title, share=None):
    wbox(mb, F.pt(0, 0, -0.007), (w + 0.008, 0.014, h + 0.008), 'CkCoat', T_CKC, 0.002, rot=F.R, wear=1.0)
    P = Plate(mb, F.sub(0, 0, 0.001), w, h, share=share, thick=0.001)
    P.corners(0.005, 0.0024)
    P.text(title, -w / 2 + 0.012, h / 2 - 0.0085, 0.0056, anchor='l')
    pit = (w - 0.03) / n
    for r in range(2):
        v = 0.018 - r * 0.046
        for k in range(n):
            i = k0 + r * n + k
            P.cb((k - (n - 1) / 2) * pit, v, CK_CB[i % len(CK_CB)], out=(i % 13 == 7))
    return P


def ck_walls(mb):
    cbp = {}
    for s in (-1, 1):
        # structure: frames, sill rail, stringer
        for y in (1.50, 1.80, 2.10, 2.40):
            ths = [rad(a) * s for a in range(81, 118, 6)]
            P_sweep(mb, [spi(y, t, 0.036) for t in ths], [-sn(y, t) for t in ths], 0.026, 0.016, 0.0, 'CkCoat', T_WALL)
        yy = [1.42 + 0.0975 * k for k in range(13)]; th = rad(78) * s
        P_sweep(mb, [spi(y, th, 0.034) for y in yy], [-sn(y, th) for y in yy], 0.05, 0.016, 0.0, 'CkCoat', T_CKD)
        th = rad(84) * s
        P_sweep(mb, [spi(y, th, 0.036) for y in yy], [-sn(y, th) for y in yy], 0.012, 0.006, 0.0, 'Metal', T_GUN)
        zc = 0.312
        def wf(y, back=0.016):
            return Fr(V(s * (ck_hw(y, zc, 0.035) - back), y, zc), Raxes((0, -s, 0), (0, 0, 1)))
        if s > 0:
            cbp['a'] = ck_cbpanel(mb, wf(1.84), 0.56, 0.112, 16, 0, 'ESS DC BUS  /  AC BUS 1')
            # utility panel + map light forward of the breakers
            F = wf(2.30)
            wbox(mb, F.pt(0, 0, -0.007), (0.228, 0.014, 0.12), 'CkCoat', T_CKC, 0.002, rot=F.R, wear=1.0)
            P = Plate(mb, F.sub(0, 0, 0.001), 0.22, 0.112, thick=0.001)
            P.corners(0.005, 0.0024); P.text('UTILITY', -0.098, 0.047, 0.0056, anchor='l')
            P.knob(-0.075, -0.004, 'MAP LT', r=0.0095, ticks=5, ang=-40)
            P.toggle(-0.034, -0.004, 'NVG', 'NORM'); P.toggle(-0.006, -0.004, 'DTU', 'OFF', pos=-1)
            P.rect(0.056, 0.004, 0.07, 0.022, (0.012, 0.012, 0.014), r=0.002, hgt=-1.0); P.text('DATA CART', 0.056, 0.024, 0.0048)
            P.lamp(0.056, -0.026, None, 'CkLitG', r=0.003); P.text('READY', 0.034, -0.026, 0.0045, C_DIM)
            a = F.pt(-0.075, 0.062, 0.0)
            CK_tube(mb, ck_path([a, a + F.n * 0.05 + V(0, 0, 0.03), a + F.n * 0.09 + V(0, 0.04, 0.06), a + F.n * 0.12 + V(0, 0.07, 0.05)], 4, 0.45), 0.005, 'CkRubber', T_KNOB, seg=6)
            e = a + F.n * 0.12 + V(0, 0.07, 0.05)
            P_revolve(mb, e, V(-0.5, 0.6, -0.5), [(-0.012, 0.008), (0.02, 0.014), (0.024, 0.012)], 'CkSatin', T_BEZ, seg=10)
            # canopy door latch lever on the sill
            b = spi(2.02, rad(79), 0.06)
            CK_tube(mb, ck_path([b, b + V(-0.022, 0, 0.0), b + V(-0.022, 0.09, 0.008)], 3, 0.4), 0.006, 'Metal', T_STEEL, seg=6)
            CK_tube(mb, [b + V(-0.022, 0.09, 0.008), b + V(-0.022, 0.155, 0.014)], 0.009, 'CkRubber', T_RED, seg=8)
            P_revolve(mb, b + V(0.01, 0, 0), V(-1, 0, 0), [(0, 0.016), (0.008, 0.016), (0.011, 0.011)], 'Metal', T_GUN, seg=10, cap0=False)
        else:
            cbp['b'] = ck_cbpanel(mb, wf(1.70), 0.30, 0.112, 8, 32, 'BATT / GEN')
            # emergency canopy release: hazard placard + striped D-handle
            F = wf(2.20)
            wbox(mb, F.pt(0, 0, -0.007), (0.268, 0.014, 0.12), 'CkCoat', T_CKC, 0.002, rot=F.R, wear=1.0)
            P = Plate(mb, F.sub(0, 0, 0.001), 0.26, 0.112, thick=0.001)
            P.stripes(0, 0, 0.252, 0.104, per=0.011, r=0.004); P.rect(0, 0, 0.232, 0.084, C_BLK, r=0.003)
            P.text('EMERG CANOPY', -0.044, 0.024, 0.0085, C_YEL, emi=0.3)
            P.text('LIFT GUARD', -0.044, 0.004, 0.006); P.text('PULL HANDLE AFT', -0.044, -0.01, 0.006)
            P.text('DO NOT USE IN FLIGHT', -0.044, -0.028, 0.0048, C_RED, emi=0.3)
            P.corners(0.0045, 0.0022)
            a = F.pt(0.045, -0.02, 0.0); b = F.pt(0.105, -0.02, 0.0)
            CK_tube(mb, ck_path([a, a + F.n * 0.034, b + F.n * 0.034, b], 3, 0.3), 0.0085, 'CkHazard', T_W, seg=8)
            for q in (a, b): P_revolve(mb, q, F.n, [(0, 0.014), (0.004, 0.014), (0.006, 0.01)], 'Metal', T_GUN, seg=8, cap0=False)
            F.box(mb, 0.075, 0.022, 0.012, 0.085, 0.012, 0.024, 'Paint', T_RED, 0.002)
            # grab handle on the sill
            b = spi(2.3, rad(-79), 0.05)
            CK_tube(mb, ck_path([b, b + V(0.035, 0, 0.01), b + V(0.035, 0.16, 0.01), b + V(0, 0.16, 0)], 3, 0.3), 0.007, 'Metal', T_GUN, seg=6)
        # cable looms under the sill into the instrument shroud + clamps
        for k, dz in enumerate((0.0, 0.012, -0.011)):
            pts = [V(s * (ck_hw(y, 0.39, 0.035) - 0.012 - 0.006 * (k % 2)), y, 0.388 + dz + 0.004 * sin(y * 9 + k)) for y in [1.45 + 0.1 * i for i in range(13)]]
            CK_tube(mb, pts, 0.0048 if k else 0.0062, 'CkRubber', (0.01, 0.01, 0.011) if k != 2 else (0.05, 0.035, 0.01), seg=5, cap=False)
        for y in (1.55, 1.95, 2.35):
            P_box(mb, V(s * (ck_hw(y, 0.39, 0.035) - 0.012), y, 0.388), (0.026, 0.012, 0.034), 'Metal', T_GUN, 0.002)
    # rear bulkhead dressing: extinguisher, first-aid kit, conduit
    yb = YG0 + 0.035
    P_revolve(mb, V(0.40, yb + 0.055, 0.0), V(0, 0, 1), [(0, 0.04), (0.012, 0.047), (0.19, 0.047), (0.215, 0.03), (0.23, 0.014), (0.26, 0.014)], 'Paint', T_RED, seg=12)
    P_box(mb, V(0.40, yb + 0.06, 0.275), (0.05, 0.03, 0.03), 'CkSatin', T_BEZ, 0.004)
    for z in (0.05, 0.16): P_box(mb, V(0.40, yb + 0.03, z), (0.11, 0.05, 0.016), 'Metal', T_GUN, 0.002)
    F = Fr(V(-0.40, yb + 0.062, 0.12), Raxes((1, 0, 0), (0, 0, 1)))
    wbox(mb, F.pt(0, 0, -0.03), (0.18, 0.06, 0.2), 'CkFabric', (0.06, 0.07, 0.04), 0.012, rot=F.R, wear=0.5)
    P = Plate(mb, F.sub(0, 0, 0.001), 0.08, 0.08, col=(0.72, 0.72, 0.68), thick=0, edge=False, ppm=900)
    P.rect(0, 0, 0.05, 0.016, (0.6, 0.06, 0.05)); P.rect(0, 0, 0.016, 0.05, (0.6, 0.06, 0.05))
    for s in (-1, 1):
        CK_tube(mb, [V(s * 0.3, yb + 0.02, -0.28), V(s * 0.3, yb + 0.02, 0.5), V(s * 0.33, yb + 0.02, 0.9)], 0.014, 'Metal', T_GUN, seg=6)
    return cbp


def ck_floor(mb):
    Ff = Fr(V(0, 0, -0.2945), Rtilt(rad(90)))
    first = None
    for s in (-1, 1):
        P = Plate(mb, Ff.sub(s * 0.205, 2.47, 0), 0.235, 0.50, ppm=800, col=(0.14, 0.142, 0.146), thick=0.004, share=first, cell=0.09)
        if first is None:
            first = P
            g = P._px(-P.w / 2 + 0.008, -P.h / 2 + 0.008, P.w / 2 - 0.008, P.h / 2 - 0.008); sl, xs, ys = g
            per = 0.012
            a = np.clip((np.sin(2 * pi * (xs + ys) / per) * np.sin(2 * pi * (xs - ys) / per) - 0.3) * 3, 0, 1)
            P._put(sl, a * 0.45, (0.3, 0.3, 0.31), hgt=1.2)
            P._put(sl, np.clip((CK['noise'][sl] - 0.5) * 3, 0, 0.5) * np.clip(1 - np.abs(ys - 0.02) / 0.2, 0, 1), (0.36, 0.36, 0.36))
            P.corners(0.008, 0.003)
    P = Plate(mb, Ff.sub(0, 2.19, 0), 0.16, 0.42, ppm=800, col=(0.14, 0.142, 0.146), thick=0.004, cell=0.09)
    P.corners(0.008, 0.003)
    P.rect(0, 0.03, 0.13, 0.13, (0.1, 0.1, 0.105), r=0.01); P.rect(0, 0.03, 0.13, 0.13, C_WEAR, r=0.01, line=0.001, alpha=0.6, hgt=-0.6)
    for a in (-1, 1):
        for b in (-1, 1): P.bolt(a * 0.055, 0.03 + b * 0.055, 0.004)
    # seat rails
    for s in (-1, 1):
        P_box(mb, V(s * 0.17, 1.78, -0.285), (0.03, 0.62, 0.03), 'Metal', T_GUN, 0.003)


def ck_pedals(mb):
    for s in (-1, 1):
        Fp = Fr(V(s * 0.17, 2.642, -0.165), Rtilt(rad(55)))
        Fp.box(mb, 0, 0.012, -0.007, 0.104, 0.12, 0.012, 'Metal', T_GUN, 0.003, wear=1.6)
        for k in range(5):
            Fp.box(mb, 0, -0.036 + k * 0.024, 0.001, 0.09, 0.008, 0.004, 'CkRubber', T_KNOB, 0.001)
        for a in (-1, 1):
            CK_tube(mb, [Fp.pt(a * 0.058, 0.0, -0.008), V(s * 0.17 + a * 0.058, 2.715, -0.275)], 0.008, 'Metal', T_GUN, seg=6)
        CK_tube(mb, [V(s * 0.17 - 0.075, 2.715, -0.275), V(s * 0.17 + 0.075, 2.715, -0.275)], 0.012, 'Metal', T_STEEL, seg=8)
        CK_tube(mb, [Fp.pt(0, 0.05, -0.012), V(s * 0.17, 2.73, -0.06)], 0.006, 'Metal', T_STEEL, seg=6)


T_FAB = (0.2, 0.19, 0.14)

def ck_seat(mb, y0, zp, fz=-0.30):
    """armoured bucket seat with fabric cushions; y0 = seat back plane, zp = pan height."""
    Rb = Matrix.Rotation(rad(9), 3, 'X')
    def bk(dz, dy=0.0): return V(0, y0 - 0.05 - 0.158 * dz + dy, zp + dz)
    wbox(mb, V(0, y0 + 0.215, zp - 0.045), (0.5, 0.5, 0.05), 'CkCoat', T_CKC, 0.008, wear=1.0)
    wbox(mb, bk(0.33), (0.5, 0.05, 0.76), 'CkCoat', T_CKC, 0.008, rot=Rb, wear=1.0)
    for s in (-1, 1):
        wbox(mb, V(s * 0.262, y0 + 0.11, zp + 0.14), (0.024, 0.36, 0.40), 'CkCoat', T_CKC, 0.008, wear=1.0)
        wbox(mb, bk(0.60, 0.07) + V(s * 0.262, 0, 0), (0.024, 0.16, 0.26), 'CkCoat', T_CKC, 0.008, rot=Rb, wear=1.0)
        # lap belt anchors + adjuster
        P_box(mb, V(s * 0.235, y0 + 0.10, zp + 0.05), (0.02, 0.05, 0.06), 'Metal', T_GUN, 0.004)
        # inertia reels at the top of the back
        CK_tube(mb, [bk(0.73, -0.02) + V(s * 0.07 - 0.03, 0, 0), bk(0.73, -0.02) + V(s * 0.07 + 0.03, 0, 0)], 0.028, 'Metal', T_GUN, seg=10)
        # legs to the rails
        for yy in (y0 + 0.04, y0 + 0.40):
            P_box(mb, V(s * 0.17, yy, (zp - 0.07 + fz) / 2), (0.03, 0.04, zp - 0.07 - fz), 'Metal', T_GUN, 0.004)
    P_box(mb, V(0, y0 + 0.225, zp + 0.012), (0.43, 0.44, 0.065), 'CkFabric', T_FAB, 0.022, seg=2)
    P_box(mb, bk(0.30, 0.045), (0.42, 0.05, 0.50), 'CkFabric', T_FAB, 0.02, rot=Rb, seg=2)
    P_box(mb, bk(0.685, 0.05), (0.24, 0.06, 0.17), 'CkFabric', T_FAB, 0.022, rot=Rb, seg=2)
    P_box(mb, bk(0.09, 0.05), (0.36, 0.045, 0.10), 'CkFabric', ck_worn(T_FAB, -0.25), 0.018, rot=Rb, seg=2)       # lumbar roll
    # height-adjust lever on the right
    CK_tube(mb, ck_path([V(0.285, y0 + 0.02, zp - 0.02), V(0.3, y0 + 0.2, zp + 0.0), V(0.3, y0 + 0.3, zp + 0.05)], 3, 0.3), 0.007, 'Metal', T_STEEL, seg=6)
    CK_tube(mb, [V(0.3, y0 + 0.3, zp + 0.05), V(0.3, y0 + 0.37, zp + 0.085)], 0.012, 'CkRubber', T_KNOB, seg=8)


# ------------------------------------------------------------------ flight controls (separate animated nodes)
CYC_PV = V(0, 2.22, -0.29)
CYC_AX = V(0, -0.215, 0.977)
CYC_G0 = CYC_PV + V(0, -0.095, 0.468)

def ck_cyclic(static):
    cy = MB(); pv = CYC_PV
    CK_tube(cy, ck_path([pv + V(0, 0, 0.02), pv + V(0, 0.005, 0.24), pv + V(0, -0.07, 0.40), pv + V(0, -0.097, 0.475)], 4, 0.45), 0.012, 'Metal', T_GUN, seg=8)
    prof = [(0.0, 0.058), (0.012, 0.06)]
    for k in range(5):
        prof += [(0.02 + k * 0.016, 0.052 - k * 0.0065), (0.028 + k * 0.016, 0.04 - k * 0.0052)]
    prof += [(0.105, 0.017), (0.115, 0.014)]
    P_revolve(cy, pv, V(0, 0, 1), prof, 'CkRubber', (0.013, 0.013, 0.014), seg=14, cap0=False, cap1=False)
    g0 = CYC_G0; ax = CYC_AX.normalized()
    # sculpted grip
    ts = (0.0, 0.012, 0.03, 0.055, 0.08, 0.1, 0.118, 0.13)
    rr = (0.014, 0.0195, 0.0205, 0.0185, 0.0195, 0.0215, 0.025, 0.027)
    CK_tube(cy, [g0 + ax * t + V(0, 0.004 * sin(t * 40), 0) for t in ts], list(rr), 'CkRubber', T_KNOB, seg=10, flat=(V(1, 0, 0), 0.84))
    CK_tube(cy, [g0 + ax * 0.012 + V(0, -0.012, 0), g0 + ax * 0.016 + V(0, -0.042, -0.004)], [0.02, 0.012], 'CkRubber', T_KNOB, seg=8, flat=(V(0, 0, 1), 0.5))   # palm rest
    # head with switches, angled toward the pilot
    hc = g0 + ax * 0.152 + V(0, 0.004, 0)
    Fh = Fr(hc, Rtilt(rad(58)))
    wbox(cy, hc, (0.06, 0.046, 0.058), 'CkSatin', T_BEZ, 0.009, rot=Fh.R, wear=1.3)
    d = 0.023
    Fh.rev(cy, 0.004, 0.01, d, [(0, 0.0095), (0.003, 0.0095), (0.0045, 0.006), (0.009, 0.0035), (0.0105, 0.0052), (0.012, 0.004)], 'Metal', (0.3, 0.3, 0.31), seg=10, cap0=False)   # trim hat
    Fh.rev(cy, -0.018, 0.012, d, [(0, 0.0075), (0.002, 0.0075), (0.002, 0.0058), (0.0055, 0.0058), (0.0065, 0.004)], 'Paint', T_RED, seg=10, cap0=False)   # weapon release
    Fh.rev(cy, 0.02, -0.01, d, [(0, 0.006), (0.004, 0.006), (0.005, 0.0045)], 'CkSatin', (0.05, 0.05, 0.055), seg=8, cap0=False)
    Fh.rev(cy, -0.016, -0.012, d, [(0, 0.0065), (0.0025, 0.0065), (0.004, 0.003), (0.008, 0.0028), (0.009, 0.004)], 'Metal', (0.3, 0.3, 0.31), seg=8, cap0=False)   # sensor slew
    Fh.box(cy, 0.022, 0.014, d + 0.002, 0.008, 0.014, 0.005, 'Paint', (0.4, 0.4, 0.38), 0.0015)                # rocker
    # trigger + guard on the forward side, pinky switch
    tb = g0 + ax * 0.112 + V(0, 0.026, 0)
    CK_tube(cy, [tb, tb + V(0, 0.016, -0.012), tb + V(0, 0.018, -0.04)], [0.006, 0.006, 0.0045], 'Paint', T_RED, seg=6, flat=(V(1, 0, 0), 0.6))
    CK_tube(cy, ck_path([tb + V(0, 0.004, 0.006), tb + V(0, 0.034, -0.008), tb + V(0, 0.03, -0.056), tb + V(0, 0.008, -0.062)], 3, 0.4), 0.003, 'Metal', T_GUN, seg=5)
    P_box(cy, g0 + ax * 0.04 + V(0, 0.022, 0), (0.012, 0.01, 0.016), 'Paint', (0.4, 0.4, 0.38), 0.002)
    ob = build(cy, 'Cyclic', origin=pv, parent='Cockpit', uvscale=4.0)
    # static base plate ring on the floor
    P_revolve(static, pv + V(0, 0, 0.004), V(0, 0, 1), [(0, 0.072), (0.006, 0.072), (0.009, 0.062)], 'Metal', T_GUN, seg=16, cap0=False)
    return ob


COL_PV = V(-0.287, 1.70, 0.02)
COL_D = V(0, 0.88, 0.475)

def ck_collective(static):
    co = MB(); pv = COL_PV; d = COL_D.normalized()
    CK_tube(co, [pv, pv + d * 0.37], 0.014, 'Metal', T_GUN, seg=8)
    P_revolve(co, pv + d * 0.355, d, [(0, 0.015), (0.005, 0.0215), (0.12, 0.0215), (0.126, 0.017)], 'CkRubber', T_KNOB, seg=12)
    for k in range(6):
        P_revolve(co, pv + d * (0.368 + k * 0.019), d, [(0, 0.0225), (0.006, 0.0225)], 'CkRubber', (0.03, 0.03, 0.032), seg=12, cap0=False, cap1=False)
    P_revolve(co, pv + d * 0.335, d, [(0, 0.019), (0.016, 0.019)], 'Metal', T_STEEL, seg=12)        # friction collar
    hc = pv + d * 0.545
    Fh = Fr(hc, Raxes((1, 0, 0), d))
    wbox(co, hc, (0.06, 0.042, 0.092), 'CkSatin', T_BEZ, 0.007, rot=Fh.R, wear=1.3)
    P = Plate(co, Fh.sub(0, 0, 0.0215), 0.05, 0.08, col=C_BLK, thick=0, ppm=1850, cell=0.1)
    P.toggle(-0.012, 0.022, 'SRCH', None, lsize=0.0046); P.toggle(0.012, 0.022, 'NVS', None, pos=-1, lsize=0.0046)
    Fh.rev(co, 0.0, -0.006, 0.0215, [(0, 0.0085), (0.003, 0.0085), (0.0045, 0.0055), (0.0085, 0.0032), (0.01, 0.0048)], 'Metal', (0.3, 0.3, 0.31), seg=10, cap0=False)
    P.text('LT SLEW', 0, -0.0185, 0.0042, C_DIM)
    Fh.rev(co, -0.012, -0.03, 0.0215, [(0, 0.006), (0.004, 0.006), (0.005, 0.0045)], 'Paint', T_RED, seg=8, cap0=False)
    Fh.rev(co, 0.012, -0.03, 0.0215, [(0, 0.006), (0.004, 0.006), (0.005, 0.0045)], 'CkSatin', (0.05, 0.05, 0.055), seg=8, cap0=False)
    Fh.box(co, 0.033, 0.01, 0.0, 0.008, 0.03, 0.012, 'Paint', (0.4, 0.4, 0.38), 0.002)
    ob = build(co, 'Collective', origin=pv, parent='Cockpit', uvscale=4.0)
    # static pivot bracket + gate
    for sx in (-1, 1):
        P_box(static, pv + V(sx * 0.022, 0, -0.02), (0.008, 0.07, 0.09), 'Metal', T_GUN, 0.003)
    CK_tube(static, [pv + V(-0.03, 0, 0), pv + V(0.03, 0, 0)], 0.012, 'Metal', T_STEEL, seg=8)
    P_box(static, pv + V(0, 0.02, -0.19), (0.05, 0.12, 0.26), 'CkCoat', T_CKC, 0.004)
    return ob


# ------------------------------------------------------------------ crew
def ck_hand(mb, c, ax, b, rg, wrap=1, tint=T_GLOVE):
    """gloved hand closed around a grip (centre c, axis ax, radius rg); b = direction from grip to palm. Returns wrist point."""
    ax = Vector(ax).normalized(); b = Vector(b); b = (b - ax * b.dot(ax)).normalized(); cc = ax.cross(b) * wrap
    R = Matrix((ax, b, cc)).transposed()
    P_sphere(mb, c + b * (rg + 0.017), (0.047, 0.021, 0.043), 'CkFabric', tint, seg=10, rings=6, rot=R)
    for i in range(4):
        o = ax * ((i - 1.5) * 0.0215)
        pts = [c + o + (b * cos(rad(a)) + cc * sin(rad(a))) * (rg + 0.008) for a in (30, 75, 125, 175, 222)]
        CK_tube(mb, pts, [0.011, 0.011, 0.0105, 0.0098, 0.009], 'CkFabric', tint, seg=6)
    o = ax * 0.036
    pts = [c + o + (b * cos(rad(a)) + cc * sin(rad(a))) * (rg + 0.009) for a in (-25, -70, -118)]
    CK_tube(mb, pts, [0.013, 0.012, 0.0105], 'CkFabric', tint, seg=6)
    return c + b * (rg + 0.04)


def ck_figure(body, head, hip, lh, rh, kneeboard=False, heel_dz=-0.485):
    """seated crew member. lh / rh: (grip centre, grip axis, palm direction, grip radius, elbow point, wrap)."""
    h = hip
    RG = ((0.0, -0.05, 0.165, 0.115), (0.005, 0.10, 0.155, 0.105), (0.02, 0.27, 0.18, 0.118), (0.035, 0.40, 0.19, 0.108),
          (0.045, 0.47, 0.15, 0.085), (0.05, 0.515, 0.062, 0.058))
    rings = []
    for (dy, dz, w, d) in RG:
        r = []
        for j in range(14):
            a = 2 * pi * j / 14
            r.append(h + V(w * math.copysign(abs(sin(a)) ** 0.8, sin(a)), dy + d * math.copysign(abs(cos(a)) ** 0.8, cos(a)), dz))
        rings.append(r)
    P_loft(body, rings, 'CkFabric', T_VEST, cap0=True, cap1=True, tintfn=lambda i, j: T_SUIT if i in (0, 5) else T_VEST)
    zs = [q[1] for q in RG]; fr = [q[0] + q[3] for q in RG]
    def yf(dz): return h.y + float(np.interp(dz, zs, fr))
    tp = (0.05, 0.06, 0.042)
    for x, dz, sz in ((-0.1, 0.17, (0.085, 0.04, 0.11)), (0.0, 0.2, (0.075, 0.035, 0.09)), (0.1, 0.17, (0.085, 0.04, 0.11)), (-0.095, 0.345, (0.065, 0.03, 0.09))):
        P_box(body, V(h.x + x, yf(dz) + 0.008, h.z + dz), sz, 'CkFabric', tp, 0.01, seg=2)
        P_box(body, V(h.x + x, yf(dz) + 0.012, h.z + dz + sz[2] * 0.3), (sz[0] + 0.004, sz[1], sz[2] * 0.42), 'CkFabric', T_VEST, 0.008)
    for s in (-1, 1):
        # harness
        A = V(h.x + s * 0.085, yf(0.44) + 0.002, h.z + 0.45)
        P_sweep(body, [A, V(h.x + s * 0.078, yf(0.3), h.z + 0.30), V(h.x + s * 0.03, yf(0.14), h.z + 0.135)], [V(0, 1, 0.2)] * 3, 0.044, 0.007, 0.004, 'CkFabric', T_STRAP)
        P_sweep(body, [V(h.x + s * 0.075, h.y - 0.14, h.z + 0.52), V(h.x + s * 0.08, h.y - 0.05, h.z + 0.505), V(h.x + s * 0.085, h.y + 0.07, h.z + 0.50), A],
                [V(0, 0, 1), V(0, 0, 1), V(0, 0.4, 1), V(0, 1, 0.3)], 0.044, 0.008, 0.004, 'CkFabric', T_STRAP)
        P_sweep(body, [V(h.x + s * 0.215, h.y - 0.01, h.z + 0.02), V(h.x + s * 0.14, yf(0.06) - 0.02, h.z + 0.08), V(h.x + s * 0.02, yf(0.11) + 0.002, h.z + 0.115)],
                [V(s * 0.7, 0.5, 0.5), V(s * 0.3, 0.9, 0.4), V(0, 1, 0.2)], 0.044, 0.007, 0.004, 'CkFabric', T_STRAP)
        # arm
        c, ax, b, rg, el, wrap = lh if s < 0 else rh
        sh = h + V(s * 0.205, 0.03, 0.43)
        wr = ck_hand(body, c, ax, b, rg, wrap)
        pts = ck_path([sh, el, wr], 4, 0.3); n = len(pts)
        rr = [0.06 - 0.014 * min(1, k / 3) - 0.008 * max(0, (k - 3) / (n - 4)) for k in range(n)]
        CK_tube(body, pts, rr, 'CkFabric', T_SUIT, seg=10)
        P_sphere(body, sh, 0.064, 'CkFabric', T_SUIT, seg=10, rings=6)
        dv = (wr - pts[-2]).normalized()
        CK_tube(body, [wr - dv * 0.05, wr - dv * 0.012, wr + dv * 0.012], [0.043, 0.044, 0.036], 'CkFabric', T_GLOVE, seg=10)
        # leg + boot
        hipj = h + V(s * 0.1, 0.02, 0.0); kn = h + V(s * 0.17, 0.47, 0.0)
        heel = h + V(s * 0.17, 0.75, heel_dz)
        al = V(0, cos(rad(35)), sin(rad(35))); un = V(0, -sin(rad(35)), cos(rad(35)))
        an = heel + al * 0.06 + un * 0.11
        pts = ck_path([hipj, kn, an], 4, 0.2); n = len(pts)
        rr = [0.09 - 0.022 * min(1, k / 3) - 0.014 * max(0, (k - 3) / (n - 4)) for k in range(n)]
        CK_tube(body, pts, rr, 'CkFabric', T_SUIT, seg=10)
        P_box(body, heel + al * 0.135 + un * 0.045, (0.1, 0.285, 0.09), 'CkRubber', T_BOOT, 0.03, rot=Matrix.Rotation(rad(35), 3, 'X'), seg=2)
        sd = (kn - an).normalized()
        CK_tube(body, [an - sd * 0.03, an + sd * 0.1, an + sd * 0.11], [0.054, 0.057, 0.052], 'CkRubber', T_BOOT, seg=10)
        mid = hipj + (kn - hipj) * 0.5
        P_box(body, mid + V(s * 0.07, 0, 0.035), (0.03, 0.15, 0.11), 'CkFabric', ck_worn(T_SUIT, -0.2), 0.008)        # thigh pocket
        if kneeboard and s > 0:
            c0 = hipj + (kn - hipj) * 0.66 + V(-0.01, 0, 0.083)
            F = Fr(c0, Rtilt(rad(89)))
            wbox(body, F.pt(0, 0, 0.0), (0.118, 0.01, 0.168), 'CkSatin', T_BEZ, 0.003, rot=F.R, wear=1.0)
            P = Plate(body, F.sub(0, -0.006, 0.0056), 0.104, 0.142, col=(0.74, 0.73, 0.66), thick=0, edge=False, ppm=1500, cell=0.08)
            ink = (0.08, 0.08, 0.1)
            P.text('MISSION CARD', 0, 0.06, 0.0075, ink, emi=0, eng=0)
            P.line(-0.046, 0.052, 0.046, 0.052, 0.0008, ink)
            for k, t in enumerate(('CALLSIGN  WARDEN 2-1', 'FARP  GRID 44 17', 'TOT  +08 MIN', 'VHF 124.50  FM 38.25', 'BINGO  620', 'RTB  HDG 240 / 12 KM')):
                P.text(t, -0.046, 0.04 - k * 0.0125, 0.0058, ink, emi=0, anchor='l', eng=0)
            P.rect(0, -0.048, 0.092, 0.028, ink, r=0.001, line=0.0008)
            for k in range(1, 4): P.line(-0.046 + k * 0.023, -0.062, -0.046 + k * 0.023, -0.034, 0.0006, ink)
            F.box(body, 0, 0.076, 0.008, 0.07, 0.014, 0.008, 'Metal', T_STEEL, 0.002)
            P_torus(body, c0 - V(0, 0, 0.082), (kn - hipj), 0.08, 0.006, 'CkFabric', T_STRAP, seg=14, rseg=4)
    P_revolve(body, V(h.x, yf(0.11) + 0.006, h.z + 0.115), V(0, 1, 0.2), [(0, 0.03), (0.008, 0.03), (0.011, 0.022)], 'Metal', T_GUN, seg=10, cap0=False)
    # head (separate mesh for the pilot so the game can hide it in first person)
    hc = h + V(0, 0.10, 0.70)
    P_cyl(head, h + V(0, 0.05, 0.5), hc + V(0, -0.02, -0.08), 0.05, 'CkFabric', T_SUIT, seg=8)
    P_sphere(head, hc, (0.118, 0.135, 0.125), 'Paint', T_HELM, seg=16, rings=10)
    P_sphere(head, hc + V(0, 0.045, -0.012), (0.1, 0.1, 0.075), 'Lens', T_W, seg=14, rings=8)
    P_sphere(head, hc + V(0, 0.03, 0.035), (0.108, 0.115, 0.09), 'Paint', ck_worn(T_HELM, -0.3), seg=14, rings=8)      # visor housing
    P_box(head, hc + V(0, 0.095, -0.085), (0.09, 0.07, 0.07), 'CkRubber', T_BLACK, 0.02)
    for s in (-1, 1):
        P_cyl(head, hc + V(s * 0.1, 0.0, -0.03), hc + V(s * 0.128, 0.0, -0.03), 0.05, 'Paint', T_HELM, seg=10)
    P_box(head, hc + V(0, 0.118, 0.06), (0.05, 0.03, 0.035), 'CkSatin', T_BEZ, 0.006)                                   # sight / NVG mount
    P_cyl(head, hc + V(-0.11, 0.02, -0.06), hc + V(-0.05, 0.12, -0.09), 0.006, 'Paint', T_BLACK, seg=5)
    CK_tube(head, ck_path([hc + V(0.04, 0.12, -0.11), hc + V(0.08, 0.12, -0.22), h + V(0.1, 0.1, 0.4)], 3, 0.4), 0.014, 'CkRubber', T_BLACK, seg=6)


# ------------------------------------------------------------------ gunner station (front seat, seen from outside)
def ck_gunner(mb, pl_l, pl_r):
    ck_seat(mb, 3.38, -0.30, fz=-0.68)
    FG = Fr(V(0, 4.32, 0.02), Rtilt(rad(20)))
    wbox(mb, FG.pt(0, 0, -0.012), (0.74, 0.02, 0.30), 'CkCoat', T_CKB, 0.003, rot=FG.R, wear=1.0)
    FG.box(mb, 0, 0.166, 0.045, 0.78, 0.026, 0.16, 'CkRubber', (0.012, 0.012, 0.013), 0.008)
    S = Plate(mb, FG, 0.2, 0.2, ppm=640, col=(0.02, 0.07, 0.035), geo=False, edge=False)
    G = (0.3, 1.0, 0.45)
    S.rect(0, 0, 0.19, 0.19, (0.03, 0.1, 0.05), r=0.004)
    for k in range(-3, 4): S.line(-0.09, k * 0.025 + 0.004 * k * k, 0.09, k * 0.025 - 0.003 * k, 0.0012, (0.05, 0.2, 0.09), emi=0.6)
    S.rect(0, 0, 0.05, 0.036, G, line=0.0016, emi=1.0); S.line(-0.07, 0, -0.03, 0, 0.0016, G, emi=1.0); S.line(0.03, 0, 0.07, 0, 0.0016, G, emi=1.0)
    S.line(0, 0.022, 0, 0.06, 0.0016, G, emi=1.0); S.line(0, -0.022, 0, -0.06, 0.0016, G, emi=1.0)
    S.text('TGT 04', -0.09, 0.08, 0.014, G, emi=1.0, anchor='l', eng=0); S.text('RNG 3.4', 0.09, 0.08, 0.014, G, emi=1.0, anchor='r', eng=0)
    S.text('LSR ARM', -0.09, -0.08, 0.014, G, emi=1.0, anchor='l', eng=0); S.text('x4', 0.09, -0.08, 0.014, G, emi=1.0, anchor='r', eng=0)
    for s in (-1, 1):
        ck_mfd(mb, FG.sub(s * 0.24, -0.012, 0), 0.25, 0.2, 0.024, None, None, share=CK['mfd_plate'], screen=S)
    ck_dial(mb, FG, 0, 0.098, 0.035, share=CK['dial_kts'])
    # sight unit: eyepiece hood, housing, hand grips
    wbox(mb, V(0, 4.33, 0.16), (0.2, 0.2, 0.17), 'CkSatin', T_BEZ, 0.012, wear=1.2)
    P_revolve(mb, V(0, 4.26, 0.2), V(0, -0.88, 0.47), [(0, 0.05), (0.2, 0.05), (0.27, 0.066), (0.3, 0.07), (0.3, 0.056), (0.22, 0.04)], 'CkRubber', T_BLACK, seg=14, cap0=False, cap1=False)
    for s in (-1, 1):
        CK_tube(mb, ck_path([V(s * 0.1, 4.3, 0.1), V(s * 0.155, 4.22, 0.02), V(s * 0.155, 4.13, 0.02)], 3, 0.4), 0.012, 'Metal', T_GUN, seg=6)
        CK_tube(mb, [V(s * 0.155, 4.16, -0.03), V(s * 0.155, 4.10, 0.035), V(s * 0.155, 4.07, 0.095)], [0.02, 0.021, 0.024], 'CkRubber', T_KNOB, seg=8)
        P_box(mb, V(s * 0.155, 4.06, 0.11), (0.04, 0.04, 0.035), 'CkSatin', T_BEZ, 0.006)
        x0, x1 = (0.27, 0.46) if s > 0 else (-0.46, -0.27)
        prism(mb, [(3.46, -0.68), (3.46, -0.15), (4.25, -0.15), (4.25, -0.68)], x0, x1, 'CkCoat', T_CKC, wear=1.0)
        Ft = Fr(V(s * 0.365, 0, -0.147), Rtilt(rad(90)))
        ck_stack(mb, Ft, 3.5, (CK_LEFT if s < 0 else CK_RIGHT)[:4], pl_l if s < 0 else pl_r)
        yy = [3.42 + 0.1 * k for k in range(9)]; th = rad(98) * s
        P_sweep(mb, [spi(y, th, 0.036) for y in yy], [-sn(y, th) for y in yy], 0.05, 0.014, 0.0, 'CkCoat', T_CKD)


# ------------------------------------------------------------------ assembly
def build_cockpit():
    mb = MB(); DEF = []
    ck_main_panel(mb, DEF)
    ck_coaming(mb)
    pl_l = ck_console(mb, -1); pl_r = ck_console(mb, 1)
    ck_pedestal(mb); ck_walls(mb); ck_floor(mb); ck_pedals(mb)
    ck_seat(mb, 1.6, 0.12)
    # bulkhead / armour between the cockpits
    P_box(mb, V(0, 2.98, 0.0), (0.9, 0.5, 0.72), 'CkCoat', T_CKD, 0.02)
    # standby compass on the canopy arch
    P_box(mb, V(0, 2.52, 1.195), (0.06, 0.05, 0.045), 'CkSatin', T_BEZ, 0.01)
    P_revolve(mb, V(0, 2.494, 1.195), V(0, -1, 0), [(0, 0.017)], 'Lens', T_W, seg=10)
    ck_gunner(mb, pl_l, pl_r)
    cyc = MB(); col = MB()
    # the static parts of the controls go into the cockpit mesh, so build the animated nodes after it
    P_revolve(mb, CYC_PV + V(0, 0, 0.004), V(0, 0, 1), [(0, 0.072), (0.006, 0.072), (0.009, 0.062)], 'Metal', T_GUN, seg=16, cap0=False)
    pv = COL_PV
    for sx in (-1, 1):
        P_box(mb, pv + V(sx * 0.022, 0, -0.02), (0.008, 0.07, 0.09), 'Metal', T_GUN, 0.003)
    CK_tube(mb, [pv + V(-0.03, 0, 0), pv + V(0.03, 0, 0)], 0.012, 'Metal', T_STEEL, seg=8)
    P_box(mb, pv + V(0, 0.02, -0.19), (0.05, 0.12, 0.26), 'CkCoat', T_CKC, 0.004)
    build(mb, 'Cockpit', parent='Body', uvscale=4.0)

    for it in DEF:
        if it[0] == 'mfd':
            _k, nm, Fs, hs = it
            q = MB()
            ids = [q.addv(Fs.pt(a, b, 0), T_W) for a, b in ((-hs, -hs), (hs, -hs), (hs, hs), (-hs, hs))]
            q.addf(ids, nm, [(0, 0), (1, 0), (1, 1), (0, 1)])
            build(q, nm, origin=Fs.pt(0, 0, 0), rot=Fs.R, parent='Cockpit')
        elif it[0] == 'warn':
            _k, nm, F, u, lw = it
            q = MB()
            F.box(q, u, 0, 0.0027, lw, 0.028, 0.005, nm, T_W, 0.0015)
            build(q, nm, origin=F.pt(u, 0, 0.0027), rot=F.R, parent='Cockpit')
        elif it[0] == 'needles':
            for nm, (F, u, v, r) in it[1].items():
                ck_needle(nm, F, u, v, r)
        elif it[0] == 'horizon':
            ck_horizon(it[1], it[2])
    ck_cyclic(MB()); ck_collective(MB())
    # HUD combiner
    hg = MB()
    Rg = Matrix.Rotation(rad(-18), 3, 'X')
    cgl = V(0, 2.5, 0.915)
    ids = [hg.addv(cgl + Rg @ V(a, 0, b), T_W) for a, b in ((-0.085, -0.07), (0.085, -0.07), (0.085, 0.07), (-0.085, 0.07))]
    hg.addf(ids, 'Glass', [(0, 0), (1, 0), (1, 1), (0, 1)])
    build(hg, 'HUDGlass', origin=cgl, parent='Cockpit')
    # crew
    pb = MB(); ph = MB()
    cd = COL_D.normalized(); cax = CYC_AX.normalized()
    lh = (COL_PV + cd * 0.415, cd, V(0.25, -0.3, 1.0), 0.0215, V(-0.325, 1.72, 0.39), -1)
    rh = (CYC_G0 + cax * 0.075, cax, V(0.6, -0.8, 0.1), 0.02, V(0.255, 1.86, 0.40), 1)
    ck_figure(pb, ph, V(0, 1.72, 0.2), lh, rh, kneeboard=True)
    build(pb, 'Pilot', parent='Cockpit', uvscale=6.0)
    build(ph, 'PilotHead', parent='Pilot', uvscale=4.0)
    gb = MB()
    ck_figure(gb, gb, V(0, 3.5, -0.22), (V(-0.155, 4.10, 0.035), V(0, -0.45, 0.9), V(0, -1, -0.3), 0.021, V(-0.3, 3.72, -0.02), -1),
              (V(0.155, 4.10, 0.035), V(0, -0.45, 0.9), V(0, -1, -0.3), 0.021, V(0.3, 3.72, -0.02), 1), heel_dz=-0.455)
    build(gb, 'Gunner', parent='Cockpit', uvscale=6.0)
    empty('PilotEye', EYE, 'Body')
    empty('GunnerEye', V(0, 3.69, 0.5), 'Body')
    ck_atlas_finish()
