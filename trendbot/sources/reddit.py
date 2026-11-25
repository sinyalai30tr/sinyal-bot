"""Reddit kaynağı. Önce anahtarsız JSON uç noktasını dener, olmazsa RSS'e düşer."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

import requests

from ..models import Item
from .rss import clean_html, fetch_feed


def _fetch_json(sub: str, min_score: int, since: datetime, weight: float,
                needs_kw: bool, user_agent: str, timeout: int) -> list[Item]:
    url = f"https://www.reddit.com/r/{sub}/top.json"
    resp = requests.get(url, params={"t": "day", "limit": 30},
                        headers={"User-Agent": user_agent}, timeout=timeout)
    resp.raise_for_status()

    items = []
    for child in resp.json().get("data", {}).get("children", []):
        d = child.get("data", {})
        if d.get("stickied") or d.get("score", 0) < min_score:
            continue
        created = datetime.fromtimestamp(d.get("created_utc", 0), tz=timezone.utc)
        if created < since:
            continue
        permalink = "https://www.reddit.com" + d.get("permalink", "")
        # Link gönderisiyse dış bağlantıyı, metin gönderisiyse Reddit sayfasını kullan
        link = permalink if d.get("is_self") else (d.get("url_overridden_by_dest") or d.get("url") or permalink)
        items.append(Item(
            title=d.get("title", ""),
            url=link,
            source=f"Reddit r/{sub}",
            published=created,
            summary=clean_html(d.get("selftext", ""), 400),
            engagement=int(d.get("score", 0)),
            comments=int(d.get("num_comments", 0)),
            source_weight=weight,
            needs_keyword=needs_kw,
            discussion_url=permalink,
        ))
    return items


def fetch(cfg: dict, since: datetime, user_agent: str = "", timeout: int = 15,
          log: Callable[[str], None] = print) -> list[Item]:
    weight = float(cfg.get("agirlik", 1.0))
    items: list[Item] = []
    for entry in cfg.get("subredditler", []) or []:
        # Basit kullanım için düz metin de kabul edilir: "- LocalLLaMA"
        if isinstance(entry, str):
            entry = {"ad": entry}
        sub = entry["ad"]
        min_score = int(entry.get("min_skor", 100))
        needs_kw = bool(entry.get("anahtar_kelime_sart", False))
        try:
            items += _fetch_json(sub, min_score, since, weight, needs_kw, user_agent, timeout)
        except Exception as e:  # noqa: BLE001 - JSON engellenirse RSS'e geç
            try:
                # RSS'te skor bilgisi yok; bu yüzden min_skor filtresi uygulanamaz
                items += fetch_feed(f"Reddit r/{sub}", f"https://www.reddit.com/r/{sub}/top/.rss?t=day",
                                    since, weight=weight * 0.8, needs_keyword=needs_kw,
                                    user_agent=user_agent, timeout=timeout)
                log(f"  [UYARI] r/{sub}: JSON alınamadı ({e.__class__.__name__}), RSS kullanıldı")
            except Exception as e2:  # noqa: BLE001
                log(f"  [HATA] r/{sub}: {e2.__class__.__name__}: {str(e2)[:100]}")
    return items
