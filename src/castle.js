// Siege Wing — the castle: procedural masonry, destructible towers / wall sections / gate, colliders, mounts
import * as THREE from 'three';
import { G, V3, patchMaterial, rnd, rndS, clamp, mulberry32, TAU, lerp } from './core.js';
import { terrain, L } from './terrain.js';
import { world } from './world.js';
import { GB } from './geo.js';
import { fx } from './fx.js';
import { audio } from './audio.js';

const C = L.CASTLE;
const STONE = [1, 1, 1], DARK = [0.08, 0.07, 0.06], SLATE = [0.5, 0.52, 0.6], WOODC = [0.75, 0.6, 0.45];
const _v = new V3();

function stoneMaterial() {
  const m = new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.92, metalness: 0, vertexColors: true });
  return patchMaterial(m, 'stone', sh => {
    sh.vertexShader = sh.vertexShader.replace('#include <common>', '#include <common>\nvarying vec2 vSU; varying vec3 vSN; varying vec3 vSW;')
      .replace('#include <begin_vertex>', '#include <begin_vertex>\n vSU = uv; vSN = normalize(mat3(modelMatrix) * normal); vSW = (modelMatrix * vec4(transformed, 1.0)).xyz;');
    sh.fragmentShader = sh.fragmentShader.replace('#include <common>', `#include <common>
      varying vec2 vSU; varying vec3 vSN; varying vec3 vSW; uniform sampler2D uNoise; uniform float uNight; uniform float uTime; vec3 swNP; float swR;
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
          swNP = (top ? vec3(0.0) : vec3(0.0, (1.0 - mort) * (f.y < 0.5 ? 1.0 : -1.0), 0.0)) * 0.6 * det;
          swR = mix(0.97, 0.86, mort);
        } else if (kind < 1.5) { // slate
          float row = floor(uvm.y / 0.42); float bx = uvm.x / 0.5 + fract(row * 0.5); vec2 f = vec2(fract(bx), fract(uvm.y / 0.42));
          float hsh = h21(vec2(floor(bx), row));
          col = mix(vec3(0.10, 0.11, 0.135), vec3(0.19, 0.20, 0.24), hsh) * (0.75 + 0.5 * n3);
          col *= mix(1.0, smoothstep(0.0, 0.07, f.x) * (0.55 + 0.45 * smoothstep(0.0, 0.5, f.y)), det);
          swR = 0.62;
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
  });
}

export const castle = {
  group: null, mat: null, structs: [], towers: [], walls: [], mounts: { ballista: [], bombard: [], treb: [] }, wallSpots: [], firePots: [], rng: null,
  build(scene) {
    this.mat = stoneMaterial();
    this.group = new THREE.Group(); this.group.name = 'castle'; scene.add(this.group);
    this.rng = mulberry32(77);
    const B = C.y; // base height
    const W = (x, z) => [C.x + x, C.z + z];
    // ---- towers ----
    const corner = [[60, -54], [60, 54], [-64, 58], [-64, -52]];
    const gate = [[60, -10], [60, 10], [104, -10.5], [104, 10.5]];
    gate.forEach((p, i) => this._tower('gate', i, C.x + p[0], C.z + p[1], 6.6, i < 2 ? 25 : 21, B));
    corner.forEach((p, i) => this._tower('corner', i, C.x + p[0], C.z + p[1], 7.6, 21, B));
    // ---- curtain walls (split into ~18 m destructible sections) ----
    const WH = 12.5;
    const ring = [[60, -54], [60, -10], null, [60, 10], [60, 54], [-64, 58], [-64, -52], [60, -54]];
    for (let i = 0; i < ring.length - 1; i++) { const a = ring[i], b = ring[i + 1]; if (!a || !b) continue; this._wallRun(C.x + a[0], C.z + a[1], C.x + b[0], C.z + b[1], WH, 4.6, B, 7.6); }
    // barbican passage walls
    this._wallRun(C.x + 60, C.z - 10, C.x + 104, C.z - 10.5, 10, 3.6, B, 6.6);
    this._wallRun(C.x + 104, C.z + 10.5, C.x + 60, C.z + 10, 10, 3.6, B, 6.6);
    // ---- gates ----
    this._gate(C.x + 60, C.z, 20, 14, B, 'inner');
    this._gate(C.x + 104, C.z, 21, 12, B, 'outer');
    // ---- keep ----
    this._keep(C.x - 30, C.z, B);
    // ---- courtyard dressing: fire pots (lit in phase 3) ----
    for (const p of [[18, -26], [18, 26], [-2, -40], [-2, 40], [38, 0], [-50, -30], [-50, 32]]) this.firePots.push({ x: C.x + p[0], y: B, z: C.z + p[1], lit: false, emitter: null });
    // ---- mounts ----
    for (const t of this.towers) this.mounts.ballista.push({ x: t.x, y: t.topY, z: t.z, tower: t });
    const bomb = [[60, -32, 0], [60, 32, 0], [0, -53, -Math.PI / 2 * 1], [-2, 56, Math.PI / 2], [82, -10.3, -Math.PI / 2]];
    for (const b of bomb) { const wall = this._nearestWall(C.x + b[0], C.z + b[1]); this.mounts.bombard.push({ x: C.x + b[0], y: wall ? wall.topY : B + WH, z: C.z + b[1], yaw: b[2], wall }); }
    for (const t of [[-112, -44], [-120, 2], [-112, 48]]) { const x = C.x + t[0], z = C.z + t[1]; this.mounts.treb.push({ x, y: terrain.height(x, z), z }); }
    this.commitShadows();
  },
  _nearestWall(x, z) { let best = null, bd = 1e9; for (const w of this.walls) { const d = Math.hypot(w.x - x, w.z - z); if (d < bd) { bd = d; best = w; } } return best; },

  _register(s) { s.hp = s.maxHp; s.alive = true; this.structs.push(s); return s; },

  _tower(kind, idx, x, z, r, h, B) {
    const rng = this.rng; const topY = B + h;
    const g = new GB(); const seg = 22;
    g.cyl(x, B - 6, z, r + 1.4, r, 9, seg, STONE, false);                 // battered base
    g.cyl(x, B + 3, z, r, r, h - 4.2, seg, STONE, false);
    g.cyl(x, topY - 1.2, z, r, r + 0.9, 0.7, seg, [0.8, 0.8, 0.8], false);  // corbel flare
    g.cyl(x, topY - 0.5, z, r + 0.9, r + 0.9, 1.6, seg, STONE, false);      // parapet outer
    g.cyl(x, topY, z, r + 0.25, r + 0.25, 1.1, seg, [0.7, 0.7, 0.7], false, null, 0, TAU, true); // parapet inner
    // parapet top ring + floor
    for (let i = 0; i < seg; i++) { const a = i / seg * TAU, b = (i + 1) / seg * TAU; const ro = r + 0.9, ri = r + 0.25; g.quad([x + Math.cos(a) * ri, topY + 1.1, z + Math.sin(a) * ri], [x + Math.cos(a) * ro, topY + 1.1, z + Math.sin(a) * ro], [x + Math.cos(b) * ro, topY + 1.1, z + Math.sin(b) * ro], [x + Math.cos(b) * ri, topY + 1.1, z + Math.sin(b) * ri], [a * r, 0], [a * r, 0.65], [b * r, 0.65], [b * r, 0], STONE); }
    g.cyl(x, topY - 0.1, z, r + 0.3, r + 0.3, 0.1, seg, [0.8, 0.8, 0.8], true);
    const nm = Math.round(TAU * (r + 0.6) / 1.25 / 2) * 2; g.merlons(x, topY + 1.1, z, r + 0.57, nm, 1.25, 1.15, 0.65, STONE);
    // corbels
    for (let i = 0; i < nm; i++) { const a = (i + 0.5) / nm * TAU; g.box(x + Math.cos(a) * (r + 0.45), topY - 1.55, z + Math.sin(a) * (r + 0.45), 0.45, 0.7, 0.8, -a + Math.PI / 2, [0.75, 0.75, 0.75], 7); }
    // arrow slits
    for (let lv = 0; lv < 3; lv++) for (let k = 0; k < 5; k++) { const a = (k + lv * 0.5) / 5 * TAU + 0.3, yy = B + 5 + lv * 5.2; if (yy > topY - 4) continue; g.box(x + Math.cos(a) * (r + 0.02), yy, z + Math.sin(a) * (r + 0.02), 0.28, 1.7, 0.12, -a + Math.PI / 2, DARK, 4); }
    const mesh = new THREE.Mesh(g.build(), this.mat); mesh.castShadow = mesh.receiveShadow = true; this.group.add(mesh);
    // ruin: jagged stump + rubble
    const rg = new GB(); const stump = h * rnd(0.28, 0.42); const jags = Array.from({ length: seg }, () => rng() * 5 - 1.5);
    rg.cyl(x, B - 6, z, r + 1.4, r, 9, seg, [0.8, 0.78, 0.75], false);
    rg.cyl(x, B + 3, z, r, r, stump - 3, seg, [0.72, 0.7, 0.66], false, i => jags[i]);
    rg.cyl(x, B + 3, z, r - 1.1, r - 1.1, stump - 3, seg, [0.3, 0.29, 0.27], false, i => jags[i], 0, TAU, true);
    rg.cyl(x, B + 2, z, r - 1.1, r - 1.1, stump * 0.5, seg, [0.25, 0.24, 0.22], true);
    for (let i = 0; i < 16; i++) { const a = rng() * TAU, d = r + rng() * 7; const s = 0.8 + rng() * 1.8; const px = x + Math.cos(a) * d, pz = z + Math.sin(a) * d; rg.box(px, Math.max(terrain.height(px, pz), B - 8) + s * 0.25, pz, s * 1.3, s * 0.7, s, rng() * 3, [0.7, 0.68, 0.64], 5); }
    const ruin = new THREE.Mesh(rg.build(), this.mat); ruin.castShadow = ruin.receiveShadow = true; ruin.visible = false; this.group.add(ruin);
    const col = world.addCyl(x, z, r + 0.9, B - 8, topY + 2.4, 'tower');
    const t = this._register({ type: 'tower', kind, idx, x, z, r, h, baseY: B, topY, y: topY, stump, mesh, ruin, col, maxHp: 300, name: (kind === 'gate' ? 'Gate tower ' : 'Corner tower ') + (idx + 1) });
    col.ref = t; this.towers.push(t); return t;
  },

  _wallRun(ax, az, bx, bz, h, th, B, inset) {
    const len = Math.hypot(bx - ax, bz - az); const dx = (bx - ax) / len, dz = (bz - az) / len;
    const a0 = inset - 1.2, a1 = len - inset + 1.2; const n = Math.max(1, Math.round((a1 - a0) / 18)); const sl = (a1 - a0) / n;
    for (let i = 0; i < n; i++) { const m = a0 + (i + 0.5) * sl; this._wall(ax + dx * m, az + dz * m, sl, Math.atan2(-dz, dx), h, th, B, a0 + i * sl); }
  },
  // wall section centred (x,z), length along local x rotated by ry; outer side = local -z (right of a→b when walking the ring clockwise from above)
  _wall(x, z, len, ry, h, th, B, uo) {
    const rng = this.rng; const topY = B + h;
    const g = new GB(); const c = Math.cos(ry), s = Math.sin(ry); const off = (lx, lz) => [x + lx * c + lz * s, z - lx * s + lz * c];
    g.box(x, B - 5 + (h + 5) / 2, z, len, h + 5, th, ry, STONE, 5, uo);
    // walkway overhang + parapets: outer (local +z is outside for our ring orientation)
    const out = 1;
    { const [px, pz] = off(0, out * (th / 2 + 0.15)); g.box(px, topY + 0.55, pz, len, 1.5, 0.6, ry, STONE, 5, uo); }
    { const [px, pz] = off(0, -out * (th / 2 - 0.2)); g.box(px, topY + 0.35, pz, len, 0.7, 0.4, ry, [0.8, 0.8, 0.8], 5, uo); }
    const nm = Math.max(2, Math.round(len / 2.3));
    for (let i = 0; i < nm; i++) { const lx = -len / 2 + (i + 0.5) * len / nm; const [px, pz] = off(lx, out * (th / 2 + 0.15)); g.box(px, topY + 1.3 + 0.55, pz, len / nm * 0.55, 1.1, 0.6, ry, STONE, 5, uo + lx); }
    for (let i = 0; i < Math.round(len / 7); i++) { const lx = -len / 2 + (i + 0.5) * 7; const [px, pz] = off(lx, out * (th / 2 + 0.02)); g.box(px, B + h * 0.55, pz, 0.26, 1.6, 0.1, ry, DARK, 4); }
    const mesh = new THREE.Mesh(g.build(), this.mat); mesh.castShadow = mesh.receiveShadow = true; this.group.add(mesh);
    const rg = new GB(); const k = Math.max(3, Math.round(len / 3));
    for (let i = 0; i < k; i++) { const lx = -len / 2 + (i + 0.5) * len / k; const [px, pz] = off(lx, 0); const hh = 1.5 + rng() * (i === 0 || i === k - 1 ? h * 0.8 : h * 0.3); rg.box(px, B - 5 + (hh + 5) / 2, pz, len / k + 0.05, hh + 5, th * (0.85 + rng() * 0.15), ry, [0.7, 0.68, 0.64], 5, uo + lx); }
    for (let i = 0; i < 10; i++) { const [px, pz] = off((rng() - 0.5) * len, (rng() - 0.5) * 14); const sz = 0.7 + rng() * 1.6; rg.box(px, terrain.height(px, pz) + sz * 0.25, pz, sz * 1.3, sz * 0.7, sz, rng() * 3, [0.7, 0.68, 0.64], 5); }
    const ruin = new THREE.Mesh(rg.build(), this.mat); ruin.castShadow = ruin.receiveShadow = true; ruin.visible = false; this.group.add(ruin);
    const col = world.addBox(x, z, len / 2, th / 2 + 0.5, ry, B - 8, topY + 2.6, 'wall');
    const w = this._register({ type: 'wall', x, z, len, ry, h, th, baseY: B, topY, y: topY, mesh, ruin, col, maxHp: 220, name: 'Wall section' });
    col.ref = w; this.walls.push(w);
    // standing spots for archers along the walkway
    for (let i = 0; i < Math.floor(len / 2.2); i++) { const lx = -len / 2 + (i + 0.5) * 2.2; const [px, pz] = off(lx, 0.6); this.wallSpots.push({ x: px, y: topY + 0.02, z: pz, yaw: ry, wall: w, ox: s, oz: c }); }
    return w;
  },

  _gate(x, z, towerSpan, h, B, which) {
    // gatehouse block between the two flanking towers; passage runs along x
    const g = new GB(); const topY = B + h; const half = 3.6;
    // wall above arch
    g.box(x, B + 7.5 + (h - 7.5) / 2, z, 5, h - 7.5, towerSpan - 8, 0, STONE, 7);
    // piers
    g.box(x, B - 4 + 11.5 / 2, z - (half + (towerSpan - 8 - half * 2) / 4), 5, 11.5, (towerSpan - 8 - half * 2) / 2, 0, STONE, 5);
    g.box(x, B - 4 + 11.5 / 2, z + (half + (towerSpan - 8 - half * 2) / 4), 5, 11.5, (towerSpan - 8 - half * 2) / 2, 0, STONE, 5);
    // crenellations
    for (let i = 0; i < 6; i++) { const lz = -((towerSpan - 8) / 2) + (i + 0.5) * (towerSpan - 8) / 6; if (i % 2 === 0) { g.box(x + 2.2, topY + 0.6, z + lz, 0.6, 1.2, 1.2, 0, STONE, 5); g.box(x - 2.2, topY + 0.6, z + lz, 0.6, 1.2, 1.2, 0, STONE, 5); } }
    const mesh = new THREE.Mesh(g.build(), this.mat); mesh.castShadow = mesh.receiveShadow = true; this.group.add(mesh);
    // door (wood) + portcullis bars, separate so it can be blown
    const dg = new GB(); dg.box(x + 1.2, B + 3.8, z, 0.5, 7.6, half * 2, 0, WOODC, 5);
    for (let i = 0; i < 7; i++) dg.box(x + 1.55, B + 3.8, z - half + (i + 0.5) * half * 2 / 7, 0.14, 7.6, 0.14, 0, DARK, 5);
    for (let i = 0; i < 6; i++) dg.box(x + 1.55, B + 0.6 + i * 1.25, z, 0.14, 0.14, half * 2, 0, DARK, 5);
    const door = new THREE.Mesh(dg.build(), this.mat); door.castShadow = door.receiveShadow = true; this.group.add(door);
    const rg = new GB(); rg.box(x, B - 4 + 6 / 2, z - half - 1.3, 5, 6 + rnd(3), 2.4, 0, [0.7, 0.68, 0.64], 5); rg.box(x, B - 4 + 5 / 2, z + half + 1.3, 5, 5 + rnd(4), 2.4, 0, [0.7, 0.68, 0.64], 5);
    for (let i = 0; i < 9; i++) { const sz = 0.7 + this.rng() * 1.5; rg.box(x + (this.rng() - 0.5) * 12, B + sz * 0.25, z + (this.rng() - 0.5) * 9, sz * 1.3, sz * 0.7, sz, this.rng() * 3, [0.7, 0.68, 0.64], 5); }
    const ruin = new THREE.Mesh(rg.build(), this.mat); ruin.castShadow = ruin.receiveShadow = true; ruin.visible = false; this.group.add(ruin);
    const col = world.addBox(x, z, 2.6, (towerSpan - 8) / 2, 0, B - 6, topY + 1.5, 'wall');
    const s = this._register({ type: 'gate', which, x, z, len: towerSpan - 8, ry: Math.PI / 2, h, th: 5, baseY: B, topY, y: topY, mesh, ruin, col, door, maxHp: 260, name: which === 'inner' ? 'Main gate' : 'Barbican gate' });
    col.ref = s; this.walls.push(s); this[which + 'Gate'] = s;
  },

  _keep(x, z, B) {
    const g = new GB(); const S = 25, H = 34; const topY = B + H;
    g.box(x, B - 5 + (H + 5) / 2, z, S, H + 5, S, 0, STONE, 5);
    g.box(x, B + 1.5, z, S + 2.4, 5, S + 2.4, 0, [0.85, 0.85, 0.85], 5);               // plinth
    g.box(x, topY - 0.9, z, S + 1.4, 1.2, S + 1.4, 0, [0.8, 0.8, 0.8], 7);              // cornice
    // parapet + merlons
    for (const [dx, dz, ry, len] of [[0, 1, 0, S + 1.4], [0, -1, 0, S + 1.4], [1, 0, Math.PI / 2, S + 1.4], [-1, 0, Math.PI / 2, S + 1.4]]) {
      const px = x + dx * (S / 2 + 0.4), pz = z + dz * (S / 2 + 0.4);
      g.box(px, topY + 0.35, pz, len, 1.3, 0.6, ry, STONE, 5);
      for (let i = 0; i < 11; i++) if (i % 2 === 0) { const l = -len / 2 + (i + 0.5) * len / 11; g.box(px + (ry ? 0 : l), topY + 1.55, pz + (ry ? l : 0), len / 11 * 1.0, 1.1, 0.6, ry, STONE, 5); }
    }
    // windows + buttresses
    for (let f = 0; f < 4; f++) { const a = f * Math.PI / 2; const nx = Math.cos(a), nz = Math.sin(a);
      for (let lv = 0; lv < 3; lv++) for (let k = -1; k <= 1; k++) { const tx = -nz * k * 6.5, tz = nx * k * 6.5; g.box(x + nx * (S / 2 + 0.03) + tx, B + 9 + lv * 8, z + nz * (S / 2 + 0.03) + tz, 0.9, lv === 2 ? 2.6 : 1.9, 0.1, -a + Math.PI / 2, DARK, 4); }
      for (const k of [-0.36, 0.36]) { const tx = -nz * k * S, tz = nx * k * S; g.box(x + nx * (S / 2 + 0.5) + tx, B - 3 + (H * 0.8) / 2, z + nz * (S / 2 + 0.5) + tz, 2.2, H * 0.8 + 3, 1.2, -a + Math.PI / 2, [0.9, 0.9, 0.9], 5); }
    }
    // entrance stair + door (east face)
    g.box(x + S / 2 + 3, B + 1.5, z, 6, 3.2, 5, 0, [0.85, 0.85, 0.85], 5); g.box(x + S / 2 + 0.05, B + 5.2, z, 0.12, 4.2, 2.6, 0, WOODC, 4);
    // corner turrets with slate cones
    for (const [sx, sz] of [[1, 1], [1, -1], [-1, 1], [-1, -1]]) {
      const tx = x + sx * S / 2, tz = z + sz * S / 2; const tr = 3.9, th = H + 7;
      g.cyl(tx, B - 5, tz, tr, tr, th + 5, 14, STONE, false); g.cyl(tx, B + th, tz, tr, tr + 0.6, 0.6, 14, [0.8, 0.8, 0.8], false); g.cyl(tx, B + th + 0.6, tz, tr + 0.6, tr + 0.6, 1.0, 14, STONE, false);
      g.cyl(tx, B + th + 1.6, tz, tr + 1.0, 0, 8.5, 14, SLATE, false);
      for (let lv = 0; lv < 4; lv++) { const a = Math.atan2(sz, sx) + (lv % 2 ? 0.6 : -0.6); g.box(tx + Math.cos(a) * (tr + 0.02), B + 8 + lv * 8, tz + Math.sin(a) * (tr + 0.02), 0.26, 1.6, 0.1, -a + Math.PI / 2, DARK, 4); }
    }
    // roof deck + central slate roof hall
    g.box(x, topY - 0.2, z, S, 0.3, S, 0, [0.8, 0.8, 0.8], 1);
    g.box(x, topY + 1.5, z, S - 9, 3.2, S - 13, 0, STONE, 5); g.gable(x, topY + 3.1, z, S - 9, S - 13, 5.5, 0, SLATE, 0.6); g.gableEnds(x, topY + 3.1, z, S - 9, S - 13, 5.5, 0, STONE);
    const mesh = new THREE.Mesh(g.build(), this.mat); mesh.castShadow = mesh.receiveShadow = true; this.group.add(mesh);
    this.keep = { x, z, S, H, topY, baseY: B, mesh };
    world.addBox(x, z, S / 2 + 1.2, S / 2 + 1.2, 0, B - 6, topY + 3, 'keep');
    world.addBox(x, z, (S - 9) / 2 + 1, (S - 13) / 2 + 1, 0, topY, topY + 9, 'keep');
    for (const [sx, sz] of [[1, 1], [1, -1], [-1, 1], [-1, -1]]) world.addCyl(x + sx * S / 2, z + sz * S / 2, 4.6, B, B + H + 17, 'keep');
    // great hall + stores against the north and south walls
    const hg = new GB();
    const hall = (hx, hz, sx, sz, hh, ry) => { hg.box(hx, B - 1 + (hh + 1) / 2, hz, sx, hh + 1, sz, ry, STONE, 4); hg.gable(hx, B + hh, hz, sx, sz, sz * 0.42, ry, SLATE, 0.7); hg.gableEnds(hx, B + hh, hz, sx, sz, sz * 0.42, ry, STONE);
      for (let i = 0; i < Math.floor(sx / 4); i++) { const l = -sx / 2 + (i + 0.5) * 4; const cc = Math.cos(ry), ss = Math.sin(ry); hg.box(hx + l * cc + (sz / 2 + 0.03) * ss, B + hh * 0.55, hz - l * ss + (sz / 2 + 0.03) * cc, 0.8, 1.8, 0.1, ry, DARK, 4); hg.box(hx + l * cc - (sz / 2 + 0.03) * ss, B + hh * 0.55, hz - l * ss - (sz / 2 + 0.03) * cc, 0.8, 1.8, 0.1, ry, DARK, 4); }
      world.addBox(hx, hz, sx / 2 + 0.5, sz / 2 + 0.5, ry, B - 2, B + hh + sz * 0.42, 'house'); terrain.stampOccluder(hx, hz, Math.min(sx, sz) / 2, B + hh + 2); };
    hall(C.x + 8, C.z - 40, 34, 11, 8, 0); hall(C.x + 22, C.z + 42, 26, 9, 6, 0); hall(C.x - 52, C.z + 36, 12, 16, 6, 0.0); hall(C.x + 46, C.z - 30, 9, 13, 5.5, 0);
    const hm = new THREE.Mesh(hg.build(), this.mat); hm.castShadow = hm.receiveShadow = true; this.group.add(hm);
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
      s.col.y1 = B + s.stump + 2;
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
    for (const s of this.structs) { s.alive = true; s.hp = s.maxHp; s.mesh.visible = true; s.ruin.visible = false; if (s.door) s.door.visible = true; s.col.alive = true; if (s.type === 'tower') s.col.y1 = s.topY + 2.4; }
    this.commitShadows();
  },
  // is a point inside the courtyard?
  inCourtyard(x, z) { return x > C.x - 62 && x < C.x + 58 && z > C.z - 52 && z < C.z + 56; },
};
