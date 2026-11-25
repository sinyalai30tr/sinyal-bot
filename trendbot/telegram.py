"""Telegram Bot API için küçük yardımcı (sadece `requests`)."""
from __future__ import annotations

import json
import time
from pathlib import Path

import requests


class TelegramError(RuntimeError):
    pass


class Telegram:
    def __init__(self, token: str):
        if not token:
            raise TelegramError("TELEGRAM_BOT_TOKEN tanımlı değil.")
        self.token = token
        self.base = f"https://api.telegram.org/bot{token}"
        self.skipped_updates = False  # Okunamayan (takılmış) mesajlar atlandıysa True

    def call(self, method: str, files: dict | None = None, http_timeout: int = 120, **params):
        # Not: Telegram'ın kendi "timeout" parametresiyle karışmasın diye bağlantı süresi http_timeout
        # reply_markup gibi sözlükler JSON metni olarak gönderilmeli
        data = {k: (json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v)
                for k, v in params.items() if v is not None}
        # Telegram'ın anlık sunucu hatalarında (502/503/504, bağlantı kopması) birkaç kez tekrar dene.
        # Dosya gönderiminde dosya bir kez okunduğu için tekrar denenmez.
        attempts = 1 if files else 3
        last = ""
        for i in range(attempts):
            try:
                r = requests.post(f"{self.base}/{method}", data=data, files=files, timeout=http_timeout)
            except (requests.ConnectionError, requests.Timeout) as e:
                last = f"bağlantı hatası ({e.__class__.__name__})"
            else:
                try:
                    j = r.json()
                except ValueError:
                    j = {"ok": False, "description": f"HTTP {r.status_code}"}
                if j.get("ok"):
                    return j["result"]
                last = j.get("description", "bilinmeyen hata")
                if r.status_code not in (429, 500, 502, 503, 504):
                    break  # Kalıcı hata (yanlış anahtar vb.): tekrar denemenin anlamı yok
            if i < attempts - 1:
                time.sleep(3 * (i + 1))
        raise TelegramError(f"{method}: {last}")

    # --- Mesajlar ---
    def send_message(self, chat_id, text: str, reply_markup=None, reply_to: int | None = None):
        return self.call("sendMessage", chat_id=chat_id, text=text[:4096], parse_mode="HTML",
                         disable_web_page_preview="true", reply_markup=reply_markup,
                         reply_to_message_id=reply_to)

    def send_video(self, chat_id, path: Path, caption: str, reply_markup=None):
        with open(path, "rb") as f:
            return self.call("sendVideo", files={"video": (path.name, f, "video/mp4")}, http_timeout=600,
                             chat_id=chat_id, caption=caption[:1024], parse_mode="HTML",
                             supports_streaming="true", reply_markup=reply_markup)

    def edit_markup(self, chat_id, message_id: int, reply_markup=None):
        return self.call("editMessageReplyMarkup", chat_id=chat_id, message_id=message_id,
                         reply_markup=reply_markup or {"inline_keyboard": []})

    def answer_callback(self, callback_id: str, text: str = ""):
        try:
            return self.call("answerCallbackQuery", callback_query_id=callback_id, text=text[:190])
        except TelegramError:
            return None  # Eski (süresi geçmiş) butonlarda Telegram hata verebilir; önemsiz

    def get_updates(self, offset: int = 0):
        """Yeni mesajları getirir. Telegram tarafında takılmış bir mesaj okunamıyorsa
        önce tek tek okumayı dener, o da olmazsa birikmiş mesajları atlar (self.skipped_updates)."""
        try:
            return self.call("getUpdates", offset=offset, timeout=0,
                             allowed_updates=["message", "callback_query"])
        except TelegramError as e:
            if "Unauthorized" in str(e) or "Not Found" in str(e):
                raise  # Anahtar hatası: atlamak çözüm değil
        try:
            return self.call("getUpdates", offset=offset, timeout=0, limit=1)
        except TelegramError as e:
            if "Unauthorized" in str(e) or "Not Found" in str(e):
                raise
        # Son çare: birikmiş mesajları atla (offset=-1 sadece en son mesajı getirir)
        self.skipped_updates = True
        return self.call("getUpdates", offset=-1, timeout=0)

    # --- Dosya ---
    def download(self, file_id: str, dest: Path) -> Path:
        info = self.call("getFile", file_id=file_id)
        r = requests.get(f"https://api.telegram.org/file/bot{self.token}/{info['file_path']}", timeout=300)
        r.raise_for_status()
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(r.content)
        return dest
