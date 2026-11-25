"""Ücretsiz Türkçe seslendirme.

Birincil : edge-tts  -> Microsoft'un Türkçe nöral sesleri (Emel = kadın, Ahmet = erkek).
           API anahtarı istemez; kelime zamanlarını da verir (karaoke altyazı için).
Yedek    : Piper     -> Tamamen çevrimdışı. config.yaml'da model yolu verilirse kullanılır.
           (Türkçe Piper sesleri erkektir.)
Para kazandıkça ElevenLabs gibi ücretli bir sağlayıcı buraya tek fonksiyonla eklenebilir.
"""
from __future__ import annotations

import asyncio
import re
import subprocess
import sys
import wave
from dataclasses import dataclass, field
from pathlib import Path

from .ffmpeg import to_wav

EDGE_VOICES = {
    "tr": {"kadin": "tr-TR-EmelNeural", "erkek": "tr-TR-AhmetNeural"},
    "en": {"kadin": "en-US-AvaNeural", "erkek": "en-US-AndrewNeural"},
}


@dataclass
class Speech:
    wav_path: Path
    duration: float
    words: list[tuple[str, float, float]] = field(default_factory=list)  # (kelime, başlangıç, bitiş) sn
    engine: str = ""


def _wav_duration(path: Path) -> float:
    with wave.open(str(path), "rb") as w:
        return w.getnframes() / float(w.getframerate())


def estimate_word_times(text: str, duration: float) -> list[tuple[str, float, float]]:
    """Kelime zamanı vermeyen motorlar için: süreyi kelime uzunluklarına göre paylaştırır.
    Noktalama sonrası küçük duraklama payı bırakır."""
    words = text.split()
    if not words:
        return []
    weights = [len(w) + 2 + (3 if re.search(r"[.!?…]$", w) else 1.5 if w.endswith(",") else 0) for w in words]
    usable = max(0.1, duration - 0.15)
    scale = usable / sum(weights)
    out, t = [], 0.05
    for w, wt in zip(words, weights):
        span = wt * scale
        speak = span * (0.8 if re.search(r"[.!?…,]$", w) else 0.95)
        out.append((w, t, t + speak))
        t += span
    return out


# ---------------- edge-tts ----------------
async def _edge_stream(text: str, voice: str, rate: str, mp3_path: Path):
    import edge_tts
    try:  # edge-tts 7+: kelime sınırları için açıkça istemek gerekiyor
        comm = edge_tts.Communicate(text, voice, rate=rate, boundary="WordBoundary")
    except TypeError:  # eski sürümler
        comm = edge_tts.Communicate(text, voice, rate=rate)
    words = []
    with open(mp3_path, "wb") as f:
        async for chunk in comm.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                start = chunk["offset"] / 1e7
                words.append((chunk["text"], start, start + chunk["duration"] / 1e7))
    return words


def _edge(text: str, gender: str, out: Path, rate: str, lang: str = "tr") -> Speech:
    mp3 = out.with_suffix(".mp3")
    boundaries = asyncio.run(_edge_stream(text, EDGE_VOICES[lang][gender], rate, mp3))
    if not mp3.exists() or mp3.stat().st_size == 0:
        raise RuntimeError("edge-tts ses döndürmedi")
    to_wav(mp3, out)
    dur = _wav_duration(out)
    # Orijinal metindeki kelimeleri (noktalamalı) zamanlarla eşleştir
    original = text.split()
    if boundaries and len(boundaries) == len(original):
        words = [(o, s, e) for o, (_, s, e) in zip(original, boundaries)]
    else:
        words = boundaries or estimate_word_times(text, dur)
    return Speech(out, dur, words, "edge-tts")


# ---------------- Piper (çevrimdışı yedek) ----------------
def _piper(text: str, out: Path, model: str, length_scale: float) -> Speech:
    raw = out.with_name(out.stem + "_raw.wav")
    subprocess.run([sys.executable, "-m", "piper", "-m", model, "-f", str(raw),
                    "--length-scale", str(length_scale)],
                   input=text.encode("utf-8"), check=True, capture_output=True)
    to_wav(raw, out)
    dur = _wav_duration(out)
    return Speech(out, dur, estimate_word_times(text, dur), "piper")


def _rate(base: str, speed: float) -> str:
    """'+8%' gibi temel hızın üstüne hız çarpanı ekler (1.10 -> +10 puan)."""
    pct = int(str(base).strip().rstrip('%') or 0) + round((speed - 1) * 100)
    return f"{pct:+d}%"


def synthesize(text: str, gender: str, out_wav: Path, cfg: dict, log=print, speed: float = 1.0,
               lang: str = "tr") -> Speech:
    """Metni seslendirir; edge-tts başarısız olursa Piper'a düşer. lang: tr | en"""
    lang = lang if lang in EDGE_VOICES else "tr"
    gender = gender if gender in ("kadin", "erkek") else "erkek"
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    engine = (cfg.get("motor") or "edge").lower()
    errors = []
    if engine == "edge":
        try:
            return _edge(text, gender, out_wav, _rate(cfg.get("hiz", "+8%"), speed), lang)
        except Exception as e:  # noqa: BLE001
            errors.append(f"edge-tts: {e.__class__.__name__}: {str(e)[:120]}")
    model = cfg.get("piper_model_en" if lang == "en" else "piper_model")
    if model:
        try:
            return _piper(text, out_wav, model, float(cfg.get("piper_length_scale", 0.95)) / speed)
        except Exception as e:  # noqa: BLE001
            errors.append(f"piper: {e}")
    raise RuntimeError("Seslendirme yapılamadı -> " + " | ".join(errors or ["motor yok"]))
