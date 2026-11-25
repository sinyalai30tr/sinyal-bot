"""Kaynak toplama katmanı.

Yeni bir kaynak türü eklemek için:
  1. Bu klasöre `yenikaynak.py` yaz; `list[Item]` döndüren bir fonksiyon olsun.
  2. Aşağıdaki `collect_all` içinde `jobs` listesine ekle.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from functools import partial
from typing import Callable

from ..models import Item
from . import hackernews, reddit, rss

DEFAULT_UA = "AITrendStudio/1.0"


def collect_all(cfg: dict, since: datetime, log: Callable[[str], None] = print) -> list[Item]:
    """config.yaml'daki tüm aktif kaynakları paralel olarak tarar."""
    ua = cfg["genel"].get("user_agent", DEFAULT_UA)
    src = cfg.get("kaynaklar", {})
    jobs: list[tuple[str, Callable[[], list[Item]]]] = []

    # 1) RSS akışları
    for feed in src.get("rss", []) or []:
        if feed.get("aktif", True) is False:
            continue
        jobs.append((feed["ad"], partial(
            rss.fetch_feed, feed["ad"], feed["url"], since,
            weight=float(feed.get("agirlik", 1.0)),
            needs_keyword=bool(feed.get("anahtar_kelime_sart", False)),
            user_agent=ua,
        )))

    # 2) Hacker News
    hn_cfg = src.get("hackernews") or {}
    if hn_cfg.get("aktif", True) and hn_cfg:
        jobs.append(("Hacker News", partial(hackernews.fetch, hn_cfg, since, ua)))

    # 3) Reddit
    rd_cfg = src.get("reddit") or {}
    if rd_cfg.get("aktif", True) and rd_cfg:
        jobs.append(("Reddit", partial(reddit.fetch, rd_cfg, since, ua, log=log)))

    # Hepsini aynı anda çalıştır (bir kaynak çökerse diğerleri etkilenmez)
    results: list[Item] = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(fn): label for label, fn in jobs}
        for fut in as_completed(futures):
            label = futures[fut]
            try:
                got = fut.result()
                log(f"  [OK]   {label}: {len(got)} öğe")
                results.extend(got)
            except Exception as e:  # noqa: BLE001
                log(f"  [HATA] {label}: {e.__class__.__name__}: {str(e)[:120]}")
    return results
