// Siege Wing — the helicopter: flight model (Punishing / Stabilized), subsystem damage, model binding, cameras
import * as THREE from 'three';
import { G, V3, clamp, lerp, smooth, damp, sat, DEG, TAU, wrapPi, rnd, rndS } from './core.js';
import { terrain, L } from './terrain.js';
import { world } from './world.js';
import { input, settings } from './input.js';
import { fx } from './fx.js';
import { audio } from './audio.js';

const GRAV = 9.81;
const _v = new V3(), _v2 = new V3(), _v3 = new V3(), _q = new THREE.Quaternion(), _q2 = new THREE.Quaternion(), _e = new THREE.Euler(0, 0, 0, 'YXZ'), _m = new THREE.Matrix4();
const UP = new V3(0, 1, 0), ZAX = new V3(0, 0, 1);

export const SUBS = ['tail', 'engine', 'hyd', 'rotor', 'canopy', 'weapons'];
export const SUB_NAMES = { tail: 'TAIL ROTOR', engine: 'ENGINE', hyd: 'HYDRAULICS', rotor: 'MAIN ROTOR', canopy: 'CANOPY', weapons: 'WEAPONS' };

export const heli = {
  // --- state ---
  pos: new V3(), vel: new V3(), q: new THREE.Quaternion(), w: new V3(),   // w = body rates (x pitch, y yaw, z roll)
  T: 1, coll: 0, rpm: 1, load: 0.5, vrs: 0, agl: 100, onGround: false, onPad: false, groundTime: 0,
  yaw: 0, pitch: 0, roll: 0, tilt: 0, speed: 0, hspeed: 0, vs: 0, gForce: 1,
  cmdP: 0, cmdR: 0, cmdY: 0, stickP: 0, stickR: 0, idleT: 0, keyRoll: 0, yawKey: 0,
  hull: 100, sub: { tail: 100, engine: 100, hyd: 100, rotor: 100, canopy: 100, weapons: 100 },
  state: 'fly', crashT: 0, tumble: false, gunner: false, cockpit: false, freelook: false,
  aimYaw: 0, aimPitch: 0, aimDir: new V3(0, 0, -1), gunHeatKick: 0,
  fwd: new V3(0, 0, -1), up: new V3(0, 1, 0), right: new V3(1, 0, 0),
  gearY: 1.75, rotorY: 2.2, rotorR: 7.3, eye: new V3(0, 0.92, -1.91),
  shake: 0, lastHitT: -10, lastHitKind: '', hitFlash: 0, washK: 0,
  model: null, nodes: {}, parts: [], partsLost: 0,
  cam: { pos: new V3(), yaw: 0, lag: new V3(), flYaw: 0, flPitch: 0, fov: 70, roll: 0, inited: false, shakeT: 0, aimBlend: 0, look: new V3() },

  reset(x, y, z, yaw, speed = 0) {
    this.pos.set(x, y, z); this.q.setFromEuler(_e.set(0, yaw, 0)); this.vel.set(-Math.sin(yaw) * speed, 0, -Math.cos(yaw) * speed); this.w.set(0, 0, 0);
    this.T = 1; this.rpm = 1; this.vrs = 0; this.onGround = false; this.onPad = false; this.hull = 100; for (const s of SUBS) this.sub[s] = 100;
    this.state = 'fly'; this.crashT = 0; this.tumble = false; this.cmdP = this.cmdR = this.cmdY = 0; this.stickP = this.stickR = 0; this.shake = 0; this.hitFlash = 0;
    this.yaw = yaw; this.pitch = 0; this.roll = 0; this.cam.inited = false; this.gunner = false; this.partsLost = 0;
    for (const p of this.parts) p.visible = true;
    if (this.model) { this.model.visible = true; this._char(false); }
    if (this.crackCtx) { this.crackCtx.clearRect(0, 0, 1024, 512); this.crackTex.needsUpdate = true; this.crackN = 0; }
    this._derive();
  },
  _derive() {
    this.fwd.set(0, 0, -1).applyQuaternion(this.q); this.up.set(0, 1, 0).applyQuaternion(this.q); this.right.set(1, 0, 0).applyQuaternion(this.q);
    _e.setFromQuaternion(this.q, 'YXZ'); this.yaw = _e.y; this.pitch = _e.x; this.roll = _e.z;
    this.tilt = Math.acos(clamp(this.up.y, -1, 1));
    this.speed = this.vel.length(); this.hspeed = Math.hypot(this.vel.x, this.vel.z); this.vs = this.vel.y;
    this.agl = this.pos.y - this.gearY - terrain.height(this.pos.x, this.pos.z);
  },
  // subsystem health factor 0 (dead) .. 1 (fine); stabilized halves the effect
  dmgK(s) { const k = 1 - sat(this.sub[s] / 100 / 0.75); return settings.mode === 'stabilized' ? k * 0.5 : settings.mode === 'assault' ? k * 0.8 : k; },
  degraded(s) { return this.sub[s] < 50; },

  // ----- damage -----
  hit(o) { // { hull, sub, subDmg, kind, dir }
    if (this.state !== 'fly') return;
    this.hull -= o.hull || 0;
    let s = o.sub;
    if (s === 'any') s = SUBS[(Math.random() * SUBS.length) | 0];
    if (s && o.subDmg) {
      const before = this.sub[s]; this.sub[s] = Math.max(0, before - o.subDmg);
      if (before >= 50 && this.sub[s] < 50) G.events.dispatchEvent(new CustomEvent('subDegraded', { detail: s }));
      if (s === 'canopy') this._crack(o.subDmg);
    }
    this.lastHitT = G.time; this.lastHitKind = o.kind || ''; this.hitFlash = Math.min(1, this.hitFlash + (o.hull || 1) * 0.06 + 0.15);
    this.shake = Math.min(1.6, this.shake + (o.hull || 1) * 0.07 + 0.08);
    // knock the airframe
    const k = (o.hull || 1) * 0.012; this.w.x += rndS(k); this.w.z += rndS(k); this.w.y += rndS(k * 0.6);
    // shed panels as hull drops
    const want = Math.floor((100 - this.hull) / 100 * (this.parts.length + 1));
    while (this.partsLost < want && this.partsLost < this.parts.length) { const p = this.parts[this.partsLost++]; if (p.visible) { p.visible = false; p.getWorldPosition(_v); fx.debrisBurst(_v, 3, 0.5, 0x3a3f33, this.vel); fx.sparks(_v, UP, 10); } }
    if (this.hull <= 0) this.kill('shot');
  },
  kill(cause) {
    if (this.state !== 'fly') return;
    this.state = 'crashing'; this.crashT = 0; this.cause = cause; this.hull = 0;
    audio.play('crashSpin'); G.events.dispatchEvent(new CustomEvent('heliDown', { detail: cause }));
  },
  explode(cause) {
    if (this.state === 'dead') return;
    if (this.state === 'fly') { this.cause = cause; this.hull = 0; G.events.dispatchEvent(new CustomEvent('heliDown', { detail: cause })); }
    this.state = 'dead'; this.crashT = 0; this.hull = 0;
    fx.explosion(this.pos, 2.4, { fire: true, debris: 26, debrisColor: 0x2c3028 });
    terrain.scorch(this.pos.x, this.pos.z, 14, 1);
    audio.play('crash'); this.shake = 2.5;
    this._char(true); this.rpm = 0; this.wreckDown = false; this.vel.multiplyScalar(0.45); this.w.set(rndS(2.2), rndS(1.5), rndS(2.2));
    G.events.dispatchEvent(new CustomEvent('heliDestroyed', { detail: this.cause }));
  },
  // burnt-out wreck look (restored on reset)
  _char(on) {
    if (!this.model || !!this.charred === on) return; this.charred = on;
    this.model.traverse(o => { if (!o.isMesh) return; for (const m of Array.isArray(o.material) ? o.material : [o.material]) { if (!m || !m.color) continue;
      if (on) { if (!m.userData.c0) { m.userData.c0 = m.color.clone(); m.userData.e0 = m.emissiveIntensity; } m.color.copy(m.userData.c0).multiplyScalar(0.09); if (m.emissiveIntensity !== undefined) m.emissiveIntensity = 0; }
      else if (m.userData.c0) { m.color.copy(m.userData.c0); if (m.userData.e0 !== undefined) m.emissiveIntensity = m.userData.e0; } } });
  },
  _crack(amount) {
    if (!this.crackCtx) return; const c = this.crackCtx; const n = Math.max(1, Math.round(amount / 6));
    for (let k = 0; k < n; k++) {
      const x = rnd(60, 964), y = rnd(40, 472); c.strokeStyle = 'rgba(235,245,255,0.85)'; c.fillStyle = 'rgba(220,235,255,0.25)';
      c.beginPath(); c.arc(x, y, rnd(3, 7), 0, TAU); c.fill();
      const rays = 5 + (Math.random() * 6 | 0);
      for (let i = 0; i < rays; i++) { let a = rnd(TAU), px = x, py = y; c.lineWidth = rnd(0.6, 1.8); c.beginPath(); c.moveTo(px, py); const segs = 3 + (Math.random() * 5 | 0); for (let s = 0; s < segs; s++) { a += rndS(0.5); const l = rnd(8, 46); px += Math.cos(a) * l; py += Math.sin(a) * l; c.lineTo(px, py); } c.stroke(); }
      c.lineWidth = 0.7; for (let r = 1; r < 3; r++) { c.beginPath(); for (let i = 0; i <= 10; i++) { const a = i / 10 * TAU, rr = r * rnd(12, 20); const X = x + Math.cos(a) * rr, Y = y + Math.sin(a) * rr; i ? c.lineTo(X, Y) : c.moveTo(X, Y); } c.stroke(); }
    }
    this.crackTex.needsUpdate = true; audio.play('glassCrack');
  },
  repair(s) { this.sub[s] = 100; if (s === 'canopy' && this.crackCtx) { this.crackCtx.clearRect(0, 0, 1024, 512); this.crackTex.needsUpdate = true; } },

  // ----- simulation -----
  update(dt) {
    const stab = settings.mode === 'stabilized';
    const m = input.mouse();
    const wasGunner = this.gunner;
    this.gunner = this.state === 'fly' && input.down('gunner');
    this.freelook = input.down('freelook') && !this.gunner;
    if (input.pressed('view')) this.cockpit = !this.cockpit;
    const sens = 0.0021 * settings.sens;
    let mx = m.dx, my = m.dy * (settings.invertY ? -1 : 1);
    if (this.gunner) {
      if (!wasGunner) { this.aimYaw = this.yaw; this.aimPitch = clamp(this.pitch - 5 * DEG, -70 * DEG, 20 * DEG); }
      const zoomK = this.cam.fov / 70;
      const as = sens / settings.sens * (settings.aimSens || 1) * 0.75 * zoomK; this.aimYaw -= mx * as; this.aimPitch = clamp(this.aimPitch - my * as, -85 * DEG, 40 * DEG);
      mx = 0; my = 0;
    } else if (this.freelook) {
      this.cam.flYaw = clamp(this.cam.flYaw - mx * sens, -2.8, 2.8); this.cam.flPitch = clamp(this.cam.flPitch - my * sens, -1.2, 1.2); mx = 0; my = 0;
    }
    if (!this.freelook) { const k = Math.exp(-dt / 0.13); this.cam.flYaw *= k; this.cam.flPitch *= k; }
    if (this.state === 'fly') {
      // accumulate mouse into command buffers
      const mouseYaw = settings.mouseX === 'yaw';
      if (stab) {
        this.stickP = clamp(this.stickP + my * sens * 0.9, -30 * DEG, 30 * DEG);
        if (!mouseYaw) this.stickR = clamp(this.stickR - mx * sens * 0.9, -30 * DEG, 30 * DEG); else this.cmdY = clamp(this.cmdY - mx * sens, -0.35, 0.35);
        if (mx === 0 && my === 0) this.idleT += dt; else this.idleT = 0;
      } else {
        this.cmdP = clamp(this.cmdP + my * sens, -0.35, 0.35);
        if (!mouseYaw) this.cmdR = clamp(this.cmdR - mx * sens, -0.35, 0.35); else this.cmdY = clamp(this.cmdY - mx * sens, -0.35, 0.35);
      }
    }
    const N = Math.max(1, Math.ceil(dt / (1 / 120))); const h = dt / N;
    for (let i = 0; i < N; i++) this._step(h, stab);
    this._derive();
    // aim direction (world)
    if (this.gunner) {
      // clamp to a 60° cone around the nose
      _v.set(-Math.sin(this.aimYaw) * Math.cos(this.aimPitch), Math.sin(this.aimPitch), -Math.cos(this.aimYaw) * Math.cos(this.aimPitch));
      const ang = _v.angleTo(this.fwd);
      if (ang > 60 * DEG) { _q.setFromUnitVectors(this.fwd, _v); _q2.identity().slerp(_q, 60 * DEG / ang); _v.copy(this.fwd).applyQuaternion(_q2); this.aimYaw = Math.atan2(-_v.x, -_v.z); this.aimPitch = Math.asin(clamp(_v.y, -1, 1)); }
      this.aimDir.copy(_v);
    } else {
      // boresight: nose line depressed 5°
      this.aimDir.copy(this.fwd).applyAxisAngle(this.right, -5 * DEG).normalize();
    }
    this.shake = Math.max(0, this.shake - dt * (1.2 + this.shake * 1.5));
    this.hitFlash = Math.max(0, this.hitFlash - dt * 2.5);
    this._visuals(dt);
  },

  _step(dt, stab) {
    const p = this.pos, v = this.vel, q = this.q;
    const up = _v.set(0, 1, 0).applyQuaternion(q);
    const ground = terrain.height(p.x, p.z);
    const agl = p.y - this.gearY - ground;
    const hs = Math.hypot(v.x, v.z);
    const aslt = settings.mode === 'assault';
    const kEng = this.dmgK('engine'), kRot = this.dmgK('rotor'), kHyd = this.dmgK('hyd'), kTail = this.dmgK('tail');

    if (this.state === 'gone') { this.pos.addScaledVector(this.vel, dt); return; }
    if (this.state === 'crashing' || this.state === 'dead') {
      this.crashT += dt;
      if (this.state === 'crashing') {
        // autorotating death spiral
        this.rpm = Math.max(0.35, this.rpm - dt * 0.12);
        this.w.y += (3.6 - this.w.y) * dt * 1.2; this.w.x += (0.25 * Math.sin(this.crashT * 2.1) - this.w.x) * dt; this.w.z += (0.3 * Math.cos(this.crashT * 1.7) - this.w.z) * dt;
        v.addScaledVector(up, GRAV * 0.55 * dt); v.y -= GRAV * dt; v.multiplyScalar(1 - 0.12 * dt);
        this._integrate(dt);
        const c = world.pointHit(p.x, p.y, p.z, 2.5);
        if (p.y - 1.2 < terrain.height(p.x, p.z) || c || this.crashT > 14) { p.y = Math.max(p.y, terrain.height(p.x, p.z) + 1); this.explode(this.cause); }
      } else if (!this.wreckDown) {
        // the burning hulk falls and comes to rest
        const gy = terrain.height(p.x, p.z) + 1.45;
        v.y -= GRAV * dt; v.multiplyScalar(1 - 0.25 * dt); p.addScaledVector(v, dt); this._integrateRot(dt);
        if (Math.random() < dt * 30) fx.smoke(p, _v3.set(rndS(1.5), 2 + rndS(1), rndS(1.5)), 1.6, 3.2, 0.85, 0.55);
        if (p.y <= gy) {
          p.y = gy; v.set(0, 0, 0); this.w.set(0, 0, 0); this.wreckDown = true;
          fx.addFire(p.x, gy - 0.6, p.z, 3.4, 60, 1.2); fx.dustRing(p.x, gy - 0.9, p.z, 5, 12); terrain.scorch(p.x, p.z, 10, 1);
          audio.play('explSmall', { pos: [p.x, p.y, p.z] });
        }
      }
      return;
    }

    // ---- collective / thrust ----
    const cu = input.axis('collDown', 'collUp');
    let target;
    const maxT = 1.8 * (1 - 0.35 * kEng);
    const cosT = Math.max(up.y, 0.3);
    if (stab) {
      const hoverAssist = this.gunner ? 0 : cu * 10;
      target = clamp((1 + (hoverAssist - v.y) * 0.45) / cosT, 0.15, maxT);
      if (this.onGround && cu <= 0) target = 0.3;
    } else if (aslt) {
      // assault (Delta Force / Battlefield style): W/S command a climb rate, neutral holds altitude, tilt is compensated
      target = clamp((1 + (cu * (cu > 0 ? 13 : 11) - v.y) * 0.34) / cosT, 0.15, maxT);
      if (this.onGround && cu <= 0) target = 0.3;
    } else {
      target = cu > 0 ? maxT : cu < 0 ? 0.22 : Math.min(0.965, maxT);
      if (this.onGround && cu <= 0) target = 0.3;
    }
    const spool = target > this.T ? (stab ? 5 : aslt ? 4.2 : 2.6) : (stab ? 5 : aslt ? 4.2 : 3.4);
    const prevT = this.T; this.T += (target - this.T) * (1 - Math.exp(-spool * dt));
    const dT = (this.T - prevT) / dt;
    // lift modifiers
    let lift = 1;
    lift *= 1 + 0.14 * sat(1 - agl / (this.rotorR * 2)) ** 1.5;            // ground effect
    lift *= 1 + 0.10 * smooth(7, 16, hs);                                   // translational lift
    lift *= 1 - 0.55 * smooth(400, 520, p.y - 24);                          // ceiling
    lift *= 1 - 0.22 * kRot;
    // vortex ring state: steep slow descent into own downwash
    const sinking = !aslt && v.y < -5.5 && hs < 6.5 && this.T > 0.5;
    this.vrs = clamp(this.vrs + (sinking ? dt * 0.42 : -dt * 0.9), 0, 1);
    lift *= 1 - 0.7 * this.vrs * this.vrs;
    const thrust = this.T * GRAV * lift;
    this.load = clamp(this.T * lift / 1.8, 0, 1.2);

    // ---- forces ----
    const ax = up.x * thrust, ay = up.y * thrust - GRAV, az = up.z * thrust;
    // drag in body frame
    _q.copy(q).invert(); const vb = _v2.copy(v).applyQuaternion(_q);
    const dxb = -(0.0050 * vb.x * Math.abs(vb.x) + 0.06 * vb.x), dyb = -(0.0065 * vb.y * Math.abs(vb.y) + 0.06 * vb.y), dzb = -(0.00165 * vb.z * Math.abs(vb.z) + 0.022 * vb.z);
    const drag = _v3.set(dxb, dyb, dzb).applyQuaternion(q);
    v.x += (ax + drag.x) * dt; v.y += (ay + drag.y) * dt; v.z += (az + drag.z) * dt;
    this.gForce = thrust / GRAV;

    // ---- rotation ----
    const tilt = Math.acos(clamp(up.y, -1, 1));
    const tau = 0.075 * (1 + kHyd * 1.3); const maxRate = 90 * DEG * (1 - 0.5 * kHyd);
    let wp, wr, wy;
    const kr = input.axis('rollL', 'rollR'); this.keyRoll = damp(this.keyRoll, kr, 9, dt);
    const ky = input.axis('yawR', 'yawL'); this.yawKey = damp(this.yawKey, ky, 7, dt);
    // yaw: tail authority fades with speed; weathervane; torque coupling
    const authority = (1 - 0.4 * sat(hs / 62)) * (1 - 0.75 * kTail);
    const ks = clamp(settings.keySens || 1, 0.3, 2.5); let yawRate = this.yawKey * 68 * DEG * authority * ks;
    const yBuf = clamp(this.cmdY / 0.09, -65 * DEG, 65 * DEG) * authority; yawRate += yBuf; this.cmdY -= clamp(this.cmdY / 0.09, -65 * DEG, 65 * DEG) * dt;
    const beta = Math.atan2(vb.x, -vb.z); const vane = smooth(6, 30, hs) * (Math.abs(beta) < 2.4 ? 1 : 0.3);
    if (aslt) yawRate += -Math.sin(beta) * vane * 1.1;
    else if (!stab) {
      yawRate += -Math.sin(beta) * vane * 1.5;
      yawRate += -(this.T * lift - 1.0) * 0.36 - clamp(dT, -3, 3) * 0.08;         // torque coupling
    } else yawRate += -Math.sin(beta) * vane * 0.8;
    if (kTail > 0.02) { yawRate += -kTail * 0.9 * (1 - 0.6 * smooth(8, 16, hs)); if (this.sub.tail <= 0 && hs < 11) yawRate += -3.2 * (1 - hs / 11); }
    if (stab) {
      // attitude command: virtual stick recentres when the mouse rests
      if (this.idleT > 0.05) { const k = Math.exp(-dt / 0.2); this.stickP *= k; this.stickR *= k; }
      let tp = this.stickP, tr = this.stickR + (-this.keyRoll) * 28 * DEG;
      tr = clamp(tr, -30 * DEG, 30 * DEG);
      // extra braking when neutral: lean against drift
      if (Math.abs(tp) < 0.03 && Math.abs(tr) < 0.03 && !this.onGround) {
        const fwdH = _v3.set(-Math.sin(this.yaw), 0, -Math.cos(this.yaw)); const vf = v.x * fwdH.x + v.z * fwdH.z, vr = v.x * fwdH.z * -1 + v.z * fwdH.x;
        tp += clamp(vf * 0.022, -0.22, 0.22); tr += clamp(vr * 0.022, -0.22, 0.22);
      }
      _e.setFromQuaternion(q, 'YXZ');
      const g = 6.5 * (1 - 0.5 * kHyd);
      wp = clamp((tp - _e.x) * g, -maxRate, maxRate); wr = clamp((tr - _e.z) * g, -maxRate, maxRate);
      this.w.x = damp(this.w.x, wp, 14, dt); this.w.z = damp(this.w.z, wr, 14, dt); this.w.y = damp(this.w.y, yawRate, 6, dt);
      // integrate in euler space (keeps it rock steady)
      _e.x += this.w.x * dt; _e.z += this.w.z * dt; _e.y += this.w.y * dt; q.setFromEuler(_e);
    } else {
      let auth = 1;
      this.tumble = tilt > 70 * DEG;
      if (this.tumble) auth = 0.35;
      wp = clamp(this.cmdP / tau, -maxRate, maxRate) * auth; this.cmdP -= clamp(this.cmdP / tau, -maxRate, maxRate) * dt;
      wr = clamp(this.cmdR / tau, -maxRate, maxRate) * auth; this.cmdR -= clamp(this.cmdR / tau, -maxRate, maxRate) * dt;
      wr += -this.keyRoll * 78 * DEG * ks * (1 - 0.5 * kHyd) * auth;
      if (aslt) { // light roll self-levelling when hands-off, and a soft attitude limit so it never tumbles
        _e.setFromQuaternion(q, 'YXZ'); const lim = smooth(48 * DEG, 68 * DEG, tilt) * 4.5;
        const idle = Math.abs(this.cmdR) < 0.004 && Math.abs(this.keyRoll) < 0.05 ? 0.8 : 0;
        wr += -_e.z * (idle + lim); wp += -_e.x * lim; this.tumble = false; auth = 1;
      }
      const lam = 1 / tau;
      this.w.x = damp(this.w.x, wp, lam, dt); this.w.z = damp(this.w.z, wr, lam, dt); this.w.y = damp(this.w.y, yawRate, 4.5, dt);
      if (this.tumble) { // past the limit the rotor disc drags it over
        const over = (tilt - 70 * DEG) * 2.2; _q.copy(q).invert(); const ub = _v3.set(0, 1, 0).applyQuaternion(_q); // world up in body frame
        this.w.x += -ub.z * over * dt * 3; this.w.z += ub.x * over * dt * 3;
      }
      // rotor damage: vibration
      if (kRot > 0.05) { const t = G.time * 31; this.w.x += Math.sin(t) * kRot * 0.9 * dt; this.w.z += Math.cos(t * 1.13) * kRot * 0.9 * dt; }
      this._integrateRot(dt);
    }
    if (stab && kRot > 0.05) { /* vibration only visual in stabilized */ }

    // ---- integrate position ----
    p.addScaledVector(v, dt);

    // ---- ground contact ----
    const g2 = terrain.height(p.x, p.z);
    if (p.y - this.gearY <= g2) {
      const vImpact = -v.y, hImpact = Math.hypot(v.x, v.z);
      if (!this.onGround) {
        const total = Math.hypot(vImpact, hImpact * 0.6);
        if (vImpact > 6 || total > 8.5 || tilt > 38 * DEG) { p.y = g2 + this.gearY; this.explode('terrain'); return; }
        audio.play('touchdown', { gain: clamp(0.3 + vImpact / 5, 0.3, 1.3) }); this.shake += vImpact * 0.12;
        if (vImpact > 3) this.hit({ hull: (vImpact - 3) * 5, sub: 'rotor', subDmg: (vImpact - 3) * 6, kind: 'hard landing' });
        fx.dustRing(p.x, g2, p.z, 6, 14);
      }
      this.onGround = true; p.y = g2 + this.gearY; if (v.y < 0) v.y = 0;
      const fr = Math.exp(-3.2 * dt); v.x *= fr; v.z *= fr;
      // settle onto the slope
      terrain.normal(p.x, p.z, _v3); _q.setFromUnitVectors(UP, _v3); _q2.setFromEuler(_e.set(0, this.yaw, 0)); _q.multiply(_q2);
      q.slerp(_q, 1 - Math.exp(-6 * dt)); this.w.x *= 0.8; this.w.z *= 0.8; this.stickP *= 0.9; this.stickR *= 0.9;
      this.groundTime += dt;
    } else if (this.onGround && p.y - this.gearY > g2 + 0.15) { this.onGround = false; this.groundTime = 0; }
    const dPad = Math.hypot(p.x - L.PAD.x, p.z - L.PAD.z);
    this.onPad = this.onGround && dPad < 26 && Math.hypot(v.x, v.z) < 1.5;

    // ---- structure / tree collisions ----
    this._collide();
  },
  _integrateRot(dt) {
    const w = this.w; const ang = Math.hypot(w.x, w.y, w.z) * dt;
    if (ang > 1e-7) { _q.setFromAxisAngle(_v3.set(w.x, w.y, w.z).normalize(), ang); this.q.multiply(_q).normalize(); }
  },
  _integrate(dt) { this._integrateRot(dt); this.pos.addScaledVector(this.vel, dt); },
  _collide() {
    const p = this.pos, q = this.q;
    // rotor disc sample points
    for (let i = 0; i < 9; i++) {
      const a = i / 8 * TAU, r = i === 8 ? 0 : this.rotorR * 0.94;
      _v3.set(Math.cos(a) * r, this.rotorY, Math.sin(a) * r).applyQuaternion(q).add(p);
      const c = world.pointHit(_v3.x, _v3.y, _v3.z);
      if (c || (_v3.y < terrain.height(_v3.x, _v3.z) && !this.onGround)) {
        if (c && c.kind === 'tree' && this.speed < 4 && !c.hard) { continue; }
        fx.sparks(_v3, UP, 30); audio.play('rotorStrike'); fx.debrisBurst(_v3, 8, 0.6, 0x222222, this.vel);
        this.sub.rotor = 0; this.cause = c ? (c.kind === 'tree' ? 'rotor strike: tree' : 'rotor strike: ' + c.kind) : 'rotor strike: terrain';
        if (this.speed > 14 || this.agl < 4) this.explode(this.cause); else { this.kill(this.cause); this.vel.multiplyScalar(0.5); }
        return;
      }
    }
    // hull points
    for (let i = 0; i < HULL_PTS.length; i++) {
      _v3.copy(HULL_PTS[i]).applyQuaternion(q).add(p);
      const c = world.pointHit(_v3.x, _v3.y, _v3.z);
      if (c) {
        if (this.speed > 6) { this.explode('collision: ' + c.kind); return; }
        // slow contact: bounce off and take damage
        const dx = p.x - c.x, dz = p.z - c.z, l = Math.hypot(dx, dz) || 1; this.vel.x = dx / l * 3; this.vel.z = dz / l * 3; this.vel.y = Math.max(this.vel.y, 1);
        this.hit({ hull: 6 + this.speed * 2, sub: 'any', subDmg: 15, kind: 'collision' }); audio.play('hullHit'); return;
      }
    }
  },

  // ----- model -----
  bindModel(root) {
    this.model = root; const n = this.nodes;
    root.traverse(o => {
      n[o.name] = o;
      if (o.isMesh) { o.castShadow = true; o.receiveShadow = true; o.frustumCulled = false; }
      if (/^Part_/.test(o.name)) this.parts.push(o);
    });
    // shuffle part order deterministically
    this.parts.sort((a, b) => (a.name.length * 7 + a.name.charCodeAt(5)) % 5 - (b.name.length * 7 + b.name.charCodeAt(5)) % 5);
    G.scene.add(root);
    const get = (name, fb) => n[name] ? n[name].position : fb;
    if (n.MainRotor) { this.rotorY = n.MainRotor.position.y; }
    root.updateWorldMatrix(true, true); if (n.PilotEye) this.eye.copy(n.PilotEye.getWorldPosition(new V3()));
    this._buildRotorBlur();
    this._buildCrackOverlay();
    // glass
    root.traverse(o => { if (o.isMesh && o.material && /glass/i.test(o.material.name)) { const m = o.material = new THREE.MeshPhysicalMaterial({ color: 0x1a2a2a, roughness: 0.06, metalness: 0.0, transparent: true, opacity: 0.38, envMapIntensity: 1.6, side: THREE.DoubleSide, depthWrite: false }); m.name = 'Glass'; o.renderOrder = 5; o.castShadow = false; this.glass = o; } });
    { const hg = root.getObjectByName('HUDGlass'); if (hg) hg.traverse(o => { if (o.isMesh) o.material = new THREE.MeshPhysicalMaterial({ color: 0xa8d8b8, roughness: 0.05, metalness: 0, transparent: true, opacity: 0.06, envMapIntensity: 0.5, depthWrite: false, side: THREE.DoubleSide }); }); }
    { const cn = root.getObjectByName('Canopy'); if (cn) cn.traverse(o => { if (o.isMesh && o.material && o.material.name === 'Glass') this.glass = o; }); }
  },
  _buildRotorBlur() {
    const n = this.nodes; if (!n.MainRotor) return;
    const mkDisc = (R, blades, hubR) => new THREE.Mesh(new THREE.CircleGeometry(R, 64), new THREE.ShaderMaterial({
      transparent: true, depthWrite: false, side: THREE.DoubleSide, fog: false,
      uniforms: { uA: { value: 0 }, uAlpha: { value: 1 }, uBlades: { value: blades }, uHub: { value: hubR / R }, uSunCol: G.U.uSunCol, uAmbCol: G.U.uAmbCol, uNight: G.U.uNight },
      vertexShader: `varying vec2 vP; void main(){ vP = position.xy; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }`,
      fragmentShader: `varying vec2 vP; uniform float uA, uAlpha, uBlades, uHub; uniform vec3 uSunCol; uniform float uNight;
        void main(){ float r = length(vP) / ${'R'.replace('R', R.toFixed(2))}; if (r > 1.0) discard; float a = atan(vP.y, vP.x) + uA;
          float lobes = 0.5 + 0.5 * cos(a * uBlades); float smear = pow(lobes, 4.0) * 0.5 + 0.17;
          float al = smear * smoothstep(uHub, uHub + 0.08, r) * smoothstep(1.0, 0.93, r) * (0.5 + 0.5 * r);
          float tip = smoothstep(0.93, 0.975, r) * smoothstep(1.0, 0.985, r) * 0.10 * (0.4 + smear);
          vec3 col = vec3(0.035, 0.037, 0.035) + uSunCol * 0.012 + vec3(0.5, 0.42, 0.1) * tip * (0.2 + dot(uSunCol, vec3(0.1)));
          gl_FragColor = vec4(col, (al * 0.8 + tip) * uAlpha); }`,
    }));
    const d = this.rotorDisc = mkDisc(this.rotorR, 4, 0.5); d.rotation.x = -Math.PI / 2; d.renderOrder = 6; d.frustumCulled = false;
    n.MainRotor.parent.add(d); d.position.copy(n.MainRotor.position); d.position.y += 0.12;
    if (n.TailRotor) { const t = this.tailDisc = mkDisc(1.45, 4, 0.15); t.rotation.y = Math.PI / 2; t.renderOrder = 6; n.TailRotor.parent.add(t); t.position.copy(n.TailRotor.position); }
  },
  _buildCrackOverlay() {
    const cv = document.createElement('canvas'); cv.width = 1024; cv.height = 512; this.crackCtx = cv.getContext('2d'); this.crackN = 0;
    this.crackTex = new THREE.CanvasTexture(cv); this.crackTex.colorSpace = THREE.SRGBColorSpace;
    const m = this.crackMesh = new THREE.Mesh(new THREE.PlaneGeometry(1.5, 0.75), new THREE.MeshBasicMaterial({ map: this.crackTex, transparent: true, depthWrite: false, depthTest: false, fog: false, toneMapped: false, opacity: 0.9 }));
    m.renderOrder = 50; m.frustumCulled = false; m.visible = false; G.scene.add(m);
  },

  _visuals(dt) {
    const n = this.nodes; if (!this.model) return;
    this.model.position.copy(this.pos); this.model.quaternion.copy(this.q);
    // rotor vibration when damaged
    const kRot = this.dmgK('rotor'); if (kRot > 0.05 && this.state === 'fly') { this.model.position.x += Math.sin(G.time * 47) * kRot * 0.05; this.model.position.y += Math.sin(G.time * 53) * kRot * 0.06; }
    this.rotA = (this.rotA || 0) + dt * this.rpm * 30; this.tailA = (this.tailA || 0) + dt * this.rpm * 120;
    const blur = sat((this.rpm - 0.3) / 0.4);
    if (n.MainRotor) { n.MainRotor.rotation.y = this.rotA; n.MainRotor.visible = true; setOpacityTree(n.MainRotor, blur > 0.9 ? 0 : 1); }
    if (this.rotorDisc) { this.rotorDisc.visible = blur > 0.02 && this.state !== 'dead'; this.rotorDisc.material.uniforms.uA.value = -this.rotA * 0.13; this.rotorDisc.material.uniforms.uAlpha.value = blur * (this.cockpit ? 0.55 : 1); }
    if (n.TailRotor) { n.TailRotor.rotation.x = this.tailA; setOpacityTree(n.TailRotor, blur > 0.9 || this.sub.tail <= 0 ? 0 : 1); }
    if (this.tailDisc) { this.tailDisc.visible = blur > 0.02 && this.sub.tail > 0; this.tailDisc.material.uniforms.uA.value = this.tailA * 0.1; this.tailDisc.material.uniforms.uAlpha.value = blur; }
    // turret follows the aim direction (in body frame)
    if (n.TurretYaw) {
      _q.copy(this.q).invert(); _v.copy(this.aimDir).applyQuaternion(_q);
      const ty = Math.atan2(-_v.x, -_v.z), tp = Math.asin(clamp(_v.y, -1, 1));
      n.TurretYaw.rotation.y = damp(n.TurretYaw.rotation.y, ty, 14, dt);
      if (n.GunPitch) n.GunPitch.rotation.x = damp(n.GunPitch.rotation.x, tp, 14, dt) ;
    }
    // sticks
    if (n.Cyclic) { n.Cyclic.rotation.x = damp(n.Cyclic.rotation.x, clamp(this.w.x * 0.25, -0.25, 0.25), 10, dt); n.Cyclic.rotation.z = damp(n.Cyclic.rotation.z, clamp(this.w.z * 0.25, -0.25, 0.25), 10, dt); }
    if (n.Collective) n.Collective.rotation.x = damp(n.Collective.rotation.x, (this.T - 1) * 0.35, 8, dt);
    // pilot head hidden from inside
    if (n.PilotHead) n.PilotHead.visible = !this.cockpit;
    if (n.Pilot) n.Pilot.visible = true;
    // gauges
    this._gauges(dt);
    // damage smoke
    if (this.state !== 'dead') {
      const dmg = 1 - this.hull / 100; this._smokeT = (this._smokeT || 0) + dt;
      const eng = this.dmgK('engine');
      const rate = this.state === 'crashing' ? 60 : (dmg > 0.35 ? (dmg - 0.3) * 40 : 0) + eng * 22;
      if (rate > 0 && this._smokeT > 1 / rate) {
        this._smokeT = 0; const src = n.Exhaust_L ? (Math.random() < 0.5 ? n.Exhaust_L : n.Exhaust_R || n.Exhaust_L).getWorldPosition(_v) : _v.copy(this.pos);
        fx.smoke(src, _v2.copy(this.vel).multiplyScalar(0.35).add(_v3.set(rndS(1), 1.5, rndS(1))), rnd(1.4, 2.4), rnd(2.2, 3.6), 0.25 + 0.6 * Math.max(dmg, eng), 0.55);
        if (this.state === 'crashing' || this.hull < 25) fx.flame(src, _v2.copy(this.vel).multiplyScalar(0.6), rnd(1.0, 1.8), 0.35);
      }
    }
    // wash strength for ground effects
    this.washK = this.state === 'dead' ? 0 : this.rpm * sat(1 - this.agl / 45) * (0.5 + this.load * 0.6);
    G.U.uHeli.value.set(this.pos.x, this.pos.y - this.gearY, this.pos.z, this.washK);
  },
  _gauges(dt) {
    const n = this.nodes;
    const rotNode = (o, ang) => { if (!o.userData.rest) { o.userData.rest = o.quaternion.clone(); o.userData.a = 0; } o.userData.a = damp(o.userData.a, ang, 8, dt); o.quaternion.copy(o.userData.rest).multiply(_q.setFromAxisAngle(ZAX, o.userData.a)); };
    const set = (name, v01) => { const o = n[name]; if (o) rotNode(o, lerp(135 * DEG, -135 * DEG, sat(v01))); };
    set('Needle_Speed', this.speed * 3.6 / 320);
    if (n.Needle_Alt) rotNode(n.Needle_Alt, -(((this.pos.y - 24) % 300) / 300) * TAU);
    if (n.Needle_VS) rotNode(n.Needle_VS, -clamp(this.vs / 20, -1, 1) * 135 * DEG);
    set('Needle_RPM', this.rpm * 0.82 + Math.sin(G.time * 9) * 0.004 * (1 + 8 * this.dmgK('rotor')));
    set('Needle_Torque', this.load * 0.85);
    set('Needle_Temp', 0.45 + this.dmgK('engine') * 0.45 + this.load * 0.1);
    if (n.Horizon) { const o = n.Horizon; if (!o.userData.rest) o.userData.rest = o.quaternion.clone(); o.quaternion.copy(o.userData.rest).multiply(_q.setFromEuler(_e.set(-this.pitch, 0, -this.roll, 'XYZ'))); _e.order = 'YXZ'; }
    const blink = (G.time * 3 % 1) < 0.55; const lamp = (name, on) => { const o = n[name]; if (o && o.material) { if (!o.userData.lampInit) { o.material = o.material.clone(); o.userData.lampInit = true; o.userData.col = o.material.emissive.getHex() || o.material.color.getHex(); } o.material.emissive.setHex(on ? (o.userData.col || 0xff2200) : 0x000000); o.material.emissiveIntensity = on ? 4 : 0; } };
    lamp('Warn_Master', (this.hull < 40 || SUBS.some(s => this.degraded(s))) && blink);
    lamp('Warn_Engine', this.degraded('engine')); lamp('Warn_Tail', this.degraded('tail')); lamp('Warn_Hyd', this.degraded('hyd')); lamp('Warn_Rotor', this.degraded('rotor') || this.vrs > 0.3);
  },

  // ----- cameras -----
  updateCamera(dt, camera) {
    const c = this.cam, p = this.pos;
    const sh = this.shake + this.dmgK('rotor') * 0.25 + (this.state === 'fly' ? this.vrs * 0.4 : 0);
    c.shakeT += dt * 38;
    const sx = (Math.sin(c.shakeT * 1.31) + Math.sin(c.shakeT * 2.9 + 1.3) * 0.5) * sh, sy = (Math.sin(c.shakeT * 1.77 + 2) + Math.sin(c.shakeT * 3.3) * 0.5) * sh, sr = Math.sin(c.shakeT * 1.13 + 4) * sh;
    const dead = this.state === 'dead';
    let targetFov;
    if (this.cockpit && !dead && this.state !== 'crashing') {
      // locked to the airframe at the pilot's eye
      c.aimBlend = damp(c.aimBlend, this.gunner ? 1 : 0, 9, dt);
      // gunner mode drops to the chin sight under the nose so the airframe never blocks the view
      const sb = c.aimBlend * c.aimBlend * (3 - 2 * c.aimBlend);
      _v.copy(this.eye).lerp(_v3.set(0, -2.0, -5.6), sb).applyQuaternion(this.q).add(this.model ? this.model.position : p);
      camera.position.copy(_v);
      _q.copy(this.q);
      if (c.aimBlend > 0.001) { _m.lookAt(_v3.set(0, 0, 0), this.aimDir, this.up); _q2.setFromRotationMatrix(_m); _q.slerp(_q2, c.aimBlend); }
      _q2.setFromEuler(_e.set(c.flPitch, c.flYaw, 0)); _q.multiply(_q2);
      camera.quaternion.copy(_q);
      camera.rotateX(sy * 0.006); camera.rotateY(sx * 0.006); camera.rotateZ(sr * 0.006);
      targetFov = lerp(68, 30, c.aimBlend);
      camera.near = 0.08; c.inited = false;
      if (this.crackMesh) { this.crackMesh.visible = this.sub.canopy < 99 && c.aimBlend < 0.4; this.crackMesh.position.copy(_v).addScaledVector(this.fwd, 0.62).addScaledVector(this.up, 0.02); this.crackMesh.quaternion.copy(this.q); }
    } else {
      if (this.crackMesh) this.crackMesh.visible = false;
      camera.near = 0.6;
      const hs = this.hspeed;
      // heading the camera sits behind: nose, swinging toward the velocity at speed
      let ty = this.yaw; if (hs > 8) { const vy = Math.atan2(-this.vel.x, -this.vel.z); ty = this.yaw + wrapPi(vy - this.yaw) * smooth(10, 38, hs) * 0.55; }
      if (!c.inited) { c.yaw = ty; c.lag.set(0, 0, 0); c.aimBlend = 0; }
      c.yaw += wrapPi(ty - c.yaw) * (1 - Math.exp(-3.4 * dt));
      c.aimBlend = damp(c.aimBlend, this.gunner ? 1 : 0, 8, dt);
      c.lag.x = damp(c.lag.x, clamp(this.vel.x * 0.085, -5, 5), 3.5, dt); c.lag.y = damp(c.lag.y, clamp(this.vel.y * 0.12, -3, 3), 3.5, dt); c.lag.z = damp(c.lag.z, clamp(this.vel.z * 0.085, -5, 5), 3.5, dt);
      const yaw = c.yaw + c.flYaw; const pitchK = clamp(this.pitch, -0.7, 0.5);
      const elev = 0.2 + c.flPitch * -1 - pitchK * 0.28; const dist = dead ? 26 : 13.5;
      const ce = Math.cos(elev), se = Math.sin(elev);
      _v.set(p.x + Math.sin(yaw) * ce * dist - c.lag.x, p.y + se * dist + 1.6 - c.lag.y, p.z + Math.cos(yaw) * ce * dist - c.lag.z);
      // gunner: over-the-shoulder along the aim line
      if (c.aimBlend > 0.001) { _v2.set(0, -2.0, -5.6).applyQuaternion(this.q).add(p); _v.lerp(_v2, c.aimBlend * c.aimBlend * (3 - 2 * c.aimBlend)); }   // gunner: the chin sight under the nose, nothing of the airframe in the way
      const minY = terrain.height(_v.x, _v.z) + (c.aimBlend > 0.5 ? 0.4 : 1.6); if (_v.y < minY) _v.y = minY;
      if (!c.inited) { c.pos.copy(_v); c.inited = true; }
      c.pos.lerp(_v, 1 - Math.exp(-(dead ? 1.5 : c.aimBlend > 0.9 ? 60 : 22) * dt));
      camera.position.copy(c.pos);
      // look target
      _v2.copy(p).addScaledVector(_v3.set(-Math.sin(yaw), 0, -Math.cos(yaw)), 14 + hs * 0.12); _v2.y += 1.0 + pitchK * 9;
      if (c.aimBlend > 0.001) { _v3.copy(camera.position).addScaledVector(this.aimDir, 300); _v2.lerp(_v3, c.aimBlend); }
      if (dead) _v2.copy(p);
      c.look.copy(_v2);
      camera.up.set(0, 1, 0); camera.lookAt(_v2);
      c.roll = damp(c.roll, -this.roll * 0.12 * (1 - c.aimBlend), 5, dt);
      camera.rotateZ(c.roll + sr * 0.008); camera.rotateX(sy * 0.007); camera.rotateY(sx * 0.007);
      targetFov = lerp(lerp(56, 68, smooth(8, 62, hs)), 30, c.aimBlend);
    }
    c.fov = damp(c.fov, targetFov, 7, dt);
    if (Math.abs(camera.fov - c.fov) > 0.01) { camera.fov = c.fov; }
    camera.updateProjectionMatrix();
  },
  muzzle(out) { const n = this.nodes.Muzzle; if (n) return n.getWorldPosition(out); return out.copy(this.pos).addScaledVector(this.fwd, 5).addScaledVector(this.up, -1.3); },
  nodePos(name, out, fbx = 0, fby = 0, fbz = 0) { const n = this.nodes[name]; if (n) return n.getWorldPosition(out); return out.set(fbx, fby, fbz).applyQuaternion(this.q).add(this.pos); },
};
const HULL_PTS = [new V3(0, -0.6, -7.2), new V3(0, 0.6, 8.2), new V3(0, -1.6, 0), new V3(2.7, -0.6, -0.5), new V3(-2.7, -0.6, -0.5), new V3(0, 0.3, 3.5)];
function setOpacityTree(o, vis) { o.traverse(c => { if (c.isMesh) c.visible = vis > 0.5; }); }
