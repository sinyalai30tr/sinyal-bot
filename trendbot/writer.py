"""Çıktı dosyalarını yazar: Markdown (düzenleme), JSON (makine), TXT (seslendirme)."""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from .models import Item

AYLAR = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
         "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]

NOT_ALANI = ("> **[SENİN NOTUN / ÖRNEĞİN]**\n"
             "> _Kendi yorumun, denediğin bir örnek, ekran kaydı fikri veya kişisel bakış açın..._\n"
             ">\n> \n")

WORDS_PER_SECOND = 2.5  # Türkçe ortalama seslendirme hızı (yaklaşık)


def tr_date(d: datetime) -> str:
    return f"{d.day} {AYLAR[d.month - 1]} {d.year}"


def unique_path(folder: Path, stem: str, ext: str) -> Path:
    """Aynı gün ikinci kez çalıştırılırsa üzerine yazmak yerine _2, _3 ekler."""
    p = folder / f"{stem}{ext}"
    n = 2
    while p.exists():
        p = folder / f"{stem}_{n}{ext}"
        n += 1
    return p


def subtitle_lines(script: str, max_words: int = 5, max_chars: int = 32) -> list[str]:
    """Senaryoyu CapCut tarzı kısa altyazı satırlarına böler."""
    lines: list[str] = []
    for sentence in re.split(r"(?<=[.!?…])\s+", script.strip()):
        words, cur = sentence.split(), []
        for w in words:
            if cur and (len(cur) >= max_words or len(" ".join(cur + [w])) > max_chars):
                lines.append(" ".join(cur))
                cur = []
            cur.append(w)
        if cur:
            lines.append(" ".join(cur))
    return lines


def enrich_topics(topics: list[dict], candidates: list[Item]) -> list[dict]:
    """LLM çıktısına kaynak linklerini, süre tahminini ve altyazı satırlarını ekler."""
    by_id = {c.id: c for c in candidates}
    for t in topics:
        srcs = [by_id[i] for i in t.get("aday_idleri", []) if i in by_id]
        t["kaynaklar"] = [{"baslik": s.title, "url": s.url, "kaynak": ", ".join(s.all_sources()),
                           "tartisma": s.discussion_url} for s in srcs]
        # Senaryo sahnelerden birleştirilir (eski biçimde doğrudan "senaryo" da gelebilir)
        if t.get("sahneler") and not t.get("senaryo"):
            t["senaryo"] = " ".join(str(s.get("seslendirme", "")).strip() for s in t["sahneler"])
        script = t.get("senaryo", "")
        wc = len(script.split())
        t["kelime_sayisi"] = wc
        t["tahmini_sure_sn"] = round(wc / WORDS_PER_SECOND)
        t["altyazi_satirlari"] = subtitle_lines(script)
        en = t.get("en")
        if isinstance(en, dict) and en.get("sahneler") and not en.get("senaryo"):
            en["senaryo"] = " ".join(str(s.get("seslendirme", "")).strip() for s in en["sahneler"])
    return topics


def _english_md(en) -> list[str]:
    """İngilizce sürüm bölümü (varsa)."""
    if not isinstance(en, dict) or not en.get("senaryo"):
        return []
    return ["### 🇬🇧 English version", f"**{en.get('baslik', '')}**", "",
            f"> **Hook:** {en.get('hook', '')}", "", en.get("senaryo", ""), "",
            f"_{en.get('paylasim_aciklamasi', '')}_", "", " ".join(en.get("hashtagler", [])), ""]


def _bullets(values) -> str:
    if isinstance(values, str):
        values = [values]
    return "\n".join(f"- {v}" for v in values or []) or "- —"


def write_markdown(path: Path, topics: list[dict], candidates: list[Item], stats: dict) -> None:
    now = datetime.now()
    out = [f"# AI Trendleri — {tr_date(now)}", "",
           f"> Oluşturma: {now:%H:%M} · Taranan: {stats['toplam']} öğe · "
           f"Tekil/yeni: {stats['yeni']} · LLM'e giden aday: {len(candidates)} · Model: {stats['model']}",
           "> ⚠️ Taslaklar otomatik üretildi. Yayından önce kaynakları ve **Doğrula** maddelerini kontrol et.",
           "", "## İçindekiler"]
    for i, t in enumerate(topics, 1):
        out.append(f"{i}. {t.get('baslik', 'Başlıksız')} _({t.get('kategori', '-')})_")
    out += ["", "---", ""]

    for i, t in enumerate(topics, 1):
        out += [
            f"## {i}. {t.get('baslik', 'Başlıksız')}",
            f"**Kategori:** {t.get('kategori', '-')} · **Süre:** ~{t['tahmini_sure_sn']} sn "
            f"({t['kelime_sayisi']} kelime)", "",
            "### Ne oldu?", t.get("ne_oldu", ""), "",
            "### Neden önemli?", t.get("neden_onemli", ""), "",
            "### 🎬 Hook (ilk 2 saniye)", f"> **{t.get('hook', '')}**", "",
            "### 🎙️ Senaryo (en fazla 30 sn)", t.get("senaryo", ""), "",
            NOT_ALANI,
            "### 📱 Ekran yazısı",
            f"- **Başlık:** {t.get('ekran_basligi', '')}",
            f"- **Alt metin:** {t.get('ekran_alt_metin', '')}", "",
            "<details><summary>Altyazı satırları (kopyala-yapıştır)</summary>", "",
            "```", *t["altyazi_satirlari"], "```", "</details>", "",
            "### 🎞️ Görsel / kurgu önerileri", _bullets(t.get("gorsel_onerileri")), "",
            "### ✅ Yayından önce doğrula", _bullets(t.get("dogrulanacaklar")), "",
            "### 📝 Paylaşım açıklaması",
            t.get("paylasim_aciklamasi", ""), "",
            " ".join(t.get("hashtagler", [])), "",
            *_english_md(t.get("en")),
            "### 🔗 Kaynaklar",
        ]
        for s in t["kaynaklar"]:
            extra = f" · [tartışma]({s['tartisma']})" if s["tartisma"] and s["tartisma"] != s["url"] else ""
            out.append(f"- [{s['baslik']}]({s['url']}) — {s['kaynak']}{extra}")
        out += ["", "---", ""]

    # Seçilmeyen ama güçlü adaylar: yedek konu listesi
    used = {i for t in topics for i in t.get("aday_idleri", [])}
    backups = [c for c in candidates if c.id not in used][:12]
    if backups:
        out += ["## 🗂️ Yedek adaylar (seçilmedi)", ""]
        out += [f"- [{c.title}]({c.url}) — {', '.join(c.all_sources())} · puan {c.score}" for c in backups]
    path.write_text("\n".join(out) + "\n", encoding="utf-8")


def write_json(path: Path, topics: list[dict], stats: dict) -> None:
    payload = {"tarih": datetime.now().isoformat(timespec="seconds"), "istatistik": stats, "konular": topics}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_scripts_txt(path: Path, topics: list[dict]) -> None:
    """Sadece seslendirme metinleri: teleprompter veya TTS aracına doğrudan yapıştırmak için."""
    blocks = [f"=== {i}. {t.get('baslik', '')} (~{t['tahmini_sure_sn']} sn) ===\n\n{t.get('senaryo', '')}\n"
              for i, t in enumerate(topics, 1)]
    path.write_text("\n".join(blocks), encoding="utf-8")


def write_candidates_only(path: Path, candidates: list[Item], stats: dict, note: str) -> None:
    """LLM kullanılamadığında ham aday listesini yazar (o günün emeği boşa gitmesin)."""
    now = datetime.now()
    out = [f"# AI Aday Haberleri — {tr_date(now)}", "", f"> {note}",
           f"> Taranan: {stats['toplam']} · Tekil/yeni: {stats['yeni']}", ""]
    for c in candidates:
        when = c.published.strftime("%d.%m %H:%M") if c.published else "?"
        out.append(f"- **[{c.id}]** [{c.title}]({c.url}) — {', '.join(c.all_sources())} · {when} · puan {c.score}")
        if c.summary:
            out.append(f"  - {c.summary[:220]}")
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
