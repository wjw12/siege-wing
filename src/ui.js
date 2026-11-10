// Siege Wing — DOM menus: loading, title, settings/rebinding, pause, end screen
import { settings, saveSettings, applyPreset, PRESETS, ACTIONS, keyLabel, input } from './input.js';
import { audio } from './audio.js';
import { perf } from './perf.js';

const $ = id => document.getElementById(id);
const screens = ['loading', 'menu', 'settings', 'pause', 'end', 'resume', 'help'];
export const ui = {
  cb: {}, current: 'loading', settingsFrom: 'menu',
  show(name) { if (name !== 'pause' && name !== 'resume') this.clearSubs(); this.current = name; for (const s of screens) $(s).classList.toggle('on', s === name); },
  hide() { this.current = null; for (const s of screens) $(s).classList.remove('on'); },
  loading(p, txt) { $('loadbar').style.width = Math.round(p * 100) + '%'; if (txt) $('loadtxt').textContent = txt; },
  fade(on) { $('fade').style.opacity = on ? 1 : 0; },
  init(cb) {
    this.cb = cb;
    const click = (id, f, snd = 'uiClick') => (typeof id === 'string' ? $(id) : id).addEventListener('click', e => { audio.play(snd); f(e); });
    document.querySelectorAll('button,.card').forEach(b => b.addEventListener('mouseenter', () => audio.play('uiHover', { gain: 0.5 })));
    document.querySelectorAll('.card').forEach(c => c.addEventListener('click', () => { settings.mode = c.dataset.mode; saveSettings(); audio.play('uiClick'); this.refresh(); }));
    click('btnFly', () => { if (settings.hideHelp) cb.start(false); else this.showHelp('start'); });
    click('btnHelp', () => this.showHelp('menu'));
    click('btnPHelp', () => this.showHelp('pause'));
    click('btnHelpGo', () => cb.start(false));
    click('btnHelpBack', () => this.show(this.helpFrom === 'pause' ? 'pause' : 'menu'), 'uiBack');
    click('btnHelpPrev', () => this.helpPage(this.hp - 1)); click('btnHelpNext', () => this.helpPage(this.hp + 1));
    document.querySelectorAll('#helpTabs button').forEach(b => click(b, () => this.helpPage(+b.dataset.p)));
    document.querySelectorAll('#helpDots i').forEach((d, i) => d.addEventListener('click', () => { audio.play('uiClick'); this.helpPage(i); }));
    addEventListener('keydown', e => { if (this.current !== 'help') return; if (e.code === 'ArrowRight' || e.code === 'PageDown') this.helpPage(this.hp + 1, true); else if (e.code === 'ArrowLeft' || e.code === 'PageUp') this.helpPage(this.hp - 1, true); });
    $('helpSkip').addEventListener('change', e => { settings.hideHelp = e.target.checked; saveSettings(); this.refresh(); });
    $('optHelp').addEventListener('change', e => { settings.hideHelp = !e.target.checked; saveSettings(); });
    $('optSubs').addEventListener('change', e => { settings.subtitles = e.target.checked; saveSettings(); if (!e.target.checked) this.clearSubs(); });
    // subtitles: one line for the radio / crew, one for voices out in the world
    const WHO = { command: ['ANVIL', '#ffb02e'], pilot: ['PILOT', '#9fd4ff'], gunner: ['GUNNER', '#a8f0a0'], betty: ['WARNING', '#ff6a55'], captain: ['ENEMY CAPTAIN', '#d9b68a'], serjeant: ['ENEMY SERJEANT', '#d9b68a'], soldier: ['SOLDIER', '#d9b68a'], warlord: ['WARLORD', '#ff8a5c'] };
    const esc = t => t.replace(/[&<>]/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[ch]));
    this.subT = [0, 0];
    cb.events.addEventListener('subtitle', e => {
      if (!settings.subtitles) return; const d = e.detail; if (!d.text) return; const w = WHO[d.speaker] || [String(d.speaker || '').toUpperCase(), '#e9f1dc'];
      const k = d.world ? 1 : 0; const el = $(k ? 'subEnemy' : 'subMain');
      const show = () => { el.innerHTML = `<b style="color:${w[1]}">${w[0]}</b>${esc(d.text)}`; el.classList.add('on'); clearTimeout(this.subT[k]); this.subT[k] = setTimeout(() => el.classList.remove('on'), (d.dur + 0.5) * 1000); };
      if (d.delay) setTimeout(show, d.delay * 1000); else show();
    });
    const sl = (id, key) => $(id).addEventListener('input', e => { settings[key] = +e.target.value; $(id + 'V').textContent = (+e.target.value).toFixed(2) + '×'; saveSettings(); });
    sl('optAim', 'aimSens'); sl('optKey', 'keySens');
    click('btnSettings', () => { this.settingsFrom = 'menu'; this.show('settings'); });
    click('btnPSettings', () => { this.settingsFrom = 'pause'; this.show('settings'); });
    click('btnBack', () => this.show(this.settingsFrom), 'uiBack');
    click('btnResume', () => cb.resume());
    click('btnRestart', () => cb.start(true));
    click('btnQuit', () => cb.quit(), 'uiBack');
    click('btnRetry', () => cb.start(true));
    click('btnEndMenu', () => cb.quit(), 'uiBack');
    $('resume').addEventListener('click', () => cb.resume());
    $('optSens').addEventListener('input', e => { settings.sens = +e.target.value; $('optSensV').textContent = settings.sens.toFixed(2) + '×'; saveSettings(); });
    $('optInv').addEventListener('change', e => { settings.invertY = e.target.checked; saveSettings(); });
    $('optVol').addEventListener('input', e => { settings.volume = +e.target.value; saveSettings(); audio.setVolume(settings.volume, 1, 1); });
    $('optMus').addEventListener('input', e => { settings.musicVolume = +e.target.value; saveSettings(); audio.setVolume(settings.volume, 1, 1, settings.musicVolume, settings.voiceVolume); });
    $('optVox').addEventListener('input', e => { settings.voiceVolume = +e.target.value; saveSettings(); audio.setVolume(settings.volume, 1, 1, settings.musicVolume, settings.voiceVolume); });
    $('optQ').addEventListener('change', e => perf.apply(e.target.value));
    $('optFps').addEventListener('change', e => { settings.showFps = e.target.checked; saveSettings(); perf.sync(); });
    this.refresh();
  },
  refresh() {
    document.querySelectorAll('.card').forEach(c => c.classList.toggle('sel', c.dataset.mode === settings.mode));
    $('optSens').value = settings.sens; $('optSensV').textContent = (+settings.sens).toFixed(2) + '×'; $('optAim').value = settings.aimSens; $('optAimV').textContent = (+settings.aimSens).toFixed(2) + '×'; $('optKey').value = settings.keySens; $('optKeyV').textContent = (+settings.keySens).toFixed(2) + '×'; $('optHelp').checked = !settings.hideHelp; $('optSubs').checked = settings.subtitles !== false; $('helpSkip').checked = !!settings.hideHelp; $('optInv').checked = settings.invertY; $('optVol').value = settings.volume; $('optMus').value = settings.musicVolume; $('optVox').value = settings.voiceVolume; $('optQ').value = settings.quality; $('optFps').checked = settings.showFps !== false;
    const k = settings.keys;
    const pr = $('presets'); pr.innerHTML = '';
    for (const [id, p] of Object.entries(PRESETS)) { const b = document.createElement('button'); b.textContent = p.name; b.className = settings.preset === id ? 'sel' : ''; b.onclick = () => { applyPreset(id); audio.play('uiClick'); this.refresh(); }; pr.appendChild(b); }
    const bd = $('binds'); bd.innerHTML = '';
    for (const [a, label] of ACTIONS) {
      const row = document.createElement('div'); row.className = 'bind'; const sp = document.createElement('span'); sp.textContent = label; const b = document.createElement('button'); b.textContent = keyLabel(k[a]);
      b.onclick = () => { b.textContent = 'press…'; b.classList.add('cap'); input.capture = code => { if (code !== 'Escape') { for (const o in k) if (k[o] === code && o !== a) k[o] = k[a]; k[a] = code; settings.preset = 'custom'; saveSettings(); } this.refresh(); }; };
      row.appendChild(sp); row.appendChild(b); bd.appendChild(row);
    }
  },
  // the flying guide, three pages: from === 'start' (before take-off), 'menu' or 'pause'
  helpPage(i, snd) {
    i = Math.max(0, Math.min(2, i)); if (snd && i !== this.hp) audio.play('uiClick'); this.hp = i;
    document.querySelectorAll('#help .gpage').forEach(p => p.classList.toggle('on', +p.dataset.p === i));
    document.querySelectorAll('#helpTabs button').forEach(b => b.classList.toggle('sel', +b.dataset.p === i));
    document.querySelectorAll('#helpDots i').forEach((d, j) => d.classList.toggle('on', j === i));
    $('btnHelpPrev').disabled = i === 0; $('btnHelpNext').disabled = i === 2;
    const pnl = document.querySelector('#help .panel'); if (pnl) pnl.scrollTop = 0;
  },
  showHelp(from) {
    this.helpFrom = from; const k = settings.keys, kb = (...a) => a.map(x => `<kbd>${keyLabel(k[x])}</kbd>`).join(' '), my = settings.mouseX === 'yaw';
    const mode = settings.mode, li = a => a.map(x => `<li>${x}</li>`).join('');
    $('helpMode').innerHTML = mode === 'assault' ? '<b>Assault handling</b> — the helicopter holds its altitude when you let go of the collective. It does not stop or level by itself.' : mode === 'stabilized' ? '<b>Stabilized handling</b> — let go of the mouse and it levels and brakes to a hover.' : '<b>Punishing handling</b> — nothing is held for you: no altitude hold, no levelling, and torque swings the nose when you change power.';
    // page 1 — the four controls (swatch colours match the arrows in the illustration)
    const ax = (col, name, keys, txt) => `<i class="sw" style="background:${col}"></i><span class="k">${keys}</span><span><b>${name}</b> — ${txt}</span>`;
    const mx = '<kbd>Mouse ↔</kbd>';
    $('helpAxes').innerHTML = ax('#e8962c', 'Pitch', '<kbd>Mouse ↕</kbd>', 'tip the nose down to speed up, up to slow down.')
      + ax('#5d86b8', 'Roll', my ? kb('rollL', 'rollR') : `${mx} ${kb('rollL', 'rollR')}`, 'bank left / right. Banking is how you turn at speed.')
      + ax('#6f9a4a', 'Yaw', my ? `${mx} ${kb('yawL', 'yawR')}` : kb('yawL', 'yawR'), 'swing the nose left / right on the spot.')
      + ax('#c0483a', 'Collective', kb('collUp', 'collDown'), 'climb / descend. It does <i>not</i> move you forward.');
    $('helpSteps').innerHTML = li([`<b>Go forward:</b> push the mouse forward to tip the nose down about 15°. You keep accelerating while the nose is down.`, `<b>Hold speed:</b> ease the nose back toward level.`, `<b>Stop:</b> pull the nose up (flare) until the speed bleeds off, then level out.`, `<b>Turn:</b> ${my ? 'move the mouse sideways to yaw, and bank with ' + kb('rollL', 'rollR') : 'bank with the mouse and add ' + kb('yawL', 'yawR') + ' to bring the nose round'}. At speed, bank and pull back slightly.`, `<b>Height:</b> ${kb('collUp')} to climb over walls and arrows, ${kb('collDown')} to sink — then use the nose to move.`]);
    // page 2 — weapons
    const card = (img, alt, cap, title, keys, how, pts) => `<div class="gcard"><figure class="plate"><img src="assets/ui/howto/${img}.jpg" alt="${alt}"><figcaption>${cap}</figcaption></figure><h3>${title}<small>${keys}</small></h3>${how ? `<div class="how">${how}</div>` : ''}<ul>${li(pts)}</ul></div>`;
    $('helpWeapons').innerHTML = card('p2_cannon', 'The helicopter strafing a formation with its chin cannon', 'Hold the sight on the banner', `${kb('wpn1')} CANNON`, '30 MM · 600', `Hold ${kb('gunner')} for the gunner sight, ${kb('fire')} to fire.`,
      [`<b>The mouse aims the turret</b> while the helicopter flies on — keep moving as you shoot.`, `<b>Kill the knights around a banner</b> and the whole block breaks and runs.`, `<b>Short bursts.</b> About 4 s of fire overheats the gun.`])
      + card('p2_rockets', 'The helicopter diving at a siege tower and firing rockets', 'Rockets fly where the nose points', `${kb('wpn2')} ROCKETS`, '38', `Point the nose, ${kb('fire')} to ripple.`,
      [`<b>Dive at the target</b> and put the impact circle on it — no circle, no hit.`, `<b>Splash damage:</b> for packed formations, siege engines and walls.`, `<b>Pull out early.</b> A dive that ends in the ground ends the run.`])
      + card('p2_missiles', 'A lock box on a gate tower and a missile launching toward it', 'Two steady seconds, then fire', `${kb('wpn3')} MISSILES`, '8', `Keep the box on the target, ${kb('fire')} on the tone.`,
      [`<b>Lock takes 2 s</b> of steady aim on a tower, trebuchet or gate.`, `<b>One missile, one tower.</b> Save them for phase two.`, `<b>Fire unlocked</b> and it flies straight like a big rocket.`]);
    $('helpKeys').innerHTML = [[kb('fire'), 'fire'], [kb('wpn1', 'wpn2', 'wpn3') + ' / wheel', 'select weapon'], [kb('flares'), 'flares'], [kb('view'), 'cockpit view'], [`hold ${kb('freelook')}`, 'look around'], ['<kbd>Esc</kbd>', 'pause'], [kb('restart'), 'restart run']].map(([a, b]) => `<span>${a} <b>${b}</b></span>`).join('');
    // page 3 — the mission, staying alive, the pad
    $('helpMission').innerHTML = `<div class="gcard"><figure class="plate"><img src="assets/ui/howto/p3_map.jpg" alt="Hand-drawn map of the valley: castle, army, village, river and the rearm pad"><figcaption>The valley, the castle, the pad</figcaption></figure><h3>THE MISSION<small>3 PHASES · 10 MIN</small></h3><ol>${li([`<b>Break the field army.</b> Rout four of the six formations.`, `<b>Silence the walls.</b> Destroy the four gate towers and their ballistae.`, `<b>Kill the warlord</b> in the courtyard — walls on every side.`, `<b>Sundown ends the run</b> at ten minutes. Watch LIGHT, top left.`])}</ol></div>`
      + card('p3_threats', 'The helicopter banking hard and dropping flares as a ballista bolt misses', 'Jink on the warning', 'STAY ALIVE', `FLARES ${kb('flares')} · 6`, '',
        [`<b>Never hover in range.</b> Archers and ballistae punish a still target — keep moving and change height.`, `<b>Ballista tone = 1.5 s.</b> Turn hard or drop flares before it fires.`, `<b>Watch the boulder arcs</b> and move off the impact marker.`, `<b>Hits break systems</b> — tail rotor, hydraulics, engine. Check the panel bottom right.`])
      + card('p3_pad', 'The helicopter landing gently on the rearm pad on a hill', 'Slow and level onto the H', 'REARM &amp; REPAIR', 'PAD · EAST HILL', '',
        [`<b>The pad is the H</b> on the map, on the eastern hill. The HUD shows its distance.`, `<b>Touch down slow and level, then stop</b> — a hard landing is a crash.`, `<b>Sit tight:</b> ammo, flares and damaged systems come back while you stay on it.`, `<b>Out of ammo or limping?</b> The flight back is cheaper than losing the helicopter.`]);
    $('btnHelpGo').style.display = from === 'start' ? '' : 'none'; $('btnHelpBack').textContent = from === 'start' ? 'Back' : from === 'pause' ? 'Back to pause menu' : 'Back'; $('helpSkipL').style.display = from === 'pause' ? 'none' : '';
    this.helpPage(0);
    this.show('help');
  },
  clearSubs() { for (const id of ['subMain', 'subEnemy']) $(id).classList.remove('on'); },
  showPause(objective) { $('pauseObj').textContent = objective; perf.note(); this.show('pause'); },
  showEnd(won, cause, score, st) {
    const t = $('endTitle'); t.textContent = won ? 'THE SIEGE IS BROKEN' : 'HELICOPTER LOST'; t.className = won ? 'win' : 'loss';
    $('endSub').textContent = won ? 'The warlord is dead and his banner is down.' : `Cause: ${cause || 'unknown'}. Reached phase ${Math.max(1, st.phase)} of 3.`;
    $('endScore').innerHTML = `${score.toLocaleString()}<small>SCORE · ${st.mode === 'stabilized' ? 'STABILIZED ×0.5' : st.mode === 'assault' ? 'ASSAULT ×0.75' : 'PUNISHING ×1.0'}</small>`;
    const mm = s => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`;
    const rows = [['Time', mm(st.time)], ['Hull remaining', Math.round(st.hull) + '%'], ['Soldiers killed', st.kills], ['Formations routed', st.routed], ['Towers destroyed', st.towers], ['Siege engines destroyed', st.engines], ['Ammunition used', `${st.shots} rds · ${st.rockets} rkt · ${st.missiles} msl`], ['Rearm landings', st.landings], ['Hits taken', `${st.hits.arrowHits} arrows · ${st.hits.boltHits} bolts · ${st.hits.flakHits} flak · ${st.hits.boulderHits} boulders`]];
    $('endStats').innerHTML = rows.map(r => `<span>${r[0]}</span><span>${r[1]}</span>`).join('');
    this.show('end');
  },
};
