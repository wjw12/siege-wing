// Siege Wing — audio director: decides *what* plays *when*. Listens to G.events and polls game state each
// frame (no per-frame allocation) to drive voice lines (priority queue with per-group cooldowns, warnings
// pre-empt chatter), the music state machine, enemy shouts placed in the world and the world-audio cues
// that have no other home (chants, shield walls, alarm bells, fire pots, cannon burst/tail edges...).
// audio.js does the sound; this module only sequences it.
import { G, V3, clamp, sat } from './core.js';
import { L, riverX } from './terrain.js';
import { dev, Q } from './dev.js';
import { settings } from './input.js';
import { audio } from './audio.js';
import { heli, SUBS } from './heli.js';
import { weapons } from './weapons.js';
import { crowd } from './crowd.js';
import { castle } from './castle.js';
import { threats } from './threats.js';
import { mission } from './mission.js';
import { fx } from './fx.js';
import { ui } from './ui.js';
import { world } from './world.js';

const rnd = (a, b) => a + Math.random() * (b - a);
// ---------------------------------------------------------------- line groups
// name: [ids, prio, cooldown s, max wait s, cooldown key]. prio 5 critical (pre-empts anything lower), 4 warning / threat call
// (pre-empts chatter + events), 3 mission, 2 event, 1 chatter.
const LN = {
  checkin: [['plt_checkin'], 3, 0, 8], brief: [['cmd_brief'], 3, 0, 12], appr1: [['cmd_appr_1'], 3, 0, 40], cleared: [['plt_cleared'], 3, 0, 40],
  appr2: [['cmd_appr_2'], 3, 0, 30], appr3: [['cmd_appr_3'], 3, 0, 30], appr4: [['cmd_appr_4'], 3, 0, 25],
  revealP: [['plt_reveal'], 4, 0, 4], revealC: [['cmd_reveal'], 4, 0, 8], p1: [['cmd_p1_start'], 3, 0, 25],
  p2: [['cmd_p2_start'], 3, 0, 15], pavise: [['cmd_pavise'], 3, 0, 20], p3: [['cmd_p3_start'], 3, 0, 15], relaid: [['cmd_relaid'], 3, 0, 20],
  restart: [['cmd_restart_1', 'cmd_restart_2', 'cmd_restart_3'], 3, 0, 6],
  routed: [['cmd_routed_1', 'cmd_routed_2', 'cmd_routed_3', 'cmd_routed_4'], 2, 0, 8], routedHalf: [['cmd_routed_half'], 2, 0, 10], routedLast: [['cmd_routed_last'], 2, 0, 10],
  running: [['plt_kill_2'], 2, 8, 3], panic: [['cmd_panic_1', 'cmd_panic_2', 'gun_fear'], 2, 25, 4],
  tower: [['cmd_tower_1', 'cmd_tower_2', 'cmd_tower_3'], 2, 0, 10], towerLast: [['cmd_tower_last'], 2, 0, 10], towerP: [['plt_kill_3'], 2, 4, 3],
  engine: [['cmd_engine_1', 'cmd_engine_2', 'cmd_engine_3', 'gun_destroyed_1'], 2, 8, 6],
  dusk1: [['cmd_dusk_1'], 3, 0, 20], dusk2: [['cmd_dusk_2'], 3, 0, 20],
  win: [['cmd_win'], 5, 0, 15], winP: [['plt_win'], 5, 0, 20],
  loseShot: [['cmd_lose_shot'], 5, 0, 15], loseCrash: [['cmd_lose_crash'], 5, 0, 15], loseBounds: [['cmd_lose_bounds'], 5, 0, 15],
  bndWarnB: [['bty_bnd_warn'], 4, 25, 2], bndWarnC: [['cmd_bnd_warn'], 3, 25, 6], bndOut: [['cmd_bnd_out', 'bty_bnd_out'], 4, 20, 1.5], turnback: [['plt_turnback'], 3, 10, 3],
  btyAmmo: [['bty_ammo'], 3, 60, 3], lowAmmo: [['cmd_low_ammo', 'plt_winchester'], 2, 60, 8],
  padP: [['plt_pad'], 2, 20, 4], padC: [['cmd_pad'], 2, 20, 8], repaired: [['cmd_repaired', 'bty_repair'], 2, 3, 4], nominal: [['bty_nominal'], 2, 10, 4], rearm: [['bty_rearm'], 2, 10, 4],
  rearmed: [['cmd_rearmed'], 2, 20, 6], lifting: [['plt_lifting'], 2, 20, 4],
  btyHull: [['bty_hull'], 4, 0, 3], hullCrit: [['cmd_hull_crit'], 3, 0, 10], nag: [['cmd_nag'], 1, 90, 5],
  guns: [['plt_guns_1', 'plt_guns_2', 'plt_guns_3'], 1, 12, 0.8], rockets: [['plt_rockets_1', 'plt_rockets_2'], 1, 10, 0.8, 'rk'], ripple: [['plt_rockets_3'], 1, 10, 0.8, 'rk'],
  lock: [['plt_lock_1', 'plt_lock_2', 'gun_lock', 'bty_lock'], 2, 6, 1], missile: [['plt_missile_1', 'plt_missile_2'], 1, 4, 0.8],
  flares: [['plt_flares_1', 'plt_flares_2'], 2, 6, 0.8], flaresOut: [['bty_flares_out'], 2, 30, 4],
  hit: [['plt_hit_1'], 1, 8, 1, 'hit'], hitBig: [['plt_hit_2'], 2, 8, 1, 'hit'], hitArrows: [['plt_hit_3'], 2, 8, 1, 'hit'], hitBolt: [['plt_hit_4'], 2, 8, 1.5, 'hit'],
  close: [['plt_close_1', 'plt_close_2'], 2, 8, 1],
  btyJam: [['bty_jam'], 4, 6, 1.5], jamCannon: [['plt_jam_cannon'], 2, 6, 3], jamPod: [['plt_jam_pod'], 2, 6, 3],
  btyOverheat: [['bty_overheat'], 4, 8, 1.5], overheat: [['plt_overheat'], 2, 15, 3],
  dryCannon: [['plt_dry_cannon'], 2, 20, 3], dryMissiles: [['plt_dry_missiles'], 2, 20, 3], dryRockets: [['plt_dry_rockets'], 2, 20, 3],
  killBig: [['plt_kill_1'], 1, 25, 2], goodHits: [['gun_destroyed_2'], 1, 25, 2], splash: [['plt_kill_4'], 1, 10, 1.5],
  bSink: [['bty_sink'], 4, 3, 0.5], sinkP: [['plt_sink'], 4, 12, 1],
  mayday1: [['plt_mayday_1'], 5, 0, 1.5], mayday2: [['plt_mayday_2'], 5, 0, 1.5], brace: [['plt_mayday_3'], 5, 0, 1],
  volley: [['gun_volley_1', 'gun_volley_2'], 4, 22, 1.2, 'vol'], volleyClimb: [['gun_volley_3'], 4, 22, 1.2, 'vol'],
  ballista: [['gun_ballista_1', 'gun_ballista_2'], 4, 7, 0.5, 'bal'], bolt: [['gun_ballista_3'], 4, 7, 0.3, 'bal'],
  bombard: [['gun_bombard_1'], 3, 12, 1, 'bom'], flak: [['gun_bombard_2'], 3, 12, 1, 'bom'],
  treb: [['gun_treb_1'], 3, 15, 1], boulder: [['gun_treb_2'], 4, 10, 0.8],
  spotBal: [['gun_spot_ballista'], 2, 120, 3], spotTreb: [['gun_spot_treb'], 2, 120, 3], spotBanner: [['gun_spot_banner'], 2, 0, 4],
  warlord: [['gun_warlord'], 3, 0, 4], smoke: [['gun_smoke'], 2, 60, 3],
  low: [['gun_low'], 4, 15, 0.6, 'prox'], trees: [['gun_trees'], 4, 15, 0.6, 'prox'], wall: [['gun_wall'], 4, 15, 0.6, 'prox'],
  bAlt: [['bty_altitude'], 4, 5, 0.5], bPull: [['bty_pullup'], 5, 3, 0.3], bRpm: [['bty_rpm'], 4, 8, 0.5], bCeil: [['bty_ceiling'], 3, 15, 1],
};
for (const s of ['engine', 'tail', 'hyd', 'rotor']) LN['bSub_' + s] = [['bty_' + s], 4, 4, 2];
for (const s of SUBS) LN['pSub_' + s] = [['plt_sub_' + s], 3, 4, 8];
for (let n = 1; n <= 10; n++) LN['n' + n] = [['bty_' + n], 5, 0, 0.4];
// enemy shouts (placed in the world, own limiter): [ids, cooldown s]
const EN = {
  loose: [['enm_loose_1', 'enm_loose_2', 'enm_loose_3'], 7], shields: [['enm_shields_1', 'enm_shields_2'], 20], hold: [['enm_hold_1', 'enm_hold_2'], 18],
  dragon: [['enm_dragon_1', 'enm_dragon_2'], 12], run: [['enm_run_1', 'enm_run_2'], 3], ballista: [['enm_ballista'], 15], bombard: [['enm_bombard'], 14], treb: [['enm_treb'], 15],
  firepots: [['enm_firepots'], 0], taunt1: [['enm_warlord_taunt_1'], 0], taunt2: [['enm_warlord_taunt_2'], 30], taunt3: [['enm_warlord_taunt_3'], 45],
  victory1: [['enm_victory_1'], 0], victory2: [['enm_victory_2'], 0],
};
// music residency per stage (decoded on entry, others evicted)
const KEEP = {
  menu: ['mus_menu', 'mus_approach', 'mus_reveal', 'mus_defeat'],
  0: ['mus_approach', 'mus_reveal', 'mus_combat_1', 'mus_phase_sting', 'mus_defeat'],
  1: ['mus_combat_1', 'mus_lull', 'mus_phase_sting', 'mus_combat_2', 'mus_defeat'],
  2: ['mus_combat_2', 'mus_lull', 'mus_phase_sting', 'mus_combat_3', 'mus_defeat'],
  3: ['mus_combat_3', 'mus_lull', 'mus_victory', 'mus_defeat', 'mus_results'],
  end: ['mus_victory', 'mus_defeat', 'mus_results', 'mus_combat_1'],
};

// ---------------------------------------------------------------- state
let T = 0;                        // director clock (game time, frozen while paused)
const queue = [];                 // { g, at, exp }
let cur = null;                   // { g, id, v, prio, t0 }
let lastEnd = -99;
const lastSaid = {}, lastId = {};
let enemyNext = 0; const enemyLast = {};
let appState = 'loading', prevApp = '', prevMS = 'idle', prevTime = 0, prevPhase = -1, prevStep = 0, runs = 0, approachRuns = 0, keepKey = '';
const R = {};                      // per-run flags / edges (reset on run start)
const camR = new V3(), _v = new V3();
const seen = new WeakSet();
let fPrev = null, ePrev = null, bomVo = null, shieldT = null, missTrack = [], missTrack2 = [];
let amT = 0, chantT = 8, proxT = 0, killRate = 0, cryT = 0;

function textOf(id) { const e = audio._smp(id); return e && e.m && e.m.text ? e.m.text : ''; }
let lastMsg = '', lastP = 0;
const logBuf = [];   // one /__log POST per frame: concurrent appends from a burst can clobber each other
function vlog(msg) { if (dev.on) { lastMsg = msg.slice(0, 80); logBuf.push(msg); } }
function flushLog() { if (logBuf.length) { dev.log(logBuf.join('\n')); logBuf.length = 0; } }

// ---------------------------------------------------------------- voice queue
function say(g, o) {
  const d = LN[g]; if (!d) return false;
  const cd = d[2], key = d[4] || g;
  if (cd && lastSaid[key] !== undefined && T - lastSaid[key] < cd) return false;
  if (cur && cur.g === g) return false;
  for (let i = 0; i < queue.length; i++) if (queue[i].g === g) return false;
  const delay = o && o.delay ? o.delay : 0;
  queue.push({ g, at: T + delay, exp: T + delay + (o && o.exp ? o.exp : d[3]) });
  if (queue.length > 10) { // overflow: drop the lowest-priority, oldest item
    let w = 0; for (let i = 1; i < queue.length; i++) if (LN[queue[i].g][1] < LN[queue[w].g][1]) w = i;
    queue.splice(w, 1);
  }
  return true;
}
function dropQueued(maxPrio) { for (let i = queue.length - 1; i >= 0; i--) if (LN[queue[i].g][1] <= maxPrio) queue.splice(i, 1); }
function loaded(g) { const ids = LN[g][0]; for (let k = 0; k < ids.length; k++) if (audio.has(ids[k])) return true; return false; }
function pickId(g) {
  const ids = LN[g][0]; let best = null;
  for (let k = 0; k < ids.length; k++) {
    const id = ids[(k + ((Math.random() * ids.length) | 0)) % ids.length];
    if (!audio.has(id)) continue;
    if (id !== lastId[g] || ids.length === 1) return id; best = best || id;
  }
  return best;
}
function startLine(it, prio) {
  const id = pickId(it.g); if (!id) return false;
  const v = audio.vo(id); if (!v) return false;
  cur = { g: it.g, id, v, prio, t0: T, it };
  lastId[it.g] = id; lastSaid[LN[it.g][4] || it.g] = T;
  { const e = audio._smp(id); G.events.dispatchEvent(new CustomEvent('subtitle', { detail: { text: textOf(id), speaker: e && e.m ? e.m.speaker : '', dur: Math.max(1.2, v.end - audio.now) } })); }
  vlog(`VO t=${mission.time.toFixed(1)} ph=${mission.phase} ${id} [${it.g} p${prio}] "${textOf(id).slice(0, 60)}"`);
  return true;
}
function pumpVO() {
  const now = audio.now;
  if (cur && now >= cur.v.end - 0.03) { cur = null; lastEnd = T; }
  for (let i = queue.length - 1; i >= 0; i--) if (T > queue[i].exp) queue.splice(i, 1);
  // best eligible item: highest priority, FIFO within a priority. A mission line that is not decoded yet stays queued and
  // holds back later lines of its priority (so the briefing never overtakes the check-in). During the boundary countdown,
  // a crash or after the run ends only critical lines start.
  const floor = R.outside || heli.state === 'crashing' || mission.state === 'won' || mission.state === 'lost' ? 5 : 0;
  let bi = -1, bp = -1, block = 0;
  for (let i = 0; i < queue.length; i++) {
    const it = queue[i], p = LN[it.g][1];
    if (it.at > T || p < floor || p <= block) continue;
    if (!loaded(it.g)) { if (p >= 3) block = p; continue; }
    if (p > bp) { bp = p; bi = i; }
  }
  if (bi < 0) return;
  const it = queue[bi];
  if (cur) {
    // critical pre-empts anything lower; warnings pre-empt chatter + events
    if (!(bp >= 4 && bp > cur.prio && (bp === 5 || cur.prio <= 2))) return;
    const prog = (now - cur.v.t0) / Math.max(0.1, cur.v.dur);
    vlog(`VO cut ${cur.id} at ${(prog * 100).toFixed(0)}% for ${it.g}`);
    audio.stop(cur.v, 0.06);
    if (cur.prio >= 3 && prog < 0.5 && !cur.it.again && !queue.some(q => q.g === cur.g)) queue.push({ g: cur.g, at: T + 0.3, exp: T + 12, again: true });   // a cut mission line comes back once
    cur = null; lastEnd = T - 1;
  }
  const gap = bp >= 4 ? 0.08 : bp === 1 ? 2.5 : 0.35;
  if (T - lastEnd < gap) return;
  queue.splice(bi, 1);
  if (!startLine(it, bp)) lastEnd = T - gap + 0.05;
}
// enemy shout at a world position (separate limiter: one at a time, cooldown per group, only within earshot)
function enemy(g, x, y, z, delay = 0) {
  const d = EN[g]; if (!d || !G.camera) return false;
  if (T < enemyNext) return false;
  if (d[1] && enemyLast[g] !== undefined && T - enemyLast[g] < d[1]) return false;
  const c = G.camera.position; if (Math.hypot(x - c.x, y - c.y, z - c.z) > 520) return false;
  const ids = d[0]; let id = ids[(Math.random() * ids.length) | 0]; if (!audio.has(id)) { id = ids.find(i => audio.has(i)); if (!id) return false; }
  const v = audio.vo(id, { pos: [x, y, z], delay }); if (!v) return false;
  enemyLast[g] = T; enemyNext = T + delay + v.dur + 0.8;
  { const e = audio._smp(id); G.events.dispatchEvent(new CustomEvent('subtitle', { detail: { text: textOf(id), speaker: e && e.m ? e.m.speaker : 'soldier', dur: Math.max(1.2, v.dur), delay, world: true } })); }
  vlog(`ENM t=${mission.time.toFixed(1)} ${id} "${textOf(id)}" d=${Math.hypot(x - c.x, z - c.z).toFixed(0)}m`);
  return true;
}
function sfx(id, x, y, z, o) { const p = { pos: [x, y, z] }; if (o) Object.assign(p, o); return audio.play(id, p); }

// ---------------------------------------------------------------- music
function bed(id, fade = 3, cutStings = false) { if (audio.music.bed !== id) audio.music.play(id, { fade, cutStings, stingFade: 1.5 }); }
let keepT = 0;
function keep(k) { if (keepKey === k && T < keepT) return; keepKey = k; keepT = T + 2; audio.music.keep(KEEP[k]); }   // re-applied every 2 s: covers a manifest that lands late
function updateMusic() {
  if (appState === 'menu') { keep('menu'); bed('mus_menu', 3, true); return; }
  if (appState !== 'play') return;
  const ms = mission.state;
  if (ms === 'won' || ms === 'lost') {
    keep('end');
    if (ui.current === 'end' && !R.results && audio.music.stingLeft() < 3) { R.results = true; audio.music.play('mus_results', { fade: 3.5 }); }
    return;
  }
  if (ms !== 'play') return;
  keep(mission.phase);
  if (mission.phase === 0) { bed('mus_approach', 1.5); return; }
  if (T < R.holdMusic) return;   // reveal / phase sting is driving the music
  bed(R.lull ? 'mus_lull' : 'mus_combat_' + Math.min(3, mission.phase), R.lull ? 5 : 3.5);
}
function updateLull(dt) {
  const p = heli.pos, dPad = Math.hypot(p.x - L.PAD.x, p.z - L.PAD.z), quiet = T - R.combatT;
  const closing = -((heli.vel.x * (p.x - L.PAD.x) + heli.vel.z * (p.z - L.PAD.z)) / (dPad || 1));   // m/s toward the pad
  const settled = T - R.phaseT > 20 && quiet > 6;
  const want = heli.onPad || weapons.rearming || (settled && (dPad < 250 || (dPad < 700 && closing > 8))) || (T - R.phaseT > 30 && quiet > 40);
  if (want === R.lull) { R.lullT = 0; return; }
  R.lullT += dt;
  if (R.lullT > (want ? 3 : quiet < 1 ? 0 : 2)) { R.lull = want; R.lullT = 0; vlog(`MUS lull=${want} t=${mission.time.toFixed(1)} dPad=${dPad.toFixed(0)} quiet=${quiet.toFixed(0)}`); }
}

// ---------------------------------------------------------------- run lifecycle
function resetRun() {
  queue.length = 0; cur = null; lastEnd = T - 1; enemyNext = 0;
  for (const k in lastSaid) delete lastSaid[k]; for (const k in enemyLast) delete enemyLast[k];
  Object.assign(R, { combatT: T, phaseT: T, lull: false, lullT: 0, holdMusic: 0, results: false, tally: false, hullCrit: false, pad: heli.onPad, armed: false, outside: false, warn: false, edge: false,
    nextN: 11, lastKillT: T, gunT: -1, gunSaid: false, salvoT: -9, salvoN: 0, salvoAt: 0, lastRocketT: -9, rockets: weapons.rocketsFired, missiles: weapons.missilesFired,
    hitT: heli.lastHitT, hull: heli.hull, arrowN: 0, arrowT: 0, locked: false, jamT: false, jamP: false, overheated: false, ammoC: weapons.ammo.cannon, ammoR: weapons.ammo.rockets, ammoM: weapons.ammo.missiles,
    lowAmmo: false, w120: false, w45: false, village: false, warlordSeen: false, taunt1: false, taunt3T: T + 20, banner: false, braced: false, lose: null, mayday: false, subs: SUBS.map(s => heli.sub[s]),
    vrs: false, dead: false });
  killRate = 0; fPrev = null; ePrev = null; bomVo = null; shieldT = null; missTrack.length = 0;
}
function onStart() {
  runs++; resetRun(); prevStep = 0; prevPhase = mission.phase;
  audio.play('mfd_boot');
  if (mission.approach) {
    approachRuns++; say('checkin', { delay: 0.6 }); if (approachRuns === 1) say('brief', { delay: 0.6 });
  } else {
    if (runs > 1) say('restart', { delay: 0.4 }); if (mission.phase === 1) say('p1', { delay: 0.6 });
    audio.music.play('mus_combat_' + clamp(mission.phase, 1, 3), { fade: 2, cutStings: true });
  }
  vlog(`DIR run ${runs} start approach=${mission.approach} phase=${mission.phase}`);
}
function onPhase(n, from) {
  R.lastKillT = T; R.combatT = T; R.lull = false; R.phaseT = T;
  if (from === 0 && n === 1) {
    dropQueued(3);
    audio.music.play('mus_reveal', { cut: true, cutFade: 1.4 }); R.holdMusic = T + 8.5;
    audio.music.play('mus_combat_1', { delay: 8.5, fade: 6 });
    say('revealP', { delay: 0.8 }); say('revealC', { delay: 0.9 }); say('p1', { delay: 2 });
    const f = nearestForm('infantry'); if (f) sfx('war_chant', f.cx, f.cy + 2, f.cz, { delay: 2.5, gain: 1.2 });
  } else if (n > from && n >= 2) {
    dropQueued(2);
    audio.music.play('mus_phase_sting', { dip: 0.3, dipT: 2.5 }); R.holdMusic = T + 1.2;
    audio.music.play('mus_combat_' + Math.min(3, n), { delay: 1.2, fade: 4.5 });
    sfx('horn_alarm', L.CASTLE.x, L.CASTLE.y + 22, L.CASTLE.z, { delay: 0.6 });
    if (n === 2) {
      say('p2', { delay: 1 }); say('pavise', { delay: 7 });
      let k = 0; for (const f of crowd.forms) if (f.pavise) sfx('shield_wall_up', f.cx + 10, f.cy + 1.5, f.cz, { delay: 2 + 0.7 * k++ });
    } else if (n === 3) {
      say('p3', { delay: 1 }); say('relaid', { delay: 7 });
      const w = crowd.warlord; if (w >= 0) enemy('firepots', crowd.x[w], crowd.y[w] + 2, crowd.z[w], 0.4);
      const pots = castle.firePots; for (let i = 0; i < pots.length; i++) if (i % 2 === 0) sfx('firepot_ignite', pots[i].x, pots[i].y + 1.7, pots[i].z, { delay: 1 + i * 0.35 });
    }
  }
  vlog(`DIR phase ${from}->${n} t=${mission.time.toFixed(1)}`);
}
function nearestForm(kind) {
  let best = null, bd = 1e9; const p = heli.pos;
  for (const f of crowd.forms) { if (f.routed || (kind && f.kind !== kind)) continue; const d = Math.hypot(f.cx - p.x, f.cz - p.z); if (d < bd) { bd = d; best = f; } }
  return best;
}

// ---------------------------------------------------------------- events
function onEvent(name, e) {
  if (appState !== 'play') return;
  const d = e.detail;
  switch (name) {
    case 'formationRouted': {
      R.combatT = T;
      if (d.kind === 'infantry') {
        let n = 0; for (const f of crowd.forms) if (f.kind === 'infantry' && f.routed) n++;
        if (n < 4) { say('running'); say(n === 2 ? 'routedHalf' : n === 3 ? 'routedLast' : 'routed', { delay: 1.5 }); }
      } else say('running');
      sfx('rout_stampede', d.cx, d.cy + 1, d.cz, { delay: 0.3 }); enemy('run', d.cx, d.cy + 2, d.cz, 0.5);
      break;
    }
    case 'formationPanic': say('panic', { delay: 0.6 }); enemy('dragon', d.cx, d.cy + 2, d.cz, 0.2); break;
    case 'structDestroyed':
      if (d.type === 'tower') {
        let n = 0; for (const t of castle.towers) if (t.kind === 'gate' && !t.alive) n++;
        say('towerP', { delay: 0.5 });
        if (d.kind !== 'gate' || n < 4) say(d.kind === 'gate' && n === 3 ? 'towerLast' : 'tower', { delay: 2.5 });
      }
      break;
    case 'engineDestroyed': say('engine', { delay: 0.8 }); break;
    case 'subDegraded': say('bSub_' + d); say('pSub_' + d, { delay: 0.2 }); break;
    case 'padLanding': say('padP', { delay: 0.6 }); say('padC', { delay: 1 }); break;
    case 'warlordDead': { const w = crowd.warlord; if (w >= 0) sfx('warlord_death', crowd.x[w], crowd.y[w] + 1.6, crowd.z[w]); break; }
    case 'heliDown':
      if (heli.state === 'crashing' && !R.mayday) { R.mayday = true; say(heli.sub.tail < 15 || String(d).startsWith('rotor') ? 'mayday2' : 'mayday1'); }
      { const f = nearestForm(null); if (f) enemy('victory2', f.cx, f.cy + 2, f.cz, 1.5); }
      break;
    case 'missionEnd':
      dropQueued(4);
      if (d) {
        audio.music.play('mus_victory', { cut: 'all', cutFade: 1.5, delay: 0.3 });
        say('win', { delay: 1.4 }); say('winP', { delay: 2 });
      } else {
        audio.music.play('mus_defeat', { cut: 'all', cutFade: 1.2, delay: 0.8 });
        R.lose = mission.cause || 'shot';
        sfx('cheer_burst', L.FIELD.x, 30, 0, { delay: 2 }); enemy('victory1', L.FIELD.x + 60, 30, 0, 2.6);
      }
      vlog(`DIR missionEnd win=${d} cause=${mission.cause}`);
      break;
    case 'flares': R.combatT = T; say('flares'); if (weapons.ammo.flares === 0) say('flaresOut', { delay: 1.5 }); break;
    case 'bombardFired': R.combatT = T; say('bombard', { delay: 0.25 }); break;
    case 'kill': {
      killRate += 1; R.lastKillT = T; R.combatT = T;
      const i = d, c = G.camera && G.camera.position;
      if (c && T - cryT > 0.3 && Math.random() < 0.5 && i >= 0) { const dd = Math.hypot(crowd.x[i] - c.x, crowd.z[i] - c.z); if (dd < 170) { cryT = T; sfx('death_cry', crowd.x[i], crowd.y[i] + 1.5, crowd.z[i]); } }
      break;
    }
  }
}

// ---------------------------------------------------------------- polling (play)
function treeOrWall(c) {
  if (proxHit) return; const p = heli.pos, ry = p.y + heli.rotorY;
  if (c.y1 < ry - 3 || c.y0 > ry + 3) return;
  let d;
  if (c.t === 0) d = Math.hypot(p.x - c.x, p.z - c.z) - c.r;
  else { const dx = p.x - c.x, dz = p.z - c.z, lx = dx * c.c + dz * c.s, lz = -dx * c.s + dz * c.c; d = Math.hypot(Math.max(0, Math.abs(lx) - c.hx), Math.max(0, Math.abs(lz) - c.hz)); }
  if (d < heli.rotorR + 5) proxHit = c.kind === 'tree' ? 'trees' : (c.kind === 'tower' || c.kind === 'wall' || c.kind === 'keep') ? 'wall' : null;
}
let proxHit = null;
function pollPlay(dt) {
  const fly = heli.state === 'fly', p = heli.pos, ph = mission.phase, ms = mission.state;
  // ---- tutorial coaching (phase 0)
  if (ph === 0 && mission.tutorialStep !== prevStep) {
    const s = mission.tutorialStep; prevStep = s;
    if (s === 1) { say('appr1'); say('cleared'); } else if (s === 2) say('appr2'); else if (s === 4) say('appr3'); else if (s === 6) say('appr4');
  }
  if (ph !== prevPhase) { const from = prevPhase; prevPhase = ph; if (ms === 'play') onPhase(ph, from); }
  // ---- end of run: lose line once the wreck settles
  if (R.lose && (heli.state === 'gone' || heli.state === 'fly' || (heli.state === 'dead' && heli.crashT > 1.0))) {
    const c = R.lose; R.lose = null;
    if (!/night/.test(c)) say(/left the combat/.test(c) ? 'loseBounds' : c === 'shot' ? 'loseShot' : 'loseCrash', { delay: heli.state === 'dead' ? 0.6 : 0.3 });   // night fall: the score speaks
  }
  if (heli.state === 'crashing' && !R.braced && (heli.agl < 40 || heli.crashT > 2.6)) { R.braced = true; say('brace'); }
  if (ms === 'won' || ms === 'lost') {
    if (ui.current === 'end' && !R.tally) { R.tally = true; audio.play('score_tally'); }
    return;
  }
  if (ms !== 'play') return;
  // ---- combat bookkeeping for the music
  if (weapons.firing || threats.volleyWarn > 0 || threats.aimWarn > 0 || G.time - heli.lastHitT < 0.1) R.combatT = T;
  killRate *= Math.exp(-dt / 1.5);
  if (killRate > 13) { say('killBig'); killRate = 0; }
  if (weapons.firing && killRate > 6) say('goodHits');
  if (ph >= 1 && T - R.lastKillT > 45 && !R.lull && !heli.onPad) { say('nag'); R.lastKillT = T; }
  // ---- weapons
  if (weapons.firing && R.gunT < 0) { R.gunT = T; R.gunSaid = false; }
  if (!weapons.firing) R.gunT = -1; else if (!R.gunSaid && T - R.gunT > 0.35) { R.gunSaid = true; say('guns'); }
  if (weapons.rocketsFired > R.rockets) {
    R.rockets = weapons.rocketsFired; R.combatT = T;
    if (T - R.lastRocketT > 0.6) { R.salvoT = T; R.salvoN = 0; R.salvoAt = 1; } R.salvoN++; R.lastRocketT = T;
  }
  if (R.salvoAt && T - R.salvoT > 0.6) { R.salvoAt = 0; say(R.salvoN >= 3 ? 'ripple' : 'rockets'); }
  if (weapons.missilesFired > R.missiles) { R.missiles = weapons.missilesFired; R.combatT = T; say('missile'); }
  if (weapons.lock.locked && !R.locked) say('lock'); R.locked = weapons.lock.locked;
  // splash: a guided missile vanished and its target is dead
  for (let i = 0; i < missTrack.length; i++) { const m = missTrack[i]; if (weapons.missiles.indexOf(m) < 0 && m.target && m.target.ref && m.target.ref.alive === false) say('splash', { delay: 0.3 }); }
  missTrack2.length = 0; for (const m of weapons.missiles) missTrack2.push(m); { const t = missTrack; missTrack = missTrack2; missTrack2 = t; }
  const jt = weapons.jam.turret, jp = weapons.jam.podL || weapons.jam.podR;
  if (jt && !R.jamT) { say('btyJam'); say('jamCannon', { delay: 0.2 }); } if (jp && !R.jamP) { say('btyJam'); say('jamPod', { delay: 0.2 }); } R.jamT = jt; R.jamP = jp;
  if (weapons.overheated && !R.overheated) { say('btyOverheat'); say('overheat', { delay: 0.2 }); } R.overheated = weapons.overheated;
  const a = weapons.ammo;
  if (a.cannon === 0 && R.ammoC > 0) say('dryCannon'); if (a.rockets === 0 && R.ammoR > 0) say('dryRockets'); if (a.missiles === 0 && R.ammoM > 0) say('dryMissiles');
  R.ammoC = a.cannon; R.ammoR = a.rockets; R.ammoM = a.missiles;
  if (mission.flaggedLowAmmo && !R.lowAmmo) { say('btyAmmo'); say('lowAmmo', { delay: 0.4 }); } R.lowAmmo = mission.flaggedLowAmmo;
  // ---- hits on us
  if (heli.lastHitT !== R.hitT) {
    R.hitT = heli.lastHitT; R.combatT = T; const dh = R.hull - heli.hull, kind = heli.lastHitKind;
    if (kind === 'arrows') { if (T - R.arrowT > 0.8) R.arrowN = 0; R.arrowN++; R.arrowT = T; }
    if (kind === 'ballista bolt') say('hitBolt', { delay: 0.3 }); else if (dh >= 10) say('hitBig', { delay: 0.2 }); else if (R.arrowN >= 3) say('hitArrows', { delay: 0.2 }); else if (kind !== 'arrows' || R.arrowN >= 2) say('hit', { delay: 0.2 });
    if (ph === 3 && crowd.warlord >= 0 && crowd.isAlive(crowd.warlord)) { const w = crowd.warlord; enemy('taunt2', crowd.x[w], crowd.y[w] + 2, crowd.z[w], 0.6); }
  }
  R.hull = heli.hull;
  if (heli.hull < 30 && !R.hullCrit && fly) { R.hullCrit = true; say('btyHull'); say('hullCrit', { delay: 0.3 }); } else if (heli.hull > 60) R.hullCrit = false;
  // ---- pad / repairs
  if (heli.onPad && weapons.fullyArmed && !R.armed) say('rearm'); R.armed = heli.onPad && weapons.fullyArmed;
  { let repaired = false, all = true; for (let i = 0; i < SUBS.length; i++) { const v = heli.sub[SUBS[i]]; if (v >= 100 && R.subs[i] < 100) repaired = true; if (v < 100) all = false; R.subs[i] = v; }
    if (repaired && heli.onPad) say(all ? 'nominal' : 'repaired'); }
  if (R.pad && !heli.onPad && fly) say(weapons.fullyArmed ? 'rearmed' : 'lifting');
  R.pad = heli.onPad;
  // ---- night
  if (mission.warn120 && !R.w120) say('dusk1'); R.w120 = mission.warn120;
  if (mission.warn45 && !R.w45) say('dusk2'); R.w45 = mission.warn45;
  // ---- boundary: warn band -> imminent exit -> spoken 10..1 matching the HUD timer -> turning back
  if (mission.warnBand && !R.warn) { say('bndWarnB'); say('bndWarnC', { delay: 0.3 }); } R.warn = mission.warnBand;
  if (mission.warnBand && mission.edgeDist < 50 && !R.edge) { const vr = (heli.vel.x * p.x + heli.vel.z * p.z) / (Math.hypot(p.x, p.z) || 1); if (vr > 4) { R.edge = true; say('bndOut'); } }
  if (mission.edgeDist > 150) R.edge = false;
  if (mission.outside && fly) {
    if (!R.outside) { R.outside = true; R.nextN = Math.min(10, Math.floor(mission.outT + 1e-3)); dropQueued(3); }
    if (R.nextN >= 1 && mission.outT <= R.nextN + 0.02) { say('n' + R.nextN); R.nextN--; }
  } else if (R.outside) { R.outside = false; if (fly) say('turnback'); }
  // ---- flight warnings
  const dPad = Math.hypot(p.x - L.PAD.x, p.z - L.PAD.z);
  if (fly && !heli.onGround) {
    const vs = heli.vs, landing = dPad < 110 && heli.speed < 14;
    const pull = vs < -8 && heli.agl < -vs * 2.2 && !landing;
    if (pull) say('bPull'); else if (heli.agl < 25 && vs < -3.5 && !landing) say('bAlt');
    const sink = heli.vrs > 0.25; if (sink) { say('bSink'); if (!R.vrs) say('sinkP', { delay: 0.8 }); } R.vrs = sink;
    if (heli.rpm < 0.9) say('bRpm');
    if (p.y - 24 > 380) say('bCeil');
    if (heli.agl < 12 && heli.hspeed > 22 && dPad > 150) say('low');
    if ((proxT -= dt) <= 0 && heli.speed > 4) { proxT = 0.2; proxHit = null; world.nearby(p.x, p.z, heli.rotorR + 12, treeOrWall); if (proxHit) say(proxHit); }
    if (heli.gForce > 2.1 || (heli.sub.hyd < 50 && heli.gForce > 1.6)) audio.play('airframe_stress', { gain: clamp(heli.gForce - 1.2, 0.4, 1.2) });
  }
  // ---- threats: tells get a voice
  const forms = crowd.forms;
  if (!fPrev || fPrev.length !== forms.length) { fPrev = new Uint8Array(forms.length * 2); shieldT = new Float32Array(forms.length).fill(-99); }
  const c = G.camera.position;
  for (let i = 0; i < forms.length; i++) {
    const f = forms[i];
    const vol = f.volleying ? 1 : 0, sh = f.posture === 'shield' ? 1 : 0;
    if (vol && !fPrev[i * 2] && f.kind === 'archers') {
      say(heli.agl < 80 ? 'volleyClimb' : 'volley', { delay: 0.15 });
      const r = Math.random(); const g = r < 0.4 ? 0 : r < 0.75 ? 1 : 2; const ids = EN.loose[0];
      if (audio.has(ids[g]) && T >= enemyNext && Math.hypot(f.cx - c.x, f.cz - c.z) < 480 && (enemyLast.loose === undefined || T - enemyLast.loose > EN.loose[1])) {
        const v = audio.vo(ids[g], { pos: [f.cx, f.cy + 2, f.cz], delay: g === 0 ? 0 : g === 1 ? 0.5 : 1.75 });
        if (v) { enemyLast.loose = T; enemyNext = T + v.dur + 1.5; vlog(`ENM t=${mission.time.toFixed(1)} ${ids[g]} "${textOf(ids[g])}"`); }
      }
    }
    if (sh && !fPrev[i * 2 + 1] && !f.routed && f.kind !== 'crew' && f.kind !== 'camp') {
      const dd = Math.hypot(f.cx - c.x, f.cz - c.z);
      if (dd < 450 && T - shieldT[i] > 15) { shieldT[i] = T; sfx('shield_wall_up', f.cx, f.cy + 1.5, f.cz); enemy('shields', f.cx, f.cy + 2, f.cz, 0.3); }
    }
    if (f.kind === 'infantry' && !f.routed && f.panicT <= 0 && f.underFire > 3.5 && Math.hypot(f.cx - c.x, f.cz - c.z) < 300) enemy('hold', f.cx, f.cy + 2, f.cz);
    if (ph === 1 && f.kind === 'infantry' && f.spotted && !R.banner && Math.hypot(f.cx - p.x, f.cz - p.z) < 420) { R.banner = true; say('spotBanner', { delay: 1 }); }
    if (!R.village && f.name === 'Village Archers' && (f.underFire > 0 || f.alive < f.initial)) { R.village = true; sfx('village_alarm_bell', L.VILLAGE.x, f.cy + 12, L.VILLAGE.z, { delay: 0.8 }); }
    fPrev[i * 2] = vol; fPrev[i * 2 + 1] = sh;
  }
  // war chants from alert formations keep the army audible as men, not as noise
  if ((chantT -= dt) <= 0) {
    chantT = rnd(9, 16); let best = null, bd = 460;
    for (const f of forms) if (f.kind === 'infantry' && !f.routed && f.panicT <= 0 && f.alert > 0.5) { const d = Math.hypot(f.cx - c.x, f.cz - c.z); if (d < bd) { bd = d; best = f; } }
    if (best) sfx('war_chant', best.cx, best.cy + 2, best.cz, { gain: 0.9 });
  }
  const E = threats.engines;
  if (!ePrev || ePrev.length !== E.length) { ePrev = new Uint8Array(E.length * 2); bomVo = new Uint8Array(E.length); }
  for (let i = 0; i < E.length; i++) {
    const e = E[i]; if (!e.alive) { ePrev[i * 2] = 0; continue; }
    const st = e.state === 'aim' ? 1 : e.state === 'swing' ? 2 : 0;
    if (st === 1 && ePrev[i * 2] !== 1) { // ballista tracking us: crank in the world + gunner call + crew order
      sfx('ballista_crank', e.x, e.y, e.z); say('ballista'); enemy('ballista', e.x, e.y + 1, e.z, 0.1); R.combatT = T;
    }
    if (st === 0 && ePrev[i * 2] === 1 && e.kind === 'ballista' && e.t > 4) say('bolt');   // fired (an aborted aim re-arms in 1.5-3 s)
    if (st === 2 && ePrev[i * 2] !== 2) { say('treb', { delay: 0.3 }); enemy('treb', e.x, e.y + 8, e.z); }
    if (e.spotted && !ePrev[i * 2 + 1]) { if (e.kind === 'ballista') say('spotBal', { delay: 0.5 }); else if (e.kind === 'treb' && ph >= 2) say('spotTreb', { delay: 0.5 }); }
    ePrev[i * 2] = st; ePrev[i * 2 + 1] = e.spotted ? 1 : 0;
    if (e.kind === 'bombard') { // the crew's order lands ~0.5 s before the shot (same gate as threats.js)
      if (e.t > 2) bomVo[i] = 0;
      else if (!bomVo[i] && ph >= 2 && fly && e.t > 0 && e.t < 0.7 && G.time - (threats.lastBombard || -99) > 2.9) {
        const dx = p.x - e.x, dz = p.z - e.z, dy = p.y - e.y;
        if (Math.abs(p.y - 24 - threats.bandCenter) < threats.bandHalf && Math.hypot(dx, dz) < e.range && dy > 10 && threats.crewAlive(e) > 0) { bomVo[i] = 1; enemy('bombard', e.x, e.y + 1, e.z); }
      }
    }
  }
  for (const b of threats.bolts) if (b.near && !seen.has(b)) { seen.add(b); say('close', { delay: 0.25 }); }
  for (const s of threats.shells) if (!seen.has(s) && s.t / s.tof > 0.9 && Math.hypot(s.tx - p.x, s.ty - p.y, s.tz - p.z) < 70) { seen.add(s); say('flak', { delay: 0.3 }); }
  for (const b of threats.boulders) if (!seen.has(b)) { const dx = p.x - b.x, dy = p.y - b.y, dz = p.z - b.z, d = Math.hypot(dx, dy, dz); if (d < 220 && dx * b.vx + dy * b.vy + dz * b.vz > 0) { seen.add(b); say('boulder'); } }
  // ---- phase 3: the warlord
  if (ph === 3 && crowd.warlord >= 0 && crowd.isAlive(crowd.warlord)) {
    const w = crowd.warlord, d = Math.hypot(crowd.x[w] - p.x, crowd.z[w] - p.z);
    if (d < 330 && !R.warlordSeen) { R.warlordSeen = true; say('warlord', { delay: 0.5 }); }
    if (d < 140 && !R.taunt1) { R.taunt1 = enemy('taunt1', crowd.x[w], crowd.y[w] + 2, crowd.z[w]); }
    if (d < 320 && T > R.taunt3T) { R.taunt3T = T + rnd(40, 60); enemy('taunt3', crowd.x[w], crowd.y[w] + 2, crowd.z[w]); }
    if (Math.hypot(p.x - (L.CASTLE.x + 22), p.z - L.CASTLE.z) < 110 && heli.agl > 30) say('smoke');
  }
}

// ---------------------------------------------------------------- per-frame world feed for the loop layers
function feedExt() {
  const X = audio.ext, c = G.camera ? G.camera.position : heli.pos, play = appState === 'play';
  const fly = play && (heli.state === 'fly' || heli.state === 'crashing');
  X.wash = fly ? heli.washK : 0; X.shake = play ? heli.shake : 0; X.menu = appState === 'menu' ? 1 : 0;
  X.countdown = play && mission.outside && heli.state === 'fly'; X.betty = audio.has('bty_sink');
  X.river = sat(1 - Math.abs(c.x - riverX(c.z)) / 260) * sat(1 - (c.y - (L.WATER_Y || 0) - 25) / 170);
  let bd = 1e9, cd = 1e9;
  for (const f of crowd.forms) {
    if (f.routed || f.kind === 'crew') continue;
    if (f.banner && f.bannerUp) { const d = Math.hypot(f.cx - c.x, f.cy + 5 - c.y, f.cz - c.z); if (d < bd) bd = d; }
    if (f.alive > 10) { const d = Math.hypot(f.cx - c.x, (f.cy || 0) - c.y, f.cz - c.z); if (d < cd) cd = d; }
  }
  X.banner = sat(1 - bd / 70) * (0.35 + 0.65 * sat(X.wash * 1.5));
  X.close = Math.pow(sat(1 - (cd - 25) / 220), 1.5);
  // nearest fire: positional single-fire loop
  let fk = 0, fe = null;
  for (const e of fx.emitters) { if (e.on === false) continue; const d = Math.hypot(e.x - c.x, e.y - c.y, e.z - c.z), k = Math.min(1.2, (e.size || 1) * 0.8) / (1 + Math.pow(d / 35, 1.3)); if (k > fk) { fk = k; fe = e; } }
  X.fireK = fk;
  if (fe && G.camera) { camR.set(1, 0, 0).applyQuaternion(G.camera.quaternion); _v.set(fe.x - c.x, fe.y - c.y, fe.z - c.z).normalize(); X.firePan = _v.dot(camR); }
}

// ---------------------------------------------------------------- public
export const director = {
  init() {
    if (Q.has('mute')) return;
    audio.onLog = vlog;
    audio.load();                                   // the sample bank streams from boot; no gesture needed to fetch + decode
    // audio starts on the first user gesture anywhere (menu music needs it before "Take off")
    const kick = () => { audio.init(); audio.resume(); applyVolume(true); if (audio.context && audio.context.state === 'running') { removeEventListener('pointerdown', kick, true); removeEventListener('keydown', kick, true); } };
    addEventListener('pointerdown', kick, true); addEventListener('keydown', kick, true);
    if (dev.on && (Q.has('ameter') || Q.has('amenu'))) kick();   // headless test runs (autoplay allowed)
    for (const n of ['formationRouted', 'formationPanic', 'structDestroyed', 'engineDestroyed', 'subDegraded', 'padLanding', 'warlordDead', 'heliDown', 'missionEnd', 'flares', 'bombardFired', 'kill']) {
      G.events.addEventListener(n, (e) => { try { onEvent(n, e); } catch (err) { if (dev.on) dev.log('DIR event error ' + n + ' ' + err.message); } });
    }
  },
  update(dt, state, paused) {
    if (Q.has('mute')) return;
    if (dev.on) { const n = performance.now(); if (lastP && n - lastP > 100) dev.log(`DIR frame gap ${(n - lastP).toFixed(0)}ms t=${mission.time.toFixed(1)} last audio: ${lastMsg}`); lastP = n; }
    appState = state;
    audio.busy = state === 'play' && !paused;
    audio.pump();
    applyVolume(false);
    if (!audio.context) return;
    try {
      if (state !== prevApp) { prevApp = state; if (state === 'menu') { queue.length = 0; cur = null; prevMS = 'idle'; } }
      if (paused) return;
      T += dt;
      if (state === 'play') {
        if (mission.state === 'play' && (prevMS !== 'play' || mission.time < prevTime - 0.5)) onStart();
        prevMS = mission.state; prevTime = mission.time;
        if (dev.on && Q.get('dirtest')) devScript();
        pollPlay(dt);
        if (mission.state === 'play' && mission.phase >= 1) updateLull(dt);
      } else if (state === 'menu') {
        if ((chantT -= dt) <= 0) { chantT = rnd(14, 24); const f = crowd.forms[(Math.random() * 6) | 0]; if (f) sfx('war_chant', f.cx, f.cy + 2, f.cz, { gain: 0.7 }); }
      }
      feedExt();
      updateMusic();
      pumpVO();
      if (dev.on && Q.has('ameter') && (amT += dt) > 2) {
        amT = 0; const b = audio.meterBus(); const bk = audio.bank;
        if (b) dev.log(`AMETER t=${(state === 'play' ? mission.time : T).toFixed(1)} st=${state}/${mission.state} ph=${mission.phase} sfx=${b.sfx.toFixed(3)} amb=${b.amb.toFixed(3)} mus=${b.mus.toFixed(3)} vox=${b.vox.toFixed(3)} duck=${audio.voiceActive ? 1 : 0} bed=${audio.music.bed} lull=${!!R.lull} pcmMB=${(bk.pcm / 1e6).toFixed(0)} q=${bk.queue.length}`);
      }
    } catch (err) { if (dev.on) dev.log('DIR error ' + (err.stack || err.message)); }
    flushLog();
  },
};
// dev only (?dirtest=win|lose): drive the mission through its audio set pieces on a fixed timeline
let dts = 0, dt0 = -1;
function devScript() {
  if (dt0 < 0) { if (audio.bank.autoLeft > 0 || !audio.bank.man) return; dt0 = mission.time; vlog('DIR dirtest: bank loaded, script starts'); }
  const t = mission.time - dt0;
  if (dts === 0 && t > 3) { dts = 1; mission.setPhase(2); }
  if (dts === 1 && t > 26) { dts = 2; mission.setPhase(3); }
  if (dts === 2 && t > 46) { dts = 3; if (Q.get('dirtest') === 'win') crowd.kill(crowd.warlord, 0, 4, 0); else heli.hit({ hull: 500, sub: 'tail', subDmg: 100, kind: 'test' }); }
}
const VOLC = [-1, -1, -1];
function applyVolume(force) {
  const m = settings.volume, mu = settings.musicVolume === undefined ? 0.7 : settings.musicVolume, vo = settings.voiceVolume === undefined ? 1 : settings.voiceVolume;
  if (!force && m === VOLC[0] && mu === VOLC[1] && vo === VOLC[2]) return; VOLC[0] = m; VOLC[1] = mu; VOLC[2] = vo;
  audio.setVolume(m, 1, 1, mu, vo);
}
