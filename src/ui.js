// Siege Wing — DOM menus: loading, title, settings/rebinding, pause, end screen
import { settings, saveSettings, applyPreset, PRESETS, ACTIONS, keyLabel, input } from './input.js';
import { audio } from './audio.js';

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
    const click = (id, f, snd = 'uiClick') => $(id).addEventListener('click', e => { audio.play(snd); f(e); });
    document.querySelectorAll('button,.card').forEach(b => b.addEventListener('mouseenter', () => audio.play('uiHover', { gain: 0.5 })));
    document.querySelectorAll('.card').forEach(c => c.addEventListener('click', () => { settings.mode = c.dataset.mode; saveSettings(); audio.play('uiClick'); this.refresh(); }));
    click('btnFly', () => { if (settings.hideHelp) cb.start(false); else this.showHelp('start'); });
    click('btnHelp', () => this.showHelp('menu'));
    click('btnPHelp', () => this.showHelp('pause'));
    click('btnHelpGo', () => cb.start(false));
    click('btnHelpBack', () => this.show(this.helpFrom === 'pause' ? 'pause' : 'menu'), 'uiBack');
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
    $('optQ').addEventListener('change', e => { settings.quality = e.target.value; saveSettings(); });
    this.refresh();
  },
  refresh() {
    document.querySelectorAll('.card').forEach(c => c.classList.toggle('sel', c.dataset.mode === settings.mode));
    $('optSens').value = settings.sens; $('optSensV').textContent = (+settings.sens).toFixed(2) + '×'; $('optAim').value = settings.aimSens; $('optAimV').textContent = (+settings.aimSens).toFixed(2) + '×'; $('optKey').value = settings.keySens; $('optKeyV').textContent = (+settings.keySens).toFixed(2) + '×'; $('optHelp').checked = !settings.hideHelp; $('optSubs').checked = settings.subtitles !== false; $('helpSkip').checked = !!settings.hideHelp; $('optInv').checked = settings.invertY; $('optVol').value = settings.volume; $('optMus').value = settings.musicVolume; $('optVox').value = settings.voiceVolume; $('optQ').value = settings.quality;
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
  // the flying guide: from === 'start' (before take-off), 'menu' or 'pause'
  showHelp(from) {
    this.helpFrom = from; const k = settings.keys, kb = (...a) => a.map(x => `<kbd>${keyLabel(k[x])}</kbd>`).join(' '), my = settings.mouseX === 'yaw';
    const mode = settings.mode;
    $('helpMode').innerHTML = mode === 'assault' ? 'ASSAULT handling — the helicopter holds its altitude when you let go of the collective. It does not stop or level by itself.' : mode === 'stabilized' ? 'STABILIZED handling — let go of the mouse and it levels and brakes to a hover.' : 'PUNISHING handling — nothing is held for you: no altitude hold, no levelling, and torque swings the nose when you change power.';
    const row = (keys, txt) => `<span class="k">${keys}</span><span>${txt}</span>`;
    $('helpKeys').innerHTML = row(kb('collUp', 'collDown'), '<b>Collective</b> — climb / descend. It does not move you forward.') + row(kb('yawL', 'yawR'), '<b>Yaw</b> — swing the nose left / right.') + row(kb('rollL', 'rollR'), '<b>Roll</b> — bank left / right.')
      + row(kb('wpn1', 'wpn2', 'wpn3'), '<b>Cannon / rockets / missiles</b> (or mouse wheel).') + row(kb('flares'), '<b>Flares</b> — break a ballista\'s aim.') + row(kb('view') + ' ' + kb('freelook'), '<b>Cockpit view</b> / hold to <b>look around</b>.') + row('<kbd>Esc</kbd> ' + kb('restart'), '<b>Pause menu</b> / <b>restart</b> the run.');
    $('helpMouse').innerHTML = `<b>Move forward / back</b> — pitch the nose down / up.<br><b>Move left / right</b> — ${my ? 'yaw the nose' : 'roll (bank)'}.<br><i style="background:rgba(255,176,46,.5)"></i><b>${keyLabel(k.fire)}</b> — fire the selected weapon.<br><i style="background:rgba(120,200,255,.3)"></i><b>Hold ${keyLabel(k.gunner)}</b> — gunner sight: the mouse aims the cannon, the helicopter flies on.<br><b>Wheel</b> — next weapon.`;
    $('helpSteps').innerHTML = [`<b>Go forward:</b> push the mouse forward to tip the nose down about 15°. The helicopter accelerates for as long as the nose is down.`, `<b>Hold speed:</b> ease the nose back toward level.`, `<b>Stop:</b> pull the nose up (flare) until the speed bleeds off, then level out.`, `<b>Turn:</b> ${my ? 'move the mouse sideways to yaw, and bank with ' + kb('rollL', 'rollR') : 'bank with the mouse and add ' + kb('yawL', 'yawR') + ' to bring the nose round'}. At speed, bank and pull back slightly.`, `<b>Shoot:</b> rockets fly where the nose points — dive at the target. For the cannon hold ${kb('gunner')} and aim with the mouse. Missiles: select ${kb('wpn3')}, keep the box on a tower for 2 s, fire on the tone.`, `<b>Land on the pad</b> (H on the map, eastern hill) slowly and level to rearm and repair.`].map(x => `<li>${x}</li>`).join('');
    $('helpTips').innerHTML = [`<b>Never hover in range.</b> Archers and ballistae punish a still target — keep moving and change height.`, `<b>Jink on the warning.</b> A ballista needs 1.5 s of steady aim: turn hard or drop flares when it calls.`, `<b>Watch the light.</b> The run ends at sundown — ten minutes.`].map(x => `<li>${x}</li>`).join('');
    $('btnHelpGo').style.display = from === 'start' ? '' : 'none'; $('btnHelpBack').textContent = from === 'start' ? 'Back' : from === 'pause' ? 'Back to pause menu' : 'Back'; $('helpSkipL').style.display = from === 'pause' ? 'none' : '';
    this.show('help');
  },
  clearSubs() { for (const id of ['subMain', 'subEnemy']) $(id).classList.remove('on'); },
  showPause(objective) { $('pauseObj').textContent = objective; this.show('pause'); },
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
