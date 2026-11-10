#!/usr/bin/env python3
"""Siege Wing audio pipeline: ElevenLabs generation + mastering to game-ready .ogg.

  python gen.py fetch [vo|sfx|music]   generate missing sources into assets/audio/_src (cached, resumable)
  python gen.py process                master everything in _src into assets/audio/{vo,sfx,music} + manifest.json
  python gen.py all                    both

Needs: ffmpeg on PATH, numpy, scipy, requests, ELEVENLABS_API_KEY in ../../.env
"""
import concurrent.futures as cf, difflib, io, json, os, re, subprocess, sys, threading, time, wave
import numpy as np, requests
from scipy import signal
import spec

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, 'assets', 'audio')
SRC = os.path.join(OUT, '_src')
SR = 48000
API = 'https://api.elevenlabs.io'
KEY = None
STOP = threading.Event()      # set when the account runs out of credits
LOCK = threading.Lock()
USAGE = {'tts_chars': 0, 'sfx_seconds': 0.0, 'music_seconds': 0, 'stt_calls': 0}


def log(*a):
    with LOCK:
        print(*a, flush=True)


def load_key():
    global KEY
    for line in open(os.path.join(ROOT, '.env')):
        if line.startswith('ELEVENLABS_API_KEY='):
            KEY = line.split('=', 1)[1].strip().strip('"\'')
    if not KEY:
        sys.exit('ELEVENLABS_API_KEY missing from .env')


class Fatal(Exception):
    pass


def post(path, timeout=600, **kw):
    """POST with retry on rate limits / server errors. Returns the response."""
    for attempt in range(7):
        if STOP.is_set():
            raise Fatal('stopped')
        try:
            r = requests.post(API + path, headers={'xi-api-key': KEY}, timeout=timeout, **kw)
        except requests.RequestException as e:
            log('  net error, retrying:', type(e).__name__); time.sleep(4 + attempt * 4); continue
        if r.status_code == 200:
            return r
        txt = r.text[:400]
        if r.status_code == 429 or r.status_code >= 500 or 'too_many_concurrent' in txt or 'system_busy' in txt:
            time.sleep(3 + attempt * 5); continue
        if 'quota' in txt or r.status_code == 402:
            STOP.set(); raise Fatal('OUT OF CREDITS: ' + txt)
        raise RuntimeError(f'{r.status_code} {txt}')
    raise RuntimeError('gave up after retries: ' + path)


def write_wav(path, pcm, ch):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with wave.open(path + '.tmp', 'wb') as w:
        w.setnchannels(ch); w.setsampwidth(2); w.setframerate(SR); w.writeframes(pcm)
    os.replace(path + '.tmp', path)


# ------------------------------------------------------------------ fetch: voice
def norm_words(s):
    s = re.sub(r'\[[^\]]*\]|\([^)]*\)', ' ', s).lower().replace('-', ' ')
    return re.sub(r"[^a-z0-9 ]", '', s).split()


def transcribe(path):
    with open(path, 'rb') as f:
        r = post('/v1/speech-to-text', timeout=120, data={'model_id': 'scribe_v1', 'language_code': 'en', 'tag_audio_events': 'false'}, files={'file': f})
    USAGE['stt_calls'] += 1
    return r.json().get('text', '')


def fetch_vo_one(vid, speaker, text, dst, min_ratio):
    """Generate one line, transcribe it back, keep the best of up to 3 takes."""
    if os.path.exists(dst):
        return
    v = spec.VOICES[speaker]
    body = {'text': text, 'model_id': v['model'], 'voice_settings': {'stability': v['stability'], 'similarity_boost': 0.8, 'use_speaker_boost': True}}
    best = None
    for take in range(3):
        try:
            r = post(f"/v1/text-to-speech/{v['id']}?output_format=pcm_48000", json=body)
        except RuntimeError as e:
            if 'voice' in str(e).lower() and v['id'] != spec.VOICES['captain']['id']:
                log(f'  {vid}: voice {v["name"]} unavailable, falling back to George'); v = dict(v, id=spec.VOICES['captain']['id']); continue
            raise
        USAGE['tts_chars'] += len(text)
        tmp = f'{dst}.take{take}.wav'; write_wav(tmp, r.content, 1)
        heard = transcribe(tmp)
        ratio = difflib.SequenceMatcher(None, norm_words(text), norm_words(heard)).ratio()
        if best is None or ratio > best[0]:
            if best: os.remove(best[1])
            best = (ratio, tmp, heard)
        else:
            os.remove(tmp)
        if ratio >= min_ratio:
            break
    ratio, tmp, heard = best
    os.replace(tmp, dst)
    json.dump({'heard': heard, 'match': round(ratio, 3)}, open(dst[:-4] + '.json', 'w'))
    log(f'  vo {vid:<22} match={ratio:.2f} {"" if ratio >= min_ratio else "  <-- CHECK: heard " + repr(heard)}')


def vo_jobs():
    lines = {i: (s, t) for i, s, t, _ in spec.VO}
    jobs = []
    for vid, speaker, text, _ in spec.VO:
        dry = spec.VOICES[speaker]['fx'] == 'dry'
        jobs.append((vid, speaker, text, os.path.join(SRC, 'vo', vid + '.wav'), 0.5 if dry else 0.8))
    for role, ids in spec.CASTING.items():
        for alt in [k for k in spec.VOICES if k.startswith(role + '_alt_')]:
            for vid in ids:
                jobs.append((f'{vid}__{alt}', alt, lines[vid][1], os.path.join(SRC, 'vo', '_casting', f'{vid}__{alt}.wav'), 0.8))
    return jobs


# ------------------------------------------------------------- fetch: sfx, music
def fetch_sfx_one(sid, k, secs, flags, prompt):
    dst = os.path.join(SRC, 'sfx', f'{sid}_{k}.wav')
    if os.path.exists(dst):
        return
    body = {'text': prompt, 'duration_seconds': secs, 'prompt_influence': 0.45, 'model_id': 'eleven_text_to_sound_v2'}
    if 'L' in flags:
        body['loop'] = True
    r = post('/v1/sound-generation?output_format=pcm_48000', json=body)
    USAGE['sfx_seconds'] += secs
    write_wav(dst, r.content, 2)
    log(f'  sfx {sid}_{k}  {len(r.content) / (SR * 4):.1f}s')


def fetch_music_one(mid, secs, prompt):
    dst = os.path.join(SRC, 'music', mid + '.mp3')
    if os.path.exists(dst):
        return
    body = {'prompt': prompt, 'music_length_ms': int(secs * 1000), 'model_id': 'music_v1', 'force_instrumental': True}
    r = post('/v1/music?output_format=mp3_44100_192', json=body, timeout=900)
    USAGE['music_seconds'] += secs
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    open(dst + '.tmp', 'wb').write(r.content); os.replace(dst + '.tmp', dst)
    log(f'  music {mid}  {len(r.content) / 1e6:.1f} MB')


def fetch(which):
    jobs = []
    if which in ('all', 'vo'):
        jobs += [(fetch_vo_one, j) for j in vo_jobs()]
    if which in ('all', 'music'):
        jobs += [(fetch_music_one, (m[0], m[1], m[4])) for m in spec.MUSIC]
    if which in ('all', 'sfx'):
        for sid, _, secs, n, flags, _, prompt in spec.SFX:
            jobs += [(fetch_sfx_one, (sid, k + 1, secs, flags, prompt)) for k in range(n)]
    fails = []

    def run(job):
        fn, args = job
        if STOP.is_set():
            return
        try:
            fn(*args)
        except Fatal as e:
            fails.append((args[0], str(e)))
        except Exception as e:
            fails.append((args[0], repr(e)[:300])); log('  FAILED', args[0], repr(e)[:300])

    with cf.ThreadPoolExecutor(4) as ex:
        list(ex.map(run, jobs))
    log(f'fetch done: {len(jobs)} jobs, {len(fails)} failed. usage this run: {USAGE}')
    for f in fails[:40]:
        log('  fail:', f)


# ------------------------------------------------------------------- dsp helpers
def load(path, ch):
    raw = subprocess.run(['ffmpeg', '-v', 'error', '-i', path, '-f', 'f32le', '-ac', str(ch), '-ar', str(SR), '-'], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32).reshape(-1, ch).astype(np.float64)


def save(path, x, q):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    x = np.clip(x, -1, 1).astype(np.float32)
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'f32le', '-ac', str(x.shape[1]), '-ar', str(SR), '-i', '-', '-c:a', 'libvorbis', '-q:a', str(q), path], input=x.tobytes(), check=True)


def db(v):
    return 20 * np.log10(max(v, 1e-9))


def rms_active(x):
    """RMS over the frames that actually carry signal (ignores gaps and tails)."""
    m = x.mean(axis=1) if x.ndim > 1 else x
    n = SR // 50
    if len(m) < n * 2:
        return float(np.sqrt(np.mean(m ** 2)) + 1e-9)
    fr = np.sqrt(np.mean(m[:len(m) // n * n].reshape(-1, n) ** 2, axis=1))
    act = fr[fr > fr.max() * 0.1]
    return float(np.sqrt(np.mean(act ** 2)) + 1e-9)


def trim(x, thresh_db=-48, head=0.004, tail=0.08):
    env = np.abs(x).max(axis=1)
    idx = np.nonzero(env > env.max() * 10 ** (thresh_db / 20))[0]
    if not len(idx):
        return x
    return x[max(0, idx[0] - int(head * SR)):min(len(x), idx[-1] + int(tail * SR))]


def fade(x, fin=0.003, fout=0.04):
    x = x.copy(); a, b = min(len(x), int(fin * SR)), min(len(x), int(fout * SR))
    if a: x[:a] *= np.linspace(0, 1, a)[:, None]
    if b: x[-b:] *= np.linspace(1, 0, b)[:, None] ** 1.5
    return x


def to_level(x, rms_db=None, peak_db=-1.0):
    """Gain to a target active-RMS, never exceeding the peak ceiling."""
    peak = np.abs(x).max() + 1e-9
    g = 10 ** (peak_db / 20) / peak
    if rms_db is not None:
        g = min(g, 10 ** (rms_db / 20) / rms_active(x))
    return x * g


def band(x, lo, hi, order=4):
    sos = signal.butter(order, [lo, hi], 'bandpass', fs=SR, output='sos')
    return signal.sosfilt(sos, x, axis=0)


def compress(x, thr_db=-28, ratio=6, att=0.004, rel=0.09):
    """Feed-forward compressor, vectorised (attack/release approximated by two smoothers)."""
    m = np.abs(x).max(axis=1)
    a = np.exp(-1 / (att * SR)); fast = signal.lfilter([1 - a], [1, -a], m)
    r = np.exp(-1 / (rel * SR)); slow = signal.lfilter([1 - r], [1, -r], m)
    env_db = 20 * np.log10(np.maximum(np.maximum(fast, slow), 1e-6))
    gain_db = -np.maximum(0, env_db - thr_db) * (1 - 1 / ratio)
    return x * (10 ** (gain_db / 20))[:, None]


def radio_chain(x, lo, hi, drive, noise_db, squelch, seed):
    """Comms treatment: band-limit, hard compression, saturation, noise bed, optional key-up click + squelch tail."""
    rng = np.random.default_rng(seed)
    y = band(x, lo, hi)
    y = compress(y / (np.abs(y).max() + 1e-9))
    y = y / (np.abs(y).max() + 1e-9)
    y = np.tanh(y * drive) / np.tanh(drive)
    y = y + 0.45 * band(y, 1500, 2700, 2)          # presence bump: the "telephone honk"
    y = band(y, lo * 0.9, hi * 1.1, 2)
    y = to_level(y, -20, -3)
    lvl = rms_active(y)
    head, tail = (int(0.07 * SR), int(0.19 * SR)) if squelch else (int(0.02 * SR), int(0.05 * SR))
    out = np.zeros((head + len(y) + tail, 1)); out[head:head + len(y)] = y
    if noise_db is not None:                        # carrier hiss for the whole transmission
        n = band(rng.standard_normal((len(out), 1)), lo, hi, 2)
        n *= lvl * 10 ** (noise_db / 20) / (np.sqrt(np.mean(n ** 2)) + 1e-9)
        out += fade(n, 0.002, 0.002)
    if squelch:
        k = int(0.035 * SR)                         # key-up: short click + static burst
        c = band(rng.standard_normal((k, 1)), 800, 3200, 2); c *= lvl * 0.9 / (np.sqrt(np.mean(c ** 2)) + 1e-9)
        out[:k] += c * np.exp(-np.arange(k) / (0.012 * SR))[:, None]
        k = int(0.15 * SR)                          # squelch tail: "kshh" then a hard cut
        s = band(rng.standard_normal((k, 1)), 900, 3400, 2); s *= lvl * 0.7 / (np.sqrt(np.mean(s ** 2)) + 1e-9)
        s *= (0.55 + 0.45 * np.exp(-np.arange(k) / (0.05 * SR)))[:, None]
        p = head + len(y) + int(0.02 * SR); out[p:p + k] += s[:len(out) - p]
        out = out[:p + k]
        out[-int(0.004 * SR):] *= np.linspace(1, 0, int(0.004 * SR))[:, None]
    return np.tanh(out * 1.1) / 1.1


FX = {
    'radio':    lambda x, s: radio_chain(x, 380, 3100, 2.6, -27, True, s),    # long-range radio net
    'intercom': lambda x, s: radio_chain(x, 240, 4300, 1.6, -40, False, s),   # crew headsets
    'betty':    lambda x, s: radio_chain(x, 300, 5200, 1.2, None, False, s),  # cockpit warning speaker
    'dry':      lambda x, s: to_level(fade(x, 0.003, 0.05), -18, -1),         # world voices: engine adds distance + reverb
}


# --------------------------------------------------------------- music loop find
def loop_points(x):
    """Find (start, end) so that what follows `end` sounds like what follows `start`."""
    m = x.mean(axis=1); hop = 1024
    _, _, Z = signal.stft(m, SR, nperseg=2048, noverlap=2048 - hop, boundary=None, padded=False)
    mag = np.abs(Z).T                                # frames x bins
    freqs = np.linspace(0, SR / 2, mag.shape[1]); edges = np.geomspace(40, 12000, 33)
    F = np.stack([mag[:, (freqs >= a) & (freqs < b)].sum(axis=1) for a, b in zip(edges[:-1], edges[1:])], axis=1)
    F = np.log1p(F * 50); fps = SR / hop; dur = len(m) / SR
    W = int(3.0 * fps)

    def wins(frames):
        A = np.stack([F[f:f + W].ravel() for f in frames]).astype(np.float32)
        A -= A.mean(axis=1, keepdims=True); A /= np.linalg.norm(A, axis=1, keepdims=True) + 1e-9
        return A
    s_fr = np.arange(int(1.5 * fps), int(min(0.35 * dur, 32) * fps), 2)
    t_fr = np.arange(int(0.62 * dur * fps), len(F) - W - int(0.5 * fps), 2)
    sc = wins(s_fr) @ wins(t_fr).T
    sc += 0.03 * (t_fr[None, :] - s_fr[:, None]) / len(F)      # prefer longer loops
    i, j = np.unravel_index(np.argmax(sc), sc.shape)
    S, T = int(s_fr[i] * hop), int(t_fr[j] * hop)
    # sample-accurate alignment of the seam
    lp = signal.sosfilt(signal.butter(2, 400, 'low', fs=SR, output='sos'), m)
    tpl = lp[S:S + SR // 4]; seg = lp[T - hop:T + hop + SR // 4]
    T += int(np.argmax(signal.correlate(seg, tpl, 'valid'))) - hop
    return S, T, float(sc[i, j])


def make_loop(x, S, T, xf=0.06):
    n = int(xf * SR); body = x[S:T].copy(); w = np.linspace(0, 1, n)[:, None]
    body[-n:] = body[-n:] * (1 - w) + x[S - n:S] * w     # end of loop blends into the lead-in of its start
    return body


def lufs(path):
    out = subprocess.run(['ffmpeg', '-hide_banner', '-nostats', '-i', path, '-af', 'ebur128', '-f', 'null', '-'], capture_output=True, text=True).stderr
    m = re.findall(r'I:\s+(-?[\d.]+) LUFS', out)
    return float(m[-1]) if m else -20.0


# ------------------------------------------------------------------------ process
def rel(p):
    return os.path.relpath(p, OUT).replace(os.sep, '/')


def process():
    man = {'generated': time.strftime('%Y-%m-%d'), 'sample_rate': SR, 'format': 'ogg vorbis',
           'levels': {'vo': 'active RMS -20 dBFS', 'sfx one-shots': 'peak -1 dBFS', 'sfx loops': 'active RMS -22 dBFS', 'music': '-16 LUFS integrated'},
           'call_signs': {'player': 'Hammer Two-Six', 'command': 'Anvil Actual'}, 'vo': [], 'casting': [], 'sfx': [], 'music': []}
    # ---- voice
    for n, (vid, speaker, text, event) in enumerate(spec.VO):
        src = os.path.join(SRC, 'vo', vid + '.wav')
        if not os.path.exists(src):
            continue
        v = spec.VOICES[speaker]; x = trim(load(src, 1), -42, 0.01, 0.12)
        y = FX[v['fx']](fade(x, 0.004, 0.06), n)
        dst = os.path.join(OUT, 'vo', speaker if v['fx'] != 'dry' else 'enemy', vid + '.ogg'); save(dst, y, 4)
        qa = json.load(open(src[:-4] + '.json')) if os.path.exists(src[:-4] + '.json') else {}
        man['vo'].append({'id': vid, 'speaker': speaker, 'voice': v['name'], 'fx': v['fx'], 'text': re.sub(r'\s*\[[^\]]*\]\s*', ' ', text).strip(),
                          'event': event, 'file': rel(dst), 'dur': round(len(y) / SR, 2), 'stt_match': qa.get('match')})
    cdir = os.path.join(SRC, 'vo', '_casting')
    for f in sorted(os.listdir(cdir)) if os.path.isdir(cdir) else []:
        if not f.endswith('.wav'):
            continue
        vid, alt = f[:-4].split('__'); v = spec.VOICES[alt]
        y = FX[v['fx']](fade(trim(load(os.path.join(cdir, f), 1), -42, 0.01, 0.12), 0.004, 0.06), 7)
        dst = os.path.join(OUT, 'vo', '_casting', f[:-4] + '.ogg'); save(dst, y, 4)
        man['casting'].append({'line': vid, 'role': alt.split('_alt_')[0], 'voice': v['name'], 'file': rel(dst)})
    # ---- sfx
    for sid, group, secs, n, flags, hook, prompt in spec.SFX:
        files, durs, seam = [], [], None
        for k in range(1, n + 1):
            src = os.path.join(SRC, 'sfx', f'{sid}_{k}.wav')
            if not os.path.exists(src):
                continue
            x = load(src, 2)
            if 'L' in flags:
                r = rms_active(x); jump = float(np.abs(x[0] - x[-1]).max()); seam = round(db(jump / r), 1)
                if jump > r * 0.25:                      # seam not clean: fold 60 ms of the tail under the head
                    m = int(0.06 * SR); w = np.linspace(0, 1, m)[:, None]
                    x = np.concatenate([x[:m] * w + x[-m:] * (1 - w), x[m:-m]])
                x = to_level(x, -22, -1)
            else:
                if 'M' in flags:
                    x = x.mean(axis=1, keepdims=True)
                x = to_level(fade(trim(x, -50, 0.003, 0.12), 0.002, 0.12), None, -1)
            dst = os.path.join(OUT, 'sfx', group, f'{sid}_{k}.ogg' if n > 1 else f'{sid}.ogg'); save(dst, x, 5)
            files.append(rel(dst)); durs.append(round(len(x) / SR, 2))
        if files:
            e = {'id': sid, 'group': group, 'files': files, 'dur': durs, 'loop': 'L' in flags, 'channels': 1 if 'M' in flags else 2,
                 'positional': 'M' in flags, 'hook': hook, 'prompt': prompt}
            if seam is not None: e['seam_db'] = seam
            man['sfx'].append(e)
    # ---- music
    for mid, secs, loop, hook, prompt in spec.MUSIC:
        src = os.path.join(SRC, 'music', mid + '.mp3')
        if not os.path.exists(src):
            continue
        L = lufs(src); x = load(src, 2)
        g = min(10 ** ((-16 - L) / 20), 0.89 / (np.abs(x).max() + 1e-9)); x = x * g
        full = fade(trim(x, -55, 0.0, 0.3), 0.002, 0.25)
        dst = os.path.join(OUT, 'music', mid + '.ogg'); save(dst, full, 6)
        e = {'id': mid, 'file': rel(dst), 'dur': round(len(full) / SR, 2), 'lufs': round(L + db(g), 1), 'loop': loop, 'hook': hook, 'prompt': prompt}
        if loop:
            S, T, score = loop_points(x)
            dst = os.path.join(OUT, 'music', mid + '_loop.ogg'); save(dst, make_loop(x, S, T), 6)
            e.update({'loop_file': rel(dst), 'loop_dur': round((T - S) / SR, 2), 'loop_src_start': round(S / SR, 2), 'loop_src_end': round(T / SR, 2), 'loop_match': round(score, 3),
                      'intro_note': f'play {mid}.ogg from 0 and it reaches the loop body at {S / SR:.2f}s; or start {mid}_loop.ogg directly'})
        man['music'].append(e)
        log(f'  music {mid}: {e["dur"]}s {e["lufs"]} LUFS' + (f'  loop {e["loop_dur"]}s match={e["loop_match"]}' if loop else ''))
    json.dump(man, open(os.path.join(OUT, 'manifest.json'), 'w'), indent=1)
    log(f'processed: {len(man["vo"])} vo lines, {len(man["casting"])} casting takes, {sum(len(s["files"]) for s in man["sfx"])} sfx files ({len(man["sfx"])} sounds), {len(man["music"])} music cues')


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'all'
    if cmd in ('fetch', 'all'):
        load_key(); fetch(sys.argv[2] if len(sys.argv) > 2 else 'all')
    if cmd in ('process', 'all'):
        process()
