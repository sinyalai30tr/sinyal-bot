"""Günün taslak dosyasındaki bir konudan video üretir.

Kullanım:
    python make_video.py                       # En son günlük JSON'daki 1. konu
    python make_video.py --konu 3              # 3. konu (Türkçe + İngilizce)
    python make_video.py --konu 3 --dil en     # Sadece İngilizce
    python make_video.py outputs/2026-11-19_trendler.json --konu 2
"""
from __future__ import annotations

import sys

# Paketler kurulu değilse anlaşılır bir mesaj göster (pencere hemen kapanmasın)
try:
    import yaml  # noqa: F401
    import dotenv  # noqa: F401
    import requests  # noqa: F401
except ImportError as _e:
    print(f"Eksik paket: {_e.name}. Önce '1-KURULUM.bat' dosyasına çift tıkla.")
    input("Kapatmak için Enter'a bas...")
    sys.exit(1)


import argparse
import json
import sys
from pathlib import Path

from trendbot.config import load_config, resolve_path
from trendbot.publishers import load_accounts
from trendbot.video.maker import make_video

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass


def main() -> int:
    ap = argparse.ArgumentParser(description="Taslak konudan dikey video üretir.")
    ap.add_argument("json_dosyasi", nargs="?", help="outputs/..._trendler.json (boşsa en yenisi)")
    ap.add_argument("--konu", type=int, default=1, help="Kaçıncı konu (1'den başlar)")
    ap.add_argument("--dil", choices=["tr", "en", "hepsi"], default="hepsi", help="Hangi dilde video")
    args = ap.parse_args()

    cfg = load_config()
    out_dir = resolve_path(cfg["genel"].get("cikti_klasoru", "outputs"))
    if args.json_dosyasi:
        src = Path(args.json_dosyasi)
    else:
        files = sorted(out_dir.glob("*_trendler*.json"))
        if not files:
            print("Taslak bulunamadı. Önce `python run_daily.py` çalıştır.")
            return 1
        src = files[-1]
    data = json.loads(src.read_text(encoding="utf-8"))
    topics = data.get("konular", [])
    if not 1 <= args.konu <= len(topics):
        print(f"Bu dosyada {len(topics)} konu var.")
        return 1

    vcfg = cfg.setdefault("video", {})
    if not vcfg.get("kanal_adi"):
        vcfg["kanal_adi"] = load_accounts().get("kanal_adi", "")
    date_str = src.name[:10]
    langs = cfg.get("video", {}).get("diller", ["tr", "en"]) if args.dil == "hepsi" else [args.dil]
    for lang in langs:
        try:
            make_video(topics[args.konu - 1], out_dir / "videolar", cfg, date_str, args.konu - 1, lang=lang)
        except ValueError as e:
            print(f"  [ATLANDI] {lang.upper()}: {e}")
    print("Onay için: python studio.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
