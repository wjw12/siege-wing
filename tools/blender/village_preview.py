# Imports village.glb, lays assets out, renders golden-hour previews + writes a verification listing.
import bpy, math, json, sys
from mathutils import Vector, Matrix
ROOT = r"C:\Users\shaoy\game"
PREV = ROOT + r"\tools\blender\preview"
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=ROOT + r"\assets\models\village.glb")
sc = bpy.context.scene
tops = [o for o in sc.objects if o.parent is None]
info = {}
def tri_count(o):
    n = 0
    if o.type == 'MESH':
        o.data.calc_loop_triangles(); n += len(o.data.loop_triangles)
    return n
for o in tops:
    objs = [o] + list(o.children_recursive)
    pts = [c.matrix_world @ Vector(v) for c in objs if c.type == 'MESH' for v in c.bound_box]
    info[o.name] = {
        'children': [c.name for c in o.children_recursive],
        'tris': sum(tri_count(c) for c in objs),
        'bbox_xyz_blender': [round(max(p[i] for p in pts) - min(p[i] for p in pts), 2) for i in range(3)],
        'min_z': round(min(p[2] for p in pts), 2),
        'materials': sorted({m.name for c in objs if c.type == 'MESH' for m in c.data.materials}),
        'color_attrs': [a.name for a in o.data.color_attributes] if o.type == 'MESH' else [],
        'uv': [u.name for u in o.data.uv_layers] if o.type == 'MESH' else [],
    }
json.dump(info, open(ROOT + r"\tools\blender\village_verify.json", 'w'), indent=1)

# make sure materials show vertex colours w/ backface culling so winding errors are visible
for m in bpy.data.materials:
    m.use_backface_culling = True

# world + sun (low golden hour)
w = bpy.data.worlds.new('W'); sc.world = w; w.use_nodes = True
bg = w.node_tree.nodes['Background']; bg.inputs[0].default_value = (0.45, 0.55, 0.8, 1); bg.inputs[1].default_value = 0.55
sun = bpy.data.objects.new('Sun', bpy.data.lights.new('Sun', 'SUN')); sc.collection.objects.link(sun)
sun.data.energy = 5.0; sun.data.color = (1.0, 0.78, 0.55); sun.data.angle = 0.02
sun.rotation_euler = (math.radians(70), 0, math.radians(125))
bpy.ops.mesh.primitive_plane_add(size=600)
g = bpy.context.active_object
gm = bpy.data.materials.new('G'); gm.use_nodes = True
gm.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value = (0.11, 0.14, 0.05, 1)
gm.node_tree.nodes['Principled BSDF'].inputs['Roughness'].default_value = 1
g.data.materials.append(gm)
cam = bpy.data.objects.new('Cam', bpy.data.cameras.new('Cam')); sc.collection.objects.link(cam); sc.camera = cam
cam.data.lens = 40; cam.data.clip_end = 2000
sc.render.engine = 'BLENDER_EEVEE'
try:
    sc.eevee.use_shadows = True; sc.eevee.use_raytracing = False
except Exception as e: print(e)
sc.render.resolution_x = 1500; sc.render.resolution_y = 900
sc.view_settings.view_transform = 'AgX'

by = {o.name: o for o in tops}
def place(names, spacing, y=0.0, x0=None):
    x = -(len(names) - 1) * spacing / 2 if x0 is None else x0
    for n in names:
        by[n].location = (x, y, 0); x += spacing
def hide_all():
    for o in tops: o.location = (0, 5000, 0)
def shot(name, target, dist, elev, azim, lens=40):
    t = Vector(target)
    e, a = math.radians(elev), math.radians(azim)
    cam.location = t + Vector((math.sin(a) * math.cos(e), -math.cos(a) * math.cos(e), math.sin(e))) * dist
    cam.rotation_euler = (t - cam.location).to_track_quat('-Z', 'Y').to_euler()
    cam.data.lens = lens
    sa = a - math.radians(65)
    sd = Vector((math.sin(sa) * math.cos(math.radians(20)), -math.cos(sa) * math.cos(math.radians(20)), math.sin(math.radians(20))))
    sun.rotation_euler = sd.to_track_quat('Z', 'Y').to_euler()
    sc.render.filepath = PREV + "\\village_" + name + ".png"
    bpy.ops.render.render(write_still=True)

which = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else ['houses', 'houses2', 'church', 'trees', 'small', 'far']
if 'houses' in which:
    hide_all(); place(['House_A', 'House_B'], 15)
    shot('houses', (0, 0, 3), 30, 24, -28)
if 'houses2' in which:
    hide_all(); place(['House_C', 'House_D'], 19)
    shot('houses2', (0, 0, 3), 34, 24, 30)
if 'backs' in which:
    hide_all(); place(['House_A', 'House_B', 'House_C', 'House_D'], 17)
    shot('backs', (0, 0, 3), 52, 30, 160)
if 'church' in which:
    hide_all(); place(['Chapel', 'Windmill'], 24)
    shot('church', (0, 0, 6), 46, 20, -30)
if 'church2' in which:
    hide_all(); place(['Chapel', 'Windmill'], 24)
    shot('church2', (0, 0, 6), 46, 25, 150)
if 'trees' in which:
    hide_all(); place(['Tree_Pine_A', 'Tree_Pine_B', 'Tree_Oak_A', 'Tree_Oak_B', 'Tree_Birch', 'Tree_Dead', 'Bush_A', 'Bush_B', 'Tree_Pine_LOD', 'Tree_Oak_LOD'], 9)
    shot('trees', (-18, 0, 7), 52, 12, -15, 40)
    shot('trees2', (22, 0, 5), 50, 30, -15, 40)
if 'small' in which:
    hide_all(); place(['Bridge', 'Well', 'Fence', 'StoneWall', 'Dock', 'Rock_A', 'Rock_B', 'Rock_C', 'Cliff_A'], 9, x0=-40)
    by['Bridge'].location = (-40, 0, 1.2); by['Dock'].location.z = 1.0
    shot('small', (-8, 0, 1.5), 52, 20, -20, 45)
    shot('bridge', (-40, 0, 2), 22, 14, -35, 40)
    shot('props', (-16, 0, 1), 16, 22, -20, 40)
if 'far' in which:
    # hamlet from a helicopter at ~200 m
    hide_all()
    import random
    r = random.Random(3)
    L = [('House_A', -20, 5, 0.3), ('House_B', 0, 0, 0), ('House_C', 22, 12, -0.2), ('House_D', -8, -22, 1.4), ('Chapel', 30, -25, 0.1), ('Windmill', -45, -10, 0.6),
         ('Well', 4, -11, 0), ('Tree_Oak_A', -30, 20, 0), ('Tree_Oak_B', 12, 28, 0), ('Tree_Pine_A', 45, 15, 0), ('Tree_Pine_B', 50, 22, 0), ('Tree_Birch', -14, -8, 0),
         ('Rock_C', 40, -5, 0), ('Bush_A', -3, 12, 0), ('Tree_Dead', 16, -12, 0), ('Tree_Pine_LOD', 56, 10, 0), ('Tree_Oak_LOD', -38, 30, 0), ('Cliff_A', -50, 30, 0)]
    for n, x, y, a in L:
        by[n].location = (x, y, 0); by[n].rotation_mode = 'XYZ'; by[n].rotation_euler = (0, 0, a)
    shot('far', (0, 0, 3), 190, 28, -20, 60)
    shot('mid', (0, 0, 3), 80, 22, -40, 40)
