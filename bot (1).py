"""Sinyal Telegram botu: videoları telefona gönderir, onay/red ve komutları işler.

Bulutta (GitHub Actions) iki şekilde çalışır:
    python bot.py gunluk    ->  günün videosunu üretir ve Telegram'a gönderir
    python bot.py kontrol   ->  Telegram'daki yeni mesajları/buton basışlarını işler

Telegram'dan kullanılabilecek komutlar:
    /start               ->  botu sahiplen (ilk yazan kişi sahip olur, sonra kilitlenir)
    yeni video / /video  ->  hemen yeni video hazırla
    /durum               ->  onay bekleyen videoları listele
    (videoya yanıt yaz)  ->  o videonun açıklama metnini değiştir
    (sesli mesaj yanıtı) ->  videoyu senin sesinle yeniden hazırla
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime
from html import escape
from pathlib import Path

from trendbot.config import ROOT, load_config, resolve_path
from trendbot.publishers import PLATFORMS, load_accounts, platform_status, publish_all
from trendbot.telegram import Telegram, TelegramError

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

STATE_PATH = ROOT / "data" / "bot_durum.json"
MAX_RETRY = 3            # Yapay zekâ yoğunsa kaç kez otomatik tekrar denensin
OFFER_OWN_VOICE = False  # True yapılırsa her videonun altında "kendi sesinle oku" mesajı gönderilir
VIDEO_WORDS = ("yeni video", "/video", "video yap", "video üret", "video uret")
HELP = ("Komutlar:\n"
        "• <b>yeni video</b> → hemen yeni video hazırlarım (~10 dk)\n"
        "• <b>/durum</b> → onay bekleyen videolar\n"
        "• Bir videoya <b>yanıt</b> olarak yazarsan, o videonun açıklamasını değiştiririm\n"
        "• Bir videoya <b>sesli mesajla</b> yanıt verirsen, videoyu senin sesinle yeniden hazırlarım\n"
        "• Her sabah 08:00'de günün videosu otomatik gelir")


# ---------------- Durum dosyası ----------------
def load_state() -> dict:
    if STATE_PATH.exists():
        s = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    else:
        s = {}
    s.setdefault("sahip", os.getenv("TELEGRAM_CHAT_ID") or None)
    s.setdefault("offset", 0)
    s.setdefault("bekleyen", {})   # kısa_kod -> video bilgisi
    s.setdefault("gecmis", [])     # son kararlar (en fazla 50)
    s.setdefault("ses_isleri", [])  # kendi sesinle yeniden üretilecek videolar
    s.setdefault("yeni_video_istendi", False)
    s.setdefault("tekrar_deneme", 0)    # Yapay zekâ yoğunken yapılan otomatik deneme sayısı
    return s


def save_state(s: dict) -> None:
    s["gecmis"] = s["gecmis"][-50:]
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8")


def set_output(name: str, value: str) -> None:
    """GitHub Actions'ta sonraki adıma bilgi aktarır."""
    out = os.getenv("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as f:
            f.write(f"{name}={value}\n")


# ---------------- Mesaj biçimleri ----------------
def caption_for(meta: dict) -> str:
    lines = [f"🎬 <b>{escape(meta.get('baslik', ''))}</b>",
             f"⏱ {meta.get('sure_sn', 0)} sn · 🔊 {escape(meta.get('ses', ''))} ses", "",
             f"📝 <b>Açıklama</b>\n{escape(meta.get('aciklama', ''))[:450]}"]
    checks = meta.get("dogrulanacaklar") or []
    if checks:
        lines += ["", "✅ <b>Yayından önce kontrol et</b>"] + [f"• {escape(str(c))}" for c in checks[:3]]
    srcs = meta.get("kaynaklar") or []
    if srcs:
        lines += ["", "🔗 " + " · ".join(f'<a href="{escape(s.get("url", ""))}">{escape(str(s.get("kaynak", "kaynak")).split(",")[0])}</a>'
                                          for s in srcs[:3])]
    lines += ["", "<i>Açıklamayı değiştirmek için bu videoya yanıt yaz.</i>"]
    return "\n".join(lines)[:1024]


def buttons(code: str) -> dict:
    return {"inline_keyboard": [[{"text": "✅ Onayla ve paylaş", "callback_data": f"ok:{code}"},
                                 {"text": "❌ Reddet", "callback_data": f"no:{code}"}]]}


def script_message(meta: dict) -> str:
    return ("🎙️ <b>Kendi sesinle seslendirmek ister misin?</b>\n"
            "Bu mesaja (ya da videoya) <b>sesli mesajla yanıt ver</b> ve aşağıdaki metni oku. "
            "Videoyu senin sesinle yeniden hazırlayıp onayına getiririm.\n\n"
            f"<i>{escape(meta.get('senaryo', ''))}</i>")[:4096]


def send_for_approval(tg: Telegram, chat, state: dict, meta: dict, video: Path, code: str | None = None) -> str:
    """Videoyu butonlarla gönderir, seslendirme metnini ayrı mesaj olarak ekler, bekleyenlere kaydeder."""
    code = code or uuid.uuid4().hex[:8]
    msg = tg.send_video(chat, video, caption_for(meta), buttons(code))
    meta["file_id"] = msg["video"]["file_id"]
    meta["message_id"] = msg["message_id"]
    if OFFER_OWN_VOICE and meta.get("ses") != "kendi sesin":
        meta["metin_mesaj_id"] = tg.send_message(chat, script_message(meta), reply_to=msg["message_id"])["message_id"]
    state["bekleyen"][code] = meta
    return code


def active_platforms(acc: dict) -> list[str]:
    return [p for p in PLATFORMS if platform_status(p, acc)[0]]


# ---------------- Görevler ----------------
def videos_dir() -> Path:
    return resolve_path(load_config()["genel"].get("cikti_klasoru", "outputs")) / "videolar"


def cmd_gunluk(tg: Telegram, state: dict, skip_generate: bool = False) -> None:
    """Video üretir ve henüz gönderilmemiş, onay bekleyen videoları Telegram'a yollar."""
    chat = state.get("sahip")
    if not chat:
        print("Bot sahibi yok: önce Telegram'da bota /start yaz.")
        return
    process_voice_jobs(tg, state)
    # "Telegram kontrol" iş akışından çağrıldıysa sadece istenmişse yeni video üret
    from_control = os.getenv("GITHUB_WORKFLOW", "") == "Telegram kontrol"
    if from_control and not state.get("yeni_video_istendi"):
        return
    state["yeni_video_istendi"] = False
    sent_ids = {v["id"] for v in state["bekleyen"].values()} | {g.get("id") for g in state["gecmis"]}
    log_tail = ""
    if not skip_generate:
        print("Günlük üretim başlıyor...")
        proc = subprocess.run([sys.executable, "run_daily.py", "--acma"], cwd=ROOT,
                              capture_output=True, text=True, encoding="utf-8", errors="replace")
        print(proc.stdout[-6000:])
        print(proc.stderr[-3000:], file=sys.stderr)
        log_tail = (proc.stdout + proc.stderr)[-600:]
        if proc.returncode == 2:  # run_daily: yapay zekâ cevap vermedi (genelde "yoğunluk")
            state["tekrar_deneme"] = state.get("tekrar_deneme", 0) + 1
            if state["tekrar_deneme"] <= MAX_RETRY:
                state["yeni_video_istendi"] = True  # Kontrol iş akışı ~10 dk sonra tekrar dener
                tg.send_message(chat, f"⏳ Google'ın ücretsiz yapay zekâsı şu an çok yoğun. "
                                      f"10 dakika sonra kendim tekrar deneyeceğim ({state['tekrar_deneme']}/{MAX_RETRY}). "
                                      "Senin bir şey yapmana gerek yok.")
            else:
                state["tekrar_deneme"] = 0
                tg.send_message(chat, "⚠️ Yapay zekâ birkaç denemede de cevap vermedi. Daha sonra "
                                      "<b>yeni video</b> yazarak tekrar isteyebilirsin.")
            return
        state["tekrar_deneme"] = 0

    new = []
    vdir = videos_dir()
    for mp in sorted(vdir.glob("*.json")) if vdir.exists() else []:
        meta = json.loads(mp.read_text(encoding="utf-8"))
        if meta.get("durum") == "onay_bekliyor" and meta["id"] not in sent_ids and (vdir / meta["video"]).exists():
            new.append(meta)

    if not new:
        tg.send_message(chat, "⚠️ Bugün yeni video üretilemedi.\n\n<code>" + escape(log_tail[-500:] or "Yeni haber bulunamadı.") + "</code>")
        return
    for meta in new:
        code = send_for_approval(tg, chat, state, meta, vdir / meta["video"])
        print(f"Gönderildi: {meta['baslik']} ({code})")


def process_voice_jobs(tg: Telegram, state: dict) -> None:
    """Sesli mesajla gelen kayıtlarla videoları yeniden üretir ve onaya sunar."""
    jobs, state["ses_isleri"] = state["ses_isleri"], []
    if not jobs:
        return
    from trendbot.video.maker import remake_with_voice
    cfg = load_config()
    acc = load_accounts()
    if not cfg.get("video", {}).get("kanal_adi"):
        cfg.setdefault("video", {})["kanal_adi"] = acc.get("kanal_adi", "")
    chat = state["sahip"]
    for job in jobs:
        old = state["bekleyen"].get(job["code"])
        if not old:
            continue
        try:
            with tempfile.TemporaryDirectory() as tmp:
                voice = tg.download(job["file_id"], Path(tmp) / "ses.ogg")
                new = remake_with_voice(old, voice, videos_dir(), cfg)
            new["metin_mesaj_id"] = old.get("metin_mesaj_id")
            # Eski videonun butonlarını kaldır, yerine yenisini gönder
            try:
                tg.edit_markup(chat, old["message_id"])
            except TelegramError:
                pass
            state["bekleyen"].pop(job["code"], None)
            send_for_approval(tg, chat, state, new, videos_dir() / new["video"])
            tg.send_message(chat, "☝️ Videonun <b>senin sesinle</b> hali hazır. Beğendiysen onayla. "
                                  "Tekrar okumak istersen yeni videoya yine sesli mesajla yanıt ver.")
        except Exception as e:  # noqa: BLE001
            tg.send_message(chat, f"⚠️ Sesinle video hazırlanamadı: <code>{escape(str(e)[:300])}</code>")


def handle_decision(tg: Telegram, state: dict, cb: dict) -> None:
    action, _, code = cb.get("data", "").partition(":")
    chat = cb["message"]["chat"]["id"]
    meta = state["bekleyen"].pop(code, None)
    if not meta:
        tg.answer_callback(cb["id"], "Bu video zaten işlenmiş.")
        return
    tg.edit_markup(chat, cb["message"]["message_id"])  # Butonları kaldır (çift basmayı önler)
    if action == "no":
        tg.answer_callback(cb["id"], "Reddedildi")
        tg.send_message(chat, f"❌ Reddedildi: <b>{escape(meta['baslik'])}</b>", reply_to=meta.get("message_id"))
        state["gecmis"].append({"id": meta["id"], "karar": "red", "zaman": datetime.now().isoformat(timespec="seconds")})
        return

    tg.answer_callback(cb["id"], "Paylaşılıyor...")
    acc = load_accounts()
    platforms = active_platforms(acc)
    if not platforms:
        tg.send_message(chat, "⚠️ Bağlı platform yok. GitHub'daki gizli bilgileri (UPLOAD_POST_API_KEY, UPLOAD_POST_USER) kontrol et.")
        state["bekleyen"][code] = meta  # Kaybolmasın
        return
    with tempfile.TemporaryDirectory() as tmp:
        video = tg.download(meta["file_id"], Path(tmp) / "video.mp4")
        results = publish_all(video, meta, platforms, acc)
    lines = [f"📤 <b>{escape(meta['baslik'])}</b>"]
    for p, r in results.items():
        icon = "✅" if r.get("ok") else "⚠️"
        link = f' — <a href="{escape(r["url"])}">aç</a>' if r.get("url") else ""
        lines.append(f"{icon} {PLATFORMS[p]['ad']}: {escape(r.get('mesaj', ''))}{link}")
    tg.send_message(chat, "\n".join(lines), reply_to=meta.get("message_id"))
    state["gecmis"].append({"id": meta["id"], "karar": "onay", "sonuc": {p: r.get("ok") for p, r in results.items()},
                            "zaman": datetime.now().isoformat(timespec="seconds")})


def cmd_kontrol(tg: Telegram, state: dict) -> bool:
    """Yeni Telegram güncellemelerini işler. Yeni video istendiyse True döndürür."""
    want_video = False
    updates = tg.get_updates(state["offset"])
    for u in updates:
        state["offset"] = u["update_id"] + 1
        msg, cb = u.get("message"), u.get("callback_query")
        sender = (msg or {}).get("chat", {}).get("id") if msg else cb["message"]["chat"]["id"] if cb else None
        text = ((msg or {}).get("text") or "").strip()

        # İlk /start yazan sahip olur; sonra bot sadece ona cevap verir
        if not state.get("sahip") and msg and text.startswith("/start"):
            state["sahip"] = sender
            tg.send_message(sender, "👋 Merhaba! Ben Sinyal'in video asistanıyım. Bot artık sadece sana cevap verecek.\n\n" + HELP)
            continue
        if str(sender) != str(state.get("sahip")):
            continue  # Yabancılardan gelenleri yok say

        if cb:
            try:
                handle_decision(tg, state, cb)
            except Exception as e:  # noqa: BLE001
                tg.send_message(sender, f"⚠️ İşlem sırasında hata: <code>{escape(str(e)[:300])}</code>")
            continue

        low = text.lower()
        reply_to = (msg.get("reply_to_message") or {}).get("message_id")
        target = next((c for c, m in state["bekleyen"].items()
                       if reply_to and reply_to in (m.get("message_id"), m.get("metin_mesaj_id"))), None)
        voice = msg.get("voice") or msg.get("audio")
        if voice and not target and len(state["bekleyen"]) == 1:
            target = next(iter(state["bekleyen"]))  # Tek video bekliyorsa yanıt şart değil
        if voice and target:
            state["ses_isleri"].append({"code": target, "file_id": voice["file_id"]})
            want_video = True
            tg.send_message(sender, "🎙️ Sesin alındı! Videoyu senin sesinle hazırlıyorum, birkaç dakika içinde burada.",
                            reply_to=msg.get("message_id"))
        elif voice:
            tg.send_message(sender, "🎙️ Sesin hangi video için? Lütfen ilgili videoya ya da metin mesajına <b>yanıt</b> olarak gönder.")
        elif reply_to and target and text:
            state["bekleyen"][target]["aciklama"] = text
            tg.send_message(sender, "✏️ Açıklama güncellendi. Onaylarsan bu metinle paylaşılacak.", reply_to=reply_to)
        elif any(w in low for w in VIDEO_WORDS):
            want_video = True
            state["yeni_video_istendi"] = True
            tg.send_message(sender, "🎬 Tamam, yeni video hazırlıyorum. Yaklaşık 10 dakika içinde burada olacak.")
        elif low.startswith("/durum"):
            if state["bekleyen"]:
                tg.send_message(sender, "⏳ Onay bekleyenler:\n" + "\n".join(f"• {escape(m['baslik'])}" for m in state["bekleyen"].values()))
            else:
                tg.send_message(sender, "Onay bekleyen video yok.")
        elif low.startswith("/start"):
            tg.send_message(sender, HELP)
        elif text:
            tg.send_message(sender, "Bunu anlayamadım 🙂\n\n" + HELP)
    # Önceki denemede yapay zekâ yoğunsa bekleyen otomatik tekrar
    return want_video or bool(state.get("yeni_video_istendi"))


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else "kontrol"
    tg = Telegram(os.getenv("TELEGRAM_BOT_TOKEN", ""))
    state = load_state()
    try:
        if mode == "gunluk":
            cmd_gunluk(tg, state, skip_generate="--uretme" in sys.argv)
        elif mode == "kontrol":
            set_output("video", "1" if cmd_kontrol(tg, state) else "0")
        else:
            print(__doc__)
            return 1
    except TelegramError as e:
        print(f"Telegram hatası: {e}")
        return 2
    finally:
        save_state(state)
    return 0


if __name__ == "__main__":
    sys.exit(main())
