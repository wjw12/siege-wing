// Siege Wing — bootstrap, state machine, main loop
import * as THREE from 'three';
import { G, V3, installShaderPatches, clamp, lerp, damp, sat, smooth, DEG } from './core.js';
import { terrain, L } from './terrain.js';
import { sky } from './sky.js';
import { post } from './post.js';
import { dev, Q } from './dev.js';
import { input, settings } from './input.js';
import { heli, SUBS } from './heli.js';
import { fx } from './fx.js';
import { audio } from './audio.js';
import { director } from './director.js';
import { loadAssets, assets } from './assets.js';
import { castle } from './castle.js';
import { scenery } from './scenery.js';
import { crowd } from './crowd.js';
import { threats } from './threats.js';
import { weapons } from './weapons.js';
import { mission } from './mission.js';
import { hud } from './hud.js';
import { ui } from './ui.js';

dev.init();
installShaderPatches();
const QUALITY = { high: { px: 1.5, maxW: 1920, shadow: 4096 }, medium: { px: 1.0, maxW: 1600, shadow: 2048 }, low: { px: 0.8, maxW: 1280, shadow: 1024 } }[Q.get('q') || settings.quality] || { px: 1.5, maxW: 1920, shadow: 4096 };
const canvas = document.getElementById('c');
const renderer = G.renderer = new THREE.WebGLRenderer({ canvas, antialias: false, powerPreference: 'high-performance', stencil: false, depth: false });
renderer.shadowMap.enabled = !Q.has('noshadow'); renderer.shadowMap.type = THREE.PCFSoftShadowMap;
renderer.toneMapping = THREE.NoToneMapping; renderer.info.autoReset = false;
const scene = G.scene = new THREE.Scene();
const camera = G.camera = new THREE.PerspectiveCamera(70, 1, 0.6, 14000);
post.init(renderer);
function resize() { const w = innerWidth, h = innerHeight; const pr = Math.min(devicePixelRatio || 1, QUALITY.maxW / w, QUALITY.px); renderer.setPixelRatio(pr); renderer.setSize(w, h, false); camera.aspect = w / h; camera.updateProjectionMatrix(); post.resize(Math.round(w * pr), Math.round(h * pr)); }
addEventListener('resize', resize); resize();
input.init(canvas);

let state = 'loading', paused = false, T = 0, playT = 0, menuT = 0, endShown = false, fadeT = 0, pendingStart = null, slowmo = 1;
const tick = () => new Promise(r => setTimeout(r, 0));

async function boot() {
  const t0 = performance.now();
  director.init(); // audio: start streaming the sample bank, first-gesture init, event wiring
  ui.loading(0.05, 'LOADING MODELS');
  await loadAssets(p => ui.loading(0.05 + p * 0.3));
  ui.loading(0.4, 'RAISING THE VALLEY'); await tick();
  terrain.build(scene); await tick();
  sky.build(scene); sky.sun.shadow.mapSize.set(QUALITY.shadow, QUALITY.shadow);
  fx.init(scene); fx.onShake = s => { heli.shake = Math.min(2.5, heli.shake + s); };
  ui.loading(0.55, 'BUILDING THE CASTLE'); await tick();
  castle.build(scene);
  ui.loading(0.65, 'PLANTING THE FOREST'); await tick();
  scenery.build(scene);
  ui.loading(0.8, 'MUSTERING 2,000 MEN'); await tick();
  crowd.build(scene); threats.build(scene); weapons.init(scene); mission.init();
  heli.bindModel(assets.heli.scene); navLights();
  hud.init(); hud.bindMFD();
  ui.init({ start: startGame, resume, quit, events: G.events });
  ui.loading(1, 'READY'); await tick();
  dev.log('built in ' + (performance.now() - t0).toFixed(0) + 'ms; soldiers=' + crowd.total);
  input.onUnlock = () => { if (state === 'play' && !paused && !dev.on) pause(); };
  G.events.addEventListener('missionEnd', () => { endShown = false; });
  addEventListener('keydown', e => {
    if (e.code === settings.keys.restart && (state === 'play') && (mission.state === 'won' || mission.state === 'lost' || paused)) startGame(true);
    if (e.code === settings.keys.pause && state === 'play' && !paused && mission.state === 'play') { input.unlock(); pause(); }
  });
  toMenu();
  // dev / test entry points
  if (Q.has('play') || Q.has('auto') || Q.has('approach')) { startGame(!Q.has('approach'), true); devSetup(); }
  requestAnimationFrame(frame);
}

function navLights() {
  const mk = (name, col, r) => { const n = heli.nodes[name]; if (!n) return null; const m = new THREE.Mesh(new THREE.SphereGeometry(r * 0.6, 8, 6), new THREE.MeshBasicMaterial({ color: col, fog: false })); m.material.color.multiplyScalar(3); n.add(m); return m; };
  heli.navL = mk('Light_Nav_L', 0xff2010, 0.07); heli.navR = mk('Light_Nav_R', 0x10ff30, 0.07); heli.beacon = mk('Light_Beacon', 0xff2010, 0.09);
}

// ---------- state transitions ----------
function toMenu() {
  state = 'menu'; paused = false; menuT = 0; hud.clear(); input.enabled = false; input.unlock();
  castle.reset(); crowd.reset(); threats.reset(); weapons.reset(); fx.clear(); terrain.clearScorch(); mission.state = 'idle'; mission.phase = 0;
  heli.reset(L.PAD.x, L.PAD.y + heli.gearY + 0.15, L.PAD.z, 80 * DEG, 0); heli.onGround = true; heli.rpm = 0.25; heli.cockpit = false;
  sky.setTime(0.14); sky.envT = 1e9; post.p.fade = 0; post.p.desat = 0;
  ui.show('menu'); ui.refresh();
}
let pendingFade = 0;
function startGame(skipApproach, immediate) {
  if (!Q.has('mute')) { audio.init(); audio.resume(); audio.setVolume(settings.volume, 1, 1); audio.stopAll(); }
  ui.hide(); ui.fade(true);
  const go = () => {
    if (Q.get('mode')) settings.mode = Q.get('mode');
    fx.clear(); hud.clear(); mission.start(skipApproach); heli.rpm = 1; heli.cockpit = Q.has('cockpit');
    sky.setTime(mission.time / 600); sky.envT = 1e9; terrain.farDirty = true;
    state = 'play'; paused = false; playT = 0; endShown = false; input.enabled = true; post.p.desat = 0; slowmo = 1;
    if (!dev.on) input.lock();
    pendingFade = 4;   // lift the fade only after the first heavy frames (shader warm-up, sky refresh) have been drawn behind it
  };
  if (immediate) go(); else setTimeout(go, 260);
}
function pause() { if (state !== 'play' || mission.state !== 'play') return; paused = true; input.enabled = false; audio.suspend(); ui.showPause(`${mission.objective} — ${mission.progress}`); }
function resume() { if (state !== 'play') return; paused = false; input.enabled = true; audio.resume(); ui.hide(); input.lock(); }
function quit() { audio.resume(); audio.stopAll(); toMenu(); }

// ---------- dev helpers ----------
let auto = null, cams = null, nShots = 0, logT = 0;
function devSetup() {
  auto = Q.get('auto'); if (auto) input.virtual = { held: new Set(), hit: new Set(), dx: 0, dy: 0 };
  cams = Q.get('cams') ? Q.get('cams').split(';').map(c => c.split(',').map(Number)) : null; nShots = dev.shots.length;
  if (Q.get('pos')) { const sp = Q.get('pos').split(',').map(Number); heli.reset(sp[0], sp[1], sp[2], parseFloat(Q.get('yaw') || '90') * DEG, parseFloat(Q.get('spd') || '0')); }
  if (Q.get('phase')) { mission.setPhase(+Q.get('phase'), true); }
  if (Q.get('time')) mission.time = +Q.get('time');
  if (Q.get('kill')) setTimeout(() => castle.destroy(castle.towers[parseInt(Q.get('kill'))]), 2500);
  if (Q.has('god')) heli.hit = () => { };
  dev.capture = () => { const c = document.createElement('canvas'); c.width = canvas.width; c.height = canvas.height; const x = c.getContext('2d'); x.drawImage(canvas, 0, 0); if (!Q.has('nohud')) x.drawImage(hud.cv, 0, 0, c.width, c.height); return c.toDataURL('image/jpeg', 0.9); };
  dev.extra = () => `prof=${JSON.stringify(Object.fromEntries(Object.entries(dev.prof || {}).map(([k, v]) => [k, +v.toFixed(1)])))}${(dev.prof = {}) && ''} fx=${fx.n} arrows=${threats.na} killed=${crowd.killed} hull=${heli.hull.toFixed(0)} phase=${mission.phase} st=${mission.state}/${heli.state}${dev.am ? ` audio={pk:${dev.am.pk.toFixed(2)},rms:${(dev.am.rms / dev.am.n).toFixed(3)},clipFrames:${dev.am.clip}/${dev.am.n},lo:${(dev.am.lo / dev.am.n | 0)},mid:${(dev.am.mid / dev.am.n | 0)},hi:${(dev.am.hi / dev.am.n | 0)},ctx:${audio.context && audio.context.state}}` : ''}${(dev.am = null) || ''}`;
}
function autopilot(name, t, dt) {
  const v = input.virtual; v.held.clear(); v.dx = 0; v.dy = 0;
  const stab = settings.mode === 'stabilized'; const hold = alt => { if (heli.agl < alt - 2 || heli.vs < -1.5) v.held.add('collUp'); else if (heli.agl > alt + 6 && heli.vs > -1) v.held.add('collDown'); };
  const pitchTo = deg => { const err = deg * DEG - heli.pitch; v.dy = clamp(err * 60, -30, 30) * (stab ? 0.3 : 1); };
  const rollTo = deg => { const err = deg * DEG - heli.roll; v.dx = -clamp(err * 60, -30, 30) * (stab ? 0.3 : 1); };
  const A = Q.get('alt') ? +Q.get('alt') : 45;
  if (name === 'hover') { hold(A); if (!stab) { pitchTo(0); rollTo(0); } }
  if (name === 'fwd') { pitchTo(t < 12 ? -22 : 10); rollTo(0); hold(A); }
  if (name === 'gun') { hold(A); if (!stab) { pitchTo(0); rollTo(0); } v.held.add('gunner'); if (t > 1.0) v.held.add('fire'); if (t < 0.8) v.dy = 5; v.dx += Math.sin(t * 1.3) * 3; }
  if (name === 'rockets') { hold(A); pitchTo(-14); rollTo(0); if (t > 0.3 && t < 0.5) v.hit.add('wpn2'); if (t > 1.2) v.held.add('fire'); }
  if (name === 'missile') { hold(A); if (!stab) { pitchTo(-3); rollTo(0); } if (t > 0.3 && t < 0.5) v.hit.add('wpn3'); if (weapons.lock.locked) v.hit.add('fire'); }
  if (name === 'lowpass') { pitchTo(heli.speed < 45 ? -20 : -5); rollTo(0); hold(A); }
  if (name === 'crash') { pitchTo(-35); }
  if (name === 'land') { if (t < 3) { v.held.add('fire'); heli.hull = 60; } else if (!heli.onGround && heli.vs > (heli.agl > 14 ? -6 : -1.4)) v.held.add('collDown'); if ((bot.lt = (bot.lt || 0) + dt) > 2) { bot.lt = 0; dev.log(`LAND t=${t.toFixed(0)} agl=${heli.agl.toFixed(1)} vs=${heli.vs.toFixed(1)} ground=${heli.onGround} pad=${heli.onPad} cannon=${weapons.ammo.cannon} hull=${heli.hull.toFixed(0)} st=${heli.state}`); } }
  if (name === 'bot') { botPlay(v, t, dt);
    // jink on the ballista tell, the way the gunner calls it: change height hard while the bolt is in the air
    let aimT = 0; for (const e of threats.engines) if (e.kind === 'ballista' && e.alive && e.state === 'aim') aimT = Math.max(aimT, e.t);
    if (threats.shells.some(sh => sh.t < 0.25)) aimT = 1;
    if (mission.phase === 3) aimT = 0;
    if (aimT > 0.95 && !(bot.jink > 0)) { bot.jink = 3.4; bot.jdir = mission.phase <= 1 ? 1 : heli.agl > 110 ? -1 : heli.agl < 70 ? 1 : (bot.jdir === 1 ? -1 : 1); }
    if (bot.jink > 0 && heli.state === 'fly' && !heli.onGround && !(bot.rtb && heli.agl < 30)) { bot.jink -= dt; v.held.delete('collUp'); v.held.delete('collDown'); v.held.add(bot.jdir > 0 ? 'collUp' : 'collDown'); }
  }
}

const SPEED = Math.max(1, +(Q.get('speed') || 1));
function playStep(dt) {
  playT += dt;
  if (auto) autopilot(auto, playT, dt);
  if (Q.has('ammo')) { weapons.ammo.cannon = 600; weapons.ammo.rockets = 38; weapons.ammo.missiles = Math.max(weapons.ammo.missiles, 2); }
  mission.update(dt);
  if (dev.on) { const P = dev.prof = dev.prof || {}; const tm = (n, f) => { const a = performance.now(); f(); const d = performance.now() - a; if (!(P[n] > d)) P[n] = d; }; tm('heli', () => heli.update(dt)); tm('weapons', () => weapons.update(dt)); tm('threats', () => threats.update(dt)); tm('crowd', () => crowd.update(dt, heli, camera)); }
  else { heli.update(dt); weapons.update(dt); threats.update(dt); crowd.update(dt, heli, camera); }
  sky.setTime(Q.get('tod') ? +Q.get('tod') : mission.tod);
  if (input.virtual) input.virtual.hit.clear();
}
// scripted bot that plays the mission (stabilized mode) — used for end-to-end testing
const bot = { fireT: 0, last: '' };
function botPlay(v, t, dt) {
  const p = heli.pos; let tgt = null, standoff = 200, alt = 152, wpn = 0;
  if (mission.phase <= 1) { let bd = 1e9; for (const f of crowd.forms) if (f.kind === 'infantry' && !f.routed) { const d = Math.hypot(f.cx - p.x, f.cz - p.z); if (d < bd) { bd = d; tgt = { x: f.cx, y: f.cy + 1, z: f.cz }; } } }
  else if (mission.phase === 2) { let bd = 1e9; for (const s of castle.towers) if (s.kind === 'gate' && s.alive) { const d = Math.hypot(s.x - p.x, s.z - p.z); if (d < bd) { bd = d; tgt = { x: s.x, y: s.topY - 3, z: s.z, ref: s }; } } standoff = 430; alt = -42; wpn = tgt && tgt.ref.hp <= 75 ? 0 : 2; }
  else { const w = crowd.warlord; tgt = { x: crowd.x[w], y: crowd.y[w] + 1, z: crowd.z[w] }; standoff = 75; alt = 205; }
  // return to the pad when badly hurt, land, repair, go again
  if (((heli.hull < (mission.phase >= 2 ? 50 : 42) && mission.lightLeft > 100) || (mission.phase === 3 && !bot.p3 && heli.hull < 80 && mission.lightLeft > 170) || (!Q.has('ammo') && weapons.ammo.cannon < 30 && weapons.ammo.rockets === 0) || (!Q.has('ammo') && mission.phase === 2 && weapons.ammo.missiles === 0 && tgt && tgt.ref && tgt.ref.hp > 75)) && !bot.rtb) { bot.rtb = true; dev.log(`BOT RTB t=${t.toFixed(0)} hull=${heli.hull.toFixed(0)}`); }
  if (mission.phase === 3 && !bot.rtb) bot.p3 = true; if (mission.phase < 3) bot.p3 = false;
  if (bot.rtb && heli.onPad && heli.hull >= 99) { bot.rtb = false; dev.log(`BOT REPAIRED t=${t.toFixed(0)}`); }
  if (bot.rtb) { tgt = { x: L.PAD.x, y: terrain.height(L.PAD.x, L.PAD.z), z: L.PAD.z }; standoff = 0; alt = 40; }
  if (!tgt) return;
  // rocket attack runs on the field army: dive at the block, ripple rockets, break away, come round again
  if (!bot.rtb && (mission.phase <= 1) && settings.mode !== 'stabilized' && weapons.ammo.rockets > 0 && Q.has('orbit')) {
    const dxr = tgt.x - p.x, dzr = tgt.z - p.z, dh = Math.hypot(dxr, dzr); bot.eg = Math.max(0, (bot.eg || 0) - dt);
    if (dh < (mission.phase === 2 ? 210 : mission.phase === 3 ? 140 : 215) && bot.eg <= 0) bot.eg = 8;
    const wy = bot.eg > 0 ? Math.atan2(-1, -(p.z > tgt.z ? 0.5 : -0.5)) : Math.atan2(-dxr, -dzr); let ye = wy - heli.yaw; ye = Math.atan2(Math.sin(ye), Math.cos(ye)); if (ye > 0.03) v.held.add('yawL'); else if (ye < -0.03) v.held.add('yawR');
    if (weapons.sel !== 1) v.hit.add('wpn2');
    const want = Math.max(tgt.y + (bot.eg > 0 ? 120 : mission.phase === 3 ? 200 : 150), terrain.height(p.x, p.z) + 55); if (p.y < want - 3) v.held.add('collUp'); else if (p.y > want + 8) v.held.add('collDown');
    const aim = Math.atan2(tgt.y - p.y, dh) + 0.03; const tp = bot.eg > 0 ? -0.22 : dh > 430 ? -0.28 : Math.max(aim, -0.85);
    if (heli.agl > 10) { v.dy = clamp((tp - heli.pitch) * 60, -30, 30); v.dx = -clamp((0 - heli.roll) * 60, -30, 30); }
    if (bot.eg <= 0 && dh < 440 && dh > 200 && Math.abs(ye) < 0.05 && Math.abs(heli.pitch - tp) < 0.04) v.held.add('fire');
    return;
  }
  // hold a position east of the target at standoff
  let dx = p.x - tgt.x, dz = p.z - tgt.z; let dl = Math.hypot(dx, dz) || 1; const orbit = Q.has('orbit') && !bot.rtb; if (mission.phase === 3 && !orbit) { dx = 1; dz = 0.2; dl = Math.hypot(dx, dz); }
  const gx = tgt.x + dx / dl * standoff, gz = tgt.z + dz / dl * standoff, gy = Math.max(tgt.y + alt + (orbit && mission.phase <= 1 ? 8 * Math.sin(t * 0.5) : 0), terrain.height(p.x, p.z) + 38);
  const ex = gx - p.x, ez = gz - p.z; const dist = Math.hypot(ex, ez);
  if (threats.boulders.some(b => b.t < 0.3) && !(bot.flipCd > 0)) { bot.odir = -(bot.odir || 1); bot.flipCd = 2.5; } bot.flipCd = (bot.flipCd || 0) - dt;
  const ov = orbit ? +(Q.get('orbit') || 16) * (bot.odir || 1) * (mission.phase >= 2 ? 1.5 : 1) : 0; const vmax = bot.rtb && dist > 250 ? 50 : 28; const wantVx = clamp(ex * 0.22, -vmax, vmax) - dz / dl * ov, wantVz = clamp(ez * 0.22, -vmax, vmax) + dx / dl * ov; const evx = wantVx - heli.vel.x, evz = wantVz - heli.vel.z;
  const fwdx = -Math.sin(heli.yaw), fwdz = -Math.cos(heli.yaw); const af = evx * fwdx + evz * fwdz, ar = evx * -fwdz + evz * fwdx;
  const settled = orbit ? dist < 70 : dist < 45 && heli.speed < 7;
  if (!settled || orbit) { heli.stickP = clamp(-af * 0.05, -0.5, 0.5); heli.stickR = clamp(-ar * 0.05, -0.5, 0.5); heli.idleT = 0; }
  if (settings.mode !== 'stabilized') { // fly it with the virtual mouse, like a player would
    const lowK = heli.agl < 10 ? 0 : 1; const tp = clamp(-af * 0.05, -0.5, 0.5) * lowK, tr = clamp(-ar * 0.05, -0.5, 0.5) * lowK;
    v.dy = clamp((tp - heli.pitch) * 60, -30, 30); v.dx = -clamp((tr - heli.roll) * 60, -30, 30);
  }
  const landing = bot.rtb && dist < 14 && heli.speed < 5;
  const ey = gy - p.y; if (landing) { if (!heli.onGround && heli.vs > (heli.agl > 14 ? -5 : -1.3)) v.held.add('collDown'); } else if (ey > 3 || heli.vs < -2) v.held.add('collUp'); else if (ey < -6) v.held.add('collDown');
  // face the target
  const wantYaw = Math.atan2(-(tgt.x - p.x), -(tgt.z - p.z)); let yawErr = wantYaw - heli.yaw; yawErr = Math.atan2(Math.sin(yawErr), Math.cos(yawErr)); if (yawErr > 0.06) v.held.add('yawL'); else if (yawErr < -0.06) v.held.add('yawR');
  if (weapons.sel !== wpn) v.hit.add('wpn' + (wpn + 1));
  if (settled && !bot.rtb && Math.abs(yawErr) < 0.6) {
    v.held.add('gunner'); const d3 = Math.hypot(tgt.x - p.x, tgt.y - p.y, tgt.z - p.z);
    heli.aimYaw = wantYaw + Math.sin(t * 1.7) * (wpn === 0 ? 6 / d3 : 0); heli.aimPitch = Math.asin((tgt.y - p.y) / d3) + Math.cos(t * 2.3) * (wpn === 0 ? 5 / d3 : 0);
    if (wpn === 0) { bot.fireT += dt; if (weapons.overheated) bot.fireT = -1.5; if (bot.fireT > 0 && weapons.heat < 0.85) v.held.add('fire'); }
    else if (weapons.lock.locked && (!tgt.ref || (weapons.lock.target && weapons.lock.target.ref === tgt.ref))) v.hit.add('fire');
  }
  if (dev.on && (bot.dbg = (bot.dbg || 0) + dt) > 10) { bot.dbg = 0; dev.log(`BOT t=${t.toFixed(0)} ph=${mission.phase} dist=${dist.toFixed(0)} spd=${heli.speed.toFixed(0)} settled=${settled} yawErr=${yawErr.toFixed(2)} sel=${weapons.sel} lock=${weapons.lock.t.toFixed(1)}/${weapons.lock.locked} msl=${weapons.ammo.missiles} hull=${heli.hull.toFixed(0)} killed=${crowd.killed} guard=${crowd.guardForm.alive} wl=${crowd.warlordHp} rk=${weapons.ammo.rockets}`); }
}
// ---------- main loop ----------
let last = performance.now();
const focus = new V3(), camDir = new V3(), listenerR = new V3();
function frame(now) {
  requestAnimationFrame(frame); const fT0 = performance.now();
  const rdt = Math.min((now - last) / 1000, 0.05); last = now;
  const playing = state === 'play' && !paused;
  let dt = playing || state === 'menu' ? rdt * slowmo : 0;
  T += dt; G.time = T; G.dt = dt; G.U.uTime.value = T; renderer.info.reset();

  if (state === 'menu') {
    menuT += dt; mission.state = 'idle';
    heli.rpm = 0.25; heli.T = 0.3; heli._derive(); heli._visuals(dt);
    crowd.update(dt, heli, camera); threats.update(dt);
    // slow cinematic drift over the field toward the castle
    const a = menuT * 0.035 + 0.5; const r = 330 + Math.sin(menuT * 0.05) * 90; const cxm = 40, czm = 0;
    camera.position.set(cxm + Math.cos(a) * r + 200, 58 + Math.sin(menuT * 0.07) * 16, czm + Math.sin(a) * r * 0.75); camera.up.set(0, 1, 0);
    camera.lookAt(-140, 62, 0); camera.fov = 50; camera.near = 0.6; camera.updateProjectionMatrix();
    focus.set(160, 26, 0);
    sky.update(dt, focus, 300);
  } else if (state === 'play') {
    if (dt > 0) {
      for (let k = 1; k < SPEED; k++) { playStep(dt); fx.update(dt, camera); T += dt; G.time = T; G.U.uTime.value = T; }
      playStep(dt);
      // crash drama: brief slow motion on destruction, end panel after the fireball
      if (mission.state === 'lost' || mission.state === 'won') {
        slowmo = mission.endT < 1.2 && mission.state === 'lost' ? 0.45 : 1;
        if (!endShown && mission.endT > (mission.state === 'won' ? 4.5 : heli.state === 'crashing' ? 9 : 4.2) || (!endShown && heli.state === 'dead' && heli.crashT > 3.6 && mission.state === 'lost')) { endShown = true; input.enabled = false; input.unlock(); ui.showEnd(mission.state === 'won', mission.cause, mission.score, mission.result); dev.log('END ' + mission.state + ' cause=' + mission.cause + ' score=' + mission.score + ' ' + JSON.stringify(mission.result)); if (dev.on && Q.has('endstop')) setTimeout(() => dev.log('DONE'), 600); }
      }
    }
    heli.updateCamera(dt, camera);
    if (cams) { const c = cams[Math.min(cams.length - 1, nShots - dev.shots.length)]; camera.position.set(c[0], c[1], c[2]); camera.up.set(0, 1, 0); camera.lookAt(c[3], c[4], c[5]); camera.fov = c[6] || 60; camera.updateProjectionMatrix(); }
    focus.copy(heli.pos); if (!heli.cockpit) focus.lerp(heli.cam.look, 0.35);
    sky.update(dt, focus, clamp(130 + heli.agl * 1.5, 150, 330));
    // nav lights
    const bl = (T % 1.1) < 0.12; if (heli.beacon) heli.beacon.visible = bl; const nv = G.U.uNight.value > 0.1 || (T % 1.6) < 0.8; if (heli.navL) { heli.navL.visible = nv; heli.navR.visible = nv; }
  }
  { const a0 = performance.now(); if (dt > 0) { fx.update(dt, camera); scenery.update(dt, camera); terrain.update(dt); } if (dev.on) { const P = dev.prof = dev.prof || {}; const d = performance.now() - a0; if (!(P.fx > d)) P.fx = d; } }

  // ---- audio ----
  const aT0 = performance.now();
  if (audio.context && state !== 'loading' && !Q.has('noaudio')) {
    camDir.set(0, 0, -1).applyQuaternion(camera.quaternion); listenerR.set(1, 0, 0).applyQuaternion(camera.quaternion);
    const inPlay = state === 'play'; const fly = inPlay && heli.state === 'fly';
    const near = crowd.forms.reduce((m, f) => (f.kind !== 'crew' && !f.routed && f.alive > 10 ? Math.min(m, Math.hypot(f.cx - camera.position.x, f.cz - camera.position.z, (f.cy || 0) - camera.position.y)) : m), 3000);
    if (dev.on && Q.has('ameter')) { const m = audio.meter(); if (m) { const A = dev.am = dev.am || { pk: 0, rms: 0, n: 0, clip: 0, lo: 0, mid: 0, hi: 0 }; A.pk = Math.max(A.pk, m.pk); A.rms += m.rms; A.n++; if (m.pk > 0.985) A.clip++; A.lo += m.lo; A.mid += m.mid; A.hi += m.hi; } }
    audio.update(rdt, {
      listener: [camera.position.x, camera.position.y, camera.position.z], fwd: [camDir.x, camDir.y, camDir.z], right: [listenerR.x, listenerR.y, listenerR.z],
      active: inPlay && !paused, rotorRPM: inPlay ? (heli.state === 'dead' || heli.state === 'gone' ? 0 : heli.rpm) : 0, rotorLoad: heli.load, speed: heli.speed, cockpit: heli.cockpit && fly,
      dmgRotor: heli.dmgK('rotor'), dmgEngine: heli.dmgK('engine'), dmgTail: heli.dmgK('tail'),
      crowd: crowd.strength || 0, crowdPanic: crowd.panicLevel || 0, crowdDist: near, cheer: crowd.cheering ? 1 : 0, fire: sat(fx.emitters.length / 14) * (near < 800 ? 1 : 0.4),
      warnBallista: fly ? threats.aimWarn : 0, lock: fly && weapons.sel === 2 && weapons.lock.target ? (weapons.lock.locked ? 2 : 1) : 0, boundary: fly ? (mission.outside ? 2 : mission.warnBand ? 1 : 0) : 0,
      masterAlarm: fly && (heli.hull < 30 || heli.sub.tail <= 0), sink: fly && (heli.vrs > 0.25 || (heli.agl < 25 && heli.vs < -7)), lowRPM: false, overheat: weapons.heat, gunFiring: weapons.firing, night: G.U.uNight.value,
    });
  }
  director.update(rdt, state, paused);
  if (dev.on) { const P = dev.prof = dev.prof || {}; const d = performance.now() - aT0; if (!(P.audio > d)) P.audio = d; }
  // ---- post params ----
  const pp = post.p; pp.exposure = sky.exposure;
  pp.damage = state === 'play' ? clamp(heli.hitFlash * 0.7 + (heli.hull < 30 && heli.state === 'fly' ? 0.18 + 0.12 * Math.sin(T * 6) : 0), 0, 1) : 0;
  pp.edgeDark = state === 'play' ? damp(pp.edgeDark, mission.outside ? 0.6 : mission.warnBand ? 0.12 : 0, 4, rdt) : 0;
  pp.dof = state === 'play' && heli.cockpit && heli.state === 'fly' ? 0.12 : 0;
  pp.desat = damp(pp.desat, state === 'play' && mission.state === 'lost' ? 0.55 : 0, 1.5, rdt);
  pp.vignette = state === 'menu' ? 0.5 : heli.gunner ? 0.5 : 0.32;
  if (pendingFade > 0 && --pendingFade === 0) ui.fade(false);
  { const a0 = performance.now(); post.render(scene, camera, sky.sunDir, sky.sunVisible); const a1 = performance.now(); if (!Q.has('nohuddraw')) hud.draw(rdt, paused ? 'paused' : state); if (dev.on) { const P = dev.prof = dev.prof || {}; if (!(P.render > a1 - a0)) P.render = a1 - a0; const d = performance.now() - a1; if (!(P.hud > d)) P.hud = d; } }
  input.endFrame();
  if (dev.on) { const P = dev.prof = dev.prof || {}; const d = performance.now() - fT0; if (!(P.frame > d)) P.frame = d; }
  if (dev.on) { if (auto && !Q.has('nolog') && playT > logT) { logT += 1; dev.log(`t=${playT.toFixed(0)} agl=${heli.agl.toFixed(1)} spd=${heli.speed.toFixed(1)} vs=${heli.vs.toFixed(1)} p=${(heli.pitch / DEG).toFixed(0)} r=${(heli.roll / DEG).toFixed(0)} y=${(heli.yaw / DEG).toFixed(0)} T=${heli.T.toFixed(2)} hull=${heli.hull.toFixed(0)} st=${heli.state} ph=${mission.phase} killed=${crowd.killed}`); } dev.frame(state === 'play' ? playT : menuT, rdt); }
}
boot().catch(e => { dev.log('BOOT FAIL ' + (e.stack || e)); console.error(e); document.getElementById('loadtxt').textContent = 'FAILED TO START: ' + e.message; });
