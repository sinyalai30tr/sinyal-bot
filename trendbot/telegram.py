"""Telegram Bot API için küçük yardımcı (sadece `requests`)."""
from __future__ import annotations

import json
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

    def call(self, method: str, files: dict | None = None, http_timeout: int = 120, **params):
        # Not: Telegram'ın kendi "timeout" parametresiyle karışmasın diye bağlantı süresi http_timeout
        # reply_markup gibi sözlükler JSON metni olarak gönderilmeli
        data = {k: (json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v)
                for k, v in params.items() if v is not None}
        r = requests.post(f"{self.base}/{method}", data=data, files=files, timeout=http_timeout)
        try:
            j = r.json()
        except ValueError as e:
            raise TelegramError(f"{method}: HTTP {r.status_code}") from e
        if not j.get("ok"):
            raise TelegramError(f"{method}: {j.get('description', 'bilinmeyen hata')}")
        return j["result"]

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
        return self.call("getUpdates", offset=offset, timeout=0,
                         allowed_updates=["message", "callback_query"])

    # --- Dosya ---
    def download(self, file_id: str, dest: Path) -> Path:
        info = self.call("getFile", file_id=file_id)
        r = requests.get(f"https://api.telegram.org/file/bot{self.token}/{info['file_path']}", timeout=300)
        r.raise_for_status()
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(r.content)
        return dest
