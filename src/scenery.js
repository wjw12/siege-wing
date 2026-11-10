// Siege Wing — scenery: forests (LOD cells), village, camp, river, grass, rocks, rearm pad, cloth banners
import * as THREE from 'three';
import { G, V3, patchMaterial, mulberry32, clamp, smooth, lerp, TAU, fbm, GLSL_FOG, GLSL_FARSH } from './core.js';
import { terrain, L, riverX, forestDensity } from './terrain.js';
import { world } from './world.js';
import { assets } from './assets.js';
import { fx } from './fx.js';

const _m = new THREE.Matrix4(), _q = new THREE.Quaternion(), _p = new V3(), _s = new V3(), _e = new THREE.Euler(), _c = new THREE.Color();
const N = L.HM_N, HALF = L.HM_HALF;

// --- collect (geometry, material, localMatrix) for every mesh under a named node of a gltf ---
function parts(gltf, name) {
  const root = gltf.scene.getObjectByName(name); if (!root) { console.warn('missing asset node', name); return []; }
  root.updateWorldMatrix(true, true); const inv = new THREE.Matrix4().copy(root.matrixWorld).invert(); const out = [];
  root.traverse(o => { if (o.isMesh) out.push({ geometry: o.geometry, material: o.material, matrix: new THREE.Matrix4().multiplyMatrices(inv, o.matrixWorld), name: o.name }); });
  return out;
}
// merge all meshes under a node into ONE geometry (vertex colours carry albedo), baking local transforms
function mergedGeo(gltf, name, extra) {
  const ps = parts(gltf, name); let n = 0, ni = 0; for (const p of ps) { n += p.geometry.attributes.position.count; ni += p.geometry.index.count; }
  const pos = new Float32Array(n * 3), nor = new Float32Array(n * 3), col = new Float32Array(n * 3), uv = new Float32Array(n * 2), idx = new Uint32Array(ni); let o = 0, io = 0;
  const nm = new THREE.Matrix3();
  for (const p of ps) {
    const g = p.geometry, P = g.attributes.position, Nn = g.attributes.normal, Cc = g.attributes.color, U = g.attributes.uv; nm.getNormalMatrix(p.matrix);
    const rough = /Leaf|Thatch/i.test(p.material.name) ? 1 : 0;
    for (let i = 0; i < P.count; i++) {
      _p.fromBufferAttribute(P, i).applyMatrix4(p.matrix); pos[(o + i) * 3] = _p.x; pos[(o + i) * 3 + 1] = _p.y; pos[(o + i) * 3 + 2] = _p.z;
      _p.fromBufferAttribute(Nn, i).applyMatrix3(nm).normalize(); nor[(o + i) * 3] = _p.x; nor[(o + i) * 3 + 1] = _p.y; nor[(o + i) * 3 + 2] = _p.z;
      if (Cc) { col[(o + i) * 3] = Cc.getX(i); col[(o + i) * 3 + 1] = Cc.getY(i); col[(o + i) * 3 + 2] = Cc.getZ(i); } else col.fill(1, (o + i) * 3, (o + i) * 3 + 3);
      if (U) { uv[(o + i) * 2] = U.getX(i); uv[(o + i) * 2 + 1] = U.getY(i); }
    }
    const I = g.index; for (let i = 0; i < I.count; i++) idx[io + i] = I.getX(i) + o;
    o += P.count; io += I.count;
  }
  const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.BufferAttribute(pos, 3)); g.setAttribute('normal', new THREE.BufferAttribute(nor, 3)); g.setAttribute('color', new THREE.BufferAttribute(col, 3)); g.setAttribute('uv', new THREE.BufferAttribute(uv, 2)); g.setIndex(new THREE.BufferAttribute(idx, 1));
  g.computeBoundingSphere(); g.computeBoundingBox(); return g;
}

// instanced static props: list of {x,y,z,ry,s,tint}
function instanced(scene, geo, mat, list, cast = true) {
  if (!list.length) return null;
  const im = new THREE.InstancedMesh(geo, mat, list.length);
  let hasTint = false;
  list.forEach((t, i) => { _q.setFromEuler(_e.set(t.rx || 0, t.ry || 0, t.rz || 0, 'YXZ')); _m.compose(_p.set(t.x, t.y, t.z), _q, _s.set(t.s || 1, t.sy || t.s || 1, t.s || 1)); im.setMatrixAt(i, _m); if (t.tint !== undefined) { hasTint = true; } });
  if (hasTint) list.forEach((t, i) => im.setColorAt(i, _c.setHex(t.tint !== undefined ? t.tint : 0xffffff)));
  im.castShadow = cast; im.receiveShadow = true; im.instanceMatrix.needsUpdate = true; im.computeBoundingSphere(); im.updateMatrix(); im.matrixAutoUpdate = false; scene.add(im); return im;
}

import { settings as _set } from './input.js';
const TREE_R = ({ high: 250, medium: 180, low: 120 })[new URLSearchParams(location.search).get('q') || _set.quality] || 250;   // radius inside which trees draw at full detail
export const scenery = {
  mats: {}, trees: [], cells: [], houses: [], fires: [], banners: [], windsock: null, millSails: null,
  build(scene) {
    this.scene = scene; const rng = this.rng = mulberry32(2024);
    this._materials();
    this._forest(scene, rng);
    this._village(scene, rng);
    this._camp(scene, rng);
    this._pad(scene, rng);
    this._rocks(scene, rng);
    this._water(scene);
    this._grass(scene, rng);
  },

  _materials() {
    // generic vertex-coloured prop material (uv.x = heraldic tint mask → instanceColor)
    const prop = this.mats.prop = new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.88, metalness: 0, vertexColors: true });
    patchMaterial(prop, 'prop', sh => {
      sh.vertexShader = sh.vertexShader.replace('#include <common>', '#include <common>\nvarying float vTintM; varying vec3 vPW;').replace('#include <color_vertex>', `
        #if defined( USE_COLOR_ALPHA )
          vColor = vec4(1.0);
        #elif defined( USE_COLOR ) || defined( USE_INSTANCING_COLOR )
          vColor = vec3(1.0);
        #endif
        #ifdef USE_COLOR
          vColor *= color;
        #endif
        vTintM = uv.x;
        #ifdef USE_INSTANCING_COLOR
          vColor.xyz *= mix(vec3(1.0), instanceColor.xyz, clamp(uv.x, 0.0, 1.0));
        #endif`).replace('#include <begin_vertex>', '#include <begin_vertex>\n vPW = (modelMatrix * vec4(transformed, 1.0)).xyz;');
      sh.fragmentShader = sh.fragmentShader.replace('#include <common>', '#include <common>\nvarying vec3 vPW; uniform sampler2D uNoise;')
        .replace('#include <color_fragment>', '#include <color_fragment>\n diffuseColor.rgb *= 0.78 + 0.44 * texture2D(uNoise, vPW.xz * 0.21 + vPW.y * 0.17).b;');
    });
    const iron = this.mats.iron = prop.clone(); iron.metalness = 0.85; iron.roughness = 0.55; patchMaterial(iron, 'prop', prop.onBeforeCompile);
    // foliage with wind + rotor wash (uv.x = sway weight)
    const fol = this.mats.foliage = new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.9, metalness: 0, vertexColors: true });
    const windPatch = sh => {
      sh.vertexShader = sh.vertexShader.replace('#include <common>', '#include <common>\nuniform float uTime; uniform vec4 uHeli; varying vec3 vTW;')
        .replace('#include <begin_vertex>', /* glsl */`#include <begin_vertex>
        {
          #ifdef USE_INSTANCING
            vec3 ip = instanceMatrix[3].xyz; vec3 wpv = (instanceMatrix * vec4(transformed, 1.0)).xyz;
          #else
            vec3 ip = modelMatrix[3].xyz; vec3 wpv = (modelMatrix * vec4(transformed, 1.0)).xyz;
          #endif
          float w = uv.x; float ph = ip.x * 0.13 + ip.z * 0.17;
          vec2 sway = vec2(sin(uTime * 1.3 + ph + wpv.y * 0.2), cos(uTime * 1.05 + ph * 1.3)) * 0.16 * w + vec2(sin(uTime * 3.7 + wpv.x * 0.9 + wpv.z * 0.7), cos(uTime * 4.1 + wpv.z)) * 0.035 * w;
          vec3 dh = wpv - uHeli.xyz; float dl = length(dh.xz);
          float wash = uHeli.w * smoothstep(48.0, 6.0, dl) * step(-8.0, dh.y) * smoothstep(70.0, 10.0, -dh.y);
          sway += (dh.xz / max(dl, 1.0)) * wash * w * (0.9 + 0.5 * sin(uTime * 17.0 + wpv.x * 2.0 + wpv.z * 1.7));
          #ifdef USE_INSTANCING
            transformed.xz += (vec4(sway.x, 0.0, sway.y, 0.0) * instanceMatrix).xz / max(dot(instanceMatrix[0].xyz, instanceMatrix[0].xyz), 0.01);
          #else
            transformed.xz += sway;
          #endif
          vTW = wpv;
        }`);
      sh.fragmentShader = sh.fragmentShader.replace('#include <common>', '#include <common>\nvarying vec3 vTW; uniform sampler2D uNoise;')
        .replace('#include <color_fragment>', '#include <color_fragment>\n { float tn = texture2D(uNoise, vTW.xz * 0.004).r; diffuseColor.rgb *= mix(vec3(0.62, 0.72, 0.5), vec3(1.15, 1.05, 0.7), tn) * (0.8 + 0.4 * texture2D(uNoise, vTW.xz * 0.35 + vTW.y * 0.3).g); float lf = texture2D(uNoise, vTW.xz * 1.7 + vTW.y * 1.1).r * 0.6 + texture2D(uNoise, vTW.zx * 5.3 + vTW.y * 3.7).b * 0.4; diffuseColor.rgb *= 0.66 + 0.68 * lf; }');
    };
    patchMaterial(fol, 'foliage', windPatch);
    this.windPatch = windPatch;
  },

  // ---------------- forest ----------------
  _forest(scene, rng) {
    const V = assets.village; const types = ['Tree_Pine_A', 'Tree_Pine_B', 'Tree_Oak_A', 'Tree_Oak_B', 'Tree_Birch', 'Tree_Dead'];
    const geos = types.map(n => mergedGeo(V, n)); const lodPine = mergedGeo(V, 'Tree_Pine_LOD'), lodOak = mergedGeo(V, 'Tree_Oak_LOD'), lodBirch = mergedGeo(V, 'Tree_Birch_LOD');
    const dims = [[17, 3.0], [20, 2.6], [12, 5.5], [10, 5.0], [12, 2.0], [8, 1.2]]; // height, crown radius
    const CS = 160; const cells = new Map();
    const SP = 12.5; const R = 2500;
    for (let gz = -R; gz < R; gz += SP) for (let gx = -R; gx < R; gx += SP) {
      const x = gx + rng() * SP, z = gz + rng() * SP; const r = Math.hypot(x, z); if (r > R) continue;
      const d = forestDensity(x, z); if (rng() > d * (r > 1900 ? 0.55 : 0.9)) { if (!(d < 0.05 && rng() < 0.004)) continue; if (Math.hypot((x - L.FIELD.x) / (L.FIELD.rx + 60), z / (L.FIELD.rz + 60)) < 1 || Math.hypot(x - L.CASTLE.x, z - L.CASTLE.z) < 240 || Math.hypot(x - L.PAD.x, z - L.PAD.z) < 90 || Math.hypot(x - L.VILLAGE.x, z - L.VILLAGE.z) < 150) continue; }
      const y = terrain.height(x, z); if (y < L.WATER_Y + 1.2 || y > 330) continue;
      terrain.normal(x, z, _p); if (_p.y < 0.8) continue;
      if (terrain.roadDist(x, z) < 9) continue;
      const hi = smooth(60, 200, y) + (rng() - 0.5) * 0.5; const k = rng();
      const t = hi > 0.55 ? (k < 0.55 ? 0 : k < 0.95 ? 1 : 5) : (k < 0.3 ? 0 : k < 0.45 ? 1 : k < 0.7 ? 2 : k < 0.85 ? 3 : k < 0.96 ? 4 : 5);
      const s = 0.75 + rng() * 0.6; const ry = rng() * TAU;
      const key = Math.floor(x / CS) + ',' + Math.floor(z / CS); let c = cells.get(key); if (!c) cells.set(key, c = { cx: (Math.floor(x / CS) + 0.5) * CS, cz: (Math.floor(z / CS) + 0.5) * CS, lists: types.map(() => []), lp: [], lo: [], lb: [], cy: y });
      const inst = { x, y: y - 0.15, z, ry, s, rx: (rng() - 0.5) * 0.08, rz: (rng() - 0.5) * 0.08 };
      c.lists[t].push(inst); (t === 4 ? c.lb : t < 2 || t === 5 ? c.lp : c.lo).push(t === 4 ? inst : t === 5 ? { ...inst, s: s * 0.45 } : t >= 2 ? { ...inst, s: s * 1.16 } : { ...inst, s: s * 1.08 });
      if (r < 1750) { const col = world.addCyl(x, z, Math.max(1.0, dims[t][1] * s * 0.55), y, y + dims[t][0] * s - 1.0, 'tree'); col.hard = true; }
    }
    const fol = this.mats.foliage;
    for (const c of cells.values()) {
      c.full = []; c.lod = [];
      c.lists.forEach((l, i) => { const im = instanced(scene, geos[i], fol, l, true); if (im) { im.visible = false; c.full.push(im); } });
      for (const [l, g] of [[c.lp, lodPine], [c.lo, lodOak], [c.lb, lodBirch]]) { const im = instanced(scene, g, fol, l, false); if (im) c.lod.push(im); }
      // Identity parents retain the original instance/world transforms and draw order.
      // Bounds enclose the exact child spheres already used by Three.js culling.
      for (const key of ['full', 'lod']) {
        const group = new THREE.Group(); group.name = 'forest-' + key;
        const bounds = new THREE.Sphere().makeEmpty();
        for (const mesh of c[key]) { group.add(mesh); bounds.union(mesh.boundingSphere); mesh.visible = true; }
        bounds.radius += 0.001; // conservative floating-point margin
        group.userData.swSubtreeSphere = bounds;
        group.userData.swNoShadow = key === 'lod'; // existing LODs never cast PCF shadows
        group.visible = key === 'lod'; group.matrixAutoUpdate = false;
        scene.add(group); c[key + 'Group'] = group;
      }
      this.cells.push(c);
    }
  },

  // ---------------- village ----------------
  _village(scene, rng) {
    const V = assets.village; const P = this.mats.prop; const Vp = L.VILLAGE;
    const g = n => mergedGeo(V, n);
    const place = (x, z, ry, fx2, fz2, h, extra = 0.4) => { // returns ground y for a footprint; registers collider
      let y = 1e9; for (const [ax, az] of [[-1, -1], [1, -1], [1, 1], [-1, 1], [0, 0]]) { const c = Math.cos(ry), s = Math.sin(ry); const px = x + (ax * fx2 * c + az * fz2 * s), pz = z + (-ax * fx2 * s + az * fz2 * c); y = Math.min(y, terrain.height(px, pz)); }
      const col = world.addBox(x, z, fx2, fz2, ry, y - 2, y + h, 'house'); terrain.stampOccluder(x, z, Math.min(fx2, fz2), y + h * 0.8); return { y: y - extra, col };
    };
    const kinds = [['House_A', 4.2, 3.2, 6.7], ['House_B', 5.2, 3.8, 10.8], ['House_C', 7.0, 5.0, 8.1], ['House_D', 5.0, 3.0, 7.2]];
    const lists = kinds.map(() => []);
    // houses along the village street (road polyline 0, first segments) with jitter
    const spots = [];
    for (let i = 0; i < 60; i++) {
      const a = rng() * TAU, d = 16 + rng() * 78; const x = Vp.x + Math.cos(a) * d * 1.3, z = Vp.z + 20 + Math.sin(a) * d * 0.85;
      const rd = terrain.roadDist(x, z); if (rd < 9 || Math.abs(x - riverX(z)) < 34) continue;
      if (spots.some(s => Math.hypot(s[0] - x, s[1] - z) < 17)) continue;
      spots.push([x, z]);
      const k = rng() < 0.4 ? 0 : rng() < 0.45 ? 1 : rng() < 0.5 ? 2 : 3; const K = kinds[k];
      // face the nearest road-ish direction: toward village centre with noise
      const ry = Math.atan2(Vp.x - x, Vp.z - z) + (rng() - 0.5) * 0.9;
      const pl = place(x, z, ry, K[1], K[2], K[3]);
      lists[k].push({ x, y: pl.y, z, ry, s: 1 }); this.houses.push({ x, y: pl.y, z, h: K[3], col: pl.col, burning: false });
    }
    kinds.forEach((K, i) => instanced(scene, g(K[0]), P, lists[i]));
    // chapel, windmill, well, bridge, dock
    { const x = Vp.x - 52, z = Vp.z - 44; const pl = place(x, z, 0.4, 8.5, 5.5, 14); instanced(scene, g('Chapel'), P, [{ x, y: pl.y, z, ry: 0.4 }]); world.addCyl(x - 7, z + 3, 3, pl.y, pl.y + 17.5, 'house'); }
    { const x = Vp.x - 120, z = Vp.z + 78; const y = terrain.height(x, z) - 0.3; const ry = 1.9;
      const mill = V.scene.getObjectByName('Windmill').clone(true); mill.position.set(x, y, z); mill.rotation.y = ry; mill.traverse(o => { if (o.isMesh) { o.material = P; o.castShadow = o.receiveShadow = true; } }); scene.add(mill);
      this.millSails = mill.getObjectByName('Mill_Sails'); world.addCyl(x, z, 4.2, y, y + 14.5, 'house'); terrain.stampOccluder(x, z, 4, y + 12); }
    { const x = Vp.x + 6, z = Vp.z + 10; instanced(scene, g('Well'), P, [{ x, y: terrain.height(x, z) - 0.1, z, ry: 0.3 }]); }
    { const bz = Vp.z + 50, bx = riverX(bz); this.bridge = { x: bx, z: bz }; instanced(scene, g('Bridge'), P, [{ x: bx, y: L.WATER_Y + 0.3, z: bz, ry: 0, s: 2.0 }]);
      world.addBox(bx, bz, 18, 5.5, 0, L.WATER_Y - 3, L.WATER_Y + 5.6, 'prop'); }
    { const dz = Vp.z - 40, dx = riverX(dz) - 17; instanced(scene, g('Dock'), P, [{ x: dx, y: L.WATER_Y + 0.1, z: dz, ry: Math.PI / 2 }]); }
    // fences and dry-stone walls around plots
    const fences = [], walls = [];
    for (const s of spots) { const n = 3 + (rng() * 4 | 0); const a0 = rng() * TAU; const r = 13 + rng() * 5; for (let i = 0; i < n; i++) { const a = a0 + i * 0.3; const x = s[0] + Math.cos(a) * r, z = s[1] + Math.sin(a) * r; if (terrain.roadDist(x, z) < 5) continue; (rng() < 0.5 ? fences : walls).push({ x, y: terrain.height(x, z) - 0.05, z, ry: -a + Math.PI / 2 * 0 + Math.PI / 2 - 0.0 }); } }
    instanced(scene, g('Fence'), P, fences); instanced(scene, g('StoneWall'), P, walls);
    // haystacks + bushes near village and field edges
    const bushes = [[], []];
    for (let i = 0; i < 520; i++) { const a = rng() * TAU, d = 100 + rng() * 1500; const x = Math.cos(a) * d + 150, z = Math.sin(a) * d; const y = terrain.height(x, z); if (y < L.WATER_Y + 0.6 || terrain.roadDist(x, z) < 6) continue; const fe = Math.hypot((x - L.FIELD.x) / L.FIELD.rx, z / L.FIELD.rz); if (fe < 0.95 || Math.hypot(x - L.CASTLE.x, z - L.CASTLE.z) < 150 || Math.hypot(x - L.PAD.x, z - L.PAD.z) < 40) continue; bushes[i & 1].push({ x, y: y - 0.1, z, ry: rng() * TAU, s: 0.8 + rng() * 1.2 }); }
    instanced(scene, g('Bush_A'), this.mats.foliage, bushes[0], false); instanced(scene, g('Bush_B'), this.mats.foliage, bushes[1], false);
  },

  // ---------------- army camp ----------------
  _camp(scene, rng) {
    const Pr = assets.props; const P = this.mats.prop, I = this.mats.iron;
    // helper: split a prop into cloth/wood(etc) + iron instanced meshes
    const put = (name, list, cast = true) => { if (!list.length) return; for (const p of parts(Pr, name)) { const isIron = /Iron/.test(p.material.name); const isEm = /Emissive/.test(p.material.name);
        const mat = isEm ? p.material : isIron ? I : P; const im = new THREE.InstancedMesh(p.geometry, mat, list.length);
        list.forEach((t, i) => { _q.setFromEuler(_e.set(0, t.ry || 0, 0)); _m.compose(_p.set(t.x, t.y, t.z), _q, _s.setScalar(t.s || 1)).multiply(p.matrix); im.setMatrixAt(i, _m); if (t.tint !== undefined) im.setColorAt(i, _c.setHex(t.tint)); });
        im.castShadow = cast && !isEm; im.receiveShadow = true; im.computeBoundingSphere(); scene.add(im); } };
    this.put = put;
    const H = (x, z) => terrain.height(x, z);
    const tints = [0x8f1d1d, 0x1d3f8f, 0x8f7a1d, 0x2d6b3a, 0x6b2d6b, 0xb8b0a0];
    const tentsA = [], tentsB = [], carts = [], crates = [], barrels = [], racks = [], fires = [], hay = [], stakes = [], palis = [], poles = [];
    // camp behind the army, at the foot of the crag
    const cx = -60, cz = 10;
    for (let row = 0; row < 7; row++) for (let i = 0; i < 9; i++) {
      const x = cx - 95 + row * 21 + (rng() - 0.5) * 5, z = cz - 150 + i * 36 + (row % 2) * 16 + (rng() - 0.5) * 8;
      if (terrain.roadDist(x, z) < 8) continue; terrain.normal(x, z, _p); if (_p.y < 0.96) continue;
      if (rng() < 0.82) { tentsA.push({ x, y: H(x, z) - 0.05, z, ry: Math.PI / 2 + (rng() - 0.5) * 0.5, tint: 0xffffff }); world.addCyl(x, z, 2.4, H(x, z), H(x, z) + 2.4, 'prop'); }
      else { const k = rng(); (k < 0.3 ? carts : k < 0.55 ? crates : k < 0.75 ? barrels : k < 0.9 ? racks : hay).push({ x, y: H(x, z) - 0.03, z, ry: rng() * TAU }); }
      if (rng() < 0.16) { const fx2 = x + 7, fz2 = z + 5; fires.push({ x: fx2, y: H(fx2, fz2), z: fz2, ry: rng() * TAU }); }
    }
    // command pavilions
    [[-20, -40, 0x8f1d1d], [-34, 30, 0x1d3f8f], [10, 96, 0x8f7a1d]].forEach(([x, z, tint]) => { tentsB.push({ x, y: H(x, z) - 0.05, z, ry: Math.PI / 2, tint }); world.addCyl(x, z, 4.2, H(x, z), H(x, z) + 6.3, 'prop'); poles.push({ x: x + 6, y: H(x + 6, z + 5), z: z + 5, tint }); });
    // defensive stakes in front of the army (east edge of the field)
    for (let i = 0; i < 42; i++) { const z = -320 + i * 15.5 + (rng() - 0.5) * 4; const x = 205 + Math.sin(i * 0.4) * 12 + (rng() - 0.5) * 4; if (terrain.roadDist(x, z) < 7) continue; (i % 5 === 4 ? palis : stakes).push({ x, y: H(x, z) - 0.05, z, ry: Math.PI / 2 + (rng() - 0.5) * 0.3 }); }
    put('Tent_A', tentsA); put('Tent_B', tentsB); put('Cart', carts); put('Crates', crates); put('Barrels', barrels); put('WeaponRack', racks); put('Campfire', fires, false); put('Haystack', hay); put('Stakes', stakes); put('Palisade', palis);
    for (const f of fires) { this.fires.push(fx.addFire(f.x, f.y + 0.35, f.z, 0.55, 1e9, 0.25, true, false)); }
    this.campFires = fires; this.campPoles = poles;
    // ---- war dressing around the host: standards, idle siege engines, pavise lines, wagons ----
    const poleGeo = new THREE.CylinderGeometry(0.07, 0.1, 9, 6).translate(0, 4.5, 0);
    const standard = (x, z, c1, c2, emb, sc = 1) => { const g = new THREE.Group(); const pm = new THREE.Mesh(poleGeo, P); pm.castShadow = true; g.add(pm); const cl = this.makeBanner(1.7, 4.6, c1, c2, emb); cl.position.set(0, 8.8, 0.1); g.add(cl); g.position.set(x, H(x, z) - 0.1, z); g.rotation.y = Math.PI / 2 + (rng() - 0.5) * 0.4; g.scale.setScalar(sc); scene.add(g); };
    for (const pl of poles) standard(pl.x, pl.z, pl.tint, 0xd8c9a0, 2, 1.25);
    const HC = [[0x8f1d1d, 0xe2c46a], [0x1d3f8f, 0xe8e2d0], [0xc79a1e, 0x2a1a10], [0x2d6b3a, 0xe8e2d0], [0x5a2d6b, 0xd9b84a], [0xd8d2c2, 0x8f1d1d]];
    for (let i = 0; i < 12; i++) { const z = -230 + i * 42 + (rng() - 0.5) * 10, x = 168 + Math.sin(i * 1.3) * 10; if (terrain.roadDist(x, z) < 6) continue; const h = HC[i % 6]; standard(x, z, h[0], h[1], i % 6, 1.0); }
    for (let i = 0; i < 6; i++) { const z = -150 + i * 60 + (rng() - 0.5) * 12, x = -2 + (rng() - 0.5) * 14; const h = HC[(i + 3) % 6]; standard(x, z, h[0], h[1], (i + 2) % 6, 1.15); }
    const trebs = [], ball = [], pav = [], carts2 = [], racks2 = [];
    [[-12, -128, 1.45], [-22, -6, 1.5], [-12, 132, 1.45]].forEach(([x, z, ry]) => { trebs.push({ x, y: H(x, z) - 0.05, z, ry }); world.addCyl(x, z, 5, H(x, z), H(x, z) + 9, 'prop'); });
    [[150, -42], [150, 42], [86, -128], [86, 128]].forEach(([x, z]) => ball.push({ x, y: H(x, z), z, ry: Math.PI / 2 + (rng() - 0.5) * 0.3 }));
    for (const [ax, az] of [[82, -178], [82, 178], [250, 70], [300, -330]]) for (let i = 0; i < 9; i++) { const x = ax + 13 + (rng() - 0.5) * 1.5, z = az - 12 + i * 3 + (rng() - 0.5) * 0.6; pav.push({ x, y: H(x, z), z, ry: Math.PI / 2 + (rng() - 0.5) * 0.25 }); }
    for (let i = 0; i < 10; i++) { const x = 8 + rng() * 26, z = -190 + i * 40 + (rng() - 0.5) * 14; if (terrain.roadDist(x, z) < 6) continue; (i % 3 ? carts2 : racks2).push({ x, y: H(x, z) - 0.03, z, ry: rng() * TAU }); }
    put('Trebuchet', trebs); put('Ballista', ball); put('Cart', carts2); put('WeaponRack', racks2);
  },

  // ---------------- rearm pad ----------------
  _pad(scene) {
    const P = L.PAD; const y = P.y;
    // steel-plank landing mat with painted H
    const cv = document.createElement('canvas'); cv.width = cv.height = 1024; const c = cv.getContext('2d');
    c.fillStyle = '#4a4d48'; c.fillRect(0, 0, 1024, 1024);
    for (let i = 0; i < 26; i++) { c.fillStyle = i % 2 ? 'rgba(0,0,0,0.10)' : 'rgba(255,255,255,0.03)'; c.fillRect(0, i * 40, 1024, 38); for (let j = 0; j < 60; j++) { c.fillStyle = 'rgba(0,0,0,0.25)'; c.beginPath(); c.arc(j * 18 + (i % 2) * 9, i * 40 + 19, 3, 0, TAU); c.fill(); } }
    for (let i = 0; i < 900; i++) { c.fillStyle = `rgba(${20 + Math.random() * 40 | 0},${15 + Math.random() * 30 | 0},10,${Math.random() * 0.12})`; c.beginPath(); c.arc(Math.random() * 1024, Math.random() * 1024, 4 + Math.random() * 40, 0, TAU); c.fill(); }
    c.strokeStyle = '#d9c84a'; c.lineWidth = 22; c.beginPath(); c.arc(512, 512, 400, 0, TAU); c.stroke();
    c.fillStyle = '#e6e2d0'; c.fillRect(352, 300, 60, 424); c.fillRect(612, 300, 60, 424); c.fillRect(352, 482, 320, 60);
    c.strokeStyle = '#d9c84a'; c.lineWidth = 10; c.setLineDash([40, 30]); c.strokeRect(40, 40, 944, 944);
    const tex = new THREE.CanvasTexture(cv); tex.colorSpace = THREE.SRGBColorSpace; tex.anisotropy = 8;
    const pad = new THREE.Mesh(new THREE.BoxGeometry(34, 0.5, 34), [0, 1, 2, 3, 4, 5].map(i => new THREE.MeshStandardMaterial({ map: i === 2 ? tex : null, color: i === 2 ? 0xffffff : 0x3a3c38, roughness: 0.7, metalness: 0.5 })));
    pad.position.set(P.x, y - 0.12, P.z); pad.receiveShadow = true; scene.add(pad);
    this.padY = y + 0.13;
    const put = this.put;
    put('Pad_Truck', [{ x: P.x + 24, y: terrain.height(P.x + 24, P.z - 8), z: P.z - 8, ry: 0.3 }]); world.addBox(P.x + 24, P.z - 8, 1.6, 3.8, 0.3, y - 1, y + 3.4, 'prop');
    put('Pad_Crates', [{ x: P.x + 21, y: terrain.height(P.x + 21, P.z + 9), z: P.z + 9, ry: 1.2 }, { x: P.x - 4, y: terrain.height(P.x - 4, P.z + 23), z: P.z + 23, ry: 0.1 }]);
    put('Pad_Generator', [{ x: P.x - 23, y: terrain.height(P.x - 23, P.z + 16), z: P.z + 16, ry: 2.2 }]); world.addCyl(P.x - 23, P.z + 16, 1.2, y - 1, y + 4.2, 'prop');
    const lights = []; for (let i = 0; i < 12; i++) { const a = i / 12 * TAU; lights.push({ x: P.x + Math.cos(a) * 19.5, y: y + 0.05, z: P.z + Math.sin(a) * 19.5, ry: 0 }); }
    put('Pad_Light', lights, false);
    // windsock (animated)
    const ws = assets.props.scene.getObjectByName('Windsock').clone(true); ws.position.set(P.x - 21, terrain.height(P.x - 21, P.z - 19), P.z - 19); ws.traverse(o => { if (o.isMesh) { o.material = this.mats.prop; o.castShadow = true; } }); scene.add(ws);
    this.windsock = ws.getObjectByName('Windsock_Sock');
    // pad beacon light (helps find it at dusk)
    const bl = this.padLight = new THREE.PointLight(0xffd9a0, 0, 60, 1.5); bl.position.set(P.x, y + 5, P.z); scene.add(bl);
    const gm = new THREE.Mesh(new THREE.SphereGeometry(0.35, 8, 6), new THREE.MeshBasicMaterial({ color: 0x66ff88, fog: false })); gm.position.set(P.x - 23, y + 4.4, P.z + 16); scene.add(gm); this.padBeacon = gm;
  },

  // ---------------- rocks ----------------
  _rocks(scene, rng) {
    const V = assets.village; const lists = [[], [], [], []];
    const C = L.CASTLE;
    for (let i = 0; i < 2600; i++) {
      const a = rng() * TAU, d = Math.sqrt(rng()) * 2300; const x = Math.cos(a) * d, z = Math.sin(a) * d; const y = terrain.height(x, z); if (y < L.WATER_Y - 0.5) continue;
      terrain.normal(x, z, _p); const slope = 1 - _p.y; const dc = Math.hypot(x - C.x, z - C.z);
      const crag = dc > 150 && dc < 260; if (slope < 0.1 && !(rng() < 0.03)) continue; if (dc < 150 || Math.hypot(x - L.PAD.x, z - L.PAD.z) < 40) continue;
      const k = crag && rng() < 0.4 ? 3 : (rng() * 3) | 0; lists[k].push({ x, y: y - 0.3 - (k === 3 ? 1.2 : 0), z, ry: rng() * TAU, s: (k === 3 ? 1.0 : 0.7) + rng() * 1.5, rx: (rng() - 0.5) * 0.5, rz: (rng() - 0.5) * 0.5 });
    }
    // boulders and crag pieces: the same photoscanned rock as the terrain cliffs, projected triplanar in world space
    const rm = this.mats.rock = this.mats.prop.clone(); rm.roughness = 0.95; const basePatch = this.mats.prop.onBeforeCompile; const gr = assets.ground;
    patchMaterial(rm, 'rock', sh => {
      basePatch(sh); Object.assign(sh.uniforms, { uGA: { value: gr.A }, uGB: { value: gr.B }, uGMean: { value: gr.mean } });
      sh.fragmentShader = sh.fragmentShader.replace('varying vec3 vPW; uniform sampler2D uNoise;', `varying vec3 vPW; uniform sampler2D uNoise;
        uniform sampler2DArray uGA; uniform sampler2DArray uGB; uniform vec3 uGMean[${gr.n}]; vec3 swRkN; float swRkR;`)
        .replace('#include <color_fragment>', /* glsl */`#include <color_fragment>
        { vec3 dx = dFdx(vPW), dy = dFdy(vPW); vec3 w = abs(normalize(cross(dx, dy))); w = w * w; w = w * w; w /= (w.x + w.y + w.z);
          vec3 c = vec3(0.0), c2 = vec3(0.0); vec4 b = vec4(0.0); vec3 nn = vec3(0.0); const float s = 1.0 / 3.4, s2 = 1.0 / 23.0;
          if (w.y > 0.03) { c += textureGrad(uGA, vec3(vPW.xz * s, 4.0), dx.xz * s, dy.xz * s).rgb * w.y; c2 += textureGrad(uGA, vec3(vPW.xz * s2, 8.0), dx.xz * s2, dy.xz * s2).rgb * w.y; vec4 B = textureGrad(uGB, vec3(vPW.xz * s, 4.0), dx.xz * s, dy.xz * s); b += B * w.y; vec2 n = B.rg * 2.0 - 1.0; nn += vec3(n.x, 0.0, -n.y) * w.y; }
          if (w.x > 0.03) { vec2 u = vec2(vPW.z, -vPW.y), ux = vec2(dx.z, -dx.y), uy = vec2(dy.z, -dy.y); c += textureGrad(uGA, vec3(u * s, 4.0), ux * s, uy * s).rgb * w.x; c2 += textureGrad(uGA, vec3(u * s2, 8.0), ux * s2, uy * s2).rgb * w.x; vec4 B = textureGrad(uGB, vec3(u * s, 4.0), ux * s, uy * s); b += B * w.x; vec2 n = B.rg * 2.0 - 1.0; nn += vec3(0.0, n.y, n.x) * w.x; }
          if (w.z > 0.03) { vec2 u = vec2(vPW.x, -vPW.y), ux = vec2(dx.x, -dx.y), uy = vec2(dy.x, -dy.y); c += textureGrad(uGA, vec3(u * s, 4.0), ux * s, uy * s).rgb * w.z; c2 += textureGrad(uGA, vec3(u * s2, 8.0), ux * s2, uy * s2).rgb * w.z; vec4 B = textureGrad(uGB, vec3(u * s, 4.0), ux * s, uy * s); b += B * w.z; vec2 n = B.rg * 2.0 - 1.0; nn += vec3(n.x, n.y, 0.0) * w.z; }
          diffuseColor.rgb *= (c / uGMean[4]) * mix(vec3(1.0), c2 / uGMean[8], 0.6) * mix(1.0, b.a, 0.7) * 1.1; swRkN = nn * 1.4; swRkR = b.b; }`)
        .replace('#include <roughnessmap_fragment>', '#include <roughnessmap_fragment>\n roughnessFactor = 0.78 + 0.22 * swRkR;')
        .replace('#include <normal_fragment_maps>', '#include <normal_fragment_maps>\n normal = normalize(normal + (viewMatrix * vec4(swRkN, 0.0)).xyz);');
    });
    ['Rock_A', 'Rock_B', 'Rock_C', 'Cliff_A'].forEach((n, i) => instanced(scene, mergedGeo(V, n), rm, lists[i], i >= 2));
  },

  // ---------------- river ----------------
  _water(scene) {
    const pos = [], idx = []; const W = 62; let k = 0;
    for (let z = -2700; z <= 2700; z += 15) { const x = riverX(z); pos.push(x - W, L.WATER_Y, z, x + W, L.WATER_Y, z); if (k > 0) { const a = (k - 1) * 2; idx.push(a, a + 2, a + 1, a + 1, a + 2, a + 3); } k++; }
    const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3)); g.setIndex(idx);
    const mat = new THREE.ShaderMaterial({
      transparent: true, depthWrite: false, fog: false,
      uniforms: { uZen: { value: new THREE.Color(0.1, 0.2, 0.4) } },
      vertexShader: `varying vec3 vW; void main(){ vW = position; gl_Position = projectionMatrix * viewMatrix * vec4(position, 1.0); }`,
      fragmentShader: /* glsl */`precision highp float; varying vec3 vW; uniform sampler2D uNoise; uniform float uTime; uniform vec3 uSunCol; uniform vec3 uZen; uniform vec4 uHeli;
        ${GLSL_FOG} ${GLSL_FARSH}
        void main(){
          vec3 V = normalize(cameraPosition - vW); float d = length(cameraPosition - vW);
          vec2 fl = vec2(0.0, uTime * 0.035);
          vec2 n1 = texture2D(uNoise, vW.xz * 0.045 + fl).rg - 0.5, n2 = texture2D(uNoise, vW.xz * 0.19 - fl * 2.3 + 0.3).gb - 0.5;
          // rotor wash ripples
          vec2 dh = vW.xz - uHeli.xz; float dl = length(dh); float wash = uHeli.w * smoothstep(40.0, 4.0, dl) * smoothstep(60.0, 5.0, uHeli.y - vW.y);
          float rip = sin(dl * 2.2 - uTime * 14.0) * wash;
          vec3 N = normalize(vec3((n1.x * 0.5 + n2.x * 0.35) * smoothstep(900.0, 40.0, d) + dh.x / max(dl, 1.0) * rip * 0.5, 1.0, (n1.y * 0.5 + n2.y * 0.35) * smoothstep(900.0, 40.0, d) + dh.y / max(dl, 1.0) * rip * 0.5));
          vec3 R = reflect(-V, N); R.y = abs(R.y);
          float fres = 0.03 + 0.97 * pow(1.0 - max(dot(N, V), 0.0), 5.0);
          float s = max(dot(normalize(vec3(R.x, 0.0, R.z)), uSunDir), 0.0);
          vec3 hor = mix(uFogColB, uFogColA, pow(s, uFogP.w) * 0.85 + 0.15 * s);
          vec3 skyR = mix(hor, uZen, 1.0 - exp(-R.y * 4.0));
          float sh = swFarShadow(vW + vec3(0.0, 0.5, 0.0));
          float spec = pow(max(dot(R, uSunDir), 0.0), 380.0) * 14.0 + pow(max(dot(R, uSunDir), 0.0), 40.0) * 0.35;
          vec3 deep = vec3(0.018, 0.035, 0.028) * (0.4 + dot(uSunCol, vec3(0.12)));
          vec3 col = mix(deep, skyR, fres) + uSunCol * spec * sh;
          col += vec3(0.5, 0.55, 0.55) * wash * (0.25 + 0.5 * max(rip, 0.0)) * dot(uSunCol + 0.3, vec3(0.1));
          col = swFog(col, vW);
          gl_FragColor = vec4(col, 0.93);
        }`,
    });
    this.waterMat = mat;
    const m = new THREE.Mesh(g, mat); m.frustumCulled = false; m.renderOrder = 1; scene.add(m);
  },

  // ---------------- grass ----------------
  _grass(scene, rng) {
    const COUNT = 120000, S = 84;
    const hmTex = new THREE.DataTexture(terrain.hm, N, N, THREE.RedFormat, THREE.FloatType); hmTex.minFilter = hmTex.magFilter = THREE.LinearFilter; hmTex.needsUpdate = true;
    const g = new THREE.InstancedBufferGeometry();
    // blade: 5 verts, slightly bent
    g.setAttribute('position', new THREE.Float32BufferAttribute([-0.5, 0, 0, 0.5, 0, 0, -0.4, 0.38, 0, 0.4, 0.38, 0, -0.24, 0.72, 0, 0.24, 0.72, 0, 0, 1, 0], 3));
    g.setAttribute('normal', new THREE.Float32BufferAttribute([0, 1, 0, 0, 1, 0, 0, 1, 0, 0, 1, 0, 0, 1, 0, 0, 1, 0, 0, 1, 0], 3));
    g.setIndex([0, 1, 2, 1, 3, 2, 2, 3, 4, 3, 5, 4, 4, 5, 6]);
    const off = new Float32Array(COUNT * 4); for (let i = 0; i < COUNT; i++) { off[i * 4] = rng() * S; off[i * 4 + 1] = rng() * S; off[i * 4 + 2] = rng() * TAU; off[i * 4 + 3] = rng(); }
    g.setAttribute('iOff', new THREE.InstancedBufferAttribute(off, 4)); g.instanceCount = COUNT;
    const mat = new THREE.MeshLambertMaterial({ color: 0xffffff, side: THREE.DoubleSide });
    patchMaterial(mat, 'grass', sh => {
      sh.vertexShader = sh.vertexShader.replace('#include <common>', `#include <common>
        attribute vec4 iOff; uniform sampler2D uHM; uniform sampler2D uCtl; uniform sampler2D uNoise; uniform float uTime; uniform vec4 uHeli; uniform vec3 uCamG; uniform sampler2D uScorch; uniform vec4 uScorchP;
        varying vec3 vGCol; varying float vGH;
        float hAt(vec2 p){ vec2 uv = (p + ${HALF}.0) / ${2 * HALF}.0 * ${N - 1}.0 / ${N}.0 + 0.5 / ${N}.0; return texture2D(uHM, uv).r; }`)
        .replace('#include <beginnormal_vertex>', 'vec3 objectNormal = vec3(0.0, 1.0, 0.0);')
        .replace('#include <begin_vertex>', /* glsl */`
        vec2 base = iOff.xy + ${S}.0 * floor((uCamG.xz - iOff.xy) / ${S}.0 + 0.5);
        float dist = length(base - uCamG.xz);
        float gh = hAt(base); float ghx = hAt(base + vec2(2.5, 0.0)), ghz = hAt(base + vec2(0.0, 2.5));
        float slope = length(vec2(ghx - gh, ghz - gh)) / 2.5;
        vec4 ctl = texture2D(uCtl, base / 4096.0 + 0.5);
        float n1 = texture2D(uNoise, base * 0.0019).r; float n2 = texture2D(uNoise, base * 0.013 + n1 * 0.3).g; float n3 = texture2D(uNoise, base * 0.11).b;
        vec2 suv = (base - uScorchP.xy) * uScorchP.z + 0.5; float burn = texture2D(uScorch, suv).r;
        float keep = smoothstep(${(S * 0.5).toFixed(1)}, ${(S * 0.3).toFixed(1)}, dist) * smoothstep(0.34, 0.2, slope) * smoothstep(0.22, 0.04, ctl.r * 0.75 + (n3 - 0.5) * 0.2) * smoothstep(0.5, 0.2, ctl.g) * smoothstep(${(L.WATER_Y + 0.5).toFixed(1)}, ${(L.WATER_Y + 1.8).toFixed(1)}, gh) * smoothstep(0.5, 0.15, burn) * (1.0 - ctl.b * 0.7);
        float hgt = (0.35 + 0.5 * iOff.w + 0.35 * n2) * keep; float wdt = 0.055 + 0.05 * iOff.w;
        float ca = cos(iOff.z), sa = sin(iOff.z);
        float t = position.y;
        // wind + rotor wash bend
        vec3 dh = vec3(base.x, gh, base.y) - uHeli.xyz; float dl = length(dh.xz);
        float wash = uHeli.w * smoothstep(34.0, 3.0, dl) * smoothstep(45.0, 6.0, -dh.y);
        float gust = texture2D(uNoise, base * 0.006 + vec2(uTime * 0.05, uTime * 0.02)).r;
        vec2 bend = vec2(0.35 + gust * 0.9, 0.2 * gust) * 0.45 + vec2(sin(uTime * 2.3 + base.x * 0.4 + base.y * 0.3), cos(uTime * 1.9 + base.y * 0.5)) * 0.07;
        bend += (dh.xz / max(dl, 0.5)) * wash * (1.6 + 0.5 * sin(uTime * 23.0 + base.x * 3.0 + base.y * 2.0));
        float bl = length(bend); float flat_ = clamp(bl * 0.55, 0.0, 0.92);
        vec3 transformed = vec3(base.x + position.x * wdt * ca + bend.x * t * t * hgt, gh + t * hgt * (1.0 - flat_ * t * 0.9), base.y + position.x * wdt * sa + bend.y * t * t * hgt);
        // colour matches the terrain grass
        vec3 gLush = vec3(0.115, 0.17, 0.035), gDry = vec3(0.34, 0.27, 0.085), gDark = vec3(0.05, 0.085, 0.022);
        float dry = smoothstep(0.38, 0.68, n1 * 0.55 + n2 * 0.45);
        vec3 gc = mix(gLush, gDry, dry); gc = mix(gc, gDark, smoothstep(0.52, 0.78, n2) * 0.55 * (1.0 - dry));
        float bh = fract(iOff.w * 37.31 + iOff.z * 5.7); // per-blade variety: greener shoots, bleached straw, a few seed-brown stems
        gc = mix(gc, gc * vec3(0.62, 1.12, 0.55), smoothstep(0.55, 0.9, bh) * 0.8); gc = mix(gc, vec3(0.46, 0.38, 0.2), smoothstep(0.0, 0.18, 0.18 - bh) * 0.7);
        vGCol = gc * (0.7 + 0.6 * mix(0.5, n3, 0.7)) * (0.8 + 0.4 * iOff.w); vGH = t;
        `);
      sh.fragmentShader = sh.fragmentShader.replace('#include <common>', '#include <common>\nvarying vec3 vGCol; varying float vGH;')
        .replace('#include <color_fragment>', 'diffuseColor.rgb = vGCol * mix(0.45, 1.5, sqrt(clamp(vGH, 0.0, 1.0))) * (gl_FrontFacing ? 1.0 : 0.82);')
        .replace('#include <normal_fragment_begin>', '#include <normal_fragment_begin>\n normal = normalize(mix(normalize(vNormal), (viewMatrix * vec4(0.0, 1.0, 0.0, 0.0)).xyz, 0.8));');
    }, this.grassU = { uHM: { value: hmTex }, uCtl: { value: terrain.ctlTex }, uCamG: { value: new V3() } });
    this.grassMat = mat;
    const m = this.grass = new THREE.Mesh(g, mat); m.frustumCulled = false; m.receiveShadow = true; m.castShadow = false; scene.add(m);
  },

  // cloth banner hanging from a crossbar; returns mesh (position it at the attach point)
  makeBanner(w, h, color, color2, emblem = 0) {
    const g = new THREE.PlaneGeometry(w, h, 6, 10); g.translate(0, -h / 2, 0);
    const m = new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.85, side: THREE.DoubleSide });
    const u = { uCol: { value: new THREE.Color(color) }, uCol2: { value: new THREE.Color(color2) }, uH: { value: h }, uEmb: { value: emblem }, uFall: { value: 0 } };
    patchMaterial(m, 'banner', sh => {
      sh.vertexShader = sh.vertexShader.replace('#include <common>', '#include <common>\nuniform float uTime; uniform vec4 uHeli; uniform float uH; uniform float uFall; varying vec2 vBU;')
        .replace('#include <begin_vertex>', /* glsl */`#include <begin_vertex>
        { vBU = uv; float k = -position.y / uH; vec3 wp0 = (modelMatrix * vec4(0.0, 0.0, 0.0, 1.0)).xyz; float ph = wp0.x * 0.7 + wp0.z * 0.9;
          vec3 dh = wp0 - uHeli.xyz; float dl = length(dh.xz); float wash = uHeli.w * smoothstep(55.0, 8.0, dl) * smoothstep(70.0, 5.0, -dh.y);
          float amp = (0.22 + wash * 0.9) * k; float sp = 3.2 + wash * 12.0;
          transformed.z += (sin(uTime * sp + position.x * 2.4 + k * 5.0 + ph) * 0.6 + sin(uTime * sp * 1.7 + k * 9.0 + ph) * 0.3 + 0.9) * amp;
          transformed.x += sin(uTime * sp * 0.8 + k * 4.0 + ph) * amp * 0.25;
          transformed.y += k * (amp * 0.8 + wash * 0.5 * uH * k); }`);
      sh.fragmentShader = sh.fragmentShader.replace('#include <common>', '#include <common>\nuniform vec3 uCol; uniform vec3 uCol2; uniform float uEmb; varying vec2 vBU;')
        .replace('#include <color_fragment>', /* glsl */`#include <color_fragment>
        { vec2 q = vBU; vec3 c = uCol; float e = uEmb;
          if (e < 0.5) { c = mix(uCol, uCol2, step(0.5, q.x)); }                              // per pale
          else if (e < 1.5) { c = mix(uCol, uCol2, step(abs(q.x - 0.5), 0.14)); }             // pale stripe
          else if (e < 2.5) { c = mix(uCol, uCol2, step(abs(q.x - 0.5) + abs(q.y - 0.55) * 0.7, 0.22)); } // lozenge
          else if (e < 3.5) { c = mix(uCol, uCol2, step(abs(q.y - 0.6), 0.1)); }              // fess
          else if (e < 4.5) { c = mix(uCol, uCol2, step(min(abs(q.x - 0.5), abs(q.y - 0.55) * 0.7), 0.075)); } // cross
          else { c = mix(uCol, uCol2, step(length((q - vec2(0.5, 0.55)) * vec2(1.0, 0.7)), 0.2)); } // roundel
          if (q.y < 0.14 && abs(q.x - 0.5) < (0.14 - q.y) * 2.2) discard; // swallow tail
          diffuseColor.rgb = c; }`);
    }, u);
    const mesh = new THREE.Mesh(g, m); mesh.castShadow = true; mesh.frustumCulled = false; mesh.userData.u = u;
    return mesh;
  },

  update(dt, camera) {
    const cx = camera.position.x, cz = camera.position.z;
    // forest LOD
    for (const c of this.cells) { const d = Math.hypot(c.cx - cx, c.cz - cz); const near = d < TREE_R; c.fullGroup.visible = near; c.lodGroup.visible = !near; }
    this.grassU.uCamG.value.copy(camera.position);
    if (this.millSails) this.millSails.rotation.z += dt * 0.5;
    if (this.windsock) this.windsock.rotation.y = 1.9 + Math.sin(G.time * 0.7) * 0.25 + Math.sin(G.time * 2.3) * 0.06;
    this.waterMat.uniforms.uZen.value.copy(G.skyZenith || _c.setRGB(0.1, 0.2, 0.4));
    const night = G.U.uNight.value; this.padLight.intensity = 30 + night * 220; this.padBeacon.visible = (G.time % 1.2) < 0.6;
    this.grass.visible = camera.position.y - terrain.height(cx, cz) < 140;
  },
};
