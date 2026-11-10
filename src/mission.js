// Siege Wing — mission flow: approach, three phases, boundary, sunset clock, scoring
import { G, V3, clamp, DEG, smooth } from './core.js';
import { terrain, L } from './terrain.js';
import { heli, SUBS } from './heli.js';
import { weapons } from './weapons.js';
import { crowd } from './crowd.js';
import { castle } from './castle.js';
import { threats } from './threats.js';
import { audio } from './audio.js';
import { settings } from './input.js';
import { sky } from './sky.js';

export const RUN_SECONDS = 600;   // sunset clock: full dusk at 10 minutes
const EMPTY = [['cannon', '30MM'], ['rockets', 'ROCKETS'], ['missiles', 'MISSILES'], ['flares', 'FLARES']];
const say = (text, kind = 'info', dur = 4) => G.events.dispatchEvent(new CustomEvent('msg', { detail: { text, kind, dur } }));
const banner = (title, sub) => G.events.dispatchEvent(new CustomEvent('banner', { detail: { title, sub } }));

export const mission = {
  phase: 0, state: 'idle', time: 0, tod: 0, outT: 10, outside: false, warnBand: false, edgeDist: 0, rearmLandings: 0, altBins: new Float32Array(24), result: null, endT: 0,
  objective: '', progress: '', marker: new V3(), hasMarker: false, tutorialStep: 0, tutT: 0, score: 0, approach: true, cause: '', flaggedLowAmmo: false,
  init() {
    const on = (n, f) => G.events.addEventListener(n, f);
    on('formationRouted', e => { const f = e.detail; if (f.kind === 'infantry') say(`${f.name.toUpperCase()} ROUTED`, 'good', 4); else say(`${f.name.toUpperCase()} BROKEN`, 'good', 3); });
    on('formationPanic', e => say('SHIELD WALL BROKEN — ' + e.detail.name.toUpperCase(), 'good', 3));
    on('structDestroyed', e => { const s = e.detail; if (s.type === 'tower') say(s.name.toUpperCase() + ' DESTROYED', 'good', 4); });
    on('engineDestroyed', e => say(e.detail.name.toUpperCase() + ' DESTROYED', 'good', 3));
    on('subDegraded', e => say({ tail: 'TAIL ROTOR DAMAGED — HOLD YAW', engine: 'ENGINE DAMAGED — POWER DOWN 35%', hyd: 'HYDRAULICS DAMAGED — SLOW CONTROLS', rotor: 'MAIN ROTOR DAMAGED', canopy: 'CANOPY CRACKED', weapons: 'WEAPONS DAMAGED' }[e.detail], 'warn', 4));
    on('padLanding', () => { if (this.state === 'play') { this.rearmLandings++; say('ON THE PAD — REARMING AND REPAIRING', 'good', 3); } });
    on('warlordDead', () => { if (this.state === 'play') this.win(); });
    on('heliDown', e => { if (this.state === 'play') { this.cause = e.detail; this.lose(e.detail); } });
    on('heliDestroyed', e => { if (this.state === 'play') { this.cause = e.detail; this.lose(e.detail); } });
  },
  start(skipApproach) {
    this.state = 'play'; this.time = 0; this.outT = 10; this.outside = false; this.rearmLandings = 0; this.altBins.fill(0); this.result = null; this.endT = 0; this.flaggedLowAmmo = false; this.flagHull = false; this.flagEmpty = {};
    this.warn120 = this.warn45 = false; this.lightLeft = RUN_SECONDS; this.approach = !skipApproach; this.tutorialStep = 0; this.tutT = 0; this.cause = '';
    castle.reset(); crowd.reset(); threats.reset(); weapons.reset(); terrain.clearScorch();
    if (skipApproach) {
      const x = 640, z = 150; heli.reset(x, terrain.height(x, z) + 60, z, 90 * DEG, 30); this.time = 45; this.setPhase(1, true);
    } else {
      const x = L.START.x, z = L.START.z; heli.reset(x, terrain.height(x, z) + 42, z, 82 * DEG, 30); this.phase = 0;
      this.objective = 'Cross the ridge'; this.progress = 'Rearm pad is on the hill ahead';
    }
  },
  setPhase(n, quiet) {
    this.phase = n; const fav = this.favAlt();
    threats.setPhase(n, fav);
    if (n === 1) { banner('PHASE 1 — BREAK THE FIELD ARMY', 'Rout four of the six formations. Kill the knights around a banner and the block runs.'); }
    if (n === 2) { banner('PHASE 2 — SILENCE THE WALLS', 'Destroy the four gate towers. Bombards and trebuchets are now firing.'); say('PAVISE SHIELDS OUT — ARCHERS ARE PROTECTED', 'warn', 5); }
    if (n === 3) { banner('PHASE 3 — KILL THE WARLORD', 'He holds the courtyard. Fire pots are lit: your rotor wash clears the smoke.'); say(`BOMBARDS RE-LAID TO ${Math.round(threats.bandCenter)} M`, 'warn', 5); }
    if (!quiet || n > 1) audio.play('phase');
  },
  favAlt() { let b = 0, bv = 0; for (let i = 0; i < this.altBins.length; i++) if (this.altBins[i] > bv) { bv = this.altBins[i]; b = i; } return bv > 5 ? b * 20 + 10 : undefined; },

  update(dt) {
    if (this.state !== 'play') { if (this.state === 'won' || this.state === 'lost') this.endT += dt; return; }
    this.time += dt; this.tod = clamp(this.time / RUN_SECONDS, 0, 1.15);
    const p = heli.pos; const r = Math.hypot(p.x, p.z);
    // altitude histogram for adaptive bombards
    if (this.phase >= 1) { const b = clamp(Math.floor((p.y - 24) / 20), 0, 23); this.altBins[b] += dt; }
    // ---- approach + tutorial prompts ----
    if (this.phase === 0) {
      this.tutT += dt;
      const steps = [[1.5, 'W / S — COLLECTIVE: CLIMB AND DESCEND. W DOES NOT MOVE YOU FORWARD.'], [8, 'MOUSE — TILT THE NOSE DOWN TO FLY FORWARD. LEVEL OFF TO HOLD SPEED.'], [15, settings.mouseX === 'yaw' ? 'MOUSE X / Q E — YAW.  A / D — ROLL.' : 'A / D — YAW.  MOUSE X OR Q / E — ROLL.'], [22, 'HOLD RIGHT MOUSE — GUNNER MODE: THE MOUSE AIMS THE CANNON, NOT THE HELICOPTER.'], [29, '1 / 2 / 3 — CANNON / ROCKETS / MISSILES.   X — FLARES.   C — COCKPIT.'], [35, 'FLARE BACK (NOSE UP) TO STOP. THE ARMY IS OVER THE RIDGE.']];
      if (this.tutorialStep < steps.length && this.tutT > steps[this.tutorialStep][0]) { say(steps[this.tutorialStep][1], 'tut', 6.5); this.tutorialStep++; }
      if (p.x < 1010 || this.time > 75) this.setPhase(1);
    }
    // ---- objectives ----
    if (this.phase === 1) {
      const inf = crowd.forms.filter(f => f.kind === 'infantry'); const routed = inf.filter(f => f.routed).length;
      this.objective = 'Break the field army'; this.progress = `Formations routed ${routed} / 4`;
      let best = null, bd = 1e9; for (const f of inf) if (!f.routed) { const d = Math.hypot(f.cx - p.x, f.cz - p.z); if (d < bd) { bd = d; best = f; } }
      if (best) { this.marker.set(best.cx, best.cy + 6, best.cz); this.hasMarker = true; }
      if (routed >= 4) this.setPhase(2);
    } else if (this.phase === 2) {
      const gt = castle.towers.filter(t => t.kind === 'gate'); const down = gt.filter(t => !t.alive).length;
      this.objective = 'Silence the walls'; this.progress = `Gate towers destroyed ${down} / 4`;
      let best = null, bd = 1e9; for (const t of gt) if (t.alive) { const d = Math.hypot(t.x - p.x, t.z - p.z); if (d < bd) { bd = d; best = t; } }
      if (best) { this.marker.set(best.x, best.topY + 4, best.z); this.hasMarker = true; }
      if (down >= 4) this.setPhase(3);
    } else if (this.phase === 3) {
      const w = crowd.warlord; this.objective = 'Kill the warlord'; this.progress = `In the courtyard — guard ${crowd.guardForm.alive}`;
      this.marker.set(crowd.x[w], crowd.y[w] + 4, crowd.z[w]); this.hasMarker = true;
    } else this.hasMarker = false;
    // low ammo nudge
    const a = weapons.ammo; const low = a.cannon < 80 && a.rockets < 6 && a.missiles === 0;
    if (low && !this.flaggedLowAmmo) { this.flaggedLowAmmo = true; say('AMMUNITION LOW — REARM PAD ON THE FAR HILL', 'warn', 5); } if (!low) this.flaggedLowAmmo = false;
    // return-to-pad notices: hull under half, or any store emptied (re-armed once repaired / reloaded)
    if (heli.state === 'fly' && !heli.onPad) {
      if (heli.hull < 50 && !this.flagHull) { this.flagHull = true; say(`HULL ${Math.round(heli.hull)}% — RETURN TO THE PAD (H) TO REPAIR`, 'warn', 6); }
      for (const [k, name] of EMPTY) if (a[k] <= 0 && !this.flagEmpty[k]) { this.flagEmpty[k] = true; say(`${name} EMPTY — RETURN TO THE PAD (H) TO REARM`, 'warn', 6); }
    }
    if (heli.hull >= 60) this.flagHull = false; for (const [k] of EMPTY) if (a[k] > 0) this.flagEmpty[k] = false;
    // ---- last light: the run is capped at ten minutes ----
    if (this.phase >= 1) {
      const left = RUN_SECONDS - this.time;
      if (left < 120 && !this.warn120) { this.warn120 = true; say('TWO MINUTES OF LIGHT LEFT', 'warn', 5); audio.play('phase'); }
      if (left < 45 && !this.warn45) { this.warn45 = true; say('LAST LIGHT — FINISH IT NOW', 'warn', 6); audio.play('phase'); }
      this.lightLeft = Math.max(0, left);
      if (left <= 0) { this.cause = 'night fell — the warlord slipped away in the dark'; this.lose(this.cause); return; }
    }
    // ---- boundary ----
    this.edgeDist = L.PLAY_R - r;
    const enforce = this.phase >= 1;
    this.warnBand = enforce && this.edgeDist < 150 && this.edgeDist >= 0;
    this.outside = enforce && this.edgeDist < 0;
    if (this.outside) { this.outT -= dt; if (this.outT <= 0 && heli.state === 'fly') { this.cause = 'left the combat area'; this.lose(this.cause); heli.state = 'gone'; } }
    else this.outT = Math.min(10, this.outT + dt);
  },
  stats() {
    const inf = crowd.forms.filter(f => f.kind === 'infantry'); const a = weapons.ammo, m = weapons.max;
    return { time: this.time, hull: Math.max(0, heli.hull), kills: crowd.killed, routed: crowd.forms.filter(f => f.routed).length, towers: castle.towers.filter(t => !t.alive).length, engines: threats.engines.filter(e => !e.alive).length,
      shots: weapons.shotsFired, rockets: weapons.rocketsFired, missiles: weapons.missilesFired, landings: this.rearmLandings, phase: this.phase, mode: settings.mode, hits: threats.stats };
  },
  calcScore(won) {
    const s = this.stats(); const mult = settings.mode === 'stabilized' ? 0.5 : settings.mode === 'assault' ? 0.75 : 1;
    const ammoUsed = s.shots / 600 + s.rockets / 38 + s.missiles / 8;
    let sc = (this.phase - 1) * 4000 + s.kills * 6 + s.routed * 700 + s.towers * 900 + s.engines * 500;
    if (won) sc += 12000 + s.hull * 60 + Math.max(0, 600 - s.time) * 12 - s.landings * 500 - ammoUsed * 400;
    return Math.max(0, Math.round(sc * mult));
  },
  win() { if (this.state !== 'play') return; this.state = 'won'; this.endT = 0; this.score = this.calcScore(true); this.result = this.stats(); audio.play('win'); banner('THE WARLORD IS DEAD', 'The siege is broken.'); G.events.dispatchEvent(new CustomEvent('missionEnd', { detail: true })); },
  lose(cause) { if (this.state !== 'play') return; this.state = 'lost'; this.endT = 0; this.score = this.calcScore(false); this.result = this.stats(); if (heli.state !== 'fly' && heli.state !== 'gone') this.result.hull = 0; crowd.cheer(); audio.play('lose', { delay: 1.8 }); audio.play('cheer', { pos: [L.FIELD.x, 30, 0], delay: 1.2 }); G.events.dispatchEvent(new CustomEvent('missionEnd', { detail: false })); },
};
