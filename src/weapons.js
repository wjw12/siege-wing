// Siege Wing — weapons: 30 mm chin cannon, rocket pods, guided missiles, flares, rearm/repair
import * as THREE from 'three';
import { G, V3, clamp, lerp, sat, rnd, rndS, DEG, TAU } from './core.js';
import { terrain, L } from './terrain.js';
import { world } from './world.js';
import { input } from './input.js';
import { heli, SUBS } from './heli.js';
import { fx } from './fx.js';
import { audio } from './audio.js';
import { crowd } from './crowd.js';
import { castle } from './castle.js';
import { threats } from './threats.js';

const _v = new V3(), _v2 = new V3(), _v3 = new V3(), _d = new V3(), _q = new THREE.Quaternion(), _m = new THREE.Matrix4();
export const WPN = ['CANNON', 'ROCKETS', 'MISSILES'];
const MAX = { cannon: 600, rockets: 38, missiles: 8, flares: 6 };

export const weapons = {
  sel: 0, ammo: { ...MAX }, max: MAX, heat: 0, overheated: false, fireT: 0, rocketT: 0, rocketSide: 0, missileT: 0, flareCd: 0, flareT: 0, flarePos: new V3(),
  jam: { turret: false, podL: false, podR: false }, pending: [], rockets: [], missiles: [], flares: [],
  lock: { target: null, t: 0, locked: false }, ccip: new V3(), ccipValid: false, ccipDist: 0, firing: false,
  shotsFired: 0, rocketsFired: 0, missilesFired: 0, rearmT: 0, repairT: 0, rearming: false, kills: 0,
  init(scene) {
    this.scene = scene;
    // rocket + missile visual pools
    const rg = new THREE.CylinderGeometry(0.06, 0.06, 1.6, 6); rg.rotateX(Math.PI / 2);
    const rm = new THREE.MeshStandardMaterial({ color: 0x3a3d36, roughness: 0.5, metalness: 0.6 });
    this.rocketMesh = new THREE.InstancedMesh(rg, rm, 48); this.rocketMesh.count = 0; this.rocketMesh.frustumCulled = false; scene.add(this.rocketMesh);
    const mg = new THREE.CylinderGeometry(0.09, 0.09, 1.7, 8); mg.rotateX(Math.PI / 2);
    this.missileMesh = new THREE.InstancedMesh(mg, rm, 10); this.missileMesh.count = 0; this.missileMesh.frustumCulled = false; scene.add(this.missileMesh);
  },
  reset() {
    this.ammo = { ...MAX }; this.heat = 0; this.overheated = false; this.pending.length = 0; this.rockets.length = 0; this.missiles.length = 0; this.flares.length = 0; this.flareCd = 0; this.flareT = 0;
    this.jam.turret = this.jam.podL = this.jam.podR = false; this.lock.target = null; this.lock.t = 0; this.lock.locked = false; this.shotsFired = this.rocketsFired = this.missilesFired = 0; this.sel = 0;
    for (let i = 1; i <= 4; i++) for (const s of ['L', 'R']) { const n = heli.nodes['Missile_' + s + i]; if (n) n.visible = true; }
  },
  targets() { // lockable things
    const out = [];
    for (const s of castle.structs) if (s.alive && (s.type === 'tower' || s.type === 'gate')) out.push({ ref: s, kind: s.type, x: s.x, y: s.topY - 3, z: s.z, name: s.name });
    for (const e of threats.engines) if (e.alive && e.kind !== 'ballista') out.push({ ref: e, kind: e.kind, x: e.x, y: e.y + (e.kind === 'treb' ? 5 : 1), z: e.z, name: e.name });
    return out;
  },

  update(dt) {
    const fly = heli.state === 'fly';
    // selection
    if (fly) {
      const prev = this.sel;
      if (input.pressed('wpn1')) this.sel = 0; if (input.pressed('wpn2')) this.sel = 1; if (input.pressed('wpn3')) this.sel = 2;
      if (input.wheel) this.sel = (this.sel + (input.wheel > 0 ? 1 : 2)) % 3;
      if (prev !== this.sel) audio.play('weaponSwitch');
    }
    // jams from weapons subsystem damage
    if (heli.sub.weapons < 50 && !this.jam.turret && !this.jam.podL && !this.jam.podR) { const k = Math.random(); if (k < 0.34) this.jam.turret = true; else if (k < 0.67) this.jam.podL = true; else this.jam.podR = true; audio.play('jam'); G.events.dispatchEvent(new CustomEvent('msg', { detail: { text: this.jam.turret ? 'CANNON JAMMED' : 'ROCKET POD JAMMED', kind: 'warn' } })); }
    if (heli.sub.weapons >= 50) this.jam.turret = this.jam.podL = this.jam.podR = false;

    const trig = fly && input.down('fire') && !heli.onPad;
    this.firing = false;
    // ---- cannon ----
    this.fireT -= dt;
    if (trig && this.sel === 0) {
      if (this.jam.turret || this.overheated || this.ammo.cannon <= 0) { if (input.pressed('fire')) { audio.play(this.jam.turret ? 'jam' : 'dryFire'); } }
      else {
        this.firing = true;
        while (this.fireT <= 0) { this.fireT += 0.1; this._fireCannon(); }
        this.heat += dt / 4.0; if (this.heat >= 1) { this.heat = 1; this.overheated = true; audio.play('overheat'); G.events.dispatchEvent(new CustomEvent('msg', { detail: { text: 'CANNON OVERHEAT', kind: 'warn' } })); }
      }
    } else if (this.fireT < 0) this.fireT = 0;
    if (!this.firing) { this.heat = Math.max(0, this.heat - dt * 0.24); if (this.overheated && this.heat < 0.35) this.overheated = false; }
    // ---- rockets ----
    this.rocketT -= dt;
    if (trig && this.sel === 1 && this.rocketT <= 0) {
      if (this.ammo.rockets <= 0) { if (input.pressed('fire')) audio.play('dryFire'); }
      else { let side = this.rocketSide ^= 1; if (side === 0 && this.jam.podL) side = 1; else if (side === 1 && this.jam.podR) side = 0; if ((side === 0 && this.jam.podL) || (side === 1 && this.jam.podR)) { if (input.pressed('fire')) audio.play('jam'); } else { this._fireRocket(side); this.rocketT = (this.jam.podL || this.jam.podR) ? 0.36 : 0.19; } }
    }
    // ---- missiles: lock + fire ----
    this._updateLock(dt, fly && this.sel === 2);
    this.missileT -= dt;
    if (fly && this.sel === 2 && input.pressed('fire') && !heli.onPad) {
      if (this.ammo.missiles <= 0 || this.missileT > 0) audio.play('dryFire');
      else this._fireMissile();
    }
    // ---- flares ----
    this.flareCd = Math.max(0, this.flareCd - dt); this.flareT = Math.max(0, this.flareT - dt);
    if (fly && input.pressed('flares')) { if (this.ammo.flares > 0 && this.flareCd <= 0) this._flares(); else audio.play('dryFire'); }
    this._updateFlares(dt);
    this._updatePending(dt); this._updateRockets(dt); this._updateMissiles(dt);
    this._ccip();
    this._rearm(dt);
  },

  _fireCannon() {
    this.ammo.cannon--; this.shotsFired++;
    const m = heli.muzzle(_v);
    // spread grows with airframe rotation
    const rot = Math.hypot(heli.w.x, heli.w.y, heli.w.z); const spread = (0.35 + rot * 2.6 + (heli.gunner ? 0 : 0.25)) * DEG;
    _d.copy(heli.aimDir); const a = rnd(TAU), r = Math.sqrt(Math.random()) * spread;
    _v2.crossVectors(_d, heli.up).normalize(); _v3.crossVectors(_v2, _d);
    _d.addScaledVector(_v2, Math.cos(a) * r).addScaledVector(_v3, Math.sin(a) * r).normalize();
    const range = 1500; const hit = world.segHit(m.x, m.y, m.z, m.x + _d.x * range, m.y + _d.y * range, m.z + _d.z * range, 2.2, true);
    const dist = hit ? hit.t * range : range; const speed = 820;
    fx.muzzle(m, _d, heli.vel); audio.play('cannon');
    fx.streak(m.x, m.y, m.z, _d.x * speed + heli.vel.x, _d.y * speed + heli.vel.y, _d.z * speed + heli.vel.z, Math.min(dist / speed, 1.9), 0.05, 0.13, 4.2, 2.0, 0.55, 0, 0);
    fx.streak(m.x, m.y, m.z, _d.x * speed + heli.vel.x, _d.y * speed + heli.vel.y, _d.z * speed + heli.vel.z, Math.min(dist / speed, 1.9), 0.022, 0.045, 6, 5.4, 4.2, 0, 0);   // white-hot core
    if (!heli.gunner && Math.random() < 0.5) fx.smoke(m, _v2.set(heli.vel.x + _d.x * 6 + rndS(1.5), heli.vel.y + _d.y * 6 + 0.8, heli.vel.z + _d.z * 6 + rndS(1.5)), 0.35, 0.7, 0.3, 0.3);
    heli.shake = Math.min(1.2, heli.shake + 0.035);
    if (hit) this.pending.push({ t: dist / speed, x: hit.x, y: hit.y, z: hit.z, c: hit.c });
  },
  _updatePending(dt) {
    const P = this.pending;
    for (let i = P.length - 1; i >= 0; i--) {
      const p = P[i]; p.t -= dt; if (p.t > 0) continue; P.splice(i, 1);
      _v.set(p.x, p.y, p.z);
      const water = !p.c && p.y < L.WATER_Y;
      fx.impact(_v, water ? 'water' : p.c && p.c.kind !== 'tree' && p.c.kind !== 'prop' ? 'stone' : 'ground');
      if (Math.random() < 0.5) audio.play('cannonImpact', { pos: [p.x, p.y, p.z], mat: water ? 'water' : p.c && p.c.kind !== 'tree' && p.c.kind !== 'prop' ? 'stone' : 'dirt' });
      this.kills += crowd.blast(p.x, p.y, p.z, 2.6, 5, 0.32);
      if (p.c && p.c.ref) castle.damage(p.c.ref, 2.2, _v);
      threats.damageAt(_v, 3.2, 14);
    }
  },
  _fireRocket(side) {
    this.ammo.rockets--; this.rocketsFired++;
    const p = heli.nodePos(side ? 'RocketR' : 'RocketL', _v, side ? 1.4 : -1.4, -0.7, -1);
    const d = _d.copy(heli.fwd).addScaledVector(heli.up, rndS(0.006)).addScaledVector(heli.right, rndS(0.006)).normalize();
    this.rockets.push({ x: p.x, y: p.y, z: p.z, vx: heli.vel.x + d.x * 45, vy: heli.vel.y + d.y * 45, vz: heli.vel.z + d.z * 45, dx: d.x, dy: d.y, dz: d.z, t: 0, trail: 0 });
    audio.play('rocket'); fx.light(p, 0xffa050, 60, 40, 0.15); heli.shake = Math.min(1.2, heli.shake + 0.08);
    fx.smoke(p, _v2.set(heli.vel.x - d.x * 10 + rndS(2), heli.vel.y - d.y * 10 + rndS(2), heli.vel.z - d.z * 10 + rndS(2)), 0.5, 0.9, 0.15, 0.3);
  },
  _updateRockets(dt) {
    const R = this.rockets; const im = this.rocketMesh; let n = 0;
    for (let i = R.length - 1; i >= 0; i--) {
      const r = R[i]; r.t += dt;
      const sp = Math.hypot(r.vx, r.vy, r.vz); if (r.t < 1.1 && sp < 330) { const a = 420 * dt; r.vx += r.dx * a; r.vy += r.dy * a; r.vz += r.dz * a; }
      r.vy -= 4.5 * dt;
      const nx = r.x + r.vx * dt, ny = r.y + r.vy * dt, nz = r.z + r.vz * dt;
      const hit = world.segHit(r.x, r.y, r.z, nx, ny, nz, 1.5, true);
      if (hit || r.t > 7) { if (hit) this._explodeRocket(hit.x, hit.y, hit.z, hit.c); R.splice(i, 1); continue; }
      r.x = nx; r.y = ny; r.z = nz;
      if (r.t > 0.06) r.trail += dt * 100; while (r.trail > 1) { r.trail -= 1; const k = Math.random(); fx.spawn(0, r.x - r.vx * dt * k, r.y - r.vy * dt * k, r.z - r.vz * dt * k, rndS(0.8), rndS(0.8) + 0.4, rndS(0.8), 0.7, 1.9, rnd(1.4, 2.4), 0.62, 0.6, 0.58, 0.32, r.t < 0.5 ? 0.6 : 0, 1, -0.2); }
      if (r.t < 1.1) fx.spawn(3, r.x, r.y, r.z, 0, 0, 0, 1.5, 1.5, 0.04, 1, 0.7, 0.3, 1, 1, 0, 0);
    }
    for (const r of R) { _v.set(r.x, r.y, r.z); _m.lookAt(_v, _v2.set(r.x + r.vx, r.y + r.vy, r.z + r.vz), heli.up).setPosition(_v); im.setMatrixAt(n++, _m); }
    im.count = n; im.instanceMatrix.needsUpdate = true;
  },
  _explodeRocket(x, y, z, c) {
    _v.set(x, y, z);
    if (!c && y < L.WATER_Y + 0.2) { fx.splash(x, z, 2.2); audio.play('explSmall', { pos: [x, y, z], water: true }); return; }
    fx.explosion(_v, 1.5, { fire: Math.random() < 0.3, fireLife: 14, debrisColor: c && c.kind !== 'tree' ? 0x8a8378 : 0x3b2e20 });
    audio.play('explMedium', { pos: [x, y, z] });
    this.kills += crowd.blast(x, y, z, 10, 12, 1);
    castle.damageAt(_v, 7, 62); threats.damageAt(_v, 8, 110);
    if (c && c.kind === 'house') fx.addFire(x, y + 1, z, 2.2, 60, 1.3);
  },
  _updateLock(dt, active) {
    const L_ = this.lock;
    if (!active || this.ammo.missiles <= 0) { L_.target = null; L_.t = 0; L_.locked = false; return; }
    // candidates inside a small cone around the boresight (camera forward in gunner mode, nose otherwise)
    const dir = heli.gunner ? heli.aimDir : _d.copy(heli.fwd); const eye = heli.pos; let best = null, bestA = 4.2 * DEG;
    const cur = L_.target;
    for (const t of this.targets()) {
      _v.set(t.x - eye.x, t.y - eye.y, t.z - eye.z); const d = _v.length(); if (d > 1500 || d < 40) continue; _v.multiplyScalar(1 / d);
      const ang = Math.acos(clamp(_v.dot(dir), -1, 1)); const lim = (cur && cur.ref === t.ref) ? 5.5 * DEG : 4.2 * DEG;
      if (ang < lim && ang < bestA + (cur && cur.ref === t.ref ? 2 * DEG : 0)) { best = t; bestA = ang; if (cur && cur.ref === t.ref) { bestA = -1; } }
    }
    if (!best) { if (L_.target) { L_.target = null; L_.t = 0; L_.locked = false; } return; }
    if (!L_.target || L_.target.ref !== best.ref) { L_.target = best; L_.t = 0; L_.locked = false; }
    else { L_.target = best; L_.t += dt; if (!L_.locked && L_.t >= 2) { L_.locked = true; audio.play('lockOn'); } }
  },
  _fireMissile() {
    const idx = MAX.missiles - this.ammo.missiles; const side = idx % 2; const num = (idx >> 1) + 1; const name = 'Missile_' + (side ? 'R' : 'L') + num;
    const node = heli.nodes[name]; const p = node ? node.getWorldPosition(_v) : _v.copy(heli.pos); if (node) node.visible = false;
    this.ammo.missiles--; this.missilesFired++; this.missileT = 0.7;
    const d = heli.fwd; const L_ = this.lock;
    this.missiles.push({ x: p.x, y: p.y - 0.3, z: p.z, vx: heli.vel.x + d.x * 30, vy: heli.vel.y + d.y * 30 - 2, vz: heli.vel.z + d.z * 30, dx: d.x, dy: d.y, dz: d.z, t: 0, target: L_.locked ? L_.target : null, trail: 0, speed: 40 });
    audio.play('missile'); fx.light(p, 0xffa050, 120, 60, 0.3); heli.shake = Math.min(1.4, heli.shake + 0.25);
    L_.t = 0; L_.locked = false;
  },
  _updateMissiles(dt) {
    const M = this.missiles; const im = this.missileMesh; let n = 0;
    for (let i = M.length - 1; i >= 0; i--) {
      const m = M[i]; m.t += dt; m.speed = Math.min(300, m.speed + 260 * dt);
      if (m.target && m.t > 0.25) { const t = m.target; const alive = t.ref.alive; if (alive) { _v.set(t.x - m.x, t.y - m.y, t.z - m.z).normalize(); const k = Math.min(1, dt * 3.2); m.dx = lerp(m.dx, _v.x, k); m.dy = lerp(m.dy, _v.y, k); m.dz = lerp(m.dz, _v.z, k); const l = Math.hypot(m.dx, m.dy, m.dz); m.dx /= l; m.dy /= l; m.dz /= l; } }
      else if (!m.target) m.dy -= 0.02 * dt;
      m.vx = m.dx * m.speed; m.vy = m.dy * m.speed; m.vz = m.dz * m.speed;
      const nx = m.x + m.vx * dt, ny = m.y + m.vy * dt, nz = m.z + m.vz * dt;
      let hit = world.segHit(m.x, m.y, m.z, nx, ny, nz, 1.5, true);
      let direct = false; if (m.target && Math.hypot(m.target.x - nx, m.target.y - ny, m.target.z - nz) < 6) { direct = true; hit = hit || { x: nx, y: ny, z: nz, c: null }; }
      if (hit || m.t > 9) {
        if (hit) { _v.set(hit.x, hit.y, hit.z); fx.explosion(_v, 2.4, { fire: true, fireLife: 20, debrisColor: 0x8a8378 }); audio.play('explLarge', { pos: [hit.x, hit.y, hit.z] });
          this.kills += crowd.blast(hit.x, hit.y, hit.z, 12, 14, 1);
          const ref = direct ? m.target.ref : hit.c && hit.c.ref;
          if (ref && ref.type) castle.damage(ref, 150, _v); else if (ref && ref.kind) threats.destroy(ref);
          castle.damageAt(_v, 9, 120); threats.damageAt(_v, 12, 400); }
        M.splice(i, 1); continue;
      }
      m.x = nx; m.y = ny; m.z = nz;
      m.trail += dt * 150; while (m.trail > 1) { m.trail -= 1; const k = Math.random(); fx.spawn(0, m.x - m.vx * dt * k, m.y - m.vy * dt * k, m.z - m.vz * dt * k, rndS(1), rndS(1) + 0.5, rndS(1), 1.1, 3.0, rnd(2.5, 4), 0.7, 0.68, 0.66, 0.42, m.t < 0.6 ? 0.8 : 0.1, 1, -0.25); }
      fx.spawn(3, m.x, m.y, m.z, 0, 0, 0, 2.4, 2.4, 0.04, 1, 0.75, 0.35, 1, 1, 0, 0);
    }
    for (const m of M) { _v.set(m.x, m.y, m.z); _m.lookAt(_v, _v2.set(m.x + m.dx, m.y + m.dy, m.z + m.dz), heli.up).setPosition(_v); im.setMatrixAt(n++, _m); }
    im.count = n; im.instanceMatrix.needsUpdate = true;
  },
  _flares() {
    this.ammo.flares--; this.flareCd = 10; this.flareT = 3; audio.play('flare'); this.flarePos.copy(heli.pos);
    for (let i = 0; i < 8; i++) { const side = i % 2 ? 1 : -1; const p = heli.nodePos(side > 0 ? 'FlareR' : 'FlareL', _v, side * 0.35, 0.1, 5.3);
      this.flares.push({ x: p.x, y: p.y, z: p.z, vx: heli.vel.x * 0.7 + heli.right.x * side * rnd(8, 16) - heli.fwd.x * rnd(2, 8), vy: heli.vel.y * 0.5 + rnd(-2, 6), vz: heli.vel.z * 0.7 + heli.right.z * side * rnd(8, 16) - heli.fwd.z * rnd(2, 8), t: -i * 0.07, life: rnd(2.6, 3.4), s: 0 }); }
    G.events.dispatchEvent(new CustomEvent('flares'));
  },
  _updateFlares(dt) {
    const F = this.flares;
    for (let i = F.length - 1; i >= 0; i--) {
      const f = F[i]; f.t += dt; if (f.t < 0) continue; if (f.t > f.life) { F.splice(i, 1); continue; }
      f.vy -= 6 * dt; const d = Math.exp(-0.8 * dt); f.vx *= d; f.vz *= d; f.x += f.vx * dt; f.y += f.vy * dt; f.z += f.vz * dt;
      fx.spawn(3, f.x, f.y, f.z, 0, 0, 0, 3.2, 3.2, 0.05, 1, 0.8, 0.55, 1, 2.2, 0, 0);
      f.s += dt * 40; while (f.s > 1) { f.s -= 1; fx.spawn(0, f.x, f.y, f.z, rndS(0.6), 0.8, rndS(0.6), 0.35, 1.8, rnd(1.2, 2.2), 0.8, 0.78, 0.74, 0.4, 2.5, 1, -0.4); }
      if (Math.random() < dt * 30) fx.streak(f.x, f.y, f.z, rndS(6), rndS(6), rndS(6), 0.3, 0.04, 0.04, 3, 2, 1, 6, 0);
      if (i === 0) { fx.lights[4].position.set(f.x, f.y, f.z); }
    }
    if (F.length) this.flarePos.set(F[0].x, F[0].y, F[0].z);
  },
  // predicted impact point for the HUD reticle
  _ccip() {
    const m = heli.muzzle(_v);
    if (this.sel === 1) { // rockets: simulate a short ballistic path
      let x = heli.pos.x, y = heli.pos.y - 0.7, z = heli.pos.z; const d = heli.fwd; let vx = heli.vel.x + d.x * 45, vy = heli.vel.y + d.y * 45, vz = heli.vel.z + d.z * 45; let t = 0; this.ccipValid = false;
      const h = 0.05;
      for (let i = 0; i < 130; i++) { if (t < 1.1 && Math.hypot(vx, vy, vz) < 330) { vx += d.x * 420 * h; vy += d.y * 420 * h; vz += d.z * 420 * h; } vy -= 4.5 * h; const nx = x + vx * h, ny = y + vy * h, nz = z + vz * h; t += h;
        if (ny < terrain.height(nx, nz) || world.pointHit(nx, ny, nz)) { this.ccip.set(nx, ny, nz); this.ccipValid = true; break; } x = nx; y = ny; z = nz; }
      if (!this.ccipValid) this.ccip.set(x, y, z);
    } else {
      const d = this.sel === 0 ? heli.aimDir : heli.fwd; const range = 1500; const hit = world.segHit(m.x, m.y, m.z, m.x + d.x * range, m.y + d.y * range, m.z + d.z * range, 4, true);
      if (hit) { this.ccip.set(hit.x, hit.y, hit.z); this.ccipValid = true; } else { this.ccip.copy(m).addScaledVector(d, range); this.ccipValid = false; }
    }
    this.ccipDist = this.ccip.distanceTo(heli.pos);
  },
  _rearm(dt) {
    const on = heli.onPad && heli.state === 'fly';
    if (on && !this.rearming) { this.rearming = true; this.rearmT = 0.6; this.repairT = 0; G.events.dispatchEvent(new CustomEvent('padLanding')); }
    if (!on) { this.rearming = false; return; }
    this.rearmT -= dt;
    if (this.rearmT <= 0) {
      this.rearmT = 0.45; let did = false; const a = this.ammo;
      if (a.cannon < MAX.cannon) { a.cannon = Math.min(MAX.cannon, a.cannon + 50); did = true; }
      if (a.rockets < MAX.rockets) { a.rockets = Math.min(MAX.rockets, a.rockets + 3); did = true; }
      if (a.missiles < MAX.missiles) { a.missiles++; did = true; const idx = MAX.missiles - a.missiles; const n = heli.nodes['Missile_' + (idx % 2 ? 'R' : 'L') + ((idx >> 1) + 1)]; if (n) n.visible = true; }
      if (a.flares < MAX.flares) { a.flares++; did = true; }
      if (did) audio.play('rearmTick');
    }
    heli.hull = Math.min(100, heli.hull + dt * 5);
    // limp home: one subsystem repaired per 5 s on the ground
    const worst = SUBS.filter(s => heli.sub[s] < 100).sort((x, y) => heli.sub[x] - heli.sub[y])[0];
    if (worst) { this.repairT += dt; this.repairing = worst; if (this.repairT >= 5) { this.repairT = 0; heli.repair(worst); audio.play('repairDone'); G.events.dispatchEvent(new CustomEvent('msg', { detail: { text: worst.toUpperCase() + ' REPAIRED', kind: 'good' } })); } } else { this.repairing = null; this.repairT = 0; }
    this.fullyArmed = this.ammo.cannon === MAX.cannon && this.ammo.rockets === MAX.rockets && this.ammo.missiles === MAX.missiles && this.ammo.flares === MAX.flares && !worst && heli.hull >= 99.5;
  },
};
