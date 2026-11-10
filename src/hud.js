// Siege Wing — HUD (2D canvas overlay): flight symbology, reticles, weapons, damage, minimap, warnings, messages
import * as THREE from 'three';
import { G, V3, clamp, lerp, sat, smooth, DEG, TAU, wrapPi } from './core.js';
import { terrain, L, riverX, forestDensity } from './terrain.js';
import { heli, SUBS, SUB_NAMES } from './heli.js';
import { weapons, WPN } from './weapons.js';
import { threats } from './threats.js';
import { crowd } from './crowd.js';
import { castle } from './castle.js';
import { mission } from './mission.js';
import { settings, keyLabel } from './input.js';

const _v = new V3(), _v2 = new V3();
const COL = { fg: 'rgba(226,242,214,0.95)', dim: 'rgba(226,242,214,0.55)', faint: 'rgba(226,242,214,0.28)', amber: '#ffb02e', red: '#ff4a36', good: '#9dff8a', dark: 'rgba(8,12,10,0.55)', panel: 'rgba(10,14,12,0.42)' };
const FONT = (px, w = 600) => `${w} ${px}px "Segoe UI", "Helvetica Neue", Arial, sans-serif`;
const _mq = new THREE.Quaternion(), _mv = new V3();
const MONO = (px, w = 600) => `${w} ${px}px Consolas, "SF Mono", ui-monospace, monospace`;

const _q2d = { x: 0, y: 0 };
export const hud = {
  cv: null, c: null, w: 0, h: 0, s: 1, msgs: [], banner: null, visible: true, map: null, hitDirs: [], boulders: [], t: 0,
  init() {
    const cv = this.cv = document.createElement('canvas'); cv.id = 'hud'; cv.style.cssText = 'position:fixed;inset:0;width:100%;height:100%;pointer-events:none;z-index:5';
    document.body.appendChild(cv); this.c = cv.getContext('2d'); this.resize();
    addEventListener('resize', () => this.resize());
    G.events.addEventListener('msg', e => this.msg(e.detail.text, e.detail.kind, e.detail.dur));
    G.events.addEventListener('banner', e => { this.banner = { title: e.detail.title, sub: e.detail.sub, t: 0 }; });
    G.events.addEventListener('boulder', e => this.boulders.push({ x: e.detail.x, z: e.detail.z, eta: e.detail.eta, t: 0 }));
    this._bakeMap();
    this.mfd = [0, 1, 2].map(() => { const c = document.createElement('canvas'); c.width = c.height = 256; const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; return { c, x: c.getContext('2d'), t }; });
    for (const m of this.mfd) { const t = m.t; t.wrapT = THREE.RepeatWrapping; t.repeat.y = -1; t.offset.y = 1; }   // the MFD screens' UVs are vertically flipped in the model
    this.mfdT = 0;
  },
  bindMFD() {
    ['MFD_L', 'MFD_R', 'MFD_C'].forEach((n, i) => { const o = heli.nodes[n]; if (o && o.isMesh) { o.material = new THREE.MeshBasicMaterial({ map: this.mfd[i].t, toneMapped: false, fog: false }); o.material.color.setScalar(1.6); } });
  },
  resize() { const dpr = Math.min(devicePixelRatio || 1, 2); this.w = innerWidth; this.h = innerHeight; this.cv.width = Math.round(this.w * dpr); this.cv.height = Math.round(this.h * dpr); this.dpr = dpr; this.s = clamp(this.h / 900, 0.75, 1.6); },
  msg(text, kind = 'info', dur = 4) { if (this.msgs.length && this.msgs[this.msgs.length - 1].text === text) return; this.msgs.push({ text, kind, t: 0, dur }); if (this.msgs.length > 5) this.msgs.shift(); },
  clear() { this.msgs.length = 0; this.banner = null; this.boulders.length = 0; },

  // top-down map texture of the valley (static)
  _bakeMap() {
    const S = 512, R = 2000; const cv = this.map = document.createElement('canvas'); cv.width = cv.height = S; const c = cv.getContext('2d'); const img = c.createImageData(S, S); const d = img.data;
    for (let j = 0; j < S; j++) for (let i = 0; i < S; i++) {
      const x = (i + 0.5) / S * 2 * R - R, z = (j + 0.5) / S * 2 * R - R; const h = terrain.height(x, z); const hx = terrain.height(x + 12, z) - h;
      let r = 62, g = 72, b = 50; const k = clamp((h - 15) / 260, 0, 1); r += k * 70; g += k * 62; b += k * 52;
      const shade = clamp(1 - hx * 0.06, 0.6, 1.35); r *= shade; g *= shade; b *= shade;
      const f = forestDensity(x, z); if (f > 0.3) { r = lerp(r, 28, 0.6); g = lerp(g, 46, 0.6); b = lerp(b, 28, 0.6); }
      if (terrain.roadDist(x, z) < 5) { r = 150; g = 128; b = 92; }
      if (h < L.WATER_Y) { r = 52; g = 96; b = 128; }
      const o = (j * S + i) * 4; d[o] = r; d[o + 1] = g; d[o + 2] = b; d[o + 3] = 255;
    }
    c.putImageData(img, 0, 0);
    this.mapR = R;
  },

  project(p, out) { // world → screen px; returns false if behind
    _v.copy(p).project(G.camera); out.x = (_v.x * 0.5 + 0.5) * this.w; out.y = (-_v.y * 0.5 + 0.5) * this.h; return _v.z < 1 && _v.z > -1;
  },

  draw(dt, state) {
    const c = this.c; this.t += dt; c.setTransform(this.dpr, 0, 0, this.dpr, 0, 0); c.clearRect(0, 0, this.w, this.h);
    if (!this.visible || state !== 'play') { this._banner(c, dt); return; }
    const s = this.s, w = this.w, h = this.h; const fly = heli.state === 'fly';
    c.lineCap = 'round'; c.lineJoin = 'round'; c.textBaseline = 'middle';
    c.shadowColor = 'rgba(0,0,0,0.65)'; c.shadowBlur = 3 * s;
    if (fly) { this._flight(c, s, w, h); this._reticle(c, s, w, h); this._threatArcs(c, s, w, h, dt); }
    this._objective(c, s, w, h);
    this._weapons(c, s, w, h);
    this._damage(c, s, w, h);
    this._minimap(c, s, w, h, dt);
    this._warnings(c, s, w, h, dt);
    this._messages(c, s, w, h, dt);
    this._banner(c, dt);
    this.mfdT -= dt; if (this.mfdT <= 0 && heli.cockpit) { this.mfdT = 0.2; this._mfd(); }
  },

  // ---------- flight symbology ----------
  _flight(c, s, w, h) {
    const cx = w / 2, cy = h / 2; const ck = heli.cockpit;
    c.strokeStyle = COL.fg; c.fillStyle = COL.fg; c.lineWidth = 1.6 * s;
    if (!ck) {
      // attitude: horizon line + pitch ladder, rolled
      const pxPerDeg = h / G.camera.fov; const roll = heli.roll, pitch = heli.pitch / DEG;
      c.save(); c.translate(cx, cy); c.rotate(-roll); c.globalAlpha = 0.55;
      for (let a = -60; a <= 60; a += 10) { const y = (pitch - a) * -pxPerDeg * -1; const yy = (a - pitch) * -pxPerDeg; if (Math.abs(yy) > h * 0.28) continue; const half = a === 0 ? 150 * s : 46 * s; c.beginPath(); if (a === 0) { c.moveTo(-half, yy); c.lineTo(-60 * s, yy); c.moveTo(60 * s, yy); c.lineTo(half, yy); } else { c.setLineDash(a < 0 ? [5 * s, 5 * s] : []); c.moveTo(-half, yy); c.lineTo(-20 * s, yy); c.moveTo(20 * s, yy); c.lineTo(half, yy); } c.stroke(); c.setLineDash([]); if (a !== 0) { c.font = MONO(10 * s); c.textAlign = 'right'; c.fillText(String(a), -half - 5 * s, yy); } }
      c.restore(); c.globalAlpha = 1;
    }
    // speed (left) and altitude (right) boxes
    const bx = (ck ? 150 : 215) * s, by = cy;
    const spd = Math.round(heli.speed * 3.6), alt = Math.max(0, Math.round(heli.agl)), vs = heli.vs;
    c.font = MONO(22 * s, 700); c.textAlign = 'right'; c.fillText(String(spd), cx - bx, by); c.font = FONT(10 * s); c.fillStyle = COL.dim; c.fillText('KM/H', cx - bx, by + 17 * s);
    c.fillStyle = heli.agl < 12 && heli.vs < -3 ? COL.amber : COL.fg; c.font = MONO(22 * s, 700); c.textAlign = 'left'; c.fillText(String(alt), cx + bx, by); c.font = FONT(10 * s); c.fillStyle = COL.dim; c.fillText('M AGL', cx + bx, by + 17 * s);
    // vertical speed tape
    const vx = cx + bx + 74 * s; c.strokeStyle = COL.faint; c.beginPath(); c.moveTo(vx, by - 46 * s); c.lineTo(vx, by + 46 * s); c.stroke();
    for (let i = -2; i <= 2; i++) { c.beginPath(); c.moveTo(vx - 4 * s, by + i * 23 * s); c.lineTo(vx, by + i * 23 * s); c.stroke(); }
    const vy = by - clamp(vs / 12, -1, 1) * 46 * s; c.fillStyle = vs < -6 ? COL.amber : COL.fg; c.beginPath(); c.moveTo(vx + 2 * s, vy); c.lineTo(vx + 11 * s, vy - 5 * s); c.lineTo(vx + 11 * s, vy + 5 * s); c.closePath(); c.fill();
    c.font = MONO(10 * s); c.textAlign = 'left'; c.fillStyle = COL.dim; c.fillText((vs >= 0 ? '+' : '') + vs.toFixed(1), vx + 15 * s, vy);
    // collective / torque bar (left of speed)
    const tx = cx - bx - 92 * s; c.strokeStyle = COL.faint; c.strokeRect(tx, by - 46 * s, 6 * s, 92 * s);
    const tk = sat((heli.T - 0.2) / 1.6); c.fillStyle = heli.T > 1.55 ? COL.amber : COL.fg; c.fillRect(tx, by + 46 * s - tk * 92 * s, 6 * s, tk * 92 * s);
    const hk = sat((1 - 0.2) / 1.6); c.strokeStyle = COL.fg; c.beginPath(); c.moveTo(tx - 4 * s, by + 46 * s - hk * 92 * s); c.lineTo(tx + 10 * s, by + 46 * s - hk * 92 * s); c.stroke();
    c.font = FONT(9 * s); c.fillStyle = COL.dim; c.textAlign = 'center'; c.fillText('COLL', tx + 3 * s, by + 58 * s);
    // heading tape (top)
    const hy = 46 * s; const hdg = ((-heli.yaw / DEG) % 360 + 360) % 360; c.strokeStyle = COL.dim; c.fillStyle = COL.fg; c.font = MONO(11 * s);
    c.save(); c.beginPath(); c.rect(cx - 170 * s, hy - 16 * s, 340 * s, 34 * s); c.clip();
    for (let a = Math.floor(hdg / 10) * 10 - 40; a <= hdg + 40; a += 10) { const x = cx + (a - hdg) * 4.2 * s; const aa = (a % 360 + 360) % 360; c.beginPath(); c.moveTo(x, hy + 8 * s); c.lineTo(x, hy + (aa % 30 === 0 ? 0 : 4 * s)); c.stroke(); if (aa % 30 === 0) { c.textAlign = 'center'; c.fillText(aa === 0 ? 'N' : aa === 90 ? 'E' : aa === 180 ? 'S' : aa === 270 ? 'W' : String(aa / 10).padStart(2, '0'), x, hy - 8 * s); } }
    c.restore(); c.fillStyle = COL.fg; c.beginPath(); c.moveTo(cx, hy + 11 * s); c.lineTo(cx - 5 * s, hy + 19 * s); c.lineTo(cx + 5 * s, hy + 19 * s); c.closePath(); c.fill();
    // mode tags
    c.font = FONT(10 * s, 700); c.textAlign = 'center'; c.fillStyle = COL.dim;
    const tags = []; if (heli.gunner) tags.push('GUNNER'); if (settings.mode === 'stabilized') tags.push('STAB'); if (settings.mode === 'punishing') tags.push('SIM'); if (heli.onGround) tags.push('GROUND'); if (heli.tumble) tags.push('TUMBLE');
    c.fillText(tags.join('  ·  '), cx, hy + 32 * s);
  },

  // ---------- reticles ----------
  _reticle(c, s, w, h) {
    const p = { x: 0, y: 0 }; const cx = w / 2, cy = h / 2;
    // boresight (nose) marker
    _v2.copy(heli.pos).addScaledVector(heli.fwd, 400); if (this.project(_v2, p) && !heli.gunner) { c.strokeStyle = COL.dim; c.lineWidth = 1.4 * s; c.beginPath(); c.moveTo(p.x - 12 * s, p.y); c.lineTo(p.x - 5 * s, p.y); c.moveTo(p.x + 5 * s, p.y); c.lineTo(p.x + 12 * s, p.y); c.moveTo(p.x, p.y - 5 * s); c.lineTo(p.x, p.y - 10 * s); c.stroke(); }
    const sel = weapons.sel; const ok = this.project(weapons.ccip, p); if (!ok) return;
    const dist = weapons.ccipDist; c.lineWidth = 1.8 * s;
    if (sel === 0) {
      const col = weapons.overheated || weapons.jam.turret ? COL.red : COL.fg; c.strokeStyle = col; c.fillStyle = col;
      const r = (heli.gunner ? 15 : 12) * s + Math.hypot(heli.w.x, heli.w.y, heli.w.z) * 22 * s;
      c.beginPath(); for (let i = 0; i < 4; i++) { const a = i * Math.PI / 2 + Math.PI / 4; c.moveTo(p.x + Math.cos(a) * r, p.y + Math.sin(a) * r); c.arc(p.x, p.y, r, a, a + 0.5); } c.stroke();
      c.beginPath(); c.arc(p.x, p.y, 1.8 * s, 0, TAU); c.fill();
      // heat arc
      if (weapons.heat > 0.02) { c.strokeStyle = weapons.heat > 0.75 ? COL.red : COL.amber; c.lineWidth = 3 * s; c.beginPath(); c.arc(p.x, p.y, r + 7 * s, Math.PI * 0.75, Math.PI * 0.75 + weapons.heat * Math.PI * 1.5); c.stroke(); }
    } else if (sel === 1) {
      const jam = weapons.jam.podL && weapons.jam.podR; c.strokeStyle = jam ? COL.red : COL.fg; c.fillStyle = c.strokeStyle;
      const r = clamp(2600 / Math.max(dist, 60), 9, 30) * s;
      c.beginPath(); c.arc(p.x, p.y, r, 0, TAU); c.stroke(); c.beginPath(); c.arc(p.x, p.y, 2 * s, 0, TAU); c.fill();
      c.beginPath(); c.moveTo(p.x - r - 8 * s, p.y); c.lineTo(p.x - r, p.y); c.moveTo(p.x + r, p.y); c.lineTo(p.x + r + 8 * s, p.y); c.moveTo(p.x, p.y + r); c.lineTo(p.x, p.y + r + 8 * s); c.stroke();
      if (!weapons.ccipValid) { c.font = FONT(10 * s, 700); c.textAlign = 'center'; c.fillText('NO IMPACT', p.x, p.y + r + 20 * s); }
    } else {
      // missile seeker circle at the boresight / gunner aim
      _v2.copy(heli.pos).addScaledVector(heli.gunner ? heli.aimDir : heli.fwd, 600); const q = { x: 0, y: 0 }; if (this.project(_v2, q)) { const r = (h / G.camera.fov) * 4.2; c.strokeStyle = COL.dim; c.setLineDash([6 * s, 6 * s]); c.beginPath(); c.arc(q.x, q.y, r, 0, TAU); c.stroke(); c.setLineDash([]); }
      const L_ = weapons.lock;
      if (L_.target) { const t = L_.target; if (this.project(_v2.set(t.x, t.y, t.z), q)) { const k = sat(L_.t / 2); const sz = lerp(46, 20, k) * s; const col = L_.locked ? COL.red : COL.amber; c.strokeStyle = col; c.fillStyle = col; c.lineWidth = 2.2 * s;
          c.save(); c.translate(q.x, q.y); if (!L_.locked) c.rotate(this.t * 2.5); for (let i = 0; i < 4; i++) { c.rotate(Math.PI / 2); c.beginPath(); c.moveTo(sz, sz * 0.45); c.lineTo(sz, sz); c.lineTo(sz * 0.45, sz); c.stroke(); } c.restore();
          c.font = FONT(11 * s, 700); c.textAlign = 'center'; c.fillText(L_.locked ? 'LOCKED — FIRE' : 'LOCKING ' + (2 - L_.t).toFixed(1), q.x, q.y + sz + 16 * s); c.font = FONT(10 * s); c.fillStyle = COL.dim; c.fillText(t.name.toUpperCase() + '  ' + Math.round(Math.hypot(t.x - heli.pos.x, t.z - heli.pos.z)) + ' M', q.x, q.y - sz - 12 * s); } }
    }
    if (sel !== 2) { c.font = MONO(10 * s); c.fillStyle = COL.dim; c.textAlign = 'left'; c.fillText(Math.round(dist) + ' M', p.x + 26 * s, p.y + 16 * s); }
    // objective marker in world
    if (mission.hasMarker) { const q = { x: 0, y: 0 }; const vis = this.project(mission.marker, q); if (vis && q.x > 20 && q.x < w - 20 && q.y > 20 && q.y < h - 20) { const pul = 0.6 + 0.4 * Math.sin(this.t * 5); c.strokeStyle = `rgba(255,176,46,${pul})`; c.lineWidth = 2 * s; const r = 9 * s; c.beginPath(); c.moveTo(q.x, q.y - r); c.lineTo(q.x + r, q.y); c.lineTo(q.x, q.y + r); c.lineTo(q.x - r, q.y); c.closePath(); c.stroke(); c.font = MONO(10 * s); c.fillStyle = COL.amber; c.textAlign = 'center'; c.fillText(Math.round(mission.marker.distanceTo(heli.pos)) + ' M', q.x, q.y - r - 9 * s); } }
  },

  // ---------- threat direction indicators ----------
  // a tapered arc on a ring round the reticle, a chevron pointing at the source, a labelled tag with range,
  // a progress sweep for timed threats, and a bracket on the source itself when it is on screen
  _threatArcs(c, s, w, h, dt) {
    const cx = w / 2, cy = h / 2; const R = 205 * s;
    const cam = G.camera; _v.set(0, 0, -1).applyQuaternion(cam.quaternion); const camYaw = Math.atan2(_v.x, -_v.z);
    const used = [];
    const mark = (wx, wy, wz, rgb, label, width, prog, urgent) => {
      const b = Math.atan2(wx - heli.pos.x, -(wz - heli.pos.z)) - camYaw; const a = b - Math.PI / 2;
      const dist = Math.hypot(wx - heli.pos.x, wz - heli.pos.z);
      const pulse = urgent ? 0.72 + 0.28 * Math.sin(this.t * 22) : 1; const col = al => `rgba(${rgb},${(al * pulse).toFixed(3)})`;
      c.lineCap = 'butt';
      // tapered band: wide faint → narrow bright
      c.strokeStyle = col(0.16); c.lineWidth = 9 * s; c.beginPath(); c.arc(cx, cy, R, a - width, a + width); c.stroke();
      c.strokeStyle = col(0.42); c.lineWidth = 4.5 * s; c.beginPath(); c.arc(cx, cy, R, a - width * 0.72, a + width * 0.72); c.stroke();
      c.strokeStyle = col(0.95); c.lineWidth = 2 * s; c.beginPath(); c.arc(cx, cy, R + 3.2 * s, a - width * 0.45, a + width * 0.45); c.stroke();
      // end ticks
      for (const e of [-1, 1]) { const t = a + e * width; c.strokeStyle = col(0.5); c.lineWidth = 1.5 * s; c.beginPath(); c.moveTo(cx + Math.cos(t) * (R - 6 * s), cy + Math.sin(t) * (R - 6 * s)); c.lineTo(cx + Math.cos(t) * (R + 6 * s), cy + Math.sin(t) * (R + 6 * s)); c.stroke(); }
      // progress sweep (aim time / time to impact)
      if (prog !== undefined) { c.strokeStyle = col(1); c.lineWidth = 3.2 * s; c.beginPath(); c.arc(cx, cy, R - 7 * s, a - width, a - width + 2 * width * sat(prog)); c.stroke(); }
      // chevron
      const ca = Math.cos(a), sa = Math.sin(a), px = -sa, py = ca; const r0 = R + 9 * s, r1 = R + 21 * s, hw = 8 * s;
      c.fillStyle = col(0.95); c.beginPath(); c.moveTo(cx + ca * r1, cy + sa * r1); c.lineTo(cx + ca * r0 + px * hw, cy + sa * r0 + py * hw); c.lineTo(cx + ca * (r0 + 4 * s), cy + sa * (r0 + 4 * s)); c.lineTo(cx + ca * r0 - px * hw, cy + sa * r0 - py * hw); c.closePath(); c.fill();
      // tag: label + range on a dark plate, kept upright, nudged apart if two share a bearing
      let tr = R + 44 * s; for (const u of used) if (Math.abs(wrapPi(u - a)) < 0.34) tr += 24 * s; used.push(a);
      const tx = cx + ca * tr, ty = cy + sa * tr; const txt = label, sub = dist >= 1000 ? (dist / 1000).toFixed(1) + ' KM' : Math.round(dist / 10) * 10 + ' M';
      c.font = FONT(11 * s, 800); const tw = c.measureText(txt).width; c.font = MONO(10 * s, 600); const sw = c.measureText(sub).width; const pw = tw + sw + 26 * s, ph = 19 * s;
      const sb = c.shadowBlur; c.shadowBlur = 0;
      c.fillStyle = 'rgba(8,11,9,0.72)'; c.fillRect(tx - pw / 2, ty - ph / 2, pw, ph); c.fillStyle = col(0.95); c.fillRect(tx - pw / 2, ty - ph / 2, 3 * s, ph);
      c.textBaseline = 'middle'; c.textAlign = 'left'; c.font = FONT(11 * s, 800); c.fillStyle = col(1); c.fillText(txt, tx - pw / 2 + 9 * s, ty + 0.5 * s);
      c.font = MONO(10 * s, 600); c.fillStyle = 'rgba(226,242,214,0.78)'; c.fillText(sub, tx - pw / 2 + 15 * s + tw, ty + 0.5 * s);
      c.shadowBlur = sb;
      // bracket on the source when it is in view
      if (wy !== null) { const q = _q2d; _v2.set(wx, wy, wz); if (this.project(_v2, q) && q.x > 20 && q.x < w - 20 && q.y > 20 && q.y < h - 20) {
        const r = (10 + 5 * (1 - sat(prog || 0))) * s; c.strokeStyle = col(0.95); c.lineWidth = 1.8 * s; c.beginPath();
        for (const [ex, ey] of [[-1, -1], [1, -1], [1, 1], [-1, 1]]) { c.moveTo(q.x + ex * r, q.y + ey * r * 0.45); c.lineTo(q.x + ex * r, q.y + ey * r); c.lineTo(q.x + ex * r * 0.45, q.y + ey * r); }
        c.stroke(); } }
    };
    for (const e of threats.engines) if (e.alive && e.kind === 'ballista' && e.state === 'aim') { const k = e.t / 1.5; mark(e.x, e.y, e.z, '255,74,54', 'BALLISTA', 0.2 - 0.09 * k, k, k > 0.6); }
    if (threats.volleyWarn > 0) mark(threats.lastVolleyPos.x, null, threats.lastVolleyPos.z, '255,176,46', 'VOLLEY', 0.3, 1 - threats.volleyWarn / 2.4, false);
    for (const b of threats.boulders) mark(b.x, b.y, b.z, '255,138,60', 'BOULDER', 0.09, b.eta ? b.t / b.eta : undefined, true);
    for (const sh of threats.shells) mark(sh.sx, sh.sy, sh.sz, '255,74,54', 'FLAK', 0.11, sh.tof ? sh.t / sh.tof : undefined, false);
  },

  // ---------- objective ----------
  _objective(c, s, w, h) {
    const x = 26 * s, y = 30 * s;
    c.textAlign = 'left'; c.font = FONT(11 * s, 700); c.fillStyle = COL.amber; c.fillText(mission.phase > 0 ? `PHASE ${mission.phase} / 3` : 'APPROACH', x, y);
    c.font = FONT(19 * s, 700); c.fillStyle = COL.fg; c.fillText(mission.objective.toUpperCase(), x, y + 22 * s);
    c.font = FONT(13 * s, 500); c.fillStyle = COL.dim; c.fillText(mission.progress, x, y + 44 * s);
    // army strength bar
    const bw = 190 * s; c.fillStyle = COL.faint; c.fillRect(x, y + 60 * s, bw, 3 * s); c.fillStyle = COL.fg; c.fillRect(x, y + 60 * s, bw * sat(crowd.strength || 0), 3 * s);
    c.font = FONT(10 * s); c.fillStyle = COL.dim; c.fillText(`ARMY ${Math.round((crowd.strength || 0) * 100)}%   ·   ${crowd.killed} KILLED`, x, y + 74 * s);
    if (mission.phase >= 1) { const L = mission.lightLeft == null ? 600 : mission.lightLeft; const low = L < 120; const mm = Math.floor(L / 60), ss = Math.floor(L % 60); c.font = MONO(15 * s, 700); c.fillStyle = low ? (L < 45 && (G.time * 3 % 1) < 0.5 ? COL.red : COL.amber) : COL.dim; c.fillText(`LIGHT  ${mm}:${ss < 10 ? '0' : ''}${ss}`, x, y + 96 * s); }
  },

  // ---------- weapons panel ----------
  _weapons(c, s, w, h) {
    const x = w - 26 * s, y = h - 34 * s; const a = weapons.ammo; c.textAlign = 'right';
    const rows = [['FLARES', a.flares, 6, weapons.flareCd > 0 ? `${weapons.flareCd.toFixed(0)}s` : keyLabel(settings.keys.flares), -1], ['MISSILES', a.missiles, 8, '3', 2], ['ROCKETS', a.rockets, 38, '2', 1], ['30MM', a.cannon, 600, '1', 0]];
    rows.forEach((r, i) => {
      const yy = y - i * 27 * s; const sel = r[4] === weapons.sel; const jam = (r[4] === 0 && weapons.jam.turret) || (r[4] === 1 && (weapons.jam.podL || weapons.jam.podR));
      const col = jam ? COL.red : r[1] === 0 ? COL.red : r[1] / r[2] < 0.2 ? COL.amber : COL.fg;
      if (sel) { c.fillStyle = 'rgba(226,242,214,0.14)'; c.fillRect(x - 236 * s, yy - 12 * s, 242 * s, 24 * s); c.fillStyle = COL.fg; c.fillRect(x + 6 * s, yy - 12 * s, 3 * s, 24 * s); }
      c.font = MONO(18 * s, 700); c.fillStyle = col; c.fillText(String(r[1]), x, yy);
      c.font = FONT(11 * s, 700); c.fillStyle = sel ? COL.fg : COL.dim; c.fillText(r[0] + (jam ? ' JAM' : ''), x - 58 * s, yy);
      c.font = MONO(10 * s); c.fillStyle = COL.faint; c.fillText('[' + r[3] + ']', x - 150 * s, yy);
      // pips
      const pw = 60 * s; c.fillStyle = COL.faint; c.fillRect(x - 236 * s, yy + 7 * s, pw, 2 * s); c.fillStyle = col; c.fillRect(x - 236 * s, yy + 7 * s, pw * r[1] / r[2], 2 * s);
    });
    // cannon heat
    const hy = y - 4 * 27 * s + 2 * s; c.font = FONT(10 * s, 700); c.fillStyle = weapons.overheated ? COL.red : COL.dim; c.fillText(weapons.overheated ? 'OVERHEAT' : 'HEAT', x - 170 * s, hy);
    c.fillStyle = COL.faint; c.fillRect(x - 160 * s, hy - 3 * s, 160 * s, 6 * s); c.fillStyle = weapons.overheated ? COL.red : weapons.heat > 0.7 ? COL.amber : COL.fg; c.fillRect(x - 160 * s, hy - 3 * s, 160 * s * weapons.heat, 6 * s);
  },

  // ---------- damage panel ----------
  _damage(c, s, w, h) {
    const x = w - 26 * s, y = h - 34 * s - 5 * 27 * s - 14 * s; c.textAlign = 'right';
    const order = ['tail', 'engine', 'hyd', 'rotor', 'canopy', 'weapons'];
    order.forEach((k, i) => { const v = heli.sub[k]; const yy = y - i * 15 * s; const col = v <= 0 ? COL.red : v < 50 ? COL.amber : v < 100 ? COL.fg : COL.faint;
      if (v < 50 && (this.t * 2 % 1) < 0.5) c.globalAlpha = 0.55; c.font = FONT(10 * s, 700); c.fillStyle = col; c.fillText(SUB_NAMES[k], x - 50 * s, yy); c.globalAlpha = 1;
      c.fillStyle = COL.faint; c.fillRect(x - 42 * s, yy - 2.5 * s, 42 * s, 5 * s); c.fillStyle = col === COL.faint ? COL.dim : col; c.fillRect(x - 42 * s, yy - 2.5 * s, 42 * s * v / 100, 5 * s); });
    const yy = y - 6 * 15 * s - 6 * s; const hv = Math.max(0, heli.hull); const col = hv < 30 ? COL.red : hv < 60 ? COL.amber : COL.fg;
    c.font = FONT(11 * s, 700); c.fillStyle = col; c.fillText('HULL ' + Math.round(hv) + '%', x - 126 * s, yy); c.fillStyle = COL.faint; c.fillRect(x - 118 * s, yy - 4 * s, 118 * s, 8 * s); c.fillStyle = col; c.fillRect(x - 118 * s, yy - 4 * s, 118 * s * hv / 100, 8 * s);
  },

  // ---------- minimap ----------
  _mapDraw(c, cx, cy, R, range, rot, full) {
    const hp = heli.pos; const sc = R / range;
    c.save(); c.beginPath(); c.arc(cx, cy, R, 0, TAU); c.clip();
    c.fillStyle = 'rgba(14,20,16,0.82)'; c.fillRect(cx - R, cy - R, R * 2, R * 2);
    c.translate(cx, cy); c.rotate(rot); c.scale(sc, sc); c.translate(-hp.x, -hp.z);
    c.globalAlpha = 0.8; c.drawImage(this.map, -this.mapR, -this.mapR, this.mapR * 2, this.mapR * 2); c.globalAlpha = 1;
    const lw = 1 / sc;
    // play-area ring
    c.lineWidth = 2.5 * lw; c.strokeStyle = mission.outside ? COL.red : mission.warnBand ? COL.amber : 'rgba(226,242,214,0.5)'; c.beginPath(); c.arc(0, 0, L.PLAY_R, 0, TAU); c.stroke();
    // castle structures
    c.fillStyle = 'rgba(205,198,180,0.95)'; c.strokeStyle = 'rgba(205,198,180,0.95)';
    for (const st of castle.structs) { if (st.type === 'tower') { c.globalAlpha = st.alive ? 1 : 0.3; c.beginPath(); c.arc(st.x, st.z, st.r + 1, 0, TAU); c.fill(); } else { c.globalAlpha = st.alive ? 1 : 0.25; c.save(); c.translate(st.x, st.z); c.rotate(-st.ry); c.fillRect(-st.len / 2, -2.5, st.len, 5); c.restore(); } }
    c.globalAlpha = 1; if (castle.keep) c.fillRect(castle.keep.x - 12, castle.keep.z - 12, 24, 24);
    // formations: blocks that shrink with losses, fade when routed
    for (const f of crowd.forms) { if (f.kind === 'crew' || f.kind === 'camp' || f.onWalls || !f.spotted) continue; const k = sat(f.alive / Math.max(1, f.initial)); if (k <= 0.02) continue; c.globalAlpha = f.routed ? 0.25 : 0.95;
      const col = '#' + f.herald[0].toString(16).padStart(6, '0'); c.fillStyle = col; const sz = (f.kind === 'infantry' ? 30 : f.kind === 'guard' ? 16 : 20) * (0.35 + 0.65 * Math.sqrt(k));
      c.fillRect(f.cx - sz / 2, f.cz - sz * 0.8, sz, sz * 1.6); c.strokeStyle = 'rgba(0,0,0,0.6)'; c.lineWidth = lw; c.strokeRect(f.cx - sz / 2, f.cz - sz * 0.8, sz, sz * 1.6);
      if (f.kind === 'archers' && !f.routed) { c.strokeStyle = f.volleying ? COL.amber : 'rgba(255,176,46,0.25)'; c.lineWidth = 1.2 * lw; c.beginPath(); c.arc(f.cx, f.cz, 270, 0, TAU); c.stroke(); } }
    c.globalAlpha = 1;
    // engines (once spotted)
    for (const e of threats.engines) { if (!e.alive || !e.spotted) continue; const col = e.kind === 'ballista' ? (e.state === 'aim' ? COL.red : '#ff9a7a') : e.kind === 'bombard' ? '#ffc04a' : '#ff7a3a'; c.fillStyle = col; c.strokeStyle = 'rgba(0,0,0,0.7)'; c.lineWidth = lw; const r = 5.5 * lw;
      c.beginPath(); if (e.kind === 'ballista') { c.moveTo(e.x, e.z - r); c.lineTo(e.x + r, e.z + r); c.lineTo(e.x - r, e.z + r); c.closePath(); } else if (e.kind === 'bombard') c.rect(e.x - r * 0.8, e.z - r * 0.8, r * 1.6, r * 1.6); else { c.moveTo(e.x, e.z - r * 1.2); c.lineTo(e.x + r * 1.2, e.z); c.lineTo(e.x, e.z + r * 1.2); c.lineTo(e.x - r * 1.2, e.z); c.closePath(); } c.fill(); c.stroke(); }
    // incoming boulders: predicted impact
    for (const b of this.boulders) { const k = sat(b.t / b.eta); c.strokeStyle = COL.red; c.lineWidth = 2 * lw; c.beginPath(); c.arc(b.x, b.z, (26 - 16 * k) * lw * 0.9 + 6, 0, TAU); c.stroke(); c.beginPath(); c.moveTo(b.x - 8 * lw, b.z); c.lineTo(b.x + 8 * lw, b.z); c.moveTo(b.x, b.z - 8 * lw); c.lineTo(b.x, b.z + 8 * lw); c.stroke(); }
    // rearm pad
    c.fillStyle = '#7fd7ff'; c.strokeStyle = '#7fd7ff'; c.lineWidth = 2 * lw; c.beginPath(); c.arc(L.PAD.x, L.PAD.z, 9 * lw, 0, TAU); c.stroke(); c.save(); c.translate(L.PAD.x, L.PAD.z); c.rotate(-rot); c.font = FONT(11 * lw, 700); c.textAlign = 'center'; c.textBaseline = 'middle'; c.fillText('H', 0, 0.5 * lw); c.restore();
    // objective
    if (mission.hasMarker) { const m = mission.marker; const pul = 0.5 + 0.5 * Math.sin(this.t * 5); c.strokeStyle = `rgba(255,176,46,${0.5 + 0.5 * pul})`; c.lineWidth = 2.2 * lw; c.beginPath(); c.arc(m.x, m.z, (9 + 7 * pul) * lw, 0, TAU); c.stroke(); }
    c.restore();
    // edge pointers for pad / objective when off the map
    const edge = (wx, wz, col, label) => { const dx = wx - hp.x, dz = wz - hp.z; const d = Math.hypot(dx, dz); if (d < range * 0.96) return; const a = Math.atan2(dz, dx) + rot; const ex = cx + Math.cos(a) * (R - 7), ey = cy + Math.sin(a) * (R - 7); c.fillStyle = col; c.beginPath(); c.arc(ex, ey, 4.5, 0, TAU); c.fill(); if (label) { c.font = FONT(9, 700); c.textAlign = 'center'; c.fillText(label, cx + Math.cos(a) * (R - 20), cy + Math.sin(a) * (R - 20)); } };
    edge(L.PAD.x, L.PAD.z, '#7fd7ff', 'H'); if (mission.hasMarker) edge(mission.marker.x, mission.marker.z, COL.amber, '');
    // own ship + view cone
    c.save(); c.translate(cx, cy); const camFov = G.camera.fov * DEG * G.camera.aspect * 0.5;
    c.fillStyle = 'rgba(226,242,214,0.10)'; c.beginPath(); c.moveTo(0, 0); c.arc(0, 0, R * 0.9, -Math.PI / 2 - camFov * 0.6, -Math.PI / 2 + camFov * 0.6); c.closePath(); c.fill();
    c.fillStyle = COL.fg; c.strokeStyle = 'rgba(0,0,0,0.8)'; c.lineWidth = 1; c.beginPath(); c.moveTo(0, -8); c.lineTo(5.5, 6); c.lineTo(0, 3); c.lineTo(-5.5, 6); c.closePath(); c.fill(); c.stroke(); c.restore();
  },
  _minimap(c, s, w, h, dt) {
    const R = 110 * s; const cx = 26 * s + R, cy = h - 30 * s - R;
    for (let i = this.boulders.length - 1; i >= 0; i--) { const b = this.boulders[i]; b.t += dt; if (b.t > b.eta + 0.3) this.boulders.splice(i, 1); }
    c.shadowBlur = 0;
    // heading-up: rotate so the nose points up. world→map: x right, z down; heading yaw: fwd = (-sin, -cos)
    const rot = heli.yaw; // rotating the map by +yaw brings fwd to "up"
    this._mapDraw(c, cx, cy, R, 620, rot, false);
    c.strokeStyle = mission.outside ? COL.red : mission.warnBand ? COL.amber : 'rgba(226,242,214,0.6)'; c.lineWidth = 2 * s; c.beginPath(); c.arc(cx, cy, R, 0, TAU); c.stroke();
    // north tick
    const na = -Math.PI / 2 + rot; c.fillStyle = COL.fg; c.font = FONT(10 * s, 700); c.textAlign = 'center'; c.fillText('N', cx + Math.cos(na) * (R + 9 * s), cy + Math.sin(na) * (R + 9 * s));
    // pad distance
    const pd = Math.hypot(L.PAD.x - heli.pos.x, L.PAD.z - heli.pos.z); c.textAlign = 'left'; c.font = MONO(10 * s); c.fillStyle = '#7fd7ff'; c.fillText('PAD ' + Math.round(pd) + ' M', cx + R + 10 * s, cy + R - 8 * s);
    c.shadowBlur = 3 * s;
  },

  // ---------- warnings ----------
  _warnings(c, s, w, h, dt) {
    const cx = w / 2; let y = h * 0.27; const blink = (this.t * 4 % 1) < 0.6;
    const warn = (text, col, big) => { c.font = FONT((big ? 20 : 14) * s, 800); c.textAlign = 'center'; const tw = c.measureText(text).width + 22 * s; c.fillStyle = 'rgba(0,0,0,0.35)'; c.fillRect(cx - tw / 2, y - (big ? 15 : 11) * s, tw, (big ? 30 : 22) * s); c.fillStyle = col; c.fillText(text, cx, y + 1); y += (big ? 36 : 27) * s; };
    const fly = heli.state === 'fly';
    if (mission.outside) {
      warn('RETURN TO COMBAT AREA', COL.red, true); c.font = MONO(54 * s, 800); c.fillStyle = COL.red; c.textAlign = 'center'; c.fillText(Math.max(0, mission.outT).toFixed(1), cx, y + 24 * s); y += 64 * s;
      // arrow to the nearest point of the circle (toward origin)
      const cam = G.camera; _v.set(0, 0, -1).applyQuaternion(cam.quaternion); const camYaw = Math.atan2(_v.x, -_v.z); const b = Math.atan2(-heli.pos.x, heli.pos.z) - camYaw; const a = b - Math.PI / 2;
      c.save(); c.translate(cx + Math.cos(a) * 120 * s, h / 2 + Math.sin(a) * 120 * s); c.rotate(a); c.fillStyle = COL.red; c.beginPath(); c.moveTo(22 * s, 0); c.lineTo(-10 * s, -13 * s); c.lineTo(-3 * s, 0); c.lineTo(-10 * s, 13 * s); c.closePath(); c.fill(); c.restore();
    } else if (mission.warnBand && blink) warn('COMBAT AREA EDGE  ' + Math.round(mission.edgeDist) + ' M', COL.amber);
    if (!fly) return;
    if (threats.aimWarn > 0 && blink) warn('BALLISTA AIMING — JINK', COL.red);
    if (heli.vrs > 0.25) warn('SETTLING WITH POWER — FLY FORWARD', COL.red);
    else if (heli.agl < 25 && heli.vs < -6 && blink) warn('SINK RATE', COL.amber);
    if (heli.tumble) warn('ATTITUDE — RECOVER', COL.red);
    if (heli.sub.tail <= 0) warn('TAIL ROTOR OUT — KEEP SPEED ABOVE 40 KM/H', COL.red);
    if (heli.pos.y - 24 > 400 && blink) warn('SERVICE CEILING', COL.amber);
    if (heli.hull < 30 && blink) warn('HULL CRITICAL', COL.red);
    if (heli.onPad) {
      const txt = weapons.fullyArmed ? 'REARM COMPLETE — LIFT OFF' : weapons.repairing ? `REARMING · REPAIRING ${SUB_NAMES[weapons.repairing]} ${Math.ceil(5 - weapons.repairT)}s` : 'REARMING';
      warn(txt, weapons.fullyArmed ? COL.good : COL.fg);
    } else if (heli.onGround === false && Math.hypot(heli.pos.x - L.PAD.x, heli.pos.z - L.PAD.z) < 70 && heli.agl < 40) {
      const okV = Math.abs(heli.vs) < 2, okH = heli.hspeed < 3; warn(`PAD: TOUCH DOWN UNDER 2 M/S VERT ${okV ? '✓' : '✗'}  3 M/S HORIZ ${okH ? '✓' : '✗'}`, okV && okH ? COL.good : COL.amber);
    }
  },

  // ---------- messages ----------
  _messages(c, s, w, h, dt) {
    let y = h * 0.74; const cx = w / 2;
    for (let i = this.msgs.length - 1; i >= 0; i--) { const m = this.msgs[i]; m.t += dt; if (m.t > m.dur) { this.msgs.splice(i, 1); continue; } }
    for (let i = this.msgs.length - 1; i >= 0; i--) {
      const m = this.msgs[i]; const a = sat(m.t / 0.25) * sat((m.dur - m.t) / 0.6);
      const tut = m.kind === 'tut'; c.font = FONT((tut ? 16 : 13) * s, tut ? 700 : 700); c.textAlign = 'center';
      const col = m.kind === 'warn' ? COL.amber : m.kind === 'good' ? COL.good : COL.fg; const tw = c.measureText(m.text).width + 28 * s; const bh = (tut ? 30 : 22) * s;
      c.globalAlpha = a * (tut ? 0.6 : 0.4); c.fillStyle = '#000'; c.fillRect(cx - tw / 2, y - bh / 2, tw, bh); c.globalAlpha = a; c.fillStyle = col; c.fillText(m.text, cx, y + 1); c.globalAlpha = 1; y -= bh + 5 * s;
    }
  },
  _banner(c, dt) {
    const b = this.banner; if (!b) return; b.t += dt; const D = 6; if (b.t > D) { this.banner = null; return; }
    const s = this.s, w = this.w, h = this.h; const a = sat(b.t / 0.5) * sat((D - b.t) / 1.0); const y = h * 0.2;
    c.save(); c.globalAlpha = a; c.shadowColor = 'rgba(0,0,0,0.8)'; c.shadowBlur = 10 * s; c.textAlign = 'center'; c.textBaseline = 'middle';
    const lw = lerp(60, 330, sat(b.t / 0.8)) * s; c.strokeStyle = COL.amber; c.lineWidth = 2 * s; c.beginPath(); c.moveTo(w / 2 - lw, y - 27 * s); c.lineTo(w / 2 + lw, y - 27 * s); c.moveTo(w / 2 - lw, y + 26 * s); c.lineTo(w / 2 + lw, y + 26 * s); c.stroke();
    c.font = FONT(30 * s, 800); c.fillStyle = '#fff5e0'; c.fillText(b.title, w / 2, y); c.font = FONT(14 * s, 500); c.fillStyle = COL.fg; c.fillText(b.sub || '', w / 2, y + 46 * s); c.restore();
  },

  // ---------- cockpit MFD pages ----------
  _mfd() {
    // left: tactical map, north-up
    { const m = this.mfd[0], c = m.x; c.setTransform(1, 0, 0, 1, 0, 0); c.fillStyle = '#04140a'; c.fillRect(0, 0, 256, 256); c.shadowBlur = 0; this._mapDraw(c, 128, 128, 124, 900, heli.yaw, true);
      c.fillStyle = '#7dff9a'; c.font = MONO(13, 700); c.textAlign = 'left'; c.textBaseline = 'top'; c.fillText('TAC', 8, 6); c.textAlign = 'right'; c.fillText('900M', 248, 6); this._mfdFx(m, 0); m.t.needsUpdate = true; }
    { const m = this.mfd[1], c = m.x; c.setTransform(1, 0, 0, 1, 0, 0); c.fillStyle = '#04140a'; c.fillRect(0, 0, 256, 256); c.textBaseline = 'middle'; c.shadowBlur = 0;
      c.fillStyle = '#7dff9a'; c.font = MONO(14, 700); c.textAlign = 'left'; c.fillText('STORES', 10, 16);
      const a = weapons.ammo; [['30MM', a.cannon, 600], ['RKT', a.rockets, 38], ['MSL', a.missiles, 8], ['FLR', a.flares, 6]].forEach((r, i) => { const y = 42 + i * 24; const sel = i === weapons.sel; c.fillStyle = sel ? '#e8ffe0' : '#7dff9a'; c.font = MONO(15, 700); c.textAlign = 'left'; c.fillText((sel ? '>' : ' ') + r[0], 8, y); c.textAlign = 'right'; c.fillText(String(r[1]), 126, y); c.fillStyle = '#1d5a30'; c.fillRect(136, y - 6, 110, 12); c.fillStyle = r[1] / r[2] < 0.2 ? '#ffb02e' : '#7dff9a'; c.fillRect(136, y - 6, 110 * r[1] / r[2], 12); });
      c.fillStyle = '#7dff9a'; c.font = MONO(14, 700); c.textAlign = 'left'; c.fillText('SYSTEMS', 10, 146);
      if (heli.sub.weapons <= 0 && (this.t * 2 % 1) < 0.6) { c.fillStyle = '#ff4a36'; c.fillRect(134, 8, 114, 17); c.fillStyle = '#04140a'; c.font = MONO(12, 700); c.textAlign = 'center'; c.fillText('WEAPONS FAIL', 191, 17); }
      SUBS.forEach((k, i) => { const v = heli.sub[k]; const y = 168 + i * 14; c.fillStyle = v <= 0 ? '#ff4a36' : v < 50 ? '#ffb02e' : '#7dff9a'; c.font = MONO(12, 700); c.textAlign = 'left'; c.fillText(SUB_NAMES[k], 10, y); c.fillRect(136, y - 4, 110 * v / 100, 8); });
      this._mfdFx(m, 1); m.t.needsUpdate = true; }
    // centre: sight page — attitude, where the gun is looking, range, lock
    { const m = this.mfd[2], c = m.x; c.setTransform(1, 0, 0, 1, 0, 0); c.fillStyle = '#04140a'; c.fillRect(0, 0, 256, 256); c.shadowBlur = 0; c.textBaseline = 'middle';
      const G1 = '#7dff9a', G2 = '#2c7a45', K = 2.6;   // px per degree
      const bank = Math.asin(clamp(heli.right.y, -1, 1)), pit = Math.asin(clamp(heli.fwd.y, -1, 1)) / DEG;
      c.save(); c.beginPath(); c.rect(6, 26, 244, 196); c.clip(); c.translate(128, 124); c.rotate(bank); c.translate(0, pit * K);
      c.fillStyle = 'rgba(40,110,60,0.16)'; c.fillRect(-300, 0, 600, 400);
      c.strokeStyle = G1; c.lineWidth = 1.5; c.beginPath(); c.moveTo(-300, 0); c.lineTo(-22, 0); c.moveTo(22, 0); c.lineTo(300, 0); c.stroke();
      c.strokeStyle = G2; c.fillStyle = G2; c.font = MONO(10, 700); c.lineWidth = 1;
      for (let d = -60; d <= 60; d += 10) { if (!d) continue; const y = -d * K, w2 = 26; c.beginPath(); if (d < 0) c.setLineDash([4, 4]); c.moveTo(-w2, y); c.lineTo(-10, y); c.moveTo(10, y); c.lineTo(w2, y); c.stroke(); c.setLineDash([]); c.textAlign = 'right'; c.fillText(String(Math.abs(d)), -w2 - 4, y); }
      c.restore();
      // boresight + gun line of sight in the airframe's frame
      c.strokeStyle = G1; c.lineWidth = 1.5; c.beginPath(); c.moveTo(108, 124); c.lineTo(120, 124); c.lineTo(128, 132); c.lineTo(136, 124); c.lineTo(148, 124); c.stroke();
      _mq.copy(heli.q).invert(); _mv.copy(heli.aimDir).applyQuaternion(_mq);
      const ax = clamp(128 + Math.atan2(_mv.x, -_mv.z) / DEG * K, 20, 236), ay = clamp(124 - Math.asin(clamp(_mv.y, -1, 1)) / DEG * K, 38, 210);
      const lk = weapons.lock, locked = lk.locked, col = locked ? '#e8ffe0' : weapons.sel === 2 && lk.target ? '#ffb02e' : G1;
      c.strokeStyle = col; c.lineWidth = 2; const b = 13; for (const [sx, sy] of [[-1, -1], [1, -1], [1, 1], [-1, 1]]) { c.beginPath(); c.moveTo(ax + sx * b, ay + sy * (b - 6)); c.lineTo(ax + sx * b, ay + sy * b); c.lineTo(ax + sx * (b - 6), ay + sy * b); c.stroke(); }
      c.fillStyle = col; c.fillRect(ax - 1, ay - 1, 3, 3);
      // header / footer
      c.fillStyle = G1; c.font = MONO(13, 700); c.textAlign = 'left'; c.fillText('SIGHT', 8, 13); c.textAlign = 'right'; c.fillText(['30MM', 'RKT', 'MSL'][weapons.sel] || '', 248, 13);
      const hdg = ((-heli.yaw / DEG) % 360 + 360) % 360; c.textAlign = 'center'; c.fillText(String(Math.round(hdg)).padStart(3, '0') + '°', 128, 13);
      c.font = MONO(12, 700); c.textAlign = 'left'; c.fillText('RNG ' + (weapons.ccipValid ? Math.round(weapons.ccipDist) + 'M' : '----'), 8, 240);
      c.textAlign = 'right'; if (weapons.sel === 2 && lk.target) { c.fillStyle = col; c.fillText(locked ? 'LOCKED' : 'LOCKING', 248, 240); c.fillRect(172, 226, 76 * sat(lk.t / 2), 3); } else c.fillText('AGL ' + Math.round(heli.agl), 248, 240);
      if (threats.aimWarn > 0 && (this.t * 4 % 1) < 0.6) { c.fillStyle = '#ff4a36'; c.fillRect(78, 196, 100, 18); c.fillStyle = '#04140a'; c.textAlign = 'center'; c.fillText('BALLISTA', 128, 206); }
      this._mfdFx(m, 2); m.t.needsUpdate = true; }
  },
  // battle damage on the displays: tearing and dropouts as the hull goes, cracked glass and dead zones when it is nearly gone
  _mfdFx(m, i) {
    const c = m.x, cv = m.c; const hurt = heli.state === 'crashing' ? 1 : sat((60 - heli.hull) / 45); if (hurt <= 0) return;
    const R = (a, b2) => a + Math.random() * (b2 - a);
    const tears = Math.floor(hurt * 5 * Math.random() + hurt * 1.5); for (let k = 0; k < tears; k++) { const y = R(0, 240) | 0, h2 = R(3, 22) | 0, dx = R(-34, 34) * hurt | 0; c.drawImage(cv, 0, y, 256, h2, dx, y, 256, h2); if (Math.random() < 0.4) { c.fillStyle = `rgba(125,255,154,${R(0.08, 0.3)})`; c.fillRect(0, y, 256, 1); } }
    const blocks = Math.floor(hurt * 7 * Math.random()); for (let k = 0; k < blocks; k++) { c.fillStyle = Math.random() < 0.5 ? '#04140a' : `rgba(125,255,154,${R(0.2, 0.7)})`; c.fillRect(R(0, 240) | 0, R(0, 240) | 0, R(6, 50) | 0, R(2, 9) | 0); }
    if (hurt > 0.45 && Math.random() < 0.12 * hurt) { c.fillStyle = 'rgba(2,8,4,0.86)'; c.fillRect(0, 0, 256, 256); }
    if (heli.hull < 28 || heli.state === 'crashing') {   // the same fracture every refresh: seeded per screen
      let sd = 77 + i * 131; const rs = () => (sd = (sd * 16807) % 2147483647) / 2147483647; const x0 = 40 + rs() * 176, y0 = 40 + rs() * 176;
      c.fillStyle = 'rgba(2,6,3,0.92)'; c.beginPath(); c.moveTo(x0, y0); const a0 = rs() * TAU; for (let k = 0; k <= 5; k++) { const a = a0 + k / 5 * 1.3, r = 150 + rs() * 120; c.lineTo(x0 + Math.cos(a) * r, y0 + Math.sin(a) * r); } c.closePath(); c.fill();
      c.strokeStyle = 'rgba(210,235,225,0.75)'; c.lineWidth = 1; for (let k = 0; k < 9; k++) { let a = rs() * TAU, x = x0, y = y0; c.beginPath(); c.moveTo(x, y); for (let j = 0; j < 6; j++) { a += (rs() - 0.5) * 0.7; const l = 12 + rs() * 34; x += Math.cos(a) * l; y += Math.sin(a) * l; c.lineTo(x, y); } c.stroke(); }
      c.fillStyle = 'rgba(225,240,232,0.8)'; c.beginPath(); c.arc(x0, y0, 3.5, 0, TAU); c.fill();
    }
  },
};
