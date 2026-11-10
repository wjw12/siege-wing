# Vegetation previews: blender.exe -b -P trees_preview.py -- [glb path] [single] [grove] [sheet] [lod]
#   single -> preview/tree_<name>.png  (each tree alone, eye level, ~15 m away, warm low sun)
#   grove  -> preview/grove.png        (mixed grove from a low helicopter angle: 40 m up, looking 25 deg down)
#   sheet  -> preview/tree_sheet*.png  (line-up for quick iteration)   lod -> preview/tree_lod.png (full vs LOD at distance)
import bpy, math, sys, random
from mathutils import Vector
ROOT = r"C:\Users\shaoy\game"
PREV = ROOT + r"\tools\blender\preview"
args = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
glb = next((a for a in args if a.lower().endswith('.glb')), ROOT + r"\assets\models\village.glb")
which = [a for a in args if not a.lower().endswith('.glb')] or ['single', 'grove']
tag = next((a[4:] for a in which if a.startswith('tag=')), '')
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=glb)
sc = bpy.context.scene
src = {o.name: o for o in sc.objects if o.parent is None and o.name.startswith(('Tree_', 'Bush_'))}
for o in list(sc.objects):
    if o.parent is None and o.name not in src: o.location = (0, 9000, 0)
for m in bpy.data.materials: m.use_backface_culling = True      # the game material is single sided

w = bpy.data.worlds.new('W'); sc.world = w; w.use_nodes = True
bg = w.node_tree.nodes['Background']; bg.inputs[0].default_value = (0.5, 0.56, 0.75, 1); bg.inputs[1].default_value = 0.6
sun = bpy.data.objects.new('Sun', bpy.data.lights.new('Sun', 'SUN')); sc.collection.objects.link(sun)
sun.data.energy = 5.0; sun.data.color = (1.0, 0.76, 0.5); sun.data.angle = 0.03
bpy.ops.mesh.primitive_plane_add(size=900)
g = bpy.context.active_object
gm = bpy.data.materials.new('G'); gm.use_nodes = True
gm.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value = (0.1, 0.125, 0.045, 1)
gm.node_tree.nodes['Principled BSDF'].inputs['Roughness'].default_value = 1
g.data.materials.append(gm)
cam = bpy.data.objects.new('Cam', bpy.data.cameras.new('Cam')); sc.collection.objects.link(cam); sc.camera = cam
cam.data.clip_end = 3000
sc.render.engine = 'BLENDER_EEVEE'
try:
    sc.eevee.use_shadows = True; sc.eevee.use_raytracing = False
except Exception as e: print(e)
sc.view_settings.view_transform = 'AgX'

extra = []
def clear():
    for o in src.values(): o.location = (0, 9000, 0); o.rotation_euler = (0, 0, 0); o.scale = (1, 1, 1)
    for o in extra: bpy.data.objects.remove(o)
    extra.clear()
def inst(name, x, y, rot=0.0, s=1.0):
    o = bpy.data.objects.new(name + '_i', src[name].data); sc.collection.objects.link(o)
    o.location = (x, y, 0); o.rotation_euler = (0, 0, rot); o.scale = (s, s, s); extra.append(o); return o
def shot(name, cam_pos, target, lens, res, sun_az=None, sun_el=18):
    cam.location = Vector(cam_pos); t = Vector(target)
    cam.rotation_euler = (t - cam.location).to_track_quat('-Z', 'Y').to_euler()
    cam.data.lens = lens
    v = t - cam.location; a = math.atan2(v.x, v.y) if sun_az is None else sun_az
    sa = a + math.radians(180 - 62); e = math.radians(sun_el)     # sun behind-left of the camera, low
    sd = Vector((math.sin(sa) * math.cos(e), math.cos(sa) * math.cos(e), math.sin(e)))
    sun.rotation_euler = sd.to_track_quat('Z', 'Y').to_euler()
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.filepath = PREV + "\\" + name + tag + ".png"
    bpy.ops.render.render(write_still=True)

H = {'Tree_Pine_A': 17, 'Tree_Pine_B': 20, 'Tree_Oak_A': 12, 'Tree_Oak_B': 10, 'Tree_Birch': 12, 'Tree_Dead': 8, 'Bush_A': 1.3, 'Bush_B': 0.95}
if 'single' in which:
    for n, h in H.items():
        if n not in src: continue
        clear(); inst(n, 0, 0)
        short = n.replace('Tree_', '').lower()
        if n.startswith('Bush'): shot('tree_' + short, (0, -5.0, 1.5), (0, 0, h * 0.45), 35, (1000, 800))
        else: shot('tree_' + short, (0, -15, 1.7), (0, 0, h * 0.5), 26 if h > 13 else 30, (900, 1200))
if 'close' in which:      # crown detail from a hovering helicopter ~12 m off the foliage
    for n, h in H.items():
        if n not in src or n.startswith('Bush') : continue
        clear(); inst(n, 0, 0)
        shot('tree_close_' + n.replace('Tree_', '').lower(), (11, -14, h + 4), (0, 0, h * 0.62), 35, (1100, 800))
if 'sheet' in which:
    clear()
    xs = {'Tree_Pine_A': -12, 'Tree_Pine_B': -4, 'Tree_Dead': 3, 'Tree_Birch': 9}
    for n, x in xs.items(): inst(n, x, 0)
    shot('tree_sheet1', (-1.5, -30, 1.7), (-1.5, 0, 9.5), 30, (1500, 1100))
    clear()
    xs = {'Tree_Oak_A': -7.5, 'Tree_Oak_B': 6.5, 'Bush_A': -1.5, 'Bush_B': 1.0}
    for n, x in xs.items(): inst(n, x, -7 if n.startswith('Bush') else 0)
    shot('tree_sheet2', (0, -24, 1.7), (0, 0, 5.6), 28, (1500, 900))
if 'grove' in which:
    clear(); r = random.Random(11)
    names = ['Tree_Pine_A'] * 6 + ['Tree_Pine_B'] * 5 + ['Tree_Oak_A'] * 4 + ['Tree_Oak_B'] * 4 + ['Tree_Birch'] * 4 + ['Tree_Dead'] * 2 + ['Bush_A'] * 5 + ['Bush_B'] * 5
    pts = []
    for n in names:
        for _ in range(200):
            x, y = r.uniform(-34, 34), r.uniform(-20, 26)
            rad = 1.5 if n.startswith('Bush') else (5.5 if 'Oak' in n else 3.2)
            if all(math.hypot(x - a, y - b_) > rad + c for a, b_, c in pts): break
        pts.append((x, y, rad)); inst(n, x, y, r.uniform(0, 6.28), r.uniform(0.8, 1.25))
    d = 40 / math.tan(math.radians(25))
    shot('grove', (0, -d + 8, 40), (0, 8, 0), 38, (1600, 900))
if 'lod' in which:
    # full trees (left of each pair) vs their far LOD stand-ins at the swap distance (~300 m)
    clear()
    pairs = [('Tree_Pine_A', 'Tree_Pine_LOD', 1), ('Tree_Pine_B', 'Tree_Pine_LOD', 1), ('Tree_Oak_A', 'Tree_Oak_LOD', 1), ('Tree_Oak_B', 'Tree_Oak_LOD', 1), ('Tree_Birch', 'Tree_Oak_LOD', 0.8), ('Tree_Dead', 'Tree_Pine_LOD', 0.45)]
    x = -52
    for a, b_, s in pairs:
        inst(a, x, 0); inst(b_, x + 9, 0, 0, s); x += 21
    shot('tree_lod', (5, -300, 60), (5, 0, 7), 85, (1600, 500))
if 'lodcol' in which:
    # mean rendered colour (linear) + pixel coverage of each full tree vs its LOD, seen from the helicopter at the swap distance
    import numpy as np
    g.hide_render = True; sc.render.film_transparent = True; sc.view_settings.view_transform = 'Standard'
    for n in ['Tree_Pine_A', 'Tree_Pine_B', 'Tree_Pine_LOD', 'Tree_Oak_A', 'Tree_Oak_B', 'Tree_Oak_LOD', 'Tree_Birch']:
        acc = np.zeros(3); cov = 0.0
        for k, az in enumerate((0.0, 2.2, 4.2)):
            clear(); inst(n, 0, 0, az)
            shot('_lodcol', (0, -290, 75), (0, 0, 8), 600, (256, 256), sun_az=0.0)
            im = bpy.data.images.load(PREV + "\\_lodcol" + tag + ".png"); px = np.array(im.pixels[:]).reshape(-1, 4); bpy.data.images.remove(im)
            a = px[:, 3]; lin = np.where(px[:, :3] <= 0.04045, px[:, :3] / 12.92, ((px[:, :3] + 0.055) / 1.055) ** 2.4)
            acc += (lin * a[:, None]).sum(0) / max(a.sum(), 1e-6); cov += a.sum()
        print('LODCOL', n, [round(float(x), 4) for x in acc / 3], 'coverage', round(cov / 3, 1))
