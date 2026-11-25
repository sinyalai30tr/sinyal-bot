"""Hacker News kaynağı (Algolia arama API'si, anahtar gerektirmez)."""
from __future__ import annotations

from datetime import datetime, timezone

import requests

from ..models import Item
from .rss import clean_html

API_URL = "https://hn.algolia.com/api/v1/search"


def fetch(cfg: dict, since: datetime, user_agent: str = "", timeout: int = 15) -> list[Item]:
    """Belirtilen sorgulara uyan, belli puanın üstündeki HN hikâyelerini getirir."""
    min_points = int(cfg.get("min_puan", 50))
    weight = float(cfg.get("agirlik", 1.0))
    ts = int(since.timestamp())
    found: dict[str, Item] = {}  # objectID -> Item (sorgular arası tekrarı önler)

    for query in cfg.get("sorgular", ["AI"]):
        params = {
            "tags": "story",
            "query": query,
            "numericFilters": f"created_at_i>{ts},points>={min_points}",
            "hitsPerPage": 50,
        }
        resp = requests.get(API_URL, params=params, headers={"User-Agent": user_agent}, timeout=timeout)
        resp.raise_for_status()

        for hit in resp.json().get("hits", []):
            oid = hit.get("objectID")
            if not oid or oid in found or not hit.get("title"):
                continue
            discussion = f"https://news.ycombinator.com/item?id={oid}"
            found[oid] = Item(
                title=hit["title"],
                url=hit.get("url") or discussion,  # "Ask HN" gibi gönderilerde dış link yok
                source="Hacker News",
                published=datetime.fromtimestamp(hit["created_at_i"], tz=timezone.utc),
                summary=clean_html(hit.get("story_text") or "", 400),
                engagement=hit.get("points") or 0,
                comments=hit.get("num_comments") or 0,
                source_weight=weight,
                needs_keyword=True,  # Algolia gevşek eşleşebilir; AI kelimesi şartı koyuyoruz
                discussion_url=discussion,
            )
    return list(found.values())
