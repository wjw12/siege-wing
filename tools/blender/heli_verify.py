import bpy, sys, json, os
bpy.ops.wm.read_factory_settings(use_empty=True)
p = r'C:\Users\shaoy\game\assets\models\heli.glb'
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
open(r'C:\Users\shaoy\game\tools\blender\heli_verify.txt', 'w').write('\n'.join(out))
