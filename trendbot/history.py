"""İşlenen konuların geçmişi (data/history.json).

İki şey saklanır:
  - items : seçilen haberlerin normalize URL'leri ve başlıkları -> aynı link bir daha gelmez
  - topics: seçilen konu başlıkları -> LLM'e "bunları yakın zamanda işledin" diye verilir,
            böylece aynı olay farklı bir siteden gelse bile tekrar seçilmez.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from .models import Item
from .ranking import normalize_title, normalize_url


class History:
    def __init__(self, path: Path, retention_days: int = 45):
        self.path = path
        self.retention_days = retention_days
        self.data: dict = {"items": {}, "topics": []}
        if path.exists():
            try:
                self.data = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                # Bozuk dosyayı yedekle, sıfırdan başla (veri kaybı olmasın)
                path.rename(path.with_suffix(".bozuk.json"))
        self.data.setdefault("items", {})
        self.data.setdefault("topics", [])
        self._titles = {v.get("norm_title") for v in self.data["items"].values()}

    # ---------- Sorgular ----------
    def is_seen(self, item: Item) -> bool:
        nu = item.norm_url or normalize_url(item.url)
        nt = item.norm_title or normalize_title(item.title)
        return nu in self.data["items"] or nt in self._titles

    def recent_topics(self, days: int = 7) -> list[str]:
        cutoff = (date.today() - timedelta(days=days)).isoformat()
        return [t["title"] for t in self.data["topics"] if t.get("date", "") >= cutoff]

    # ---------- Güncelleme ----------
    def add(self, items: list[Item], topic_titles: list[str]) -> None:
        today = date.today().isoformat()
        for it in items:
            nu = it.norm_url or normalize_url(it.url)
            nt = it.norm_title or normalize_title(it.title)
            self.data["items"][nu] = {"title": it.title, "norm_title": nt, "date": today}
            self._titles.add(nt)
        for t in topic_titles:
            self.data["topics"].append({"title": t, "date": today})

    def prune(self) -> None:
        """Saklama süresini aşan kayıtları siler (dosya şişmesin)."""
        cutoff = (date.today() - timedelta(days=self.retention_days)).isoformat()
        self.data["items"] = {k: v for k, v in self.data["items"].items() if v.get("date", "") >= cutoff}
        self.data["topics"] = [t for t in self.data["topics"] if t.get("date", "") >= cutoff]

    def save(self) -> None:
        self.prune()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)  # Yarım yazılmış dosya kalmaması için atomik değiştirme
