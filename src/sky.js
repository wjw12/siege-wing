// Siege Wing — sky dome, sun, time of day ("sunset clock"), image-based lighting, sun shadow frustum
import * as THREE from 'three';
import { G, V3, lerp, smooth, clamp, DEG, GLSL_FOG } from './core.js';

const SKY_FRAG = /* glsl */`
precision highp float;
varying vec3 vDir;
uniform vec3 uZenith; uniform vec3 uGround; uniform vec3 uSkySun; uniform vec3 uSkyDir; uniform float uTime; uniform float uNight; uniform sampler2D uNoise; uniform float uCloud; uniform float uEnvMode;
${GLSL_FOG}
float cl(vec2 p){ float a = texture2D(uNoise, p).r * 0.55 + texture2D(uNoise, p * 2.7 + 0.3).g * 0.28 + texture2D(uNoise, p * 7.1).b * 0.17; return a; }
void main(){
  vec3 rd = normalize(vDir);
  float mu = dot(rd, uSkyDir); float mup = max(mu, 0.0);
  // horizon colour == fog colour so terrain melts into sky
  vec3 hd = normalize(vec3(rd.x, 0.0, rd.z)); float s = max(dot(hd, uSunDir), 0.0);
  vec3 hor = mix(uFogColB, uFogColA, pow(s, uFogP.w) * 0.85 + 0.15 * s);
  float h = max(rd.y, 0.0);
  vec3 col = mix(hor, uZenith, 1.0 - exp(-h * 4.2));
  // warm band above the horizon near the sun, pink "belt of venus" opposite
  col = mix(col, uFogColA * 1.05, pow(mup, 2.5) * 0.6 * exp(-h * 2.2));
  col += uFogColA * 0.45 * exp(-h * 9.0) * pow(mup, 2.0);
  col += vec3(0.20, 0.07, 0.10) * (1.0 - uNight) * exp(-h * 7.0) * pow(max(-mu, 0.0), 2.0) * dot(uSkySun, vec3(0.2));
  // sun glow + disc
  float above = smoothstep(-0.02, 0.01, rd.y);
  col += uSkySun * (pow(mup, 10.0) * 0.02 + pow(mup, 120.0) * 0.12 + pow(mup, 1500.0) * 0.7) * above;
  if (uEnvMode < 0.5) col += uSkySun * smoothstep(0.99985, 0.99994, mu) * 30.0 * above;
  // clouds: two layers projected on planes
  if (rd.y > 0.005) {
    vec2 sunXZ = normalize(uSkyDir.xz + 1e-4);
    // high cirrus streaks
    vec2 p1 = rd.xz / (rd.y + 0.12) * 0.11 + vec2(uTime * 0.0006, 0.0);
    float c1 = texture2D(uNoise, p1 * vec2(0.35, 1.6)).r * 0.6 + texture2D(uNoise, p1 * vec2(1.1, 4.0)).g * 0.4;
    c1 = smoothstep(0.52, 0.85, c1) * 0.55;
    // cumulus
    vec2 p2 = rd.xz / (rd.y + 0.06) * 0.045 + vec2(uTime * 0.0011, uTime * 0.0004);
    float d0 = cl(p2); float c2 = smoothstep(1.0 - uCloud, 1.0 - uCloud + 0.22, d0);
    float dS = cl(p2 + sunXZ * 0.012); float shade = clamp((d0 - dS) * 5.0 + 0.5, 0.0, 1.0); // lit edge toward sun
    float thick = smoothstep(1.0 - uCloud, 1.0 - uCloud + 0.4, d0);
    vec3 lit = uSkySun * (0.16 + 0.5 * shade) * (1.0 + 2.5 * pow(mup, 6.0)) + uZenith * 0.5;
    vec3 dark = mix(uZenith * 0.55 + hor * 0.25, uSkySun * 0.08, 0.3);
    vec3 cc = mix(lit, dark, thick * 0.75);
    cc += uSkySun * pow(mup, 24.0) * (1.0 - thick) * 0.9;        // silver lining
    float fade = smoothstep(0.005, 0.16, rd.y);
    col = mix(col, uSkySun * (0.10 + 0.3 * pow(mup, 3.0)) + uZenith * 0.6, c1 * fade * (1.0 - c2));
    col = mix(col, cc, c2 * fade * 0.93);
  }
  // stars
  if (uNight > 0.01 && rd.y > 0.0) {
    vec3 sd = rd * 190.0; vec3 ip = floor(sd); vec3 fp = fract(sd) - 0.5;
    float sh = fract(sin(dot(ip, vec3(127.1, 311.7, 74.7))) * 43758.5453);
    float st = step(0.9972, sh) * smoothstep(0.32, 0.0, length(fp)) * (0.4 + 0.6 * fract(sh * 917.0));
    col += vec3(0.8, 0.86, 1.0) * st * smoothstep(0.45, 0.95, uNight) * 1.4 * smoothstep(0.02, 0.3, rd.y);
  }
  // below horizon
  if (rd.y < 0.0) col = mix(hor, uEnvMode > 0.5 ? uGround : hor * 0.6, smoothstep(0.0, uEnvMode > 0.5 ? -0.25 : -0.05, rd.y));
  gl_FragColor = vec4(col, 1.0);
}`;

export const sky = {
  tod: 0, elev: 12 * DEG, night: 0, sunDir: new V3(), sunVisible: 1,
  build(scene) {
    this.scene = scene;
    this.uniforms = { uZenith: { value: new THREE.Color() }, uGround: { value: new THREE.Color() }, uCloud: { value: 0.5 }, uEnvMode: { value: 0 }, ...pick(G.U, ['uSunDir', 'uFogColA', 'uFogColB', 'uFogP', 'uTime', 'uNight', 'uNoise']) };
    // sky uses a brighter sun colour than the lights; keep own uniform
    this.uniforms.uSkySun = { value: new THREE.Color() }; this.uniforms.uSkyDir = { value: this.sunDir };
    const mk = env => new THREE.ShaderMaterial({
      uniforms: env ? { ...this.uniforms, uEnvMode: { value: 1 } } : this.uniforms, side: THREE.BackSide, depthWrite: false, depthTest: !env, fog: false,
      vertexShader: env ? `varying vec3 vDir; void main(){ vDir = position; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }`
        : `varying vec3 vDir; void main(){ vDir = position; vec4 p = projectionMatrix * vec4(mat3(viewMatrix) * position, 1.0); gl_Position = p.xyww; }`,
      fragmentShader: SKY_FRAG,
    });
    const dome = this.dome = new THREE.Mesh(new THREE.SphereGeometry(1, 48, 24), mk(false));
    dome.frustumCulled = false; dome.renderOrder = -100; scene.add(dome);
    // env capture scene
    this.envScene = new THREE.Scene(); this.envScene.add(new THREE.Mesh(new THREE.SphereGeometry(50, 32, 16), mk(true)));
    this.pmrem = new THREE.PMREMGenerator(G.renderer); this.envRT = null; this.envT = 1e9;
    // sun
    const sun = this.sun = new THREE.DirectionalLight(0xffffff, 1);
    sun.castShadow = true; sun.shadow.mapSize.set(4096, 4096); sun.shadow.bias = -0.0004; sun.shadow.normalBias = 0.35; sun.shadow.radius = 2.2;
    scene.add(sun); scene.add(sun.target);
    this.fill = new THREE.HemisphereLight(0xffffff, 0xffffff, 0.0); scene.add(this.fill);
    scene.fog = new THREE.FogExp2(0xffffff, 0.0001); // only enables USE_FOG; real fog is in core.js chunks
    this.shadowSize = 260;
    this.setTime(0);
  },
  // tod 0..1 over the run
  setTime(tod) {
    this.tod = tod = clamp(tod, 0, 1.2);
    // elevation: 13° → 5° at 0.6 → 0° at 0.85 → -6° at 1.0
    const e = tod < 0.6 ? lerp(21, 7.5, tod / 0.6) : tod < 0.85 ? lerp(7.5, 0.4, (tod - 0.6) / 0.25) : lerp(0.4, -7, (tod - 0.85) / 0.25);
    this.elev = e * DEG;
    const az = (184 + tod * 10) * DEG; // from +x axis; ~west, drifting north-west
    this.sunDir.set(Math.cos(az) * Math.cos(this.elev), Math.sin(this.elev), Math.sin(az) * Math.cos(this.elev)).normalize();
    const U = G.U;
    const day = smooth(-1.5, 9, e);          // 1 = golden hour, 0 = sun at horizon
    const up = smooth(-5.5, 0.5, e);         // sun still contributing
    const night = this.night = 1 - smooth(-6, 1.5, e);
    U.uNight.value = night;
    // light direction: never let the light vector go below ~1.2° so shadows stay sane while it fades
    const le = Math.max(this.elev, 1.4 * DEG);
    U.uSunDir.value.set(Math.cos(az) * Math.cos(le), Math.sin(le), Math.sin(az) * Math.cos(le)).normalize();
    // sun light colour (linear) — reddens and dims toward the horizon
    const sc = new THREE.Color().setRGB(1.0, lerp(0.26, 0.60, day), lerp(0.06, 0.27, day));
    const inten = lerp(0.0, lerp(3.2, 8.5, day), smooth(-1.2, 2.5, e));
    this.sunVisible = smooth(-1.2, 2.5, e);
    this.sun.color.copy(sc); this.sun.intensity = inten;
    this.sun.castShadow = inten > 0.05;
    U.uSunCol.value.copy(sc).multiplyScalar(inten);
    this.uniforms.uSkySun.value.copy(sc).multiplyScalar(lerp(0.0, lerp(3.2, 4.2, day), up));
    // sky colours
    const zen = this.uniforms.uZenith.value;
    zen.setRGB(lerp(0.04, 0.065, day), lerp(0.08, 0.165, day), lerp(0.20, 0.42, day)).multiplyScalar(lerp(0.10, 1, up * up) * 1.0);
    zen.lerp(new THREE.Color(0.012, 0.018, 0.045), night * 0.85);
    G.skyZenith = zen;
    const fa = U.uFogColA.value, fb = U.uFogColB.value;
    fa.setRGB(lerp(1.0, 1.05, day), lerp(0.30, 0.52, day), lerp(0.08, 0.19, day)).multiplyScalar(lerp(0.05, 1, up));
    fb.setRGB(lerp(0.24, 0.34, day), lerp(0.25, 0.37, day), lerp(0.36, 0.46, day)).multiplyScalar(lerp(0.07, 0.9, up));
    fa.lerp(new THREE.Color(0.03, 0.035, 0.06), night * 0.8); fb.lerp(new THREE.Color(0.018, 0.024, 0.045), night * 0.8);
    U.uFogP.value.set(lerp(0.00062, 0.00042, day), 0.012, 18, lerp(3.5, 7, day));
    this.uniforms.uGround.value.setRGB(0.10, 0.085, 0.05).multiplyScalar(lerp(0.05, 1, up) * (0.5 + inten * 0.12));
    this.uniforms.uCloud.value = 0.53;
    this.fill.color.setRGB(0.42, 0.52, 0.85); this.fill.groundColor.setRGB(0.10, 0.10, 0.14); this.fill.intensity = night * 0.75;
    this.exposure = lerp(1.18, 1.6, night);
  },
  update(dt, focus, shadowSize) {
    const cam = G.camera;
    this.dome.position.copy(cam.position);
    // shadow frustum follows the focus point, snapped to texels
    const S = this.shadowSize = shadowSize || this.shadowSize; const sun = this.sun; const sc = sun.shadow.camera;
    if (sc.right !== S) { sc.left = -S; sc.right = S; sc.top = S; sc.bottom = -S; sc.near = 10; sc.far = 2600; sc.updateProjectionMatrix(); }
    const d = G.U.uSunDir.value;
    // build light basis and snap
    const texel = (2 * S) / sun.shadow.mapSize.x;
    const right = _r.crossVectors(_up, d).normalize(), up2 = _u.crossVectors(d, right).normalize();
    const fx = Math.round(focus.dot(right) / texel) * texel, fy = Math.round(focus.dot(up2) / texel) * texel, fz = focus.dot(d);
    _f.set(0, 0, 0).addScaledVector(right, fx).addScaledVector(up2, fy).addScaledVector(d, fz);
    sun.target.position.copy(_f); sun.position.copy(_f).addScaledVector(d, 1300); sun.target.updateMatrixWorld();
    // refresh IBL periodically
    this.envT += dt;
    if (this.envT > (this.envRT && location.search.includes('noenv') ? 1e9 : 6)) {
      this.envT = 0; const old = this.envRT;
      this.envRT = this.pmrem.fromScene(this.envScene, 0, 1, 100);
      this.scene.environment = this.envRT.texture; this.scene.environmentIntensity = 1.9;
      if (old) old.dispose();
    }
  },
};
const _r = new V3(), _u = new V3(), _f = new V3(), _up = new V3(0, 1, 0);
function pick(o, keys) { const r = {}; for (const k of keys) r[k] = o[k]; return r; }
