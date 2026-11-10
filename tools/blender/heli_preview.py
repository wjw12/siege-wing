import bpy, math, os
from mathutils import Vector

def wire_vcol(MATS):
    for name, m in MATS.items():
        nt = m.node_tree
        b = nt.nodes['Principled BSDF']
        vc = nt.nodes.new('ShaderNodeVertexColor'); vc.layer_name = 'Col'
        mix = nt.nodes.new('ShaderNodeMix'); mix.data_type = 'RGBA'; mix.blend_type = 'MULTIPLY'
        mix.inputs[0].default_value = 1.0
        inp = b.inputs['Base Color']
        if inp.is_linked:
            src = inp.links[0].from_socket
            nt.links.new(src, mix.inputs[6])
        else:
            mix.inputs[6].default_value = inp.default_value[:]
        nt.links.new(vc.outputs['Color'], mix.inputs[7])
        nt.links.new(mix.outputs[2], inp)

def render(PREV, MATS, EYE, ARGS):
    wire_vcol(MATS)
    sc = bpy.context.scene
    for eng in ('BLENDER_EEVEE', 'BLENDER_EEVEE_NEXT'):
        try:
            sc.render.engine = eng; break
        except Exception: pass
    try: sc.eevee.taa_render_samples = 24
    except Exception: pass
    sc.render.resolution_x = 1280; sc.render.resolution_y = 720
    sc.render.image_settings.file_format = 'PNG'
    w = bpy.data.worlds.new('W'); sc.world = w; w.use_nodes = True
    bg = w.node_tree.nodes['Background']
    bg.inputs[0].default_value = (0.55, 0.68, 0.9, 1); bg.inputs[1].default_value = 0.9
    sun = bpy.data.lights.new('Sun', 'SUN'); sun.energy = 4.5; sun.color = (1.0, 0.9, 0.75); sun.angle = 0.02
    so = bpy.data.objects.new('Sun', sun); sc.collection.objects.link(so)
    so.rotation_euler = (math.radians(58), 0, math.radians(215))
    # ground
    me = bpy.data.meshes.new('G'); s = 200
    me.from_pydata([(-s, -s, -1.75), (s, -s, -1.75), (s, s, -1.75), (-s, s, -1.75)], [], [(0, 1, 2, 3)])
    gm = bpy.data.materials.new('G'); gm.use_nodes = True
    gm.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value = (0.25, 0.24, 0.2, 1)
    me.materials.append(gm)
    sc.collection.objects.link(bpy.data.objects.new('G', me))
    cam = bpy.data.cameras.new('C'); co = bpy.data.objects.new('C', cam); sc.collection.objects.link(co); sc.camera = co
    cam.clip_start = 0.02; cam.clip_end = 500
    views = {
        'front': ((8.5, 12.5, 2.6), (0, 0.5, 0.2), 38),
        'chase': ((0.0, -19, 6.5), (0, -1, 0.8), 62),
        'side': ((22, -1, 0.6), (0, -1, 0.2), 40),
        'rear': ((-7, -13, 2.0), (0, -3, 0.5), 45),
        'low': ((4.2, 9.0, -1.2), (0, 3.2, -0.3), 60),
        'hub': ((2.9, 0.6, 3.1), (0, 0, 1.95), 42),
        'top': ((0.01, -1, 24), (0, -1, 0), 40),
        'cockpit': (tuple(EYE), (0, EYE[1] + 5, EYE[2] - 0.9), 107),
        'cockpit_dn': (tuple(EYE), (0, EYE[1] + 2, EYE[2] - 1.2), 90),
        'panel': ((0, 2.25, 0.72), (0, 2.7, 0.55), 80),
        'tail': ((4.5, -11.5, 2.2), (0, -7.6, 0.8), 45),
        'mark_r': ((6, -4.3, 0.3), (0, -4.3, 0.2), 30),
        'mark_l': ((-6, -4.3, 0.3), (0, -4.3, 0.2), 30),
        'wing': ((5.5, 3.5, -0.2), (1.6, 0.2, -0.5), 40),
        'nose': ((2.6, 8.6, 0.3), (0, 5.2, -0.3), 40),
        'nacelle': ((4.2, -5.2, 2.2), (0.9, -1.2, 0.6), 40),
        'gear': ((3.4, 3.6, -1.0), (1.0, 1.7, -0.9), 40),
        'q34': ((13, 11.5, 4.5), (0, -1.0, 0.2), 42),
        'rq34': ((11, -14, 4.0), (0, -1.5, 0.3), 46),
        'under': ((5, 4, -1.6), (0, 0.5, -0.5), 55),
        'trotor': ((3.2, -9.6, 1.6), (0.2, -8.2, 1.0), 40),
        'canopy': ((3.6, 5.4, 1.9), (0, 3.0, 0.5), 40),
        'mid': ((6.5, -3.5, 1.2), (0.3, -1.6, 0.2), 38),
        'gun': ((1.9, 6.3, -1.3), (0, 4.5, -0.95), 42),
        'intake': ((2.6, 3.6, 1.5), (0.8, 0.9, 0.5), 38),
        'spine': ((2.2, -3.4, 2.6), (0.2, -0.6, 1.1), 42),
        'tailgear': ((2.4, -6.6, -0.6), (0, -7.7, -0.7), 42),
        'wingtop': ((4.2, 2.2, 1.6), (1.6, 0.2, -0.3), 40),
        'chase2': ((0.0, -15.5, 5.2), (0, -1.5, 0.6), 36),
    }
    want = None
    for a in ARGS:
        if a.startswith('views='): want = a[6:].split(',')
    hide = [a[5:] for a in ARGS if a.startswith('hide=')]
    for h in hide:
        for nm in h.split(','):
            for ob in bpy.data.objects:
                if ob.name.startswith(nm): ob.hide_render = True
    for name, (pos, tgt, fov) in views.items():
        if want and name not in want: continue
        if name.startswith('cockpit'):
            ob = bpy.data.objects.get('PilotHead')
            if ob: ob.hide_render = True
        co.location = pos
        d = Vector(tgt) - Vector(pos)
        co.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
        cam.sensor_fit = 'HORIZONTAL'; cam.angle = math.radians(fov)
        sc.render.filepath = os.path.join(PREV, 'heli_%s.png' % name)
        bpy.ops.render.render(write_still=True)
