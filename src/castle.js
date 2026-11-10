// Siege Wing — the castle: procedural masonry, destructible towers / wall sections / gate, colliders, mounts, courtyard and the crag it stands on
import * as THREE from 'three';
import { G, V3, patchMaterial, rnd, rndS, clamp, mulberry32, TAU, lerp } from './core.js';
import { assets } from './assets.js';
import { terrain, L } from './terrain.js';
import { world } from './world.js';
import { GB } from './geo.js';
import { fx } from './fx.js';
import { audio } from './audio.js';
import { scenery } from './scenery.js';

const C = L.CASTLE;
// vertex colours double as material ids in the stone shader: neutral = masonry, bluish = slate, warm = wood, below 0.1 = window that glows at dusk
const STONE = [1, 1, 1], DRESS = [1.14, 1.12, 1.08], MID = [0.8, 0.8, 0.8], DIM = [0.6, 0.59, 0.57], RUB = [0.7, 0.68, 0.64], CORE = [0.4, 0.39, 0.37], HOLE = [0.2, 0.19, 0.18], IRON = [0.17, 0.17, 0.18];
const DARK = [0.08, 0.07, 0.06], SLATE = [0.5, 0.52, 0.6], WOODC = [0.75, 0.6, 0.45], WOODD = [0.5, 0.38, 0.27];
const TREBS = [[-112, -44], [-120, 2], [-112, 48]]; // trebuchet emplacements west of the walls (castle-relative)
const _v = new V3();

// ---- small modelling helpers ----
// local frame at (x, z) with yaw ry: (lx, y, lz) -> world point; local +x runs along, local +z is "out"
const frame = (x, z, ry) => { const c = Math.cos(ry), s = Math.sin(ry); return (lx, y, lz) => [x + lx * c + lz * s, y, z - lx * s + lz * c]; };
// frame sitting on a face of another frame: origin at F(lx, ., lz), turned by dry
const faceOf = (F, ry, lx, lz, dry = 0) => { const o = F(lx, 0, lz); return frame(o[0], o[2], ry + dry); };
const rect = (F, x0, x1, y, z0, z1) => { const xa = Math.min(x0, x1), xb = Math.max(x0, x1), za = Math.min(z0, z1), zb = Math.max(z0, z1); return [F(xa, y, zb), F(xb, y, zb), F(xb, y, za), F(xa, y, za)]; };
const slab = (g, F, x0, x1, y0, y1, z0, z1, col, faces = 5, uo = 0) => g.hexa(rect(F, x0, x1, y0, z0, z1), rect(F, x0, x1, y1, z0, z1), col, faces, uo);
// prism between two points of a frame (beams, braces, chains): a = [lx, y, lz], b likewise; w wide, t deep
const beam = (g, F, a, b, w, t, col) => { const hw = w / 2; g.hexa([F(a[0] - hw, a[1], a[2] + t / 2), F(a[0] + hw, a[1], a[2] + t / 2), F(a[0] + hw, a[1], a[2] - t / 2), F(a[0] - hw, a[1], a[2] - t / 2)], [F(b[0] - hw, b[1], b[2] + t / 2), F(b[0] + hw, b[1], b[2] + t / 2), F(b[0] + hw, b[1], b[2] - t / 2), F(b[0] - hw, b[1], b[2] - t / 2)], col, 7); };
// moulded string course round a drum
const band = (g, x, y, z, r, proud, h, seg, col) => { g.cyl(x, y, z, r, r + proud, h * 0.3, seg, col, false); g.cyl(x, y + h * 0.3, z, r + proud, r + proud, h * 0.4, seg, col, false); g.cyl(x, y + h * 0.7, z, r + proud, r, h * 0.3, seg, col, false); };
// arrow loop: dressed surround and a cross slit; F is a face frame (local +z out of the wall)
const loop = (g, F, lx, y, h = 2.0) => {
  slab(g, F, lx - 0.42, lx + 0.42, y - h / 2 - 0.28, y + h / 2 + 0.28, 0, 0.13, DRESS, 5);
  slab(g, F, lx - 0.1, lx + 0.1, y - h / 2, y + h / 2, 0.13, 0.17, DARK, 5);
  slab(g, F, lx - 0.3, lx + 0.3, y + h * 0.12, y + h * 0.12 + 0.2, 0.13, 0.17, DARK, 5);
};
// window: dressed surround round a dark opening (firelit at dusk), optionally with a pointed head
const win = (g, F, lx, y, w, h, pointed = false, col = DARK) => {
  const hw = w / 2, y0 = y - h / 2, y1 = y + h / 2;
  slab(g, F, lx - hw - 0.22, lx + hw + 0.22, y0 - 0.22, y1 + 0.1, 0, 0.12, DRESS, 5);
  slab(g, F, lx - hw, lx + hw, y0, y1, 0.12, 0.16, col, 5);
  if (pointed) {
    const ya = y1 + 0.1 + w * 0.9 + 0.25, yb = y1 + w * 0.9;
    g.hexa(rect(F, lx - hw - 0.22, lx + hw + 0.22, y1 + 0.1, 0, 0.12), [F(lx, ya, 0.12), F(lx, ya, 0.12), F(lx, ya, 0), F(lx, ya, 0)], DRESS, 4);
    g.hexa(rect(F, lx - hw, lx + hw, y1, 0.12, 0.16), [F(lx, yb, 0.16), F(lx, yb, 0.16), F(lx, yb, 0.12), F(lx, yb, 0.12)], col, 4);
  }
};
// crenellated parapet strip along a frame: breast wall with coped merlons, every other one pierced by a slit; z0..z1 is its thickness, +z1 the outer face
const parapet = (g, F, x0, x1, y, z0, z1, uo = 0, skip = null) => {
  const len = x1 - x0; const n = Math.max(2, Math.round(len / 2.6)); const pw = len / n; const mw = Math.min(pw * 0.31, 0.85);
  for (let i = 0; i < n; i++) { const lx = x0 + (i + 0.5) * pw; if (skip && skip(lx)) continue;
    slab(g, F, lx - mw, lx + mw, y, y + 1.4, z0, z1, STONE, 5, uo + lx); slab(g, F, lx - mw - 0.08, lx + mw + 0.08, y + 1.4, y + 1.55, z0 - 0.08, z1 + 0.08, DRESS, 7);
    if (i % 2) slab(g, F, lx - 0.07, lx + 0.07, y + 0.3, y + 1.1, z1, z1 + 0.02, HOLE, 4); }
};
// pitched roof over a frame-aligned footprint (ridge along local x): two slopes with eave overhang
const roof = (g, F, hx, hz, y, rise, over, col) => {
  const k = rise / hz, ye = y - over * k, sl = Math.hypot(hz + over, rise + over * k);
  g.quad(F(-hx, ye, hz + over), F(hx, ye, hz + over), F(hx, y + rise, 0), F(-hx, y + rise, 0), [0, 0], [hx * 2, 0], [hx * 2, sl], [0, sl], col);
  g.quad(F(hx, ye, -hz - over), F(-hx, ye, -hz - over), F(-hx, y + rise, 0), F(hx, y + rise, 0), [0, 0], [hx * 2, 0], [hx * 2, sl], [0, sl], col);
};

function stoneMaterial() {
  const m = new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.92, metalness: 0, vertexColors: true });
  return patchMaterial(m, 'stone', sh => {
    sh.vertexShader = sh.vertexShader.replace('#include <common>', '#include <common>\nvarying vec2 vSU; varying vec3 vSN; varying vec3 vSW;')
      .replace('#include <begin_vertex>', '#include <begin_vertex>\n vSU = uv; vSN = normalize(mat3(modelMatrix) * normal); vSW = (modelMatrix * vec4(transformed, 1.0)).xyz;');
    sh.fragmentShader = sh.fragmentShader.replace('#include <common>', `#include <common>
      varying vec2 vSU; varying vec3 vSN; varying vec3 vSW; uniform sampler2D uNoise; uniform float uNight; uniform float uTime; vec3 swNP; float swR;
      uniform sampler2DArray uCA; uniform sampler2DArray uCB; uniform vec3 uCMean[3];
      float h21(vec2 p){ return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }`)
      .replace('#include <color_fragment>', /* glsl */`#include <color_fragment>
      {
        float kind = vColor.b > vColor.r + 0.05 ? 1.0 : (vColor.r > vColor.b + 0.12 ? 2.0 : 0.0); // slate roofs are bluish, wood is warm
        float camD = length(vSW - cameraPosition); float det = smoothstep(420.0, 60.0, camD);
        vec2 uvm = vSU; bool top = vSN.y > 0.7;
        float n1 = texture2D(uNoise, vSW.xz * 0.013 + vSW.y * 0.021).r, n2 = texture2D(uNoise, uvm * 0.07).g, n3 = texture2D(uNoise, uvm * 0.45).b, n4 = texture2D(uNoise, uvm * 1.9).a;
        vec3 col; swNP = vec3(0.0); swR = 0.92;
        if (kind < 0.5) {
          float course = top ? 1.1 : 0.62; float bw = top ? 1.3 : 1.05;
          float row = floor(uvm.y / course); float off = fract(row * 0.5) * 0.9 + h21(vec2(row, 3.0)) * 0.35;
          float bx = uvm.x / bw + off; vec2 cell = vec2(floor(bx), row); vec2 f = vec2(fract(bx), fract(uvm.y / course));
          float hsh = h21(cell);
          float ex = 0.045, ey = 0.075;
          float mort = smoothstep(0.0, ex, f.x) * smoothstep(1.0, 1.0 - ex, f.x) * smoothstep(0.0, ey, f.y) * smoothstep(1.0, 1.0 - ey, f.y);
          mort = mix(1.0, mort, det);
          vec3 stone = mix(vec3(0.30, 0.275, 0.24), vec3(0.47, 0.435, 0.37), hsh * det + 0.5 * (1.0 - det));
          stone = mix(stone, stone * vec3(1.12, 0.96, 0.78), step(0.82, h21(cell + 7.7)) * 0.6 * det);
          stone *= 0.72 + 0.5 * n3 + (n4 - 0.5) * 0.3 * det;
          col = mix(vec3(0.15, 0.135, 0.115), stone, mort);
          // weathering: streaks, damp base, sooty tops
          float streak = smoothstep(0.45, 0.8, texture2D(uNoise, vec2(uvm.x * 0.045, uvm.y * 0.004)).r);
          col *= 1.0 - 0.38 * streak * (top ? 0.3 : 1.0);
          col = mix(col, col * vec3(0.62, 0.72, 0.5), smoothstep(0.5, 0.75, n2) * 0.35);       // lichen
          col *= 0.75 + 0.5 * n1;
          // photoscanned masonry over the procedural coursing: dressed ashlar with patches of older rubble stonework
          { vec2 t0 = uvm / 3.3, t1 = uvm / 3.7 + 0.37; float rub = smoothstep(0.52, 0.7, n1 * 0.6 + n2 * 0.5) * (top ? 0.3 : 1.0);
            vec4 A = mix(texture(uCA, vec3(t0, 0.0)), texture(uCA, vec3(t1, 1.0)), rub), B = mix(texture(uCB, vec3(t0, 0.0)), texture(uCB, vec3(t1, 1.0)), rub);
            vec3 mean = mix(uCMean[0], uCMean[1], rub); vec3 ph = A.rgb / mean * vec3(0.40, 0.365, 0.31) * mix(1.0, B.a, 0.7);
            col = ph * clamp(col / max(mix(vec3(0.15, 0.135, 0.115), stone, mort), vec3(1e-3)), 0.0, 1.6);
            vec2 nt = B.rg * 2.0 - 1.0; vec3 T = top ? vec3(1.0, 0.0, 0.0) : normalize(cross(vec3(0.0, 1.0, 0.0), vSN) + 1e-4); vec3 Bt = top ? vec3(0.0, 0.0, -1.0) : vec3(0.0, 1.0, 0.0);
            swNP = (T * nt.x + Bt * nt.y) * 0.9; swR = 0.72 + 0.28 * B.b; }
        } else if (kind < 1.5) { // slate
          float row = floor(uvm.y / 0.42); float bx = uvm.x / 0.5 + fract(row * 0.5); vec2 f = vec2(fract(bx), fract(uvm.y / 0.42));
          float hsh = h21(vec2(floor(bx), row));
          col = mix(vec3(0.10, 0.11, 0.135), vec3(0.19, 0.20, 0.24), hsh) * (0.75 + 0.5 * n3);
          { vec2 t0 = uvm / 2.6; vec4 A = texture(uCA, vec3(t0, 2.0)), B = texture(uCB, vec3(t0, 2.0)); col = A.rgb / uCMean[2] * vec3(0.135, 0.145, 0.175) * (0.8 + 0.4 * n3) * mix(1.0, B.a, 0.7);
            vec2 nt = B.rg * 2.0 - 1.0; swNP = vec3(nt.x, 0.0, -nt.y) * 0.6; swR = 0.5 + 0.3 * B.b; }
        } else { // wood planks
          float bx = uvm.x / 0.32; float hsh = h21(vec2(floor(bx), 1.0));
          col = mix(vec3(0.13, 0.085, 0.05), vec3(0.22, 0.15, 0.09), hsh) * (0.7 + 0.6 * texture2D(uNoise, vec2(uvm.x * 2.0, uvm.y * 0.08)).r);
          col *= mix(1.0, smoothstep(0.0, 0.08, fract(bx)), det); swR = 0.8;
        }
        float shade = max(vColor.r, max(vColor.g, vColor.b));
        diffuseColor.rgb = col * (kind < 0.5 ? vColor.rgb : vec3(shade));
      }`)
      .replace('#include <roughnessmap_fragment>', 'float roughnessFactor = swR;')
      .replace('#include <normal_fragment_maps>', 'normal = normalize(normal + (viewMatrix * vec4(swNP, 0.0)).xyz);')
      // windows and arrow slits (the DARK vertex colour) glow with firelight as dusk falls; about two in three are lit, each flickering slightly
      .replace('#include <emissivemap_fragment>', `#include <emissivemap_fragment>
      { float isWin = step(max(vColor.r, max(vColor.g, vColor.b)), 0.1); if (isWin > 0.5) { float id = h21(floor(vSW.xz * 0.35) + floor(vSW.y * 0.2) * 17.0);
          float fl = 0.8 + 0.2 * sin(uTime * (5.0 + id * 9.0) + id * 40.0); totalEmissiveRadiance += vec3(1.0, 0.47, 0.13) * step(0.34, id) * fl * smoothstep(0.12, 0.75, uNight) * 3.2; } }`);
  }, { uCA: { value: assets.masonry.A }, uCB: { value: assets.masonry.B }, uCMean: { value: assets.masonry.mean } });
}

// bare rock of the crag: the terrain's photoscanned cliff rock projected triplanar in world space, lichen and dry turf on the flats
function cragMaterial() {
  const gr = assets.ground; const m = new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.95, metalness: 0, vertexColors: true });
  return patchMaterial(m, 'crag', sh => {
    sh.vertexShader = sh.vertexShader.replace('#include <common>', '#include <common>\nvarying vec3 vPW;').replace('#include <begin_vertex>', '#include <begin_vertex>\n vPW = (modelMatrix * vec4(transformed, 1.0)).xyz;');
    sh.fragmentShader = sh.fragmentShader.replace('#include <common>', `#include <common>
      varying vec3 vPW; uniform sampler2D uNoise; uniform sampler2DArray uGA; uniform sampler2DArray uGB; uniform vec3 uGMean[${gr.n}]; vec3 swRkN; float swRkR;`)
      .replace('#include <color_fragment>', /* glsl */`#include <color_fragment>
      { vec3 dx = dFdx(vPW), dy = dFdy(vPW); vec3 gn = normalize(cross(dx, dy)); vec3 w = abs(gn); w = w * w; w = w * w; w /= (w.x + w.y + w.z);
        vec3 c = vec3(0.0), c2 = vec3(0.0); vec4 b = vec4(0.0); vec3 nn = vec3(0.0); const float s = 1.0 / 3.4, s2 = 1.0 / 23.0;
        if (w.y > 0.03) { c += textureGrad(uGA, vec3(vPW.xz * s, 4.0), dx.xz * s, dy.xz * s).rgb * w.y; c2 += textureGrad(uGA, vec3(vPW.xz * s2, 8.0), dx.xz * s2, dy.xz * s2).rgb * w.y; vec4 B = textureGrad(uGB, vec3(vPW.xz * s, 4.0), dx.xz * s, dy.xz * s); b += B * w.y; vec2 n = B.rg * 2.0 - 1.0; nn += vec3(n.x, 0.0, -n.y) * w.y; }
        if (w.x > 0.03) { vec2 u = vec2(vPW.z, -vPW.y), ux = vec2(dx.z, -dx.y), uy = vec2(dy.z, -dy.y); c += textureGrad(uGA, vec3(u * s, 4.0), ux * s, uy * s).rgb * w.x; c2 += textureGrad(uGA, vec3(u * s2, 8.0), ux * s2, uy * s2).rgb * w.x; vec4 B = textureGrad(uGB, vec3(u * s, 4.0), ux * s, uy * s); b += B * w.x; vec2 n = B.rg * 2.0 - 1.0; nn += vec3(0.0, n.y, n.x) * w.x; }
        if (w.z > 0.03) { vec2 u = vec2(vPW.x, -vPW.y), ux = vec2(dx.x, -dx.y), uy = vec2(dy.x, -dy.y); c += textureGrad(uGA, vec3(u * s, 4.0), ux * s, uy * s).rgb * w.z; c2 += textureGrad(uGA, vec3(u * s2, 8.0), ux * s2, uy * s2).rgb * w.z; vec4 B = textureGrad(uGB, vec3(u * s, 4.0), ux * s, uy * s); b += B * w.z; vec2 n = B.rg * 2.0 - 1.0; nn += vec3(n.x, n.y, 0.0) * w.z; }
        vec3 rock = diffuseColor.rgb * (c / uGMean[4]) * mix(vec3(1.0), c2 / uGMean[8], 0.6) * mix(1.0, b.a, 0.7) * 1.1;
        float n1 = texture2D(uNoise, vPW.xz * 0.031).r, n2 = texture2D(uNoise, vPW.xz * 0.19 + vPW.y * 0.07).g;
        float upf = gl_FrontFacing ? gn.y : -gn.y; float turf = smoothstep(0.62, 0.92, abs(upf)) * step(0.0, upf + 2.0) * smoothstep(0.3, 0.62, n1 * 0.6 + n2 * 0.5);
        rock = mix(rock, vec3(0.115, 0.105, 0.06) * (0.6 + 0.9 * n2) * (0.7 + 0.6 * dot(c, vec3(0.33)) / dot(uGMean[4], vec3(0.33))), turf * 0.8);
        rock *= 1.0 - 0.3 * smoothstep(0.55, 0.8, texture2D(uNoise, vec2(vPW.x + vPW.z, vPW.y * 0.25) * 0.02).b) * (1.0 - abs(gn.y)); // water staining down the faces
        diffuseColor.rgb = rock; swRkN = nn * 1.4 * (1.0 - turf * 0.6); swRkR = b.b; }`)
      .replace('#include <roughnessmap_fragment>', '#include <roughnessmap_fragment>\n roughnessFactor = 0.78 + 0.22 * swRkR;')
      .replace('#include <normal_fragment_maps>', '#include <normal_fragment_maps>\n normal = normalize(normal + (viewMatrix * vec4(swRkN, 0.0)).xyz);');
  }, { uGA: { value: gr.A }, uGB: { value: gr.B }, uGMean: { value: gr.mean } });
}

export const castle = {
  group: null, mat: null, structs: [], towers: [], walls: [], mounts: { ballista: [], bombard: [], treb: [] }, wallSpots: [], firePots: [], rng: null,
  build(scene) {
    this.mat = stoneMaterial();
    this.group = new THREE.Group(); this.group.name = 'castle'; scene.add(this.group);
    this.rng = mulberry32(77);
    const B = C.y; // base height
    // ---- towers ----
    const corner = [[60, -54], [60, 54], [-64, 58], [-64, -52]];
    const gate = [[60, -10], [60, 10], [104, -10.5], [104, 10.5]];
    // inner gate towers and the corner towers carry a roofed stair turret on the courtyard side; the barbican towers fly the garrison's colours
    gate.forEach((p, i) => this._tower('gate', i, C.x + p[0], C.z + p[1], 6.6, i < 2 ? 25 : 21, B, i < 2 ? { talus: 1.2, turret: Math.atan2(Math.sign(p[1]) * 0.6, -1) } : { talus: 1.2, flag: [0x8f1d1d, 0xe2c46a, 4], flagA: Math.PI }));
    corner.forEach((p, i) => this._tower('corner', i, C.x + p[0], C.z + p[1], 7.6, 21, B, { talus: 2.4, turret: Math.atan2(-p[1], -p[0]), flag: i < 2 ? [0x2a1a10, 0xc79a1e, i ? 2 : 5] : null }));
    // ---- curtain walls (split into ~18 m destructible sections); the listed sections carry timber hoardings ----
    const WH = 12.5;
    const ring = [[60, -54], [60, -10], null, [60, 10], [60, 54], [-64, 58], [-64, -52], [60, -54]];
    const hoards = [[1], null, null, [0], [1, 4], [2], [1, 4]];
    for (let i = 0; i < ring.length - 1; i++) { const a = ring[i], b = ring[i + 1]; if (!a || !b) continue; this._wallRun(C.x + a[0], C.z + a[1], C.x + b[0], C.z + b[1], WH, 4.6, B, 7.6, hoards[i]); }
    // barbican passage walls
    this._wallRun(C.x + 60, C.z - 10, C.x + 104, C.z - 10.5, 10, 3.6, B, 6.6);
    this._wallRun(C.x + 104, C.z + 10.5, C.x + 60, C.z + 10, 10, 3.6, B, 6.6);
    // ---- gates ----
    this._gate(C.x + 60, C.z, 20, 14, B, 'inner');
    this._gate(C.x + 104, C.z, 21, 12, B, 'outer');
    // ---- keep ----
    this._keep(C.x - 30, C.z, B);
    // ---- courtyard: great hall, stables, chapel, smithy, well, stores, wall stairs; drawbridge at the barbican ----
    this._yard(B, WH);
    // ---- courtyard dressing: fire pots (lit in phase 3) ----
    for (const p of [[18, -26], [18, 26], [-2, -40], [-2, 40], [38, 0], [-50, -30], [-50, 32]]) this.firePots.push({ x: C.x + p[0], y: B, z: C.z + p[1], lit: false, emitter: null });
    // ---- mounts ----
    for (const t of this.towers) this.mounts.ballista.push({ x: t.x, y: t.topY, z: t.z, tower: t });
    const bomb = [[60, -32, 0], [60, 32, 0], [0, -53, -Math.PI / 2 * 1], [-2, 56, Math.PI / 2], [82, -10.3, -Math.PI / 2]];
    for (const b of bomb) { const wall = this._nearestWall(C.x + b[0], C.z + b[1]); this.mounts.bombard.push({ x: C.x + b[0], y: wall ? wall.topY : B + WH, z: C.z + b[1], yaw: b[2], wall }); }
    for (const t of TREBS) { const x = C.x + t[0], z = C.z + t[1]; this.mounts.treb.push({ x, y: terrain.height(x, z), z }); }
    // ---- the crag: outcrops, ledges, pinnacles and scree around and below the plateau ----
    this._crag(B);
    this.commitShadows();
  },
  _nearestWall(x, z) { let best = null, bd = 1e9; for (const w of this.walls) { const d = Math.hypot(w.x - x, w.z - z); if (d < bd) { bd = d; best = w; } } return best; },

  _register(s) { s.hp = s.maxHp; s.alive = true; this.structs.push(s); return s; },
  _mesh(g, visible = true) { const m = new THREE.Mesh(g.build(), this.mat); m.castShadow = m.receiveShadow = true; m.visible = visible; this.group.add(m); return m; },
  // flag pole from (x, y0, z) with a short yard, built into a structure's own geometry; _banner then hangs the cloth gonfalon on it, facing the field, parented to the structure's mesh so it goes down with it
  _pole(g, x, y0, z, len) { g.cyl(x, y0, z, 0.16, 0.1, len, 6, WOODD, true); g.box(x, y0 + len - 0.26, z, 0.12, 0.12, 1.9, 0, WOODD, 7); return [x + 0.08, y0 + len - 0.3, z]; },
  _banner(parent, at, spec) { const cl = scenery.makeBanner(1.5, 3.6, spec[0], spec[1], spec[2]); cl.position.set(at[0], at[1], at[2]); cl.rotation.y = Math.PI / 2; parent.add(cl); },

  // battered base of a drum tower with a dressed offset course on top
  _talus(g, x, z, r, B, seg, tal, col) { g.cyl(x, B - 6, z, r + tal + 0.3, r + 0.3, 10.5, seg, col, false); g.cyl(x, B + 4.5, z, r + 0.3, r, 0.5, seg, col === STONE ? DRESS : col, false); },

  _tower(kind, idx, x, z, r, h, B, opt = {}) {
    const rng = this.rng; const topY = B + h;
    const g = new GB(); const seg = 24; const ro = r + 1.25, ri = r + 0.6, tal = opt.talus || 1.4;
    this._talus(g, x, z, r, B, seg, tal, STONE);
    g.cyl(x, B + 4.5, z, r, r, h - 6.2, seg, STONE, false);                      // shaft up to the machicolation
    band(g, x, B + 10.2, z, r, 0.2, 0.5, seg, DRESS);
    // machicolated head: stepped corbels, lintel course, overhanging parapet
    const nc = Math.round(TAU * (r + 0.6) / 1.35);
    for (let i = 0; i < nc; i++) { const a = (i + 0.5) / nc * TAU, ry = -a + Math.PI / 2, ca = Math.cos(a), sa = Math.sin(a);
      g.box(x + ca * (r + 0.25), topY - 2.5, z + sa * (r + 0.25), 0.5, 0.55, 0.6, ry, MID, 7); g.box(x + ca * (r + 0.55), topY - 1.95, z + sa * (r + 0.55), 0.55, 0.55, 1.2, ry, MID, 7); }
    g.ring(x, topY - 1.7, z, r - 0.1, ro, seg, HOLE, true);
    g.cyl(x, topY - 1.7, z, ro, ro, 0.35, seg, DRESS, false);
    g.cyl(x, topY - 1.35, z, ro - 0.07, ro - 0.07, 2.35, seg, STONE, false);
    g.cyl(x, topY, z, ri, ri, 1.0, seg, MID, false, null, 0, TAU, true);
    g.ring(x, topY + 1.0, z, ri, ro - 0.07, seg, STONE);
    g.cyl(x, topY - 0.1, z, ri + 0.05, ri + 0.05, 0.1, seg, MID, true);          // fighting platform
    // stair turret (caphouse) with a slate cone, set on the courtyard side
    let col2 = null; const ta = opt.turret, tr = 1.9, tth = 5.6; const tx = x + Math.cos(ta || 0) * (r - 0.9), tz = z + Math.sin(ta || 0) * (r - 0.9);
    // merlons with copings; every other one pierced
    const rm = (ri + ro) / 2 - 0.035, nm = Math.round(TAU * rm / 2.5), mw = TAU * rm / nm * 0.6, mt = ro - 0.07 - ri;
    for (let i = 0; i < nm; i++) { const a = (i + 0.5) / nm * TAU, ry = -a + Math.PI / 2, ca = Math.cos(a), sa = Math.sin(a);
      if (ta !== undefined && Math.hypot(x + ca * rm - tx, z + sa * rm - tz) < tr + 0.7) continue;
      g.box(x + ca * rm, topY + 1.0 + 0.725, z + sa * rm, mw, 1.45, mt, ry, STONE, 5); g.box(x + ca * rm, topY + 2.52, z + sa * rm, mw + 0.16, 0.14, mt + 0.16, ry, DRESS, 7);
      if (i % 2) g.box(x + ca * (ro - 0.05), topY + 1.75, z + sa * (ro - 0.05), 0.14, 0.8, 0.04, ry, HOLE, 4); }
    // arrow loops in dressed surrounds, staggered round the drum
    for (let lv = 0; lv < 3; lv++) { const yy = B + 7.5 + lv * 5.4; if (yy > topY - 4.5) continue; for (let k = 0; k < 5; k++) { const a = (k + lv * 0.5) / 5 * TAU + 0.3; loop(g, frame(x + Math.cos(a) * r, z + Math.sin(a) * r, -a + Math.PI / 2), 0, yy, 2.0); } }
    if (ta !== undefined) {
      g.cyl(tx, topY - 4.4, tz, 0.5, tr, 2.6, 12, MID, false);                    // corbelled out of the drum below the parapet
      g.cyl(tx, topY - 1.8, tz, tr, tr, tth + 1.8, 12, STONE, false);
      band(g, tx, topY + tth - 0.9, tz, tr, 0.16, 0.4, 12, DRESS);
      g.ring(tx, topY + tth, tz, 0, tr + 0.5, 12, HOLE, true); g.cyl(tx, topY + tth, tz, tr + 0.5, 0, 4.8, 12, SLATE, false);
      g.cyl(tx, topY + tth + 4.5, tz, 0.09, 0.05, 1.5, 5, IRON, true);
      const da = ta + Math.PI; const Fd = frame(tx + Math.cos(da) * tr, tz + Math.sin(da) * tr, -da + Math.PI / 2); slab(g, Fd, -0.5, 0.5, topY, topY + 2.0, 0, 0.12, WOODC, 5); // door onto the platform
      for (const k of [-0.9, 0.9]) { const a = ta + k; loop(g, frame(tx + Math.cos(a) * tr, tz + Math.sin(a) * tr, -a + Math.PI / 2), 0, topY + 3.4, 1.2); }
      col2 = world.addCyl(tx, tz, tr + 0.3, topY + 2.4, topY + tth + 4.8, 'tower'); // the part of the turret that stands above the tower's own collider
    }
    const flagAt = !opt.flag ? null : ta !== undefined ? this._pole(g, tx, topY + tth + 4.3, tz, 7.5) : this._pole(g, x + Math.cos(opt.flagA) * (r - 0.6), topY, z + Math.sin(opt.flagA) * (r - 0.6), 8.5);
    const mesh = this._mesh(g); if (flagAt) this._banner(mesh, flagAt, opt.flag);
    // ruin: a broken ring of masonry with one standing shard, exposed floor beams, rubble spilled down the far side
    const rg = new GB(); const stump = h * rnd(0.28, 0.42); const ja = rng() * TAU; const jags = Array.from({ length: seg }, (_, i) => rng() * 3.2 - 1.3 + 3.6 * Math.max(0, Math.cos(i / seg * TAU - ja)) ** 3);
    const y1 = B + stump, ri2 = r - 1.4, jg = i => jags[i];
    this._talus(rg, x, z, r, B, seg, tal, RUB);
    rg.cyl(x, B + 4.5, z, r, r, stump - 4.5, seg, RUB, false, jg);
    rg.cyl(x, B + 1, z, ri2, ri2, stump - 1, seg, CORE, false, jg, 0, TAU, true);
    for (let i = 0; i < seg; i++) { const a = i / seg * TAU, b = (i + 1) / seg * TAU, ya = y1 + jags[i], yb = y1 + jags[(i + 1) % seg]; const P = (an, rr, yy) => [x + Math.cos(an) * rr, yy, z + Math.sin(an) * rr];
      rg.quad(P(a, ri2, ya), P(b, ri2, yb), P(b, r, yb), P(a, r, ya), [a * r, 0], [b * r, 0], [b * r, 1.4], [a * r, 1.4], DIM); }
    rg.cyl(x, B + 0.6, z, ri2, ri2, 0.4 + stump * 0.3, seg, CORE, true);
    { const by = B + stump * 0.72, Fb = frame(x, z, rng() * Math.PI);
      for (let k = -2; k <= 2; k++) { const lz = k * 1.25, hl = Math.sqrt(Math.max(0.5, ri2 * ri2 - lz * lz)) + 0.3; const broke = rng() < 0.55; const e1 = broke ? hl * (rng() * 0.7 - 0.2) : hl, drop = broke ? 1.2 + rng() * 2.2 : 0;
        rg.hexa([Fb(-hl, by - 0.2, lz + 0.18), Fb(e1, by - 0.2 - drop, lz + 0.18), Fb(e1, by - 0.2 - drop, lz - 0.18), Fb(-hl, by - 0.2, lz - 0.18)], [Fb(-hl, by + 0.2, lz + 0.18), Fb(e1, by + 0.2 - drop, lz + 0.18), Fb(e1, by + 0.2 - drop, lz - 0.18), Fb(-hl, by + 0.2, lz - 0.18)], WOODD, 7); } }
    for (let i = 0; i < 5; i++) { const a = ja + Math.PI + (i - 2) * 0.5; rg.rock(x + Math.cos(a) * (r + 1.2), B + 0.9, z + Math.sin(a) * (r + 1.2), 3.2 + rng() * 1.6, 1.8 + rng() * 1.6, 2.6 + rng(), rng, 1, RUB, -a + Math.PI / 2, 0, 0.3); }
    for (let i = 0; i < 18; i++) { const a = ja + Math.PI + (rng() - 0.5) * 3.4, d = r + 1 + rng() * 8; const s = 0.7 + rng() * 1.5; const px = x + Math.cos(a) * d, pz = z + Math.sin(a) * d, py = Math.max(terrain.height(px, pz), B - 8);
      if (i % 3) rg.rock(px, py + s * 0.25, pz, s * 1.3, s * 0.8, s, rng, 1, RUB, rng() * TAU, (rng() - 0.5) * 0.6, 0.2); else rg.box(px, py + s * 0.3, pz, s * 1.4, s * 0.7, s, rng() * 3, RUB, 5); }
    const ruin = this._mesh(rg, false);
    const col = world.addCyl(x, z, r + 0.9, B - 8, topY + 2.4, 'tower');
    const t = this._register({ type: 'tower', kind, idx, x, z, r, h, baseY: B, topY, y: topY, stump, mesh, ruin, col, col2, maxHp: 300, name: (kind === 'gate' ? 'Gate tower ' : 'Corner tower ') + (idx + 1) });
    col.ref = t; if (col2) col2.ref = t; this.towers.push(t); return t;
  },

  _wallRun(ax, az, bx, bz, h, th, B, inset, hoard) {
    const len = Math.hypot(bx - ax, bz - az); const dx = (bx - ax) / len, dz = (bz - az) / len;
    const a0 = inset - 1.2, a1 = len - inset + 1.2; const n = Math.max(1, Math.round((a1 - a0) / 18)); const sl = (a1 - a0) / n;
    for (let i = 0; i < n; i++) { const m = a0 + (i + 0.5) * sl; this._wall(ax + dx * m, az + dz * m, sl, Math.atan2(-dz, dx), h, th, B, a0 + i * sl, !!(hoard && hoard.includes(i))); }
  },
  // wall section centred (x,z), length along local x rotated by ry; the field side is local -z, the courtyard / passage side local +z
  _wall(x, z, len, ry, h, th, B, uo, hoard) {
    const rng = this.rng; const topY = B + h;
    const g = new GB(); const c = Math.cos(ry), s = Math.sin(ry); const off = (lx, lz) => [x + lx * c + lz * s, z - lx * s + lz * c];
    const F = frame(x, z, ry), Fo = faceOf(F, ry, 0, -th / 2, Math.PI), hl = len / 2, zi = th / 2; // Fo: on the outer face, +z pointing at the field
    slab(g, F, -hl, hl, B - 5, topY, -zi, zi, STONE, 5, uo);
    // battered plinth with a weathered offset
    g.hexa(rect(Fo, -hl, hl, B - 5, 0, 1.6), rect(Fo, -hl, hl, B + 2.6, 0, 0.32), STONE, 4, uo); g.hexa(rect(Fo, -hl, hl, B + 2.6, 0, 0.32), rect(Fo, -hl, hl, B + 3.0, 0, 0.02), DRESS, 4, uo);
    // stepped buttresses
    const nb = Math.max(1, Math.round(len / 8)); const bxs = [];
    for (let i = 0; i < nb; i++) { const lx = -hl + (i + 0.5) * len / nb, y0 = B + h * 0.45; bxs.push(lx);
      g.hexa(rect(Fo, lx - 0.85, lx + 0.85, B - 5, 0, 2.6), rect(Fo, lx - 0.85, lx + 0.85, y0, 0, 1.5), STONE, 4, lx);
      g.hexa(rect(Fo, lx - 0.85, lx + 0.85, y0, 0, 1.5), rect(Fo, lx - 0.85, lx + 0.85, y0 + 0.9, 0, 0.8), DRESS, 4);
      slab(g, Fo, lx - 0.85, lx + 0.85, y0 + 0.9, topY - 2.7, 0, 0.8, STONE, 4, lx);
      g.hexa(rect(Fo, lx - 0.85, lx + 0.85, topY - 2.7, 0, 0.8), rect(Fo, lx - 0.85, lx + 0.85, topY - 1.5, 0, 0), DRESS, 4); }
    // arrow loops between the buttresses, putlog holes left by the builders' scaffolding
    for (let i = 1; i < nb; i++) loop(g, Fo, -hl + i * len / nb, B + h * 0.56, 2.0);
    for (const yy of [B + 5.4, B + 9.3]) for (let lx = -hl + 1.3; lx < hl - 0.5; lx += 2.6) { if (bxs.some(b => Math.abs(b - lx) < 1.15)) continue; slab(g, Fo, lx - 0.13, lx + 0.13, yy - 0.13, yy + 0.13, 0, 0.03, HOLE, 4); }
    slab(g, Fo, -hl, hl, topY - 1.3, topY - 1.0, 0, 0.16, DRESS, 7, uo);
    // wall-walk: parapet on a corbel table toward the field, a low kerb toward the yard
    const h0 = -hl * 0.72, h1 = hl * 0.72; // extent of the hoarding, where there is one
    for (let lx = -hl + 0.65; lx < hl; lx += 1.3) if (!hoard || lx < h0 || lx > h1) slab(g, Fo, lx - 0.2, lx + 0.2, topY - 0.85, topY - 0.4, 0, 0.45, MID, 6);
    slab(g, Fo, -hl, hl, topY - 0.4, topY + 1.0, -0.25, 0.45, STONE, 7, uo);
    parapet(g, Fo, -hl, hl, topY + 1.0, -0.25, 0.45, uo, hoard ? lx => lx > h0 - 0.6 && lx < h1 + 0.6 : null);
    slab(g, F, -hl, hl, topY, topY + 0.4, zi - 0.35, zi, MID, 5, uo);
    if (hoard) { // timber hoarding: a roofed fighting gallery jettied out over the wall foot
      for (let lx = h0 + 0.3; lx < h1; lx += 1.3) slab(g, Fo, lx - 0.11, lx + 0.11, topY - 0.45, topY - 0.2, -0.2, 2.05, WOODD, 7);
      for (let lx = h0 + 0.3; lx < h1; lx += 2.6) { beam(g, Fo, [lx, topY - 2.5, 0.12], [lx, topY - 0.45, 1.7], 0.2, 0.24, WOODD); slab(g, Fo, lx - 0.1, lx + 0.1, topY, topY + 2.9, -0.62, -0.42, WOODD, 4);
        slab(g, Fo, lx + 1.0, lx + 1.6, topY + 0.95, topY + 1.25, 2.0, 2.03, HOLE, 4); }
      slab(g, Fo, h0, h1, topY - 0.2, topY - 0.08, 0.45, 2.05, WOODD, 7);
      slab(g, Fo, h0, h1, topY - 0.08, topY + 1.8, 1.85, 2.0, WOODC, 5, uo);
      for (const e of [h0, h1 - 0.15]) slab(g, Fo, e, e + 0.15, topY - 0.08, topY + 2.3, 0.45, 2.0, WOODC, 5);
      g.hexa([Fo(h0 - 0.3, topY + 1.72, 2.35), Fo(h1 + 0.3, topY + 1.72, 2.35), Fo(h1 + 0.3, topY + 3.0, -0.75), Fo(h0 - 0.3, topY + 3.0, -0.75)], [Fo(h0 - 0.3, topY + 1.86, 2.35), Fo(h1 + 0.3, topY + 1.86, 2.35), Fo(h1 + 0.3, topY + 3.14, -0.75), Fo(h0 - 0.3, topY + 3.14, -0.75)], WOODD, 7);
    }
    const mesh = this._mesh(g);
    // ruin: ragged stubs standing highest at the ends, the plinth, and the fallen masonry heaped on both sides
    const rg = new GB(); const k = Math.max(4, Math.round(len / 2.4)), pw = len / k;
    for (let i = 0; i < k; i++) { const lx = -hl + (i + 0.5) * pw, e = Math.abs((i + 0.5) / k * 2 - 1); const hh = 1.2 + rng() * h * 0.2 + h * 0.62 * e * e * e * (0.55 + 0.45 * rng()); const t0 = zi * (0.82 + rng() * 0.18), t1 = zi * (0.82 + rng() * 0.18);
      slab(rg, F, lx - pw / 2, lx + pw / 2 + 0.03, B - 5, B + hh, -t0, t1, i % 2 ? RUB : DIM, 5, uo + lx); }
    rg.hexa(rect(Fo, -hl, hl, B - 5, 0, 1.6), rect(Fo, -hl, hl, B + 1.4, 0, 0.9), RUB, 5, uo);
    for (let i = 0; i < 6; i++) { const [px, pz] = off((rng() - 0.5) * len * 0.8, (i % 2 ? 1 : -1) * (zi + 0.6 + rng() * 1.4)); rg.rock(px, B + 0.5, pz, 2.6 + rng() * 2.2, 1.2 + rng() * 1.5, 1.8 + rng() * 1.4, rng, 1, RUB, ry + (rng() - 0.5) * 0.6, 0, 0.3); }
    for (let i = 0; i < 12; i++) { const [px, pz] = off((rng() - 0.5) * len, (rng() - 0.5) * 15); const sz = 0.7 + rng() * 1.5, py = terrain.height(px, pz);
      if (i % 3) rg.rock(px, py + sz * 0.25, pz, sz * 1.3, sz * 0.8, sz, rng, 1, RUB, rng() * TAU, (rng() - 0.5) * 0.6, 0.2); else rg.box(px, py + sz * 0.3, pz, sz * 1.4, sz * 0.7, sz, rng() * 3, RUB, 5); }
    const ruin = this._mesh(rg, false);
    const col = world.addBox(x, z, len / 2, th / 2 + 0.5, ry, B - 8, topY + 2.6, 'wall');
    const w = this._register({ type: 'wall', x, z, len, ry, h, th, baseY: B, topY, y: topY, mesh, ruin, col, maxHp: 220, name: 'Wall section' });
    col.ref = w; this.walls.push(w);
    // standing spots for archers along the walkway
    for (let i = 0; i < Math.floor(len / 2.2); i++) { const lx = -len / 2 + (i + 0.5) * 2.2; const [px, pz] = off(lx, 0.6); this.wallSpots.push({ x: px, y: topY + 0.02, z: pz, yaw: ry, wall: w, ox: s, oz: c }); }
    return w;
  },

  _gate(x, z, towerSpan, h, B, which) {
    // gatehouse block between the two flanking towers; the passage runs along x, the field side is +x
    const g = new GB(); const topY = B + h; const half = 3.6, Lh = (towerSpan - 8) / 2, sp = B + 4.7, rise = 3.0;
    const F = frame(x, z, Math.PI / 2), Fx = frame(x + 2.5, z, Math.PI / 2), Fi = frame(x - 2.5, z, -Math.PI / 2); // F: local x along the gate, +z toward the field; Fx / Fi: outer and inner faces
    for (const sg of [-1, 1]) { slab(g, F, sg * half, sg * Lh, B - 4, topY, -2.5, 2.5, STONE, 5); slab(g, F, sg * (half - 0.6), sg * half, B - 4, B + 3.3, -2.5, 2.5, MID, 5); // piers and the jamb plinths in the passage
      for (const Ff of [Fx, Fi]) slab(g, Ff, sg * half, sg * (half + 0.55), B, sp, 0, 0.12, DRESS, 5); }
    // round arch: the wall above it in slices, a ring of voussoirs on both faces
    const ay = t => sp + rise * Math.sqrt(Math.max(0, 1 - t * t)); const N = 12;
    for (let j = 0; j < N; j++) { const l0 = -half + j * 2 * half / N, l1 = l0 + 2 * half / N, y0 = ay(l0 / half), y1 = ay(l1 / half);
      g.hexa([F(l0, y0, 2.5), F(l1, y1, 2.5), F(l1, y1, -2.5), F(l0, y0, -2.5)], rect(F, l0, l1, topY, -2.5, 2.5), STONE, 3);
      g.quad(F(l0, y0, 2.5), F(l1, y1, 2.5), F(l1, topY, 2.5), F(l0, topY, 2.5), [l0, y0], [l1, y1], [l1, topY], [l0, topY], STONE);
      g.quad(F(l1, y1, -2.5), F(l0, y0, -2.5), F(l0, topY, -2.5), F(l1, topY, -2.5), [-l1, y1], [-l0, y0], [-l0, topY], [-l1, topY], STONE);
      for (const Ff of [Fx, Fi]) { const m0 = Ff === Fx ? l0 : -l1, m1 = Ff === Fx ? l1 : -l0, ya = Ff === Fx ? y0 : y1, yb = Ff === Fx ? y1 : y0;
        g.hexa([Ff(m0, ya, 0.12), Ff(m1, yb, 0.12), Ff(m1, yb, 0), Ff(m0, ya, 0)], [Ff(m0, ya + 0.62, 0.12), Ff(m1, yb + 0.62, 0.12), Ff(m1, yb + 0.62, 0), Ff(m0, ya + 0.62, 0)], DRESS, 7); } }
    // chamber over the passage: loops and a carved panel, then a machicolated parapet over the gate and a plain one toward the yard
    for (const lx of [-2.3, 2.3]) loop(g, Fx, lx, sp + rise + 1.9, 1.5);
    slab(g, Fx, -0.8, 0.8, sp + rise + 1.0, sp + rise + 2.9, 0, 0.1, DRESS, 5); slab(g, Fx, -0.5, 0.5, sp + rise + 1.3, sp + rise + 2.6, 0.1, 0.14, MID, 5);
    for (let lx = -Lh + 0.5; lx < Lh; lx += 1.2) slab(g, Fx, lx - 0.2, lx + 0.2, topY - 1.9, topY - 1.3, 0, 0.75, MID, 6);
    slab(g, Fx, -Lh, Lh, topY - 1.3, topY + 1.0, 0.1, 0.75, STONE, 7); parapet(g, Fx, -Lh, Lh, topY + 1.0, 0.1, 0.75);
    slab(g, Fi, -Lh, Lh, topY, topY + 1.0, -0.6, 0, STONE, 5); parapet(g, Fi, -Lh, Lh, topY + 1.0, -0.6, 0);
    slab(g, Fi, -Lh, Lh, topY - 1.3, topY - 1.0, 0, 0.14, DRESS, 7); for (const lx of [-2.2, 2.2]) win(g, Fi, lx, sp + rise + 2.0, 0.7, 1.3, true);
    const mesh = this._mesh(g);
    // doors (planks with iron straps, drawbar on the yard side) behind a portcullis grille, separate so they can be blown
    const dg = new GB(); slab(dg, F, -half, half, B, B + 7.6, 0.95, 1.45, WOODC, 5);
    for (const yy of [1.2, 3.6, 6.0]) slab(dg, F, -half, half, B + yy, B + yy + 0.28, 1.45, 1.5, IRON, 4);
    slab(dg, F, -0.06, 0.06, B, B + 7.6, 1.45, 1.49, IRON, 4); slab(dg, F, -half - 0.3, half + 0.3, B + 2.7, B + 3.1, 0.6, 0.95, WOODD, 7);
    for (let i = 0; i < 9; i++) { const lx = -half + (i + 0.5) * half * 2 / 9; slab(dg, F, lx - 0.075, lx + 0.075, B, B + 7.6, 1.62, 1.77, IRON, 4); }
    for (let i = 0; i < 6; i++) slab(dg, F, -half, half, B + 0.55 + i * 1.25, B + 0.69 + i * 1.25, 1.6, 1.79, IRON, 6);
    const door = this._mesh(dg);
    // ruin: the stumps of the piers, splintered door leaves, the fallen arch
    const rg = new GB(); const rng = this.rng;
    for (const sg of [-1, 1]) { const hh = 5 + rnd(4); slab(rg, F, sg * half, sg * Lh, B - 4, B + hh, -2.5, 2.5, RUB, 5); slab(rg, F, sg * (half + 0.9), sg * Lh, B + hh, B + hh + 1.5 + rng() * 2.5, -2.5 + rng(), 2.2, DIM, 5); slab(rg, F, sg * (half - 0.6), sg * half, B - 4, B + 2.2, -2.5, 2.5, RUB, 5); }
    for (let i = 0; i < 4; i++) { const a = [(rng() - 0.5) * 5, B + 0.25, (rng() - 0.5) * 7]; beam(rg, F, a, [a[0] + (rng() - 0.5) * 3, B + 0.3 + rng() * 1.6, a[2] + 2 + rng() * 2], 0.9, 0.18, WOODC); }
    for (let i = 0; i < 5; i++) rg.rock(x + (rng() - 0.5) * 9, B + 0.5, z + (rng() - 0.5) * 6, 2.2 + rng() * 1.8, 1.0 + rng() * 1.2, 1.6 + rng() * 1.2, rng, 1, RUB, rng() * TAU, 0, 0.3);
    for (let i = 0; i < 10; i++) { const sz = 0.7 + rng() * 1.4, px = x + (rng() - 0.5) * 13, pz = z + (rng() - 0.5) * 9; if (i % 3) rg.rock(px, B + sz * 0.25, pz, sz * 1.3, sz * 0.8, sz, rng, 1, RUB, rng() * TAU, (rng() - 0.5) * 0.6, 0.2); else rg.box(px, B + sz * 0.3, pz, sz * 1.4, sz * 0.7, sz, rng() * 3, RUB, 5); }
    const ruin = this._mesh(rg, false);
    const col = world.addBox(x, z, 2.6, (towerSpan - 8) / 2, 0, B - 6, topY + 1.5, 'wall');
    const s = this._register({ type: 'gate', which, x, z, len: towerSpan - 8, ry: Math.PI / 2, h, th: 5, baseY: B, topY, y: topY, mesh, ruin, col, door, maxHp: 260, name: which === 'inner' ? 'Main gate' : 'Barbican gate' });
    col.ref = s; this.walls.push(s); this[which + 'Gate'] = s;
  },

  _keep(x, z, B) {
    const g = new GB(); const S = 25, H = 34; const topY = B + H, hs = S / 2; const F0 = frame(x, z, 0);
    g.box(x, B - 5 + (H + 5) / 2, z, S, H + 5, S, 0, STONE, 5);
    g.hexa(rect(F0, -hs - 2.8, hs + 2.8, B - 5, -hs - 2.8, hs + 2.8), rect(F0, -hs, hs, B + 7, -hs, hs), STONE, 4);   // battered plinth
    g.box(x, B + 7.2, z, S + 0.5, 0.45, S + 0.5, 0, DRESS, 7);
    for (const yy of [B + 16, B + 25]) g.box(x, yy, z, S + 0.36, 0.4, S + 0.36, 0, DRESS, 7);                          // string courses at the floors
    g.box(x, topY - 0.2, z, S + 1.6, 0.3, S + 1.6, 0, MID, 1);                                                       // roof walk
    for (let f = 0; f < 4; f++) { const a = f * Math.PI / 2, nx = Math.cos(a), nz = Math.sin(a); const Ff = frame(x + nx * hs, z + nz * hs, -a + Math.PI / 2);
      for (const lx of [-5.4, 5.4]) { slab(g, Ff, lx - 1.1, lx + 1.1, B + 7.4, topY - 2.6, 0, 0.6, STONE, 4, lx); g.hexa(rect(Ff, lx - 1.1, lx + 1.1, topY - 2.6, 0, 0.6), rect(Ff, lx - 1.1, lx + 1.1, topY - 2.0, 0, 0), DRESS, 4); } // pilaster buttresses
      // three storeys: loops below, paired lancets, the great chamber's tall windows on top
      for (const lx of [-2.6, 2.6]) loop(g, Ff, lx, B + 11.6, 2.0);
      for (const lx of [-1.1, 1.1]) win(g, Ff, lx, B + 20.2, 0.8, 2.2, true);
      win(g, Ff, 0, B + 29, 1.4, 3.0, true); for (const lx of [-2.7, 2.7]) win(g, Ff, lx, B + 28.6, 0.8, 2.2, true);
      for (const lx of [-7.6, 7.6]) for (const yy of [B + 12.5, B + 20.6, B + 29]) loop(g, Ff, lx, yy, 1.6);
      // machicolated parapet between the turrets
      for (let lx = -8.1; lx < 8.2; lx += 1.25) { slab(g, Ff, lx - 0.22, lx + 0.22, topY - 2.1, topY - 1.5, 0, 0.6, MID, 6); slab(g, Ff, lx - 0.22, lx + 0.22, topY - 1.5, topY - 0.95, 0, 1.15, MID, 6); }
      slab(g, Ff, -hs, hs, topY - 0.97, topY - 0.95, 0, 0.62, HOLE, 2);
      slab(g, Ff, -hs - 1.2, hs + 1.2, topY - 0.95, topY + 1.1, 0.6, 1.2, STONE, 7); parapet(g, Ff, -8.6, 8.6, topY + 1.1, 0.6, 1.2);
      // garderobes corbelled out high on the north and west faces
      if (f >= 2) { const lx = f === 2 ? -3.3 : 5.2, yy = B + (f === 2 ? 23.2 : 14.2);
        for (const k of [-0.7, 0.7]) g.hexa(rect(Ff, lx + k - 0.2, lx + k + 0.2, yy - 1.3, 0, 0.1), rect(Ff, lx + k - 0.2, lx + k + 0.2, yy, 0, 1.2), MID, 6);
        slab(g, Ff, lx - 1.1, lx + 1.1, yy, yy + 2.9, 0, 1.3, STONE, 7); g.hexa(rect(Ff, lx - 1.25, lx + 1.25, yy + 2.9, 0, 1.45), rect(Ff, lx - 1.25, lx + 1.25, yy + 3.9, 0, 0), SLATE, 4); slab(g, Ff, lx - 0.08, lx + 0.08, yy + 1.2, yy + 2.0, 1.3, 1.32, HOLE, 4); }
    }
    // corner turrets: battered feet, string courses, corbelled heads with lit lookout windows under slate cones; the south-east one stands a storey taller and flies the warlord's banner
    [[1, 1], [1, -1], [-1, 1], [-1, -1]].forEach(([sx, sz], q) => {
      const tx = x + sx * hs, tz = z + sz * hs; const tr = 3.9, th = H + 7 + (q === 0 ? 7 : 0), yh = B + th;
      g.cyl(tx, B - 5, tz, tr + 1.7, tr, 12, 16, STONE, false); g.cyl(tx, B + 7, tz, tr, tr, th - 8.2, 16, STONE, false);
      for (const yy of [B + 16, B + 25, B + 33.2]) band(g, tx, yy - 0.2, tz, tr, 0.18, 0.4, 16, DRESS);
      g.cyl(tx, yh - 1.2, tz, tr, tr + 0.7, 1.2, 16, MID, false); g.cyl(tx, yh, tz, tr + 0.7, tr + 0.7, 1.6, 16, STONE, false);
      for (let k = 0; k < 6; k++) { const a = Math.atan2(sz, sx) + (k - 2.5) * 0.62; win(g, frame(tx + Math.cos(a) * (tr + 0.7), tz + Math.sin(a) * (tr + 0.7), -a + Math.PI / 2), 0, yh + 0.75, 0.5, 0.8); }
      g.ring(tx, yh + 1.6, tz, 0, tr + 1.35, 16, HOLE, true); g.cyl(tx, yh + 1.6, tz, tr + 1.35, 0, 9.5, 16, SLATE, false); g.cyl(tx, yh + 10.6, tz, 0.12, 0.05, 1.8, 5, IRON, true);
      for (let lv = 0; lv < 4; lv++) { const a = Math.atan2(sz, sx) + (lv % 2 ? 0.6 : -0.6); loop(g, frame(tx + Math.cos(a) * tr, tz + Math.sin(a) * tr, -a + Math.PI / 2), 0, B + 10.5 + lv * 7.4, 1.6); }
      if (q === 0) { world.addCyl(tx, tz, 4.6, B + H + 17, yh + 11.2, 'keep'); this.flagAt = this._pole(g, tx, yh + 10.5, tz, 7); }
    });
    // hipped slate roof over the great chamber, chimney stacks
    g.box(x, topY + 1.5, z, S - 9, 3.2, S - 13, 0, STONE, 4);
    g.hexa(rect(F0, -8.8, 8.8, topY + 2.9, -6.8, 6.8), rect(F0, -3.4, 3.4, topY + 9.2, 0, 0), SLATE, 4);
    for (const lx of [-4.5, 0, 4.5]) for (const sg of [-1, 1]) win(g, frame(x, z + sg * (S - 13) / 2, sg > 0 ? 0 : Math.PI), lx, topY + 1.7, 0.7, 1.3);
    for (const [cx, cz] of [[-5.6, 2.2], [5.2, -2.4]]) { slab(g, F0, cx - 0.55, cx + 0.55, topY + 4, topY + 10.1, cz - 0.55, cz + 0.55, MID, 5); slab(g, F0, cx - 0.7, cx + 0.7, topY + 10.1, topY + 10.4, cz - 0.7, cz + 0.7, DRESS, 7); slab(g, F0, cx - 0.3, cx + 0.3, topY + 10.4, topY + 10.42, cz - 0.3, cz + 0.3, HOLE, 1); }
    // forebuilding on the courtyard face: the stair to the first-floor door under a lean-to roof
    { const Fe = frame(x + hs, z, Math.PI / 2), Fd = frame(x + hs + 7, z, Math.PI / 2);
      slab(g, Fe, -4.5, 4.5, B - 1, B + 9.5, 0, 7, STONE, 4); slab(g, Fe, -4.75, 4.75, B - 1, B + 1.1, 0, 7.25, MID, 5);
      g.hexa(rect(Fe, -4.5, 4.5, B + 9.5, 0, 7), [Fe(-4.5, B + 9.5, 7), Fe(4.5, B + 9.5, 7), Fe(4.5, B + 13.2, 0), Fe(-4.5, B + 13.2, 0)], STONE, 4);
      g.hexa([Fe(-4.95, B + 9.25, 7.55), Fe(4.95, B + 9.25, 7.55), Fe(4.95, B + 13.25, 0), Fe(-4.95, B + 13.25, 0)], [Fe(-4.95, B + 9.5, 7.55), Fe(4.95, B + 9.5, 7.55), Fe(4.95, B + 13.5, 0), Fe(-4.95, B + 13.5, 0)], SLATE, 7);
      slab(g, Fd, -1.5, 1.5, B, B + 4.6, 0, 0.14, DRESS, 5); slab(g, Fd, -1.1, 1.1, B + 0.9, B + 4.2, 0.14, 0.2, WOODC, 5);
      for (let k = 0; k < 3; k++) slab(g, Fd, -2.1, 2.1, B, B + 0.9 - k * 0.3, 0.14, 0.9 + k * 0.55, MID, 5);
      for (const lx of [-2.9, 2.9]) win(g, Fd, lx, B + 6.6, 0.6, 1.5, true);
      for (const sg of [-1, 1]) win(g, frame(x + hs + 3.5, z - sg * 4.5, sg > 0 ? Math.PI : 0), 0, B + 6.6, 0.6, 1.5, true);
      world.addBox(x + hs + 3.5, z, 3.7, 4.7, 0, B - 2, B + 13, 'keep'); }
    const mesh = this._mesh(g);
    this._banner(mesh, this.flagAt, [0x8f1d1d, 0xe2c46a, 4]);
    this.keep = { x, z, S, H, topY, baseY: B, mesh };
    world.addBox(x, z, S / 2 + 1.2, S / 2 + 1.2, 0, B - 6, topY + 3, 'keep');
    world.addBox(x, z, (S - 9) / 2 + 1, (S - 13) / 2 + 1, 0, topY, topY + 9, 'keep');
    for (const [sx, sz] of [[1, 1], [1, -1], [-1, 1], [-1, -1]]) world.addCyl(x + sx * S / 2, z + sz * S / 2, 4.6, B, B + H + 17, 'keep');
  },

  // courtyard buildings and dressing (one merged mesh); the footprints and colliders of the four ranges are the ones the game has always had
  _yard(B, WH) {
    const g = new GB(); const rng = mulberry32(911);
    // a range: stone walls on a plinth course, coped gables, slate roof with a dressed ridge
    const bld = (hx, hz, sx, sz, hh, pitch) => { const F = frame(hx, hz, 0), rise = sz * pitch;
      g.box(hx, B - 1 + (hh + 1) / 2, hz, sx, hh + 1, sz, 0, STONE, 4); g.box(hx, B + 0.4, hz, sx + 0.5, 0.9, sz + 0.5, 0, MID, 5);
      for (const sg of [-1, 1]) { const x0 = sg * (sx / 2 - 0.5), x1 = sg * sx / 2, xa = Math.min(x0, x1), xb = Math.max(x0, x1); g.hexa(rect(F, xa, xb, B + hh, -sz / 2, sz / 2), [F(xa, B + hh + rise + 0.45, 0), F(xb, B + hh + rise + 0.45, 0), F(xb, B + hh + rise + 0.45, 0), F(xa, B + hh + rise + 0.45, 0)], STONE, 4); }
      roof(g, F, sx / 2 - 0.45, sz / 2, B + hh, rise, 0.7, SLATE); slab(g, F, -sx / 2 + 0.5, sx / 2 - 0.5, B + hh + rise - 0.12, B + hh + rise + 0.2, -0.16, 0.16, DRESS, 5);
      world.addBox(hx, hz, sx / 2 + 0.5, sz / 2 + 0.5, 0, B - 2, B + hh + sz * 0.42, 'house'); terrain.stampOccluder(hx, hz, Math.min(sx, sz) / 2, B + hh + 2);
      return { F, rise, S: frame(hx, hz + sz / 2, 0), N: frame(hx, hz - sz / 2, Math.PI), E: frame(hx + sx / 2, hz, Math.PI / 2), W: frame(hx - sx / 2, hz, -Math.PI / 2) }; };
    const butt = (Ff, lx, y0, y1, d = 1.0) => { slab(g, Ff, lx - 0.45, lx + 0.45, y0, y1, 0, d, STONE, 4, lx); g.hexa(rect(Ff, lx - 0.45, lx + 0.45, y1, 0, d), rect(Ff, lx - 0.45, lx + 0.45, y1 + 1.3, 0, 0), DRESS, 4); };
    const door = (Ff, lx, w, h) => { slab(g, Ff, lx - w / 2 - 0.25, lx + w / 2 + 0.25, B, B + h + 0.3, 0, 0.12, DRESS, 5); slab(g, Ff, lx - w / 2, lx + w / 2, B, B + h, 0.12, 0.17, WOODC, 5); };
    const barrel = (px, pz, s = 1) => { g.cyl(px, B, pz, 0.36 * s, 0.4 * s, 0.5 * s, 8, WOODC, false); g.cyl(px, B + 0.5 * s, pz, 0.4 * s, 0.36 * s, 0.5 * s, 8, WOODC, true); g.cyl(px, B + 0.22 * s, pz, 0.4 * s, 0.415 * s, 0.07, 8, IRON, false); g.cyl(px, B + 0.72 * s, pz, 0.415 * s, 0.4 * s, 0.07, 8, IRON, false); };
    const stores = (cx, cz, n, spread) => { for (let i = 0; i < n; i++) { const px = cx + (rng() - 0.5) * spread, pz = cz + (rng() - 0.5) * spread; if (rng() < 0.55) { barrel(px, pz, 0.9 + rng() * 0.3); }
      else { const s = 0.7 + rng() * 0.5, ry = rng() * 3; g.box(px, B + s / 2, pz, s * 1.2, s, s, ry, rng() < 0.5 ? WOODC : WOODD, 5); if (rng() < 0.4) g.box(px + 0.1, B + s + s * 0.35, pz, s * 0.8, s * 0.7, s * 0.8, ry + 0.5, WOODD, 5); } } };
    const leanTo = (Ff, x0, x1, depth, yBack, yFront) => { // open timber shed against a wall: posts, plate, plank roof
      for (let lx = x0 + 0.2; lx <= x1 + 0.01; lx += (x1 - x0 - 0.4) / Math.max(1, Math.round((x1 - x0) / 3.6))) slab(g, Ff, lx - 0.12, lx + 0.12, B, yFront - 0.1, depth - 0.42, depth - 0.18, WOODD, 4);
      slab(g, Ff, x0, x1, yFront - 0.32, yFront - 0.1, depth - 0.45, depth - 0.15, WOODD, 7);
      g.hexa([Ff(x0 - 0.3, yFront - 0.12, depth + 0.4), Ff(x1 + 0.3, yFront - 0.12, depth + 0.4), Ff(x1 + 0.3, yBack, 0), Ff(x0 - 0.3, yBack, 0)], [Ff(x0 - 0.3, yFront + 0.02, depth + 0.4), Ff(x1 + 0.3, yFront + 0.02, depth + 0.4), Ff(x1 + 0.3, yBack + 0.14, 0), Ff(x0 - 0.3, yBack + 0.14, 0)], WOODD, 7); };

    // great hall along the north wall: buttressed bays of tall lancets, a louvre on the ridge, the door near its east end
    { const h = bld(C.x + 8, C.z - 40, 34, 11, 8, 0.55);
      for (let i = 0; i <= 7; i++) butt(h.S, -16.4 + i * 32.8 / 7, B, B + 5.6);
      for (let i = 0; i < 7; i++) { const lx = -16.4 + (i + 0.5) * 32.8 / 7; if (i === 1) { door(h.S, lx, 2.0, 3.3); win(g, h.S, lx, B + 6.1, 0.9, 0.9, true); } else win(g, h.S, lx, B + 4.3, 1.0, 3.4, true); }
      win(g, h.W, 0, B + 6.4, 1.6, 4.0, true); win(g, h.E, 0, B + 6.4, 1.6, 4.0, true);
      const lv = h.F(-5, 0, 0); g.cyl(lv[0], B + 8 + h.rise - 0.7, lv[2], 1.0, 1.0, 2.0, 8, WOODD, false); g.cyl(lv[0], B + 8 + h.rise + 1.3, lv[2], 1.5, 0, 2.2, 8, SLATE, false); g.cyl(lv[0], B + 8 + h.rise + 3.3, lv[2], 0.07, 0.04, 0.9, 5, IRON, true);
      slab(g, h.F, 11.2, 12.6, B + 8, B + 8 + h.rise + 2.0, -5.5, -4.1, MID, 5); slab(g, h.F, 11.05, 12.75, B + 8 + h.rise + 2.0, B + 8 + h.rise + 2.3, -5.65, -3.95, DRESS, 7);
      g.box(C.x + 8, B + 0.04, C.z - 32.6, 34, 0.12, 3.4, 0, MID, 1); }
    // stables and barracks along the south wall: stable doors under a timber pentice
    { const h = bld(C.x + 22, C.z + 42, 26, 9, 6, 0.5);
      for (let i = 0; i < 5; i++) { const lx = -10.4 + i * 5.2; door(h.N, lx, 1.9, 2.5); win(g, h.N, lx + 2.6, B + 4.6, 0.7, 0.9); }
      leanTo(h.N, -13, 13, 3.3, B + 5.1, B + 3.1); win(g, h.W, 0, B + 5.2, 0.9, 1.6, true); win(g, h.E, 0, B + 5.2, 0.9, 1.6, true);
      slab(g, h.N, -6.5, -3.5, B, B + 0.7, 1.6, 2.3, WOODD, 5); g.box(C.x + 22, B + 0.04, C.z + 35.3, 27, 0.12, 4.6, 0, MID, 1);
      stores(C.x + 37.5, C.z + 39, 9, 4); }
    // chapel by the south-west tower: lancets, corner buttresses, a bellcote and cross on the east gable
    { const h = bld(C.x - 52, C.z + 36, 12, 16, 6, 0.5);
      win(g, h.E, 0, B + 6.2, 1.0, 4.2, true); for (const lx of [-2.3, 2.3]) win(g, h.E, lx, B + 5.2, 0.8, 3.0, true);
      for (const lx of [-3.6, 0, 3.6]) win(g, h.N, lx, B + 3.6, 0.8, 2.6, true);
      for (const Ff of [h.E, h.W]) for (const lx of [-7.4, 7.4]) butt(Ff, lx, B, B + 4.6, 0.9); for (const lx of [-5.4, 5.4]) butt(h.N, lx, B, B + 4.6, 0.9);
      door(h.N, -1.8, 1.5, 2.6);
      const ya = B + 6 + h.rise + 0.4; slab(g, h.F, 5.5, 6.05, ya - 0.6, ya + 2.2, -0.9, 0.9, STONE, 5); slab(g, h.E, -0.35, 0.35, ya + 0.5, ya + 1.6, 0.05, 0.08, HOLE, 4);
      g.hexa(rect(h.F, 5.4, 6.15, ya + 2.2, -1.05, 1.05), [h.F(5.4, ya + 3.1, 0), h.F(6.15, ya + 3.1, 0), h.F(6.15, ya + 3.1, 0), h.F(5.4, ya + 3.1, 0)], DRESS, 4);
      slab(g, h.F, 5.68, 5.86, ya + 3.0, ya + 4.5, -0.09, 0.09, DRESS, 5); slab(g, h.F, 5.68, 5.86, ya + 3.85, ya + 4.03, -0.5, 0.5, DRESS, 7); }
    // smithy by the north-east tower: open forge front, hearth with glowing coals in the yard, a tall stack
    { const h = bld(C.x + 46, C.z - 30, 9, 13, 5.5, 0.45);
      slab(g, h.W, -2.6, 2.6, B, B + 3.6, 0, 0.1, DRESS, 5); slab(g, h.W, -2.3, 2.3, B + 0.1, B + 3.2, 0.1, 0.14, DARK, 5); slab(g, h.W, -2.9, 2.9, B + 3.3, B + 3.7, 0.05, 0.35, WOODD, 7);
      win(g, h.W, 0, B + 6.2, 0.8, 1.4, true); win(g, h.S, 0, B + 3.2, 0.8, 1.4); door(h.S, 2.6, 1.3, 2.4);
      slab(g, h.F, 1.2, 2.7, B + 5.5, B + 5.5 + h.rise + 2.6, 3.4, 4.9, MID, 5); slab(g, h.F, 1.05, 2.85, B + 5.5 + h.rise + 2.6, B + 5.5 + h.rise + 2.9, 3.25, 5.05, DRESS, 7); slab(g, h.F, 1.5, 2.4, B + 5.5 + h.rise + 2.9, B + 5.5 + h.rise + 2.92, 3.7, 4.6, HOLE, 1);
      leanTo(h.W, -4.5, -0.6, 3.0, B + 4.4, B + 3.0);
      slab(g, h.W, 0.4, 2.6, B, B + 1.0, 1.6, 3.6, MID, 5); slab(g, h.W, 0.75, 2.25, B + 1.0, B + 1.05, 1.95, 3.25, DARK, 1);   // raised hearth: the coals glow at dusk
      slab(g, h.W, -1.3, -0.7, B, B + 0.55, 2.0, 2.4, DIM, 5); slab(g, h.W, -1.45, -0.55, B + 0.55, B + 0.8, 1.95, 2.45, IRON, 7); barrel(C.x + 38.4, C.z - 26.6, 1.1);
      g.box(C.x + 39.3, B + 0.04, C.z - 30, 4.4, 0.12, 12, 0, MID, 1); stores(C.x + 39.5, C.z - 37.5, 7, 3.4); }
    // well with a little shingled roof, south-east of the gate
    { const wx = C.x + 42, wz = C.z + 23, Fw = frame(wx, wz, 0.5);
      g.cyl(wx, B - 0.02, wz, 3.1, 3.1, 0.12, 14, MID, true); g.cyl(wx, B, wz, 1.45, 1.45, 0.95, 12, STONE, false); g.cyl(wx, B, wz, 1.05, 1.05, 0.95, 12, DIM, false, null, 0, TAU, true); g.ring(wx, B + 0.95, wz, 1.05, 1.45, 12, DRESS); g.cyl(wx, B + 0.2, wz, 1.05, 1.05, 0.02, 12, HOLE, true);
      for (const sg of [-1, 1]) slab(g, Fw, sg * 1.25 - 0.11, sg * 1.25 + 0.11, B + 0.9, B + 3.1, -0.11, 0.11, WOODD, 4);
      slab(g, Fw, -1.5, 1.5, B + 2.3, B + 2.48, -0.09, 0.09, WOODD, 7); roof(g, Fw, 1.75, 1.0, B + 3.0, 0.85, 0.25, WOODD); g.cyl(wx + 2.2, B, wz + 0.6, 0.3, 0.36, 0.6, 8, WOODC, true); }
    // sheds against the north and west walls, stores by the gate
    { const Fs = frame(C.x - 40, C.z - 50.05, 0); leanTo(Fs, -7, 7, 4.4, B + 5.0, B + 3.0); stores(C.x - 42, C.z - 47.6, 12, 4.2);
      const Fs2 = frame(C.x - 61.65, C.z - 12, Math.PI / 2); leanTo(Fs2, -8, 8, 4.0, B + 5.0, B + 3.0); stores(C.x - 59.4, C.z - 12, 10, 3.0); stores(C.x - 59.4, C.z - 17, 5, 2.4);
      stores(C.x + 52.5, C.z + 13.5, 6, 2.6); stores(C.x + 52.5, C.z - 14, 5, 2.6); }
    // stone stairs up to the wall-walk on either side of the gate
    for (const sg of [-1, 1]) { const Fst = frame(C.x + 57.68, C.z + sg * 29, -Math.PI / 2); const n = 36, run = 18 / n, yT = B + WH, yL = B + WH / n;
      for (let k = 0; k < n; k++) { const l0 = sg * (-9 + k * run), l1 = sg * (-9 + (k + 1) * run); slab(g, Fst, l0, l1, B, yT - k * (WH / n), 0, 1.7, k % 2 ? MID : STONE, 5, k); }
      const ya = sg > 0 ? yT : yL, yb = sg > 0 ? yL : yT; // a parapet on the open side follows the flight
      g.hexa(rect(Fst, -9, 9, B - 0.3, 1.7, 2.05), [Fst(-9, ya + 1.0, 2.05), Fst(9, yb + 1.0, 2.05), Fst(9, yb + 1.0, 1.7), Fst(-9, ya + 1.0, 1.7)], STONE, 4);
      g.hexa([Fst(-9, ya + 1.0, 2.12), Fst(9, yb + 1.0, 2.12), Fst(9, yb + 1.0, 1.63), Fst(-9, ya + 1.0, 1.63)], [Fst(-9, ya + 1.16, 2.12), Fst(9, yb + 1.16, 2.12), Fst(9, yb + 1.16, 1.63), Fst(-9, ya + 1.16, 1.63)], DRESS, 7); }
    // threshold paving inside the gate
    g.box(C.x + 51.5, B + 0.04, C.z, 11, 0.12, 9, 0, MID, 1);
    // ---- barbican approach: a lowered drawbridge with its lifting chains, stone piers where the road arrives ----
    { const Fa = frame(C.x + 104, C.z, 0);
      slab(g, Fa, 2.7, 9.2, B + 0.04, B + 0.3, -3.5, 3.5, WOODD, 5); for (let lx = 3.3; lx < 9.2; lx += 1.45) slab(g, Fa, lx - 0.13, lx + 0.13, B + 0.3, B + 0.36, -3.5, 3.5, WOODC, 5);
      for (const sg of [-1, 1]) { for (let lx = 3.4; lx < 9.3; lx += 1.9) slab(g, Fa, lx - 0.09, lx + 0.09, B + 0.3, B + 1.35, sg * 3.4 - 0.09, sg * 3.4 + 0.09, WOODD, 4); slab(g, Fa, 3.2, 9.2, B + 1.2, B + 1.36, sg * 3.4 - 0.07, sg * 3.4 + 0.07, WOODD, 7);
        g.hexa(rect(Fa, 8.9, 9.02, B + 0.35, sg * 3.2 - 0.06, sg * 3.2 + 0.06), rect(Fa, 3.3, 3.42, B + 10.4, sg * 3.2 - 0.06, sg * 3.2 + 0.06), IRON, 4);
        slab(g, Fa, 9.4, 10.9, B - 0.5, B + 2.3, sg * 5.2 - 0.75, sg * 5.2 + 0.75, STONE, 4); slab(g, Fa, 9.25, 11.05, B + 2.3, B + 2.6, sg * 5.2 - 0.9, sg * 5.2 + 0.9, DRESS, 7);
        g.hexa(rect(Fa, 9.4, 10.9, B + 2.6, sg * 5.2 - 0.75, sg * 5.2 + 0.75), [Fa(10.15, B + 3.5, sg * 5.2), Fa(10.15, B + 3.5, sg * 5.2), Fa(10.15, B + 3.5, sg * 5.2), Fa(10.15, B + 3.5, sg * 5.2)], MID, 4); } }
    this.yard = this._mesh(g);
  },

  // the crag: faceted rock grown out of the plateau and its slopes — bedrock under the walls, a broken rim, cliff bands of ledges on the steep faces, a few pinnacles, scree fans below
  _crag(B) {
    const g = new GB(); const rng = mulberry32(4107); const H = (x, z) => terrain.height(x, z);
    const bur = (a, b, c) => !(a[1] < H(a[0], a[2]) - 0.3 && b[1] < H(b[0], b[2]) - 0.3 && c[1] < H(c[0], c[2]) - 0.3); // drop triangles that are wholly underground
    const col = () => { const k = 0.21 + rng() * 0.08; return [k * 1.1, k, k * 0.86]; };
    const ok = (x, z, pad = 0) => { if (terrain.roadDist(x, z) < 8 + pad) return false; const rx = x - C.x, rz = z - C.z; if (rx > 96 && rx < 150 && Math.abs(rz) < 16 + pad) return false;
      for (const t of TREBS) if (Math.hypot(rx - t[0], rz - t[1]) < 15 + pad) return false; return true; };
    const inWalls = (rx, rz, pad) => (rx > -64 - pad && rx < 60 + pad && rz > -54 - pad && rz < 58 + pad) || (rx >= 60 && rx < 112 + pad && Math.abs(rz) < 18 + pad);
    const grad = (x, z) => { const gx = (H(x + 3, z) - H(x - 3, z)) / 6, gz = (H(x, z + 3) - H(x, z - 3)) / 6; return [gx, gz, Math.hypot(gx, gz)]; };
    const patch = (a, d) => 0.5 + 0.5 * Math.sin(a * 5 + d * 0.11) * Math.sin(a * 2.3 + 1.7 - d * 0.05); // where the rock breaks out and where the slope stays bare
    // bedrock breaking out along the foot of the curtain walls and round the corner towers
    for (const w of this.walls) { if (w.type !== 'wall') continue; const F = frame(w.x, w.z, w.ry); const n = 1 + (rng() * 3 | 0);
      for (let i = 0; i < n; i++) { const p = F((rng() - 0.5) * w.len, 0, -w.th / 2 - 1.0 - rng() * 2.0); if (!ok(p[0], p[2], -3) || (p[0] - C.x > 56 && p[0] - C.x < 108 && Math.abs(p[2] - C.z) < 9)) continue;
        g.rock(p[0], B + rng() * 0.6, p[2], 3 + rng() * 4.5, 1.6 + rng() * 2.6, 2.2 + rng() * 2, rng, 1, col(), w.ry + (rng() - 0.5) * 0.5, (rng() - 0.5) * 0.3, 0.6, bur); } }
    for (const t of this.towers) { if (t.kind === 'gate') continue; const a0 = Math.atan2(t.z - C.z, t.x - C.x);
      for (let i = 0; i < 4; i++) { const a = a0 + (i - 1.5) * 0.62 + (rng() - 0.5) * 0.3, d = t.r + 2.2 + rng() * 1.6; g.rock(t.x + Math.cos(a) * d, B + rng() * 0.8, t.z + Math.sin(a) * d, 3.2 + rng() * 3, 2 + rng() * 3, 2.4 + rng() * 1.6, rng, 1, col(), -a + Math.PI / 2 + (rng() - 0.5) * 0.5, (rng() - 0.5) * 0.3, 0.6, bur); } }
    // low sheets of bedrock and loose boulders on the plateau outside the walls
    for (let i = 0; i < 110; i++) { const a = rng() * TAU, d = 66 + rng() * 64, x = C.x + Math.cos(a) * d, z = C.z + Math.sin(a) * d / 0.92; if (inWalls(x - C.x, z - C.z, 5) || !ok(x, z) || patch(a, d) < 0.35) continue;
      const s = 2.5 + rng() * rng() * 5; g.rock(x, H(x, z) - 0.2, z, s * (1 + rng() * 0.8), 0.9 + s * 0.2 + rng() * 0.8, s * (0.6 + rng() * 0.5), rng, 1, col(), rng() * TAU, (rng() - 0.5) * 0.14, 0.9, bur); }
    for (let i = 0; i < 260; i++) { const a = rng() * TAU, d = 66 + rng() * 76, x = C.x + Math.cos(a) * d, z = C.z + Math.sin(a) * d / 0.92; if (inWalls(x - C.x, z - C.z, 3) || !ok(x, z, -2)) continue;
      const s = 0.35 + rng() * rng() * 1.2; g.rock(x, H(x, z) + s * 0.2, z, s * (1 + rng() * 0.6), s * (0.6 + rng() * 0.5), s, rng, 0, col(), rng() * TAU, (rng() - 0.5) * 0.8, 0.1); }
    // broken rim: tors standing where the plateau falls away, each a few jointed blocks
    for (let i = 0; i < 70; i++) { const a = (i + rng() * 0.8) / 70 * TAU, d = 129 + rng() * 12, x = C.x + Math.cos(a) * d, z = C.z + Math.sin(a) * d / 0.92; if (!ok(x, z, 2) || patch(a, d) < 0.3) continue;
      const s = 1.8 + rng() * rng() * 3.6, sy = s * (0.7 + rng() * 0.6), y = H(x, z), ry = -a + Math.PI / 2 + (rng() - 0.5) * 0.7;
      g.rock(x, y + sy * 0.25, z, s * (1.2 + rng()), sy, s * (0.9 + rng() * 0.5), rng, s > 3.4 ? 2 : 1, col(), ry, (rng() - 0.5) * 0.3, 0.7, bur);
      if (s > 2.6) g.rock(x + Math.cos(ry) * s * 1.2, y + sy * 0.1, z - Math.sin(ry) * s * 1.2, s * 0.9, sy * (0.5 + rng() * 0.4), s * 0.8, rng, 1, col(), ry + (rng() - 0.5), (rng() - 0.5) * 0.4, 0.7, bur);
      if (sy > 4.6) world.addCyl(x, z, s * 0.8, y - 3, y + sy, 'rock'); }
    // cliff bands: jointed ledges following the contours wherever the ground is steep, rooted deep in the slope so only their faces and tops show
    for (let ring = 0; ring < 7; ring++) { const dcr = 141 + ring * 9, n = Math.round(TAU * dcr / 15);
      for (let i = 0; i < n; i++) { const a = (i + rng()) / n * TAU, d = dcr + (rng() - 0.5) * 6, x = C.x + Math.cos(a) * d, z = C.z + Math.sin(a) * d / 0.92; if (!ok(x, z, 4) || patch(a, d) < 0.22) continue;
        const [gx, gz, sl] = grad(x, z); if (sl < 0.3) continue; const y = H(x, z), ry = Math.atan2(-gx, -gz); // local +z of the rock points downhill
        const hx = 7 + rng() * 11, hy = 5 + rng() * 5, hz = 4.5 + rng() * 3.5;
        g.rock(x, y - hy * 0.35, z, hx, hy, hz, rng, 2, col(), ry + (rng() - 0.5) * 0.3, 0.05 + rng() * 0.16, 0.8, bur);
        for (let k = 0; k < 2; k++) if (rng() < 0.75) { const o = (k ? -1 : 1) * hx * (0.55 + rng() * 0.4), dn = (rng() - 0.3) * hz * 0.8, x2 = x + Math.cos(ry) * o + Math.sin(ry) * dn, z2 = z - Math.sin(ry) * o + Math.cos(ry) * dn; if (!ok(x2, z2, 2)) continue;
          const h2 = hy * (0.5 + rng() * 0.6); g.rock(x2, H(x2, z2) - h2 * 0.3, z2, hx * (0.35 + rng() * 0.3), h2, hz * (0.6 + rng() * 0.3), rng, 1, col(), ry + (rng() - 0.5) * 0.6, rng() * 0.2, 0.8, bur); } } }
    // pinnacles and buttresses of rock standing out of the faces (these have colliders)
    for (const [deg, d] of [[-62, 152], [-38, 158], [-21, 150], [24, 153], [47, 160], [71, 151], [118, 156], [158, 150], [203, 155], [236, 152], [-105, 154]]) { const a = deg * Math.PI / 180 + (rng() - 0.5) * 0.08, x = C.x + Math.cos(a) * d, z = C.z + Math.sin(a) * d / 0.92; if (!ok(x, z, 6)) continue;
      const [gx, gz] = grad(x, z), ry = Math.atan2(-gx, -gz), y = H(x, z); const hy = 6.5 + rng() * 3.5, hr = 5 + rng() * 3;
      g.rock(x, y + hy * 0.15, z, hr * 1.3, hy, hr, rng, 2, col(), ry + (rng() - 0.5) * 0.6, 0.05, 0.7, bur);
      g.rock(x + (rng() - 0.5) * 3, y + hy * 0.6, z + (rng() - 0.5) * 3, hr * 0.75, hy * 0.6, hr * 0.65, rng, 2, col(), rng() * TAU, (rng() - 0.5) * 0.2, 0.7);
      const x3 = x + Math.sin(ry) * hr * 1.1, z3 = z + Math.cos(ry) * hr * 1.1; g.rock(x3, H(x3, z3), z3, hr * 1.1, hy * 0.6, hr * 0.8, rng, 1, col(), ry + 0.4, 0.1, 0.7, bur);
      world.addCyl(x, z, hr * 0.8, y - 6, y + hy * 1.05, 'rock'); }
    // scree fans below the cliffs
    for (let i = 0; i < 620; i++) { const a = rng() * TAU, d = 150 + rng() * 95, x = C.x + Math.cos(a) * d, z = C.z + Math.sin(a) * d / 0.92; if (!ok(x, z, -3)) continue; const sl = grad(x, z)[2]; if (sl < 0.12 && rng() < 0.8) continue;
      const s = 0.5 + rng() * rng() * 2.2; g.rock(x, H(x, z) + s * 0.2, z, s * (1 + rng() * 0.7), s * (0.6 + rng() * 0.5), s, rng, s > 1.6 ? 1 : 0, col(), rng() * TAU, (rng() - 0.5) * 0.8, 0.1); }
    const m = this.crag = new THREE.Mesh(g.build(), cragMaterial()); m.castShadow = m.receiveShadow = true; m.name = 'crag'; this.group.add(m);
  },

  commitShadows() {
    terrain.resetOccluders();
    for (const s of this.structs) {
      const top = s.alive ? s.topY : s.baseY + (s.stump || 3);
      if (s.type === 'tower') terrain.stampOccluder(s.x, s.z, s.r + 1, top + (s.alive ? 2 : 0));
      else { const n = Math.ceil(s.len / 4); const c = Math.cos(s.ry), sn = Math.sin(s.ry); for (let i = 0; i <= n; i++) { const l = -s.len / 2 + i * s.len / n; terrain.stampOccluder(s.x + l * c, s.z - l * sn, 3, top + (s.alive ? 1.5 : 0)); } }
    }
    if (this.keep) { const k = this.keep; for (let i = -2; i <= 2; i++) for (let j = -2; j <= 2; j++) terrain.stampOccluder(k.x + i * 6, k.z + j * 6, 5, k.topY + (Math.abs(i) === 2 && Math.abs(j) === 2 ? 15 : 2)); }
    terrain.commitOccluders();
  },

  // damage from an explosion at p (world) — returns true if something was hit
  damageAt(p, radius, dmg) {
    let hit = false;
    for (const s of this.structs) {
      if (!s.alive) continue;
      const d = Math.hypot(p.x - s.x, p.z - s.z) - (s.type === 'tower' ? s.r : Math.min(s.len / 2, 6));
      if (d < radius && p.y < s.topY + radius + 2 && p.y > s.baseY - 10) { this.damage(s, dmg * clamp(1 - Math.max(d, 0) / radius * 0.6, 0.3, 1), p); hit = true; }
    }
    return hit;
  },
  damage(s, dmg, p) {
    if (!s.alive) return;
    s.hp -= dmg;
    if (s.hp <= 0) this.destroy(s, p);
    else if (dmg > 20) { fx.dustCloud(_v.set(p ? p.x : s.x, (p ? p.y : s.topY), p ? p.z : s.z), 3, 4, 2); fx.debrisBurst(_v, 4, 0.5, 0x8a8378, null, 9); }
  },
  destroy(s, p) {
    if (!s.alive) return; s.alive = false; s.hp = 0;
    s.mesh.visible = false; s.ruin.visible = true; if (s.door) s.door.visible = false;
    const B = s.baseY; const from = p || _v.set(s.x + 1, s.topY, s.z);
    const stoneCol = 0x8a8378;
    if (s.type === 'tower') {
      s.col.y1 = B + s.stump + 2; if (s.col2) s.col2.alive = false;
      const dirx = s.x - from.x, dirz = s.z - from.z, dl = Math.hypot(dirx, dirz) || 1; const tx = dirx / dl, tz = dirz / dl; // topple away from the blast
      const n = 58;
      for (let i = 0; i < n; i++) {
        const a = rnd(TAU), rr = s.r * Math.sqrt(Math.random()), hh = s.stump + Math.random() * (s.h - s.stump + 2); const k = hh / s.h;
        const d = fx.chunk(s.x + Math.cos(a) * rr, B + hh, s.z + Math.sin(a) * rr, Math.cos(a) * rnd(1, 6) + tx * k * rnd(4, 11), rnd(-2, 5) * k, Math.sin(a) * rnd(1, 6) + tz * k * rnd(4, 11), rnd(0.9, 2.3), stoneCol, rnd(10, 16), i % 2 === 0);
      }
      fx.dustCloud(_v.set(s.x, B + s.h * 0.5, s.z), s.r + 3, 26, 5); fx.dustCloud(_v.set(s.x + tx * 6, B + 2, s.z + tz * 6), s.r + 8, 22, 2);
      fx.explosion(_v.set(s.x, B + s.h * 0.7, s.z), 2.2, { debris: 14, debrisColor: stoneCol, scorch: false });
      audio.play('explLarge', { pos: [s.x, s.topY, s.z] }); audio.play('collapse', { pos: [s.x, s.topY, s.z], delay: 0.25 });
      fx.shake(_v, 1.6, 900);
    } else {
      s.col.alive = false;
      const c = Math.cos(s.ry), sn = Math.sin(s.ry); const n = Math.round(s.len * 1.8);
      for (let i = 0; i < n; i++) { const l = (Math.random() - 0.5) * s.len; const hh = Math.random() * (s.h + 1); const out = rndS(1); fx.chunk(s.x + l * c, B + hh, s.z - l * sn, sn * out * rnd(3, 9) + rndS(2), rnd(0, 6), c * out * rnd(3, 9) + rndS(2), rnd(0.8, 1.9), stoneCol, rnd(9, 14), i % 2 === 0); }
      fx.dustCloud(_v.set(s.x, B + s.h * 0.4, s.z), s.len * 0.45, 22, 4);
      fx.explosion(_v.set(s.x, B + s.h * 0.6, s.z), 1.8, { debris: 10, debrisColor: stoneCol, scorch: false });
      audio.play('explMedium', { pos: [s.x, s.topY, s.z] }); audio.play('collapse', { pos: [s.x, s.topY, s.z], delay: 0.2, gain: 0.7, kind: 'wall' });
      fx.shake(_v, 1.2, 700);
    }
    this.commitShadows();
    G.events.dispatchEvent(new CustomEvent('structDestroyed', { detail: s }));
  },
  reset() {
    for (const s of this.structs) { s.alive = true; s.hp = s.maxHp; s.mesh.visible = true; s.ruin.visible = false; if (s.door) s.door.visible = true; s.col.alive = true; if (s.type === 'tower') s.col.y1 = s.topY + 2.4; if (s.col2) s.col2.alive = true; }
    this.commitShadows();
  },
  // is a point inside the courtyard?
  inCourtyard(x, z) { return x > C.x - 62 && x < C.x + 58 && z > C.z - 52 && z < C.z + 56; },
};
