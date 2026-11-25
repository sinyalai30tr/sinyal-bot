"""config.yaml ve .env dosyalarını yükler."""
from __future__ import annotations

from pathlib import Path

import yaml
from dotenv import load_dotenv

# Proje kök klasörü (run_daily.py'nin bulunduğu yer)
ROOT = Path(__file__).resolve().parent.parent


def load_config(path: str | None = None) -> dict:
    """Ayarları okur; .env içindeki API anahtarlarını ortam değişkenlerine yükler."""
    load_dotenv(ROOT / ".env")
    cfg_path = Path(path) if path else ROOT / "config.yaml"
    with open(cfg_path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}

    # Eksik bölümler için boş sözlük koy ki kodun geri kalanı KeyError almasın
    for key in ("genel", "llm", "kaynaklar"):
        cfg.setdefault(key, {})
    cfg.setdefault("anahtar_kelimeler", [])
    cfg.setdefault("sinyal_kelimeleri", [])
    return cfg


def resolve_path(relative: str) -> Path:
    """config'teki göreli yolları proje köküne göre çözer."""
    p = Path(relative)
    return p if p.is_absolute() else ROOT / p
