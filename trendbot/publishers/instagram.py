"""Instagram Graph API ile doğrudan Reels paylaşımı (ücretsiz, "resumable upload").

Gereksinimler: Instagram İşletme/İçerik Üretici hesabı + bağlı Facebook sayfası + Meta geliştirici
uygulaması (instagram_business_content_publish izni). Kurulumu uzun olduğundan başlangıç için
Upload-Post yolunu öneriyoruz.
"""
from __future__ import annotations

import time
from pathlib import Path

import requests

GRAPH = "https://graph.facebook.com/v25.0"


def publish(video: Path, meta: dict, cfg: dict, log=print) -> dict:
    uid, token = cfg["ig_user_id"], cfg["access_token"]
    # 1) Yükleme oturumu aç
    r = requests.post(f"{GRAPH}/{uid}/media", params={
        "media_type": "REELS", "upload_type": "resumable",
        "caption": meta.get("aciklama", "")[:2200], "access_token": token}, timeout=60)
    r.raise_for_status()
    container, uri = r.json()["id"], r.json()["uri"]
    # 2) Dosyayı gönder
    size = video.stat().st_size
    log("  Instagram'a yükleniyor...")
    with open(video, "rb") as f:
        up = requests.post(uri, headers={"Authorization": f"OAuth {token}", "offset": "0",
                                         "file_size": str(size)}, data=f, timeout=600)
    up.raise_for_status()
    # 3) İşlenmesini bekle
    for _ in range(40):
        time.sleep(8)
        st = requests.get(f"{GRAPH}/{container}", params={"fields": "status_code", "access_token": token},
                          timeout=30).json()
        if st.get("status_code") == "FINISHED":
            break
        if st.get("status_code") == "ERROR":
            raise RuntimeError(f"Instagram videoyu işleyemedi: {st}")
    # 4) Yayınla
    pub = requests.post(f"{GRAPH}/{uid}/media_publish",
                        params={"creation_id": container, "access_token": token}, timeout=60)
    pub.raise_for_status()
    return {"ok": True, "url": "", "mesaj": f"Yayınlandı (medya id: {pub.json().get('id')})"}
