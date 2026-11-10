# Re-import props.glb and list hierarchy / stats.  blender -b -P props_verify.py
import bpy, os, json
from mathutils import Vector
HERE = os.path.dirname(os.path.abspath(__file__))
GLB = os.path.join(os.path.dirname(os.path.dirname(HERE)), 'assets', 'models', 'props.glb')
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=GLB)
bpy.context.view_layer.update()
def walk(o, d, out, st):
    info = o.name + ' [' + o.type + ']'
    if o.type == 'MESH':
        dg = bpy.context.evaluated_depsgraph_get()
        me = o.data
        me.calc_loop_triangles()
        st['tris'] += len(me.loop_triangles)
        st['mats'].update(m.name for m in me.materials)
        st['col'] &= len(me.color_attributes) > 0
        for v in me.vertices:
            w = o.matrix_world @ v.co
            for i in range(3):
                st['mn'][i] = min(st['mn'][i], w[i]); st['mx'][i] = max(st['mx'][i], w[i])
    else:
        r = o.rotation_euler if o.rotation_mode != 'QUATERNION' else o.rotation_quaternion.to_euler()
        info += ' loc(blender)=(%.2f,%.2f,%.2f) rotX=%.1fdeg' % (*o.location, r.x * 57.2958)
    out.append('  ' * d + info)
    for c in sorted(o.children, key=lambda c: c.name):
        walk(c, d + 1, out, st)
lines = []
for o in sorted([o for o in bpy.context.scene.objects if o.parent is None], key=lambda o: o.name):
    st = {'tris': 0, 'mats': set(), 'col': True, 'mn': [1e9] * 3, 'mx': [-1e9] * 3}
    out = []
    walk(o, 0, out, st)
    mn, mx = st['mn'], st['mx']
    lines.append('== %s tris=%d size_three(x,y,z)=(%.2f,%.2f,%.2f) three_y=[%.2f..%.2f] three_z=[%.2f..%.2f] mats=%s vcol=%s' % (
        o.name, st['tris'], mx[0] - mn[0], mx[2] - mn[2], mx[1] - mn[1], mn[2], mx[2], -mx[1], -mn[1], sorted(st['mats']), st['col']))
    lines += out[1:] if len(out) < 14 else [l for l in out[1:] if '[EMPTY]' in l]
open(os.path.join(HERE, 'props_verify.txt'), 'w').write('\n'.join(lines))
