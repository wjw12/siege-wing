#!/usr/bin/env python3
"""Stage a copy of the game for publishing as a Claude artifact (one link, many files).

usage: build_artifact.py OUT_DIR

Artifact limits this works around:
  - .glb is not a served type and each binary file must be <= 15 MB: models ship as .wasm byte chunks, rejoined in src/assets.js
  - the page file is wrapped in its own <!doctype><html><head><body> skeleton: index.html's wrapper tags are stripped
Writes OUT_DIR/files.json: {"batches": [[published paths...], ...]}, each batch under 255 files / 60 MB,
with assets/audio/manifest.json in the last batch so the game never sees a manifest whose files are missing.
"""
import os, sys, shutil, json, re
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.abspath(sys.argv[1]); PART = 14 * 1024 * 1024
if os.path.exists(OUT): shutil.rmtree(OUT)
os.makedirs(OUT)

def copy(rel):
    dst = os.path.join(OUT, rel); os.makedirs(os.path.dirname(dst), exist_ok=True); shutil.copyfile(os.path.join(ROOT, rel), dst)

def walk(rel, ok=lambda p: True):
    for d, _, fs in os.walk(os.path.join(ROOT, rel)):
        for f in sorted(fs):
            p = os.path.relpath(os.path.join(d, f), ROOT).replace(os.sep, '/')
            if '__pycache__' not in p and ok(p): yield p

core, audio = [], []
for p in list(walk('src')) + list(walk('vendor')) + list(walk('assets/textures')) + list(walk('assets/ui')):
    copy(p); core.append(p)

# models: artifacts don't serve .glb, so each model ships as raw byte chunks named .wasm (a served binary type,
# also keeping each file under the size limit) and src/assets.js fetches, joins and parses them
nparts = {}; os.makedirs(os.path.join(OUT, 'assets/models'), exist_ok=True)
for n in ['heli', 'soldiers', 'props', 'village']:
    data = open(os.path.join(ROOT, f'assets/models/{n}.glb'), 'rb').read()
    parts = [data[i:i + PART] for i in range(0, len(data), PART)]; nparts[n] = len(parts)
    for i, b in enumerate(parts):
        p = f'assets/models/{n}.part{i}.wasm'; open(os.path.join(OUT, p), 'wb').write(b); core.append(p)
a = os.path.join(OUT, 'src/assets.js'); s = open(a).read()
old = "loader.loadAsync(`./assets/models/${n === 'heli' ? 'heli' : n}.glb`)"
assert old in s, 'assets.js loader line changed; update build_artifact.py'
s = s.replace(old, "loadParts(loader, n)")
s += f"""
// artifact build: each .glb ships as byte chunks (.wasm is a served binary type) and is rejoined here
const NPARTS = {json.dumps(nparts)};
async function loadParts(loader, n) {{
  const bufs = await Promise.all(Array.from({{ length: NPARTS[n] }}, (_, i) => fetch(`./assets/models/${{n}}.part${{i}}.wasm`).then(r => {{ if (!r.ok) throw new Error('missing ' + n + ' part ' + i); return r.arrayBuffer(); }})));
  return loader.parseAsync(await new Blob(bufs).arrayBuffer(), './assets/models/');
}}
"""
open(a, 'w').write(s)

# audio: only files the manifest references
man = json.load(open(os.path.join(ROOT, 'assets/audio/manifest.json')))
refs = set(re.findall(r'"((?:music|sfx|vo)/[^"]+\.ogg)"', json.dumps(man)))
for p in walk('assets/audio', lambda p: p.endswith('.ogg') and '/_src/' not in p):
    if p[len('assets/audio/'):] in refs: copy(p); audio.append(p)
missing = [r for r in refs if not os.path.exists(os.path.join(ROOT, 'assets/audio', r))]
assert not missing, f'manifest references missing files: {missing[:5]}'
copy('assets/audio/manifest.json')

# page: strip the document wrapper (the artifact adds its own) and the dev-harness error hook
h = open(os.path.join(ROOT, 'index.html')).read()
h = re.sub(r'(?is)<!doctype html>\s*', '', h)
h = re.sub(r'(?is)<html[^>]*>\s*<head>', '', h)
h = re.sub(r'(?is)</head>\s*<body[^>]*>', '', h)
h = re.sub(r'(?is)</body>\s*</html>\s*$', '', h)
h = re.sub(r'(?is)<meta charset="utf-8">', '', h)
h = re.sub(r'(?s)<script>if\(/\[\?&\]\(shots\|dev\)/.*?</script>\n?', '', h)
open(os.path.join(OUT, 'index.html'), 'w').write(h.lstrip())

# batches
size = lambda p: os.path.getsize(os.path.join(OUT, p))
batches, cur, cs = [], [], 0
for p in core + audio + ['assets/audio/manifest.json']:
    if cur and (len(cur) >= 250 or cs + size(p) > 60e6): batches.append(cur); cur, cs = [], 0
    cur.append(p); cs += size(p)
batches.append(cur)
json.dump({'batches': batches}, open(os.path.join(OUT, 'files.json'), 'w'), indent=0)
for i, b in enumerate(batches): print(f'batch {i}: {len(b)} files, {sum(map(size, b)) / 1e6:.1f} MB')
print('largest:', max(((size(p), p) for b in batches for p in b))[1], max(size(p) for b in batches for p in b) / 1e6, 'MB')
