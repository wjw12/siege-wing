// Siege Wing — visible damage on the helicopter: canopy glass (cracks, oil), arrows stuck in the airframe, cockpit emergency light
import * as THREE from 'three';
import { G, V3, rnd, rndS, sat, clamp, lerp, damp, TAU, DEG } from './core.js';
import { assets } from './assets.js';
import { fx } from './fx.js';

const S = 2048;                     // canopy damage texture size
const MAXARROWS = 56, NSAMPLES = 420;
const GLASS_BASE = 'rgba(24,38,38,0.36)';
const _v = new V3(), _v2 = new V3(), _v3 = new V3(), _n = new V3(), _q = new THREE.Quaternion(), _m = new THREE.Matrix4(), _s = new V3(0.6, 0.6, 0.6), _z = new V3(0, 0, 1);
const _ray = new THREE.Raycaster();

export const damage = {
  heli: null, glass: null, ctx: null, tex: null, mat: null, impacts: 0, oiled: false,
  arrows: null, arrowN: 0, samples: null, queue: 0, light: null, sparkT: 0, lightK: 0,

  init(heli) {
    this.heli = heli; const root = heli.model;
    // ---- canopy: one texture carries the tint, the wear and every crack; it is both the colour/alpha map and the glint (emissive) map
    const cv = document.createElement('canvas'); cv.width = cv.height = S; this.ctx = cv.getContext('2d');
    const t = this.tex = new THREE.CanvasTexture(cv); t.colorSpace = THREE.SRGBColorSpace; t.flipY = false; t.anisotropy = 8; t.wrapS = t.wrapT = THREE.RepeatWrapping;
    const cn = root.getObjectByName('Canopy'); const meshes = []; if (cn) cn.traverse(o => { if (o.isMesh && o.material && /glass/i.test(o.material.name)) meshes.push(o); });
    this.glassMeshes = meshes; this.glass = meshes[0] || null;
    const m = this.mat = new THREE.MeshPhysicalMaterial({ color: 0xffffff, map: t, emissive: 0xffffff, emissiveMap: t, emissiveIntensity: 0, roughness: 0.05, metalness: 0, transparent: true, opacity: 1, envMapIntensity: 1.7, side: THREE.DoubleSide, depthWrite: false });
    m.name = 'Glass';
    for (const o of meshes) { o.material = m; o.renderOrder = 5; o.castShadow = false; }
    this._base();
    // ---- arrows that stay in the airframe
    const ag = assets.props && assets.props.scene.getObjectByName('Arrow'); let geo = null; if (ag) ag.traverse(o => { if (o.isMesh && !geo) geo = o.geometry.clone(); });
    if (geo) {
      geo.scale(1.25, 1.25, 1.25);
      const im = this.arrows = new THREE.InstancedMesh(geo, new THREE.MeshStandardMaterial({ color: 0x8a6a45, roughness: 0.8 }), MAXARROWS);
      im.count = 0; im.frustumCulled = false; im.castShadow = true; im.name = 'StuckArrows'; root.add(im);
      this._sampleHull(root);
    }
    // ---- emergency light in the cockpit (created once so no shader recompiles later)
    const fl = this.fill = new THREE.PointLight(0xdfe8ff, 0, 2.2, 1.2); fl.position.copy(heli.eye).add(_v.set(0, 0.22, -0.2)); root.add(fl);   // soft dome light so the consoles read in shade
    const l = this.light = new THREE.PointLight(0xff2a14, 0, 2.6, 1.4); l.position.copy(heli.eye).add(_v.set(0, -0.25, -0.55)); root.add(l);
  },

  // points on the outer skin where an arrow can lodge (model space), taken once
  _sampleHull(root) {
    const skip = /Rotor|Cockpit|Canopy|Pilot|Gunner|MFD|Needle|Warn|Horizon|Cyclic|Collective|HUDGlass|Missile|Pod|Gun|Turret|Gear|StuckArrows|Glass/;
    const list = []; root.updateWorldMatrix(true, true); const inv = new THREE.Matrix4().copy(root.matrixWorld).invert();
    root.traverse(o => { if (!o.isMesh || o.isInstancedMesh) return; for (let p = o; p && p !== root; p = p.parent) if (skip.test(p.name)) return; list.push(o); });
    const tris = []; let total = 0; const a = new V3(), b = new V3(), c = new V3();
    for (const o of list) {
      const g = o.geometry, pos = g.attributes.position, idx = g.index; if (!pos) continue; const M = new THREE.Matrix4().multiplyMatrices(inv, o.matrixWorld);
      const n = idx ? idx.count / 3 : pos.count / 3; const step = Math.max(1, Math.floor(n / 4000));
      for (let i = 0; i < n; i += step) {
        const i0 = idx ? idx.getX(i * 3) : i * 3, i1 = idx ? idx.getX(i * 3 + 1) : i * 3 + 1, i2 = idx ? idx.getX(i * 3 + 2) : i * 3 + 2;
        a.fromBufferAttribute(pos, i0).applyMatrix4(M); b.fromBufferAttribute(pos, i1).applyMatrix4(M); c.fromBufferAttribute(pos, i2).applyMatrix4(M);
        _v.subVectors(b, a); _v2.subVectors(c, a); _n.crossVectors(_v, _v2); const area = _n.length() * 0.5; if (area < 0.004) continue;
        _n.normalize(); _v3.copy(a).add(b).add(c).multiplyScalar(1 / 3);
        if (_n.x * _v3.x + _n.y * (_v3.y - 0.1) < 0.02) continue;           // must face away from the centreline: outer skin only
        total += area * step; tris.push({ p: _v3.clone(), n: _n.clone(), w: total });
      }
    }
    this.samples = []; if (!tris.length) return;
    for (let k = 0; k < NSAMPLES; k++) { const r = Math.random() * total; let lo = 0, hi = tris.length - 1; while (lo < hi) { const mid = (lo + hi) >> 1; if (tris[mid].w < r) lo = mid + 1; else hi = mid; } this.samples.push(tris[lo]); }
  },

  // ---------- canopy texture ----------
  _base() {
    const c = this.ctx; c.setTransform(1, 0, 0, 1, 0, 0); c.globalCompositeOperation = 'source-over'; c.clearRect(0, 0, S, S); c.fillStyle = GLASS_BASE; c.fillRect(0, 0, S, S);
    // service wear: wiper arcs, fine scratches and dust that only show when the sun is in the glass
    c.lineCap = 'round';
    for (let i = 0; i < 520; i++) { const x = rnd(S), y = rnd(S), a = rnd(TAU), l = rnd(8, 70); c.strokeStyle = `rgba(205,222,228,${rnd(0.035, 0.09)})`; c.lineWidth = rnd(0.5, 1.1); c.beginPath(); c.moveTo(x, y); c.quadraticCurveTo(x + Math.cos(a) * l * 0.5 + rndS(6), y + Math.sin(a) * l * 0.5 + rndS(6), x + Math.cos(a) * l, y + Math.sin(a) * l); c.stroke(); }
    for (let i = 0; i < 60; i++) { const x = rnd(S), y = rnd(S), r = rnd(40, 170); const g = c.createRadialGradient(x, y, 0, x, y, r); g.addColorStop(0, `rgba(150,160,150,${rnd(0.02, 0.05)})`); g.addColorStop(1, 'rgba(150,160,150,0)'); c.fillStyle = g; c.fillRect(x - r, y - r, r * 2, r * 2); }
    this.impacts = 0; this.oiled = false; this.tex.needsUpdate = true;
  },
  // ray from the pilot's seat out through the glass -> where it lands in the texture and how big a metre is there
  _probe(yaw, pitch, fromGunner) {
    const h = this.heli; if (!this.glassMeshes.length) return null;
    h.model.position.copy(h.pos); h.model.quaternion.copy(h.q); h.model.updateWorldMatrix(true, true);
    const eye = fromGunner && h.nodes.GunnerEye ? h.nodes.GunnerEye.getWorldPosition(_v) : _v.copy(h.eye).applyQuaternion(h.q).add(h.pos);
    _v2.set(-Math.sin(yaw) * Math.cos(pitch), Math.sin(pitch), -Math.cos(yaw) * Math.cos(pitch)).applyQuaternion(h.q);
    _ray.set(eye, _v2); _ray.near = 0.03; _ray.far = 5;
    const hit = _ray.intersectObjects(this.glassMeshes, false)[0]; if (!hit || !hit.uv || !hit.face) return null;
    const g = hit.object.geometry, P = g.attributes.position, U = g.attributes.uv, f = hit.face;
    const p0 = new V3().fromBufferAttribute(P, f.a), e1 = new V3().fromBufferAttribute(P, f.b).sub(p0), e2 = new V3().fromBufferAttribute(P, f.c).sub(p0);
    const u0 = U.getX(f.a), v0 = U.getY(f.a), du1 = U.getX(f.b) - u0, dv1 = U.getY(f.b) - v0, du2 = U.getX(f.c) - u0, dv2 = U.getY(f.c) - v0;
    const det = du1 * dv2 - du2 * dv1; let sx = 620, sy = 620; const dPdu = new V3(1, 0, 0), dPdv = new V3(0, 1, 0);
    if (Math.abs(det) > 1e-9) { dPdu.copy(e1).multiplyScalar(dv2).addScaledVector(e2, -dv1).multiplyScalar(1 / det); dPdv.copy(e2).multiplyScalar(du1).addScaledVector(e1, -du2).multiplyScalar(1 / det); sx = clamp(S / Math.max(1e-4, dPdu.length()), 150, 2600); sy = clamp(S / Math.max(1e-4, dPdv.length()), 150, 2600); }
    const u = hit.uv.x - Math.floor(hit.uv.x), v = hit.uv.y - Math.floor(hit.uv.y);
    return { x: u * S, y: v * S, sx, sy, dPdu, dPdv, obj: hit.object, point: hit.point.clone() };
  },
  // model-space direction -> direction in texture pixels at a probe
  _texDir(pr, dirModel) {
    const lu = pr.dPdu.lengthSq(), lv = pr.dPdv.lengthSq(); const du = dirModel.dot(pr.dPdu) / lu, dv = dirModel.dot(pr.dPdv) / lv; const x = du * S, y = dv * S, l = Math.hypot(x, y) || 1; return [x / l, y / l];
  },

  // a hit on the canopy: `amount` is the subsystem damage it did
  crack(amount) {
    if (!this.ctx) return; const n = clamp(Math.round(amount / 9), 1, 3); let drew = false;
    for (let k = 0; k < n; k++) {
      let pr = null; for (let tries = 0; tries < 6 && !pr; tries++) pr = this._probe(rndS(1) * rndS(1) * 58 * DEG, rnd(-14, 30) * DEG + Math.abs(rndS(14)) * DEG, Math.random() < 0.22);
      if (!pr) continue;
      this._impact(pr, clamp(0.55 + amount / 14, 0.6, 1.9) * rnd(0.8, 1.2)); drew = true; this.impacts++;
      fx.sparks(pr.point, _v.copy(this.heli.fwd).negate(), 6, 7);
    }
    // once the canopy is badly hurt the fractures start to run across whole panes
    if (this.heli.sub.canopy < 40 && Math.random() < 0.6) { const pr = this._probe(rndS(40) * DEG, rnd(-5, 26) * DEG); if (pr) { this._runner(pr); drew = true; } }
    if (drew) this.tex.needsUpdate = true;
  },
  _impact(pr, size) {
    const c = this.ctx; c.save(); c.translate(pr.x, pr.y); c.scale(pr.sx, pr.sy); c.lineCap = 'round'; c.lineJoin = 'round';   // now drawing in metres
    const px = 1 / Math.min(pr.sx, pr.sy);
    // bruise: crazed, milky glass around the strike
    const R = 0.085 * size; let g = c.createRadialGradient(0, 0, 0, 0, 0, R); g.addColorStop(0, 'rgba(226,238,242,0.62)'); g.addColorStop(0.35, 'rgba(214,230,236,0.24)'); g.addColorStop(1, 'rgba(210,228,235,0)'); c.fillStyle = g; c.beginPath(); c.arc(0, 0, R, 0, TAU); c.fill();
    // radial fractures: jagged, tapering, some fork
    const rays = 8 + (Math.random() * 7 | 0), web = [];
    for (let i = 0; i < rays; i++) {
      let a = i / rays * TAU + rndS(0.28); const len = (0.065 + Math.pow(Math.random(), 1.8) * 0.25) * size; const segs = 5 + (Math.random() * 4 | 0); let x = 0, y = 0, d = 0; const pts = [[0, 0, 0]];
      for (let s = 1; s <= segs; s++) {
        a += rndS(0.22); const l = len / segs * rnd(0.7, 1.3); const nx = x + Math.cos(a) * l, ny = y + Math.sin(a) * l; const k = 1 - s / (segs + 1);
        c.strokeStyle = `rgba(236,246,250,${0.45 + 0.5 * k})`; c.lineWidth = Math.max(px * 0.8, 0.0034 * size * k + px * 0.5); c.beginPath(); c.moveTo(x, y); c.lineTo(nx, ny); c.stroke();
        c.strokeStyle = `rgba(8,12,12,${0.35 * k})`; c.lineWidth = px * 0.8; c.beginPath(); c.moveTo(x + px, y + px); c.lineTo(nx + px, ny + px); c.stroke();     // the shadowed lip of each fracture
        x = nx; y = ny; d += l; pts.push([x, y, d]);
        if (s > 1 && Math.random() < 0.2) { let fa = a + (Math.random() < 0.5 ? 1 : -1) * rnd(0.5, 0.9), fx_ = x, fy = y; c.strokeStyle = 'rgba(232,244,248,0.6)'; c.lineWidth = Math.max(px * 0.7, 0.0015 * size * k); c.beginPath(); c.moveTo(fx_, fy); for (let j = 0; j < 3; j++) { fa += rndS(0.25); fx_ += Math.cos(fa) * len * 0.11; fy += Math.sin(fa) * len * 0.11; c.lineTo(fx_, fy); } c.stroke(); }
      }
      web.push(pts);
    }
    // concentric fractures: chords between neighbouring rays, broken up, densest near the centre
    for (const rr of [0.018, 0.036, 0.062, 0.095, 0.135]) {
      const r = rr * size * rnd(0.85, 1.15); c.strokeStyle = `rgba(230,242,247,${lerp(0.85, 0.4, sat(rr / 0.18))})`; c.lineWidth = Math.max(px * 0.7, 0.0016 * size);
      for (let i = 0; i < rays; i++) {
        if (Math.random() < 0.18 + rr * 2.2) continue; const A = at(web[i], r * rnd(0.9, 1.1)), B = at(web[(i + 1) % rays], r * rnd(0.9, 1.1)); if (!A || !B) continue;
        c.beginPath(); c.moveTo(A[0], A[1]); c.lineTo(B[0], B[1]); c.stroke();
      }
    }
    // crushed core + the hole
    c.fillStyle = 'rgba(240,248,250,0.93)'; c.beginPath(); const cr = 0.017 * size; for (let i = 0; i <= 9; i++) { const a = i / 9 * TAU, r = cr * rnd(0.6, 1.25); i ? c.lineTo(Math.cos(a) * r, Math.sin(a) * r) : c.moveTo(Math.cos(a) * r, Math.sin(a) * r); } c.closePath(); c.fill();
    for (let i = 0; i < 26; i++) { const a = rnd(TAU), r = cr * rnd(0.8, 3.2); c.fillStyle = `rgba(240,248,250,${rnd(0.35, 0.9)})`; c.fillRect(Math.cos(a) * r, Math.sin(a) * r, px * rnd(0.8, 2), px * rnd(0.8, 2)); }
    c.fillStyle = 'rgba(6,8,8,0.9)'; c.beginPath(); c.arc(rndS(cr * 0.2), rndS(cr * 0.2), cr * 0.38, 0, TAU); c.fill();
    c.restore();
  },
  // a long fracture running across the pane
  _runner(pr) {
    const c = this.ctx; c.save(); c.translate(pr.x, pr.y); c.scale(pr.sx, pr.sy); c.lineCap = 'round'; const px = 1 / Math.min(pr.sx, pr.sy);
    for (const dir of [0, Math.PI]) { let a = rnd(TAU) * 0.15 + dir + rndS(0.5), x = 0, y = 0; const segs = 9 + (Math.random() * 8 | 0);
      for (let s = 0; s < segs; s++) { a += rndS(0.2); const l = rnd(0.03, 0.075); const nx = x + Math.cos(a) * l, ny = y + Math.sin(a) * l, k = 1 - s / segs;
        c.strokeStyle = `rgba(236,246,250,${0.35 + 0.5 * k})`; c.lineWidth = Math.max(px * 0.8, 0.0026 * k + px * 0.4); c.beginPath(); c.moveTo(x, y); c.lineTo(nx, ny); c.stroke();
        c.strokeStyle = `rgba(8,12,12,${0.3 * k})`; c.lineWidth = px * 0.8; c.beginPath(); c.moveTo(x + px, y + px); c.lineTo(nx + px, ny + px); c.stroke(); x = nx; y = ny; } }
    c.restore();
  },
  // hydraulic fluid thrown onto the windscreen and dragged aft by the airflow
  oil() {
    if (!this.ctx || this.oiled) return; this.oiled = true; const c = this.ctx; let drew = false;
    for (let k = 0; k < 2; k++) {
      const pr = this._probe(rndS(34) * DEG, rnd(-6, 14) * DEG); if (!pr) continue; drew = true;
      const [dx, dy] = this._texDir(pr, _v.set(rndS(0.15), 0.75, 0.65).normalize());      // up and aft over the glass (model space: +z is aft)
      const sc = Math.min(pr.sx, pr.sy); c.save(); c.translate(pr.x, pr.y); c.lineCap = 'round';
      // a fine spray thrown from one side, each drop dragged into a thin tail; a few heavier runs
      for (let i = 0; i < 90; i++) {
        const big = i < 7, sp = big ? 0.07 : 0.16; const ox = rndS(sp) * rnd(0.3, 1) * sc, oy = rndS(sp) * rnd(0.3, 1) * sc, r = (big ? rnd(0.004, 0.009) : rnd(0.0008, 0.003)) * sc, len = (big ? rnd(0.12, 0.34) : rnd(0.01, 0.07)) * sc;
        const ex = ox + dx * len + rndS(0.012) * sc, ey = oy + dy * len + rndS(0.012) * sc;
        const g = c.createLinearGradient(ox, oy, ex, ey); g.addColorStop(0, `rgba(24,16,6,${big ? 0.7 : 0.55})`); g.addColorStop(0.5, 'rgba(36,25,9,0.3)'); g.addColorStop(1, 'rgba(40,28,10,0)');
        c.strokeStyle = g; c.lineWidth = Math.max(0.8, r * (big ? 1.1 : 1.4)); c.beginPath(); c.moveTo(ox, oy); c.quadraticCurveTo((ox + ex) / 2 + rndS(0.008) * sc, (oy + ey) / 2 + rndS(0.008) * sc, ex, ey); c.stroke();
        c.fillStyle = `rgba(20,13,5,${big ? 0.8 : 0.6})`; c.beginPath(); c.ellipse(ox, oy, r * rnd(0.8, 1.3), r * rnd(0.6, 1), rnd(TAU), 0, TAU); c.fill();
      }
      { const r = 0.14 * sc, g = c.createRadialGradient(0, 0, 0, 0, 0, r); g.addColorStop(0, 'rgba(34,24,9,0.2)'); g.addColorStop(1, 'rgba(34,24,9,0)'); c.fillStyle = g; c.beginPath(); c.arc(0, 0, r, 0, TAU); c.fill(); }   // thin film
      c.restore();
    }
    if (drew) this.tex.needsUpdate = true;
  },

  // ---------- arrows lodged in the skin ----------
  arrowHit() { if (this.arrows && Math.random() < 0.7) this.queue = Math.min(3, this.queue + 1); },
  _stick() {
    const im = this.arrows, sm = this.samples; if (!im || !sm || !sm.length) return;
    // archers shoot up from the ground: the arrow travels upward in the airframe's frame
    _v.set(rndS(0.8), rnd(0.35, 1), rndS(0.8)).normalize(); let best = null, bd = 0.25;
    for (let k = 0; k < 10; k++) { const s = sm[(Math.random() * sm.length) | 0]; const d = -s.n.dot(_v); if (d > bd) { bd = d; best = s; } }
    if (!best) return; const i = this.arrowN % MAXARROWS; this.arrowN++;
    _q.setFromUnitVectors(_z, _v); _m.compose(_v2.copy(best.p).addScaledVector(_v, -rnd(0.12, 0.26)), _q, _s); im.setMatrixAt(i, _m); im.count = Math.min(MAXARROWS, this.arrowN); im.instanceMatrix.needsUpdate = true;
  },

  repair(s) { if (s === 'canopy') this._base(); if (s === 'hyd' && this.oiled) { const keep = this.impacts; /* glass is cleaned with the repair */ if (!keep) this._base(); else this.oiled = false; } },
  reset() { if (this.ctx) this._base(); this.queue = 0; this.arrowN = 0; if (this.arrows) { this.arrows.count = 0; this.arrows.instanceMatrix.needsUpdate = true; } this.lightK = 0; if (this.light) this.light.intensity = 0; },

  update(dt, camera) {
    const h = this.heli; if (!h || !h.model) return;
    if (this.queue > 0) { this.queue--; this._stick(); }
    // fractures and scratches catch the sun: brightest when you look into it
    if (this.mat) {
      _v.set(0, 0, -1).applyQuaternion(camera.quaternion); const toward = sat(_v.dot(G.U.uSunDir.value) * 0.5 + 0.5); const sunLum = G.U.uSunCol.value.r * 0.4 + G.U.uSunCol.value.g * 0.5 + G.U.uSunCol.value.b * 0.1;
      this.mat.emissiveIntensity = (0.03 + 0.3 * Math.pow(toward, 3)) * Math.min(1.6, sunLum) * (h.charred ? 0 : 1);
      this.mat.emissive.copy(G.U.uSunCol.value); const mx = Math.max(this.mat.emissive.r, this.mat.emissive.g, this.mat.emissive.b, 1e-3); this.mat.emissive.multiplyScalar(1 / mx);
    }
    // cockpit emergency: a red lamp pulses once the airframe is in real trouble, and the panel throws sparks
    const bad = h.state === 'crashing' ? 1 : h.state === 'fly' ? sat((45 - h.hull) / 30) : 0;
    this.lightK = damp(this.lightK, bad, 3, dt);
    if (this.fill) this.fill.intensity = h.cockpit && h.state !== 'dead' ? 0.55 : 0;
    if (this.light) this.light.intensity = h.cockpit ? this.lightK * (0.35 + 0.65 * Math.pow(0.5 + 0.5 * Math.sin(G.time * 7.5), 2)) * 1.3 : 0;
    if (h.cockpit && bad > 0.3 && h.state !== 'dead') {
      this.sparkT -= dt; if (this.sparkT <= 0) { this.sparkT = rnd(0.5, 2.6) / bad; _v.copy(h.eye).add(_v2.set(rndS(0.42), rnd(-0.5, -0.2), rnd(-0.85, -0.6))).applyQuaternion(h.q).add(h.pos); fx.sparks(_v, h.up, 5 + (Math.random() * 8 | 0), 4); }
    }
  },
};
// point at path length d along a fractured ray ([x, y, cumulative length] nodes)
function at(pts, d) { for (let i = 1; i < pts.length; i++) { if (pts[i][2] >= d) { const a = pts[i - 1], b = pts[i], t = (d - a[2]) / Math.max(1e-6, b[2] - a[2]); return [lerp(a[0], b[0], t), lerp(a[1], b[1], t)]; } } return null; }
