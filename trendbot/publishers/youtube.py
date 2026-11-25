"""YouTube Data API ile doğrudan yükleme (ücretsiz).

Kurulum (bir kez):
 1. console.cloud.google.com -> yeni proje -> "YouTube Data API v3"ü etkinleştir.
 2. OAuth izin ekranı -> kendini test kullanıcısı olarak ekle.
 3. Kimlik bilgileri -> OAuth istemci kimliği -> "Masaüstü uygulaması" -> JSON'u indir,
    `data/youtube_client_secret.json` olarak kaydet.
 4. İlk yüklemede tarayıcı açılır, kanalına izin verirsin; anahtar `data/youtube_token.json`a kaydedilir.

ÖNEMLİ: Google, denetimden geçmemiş API projelerinden yüklenen videoları "gizli" yapar.
Videoyu sonra YouTube Studio'dan elle herkese açabilirsin veya projeyi denetime gönderebilirsin.
"""
from __future__ import annotations

from pathlib import Path

from ..config import ROOT

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
TOKEN = ROOT / "data" / "youtube_token.json"


def _credentials(secret_path: Path):
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    creds = Credentials.from_authorized_user_file(str(TOKEN), SCOPES) if TOKEN.exists() else None
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    if not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file(str(secret_path), SCOPES)
        creds = flow.run_local_server(port=0)  # Tarayıcıda izin ekranı açılır
    TOKEN.write_text(creds.to_json(), encoding="utf-8")
    return creds


def publish(video: Path, meta: dict, cfg: dict, log=print) -> dict:
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    yt = build("youtube", "v3", credentials=_credentials(ROOT / cfg["client_secret"]))
    body = {
        "snippet": {
            "title": meta.get("youtube_baslik", meta.get("baslik", ""))[:100],
            "description": meta.get("aciklama", ""),
            "categoryId": "28",  # Bilim ve Teknoloji
            "defaultLanguage": "tr",
        },
        "status": {
            "privacyStatus": cfg.get("gizlilik", "public"),
            "selfDeclaredMadeForKids": False,
            "containsSyntheticMedia": True,  # Yapay seslendirme kullanıldığını beyan eder
        },
    }
    log("  YouTube'a yükleniyor...")
    req = yt.videos().insert(part="snippet,status", body=body,
                             media_body=MediaFileUpload(str(video), chunksize=-1, resumable=True))
    resp = None
    while resp is None:
        _, resp = req.next_chunk()
    vid = resp["id"]
    status = resp.get("status", {}).get("privacyStatus", "")
    note = " (Google denetimi olmadan gizli kalır)" if status == "private" else ""
    return {"ok": True, "url": f"https://youtube.com/shorts/{vid}", "mesaj": f"Yüklendi: {status}{note}"}
