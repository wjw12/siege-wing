import bpy, sys, json, os
HERE = os.path.dirname(os.path.abspath(__file__))
bpy.ops.wm.read_factory_settings(use_empty=True)
p = os.path.join(HERE, 'heli.glb') if os.path.basename(HERE) != 'blender' else os.path.join(os.path.dirname(os.path.dirname(HERE)), 'assets', 'models', 'heli.glb')
bpy.ops.import_scene.gltf(filepath=p)
out = []
tris = 0
for o in sorted(bpy.data.objects, key=lambda o: o.name):
    par = o.parent.name if o.parent else '-'
    info = ''
    if o.type == 'MESH':
        o.data.calc_loop_triangles(); n = len(o.data.loop_triangles); tris += n
        info = 'tris=%d mats=%s col=%s uv=%d' % (n, [m.name for m in o.data.materials], [c.name for c in o.data.color_attributes], len(o.data.uv_layers))
    mw = o.matrix_world
    out.append('%-16s %-6s parent=%-10s loc(blender)=(%.3f, %.3f, %.3f) %s' % (o.name, o.type, par, mw[0][3], mw[1][3], mw[2][3], info))
out.append('TOTAL TRIS %d  size %d' % (tris, os.path.getsize(p)))
out.append('materials: ' + ', '.join(sorted(m.name for m in bpy.data.materials)))
out.append('images: ' + ', '.join('%s %dx%d' % (i.name, i.size[0], i.size[1]) for i in bpy.data.images))
# canopy UV sanity: range, overlap (rasterised), texel density spread
c = bpy.data.objects.get('Canopy')
if c:
    import numpy as np
    me = c.data; uvl = me.uv_layers[0].data
    S = 512; grid = np.zeros((S, S), dtype=np.int32); dens = []; lo = [9, 9]; hi = [-9, -9]
    me.calc_loop_triangles()
    for t in me.loop_triangles:
        uv = [uvl[l].uv.copy() for l in t.loops]
        for u in uv:
            lo = [min(lo[0], u.x), min(lo[1], u.y)]; hi = [max(hi[0], u.x), max(hi[1], u.y)]
        a2 = abs((uv[1] - uv[0]).cross(uv[2] - uv[0])) / 2
        if t.area > 1e-9: dens.append(a2 / t.area)
        xs = [u.x * S for u in uv]; ys = [u.y * S for u in uv]
        for py in range(max(0, int(min(ys))), min(S, int(max(ys)) + 1)):
            for px in range(max(0, int(min(xs))), min(S, int(max(xs)) + 1)):
                x = px + 0.5; y = py + 0.5
                d = (ys[1] - ys[2]) * (xs[0] - xs[2]) + (xs[2] - xs[1]) * (ys[0] - ys[2])
                if abs(d) < 1e-12: continue
                w0 = ((ys[1] - ys[2]) * (x - xs[2]) + (xs[2] - xs[1]) * (y - ys[2])) / d
                w1 = ((ys[2] - ys[0]) * (x - xs[2]) + (xs[0] - xs[2]) * (y - ys[2])) / d
                if w0 > 0.02 and w1 > 0.02 and (1 - w0 - w1) > 0.02: grid[py, px] += 1
    out.append('Canopy UV: range u[%.3f,%.3f] v[%.3f,%.3f] coverage %.1f%% overlap_px %d density min/max ratio %.2f' % (
        lo[0], hi[0], lo[1], hi[1], 100.0 * (grid > 0).mean(), int((grid > 1).sum()), min(dens) / max(dens)))
open(os.path.join(HERE, 'heli_verify.txt'), 'w').write('\n'.join(out))
