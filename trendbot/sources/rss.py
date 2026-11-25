"""Genel RSS / Atom akış okuyucu. Her türlü haber sitesi için kullanılabilir."""
from __future__ import annotations

import html
import re
from datetime import datetime, timezone

import feedparser
import requests

from ..models import Item

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def clean_html(text: str, limit: int = 500) -> str:
    """HTML etiketlerini ve fazla boşlukları temizler, metni kısaltır."""
    text = html.unescape(_TAG_RE.sub(" ", text or ""))
    return _WS_RE.sub(" ", text).strip()[:limit]


def _entry_date(entry) -> datetime | None:
    """Akış girdisinin yayın tarihini UTC datetime olarak döndürür."""
    for key in ("published_parsed", "updated_parsed"):
        t = entry.get(key)
        if t:
            return datetime(*t[:6], tzinfo=timezone.utc)
    return None


def fetch_feed(
    name: str,
    url: str,
    since: datetime,
    *,
    weight: float = 1.0,
    needs_keyword: bool = False,
    user_agent: str = "",
    timeout: int = 15,
    max_items: int = 50,
) -> list[Item]:
    """Bir RSS akışını indirip `since` tarihinden yeni girdileri döndürür."""
    # feedparser'ın kendi indiricisinde zaman aşımı yok; bu yüzden requests kullanıyoruz.
    resp = requests.get(url, headers={"User-Agent": user_agent}, timeout=timeout)
    resp.raise_for_status()
    feed = feedparser.parse(resp.content)

    items: list[Item] = []
    for entry in feed.entries[:max_items]:
        title = clean_html(entry.get("title", ""), 300)
        link = entry.get("link", "")
        if not title or not link:
            continue
        published = _entry_date(entry)
        if published and published < since:
            continue  # Zaman penceresinin dışında
        items.append(
            Item(
                title=title,
                url=link,
                source=name,
                published=published,
                summary=clean_html(entry.get("summary", "")),
                source_weight=weight,
                needs_keyword=needs_keyword,
            )
        )
    return items
