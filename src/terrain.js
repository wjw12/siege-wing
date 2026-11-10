// Siege Wing — valley terrain: height function, heightmap, mesh, material, scorch map, far sun shadows
import * as THREE from 'three';
import { G, fbm, ridged, vnoise, smooth, lerp, clamp, wrapPi, patchMaterial, makeNoiseTexture } from './core.js';

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
      let mud = smooth(0.95, 0.35, fe) * (0.45 + 0.55 * n);
      const dcs = Math.hypot(x - C.x, z - C.z); mud = Math.max(mud, smooth(170, 100, dcs) * 0.8);
      const dv = Math.hypot(x - V.x, z - V.z); mud = Math.max(mud, smooth(170, 60, dv) * 0.6 * n);
      const dp = Math.hypot(x - L.PAD.x, z - L.PAD.z); mud = Math.max(mud, smooth(60, 30, dp) * 0.7);
      const rd = this.roadDist(x, z);
      const road = smooth(5.5, 2.5, rd + (n - 0.5) * 2.5);
      data[k] = mud * 255; data[k + 1] = road * 255; data[k + 2] = forestDensity(x, z) * 255; data[k + 3] = 255;
    }
    const t = this.ctlTex = new THREE.DataTexture(data, S, S, THREE.RGBAFormat);
    t.minFilter = THREE.LinearMipmapLinearFilter; t.magFilter = THREE.LinearFilter; t.generateMipmaps = true; t.needsUpdate = true;
  },

  _buildMaterial() {
    const mat = this.material = new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 1, metalness: 0 });
    patchMaterial(mat, 'terrain', sh => {
      sh.vertexShader = sh.vertexShader.replace('#include <common>', '#include <common>\nvarying vec3 vWp; varying vec3 vWn;')
        .replace('#include <begin_vertex>', '#include <begin_vertex>\n vWp = (modelMatrix * vec4(transformed, 1.0)).xyz; vWn = normalize(mat3(modelMatrix) * normal);');
      sh.fragmentShader = sh.fragmentShader.replace('#include <common>', `#include <common>
        varying vec3 vWp; varying vec3 vWn;
        uniform sampler2D uNoise; uniform sampler2D uCtl; uniform sampler2D uScorch; uniform vec4 uScorchP; uniform float uNight;
        float swRough; vec3 swEmis; vec3 swNrmP;`)
        .replace('#include <map_fragment>', /* glsl */`
        {
          vec3 wp = vWp; vec3 wn = normalize(vWn);
          float camD = length(wp - cameraPosition);
          float n1 = texture2D(uNoise, wp.xz * 0.0019).r;
          float n2 = texture2D(uNoise, wp.xz * 0.013 + n1 * 0.3).g;
          float n3 = texture2D(uNoise, wp.xz * 0.11).b;
          float n4 = texture2D(uNoise, wp.xz * 0.71).a;
          float n3x = texture2D(uNoise, wp.xz * 0.11 + vec2(0.012, 0.0)).b, n3z = texture2D(uNoise, wp.xz * 0.11 + vec2(0.0, 0.012)).b;
          float n4x = texture2D(uNoise, wp.xz * 0.71 + vec2(0.012, 0.0)).a, n4z = texture2D(uNoise, wp.xz * 0.71 + vec2(0.0, 0.012)).a;
          float detF = smoothstep(260.0, 30.0, camD);
          vec4 ctl = texture2D(uCtl, wp.xz / 4096.0 + 0.5);
          if (abs(wp.x) > 2040.0 || abs(wp.z) > 2040.0) ctl = vec4(0.0, 0.0, 0.25, 1.0);
          float slope = 1.0 - wn.y;
          // grass
          vec3 gLush = vec3(0.115, 0.17, 0.035), gDry = vec3(0.34, 0.27, 0.085), gDark = vec3(0.05, 0.085, 0.022);
          float dry = smoothstep(0.38, 0.68, n1 * 0.55 + n2 * 0.45);
          vec3 grass = mix(gLush, gDry, dry);
          grass = mix(grass, gDark, smoothstep(0.52, 0.78, n2) * 0.55 * (1.0 - dry));
          grass *= 0.7 + 0.6 * mix(0.5, n3, 0.7) + (n4 - 0.5) * 0.35 * detF;
          // rock
          vec3 rock = mix(vec3(0.21, 0.19, 0.17), vec3(0.40, 0.36, 0.31), n2);
          rock *= 0.55 + 0.9 * n3 * mix(1.0, n4 + 0.5, detF);
          float strata = texture2D(uNoise, vec2(wp.y * 0.035 + n2 * 0.4, n1)).g; rock *= 0.8 + 0.4 * strata;
          float rockM = smoothstep(0.20, 0.40, slope + (n3 - 0.5) * 0.18 + smoothstep(260.0, 520.0, wp.y) * 0.2);
          vec3 col = mix(grass, rock, rockM);
          // alpine tint
          col = mix(col, vec3(0.30, 0.28, 0.24) * (0.6 + 0.8 * n3), smoothstep(330.0, 600.0, wp.y + n2 * 120.0) * 0.6);
          // forest floor
          col = mix(col, vec3(0.045, 0.055, 0.02) * (0.6 + 0.8 * n3), ctl.b * 0.85 * (1.0 - rockM));
          // trampled mud
          float mudM = smoothstep(0.25, 0.6, ctl.r * 0.75 + (n3 - 0.5) * 0.5 + ctl.r * (n2 - 0.3) * 0.6) * (1.0 - rockM);
          vec3 mud = mix(vec3(0.16, 0.115, 0.07), vec3(0.24, 0.185, 0.115), n3) * (0.75 + 0.5 * n4);
          col = mix(col, mud, mudM * 0.92);
          // road
          vec3 road = mix(vec3(0.27, 0.215, 0.14), vec3(0.34, 0.28, 0.19), n4) * (0.8 + 0.4 * n3);
          float ruts = smoothstep(0.35, 0.65, ctl.g) ;
          col = mix(col, road, ruts);
          // river banks
          float wet = smoothstep(${(L.WATER_Y + 1.6).toFixed(1)}, ${(L.WATER_Y + 0.15).toFixed(2)}, wp.y + (n3 - 0.5) * 0.8);
          col = mix(col, vec3(0.25, 0.21, 0.15) * (0.6 + 0.7 * n4), wet);
          col *= mix(1.0, 0.35, smoothstep(${(L.WATER_Y).toFixed(1)}, ${(L.WATER_Y - 1.8).toFixed(1)}, wp.y));
          swRough = mix(0.96, 0.82, rockM); swRough = mix(swRough, 0.9, mudM); swRough = mix(swRough, 0.35, wet);
          // scorch + embers
          vec2 suv = (wp.xz - uScorchP.xy) * uScorchP.z + 0.5;
          vec4 sc = (suv.x > 0.0 && suv.x < 1.0 && suv.y > 0.0 && suv.y < 1.0) ? texture2D(uScorch, suv) : vec4(0.0);
          float burn = sc.r * (0.75 + 0.5 * n3);
          col = mix(col, vec3(0.012, 0.010, 0.009), clamp(burn, 0.0, 0.94));
          col = mix(col, vec3(0.2, 0.19, 0.18) * n4, clamp(burn - 0.7, 0.0, 1.0) * 0.6 * n4); // ash flecks
          swEmis = vec3(1.0, 0.28, 0.04) * sc.g * sc.g * (0.4 + 2.2 * smoothstep(0.45, 0.8, n4 * 0.6 + n3 * 0.5)) * 5.0;
          swNrmP = vec3(n3x - n3, 0.0, n3z - n3) * (0.7 + rockM * 3.5) + vec3(n4x - n4, 0.0, n4z - n4) * 2.2 * detF * (0.35 + rockM + mudM);
          diffuseColor.rgb = col;
        }`)
        .replace('#include <roughnessmap_fragment>', 'float roughnessFactor = swRough;')
        .replace('#include <normal_fragment_maps>', 'normal = normalize(normal - (viewMatrix * vec4(swNrmP, 0.0)).xyz);')
        .replace('#include <emissivemap_fragment>', 'totalEmissiveRadiance += swEmis;');
    }, { uCtl: { value: this.ctlTex } });
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
