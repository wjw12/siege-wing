// Siege Wing — collision world: static colliders (towers, walls, houses, trees) in a spatial hash
import { terrain } from './terrain.js';

const CELL = 40;
const key = (i, j) => (i + 512) * 1024 + (j + 512);
export const world = {
  grid: new Map(), all: [],
  clear() { this.grid.clear(); this.all.length = 0; },
  _insert(c, rad) {
    const i0 = Math.floor((c.x - rad) / CELL), i1 = Math.floor((c.x + rad) / CELL), j0 = Math.floor((c.z - rad) / CELL), j1 = Math.floor((c.z + rad) / CELL);
    for (let i = i0; i <= i1; i++) for (let j = j0; j <= j1; j++) { const k = key(i, j); let a = this.grid.get(k); if (!a) this.grid.set(k, a = []); a.push(c); }
    this.all.push(c); return c;
  },
  // kind: 'tower' | 'wall' | 'keep' | 'house' | 'tree' | 'prop'; ref: owner object (for damage callbacks)
  addCyl(x, z, r, y0, y1, kind, ref) { return this._insert({ t: 0, x, z, r, y0, y1, kind, ref, alive: true }, r); },
  addBox(x, z, hx, hz, rot, y0, y1, kind, ref) { return this._insert({ t: 1, x, z, hx, hz, c: Math.cos(rot), s: Math.sin(rot), y0, y1, kind, ref, alive: true }, Math.hypot(hx, hz)); },
  _test(c, x, y, z, pad) {
    if (!c.alive || y < c.y0 - pad || y > c.y1 + pad) return false;
    const dx = x - c.x, dz = z - c.z;
    if (c.t === 0) { const r = c.r + pad; return dx * dx + dz * dz < r * r; }
    const lx = dx * c.c + dz * c.s, lz = -dx * c.s + dz * c.c; return Math.abs(lx) < c.hx + pad && Math.abs(lz) < c.hz + pad;
  },
  // returns collider containing the point (optionally padded) or null
  pointHit(x, y, z, pad = 0) {
    const a = this.grid.get(key(Math.floor(x / CELL), Math.floor(z / CELL))); if (!a) return null;
    for (let i = 0; i < a.length; i++) if (this._test(a[i], x, y, z, pad)) return a[i];
    return null;
  },
  // segment test by stepping; returns { c, t (0..1), x,y,z } or null. Also tests terrain when withTerrain.
  segHit(x0, y0, z0, x1, y1, z1, step = 1.5, withTerrain = true, out = _out) {
    const dx = x1 - x0, dy = y1 - y0, dz = z1 - z0; const len = Math.hypot(dx, dy, dz); const n = Math.max(1, Math.ceil(len / step));
    for (let i = 1; i <= n; i++) {
      const t = i / n, x = x0 + dx * t, y = y0 + dy * t, z = z0 + dz * t;
      const c = this.pointHit(x, y, z);
      if (c) { out.c = c; out.t = t; out.x = x; out.y = y; out.z = z; return out; }
      if (withTerrain && y < terrain.height(x, z)) { out.c = null; out.t = t; out.x = x; out.y = terrain.height(x, z); out.z = z; return out; }
    }
    return null;
  },
  // highest structure top under a point (for things standing on walls), or terrain
  nearby(x, z, r, fn) {
    const i0 = Math.floor((x - r) / CELL), i1 = Math.floor((x + r) / CELL), j0 = Math.floor((z - r) / CELL), j1 = Math.floor((z + r) / CELL); const seen = _seen; seen.clear();
    for (let i = i0; i <= i1; i++) for (let j = j0; j <= j1; j++) { const a = this.grid.get(key(i, j)); if (a) for (const c of a) if (c.alive && !seen.has(c)) { seen.add(c); fn(c); } }
  },
};
const _out = { c: null, t: 0, x: 0, y: 0, z: 0 }, _seen = new Set();
