#!/usr/bin/env python3
"""Turn a song into a drum practice chart for /drums.

    python drumchart.py song.mp3 -o out/            # separate + transcribe
    python drumchart.py song.mp3 --drums drums.wav  # skip separation

Outputs in the output dir:
    chart.json     notes for the web app  (kick / snare / hihat lanes)
    drums.wav      isolated drum stem      (needs demucs)
    backing.wav    song without drums      (needs demucs)  <- play along with this
    chart.mid      General MIDI export of the chart

Requires: ffmpeg, numpy. Separation additionally needs `pip install demucs`.
"""
import argparse, json, shutil, struct, subprocess, sys
from pathlib import Path

import numpy as np

SR = 44100
N_FFT = 2048
HOP = 256
LANES = ["hihat", "snare", "kick"]
GM = {"kick": 36, "snare": 38, "hihat": 42}


# ---------- audio io ----------
def load_mono(path):
    cmd = ["ffmpeg", "-v", "error", "-i", str(path), "-f", "f32le", "-ac", "1", "-ar", str(SR), "-"]
    raw = subprocess.run(cmd, check=True, capture_output=True).stdout
    return np.frombuffer(raw, dtype=np.float32)


def separate(song, out):
    if not shutil.which("demucs") and subprocess.run([sys.executable, "-c", "import demucs"]).returncode:
        sys.exit("demucs not installed. `pip install demucs`, or pass --drums <stem> to skip separation.")
    tmp = out / "_demucs"
    subprocess.run([sys.executable, "-m", "demucs", "--two-stems=drums", "-n", "htdemucs",
                    "--float32", "-o", str(tmp), str(song)], check=True)
    stem_dir = next((tmp / "htdemucs").iterdir())
    drums, backing = stem_dir / "drums.wav", stem_dir / "no_drums.wav"
    shutil.move(drums, out / "drums.wav")
    shutil.move(backing, out / "backing.wav")
    shutil.rmtree(tmp)
    return out / "drums.wav"


# ---------- onset detection ----------
def stft_mag(x):
    win = np.hanning(N_FFT).astype(np.float32)
    n = 1 + max(0, (len(x) - N_FFT) // HOP)
    idx = np.arange(N_FFT)[None, :] + HOP * np.arange(n)[:, None]
    return np.abs(np.fft.rfft(x[idx] * win, axis=1))


def band_novelty(mag, lo, hi):
    freqs = np.fft.rfftfreq(N_FFT, 1 / SR)
    sel = (freqs >= lo) & (freqs < hi)
    s = np.log1p(30 * mag[:, sel] / mag.max())
    flux = np.maximum(0, np.diff(s, axis=0, prepend=s[:1])).sum(axis=1)
    return flux, s.mean(axis=1)


def pick_peaks(nov, sens, min_gap_s, gate):
    # adaptive threshold: local mean + k * local std over ~0.75s
    w = int(0.75 * SR / HOP)
    k = np.ones(w) / w
    mean = np.convolve(nov, k, "same")
    std = np.sqrt(np.maximum(np.convolve(nov ** 2, k, "same") - mean ** 2, 0))
    thr = mean + sens * std
    ref = np.percentile(nov, 99) + 1e-9
    peaks, gap = [], int(min_gap_s * SR / HOP)
    r = 3
    for i in range(r, len(nov) - r):
        if nov[i] >= nov[i - r:i + r + 1].max() and nov[i] > thr[i] and nov[i] > 0.08 * ref:
            if peaks and i - peaks[-1] < gap:
                if nov[i] > nov[peaks[-1]]:
                    peaks[-1] = i
            else:
                peaks.append(i)
    peaks = np.array(peaks, dtype=int)
    if peaks.size:  # drop weak peaks relative to this lane's loud hits (cross-band bleed)
        peaks = peaks[nov[peaks] / ref >= gate * np.percentile(nov[peaks] / ref, 90)]
    return peaks, nov / ref


def transcribe(x, sens=1.0, gate=0.7):
    mag = stft_mag(x)
    bands = {"kick": (35, 150), "snare": (1200, 5000), "hihat": (7000, 16000)}
    nov, level, peaks, norm = {}, {}, {}, {}
    for name, (lo, hi) in bands.items():
        nov[name], level[name] = band_novelty(mag, lo, hi)
        peaks[name], norm[name] = pick_peaks(nov[name], sens, 0.07 if name != "hihat" else 0.04, gate)
    fps = SR / HOP
    notes = []
    snare_t = peaks["snare"] / fps
    kick_t = peaks["kick"] / fps
    for i in peaks["kick"]:
        notes.append({"t": i / fps, "lane": "kick", "v": float(norm["kick"][i])})
    for i in peaks["snare"]:
        notes.append({"t": i / fps, "lane": "snare", "v": float(norm["snare"][i])})
    for i in peaks["hihat"]:
        t = i / fps
        # a snare's noise tail lights the hat band too; keep a hat only if it is clearly its own hit
        near_snare = snare_t.size and np.abs(snare_t - t).min() < 0.03
        if near_snare and norm["hihat"][i] < 0.6:
            continue
        notes.append({"t": t, "lane": "hihat", "v": float(norm["hihat"][i])})
    notes.sort(key=lambda n: n["t"])
    return notes, nov


# ---------- tempo & quantise ----------
def estimate_tempo(nov, lo=70, hi=180):
    env = nov["kick"] + nov["snare"] + 0.5 * nov["hihat"]
    env = env - env.mean()
    fps = SR / HOP
    ac = np.correlate(env, env, "full")[len(env) - 1:]
    best, best_score = 120.0, -1
    for bpm in np.arange(lo, hi, 0.25):
        lag = fps * 60 / bpm
        score = sum(np.interp(lag * m, np.arange(len(ac)), ac) for m in (1, 2, 4))
        score *= 1 - 0.15 * abs(np.log2(bpm / 110))  # mild prior toward common tempi
        if score > best_score:
            best, best_score = bpm, score
    return float(best)


def fit_grid(notes, bpm, div=4):
    step = 60 / bpm / div
    ts = np.array([n["t"] for n in notes if n["lane"] != "hihat"] or [n["t"] for n in notes])
    offs = np.arange(0, step, 0.002)
    cost = [np.mean(np.abs(((ts - o + step / 2) % step) - step / 2)) for o in offs]
    return float(offs[int(np.argmin(cost))]), step


def refine_bpm(notes, bpm):
    best = (1e9, bpm, 0)
    for b in np.arange(bpm - 2, bpm + 2, 0.05):
        off, step = fit_grid(notes, b)
        ts = np.array([n["t"] for n in notes])
        err = np.mean(np.abs(((ts - off + step / 2) % step) - step / 2))
        if err < best[0]:
            best = (err, b, off)
    return float(best[1]), float(best[2])


def quantise(notes, bpm, offset, div=4, tol=0.4):
    step = 60 / bpm / div
    for n in notes:
        k = round((n["t"] - offset) / step)
        snapped = offset + k * step
        if abs(snapped - n["t"]) <= tol * step:
            n["t"] = snapped
    # drop duplicates created by snapping
    seen, out = set(), []
    for n in notes:
        key = (n["lane"], round(n["t"], 3))
        if key not in seen:
            seen.add(key)
            out.append(n)
    return out


# ---------- midi ----------
def vlq(n):
    b = [n & 0x7F]
    while n >> 7:
        n >>= 7
        b.append((n & 0x7F) | 0x80)
    return bytes(reversed(b))


def write_midi(path, notes, bpm):
    ppq = 480
    tick = lambda t: int(round(t * bpm / 60 * ppq))
    ev = []
    for n in notes:
        k = tick(n["t"])
        vel = int(np.clip(50 + 77 * n.get("v", 1), 40, 127))
        ev += [(k, 0x99, GM[n["lane"]], vel), (k + 30, 0x89, GM[n["lane"]], 0)]
    ev.sort()
    trk = b"\x00\xff\x51\x03" + int(60e6 / bpm).to_bytes(3, "big")
    last = 0
    for k, st, nt, vel in ev:
        trk += vlq(k - last) + bytes([st, nt, vel])
        last = k
    trk += b"\x00\xff\x2f\x00"
    path.write_bytes(b"MThd" + struct.pack(">IHHH", 6, 0, 1, ppq) + b"MTrk" + struct.pack(">I", len(trk)) + trk)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("song")
    ap.add_argument("-o", "--out", default="out")
    ap.add_argument("--drums", help="already-isolated drum stem; skips separation")
    ap.add_argument("--sens", type=float, default=1.0, help="onset threshold in std devs; lower = more notes (default 1.0)")
    ap.add_argument("--gate", type=float, default=0.7, help="drop hits weaker than this fraction of the lane's loud hits; lower keeps ghost notes (default 0.7)")
    ap.add_argument("--bpm", type=float, help="override tempo detection")
    ap.add_argument("--no-quantize", action="store_true", help="keep the original micro-timing")
    ap.add_argument("--title")
    a = ap.parse_args()

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    drums = Path(a.drums) if a.drums else separate(a.song, out)
    x = load_mono(drums)
    notes, nov = transcribe(x, a.sens, a.gate)
    bpm = a.bpm or estimate_tempo(nov)
    bpm, offset = refine_bpm(notes, bpm) if not a.bpm else (bpm, fit_grid(notes, bpm)[0])
    if not a.no_quantize:
        notes = quantise(notes, bpm, offset)
    notes.sort(key=lambda n: n["t"])
    chart = {
        "title": a.title or Path(a.song).stem, "bpm": round(bpm, 2), "offset": round(offset, 4),
        "duration": round(len(x) / SR, 2), "lanes": LANES,
        "notes": [{"t": round(n["t"], 4), "l": LANES.index(n["lane"])} for n in notes],
    }
    (out / "chart.json").write_text(json.dumps(chart))
    write_midi(out / "chart.mid", notes, bpm)
    counts = {l: sum(n["lane"] == l for n in notes) for l in LANES}
    print(f"{chart['title']}: {bpm:.1f} BPM, {len(notes)} notes {counts} -> {out}/")


if __name__ == "__main__":
    main()
