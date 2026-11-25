"""Tüm kaynakların ortak kullandığı veri modeli."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Item:
    """Herhangi bir kaynaktan gelen tek bir haber / gönderi."""

    title: str
    url: str
    source: str                          # Örn: "TechCrunch AI", "Hacker News", "Reddit r/LocalLLaMA"
    published: Optional[datetime] = None  # UTC zaman damgası (bilinmiyorsa None)
    summary: str = ""                    # Kısa açıklama (HTML temizlenmiş)
    engagement: int = 0                  # HN puanı / Reddit upvote (RSS'te 0)
    comments: int = 0                    # Yorum sayısı
    source_weight: float = 1.0           # config.yaml'daki "agirlik"
    needs_keyword: bool = False          # True ise AI anahtar kelimesi şartı uygulanır
    discussion_url: str = ""             # HN / Reddit tartışma linki (varsa)

    # --- Sonradan doldurulan alanlar ---
    extra_sources: list[str] = field(default_factory=list)  # Aynı haberi veren diğer kaynaklar
    score: float = 0.0
    id: str = ""                          # LLM'e gönderilirken atanır: k1, k2...
    norm_url: str = ""
    norm_title: str = ""

    def all_sources(self) -> list[str]:
        return [self.source] + self.extra_sources
