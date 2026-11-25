"""Sosyal medya yayın katmanı.

Hesap bilgileri `data/hesaplar.json` dosyasında durur (bilgisayarında kalır, paylaşılmaz).
Bu dosyayı elle düzenlemek yerine Onay Masası'ndaki "Hesaplar" sayfasını kullan.

İki yol var:
  1) upload_post : Tek API anahtarıyla YouTube, Instagram, TikTok ve X'e birlikte gönderir.
                   Hazır onaylı uygulama kullandığı için videolar herkese açık yayınlanabilir.
  2) dogrudan    : Platformun kendi API'si (şimdilik YouTube ve Instagram). Ücretsiz ama kurulumu uzun;
                   YouTube'da Google denetimi bitene kadar videolar "gizli" yüklenir.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from ..config import ROOT

ACCOUNTS_PATH = ROOT / "data" / "hesaplar.json"

PLATFORMS = {
    "youtube":   {"ad": "YouTube Shorts", "yollar": ["upload_post", "dogrudan"]},
    "instagram": {"ad": "Instagram Reels", "yollar": ["upload_post", "dogrudan"]},
    "tiktok":    {"ad": "TikTok", "yollar": ["upload_post"]},
    "x":         {"ad": "X (Twitter)", "yollar": ["upload_post"]},
}

DEFAULT_ACCOUNTS = {
    "kanal_adi": "",
    "yapay_zeka": {"gemini_api_key": "", "anthropic_api_key": ""},
    "upload_post": {"api_key": "", "kullanici": ""},
    "youtube": {"aktif": False, "yol": "upload_post", "gizlilik": "public",
                "client_secret": "data/youtube_client_secret.json"},
    "instagram": {"aktif": False, "yol": "upload_post", "ig_user_id": "", "access_token": ""},
    "tiktok": {"aktif": False, "yol": "upload_post", "gizlilik": "PUBLIC_TO_EVERYONE"},
    "x": {"aktif": False, "yol": "upload_post"},
}


def load_accounts() -> dict:
    data = json.loads(json.dumps(DEFAULT_ACCOUNTS))  # derin kopya
    if ACCOUNTS_PATH.exists():
        saved = json.loads(ACCOUNTS_PATH.read_text(encoding="utf-8"))
        for k, v in saved.items():
            if isinstance(v, dict) and isinstance(data.get(k), dict):
                data[k].update(v)
            else:
                data[k] = v
    _apply_env(data)
    return data


def _apply_env(data: dict) -> None:
    """Bulutta (GitHub) çalışırken bilgiler dosyadan değil gizli değişkenlerden gelir:
    UPLOAD_POST_API_KEY, UPLOAD_POST_USER, PLATFORMLAR (ör. "youtube,instagram"), KANAL_ADI."""
    if os.getenv("UPLOAD_POST_API_KEY"):
        data["upload_post"]["api_key"] = os.environ["UPLOAD_POST_API_KEY"].strip()
        data["upload_post"]["kullanici"] = os.getenv("UPLOAD_POST_USER", data["upload_post"].get("kullanici", "")).strip()
        wanted = [p.strip() for p in os.getenv("PLATFORMLAR", "youtube,instagram").split(",") if p.strip()]
        for p in PLATFORMS:
            data[p]["aktif"] = p in wanted
            data[p]["yol"] = "upload_post"
    if os.getenv("KANAL_ADI"):
        data["kanal_adi"] = os.environ["KANAL_ADI"].strip()


def save_accounts(data: dict) -> None:
    ACCOUNTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    ACCOUNTS_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def platform_status(name: str, acc: dict) -> tuple[bool, str]:
    """(hazır_mı, açıklama) döndürür. Hesaplar sayfasında ve onay ekranında gösterilir."""
    p = acc.get(name, {})
    if not p.get("aktif"):
        return False, "Kapalı"
    if p.get("yol") == "upload_post":
        up = acc.get("upload_post", {})
        if up.get("api_key") and up.get("kullanici"):
            return True, "Upload-Post üzerinden"
        return False, "Upload-Post API anahtarı / kullanıcı adı eksik"
    if name == "youtube":
        secret = ROOT / p.get("client_secret", "")
        return (True, "Doğrudan YouTube API (denetim bitene kadar gizli yüklenir)") if secret.exists() \
            else (False, f"client_secret dosyası yok: {p.get('client_secret')}")
    if name == "instagram":
        ok = bool(p.get("ig_user_id") and p.get("access_token"))
        return (ok, "Doğrudan Instagram Graph API") if ok else (False, "IG kullanıcı ID / erişim anahtarı eksik")
    return False, "Bu platform yalnızca Upload-Post ile bağlanabilir"


def publish_all(video: Path, meta: dict, platforms: list[str], acc: dict, log=print) -> dict:
    """Onaylanan videoyu seçilen platformlara gönderir. Her platform için sonuç döndürür."""
    from . import instagram, upload_post, youtube

    results: dict[str, dict] = {}
    ready = []
    for p in platforms:
        ok, why = platform_status(p, acc)
        if ok:
            ready.append(p)
        else:
            results[p] = {"ok": False, "mesaj": f"Bağlı değil: {why}"}

    via_up = [p for p in ready if acc[p].get("yol") == "upload_post"]
    if via_up:
        try:
            results.update(upload_post.publish(video, meta, via_up, acc, log))
        except Exception as e:  # noqa: BLE001
            for p in via_up:
                results[p] = {"ok": False, "mesaj": f"Upload-Post hatası: {e}"}

    for p in ready:
        if acc[p].get("yol") != "dogrudan":
            continue
        try:
            if p == "youtube":
                results[p] = youtube.publish(video, meta, acc["youtube"], log)
            elif p == "instagram":
                results[p] = instagram.publish(video, meta, acc["instagram"], log)
        except Exception as e:  # noqa: BLE001
            results[p] = {"ok": False, "mesaj": f"{e.__class__.__name__}: {str(e)[:200]}"}
    return results
