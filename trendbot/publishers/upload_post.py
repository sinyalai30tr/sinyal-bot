"""Upload-Post: tek API çağrısıyla birden çok platforma video gönderir.

Kurulum: upload-post.com'da hesap aç -> "Manage Users" bölümünde bir profil (kullanıcı adı) oluştur
-> YouTube / Instagram / TikTok / X hesaplarını o profile bağla -> API anahtarını kopyala.
Belgeler: https://docs.upload-post.com/api/upload-video
"""
from __future__ import annotations

import time
from pathlib import Path

import requests

BASE = "https://api.upload-post.com/api"


def _headers(acc: dict) -> dict:
    return {"Authorization": f"Apikey {acc['upload_post']['api_key']}"}


def test_connection(acc: dict) -> tuple[bool, str]:
    """API anahtarının çalıştığını kontrol eder."""
    try:
        r = requests.get(f"{BASE}/uploadposts/me", headers=_headers(acc), timeout=20)
        if r.status_code == 200:
            return True, "Bağlantı başarılı"
        return False, f"HTTP {r.status_code}: {r.text[:200]}"
    except requests.RequestException as e:
        return False, str(e)


def publish(video: Path, meta: dict, platforms: list[str], acc: dict, log=print) -> dict:
    caption = meta.get("aciklama", "")
    short_caption = caption if len(caption) <= 270 else caption[:267] + "..."  # X sınırı 280
    fields: list[tuple[str, str]] = [
        ("user", acc["upload_post"]["kullanici"]),
        ("title", meta.get("baslik", "")[:100]),
        ("async_upload", "true"),
    ]
    fields += [("platform[]", p) for p in platforms]
    if "youtube" in platforms:
        fields += [("youtube_title", meta.get("youtube_baslik", meta.get("baslik", ""))[:100]),
                   ("youtube_description", caption),
                   ("privacyStatus", acc["youtube"].get("gizlilik", "public"))]
    if "instagram" in platforms:
        fields += [("instagram_title", caption), ("media_type", "REELS")]
    if "tiktok" in platforms:
        fields += [("tiktok_title", caption[:2000]),
                   ("privacy_level", acc["tiktok"].get("gizlilik", "PUBLIC_TO_EVERYONE"))]
    if "x" in platforms:
        fields += [("x_title", short_caption)]

    log(f"  Upload-Post'a gönderiliyor: {', '.join(platforms)}")
    with open(video, "rb") as f:
        r = requests.post(f"{BASE}/upload", headers=_headers(acc), data=fields,
                          files={"video": (video.name, f, "video/mp4")}, timeout=600)
    if r.status_code >= 400:
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:300]}")
    data = r.json()

    # Eşzamansız yükleme: durum kontrolü ile sonucu bekle (en fazla ~5 dk)
    request_id = data.get("request_id")
    if request_id:
        for _ in range(30):
            time.sleep(10)
            s = requests.get(f"{BASE}/uploadposts/status", params={"request_id": request_id},
                             headers=_headers(acc), timeout=30)
            if s.status_code != 200:
                continue
            st = s.json()
            res = st.get("results") or st.get("result") or {}
            if isinstance(res, dict) and res and all(isinstance(v, dict) for v in res.values()):
                return _normalize(res, platforms)
            if str(st.get("status", "")).lower() in ("completed", "finished", "failed", "error"):
                break
        return {p: {"ok": True, "mesaj": f"Gönderildi, işleniyor (request_id: {request_id})"} for p in platforms}
    return _normalize(data.get("results", {}), platforms)


def _normalize(results: dict, platforms: list[str]) -> dict:
    out = {}
    for p in platforms:
        r = results.get(p, {})
        ok = bool(r.get("success"))
        out[p] = {"ok": ok, "url": r.get("url", ""), "mesaj": "Yayınlandı" if ok else r.get("error", "Sonuç yok")}
    return out
