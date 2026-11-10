// Siege Wing — valley terrain: height function, heightmap, mesh, material, scorch map, far sun shadows
import * as THREE from 'three';
import { G, fbm, ridged, vnoise, smooth, lerp, clamp, wrapPi, patchMaterial, makeNoiseTexture } from './core.js';
import { assets } from './assets.js';

// ---------- world layout (x = east, z = south, y = up) ----------
export const L = {
  PLAY_R: 1500,
  CASTLE: { x: -450, z: 0, y: 104 },
  FIELD: { x: 170, z: 0, rx: 380, rz: 430 },
  PAD: { x: 1150, z: 250, y: 118 },
  START: { x: 1980, z: 400 },
  VILLAGE: { x: 440, z: -520 },
  WATER_Y: 15,
  HM_HALF: 2000, HM_N: 801, HM_CELL: 5,
};
export const riverX = z => 640 + 110 * Math.sin(z * 0.004) + 45 * Math.sin(z * 0.011 + 1);

export function heightRaw(x, z) {
  const r = Math.hypot(x, z);
  let h = 30 + fbm(x * 0.0011 + 3.1, z * 0.0011 - 1.7, 5) * 34 + fbm(x * 0.007, z * 0.007, 3) * 3.5;
  // mountain ring with an opening to the west (where the sun sets)
  const ang = Math.atan2(z, x);
  const wg = wrapPi(ang - Math.PI) / 0.5; const westGap = Math.exp(-wg * wg);
  const m = smooth(1500, 4300, r);
  const rg = ridged(x * 0.00055 + 5, z * 0.00055 + 9, 5);
  h += m * m * (130 + 620 * rg) * (1 - 0.82 * westGap) + m * 30;
  // castle ridge running north-south
  const rx = (x + 480) / 135; const zfade = smooth(1300, 500, Math.abs(z));
  h += Math.exp(-rx * rx) * (72 + 10 * vnoise(z * 0.004, 2.2)) * zfade;
  // castle plateau
  const dc = Math.hypot(x - L.CASTLE.x, (z - L.CASTLE.z) * 0.92);
  h = lerp(h, L.CASTLE.y, smooth(196, 138, dc));
  // the field
  const fe = Math.hypot((x - L.FIELD.x) / L.FIELD.rx, (z - L.FIELD.z) / L.FIELD.rz);
  h = lerp(h, 24 + fbm(x * 0.004, z * 0.004, 3) * 3, smooth(1.15, 0.6, fe) * 0.92);
  // far hill + rearm pad
  const dh = Math.hypot(x - L.PAD.x, z - L.PAD.z);
  h += 92 * Math.exp(-(dh * dh) / (300 * 300));
  h = lerp(h, L.PAD.y, smooth(64, 36, dh));
  // river
  const d = Math.abs(x - riverX(z)); const rm = smooth(2900, 2000, Math.abs(z));
  h = lerp(h, Math.min(h, L.WATER_Y + 3), smooth(260, 70, d) * 0.75 * rm);
  h = lerp(h, L.WATER_Y - 3.2, smooth(27, 5, d) * rm);
  return h;
}

const N = L.HM_N, HALF = L.HM_HALF, CELL = L.HM_CELL;
export const terrain = {
  hm: null,          // Float32Array N*N heights
  occ: null,         // heights incl. structures (for far shadows)
  mesh: null, ctlTex: null, scorchRT: null, farRT: null,

  // exact height of the rendered triangle surface inside the heightmap, analytic outside
  height(x, z) {
    const fx = (x + HALF) / CELL, fz = (z + HALF) / CELL;
    if (fx < 0 || fz < 0 || fx >= N - 1 || fz >= N - 1) return heightRaw(x, z);
    const ix = fx | 0, iz = fz | 0, tx = fx - ix, tz = fz - iz; const i = iz * N + ix; const hm = this.hm;
    const h00 = hm[i], h10 = hm[i + 1], h01 = hm[i + N], h11 = hm[i + N + 1];
    // triangles: (00,01,10) and (10,01,11)
    return tx + tz <= 1 ? h00 + (h10 - h00) * tx + (h01 - h00) * tz : h11 + (h01 - h11) * (1 - tx) + (h10 - h11) * (1 - tz);
  },
  normal(x, z, out) {
    const e = 2.5; const hx = this.height(x + e, z) - this.height(x - e, z), hz = this.height(x, z + e) - this.height(x, z - e);
    return out.set(-hx, 2 * e, -hz).normalize();
  },
  // march a ray against terrain; returns distance or -1
  raycast(o, d, maxDist = 3000, step = 4) {
    let t = 0, prev = 0; let hPrev = o.y - this.height(o.x, o.z); if (hPrev < 0) return 0;
    while (t < maxDist) {
      const st = Math.max(step, hPrev * 0.4); t += st;
      const y = o.y + d.y * t; const h = y - this.height(o.x + d.x * t, o.z + d.z * t);
      if (h < 0) { // refine
        let a = prev, b = t; for (let i = 0; i < 8; i++) { const mid = (a + b) / 2; const hm = o.y + d.y * mid - this.height(o.x + d.x * mid, o.z + d.z * mid); if (hm < 0) b = mid; else a = mid; }
        return (a + b) / 2;
      }
      prev = t; hPrev = h;
    }
    return -1;
  },

  build(scene, onProgress) {
    const hm = this.hm = new Float32Array(N * N);
    for (let j = 0; j < N; j++) { const z = -HALF + j * CELL; for (let i = 0; i < N; i++) hm[j * N + i] = heightRaw(-HALF + i * CELL, z); }
    this.occ = new Float32Array(hm);
    G.U.uNoise.value = makeNoiseTexture(256);
    this._buildControl();
    this._buildMaterial();
    this._buildMeshes(scene);
    this._buildScorch();
    this._buildFarShadow();
  },

  // ---- control map: R = trampled mud, G = road, B = forest floor, A = camp/packed earth ----
  roads: [],
  _buildControl() {
    const S = 1024, data = new Uint8Array(S * S * 4);
    const C = L.CASTLE, V = L.VILLAGE;
    const bridgeX = riverX(V.z + 50);
    // polylines: village -> field -> castle gate (switchback up the crag), bridge -> far hill
    const roads = this.roads = [
      [[bridgeX + 30, V.z + 50], [V.x + 40, V.z + 40], [V.x - 60, V.z + 60], [300, -330], [170, -160], [40, -40], [-110, 10], [-200, 60], [-262, 95], [-300, 60], [-318, 14], [-340, 0], [C.x + 60, 0]],
      [[bridgeX + 30, V.z + 50], [bridgeX + 140, V.z + 120], [860, -200], [960, 60], [1040, 200], [1110, 246]],
      [[170, -160], [260, 40], [330, 260], [380, 560], [420, 900], [520, 1500]],
    ];
    const segDist = (px, pz, a, b) => { const vx = b[0] - a[0], vz = b[1] - a[1]; const t = clamp(((px - a[0]) * vx + (pz - a[1]) * vz) / (vx * vx + vz * vz), 0, 1); return Math.hypot(px - a[0] - vx * t, pz - a[1] - vz * t); };
    this.roadDist = (x, z) => { let d = 1e9; for (const r of roads) for (let i = 0; i < r.length - 1; i++) d = Math.min(d, segDist(x, z, r[i], r[i + 1])); return d; };
    for (let j = 0; j < S; j++) for (let i = 0; i < S; i++) {
      const x = (i + 0.5) / S * 4096 - 2048, z = (j + 0.5) / S * 4096 - 2048; const k = (j * S + i) * 4;
      const fe = Math.hypot((x - L.FIELD.x) / L.FIELD.rx, (z - L.FIELD.z) / L.FIELD.rz);
      const n = fbm(x * 0.01, z * 0.01, 3) * 0.5 + 0.5;
      let mud = smooth(0.95, 0.35, fe) * (0.16 + 0.5 * smooth(0.42, 0.75, n));
      // ground churned where the army stands, drills and camps
      for (const [bx, bz, br] of TRAMPLE) { const d = Math.hypot(x - bx, z - bz); if (d < br * 1.6) mud = Math.max(mud, smooth(br * 1.5, br * 0.55, d + (n - 0.5) * 22) * 0.95); }
      const dcs = Math.hypot(x - C.x, z - C.z); mud = Math.max(mud, smooth(170, 100, dcs) * 0.8);
      const dv = Math.hypot(x - V.x, z - V.z); mud = Math.max(mud, smooth(170, 60, dv) * 0.6 * n);
      const dp = Math.hypot(x - L.PAD.x, z - L.PAD.z); mud = Math.max(mud, smooth(60, 30, dp) * 0.7);
      const rd = this.roadDist(x, z);
      const road = smooth(5.5, 2.5, rd + (n - 0.5) * 2.5);
      const fd = forestDensity(x, z);
      // farmland mask: gentle open ground away from the battlefield, the castle crag and the river bed
      let farm = 0;
      if (fd < 0.3 && Math.abs(x) < 1950 && Math.abs(z) < 1950) {
        const e = 6, sl = Math.hypot(this.height(x + e, z) - this.height(x - e, z), this.height(x, z + e) - this.height(x, z - e)) / (2 * e);
        const big = fbm(x * 0.0016 + 9, z * 0.0016 - 4, 3) * 0.5 + 0.5;
        farm = smooth(0.2, 0.09, sl) * smooth(1.12, 1.3, fe) * smooth(0.3, 0.05, fd) * smooth(250, 330, dcs) * smooth(70, 110, dp) * smooth(34, 60, Math.abs(x - riverX(z))) * smooth(1900, 1500, Math.hypot(x, z)) * smooth(0.28, 0.4, big) * smooth(16.5, 19, this.height(x, z));
      }
      data[k] = mud * 255; data[k + 1] = road * 255; data[k + 2] = fd * 255; data[k + 3] = farm * 255;
    }
    const t = this.ctlTex = new THREE.DataTexture(data, S, S, THREE.RGBAFormat);
    t.minFilter = THREE.LinearMipmapLinearFilter; t.magFilter = THREE.LinearFilter; t.generateMipmaps = true; t.needsUpdate = true;
  },

  _buildMaterial() {
    const mat = this.material = new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 1, metalness: 0 });
    const gr = assets.ground;
    patchMaterial(mat, 'terrain', sh => {
      sh.vertexShader = sh.vertexShader.replace('#include <common>', '#include <common>\nvarying vec3 vWp; varying vec3 vWn;')
        .replace('#include <begin_vertex>', '#include <begin_vertex>\n vWp = (modelMatrix * vec4(transformed, 1.0)).xyz; vWn = normalize(mat3(modelMatrix) * normal);');
      sh.fragmentShader = sh.fragmentShader.replace('#include <common>', /* glsl */`#include <common>
        varying vec3 vWp; varying vec3 vWn;
        uniform sampler2D uNoise; uniform sampler2D uCtl; uniform sampler2D uScorch; uniform vec4 uScorchP; uniform float uNight;
        uniform sampler2DArray uGA; uniform sampler2DArray uGB; uniform vec3 uGMean[${gr.n}];
        float swRough; vec3 swEmis; vec3 swNrmP;
        // photoscanned ground layers: A = albedo + height, B = normal.xy + roughness + AO
        struct SwS { vec3 c; vec3 n; float r; float h; };
        vec2 swP, swDx, swDy; vec3 swD3x, swD3y; float swFar;
        SwS swPack(vec4 a, vec4 b, vec3 nw, int L, vec3 tgt, float tk) {
          SwS o; o.c = mix(a.rgb, a.rgb / uGMean[L] * tgt, tk) * mix(1.0, b.a, 0.65); o.n = nw; o.r = b.b; o.h = a.a; return o; }
        // planar (xz) sample at two tile scales, cross-faded by distance to hide repetition
        SwS swSamp(int L, float s1, float s2, vec3 tgt, float tk) {
          vec4 a = vec4(0.0), b = vec4(0.0); float fl = float(L);
          if (swFar < 0.995) { vec2 u = swP * s1; a = textureGrad(uGA, vec3(u, fl), swDx * s1, swDy * s1); b = textureGrad(uGB, vec3(u, fl), swDx * s1, swDy * s1); }
          if (swFar > 0.005) { vec2 u = swP * s2 + 0.31; vec4 a2 = textureGrad(uGA, vec3(u, fl), swDx * s2, swDy * s2), b2 = textureGrad(uGB, vec3(u, fl), swDx * s2, swDy * s2);
            if (swFar < 0.995) { a = mix(a, a2, swFar); b = mix(b, b2, swFar); } else { a = a2; b = b2; } }
          vec2 n = b.rg * 2.0 - 1.0; return swPack(a, b, vec3(n.x, 0.0, -n.y), L, tgt, tk); }
        // triplanar sample (cliffs)
        SwS swTri(int L, vec3 wp, vec3 wn, float s, vec3 tgt, float tk) {
          vec3 w = abs(wn); w = w * w; w = w * w; w /= (w.x + w.y + w.z); float fl = float(L);
          vec4 a = vec4(0.0), b = vec4(0.0); vec3 nn = vec3(0.0); float ws = 0.0;
          if (w.y > 0.03) { vec4 A = textureGrad(uGA, vec3(wp.xz * s, fl), swD3x.xz * s, swD3y.xz * s), B = textureGrad(uGB, vec3(wp.xz * s, fl), swD3x.xz * s, swD3y.xz * s);
            a += A * w.y; b += B * w.y; ws += w.y; vec2 n = B.rg * 2.0 - 1.0; nn += vec3(n.x, 0.0, -n.y) * w.y; }
          if (w.x > 0.03) { vec2 u = vec2(wp.z, -wp.y) * s; vec4 A = textureGrad(uGA, vec3(u, fl), vec2(swD3x.z, -swD3x.y) * s, vec2(swD3y.z, -swD3y.y) * s), B = textureGrad(uGB, vec3(u, fl), vec2(swD3x.z, -swD3x.y) * s, vec2(swD3y.z, -swD3y.y) * s);
            a += A * w.x; b += B * w.x; ws += w.x; vec2 n = B.rg * 2.0 - 1.0; nn += vec3(0.0, n.y, n.x) * w.x; }
          if (w.z > 0.03) { vec2 u = vec2(wp.x, -wp.y) * s; vec4 A = textureGrad(uGA, vec3(u, fl), vec2(swD3x.x, -swD3x.y) * s, vec2(swD3y.x, -swD3y.y) * s), B = textureGrad(uGB, vec3(u, fl), vec2(swD3x.x, -swD3x.y) * s, vec2(swD3y.x, -swD3y.y) * s);
            a += A * w.z; b += B * w.z; ws += w.z; vec2 n = B.rg * 2.0 - 1.0; nn += vec3(n.x, n.y, 0.0) * w.z; }
          ws = 1.0 / max(ws, 1e-3); return swPack(a * ws, b * ws, nn * ws, L, tgt, tk); }
        void swMix(inout SwS a, SwS b, float m) { a.c = mix(a.c, b.c, m); a.n = mix(a.n, b.n, m); a.r = mix(a.r, b.r, m); a.h = mix(a.h, b.h, m); }
        // height-aware mask: the taller material wins inside the transition band
        float swHB(float m, float dh) { return smoothstep(0.3, 0.7, m + dh * 1.1 * (1.0 - abs(2.0 * m - 1.0))); }`)
        .replace('#include <map_fragment>', /* glsl */`
        {
          vec3 wp = vWp; vec3 wn = normalize(vWn);
          float camD = length(wp - cameraPosition);
          swD3x = dFdx(wp); swD3y = dFdy(wp);
          float n1 = texture2D(uNoise, wp.xz * 0.0019).r;
          float n2 = texture2D(uNoise, wp.xz * 0.013 + n1 * 0.3).g;
          float n3 = texture2D(uNoise, wp.xz * 0.11).b;
          float n4 = texture2D(uNoise, wp.xz * 0.71).a;
          vec2 warp = (vec2(texture2D(uNoise, wp.xz * 0.0017).r, texture2D(uNoise, wp.zx * 0.0017 + 0.37).r) - 0.5) * 9.0; // slow domain warp breaks the tile grid
          swP = wp.xz + warp; swDx = swD3x.xz; swDy = swD3y.xz; swFar = smoothstep(30.0, 190.0, camD);
          float macro = smoothstep(140.0, 620.0, camD);
          vec4 ctl = texture2D(uCtl, wp.xz / 4096.0 + 0.5);
          if (abs(wp.x) > 2040.0 || abs(wp.z) > 2040.0) ctl = vec4(0.0, 0.0, 0.25, 0.0);
          float slope = 1.0 - wn.y;
          vec3 gLush = vec3(0.115, 0.17, 0.035), gDry = vec3(0.34, 0.27, 0.085), gDark = vec3(0.05, 0.085, 0.022);
          float dry = smoothstep(0.38, 0.68, n1 * 0.55 + n2 * 0.45) * (1.0 - 0.6 * smoothstep(120.0, 330.0, wp.y + n2 * 60.0)); // upland turf stays greener
          float cragK = smoothstep(300.0, 215.0, length(wp.xz - vec2(${L.CASTLE.x.toFixed(1)}, ${L.CASTLE.z.toFixed(1)}))) * smoothstep(0.035, 0.11, slope); // the castle stands on bare rock, not a lawn
          float rockM = smoothstep(0.20, 0.40, slope + (n3 - 0.5) * 0.18 + smoothstep(230.0, 560.0, wp.y + n1 * 160.0) * 0.3 + cragK * (0.16 + 0.12 * n2));
          // ---- grass: meadow, straw-dry and lush patches ----
          SwS g = swSamp(1, 0.43, 0.061, mix(gLush, gDry, 0.3), 0.72);
          if (dry > 0.004) { SwS d = swSamp(2, 0.37, 0.052, gDry, 0.72); swMix(g, d, swHB(dry, d.h - g.h)); }
          float lushM = smoothstep(0.52, 0.78, n2) * 0.7 * (1.0 - dry);
          if (lushM > 0.004) { SwS d = swSamp(0, 0.47, 0.067, gDark * 1.5, 0.72); swMix(g, d, swHB(lushM, d.h - g.h)); }
          // aerial-scale variation (a 60 m scan) so the field never reads as one flat carpet
          { vec2 u = swP / 61.0; vec3 ae = textureGrad(uGA, vec3(u, 7.0), swDx / 61.0, swDy / 61.0).rgb / uGMean[7];
            ae = clamp(mix(vec3(dot(ae, vec3(0.3, 0.55, 0.15))), ae, 0.3), 0.5, 1.45);
            g.c *= mix(vec3(1.0), ae, mix(0.5, 0.95, macro)) * (0.86 + 0.28 * n3 * (1.0 - macro)); }
          // ---- rock: aerial crag scan for structure, close-up rock face for detail ----
          if (rockM > 0.004) {
            vec3 rt = mix(vec3(0.21, 0.19, 0.17), vec3(0.40, 0.36, 0.31), n2);
            SwS r = swTri(8, wp, wn, 1.0 / 74.0, rt, 0.55);
            if (camD < 520.0) { SwS d = swTri(4, wp, wn, 1.0 / 6.5, vec3(1.0), 1.0); float k = smoothstep(520.0, 260.0, camD); r.c *= mix(vec3(1.0), d.c, k); r.n += d.n * k; r.r = mix(r.r, d.r, k * 0.6); r.h = mix(r.h, d.h, k * 0.5); }
            float strata = texture2D(uNoise, vec2(wp.y * 0.035 + n2 * 0.4, n1)).g; r.c *= 0.8 + 0.4 * strata; r.n *= 1.5;
            swMix(g, r, swHB(rockM, r.h - g.h));
          }
          // ---- farmland: strip fields (stubble, plough, green crop) divided by grassy balks ----
          float farm = ctl.a * (1.0 - rockM);
          if (farm > 0.01) {
            vec2 fp = vec2(wp.x * 0.94 + wp.z * 0.342, wp.z * 0.94 - wp.x * 0.342) + warp * 0.6;
            vec2 fs = vec2(34.0, 126.0); vec2 cell = floor(fp / fs); vec2 fq = fp - cell * fs;
            vec4 hh = textureLod(uNoise, (cell + 0.5) / 256.0, 0.0);
            float fw = max(length(swD3x.xz), length(swD3y.xz));
            float edge = min(min(fq.x, fs.x - fq.x), min(fq.y, fs.y - fq.y));
            float inner = smoothstep(1.3 - fw, 2.4 + fw, edge + (n3 - 0.5) * 1.2) * smoothstep(0.25, 0.6, farm + (n2 - 0.5) * 0.3);
            float kind = fract(hh.r * 7.31 + hh.g * 3.17);
            // furrows run along the strip; fade out before they alias
            float fur = sin(fq.x * 3.9 + n3 * 1.5) * smoothstep(0.55, 0.16, fw);
            if (kind > 0.34 && inner > 0.004) {
              if (kind < 0.58) { SwS d = swSamp(2, 0.41, 0.057, vec3(0.42, 0.33, 0.11) * (0.85 + 0.3 * hh.b), 0.8); d.c *= 1.0 + 0.10 * fur; swMix(g, d, inner * 0.92); }
              else if (kind < 0.82) { SwS d = swSamp(3, 0.36, 0.055, vec3(0.20, 0.135, 0.085) * (0.8 + 0.4 * hh.b), 0.8); d.c *= 1.0 + 0.24 * fur; d.n.x += fur * 0.5 * 0.94; d.n.z += fur * 0.5 * 0.342; swMix(g, d, inner * 0.95); }
              else { SwS d = swSamp(0, 0.45, 0.063, vec3(0.105, 0.19, 0.04) * (0.85 + 0.3 * hh.b), 0.8); d.c *= 1.0 + 0.16 * fur; swMix(g, d, inner * 0.9); }
            }
            g.c = mix(g.c, g.c * vec3(0.55, 0.7, 0.45), (1.0 - inner) * smoothstep(0.3, 0.6, farm) * 0.6); // balks / hedge banks
          }
          // alpine tint
          g.c = mix(g.c, vec3(0.30, 0.28, 0.24) * (0.6 + 0.8 * n3), smoothstep(330.0, 600.0, wp.y + n2 * 120.0) * 0.45);
          // ---- forest floor (leaf litter) ----
          float forM = ctl.b * 0.85 * (1.0 - rockM);
          if (forM > 0.004) { SwS d = swSamp(5, 0.31, 0.047, vec3(0.05, 0.057, 0.026), 0.85); swMix(g, d, swHB(forM, d.h - g.h));
            // from far off the gaps between crowns close up: let the floor take the canopy's colour so woodland reads as a mass
            float cf = smoothstep(200.0, 650.0, camD) * smoothstep(0.25, 0.7, ctl.b); g.c = mix(g.c, vec3(0.032, 0.055, 0.02) * (0.65 + 0.7 * n3) * (0.8 + 0.4 * n2), cf * 0.85); g.n *= 1.0 - cf; }
          // ---- trampled mud ----
          float mudM = smoothstep(0.25, 0.6, ctl.r * 0.75 + (n3 - 0.5) * 0.5 + ctl.r * (n2 - 0.3) * 0.6) * (1.0 - rockM);
          if (mudM > 0.004) { SwS d = swSamp(3, 0.39, 0.058, mix(vec3(0.16, 0.115, 0.07), vec3(0.24, 0.185, 0.115), n3), 0.7); swMix(g, d, swHB(mudM * 0.94, (d.h - g.h) * 0.8)); }
          // ---- road (stony track) ----
          float ruts = smoothstep(0.35, 0.65, ctl.g) * (1.0 - 0.55 * rockM);
          if (ruts > 0.004) { SwS d = swSamp(6, 0.33, 0.071, mix(vec3(0.27, 0.215, 0.14), vec3(0.34, 0.28, 0.19), n3), 0.7); swMix(g, d, swHB(ruts, (d.h - g.h) * 0.6)); }
          // ---- river banks: wet shingle ----
          float wet = smoothstep(${(L.WATER_Y + 1.6).toFixed(1)}, ${(L.WATER_Y + 0.15).toFixed(2)}, wp.y + (n3 - 0.5) * 0.8);
          if (wet > 0.004) { SwS d = swSamp(6, 0.27, 0.063, vec3(0.2, 0.17, 0.125), 0.7); swMix(g, d, wet); }
          vec3 col = g.c;
          col *= mix(1.0, 0.35, smoothstep(${(L.WATER_Y).toFixed(1)}, ${(L.WATER_Y - 1.8).toFixed(1)}, wp.y));
          swRough = 0.76 + 0.24 * g.r; swRough = mix(swRough, 0.32, wet * 0.9);
          // scorch + embers
          vec2 suv = (wp.xz - uScorchP.xy) * uScorchP.z + 0.5;
          vec4 sc = (suv.x > 0.0 && suv.x < 1.0 && suv.y > 0.0 && suv.y < 1.0) ? texture2D(uScorch, suv) : vec4(0.0);
          float burn = sc.r * (0.75 + 0.5 * n3);
          col = mix(col, vec3(0.012, 0.010, 0.009) * (0.5 + g.h), clamp(burn, 0.0, 0.94));
          col = mix(col, vec3(0.2, 0.19, 0.18) * n4, clamp(burn - 0.7, 0.0, 1.0) * 0.6 * n4); // ash flecks
          swEmis = vec3(1.0, 0.28, 0.04) * sc.g * sc.g * (0.06 + 2.6 * smoothstep(0.52, 0.86, n4 * 0.6 + n3 * 0.5) * (0.4 + 0.6 * g.h)) * 3.0; // scattered embers in the cracks, not a glowing disc
          swNrmP = g.n * 1.15;
          diffuseColor.rgb = col;
        }`)
        .replace('#include <roughnessmap_fragment>', 'float roughnessFactor = swRough;')
        .replace('#include <normal_fragment_maps>', 'normal = normalize(normal + (viewMatrix * vec4(swNrmP, 0.0)).xyz);')
        .replace('#include <emissivemap_fragment>', 'totalEmissiveRadiance += swEmis;');
    }, { uCtl: { value: this.ctlTex }, uGA: { value: gr.A }, uGB: { value: gr.B }, uGMean: { value: gr.mean } });
  },

  _buildMeshes(scene) {
    const hm = this.hm; const group = this.group = new THREE.Group(); group.name = 'terrain';
    // vertex normals from grid
    const nrm = (i, j, out, o) => {
      const i0 = Math.max(i - 1, 0), i1 = Math.min(i + 1, N - 1), j0 = Math.max(j - 1, 0), j1 = Math.min(j + 1, N - 1);
      const hx = (hm[j * N + i1] - hm[j * N + i0]) / ((i1 - i0) * CELL), hz = (hm[j1 * N + i] - hm[j0 * N + i]) / ((j1 - j0) * CELL);
      const l = 1 / Math.hypot(hx, 1, hz); out[o] = -hx * l; out[o + 1] = l; out[o + 2] = -hz * l;
    };
    const CH = 100; // cells per chunk
    for (let cj = 0; cj < (N - 1) / CH; cj++) for (let ci = 0; ci < (N - 1) / CH; ci++) {
      const vn = CH + 1; const pos = new Float32Array(vn * vn * 3), nor = new Float32Array(vn * vn * 3); const idx = new Uint32Array(CH * CH * 6);
      for (let j = 0; j < vn; j++) for (let i = 0; i < vn; i++) {
        const gi = ci * CH + i, gj = cj * CH + j, o = (j * vn + i) * 3;
        pos[o] = -HALF + gi * CELL; pos[o + 1] = hm[gj * N + gi]; pos[o + 2] = -HALF + gj * CELL; nrm(gi, gj, nor, o);
      }
      let k = 0; for (let j = 0; j < CH; j++) for (let i = 0; i < CH; i++) { const a = j * vn + i, b = a + 1, c = a + vn, d = c + 1; idx[k++] = a; idx[k++] = c; idx[k++] = b; idx[k++] = b; idx[k++] = c; idx[k++] = d; }
      const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.BufferAttribute(pos, 3)); g.setAttribute('normal', new THREE.BufferAttribute(nor, 3)); g.setIndex(new THREE.BufferAttribute(idx, 1));
      g.computeBoundingSphere(); g.computeBoundingBox();
      const m = new THREE.Mesh(g, this.material); m.receiveShadow = true; m.matrixAutoUpdate = false; group.add(m);
    }
    // outer ring: polar-ish warped grid from the heightmap edge out to ~9 km
    {
      const RN = 96, SEG = 4 * 80; // radial steps, perimeter segments (matches every 10th edge vertex)
      const pos = [], nor = [], idx = [];
      const edge = s => { // perimeter param 0..SEG -> point on square edge
        const side = Math.floor(s / 80) % 4, t = (s % 80) / 80 * 2 - 1;
        return side === 0 ? [t * HALF, -HALF] : side === 1 ? [HALF, t * HALF] : side === 2 ? [-t * HALF, HALF] : [-HALF, -t * HALF];
      };
      for (let r = 0; r <= RN; r++) {
        const f = r / RN; const scale = 1 + f * 0.9 + f * f * f * 2.8; // 1 .. 4.7
        for (let s = 0; s < SEG; s++) {
          const [ex, ez] = edge(s); const x = ex * scale, z = ez * scale;
          let y = r === 0 ? this.height(ex, ez) - 0.02 : heightRaw(x, z);
          pos.push(x, y, z);
          const e = 12; const hx = heightRaw(x + e, z) - heightRaw(x - e, z), hz = heightRaw(x, z + e) - heightRaw(x, z - e); const l = 1 / Math.hypot(hx, 2 * e, hz);
          nor.push(-hx * l, 2 * e * l, -hz * l);
        }
      }
      for (let r = 0; r < RN; r++) for (let s = 0; s < SEG; s++) { const a = r * SEG + s, b = r * SEG + (s + 1) % SEG, c = a + SEG, d = b + SEG; idx.push(a, b, c, b, d, c); }
      // skirt under the seam
      const base = pos.length / 3;
      for (let s = 0; s < SEG; s++) { const [ex, ez] = edge(s); pos.push(ex * 0.995, this.height(ex, ez) - 30, ez * 0.995); nor.push(0, 1, 0); }
      for (let s = 0; s < SEG; s++) { const a = s, b = (s + 1) % SEG, c = base + s, d = base + (s + 1) % SEG; idx.push(a, c, b, b, c, d); }
      const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3)); g.setAttribute('normal', new THREE.Float32BufferAttribute(nor, 3)); g.setIndex(idx);
      // the ring's cells are hundreds of metres wide: use normals of the triangles actually drawn (a 12 m finite difference at each
      // vertex is far too local and paints the mesh grid onto the mountains as lines of rock). Keep the seam row matching the heightmap.
      { g.computeVertexNormals(); const na = g.attributes.normal; for (let i = 0; i < SEG * 3; i++) na.array[i] = nor[i]; for (let i = base * 3; i < na.array.length; i += 3) { na.array[i] = 0; na.array[i + 1] = 1; na.array[i + 2] = 0; } na.needsUpdate = true; }
      const m = new THREE.Mesh(g, this.material); m.receiveShadow = false; m.frustumCulled = false; m.matrixAutoUpdate = false; group.add(m);
    }
    scene.add(group);
  },

  // ---- scorch map (R = burn, G = heat/embers) ----
  _buildScorch() {
    const S = 2048; const SIZE = 2048;
    const rt = this.scorchRT = new THREE.WebGLRenderTarget(S, S, { format: THREE.RGBAFormat, type: THREE.UnsignedByteType, depthBuffer: false, minFilter: THREE.LinearFilter, magFilter: THREE.LinearFilter });
    rt.texture.generateMipmaps = false;
    this.scorchCenter = { x: -80, z: 0 }; this.scorchSize = SIZE;
    G.U.uScorch.value = rt.texture; G.U.uScorchP.value.set(this.scorchCenter.x, this.scorchCenter.z, 1 / SIZE, 0);
    this.scScene = new THREE.Scene(); this.scCam = new THREE.OrthographicCamera(-SIZE / 2, SIZE / 2, SIZE / 2, -SIZE / 2, 0, 10); this.scCam.position.z = 5;
    const MAXS = 64;
    const geo = new THREE.InstancedBufferGeometry(); geo.copy(new THREE.PlaneGeometry(1, 1));
    this.scAttr = new THREE.InstancedBufferAttribute(new Float32Array(MAXS * 4), 4); this.scAttr.setUsage(THREE.DynamicDrawUsage);
    geo.setAttribute('iS', this.scAttr); geo.instanceCount = 0;
    const mat = new THREE.ShaderMaterial({
      uniforms: { uNoise: G.U.uNoise }, transparent: true, depthTest: false, depthWrite: false,
      blending: THREE.CustomBlending, blendEquation: THREE.MaxEquation, blendSrc: THREE.OneFactor, blendDst: THREE.OneFactor,
      vertexShader: `attribute vec4 iS; varying vec2 vUv; varying float vI; varying vec2 vW; void main(){ vUv = uv * 2.0 - 1.0; vI = iS.w; vec2 p = iS.xy + position.xy * iS.z * 2.0; vW = p; gl_Position = projectionMatrix * viewMatrix * vec4(p, 0.0, 1.0); }`,
      fragmentShader: `uniform sampler2D uNoise; varying vec2 vUv; varying float vI; varying vec2 vW; void main(){ float r = length(vUv); float a = atan(vUv.y, vUv.x);
        float n = texture2D(uNoise, vW * 0.05).r; float ray = texture2D(uNoise, vec2(a * 0.6, 0.3 + vI)).g;
        float e = 0.55 + 0.45 * ray + (n - 0.5) * 0.5; float b = smoothstep(e, e * 0.35, r); gl_FragColor = vec4(b * min(vI, 1.0), b * b * min(vI, 1.0), 0.0, 1.0); }`,
    });
    this.scMesh = new THREE.Mesh(geo, mat); this.scMesh.frustumCulled = false; this.scScene.add(this.scMesh);
    // cooling quad (subtract a little from G)
    const cool = new THREE.Mesh(new THREE.PlaneGeometry(SIZE, SIZE), new THREE.MeshBasicMaterial({ color: new THREE.Color(0, 1 / 255, 0), blending: THREE.CustomBlending, blendEquation: THREE.ReverseSubtractEquation, blendSrc: THREE.OneFactor, blendDst: THREE.OneFactor, depthTest: false, depthWrite: false, toneMapped: false }));
    cool.material.color.setRGB(0, 1.5 / 255, 0, THREE.LinearSRGBColorSpace);
    this.coolScene = new THREE.Scene(); this.coolScene.add(cool);
    this.scPending = []; this.coolT = 0;
    const r = G.renderer; r.setRenderTarget(rt); r.setClearColor(0x000000, 1); r.clear(); r.setRenderTarget(null);
  },
  // world-space burn mark; radius in metres, intensity 0..1
  scorch(x, z, radius, intensity = 1) { if (this.scPending.length < 64) this.scPending.push(x - this.scorchCenter.x, z - this.scorchCenter.z, radius, intensity); },
  clearScorch() { const r = G.renderer; r.setRenderTarget(this.scorchRT); r.setClearColor(0x000000, 1); r.clear(); r.setRenderTarget(null); this.scPending.length = 0; },

  // ---- far heightfield shadows ----
  _buildFarShadow() {
    this.occTex = new THREE.DataTexture(this.occ, N, N, THREE.RedFormat, THREE.FloatType);
    this.occTex.minFilter = this.occTex.magFilter = THREE.LinearFilter; this.occTex.needsUpdate = true;
    const rt = this.farRT = new THREE.WebGLRenderTarget(640, 640, { type: THREE.HalfFloatType, format: THREE.RGBAFormat, depthBuffer: false, minFilter: THREE.LinearFilter, magFilter: THREE.LinearFilter });
    G.U.uFarSh.value = rt.texture; G.U.uFarShP.value.set(0, 0, 1 / (2 * HALF), 1);
    this.farMat = new THREE.ShaderMaterial({
      uniforms: { uH: { value: this.occTex }, uSun: G.U.uSunDir }, depthTest: false, depthWrite: false,
      vertexShader: `varying vec2 vUv; void main(){ vUv = uv; gl_Position = vec4(position.xy, 0.0, 1.0); }`,
      fragmentShader: `precision highp float; uniform sampler2D uH; uniform vec3 uSun; varying vec2 vUv;
        float H(vec2 p){ vec2 uv = (p + ${HALF}.0) / ${2 * HALF}.0 * ${(N - 1)}.0 / ${N}.0 + 0.5 / ${N}.0; return texture2D(uH, uv).r; }
        void main(){ vec2 wp = (vUv - 0.5) * ${2 * HALF}.0; float tanE = max(uSun.y, 0.0) / max(length(uSun.xz), 1e-3); vec2 dir = normalize(uSun.xz);
          float horizon = -1e4; float od = 0.0; float s = 5.0;
          for (int i = 0; i < 80; i++) { vec2 p = wp + dir * s; float h = H(p) - s * tanE; if (h > horizon) { horizon = h; od = s; } s = s * 1.07 + 2.0; }
          gl_FragColor = vec4(horizon, 1.2 + od * 0.035, 0.0, 1.0); }`,
    });
    this.fsQuad = new THREE.Mesh(new THREE.PlaneGeometry(2, 2), this.farMat); this.fsQuad.frustumCulled = false;
    this.fsScene = new THREE.Scene(); this.fsScene.add(this.fsQuad); this.fsCam = new THREE.Camera();
    this.farDirty = true; this.farT = 0;
  },
  // raise occluder heights (structures) so they cast far shadows. footprint = circle
  stampOccluder(x, z, radius, topY) {
    const i0 = Math.max(0, Math.floor((x - radius + HALF) / CELL)), i1 = Math.min(N - 1, Math.ceil((x + radius + HALF) / CELL));
    const j0 = Math.max(0, Math.floor((z - radius + HALF) / CELL)), j1 = Math.min(N - 1, Math.ceil((z + radius + HALF) / CELL));
    for (let j = j0; j <= j1; j++) for (let i = i0; i <= i1; i++) { const dx = -HALF + i * CELL - x, dz = -HALF + j * CELL - z; if (dx * dx + dz * dz <= radius * radius + CELL * CELL * 0.3) { const k = j * N + i; if (this.occ[k] < topY) this.occ[k] = topY; } }
  },
  resetOccluders() { this.occ.set(this.hm); },
  commitOccluders() { this.occTex.needsUpdate = true; this.farDirty = true; },

  update(dt) {
    const r = G.renderer; const old = r.getRenderTarget(); const oldAuto = r.autoClear; r.autoClear = false;
    // scorch stamps
    if (this.scPending.length) {
      const n = this.scPending.length / 4; this.scAttr.array.set(this.scPending); this.scAttr.needsUpdate = true; this.scMesh.geometry.instanceCount = n; this.scPending.length = 0;
      r.setRenderTarget(this.scorchRT); r.render(this.scScene, this.scCam);
    }
    this.coolT += dt; if (this.coolT > 0.2) { this.coolT = 0; r.setRenderTarget(this.scorchRT); r.render(this.coolScene, this.scCam); }
    // far shadows
    this.farT += dt; if (this.farDirty || this.farT > 1.5) { this.farDirty = false; this.farT = 0; r.setRenderTarget(this.farRT); r.render(this.fsScene, this.fsCam); }
    r.setRenderTarget(old); r.autoClear = oldAuto;
  },
};

// trampled ground: [x, z, radius] — infantry blocks, archer lines, siege camp
const TRAMPLE = [[112, -84, 34], [118, 0, 34], [112, 84, 34], [46, -84, 34], [52, 0, 34], [46, 84, 34], [82, -178, 26], [82, 178, 26], [300, -330, 26], [250, 70, 26], [205, 0, 20], [-40, 0, 60], [-120, -90, 45], [-120, 100, 45]];

// ---------- forest density (0..1) — also used by scenery placement ----------
export function forestDensity(x, z) {
  const r = Math.hypot(x, z);
  const n = fbm(x * 0.0035 + 40, z * 0.0035 - 12, 4) * 0.5 + 0.5;
  let d = smooth(0.42, 0.62, n + smooth(900, 2200, r) * 0.25);
  // forest edges south and north of the field
  d = Math.max(d, smooth(470, 560, Math.abs(z) + fbm(x * 0.01, z * 0.01, 2) * 60) * smooth(-260, -120, x) * 0.95);
  const fe = Math.hypot((x - L.FIELD.x) / (L.FIELD.rx + 90), (z - L.FIELD.z) / (L.FIELD.rz + 70)); d *= smooth(0.95, 1.12, fe);
  d *= smooth(200, 290, Math.hypot(x - L.CASTLE.x, z - L.CASTLE.z));
  d *= smooth(150, 230, Math.hypot(x - L.VILLAGE.x, z - L.VILLAGE.z));
  d *= smooth(60, 130, Math.hypot(x - L.PAD.x, z - L.PAD.z));
  d *= smooth(30, 70, Math.abs(x - riverX(z)));
  return d;
}
