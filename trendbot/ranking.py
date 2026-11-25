"""Filtreleme, tekrar ayıklama ve puanlama.

Amaç: yüzlerce öğeyi LLM'e göndermeden önce en umut verici ~40 adaya indirmek.
Böylece LLM maliyeti düşük kalır ve kalite artar.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from datetime import datetime
from difflib import SequenceMatcher
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .models import Item

# URL'den temizlenecek takip parametreleri
_TRACKING_PREFIXES = ("utm_", "ref", "fbclid", "gclid", "mc_", "source", "guccounter")


def compile_keywords(words: list[str]) -> list[re.Pattern]:
    """Kelimeleri 'tam kelime' eşleşmesi yapan regex'lere çevirir (AI ≠ 'mail')."""
    return [re.compile(r"(?<!\w)" + re.escape(w) + r"(?!\w)", re.IGNORECASE) for w in words if w]


def normalize_url(url: str) -> str:
    """Aynı sayfanın farklı yazımlarını eşitler (www, utm_..., sondaki / vb.)."""
    p = urlsplit(url.strip())
    host = p.netloc.lower().removeprefix("www.")
    query = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
             if not k.lower().startswith(_TRACKING_PREFIXES)]
    return urlunsplit(("https", host, p.path.rstrip("/"), urlencode(query), ""))


def normalize_title(title: str) -> str:
    t = re.sub(r"[^\w\s]", " ", title.casefold())
    return re.sub(r"\s+", " ", t).strip()


def _similar(a: str, b: str, threshold: float = 0.82) -> bool:
    if not a or not b:
        return False
    # Uzunlukları çok farklıysa hiç hesaplama (hız için)
    if min(len(a), len(b)) / max(len(a), len(b)) < 0.6:
        return False
    return SequenceMatcher(None, a, b).ratio() >= threshold


def filter_ai(items: list[Item], patterns: list[re.Pattern]) -> list[Item]:
    """`needs_keyword` işaretli öğelerden AI ile ilgisiz olanları atar."""
    out = []
    for it in items:
        if not it.needs_keyword or any(p.search(f"{it.title} {it.summary}") for p in patterns):
            out.append(it)
    return out


def dedupe(items: list[Item]) -> list[Item]:
    """Aynı haberi (aynı URL veya çok benzer başlık) tek öğede birleştirir.

    Birleştirilen öğenin diğer kaynakları `extra_sources`a yazılır; bir haberin
    birden çok yerde görünmesi güçlü bir "trend" sinyalidir.
    """
    ordered = sorted(items, key=lambda i: (i.engagement, i.source_weight), reverse=True)
    kept: list[Item] = []
    by_url: dict[str, Item] = {}

    for it in ordered:
        nu, nt = normalize_url(it.url), normalize_title(it.title)
        dup = by_url.get(nu) or next((k for k in kept if _similar(nt, k.norm_title)), None)
        if dup:
            if it.source not in dup.all_sources():
                dup.extra_sources.append(it.source)
            dup.engagement = max(dup.engagement, it.engagement)
            dup.comments = max(dup.comments, it.comments)
            dup.summary = dup.summary or it.summary
            dup.discussion_url = dup.discussion_url or it.discussion_url
            dup.source_weight = max(dup.source_weight, it.source_weight)
            if it.published and (not dup.published or it.published < dup.published):
                dup.published = it.published  # En erken yayın tarihini tut
        else:
            it.norm_url, it.norm_title = nu, nt
            kept.append(it)
            by_url[nu] = it
    return kept


def score_items(items: list[Item], window_hours: float,
                signal_patterns: list[re.Pattern], now: datetime) -> list[Item]:
    """Basit, açıklanabilir bir puan hesaplar ve büyükten küçüğe sıralar.

    puan = kaynak ağırlığı
         + log10(1 + etkileşim)            (100 puan ≈ +2, 1000 ≈ +3)
         + 0.5 * log10(1 + yorum)
         + tazelik (0..1, yeni = 1)
         + 0.8 * (aynı haberi veren ek kaynak sayısı)
         + 0.5 (başlıkta "launch / yeni / duyurdu" gibi sinyal kelime varsa)
    """
    for it in items:
        s = it.source_weight
        s += math.log10(1 + it.engagement)
        s += 0.5 * math.log10(1 + it.comments)
        if it.published:
            age_h = max(0.0, (now - it.published).total_seconds() / 3600)
            s += max(0.0, 1 - age_h / window_hours)
        else:
            s += 0.3  # Tarihi bilinmiyorsa küçük nötr bonus
        s += 0.8 * len(it.extra_sources)
        if any(p.search(it.title) for p in signal_patterns):
            s += 0.5
        it.score = round(s, 3)
    return sorted(items, key=lambda i: i.score, reverse=True)


def pick_candidates(items: list[Item], limit: int, per_source_max: int) -> list[Item]:
    """En yüksek puanlıları seçer ama tek bir kaynağın listeyi doldurmasını engeller."""
    counts: Counter = Counter()
    picked = []
    for it in items:
        if counts[it.source] >= per_source_max:
            continue
        counts[it.source] += 1
        picked.append(it)
        if len(picked) >= limit:
            break
    for i, it in enumerate(picked, 1):
        it.id = f"k{i}"
    return picked
