// Siege Wing — core: shared context, math, noise, global shader patches (fog, far shadows)
import * as THREE from 'three';

export const V3 = THREE.Vector3;
export const clamp = (x, a, b) => x < a ? a : x > b ? b : x;
export const lerp = (a, b, t) => a + (b - a) * t;
export const sat = x => x < 0 ? 0 : x > 1 ? 1 : x;
export const smooth = (a, b, x) => { const t = sat((x - a) / (b - a)); return t * t * (3 - 2 * t); };
export const damp = (a, b, lambda, dt) => lerp(a, b, 1 - Math.exp(-lambda * dt));
export const TAU = Math.PI * 2;
export const DEG = Math.PI / 180;
export const wrapPi = a => { a = (a + Math.PI) % TAU; if (a < 0) a += TAU; return a - Math.PI; };

export function mulberry32(seed) {
  let a = seed >>> 0;
  return () => { a |= 0; a = a + 0x6D2B79F5 | 0; let t = Math.imul(a ^ a >>> 15, 1 | a); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; };
}
export const rand = mulberry32(1337);
export const rnd = (a = 1, b) => b === undefined ? Math.random() * a : a + Math.random() * (b - a);
export const rndS = (a = 1) => (Math.random() * 2 - 1) * a;

// ---------- value noise / fbm (CPU, deterministic) ----------
const P = new Uint8Array(512);
{ const r = mulberry32(90210); const p = Array.from({ length: 256 }, (_, i) => i); for (let i = 255; i > 0; i--) { const j = (r() * (i + 1)) | 0; [p[i], p[j]] = [p[j], p[i]]; } for (let i = 0; i < 512; i++) P[i] = p[i & 255]; }
const GR = new Float32Array(512); { const r = mulberry32(4242); for (let i = 0; i < 512; i++) GR[i] = r() * 2 - 1; }
export function vnoise(x, y) { // -1..1 gradient-ish value noise
  const xi = Math.floor(x), yi = Math.floor(y); const xf = x - xi, yf = y - yi;
  const u = xf * xf * xf * (xf * (xf * 6 - 15) + 10), v = yf * yf * yf * (yf * (yf * 6 - 15) + 10);
  const X = xi & 255, Y = yi & 255;
  const a = GR[P[X + P[Y]]], b = GR[P[X + 1 + P[Y]]], c = GR[P[X + P[Y + 1]]], d = GR[P[X + 1 + P[Y + 1]]];
  return a + (b - a) * u + (c - a) * v + (a - b - c + d) * u * v;
}
export function fbm(x, y, oct = 5, lac = 2.03, gain = 0.5) {
  let s = 0, a = 0.5, n = 0;
  for (let i = 0; i < oct; i++) { s += a * vnoise(x, y); n += a; x = x * lac + 17.3; y = y * lac - 9.1; a *= gain; }
  return s / n;
}
export function ridged(x, y, oct = 5) {
  let s = 0, a = 0.5, n = 0;
  for (let i = 0; i < oct; i++) { const v = 1 - Math.abs(vnoise(x, y)); s += a * v * v; n += a; x = x * 2.07 + 31.7; y = y * 2.07 + 11.9; a *= 0.5; }
  return s / n;
}

// ---------- shared context ----------
export const G = {
  renderer: null, scene: null, camera: null,
  time: 0, dt: 0, frame: 0, realTime: 0,
  quality: 1,
  settings: null,
  // shared uniforms (same object references in every material)
  U: {
    uTime: { value: 0 },
    uSunDir: { value: new V3(-0.9, 0.2, 0.1).normalize() },
    uSunCol: { value: new THREE.Color(1, 0.8, 0.6) },
    uFogColA: { value: new THREE.Color(1.0, 0.7, 0.4) },   // toward sun
    uFogColB: { value: new THREE.Color(0.45, 0.5, 0.6) },  // away from sun
    uFogP: { value: new THREE.Vector4(0.00035, 0.012, 20, 6) }, // density, height falloff, base height, sun exponent
    uFarSh: { value: null },
    uFarShP: { value: new THREE.Vector4(0, 0, 1 / 4096, 1) },
    uNoise: { value: null },
    uHeli: { value: new THREE.Vector4(0, -1000, 0, 0) },     // xyz pos, w = wash strength
    uNight: { value: 0 },
    uAmbCol: { value: new THREE.Color(0.3, 0.35, 0.45) },
    uScorch: { value: null },
    uScorchP: { value: new THREE.Vector4(0, 0, 1 / 2048, 0) },
  },
  events: new EventTarget(),
};

// Tiling RGBA noise texture used by many shaders (R,G,B,A = independent smooth noise octaves)
export function makeNoiseTexture(size = 256) {
  const data = new Uint8Array(size * size * 4);
  const tile = (fx, fy, per, off) => { // tileable value noise via periodic lattice
    const x0 = Math.floor(fx), y0 = Math.floor(fy), xf = fx - x0, yf = fy - y0;
    const u = xf * xf * (3 - 2 * xf), v = yf * yf * (3 - 2 * yf);
    const h = (x, y) => GR[P[((x % per) + per) % per + off + P[(((y % per) + per) % per + off * 3) & 255] & 255]];
    const a = h(x0, y0), b = h(x0 + 1, y0), c = h(x0, y0 + 1), d = h(x0 + 1, y0 + 1);
    return a + (b - a) * u + (c - a) * v + (a - b - c + d) * u * v;
  };
  for (let y = 0; y < size; y++) for (let x = 0; x < size; x++) {
    const i = (y * size + x) * 4;
    for (let c = 0; c < 4; c++) {
      let s = 0, a = 0.5, per = [4, 8, 16, 32][c], n = 0;
      for (let o = 0; o < 5; o++) { s += a * tile(x / size * per, y / size * per, per, c * 37 + o * 11); n += a; per *= 2; a *= 0.55; }
      data[i + c] = clamp(Math.round((s / n * 0.9 + 0.5) * 255), 0, 255);
    }
  }
  const t = new THREE.DataTexture(data, size, size, THREE.RGBAFormat);
  t.wrapS = t.wrapT = THREE.RepeatWrapping; t.minFilter = THREE.LinearMipmapLinearFilter; t.magFilter = THREE.LinearFilter;
  t.generateMipmaps = true; t.anisotropy = 16; t.needsUpdate = true;
  return t;
}

// ---------- GLSL shared snippets ----------
export const GLSL_FOG = /* glsl */`
uniform vec3 uSunDir; uniform vec3 uFogColA; uniform vec3 uFogColB; uniform vec4 uFogP;
vec4 swFogCalc(vec3 wpos){
  vec3 rd = wpos - cameraPosition; float d = length(rd); rd /= max(d,1e-4);
  float a = uFogP.x * exp(-uFogP.y * max(cameraPosition.y - uFogP.z, -40.0));
  float t = uFogP.y * rd.y * d;
  float integ = a * d * (abs(t) > 1e-3 ? (1.0 - exp(-t)) / t : 1.0);
  integ += d * 0.000022; // thin uniform aerial haze
  float f = 1.0 - exp(-integ);
  float s = max(dot(rd, uSunDir), 0.0);
  vec3 fc = mix(uFogColB, uFogColA, pow(s, uFogP.w) * 0.85 + 0.15 * s);
  return vec4(fc, f);
}
vec3 swFog(vec3 col, vec3 wpos){ vec4 f = swFogCalc(wpos); return mix(col, f.rgb, f.a); }
`;
export const GLSL_FARSH = /* glsl */`
uniform sampler2D uFarSh; uniform vec4 uFarShP;
float swFarShadow(vec3 wp){
  vec2 uv = (wp.xz - uFarShP.xy) * uFarShP.z + 0.5;
  if (uv.x < 0.0 || uv.x > 1.0 || uv.y < 0.0 || uv.y > 1.0) return 1.0;
  vec2 s = texture2D(uFarSh, uv).rg; // r = sun-horizon height at this xz, g = penumbra width
  float e = min(min(uv.x, 1.0 - uv.x), min(uv.y, 1.0 - uv.y));
  return mix(1.0, clamp((wp.y - s.r) / max(s.g, 0.5) + 1.0, 0.0, 1.0), clamp(e * 30.0, 0.0, 1.0));
}
`;

export function installShaderPatches() {
  const C = THREE.ShaderChunk;
  C.fog_pars_vertex = `#ifdef USE_FOG\n varying vec3 vFogViewPos;\n#endif`;
  C.fog_vertex = `#ifdef USE_FOG\n vFogViewPos = mvPosition.xyz;\n#endif`;
  C.fog_pars_fragment = `#ifdef USE_FOG\n varying vec3 vFogViewPos;\n${GLSL_FOG}\n#endif`;
  C.fog_fragment = `#ifdef USE_FOG\n { vec3 swW = cameraPosition + (vec4(vFogViewPos, 0.0) * viewMatrix).xyz; gl_FragColor.rgb = swFog(gl_FragColor.rgb, swW); }\n#endif`;
  // far (heightfield) sun shadows for every lit material
  C.lights_pars_begin = GLSL_FARSH + '\n' + C.lights_pars_begin;
  C.lights_fragment_begin = C.lights_fragment_begin
    .replace('IncidentLight directLight;', 'IncidentLight directLight;\n float swFS = swFarShadow(cameraPosition + (vec4(geometryPosition, 0.0) * viewMatrix).xyz);')
    .replace('getDirectionalLightInfo( directionalLight, directLight );', 'getDirectionalLightInfo( directionalLight, directLight ); directLight.color *= swFS;');
  // every material gets the shared uniforms
  THREE.Material.prototype.onBeforeCompile = function (shader) { Object.assign(shader.uniforms, G.U); };
}

// patch helper: fn(shader) edits shader; key must be unique per distinct patch
export function patchMaterial(mat, key, fn, extraUniforms) {
  mat.onBeforeCompile = shader => { Object.assign(shader.uniforms, G.U, extraUniforms || {}); fn(shader); };
  mat.customProgramCacheKey = () => key;
  return mat;
}

// tiny helpers
export function setShadow(obj, cast = true, receive = true) { obj.traverse(o => { if (o.isMesh) { o.castShadow = cast; o.receiveShadow = receive; } }); return obj; }
export const tmpV = [new V3(), new V3(), new V3(), new V3(), new V3(), new V3()];
export const tmpQ = [new THREE.Quaternion(), new THREE.Quaternion()];
export const tmpM = [new THREE.Matrix4(), new THREE.Matrix4()];
