"""Bir konuyu (LLM çıktısı) baştan sona videoya çevirir ve onay için meta dosyası yazar."""
from __future__ import annotations

import json
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Callable

from ..config import ROOT
from . import audio, tts
from .render import ACCENTS, Scene, Timeline, render

SCENE_GAP = 0.12   # Sahneler arası nefes (sn)
TAIL = 0.6         # Sondaki bekleme (sn)
TIPLER = {"hook", "bilgi", "rakam", "soru", "kapanis"}


def scenes_from_topic(topic: dict) -> list[dict]:
    """LLM'in verdiği sahneleri kullanır; yoksa senaryoyu cümlelere bölerek sahne üretir."""
    sc = [s for s in topic.get("sahneler") or [] if str(s.get("seslendirme", "")).strip()]
    if sc:
        return sc
    sentences = [s for s in re.split(r"(?<=[.!?…])\s+", topic.get("senaryo", "").strip()) if s]
    if not sentences:
        raise ValueError("Konuda senaryo veya sahne yok")
    groups = [sentences[0]] + [" ".join(sentences[i:i + 2]) for i in range(1, len(sentences), 2)]
    out = []
    for i, g in enumerate(groups):
        tip = "hook" if i == 0 else ("kapanis" if i == len(groups) - 1 else "bilgi")
        ekran = topic.get("ekran_basligi") if i == 0 else " ".join(g.split()[:4])
        out.append({"tip": tip, "ekran": ekran or g[:30], "seslendirme": g})
    return out


def choose_gender(topic: dict, index: int) -> str:
    g = str(topic.get("ses", "")).lower().replace("ı", "i")
    if g in ("kadin", "erkek"):
        return g
    return "kadin" if index % 2 else "erkek"


def slugify(s: str, n: int = 40) -> str:
    tr = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s.translate(tr)).strip("-").lower()
    return s[:n] or "konu"


def language_view(topic: dict, lang: str) -> dict | None:
    """Konunun istenen dildeki görünümü. İngilizce alanlar topic["en"] içinde durur;
    kaynaklar, doğrulanacaklar ve ses ortak kalır. İngilizce sürüm yoksa None."""
    if lang == "tr":
        return topic
    sub = topic.get(lang)
    if not isinstance(sub, dict) or not (sub.get("sahneler") or sub.get("senaryo")):
        return None
    view = {k: v for k, v in topic.items() if k in ("kaynaklar", "dogrulanacaklar", "ses", "aday_idleri")}
    view.update(sub)
    view.setdefault("kategori", "")
    return view


def make_video(topic: dict, videos_dir: Path, cfg: dict, date_str: str, index: int = 0,
               log: Callable[[str], None] = print, lang: str = "tr") -> Path:
    """Videoyu üretir; yolunu döndürür. Yanına onay için <ad>.json yazar.
    lang="en" ise konunun İngilizce sürümünü (topic["en"]) İngilizce sesle üretir."""
    base_title = topic.get("baslik", "konu")
    view = language_view(topic, lang)
    if view is None:
        raise ValueError(f"Konunun '{lang}' sürümü yok")
    topic = view
    vcfg = cfg.get("video", {})
    tcfg = cfg.get("tts", {})
    videos_dir.mkdir(parents=True, exist_ok=True)
    # Aynı konunun iki dili yan yana dursun: ..._01_konu-adi_tr / _en
    stem = f"{date_str}_{index + 1:02d}_{slugify(base_title)}_{lang}"
    tmp = videos_dir / f".tmp_{stem}"
    tmp.mkdir(exist_ok=True)
    gender = choose_gender(topic, index)
    raw_scenes = scenes_from_topic(topic)
    log(f"  Video [{lang.upper()}]: '{topic.get('baslik')}' ({len(raw_scenes)} sahne, {gender} ses)")

    try:
        # 1) Her sahneyi ayrı seslendir -> sahne süreleri kesin olur.
        #    Hedef süre aşılırsa konuşmayı hızlandırıp bir kez daha dener (en fazla %22).
        target = float(vcfg.get("hedef_sure_sn", 30))
        speed = 1.0
        for attempt in range(2):
            scenes, voice_parts, t, engine = [], [], 0.0, ""
            for i, s in enumerate(raw_scenes):
                sp = tts.synthesize(str(s["seslendirme"]).strip(), gender, tmp / f"s{i}.wav", tcfg, log, speed, lang)
                engine = sp.engine
                words = [(w, t + a, t + b) for w, a, b in sp.words]
                tip = s.get("tip") if s.get("tip") in TIPLER else ("hook" if i == 0 else "bilgi")
                end = t + sp.duration + SCENE_GAP
                scenes.append(Scene(tip, str(s.get("ekran") or ""), t, end, words, ACCENTS[i % len(ACCENTS)]))
                voice_parts.append((t, audio.read_wav(sp.wav_path)))
                t = end
            total = t + TAIL
            if total <= target + 0.5 or attempt == 1:
                break
            speed = min(1.22, total / target * 1.02)
            log(f"    {total:.1f} sn > hedef {target:.0f} sn: konuşma %{round((speed - 1) * 100)} hızlandırılıyor")
        if total > target + 1:
            log(f"    [UYARI] Video {total:.0f} sn; senaryo hedef için uzun, kısaltmak gerekebilir.")
        scenes[-1].end = total
        tl = Timeline(scenes, total)

        # 2) Müzik + efekt + ses miksajı
        seed = sum(map(ord, stem))
        sfx = [(0.0, audio.pop())] + [(max(0.0, s.start - 0.15), audio.whoosh(seed=i)) for i, s in enumerate(scenes[1:])]
        music = audio.load_music(ROOT / "assets" / "music", total, seed)
        mix = audio.mix(total, voice_parts, music, sfx, float(vcfg.get("muzik_sesi", 0.22)))
        mix_wav = audio.write_wav(tmp / "mix.wav", mix)

        # 3) Görüntü + kodlama
        out_mp4 = videos_dir / f"{stem}.mp4"
        meta_render = {"kanal_adi": vcfg.get("kanal_adi", ""), "kategori": topic.get("kategori", ""),
                       "kaynak_notu": topic.get("kaynak_notu") or _source_note(topic, lang), "dil": lang}
        render(tl, meta_render, mix_wav, out_mp4, log, preset=vcfg.get("kodlama_hizi", "veryfast"))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # 4) Onay masası için meta dosyası
    tags = " ".join(topic.get("hashtagler", []))
    title = (topic.get("ekran_basligi") or topic.get("baslik") or "")[:90]
    meta = {
        "id": stem,
        "dil": lang,
        "video": out_mp4.name,
        "olusturma": datetime.now().isoformat(timespec="seconds"),
        "durum": "onay_bekliyor",
        "baslik": topic.get("baslik", ""),
        "youtube_baslik": f"{title} #Shorts",
        "aciklama": (topic.get("paylasim_aciklamasi", "") + ("\n\n" + tags if tags else "")).strip(),
        "senaryo": " ".join(str(s["seslendirme"]) for s in raw_scenes),
        "kaynaklar": topic.get("kaynaklar", []),
        "dogrulanacaklar": topic.get("dogrulanacaklar", []),
        "ses": gender,
        "tts_motoru": engine,
        "sure_sn": round(total, 1),
        "paylasim_sonuclari": {},
    }
    (videos_dir / f"{stem}.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"  [OK] {out_mp4.name} ({total:.0f} sn, ses motoru: {engine})")
    return out_mp4


def _source_note(topic: dict, lang: str = "tr") -> str:
    names = []
    for s in topic.get("kaynaklar", []):
        first = str(s.get("kaynak", "")).split(",")[0].strip()
        if first and first not in names:
            names.append(first)
    label = "Source: " if lang == "en" else "Kaynak: "
    return (label + ", ".join(names[:2])) if names else ""
