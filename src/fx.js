// Siege Wing — effects: lit smoke/fire/dust particles, streaks (tracers/sparks), debris, flash lights, emitters
import * as THREE from 'three';
import { G, V3, clamp, lerp, sat, rnd, rndS, TAU, GLSL_FOG, GLSL_FARSH } from './core.js';
import { terrain, L } from './terrain.js';

const MAXP = 7000, MAXS = 2500, MAXD = 500, NL = 5;
const T_SMOKE = 0, T_FIRE = 1, T_DUST = 2, T_FLASH = 3, T_RING = 4, T_SPRAY = 5;
const _v = new V3(), _v2 = new V3(), _c = new THREE.Color(), _m = new THREE.Matrix4(), _q = new THREE.Quaternion(), _s = new V3();

export const fx = {
  n: 0, onShake: null,
  init(scene) {
    this.scene = scene;
    // ---------- particles ----------
    const P = this.P = {
      x: new Float32Array(MAXP), y: new Float32Array(MAXP), z: new Float32Array(MAXP), vx: new Float32Array(MAXP), vy: new Float32Array(MAXP), vz: new Float32Array(MAXP),
      life: new Float32Array(MAXP), max: new Float32Array(MAXP), s0: new Float32Array(MAXP), s1: new Float32Array(MAXP), rot: new Float32Array(MAXP), rv: new Float32Array(MAXP),
      type: new Uint8Array(MAXP), r: new Float32Array(MAXP), g: new Float32Array(MAXP), b: new Float32Array(MAXP), a: new Float32Array(MAXP), em: new Float32Array(MAXP),
      drag: new Float32Array(MAXP), grav: new Float32Array(MAXP), seed: new Float32Array(MAXP), dist: new Float32Array(MAXP),
    };
    this.order = new Uint16Array(MAXP);
    const geo = new THREE.InstancedBufferGeometry(); geo.setAttribute('position', new THREE.Float32BufferAttribute([-1, -1, 0, 1, -1, 0, 1, 1, 0, -1, 1, 0], 3)); geo.setIndex([0, 1, 2, 0, 2, 3]);
    const mk = (n, sz) => { const a = new THREE.InstancedBufferAttribute(new Float32Array(n * sz), sz); a.setUsage(THREE.DynamicDrawUsage); return a; };
    this.aPos = mk(MAXP, 4); this.aCol = mk(MAXP, 4); this.aMisc = mk(MAXP, 4);
    geo.setAttribute('iPos', this.aPos); geo.setAttribute('iCol', this.aCol); geo.setAttribute('iMisc', this.aMisc); geo.instanceCount = 0;
    const mat = new THREE.ShaderMaterial({
      transparent: true, depthWrite: false, fog: false, blending: THREE.CustomBlending, blendSrc: THREE.OneFactor, blendDst: THREE.OneMinusSrcAlphaFactor, blendSrcAlpha: THREE.OneFactor, blendDstAlpha: THREE.OneMinusSrcAlphaFactor,
      uniforms: {},
      vertexShader: /* glsl */`
        attribute vec4 iPos; attribute vec4 iCol; attribute vec4 iMisc; // iPos.w = size; iMisc = rot, age01, type, seed ; iCol.a = alpha (emissive packed in sign of size? no: see em below)
        varying vec2 vUv; varying vec4 vCol; varying vec4 vMisc; varying vec3 vWp; varying vec3 vView;
        void main(){
          vUv = position.xy; vCol = iCol; vMisc = iMisc;
          float c = cos(iMisc.x), s = sin(iMisc.x); vec2 p = vec2(position.x * c - position.y * s, position.x * s + position.y * c) * iPos.w;
          float tyv = floor(iMisc.z + 0.5); if (tyv > 0.5 && tyv < 1.5) p = vec2(position.x * 0.82, position.y * 1.5 + 0.42) * iPos.w; // flames stand upright and tall instead of tumbling as round blobs
          vec4 mv = viewMatrix * vec4(iPos.xyz, 1.0);
          float ty = floor(iMisc.z + 0.5);
          if (ty > 3.5 && ty < 4.5) { // ground ring: lie flat in world space
            vec3 wp = iPos.xyz + vec3(position.x, 0.0, position.y) * iPos.w; mv = viewMatrix * vec4(wp, 1.0); vWp = wp;
          } else { mv.xy += p; vWp = iPos.xyz; }
          vView = mv.xyz;
          gl_Position = projectionMatrix * mv;
        }`,
      fragmentShader: /* glsl */`
        precision highp float;
        varying vec2 vUv; varying vec4 vCol; varying vec4 vMisc; varying vec3 vWp; varying vec3 vView;
        uniform sampler2D uNoise; uniform vec3 uSunCol; uniform float uNight;
        ${GLSL_FOG}
        ${GLSL_FARSH}
        void main(){
          float r = length(vUv); if (r > 1.0) discard;
          float nearK = smoothstep(2.0, 9.0, length(vView));   // anything right at the lens fades out instead of filling the screen
          float age = vMisc.y; float ty = floor(vMisc.z + 0.5); float seed = fract(vMisc.w); float em = floor(vMisc.w) / 16.0;
          vec2 nuv = vUv * 0.23 + seed * vec2(7.3, 3.1);
          float n = texture2D(uNoise, nuv).r * 0.6 + texture2D(uNoise, nuv * 2.9 + age * 0.15).g * 0.4;
          vec3 col; float alpha;
          vec4 fog = swFogCalc(vWp);
          if (ty < 0.5 || (ty > 1.5 && ty < 2.5) || ty > 4.5) { // smoke / dust / spray : lit volume
            float n3 = texture2D(uNoise, nuv * 6.7 - vec2(age * 0.22, age * 0.31)).b;
            float dens = smoothstep(1.0, 0.25, r + (n - 0.5) * 1.1 + (n3 - 0.5) * (0.35 + 0.55 * age)) * smoothstep(1.0, 0.62, r);
            dens *= smoothstep(0.0, 0.08, age) * (1.0 - smoothstep(0.55, 1.0, age));
            alpha = dens * vCol.a * nearK;
            vec3 N = normalize(vec3(vUv + (n - 0.5) * 0.6 + (n3 - 0.5) * 0.7, sqrt(max(1.0 - r * r, 0.0)) + 0.25));
            vec3 Lv = normalize((viewMatrix * vec4(uSunDir, 0.0)).xyz);
            float ndl = dot(N, Lv); float wrap = clamp(ndl * 0.6 + 0.4, 0.0, 1.0);
            float fwd = pow(max(dot(normalize(vView), Lv), 0.0), 5.0); // looking toward the sun through the puff
            float sh = swFarShadow(vWp);
            vec3 amb = mix(uFogColB, uFogColA, 0.25) * 0.55 + vec3(0.012, 0.015, 0.025);
            col = vCol.rgb * (0.72 + 0.56 * n3) * (amb + uSunCol * sh * (0.10 + 0.5 * wrap)) + uSunCol * sh * fwd * 0.3 * (1.0 - dens * 0.6) * (0.04 + vCol.rgb * 0.9);
            // inner glow from fire underneath
            col += vec3(1.0, 0.36, 0.07) * em * 0.5 * pow(1.0 - age, 3.0) * (0.4 + n);
            col = mix(col, fog.rgb, fog.a);
          } else if (ty < 1.5) { // fire
            float rf = length(vec2(vUv.x * (1.0 + 1.25 * smoothstep(-0.3, 1.0, vUv.y)), vUv.y)); // teardrop: wide at the base, licking to a point
            float dens = smoothstep(1.0, 0.1, rf + (n - 0.5) * 1.3) * smoothstep(1.0, 0.6, rf);
            float n2 = texture2D(uNoise, nuv * vec2(4.3, 2.6) - vec2(0.0, age * 1.6 + seed * 3.0)).b; dens *= smoothstep(0.25, 0.6, n2 + (1.0 - r) * 0.6);
            float heat = dens * (1.0 - age) * (0.55 + 0.9 * n);
            vec3 fire = mix(vec3(1.0, 0.12, 0.0), vec3(1.0, 0.55, 0.12), smoothstep(0.15, 0.55, heat)); fire = mix(fire, vec3(1.0, 0.92, 0.7), smoothstep(0.6, 0.95, heat));
            float soot = smoothstep(0.45, 1.0, age);
            alpha = dens * vCol.a * smoothstep(1.0, 0.75, age) * mix(0.35, 0.9, soot);
            col = mix(fire * (2.0 + em * 5.0) * heat, vec3(0.02), soot) * (1.0 - fog.a);
            gl_FragColor = vec4(col * dens * vCol.a * smoothstep(1.0, 0.8, age) + vec3(0.015) * alpha * soot, alpha * soot) * nearK; return;
          } else if (ty < 3.5) { // additive flash
            float g = pow(1.0 - r, 2.2) * (1.0 - age);
            gl_FragColor = vec4(vCol.rgb * g * vCol.a * (1.0 + em * 6.0) * (1.0 - fog.a * 0.7) * nearK, 0.0); return;
          } else { // shock ring on ground
            float w = 0.08 + 0.1 * age; float ring = smoothstep(w, 0.0, abs(r - (0.25 + 0.7 * age))) * (1.0 - age) * (1.0 - age);
            alpha = ring * vCol.a * (0.5 + 0.5 * n); col = mix(vCol.rgb * (uSunCol * 0.4 + uFogColB * 0.5), fog.rgb, fog.a);
          }
          gl_FragColor = vec4(col * alpha, alpha);
        }`,
    });
    this.pMesh = new THREE.Mesh(geo, mat); this.pMesh.frustumCulled = false; this.pMesh.renderOrder = 20; scene.add(this.pMesh);

    // ---------- streaks ----------
    const S = this.S = { x: new Float32Array(MAXS), y: new Float32Array(MAXS), z: new Float32Array(MAXS), vx: new Float32Array(MAXS), vy: new Float32Array(MAXS), vz: new Float32Array(MAXS), life: new Float32Array(MAXS), max: new Float32Array(MAXS), len: new Float32Array(MAXS), w: new Float32Array(MAXS), r: new Float32Array(MAXS), g: new Float32Array(MAXS), b: new Float32Array(MAXS), grav: new Float32Array(MAXS), bounce: new Uint8Array(MAXS) };
    this.sn = 0;
    const sg = new THREE.InstancedBufferGeometry(); sg.setAttribute('position', new THREE.Float32BufferAttribute([0, -1, 0, 1, -1, 0, 1, 1, 0, 0, 1, 0], 3)); sg.setIndex([0, 1, 2, 0, 2, 3]);
    this.sA = mk(MAXS, 4); this.sB = mk(MAXS, 4); this.sC = mk(MAXS, 4); sg.setAttribute('iA', this.sA); sg.setAttribute('iB', this.sB); sg.setAttribute('iC', this.sC); sg.instanceCount = 0;
    const smat = new THREE.ShaderMaterial({
      transparent: true, depthWrite: false, fog: false, blending: THREE.AdditiveBlending,
      vertexShader: `attribute vec4 iA; attribute vec4 iB; attribute vec4 iC; varying vec2 vUv; varying vec4 vC;
        void main(){ vUv = position.xy; vC = iC; vec3 head = iA.xyz; vec3 tail = iA.xyz - iB.xyz; // iB.xyz = dir*len
          vec4 h = viewMatrix * vec4(head, 1.0), t = viewMatrix * vec4(tail, 1.0);
          // a streak with one end at or behind the lens would project as a screen-filling cone: fade it out and keep both ends in front
          vC.a *= smoothstep(1.0, 5.0, min(-h.z, -t.z)); h.z = min(h.z, -0.5); t.z = min(t.z, -0.5);
          vec2 d = normalize(h.xy - t.xy + 1e-5); vec2 nrm = vec2(-d.y, d.x);
          float wd = max(iA.w, -min(h.z, t.z) * 0.0011); // keep visible at range
          vec4 p = mix(t, h, position.x); p.xy += nrm * position.y * wd; gl_Position = projectionMatrix * p; }`,
      fragmentShader: `varying vec2 vUv; varying vec4 vC; void main(){ float a = (1.0 - abs(vUv.y)); a *= a; float l = smoothstep(0.0, 0.5, vUv.x); gl_FragColor = vec4(vC.rgb * a * l * vC.a, 1.0); }`,
    });
    this.sMesh = new THREE.Mesh(sg, smat); this.sMesh.frustumCulled = false; this.sMesh.renderOrder = 21; scene.add(this.sMesh);

    // ---------- debris ----------
    const dg = new THREE.IcosahedronGeometry(1, 0); { const p = dg.attributes.position; for (let i = 0; i < p.count; i++) { const k = 0.6 + ((i * 7919) % 13) / 13 * 0.7; p.setXYZ(i, p.getX(i) * k, p.getY(i) * k * 0.7, p.getZ(i) * k); } dg.computeVertexNormals(); }
    const dm = new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.9, flatShading: true });
    this.dMesh = new THREE.InstancedMesh(dg, dm, MAXD); this.dMesh.count = 0; this.dMesh.castShadow = true; this.dMesh.frustumCulled = false; this.dMesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
    this.dMesh.instanceColor = new THREE.InstancedBufferAttribute(new Float32Array(MAXD * 3), 3); scene.add(this.dMesh);
    this.D = []; // {x,y,z,vx,vy,vz,rx,ry,rz,ax,ay,az,size,life,col, rest}

    // ---------- flash lights ----------
    this.lights = []; for (let i = 0; i < NL; i++) { const l = new THREE.PointLight(0xffaa55, 0, 60, 1.6); l.userData = { t: 0, dur: 0, peak: 0 }; scene.add(l); this.lights.push(l); }
    this.emitters = [];
    this.washT = 0;
  },
  clear() { this.n = 0; this.sn = 0; this.D.length = 0; this.emitters = this.emitters.filter(e => e.permanent); for (const l of this.lights) { l.intensity = 0; l.userData.dur = 0; } },

  // ---------- low level spawners ----------
  spawn(type, x, y, z, vx, vy, vz, s0, s1, life, r, g, b, a, em = 0, drag = 0.8, grav = 0) {
    if (this.n >= MAXP) { // overwrite a random old one
      const i = (Math.random() * MAXP) | 0; this._set(i, type, x, y, z, vx, vy, vz, s0, s1, life, r, g, b, a, em, drag, grav); return i;
    }
    const i = this.n++; this._set(i, type, x, y, z, vx, vy, vz, s0, s1, life, r, g, b, a, em, drag, grav); return i;
  },
  _set(i, type, x, y, z, vx, vy, vz, s0, s1, life, r, g, b, a, em, drag, grav) {
    const P = this.P; P.type[i] = type; P.x[i] = x; P.y[i] = y; P.z[i] = z; P.vx[i] = vx; P.vy[i] = vy; P.vz[i] = vz; P.s0[i] = s0; P.s1[i] = s1; P.life[i] = 0; P.max[i] = life;
    P.r[i] = r; P.g[i] = g; P.b[i] = b; P.a[i] = a; P.em[i] = em; P.drag[i] = drag; P.grav[i] = grav; P.rot[i] = Math.random() * TAU; P.rv[i] = rndS(0.5); P.seed[i] = Math.random() * 0.999;
  },
  streak(x, y, z, vx, vy, vz, life, len, w, r, g, b, grav = 0, bounce = 0) {
    let i; if (this.sn >= MAXS) i = (Math.random() * MAXS) | 0; else i = this.sn++;
    const S = this.S; S.x[i] = x; S.y[i] = y; S.z[i] = z; S.vx[i] = vx; S.vy[i] = vy; S.vz[i] = vz; S.life[i] = 0; S.max[i] = life; S.len[i] = len; S.w[i] = w; S.r[i] = r; S.g[i] = g; S.b[i] = b; S.grav[i] = grav; S.bounce[i] = bounce;
    return i;
  },
  light(p, color, intensity, range, dur) {
    let best = this.lights[0]; for (const l of this.lights) { if (l.userData.t >= l.userData.dur) { best = l; break; } if (l.userData.dur - l.userData.t < best.userData.dur - best.userData.t) best = l; }
    best.position.copy(p); best.color.setHex(color); best.distance = range; best.userData.t = 0; best.userData.dur = dur; best.userData.peak = intensity; best.intensity = intensity;
  },
  shake(p, strength, radius = 400) { if (this.onShake) { const d = p.distanceTo(G.camera.position); this.onShake(strength * sat(1 - d / radius) ** 2); } },

  // ---------- recipes ----------
  smoke(p, v, size, life, dark = 0.5, alpha = 0.6, em = 0) { const c = lerp(0.62, 0.035, dark); this.spawn(T_SMOKE, p.x, p.y, p.z, v.x, v.y, v.z, size, size * 2.6, life, c, c * 0.98, c * 0.95, alpha, em, 0.9, -0.5); },
  flame(p, v, size, life) { this.spawn(T_FIRE, p.x, p.y, p.z, v.x + rndS(0.5), v.y + 1.5, v.z + rndS(0.5), size, size * 1.7, life, 1, 1, 1, 0.9, 0.3, 1.2, -2.5); },
  dust(x, y, z, vx, vy, vz, size, life, alpha = 0.35, tint = 0) { const k = rnd(0.85, 1.1); this.spawn(T_DUST, x, y, z, vx, vy, vz, size, size * 3.2, life, lerp(0.42, 0.75, tint) * k, lerp(0.34, 0.74, tint) * k, lerp(0.24, 0.72, tint) * k, alpha, 0, 1.3, -0.15); },
  dustRing(x, y, z, r, n, speed = 7) { for (let i = 0; i < n; i++) { const a = rnd(TAU), c = Math.cos(a), s = Math.sin(a); this.dust(x + c * r * 0.3, y + 0.4, z + s * r * 0.3, c * speed * rnd(0.6, 1.2), rnd(0.3, 1.6), s * speed * rnd(0.6, 1.2), rnd(1.5, 2.6), rnd(1.6, 3.2), 0.3); } },
  sparks(p, dir, n, speed = 16, col = 0) {
    for (let i = 0; i < n; i++) { const vx = dir.x * speed * 0.5 + rndS(speed), vy = dir.y * speed * 0.5 + rnd(-0.2, 1) * speed, vz = dir.z * speed * 0.5 + rndS(speed); this.streak(p.x, p.y, p.z, vx, vy, vz, rnd(0.25, 0.9), 0.05, 0.035, col ? 1.5 : 3.0, col ? 1.5 : 1.6, col ? 1.8 : 0.5, 14, 1); }
  },
  debrisBurst(p, n, size, color, baseVel, speed = 11) {
    _c.setHex(color);
    for (let i = 0; i < n; i++) {
      if (this.D.length >= MAXD) this.D.shift();
      const a = rnd(TAU), e = rnd(0.2, 1.4), sp = speed * rnd(0.3, 1);
      const k = rnd(0.7, 1.15);
      this.D.push({ x: p.x + rndS(size), y: p.y + rnd(size), z: p.z + rndS(size), vx: Math.cos(a) * Math.cos(e) * sp + (baseVel ? baseVel.x * 0.5 : 0), vy: Math.sin(e) * sp + (baseVel ? baseVel.y * 0.5 : 0), vz: Math.sin(a) * Math.cos(e) * sp + (baseVel ? baseVel.z * 0.5 : 0), rx: rnd(TAU), ry: rnd(TAU), rz: rnd(TAU), ax: rndS(8), ay: rndS(8), az: rndS(8), size: size * rnd(0.35, 1), life: rnd(5, 9), r: _c.r * k, g: _c.g * k, b: _c.b * k, rest: false, smoke: false });
    }
  },
  // a big physics chunk (masonry); returns the debris object so callers can tweak it
  chunk(x, y, z, vx, vy, vz, size, color, life = 12, smoke = true) {
    if (this.D.length >= MAXD) this.D.shift(); _c.setHex(color); const k = rnd(0.8, 1.1);
    const d = { x, y, z, vx, vy, vz, rx: rnd(TAU), ry: rnd(TAU), rz: rnd(TAU), ax: rndS(3), ay: rndS(3), az: rndS(3), size, life, r: _c.r * k, g: _c.g * k, b: _c.b * k, rest: false, smoke, big: true };
    this.D.push(d); return d;
  },
  muzzle(p, dir, vel) {
    this.spawn(T_FLASH, p.x + dir.x * 0.6, p.y + dir.y * 0.6, p.z + dir.z * 0.6, vel.x, vel.y, vel.z, rnd(0.8, 1.25), 1.2, 0.05, 1.0, 0.75, 0.35, 1, 0.5, 0, 0);
    if (Math.random() < 0.5) this.spawn(T_SMOKE, p.x + dir.x, p.y + dir.y, p.z + dir.z, vel.x + dir.x * 6 + rndS(1), vel.y + dir.y * 6 + rnd(1), vel.z + dir.z * 6 + rndS(1), 0.3, 1.5, 0.7, 0.6, 0.6, 0.6, 0.25, 0, 2, -0.3);
    this.light(p, 0xffb060, 14, 26, 0.05);
  },
  // cannon round hitting something
  impact(p, kind = 'ground') {
    const y = p.y;
    if (kind === 'water') { for (let i = 0; i < 4; i++) this.spawn(T_SPRAY, p.x + rndS(0.5), L.WATER_Y + 0.3, p.z + rndS(0.5), rndS(1.5), rnd(4, 9), rndS(1.5), 0.5, 2.2, rnd(0.6, 1.1), 0.85, 0.9, 0.95, 0.5, 0, 0.6, 9); return; }
    const stone = kind === 'stone';
    this.spawn(T_FLASH, p.x, y + 0.3, p.z, 0, 0, 0, 1.6, 1.6, 0.07, 1.0, 0.7, 0.3, 1, 0.6, 0, 0);
    for (let i = 0; i < 3; i++) this.dust(p.x + rndS(0.4), y + 0.3, p.z + rndS(0.4), rndS(2.2), rnd(1.5, 5), rndS(2.2), rnd(0.6, 1.1), rnd(1.1, 2.4), 0.42, stone ? 0.6 : 0.1);
    if (Math.random() < 0.35) this.spawn(T_SMOKE, p.x, y + 0.5, p.z, rndS(1), rnd(2, 4), rndS(1), 0.8, 2.6, rnd(1.5, 2.5), 0.1, 0.1, 0.1, 0.4, 0.5, 1, -0.6);
    for (let i = 0; i < 4; i++) this.streak(p.x, y + 0.2, p.z, rndS(9), rnd(3, 14), rndS(9), rnd(0.2, 0.5), 0.05, 0.03, 3, 1.7, 0.5, 16, 0);
    if (Math.random() < 0.6) this.debrisBurst(p, 1 + (Math.random() * 2 | 0), stone ? 0.28 : 0.16, stone ? 0x8a8378 : 0x3a2c1c, null, 8);
    if (!stone) terrain.scorch(p.x, p.z, rnd(1.0, 1.7), 0.75);
  },
  // scale 1 = rocket, 2+ = big
  explosion(p, scale = 1, o = {}) {
    const g = terrain.height(p.x, p.z); const nearGround = p.y - g < 5 * scale; const y = Math.max(p.y, g + 0.3);
    this.spawn(T_FLASH, p.x, y + 1, p.z, 0, 0, 0, 12 * scale, 12 * scale, 0.15, 1.0, 0.82, 0.5, 1, 1, 0, 0);
    this.spawn(T_FLASH, p.x, y + 1, p.z, 0, 0, 0, 26 * scale, 26 * scale, 0.22, 1.0, 0.55, 0.2, 0.16, 0.3, 0, 0);
    this.light(_v.set(p.x, y + 2.5 * scale, p.z), 0xff9a40, 260 * scale, 80 * scale, 0.35);
    const nf = Math.round(11 * Math.sqrt(scale));
    for (let i = 0; i < nf; i++) { const a = rnd(TAU), e = rnd(0.1, 1.5), sp = rnd(3, 10) * scale; this.spawn(T_FIRE, p.x + rndS(scale), y + rnd(scale), p.z + rndS(scale), Math.cos(a) * Math.cos(e) * sp, Math.sin(e) * sp + 2, Math.sin(a) * Math.cos(e) * sp, rnd(1.4, 2.4) * scale, rnd(3.2, 4.6) * scale, rnd(0.45, 0.9) * (0.7 + 0.3 * scale), 1, 1, 1, 1, 0.6, 2.2, -2); }
    const ns = Math.round(12 * Math.sqrt(scale));
    for (let i = 0; i < ns; i++) { const a = rnd(TAU), sp = rnd(1, 5) * scale; const c = rnd(0.03, 0.12); this.spawn(T_SMOKE, p.x + rndS(1.5 * scale), y + rnd(2 * scale), p.z + rndS(1.5 * scale), Math.cos(a) * sp, rnd(3, 8) * Math.sqrt(scale), Math.sin(a) * sp, rnd(1.6, 2.6) * scale, rnd(5, 8) * scale, rnd(3.5, 7) * (0.8 + 0.2 * scale), c, c, c, rnd(0.55, 0.8), 1.2, 0.9, -1.1); }
    if (nearGround) {
      const nd = Math.round(12 * Math.sqrt(scale));
      for (let i = 0; i < nd; i++) { const a = i / nd * TAU + rnd(0.3), sp = rnd(8, 15) * Math.sqrt(scale); this.dust(p.x + Math.cos(a) * scale, g + 0.5, p.z + Math.sin(a) * scale, Math.cos(a) * sp, rnd(0.5, 3), Math.sin(a) * sp, rnd(1.6, 2.6) * scale, rnd(2.5, 4.5), 0.4); }
      for (let i = 0; i < 5 * scale; i++) this.dust(p.x + rndS(scale), g + 1, p.z + rndS(scale), rndS(3), rnd(8, 18) * Math.sqrt(scale), rndS(3), rnd(1.2, 2) * scale, rnd(2, 3.5), 0.5); // dirt column
      this.spawn(T_RING, p.x, g + 0.25, p.z, 0, 0, 0, 5 * scale, 22 * scale, 0.5, 0.85, 0.8, 0.7, 0.5, 0, 0, 0);
      if (o.scorch !== false) terrain.scorch(p.x, p.z, 5.5 * scale * rnd(0.9, 1.15), 1);
    }
    const nsp = Math.round(28 * scale);
    for (let i = 0; i < nsp; i++) { const a = rnd(TAU), e = rnd(0.1, 1.5), sp = rnd(12, 34) * Math.sqrt(scale); this.streak(p.x, y + 0.5, p.z, Math.cos(a) * Math.cos(e) * sp, Math.sin(e) * sp, Math.sin(a) * Math.cos(e) * sp, rnd(0.5, 1.4), 0.06, 0.05, 3.2, 1.6, 0.45, 15, 1); }
    this.debrisBurst(_v.set(p.x, y, p.z), o.debris !== undefined ? o.debris : Math.round(6 * scale), 0.3 * Math.sqrt(scale), o.debrisColor || 0x3b2e20, null, 15 * Math.sqrt(scale));
    if (o.fire) this.emitters.push({ x: p.x, y: g + 0.4, z: p.z, life: o.fireLife || 30, size: 1.3 * scale, rate: 14, t: 0, smoke: 1 });
    this.shake(p, 0.9 * scale, 350 * Math.sqrt(scale));
  },
  flak(p) {
    this.spawn(T_FLASH, p.x, p.y, p.z, 0, 0, 0, 14, 14, 0.1, 1, 0.85, 0.6, 1, 1, 0, 0);
    this.light(p, 0xffc080, 200, 90, 0.2);
    for (let i = 0; i < 14; i++) { const d = _v.set(rndS(1), rndS(1), rndS(1)).normalize(); const sp = rnd(4, 16); const c = rnd(0.02, 0.07); this.spawn(T_SMOKE, p.x + d.x * 2, p.y + d.y * 2, p.z + d.z * 2, d.x * sp, d.y * sp, d.z * sp, rnd(2.5, 4), rnd(8, 12), rnd(5, 9), c, c, c, 0.8, 0.5, 2.2, -0.1); }
    for (let i = 0; i < 40; i++) { const d = _v.set(rndS(1), rndS(1), rndS(1)).normalize(); const sp = rnd(30, 70); this.streak(p.x, p.y, p.z, d.x * sp, d.y * sp, d.z * sp, rnd(0.3, 0.7), 0.08, 0.05, 2.5, 1.5, 0.6, 9, 0); }
    this.shake(p, 1.1, 260);
  },
  // collapsing masonry dust
  dustCloud(p, radius, n, rise = 3) {
    for (let i = 0; i < n; i++) { const a = rnd(TAU), r = rnd(radius), c = rnd(0.42, 0.6); this.spawn(T_DUST, p.x + Math.cos(a) * r, p.y + rnd(radius * 0.6), p.z + Math.sin(a) * r, Math.cos(a) * rnd(1, 6), rnd(0.3, rise), Math.sin(a) * rnd(1, 6), rnd(3, 5), rnd(10, 16), rnd(5, 10), c, c * 0.93, c * 0.82, rnd(0.45, 0.7), 0, 0.7, -0.2); }
  },
  splash(x, z, scale = 1) { for (let i = 0; i < 10 * scale; i++) this.spawn(T_SPRAY, x + rndS(scale), L.WATER_Y + 0.3, z + rndS(scale), rndS(3 * scale), rnd(6, 16) * Math.sqrt(scale), rndS(3 * scale), 0.8 * scale, 3.5 * scale, rnd(0.8, 1.6), 0.85, 0.9, 0.95, 0.55, 0, 0.6, 9); },
  addFire(x, y, z, size, life, smoke = 1, permanent = false, washable = false) { const e = { x, y, z, life, size, rate: 12, t: 0, smoke, permanent, washable, on: true, sup: 0 }; this.emitters.push(e); return e; },

  // ---------- update ----------
  update(dt, camera) {
    const P = this.P; const H = G.U.uHeli.value; const wash = H.w;
    // emitters
    for (let k = this.emitters.length - 1; k >= 0; k--) {
      const e = this.emitters[k]; if (!e.permanent) { e.life -= dt; if (e.life <= 0) { this.emitters.splice(k, 1); continue; } }
      if (!e.on) continue;
      const dx = e.x - camera.position.x, dz = e.z - camera.position.z; const far = dx * dx + dz * dz > 900 * 900;
      // rotor wash suppresses washable smoke
      let sup = 0; if (e.washable) { const hx = e.x - H.x, hz = e.z - H.z, hy = H.y - e.y; const d = Math.hypot(hx, hz); if (d < 45 && hy < 60 && hy > -5) sup = wash * sat(1 - d / 45); e.sup = sup; }
      const fade = e.permanent ? 1 : sat(e.life / 6);
      e.t += dt * e.rate * (far ? 0.4 : 1);
      while (e.t > 1) {
        e.t -= 1; const s = e.size;
        if (Math.random() < fade) this.spawn(T_FIRE, e.x + rndS(s * 0.5), e.y + rnd(s * 0.4), e.z + rndS(s * 0.5), rndS(0.6), rnd(2, 4), rndS(0.6), s * rnd(0.6, 1), s * rnd(1.2, 1.9), rnd(0.5, 0.9), 1, 1, 1, 0.9, 0.35, 1, -2.5);
        if (e.smoke > 0 && Math.random() < 0.5 * e.smoke) { const c = rnd(0.04, 0.13); this.spawn(T_SMOKE, e.x + rndS(s * 0.5), e.y + s * 1.3, e.z + rndS(s * 0.5), rndS(0.8) + 1.2, rnd(3.5, 6), rndS(0.8) + 0.3, s * rnd(1.0, 1.6), s * rnd(5, 8) * e.smoke, rnd(6, 11) * (0.6 + 0.4 * e.smoke) * (1 - sup * 0.8), c, c, c, rnd(0.5, 0.75), 0.5, 0.25, -0.9); }
      }
      if (Math.random() < dt * 3 * fade) this.streak(e.x + rndS(e.size * 0.5), e.y + e.size, e.z + rndS(e.size * 0.5), rndS(2), rnd(3, 8), rndS(2), rnd(0.6, 1.6), 0.03, 0.03, 3, 1.4, 0.4, -1, 0);
    }
    // rotor wash dust / spray
    if (wash > 0.05) {
      this.washT += dt * (26 * wash);
      while (this.washT > 1) {
        this.washT -= 1; const a = rnd(TAU), r = rnd(4, 11), c = Math.cos(a), s = Math.sin(a); const x = H.x + c * r, z = H.z + s * r; const gy = terrain.height(x, z);
        if (gy < L.WATER_Y) this.spawn(T_SPRAY, x, L.WATER_Y + 0.2, z, c * rnd(8, 14), rnd(1, 3), s * rnd(8, 14), 1.2, 4.5, rnd(0.8, 1.5), 0.85, 0.9, 0.95, 0.28 * wash, 0, 1.4, 2);
        else this.dust(x, gy + 0.3, z, c * rnd(9, 16) * wash, rnd(0.5, 2.5), s * rnd(9, 16) * wash, rnd(1.4, 2.2), rnd(1.6, 3.0), 0.26 * wash);
      }
    }
    // integrate particles
    const cx = camera.position.x, cy = camera.position.y, cz = camera.position.z;
    let n = this.n;
    for (let i = 0; i < n; i++) {
      P.life[i] += dt;
      if (P.life[i] >= P.max[i]) { // swap-remove
        n--; if (i !== n) { for (const k in P) P[k][i] = P[k][n]; } i--; continue;
      }
      const d = Math.exp(-P.drag[i] * dt); P.vx[i] *= d; P.vz[i] *= d; P.vy[i] = P.vy[i] * d - P.grav[i] * dt;
      const t = P.type[i];
      if (wash > 0.05 && (t === T_SMOKE || t === T_DUST)) { // downwash pushes smoke out and away
        const hx = P.x[i] - H.x, hz = P.z[i] - H.z, hy = H.y - P.y[i]; const dd = hx * hx + hz * hz;
        if (dd < 1600 && hy > -6 && hy < 55) { const dl = Math.sqrt(dd) + 0.5; const f = wash * (1 - dl / 40) * 38 * dt; P.vx[i] += hx / dl * f; P.vz[i] += hz / dl * f; P.vy[i] -= f * 0.25 * (hy > 4 ? 1 : -0.5); P.life[i] += dt * wash * 1.2 * (1 - dl / 40); }
      }
      P.x[i] += (P.vx[i] + (t === T_SMOKE ? 1.6 : t === T_DUST ? 1.0 : 0)) * dt; P.y[i] += P.vy[i] * dt; P.z[i] += (P.vz[i] + (t === T_SMOKE ? 0.5 : 0)) * dt; // gentle wind
      P.rot[i] += P.rv[i] * dt;
      const dx = P.x[i] - cx, dy = P.y[i] - cy, dz = P.z[i] - cz; P.dist[i] = dx * dx + dy * dy + dz * dz;
    }
    this.n = n;
    // sort back-to-front
    const ord = this.order; for (let i = 0; i < n; i++) ord[i] = i;
    const dist = P.dist; ord.subarray(0, n).sort((a, b) => dist[b] - dist[a]);
    const ap = this.aPos.array, ac = this.aCol.array, am = this.aMisc.array;
    for (let k = 0; k < n; k++) {
      const i = ord[k], o = k * 4; const age = P.life[i] / P.max[i]; const t = P.type[i];
      const grow = t === T_RING || t === T_FLASH ? age : 1 - (1 - age) * (1 - age);
      ap[o] = P.x[i]; ap[o + 1] = P.y[i]; ap[o + 2] = P.z[i]; ap[o + 3] = P.s0[i] + (P.s1[i] - P.s0[i]) * grow;
      ac[o] = P.r[i]; ac[o + 1] = P.g[i]; ac[o + 2] = P.b[i]; ac[o + 3] = P.a[i];
      am[o] = P.rot[i]; am[o + 1] = age; am[o + 2] = t; am[o + 3] = Math.floor(clamp(P.em[i], 0, 3.9) * 16) + P.seed[i];
    }
    this.aPos.needsUpdate = this.aCol.needsUpdate = this.aMisc.needsUpdate = true;
    this.aPos.clearUpdateRanges && (this.aPos.clearUpdateRanges(), this.aPos.addUpdateRange(0, n * 4), this.aCol.clearUpdateRanges(), this.aCol.addUpdateRange(0, n * 4), this.aMisc.clearUpdateRanges(), this.aMisc.addUpdateRange(0, n * 4));
    this.pMesh.geometry.instanceCount = n;

    // streaks
    const S = this.S; let sn = this.sn; const a = this.sA.array, b = this.sB.array, c = this.sC.array;
    for (let i = 0; i < sn; i++) {
      S.life[i] += dt;
      if (S.life[i] >= S.max[i]) { sn--; if (i !== sn) for (const k in S) S[k][i] = S[k][sn]; i--; continue; }
      S.vy[i] -= S.grav[i] * dt; S.x[i] += S.vx[i] * dt; S.y[i] += S.vy[i] * dt; S.z[i] += S.vz[i] * dt;
      if (S.bounce[i] && S.vy[i] < 0) { const gy = terrain.height(S.x[i], S.z[i]); if (S.y[i] < gy) { S.y[i] = gy; S.vy[i] *= -0.35; S.vx[i] *= 0.6; S.vz[i] *= 0.6; } }
      const o = i * 4; const sp = Math.hypot(S.vx[i], S.vy[i], S.vz[i]) || 1; const len = Math.max(S.len[i] * sp, 0.15); const age = S.life[i] / S.max[i];
      a[o] = S.x[i]; a[o + 1] = S.y[i]; a[o + 2] = S.z[i]; a[o + 3] = S.w[i];
      b[o] = S.vx[i] / sp * len; b[o + 1] = S.vy[i] / sp * len; b[o + 2] = S.vz[i] / sp * len;
      c[o] = S.r[i]; c[o + 1] = S.g[i]; c[o + 2] = S.b[i]; c[o + 3] = 1 - age * age;
    }
    this.sn = sn; this.sA.needsUpdate = this.sB.needsUpdate = this.sC.needsUpdate = true; this.sMesh.geometry.instanceCount = sn;

    // debris
    const D = this.D; const dm = this.dMesh; const col = dm.instanceColor.array;
    for (let i = D.length - 1; i >= 0; i--) {
      const d = D[i]; d.life -= dt; if (d.life <= 0) { D.splice(i, 1); continue; }
      if (!d.rest) {
        d.vy -= 9.81 * dt; d.x += d.vx * dt; d.y += d.vy * dt; d.z += d.vz * dt; d.rx += d.ax * dt; d.ry += d.ay * dt; d.rz += d.az * dt;
        const gy = terrain.height(d.x, d.z) + d.size * 0.4;
        if (d.y < gy) {
          d.y = gy; const sp = Math.hypot(d.vx, d.vy, d.vz);
          if (d.big && sp > 6) { this.dust(d.x, gy, d.z, rndS(2), rnd(1, 3), rndS(2), d.size * 1.2, rnd(1.5, 3), 0.4, 0.5); if (d.onHit) d.onHit(d); }
          if (sp < 2.2) { d.rest = true; } else { terrain.normal(d.x, d.z, _v); const vn = d.vx * _v.x + d.vy * _v.y + d.vz * _v.z; d.vx = (d.vx - 1.45 * vn * _v.x) * 0.55; d.vy = (d.vy - 1.45 * vn * _v.y) * 0.55; d.vz = (d.vz - 1.45 * vn * _v.z) * 0.55; d.ax *= 0.6; d.ay *= 0.6; d.az *= 0.6; }
        } else if (d.smoke && Math.random() < dt * 14) { const cc = 0.5; this.spawn(T_DUST, d.x, d.y, d.z, 0, 0.5, 0, d.size * 0.8, d.size * 2.5, rnd(1, 2), cc, cc * 0.93, cc * 0.82, 0.35, 0, 1, 0); }
      }
    }
    const nd = D.length; dm.count = nd;
    for (let i = 0; i < nd; i++) { const d = D[i]; const s = d.size * Math.min(1, d.life * 2); _q.setFromEuler(_eul.set(d.rx, d.ry, d.rz)); _m.compose(_v.set(d.x, d.y, d.z), _q, _s.set(s, s, s)); _m.toArray(dm.instanceMatrix.array, i * 16); col[i * 3] = d.r; col[i * 3 + 1] = d.g; col[i * 3 + 2] = d.b; }
    dm.instanceMatrix.needsUpdate = true; dm.instanceColor.needsUpdate = true;

    // lights
    for (const l of this.lights) { const u = l.userData; if (u.t < u.dur) { u.t += dt; const k = Math.max(0, 1 - u.t / u.dur); l.intensity = u.peak * k * k; } else l.intensity = 0; }
  },
};
const _eul = new THREE.Euler();
