// dev/test automation: ?shots=a@2,b@5&cam=x,y,z,tx,ty,tz&tod=0.3&auto=scenario
import { G } from './core.js';
export const Q = new URLSearchParams(location.search);
export const dev = {
  on: Q.has('shots') || Q.has('dev'),
  shots: (Q.get('shots') || '').split(',').filter(Boolean).map(s => { const [n, t] = s.split('@'); return { name: n, t: parseFloat(t) }; }),
  log(msg) { if (this.on) fetch('/__log', { method: 'POST', body: String(msg) }).catch(() => { }); else console.log(msg); },
  fpsAcc: 0, fpsN: 0, worst: 0, t0: 0,
  init() {
    if (!this.on) return;
    window.addEventListener('error', e => this.log('ERROR ' + e.message + ' @' + (e.filename || '').split('/').pop() + ':' + e.lineno));
    window.addEventListener('unhandledrejection', e => this.log('REJECT ' + (e.reason && (e.reason.stack || e.reason.message) || e.reason)));
    const ce = console.error.bind(console); console.error = (...a) => { this.log('CONSOLE.ERROR ' + a.map(x => (x && x.message) || String(x)).join(' ').slice(0, 1500)); ce(...a); };
    const cw = console.warn.bind(console); console.warn = (...a) => { this.log('WARN ' + a.map(String).join(' ').slice(0, 400)); cw(...a); };
  },
  // call after each rendered frame with sim time since play start
  frame(t, dtReal) {
    if (!this.on) return;
    const nowP = performance.now(); const real = (nowP - (this.lastP || nowP)) / 1000; this.lastP = nowP; (this.samples = this.samples || []).push(real);
    this.fpsAcc += real; this.fpsN++; if (real > this.worst) this.worst = real;
    if (real > 0.04) (this.hitches = this.hitches || []).push(t.toFixed(1) + ':' + (real * 1000).toFixed(0));
    while (this.shots.length && t >= this.shots[0].t) {
      const s = this.shots.shift();
      const ri = G.renderer.info; const sm = this.samples.slice().sort((a, b) => a - b); const med = sm[sm.length >> 1] * 1000, p95 = sm[Math.floor(sm.length * 0.95)] * 1000; this.samples.length = 0;
      const info = `SHOT ${s.name} t=${t.toFixed(1)} avgFps=${(this.fpsN / this.fpsAcc).toFixed(0)} medMs=${med.toFixed(1)} p95Ms=${p95.toFixed(1)} worstMs=${(this.worst * 1000).toFixed(0)} calls=${ri.render.calls} tris=${ri.render.triangles} ${this.extra ? this.extra() : ''} hitches=[${(this.hitches || []).join(' ')}]`; this.hitches = [];
      this.fpsAcc = 0; this.fpsN = 0; this.worst = 0;
      const url = this.capture ? this.capture() : G.renderer.domElement.toDataURL('image/jpeg', 0.9);
      const last = !this.shots.length;
      fetch('/__shot?name=' + s.name + '.jpg', { method: 'POST', body: url }).then(() => { this.log(info); if (last) setTimeout(() => this.log('DONE'), 200); });
    }
  },
};
