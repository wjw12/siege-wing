// Siege Wing — the army: animation baked to a bone-matrix texture, GPU-instanced soldiers (2 LODs), formations, morale, rout
import * as THREE from 'three';
import { G, V3, patchMaterial, clamp, lerp, smooth, damp, sat, rnd, rndS, TAU, wrapPi, mulberry32 } from './core.js';
import { terrain, L, riverX } from './terrain.js';
import { assets } from './assets.js';
import { castle } from './castle.js';
import { scenery } from './scenery.js';
import { fx } from './fx.js';
import { audio } from './audio.js';

const CLIPS = ['Idle', 'ShieldUp', 'Walk', 'Run', 'Panic', 'Volley', 'Attack', 'Cheer', 'Thrown', 'Die', 'Crank'];
const A = Object.fromEntries(CLIPS.map((n, i) => [n, i]));
const LOOP = [1, 1, 1, 1, 1, 0, 0, 1, 1, 0, 1];
const FPS = 15, NB = 16;
export const ST = { FORM: 0, PANIC: 1, ROUT: 2, THROWN: 3, DYING: 4, DEAD: 5, FLED: 6, CHEER: 7 };
export const TY = { INF: 0, ARCH: 1, KNIGHT: 2, WARLORD: 3 };
const MAXN = 2200, LOD_D = 95;
const _v = new V3(), _v2 = new V3(), _m = new THREE.Matrix4(), _c = new THREE.Color();
const HERALD = [[0x9a1b1b, 0xe8d9a0], [0x1c3f95, 0xe6e6e6], [0xc49a1a, 0x1a1a1a], [0x2a6e3a, 0xe8d9a0], [0x6a2470, 0xd9b84a], [0xd8d2c2, 0x8a1515], [0x15616d, 0xf0e0b0], [0x7a3b12, 0xe0e0e0]];

const GLSL_ANIM = /* glsl */`
attribute float aJ; attribute vec4 iPos; attribute vec4 iAnim; attribute vec4 iTint;
uniform sampler2D uAnim; uniform float uAnimH;
mat4 swBone(float row){ float v = (row + 0.5) / uAnimH; float u = (aJ * 3.0 + 0.5) / ${NB * 3}.0;
  vec4 a = texture2D(uAnim, vec2(u, v)), b = texture2D(uAnim, vec2(u + 1.0 / ${NB * 3}.0, v)), c = texture2D(uAnim, vec2(u + 2.0 / ${NB * 3}.0, v));
  return mat4(a.x, b.x, c.x, 0.0, a.y, b.y, c.y, 0.0, a.z, b.z, c.z, 0.0, a.w, b.w, c.w, 1.0); }
void swXform(inout vec3 p, inout vec3 n){
  mat4 m = swBone(iAnim.x); if (iAnim.z > 0.001) { mat4 m2 = swBone(iAnim.y); m = m * (1.0 - iAnim.z) + m2 * iAnim.z; }
  p = (m * vec4(p, 1.0)).xyz * iAnim.w; n = normalize(mat3(m) * n);
  float ta = iTint.w; if (abs(ta) > 0.001) { float c = cos(ta), s = sin(ta); p.y -= 0.9; p = vec3(p.x, p.y * c - p.z * s, p.y * s + p.z * c); p.y += 0.9; n = vec3(n.x, n.y * c - n.z * s, n.y * s + n.z * c); }
  float cy = cos(iPos.w), sy = sin(iPos.w); p = vec3(p.x * cy + p.z * sy, p.y, -p.x * sy + p.z * cy) + iPos.xyz; n = vec3(n.x * cy + n.z * sy, n.y, -n.x * sy + n.z * cy);
}`;

const _poleGeo = new THREE.CylinderGeometry(0.05, 0.07, 5.2, 6).translate(0, 2.6, 0);
export const crowd = {
  n: 0, forms: [], clip: [], total: 0, killed: 0, routedCount: 0, warlord: -1, warlordHp: 6, cheering: false, panicLevel: 0,
  build(scene) {
    this.scene = scene;
    this._bake();
    this._alloc();
    this._meshes(scene);
    this._spawnAll();
    this._saveInit();
  },

  // ---------- bake bone matrices for every clip frame into a float texture ----------
  _bake() {
    const gl = assets.soldiers, root = gl.scene; root.updateMatrixWorld(true);
    const meshes = this.src = {}; root.traverse(o => { if (o.isSkinnedMesh) meshes[o.name] = o; });
    const sk = meshes.Infantry.skeleton; const mixer = new THREE.AnimationMixer(root);
    let rows = 0; const clip = this.clip = CLIPS.map(name => { const c = gl.animations.find(a => a.name === name); const frames = Math.max(2, Math.round(c.duration * FPS) + 1); const o = { name, clip: c, dur: c.duration, frames, start: rows }; rows += frames; return o; });
    const data = new Float32Array(NB * 3 * rows * 4);
    for (const c of clip) {
      const act = mixer.clipAction(c.clip); act.play();
      for (let f = 0; f < c.frames; f++) {
        act.time = Math.min(f / (c.frames - 1) * c.dur, c.dur - 1e-4); mixer.update(0); root.updateMatrixWorld(true);
        for (let b = 0; b < NB; b++) {
          _m.multiplyMatrices(sk.bones[b].matrixWorld, sk.boneInverses[b]); const e = _m.elements; const o = ((c.start + f) * NB * 3 + b * 3) * 4;
          data[o] = e[0]; data[o + 1] = e[4]; data[o + 2] = e[8]; data[o + 3] = e[12];
          data[o + 4] = e[1]; data[o + 5] = e[5]; data[o + 6] = e[9]; data[o + 7] = e[13];
          data[o + 8] = e[2]; data[o + 9] = e[6]; data[o + 10] = e[10]; data[o + 11] = e[14];
        }
      }
      act.stop();
    }
    const tex = this.animTex = new THREE.DataTexture(data, NB * 3, rows, THREE.RGBAFormat, THREE.FloatType);
    const canLin = !!G.renderer.extensions.get('OES_texture_float_linear');
    tex.minFilter = tex.magFilter = canLin ? THREE.LinearFilter : THREE.NearestFilter; tex.needsUpdate = true; this.animRows = rows;
  },
  _geo(name) {
    const sm = this.src[name]; const g0 = sm.geometry; const n = g0.attributes.position.count;
    const pos = new Float32Array(n * 3), nor = new Float32Array(n * 3), col = new Float32Array(n * 3), uv = new Float32Array(n * 2), aj = new Float32Array(n);
    const bm = sm.bindMatrix, nm = new THREE.Matrix3().getNormalMatrix(bm);
    for (let i = 0; i < n; i++) {
      _v.fromBufferAttribute(g0.attributes.position, i).applyMatrix4(bm); pos.set([_v.x, _v.y, _v.z], i * 3);
      _v.fromBufferAttribute(g0.attributes.normal, i).applyMatrix3(nm).normalize(); nor.set([_v.x, _v.y, _v.z], i * 3);
      const c = g0.attributes.color; col.set([c.getX(i), c.getY(i), c.getZ(i)], i * 3);
      uv.set([g0.attributes.uv.getX(i), g0.attributes.uv.getY(i)], i * 2); aj[i] = g0.attributes.skinIndex.getX(i);
    }
    const g = new THREE.InstancedBufferGeometry();
    g.setAttribute('position', new THREE.BufferAttribute(pos, 3)); g.setAttribute('normal', new THREE.BufferAttribute(nor, 3)); g.setAttribute('color', new THREE.BufferAttribute(col, 3)); g.setAttribute('uv', new THREE.BufferAttribute(uv, 2)); g.setAttribute('aJ', new THREE.BufferAttribute(aj, 1));
    g.setIndex(g0.index); return g;
  },
  _meshes(scene) {
    const u = { uAnim: { value: this.animTex }, uAnimH: { value: this.animRows } };
    const mat = this.mat = new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.8, metalness: 0, vertexColors: true });
    patchMaterial(mat, 'crowd', sh => {
      sh.vertexShader = sh.vertexShader.replace('#include <common>', '#include <common>\n' + GLSL_ANIM + '\nvarying vec3 vSwT; varying vec2 vSwM;')
        .replace('#include <beginnormal_vertex>', 'vec3 objectNormal = vec3(normal); vec3 swP = vec3(position); swXform(swP, objectNormal); vSwT = iTint.rgb; vSwM = uv;')
        .replace('#include <begin_vertex>', 'vec3 transformed = swP;');
      sh.fragmentShader = sh.fragmentShader.replace('#include <common>', '#include <common>\nvarying vec3 vSwT; varying vec2 vSwM;')
        .replace('#include <color_fragment>', '#include <color_fragment>\n diffuseColor.rgb = mix(diffuseColor.rgb, diffuseColor.rgb * mix(vec3(0.75), vSwT * 1.5, 0.8), step(0.5, vSwM.x));')
        .replace('#include <metalnessmap_fragment>', 'float metalnessFactor = step(0.5, vSwM.y) * 0.9;')
        .replace('#include <roughnessmap_fragment>', 'float roughnessFactor = mix(0.86, 0.38, step(0.5, vSwM.y));');
    }, u);
    const dmat = this.dmat = new THREE.MeshDepthMaterial({ depthPacking: THREE.RGBADepthPacking });
    patchMaterial(dmat, 'crowdDepth', sh => {
      sh.vertexShader = sh.vertexShader.replace('#include <common>', '#include <common>\n' + GLSL_ANIM)
        .replace('#include <begin_vertex>', 'vec3 transformed = vec3(position); vec3 swN = vec3(0.0, 1.0, 0.0); swXform(transformed, swN);');
    }, u);
    // buckets: [type][lod]
    const names = [['Infantry', 'Infantry_LOD1'], ['Archer', 'Archer_LOD1'], ['Knight', 'Knight_LOD1'], ['Warlord', null]];
    const caps = [1500, 520, 170, 1];
    this.buckets = names.map((nm, t) => nm.map((name, lod) => {
      if (!name) return null; const g = this._geo(name); const cap = caps[t];
      const mk = sz => { const a = new THREE.InstancedBufferAttribute(new Float32Array(cap * sz), sz); a.setUsage(THREE.DynamicDrawUsage); return a; };
      const b = { geo: g, iPos: mk(4), iAnim: mk(4), iTint: mk(4), n: 0, cap };
      g.setAttribute('iPos', b.iPos); g.setAttribute('iAnim', b.iAnim); g.setAttribute('iTint', b.iTint); g.instanceCount = 0;
      const mesh = new THREE.Mesh(g, mat); mesh.customDepthMaterial = dmat; mesh.frustumCulled = false; mesh.castShadow = true; mesh.receiveShadow = true; scene.add(mesh); b.mesh = mesh; return b;
    }));
  },
  _alloc() {
    const F = () => new Float32Array(MAXN), U8 = () => new Uint8Array(MAXN), I16 = () => new Int16Array(MAXN);
    Object.assign(this, { x: F(), y: F(), z: F(), vx: F(), vy: F(), vz: F(), yaw: F(), hx: F(), hz: F(), hy: F(), t: F(), at: F(), bl: F(), prow: F(), tr: F(), tg: F(), tb: F(), sc: F(), tum: F(), tumR: F(), dur: F(), fx_: F(), fz_: F(), ph: F(),
      type: U8(), st: U8(), an: U8(), fixed: U8(), form: I16(), crew: I16() });
  },

  // ---------- spawning ----------
  _add(type, x, z, yaw, form, y = null) {
    const i = this.n++; this.type[i] = type; this.x[i] = this.hx[i] = x; this.z[i] = this.hz[i] = z; this.yaw[i] = yaw; this.form[i] = form ? form.id : -1; this.crew[i] = -1;
    if (y === null) { this.y[i] = terrain.height(x, z); this.fixed[i] = 0; } else { this.y[i] = y; this.fixed[i] = 1; } this.hy[i] = this.y[i];
    this.st[i] = ST.FORM; this.an[i] = A.Idle; this.at[i] = Math.random() * 2; this.bl[i] = 0; this.ph[i] = Math.random();
    const h = form ? form.herald : HERALD[0]; _c.setHex(h[0]); this.tr[i] = _c.r; this.tg[i] = _c.g; this.tb[i] = _c.b; this.sc[i] = type === TY.WARLORD ? 1.2 : 0.94 + Math.random() * 0.12; this.tum[i] = 0;
    if (form) { form.agents.push(i); if (type === TY.KNIGHT || type === TY.WARLORD) form.guard.push(i); }
    return i;
  },
  _form(kind, name, cx, cz, facing, heraldIdx) {
    const f = { id: this.forms.length, kind, name, cx, cz, cy: terrain.height(cx, cz), facing, herald: HERALD[heraldIdx % HERALD.length], agents: [], guard: [], initial: 0, alive: 0, guardAlive: 0, posture: 'hold', panicT: 0, panicCd: 0, routed: false, underFire: 0, alert: 0, volleyT: rnd(1, 5), volleying: false, radius: 20, bannerUp: true, banner: null, spotted: false, stationary: false };
    this.forms.push(f); return f;
  },
  _banner(f, tall = 1) {
    const pole = assets.props.scene.getObjectByName('BannerPole').clone(true); pole.traverse(o => { if (o.isMesh) { o.material = /Iron/.test(o.material.name) ? scenery.mats.iron : scenery.mats.prop; o.castShadow = true; } });
    const grp = new THREE.Group(); grp.add(pole); const cloth = scenery.makeBanner(1.5, 2.6, f.herald[0], f.herald[1], f.id % 6); cloth.position.set(0, 5.5, 0.09); grp.add(cloth);
    grp.position.set(f.cx, f.cy, f.cz); grp.rotation.y = f.facing; grp.scale.setScalar(1.9 * tall); this.scene.add(grp); f.banner = grp; f.bannerFall = 0;
  },
  _spawnAll() {
    const rng = mulberry32(99);
    // --- six infantry blocks with banner guards ---
    const E = Math.PI / 2; // facing east (+x)
    const blocks = [[112, -84], [118, 0], [112, 84], [46, -84], [52, 0], [46, 84]];
    const names = ['Red Boars', 'Blue Lions', 'Golden Hawks', 'Green Stags', 'Purple Wolves', 'White Bears'];
    blocks.forEach(([cx, cz], k) => {
      const f = this._form('infantry', names[k], cx, cz, E, k); const W = 20, D = 11, sp = 1.5;
      for (let r = 0; r < D; r++) for (let c = 0; c < W; c++) {
        const lx = (c - (W - 1) / 2) * sp + (rng() - 0.5) * 0.3, lz = ((D - 1) / 2 - r) * sp + (rng() - 0.5) * 0.3; if (Math.hypot(lx, lz) < 4.6) continue;
        this._add(TY.INF, cx + lz, cz - lx, E + (rng() - 0.5) * 0.15, f); // local (lx across, lz forward) with facing east
      }
      for (let i = 0; i < 12; i++) { const a = i / 12 * TAU, r = i % 2 ? 2.2 : 3.6; this._add(TY.KNIGHT, cx + Math.cos(a) * r, cz + Math.sin(a) * r, E, f); }
      f.radius = 21; this._banner(f);
      // file pennants at the corners of the block
      f.pennants = [[-1, -1], [1, -1], [1, 1], [-1, 1]].map(([a, b], q) => { const g = new THREE.Group(); const pole = new THREE.Mesh(_poleGeo, scenery.mats.prop); pole.castShadow = true; g.add(pole);
        const cl = scenery.makeBanner(0.9, 2.2, q % 2 ? f.herald[1] : f.herald[0], q % 2 ? f.herald[0] : f.herald[1], (k + q) % 6); cl.position.set(0, 5.0, 0.06); g.add(cl);
        g.userData.ox = b * (D * sp / 2 + 1.2); g.userData.oz = -a * (W * sp / 2 + 1.2); g.position.set(cx + g.userData.ox, terrain.height(cx + g.userData.ox, cz + g.userData.oz), cz + g.userData.oz); g.rotation.y = E; this.scene.add(g); return g; });
    });
    // --- archer companies (ground) ---
    const arch = [[82, -178, 'North Flank Archers'], [82, 178, 'South Flank Archers'], [300, -330, 'Village Archers'], [250, 70, 'Picket Archers']];
    arch.forEach(([cx, cz, name], k) => {
      const f = this._form('archers', name, cx, cz, E, 6 + k);
      for (let r = 0; r < 8; r++) for (let c = 0; c < 10; c++) { const lx = (c - 4.5) * 2.1 + (rng() - 0.5) * 0.6, lz = (3.5 - r) * 2.1 + (rng() - 0.5) * 0.6; this._add(TY.ARCH, cx + lz, cz - lx, E, f); }
      f.radius = 14; this._banner(f, 0.8);
    });
    // --- castle wall archers (two companies spread over the parapets) ---
    const spots = castle.wallSpots; const pick = [];
    for (let i = 0; i < spots.length; i += Math.max(1, Math.floor(spots.length / 165))) pick.push(spots[i]);
    const fE = this._form('archers', 'Gate Wall Archers', L.CASTLE.x + 62, L.CASTLE.z, E, 2), fW = this._form('archers', 'Curtain Wall Archers', L.CASTLE.x - 10, L.CASTLE.z, E, 4);
    fE.stationary = fW.stationary = true; fE.onWalls = fW.onWalls = true; fE.radius = fW.radius = 70; fE.cy = fW.cy = L.CASTLE.y + 13;
    pick.slice(0, 160).forEach(s => { const east = s.x > L.CASTLE.x + 40; const f = east ? fE : fW; const i = this._add(TY.ARCH, s.x, s.z, Math.atan2(s.x - L.CASTLE.x, s.z - L.CASTLE.z), f, s.y); this.wallOf = this.wallOf || new Map(); this.wallOf.set(i, s.wall); });
    // --- warlord and his guard in the courtyard ---
    { const cx = L.CASTLE.x + 22, cz = L.CASTLE.z; const f = this.guardForm = this._form('guard', "Warlord's Guard", cx, cz, E, 5); f.stationary = true; f.radius = 12;
      this.warlord = this._add(TY.WARLORD, cx, cz, E, f);
      for (let ring = 0; ring < 3; ring++) { const nn = 12 + ring * 8; for (let i = 0; i < nn; i++) { const a = i / nn * TAU + ring * 0.2, r = 3 + ring * 2.2; this._add(TY.KNIGHT, cx + Math.cos(a) * r, cz + Math.sin(a) * r, a + Math.PI / 2 * 0 + Math.atan2(Math.cos(a), Math.sin(a)) - a, f); } }
      this._banner(f, 1.3); f.banner.position.x -= 3; }
    // --- courtyard + camp garrison ---
    { const f = this.campForm = this._form('camp', 'Camp', -60, 10, E, 3); f.radius = 130;
      for (let i = 0; i < 150; i++) { const x = -150 + rng() * 190, z = -150 + rng() * 320; if (terrain.height(x, z) > 40) continue; this._add(rng() < 0.85 ? TY.INF : TY.ARCH, x, z, rng() * TAU, f); } }
    { const f = this.yardForm = this._form('camp', 'Garrison', L.CASTLE.x + 5, L.CASTLE.z, E, 0); f.stationary = true; f.radius = 60;
      for (let i = 0; i < 70; i++) { const x = L.CASTLE.x - 5 + (rng() - 0.5) * 80, z = L.CASTLE.z + (rng() - 0.5) * 70; if (Math.hypot(x - (L.CASTLE.x - 30), z - L.CASTLE.z) < 20 || Math.hypot(x - (L.CASTLE.x + 22), z) < 12) continue; if (Math.abs(z - L.CASTLE.z) > 30) continue; this._add(TY.INF, x, z, rng() * TAU, f); } }
    for (const f of this.forms) { f.initial = f.alive = f.agents.length; f.guardInit = f.guardAlive = f.guard.length; }
    this.total = this.n;
  },
  // crews for siege engines (called by threats): returns agent indices
  addCrew(x, y, z, n, radius, fixed) {
    if (!this.crewForm) { this.crewForm = this._form('crew', 'Crews', 0, 0, 0, 2); this.crewForm.stationary = true; }
    const out = []; for (let i = 0; i < n; i++) { const a = i / n * TAU + 0.5; const px = x + Math.cos(a) * radius, pz = z + Math.sin(a) * radius; const idx = this._add(TY.INF, px, pz, Math.atan2(x - px, z - pz), this.crewForm, fixed ? y : null); this.an[idx] = A.Crank; this.crew[idx] = 1; out.push(idx); }
    this.crewForm.initial = this.crewForm.alive = this.crewForm.agents.length; this.total = this.n; return out;
  },
  _saveInit() { this.init = { x: this.x.slice(), y: this.y.slice(), z: this.z.slice(), yaw: this.yaw.slice(), fixed: this.fixed.slice() }; },
  finalize() { this._saveInit(); },
  reset() {
    const I = this.init; this.hx.set(I.x); this.hz.set(I.z); for (const f of this.forms) if (f.cx0 !== undefined) { f.ox = f.oz = f.gx = f.gz = 0; f.cx = f.cx0; f.cz = f.cz0; f.cy = terrain.height(f.cx, f.cz); f.hitN = 0; if (f.banner) f.banner.position.set(f.cx, f.cy, f.cz); if (f.pennants) for (const g of f.pennants) { g.visible = true; g.rotation.z = 0; g.position.set(f.cx + g.userData.ox, terrain.height(f.cx + g.userData.ox, f.cz + g.userData.oz), f.cz + g.userData.oz); } }
    this.x.set(I.x); this.y.set(I.y); this.z.set(I.z); this.yaw.set(I.yaw); this.fixed.set(I.fixed);
    for (let i = 0; i < this.n; i++) { this.st[i] = ST.FORM; this.an[i] = this.form[i] === (this.crewForm ? this.crewForm.id : -9) ? A.Crank : A.Idle; this.at[i] = Math.random() * 2; this.bl[i] = 0; this.tum[i] = 0; this.vx[i] = this.vy[i] = this.vz[i] = 0; }
    for (const f of this.forms) { f.alive = f.initial; f.guardAlive = f.guardInit; f.posture = 'hold'; f.panicT = 0; f.panicCd = 0; f.routed = false; f.underFire = 0; f.alert = 0; f.volleyT = rnd(1, 5); f.volleying = false; f.bannerUp = true; f.spotted = false; if (f.banner) { f.banner.rotation.set(0, f.facing, 0); f.bannerFall = 0; f.banner.visible = true; } }
    this.killed = 0; this.routedCount = 0; this.warlordHp = 6; this.cheering = false;
  },

  setAnim(i, a, restart = true) {
    if (this.an[i] === a) return; const c = this.clip[this.an[i]];
    this.prow[i] = c.start + this._frame(c, this.at[i], i); this.bl[i] = 1; this.an[i] = a; if (restart) this.at[i] = LOOP[a] ? Math.random() * this.clip[a].dur : 0;
  },
  _frame(c, t, i) { const k = LOOP[this.an[i]] ? (t % c.dur) / c.dur : Math.min(t / c.dur, 1); return k * (c.frames - 1); },

  // ---------- damage ----------
  // explosion / impact: returns number killed. shieldPen 0..1 = how well shields are ignored (rockets 1, cannon 0.45)
  blast(x, y, z, radius, power = 8, shieldPen = 1) {
    let kills = 0; const reach = Math.max(radius * 2.6, 10.5); const r2 = reach * reach;
    for (let i = 0; i < this.n; i++) {
      const s = this.st[i]; if (s >= ST.THROWN) continue;
      const dx = this.x[i] - x, dz = this.z[i] - z; const d2 = dx * dx + dz * dz; if (d2 > r2) continue;
      const dy = this.y[i] + 0.9 - y; if (Math.abs(dy) > radius * 1.5 + 2) continue;
      const d = Math.sqrt(d2 + dy * dy * 0.5);
      const f = this.form[i] >= 0 ? this.forms[this.form[i]] : null;
      let pk = clamp(1.3 - d / radius, 0, 1);
      if (pk > 0 && s === ST.FORM && this.an[i] === A.ShieldUp && d > 1.0) pk *= shieldPen;
      if (shieldPen < 1 && (this.type[i] === TY.KNIGHT || i === this.warlord) && d > 0.8) pk *= 0.45;   // plate armour shrugs off fragments
      if (pk > 0 && Math.random() < pk) {
        if (i === this.warlord && --this.warlordHp > 0) { this.st[i] = ST.PANIC; this.t[i] = 0; this.dur[i] = 1.5; this.fx_[i] = x; this.fz_[i] = z; continue; }
        const k = clamp(1.2 - d / radius, 0.25, 1) * power; const dl = Math.sqrt(d2) || 1;
        this.kill(i, dx / dl * k * rnd(0.5, 1.1) + rndS(1), k * rnd(0.55, 1.2) + 2, dz / dl * k * rnd(0.5, 1.1) + rndS(1)); kills++;
      } else if (s === ST.FORM || s === ST.PANIC) {
        if (f) { f.underFire = 4; f.hitX = x; f.hitZ = z; f.hitN = (f.hitN || 0) + 1; }
        if (d < reach && Math.random() < (d < radius * 2.6 ? 0.85 : 0.5)) { this.st[i] = ST.PANIC; this.t[i] = 0; this.dur[i] = rnd(1.8, 4); this.fx_[i] = x; this.fz_[i] = z; }
      }
    }
    return kills;
  },
  kill(i, vx = 0, vy = 3, vz = 0) {
    if (this.st[i] >= ST.THROWN) return;
    this.st[i] = ST.THROWN; this.vx[i] = vx; this.vy[i] = vy; this.vz[i] = vz; this.tumR[i] = rndS(9); this.t[i] = 0; this.setAnim(i, A.Thrown);
    this.killed++;
    const f = this.form[i] >= 0 ? this.forms[this.form[i]] : null;
    if (f) { f.alive--; f.underFire = 4; f.hitX = this.x[i]; f.hitZ = this.z[i]; f.hitN = (f.hitN || 0) + 1; if (this.type[i] === TY.KNIGHT || this.type[i] === TY.WARLORD) f.guardAlive--; }
    if (i === this.warlord) G.events.dispatchEvent(new CustomEvent('warlordDead'));
    G.events.dispatchEvent(new CustomEvent('kill', { detail: i }));
  },
  isAlive(i) { return this.st[i] < ST.THROWN; },
  rout(f, hx, hz) {
    if (f.routed || f.stationary) return; f.routed = true; f.posture = 'rout'; f.bannerUp = false; this.routedCount++;
    for (const i of f.agents) if (this.st[i] < ST.ROUT) { this.st[i] = ST.ROUT; this.t[i] = -Math.random() * 1.2; this.dur[i] = rnd(22, 40); const ax = this.x[i] - hx, az = this.z[i] - hz, al = Math.hypot(ax, az) || 1; const a = Math.atan2(ax / al + rndS(0.5), az / al + rndS(0.5)); this.fx_[i] = Math.sin(a); this.fz_[i] = Math.cos(a); }
    audio.play('hornRout', { pos: [f.cx, f.cy + 2, f.cz] }); audio.play('scream', { pos: [f.cx, f.cy + 2, f.cz] });
    G.events.dispatchEvent(new CustomEvent('formationRouted', { detail: f }));
  },
  panic(f, sx, sz, dur = 8) {
    if (f.routed || f.panicT > 0) return; f.panicT = dur; f.posture = 'panic'; f.panicCd = dur + 6;
    for (const i of f.agents) if (this.st[i] === ST.FORM) { this.st[i] = ST.PANIC; this.t[i] = -Math.random() * 0.5; this.dur[i] = dur * rnd(0.8, 1.1); this.fx_[i] = sx + rndS(8); this.fz_[i] = sz + rndS(8); }
    audio.play('scream', { pos: [f.cx, f.cy + 2, f.cz] });
    G.events.dispatchEvent(new CustomEvent('formationPanic', { detail: f }));
  },
  cheer() { this.cheering = true; for (let i = 0; i < this.n; i++) if (this.st[i] <= ST.PANIC) { this.st[i] = ST.CHEER; this.setAnim(i, A.Cheer); } },
  // a structure fell: everyone standing on it goes with it
  structFell(s) {
    for (let i = 0; i < this.n; i++) { if (!this.fixed[i] || this.st[i] >= ST.THROWN) continue; const d = Math.hypot(this.x[i] - s.x, this.z[i] - s.z); const lim = s.type === 'tower' ? s.r + 1.5 : s.len / 2 + 1; if (d < lim && Math.abs(this.y[i] - s.topY) < 3) { this.fixed[i] = 0; this.kill(i, rndS(4), rnd(1, 5), rndS(4)); } }
  },

  // ---------- update ----------
  update(dt, heli, camera) {
    const hx = heli.pos.x, hy = heli.pos.y, hz = heli.pos.z; const hspeed = heli.speed; const alive = heli.state === 'fly';
    let panicAcc = 0, strength = 0;
    // formation logic
    for (const f of this.forms) {
      if (f.kind === 'crew') continue;
      const dxz = Math.hypot(hx - f.cx, hz - f.cz); const agl = hy - f.cy;
      f.dist = dxz; f.underFire = Math.max(0, f.underFire - dt); f.panicCd = Math.max(0, f.panicCd - dt);
      if (dxz < 420 && alive) f.spotted = true;
      if (f.routed) { if (f.pennants) for (const g of f.pennants) if (g.rotation.z < 1.4) g.rotation.z = Math.min(1.4, g.rotation.z + dt * 1.1); continue; }
      strength += f.alive;
      // the block is alive: it edges toward the helicopter under shields, and shifts ground when fire lands on it
      if (!f.stationary && (f.kind === 'infantry' || f.kind === 'archers') && this.init) {
        if (f.cx0 === undefined) { f.cx0 = f.cx; f.cz0 = f.cz; f.ox = f.oz = f.gx = f.gz = 0; f.dodgeCd = 0; }
        f.dodgeCd -= dt;
        if (f.hitN > 0 && f.dodgeCd <= 0) {
          let ax = f.cx - f.hitX, az = f.cz - f.hitZ; let al = Math.hypot(ax, az); if (al < 2.5) { const a = Math.random() * TAU; ax = Math.cos(a); az = Math.sin(a); al = 1; }
          const step = f.kind === 'archers' ? 34 : 24; f.gx = f.ox + ax / al * step; f.gz = f.oz + az / al * step; f.dodgeCd = 3.2;
        } else if (f.underFire <= 0 && f.panicT <= 0 && f.dodgeCd <= -4) {
          if (alive && dxz < 430 && dxz > 90) { const k = (f.kind === 'archers' ? -30 : 55) / dxz; f.gx = (hx - f.cx0) * k; f.gz = (hz - f.cz0) * k; } else { f.gx = 0; f.gz = 0; }
        }
        f.hitN = 0;
        const gl = Math.hypot(f.gx, f.gz); if (gl > 85) { f.gx *= 85 / gl; f.gz *= 85 / gl; }
        const ex = f.gx - f.ox, ez = f.gz - f.oz, el = Math.hypot(ex, ez);
        if (el > 0.05) {
          const sp = Math.min(el, (f.underFire > 0 ? 3.0 : 1.25) * dt); f.ox += ex / el * sp; f.oz += ez / el * sp;
          f.cx = f.cx0 + f.ox; f.cz = f.cz0 + f.oz; f.cy = terrain.height(f.cx, f.cz);
          const IX = this.init.x, IZ = this.init.z; for (const i of f.agents) { this.hx[i] = IX[i] + f.ox; this.hz[i] = IZ[i] + f.oz; }
          if (f.banner && f.bannerFall <= 0) f.banner.position.set(f.cx, f.cy, f.cz);
          if (f.pennants) for (const g of f.pennants) g.position.set(f.cx + g.userData.ox, terrain.height(f.cx + g.userData.ox, f.cz + g.userData.oz), f.cz + g.userData.oz);
        }
      }
      f.alert = damp(f.alert, alive && dxz < 380 ? 1 : 0, 2, dt);
      if (f.panicT > 0) { f.panicT -= dt; panicAcc += f.alive; if (f.panicT <= 0) f.posture = 'shield'; }
      else {
        f.posture = (f.alert > 0.5 || f.underFire > 0) ? 'shield' : 'hold';
        // low fast pass → panic (breaks the shield wall for 8 s)
        if (alive && !f.stationary && f.panicCd <= 0 && dxz < f.radius + 22 && agl < 32 && agl > -5 && hspeed > 17) this.panic(f, hx, hz, 8);
      }
      // morale
      if (!f.stationary && f.kind !== 'camp') {
        if (f.guardInit > 0 && f.guardAlive <= Math.floor(f.guardInit * 0.25)) this.rout(f, hx, hz);
        else if (f.alive < f.initial * (f.kind === 'archers' ? 0.5 : 0.5)) this.rout(f, hx, hz);
      } else if (f.kind === 'camp' && !f.stationary && f.alive < f.initial * 0.6) this.rout(f, hx, hz);
      // banner
      if (f.banner) { if (!f.bannerUp || f.routed) { } }
    }
    for (const f of this.forms) if (f.banner && (f.routed || (f.guardInit > 0 && f.guardAlive <= 0)) && f.bannerFall < 1) { f.bannerFall = Math.min(1, f.bannerFall + dt * 0.9); const k = f.bannerFall * f.bannerFall; f.banner.rotation.z = k * 1.45; if (f.bannerFall >= 1 && !f.dusted) { f.dusted = true; fx.dustRing(f.cx + 6, f.cy, f.cz, 2, 6, 3); } }
    this.strength = strength / Math.max(1, this.total); this.panicLevel = damp(this.panicLevel, sat(panicAcc / 300 + this.routedCount * 0.08), 2, dt);

    // agents
    const clip = this.clip; const B = this.buckets; for (const t of B) for (const b of t) if (b) b.n = 0;
    const cx = camera.position.x, cy = camera.position.y, cz = camera.position.z;
    const n = this.n;
    for (let i = 0; i < n; i++) {
      let s = this.st[i]; if (s === ST.FLED) continue;
      const f = this.form[i] >= 0 ? this.forms[this.form[i]] : null;
      if (s !== ST.DEAD) {
        this.at[i] += dt; if (this.bl[i] > 0) this.bl[i] = Math.max(0, this.bl[i] - dt * 4.5);
        if (s === ST.FORM) {
          // posture → animation
          const post = f ? f.posture : 'hold';
          const dxh = this.x[i] - this.hx[i], dzh = this.z[i] - this.hz[i]; const dh = dxh * dxh + dzh * dzh;
          if (dh > 0.2 && !this.fixed[i]) { // walk back to the slot
            const l = Math.sqrt(dh), far_ = l > 3.5, sp = Math.min(far_ ? 4.6 : 1.9, l / dt); this.x[i] -= dxh / l * sp * dt; this.z[i] -= dzh / l * sp * dt; this.y[i] = terrain.height(this.x[i], this.z[i]); this.yaw[i] += wrapPi(Math.atan2(-dxh, -dzh) - this.yaw[i]) * Math.min(1, dt * 6); this.setAnim(i, far_ ? A.Run : A.Walk);
          } else {
            let want = this.an[i];
            if (this.crew[i] >= 0) want = this.crew[i] === 1 ? A.Crank : A.Idle;
            else if (f && f.volleying && this.type[i] === TY.ARCH) want = A.Volley;
            else if (post === 'shield') { if (this.an[i] === A.Attack && this.at[i] < clip[A.Attack].dur) want = A.Attack; else want = (this.type[i] !== TY.ARCH && f && f.dist < 170 && f.dist > 40 && Math.random() < dt * 0.12) ? A.Attack : (this.type[i] === TY.ARCH ? A.Idle : A.ShieldUp); }
            else want = A.Idle;
            if (want !== this.an[i]) { if (want === A.Volley) { this.setAnim(i, want); this.at[i] = f.volleyClock - this.ph[i] * 0.25; } else if (Math.random() < dt * 5 || want === A.Attack) this.setAnim(i, want); }
            // face the helicopter when alert
            if (f && f.alert > 0.5 && this.crew[i] < 0 && !(this.fixed[i] && this.type[i] !== TY.ARCH)) { const ty = Math.atan2(hx - this.x[i], hz - this.z[i]); this.yaw[i] += wrapPi(ty - this.yaw[i]) * Math.min(1, dt * 2.5); }
          }
        } else if (s === ST.PANIC) {
          this.t[i] += dt; const t = this.t[i];
          if (t > this.dur[i]) { this.st[i] = ST.FORM; }
          else if (t > 0 && t < 2.3 && !this.fixed[i]) { // scatter from the source
            const ax = this.x[i] - this.fx_[i], az = this.z[i] - this.fz_[i], al = Math.hypot(ax, az) || 1; const sp = 5.4 * (1 - t / 2.3) + 1.2;
            this.x[i] += ax / al * sp * dt; this.z[i] += az / al * sp * dt; this.y[i] = terrain.height(this.x[i], this.z[i]); this.yaw[i] += wrapPi(Math.atan2(ax, az) - this.yaw[i]) * Math.min(1, dt * 8); this.setAnim(i, A.Run);
          } else if (t > 0) this.setAnim(i, A.Panic);
        } else if (s === ST.ROUT) {
          this.t[i] += dt; const t = this.t[i];
          if (t > 0) {
            const sp = 5.2 + this.ph[i] * 1.6; let dx = this.fx_[i], dz = this.fz_[i];
            // keep running away from the helicopter if it is close
            const ax = this.x[i] - hx, az = this.z[i] - hz, al = Math.hypot(ax, az); if (al < 120 && al > 1) { dx = lerp(dx, ax / al, dt * 1.5); dz = lerp(dz, az / al, dt * 1.5); const l = Math.hypot(dx, dz) || 1; this.fx_[i] = dx / l; this.fz_[i] = dz / l; }
            const nx = this.x[i] + dx * sp * dt, nz = this.z[i] + dz * sp * dt; const ny = terrain.height(nx, nz);
            if (ny < L.WATER_Y - 0.6 || ny - this.y[i] > sp * dt * 1.2) { const a = Math.atan2(dx, dz) + (this.ph[i] > 0.5 ? 1.2 : -1.2); this.fx_[i] = Math.sin(a); this.fz_[i] = Math.cos(a); }
            else { this.x[i] = nx; this.z[i] = nz; this.y[i] = ny; }
            this.yaw[i] += wrapPi(Math.atan2(dx, dz) - this.yaw[i]) * Math.min(1, dt * 7); this.setAnim(i, A.Run);
            if (t > this.dur[i]) { this.st[i] = ST.FLED; if (f) f.alive--; continue; }
          } else this.setAnim(i, A.Panic);
        } else if (s === ST.THROWN) {
          this.vy[i] -= 9.81 * dt; this.x[i] += this.vx[i] * dt; this.y[i] += this.vy[i] * dt; this.z[i] += this.vz[i] * dt; this.tum[i] += this.tumR[i] * dt;
          const g = terrain.height(this.x[i], this.z[i]);
          if (this.y[i] <= g && this.vy[i] < 0) { this.y[i] = g; this.st[i] = ST.DYING; this.setAnim(i, A.Die); this.at[i] = clip[A.Die].dur * 0.55; this.t[i] = 0; if (Math.abs(this.vy[i]) > 5) fx.dust(this.x[i], g + 0.3, this.z[i], rndS(1), 1, rndS(1), 0.8, 1.2, 0.3); }
        } else if (s === ST.DYING) {
          this.tum[i] *= Math.exp(-dt * 10); this.t[i] += dt; if (this.at[i] >= clip[A.Die].dur && this.t[i] > 0.6) { this.st[i] = ST.DEAD; this.tum[i] = 0; this.bl[i] = 0; this.at[i] = clip[A.Die].dur; }
        }
      }
      // write instance
      const ty = this.type[i]; const dx = this.x[i] - cx, dy = this.y[i] - cy, dz = this.z[i] - cz; const d2 = dx * dx + dy * dy + dz * dz;
      const lod = (d2 > LOD_D * LOD_D && B[ty][1]) ? 1 : 0; const b = B[ty][lod]; if (b.n >= b.cap) continue; const o = b.n++ * 4;
      const c = clip[this.an[i]]; const fr = LOOP[this.an[i]] ? ((this.at[i] % c.dur) / c.dur) * (c.frames - 1) : Math.min(Math.max(this.at[i], 0) / c.dur, 1) * (c.frames - 1);
      const P = b.iPos.array, An = b.iAnim.array, T = b.iTint.array;
      P[o] = this.x[i]; P[o + 1] = this.y[i]; P[o + 2] = this.z[i]; P[o + 3] = this.yaw[i];
      An[o] = c.start + fr; An[o + 1] = this.prow[i]; An[o + 2] = this.bl[i]; An[o + 3] = this.sc[i];
      T[o] = this.tr[i]; T[o + 1] = this.tg[i]; T[o + 2] = this.tb[i]; T[o + 3] = this.tum[i];
    }
    for (const t of B) for (const b of t) if (b) { b.geo.instanceCount = b.n; b.iPos.needsUpdate = b.iAnim.needsUpdate = b.iTint.needsUpdate = true; b.mesh.visible = b.n > 0; }
  },
};
