// Siege Wing — HDR post pipeline: dynamically scaled MSAA scene → light shafts → bloom → DOF/grade/tonemap → FXAA + grain
import * as THREE from 'three';
import { G, V3, clamp } from './core.js';

const VS = `varying vec2 vUv; void main(){ vUv = uv; gl_Position = vec4(position.xy, 0.0, 1.0); }`;
const quadGeo = new THREE.PlaneGeometry(2, 2);
function pass(frag, uniforms) {
  const m = new THREE.ShaderMaterial({ vertexShader: VS, fragmentShader: 'precision highp float; varying vec2 vUv;\n' + frag, uniforms, depthTest: false, depthWrite: false, fog: false });
  m.onBeforeCompile = () => { };
  return m;
}

export const post = {
  // live parameters other systems poke
  p: { exposure: 1, bloom: 0.5, shafts: 0.55, vignette: 0.32, grain: 0.035, dof: 0, damage: 0, flash: 0, edgeDark: 0, sat: 1.14, chroma: 0.0012, shake: 0, desat: 0, fade: 0 },
  init(renderer, samples = 4) {
    this.r = renderer; this.scene = new THREE.Scene(); this.cam = new THREE.Camera();
    this.quad = new THREE.Mesh(quadGeo, null); this.quad.frustumCulled = false; this.scene.add(this.quad);
    const hf = { type: THREE.HalfFloatType, format: THREE.RGBAFormat, depthBuffer: false, minFilter: THREE.LinearFilter, magFilter: THREE.LinearFilter };
    this.hf = hf;
    this.rtScene = new THREE.WebGLRenderTarget(4, 4, { ...hf, depthBuffer: true, samples });
    this.rtScene.depthTexture = new THREE.DepthTexture(4, 4); this.rtScene.depthTexture.type = THREE.UnsignedIntType;
    this.rtLDR = new THREE.WebGLRenderTarget(4, 4, { type: THREE.UnsignedByteType, format: THREE.RGBAFormat, depthBuffer: false, minFilter: THREE.LinearFilter, magFilter: THREE.LinearFilter });
    this.rtShaftA = new THREE.WebGLRenderTarget(4, 4, hf); this.rtShaftB = new THREE.WebGLRenderTarget(4, 4, hf);
    this.mips = []; for (let i = 0; i < 6; i++) this.mips.push([new THREE.WebGLRenderTarget(4, 4, hf), new THREE.WebGLRenderTarget(4, 4, hf)]);

    this.mShaftMask = pass(`uniform sampler2D tScene; uniform sampler2D tDepth; uniform vec2 uSun; uniform float uAspect;
      void main(){ vec3 c = texture2D(tScene, vUv).rgb; float d = texture2D(tDepth, vUv).r; float l = dot(c, vec3(0.3, 0.5, 0.2));
        vec2 dv = (vUv - uSun) * vec2(uAspect, 1.0); float w = exp(-dot(dv, dv) * 2.2);
        float skyM = step(0.99999, d); gl_FragColor = vec4(c * smoothstep(1.2, 5.0, l) * w * (0.25 + 0.75 * skyM), 1.0); }`,
      { tScene: { value: null }, tDepth: { value: null }, uSun: { value: new THREE.Vector2() }, uAspect: { value: 1 } });
    this.mShaftBlur = pass(`uniform sampler2D tIn; uniform vec2 uSun; uniform float uLen;
      void main(){ vec2 d = (uSun - vUv) * uLen / 8.0; vec3 a = vec3(0.0); float jit = fract(52.9829189 * fract(dot(gl_FragCoord.xy, vec2(0.06711056, 0.00583715)))); vec2 p = vUv + d * (jit - 0.5); float w = 1.0, tw = 0.0; /* jittered start hides the 8-step banding that showed as streaks on far slopes */
        for (int i = 0; i < 8; i++) { a += texture2D(tIn, p).rgb * w; tw += w; p += d; w *= 0.93; } gl_FragColor = vec4(a / tw, 1.0); }`,
      { tIn: { value: null }, uSun: { value: new THREE.Vector2() }, uLen: { value: 0.3 } });
    this.mPre = pass(`uniform sampler2D tIn; uniform vec2 uTexel;
      void main(){ vec3 c = vec3(0.0); c += texture2D(tIn, vUv + uTexel * vec2(-1.0, -1.0)).rgb; c += texture2D(tIn, vUv + uTexel * vec2(1.0, -1.0)).rgb; c += texture2D(tIn, vUv + uTexel * vec2(-1.0, 1.0)).rgb; c += texture2D(tIn, vUv + uTexel * vec2(1.0, 1.0)).rgb; c *= 0.25;
        c = min(c, vec3(60.0)); float l = max(c.r, max(c.g, c.b)); float k = max(l - 1.0, 0.0) / max(l, 1e-3); gl_FragColor = vec4(c * k, 1.0); }`,
      { tIn: { value: null }, uTexel: { value: new THREE.Vector2() } });
    this.mDown = pass(`uniform sampler2D tIn; uniform vec2 uTexel;
      void main(){ vec3 c = texture2D(tIn, vUv).rgb * 4.0; c += texture2D(tIn, vUv + uTexel * vec2(-1.0, -1.0)).rgb; c += texture2D(tIn, vUv + uTexel * vec2(1.0, -1.0)).rgb; c += texture2D(tIn, vUv + uTexel * vec2(-1.0, 1.0)).rgb; c += texture2D(tIn, vUv + uTexel * vec2(1.0, 1.0)).rgb; gl_FragColor = vec4(c / 8.0, 1.0); }`,
      { tIn: { value: null }, uTexel: { value: new THREE.Vector2() } });
    this.mUp = pass(`uniform sampler2D tIn; uniform sampler2D tAdd; uniform vec2 uTexel; uniform float uW;
      void main(){ vec3 c = vec3(0.0); vec2 t = uTexel;
        c += texture2D(tIn, vUv + t * vec2(-1.0, 0.0)).rgb * 2.0; c += texture2D(tIn, vUv + t * vec2(1.0, 0.0)).rgb * 2.0; c += texture2D(tIn, vUv + t * vec2(0.0, -1.0)).rgb * 2.0; c += texture2D(tIn, vUv + t * vec2(0.0, 1.0)).rgb * 2.0;
        c += texture2D(tIn, vUv + t * vec2(-1.0, -1.0)).rgb; c += texture2D(tIn, vUv + t * vec2(1.0, -1.0)).rgb; c += texture2D(tIn, vUv + t * vec2(-1.0, 1.0)).rgb; c += texture2D(tIn, vUv + t * vec2(1.0, 1.0)).rgb; c += texture2D(tIn, vUv).rgb * 4.0;
        gl_FragColor = vec4(c / 16.0 * uW + texture2D(tAdd, vUv).rgb, 1.0); }`,
      { tIn: { value: null }, tAdd: { value: null }, uTexel: { value: new THREE.Vector2() }, uW: { value: 1 } });
    this.mFinal = pass(/* glsl */`
      uniform sampler2D tScene; uniform sampler2D tBloom; uniform sampler2D tShaft; uniform sampler2D tDepth; uniform sampler2D uNoise;
      uniform vec2 uRes; uniform float uSS; uniform float uTime; uniform float uExposure, uBloom, uShafts, uVig, uGrain, uDof, uDamage, uFlash, uEdge, uSat, uChroma, uDesat, uFade, uNight; uniform vec2 uNF;
      vec3 aces(vec3 x){ // Stephen Hill fit
        const mat3 m1 = mat3(0.59719, 0.07600, 0.02840, 0.35458, 0.90834, 0.13383, 0.04823, 0.01566, 0.83777);
        const mat3 m2 = mat3(1.60475, -0.10208, -0.00327, -0.53108, 1.10813, -0.07276, -0.07367, -0.00605, 1.07602);
        vec3 v = m1 * x; vec3 a = v * (v + 0.0245786) - 0.000090537; vec3 b = v * (0.983729 * v + 0.4329510) + 0.238081; return clamp(m2 * (a / b), 0.0, 1.0); }
      float lin(float d){ float z = d * 2.0 - 1.0; return 2.0 * uNF.x * uNF.y / (uNF.y + uNF.x - z * (uNF.y - uNF.x)); }
      // supersample resolve: 4 rotated-grid taps, each weighted by 1/(1+luma) so a hot pixel can't alias an edge
      vec3 S(vec2 u){
        vec2 px = (uSS < 1.02 ? 0.0 : 1.0) / uRes; vec3 a = vec3(0.0); float tw = 0.0; vec3 c; float w;
        c = texture2D(tScene, u + px * vec2(0.125, 0.375)).rgb; w = 1.0 / (1.0 + max(c.r, max(c.g, c.b))); a += c * w; tw += w;
        c = texture2D(tScene, u + px * vec2(-0.375, 0.125)).rgb; w = 1.0 / (1.0 + max(c.r, max(c.g, c.b))); a += c * w; tw += w;
        c = texture2D(tScene, u + px * vec2(0.375, -0.125)).rgb; w = 1.0 / (1.0 + max(c.r, max(c.g, c.b))); a += c * w; tw += w;
        c = texture2D(tScene, u + px * vec2(-0.125, -0.375)).rgb; w = 1.0 / (1.0 + max(c.r, max(c.g, c.b))); a += c * w; tw += w;
        return a / tw; }
      void main(){
        vec2 uv = vUv; vec2 cc = uv - 0.5; float r2 = dot(cc, cc);
        vec2 ca = cc * (uChroma + uDamage * 0.004) * (0.4 + r2 * 4.0);
        vec3 col;
        if (uDof > 0.001) { // near-field blur (cockpit interior) + slight far softness
          float d = lin(texture2D(tDepth, uv).r); float coc = clamp((2.2 - d) / 2.2, 0.0, 1.0) * uDof * 5.0;
          vec3 s = texture2D(tScene, uv).rgb; float tw = 1.0; vec2 px = coc / uRes;
          for (int i = 0; i < 8; i++) { float a = float(i) * 0.7854 + 0.3; vec2 o = vec2(cos(a), sin(a)) * px * (1.0 + mod(float(i), 2.0)); float dd = lin(texture2D(tDepth, uv + o).r); float w = step(dd, 3.5) + 0.15; s += texture2D(tScene, uv + o).rgb * w; tw += w; }
          col = s / tw;
        } else { col = S(uv); float ck = clamp(r2 * 4.0 + uDamage * 4.0, 0.0, 1.0); col.r = mix(col.r, texture2D(tScene, uv + ca).r, ck); col.b = mix(col.b, texture2D(tScene, uv - ca).b, ck); }
        vec3 bloom = texture2D(tBloom, uv).rgb; vec3 shaft = texture2D(tShaft, uv).rgb;
        col += bloom * uBloom + shaft * uShafts;
        col += bloom * 0.06 * texture2D(uNoise, uv * vec2(2.0, 1.2)).g; // faint lens dirt
        col *= uExposure;
        col += vec3(1.0, 0.85, 0.6) * uFlash;
        col *= 1.0 - uVig * smoothstep(0.12, 0.75, r2 * 1.6);
        col = aces(col * 0.9);
        // grade: gentle teal shadows / warm highlights, saturation
        float l = dot(col, vec3(0.2126, 0.7152, 0.0722));
        col = mix(vec3(l), col, uSat * (1.0 - uDesat));
        col += (vec3(-0.012, 0.004, 0.022) * (1.0 - l) + vec3(0.02, 0.008, -0.02) * l) * (1.0 - uNight * 0.5);
        col = pow(max(col, 0.0), vec3(1.03));
        // damage / boundary edge effects
        float edge = smoothstep(0.10, 0.62, r2 * 1.5);
        col = mix(col, col * vec3(0.55, 0.06, 0.04), edge * uDamage);
        col = mix(col, vec3(0.0), edge * uEdge);
        col = mix(col, vec3(0.0), uFade);
        col = pow(col, vec3(1.0 / 2.2));
        gl_FragColor = vec4(col, dot(col, vec3(0.299, 0.587, 0.114))); // alpha = perceptual luma for the FXAA pass
      }`, {
      tScene: { value: null }, tBloom: { value: null }, tShaft: { value: null }, tDepth: { value: null }, uNoise: G.U.uNoise, uRes: { value: new THREE.Vector2() }, uSS: { value: 1 }, uTime: G.U.uTime,
      uExposure: { value: 1 }, uBloom: { value: 0.5 }, uShafts: { value: 0.8 }, uVig: { value: 0.3 }, uGrain: { value: 0.03 }, uDof: { value: 0 }, uDamage: { value: 0 }, uFlash: { value: 0 }, uEdge: { value: 0 }, uSat: { value: 1 }, uChroma: { value: 0.001 }, uDesat: { value: 0 }, uFade: { value: 0 }, uNight: G.U.uNight, uNF: { value: new THREE.Vector2(0.5, 12000) },
    });
    // FXAA 3.11 (quality path, 10 search steps) on the tonemapped image, then film grain on top so grain stays crisp
    this.fxaa = !/[?&]nofxaa/.test(location.search); this.noGrain = /[?&]nograin/.test(location.search);
    this.mFxaa = pass(/* glsl */`
      uniform sampler2D tIn; uniform sampler2D uNoise; uniform vec2 uInv; uniform vec2 uRes; uniform float uTime, uGrain, uOn;
      float L(vec2 p){ return textureLod(tIn, p, 0.0).a; }
      vec3 fxaa(vec2 uv, vec4 cM){
        float lM = cM.a;
        float lS = L(uv + vec2(0.0, uInv.y)), lE = L(uv + vec2(uInv.x, 0.0)), lN = L(uv - vec2(0.0, uInv.y)), lW = L(uv - vec2(uInv.x, 0.0));
        float mx = max(max(lN, lS), max(max(lE, lW), lM)), mn = min(min(lN, lS), min(min(lE, lW), lM)); float range = mx - mn;
        if (range < max(0.0312, mx * 0.125)) return cM.rgb;
        float lNW = L(uv + vec2(-uInv.x, -uInv.y)), lSE = L(uv + uInv), lNE = L(uv + vec2(uInv.x, -uInv.y)), lSW = L(uv + vec2(-uInv.x, uInv.y));
        float lNS = lN + lS, lWE = lW + lE, lNESE = lNE + lSE, lNWNE = lNW + lNE, lNWSW = lNW + lSW, lSWSE = lSW + lSE;
        float edgeHorz = abs(-2.0 * lW + lNWSW) + abs(-2.0 * lM + lNS) * 2.0 + abs(-2.0 * lE + lNESE);
        float edgeVert = abs(-2.0 * lS + lSWSE) + abs(-2.0 * lM + lWE) * 2.0 + abs(-2.0 * lN + lNWNE);
        bool horz = edgeHorz >= edgeVert;
        float subA = (lNS + lWE) * 2.0 + lNWSW + lNESE; float subC = clamp(abs(subA / 12.0 - lM) / range, 0.0, 1.0);
        float len = horz ? uInv.y : uInv.x; if (!horz) { lN = lW; lS = lE; }
        float gN = lN - lM, gS = lS - lM; float lNN = lN + lM, lSS = lS + lM;
        bool pairN = abs(gN) >= abs(gS); float grad = max(abs(gN), abs(gS)); if (pairN) len = -len; if (!pairN) lNN = lSS;
        vec2 posB = uv; vec2 off = horz ? vec2(uInv.x, 0.0) : vec2(0.0, uInv.y);
        if (horz) posB.y += len * 0.5; else posB.x += len * 0.5;
        vec2 posN = posB - off, posP = posB + off;
        float half_ = lNN * 0.5; float gs = grad * 0.25; bool ltz = (lM - half_) < 0.0;
        float eN = L(posN) - half_, eP = L(posP) - half_; bool dN = abs(eN) >= gs, dP = abs(eP) >= gs;
        float st = 1.5;
        for (int i = 0; i < 10; i++) {
          if (dN && dP) break;
          if (!dN) { posN -= off * st; eN = L(posN) - half_; dN = abs(eN) >= gs; }
          if (!dP) { posP += off * st; eP = L(posP) - half_; dP = abs(eP) >= gs; }
          st = i < 4 ? 2.0 : i < 6 ? 4.0 : 8.0;
        }
        float dstN = horz ? uv.x - posN.x : uv.y - posN.y, dstP = horz ? posP.x - uv.x : posP.y - uv.y;
        bool good = dstN < dstP ? ((eN < 0.0) != ltz) : ((eP < 0.0) != ltz);
        float po = good ? 0.5 - min(dstN, dstP) / (dstN + dstP) : 0.0;
        float subF = (-2.0 * subC + 3.0) * subC * subC; po = max(po, subF * subF * 0.6);
        vec2 pm = uv; if (horz) pm.y += po * len; else pm.x += po * len;
        return textureLod(tIn, pm, 0.0).rgb; }
      void main(){
        vec4 c = textureLod(tIn, vUv, 0.0); vec3 col = uOn > 0.5 ? fxaa(vUv, c) : c.rgb;
        float g = texture2D(uNoise, vUv * uRes / 256.0 + fract(uTime * vec2(7.13, 3.71))).r - 0.5;
        col += g * uGrain * (1.2 - c.a * c.a * 0.7);
        gl_FragColor = vec4(col, 1.0);
      }`, { tIn: { value: null }, uNoise: G.U.uNoise, uInv: { value: new THREE.Vector2() }, uRes: { value: new THREE.Vector2() }, uTime: G.U.uTime, uGrain: { value: 0.03 }, uOn: { value: 1 } });
  },
  // MSAA samples on the HDR scene target (0 = off); three re-creates the target with the new count on next use
  setSamples(n) { if (this.rtScene.samples === n) return; this.rtScene.samples = n; this.rtScene.dispose(); },
  // w,h = output (canvas) pixels; ss = scene render scale (>1 supersampled, <1 upscaled by the final pass)
  resize(w, h, ss = 1) {
    this.w = w; this.h = h; this.ss = ss; this.rtScene.setSize(Math.round(w * ss), Math.round(h * ss)); this.rtLDR.setSize(w, h);
    this.mFinal.uniforms.uSS.value = ss; this.mFxaa.uniforms.uInv.value.set(1 / w, 1 / h); this.mFxaa.uniforms.uRes.value.set(w, h);
    const sw = Math.max(2, w >> 2), sh = Math.max(2, h >> 2); this.rtShaftA.setSize(sw, sh); this.rtShaftB.setSize(sw, sh);
    let mw = w >> 1, mh = h >> 1; for (const m of this.mips) { m[0].setSize(Math.max(2, mw), Math.max(2, mh)); m[1].setSize(Math.max(2, mw), Math.max(2, mh)); mw >>= 1; mh >>= 1; }
    this.mFinal.uniforms.uRes.value.set(w, h);
  },
  _draw(mat, target) { this.quad.material = mat; this.r.setRenderTarget(target); this.r.render(this.scene, this.cam); },
  render(scene, camera, sunDirTrue, sunVisible) {
    const r = this.r, p = this.p;
    r.setRenderTarget(this.rtScene); r.clear(); r.render(scene, camera);
    const tScene = this.rtScene.texture;
    // --- light shafts ---
    _v.copy(camera.position).addScaledVector(sunDirTrue, 5000).project(camera);
    const facing = _d.set(0, 0, -1).applyQuaternion(camera.quaternion).dot(sunDirTrue);
    const sunUV = _s.set(_v.x * 0.5 + 0.5, _v.y * 0.5 + 0.5);
    const shaftK = p.shafts * clamp((facing - 0.15) * 2.5, 0, 1) * clamp(1.6 - Math.max(Math.abs(_v.x), Math.abs(_v.y)), 0, 1) * (0.25 + 0.75 * sunVisible);
    if (shaftK > 0.01) {
      const u = this.mShaftMask.uniforms; u.tScene.value = tScene; u.tDepth.value = this.rtScene.depthTexture; u.uSun.value.copy(sunUV); u.uAspect.value = this.w / this.h;
      this._draw(this.mShaftMask, this.rtShaftA);
      const b = this.mShaftBlur.uniforms; b.uSun.value.copy(sunUV);
      b.tIn.value = this.rtShaftA.texture; b.uLen.value = 0.12; this._draw(this.mShaftBlur, this.rtShaftB);
      b.tIn.value = this.rtShaftB.texture; b.uLen.value = 0.3; this._draw(this.mShaftBlur, this.rtShaftA);
      b.tIn.value = this.rtShaftA.texture; b.uLen.value = 0.7; this._draw(this.mShaftBlur, this.rtShaftB);
    }
    // --- bloom ---
    const mips = this.mips;
    this.mPre.uniforms.tIn.value = tScene; this.mPre.uniforms.uTexel.value.set(1 / this.w, 1 / this.h); this._draw(this.mPre, mips[0][0]);
    for (let i = 1; i < mips.length; i++) { const src = mips[i - 1][0]; this.mDown.uniforms.tIn.value = src.texture; this.mDown.uniforms.uTexel.value.set(1 / src.width, 1 / src.height); this._draw(this.mDown, mips[i][0]); }
    let cur = mips[mips.length - 1][0];
    for (let i = mips.length - 2; i >= 0; i--) { const u = this.mUp.uniforms; u.tIn.value = cur.texture; u.tAdd.value = mips[i][0].texture; u.uTexel.value.set(1 / cur.width, 1 / cur.height); u.uW.value = 1.0; this._draw(this.mUp, mips[i][1]); cur = mips[i][1]; }
    // --- final ---
    const f = this.mFinal.uniforms; f.tScene.value = tScene; f.tBloom.value = cur.texture; f.tShaft.value = this.rtShaftB.texture; f.tDepth.value = this.rtScene.depthTexture;
    f.uExposure.value = p.exposure; f.uBloom.value = p.bloom / mips.length * 1.6; f.uShafts.value = shaftK > 0.01 ? shaftK : 0; f.uVig.value = p.vignette; f.uGrain.value = p.grain; f.uDof.value = p.dof; f.uDamage.value = p.damage; f.uFlash.value = p.flash; f.uEdge.value = p.edgeDark; f.uSat.value = p.sat; f.uChroma.value = p.chroma; f.uDesat.value = p.desat; f.uFade.value = p.fade;
    f.uNF.value.set(camera.near, camera.far);
    this._draw(this.mFinal, this.rtLDR);
    const x = this.mFxaa.uniforms; x.tIn.value = this.rtLDR.texture; x.uGrain.value = this.noGrain ? 0 : p.grain; x.uOn.value = this.fxaa ? 1 : 0; this._draw(this.mFxaa, null);
  },
};
const _v = new V3(), _d = new V3(), _s = new THREE.Vector2();
