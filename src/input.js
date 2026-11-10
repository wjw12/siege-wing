// Siege Wing — input: keyboard + mouse (pointer lock), rebindable actions, two presets
export const ACTIONS = [
  ['collUp', 'Collective up'], ['collDown', 'Collective down'], ['yawL', 'Yaw left'], ['yawR', 'Yaw right'],
  ['rollL', 'Roll left'], ['rollR', 'Roll right'], ['fire', 'Fire weapon'], ['gunner', 'Gunner mode (hold)'],
  ['wpn1', 'Cannon'], ['wpn2', 'Rockets'], ['wpn3', 'Missiles'], ['flares', 'Flares'], ['view', 'Switch view'], ['freelook', 'Free look (hold)'],
  ['restart', 'Restart run'], ['pause', 'Pause'],
];
export const PRESETS = {
  delta: { name: 'Delta (mouse = pitch + roll)', mouseX: 'roll', keys: { collUp: 'KeyW', collDown: 'KeyS', yawL: 'KeyA', yawR: 'KeyD', rollL: 'KeyQ', rollR: 'KeyE', fire: 'Mouse0', gunner: 'Mouse2', wpn1: 'Digit1', wpn2: 'Digit2', wpn3: 'Digit3', flares: 'KeyX', view: 'KeyC', freelook: 'AltLeft', restart: 'KeyR', pause: 'KeyP' } },
  battlefield: { name: 'Battlefield (mouse = pitch + yaw)', mouseX: 'yaw', keys: { collUp: 'KeyW', collDown: 'KeyS', yawL: 'KeyQ', yawR: 'KeyE', rollL: 'KeyA', rollR: 'KeyD', fire: 'Mouse0', gunner: 'Mouse2', wpn1: 'Digit1', wpn2: 'Digit2', wpn3: 'Digit3', flares: 'KeyX', view: 'KeyC', freelook: 'AltLeft', restart: 'KeyR', pause: 'KeyP' } },
};
const LS = 'siegewing.settings.v2';
export const settings = Object.assign({ preset: 'delta', keys: { ...PRESETS.delta.keys }, mouseX: 'roll', invertY: false, sens: 1.0, aimSens: 1.0, keySens: 1.0, hideHelp: false, subtitles: true, mode: 'assault', volume: 0.8, musicVolume: 0.7, voiceVolume: 1.0, quality: 'high', seenHelp: false }, load());
function load() { try { return JSON.parse(localStorage.getItem(LS)) || {}; } catch (e) { return {}; } }
export function saveSettings() { try { localStorage.setItem(LS, JSON.stringify(settings)); } catch (e) { } }
export function applyPreset(name) { settings.preset = name; settings.keys = { ...PRESETS[name].keys }; settings.mouseX = PRESETS[name].mouseX; saveSettings(); }
export function keyLabel(code) {
  if (!code) return '—';
  return code.replace(/^Key/, '').replace(/^Digit/, '').replace('Mouse0', 'LMB').replace('Mouse1', 'MMB').replace('Mouse2', 'RMB').replace('AltLeft', 'Alt').replace('AltRight', 'R-Alt').replace('ShiftLeft', 'Shift').replace('ControlLeft', 'Ctrl').replace('Arrow', '');
}

export const input = {
  held: new Set(), hit: new Set(), dx: 0, dy: 0, wheel: 0, locked: false, enabled: false,
  virtual: null,   // dev autopilot: { held:Set, dx, dy }
  capture: null,   // rebinding: callback(code)
  canvas: null,
  init(canvas) {
    this.canvas = canvas;
    const kd = (code, e) => {
      if (this.capture) { const c = this.capture; this.capture = null; c(code); e && e.preventDefault(); return; }
      if (!this.held.has(code)) this.hit.add(code); this.held.add(code);
    };
    addEventListener('keydown', e => { if (e.repeat) return; if (this.locked && (e.code === 'AltLeft' || e.code === 'Tab' || e.code.startsWith('F') === false && e.ctrlKey)) e.preventDefault(); if (e.code === 'AltLeft' || e.code === 'Tab') e.preventDefault(); kd(e.code, e); });
    addEventListener('keyup', e => { this.held.delete(e.code); if (e.code === 'AltLeft') e.preventDefault(); });
    addEventListener('mousedown', e => { if (this.locked || this.capture) { kd('Mouse' + e.button, e); } });
    addEventListener('mouseup', e => this.held.delete('Mouse' + e.button));
    addEventListener('contextmenu', e => e.preventDefault());
    addEventListener('mousemove', e => { if (this.locked) { this.dx += e.movementX; this.dy += e.movementY; } });
    addEventListener('wheel', e => { if (this.locked) this.wheel += Math.sign(e.deltaY); }, { passive: true });
    addEventListener('blur', () => this.held.clear());
    document.addEventListener('pointerlockchange', () => { this.locked = document.pointerLockElement === canvas; if (!this.locked) { this.held.clear(); this.onUnlock && this.onUnlock(); } });
  },
  lock() { if (!this.locked && this.canvas.requestPointerLock) { try { const p = this.canvas.requestPointerLock({ unadjustedMovement: true }); if (p && p.catch) p.catch(() => { try { this.canvas.requestPointerLock(); } catch (e) { } }); } catch (e) { } } },
  unlock() { if (document.pointerLockElement) document.exitPointerLock(); },
  down(a) { const v = this.virtual; if (v && v.held.has(a)) return true; return this.enabled && this.held.has(settings.keys[a]); },
  pressed(a) { const v = this.virtual; if (v && v.hit && v.hit.has(a)) return true; return this.enabled && this.hit.has(settings.keys[a]); },
  axis(neg, pos) { return (this.down(pos) ? 1 : 0) - (this.down(neg) ? 1 : 0); },
  mouse() { const v = this.virtual; return v ? { dx: v.dx || 0, dy: v.dy || 0 } : this.enabled ? { dx: this.dx, dy: this.dy } : { dx: 0, dy: 0 }; },
  endFrame() { this.hit.clear(); this.dx = 0; this.dy = 0; this.wheel = 0; if (this.virtual && this.virtual.hit) this.virtual.hit.clear(); },
};
