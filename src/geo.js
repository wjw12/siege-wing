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
  build() {
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(this.p, 3)); g.setAttribute('normal', new THREE.Float32BufferAttribute(this.n, 3));
    g.setAttribute('uv', new THREE.Float32BufferAttribute(this.u, 2)); g.setAttribute('color', new THREE.Float32BufferAttribute(this.c, 3));
    g.setIndex(this.i); g.computeBoundingSphere(); g.computeBoundingBox(); return g;
  }
}
const WHITE = [1, 1, 1];
