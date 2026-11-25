"""Günlük AI trend taslaklarını üretir.

Kullanım:
    python run_daily.py               # Normal çalıştırma
    python run_daily.py --deneme      # Geçmişe kaydetmeden dene
    python run_daily.py --llm-yok     # LLM'siz: sadece aday listesini yaz (ücretsiz)
    python run_daily.py --saat 48 --konu 4
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
import sys
import webbrowser
from datetime import datetime, timedelta, timezone

from trendbot.config import load_config, resolve_path
from trendbot.history import History
from trendbot.llm import LLMError, complete, extract_json, model_label
from trendbot.prompts import SYSTEM_PROMPT, build_user_prompt
from trendbot.ranking import compile_keywords, dedupe, filter_ai, pick_candidates, score_items
from trendbot.sources import collect_all
from trendbot import html_writer, writer
from trendbot.publishers import load_accounts

# Windows konsolunda Türkçe karakterler bozulmasın
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Günlük AI trend içerik taslakları üretir.")
    p.add_argument("--saat", type=int, help="Son kaç saat taransın (config'i ezer)")
    p.add_argument("--konu", type=int, help="Kaç konu seçilsin (config'i ezer)")
    p.add_argument("--llm-yok", action="store_true", help="LLM çağırma, sadece aday listesini yaz")
    p.add_argument("--deneme", action="store_true", help="Geçmiş kaydını güncelleme")
    p.add_argument("--config", help="Farklı bir config dosyası yolu")
    p.add_argument("--acma", action="store_true", help="HTML sayfasını tarayıcıda otomatik açma")
    p.add_argument("--video-yok", action="store_true", help="Bu çalıştırmada video üretme")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    cfg = load_config(args.config)
    g = cfg["genel"]
    hours = args.saat or int(g.get("saat_araligi", 36))
    n_topics = args.konu or int(g.get("konu_sayisi", 5))

    now = datetime.now(timezone.utc)
    since = now - timedelta(hours=hours)
    out_dir = resolve_path(g.get("cikti_klasoru", "outputs"))
    out_dir.mkdir(parents=True, exist_ok=True)
    history = History(resolve_path(g.get("gecmis_dosyasi", "data/history.json")),
                      int(g.get("gecmis_saklama_gun", 45)))

    # 1) TOPLA
    print(f"\n[1/4] Kaynaklar taranıyor (son {hours} saat)...")
    raw = collect_all(cfg, since)
    if not raw:
        print("Hiç öğe toplanamadı. İnternet bağlantını ve config.yaml'daki kaynakları kontrol et.")
        return 1

    # 2) FİLTRELE + PUANLA
    print("\n[2/4] Filtreleniyor ve puanlanıyor...")
    items = filter_ai(raw, compile_keywords(cfg["anahtar_kelimeler"]))
    items = dedupe(items)
    fresh = [it for it in items if not history.is_seen(it)]
    ranked = score_items(fresh, hours, compile_keywords(cfg["sinyal_kelimeleri"]), now)
    candidates = pick_candidates(ranked, int(g.get("llm_aday_sayisi", 40)), int(g.get("kaynak_basina_max", 8)))
    stats = {"toplam": len(raw), "ai_ilgili_tekil": len(items), "yeni": len(fresh),
             "model": model_label(cfg["llm"])}
    print(f"  {len(raw)} öğe -> {len(items)} AI ile ilgili tekil -> {len(fresh)} yeni -> {len(candidates)} aday")
    if not candidates:
        print("Yeni aday yok (hepsi daha önce işlenmiş olabilir). --saat değerini artırmayı dene.")
        return 1

    stem = f"{datetime.now():%Y-%m-%d}_trendler"

    # LLM'siz mod: sadece aday listesi
    if args.llm_yok:
        path = writer.unique_path(out_dir, stem + "_adaylar", ".md")
        writer.write_candidates_only(path, candidates, stats, "LLM kullanılmadan oluşturuldu (--llm-yok).")
        print(f"\n[OK] Aday listesi yazıldı: {path}")
        return 0

    # 3) LLM ANALİZİ
    print(f"\n[3/4] Yapay zekâ en iyi {n_topics} konuyu seçiyor ve senaryoları yazıyor...")
    recent = history.recent_topics(int(g.get("son_konular_gun", 7)))
    try:
        reply = complete(SYSTEM_PROMPT.format(n=n_topics),
                         build_user_prompt(candidates, recent, n_topics), cfg["llm"])
        topics = extract_json(reply).get("konular", [])
        if not topics:
            raise LLMError("Model konu döndürmedi.")
    except LLMError as e:
        # Hata olsa bile emek kaybolmasın: ham cevabı ve aday listesini kaydet
        print(f"  [HATA] {e}")
        if "reply" in locals() and reply:
            (out_dir / f"{stem}_ham_cevap.txt").write_text(reply, encoding="utf-8")
        path = writer.unique_path(out_dir, stem + "_adaylar", ".md")
        writer.write_candidates_only(path, candidates, stats, f"LLM hatası nedeniyle sadece adaylar: {e}")
        print(f"  Aday listesi yine de kaydedildi: {path}")
        return 2

    topics = writer.enrich_topics(topics[:n_topics], candidates)

    # 4) YAZ
    print("\n[4/4] Dosyalar yazılıyor...")
    md_path = writer.unique_path(out_dir, stem, ".md")
    base = md_path.with_suffix("")
    writer.write_markdown(md_path, topics, candidates, stats)
    writer.write_json(base.with_suffix(".json"), topics, stats)
    writer.write_scripts_txt(base.parent / f"{base.name}_senaryolar.txt", topics)
    html_path = base.with_suffix(".html")
    html_writer.write_html(html_path, topics, candidates, stats)

    if args.deneme:
        print("  (--deneme: geçmiş kaydı güncellenmedi)")
    else:
        by_id = {c.id: c for c in candidates}
        used = [by_id[i] for t in topics for i in t.get("aday_idleri", []) if i in by_id]
        history.add(used, [t.get("baslik", "") for t in topics])
        history.save()

    print(f"\n[OK] Hazır: {html_path}")
    for i, t in enumerate(topics, 1):
        print(f"   {i}. {t.get('baslik')}  (~{t['tahmini_sure_sn']} sn)")

    # 5) VİDEO (onay masasına düşer; hiçbir şey otomatik paylaşılmaz)
    vcfg = cfg.get("video", {})
    n_videos = int(vcfg.get("konu_sayisi", 1))
    if vcfg.get("aktif", True) and not args.video_yok and n_videos > 0:
        from trendbot.video.maker import make_video
        if not vcfg.get("kanal_adi"):
            vcfg["kanal_adi"] = load_accounts().get("kanal_adi", "")
        langs = [d for d in vcfg.get("diller", ["tr"]) if d in ("tr", "en")] or ["tr"]
        print(f"\n[5/5] {min(n_videos, len(topics))} konu x {len(langs)} dil ({', '.join(langs)}) video üretiliyor...")
        for i, t in enumerate(topics[:n_videos]):
            for lang in langs:
                try:
                    make_video(t, out_dir / "videolar", cfg, f"{datetime.now():%Y-%m-%d}", i, lang=lang)
                except Exception as e:  # noqa: BLE001 - bir video bozulursa diğerleri devam etsin
                    print(f"  [HATA] {lang.upper()} video üretilemedi ({t.get('baslik')}): {e}")
        print("  Onaylamak için: python studio.py")

    # Sonucu tarayıcıda aç (config'te html_otomatik_ac: false veya --acma ile kapatılabilir)
    if g.get("html_otomatik_ac", True) and not args.acma:
        webbrowser.open(html_path.resolve().as_uri())
    return 0


if __name__ == "__main__":
    sys.exit(main())
