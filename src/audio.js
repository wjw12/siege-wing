// Siege Wing — Web Audio engine: procedural core + generated sample bank. No dependencies.
// Synth: one-shots are pre-rendered through OfflineAudioContext into AudioBuffers (a few
// variants each) in the background after init(); loops (rotor, turbine, alerts) are live
// graphs driven by update(). Samples (assets/audio/manifest.json) replace everything human
// or acoustic, layer under the synth rotor / explosions, and fall back to the synth recipe
// until decoded. Buses: sfx, amb, music, voice -> pre -> comp -> lim -> clip -> master.
// The voice / music sequencing ("what plays when") lives in director.js.

const TAU = Math.PI * 2;
const clamp = (v, a, b) => (v < a ? a : v > b ? b : v);
const lerp = (a, b, t) => a + (b - a) * t;
const rnd = (a = 1, b) => (b === undefined ? Math.random() * a : a + Math.random() * (b - a));
const pick = (arr) => arr[(Math.random() * arr.length) | 0];
const num = (v, d) => (typeof v === 'number' && isFinite(v) ? v : d);

let SR = 48000;
const NOISE = {};           // white / pink / brown AudioBuffers (context independent)
const BUF = {};             // name -> [AudioBuffer]   (one-shots + loops)
const OfflineCtx = typeof OfflineAudioContext !== 'undefined' ? OfflineAudioContext
  : (typeof webkitOfflineAudioContext !== 'undefined' ? webkitOfflineAudioContext : null); // eslint-disable-line no-undef

function newBuffer(ch, len, sr) { return new AudioBuffer({ numberOfChannels: ch, length: Math.max(1, len | 0), sampleRate: sr }); }

function ensureNoise() {
  if (NOISE.white) return;
  const len = SR * 3;
  const w = newBuffer(1, len, SR), p = newBuffer(1, len, SR), b = newBuffer(1, len, SR);
  const wd = w.getChannelData(0), pd = p.getChannelData(0), bd = b.getChannelData(0);
  let b0 = 0, b1 = 0, b2 = 0, b3 = 0, b4 = 0, b5 = 0, b6 = 0, br = 0;
  for (let i = 0; i < len; i++) {
    const x = Math.random() * 2 - 1;
    wd[i] = x;
    b0 = 0.99886 * b0 + x * 0.0555179; b1 = 0.99332 * b1 + x * 0.0750759; b2 = 0.969 * b2 + x * 0.153852;
    b3 = 0.8665 * b3 + x * 0.3104856; b4 = 0.55 * b4 + x * 0.5329522; b5 = -0.7616 * b5 - x * 0.016898;
    pd[i] = (b0 + b1 + b2 + b3 + b4 + b5 + b6 + x * 0.5362) * 0.11; b6 = x * 0.115926;
    br = (br + 0.02 * x) / 1.02; bd[i] = br * 3.5;
  }
  // make the loop seamless-ish for brown noise (remove drift step)
  const d = bd[len - 1] - bd[0];
  for (let i = 0; i < len; i++) bd[i] -= d * (i / len);
  NOISE.white = w; NOISE.pink = p; NOISE.brown = b;
}

// ---------------------------------------------------------------- toolkit
function kit(ctx) {
  const k = { ctx };
  k.g = (v = 1) => { const n = ctx.createGain(); n.gain.value = v; return n; };
  k.f = (type, freq, q = 0.707, gain = 0) => {
    const n = ctx.createBiquadFilter(); n.type = type; n.frequency.value = freq; n.Q.value = q; n.gain.value = gain; return n;
  };
  k.o = (type, freq, t0 = 0, t1) => {
    const n = ctx.createOscillator(); n.type = type; n.frequency.value = freq; n.start(t0); if (t1 != null) n.stop(t1); return n;
  };
  k.n = (kind, t0 = 0, t1, rate = 1) => {
    const n = ctx.createBufferSource(); n.buffer = NOISE[kind]; n.loop = true; n.playbackRate.value = rate;
    n.start(t0, Math.random() * 2.5); if (t1 != null) n.stop(t1); return n;
  };
  k.loop = (buf, rate = 1) => {
    const n = ctx.createBufferSource(); n.buffer = buf; n.loop = true; n.playbackRate.value = rate;
    n.start(0, buf ? Math.random() * buf.duration : 0); return n;
  };
  k.shaper = (amount = 2) => {
    const n = ctx.createWaveShaper(); const c = new Float32Array(1025);
    const norm = Math.tanh(amount);
    for (let i = 0; i < 1025; i++) { const x = i / 512 - 1; c[i] = Math.tanh(x * amount) / norm; }
    n.curve = c; return n;
  };
  // envelope: pts = [[tOffset, value, 'e'?], ...]
  k.env = (param, t0, pts) => {
    param.cancelScheduledValues(t0);
    param.setValueAtTime(pts[0][1], t0 + pts[0][0]);
    for (let i = 1; i < pts.length; i++) {
      const [dt, v, kind] = pts[i];
      if (kind === 'e') param.exponentialRampToValueAtTime(Math.max(v, 0.0001), t0 + dt);
      else param.linearRampToValueAtTime(v, t0 + dt);
    }
  };
  k.chain = (...nodes) => { for (let i = 0; i < nodes.length - 1; i++) nodes[i].connect(nodes[i + 1]); return nodes[nodes.length - 1]; };
  return k;
}

// ------------------------------------------------------------ primitives
// pitched sine thump with pitch drop
function sub(k, o, t, f0, f1, dur, g, drop) {
  const os = k.o('sine', f0, t, t + dur + 0.05);
  os.frequency.setValueAtTime(f0, t); os.frequency.exponentialRampToValueAtTime(Math.max(f1, 1), t + (drop || dur * 0.45));
  const a = k.g(0); k.env(a.gain, t, [[0, 0], [0.005, g], [dur, 0.0001, 'e']]);
  os.connect(a).connect(o);
}
// filtered noise burst with optional cutoff sweep
function nz(k, o, t, kind, ftype, f0, f1, q, att, dur, g, sweep) {
  const s = k.n(kind, t, t + dur + 0.05), f = k.f(ftype, f0, q), a = k.g(0);
  if (f1 !== f0) { f.frequency.setValueAtTime(f0, t); f.frequency.exponentialRampToValueAtTime(Math.max(f1, 10), t + (sweep || dur)); }
  k.env(a.gain, t, [[0, 0], [att, g], [dur, 0.0001, 'e']]);
  s.connect(f).connect(a).connect(o); return a;
}
// noise with a sustained (swelling) envelope
function nzSus(k, o, t, kind, ftype, f0, f1, q, att, hold, rel, g) {
  const dur = att + hold + rel, s = k.n(kind, t, t + dur + 0.05), f = k.f(ftype, f0, q), a = k.g(0);
  if (f1 !== f0) { f.frequency.setValueAtTime(f0, t); f.frequency.exponentialRampToValueAtTime(Math.max(f1, 10), t + dur); }
  k.env(a.gain, t, [[0, 0], [att, g], [att + hold, g * 0.8], [dur, 0]]);
  s.connect(f).connect(a).connect(o); return f;
}
// inharmonic partials -> metal / wood resonances
function ping(k, o, t, freqs, dur, g, type = 'sine') {
  freqs.forEach((f, i) => {
    const d = dur / (1 + i * 0.3), os = k.o(type, f, t, t + d + 0.02), a = k.g(0);
    k.env(a.gain, t, [[0, 0], [0.0015, g / (1 + i * 0.45)], [d, 0.0001, 'e']]);
    os.connect(a).connect(o);
  });
}
// sparse random impulses (debris, crackle, fizz)
function crackle(k, o, t, dur, density, g, f = 2500, q = 0.8, ftype = 'bandpass', shape = 1.5) {
  const ctx = k.ctx, len = Math.ceil(dur * SR), b = newBuffer(1, len, SR), d = b.getChannelData(0);
  const p = density / SR;
  for (let i = 0; i < len; i++) {
    const fade = Math.pow(1 - i / len, shape);
    if (Math.random() < p * (0.3 + fade)) {
      const a = (Math.random() * 2 - 1) * fade, L = 8 + ((Math.random() * 60) | 0);
      for (let j = 0; j < L && i + j < len; j++) d[i + j] += a * (1 - j / L) * (Math.random() * 2 - 1);
    }
  }
  const s = ctx.createBufferSource(); s.buffer = b; s.start(t);
  k.chain(s, k.f(ftype, f, q), k.g(g), o);
}
// simple tone with attack / decay and optional glide
function tone(k, o, t, type, f0, f1, att, dur, g, lp) {
  const os = k.o(type, f0, t, t + dur + 0.03), a = k.g(0);
  if (f1 !== f0) { os.frequency.setValueAtTime(f0, t); os.frequency.exponentialRampToValueAtTime(f1, t + dur); }
  k.env(a.gain, t, [[0, 0], [att, g], [dur * 0.7, g * 0.7], [dur, 0]]);
  if (lp) k.chain(os, k.f('lowpass', lp, 0.7), a, o); else os.connect(a).connect(o);
  return os;
}
// formant voice: shout / scream / "hah"
function voice(k, o, t, f0, f1, dur, g, F, breath = 0.15, att = 0.04) {
  const os = k.o('sawtooth', f0, t, t + dur + 0.05);
  os.frequency.setValueAtTime(f0, t);
  os.frequency.linearRampToValueAtTime(f1, t + dur * 0.35);
  os.frequency.linearRampToValueAtTime(f0 * 0.85, t + dur);
  const vib = k.o('sine', rnd(4.5, 7.5), t, t + dur + 0.05), vg = k.g(f0 * 0.025); vib.connect(vg).connect(os.frequency);
  const a = k.g(0);
  k.env(a.gain, t, [[0, 0], [att, g], [dur * 0.6, g * 0.75], [dur, 0]]);
  const pre = k.g(1); os.connect(pre);
  const ns = k.n('white', t, t + dur + 0.05), ng = k.g(breath * 0.6); ns.connect(ng).connect(pre);
  F.forEach((ff, i) => { k.chain(pre, k.f('bandpass', ff * rnd(0.93, 1.07), 5 + i * 2), k.g(i === 0 ? 1 : 0.6 / i), a); });
  a.connect(o);
}
const VOW = { ah: [730, 1150, 2500], oh: [520, 900, 2400], eh: [560, 1750, 2500], ee: [320, 2200, 2900], uh: [600, 1050, 2400], aa: [850, 1500, 2700] };
const vowel = () => VOW[pick(['ah', 'oh', 'eh', 'uh', 'aa', 'ah'])];

// brass-like note (horns, stings)
function brass(k, o, t, f, dur, g, bright = 1400, att = 0.12) {
  const mix = k.g(1), lp = k.f('lowpass', 200, 1.2), a = k.g(0);
  [1, 1.004, 0.5].forEach((m, i) => {
    const os = k.o('sawtooth', f * m, t, t + dur + 0.1);
    os.frequency.setValueAtTime(f * m * 0.94, t); os.frequency.linearRampToValueAtTime(f * m, t + att * 0.8);
    os.connect(k.g(i === 2 ? 0.5 : 0.4)).connect(mix);
  });
  lp.frequency.setValueAtTime(180, t); lp.frequency.linearRampToValueAtTime(bright, t + att * 1.6);
  lp.frequency.setTargetAtTime(bright * 0.55, t + att * 2, dur * 0.4);
  k.env(a.gain, t, [[0, 0], [att, g], [dur * 0.75, g * 0.8], [dur, 0]]);
  k.chain(mix, lp, k.f('peaking', 520, 1.2, 5), a, o);
}
// big drum
function drum(k, o, t, f, g, dur = 0.7) {
  sub(k, o, t, f * 1.9, f, dur, g, 0.09);
  nz(k, o, t, 'pink', 'lowpass', 900, 150, 0.7, 0.002, 0.16, g * 0.5);
}

// layered explosion; size ~0.5 small, 1 medium, 2 large
function explosion(k, o, t, size, opts = {}) {
  const s = size, drive = k.shaper(2.5), body = k.g(1);
  body.connect(drive).connect(o);
  // initial crack
  nz(k, o, t, 'white', 'highpass', 1800, 900, 0.5, 0.001, 0.07 + 0.03 * s, 0.9);
  // sub-bass drop
  sub(k, body, t, 95 / Math.sqrt(s) + 25, 26, 0.7 + 0.55 * s, 1.3, 0.28 + 0.16 * s);
  sub(k, body, t + 0.01, 160 / Math.sqrt(s), 42, 0.3 + 0.2 * s, 0.6, 0.1 + 0.05 * s);
  // noise body with closing filter
  nz(k, body, t, 'pink', 'lowpass', 4200, 140, 0.6, 0.004, 0.9 + 0.8 * s, 1.1, 0.5 + 0.5 * s);
  // rolling rumble tail
  const tail = nz(k, o, t + 0.05, 'brown', 'lowpass', 320, 70, 0.5, 0.08, 1.4 + 1.6 * s, 0.9);
  if (s > 1.2) { // secondary rumbles for big ones
    for (let i = 0; i < 4; i++) sub(k, body, t + 0.25 + i * rnd(0.18, 0.4), rnd(55, 80), 30, 0.6, 0.35);
  }
  void tail;
  if (!opts.noDebris) crackle(k, o, t + 0.12, 0.9 + 1.0 * s, 260 + 100 * s, 0.5, 2200, 0.6);
}

// the transient of an explosion only: supersonic crack, mid snap, debris patter
function crackLayer(k, o, t, s) {
  nz(k, o, t, 'white', 'highpass', 2400, 1100, 0.5, 0.0008, 0.05 + 0.03 * s, 1.0);
  nz(k, o, t, 'pink', 'bandpass', rnd(1100, 1600), 520, 0.9, 0.001, 0.08 + 0.05 * s, 0.75);
  crackle(k, o, t + 0.09, 0.5 + 0.7 * s, 240 + 90 * s, 0.4, 2600, 0.6, 'bandpass', 1.4);
}

// ---------------------------------------------------------------- recipes
// name: { d: duration s, n: variants, lvl: playback gain, ref: distance reference m,
//         rev: reverb send, max: max simultaneous voices, gap: min seconds between triggers, fn }
const R = {
  cannon: { d: 0.5, n: 4, lvl: 0.5, ref: 80, rev: 0.25, max: 8, gap: 0.03, fn(k, o, t) {
    nz(k, o, t, 'white', 'highpass', 2400, 1500, 0.6, 0.0008, 0.035, 1.0);
    sub(k, o, t, rnd(150, 175), 48, 0.13, 1.3, 0.05);
    nz(k, o, t, 'pink', 'bandpass', rnd(750, 950), 220, 0.9, 0.001, 0.12, 1.0);
    ping(k, o, t + 0.012, [rnd(1750, 2100), rnd(2700, 3100), 4300], 0.05, 0.13);
    nz(k, o, t + 0.03, 'brown', 'lowpass', 500, 120, 0.6, 0.02, 0.4, 0.35);
  } },
  cannonImpact: { d: 0.6, n: 4, lvl: 0.42, ref: 50, rev: 0.3, max: 8, gap: 0.03, fn(k, o, t) {
    nz(k, o, t, 'white', 'bandpass', rnd(2500, 3600), 900, 0.8, 0.001, 0.06, 0.9);
    sub(k, o, t, rnd(110, 140), 40, 0.2, 1.0, 0.07);
    nz(k, o, t, 'pink', 'lowpass', 1800, 200, 0.6, 0.003, 0.3, 0.8);
    crackle(k, o, t + 0.04, 0.5, 350, 0.45, 3000, 0.7);
  } },
  rocket: { d: 1.5, n: 3, lvl: 0.6, ref: 80, rev: 0.3, max: 6, gap: 0.04, fn(k, o, t) {
    nz(k, o, t, 'white', 'highpass', 1500, 1500, 0.5, 0.002, 0.08, 0.7);
    sub(k, o, t, 120, 45, 0.3, 0.9, 0.12);
    const f = nzSus(k, o, t, 'white', 'bandpass', 900, rnd(2600, 3400), 0.9, 0.03, 0.25, 1.1, 0.9);
    f.Q.setTargetAtTime(2.5, t + 0.2, 0.3);
    nzSus(k, o, t, 'pink', 'lowpass', 700, 250, 0.6, 0.02, 0.2, 0.9, 0.7);
  } },
  missile: { d: 2.4, n: 2, lvl: 0.7, ref: 100, rev: 0.35, max: 4, gap: 0.1, fn(k, o, t) {
    ping(k, o, t, [820, 1370, 2210], 0.08, 0.3);
    sub(k, o, t + 0.03, 130, 38, 0.6, 1.0, 0.25);
    nz(k, o, t + 0.03, 'white', 'highpass', 1200, 1200, 0.5, 0.002, 0.1, 0.8);
    const sh = k.shaper(3), b = k.g(1); b.connect(sh).connect(o);
    nzSus(k, b, t + 0.03, 'pink', 'lowpass', 2800, 500, 0.8, 0.04, 0.5, 1.8, 1.0);
    nzSus(k, o, t + 0.05, 'white', 'bandpass', 1500, 4200, 1.5, 0.05, 0.3, 1.7, 0.45);
  } },
  flare: { d: 1.6, n: 3, lvl: 0.5, ref: 60, rev: 0.2, max: 6, gap: 0.03, fn(k, o, t) {
    sub(k, o, t, 260, 90, 0.09, 0.9, 0.04);
    nz(k, o, t, 'white', 'bandpass', 1800, 900, 1.0, 0.001, 0.07, 1.0);
    nzSus(k, o, t + 0.03, 'white', 'highpass', 5200, 3800, 0.7, 0.03, 0.4, 1.0, 0.3);
    crackle(k, o, t + 0.03, 1.4, 900, 0.5, 6000, 0.8, 'highpass', 0.8);
  } },
  explSmall: { d: 2.2, n: 3, lvl: 0.75, ref: 90, rev: 0.4, max: 8, gap: 0.02, fn(k, o, t) { explosion(k, o, t, 0.5); } },
  explMedium: { d: 3.4, n: 3, lvl: 0.9, ref: 140, rev: 0.45, max: 7, gap: 0.02, fn(k, o, t) { explosion(k, o, t, 1.0); } },
  explLarge: { d: 6.0, n: 2, lvl: 1.1, ref: 240, rev: 0.5, max: 4, gap: 0.05, fn(k, o, t) {
    explosion(k, o, t, 2.0);
    nz(k, o, t + 0.3, 'brown', 'lowpass', 200, 50, 0.5, 0.4, 5.4, 2.2);
  } },
  // crack-only layers laid over the generated explosion samples (the samples carry the body and the bass)
  crackS: { d: 1.0, n: 3, lvl: 0.42, ref: 90, rev: 0.35, max: 8, gap: 0.02, fn(k, o, t) { crackLayer(k, o, t, 0.5); } },
  crackM: { d: 1.5, n: 3, lvl: 0.5, ref: 140, rev: 0.4, max: 7, gap: 0.02, fn(k, o, t) { crackLayer(k, o, t, 1.0); } },
  crackL: { d: 2.2, n: 2, lvl: 0.55, ref: 240, rev: 0.45, max: 4, gap: 0.05, fn(k, o, t) { crackLayer(k, o, t, 2.0); } },
  collapse: { d: 4.8, n: 2, lvl: 1.0, ref: 200, rev: 0.45, max: 3, gap: 0.2, fn(k, o, t) {
    const sh = k.shaper(2), b = k.g(1); b.connect(sh).connect(o);
    const f = nzSus(k, b, t, 'brown', 'lowpass', 160, 420, 0.6, 0.5, 2.0, 2.2, 1.3); void f;
    nzSus(k, b, t + 0.2, 'pink', 'bandpass', 500, 260, 0.7, 0.6, 1.4, 2.4, 0.5);
    for (let i = 0; i < 26; i++) { // cascade of block impacts, densest in the middle
      const tt = t + 0.15 + Math.pow(Math.random(), 0.8) * 3.6, s = rnd(0.3, 1);
      sub(k, b, tt, rnd(70, 150), rnd(30, 50), 0.18 + 0.3 * s, 0.6 * s, 0.06);
      nz(k, o, tt, 'pink', 'bandpass', rnd(500, 1800), 300, 0.8, 0.002, 0.08 + 0.1 * s, 0.35 * s);
    }
    crackle(k, o, t + 0.2, 4.4, 520, 0.55, 1800, 0.5, 'bandpass', 0.6);
  } },
  debris: { d: 1.6, n: 3, lvl: 0.45, ref: 50, rev: 0.3, max: 5, gap: 0.05, fn(k, o, t) {
    crackle(k, o, t, 1.5, 420, 0.9, 1700, 0.6, 'bandpass', 1.2);
    for (let i = 0; i < 7; i++) { const tt = t + Math.random() * 1.0; ping(k, o, tt, [rnd(380, 900), rnd(1100, 2400)], 0.05, 0.22, 'triangle'); sub(k, o, tt, rnd(120, 200), 70, 0.07, 0.3, 0.03); }
  } },
  arrowHit: { d: 0.3, n: 6, lvl: 0.4, max: 6, gap: 0.02, fn(k, o, t) {
    const f = rnd(700, 1500);
    nz(k, o, t, 'white', 'bandpass', rnd(2500, 4500), 1500, 1.5, 0.0008, 0.025, 0.9);
    ping(k, o, t, [f, f * 2.31, f * 3.87, f * 5.2], rnd(0.1, 0.24), 0.5);
    sub(k, o, t, rnd(180, 260), 110, 0.05, 0.5, 0.02);
    if (Math.random() < 0.5) ping(k, o, t + rnd(0.03, 0.09), [f * 1.4, f * 3.1], 0.05, 0.2); // skitter
    ping(k, o, t + 0.004, [rnd(240, 330)], 0.09, 0.25, 'triangle'); // shaft thrum
  } },
  arrowWhoosh: { d: 1.3, n: 3, lvl: 0.45, max: 3, gap: 0.2, fn(k, o, t) {
    for (let i = 0; i < 14; i++) {
      const tt = t + Math.random() * 0.8, s = k.n('white', tt, tt + 0.3), f = k.f('bandpass', rnd(2500, 5000), 6), a = k.g(0);
      f.frequency.setValueAtTime(f.frequency.value, tt); f.frequency.exponentialRampToValueAtTime(rnd(900, 1800), tt + 0.25);
      k.env(a.gain, tt, [[0, 0], [0.09, rnd(0.2, 0.6)], [0.25, 0]]);
      s.connect(f).connect(a).connect(o);
    }
  } },
  volleyLoose: { d: 3.0, n: 2, lvl: 0.7, ref: 120, rev: 0.3, max: 4, gap: 0.2, fn(k, o, t) {
    for (let i = 0; i < 46; i++) { // bowstrings: thrum + slap
      const tt = t + Math.pow(Math.random(), 1.6) * 0.5, f = rnd(110, 210);
      ping(k, o, tt, [f, f * 2.02], rnd(0.06, 0.12), 0.12, 'triangle');
      if (i % 3 === 0) nz(k, o, tt, 'white', 'bandpass', rnd(1800, 3200), 1200, 2, 0.001, 0.02, 0.2);
    }
    // massed whistle of shafts rising then fading away
    const f = nzSus(k, o, t + 0.1, 'white', 'bandpass', 2200, 4200, 2.2, 0.5, 0.8, 1.5, 0.5); void f;
    nzSus(k, o, t + 0.1, 'pink', 'bandpass', 900, 1500, 1.0, 0.4, 0.8, 1.5, 0.3);
  } },
  horn: { d: 2.6, n: 2, lvl: 0.7, ref: 250, rev: 0.6, max: 3, gap: 0.3, fn(k, o, t) {
    const f = pick([110, 116.5, 123.5]);
    brass(k, o, t, f, 0.5, 0.7, 1100, 0.1);
    brass(k, o, t + 0.55, f * 1.498, 1.9, 0.9, 1500, 0.16);
    nzSus(k, o, t, 'pink', 'bandpass', 600, 600, 2, 0.1, 2.0, 0.3, 0.05);
  } },
  hornRout: { d: 3.0, n: 2, lvl: 0.7, ref: 250, rev: 0.6, max: 2, gap: 0.5, fn(k, o, t) {
    const mix = k.g(1), lp = k.f('lowpass', 1300, 1.5), a = k.g(0);
    [1, 1.007, 0.5].forEach((m) => {
      const os = k.o('sawtooth', 165 * m, t, t + 2.9);
      os.frequency.setValueAtTime(165 * m, t); os.frequency.linearRampToValueAtTime(160 * m, t + 0.8);
      os.frequency.exponentialRampToValueAtTime(92 * m, t + 2.6);
      const wob = k.o('sine', 7, t, t + 2.9), wg = k.g(0); wg.gain.setValueAtTime(0, t); wg.gain.linearRampToValueAtTime(9, t + 2.4);
      wob.connect(wg).connect(os.frequency); os.connect(k.g(0.4)).connect(mix);
    });
    lp.frequency.setValueAtTime(1500, t); lp.frequency.exponentialRampToValueAtTime(380, t + 2.7);
    k.env(a.gain, t, [[0, 0], [0.1, 0.9], [1.3, 0.8], [1.45, 0.25], [1.6, 0.7], [2.2, 0.4], [2.3, 0.12], [2.45, 0.3], [2.8, 0]]);
    k.chain(mix, lp, k.f('peaking', 520, 1.2, 5), a, o);
  } },
  boltFire: { d: 0.9, n: 3, lvl: 0.7, ref: 110, rev: 0.4, max: 4, gap: 0.05, fn(k, o, t) {
    sub(k, o, t, 170, 55, 0.22, 1.1, 0.07);
    nz(k, o, t, 'white', 'bandpass', 1500, 600, 1.2, 0.001, 0.05, 0.9);
    ping(k, o, t, [rnd(190, 230), 410, 655, 980], 0.4, 0.45, 'triangle'); // timber frame ring
    ping(k, o, t + 0.01, [88, 176], 0.5, 0.4, 'sawtooth');                // rope twang
    nz(k, o, t + 0.02, 'white', 'bandpass', 3000, 1200, 2, 0.02, 0.3, 0.25);
  } },
  boltPass: { d: 0.5, n: 3, lvl: 0.75, max: 3, gap: 0.05, fn(k, o, t) {
    const s = k.n('white', t, t + 0.45), f = k.f('bandpass', 600, 3), a = k.g(0);
    f.frequency.setValueAtTime(700, t); f.frequency.exponentialRampToValueAtTime(5200, t + 0.11); f.frequency.exponentialRampToValueAtTime(500, t + 0.4);
    k.env(a.gain, t, [[0, 0], [0.1, 1], [0.14, 0.5], [0.42, 0]]);
    s.connect(f).connect(a).connect(o);
    nz(k, o, t + 0.105, 'white', 'highpass', 3000, 3000, 0.7, 0.0005, 0.03, 1.0); // crack
    sub(k, o, t + 0.105, 220, 80, 0.08, 0.5, 0.03);
  } },
  boltHit: { d: 1.2, n: 3, lvl: 0.95, max: 3, gap: 0.05, fn(k, o, t) {
    const f = rnd(190, 240);
    sub(k, o, t, 150, 42, 0.35, 1.3, 0.1);
    nz(k, o, t, 'white', 'bandpass', 2200, 500, 0.8, 0.001, 0.09, 1.0);
    ping(k, o, t, [f, f * 2.76, f * 5.4, f * 8.93, f * 11.3], 1.0, 0.4);
    ping(k, o, t + 0.002, [f * 1.51, f * 3.9], 0.5, 0.25, 'square');
    crackle(k, o, t + 0.05, 0.6, 300, 0.35, 4000, 0.8);
  } },
  bombardFire: { d: 3.6, n: 2, lvl: 1.0, ref: 220, rev: 0.55, max: 4, gap: 0.1, fn(k, o, t) {
    const sh = k.shaper(3), b = k.g(1); b.connect(sh).connect(o);
    nz(k, o, t, 'white', 'highpass', 1200, 800, 0.5, 0.001, 0.09, 0.7);
    sub(k, b, t, 105, 24, 1.5, 1.4, 0.4);
    sub(k, b, t + 0.02, 62, 30, 1.0, 0.8, 0.3);
    nz(k, b, t, 'pink', 'lowpass', 2600, 110, 0.6, 0.005, 1.5, 1.0, 0.7);
    nz(k, o, t + 0.1, 'brown', 'lowpass', 260, 60, 0.5, 0.15, 3.2, 0.8);
    nzSus(k, o, t + 0.05, 'white', 'bandpass', 3500, 1800, 0.8, 0.05, 0.3, 1.2, 0.12); // powder hiss
  } },
  flak: { d: 1.8, n: 3, lvl: 0.95, ref: 130, rev: 0.45, max: 6, gap: 0.03, fn(k, o, t) {
    nz(k, o, t, 'white', 'highpass', 1500, 700, 0.5, 0.0006, 0.08, 1.2);
    sub(k, o, t, 180, 45, 0.3, 1.1, 0.08);
    nz(k, o, t, 'pink', 'bandpass', 900, 250, 0.7, 0.002, 0.5, 0.9);
    nz(k, o, t + 0.04, 'brown', 'lowpass', 300, 80, 0.5, 0.05, 1.5, 0.5);
    crackle(k, o, t + 0.03, 1.2, 800, 0.6, 3800, 0.7, 'bandpass', 2.0); // shrapnel rattle
  } },
  trebRelease: { d: 2.2, n: 2, lvl: 0.75, ref: 160, rev: 0.4, max: 3, gap: 0.2, fn(k, o, t) {
    // timber creak: slow sawtooth stick-slip through wooden resonances
    const os = k.o('sawtooth', 38, t, t + 0.9), a = k.g(0);
    os.frequency.setValueAtTime(30, t); os.frequency.linearRampToValueAtTime(64, t + 0.5); os.frequency.linearRampToValueAtTime(44, t + 0.85);
    k.env(a.gain, t, [[0, 0], [0.08, 0.7], [0.7, 0.6], [0.9, 0]]);
    [rnd(520, 640), rnd(980, 1200), 1900].forEach((f) => k.chain(os, k.f('bandpass', f, 9), a));
    a.connect(o);
    // whump of the counterweight + arm swish
    sub(k, o, t + 0.75, 85, 28, 0.9, 1.3, 0.3);
    nz(k, o, t + 0.75, 'pink', 'lowpass', 700, 120, 0.6, 0.01, 0.5, 0.8);
    const f = nzSus(k, o, t + 0.45, 'white', 'bandpass', 500, 2400, 1.5, 0.3, 0.1, 0.5, 0.45); void f;
    ping(k, o, t + 0.78, [140, 310, 470], 0.5, 0.3, 'triangle');
  } },
  boulderWhoosh: { d: 2.6, n: 2, lvl: 0.8, max: 2, gap: 0.3, fn(k, o, t) {
    const sh = k.shaper(2), b = k.g(0); b.connect(sh).connect(o);
    k.env(b.gain, t, [[0, 0], [1.3, 1], [1.5, 0.8], [2.5, 0]]);
    const s = k.n('pink', t, t + 2.6), f = k.f('bandpass', 300, 1.2);
    f.frequency.setValueAtTime(260, t); f.frequency.exponentialRampToValueAtTime(1300, t + 1.35); f.frequency.exponentialRampToValueAtTime(220, t + 2.5);
    s.connect(f).connect(b);
    const s2 = k.n('brown', t, t + 2.6), f2 = k.f('lowpass', 240, 0.7), am = k.g(0.6), lfo = k.o('sawtooth', 17, t, t + 2.6), lg = k.g(0.4);
    lfo.connect(lg).connect(am.gain); s2.connect(f2).connect(am).connect(b); // fluttering flame roar
    crackle(k, b, t, 2.5, 500, 0.4, 3500, 0.7, 'bandpass', 0.1);
  } },
  boulderImpact: { d: 3.2, n: 2, lvl: 1.0, ref: 170, rev: 0.45, max: 3, gap: 0.1, fn(k, o, t) {
    const sh = k.shaper(2.5), b = k.g(1); b.connect(sh).connect(o);
    sub(k, b, t, 90, 24, 1.3, 1.5, 0.3);
    nz(k, b, t, 'pink', 'lowpass', 2200, 120, 0.6, 0.004, 1.0, 1.0, 0.5);
    nz(k, o, t, 'white', 'bandpass', 1400, 500, 0.7, 0.002, 0.12, 0.6);
    nz(k, o, t + 0.1, 'brown', 'lowpass', 240, 60, 0.5, 0.1, 2.6, 0.7);
    crackle(k, o, t + 0.1, 2.4, 420, 0.55, 1600, 0.5, 'bandpass', 1.4);
    nzSus(k, o, t + 0.05, 'white', 'highpass', 3000, 2000, 0.6, 0.1, 0.4, 1.4, 0.1); // fire splash
  } },
  hullHit: { d: 0.7, n: 4, lvl: 0.8, max: 5, gap: 0.03, fn(k, o, t) {
    const f = rnd(130, 190);
    sub(k, o, t, 140, 45, 0.25, 1.2, 0.08);
    nz(k, o, t, 'pink', 'bandpass', 1300, 300, 0.8, 0.001, 0.1, 0.9);
    ping(k, o, t, [f, f * 2.4, f * 4.1, f * 6.6], 0.45, 0.3);
    crackle(k, o, t + 0.03, 0.3, 240, 0.25, 3500, 0.8);
  } },
  glassCrack: { d: 0.8, n: 3, lvl: 0.6, max: 3, gap: 0.05, fn(k, o, t) {
    nz(k, o, t, 'white', 'highpass', 4000, 3000, 0.6, 0.0005, 0.03, 1.0);
    ping(k, o, t, [rnd(2600, 3400), rnd(4200, 5200), rnd(6100, 7400), 8800], 0.2, 0.3);
    crackle(k, o, t + 0.01, 0.7, 700, 0.7, 6500, 1.2, 'bandpass', 2.5);
    sub(k, o, t, 300, 150, 0.04, 0.4, 0.02);
  } },
  jam: { d: 0.6, n: 2, lvl: 0.6, max: 2, gap: 0.1, fn(k, o, t) {
    ping(k, o, t, [310, 742, 1210, 1890], 0.12, 0.5, 'square');
    sub(k, o, t, 130, 70, 0.1, 0.9, 0.04);
    nz(k, o, t, 'white', 'bandpass', 2400, 900, 1, 0.001, 0.04, 0.6);
    ping(k, o, t + 0.16, [260, 610, 1400], 0.09, 0.35, 'square');
    nz(k, o, t + 0.16, 'white', 'bandpass', 1500, 700, 1, 0.001, 0.05, 0.4);
    const s = k.n('white', t + 0.22, t + 0.55), f = k.f('bandpass', 900, 8), a = k.g(0); // grinding wind-down
    f.frequency.setValueAtTime(1100, t + 0.22); f.frequency.exponentialRampToValueAtTime(260, t + 0.55);
    k.env(a.gain, t + 0.22, [[0, 0], [0.02, 0.5], [0.33, 0]]); s.connect(f).connect(a).connect(o);
  } },
  overheat: { d: 0.6, n: 1, lvl: 0.36, max: 1, gap: 0.5, fn(k, o, t) { R.jam.fn(k, o, t); } },
  dryFire: { d: 0.16, n: 2, lvl: 0.35, max: 2, gap: 0.08, fn(k, o, t) {
    nz(k, o, t, 'white', 'bandpass', 3200, 2000, 2, 0.0005, 0.018, 1.0);
    ping(k, o, t, [1900, 3100, 4700], 0.03, 0.3);
    ping(k, o, t + 0.035, [1300, 2500], 0.025, 0.2);
  } },
  weaponSwitch: { d: 0.3, n: 2, lvl: 0.35, max: 2, gap: 0.05, fn(k, o, t) {
    nz(k, o, t, 'white', 'bandpass', 2600, 1500, 2, 0.0005, 0.02, 0.8);
    ping(k, o, t, [820, 1640, 2900], 0.05, 0.3, 'square');
    sub(k, o, t + 0.07, 200, 90, 0.06, 0.6, 0.03);
    ping(k, o, t + 0.07, [560, 1320, 2300], 0.07, 0.35, 'square');
    tone(k, o, t + 0.12, 'sine', 1250, 1250, 0.004, 0.07, 0.12);
  } },
  lockOn: { d: 0.4, n: 1, lvl: 0.3, max: 2, gap: 0.1, fn(k, o, t) {
    tone(k, o, t, 'square', 1480, 1480, 0.003, 0.07, 0.3, 5000);
    tone(k, o, t + 0.09, 'square', 1975, 1975, 0.003, 0.22, 0.3, 6000);
    tone(k, o, t + 0.09, 'sine', 2960, 2960, 0.003, 0.22, 0.12);
  } },
  scream: { d: 1.4, n: 5, lvl: 0.55, ref: 60, rev: 0.4, max: 5, gap: 0.08, fn(k, o, t) {
    const n = 4 + ((Math.random() * 4) | 0);
    for (let i = 0; i < n; i++) {
      const f = rnd(170, 430), d = rnd(0.35, 0.95);
      voice(k, o, t + Math.random() * 0.4, f, f * rnd(1.15, 1.6), d, rnd(0.4, 1), vowel(), 0.3, 0.03);
    }
  } },
  cheer: { d: 2.6, n: 2, lvl: 0.7, ref: 150, rev: 0.45, max: 3, gap: 0.2, fn(k, o, t) {
    nzSus(k, o, t, 'pink', 'bandpass', 800, 1300, 0.7, 0.35, 1.1, 1.1, 0.5);
    for (let i = 0; i < 18; i++) {
      const f = rnd(110, 290), d = rnd(0.5, 1.4);
      voice(k, o, t + Math.random() * 1.0, f, f * rnd(1.1, 1.45), d, rnd(0.25, 0.7), pick([VOW.ah, VOW.aa, VOW.eh]), 0.25, 0.08);
    }
  } },
  rearmTick: { d: 0.3, n: 4, lvl: 0.45, max: 3, gap: 0.04, fn(k, o, t) {
    const f = rnd(420, 700);
    for (let i = 0; i < 3; i++) { const tt = t + i * rnd(0.028, 0.04); nz(k, o, tt, 'white', 'bandpass', rnd(2400, 3600), 1500, 3, 0.0005, 0.012, 0.6); ping(k, o, tt, [f * (1 + i * 0.1), f * 2.7], 0.02, 0.2, 'square'); }
    sub(k, o, t + 0.12, 150, 70, 0.1, 0.9, 0.04);
    ping(k, o, t + 0.12, [f * 0.6, f * 1.9, f * 3.3], 0.12, 0.4);
  } },
  repairDone: { d: 0.9, n: 2, lvl: 0.45, max: 2, gap: 0.2, fn(k, o, t) {
    for (let i = 0; i < 5; i++) { const tt = t + i * 0.05; nz(k, o, tt, 'white', 'bandpass', 3000, 1800, 3, 0.0005, 0.015, 0.5); ping(k, o, tt, [900 + i * 60, 2300], 0.02, 0.18, 'square'); }
    ping(k, o, t + 0.3, [620, 1480, 2750, 4100], 0.25, 0.3);
    tone(k, o, t + 0.5, 'sine', 1320, 1320, 0.004, 0.09, 0.25);
    tone(k, o, t + 0.62, 'sine', 1760, 1760, 0.004, 0.2, 0.25);
  } },
  touchdown: { d: 0.9, n: 3, lvl: 0.7, max: 2, gap: 0.2, fn(k, o, t) {
    sub(k, o, t, 95, 34, 0.4, 1.3, 0.12);
    nz(k, o, t, 'pink', 'lowpass', 900, 150, 0.6, 0.004, 0.25, 0.7);
    ping(k, o, t + 0.01, [rnd(150, 190), 420, 760], 0.3, 0.2);
    const s = k.n('white', t, t + 0.8), f = k.f('bandpass', 1900, 12), a = k.g(0); // strut squeak
    k.env(a.gain, t + 0.05, [[0, 0], [0.05, 0.12], [0.6, 0]]);
    f.frequency.setValueAtTime(2300, t); f.frequency.linearRampToValueAtTime(1500, t + 0.6);
    s.connect(f).connect(a).connect(o);
  } },
  uiHover: { d: 0.08, n: 1, lvl: 0.16, max: 2, gap: 0.03, fn(k, o, t) {
    tone(k, o, t, 'sine', 2100, 2300, 0.002, 0.045, 0.6);
    nz(k, o, t, 'white', 'bandpass', 5000, 5000, 3, 0.0005, 0.012, 0.3);
  } },
  uiClick: { d: 0.22, n: 1, lvl: 0.3, max: 2, gap: 0.03, fn(k, o, t) {
    nz(k, o, t, 'white', 'bandpass', 2800, 1800, 2, 0.0005, 0.015, 0.7);
    sub(k, o, t, 190, 110, 0.07, 0.8, 0.03);
    tone(k, o, t + 0.01, 'triangle', 880, 880, 0.003, 0.06, 0.4);
    tone(k, o, t + 0.06, 'triangle', 1320, 1320, 0.003, 0.12, 0.35);
  } },
  uiBack: { d: 0.2, n: 1, lvl: 0.26, max: 2, gap: 0.03, fn(k, o, t) {
    nz(k, o, t, 'white', 'bandpass', 2400, 1500, 2, 0.0005, 0.015, 0.6);
    tone(k, o, t + 0.01, 'triangle', 1320, 1320, 0.003, 0.06, 0.35);
    tone(k, o, t + 0.06, 'triangle', 880, 880, 0.003, 0.12, 0.35);
  } },
  phase: { d: 4.2, n: 1, lvl: 0.85, max: 1, gap: 1, fn(k, o, t) {
    drum(k, o, t, 46, 1.3, 1.2); drum(k, o, t + 0.55, 41, 1.0, 1.4);
    [73.42, 110, 146.83, 174.61].forEach((f, i) => brass(k, o, t + 0.02 + i * 0.03, f, 3.6, 0.5 - i * 0.06, 1500, 0.5));
    nzSus(k, o, t, 'pink', 'bandpass', 300, 2400, 0.8, 0.6, 0.1, 0.5, 0.15); // riser
    nz(k, o, t + 0.55, 'white', 'highpass', 4500, 2500, 0.5, 0.01, 2.2, 0.12); // cymbal wash
  } },
  warning: { d: 0.7, n: 1, lvl: 0.35, max: 2, gap: 0.2, fn(k, o, t) {
    [0, 0.16].forEach((dt, i) => { tone(k, o, t + dt, 'triangle', i ? 1175 : 880, i ? 1175 : 880, 0.004, i ? 0.45 : 0.14, 0.5); tone(k, o, t + dt, 'sine', (i ? 1175 : 880) * 2, (i ? 1175 : 880) * 2, 0.004, i ? 0.3 : 0.1, 0.15); });
  } },
  crashSpin: { d: 2.6, n: 1, lvl: 0.6, max: 1, gap: 1, fn(k, o, t) {
    const os = k.o('sawtooth', 300, t, t + 2.6), lfo = k.o('sine', 5, t, t + 2.6), lg = k.g(60), a = k.g(0);
    os.frequency.setValueAtTime(260, t); os.frequency.linearRampToValueAtTime(520, t + 2.5);
    lfo.frequency.setValueAtTime(3, t); lfo.frequency.linearRampToValueAtTime(9, t + 2.5); lfo.connect(lg).connect(os.frequency);
    k.env(a.gain, t, [[0, 0], [0.3, 0.3], [2.3, 0.5], [2.6, 0]]);
    k.chain(os, k.f('bandpass', 1400, 1.5), a, o);
    const f = nzSus(k, o, t, 'pink', 'bandpass', 500, 1600, 1.2, 0.5, 1.6, 0.4, 0.5); void f;
    crackle(k, o, t, 2.5, 300, 0.4, 3000, 1, 'bandpass', 0.05);
  } },
  crash: { d: 7.0, n: 2, lvl: 1.15, max: 1, gap: 1, fn(k, o, t) {
    // metal crunch
    nz(k, o, t, 'white', 'bandpass', 2600, 500, 0.6, 0.001, 0.3, 1.0);
    const f = rnd(140, 180); ping(k, o, t, [f, f * 2.76, f * 5.4, f * 8.9, f * 13.3], 1.6, 0.35);
    for (let i = 0; i < 9; i++) { const tt = t + Math.random() * 0.7; ping(k, o, tt, [rnd(300, 900), rnd(1200, 3200)], rnd(0.1, 0.4), 0.2, 'square'); nz(k, o, tt, 'white', 'bandpass', rnd(1500, 4000), 800, 1.5, 0.001, 0.08, 0.4); }
    sub(k, o, t, 120, 30, 0.7, 1.3, 0.2);
    // fireball
    explosion(k, o, t + 0.28, 2.0);
    const sh = k.shaper(2), b = k.g(1); b.connect(sh).connect(o);
    nzSus(k, b, t + 0.3, 'brown', 'lowpass', 500, 140, 0.6, 0.3, 2.5, 3.6, 1.0);
    // burning tail
    crackle(k, o, t + 0.8, 6.0, 380, 0.35, 2800, 0.7, 'bandpass', 0.6);
    nzSus(k, o, t + 0.6, 'pink', 'bandpass', 700, 450, 0.7, 0.8, 2.5, 2.8, 0.25);
  } },
  win: { d: 5.0, n: 1, lvl: 0.8, max: 1, gap: 1, fn(k, o, t) {
    const seq = [[0, 146.83, 0.35], [0.32, 220, 0.35], [0.64, 293.66, 0.5], [1.1, 369.99, 3.4]];
    seq.forEach(([dt, f, d]) => { brass(k, o, t + dt, f, d, 0.6, 2200, 0.06); brass(k, o, t + dt, f / 2, d, 0.35, 1200, 0.08); });
    [146.83, 220, 293.66].forEach((f) => brass(k, o, t + 1.1, f, 3.4, 0.3, 1700, 0.25));
    drum(k, o, t, 55, 1.0, 0.8); drum(k, o, t + 0.64, 55, 0.9, 0.8); drum(k, o, t + 1.1, 46, 1.3, 1.6);
    nz(k, o, t + 1.1, 'white', 'highpass', 5000, 3000, 0.5, 0.01, 2.8, 0.14);
  } },
  lose: { d: 5.0, n: 1, lvl: 0.8, max: 1, gap: 1, fn(k, o, t) {
    const seq = [[0, 146.83, 0.9], [0.85, 138.59, 0.9], [1.7, 110, 1.0], [2.6, 73.42, 2.3]];
    seq.forEach(([dt, f, d]) => { brass(k, o, t + dt, f, d, 0.6, 800, 0.2); brass(k, o, t + dt, f * 1.189, d, 0.25, 700, 0.25); });
    drum(k, o, t, 42, 1.2, 1.4); drum(k, o, t + 2.6, 36, 1.3, 2.2);
    nzSus(k, o, t, 'brown', 'lowpass', 200, 90, 0.6, 1.0, 2.5, 1.4, 0.4);
  } },
  rotorStrike: { d: 1.5, n: 2, lvl: 1.05, max: 2, gap: 0.2, fn(k, o, t) {
    for (let i = 0; i < 4; i++) { // successive blades shattering
      const tt = t + i * rnd(0.045, 0.06), f = rnd(380, 620), g = 1 - i * 0.17;
      nz(k, o, tt, 'white', 'highpass', 2000, 1200, 0.6, 0.0005, 0.06, 1.1 * g);
      ping(k, o, tt, [f, f * 2.9, f * 5.3, f * 8.1, f * 12.2], 0.7, 0.35 * g);
      ping(k, o, tt, [f * 1.7, f * 4.4], 0.3, 0.22 * g, 'square');
      sub(k, o, tt, 190, 50, 0.2, 0.9 * g, 0.06);
    }
    crackle(k, o, t + 0.05, 1.3, 900, 0.6, 3800, 0.6, 'bandpass', 1.5);
    nz(k, o, t + 0.05, 'pink', 'lowpass', 1500, 200, 0.6, 0.02, 0.9, 0.5);
  } },
  // internal alert blips
  _lockBeep: { d: 0.09, n: 1, lvl: 0.22, max: 3, gap: 0.03, fn(k, o, t) { tone(k, o, t, 'square', 1480, 1480, 0.002, 0.055, 0.6, 5000); } },
  _bndSlow: { d: 0.5, n: 1, lvl: 0.3, max: 2, gap: 0.2, fn(k, o, t) { tone(k, o, t, 'triangle', 660, 660, 0.01, 0.4, 0.6); tone(k, o, t, 'sine', 1320, 1320, 0.01, 0.3, 0.15); } },
  _bndFast: { d: 0.34, n: 1, lvl: 0.4, max: 2, gap: 0.1, fn(k, o, t) { tone(k, o, t, 'square', 1040, 1040, 0.004, 0.13, 0.5, 4500); tone(k, o, t + 0.15, 'square', 780, 780, 0.004, 0.15, 0.5, 4500); } },
  _tick: { d: 0.08, n: 4, lvl: 0.25, max: 3, gap: 0.03, fn(k, o, t) { const f = rnd(2600, 4200); ping(k, o, t, [f, f * 1.83], 0.05, 0.6); nz(k, o, t, 'white', 'highpass', 5000, 5000, 1, 0.0005, 0.008, 0.5); } },
};

// loop beds rendered offline (loopable by folding the tail back onto the head)
const LOOPS = {
  _crowd: { d: 9, tail: 1.2, fn(k, o, t, L) {
    const am = k.g(0.5), lfo = k.n('brown', t, undefined, 0.012), lg = k.g(1.4); lfo.connect(lg).connect(am.gain);
    const src = k.n('pink', t);
    [[430, 1.6, 1], [760, 2, 0.8], [1250, 2.5, 0.45], [2300, 3, 0.15]].forEach(([f, q, g]) => k.chain(src, k.f('bandpass', f, q), k.g(g * 0.45), am));
    am.connect(o);
    for (let i = 0; i < 44; i++) {
      const tt = t + Math.random() * L, f = rnd(95, 190), d = rnd(0.2, 0.9);
      voice(k, o, tt, f, f * rnd(1.0, 1.3), d, rnd(0.08, 0.3), vowel(), 0.2, 0.04);
    }
    for (let i = 0; i < 5; i++) { // massed battle-cry "HAH!"
      const tt = t + ((i + Math.random() * 0.5) / 5) * L;
      for (let j = 0; j < 7; j++) { const f = rnd(100, 170); voice(k, o, tt + Math.random() * 0.12, f, f * 1.2, rnd(0.25, 0.4), 0.2, VOW.ah, 0.3, 0.02); }
    }
  } },
  _panic: { d: 7, tail: 1.2, fn(k, o, t, L) {
    const src = k.n('pink', t);
    [[700, 1.5, 0.6], [1400, 2, 0.5], [2600, 2.5, 0.25]].forEach(([f, q, g]) => k.chain(src, k.f('bandpass', f, q), k.g(g * 0.3), o));
    for (let i = 0; i < 46; i++) {
      const tt = t + Math.random() * L, f = rnd(190, 520), d = rnd(0.3, 1.1);
      voice(k, o, tt, f, f * rnd(1.2, 1.8), d, rnd(0.1, 0.4), pick([VOW.ah, VOW.aa, VOW.eh, VOW.ee]), 0.35, 0.03);
    }
  } },
  _cheer: { d: 6, tail: 1.2, fn(k, o, t, L) {
    const am = k.g(0.6), lfo = k.n('brown', t, undefined, 0.02), lg = k.g(1.2); lfo.connect(lg).connect(am.gain);
    const src = k.n('pink', t);
    [[650, 1.0, 0.8], [1100, 1.3, 0.7], [2000, 1.6, 0.35]].forEach(([f, q, g]) => k.chain(src, k.f('bandpass', f, q), k.g(g * 0.5), am));
    am.connect(o);
    for (let i = 0; i < 50; i++) {
      const tt = t + Math.random() * L, f = rnd(110, 300), d = rnd(0.5, 1.5);
      voice(k, o, tt, f, f * rnd(1.15, 1.5), d, rnd(0.1, 0.32), pick([VOW.ah, VOW.aa, VOW.eh]), 0.25, 0.1);
    }
  } },
  _drums: { d: 5, tail: 1.0, fold: true, fn(k, o, t, L) {
    const beat = L / 8;
    [0, 1.5, 2, 3, 4, 5.5, 6, 6.5, 7].forEach((b, i) => {
      const acc = (b === 0 || b === 4) ? 1 : 0.65;
      for (let j = 0; j < 3; j++) drum(k, o, t + b * beat + j * rnd(0.004, 0.022), rnd(50, 62) * (j === 2 ? 1.3 : 1), acc * 0.5, 0.55);
      void i;
    });
  } },
  _fire: { d: 5, tail: 0.5, fn(k, o, t, L) {
    const am = k.g(0.6), lfo = k.n('brown', t, undefined, 0.05), lg = k.g(1.0); lfo.connect(lg).connect(am.gain);
    k.chain(k.n('brown', t), k.f('lowpass', 420, 0.5), am); k.chain(k.n('pink', t), k.f('bandpass', 1100, 0.6), k.g(0.25), am);
    am.connect(o);
    const len = Math.ceil((L + 0.4) * SR), b = newBuffer(1, len, SR), d = b.getChannelData(0);
    for (let i = 0; i < len; i++) if (Math.random() < 34 / SR) { const a = Math.pow(Math.random(), 2.5) * 2, n = 20 + ((Math.random() * 180) | 0); for (let j = 0; j < n && i + j < len; j++) d[i + j] += a * Math.exp(-j / (n * 0.25)) * (Math.random() * 2 - 1); }
    const s = k.ctx.createBufferSource(); s.buffer = b; s.start(t);
    k.chain(s, k.f('highpass', 900, 0.7), k.g(1.3), o);
  } },
};

// --------------------------------------------------------- offline render
function finalize(buf, peakTarget, fadeOut = 0.03) {
  const d = buf.getChannelData(0), n = d.length;
  let mean = 0, peak = 0;
  for (let i = 0; i < n; i++) { if (!isFinite(d[i])) d[i] = 0; mean += d[i]; }
  mean /= n;
  for (let i = 0; i < n; i++) { d[i] -= mean; const a = Math.abs(d[i]); if (a > peak) peak = a; }
  const g = peak > 1e-5 ? peakTarget / peak : 0, fo = Math.min(n, (fadeOut * SR) | 0);
  for (let i = 0; i < n; i++) d[i] *= g;
  for (let i = 0; i < fo; i++) d[n - 1 - i] *= i / fo;
  return buf;
}
async function renderOne(name) {
  const r = R[name]; if (!r || !OfflineCtx) return null;
  ensureNoise();
  const ctx = new OfflineCtx(1, Math.ceil((r.d + 0.05) * SR), SR);
  const k = kit(ctx), out = k.g(1); out.connect(ctx.destination);
  r.fn(k, out, 0.004);
  return finalize(await ctx.startRendering(), 0.9);
}
async function renderLoop(name) {
  const r = LOOPS[name]; if (!r || !OfflineCtx) return null;
  ensureNoise();
  const L = r.d, n = Math.round(L * SR), nt = Math.round(r.tail * SR);
  const ctx = new OfflineCtx(1, n + nt, SR), k = kit(ctx), out = k.g(1), fade = k.g(1);
  // continuous (noise) layers must not be doubled by the fold: crossfade them via a master ramp instead
  out.connect(fade).connect(ctx.destination);
  r.fn(k, out, 0, L);
  const res = await ctx.startRendering(), src = res.getChannelData(0);
  const buf = newBuffer(1, n, SR), d = buf.getChannelData(0);
  // equal-power crossfade of tail into head (events + beds wrap smoothly)
  for (let i = 0; i < n; i++) d[i] = src[i];
  for (let i = 0; i < nt; i++) { const x = i / nt; d[i] = r.fold ? src[i] + src[n + i] : src[i] * Math.sin(x * Math.PI / 2) + src[n + i] * Math.cos(x * Math.PI / 2); }
  return finalize(buf, 0.9, 0);
}

// JS-synthesised rotor loops (one buffer = 2 revolutions of 4 blades at 20 Hz blade-pass)
function makeRotor(kind) {
  const bpf = 20, pulses = 8, n = Math.round(SR * pulses / bpf), b = newBuffer(1, n, SR), d = b.getChannelData(0);
  const amps = kind === 'dmg' ? [1.35, 0.4, 1.1, 0.7] : [1, 0.9, 1.06, 0.95];
  for (let p = 0; p < pulses; p++) {
    const jit = kind === 'dmg' ? (Math.random() - 0.5) * 0.012 : (Math.random() - 0.5) * 0.0015;
    const i0 = Math.round((p / bpf + jit + 0.02) * SR), a = amps[p % 4] * (1 + (Math.random() - 0.5) * 0.06);
    const L = Math.round(SR * 0.075); let lp = 0, lp2 = 0, hp = 0;
    const fT = kind === 'slap' ? 0 : 64 + (p % 4) * 1.5, ph = Math.random() * 0.4;
    for (let j = 0; j < L; j++) {
      const tt = j / SR, x = Math.random() * 2 - 1, att = Math.min(1, tt / 0.0025);
      let v;
      if (kind === 'slap') {
        lp += (x - lp) * 0.32; hp += (lp - hp) * 0.04; // band ~300–2500 Hz
        v = (lp - hp) * att * Math.exp(-tt / 0.007) * 2.2;
      } else {
        lp += (x - lp) * 0.06; lp2 += (lp - lp2) * 0.06;  // ~450 Hz 2-pole
        v = lp2 * att * Math.exp(-tt / 0.02) * 5 + Math.sin(TAU * fT * tt + ph) * att * Math.exp(-tt / 0.03) * 0.9
          + Math.sin(TAU * fT * 2.02 * tt) * att * Math.exp(-tt / 0.016) * 0.35;
      }
      d[(i0 + j) % n] += v * a;
    }
  }
  let peak = 0; for (let i = 0; i < n; i++) peak = Math.max(peak, Math.abs(d[i]));
  for (let i = 0; i < n; i++) d[i] *= 0.9 / peak;
  return b;
}
function makeSteps() { // random sample-and-hold control signal for engine sputter
  const n = SR * 2, b = newBuffer(1, n, SR), d = b.getChannelData(0); let v = 0, i = 0;
  while (i < n) { v = Math.random() < 0.3 ? -rnd(0.5, 1) : rnd(-0.15, 0.1); const L = (SR * rnd(0.03, 0.14)) | 0; for (let j = 0; j < L && i < n; j++, i++) d[i] = v; }
  return b;
}
function makeImpulse() { // outdoor slapback: early discrete echoes off walls/hills + diffuse tail
  const dur = 2.4, n = (SR * dur) | 0, b = newBuffer(2, n, SR);
  for (let c = 0; c < 2; c++) {
    const d = b.getChannelData(c); let lp = 0;
    for (let i = 0; i < n; i++) {
      const t = i / SR, x = Math.random() * 2 - 1; lp += (x - lp) * lerp(0.5, 0.06, Math.min(1, t / 1.2));
      d[i] = lp * Math.exp(-t / 0.55) * (t < 0.03 ? t / 0.03 : 1) * 0.5;
    }
    const taps = c ? [[0.085, 0.8], [0.19, 0.5], [0.33, 0.42], [0.61, 0.25]] : [[0.11, 0.75], [0.16, 0.55], [0.41, 0.4], [0.74, 0.22]];
    for (const [tt, g] of taps) { const i0 = (tt * SR) | 0; let l2 = 0; for (let j = 0; j < 500; j++) { const x = (Math.random() * 2 - 1); l2 += (x - l2) * 0.25; d[i0 + j] += l2 * g * 3 * Math.exp(-j / 120); } }
  }
  return b;
}
function ensureSynthBufs() {
  if (BUF._rotor) return;
  ensureNoise();
  BUF._rotor = [makeRotor('thump')]; BUF._rotorDmg = [makeRotor('dmg')]; BUF._slap = [makeRotor('slap')];
  BUF._steps = [makeSteps()]; BUF._impulse = [makeImpulse()];
}

// ------------------------------------------------------------- sample bank
// Generated, mastered Ogg Vorbis assets described by assets/audio/manifest.json. Nothing blocks on
// them: a small critical set is fetched first, the rest streams in the background in priority order,
// and every sample-backed sound falls back to the synth recipe it replaces (or silence) until its
// buffer is ready. Decoding goes through OfflineAudioContexts (no user gesture needed, so loading
// starts at boot) at a per-asset rate so resident PCM stays proportionate: voice 24 kHz, beds /
// crowds / threats 32 kHz, transient-rich weapon and impact one-shots 48 kHz. During play the queue
// runs one job at a time with a gap between decodes so no frame takes a burst of decode callbacks.
const BASE = new URL('../assets/audio/', import.meta.url).href;
const SMP = {};            // id -> { id, kind: sfx|vo|mus, m: manifest entry, files, sr, bufs, st: 0 idle 1 queued 2 loading 3 ready 4 failed, prio }
const BANK = { man: null, loading: null, queue: [], inflight: 0, busy: false, lastDone: 0, dirty: false, ord: 0,
  bytes: 0, pcm: 0, files: 0, fails: [], t0: 0, critN: 0, critLeft: 0, critBytes: 0, critT: 0, autoLeft: 0, allT: 0 };
const HF48 = new Set(['cannon_shot', 'cannon_burst', 'cannon_tail', 'cannon_impact_dirt', 'cannon_impact_stone', 'rocket_launch', 'missile_launch', 'flare_dispense',
  'weapon_select', 'dry_fire', 'cannon_jam', 'arrow_hull_hit', 'arrow_volley_hull', 'bolt_hull_hit', 'bolt_pass', 'hull_hit_heavy', 'glass_crack', 'rotor_strike',
  'ui_confirm', 'ui_hover', 'ui_back', 'mfd_boot', 'title_impact', 'score_tally']);
// load order. 0: menu + first seconds of a run (the critical set). 1: the approach. 2-4: the rest
const PRIO0 = new Set(['ui_confirm', 'ui_hover', 'ui_back', 'mfd_boot', 'cannon_shot', 'cannon_burst', 'cannon_tail', 'camp_amb_loop', 'valley_wind_loop', 'army_bed_loop',
  'plt_checkin', 'cmd_brief', 'cmd_appr_1', 'plt_cleared', 'cmd_restart_1', 'cmd_restart_2', 'cmd_restart_3', 'cmd_p1_start', 'mus_menu']);
const PRIO1 = new Set(['rotor_ext_loop', 'rotor_int_loop', 'turbine_loop', 'wind_slipstream_loop', 'blade_slap_loop', 'cmd_appr_2', 'cmd_appr_3', 'cmd_appr_4', 'plt_reveal', 'cmd_reveal',
  'cannon_impact_dirt', 'expl_small', 'expl_medium', 'war_drums_loop', 'army_close_loop', 'war_chant', 'war_horn', 'title_impact', 'mus_approach', 'mus_reveal',
  'bty_10', 'bty_9', 'bty_8', 'bty_7', 'bty_6', 'bty_5', 'bty_4', 'bty_3', 'bty_2', 'bty_1', 'bty_pullup', 'bty_altitude', 'bty_sink', 'plt_mayday_1', 'plt_mayday_2', 'plt_mayday_3', 'gun_ballista_1', 'gun_ballista_2', 'gun_volley_1', 'gun_volley_2', 'gun_volley_3']);
const MUS_AUTO = { mus_menu: 0, mus_approach: 1, mus_reveal: 1, mus_defeat: 3 }; // others are requested by the director
const UNUSED = new Set(['heli_startup', 'heli_flyby', 'radio_in', 'radio_out']);
// low / mid dominated beds: 24 kHz is transparent for them and saves a third of their PCM
const LO24 = new Set(['army_bed_loop', 'army_close_loop', 'panic_loop', 'cheer_loop', 'war_drums_loop', 'valley_wind_loop', 'camp_amb_loop', 'rotor_wash_loop', 'banner_flap_loop',
  'radio_static_loop', 'river_loop', 'rotor_int_loop', 'rotor_damaged_loop', 'engine_damaged_loop']);
const DEC = {};

const warned = {};
function warnOnce(tag, e) { if (warned[tag]) return; warned[tag] = 1; if (typeof console !== 'undefined') console.warn('[audio] ' + tag + ': ' + ((e && (e.stack || e.message)) || e)); }
function blog(msg) { if (audio.onLog) { try { audio.onLog(msg); } catch (e) { /* noop */ } } }
function prioOf(e) {
  const id = e.id, m = e.m;
  if (e.kind === 'mus') return id in MUS_AUTO ? MUS_AUTO[id] : -1;
  if (UNUSED.has(id)) return -1;
  if (PRIO0.has(id)) return 0;
  if (PRIO1.has(id)) return 1;
  if (e.kind === 'vo') return m.speaker === 'betty' || id.startsWith('gun_') ? 2 : m.fx === 'dry' ? 4 : 3;
  return m.group === 'world' ? 3 : 2;
}
function buildBank(man) {
  const add = (kind, id, files, m, sr) => { SMP[id] = { id, kind, m, files, sr, bufs: null, st: 0, prio: 9, ord: BANK.ord++, last: -1, raw: null, loop: !!m.loop, ls: 0, le: 0, crit: false }; };
  for (const s of man.sfx || []) add('sfx', s.id, s.files, s, HF48.has(s.id) ? 48000 : LO24.has(s.id) ? 24000 : 32000);
  for (const v of man.vo || []) add('vo', v.id, [v.file], v, 24000);
  for (const m of man.music || []) {
    // loop cues use the *_loop file (seam crossfade baked in); the approach keeps its intro build and gets a longer seam crossfade (prepLoop)
    const full = !m.loop || m.id === 'mus_approach';
    add('mus', m.id, [full ? m.file : (m.loop_file || m.file)], m, 48000);
  }
}
function request(id, prio) {
  const e = SMP[id]; if (!e || e.st >= 2) return;
  if (e.st === 1) { if (prio < e.prio) { e.prio = prio; BANK.dirty = true; } return; }
  if (e.st === 4) return;
  e.prio = prio; e.st = 1; BANK.queue.push(e); BANK.dirty = true;
}
function pump() {
  if (!BANK.man) return;
  if (BANK.dirty) { BANK.queue.sort((a, b) => a.prio - b.prio || a.ord - b.ord); BANK.dirty = false; }
  const max = BANK.busy ? 1 : 4;
  while (BANK.queue.length && BANK.inflight < max) {
    if (BANK.busy && performance.now() - BANK.lastDone < 140) break;
    const e = BANK.queue.shift(); if (e.st !== 1) continue;
    loadEntry(e);
    if (BANK.busy) break;
  }
}
function decodeAt(ab, sr) {
  const c = DEC[sr] || (DEC[sr] = new OfflineCtx(1, 1, sr));
  return new Promise((res, rej) => { const p = c.decodeAudioData(ab, res, rej); if (p && p.catch) p.catch(rej); });
}
// music: the full approach file loops [loop_src_start, loop_src_end] with a 2-beat (1 s at 120 BPM) equal-power seam
// crossfade baked in place: the end of the loop blends into the bars that lead into its start (the generator used 60 ms)
function prepLoop(e, b) {
  const m = e.m; if (e.kind !== 'mus' || !m.loop || e.files[0] !== m.file || !m.loop_src_end) return;
  const sr = b.sampleRate, S = Math.round(m.loop_src_start * sr), T = Math.min(b.length, Math.round(m.loop_src_end * sr)), n = Math.min(S, Math.round(1.0 * sr));
  for (let c = 0; c < b.numberOfChannels; c++) {
    const d = b.getChannelData(c);
    for (let i = 0; i < n; i++) { const x = (i + 0.5) / n * Math.PI / 2; d[T - n + i] = d[T - n + i] * Math.cos(x) + d[S - n + i] * Math.sin(x); }
  }
  e.ls = S / sr; e.le = T / sr;
}
async function loadEntry(e) {
  e.st = 2; BANK.inflight++;
  try {
    const out = [];
    for (let i = 0; i < e.files.length; i++) {
      let ab = e.raw ? e.raw[i] : null;
      if (!ab) {
        const r = await fetch(BASE + e.files[i]);
        if (!r.ok) throw new Error('HTTP ' + r.status + ' ' + e.files[i]);
        ab = await r.arrayBuffer(); BANK.bytes += ab.byteLength; BANK.files++;
        if (e.crit) BANK.critBytes += ab.byteLength;
        if (e.kind === 'mus') (e.raw = e.raw || [])[i] = ab; // keep the compressed bytes: music is evicted and re-decoded on demand
      }
      const b = await decodeAt(e.kind === 'mus' ? ab.slice(0) : ab, e.sr);
      prepLoop(e, b); out.push(b);
    }
    e.bufs = out; e.st = 3; for (const b of out) BANK.pcm += b.length * b.numberOfChannels * 4;
    if (BANK.busy) blog(`AUDIO decoded ${e.id} (${(out[0].length * out[0].numberOfChannels * out.length * 4 / 1e6).toFixed(1)} MB)`);
    if (e.kind === 'mus' && MUS.keep && !MUS.keep.includes(e.id) && MUS.want !== e.id && !MUS.decks.some(d => d.id === e.id)) evict(e.id);   // landed after the stage moved on
  } catch (err) {
    e.st = 4; BANK.fails.push(e.id);
    if (typeof console !== 'undefined') console.warn('[audio] sample failed: ' + e.id + ' - ' + ((err && err.message) || err));
  }
  BANK.inflight--; BANK.lastDone = performance.now();
  if (e.crit) { e.crit = false; if (--BANK.critLeft === 0) { BANK.critT = performance.now() - BANK.t0; blog(`AUDIO critical set ready: ${BANK.critN} sounds, ${(BANK.critBytes / 1e6).toFixed(2)} MB fetched in ${BANK.critT.toFixed(0)} ms`); } }
  if (e.auto) { e.auto = false; if (--BANK.autoLeft === 0) { BANK.allT = performance.now() - BANK.t0; blog(`AUDIO background load done: ${BANK.files} files, ${(BANK.bytes / 1e6).toFixed(1)} MB fetched, ${(BANK.pcm / 1e6).toFixed(0)} MB PCM resident, ${BANK.fails.length} failed${BANK.fails.length ? ' [' + BANK.fails.join(' ') + ']' : ''}, ${(BANK.allT / 1000).toFixed(1)} s`); } }
  pump();
}
function loadBank() {
  if (BANK.loading) return BANK.loading;
  BANK.t0 = performance.now();
  BANK.loading = fetch(BASE + 'manifest.json').then(r => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); }).then(man => {
    BANK.man = man; buildBank(man);
    for (const id in SMP) { const e = SMP[id], p = prioOf(e); if (p < 0) continue; e.auto = true; BANK.autoLeft++; if (p === 0) { e.crit = true; BANK.critN++; BANK.critLeft++; } request(id, p); }
    pump();
  }).catch(err => { if (typeof console !== 'undefined') console.warn('[audio] manifest failed - synth only: ' + ((err && err.message) || err)); });
  return BANK.loading;
}
function evict(id) {
  const e = SMP[id]; if (!e || e.kind !== 'mus' || e.st !== 3) return;
  for (const b of e.bufs) BANK.pcm -= b.length * b.numberOfChannels * 4;
  e.bufs = null; e.st = 0; blog('MUS evict ' + id);
}
const ok = (id) => { const e = SMP[id]; return !!e && e.st === 3; };
function pickBuf(e) { const n = e.bufs.length; if (n === 1) return e.bufs[0]; let i = (Math.random() * n) | 0; if (i === e.last) i = (i + 1) % n; e.last = i; return e.bufs[i]; }

// one-shot sample parameters: lvl = playback gain (calibrated against the recipe each replaces, tools/audio_test/levels.html),
// ref = distance reference m, rev = reverb send, max = simultaneous voices, gap = min s between triggers, pv = random pitch spread
const SP = {
  cannon_shot: { lvl: 0.2, ref: 80, rev: 0.25, max: 6, gap: 0.03 }, cannon_burst: { lvl: 0.18, rev: 0.2, max: 3, gap: 0.1, pv: 0 }, cannon_tail: { lvl: 0.16, rev: 0.25, max: 2, gap: 0.15, pv: 0.03 },
  cannon_impact_dirt: { lvl: 0.55, ref: 50, rev: 0.3, max: 8, gap: 0.03 }, cannon_impact_stone: { lvl: 0.42, ref: 50, rev: 0.3, max: 8, gap: 0.03 },
  rocket_launch: { lvl: 0.17, rev: 0.3, max: 6, gap: 0.04 }, missile_launch: { lvl: 0.38, rev: 0.35, max: 4, gap: 0.1 }, flare_dispense: { lvl: 0.6, rev: 0.2, max: 3, gap: 0.1 },
  expl_small: { lvl: 1.0, ref: 90, rev: 0.4, max: 8, gap: 0.02 }, expl_medium: { lvl: 0.7, ref: 140, rev: 0.45, max: 7, gap: 0.02 }, expl_large: { lvl: 0.9, ref: 240, rev: 0.5, max: 4, gap: 0.05 },
  expl_distant: { lvl: 0.9, ref: 520, rev: 0.45, max: 4, gap: 0.05 }, expl_water: { lvl: 0.75, ref: 90, rev: 0.35, max: 4, gap: 0.05 },
  tower_collapse: { lvl: 1.0, ref: 220, rev: 0.45, max: 2, gap: 0.2 }, wall_breach: { lvl: 0.95, ref: 200, rev: 0.45, max: 3, gap: 0.2 }, debris_rain: { lvl: 0.7, ref: 60, rev: 0.3, max: 3, gap: 0.3 },
  weapon_select: { lvl: 0.4, max: 2, gap: 0.05 }, dry_fire: { lvl: 0.5, max: 2, gap: 0.08 }, cannon_jam: { lvl: 0.3, max: 2, gap: 0.1 }, cannon_overheat_hiss: { lvl: 0.22, max: 1, gap: 1 },
  rearm_load: { lvl: 0.5, max: 2, gap: 1.3 }, repair_tool: { lvl: 0.35, max: 2, gap: 0.5 }, touchdown: { lvl: 0.8, max: 2, gap: 0.2 },
  arrow_hull_hit: { lvl: 0.26, max: 6, gap: 0.02 }, arrow_volley_hull: { lvl: 0.24, max: 2, gap: 0.25 }, bolt_hull_hit: { lvl: 0.72, max: 3, gap: 0.05 }, bolt_pass: { lvl: 0.28, max: 3, gap: 0.05 },
  hull_hit_heavy: { lvl: 1.0, max: 5, gap: 0.03 }, glass_crack: { lvl: 0.16, max: 3, gap: 0.05 }, rotor_strike: { lvl: 0.5, max: 2, gap: 0.2 },
  crash_spin: { lvl: 0.5, max: 1, gap: 1, pv: 0 }, crash_impact: { lvl: 0.8, max: 1, gap: 1, pv: 0 }, airframe_stress: { lvl: 0.5, max: 1, gap: 2 },
  war_horn: { lvl: 0.55, ref: 250, rev: 0.6, max: 3, gap: 0.3 }, horn_rout: { lvl: 0.55, ref: 250, rev: 0.6, max: 2, gap: 0.5 }, horn_alarm: { lvl: 0.8, ref: 300, rev: 0.6, max: 2, gap: 1 },
  volley_loose: { lvl: 1.3, ref: 120, rev: 0.3, max: 4, gap: 0.2 }, arrow_flyby: { lvl: 0.8, max: 3, gap: 0.2 },
  ballista_crank: { lvl: 0.6, ref: 90, rev: 0.3, max: 3, gap: 0.3 }, ballista_fire: { lvl: 0.3, ref: 110, rev: 0.4, max: 4, gap: 0.05 },
  bombard_fire: { lvl: 0.9, ref: 220, rev: 0.55, max: 4, gap: 0.1 }, flak_burst: { lvl: 0.45, ref: 130, rev: 0.45, max: 6, gap: 0.03 },
  trebuchet_release: { lvl: 0.6, ref: 160, rev: 0.4, max: 3, gap: 0.2 }, boulder_flyby: { lvl: 0.7, ref: 80, max: 2, gap: 0.3 }, boulder_impact: { lvl: 1.3, ref: 170, rev: 0.45, max: 3, gap: 0.1 },
  firepot_ignite: { lvl: 0.7, ref: 90, rev: 0.4, max: 4, gap: 0.1 },
  war_chant: { lvl: 0.8, ref: 160, rev: 0.5, max: 3, gap: 0.5 }, shield_wall_up: { lvl: 0.7, ref: 110, rev: 0.4, max: 3, gap: 0.3 }, rout_stampede: { lvl: 0.8, ref: 150, rev: 0.4, max: 3, gap: 0.3 },
  cheer_burst: { lvl: 0.5, ref: 150, rev: 0.45, max: 3, gap: 0.2 }, scream_group: { lvl: 0.45, ref: 60, rev: 0.4, max: 5, gap: 0.08 }, death_cry: { lvl: 0.45, ref: 40, rev: 0.35, max: 4, gap: 0.12 },
  warlord_death: { lvl: 0.9, ref: 120, rev: 0.5, max: 1, gap: 1, pv: 0 }, village_alarm_bell: { lvl: 0.8, ref: 260, rev: 0.6, max: 1, gap: 5, pv: 0 },
  ui_confirm: { lvl: 1.0, max: 2, gap: 0.03, pv: 0 }, ui_hover: { lvl: 0.3, max: 2, gap: 0.03, pv: 0 }, ui_back: { lvl: 1.0, max: 2, gap: 0.03, pv: 0 },
  mfd_boot: { lvl: 0.4, max: 1, gap: 1, pv: 0 }, title_impact: { lvl: 0.55, max: 1, gap: 1, pv: 0 }, score_tally: { lvl: 0.5, max: 1, gap: 1, pv: 0 },
};
const SP_DEF = { lvl: 0.6, max: 3, gap: 0.05 };
for (const k in SP) if (SP[k].pv === undefined) SP[k].pv = 0.06;
SP_DEF.pv = 0.06;
// voice lines: headset lines (radio / intercom / betty) are dry and centred on the voice bus; enemy shouts are placed in the world
const VO_SPEC = { radio: { lvl: 1.0, max: 2, gap: 0, pv: 0 }, intercom: { lvl: 1.0, max: 2, gap: 0, pv: 0 }, betty: { lvl: 0.85, max: 2, gap: 0, pv: 0 }, dry: { lvl: 1.0, ref: 45, rev: 0.45, max: 3, gap: 0, pv: 0 } };
// loop layer gains (sample loops are mastered at -22 dBFS RMS; calibrated against the synth layers they sit with)
const CAL = { rext: 1.0, rint: 0.75, turb: 0.35, slap: 1.0, rdmg: 1.4, edmg: 0.7, rattle: 0.5, slip: 0.8, wash: 1.0, valley: 0.2, bed: 2.2, close: 5.0, drums: 1.9, panic: 5.0, cheer: 2.0,
  fireL: 0.6, fireS: 3.5, river: 0.7, insects: 0.5, banner: 0.7, camp: 0.3, stat: 0.18 };
const MUS_BASE = 0.7, VOX_BASE = 1.7, DUCK = 0.5;   // DUCK: music + crowd sit ~6 dB down while a headset line plays

// ------------------------------------------------------------- live graph
// Built against any BaseAudioContext so it can be rendered offline for tests.
const EXT = { wash: 0, shake: 0, river: 0, banner: 0, menu: 0, close: 0, fireK: 0, firePan: 0, countdown: false, betty: false };
class Graph {
  constructor(ctx) {
    this.ctx = ctx; const k = this.k = kit(ctx);
    ensureSynthBufs();
    // master chain
    this.master = k.g(0.9); this.sfx = k.g(1); this.amb = k.g(1);
    this.pre = k.g(1);
    const comp = ctx.createDynamicsCompressor();
    comp.threshold.value = -16; comp.knee.value = 12; comp.ratio.value = 3.5; comp.attack.value = 0.006; comp.release.value = 0.22;
    const lim = ctx.createDynamicsCompressor();
    lim.threshold.value = -4; lim.knee.value = 0; lim.ratio.value = 20; lim.attack.value = 0.001; lim.release.value = 0.09;
    const clip = ctx.createWaveShaper(), cv = new Float32Array(2049);
    for (let i = 0; i < 2049; i++) { const x = (i / 1024 - 1) * 2, ax = Math.abs(x); cv[i] = Math.sign(x) * (ax < 0.7 ? ax : 0.7 + 0.28 * Math.tanh((ax - 0.7) / 0.28)); }
    clip.curve = cv; // input range mapped as [-2,2] via pre-gain 0.5 below
    const half = k.g(0.5);
    k.chain(this.pre, comp, lim, half, clip, this.master, ctx.destination);
    this.an = ctx.createAnalyser(); this.an.fftSize = 2048; this.master.connect(this.an); this._mb = new Float32Array(2048); this._fb = new Uint8Array(1024);
    this.sfx.connect(this.pre); this.amb.connect(this.pre);
    // music + voice buses (own faders). Music ducks under headset voice lines.
    this.mus = k.g(MUS_BASE); this.musDuck = k.g(1); k.chain(this.mus, this.musDuck, this.pre);
    this.vox = k.g(VOX_BASE); this.vox.connect(this.pre);
    // reverb
    this.rev = ctx.createConvolver(); this.rev.buffer = BUF._impulse[0];
    this.revIn = k.g(1); k.chain(this.revIn, this.rev, k.f('highpass', 140, 0.5), k.g(0.5), this.pre);
    // one-shot bus: world sounds are muffled in cockpit, UI/own-ship are not
    this.world = k.f('lowpass', 20000, 0.5); this.world.connect(this.sfx);
    this.ui = k.g(1); this.ui.connect(this.sfx);
    // enemy shouts: on the voice fader, but placed and muffled like any other world sound
    this.vworld = k.f('lowpass', 20000, 0.5); this.vworld.connect(this.vox);
    this._buildHeli(); this._buildAmb(); this._buildAlerts();
    this.t = { lock: 0, lockT: 0, bnd: 0, tick: 0, horn: rnd(6, 14), scream: 2, att: 0 };
    this.sm = {}; // smoothed state
    this.crowdReady = false;
    // sample loop layers: [key, sample id, destination]
    const h = this.h, a = this.a;
    this.S = {}; this.slDone = false;
    this.SLD = [['rext', 'rotor_ext_loop', h.out], ['rint', 'rotor_int_loop', h.out], ['turb', 'turbine_loop', h.out], ['slap', 'blade_slap_loop', h.ext],
      ['rdmg', 'rotor_damaged_loop', h.ext], ['edmg', 'engine_damaged_loop', h.ext], ['rattle', 'cockpit_rattle_loop', this.sfx], ['slip', 'wind_slipstream_loop', this.sfx],
      ['wash', 'rotor_wash_loop', this.world], ['valley', 'valley_wind_loop', this.amb], ['bed', 'army_bed_loop', a.murP.m], ['close', 'army_close_loop', a.closeG],
      ['drums', 'war_drums_loop', a.drumP.m], ['panic', 'panic_loop', a.panP.m], ['cheer', 'cheer_loop', a.cheerP.m], ['fireL', 'fire_large_loop', a.fireP.m],
      ['fireS', 'fire_small_loop', a.fsPan], ['river', 'river_loop', this.amb], ['insects', 'dusk_insects_loop', this.amb], ['banner', 'banner_flap_loop', this.world],
      ['camp', 'camp_amb_loop', this.amb], ['stat', 'radio_static_loop', this.vox]];
  }
  // smoothed param target; unchanged targets are skipped so the automation timeline is not re-written every frame
  set(param, v, tc = 0.08) {
    const p = param._t; if (p !== undefined && Math.abs(p - v) <= Math.abs(v) * 0.002 + 1e-6) return;
    param._t = v; param.setTargetAtTime(v, this.ctx.currentTime, tc);
  }

  _buildHeli() {
    const k = this.k, h = this.h = {};
    h.ext = k.g(1); h.cockLP = k.f('lowpass', 20000, 0.6); h.out = k.g(0);
    k.chain(h.ext, h.cockLP, h.out, this.sfx);
    h.out.connect(k.g(0.12)).connect(this.revIn);
    // blade thump + damaged thump + slap
    h.thump = k.loop(BUF._rotor[0]); h.thumpG = k.g(0); h.thump.connect(h.thumpG).connect(h.ext);
    h.dmg = k.loop(BUF._rotorDmg[0]); h.dmgG = k.g(0); h.dmg.connect(h.dmgG).connect(h.ext);
    h.slap = k.loop(BUF._slap[0]); h.slapG = k.g(0); h.slap.connect(k.f('highpass', 350, 0.6)).connect(h.slapG).connect(h.ext);
    h.rattle = k.loop(BUF._slap[0], 2.37); h.rattleG = k.g(0); k.chain(h.rattle, k.f('bandpass', 3100, 2.5), h.rattleG, h.ext);
    h.wob = k.o('sine', 1.7); h.wobG = k.g(0); h.wob.connect(h.wobG);
    [h.thump, h.dmg, h.slap].forEach((s) => h.wobG.connect(s.playbackRate));
    // sub harmonics of blade-pass for real low end (bypass cockpit low-pass: felt in the airframe)
    h.sub1 = k.o('sine', 40); h.sub2 = k.o('sine', 60); h.subG = k.g(0);
    h.sub1.connect(h.subG); h.sub2.connect(k.g(0.5)).connect(h.subG); h.subG.connect(h.out);
    // turbine
    h.turbG = k.g(0); h.turbCock = k.g(0);
    h.t1 = k.o('sawtooth', 3900); h.t2 = k.o('sine', 5850); h.t3 = k.o('sine', 2610);
    const tm = k.g(1); h.t1.connect(k.g(0.25)).connect(tm); h.t2.connect(k.g(0.3)).connect(tm); h.t3.connect(k.g(0.3)).connect(tm);
    h.hiss = k.n('white'); h.hissF = k.f('bandpass', 2400, 0.8); h.hiss.connect(h.hissF).connect(k.g(0.8)).connect(tm);
    k.chain(tm, k.f('lowpass', 9000, 0.5), h.turbG, h.ext); h.turbG.connect(h.turbCock).connect(h.out);
    h.sput = k.loop(BUF._steps[0]); h.sputG = k.g(0); h.sput.connect(h.sputG).connect(h.turbG.gain);
    // gearbox
    h.gear = k.o('sawtooth', 420); h.gear2 = k.o('triangle', 213); h.gearG = k.g(0);
    k.chain(h.gear, k.f('lowpass', 1300, 1), h.gearG, h.ext); h.gear2.connect(k.g(0.6)).connect(h.gearG);
    // engine damage grind
    h.grind = k.o('sawtooth', 87); h.grindAM = k.g(0.5); h.grindG = k.g(0);
    const gn = k.n('brown', 0, undefined, 0.2); gn.connect(k.g(2.5)).connect(h.grindAM.gain);
    k.chain(h.grind, k.f('bandpass', 950, 2), h.grindAM, h.grindG, h.ext);
    k.chain(k.n('white'), k.f('bandpass', 1900, 3), k.g(0.5), h.grindAM);
    // tail rotor damage flutter buzz
    h.tail = k.o('square', 118); h.tailAM = k.g(0.5); h.tailG = k.g(0);
    h.tailL = k.o('sine', 27); h.tailL.connect(k.g(0.5)).connect(h.tailAM.gain);
    k.chain(h.tail, k.f('highpass', 700, 0.7), k.f('lowpass', 4200, 0.7), h.tailAM, h.tailG, h.ext);
    // cockpit panel hum
    h.hum = k.o('sine', 400); h.hum2 = k.o('triangle', 800); h.humG = k.g(0);
    h.hum.connect(h.humG); h.hum2.connect(k.g(0.15)).connect(h.humG); h.humG.connect(this.sfx);
    // slipstream wind
    h.wind = k.n('pink'); h.windF = k.f('bandpass', 500, 0.6); h.windG = k.g(0);
    k.chain(h.wind, h.windF, h.windG, this.sfx);
    // continuous gun body rumble + overheat hiss
    h.gun = k.n('brown'); h.gunAM = k.g(0.5); h.gunG = k.g(0); h.gunL = k.o('sawtooth', 10.5);
    h.gunL.connect(k.g(0.5)).connect(h.gunAM.gain); k.chain(h.gun, k.f('lowpass', 170, 0.8), h.gunAM, h.gunG, this.sfx);
    h.heat = k.n('white'); h.heatG = k.g(0); k.chain(h.heat, k.f('highpass', 5500, 0.7), h.heatG, this.sfx);
  }

  _buildAmb() {
    const k = this.k, a = this.a = {};
    // base valley wind (always on, also in menu)
    a.wind = k.n('pink', 0, undefined, 0.7); a.windF = k.f('lowpass', 420, 0.4); a.windG = k.g(0.0);
    a.gust = k.n('brown', 0, undefined, 0.008); a.gustG = k.g(0.04); a.gust.connect(a.gustG).connect(a.windG.gain);
    k.chain(a.wind, a.windF, a.windG, this.amb);
    k.chain(k.n('white', 0, undefined, 0.9), k.f('bandpass', 2600, 0.5), k.g(0.035), a.windG);
    // crowd bus: synth beds until the recorded ones are decoded, then a slow crossfade (pair: s = synth, m = sample)
    a.crowdLP = k.f('lowpass', 8000, 0.5); a.crowdG = k.g(0); a.crowdDuck = k.g(1);
    k.chain(a.crowdLP, a.crowdG, a.crowdDuck, this.amb); a.crowdDuck.connect(k.g(0.35)).connect(this.revIn);
    a.murG = k.g(0); a.panG = k.g(0); a.cheerG = k.g(0); a.drumG = k.g(0); a.closeG = k.g(0);
    [a.murG, a.panG, a.cheerG, a.drumG, a.closeG].forEach((g) => g.connect(a.crowdLP));
    a.fireG = k.g(0); a.fireG.connect(this.amb);
    const pair = (out) => { const s = k.g(1), m = k.g(0); s.connect(out); m.connect(out); return { s, m }; };
    a.murP = pair(a.murG); a.panP = pair(a.panG); a.cheerP = pair(a.cheerG); a.drumP = pair(a.drumG); a.fireP = pair(a.fireG);
    // nearest single fire: positional loop (gain + pan fed by the director)
    a.fsPan = this.ctx.createStereoPanner ? this.ctx.createStereoPanner() : k.g(1); a.fsPan.connect(this.world);
  }
  attachLoops() {
    if (this.crowdReady || !BUF._crowd || !BUF._panic || !BUF._cheer || !BUF._drums || !BUF._fire) return;
    const k = this.k, a = this.a;
    k.loop(BUF._crowd[0]).connect(a.murP.s); k.loop(BUF._panic[0]).connect(a.panP.s);
    k.loop(BUF._cheer[0]).connect(a.cheerP.s); k.loop(BUF._drums[0]).connect(a.drumP.s);
    k.loop(BUF._fire[0]).connect(a.fireP.s);
    k.loop(BUF._crowd[0], 0.93).connect(k.g(0.7)).connect(a.murP.s); // second, detuned layer = bigger army
    this.crowdReady = true;
  }
  // start sample loop layers whose buffers have arrived (random start offset so layers never phase-lock)
  attachSamples() {
    let pending = 0;
    for (const d of this.SLD) {
      if (this.S[d[0]]) continue;
      const e = SMP[d[1]]; if (!e || e.st !== 3) { if (e && e.st !== 4) pending++; continue; }
      const b = e.bufs[0], src = this.ctx.createBufferSource(), g = this.k.g(0);
      src.buffer = b; src.loop = true; src.connect(g).connect(d[2]); src.start(0, Math.random() * b.duration * 0.9);
      this.S[d[0]] = { src, g };
    }
    this.slDone = pending === 0 && !!BANK.man;
  }

  _buildAlerts() {
    const k = this.k, w = this.w = {};
    // ballista aim tell: rising, tightening tremolo tone
    w.bal = k.o('triangle', 600); w.bal2 = k.o('sine', 1200); w.balAM = k.g(0.5); w.balG = k.g(0);
    w.balL = k.o('square', 6); w.balL.connect(k.g(0.5)).connect(w.balAM.gain);
    w.bal.connect(w.balAM); w.bal2.connect(k.g(0.3)).connect(w.balAM); k.chain(w.balAM, k.f('lowpass', 5000, 0.7), w.balG, this.ui);
    // solid lock tone
    w.lock = k.o('square', 1975); w.lockG = k.g(0); k.chain(w.lock, k.f('lowpass', 6000, 0.7), w.lockG, this.ui);
    // master alarm warble
    w.alarm = k.o('square', 910); w.alarmL = k.o('square', 4); w.alarmL.connect(k.g(130)).connect(w.alarm.frequency);
    w.alarmG = k.g(0); k.chain(w.alarm, k.f('lowpass', 3500, 0.7), w.alarmG, this.ui);
    // sink / low-rpm whoop
    w.whoop = k.o('sawtooth', 650); w.whoopL = k.o('sawtooth', 2.4); w.whoopL.connect(k.g(260)).connect(w.whoop.frequency);
    w.whoopG = k.g(0); k.chain(w.whoop, k.f('lowpass', 2600, 1), w.whoopG, this.ui);
  }

  update(dt, s, playFn) {
    const sm = this.sm, h = this.h, a = this.a, w = this.w, k1 = clamp(dt * 6, 0, 1);
    const sv = (key, target, rate = k1) => { sm[key] = sm[key] === undefined ? target : lerp(sm[key], target, rate); return sm[key]; }; void sv;
    const active = s.active !== false ? 1 : 0;
    const rpm = clamp(num(s.rotorRPM, active ? 1 : 0), 0, 1.2) * (active || s.rotorRPM !== undefined ? 1 : 0), load = clamp(num(s.rotorLoad, 0.5), 0, 1);
    const speed = Math.abs(num(s.speed, 0)), cock = s.cockpit ? 1 : 0;
    const dR = clamp(num(s.dmgRotor, 0), 0, 1), dE = clamp(num(s.dmgEngine, 0), 0, 1), dT = clamp(num(s.dmgTail, 0), 0, 1);
    const on = rpm > 0.02 ? 1 : 0, spN = clamp(speed / 70, 0, 1);
    const S = this.S, X = EXT;
    this.t.att -= dt; if (!this.slDone && this.t.att <= 0) { this.t.att = 0.3; this.attachSamples(); }

    // --- helicopter (synth core: responds to load / damage; recorded layers underneath)
    this.set(h.out.gain, on * 0.5 * Math.min(1, rpm * 2), 0.15);
    const rate = Math.max(0.05, rpm) * (1 - 0.035 * load);
    [h.thump, h.dmg, h.slap].forEach((src) => this.set(src.playbackRate, rate, 0.1));
    this.set(h.rattle.playbackRate, rate * 2.37, 0.1);
    this.set(h.thumpG.gain, (0.42 + 0.5 * load) * (1 - 0.6 * dR) * Math.min(1, rpm * 1.5));
    this.set(h.dmgG.gain, (0.6 + 0.6 * load) * dR);
    this.set(h.slapG.gain, (0.1 + 0.55 * load * load + 0.3 * spN) * (S.slap ? 0.6 : 1));
    this.set(h.rattleG.gain, 0.5 * dR);
    this.set(h.wobG.gain, 0.07 * dR); this.set(h.wob.frequency, 1.3 + 2.5 * dR);
    this.set(h.sub1.frequency, 40 * rate); this.set(h.sub2.frequency, 60 * rate);
    this.set(h.subG.gain, (0.035 + 0.075 * load) * Math.min(1, rpm * rpm));
    const tf = (0.35 + 0.65 * Math.min(rpm, 1.05)) * (1 - 0.22 * dE) * (1 + 0.03 * load);
    this.set(h.t1.frequency, 3900 * tf, 0.2); this.set(h.t2.frequency, 5850 * tf, 0.2); this.set(h.t3.frequency, 2610 * tf, 0.2);
    this.set(h.hissF.frequency, 1500 + 1500 * rpm);
    this.set(h.turbG.gain, (0.085 + 0.03 * load) * Math.min(1, rpm * 1.3) * (1 - 0.35 * dE) * (S.turb ? 0.6 : 1));
    this.set(h.sputG.gain, 0.06 * dE);
    this.set(h.turbCock.gain, cock * 0.8);
    this.set(h.gear.frequency, 420 * rate); this.set(h.gear2.frequency, 213 * rate);
    this.set(h.gearG.gain, 0.05 * rpm + 0.03 * load * rpm);
    this.set(h.grind.frequency, 87 * (0.6 + 0.4 * rpm)); this.set(h.grindG.gain, 0.5 * dE * Math.min(1, rpm * 2));
    this.set(h.tail.frequency, 118 * rate); this.set(h.tailG.gain, 0.16 * dT * Math.min(1, rpm * 2)); this.set(h.tailL.frequency, 19 + 14 * dT);
    this.set(h.cockLP.frequency, cock ? 750 : 20000, 0.12);
    this.set(this.world.frequency, cock ? 2600 : 20000, 0.12); this.set(this.vworld.frequency, cock ? 2600 : 20000, 0.12);
    this.set(h.humG.gain, cock * active * 0.012);
    this.set(h.windF.frequency, 350 + 900 * spN); this.set(h.windG.gain, active * (0.02 + 0.3 * spN * spN) * (cock ? 0.6 : 1) * (S.slip ? 0.45 : 1));
    this.set(h.gunG.gain, s.gunFiring ? 0.5 : 0, 0.03);
    const oh = clamp((num(s.overheat, 0) - 0.7) / 0.3, 0, 1);
    this.set(h.heatG.gain, oh * 0.05);
    // recorded layers: exterior / cockpit rotor crossfade on the view switch, rate follows rotor RPM
    const rr = clamp(rate, 0.45, 1.12), rotorK = on * Math.min(1, rpm * 1.4) * (0.75 + 0.4 * load) * (1 - 0.35 * dR);
    if (S.rext) { this.set(S.rext.g.gain, rotorK * (1 - cock) * CAL.rext, 0.12); this.set(S.rext.src.playbackRate, rr, 0.1); }
    if (S.rint) { this.set(S.rint.g.gain, rotorK * cock * CAL.rint, 0.12); this.set(S.rint.src.playbackRate, rr, 0.1); }
    if (S.turb) { this.set(S.turb.g.gain, on * CAL.turb * Math.min(1, rpm * 1.3) * (1 - 0.3 * dE) * (cock ? 1.4 : 1) * (0.85 + 0.3 * load)); this.set(S.turb.src.playbackRate, clamp(tf, 0.4, 1.1), 0.2); }
    if (S.slap) { this.set(S.slap.g.gain, on * CAL.slap * (0.08 + 0.9 * load * load + 0.35 * spN)); this.set(S.slap.src.playbackRate, rr, 0.1); }
    if (S.rdmg) { this.set(S.rdmg.g.gain, on * CAL.rdmg * dR * Math.min(1, rpm * 1.5)); this.set(S.rdmg.src.playbackRate, rr, 0.1); }
    if (S.edmg) this.set(S.edmg.g.gain, on * CAL.edmg * dE * Math.min(1, rpm * 2));
    if (S.rattle) this.set(S.rattle.g.gain, active * cock * on * CAL.rattle * clamp(0.12 + 0.7 * num(X.shake, 0) + 0.6 * dR, 0, 1.3), 0.06);
    if (S.slip) this.set(S.slip.g.gain, active * CAL.slip * Math.pow(spN, 1.5) * (cock ? 0.55 : 1), 0.15);
    if (S.wash) this.set(S.wash.g.gain, active * CAL.wash * clamp(num(X.wash, 0), 0, 1.2), 0.15);

    // --- ambience
    const night = clamp(num(s.night, 0), 0, 1);
    this.set(a.windG.gain, (active ? 0.05 : 0.16) * (1 - 0.3 * night) * (S.valley ? 0.35 : 1), 0.5);
    if (S.valley) this.set(S.valley.g.gain, CAL.valley * (active ? 0.6 : 1) * (1 - 0.3 * night), 0.5);
    this.attachLoops();
    const crowd = clamp(num(s.crowd, 0), 0, 1), panic = clamp(num(s.crowdPanic, 0), 0, 1), cheer = clamp(num(s.cheer, 0), 0, 1);
    const dist = Math.max(0, num(s.crowdDist, 400));
    const cAtt = 1 / (1 + Math.pow(dist / 220, 1.25));
    const present = Math.max(crowd, cheer);
    this.set(a.crowdG.gain, (present > 0 ? 1 : 0) * (0.25 + 2.2 * cAtt) * (cock ? 0.55 : 1) * (X.menu ? 0.45 : 1) * 0.38, 0.6);   // the menu is the score's moment
    this.set(a.crowdLP.frequency, clamp(9000 * Math.exp(-dist / 600), 500, 9000) * (cock ? 0.5 : 1), 0.3);
    this.set(a.murG.gain, Math.pow(crowd, 0.8) * (1 - 0.6 * panic) * (1 - 0.7 * cheer), 0.4);
    this.set(a.drumG.gain, crowd > 0.08 ? Math.pow(crowd, 1.3) * (1 - 0.8 * panic) * 0.9 * (1 - cheer) : 0, 0.6);
    this.set(a.panG.gain, panic * (0.3 + 0.7 * crowd), 0.3);
    this.set(a.cheerG.gain, cheer * 1.2, 0.4);
    this.set(a.closeG.gain, Math.pow(crowd, 0.8) * (1 - 0.5 * panic) * (1 - cheer) * clamp(num(X.close, 0), 0, 1) * CAL.close, 0.4);
    this.set(a.fireG.gain, clamp(num(s.fire, 0), 0, 1) * 0.28 * (cock ? 0.4 : 1), 0.5);
    const xf = (P, smp, lvl) => { this.set(P.s.gain, smp ? 0 : 1, 0.8); this.set(P.m.gain, smp ? lvl : 0, 0.8); };
    xf(a.murP, S.bed, CAL.bed); xf(a.drumP, S.drums, CAL.drums); xf(a.panP, S.panic, CAL.panic); xf(a.cheerP, S.cheer, CAL.cheer); xf(a.fireP, S.fireL, CAL.fireL);
    if (S.fireS) { this.set(S.fireS.g.gain, CAL.fireS * clamp(num(X.fireK, 0), 0, 1.5), 0.25); if (a.fsPan.pan) this.set(a.fsPan.pan, clamp(num(X.firePan, 0), -1, 1) * 0.8, 0.1); }
    if (S.river) this.set(S.river.g.gain, CAL.river * clamp(num(X.river, 0), 0, 1), 0.5);
    if (S.insects) this.set(S.insects.g.gain, CAL.insects * Math.pow(night, 1.5) * (1 - 0.5 * present * cAtt), 1.0);
    if (S.banner) this.set(S.banner.g.gain, CAL.banner * clamp(num(X.banner, 0), 0, 1), 0.3);
    if (S.camp) this.set(S.camp.g.gain, CAL.camp * (X.menu ? 1 : 0), 1.2);
    // ducking: music and crowd ~6 dB under any headset voice line
    const ducked = VOXS.until > this.ctx.currentTime;
    this.set(this.musDuck.gain, ducked ? DUCK : 1, ducked ? 0.07 : 0.35); this.set(a.crowdDuck.gain, ducked ? DUCK : 1, ducked ? 0.07 : 0.35);

    // --- alerts
    const bal = clamp(num(s.warnBallista, 0), 0, 1);
    this.set(w.balG.gain, bal > 0.01 ? 0.05 + 0.05 * bal : 0, 0.03);
    this.set(w.bal.frequency, 620 + 780 * bal, 0.04); this.set(w.bal2.frequency, (620 + 780 * bal) * 2, 0.04);
    this.set(w.balL.frequency, 5 + 13 * bal * bal, 0.04);
    const lock = s.lock | 0;
    this.set(w.lockG.gain, lock === 2 ? 0.05 : 0, 0.01);
    this.set(w.alarmG.gain, s.masterAlarm ? 0.045 : 0, 0.03);
    this.set(w.whoopG.gain, (s.sink || s.lowRPM) && !X.betty ? 0.075 : 0, 0.03);  // Betty's "sink rate" replaces the whoop once loaded

    // --- scheduled blips (live only)
    if (!playFn) return;
    const T = this.t;
    if (lock === 1) {
      T.lockT += dt; T.lock -= dt;
      if (T.lock <= 0) { playFn('_lockBeep'); T.lock = lerp(0.34, 0.085, clamp(T.lockT / 1.9, 0, 1)); }
    } else { T.lockT = 0; T.lock = 0; }
    const bnd = s.boundary | 0;
    if (bnd > 0 && !(bnd === 2 && X.countdown)) { T.bnd -= dt; if (T.bnd <= 0) { playFn(bnd === 2 ? '_bndFast' : '_bndSlow'); T.bnd = bnd === 2 ? 0.42 : 1.25; } } else T.bnd = 0;
    if (oh > 0) { T.tick -= dt; if (T.tick <= 0) { playFn('_tick', { gain: 0.5 + oh * 0.5 }); T.tick = rnd(0.05, 0.35) / (0.4 + oh); } }
    if (active && crowd > 0.15 && cheer < 0.3) { // distant horn calls + stray shouts keep the bed alive
      T.horn -= dt;
      if (T.horn <= 0) { playFn('horn', { gain: 0.5 * cAtt + 0.08, pitch: rnd(0.9, 1.1), _bus: 'world' }); T.horn = rnd(14, 30) / (0.4 + crowd); }
    }
    if (active && panic > 0.25) {
      T.scream -= dt;
      if (T.scream <= 0) { playFn('scream', { gain: (0.3 + 0.7 * panic) * (0.15 + cAtt), _bus: 'world' }); T.scream = rnd(0.6, 2.2) / (0.3 + panic); }
    }
  }
}

// ------------------------------------------------------------- public API
let ctx = null, graph = null, ready = false, preparing = null;
let vol = { master: 1, sfx: 1, amb: 1, music: 0.7, voice: 1 };
const voices = [];        // sfx one-shots { src, g, name, t0, end, lvl }
const vvoices = [];       // voice lines (never stolen by sfx)
const lastPlay = {};
const L = { p: [0, 0, 0], f: [0, 0, -1], r: [1, 0, 0] };
const MAX_VOICES = 44;
const VOXS = { until: 0 };
const NO = {};

async function prepare() {
  // loops first (ambience matters from the first second), then one-shots by priority
  const order = ['cannon', 'cannonImpact', 'explSmall', 'explMedium', 'uiClick', 'uiHover', 'weaponSwitch', '_lockBeep', '_bndSlow', '_bndFast', '_tick'];
  for (const n of Object.keys(R)) if (!order.includes(n)) order.push(n);
  const loopNames = Object.keys(LOOPS);
  // interleave: cheap priority one-shots, then loops, then the rest
  const jobs = [];
  order.slice(0, 11).forEach((n) => jobs.push(['r', n]));
  loopNames.forEach((n) => jobs.push(['l', n]));
  order.slice(11).forEach((n) => jobs.push(['r', n]));
  for (const [type, n] of jobs) {
    try {
      if (type === 'l') { const b = await renderLoop(n); if (b) BUF[n] = [b]; if (graph) graph.attachLoops(); }
      else { const arr = []; for (let i = 0; i < R[n].n; i++) { const b = await renderOne(n); if (b) arr.push(b); } if (arr.length) BUF[n] = arr; }
    } catch (e) { /* a failed recipe must never break the game */ if (typeof console !== 'undefined') console.warn('[audio] render failed', n, e); }
  }
  ready = true;
}

// play one buffer through the voice pipeline: distance gain / delay / air absorption / pan / reverb; voice limiting
function spawn(key, buf, r, o, mul, dly, pool, bus) {
  const now = ctx.currentTime;
  if (r.gap && lastPlay[key] !== undefined && now - lastPlay[key] < r.gap) return null;
  lastPlay[key] = now;
  let same = 0, oldestSame = null;
  for (let i = pool.length - 1; i >= 0; i--) {
    const v = pool[i];
    if (v.end <= now) { pool.splice(i, 1); continue; }
    if (v.name === key) { same++; if (!oldestSame || v.t0 < oldestSame.t0) oldestSame = v; }
  }
  if (same >= (r.max || 4) && oldestSame) kill(oldestSame, now, pool);
  if (pool === voices && voices.length >= MAX_VOICES) { // steal the quietest of the older half, else oldest
    let victim = voices[0];
    for (let i = 0; i < voices.length >> 1; i++) if (voices[i].lvl < victim.lvl) victim = voices[i];
    kill(victim, now, voices);
  }
  let gain = r.lvl * num(o.gain, 1) * (mul === undefined ? 1 : mul), delay = Math.max(0, num(o.delay, 0)) + (dly || 0), pan = 0, lpF = 0, revSend = r.rev || 0;
  const pv = r.pv !== undefined ? r.pv : (r.n > 1 || r.ref ? 0.08 : 0);
  const pitch = clamp(num(o.pitch, 1), 0.25, 4) * (1 + (Math.random() - 0.5) * pv);
  const pos = o.pos;
  if (pos && pos.length >= 3) {
    const dx = pos[0] - L.p[0], dy = pos[1] - L.p[1], dz = pos[2] - L.p[2], d = Math.sqrt(dx * dx + dy * dy + dz * dz);
    const ref = r.ref || 60;
    gain *= 1 / (1 + Math.pow(d / ref, 1.15));
    delay += Math.min(d / 340, 8);
    lpF = clamp(21000 * Math.exp(-d / 650), 420, 21000);
    if (d > 1) pan = clamp((dx * L.r[0] + dy * L.r[1] + dz * L.r[2]) / d, -1, 1) * (buf.numberOfChannels > 1 ? 0.6 : 0.85);
    revSend = Math.min(1, revSend * (1 + d / 400));
  }
  if (gain < 0.0015) return null;
  const src = ctx.createBufferSource(); src.buffer = buf; src.playbackRate.value = pitch;
  const g = ctx.createGain(); g.gain.value = gain;
  let node = src;
  if (lpF && lpF < 20000) { const f = ctx.createBiquadFilter(); f.type = 'lowpass'; f.frequency.value = lpF; f.Q.value = 0.5; node.connect(f); node = f; }
  node.connect(g); node = g;
  if (pan !== 0 && ctx.createStereoPanner) { const p = ctx.createStereoPanner(); p.pan.value = pan; node.connect(p); node = p; }
  node.connect(bus || (pos || o._bus === 'world' ? graph.world : graph.ui));
  if (revSend > 0) { const rs = ctx.createGain(); rs.gain.value = revSend * 0.5; node.connect(rs).connect(graph.revIn); }
  const t0 = now + delay, v = { src, g, name: key, t0, end: t0 + buf.duration / pitch + 0.05, lvl: gain, dur: buf.duration / pitch };
  src.start(t0);
  src.onended = () => { try { g.disconnect(); } catch (e) { /* noop */ } };
  pool.push(v);
  return v;
}
function kill(v, now, pool) {
  try { v.g.gain.cancelScheduledValues(now); v.g.gain.setValueAtTime(v.g.gain.value, now); v.g.gain.linearRampToValueAtTime(0, now + 0.03); v.src.stop(now + 0.04); } catch (e) { /* noop */ }
  v.end = now; const p = pool || voices, i = p.indexOf(v); if (i >= 0) p.splice(i, 1);
}
function fadeV(v, sec) {
  if (!v || !ctx) return; const now = ctx.currentTime, t = Math.max(now, v.t0);
  try { v.g.gain.cancelScheduledValues(t); v.g.gain.setValueAtTime(v.g.gain.value, t); v.g.gain.linearRampToValueAtTime(0, t + sec); v.src.stop(t + sec + 0.02); } catch (e) { /* noop */ }
  v.end = Math.min(v.end, t + sec + 0.02);
}
function synth(name, o, mul) {
  const r = R[name], bufs = BUF[name];
  if (!r || !bufs || !bufs.length) return null;
  return spawn(name, bufs[(Math.random() * bufs.length) | 0], r, o, mul, 0, voices);
}
// sample one-shot: false when not decoded yet (caller falls back), else the voice (or null if culled)
function smp(id, o, mul, dly) {
  const e = SMP[id]; if (!e || e.st !== 3) return false;
  return spawn(id, pickBuf(e), SP[id] || SP_DEF, o, mul, dly, voices) || null;
}
const dist = (p) => (p && p.length >= 3 ? Math.hypot(p[0] - L.p[0], p[1] - L.p[1], p[2] - L.p[2]) : 0);
// explosions are layered: generated sample = body + bass, synth = crack; far ones crossfade (400-600 m) to the distant take
function expl(id, crack, o) {
  const near = o.water && ok('expl_water') ? 'expl_water' : id;
  const d = dist(o.pos), kf = o.pos && ok('expl_distant') ? clamp((d - 400) / 200, 0, 1) : 0;
  if (!ok(near) && kf < 1) return false;
  if (kf < 1) smp(near, o, Math.cos(kf * Math.PI / 2));
  if (kf > 0) smp('expl_distant', o, Math.sin(kf * Math.PI / 2));
  synth(crack, o, 1 - 0.5 * kf);
  if (id === 'expl_large' && o.pos && d < 180) smp('debris_rain', o, 0.8, 0.55);
  return null;
}
// cannon: the burst layer re-triggers every five rounds (5-round takes at 10 rds/s), per-round shots sit underneath; tail on release
const GUN = { n: 0, h: null, firing: false };
function gunRelease() {
  if (GUN.n > 0) { const h = GUN.h; if (h && ctx.currentTime - h.t0 < 0.5) fadeV(h, 0.035); smp('cannon_tail', NO); }
  GUN.h = null; GUN.n = 0;
}
const winLoseByMusic = (id) => { const e = SMP[id]; return e && e.st !== 4 ? null : false; };
// recipe name (as called by the game) -> sample-backed implementation; returns false to fall back to the synth recipe
const HOOKS = {
  cannon(o) {
    if (!ok('cannon_burst')) return smp('cannon_shot', o);
    if (GUN.n++ % 5 === 0) { const v = smp('cannon_burst', NO); if (v) GUN.h = v; }
    const s = smp('cannon_shot', o, 0.5); return s === false ? null : s;
  },
  cannonImpact: (o) => smp(o.mat === 'stone' ? 'cannon_impact_stone' : 'cannon_impact_dirt', o, o.mat === 'water' ? 0.6 : 1),
  rocket: (o) => smp('rocket_launch', o), missile: (o) => smp('missile_launch', o), flare: (o) => smp('flare_dispense', o),
  explSmall: (o) => expl('expl_small', 'crackS', o), explMedium: (o) => expl('expl_medium', 'crackM', o), explLarge: (o) => expl('expl_large', 'crackL', o),
  collapse: (o) => smp(o.kind === 'wall' ? 'wall_breach' : 'tower_collapse', o),
  debris: (o) => smp('debris_rain', o), weaponSwitch: (o) => smp('weapon_select', o), dryFire: (o) => smp('dry_fire', o), jam: (o) => smp('cannon_jam', o),
  overheat: (o) => { const v = smp('cannon_overheat_hiss', o); if (v !== false) synth('jam', o, 0.4); return v; },
  rearmTick: (o) => smp('rearm_load', o), repairDone: (o) => smp('repair_tool', o), touchdown: (o) => smp('touchdown', o),
  arrowHit: (o) => smp(num(o.gain, 1) >= 0.95 && ok('arrow_volley_hull') ? 'arrow_volley_hull' : 'arrow_hull_hit', o),
  boltHit: (o) => smp('bolt_hull_hit', o), boltPass: (o) => smp('bolt_pass', o), hullHit: (o) => smp('hull_hit_heavy', o), glassCrack: (o) => smp('glass_crack', o),
  rotorStrike: (o) => smp('rotor_strike', o), crashSpin: (o) => smp('crash_spin', o),
  crash: (o) => { const v = smp('crash_impact', o); if (v !== false) synth('crash', o, 0.45); return v; },
  horn: (o) => smp('war_horn', o), hornRout: (o) => smp('horn_rout', o), volleyLoose: (o) => smp('volley_loose', o), arrowWhoosh: (o) => smp('arrow_flyby', o),
  boltFire: (o) => smp('ballista_fire', o), bombardFire: (o) => smp('bombard_fire', o), flak: (o) => smp('flak_burst', o), trebRelease: (o) => smp('trebuchet_release', o),
  boulderWhoosh: (o) => smp('boulder_flyby', o), boulderImpact: (o) => smp('boulder_impact', o),
  scream: (o) => smp('scream_group', o), cheer: (o) => smp('cheer_burst', o),
  uiClick: (o) => smp('ui_confirm', o), uiHover: (o) => smp('ui_hover', o), uiBack: (o) => smp('ui_back', o),
  phase: (o) => smp('title_impact', o),
  win: () => winLoseByMusic('mus_victory'), lose: () => winLoseByMusic('mus_defeat'),   // the director plays the score cues
};
function play(name, opts) {
  if (!ctx || !graph || ctx.state === 'closed') return null;
  const o = opts || NO, h = HOOKS[name];
  if (h) { const v = h(o); if (v !== false) return v; }
  else if (!R[name] && SMP[name]) { const v = smp(name, o); return v === false ? null : v; }
  return synth(name, o);
}
// voice line by manifest id
function vo(id, o) {
  const e = SMP[id]; if (!ctx || !graph || !e || e.kind !== 'vo' || e.st !== 3) return null;
  const fx = e.m.fx, dry = fx === 'dry', b = e.bufs[0];
  const v = spawn('vo:' + id, b, VO_SPEC[fx] || VO_SPEC.radio, o || NO, 1, 0, vvoices, dry ? graph.vworld : graph.vox);
  if (!v || dry) return v;
  VOXS.until = Math.max(VOXS.until, v.end - 0.12);
  const st = graph.S.stat;   // faint static under long net calls
  if (st && fx === 'radio' && b.duration > 5) { const g = st.g.gain; g.cancelScheduledValues(v.t0); g.setTargetAtTime(CAL.stat, v.t0 + 0.15, 0.08); g.setTargetAtTime(0, v.end - 0.35, 0.1); }
  return v;
}
function stopVoice(v, fade = 0.08) {
  if (!v || !ctx) return; fadeV(v, fade);
  const i = vvoices.indexOf(v); if (i >= 0) vvoices.splice(i, 1);
  let until = 0; for (const x of vvoices) if (!x.name.startsWith('vo:enm') && x.end > until) until = x.end - 0.12;
  VOXS.until = Math.min(VOXS.until, Math.max(until, ctx.currentTime + fade));
  const st = graph && graph.S.stat; if (st) { st.g.gain.cancelScheduledValues(ctx.currentTime); st.g.gain.setTargetAtTime(0, ctx.currentTime, 0.05); }
}

// ------------------------------------------------------------- music
// Decks of decoded cues on the music bus. Beds loop sample-accurately and crossfade (equal power); stings overlay and can cut or dip
// the bed. A cue that is not decoded yet is requested at top priority and starts when it lands.
const MUS = { decks: [], want: null, wantO: null, keep: null };
const MUS_LVL = { mus_menu: 1, mus_approach: 1, mus_reveal: 1.05, mus_combat_1: 1, mus_combat_2: 1, mus_combat_3: 1, mus_lull: 1, mus_phase_sting: 0.95, mus_victory: 1, mus_defeat: 1, mus_results: 0.9 };
function hold(p, at) { if (p.cancelAndHoldAtTime) p.cancelAndHoldAtTime(at); else { p.cancelScheduledValues(at); p.setValueAtTime(p.value, at); } }
function eqRamp(p, at, dur, from, to) {   // 4-segment equal-power fade
  for (let i = 1; i <= 4; i++) { const x = i / 4 * Math.PI / 2; p.linearRampToValueAtTime(to > from ? from + (to - from) * Math.sin(x) : to + (from - to) * Math.cos(x), at + dur * i / 4); }
}
function fadeDeck(d, at, dur) {
  if (d.out) return; d.out = true;
  try { hold(d.g.gain, at); eqRamp(d.g.gain, at, Math.max(0.02, dur), d.lvl, 0); d.src.stop(at + dur + 0.05); } catch (e) { /* noop */ }
  d.end = Math.min(d.end, at + dur + 0.1);
}
function bedDeck() { for (let i = MUS.decks.length - 1; i >= 0; i--) { const d = MUS.decks[i]; if (!d.sting && !d.out) return d; } return null; }
function musPlay(id, o) {
  o = o || NO; if (!ctx || !graph) return false;
  const e = SMP[id]; if (!e || e.kind !== 'mus' || e.st === 4) return false;
  const sting = !e.loop;
  if (!sting) { const cur = bedDeck(); if (cur && cur.id === id) { MUS.want = null; return true; } }
  if (e.st !== 3) { request(id, -1); pump(); if (!sting) { MUS.want = id; MUS.wantO = o; } else blog(`MUS sting ${id} not decoded yet - skipped`); return false; }
  if (MUS.want === id) MUS.want = null;
  const now = ctx.currentTime, at = now + Math.max(0, num(o.delay, 0)), fade = Math.max(0.02, num(o.fade, 2.5));
  for (const d of MUS.decks) {
    if (d.out) continue;
    // a new bed fades the old bed (stings ring out unless cutStings); a sting cuts the bed only when asked
    const fadeIt = sting ? (o.cut === 'all' || (!!o.cut && !d.sting)) : (!d.sting || !!o.cutStings);
    if (fadeIt) fadeDeck(d, at, sting ? num(o.cutFade, 0.5) : (d.sting ? num(o.stingFade, fade) : fade));
    else if (sting && o.dip && !d.sting) { const g = d.g.gain, lv = d.lvl; try { hold(g, at); g.linearRampToValueAtTime(lv * o.dip, at + 0.25); g.setValueAtTime(lv * o.dip, at + num(o.dipT, 2.5)); g.linearRampToValueAtTime(lv, at + num(o.dipT, 2.5) + 2); } catch (er) { /* noop */ } }
  }
  const b = e.bufs[0], src = ctx.createBufferSource(), g = ctx.createGain();
  src.buffer = b; if (e.loop) { src.loop = true; if (e.le > e.ls) { src.loopStart = e.ls; src.loopEnd = e.le; } }
  const lvl = num(o.gain, 1) * (MUS_LVL[id] || 1);
  g.gain.value = 0; src.connect(g).connect(graph.mus);
  g.gain.setValueAtTime(0, at); eqRamp(g.gain, at, sting ? num(o.fadeIn, 0.03) : fade, 0, lvl);
  src.start(at, clamp(num(o.offset, 0), 0, b.duration - 0.1));
  const d = { id, src, g, lvl, sting, out: false, t0: at, end: sting ? at + b.duration + 0.1 : Infinity };
  src.onended = () => { try { g.disconnect(); } catch (er) { /* noop */ } };
  MUS.decks.push(d);
  blog(`MUS ${sting ? 'sting' : 'bed'} ${id}${o.delay ? ' +' + num(o.delay, 0).toFixed(1) + 's' : ''} fade=${(sting ? num(o.fadeIn, 0.03) : fade).toFixed(1)}`);
  return true;
}
function musStop(fade = 2) { MUS.want = null; if (!ctx) return; for (const d of MUS.decks) fadeDeck(d, ctx.currentTime, fade); }
function musUpdate() {
  if (MUS.want && ok(MUS.want)) musPlay(MUS.want, MUS.wantO);
  const now = ctx.currentTime;
  for (let i = MUS.decks.length - 1; i >= 0; i--) if (MUS.decks[i].end < now) MUS.decks.splice(i, 1);
}

export const audio = {
  onLog: null,
  ext: EXT,
  init() {
    if (ctx) { if (ctx.state === 'suspended') ctx.resume().catch(() => {}); return; }
    const AC = typeof AudioContext !== 'undefined' ? AudioContext : (typeof webkitAudioContext !== 'undefined' ? webkitAudioContext : null); // eslint-disable-line no-undef
    if (!AC) return;
    try {
      ctx = new AC({ latencyHint: 'interactive' });
      SR = ctx.sampleRate;
      graph = new Graph(ctx);
      this.setVolume(vol.master, vol.sfx, vol.amb, vol.music, vol.voice);
      if (ctx.state === 'suspended') ctx.resume().catch(() => {});
      preparing = prepare();
      loadBank();
    } catch (e) { if (typeof console !== 'undefined') console.warn('[audio] init failed', e); ctx = null; graph = null; }
  },
  // start fetching + decoding the sample bank (no AudioContext / user gesture needed)
  load() { loadBank(); },
  pump() { pump(); },
  resume() { if (ctx && ctx.state === 'suspended') ctx.resume().catch(() => {}); },
  suspend() { if (ctx && ctx.state === 'running') ctx.suspend().catch(() => {}); },
  // dev metering of the master bus: peak, rms and coarse spectrum balance
  meter() {
    const g = graph; if (!g || !g.an) return null;
    g.an.getFloatTimeDomainData(g._mb); let pk = 0, sq = 0; const mb = g._mb;
    for (let i = 0; i < mb.length; i++) { const x = mb[i], a = Math.abs(x); if (a > pk) pk = a; sq += x * x; }
    g.an.getByteFrequencyData(g._fb); const hz = ctx.sampleRate / 2048; let lo = 0, mid = 0, hi = 0;
    for (let i = 1; i < 1024; i++) { const f = i * hz, e = g._fb[i]; if (f < 250) lo += e; else if (f < 4000) mid += e; else hi += e; }
    return { pk, rms: Math.sqrt(sq / mb.length), lo, mid, hi };
  },
  // dev: rms per bus (post fader) — analysers are created on first use
  meterBus() {
    const g = graph; if (!g) return null;
    if (!g._ba) { g._ba = {}; g._bb = new Float32Array(2048); for (const [k, n] of [['sfx', g.sfx], ['amb', g.amb], ['mus', g.musDuck], ['vox', g.vox]]) { const a = ctx.createAnalyser(); a.fftSize = 2048; n.connect(a); g._ba[k] = a; } }
    const out = {}; for (const k in g._ba) { g._ba[k].getFloatTimeDomainData(g._bb); let sq = 0; for (let i = 0; i < 2048; i++) sq += g._bb[i] * g._bb[i]; out[k] = Math.sqrt(sq / 2048); }
    return out;
  },
  setVolume(master, sfx, ambience, music, voice) {
    vol = { master: clamp(num(master, vol.master), 0, 1), sfx: clamp(num(sfx, vol.sfx), 0, 1), amb: clamp(num(ambience, vol.amb), 0, 1), music: clamp(num(music, vol.music), 0, 1), voice: clamp(num(voice, vol.voice), 0, 1) };
    if (!graph) return;
    const t = ctx.currentTime;
    graph.master.gain.setTargetAtTime(0.9 * vol.master * vol.master, t, 0.03);
    graph.sfx.gain.setTargetAtTime(vol.sfx, t, 0.03); graph.amb.gain.setTargetAtTime(vol.amb, t, 0.03);
    graph.mus.gain.setTargetAtTime(MUS_BASE * vol.music * vol.music, t, 0.03); graph.vox.gain.setTargetAtTime(VOX_BASE * vol.voice * vol.voice, t, 0.03);
  },
  update(dt, s) {
    pump();
    if (!graph || !s) return;
    if (s.listener) L.p = s.listener; if (s.fwd) L.f = s.fwd; if (s.right) L.r = s.right;
    try {
      if (GUN.firing && !s.gunFiring) gunRelease(); GUN.firing = !!s.gunFiring;
      graph.update(clamp(num(dt, 0.016), 0, 0.2), s, play);
      musUpdate();
    } catch (e) { warnOnce('update', e); /* never break the frame */ }
  },
  play(name, opts) { try { return play(name, opts); } catch (e) { warnOnce('play ' + name, e); return null; } },
  // fade out a voice returned by play()/vo()
  stop(v, fade) { try { if (v && v.name && v.name.startsWith('vo:')) stopVoice(v, fade); else fadeV(v, num(fade, 0.05)); } catch (e) { /* noop */ } },
  vo(id, opts) { try { return vo(id, opts); } catch (e) { warnOnce('vo ' + id, e); return null; } },
  stopAll() {
    if (!ctx) return; const now = ctx.currentTime;
    for (const v of voices.slice()) kill(v, now, voices);
    for (const v of vvoices.slice()) kill(v, now, vvoices);
    voices.length = 0; vvoices.length = 0; VOXS.until = 0; GUN.n = 0; GUN.h = null;
    for (const k in lastPlay) delete lastPlay[k];
  },
  music: {
    play(id, o) { try { return musPlay(id, o); } catch (e) { warnOnce('music ' + id, e); return false; } },
    stop(fade) { try { musStop(fade); } catch (e) { /* noop */ } },
    get bed() { const d = bedDeck(); return d ? d.id : (MUS.want || null); },
    stingLeft() { if (!ctx) return 0; let t = 0; for (const d of MUS.decks) if (d.sting && !d.out) t = Math.max(t, d.end - ctx.currentTime); return t; },
    // keep these decoded, drop the rest (compressed bytes stay for a quick re-decode)
    keep(ids) { MUS.keep = ids; for (const id in SMP) { const e = SMP[id]; if (e.kind !== 'mus') continue; if (ids.includes(id)) request(id, 0.5); else if (!MUS.decks.some(d => d.id === id)) evict(id); } },
  },
  has(id) { return ok(id); },
  dur(id) { const e = SMP[id]; return e && e.bufs ? e.bufs[0].duration : (e && e.m && e.m.dur) || 0; },
  request(id, prio = 2) { request(id, prio); },
  set busy(b) { BANK.busy = !!b; },
  get voiceActive() { return !!ctx && VOXS.until > ctx.currentTime; },
  get now() { return ctx ? ctx.currentTime : 0; },
  get bank() { return BANK; },
  get ready() { return ready; },
  get context() { return ctx; },
  whenReady() { return preparing || Promise.resolve(); },

  // ---- test hooks (used by tools/audio_test) ----
  _names() { return Object.keys(R); },
  _loopNames() { return Object.keys(LOOPS); },
  _smp(id) { return SMP[id]; },
  _sp(id) { return SP[id]; },
  _cal: CAL,
  _rec(name) { return R[name]; },
  async _render(name, sr) { if (sr) SR = sr; return R[name] ? renderOne(name) : renderLoop(name); },
  async _renderState(state, seconds = 3, sr = 48000) {
    SR = sr; ensureSynthBufs();
    for (const n of Object.keys(LOOPS)) if (!BUF[n]) BUF[n] = [await renderLoop(n)];
    const oc = new OfflineCtx(2, Math.ceil(seconds * SR), SR), g = new Graph(oc);
    g.attachSamples();
    g.update(1, state, null);                 // dt=1 → smoothing snaps
    // setTargetAtTime needs time to settle; that is part of what we measure
    return oc.startRendering();
  },
};
export default audio;
