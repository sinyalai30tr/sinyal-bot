"""Ses işleri: WAV okuma/yazma, telifsiz müzik ve efekt üretimi, miksaj.

Müzik kodla üretilir (lo-fi tarzı ritim + akor), bu yüzden telif sorunu yoktur.
`assets/music/` klasörüne kendi telifsiz parçalarını (mp3/wav) koyarsan onlardan biri
rastgele kullanılır.
"""
from __future__ import annotations

import random
import wave
from pathlib import Path

import numpy as np

from .ffmpeg import to_wav

SR = 44100


def read_wav(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as w:
        data = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
        if w.getnchannels() > 1:
            data = data.reshape(-1, w.getnchannels()).mean(axis=1)
    return data.astype(np.float32) / 32768.0


def write_wav(path: Path, x: np.ndarray) -> Path:
    x = np.clip(x, -1, 1)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((x * 32767).astype(np.int16).tobytes())
    return path


# ---------------- Sentez yardımcıları ----------------
def _env(n: int, attack: float, release: float) -> np.ndarray:
    a, r = max(1, int(attack * SR)), max(1, int(release * SR))
    e = np.ones(n, dtype=np.float32)
    e[:a] = np.linspace(0, 1, min(a, n))[: min(a, n)]
    e[-r:] *= np.linspace(1, 0, min(r, n))[: min(r, n)]
    return e


def _lowpass(x: np.ndarray, k: int) -> np.ndarray:
    return np.convolve(x, np.ones(k, dtype=np.float32) / k, mode="same") if k > 1 else x


def synth_music(duration: float, bpm: int = 96, seed: int = 0) -> np.ndarray:
    """Hafif lo-fi altyapı: Am-F-C-G akorları, bas, kick (pompalama etkili), hi-hat."""
    rng = np.random.default_rng(seed)
    n = int(duration * SR) + SR
    out = np.zeros(n, dtype=np.float32)
    beat = 60.0 / bpm
    chords = [(220.0, 261.63, 329.63), (174.61, 220.0, 261.63),
              (130.81, 164.81, 196.0), (196.0, 246.94, 293.66)]
    bar = 4 * beat
    t_chord = 2 * bar
    # Pad + bas
    i = 0
    while i * t_chord < duration + 1:
        s = int(i * t_chord * SR)
        length = min(int(t_chord * SR), n - s)
        if length <= 0:
            break
        t = np.arange(length) / SR
        notes = chords[i % 4]
        pad = sum(np.sin(2 * np.pi * f * t) + 0.5 * np.sin(2 * np.pi * f * 1.003 * t) for f in notes)
        pad = _lowpass(pad.astype(np.float32), 6) * _env(length, 0.4, 0.5) * 0.06
        bass = np.sin(2 * np.pi * notes[0] / 2 * t) * _env(length, 0.02, 0.3) * 0.12
        out[s:s + length] += pad + bass
        i += 1
    # Davul
    kick_len = int(0.28 * SR)
    kt = np.arange(kick_len) / SR
    kick = np.sin(2 * np.pi * (45 + 80 * np.exp(-kt * 30)) * kt) * np.exp(-kt * 14)
    hat_len = int(0.05 * SR)
    pump = np.ones(n, dtype=np.float32)
    nb = int((duration + 1) / beat)
    for b in range(nb):
        s = int(b * beat * SR)
        if b % 2 == 0 and s + kick_len < n:
            out[s:s + kick_len] += kick.astype(np.float32) * 0.35
            p = np.linspace(0.45, 1, int(0.22 * SR))  # "sidechain" pompalama
            pump[s:s + len(p)] = np.minimum(pump[s:s + len(p)], p)
        hs = int((b + 0.5) * beat * SR)
        if hs + hat_len < n:
            hat = np.diff(rng.standard_normal(hat_len + 1)).astype(np.float32)
            out[hs:hs + hat_len] += hat * np.exp(-np.arange(hat_len) / SR * 90) * 0.035
    out *= pump
    return out[: int(duration * SR)]


def whoosh(length: float = 0.4, seed: int = 1) -> np.ndarray:
    rng = np.random.default_rng(seed)
    n = int(length * SR)
    noise = rng.standard_normal(n).astype(np.float32)
    # Pencereyi daraltarak "yükselen" bir süpürme etkisi
    parts = np.array_split(noise, 8)
    swept = np.concatenate([_lowpass(p, k) for p, k in zip(parts, [40, 30, 22, 16, 11, 8, 6, 4])])
    env = np.sin(np.linspace(0, np.pi, n)) ** 2
    return swept * env * 0.5


def pop(length: float = 0.09) -> np.ndarray:
    t = np.arange(int(length * SR)) / SR
    return (np.sin(2 * np.pi * (900 - 4000 * t) * t) * np.exp(-t * 45) * 0.35).astype(np.float32)


def load_music(music_dir: Path, duration: float, seed: int) -> np.ndarray:
    """Klasörde müzik varsa onu, yoksa sentez müziği döndürür."""
    files = sorted([p for p in music_dir.glob("*") if p.suffix.lower() in (".mp3", ".wav", ".m4a", ".ogg")]) \
        if music_dir.exists() else []
    if files:
        src = random.Random(seed).choice(files)
        tmp = music_dir / f".__tmp_{src.stem}.wav"
        try:
            x = read_wav(to_wav(src, tmp))
        finally:
            tmp.unlink(missing_ok=True)
        if len(x) < duration * SR:  # Kısaysa döngüye al
            x = np.tile(x, int(duration * SR / max(1, len(x))) + 1)
        return x[: int(duration * SR)] * 0.6
    return synth_music(duration, seed=seed)


def mix(total: float, voice_parts: list[tuple[float, np.ndarray]], music: np.ndarray,
        sfx: list[tuple[float, np.ndarray]], music_gain: float = 0.22) -> np.ndarray:
    """Sesi, müziği ve efektleri birleştirir. Konuşma varken müzik kısılır (ducking)."""
    n = int(total * SR)
    voice = np.zeros(n, dtype=np.float32)
    for start, x in voice_parts:
        s = int(start * SR)
        e = min(n, s + len(x))
        voice[s:e] += x[: e - s]
    # Konuşma zarfı -> müziği kıs
    activity = _lowpass(np.abs(voice), int(0.15 * SR))
    activity = np.clip(activity / (activity.max() + 1e-6) * 4, 0, 1)
    m = np.zeros(n, dtype=np.float32)
    m[: min(n, len(music))] = music[:n]
    m *= music_gain * (1 - 0.55 * activity)
    fx = np.zeros(n, dtype=np.float32)
    for start, x in sfx:
        s = int(start * SR)
        e = min(n, s + len(x))
        if s < n:
            fx[s:e] += x[: e - s]
    out = voice * 1.0 + m + fx * 0.6
    peak = np.abs(out).max()
    return out / peak * 0.92 if peak > 0.92 else out
