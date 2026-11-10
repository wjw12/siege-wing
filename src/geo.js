// Siege Wing — tiny procedural geometry builder (positions, normals, uv in metres, vertex colours)
import * as THREE from 'three';

export class GB {
  constructor() { this.p = []; this.n = []; this.u = []; this.c = []; this.i = []; }
  get count() { return this.p.length / 3; }
  // quad a,b,c,d counter-clockwise seen from the front; uv per corner [u,v]
  quad(a, b, c, d, ua, ub, uc, ud, col = WHITE, n) {
    const i = this.count;
    if (!n) { const ux = b[0] - a[0], uy = b[1] - a[1], uz = b[2] - a[2], vx = d[0] - a[0], vy = d[1] - a[1], vz = d[2] - a[2]; let nx = uy * vz - uz * vy, ny = uz * vx - ux * vz, nz = ux * vy - uy * vx; const l = Math.hypot(nx, ny, nz) || 1; n = [nx / l, ny / l, nz / l]; }
    for (const v of [a, b, c, d]) { this.p.push(v[0], v[1], v[2]); this.n.push(n[0], n[1], n[2]); this.c.push(col[0], col[1], col[2]); }
    this.u.push(ua[0], ua[1], ub[0], ub[1], uc[0], uc[1], ud[0], ud[1]);
    this.i.push(i, i + 1, i + 2, i, i + 2, i + 3);
  }
  tri(a, b, c, ua, ub, uc, col = WHITE) {
    const i = this.count; const ux = b[0] - a[0], uy = b[1] - a[1], uz = b[2] - a[2], vx = c[0] - a[0], vy = c[1] - a[1], vz = c[2] - a[2]; let nx = uy * vz - uz * vy, ny = uz * vx - ux * vz, nz = ux * vy - uy * vx; const l = Math.hypot(nx, ny, nz) || 1;
    for (const v of [a, b, c]) { this.p.push(v[0], v[1], v[2]); this.n.push(nx / l, ny / l, nz / l); this.c.push(col[0], col[1], col[2]); }
    this.u.push(ua[0], ua[1], ub[0], ub[1], uc[0], uc[1]); this.i.push(i, i + 1, i + 2);
  }
  // oriented box: centre (cx, cy, cz), size, yaw; faces: bitmask 1 top, 2 bottom, 4 sides (default top+sides)
  box(cx, cy, cz, sx, sy, sz, ry = 0, col = WHITE, faces = 5, uo = 0) {
    const c = Math.cos(ry), s = Math.sin(ry), hx = sx / 2, hy = sy / 2, hz = sz / 2;
    const P = (x, y, z) => [cx + x * c + z * s, cy + y, cz - x * s + z * c];
    const y0 = cy - hy, y1 = cy + hy;
    if (faces & 4) {
      // +z, +x, -z, -x faces; u continuous around the perimeter
      let u = uo;
      this.quad(P(-hx, -hy, hz), P(hx, -hy, hz), P(hx, hy, hz), P(-hx, hy, hz), [u, y0], [u + sx, y0], [u + sx, y1], [u, y1], col); u += sx;
      this.quad(P(hx, -hy, hz), P(hx, -hy, -hz), P(hx, hy, -hz), P(hx, hy, hz), [u, y0], [u + sz, y0], [u + sz, y1], [u, y1], col); u += sz;
      this.quad(P(hx, -hy, -hz), P(-hx, -hy, -hz), P(-hx, hy, -hz), P(hx, hy, -hz), [u, y0], [u + sx, y0], [u + sx, y1], [u, y1], col); u += sx;
      this.quad(P(-hx, -hy, -hz), P(-hx, -hy, hz), P(-hx, hy, hz), P(-hx, hy, -hz), [u, y0], [u + sz, y0], [u + sz, y1], [u, y1], col);
    }
    if (faces & 1) { const a = P(-hx, hy, hz), b = P(hx, hy, hz), cc = P(hx, hy, -hz), d = P(-hx, hy, -hz); this.quad(a, b, cc, d, [a[0], a[2]], [b[0], b[2]], [cc[0], cc[2]], [d[0], d[2]], col); }
    if (faces & 2) { const a = P(-hx, -hy, -hz), b = P(hx, -hy, -hz), cc = P(hx, -hy, hz), d = P(-hx, -hy, hz); this.quad(a, b, cc, d, [a[0], a[2]], [b[0], b[2]], [cc[0], cc[2]], [d[0], d[2]], col); }
    return this;
  }
  // vertical cylinder / frustum; jag(i) optionally returns per-segment top height offset; capTop adds a lid at y1
  cyl(cx, y0, cz, r0, r1, h, seg = 20, col = WHITE, capTop = true, jag = null, a0 = 0, a1 = Math.PI * 2, inward = false) {
    const y1 = y0 + h; const rm = (r0 + r1) / 2; const sl = (r0 - r1) / h;
    for (let i = 0; i < seg; i++) {
      const aa = a0 + (a1 - a0) * i / seg, ab = a0 + (a1 - a0) * (i + 1) / seg;
      const ca = Math.cos(aa), sa = Math.sin(aa), cb = Math.cos(ab), sb = Math.sin(ab);
      const ja = jag ? jag(i) : 0, jb = jag ? jag((i + 1) % seg) : 0;
      const A = [cx + ca * r0, y0, cz + sa * r0], B = [cx + cb * r0, y0, cz + sb * r0], C = [cx + cb * r1, y1 + jb, cz + sb * r1], D = [cx + ca * r1, y1 + ja, cz + sa * r1];
      const ua = aa * rm, ub = ab * rm;
      const i0 = this.count; const sgn = inward ? -1 : 1;
      const na = [ca * sgn, sl * sgn, sa * sgn], nb = [cb * sgn, sl * sgn, sb * sgn];
      const vs = inward ? [B, A, D, C] : [A, B, C, D]; const ns = inward ? [nb, na, na, nb] : [na, nb, nb, na]; const us = inward ? [[ub, y0], [ua, y0], [ua, y1 + ja], [ub, y1 + jb]] : [[ua, y0], [ub, y0], [ub, y1 + jb], [ua, y1 + ja]];
      for (let k = 0; k < 4; k++) { this.p.push(...vs[k]); this.n.push(...ns[k]); this.c.push(col[0], col[1], col[2]); this.u.push(...us[k]); }
      // winding: outward faces need (A,B,C,D) with B counter-clockwise from above → flip
      this.i.push(i0, i0 + 2, i0 + 1, i0, i0 + 3, i0 + 2);
      if (capTop && r1 > 0.01) { const T = [cx, y1 + (jag ? Math.min(ja, jb) : 0), cz]; this.tri(C, D, T, [C[0], C[2]], [D[0], D[2]], [T[0], T[2]], col); }
    }
    return this;
  }
  // ring of merlons on a circle
  merlons(cx, y, cz, r, n, w, h, t, col = WHITE) { for (let i = 0; i < n; i++) { if (i % 2) continue; const a = (i + 0.5) / n * Math.PI * 2; this.box(cx + Math.cos(a) * r, y + h / 2, cz + Math.sin(a) * r, w, h, t, -a + Math.PI / 2, col, 5); } return this; }
  // gable roof over a box footprint (ridge along local x)
  gable(cx, y, cz, sx, sz, rise, ry = 0, col = WHITE, over = 0.5) {
    const c = Math.cos(ry), s = Math.sin(ry), hx = sx / 2 + over, hz = sz / 2 + over;
    const P = (x, yy, z) => [cx + x * c + z * s, y + yy, cz - x * s + z * c];
    const sl = Math.hypot(hz, rise);
    this.quad(P(-hx, 0, hz), P(hx, 0, hz), P(hx, rise, 0), P(-hx, rise, 0), [0, 0], [sx, 0], [sx, sl], [0, sl], col);
    this.quad(P(hx, 0, -hz), P(-hx, 0, -hz), P(-hx, rise, 0), P(hx, rise, 0), [0, 0], [sx, 0], [sx, sl], [0, sl], col);
    return this;
  }
  gableEnds(cx, y, cz, sx, sz, rise, ry = 0, col = WHITE) {
    const c = Math.cos(ry), s = Math.sin(ry), hx = sx / 2, hz = sz / 2; const P = (x, yy, z) => [cx + x * c + z * s, y + yy, cz - x * s + z * c];
    this.tri(P(hx, 0, hz), P(hx, 0, -hz), P(hx, rise, 0), [0, y], [sz, y], [hz, y + rise], col);
    this.tri(P(-hx, 0, -hz), P(-hx, 0, hz), P(-hx, rise, 0), [0, y], [sz, y], [hz, y + rise], col);
    return this;
  }
  // flat annulus between radii ri..ro at height y (facing up, or down for soffits)
  ring(cx, y, cz, ri, ro, seg = 20, col = WHITE, down = false, a0 = 0, a1 = Math.PI * 2) {
    for (let i = 0; i < seg; i++) {
      const aa = a0 + (a1 - a0) * i / seg, ab = a0 + (a1 - a0) * (i + 1) / seg; const ca = Math.cos(aa), sa = Math.sin(aa), cb = Math.cos(ab), sb = Math.sin(ab);
      const A = [cx + ca * ri, y, cz + sa * ri], B = [cx + cb * ri, y, cz + sb * ri], C = [cx + cb * ro, y, cz + sb * ro], D = [cx + ca * ro, y, cz + sa * ro];
      const uv = p => [p[0], p[2]];
      if (down) this.quad(D, C, B, A, uv(D), uv(C), uv(B), uv(A), col, [0, -1, 0]); else this.quad(A, B, C, D, uv(A), uv(B), uv(C), uv(D), col, [0, 1, 0]);
    }
    return this;
  }
  // general hexahedron: b = 4 bottom corners, t = 4 top corners, both in the order (-x,+z), (+x,+z), (+x,-z), (-x,-z) of a local frame (any yaw); corners may coincide (wedges, hips)
  // faces: bitmask 1 top, 2 bottom, 4 sides; sides get u in metres along the perimeter (from uo) and v = height
  hexa(b, t, col = WHITE, faces = 5, uo = 0) {
    const nrm = (A, B, C, D) => { const x1 = B[0] - A[0], y1 = B[1] - A[1], z1 = B[2] - A[2], x2 = C[0] - A[0], y2 = C[1] - A[1], z2 = C[2] - A[2], x3 = D[0] - A[0], y3 = D[1] - A[1], z3 = D[2] - A[2];
      const nx = y1 * z2 - z1 * y2 + y2 * z3 - z2 * y3, ny = z1 * x2 - x1 * z2 + z2 * x3 - x2 * z3, nz = x1 * y2 - y1 * x2 + x2 * y3 - y2 * x3; const l = Math.hypot(nx, ny, nz); return l > 1e-9 ? [nx / l, ny / l, nz / l] : null; };
    if (faces & 4) { let u = uo; for (let i = 0; i < 4; i++) { const A = b[i], B = b[(i + 1) % 4], C = t[(i + 1) % 4], D = t[i]; const l = Math.hypot(B[0] - A[0], B[2] - A[2]) || Math.hypot(C[0] - D[0], C[2] - D[2]); const n = nrm(A, B, C, D);
      if (n) this.quad(A, B, C, D, [u, A[1]], [u + l, B[1]], [u + l, C[1]], [u, D[1]], col, n); u += l; } }
    if (faces & 1) { const n = nrm(t[0], t[1], t[2], t[3]); if (n) this.quad(t[0], t[1], t[2], t[3], [t[0][0], t[0][2]], [t[1][0], t[1][2]], [t[2][0], t[2][2]], [t[3][0], t[3][2]], col, n); }
    if (faces & 2) { const n = nrm(b[3], b[2], b[1], b[0]); if (n) this.quad(b[3], b[2], b[1], b[0], [b[3][0], b[3][2]], [b[2][0], b[2][2]], [b[1][0], b[1][2]], [b[0][0], b[0][2]], col, n); }
    return this;
  }
  // faceted boulder / crag piece: a sphere cut down to a convex polytope by planes, scaled, tilted and yawed; flat shaded.
  // level 0..2 = 20 / 80 / 320 triangles. flat <= 0.5: random cuts (boulders); flat > 0.5: bedding and joint planes (a squarish block of strata) with a few chamfers.
  // keep(a, b, c) may reject triangles (e.g. buried ones)
  rock(cx, cy, cz, sx, sy, sz, rng, level = 1, col = WHITE, yaw = 0, tilt = 0, flat = 0.3, keep = null) {
    const { v, f } = icoSphere(level); const pl = []; const U = (x, y, z, d) => { const l = Math.hypot(x, y, z) || 1; pl.push([x / l, y / l, z / l, d]); };
    if (flat > 0.5) {
      const ja = 0.5 + (0.9 - Math.min(flat, 0.9)) * 2.2, cd = flat < 0.75 ? 0.6 : 0.72; const j = () => (rng() - 0.5) * ja, d = () => 0.5 + rng() * 0.3;
      U(1, j() * 0.5, j(), d()); U(-1, j() * 0.5, j(), d()); U(j(), j() * 0.5, 1, d()); U(j(), j() * 0.5, -1, d()); U(j() * 0.25, 1, j() * 0.25, 0.45 + rng() * 0.3); U(0, -1, 0, 0.7);
      for (let i = 0; i < 3 + level * 2; i++) U(rng() * 2 - 1, (rng() * 2 - 1) * 0.8, rng() * 2 - 1, cd + rng() * 0.22);
    } else {
      for (let i = 0; i < 9 + level * 5; i++) U(rng() * 2 - 1, (rng() * 2 - 1) * (1 - flat * 0.6), rng() * 2 - 1, 0.5 + rng() * 0.33);
      U(0, 1, 0, 0.45 + rng() * 0.35);
    }
    const cyw = Math.cos(yaw), syw = Math.sin(yaw), ct = Math.cos(tilt), st = Math.sin(tilt);
    const pts = v.map(p => { let t = 1.15; for (const q of pl) { const dn = p[0] * q[0] + p[1] * q[1] + p[2] * q[2]; if (dn > 1e-3 && q[3] / dn < t) t = q[3] / dn; }
      const x = p[0] * t * sx, y0 = p[1] * t * sy, z0 = p[2] * t * sz; const y = y0 * ct - z0 * st, z = y0 * st + z0 * ct; return [cx + x * cyw + z * syw, cy + y, cz - x * syw + z * cyw]; });
    for (const fc of f) {
      let a = pts[fc[0]], b = pts[fc[1]], c = pts[fc[2]]; if (keep && !keep(a, b, c)) continue;
      const ux = b[0] - a[0], uy = b[1] - a[1], uz = b[2] - a[2], vx = c[0] - a[0], vy = c[1] - a[1], vz = c[2] - a[2]; let nx = uy * vz - uz * vy, ny = uz * vx - ux * vz, nz = ux * vy - uy * vx;
      if (nx * nx + ny * ny + nz * nz < 1e-10) continue;
      if (nx * ((a[0] + b[0] + c[0]) / 3 - cx) + ny * ((a[1] + b[1] + c[1]) / 3 - cy) + nz * ((a[2] + b[2] + c[2]) / 3 - cz) < 0) { const q = b; b = c; c = q; nx = -nx; ny = -ny; nz = -nz; }
      const ax = Math.abs(nx), ay = Math.abs(ny), az = Math.abs(nz); const uv = ay >= ax && ay >= az ? p => [p[0], p[2]] : (ax > az ? p => [p[2], p[1]] : p => [p[0], p[1]]);
      this.tri(a, b, c, uv(a), uv(b), uv(c), col);
    }
    return this;
  }
  build() {
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(this.p, 3)); g.setAttribute('normal', new THREE.Float32BufferAttribute(this.n, 3));
    g.setAttribute('uv', new THREE.Float32BufferAttribute(this.u, 2)); g.setAttribute('color', new THREE.Float32BufferAttribute(this.c, 3));
    g.setIndex(this.i); g.computeBoundingSphere(); g.computeBoundingBox(); return g;
  }
}
const WHITE = [1, 1, 1];
const ICO = [];
function icoSphere(level) {
  if (ICO[level]) return ICO[level];
  const t = (1 + Math.sqrt(5)) / 2; const nm = p => { const l = Math.hypot(p[0], p[1], p[2]); return [p[0] / l, p[1] / l, p[2] / l]; };
  let v = [[-1, t, 0], [1, t, 0], [-1, -t, 0], [1, -t, 0], [0, -1, t], [0, 1, t], [0, -1, -t], [0, 1, -t], [t, 0, -1], [t, 0, 1], [-t, 0, -1], [-t, 0, 1]].map(nm);
  let f = [[0, 11, 5], [0, 5, 1], [0, 1, 7], [0, 7, 10], [0, 10, 11], [1, 5, 9], [5, 11, 4], [11, 10, 2], [10, 7, 6], [7, 1, 8], [3, 9, 4], [3, 4, 2], [3, 2, 6], [3, 6, 8], [3, 8, 9], [4, 9, 5], [2, 4, 11], [6, 2, 10], [8, 6, 7], [9, 8, 1]];
  for (let l = 0; l < level; l++) {
    const mid = new Map(), nf = []; const m = (a, b) => { const k = a < b ? a * 65536 + b : b * 65536 + a; let i = mid.get(k); if (i === undefined) { i = v.length; v.push(nm([v[a][0] + v[b][0], v[a][1] + v[b][1], v[a][2] + v[b][2]])); mid.set(k, i); } return i; };
    for (const [a, b, c] of f) { const ab = m(a, b), bc = m(b, c), ca = m(c, a); nf.push([a, ab, ca], [b, bc, ab], [c, ca, bc], [ab, bc, ca]); }
    f = nf;
  }
  return ICO[level] = { v, f };
}
