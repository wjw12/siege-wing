# Blender Bridge

> **Feel free to modify the bridge** (`C:\Users\shaoy\claude_blender\bridge.py`) if some Blender interaction or feature is needed. After editing it, re-run it in Blender's Scripting tab. Re-running is safe because it replaces the old timer.

A file-based bridge that lets code running in WSL (or anything else) execute Python inside a running Blender instance on Windows. It uses files rather than a network socket because WSL runs in NAT networking mode, which makes Windows ports hard to reach.

## Paths

| What | Windows | WSL |
|---|---|---|
| Bridge script | `C:\Users\shaoy\claude_blender\bridge.py` | `/mnt/c/Users/shaoy/claude_blender/bridge.py` |
| Inbox | `C:\Users\shaoy\claude_blender\inbox\` | `/mnt/c/Users/shaoy/claude_blender/inbox/` |
| Output dir (convention) | `C:\Users\shaoy\claude_blender\` | `/mnt/c/Users/shaoy/claude_blender/` |

## Starting it

1. In Blender, open the **Scripting** tab.
2. Click **Open**, choose `bridge.py`, then click **Run Script**.
3. The bridge stays active until Blender is closed. Run it again after each restart.

## How it works

- Every 0.5 s, a `bpy.app.timers` callback scans the inbox for `*.py` files, in sorted name order.
- Each file is read, deleted, and `exec`'d on Blender's main thread with `bpy` already in scope.
- When a script finishes, the bridge writes `<name>.out` to the inbox. Its first line is `OK` or `ERROR`, and on error the traceback follows.

## Sending a command (important rules)

1. **Write atomically.** Blender can pick up a file before WSL has finished writing it, and it then runs an empty script that still reports `OK`. Always write to a non-`.py` name and rename it when done:
   ```bash
   cd /mnt/c/Users/shaoy/claude_blender/inbox
   cat > job.tmp <<'EOF'
   # python code here
   EOF
   mv job.tmp job.py
   ```
2. **Don't rely on `print`.** stdout isn't captured in practice, so `.out` contains only `OK`. Write results to a file yourself:
   ```python
   import json
   D = r"C:\Users\shaoy\claude_blender"
   open(D + r"\info.json", "w").write(json.dumps({...}))
   ```
3. **Wait for the `.out` file** before reading results. Long jobs such as renders block Blender's UI until they finish, and the `.out` file only appears afterwards. Also check that the file has a non-zero size before reading it.
4. Delete old `.out` and result files before re-sending a job with the same name, so stale output isn't mistaken for new output.

## Recipes

### Inspect the scene
```python
import json
D = r"C:\Users\shaoy\claude_blender"
s = bpy.context.scene
info = {"version": bpy.app.version_string, "file": bpy.data.filepath,
        "engine": s.render.engine,
        "res": [s.render.resolution_x, s.render.resolution_y],
        "camera": s.camera.name if s.camera else None,
        "objects": [(o.name, o.type, list(o.location)) for o in s.objects]}
open(D + r"\info.json", "w").write(json.dumps(info, indent=1))
```

### Viewport snapshot (fast, OpenGL)
```python
D = r"C:\Users\shaoy\claude_blender"
s = bpy.context.scene
old = s.render.filepath
s.render.filepath = D + r"\viewport.png"
win = bpy.context.window_manager.windows[0]
area = next(a for a in win.screen.areas if a.type == "VIEW_3D")
region = next(r for r in area.regions if r.type == "WINDOW")
with bpy.context.temp_override(window=win, area=area, region=region):
    bpy.ops.render.opengl(write_still=True)
s.render.filepath = old
```

### Full render from the camera
```python
D = r"C:\Users\shaoy\claude_blender"
s = bpy.context.scene
old = s.render.filepath
s.render.filepath = D + r"\render.png"
bpy.ops.render.render(write_still=True)
s.render.filepath = old
```
The resulting PNG can be viewed from WSL at `/mnt/c/Users/shaoy/claude_blender/render.png`.

### Add an object with a material
```python
bpy.ops.mesh.primitive_uv_sphere_add(radius=1, location=(2, 0, 1))
obj = bpy.context.active_object
mat = bpy.data.materials.new("Red")
mat.use_nodes = True
mat.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (1, 0, 0, 1)
obj.data.materials.append(mat)
```

### Save / export
```python
bpy.ops.wm.save_as_mainfile(filepath=r"C:\Users\shaoy\game\scene.blend")
bpy.ops.export_scene.gltf(filepath=r"C:\Users\shaoy\game\model.glb")
```

## Notes and caveats

- Any process that can write a `.py` file into the inbox can run arbitrary code in Blender. Keep the folder private.
- Operators that need a UI context (`bpy.ops.view3d.*`, `render.opengl`, etc.) need `bpy.context.temp_override(...)` with a real window, area and region, as in the snapshot recipe.
- Scripts run on the main thread, so a long-running script freezes Blender until it returns.
- Ideas for extending the bridge: capture `print` by injecting a custom `print` into the exec globals, write a `.done` marker after `.out`, add a TCP listener (requires WSL mirrored networking or binding to `0.0.0.0` plus a firewall rule), or add an "always snapshot after each job" option.
