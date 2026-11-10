// Siege Wing — threats: archer volleys, ballistae, bombards (flak), trebuchets, fire pots; adaptive defence
import * as THREE from 'three';
import { G, V3, clamp, lerp, smooth, sat, rnd, rndS, DEG, TAU, wrapPi, damp } from './core.js';
import { terrain, L } from './terrain.js';
import { world } from './world.js';
import { heli } from './heli.js';
import { fx } from './fx.js';
import { audio } from './audio.js';
import { crowd, TY, ST } from './crowd.js';
import { castle } from './castle.js';
import { scenery } from './scenery.js';
import { assets } from './assets.js';
import { weapons } from './weapons.js';

const _v = new V3(), _v2 = new V3(), _v3 = new V3(), _m = new THREE.Matrix4(), _q = new THREE.Quaternion(), _s = new V3(1, 1, 1), _z = new V3(0, 0, 1);
const MAXA = 1500, GR = 9.81;

function cloneProp(name) {
  const o = assets.props.scene.getObjectByName(name).clone(true);
  o.traverse(c => { if (c.isMesh) { c.material = /Iron/.test(c.material.name) ? scenery.mats.iron : scenery.mats.prop; c.castShadow = true; c.receiveShadow = true; } });
  return o;
}

export const threats = {
  engines: [], arrows: null, na: 0, bolts: [], shells: [], boulders: [], phase: 1, aimWarn: 0, aimers: 0, bandCenter: 200, bandHalf: 100, pavises: null,
  stats: { arrowHits: 0, boltHits: 0, flakHits: 0, boulderHits: 0 }, volleyWarn: 0, lastVolleyPos: new V3(),
  build(scene) {
    this.scene = scene;
    // ---- engines ----
    castle.mounts.ballista.forEach((m, i) => {
      const obj = cloneProp('Ballista'); obj.position.set(m.x, m.y, m.z); obj.scale.setScalar(1.25); scene.add(obj);
      const e = { kind: 'ballista', name: 'Ballista', x: m.x, y: m.y + 1.6, z: m.z, obj, yawN: obj.getObjectByName('Ballista_Yaw'), pitchN: obj.getObjectByName('Ballista_Pitch'), boltN: obj.getObjectByName('Ballista_LoadedBolt'), mount: m.tower, hp: 60, maxHp: 60, alive: true, state: 'idle', t: rnd(2, 6), reload: 6.5, yaw: Math.atan2(m.x - L.CASTLE.x, m.z - L.CASTLE.z), pitch: 0.1, aim: new V3(), spotted: false, range: 400 };
      e.crew = crowd.addCrew(m.x, m.y, m.z, 2, 2.6, true); this.engines.push(e);
    });
    castle.mounts.bombard.forEach((m, i) => {
      const obj = cloneProp('Bombard'); obj.position.set(m.x, m.y, m.z); obj.rotation.y = m.yaw + Math.PI / 2; obj.scale.setScalar(0.85); scene.add(obj);
      const e = { kind: 'bombard', name: 'Bombard', x: m.x, y: m.y + 1, z: m.z, obj, pitchN: obj.getObjectByName('Bombard_Pitch'), muzzleN: obj.getObjectByName('Bombard_Muzzle'), mount: m.wall, hp: 90, maxHp: 90, alive: true, state: 'idle', t: rnd(3, 12), reload: 12, spotted: false, range: 800, baseYaw: obj.rotation.y };
      e.crew = crowd.addCrew(m.x, m.y, m.z, 3, 2.3, true); this.engines.push(e);
    });
    castle.mounts.treb.forEach((m, i) => {
      const obj = cloneProp('Trebuchet'); obj.position.set(m.x, m.y - 0.1, m.z); obj.rotation.y = Math.PI / 2; scene.add(obj); // throws toward +x (the field)
      const e = { kind: 'treb', name: 'Trebuchet', x: m.x, y: m.y, z: m.z, obj, arm: obj.getObjectByName('Treb_Arm'), cw: obj.getObjectByName('Treb_CW'), sling: obj.getObjectByName('Treb_SlingMesh'), loaded: obj.getObjectByName('Treb_LoadedBoulder'), hp: 140, maxHp: 140, alive: true, state: 'idle', t: 6 + i * 5, reload: 15, spotted: false, range: 1400, armA: -0.873 };
      e.crew = crowd.addCrew(m.x, m.y, m.z, 5, 6.5, false); world.addCyl(m.x, m.z, 3.5, m.y, m.y + 10.5, 'prop').ref = null; this.engines.push(e);
    });
    crowd.finalize();
    // ---- fire pots ----
    const pots = castle.firePots; scenery.put('FirePot', pots.map(p => ({ x: p.x, y: p.y, z: p.z, ry: rnd(TAU), s: 1.5 })));
    // ---- arrows ----
    const ag = assets.props.scene.getObjectByName('Arrow'); let geo = null; ag.traverse(o => { if (o.isMesh && !geo) geo = o.geometry.clone(); }); geo.scale(1.25, 1.25, 1.25);
    const amat = this.arrowMat = new THREE.MeshStandardMaterial({ color: 0x8a6a45, roughness: 0.8, vertexColors: false, emissive: 0xff5a10, emissiveIntensity: 0 });
    this.arrowMesh = new THREE.InstancedMesh(geo, amat, MAXA); this.arrowMesh.count = 0; this.arrowMesh.frustumCulled = false; this.arrowMesh.castShadow = false; this.arrowMesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage); scene.add(this.arrowMesh);
    this.ar = { x: new Float32Array(MAXA), y: new Float32Array(MAXA), z: new Float32Array(MAXA), vx: new Float32Array(MAXA), vy: new Float32Array(MAXA), vz: new Float32Array(MAXA), t: new Float32Array(MAXA), stuck: new Uint8Array(MAXA) };
    // ---- bolt / boulder visuals ----
    let bg = null; assets.props.scene.getObjectByName('Bolt').traverse(o => { if (o.isMesh && !bg) bg = o; });
    this.boltProto = cloneProp('Bolt'); this.boltPool = []; for (let i = 0; i < 6; i++) { const b = this.boltProto.clone(true); b.visible = false; b.scale.setScalar(1.6); scene.add(b); this.boltPool.push(b); }
    this.boulderPool = []; for (let i = 0; i < 5; i++) { const b = cloneProp('Boulder'); b.visible = false; b.scale.setScalar(1.5); scene.add(b); this.boulderPool.push(b); }
    // aim glint sprites (ballista tell)
    this.glints = []; for (let i = 0; i < 3; i++) { const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: glintTex(), color: 0xfff2c0, blending: THREE.AdditiveBlending, depthTest: false, depthWrite: false, transparent: true, fog: false })); s.visible = false; s.renderOrder = 40; scene.add(s); this.glints.push(s); }
    // pavises (phase 2+)
    G.events.addEventListener('structDestroyed', e => this._structFell(e.detail));
  },
  reset() {
    for (const e of this.engines) { e.alive = true; e.hp = e.maxHp; e.obj.visible = true; e.state = 'idle'; e.t = rnd(3, 9); e.spotted = false; if (e.kind === 'treb') { e.armA = -0.873; e.t = 6 + rnd(8); } }
    this.na = 0; this.bolts.length = 0; this.shells.length = 0; this.boulders.length = 0; this.phase = 1; this.loiterT = 0; this.aimWarn = 0; this.bandCenter = 200; this.bandHalf = 100;
    for (const b of this.boltPool) b.visible = false; for (const b of this.boulderPool) b.visible = false;
    for (const p of castle.firePots) { if (p.emitter) { p.emitter.on = false; p.emitter.permanent = false; p.emitter.life = 0; p.emitter = null; } p.lit = false; }
    if (this.pavises) { this.scene.remove(...this.pavises); this.pavises = null; }
    for (const f of crowd.forms) f.pavise = false;
    this.stats = { arrowHits: 0, boltHits: 0, flakHits: 0, boulderHits: 0 };
  },
  // defenders adapt each phase
  setPhase(n, favAlt) {
    this.phase = n;
    if (n >= 2 && !this.pavises) { // pavise mantlets come out in front of the surviving archer companies
      const list = []; for (const f of crowd.forms) if (f.kind === 'archers' && !f.routed && !f.onWalls) { f.pavise = true; for (let i = -5; i <= 5; i++) { const x = f.cx + 10 + Math.abs(i) * 0.3, z = f.cz + i * 2.2; list.push({ x, y: terrain.height(x, z), z, ry: Math.PI / 2 + rndS(0.15), tint: f.herald[0] }); } }
      const before = this.scene.children.length; scenery.put('Pavise', list); this.pavises = this.scene.children.slice(before);
    }
    if (n >= 3) {
      for (const p of castle.firePots) if (!p.lit) { p.lit = true; p.emitter = fx.addFire(p.x, p.y + 1.7, p.z, 1.0, 1e9, 2.4, true, true); p.emitter.rate = 16; }
      if (favAlt !== undefined) { this.bandCenter = clamp(favAlt, 60, 320); this.bandHalf = 75; }
    }
    if (n === 2 && favAlt !== undefined) { this.bandCenter = clamp(lerp(200, favAlt, 0.6), 80, 300); this.bandHalf = 90; }
  },
  crewAlive(e) { let n = 0; for (const i of e.crew) if (crowd.isAlive(i)) n++; return n; },
  damageAt(p, r, dmg) { for (const e of this.engines) { if (!e.alive) continue; const d = Math.hypot(p.x - e.x, p.y - e.y, p.z - e.z); if (d < r + (e.kind === 'treb' ? 5 : 2)) { e.hp -= dmg * clamp(1.2 - d / (r + 3), 0.3, 1); e.spotted = true; if (e.hp <= 0) this.destroy(e); } } },
  destroy(e) {
    if (!e.alive) return; e.alive = false; e.obj.visible = false; e.state = 'dead';
    _v.set(e.x, e.y + 1, e.z); fx.explosion(_v, e.kind === 'treb' ? 1.7 : 1.2, { fire: true, fireLife: 25, debris: e.kind === 'treb' ? 26 : 12, debrisColor: 0x5a4028 });
    audio.play('explMedium', { pos: [e.x, e.y, e.z] });
    for (const i of e.crew) if (crowd.isAlive(i)) crowd.kill(i, rndS(6), rnd(3, 8), rndS(6));
    G.events.dispatchEvent(new CustomEvent('engineDestroyed', { detail: e }));
  },
  _structFell(s) {
    crowd.structFell(s);
    for (const e of this.engines) if (e.alive && e.mount === s) { e.alive = false; e.obj.visible = false; e.state = 'dead'; fx.debrisBurst(_v.set(e.x, e.y, e.z), 10, 0.5, 0x5a4028, null, 8); G.events.dispatchEvent(new CustomEvent('engineDestroyed', { detail: e })); }
  },

  update(dt) {
    const fly = heli.state === 'fly'; const hp = heli.pos, hv = heli.vel;
    const night = G.U.uNight.value;
    // loiter clock: hovering high and slow (out of arrow reach) for more than a few seconds draws the castle's bombards even in phase 1
    // It ramps instead of switching: the slower you fly the faster it fills (nothing above 24 m/s), and it drains when you move on.
    { const hs = Math.hypot(hv.x, hv.z); const rate = fly && hp.y - 24 > 120 ? clamp(1 - hs / 24, 0, 1) : 0; const was = this.loiterT || 0;
      this.loiterT = clamp(was + (rate > 0 ? rate * dt : -1.5 * dt), 0, 14); this.loiterK = smooth(4, 10, this.loiterT);
      if (was < 4 && this.loiterT >= 4 && this.phase === 1) G.events.dispatchEvent(new CustomEvent('subtitle', { detail: { text: 'They are ranging us. Keep moving.', speaker: 'gunner', dur: 3 } }));
      if (this.phase === 1 && this.loiterK > 0) this.bandCenter = damp(this.bandCenter, clamp(hp.y - 24, 60, 420), 0.5, dt); } // in phase 1 the guns walk onto whatever height you park at
    // ================= archer volleys =================
    this.volleyWarn = Math.max(0, this.volleyWarn - dt);
    for (const f of crowd.forms) {
      if (f.kind !== 'archers') continue;
      if (f.routed || f.panicT > 0 || f.alive < 4 || !fly) { f.volleying = false; f.volleyT = Math.max(f.volleyT, 1.5); continue; }
      const dx = hp.x - f.cx, dz = hp.z - f.cz; const dh = Math.hypot(dx, dz); const alt = hp.y - f.cy;
      const reach = f.onWalls ? 250 : 270; const inRange = dh < reach + f.radius && alt < 128 + 160 * (this.loiterK || 0) && alt > -30; // a helicopter parked high and slow gets a massed high-angle volley
      if (f.volleying) {
        f.volleyClock += dt;
        if (!f.loosed && f.volleyClock >= 2.4) { f.loosed = true; this._loose(f); }
        if (f.volleyClock >= 3.0) { f.volleying = false; f.volleyT = 5 - 3.0 + rnd(-0.3, 0.6) + (this.phase >= 2 ? -0.4 : 0); }
      } else {
        f.volleyT -= dt;
        if (inRange && f.volleyT <= 0) { f.volleying = true; f.volleyClock = 0; f.loosed = false; audio.play('horn', { pos: [f.cx, f.cy + 3, f.cz], gain: 1.1 }); this.volleyWarn = 2.4; this.lastVolleyPos.set(f.cx, f.cy, f.cz); f.spotted = true; }
        else if (!inRange) f.volleyT = Math.max(f.volleyT, 0.6);
      }
    }
    this._updateArrows(dt, fly, night);

    // ================= engines =================
    let aimWarn = 0; let aimers = 0; let gi = 0; for (const g of this.glints) g.visible = false;
    for (const e of this.engines) {
      if (!e.alive) continue;
      const dx = hp.x - e.x, dy = hp.y - e.y, dz = hp.z - e.z; const dist = Math.hypot(dx, dy, dz); const dh = Math.hypot(dx, dz);
      if (dist < 520) e.spotted = true;
      const manned = this.crewAlive(e) > 0;
      for (const i of e.crew) crowd.crew[i] = 0;
      if (e.kind === 'ballista') {
        // track
        const wantYaw = Math.atan2(dx, dz), wantPitch = Math.atan2(dy, dh);
        const active = manned && fly && dist < e.range && dy > -40 && hp.y - 24 < 270 && weapons.flareT <= 0;
        if (e.state === 'idle') { e.t -= dt; if (active && e.t <= 0 && aimers + this._aiming() < 2) { e.state = 'aim'; e.t = 0; e.locked = false; audio.play('warning', { gain: 0.5 }); } }
        if (e.state === 'aim') {
          aimers++;
          if (!active) { e.state = 'idle'; e.t = weapons.flareT > 0 ? 3 : 1.5; }
          else {
            e.t += dt; e.yaw += wrapPi(wantYaw - e.yaw) * Math.min(1, dt * 6); e.pitch = damp(e.pitch, wantPitch, 6, dt);
            for (const i of e.crew) crowd.crew[i] = 1;
            aimWarn = Math.max(aimWarn, e.t / 1.5);
            // glint tell
            if (gi < this.glints.length) { const g = this.glints[gi++]; g.visible = true; g.position.set(e.x, e.y + 0.6, e.z); const k = e.t / 1.5; const sc = (3 + 9 * k) * (0.8 + 0.2 * Math.sin(G.time * 40)) * Math.max(1, dist / 160); g.scale.set(sc, sc, 1); g.material.opacity = 0.5 + 0.5 * k; g.material.rotation = G.time * 2; }
            const speed = 165;
            if (!e.locked && e.t >= 1.05) { e.locked = true; const tof = dist / speed; e.aim.set(hp.x + hv.x * tof, hp.y + hv.y * tof + 0.5 * GR * 0.25 * tof * tof, hp.z + hv.z * tof); }
            if (e.t >= 1.5) {
              // loose
              _v.set(e.x, e.y + 0.6, e.z); _v2.copy(e.aim).sub(_v).normalize(); _v2.x += rndS(0.006); _v2.y += rndS(0.006); _v2.z += rndS(0.006);
              const pool = this.boltPool.find(b => !b.visible) || this.boltPool[0]; pool.visible = true;
              this.bolts.push({ x: _v.x, y: _v.y, z: _v.z, vx: _v2.x * speed, vy: _v2.y * speed, vz: _v2.z * speed, t: 0, mesh: pool, near: false });
              audio.play('boltFire', { pos: [e.x, e.y, e.z] }); fx.dust(e.x, e.y + 0.5, e.z, 0, 1, 0, 0.8, 1, 0.3);
              e.state = 'idle'; e.t = (this.phase >= 2 ? e.reload * 0.8 : e.reload) + rnd(0, 2); if (e.boltN) e.boltN.visible = false; e.reloadVis = 2.5;
            }
          }
        } else { e.yaw += wrapPi((dist < 700 ? wantYaw : e.yaw) - e.yaw) * Math.min(1, dt * 1.2); }
        if (e.reloadVis > 0) { e.reloadVis -= dt; for (const i of e.crew) crowd.crew[i] = 1; if (e.reloadVis <= 0 && e.boltN) e.boltN.visible = true; }
        if (e.yawN) e.yawN.rotation.y = e.yaw; if (e.pitchN) e.pitchN.rotation.x = -clamp(e.pitch, -0.5, 1.1);
      } else if (e.kind === 'bombard') {
        e.t -= dt;
        const alt = hp.y - 24; const inBand = Math.abs(alt - this.bandCenter) < this.bandHalf;
        const active = (this.phase >= 2 || this.loiterK > 0.5) && manned && fly && dh < e.range && inBand && dy > 10; // in phase 1 the guns only range a helicopter that parks high over the field
        if (e.pitchN) e.pitchN.rotation.x = damp(e.pitchN.rotation.x, -clamp(Math.atan2(dy, dh), 0.15, 1.2), 2, dt);
        if (manned && dh < 900) e.obj.rotation.y += wrapPi(Math.atan2(dx, dz) - e.obj.rotation.y) * Math.min(1, dt * 0.8);
        if (e.t < 3 && active) for (const i of e.crew) crowd.crew[i] = 1;
        if (active && e.t <= 0 && G.time - (this.lastBombard || -99) > (this.phase >= 2 ? 3.6 : 9)) { /* phase 1: harassing fire only, well under half the phase 2 rate */
          this.lastBombard = G.time; e.t = e.reload + rnd(-1, 2); e.spotted = true;
          const speed = 230; const tof = dist / speed; const err = 12 + dist * 0.028;
          const tx = hp.x + hv.x * tof + rndS(err), ty = hp.y + hv.y * tof + rndS(err * 0.6), tz = hp.z + hv.z * tof + rndS(err);
          const mp = e.muzzleN ? e.muzzleN.getWorldPosition(_v) : _v.set(e.x, e.y + 1, e.z);
          this.shells.push({ x: mp.x, y: mp.y, z: mp.z, tx, ty, tz, t: 0, tof, sx: mp.x, sy: mp.y, sz: mp.z });
          // the tell: a big smoke puff and a boom
          _v2.set(tx - mp.x, ty - mp.y, tz - mp.z).normalize();
          for (let k = 0; k < 9; k++) fx.smoke(mp, _v3.set(_v2.x * rnd(4, 16) + rndS(2), _v2.y * rnd(4, 16) + rndS(2), _v2.z * rnd(4, 16) + rndS(2)), rnd(1.5, 2.5), rnd(3, 5), 0.25, 0.7, 1);
          fx.spawn(3, mp.x, mp.y, mp.z, 0, 0, 0, 7, 7, 0.12, 1, 0.7, 0.35, 1, 1, 0, 0); fx.light(mp, 0xffa050, 160, 70, 0.25);
          audio.play('bombardFire', { pos: [e.x, e.y, e.z] });
          G.events.dispatchEvent(new CustomEvent('bombardFired', { detail: e }));
        }
      } else if (e.kind === 'treb') {
        const active = this.phase >= 2 && manned && fly && dist < e.range && dist > 150;
        if (e.state === 'idle') {
          e.t -= dt; e.armA = damp(e.armA, -0.873, 1.5, dt);
          if (e.t < 5 && active) for (const i of e.crew) crowd.crew[i] = 1;
          if (e.loaded) e.loaded.visible = e.t < 4;
          if (active && e.t <= 0) { e.state = 'swing'; e.t = 0; audio.play('trebRelease', { pos: [e.x, e.y + 8, e.z] }); e.spotted = true; }
        } else if (e.state === 'swing') {
          e.t += dt; const k = sat(e.t / 0.9); e.armA = lerp(-0.873, 2.0, k * k * (3 - 2 * k));
          if (e.t > 0.62 && !e.released) { e.released = true; this._launchBoulder(e); if (e.loaded) e.loaded.visible = false; }
          if (e.t > 1.6) { e.state = 'idle'; e.released = false; e.t = e.reload + rnd(-2, 3) - (this.phase >= 3 ? 3 : 0); }
        }
        if (e.arm) { e.arm.rotation.x = e.armA; if (e.cw) e.cw.rotation.x = -e.armA; if (e.sling) e.sling.rotation.x = -e.armA - 0.3 - sat((e.armA + 0.873) / 2.8) * 2.2; }
      }
    }
    this.aimWarn = aimWarn; this.aimers = aimers;
    this._updateBolts(dt, fly); this._updateShells(dt, fly); this._updateBoulders(dt, fly);
  },
  _aiming() { return 0; },

  // ---------------- arrows ----------------
  _loose(f) {
    const hp = heli.pos, hv = heli.vel; const A = this.ar; let count = 0;
    const off = weapons.flareT > 0 ? 45 : 0; const ox = rndS(off), oz = rndS(off);
    for (const i of f.agents) {
      if (crowd.st[i] !== ST.FORM || crowd.type[i] !== TY.ARCH) continue;
      const sx = crowd.x[i], sy = crowd.y[i] + 1.7, sz = crowd.z[i];
      const d0 = Math.hypot(hp.x - sx, hp.y - sy, hp.z - sz); if (d0 > 330) continue;
      const T = clamp(d0 / 50, 0.7, 5.5) * rnd(0.94, 1.08); const sp = 5.5 + d0 * 0.03 + Math.max(0, hp.y - sy - 70) * 0.12;
      const tx = hp.x + hv.x * T * 0.92 + rndS(sp) + ox, ty = hp.y + hv.y * T * 0.6 + rndS(sp * 0.6), tz = hp.z + hv.z * T * 0.92 + rndS(sp) + oz;
      let vx = (tx - sx) / T, vy = (ty - sy) / T + 0.5 * GR * T, vz = (tz - sz) / T; const v = Math.hypot(vx, vy, vz); const vmax = 66; if (v > vmax) { vx *= vmax / v; vy *= vmax / v; vz *= vmax / v; }
      let k = this.na < MAXA ? this.na++ : (Math.random() * MAXA) | 0;
      A.x[k] = sx; A.y[k] = sy; A.z[k] = sz; A.vx[k] = vx; A.vy[k] = vy; A.vz[k] = vz; A.t[k] = -crowd.ph[i] * 0.3; A.stuck[k] = 0; count++;
    }
    if (count) audio.play('volleyLoose', { pos: [f.cx, f.cy + 2, f.cz] });
    G.events.dispatchEvent(new CustomEvent('volley', { detail: f }));
  },
  _updateArrows(dt, fly, night) {
    const A = this.ar; const hp = heli.pos; let n = this.na; const im = this.arrowMesh; let hits = 0, near = 0;
    const fwd = heli.fwd;
    for (let i = 0; i < n; i++) {
      A.t[i] += dt;
      if (A.stuck[i]) { if (A.t[i] > 9) { n--; for (const k in A) A[k][i] = A[k][n]; i--; } continue; }
      if (A.t[i] < 0) continue;
      A.vy[i] -= GR * dt; const d = 1 - 0.05 * dt; A.vx[i] *= d; A.vz[i] *= d;
      A.x[i] += A.vx[i] * dt; A.y[i] += A.vy[i] * dt; A.z[i] += A.vz[i] * dt;
      // helicopter hit: capsule along the fuselage + rotor disc
      const rx = A.x[i] - hp.x, ry = A.y[i] - hp.y, rz = A.z[i] - hp.z; const d2 = rx * rx + ry * ry + rz * rz;
      if (fly && d2 < 90) {
        const along = rx * fwd.x + ry * fwd.y + rz * fwd.z; const up = rx * heli.up.x + ry * heli.up.y + rz * heli.up.z; const side = Math.sqrt(Math.max(0, d2 - along * along - up * up));
        const body = along > -7.5 && along < 8.2 && Math.abs(up) < 1.5 && side < 1.5; const disc = Math.abs(up - heli.rotorY) < 0.5 && (along * along + side * side) < 53;
        if (body || (disc && Math.random() < 0.35)) {
          hits++; _v.set(A.x[i], A.y[i], A.z[i]); if (hits < 4) fx.sparks(_v, _v2.set(0, 1, 0), 3, 6);
          const sub = disc ? 'rotor' : along > 4 ? 'tail' : along < -2.5 ? (up > 0 ? 'canopy' : 'weapons') : Math.random() < 0.5 ? 'engine' : 'hyd';
          heli.hit({ hull: 0.4, sub, subDmg: disc ? 1.3 : sub === 'canopy' ? 3 : 1.6, kind: 'arrows' }); this.stats.arrowHits++;
          n--; for (const k in A) A[k][i] = A[k][n]; i--; continue;
        }
        if (d2 < 60) near++;
      }
      if (A.vy[i] < 0) { const g = terrain.height(A.x[i], A.z[i]); if (A.y[i] < g) { A.y[i] = g + 0.25; A.stuck[i] = 1; A.t[i] = 0; continue; } if (A.y[i] < g + 30 && world.pointHit(A.x[i], A.y[i], A.z[i])) { A.stuck[i] = 1; A.t[i] = 5; continue; } }
      if (night <= 0.3 && (i & 1) === 0 && A.t[i] >= 0 && !A.stuck[i] && Math.random() < dt * 9) fx.streak(A.x[i], A.y[i], A.z[i], A.vx[i], A.vy[i], A.vz[i], 0.2, 0.07, 0.035, 0.5, 0.44, 0.34, 0, 0);
      if (night > 0.3 && (i & 3) === 0 && Math.random() < dt * 20) fx.streak(A.x[i], A.y[i], A.z[i], A.vx[i] * 0.2, A.vy[i] * 0.2, A.vz[i] * 0.2, 0.25, 0.3, 0.06, 2.5 * night, 1.0 * night, 0.25 * night, 0, 0);
    }
    this.na = n;
    if (hits) audio.play('arrowHit', { gain: clamp(0.5 + hits * 0.15, 0.5, 1.4) });
    else if (near > 3 && Math.random() < dt * 6) audio.play('arrowWhoosh');
    this.arrowMat.emissiveIntensity = night > 0.3 ? 2.5 * night : 0;
    for (let i = 0; i < n; i++) {
      if (A.t[i] < 0 && !A.stuck[i]) { _m.makeScale(0, 0, 0); im.setMatrixAt(i, _m); continue; }
      _v.set(A.vx[i], A.vy[i], A.vz[i]).normalize(); _q.setFromUnitVectors(_z, _v); _m.compose(_v2.set(A.x[i], A.y[i], A.z[i]), _q, _s); im.setMatrixAt(i, _m);
    }
    im.count = n; im.instanceMatrix.needsUpdate = true;
  },

  // ---------------- ballista bolts ----------------
  _updateBolts(dt, fly) {
    const hp = heli.pos;
    for (let i = this.bolts.length - 1; i >= 0; i--) {
      const b = this.bolts[i]; b.t += dt; b.vy -= GR * 0.25 * dt;
      // trajectory: a pale vapour line with a bright glint riding the head
      fx.streak(b.x, b.y, b.z, b.vx, b.vy, b.vz, 0.1, 0.085, 0.09, 2.6, 2.2, 1.5, 0, 0);
      b.tr = (b.tr || 0) + dt * 70; while (b.tr > 1) { b.tr -= 1; const k = Math.random() * dt; fx.spawn(0, b.x - b.vx * k, b.y - b.vy * k, b.z - b.vz * k, rndS(0.4), rndS(0.4) + 0.3, rndS(0.4), 0.22, 1.5, rnd(1.6, 2.6), 0.8, 0.78, 0.72, 0.34, 0, 1, -0.05); }
      const steps = 4; let done = false;
      for (let s = 0; s < steps && !done; s++) {
        b.x += b.vx * dt / steps; b.y += b.vy * dt / steps; b.z += b.vz * dt / steps;
        const d = Math.hypot(b.x - hp.x, b.y - hp.y, b.z - hp.z);
        if (fly && d < 4.2) {
          const tailHit = (b.x - hp.x) * heli.fwd.x + (b.z - hp.z) * heli.fwd.z < -1;
          heli.hit({ hull: 13, sub: tailHit || Math.random() < 0.4 ? 'tail' : 'hyd', subDmg: 44, kind: 'ballista bolt' }); this.stats.boltHits++;
          audio.play('boltHit'); fx.sparks(_v.set(b.x, b.y, b.z), _v2.set(0, 1, 0), 26, 14); fx.debrisBurst(_v, 4, 0.25, 0x3a3f33, heli.vel); done = true;
        } else if (fly && d < 22 && !b.near) { b.near = true; audio.play('boltPass'); heli.shake = Math.min(1.5, heli.shake + 0.25); }
        if (!done && (b.y < terrain.height(b.x, b.z) || (b.t > 0.25 && world.pointHit(b.x, b.y, b.z)))) { fx.dust(b.x, b.y + 0.3, b.z, 0, 2, 0, 1, 1.5, 0.4); done = true; }
      }
      if (done || b.t > 6) { b.mesh.visible = false; this.bolts.splice(i, 1); continue; }
      b.mesh.position.set(b.x, b.y, b.z); _v.set(b.vx, b.vy, b.vz).normalize(); b.mesh.quaternion.setFromUnitVectors(_z, _v);
      if (Math.random() < dt * 40) fx.spawn(2, b.x, b.y, b.z, 0, 0, 0, 0.3, 1.0, 0.5, 0.8, 0.78, 0.74, 0.25, 0, 1, 0);
    }
  },
  // ---------------- bombard shells → flak ----------------
  _updateShells(dt, fly) {
    const hp = heli.pos;
    for (let i = this.shells.length - 1; i >= 0; i--) {
      const s = this.shells[i]; s.t += dt; const k = Math.min(1, s.t / s.tof);
      s.x = lerp(s.sx, s.tx, k); s.y = lerp(s.sy, s.ty, k) + Math.sin(k * Math.PI) * 6; s.z = lerp(s.sz, s.tz, k);
      fx.spawn(3, s.x, s.y, s.z, 0, 0, 0, 1.6, 1.6, 0.05, 1, 0.6, 0.25, 1, 0.6, 0, 0);
      s.tr = (s.tr || 0) + dt * 60; while (s.tr > 1) { s.tr -= 1; fx.spawn(0, s.x + rndS(0.3), s.y + rndS(0.3), s.z + rndS(0.3), rndS(0.5), 0.4 + rndS(0.4), rndS(0.5), 0.45, 2.4, rnd(1.8, 2.8), 0.34, 0.33, 0.32, 0.42, 0.25, 1, -0.1); }
      if (s.px !== undefined) fx.streak(s.x, s.y, s.z, (s.x - s.px) / dt, (s.y - s.py) / dt, (s.z - s.pz) / dt, 0.08, 0.06, 0.16, 4, 1.8, 0.5, 0, 0); s.px = s.x; s.py = s.y; s.pz = s.z;
      if (k >= 1) {
        _v.set(s.tx, s.ty, s.tz); fx.flak(_v); audio.play('flak', { pos: [s.tx, s.ty, s.tz] });
        const d = _v.distanceTo(hp);
        if (fly && d < 30) { const f = 1 - d / 30; heli.hit({ hull: 11 * f + 1, sub: 'engine', subDmg: 34 * f, kind: 'bombard burst' }); if (Math.random() < f) heli.hit({ hull: 0, sub: 'any', subDmg: 16 * f, kind: 'bombard burst' }); this.stats.flakHits++; }
        this.shells.splice(i, 1);
      }
    }
  },
  // ---------------- trebuchet boulders ----------------
  _launchBoulder(e) {
    const hp = heli.pos, hv = heli.vel; const sx = e.x + 2, sy = e.y + 17, sz = e.z;
    let tx = hp.x + hv.x * 0.6, ty = hp.y + hv.y * 0.3, tz = hp.z + hv.z * 0.6;
    if (weapons.flareT > 0) { tx = weapons.flarePos.x + rndS(20); tz = weapons.flarePos.z + rndS(20); }
    const dist = Math.hypot(tx - sx, tz - sz); const T = clamp(2.6 + dist / 130, 3.2, 7.5);
    const vx = (tx - sx) / T, vz = (tz - sz) / T, vy = (ty - sy) / T + 0.5 * GR * T;
    // predicted ground impact for the minimap
    let px = sx, py = sy, pz = sz, pvy = vy, tt = 0; while (tt < 20) { px += vx * 0.1; pz += vz * 0.1; pvy -= GR * 0.1; py += pvy * 0.1; tt += 0.1; if (py < terrain.height(px, pz)) break; }
    const mesh = this.boulderPool.find(b => !b.visible) || this.boulderPool[0]; mesh.visible = true;
    this.boulders.push({ x: sx, y: sy, z: sz, vx, vy, vz, t: 0, ix: px, iz: pz, eta: tt, mesh, whoosh: false, tr: 0 });
    G.events.dispatchEvent(new CustomEvent('boulder', { detail: { x: px, z: pz, eta: tt } }));
  },
  _updateBoulders(dt, fly) {
    const hp = heli.pos;
    for (let i = this.boulders.length - 1; i >= 0; i--) {
      const b = this.boulders[i]; b.t += dt; b.vy -= GR * dt; b.x += b.vx * dt; b.y += b.vy * dt; b.z += b.vz * dt;
      b.mesh.position.set(b.x, b.y, b.z); b.mesh.rotation.x += dt * 3; b.mesh.rotation.z += dt * 2;
      b.tr += dt * 45; while (b.tr > 1) { b.tr -= 1; fx.spawn(1, b.x + rndS(0.5), b.y + rndS(0.5), b.z + rndS(0.5), b.vx * 0.2 + rndS(1), b.vy * 0.2 + rnd(1), b.vz * 0.2 + rndS(1), 1.3, 2.4, rnd(0.4, 0.7), 1, 1, 1, 0.9, 0.5, 1, -2); if (Math.random() < 0.6) { const c = rnd(0.05, 0.12); fx.spawn(0, b.x, b.y, b.z, rndS(1), 1, rndS(1), 1.2, 4.5, rnd(2.5, 4.5), c, c, c, 0.55, 1.5, 0.6, -0.4); } }
      fx.lights[3].position.set(b.x, b.y, b.z); fx.lights[3].color.setHex(0xff7a30); fx.lights[3].distance = 70; fx.lights[3].userData.t = 0; fx.lights[3].userData.dur = 0.1; fx.lights[3].userData.peak = 90;
      const d = Math.hypot(b.x - hp.x, b.y - hp.y, b.z - hp.z);
      if (fly && d < 60 && !b.whoosh) { b.whoosh = true; audio.play('boulderWhoosh', { pos: [b.x, b.y, b.z] }); }
      let hit = false;
      if (fly && d < 6.5) { heli.hit({ hull: 48, sub: 'rotor', subDmg: 55, kind: 'trebuchet boulder' }); this.stats.boulderHits++; hit = true; }
      const g = terrain.height(b.x, b.z); const c = world.pointHit(b.x, b.y, b.z);
      if (hit || b.y < g || c) {
        _v.set(b.x, Math.max(b.y, g), b.z);
        if (!c && g < L.WATER_Y) fx.splash(b.x, b.z, 3); else fx.explosion(_v, 1.6, { fire: true, fireLife: 22 });
        audio.play('boulderImpact', { pos: [b.x, b.y, b.z] }); crowd.blast(b.x, _v.y, b.z, 8, 10, 1);
        if (c && c.ref && c.ref.type) castle.damage(c.ref, 70, _v);
        b.mesh.visible = false; this.boulders.splice(i, 1);
      }
    }
  },
};
let _gt = null;
function glintTex() {
  if (_gt) return _gt; const c = document.createElement('canvas'); c.width = c.height = 128; const x = c.getContext('2d');
  const g = x.createRadialGradient(64, 64, 0, 64, 64, 64); g.addColorStop(0, 'rgba(255,255,255,1)'); g.addColorStop(0.12, 'rgba(255,240,200,0.7)'); g.addColorStop(0.4, 'rgba(255,200,120,0.12)'); g.addColorStop(1, 'rgba(255,200,120,0)'); x.fillStyle = g; x.fillRect(0, 0, 128, 128);
  x.globalCompositeOperation = 'lighter'; for (const a of [0, Math.PI / 2, Math.PI / 4, -Math.PI / 4]) { x.save(); x.translate(64, 64); x.rotate(a); const l = x.createLinearGradient(-64, 0, 64, 0); l.addColorStop(0, 'rgba(255,255,255,0)'); l.addColorStop(0.5, 'rgba(255,255,255,0.9)'); l.addColorStop(1, 'rgba(255,255,255,0)'); x.fillStyle = l; x.fillRect(-64, -1.5, 128, 3); x.restore(); }
  _gt = new THREE.CanvasTexture(c); return _gt;
}
