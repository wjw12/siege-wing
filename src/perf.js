// Siege Wing — FPS counter (top-right) and low-frame-rate advice
import { settings, saveSettings } from './input.js';
import { Q, dev } from './dev.js';

const $ = id => document.getElementById(id);
const NEXT = { high: 'medium', medium: 'low' };
const NAME = { high: 'High', medium: 'Medium', low: 'Low' };
// advise when flying averages under 30 FPS for 8 s straight (?lowfps=N raises the threshold to test the advice)
const LOW_FPS = +(Q.get('lowfps') || 30), WINDOW = 8;

export const perf = {
  fps: 0, acc: 0, n: 0, frames: 0, time: 0, advised: {}, tipT: 0, pending: null, onApply: null,
  init(onApply) {
    this.onApply = onApply; this.el = $('fps'); this.tip = $('perfTip');
    $('perfApply').addEventListener('click', () => { const q = NEXT[settings.quality]; if (q) { this.apply(q); this.pending = { done: q }; } this.note(); });
    $('perfDismiss').addEventListener('click', () => { this.pending = null; this.note(); });
    this.sync();
  },
  sync() { this.el.classList.toggle('on', settings.showFps !== false && (!Q.has('shots') || Q.has('fps')) && !Q.has('nofps')); },
  apply(q) { settings.quality = q; saveSettings(); this.onApply(q); this.pending = null; this.frames = this.time = 0; this.tip.classList.remove('on'); },
  // rawSec: unclamped real frame time; flying: in the air, unpaused, past the first seconds of warm-up
  frame(rawSec, flying, dt) {
    if (!this.el || document.hidden || rawSec <= 0 || rawSec > 1) return;
    this.acc += rawSec; this.n++;
    if (this.acc >= 0.5) {
      this.fps = this.n / this.acc; this.acc = this.n = 0; const f = Math.round(this.fps);
      this.el.textContent = f + ' FPS'; this.el.className = 'on ' + (f >= 50 ? 'good' : f >= 30 ? 'ok' : 'bad'); this.sync();
    }
    if (!flying) { this.frames = this.time = 0; } else {
      this.frames++; this.time += rawSec;
      if (this.time >= WINDOW) { const avg = this.frames / this.time; this.frames = this.time = 0; if (avg < LOW_FPS) this._advise(avg); }
    }
    if (this.tipT > 0 && (this.tipT -= dt) <= 0) this.tip.classList.remove('on');
  },
  _advise(avg) {
    const q = settings.quality; if (this.advised[q]) return; this.advised[q] = true;
    const next = NEXT[q]; this.pending = { avg: Math.round(avg), q, next };
    this.tip.innerHTML = next ? `LOW FRAME RATE — PRESS <b>ESC</b> TO SWITCH GRAPHICS TO <b>${NAME[next].toUpperCase()}</b>` : 'LOW FRAME RATE — TRY A SMALLER BROWSER WINDOW';
    this.tip.classList.add('on'); this.tipT = 12; dev.log(`PERF advise avg=${avg.toFixed(1)} q=${q} next=${next} fpsEl="${this.el.textContent}" cls=${this.el.className}`);
  },
  // pause-menu callout with a one-click fix
  note() {
    const p = this.pending, box = $('perfNote'); box.classList.toggle('on', !!p); if (!p) return; box.querySelector('.eye').textContent = p.done ? 'GRAPHICS' : 'LOW FRAME RATE';
    if (p.done) { $('perfText').innerHTML = `Graphics set to <b>${NAME[p.done]}</b>. Resolution and shadows changed now; texture detail and forest range follow the next time the game loads.`; $('perfApply').style.display = 'none'; $('perfDismiss').textContent = 'OK'; this.pending = null; return; }   // shown once
    $('perfText').innerHTML = p.next
      ? `The game has been running at about <b>${p.avg} FPS</b> on <b>${NAME[p.q]}</b> graphics. <b>${NAME[p.next]}</b> should fly smoother.`
      : `The game has been running at about <b>${p.avg} FPS</b>, already on <b>Low</b> graphics. A smaller browser window, closing other tabs, or turning on hardware acceleration in the browser settings will help.`;
    $('perfApply').style.display = p.next ? '' : 'none'; $('perfApply').textContent = p.next ? `Switch to ${NAME[p.next]}` : '';
    $('perfDismiss').textContent = p.next ? `Keep ${NAME[p.q]}` : 'OK';
  },
};
