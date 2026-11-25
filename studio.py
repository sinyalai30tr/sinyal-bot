"""Onay Masası: videoları izle, onayla/reddet, sosyal medya hesaplarını bağla.

Çalıştır:  python studio.py     ->  tarayıcıda http://127.0.0.1:8765 açılır
Sadece kendi bilgisayarından erişilir (127.0.0.1); internete açılmaz.
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


import json
import mimetypes
import re
import sys
import threading
import webbrowser
from datetime import datetime
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from trendbot.config import load_config, resolve_path
from trendbot.publishers import PLATFORMS, load_accounts, platform_status, publish_all, save_accounts

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

CFG = load_config()
VIDEOS = resolve_path(CFG["genel"].get("cikti_klasoru", "outputs")) / "videolar"
PORT = int(CFG.get("studyo", {}).get("port", 8765))
SAFE_ID = re.compile(r"^[\w\-]+$")
DURUM = {"onay_bekliyor": ("Onay bekliyor", "warn"), "onaylandi": ("Onaylandı · hesap bekleniyor", "info"),
         "paylasildi": ("Paylaşıldı", "ok"), "kismen": ("Kısmen paylaşıldı", "warn"),
         "reddedildi": ("Reddedildi", "muted"), "gonderiliyor": ("Gönderiliyor…", "info")}
LOCK = threading.Lock()


# ---------------- Veri ----------------
def list_videos() -> list[dict]:
    if not VIDEOS.exists():
        return []
    items = []
    for p in sorted(VIDEOS.glob("*.json"), reverse=True):
        try:
            m = json.loads(p.read_text(encoding="utf-8"))
            if (VIDEOS / m.get("video", "")).exists():
                items.append(m)
        except json.JSONDecodeError:
            continue
    return items


def load_meta(vid: str) -> dict | None:
    if not SAFE_ID.match(vid or ""):
        return None
    p = VIDEOS / f"{vid}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def save_meta(m: dict) -> None:
    (VIDEOS / f"{m['id']}.json").write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------------- Sayfalar ----------------
CSS = """
:root{--bg:#f2f1ed;--panel:#fff;--ink:#16181d;--muted:#5f6570;--line:#dcdad3;--accent:#d6342b;
--ok:#1f7a4d;--ok-s:#e2f2e9;--warn:#a86300;--warn-s:#fbefd9;--info:#2456a6;--info-s:#e3ecfa;
--body:"IBM Plex Sans",system-ui,-apple-system,"Segoe UI",sans-serif;--mono:"IBM Plex Mono",ui-monospace,Consolas,monospace;color-scheme:light}
@media (prefers-color-scheme:dark){:root{--bg:#121418;--panel:#1b1e24;--ink:#eceae4;--muted:#9aa0aa;--line:#2c3038;--accent:#ff5a4e;
--ok:#5cc792;--ok-s:#173326;--warn:#f0b04a;--warn-s:#3a2c14;--info:#7fa8ff;--info-s:#1b2740;color-scheme:dark}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 var(--body)}
header{display:flex;flex-wrap:wrap;gap:16px;align-items:center;justify-content:space-between;padding:16px 24px;border-bottom:3px solid var(--ink);background:var(--panel)}
header h1{margin:0;font-size:22px;letter-spacing:.02em;text-transform:uppercase}
header h1 span{display:inline-block;width:11px;height:11px;border-radius:50%;background:var(--accent);margin-right:8px}
nav{display:flex;gap:6px}nav a{padding:7px 14px;border-radius:6px;text-decoration:none;color:var(--ink);border:1px solid var(--line);font-weight:600}
nav a.on{background:var(--ink);color:var(--bg);border-color:var(--ink)}
main{max-width:1100px;margin:0 auto;padding:24px 20px 60px;display:flex;flex-direction:column;gap:22px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:18px;display:grid;grid-template-columns:280px 1fr;gap:22px}
video{width:280px;aspect-ratio:9/16;border-radius:12px;background:#000}
h2{margin:0 0 4px;font-size:22px;text-wrap:balance}h3{font:600 12px var(--mono);text-transform:uppercase;letter-spacing:.08em;color:var(--muted);margin:14px 0 6px}
.meta{font:13px var(--mono);color:var(--muted);display:flex;flex-wrap:wrap;gap:6px 14px}
.pill{font:600 12px var(--mono);padding:3px 9px;border-radius:999px;display:inline-block}
.pill.ok{background:var(--ok-s);color:var(--ok)}.pill.warn{background:var(--warn-s);color:var(--warn)}
.pill.info{background:var(--info-s);color:var(--info)}.pill.muted{background:var(--bg);color:var(--muted)}
label{display:block;font-weight:600;font-size:14px;margin:10px 0 4px}
input[type=text],input[type=password],textarea,select{width:100%;padding:8px 10px;border:1px solid var(--line);border-radius:6px;background:var(--bg);color:var(--ink);font:14px var(--body)}
textarea{min-height:90px;resize:vertical}
.plats{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:8px}
.plat{border:1px solid var(--line);border-radius:8px;padding:8px 10px;display:flex;gap:8px;align-items:flex-start;font-size:14px}
.plat small{display:block;color:var(--muted);font-size:12px}
.plat.off{opacity:.6}
.btns{display:flex;flex-wrap:wrap;gap:10px;margin-top:16px}
button{font:600 14px var(--body);padding:10px 18px;border-radius:8px;border:1px solid var(--ink);background:var(--panel);color:var(--ink);cursor:pointer}
button.primary{background:var(--accent);border-color:var(--accent);color:#fff}
button:focus-visible,a:focus-visible,input:focus-visible{outline:2px solid var(--info);outline-offset:2px}
button:disabled{opacity:.5;cursor:wait}
ul{margin:0;padding-left:18px}.res li{margin:2px 0}
.note{background:var(--warn-s);color:var(--warn);border-radius:8px;padding:10px 14px;font-size:14px}
.empty{text-align:center;color:var(--muted);padding:60px 0}
details summary{cursor:pointer;font-weight:600}
.acc{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:18px}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.row{display:grid;grid-template-columns:180px 110px 1fr;gap:12px;align-items:center;padding:10px 0;border-top:1px solid var(--line)}
.msg{font:13px var(--mono);margin-left:8px}
@media (max-width:760px){.card{grid-template-columns:1fr}video{width:100%;max-width:320px}.grid2,.row{grid-template-columns:1fr}}
"""

JS = """
async function post(url, body){
  const r = await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  return r.json();
}
async function decide(id, action, btn){
  const card = document.getElementById('c-'+id);
  const plats = [...card.querySelectorAll('input[name=plat]:checked')].map(x=>x.value);
  const body = {id, platforms: plats,
    youtube_baslik: card.querySelector('[name=yt]').value, aciklama: card.querySelector('[name=desc]').value};
  card.querySelectorAll('button').forEach(b=>b.disabled=true);
  btn.textContent = action==='onayla' ? 'Gönderiliyor…' : 'Kaydediliyor…';
  const res = await post('/api/'+action, body);
  location.reload();
}
async function saveAcc(e){
  e.preventDefault();
  const f = e.target, data = {kanal_adi: f.kanal_adi.value,
    upload_post:{api_key:f.up_key.value, kullanici:f.up_user.value},
    yapay_zeka:{gemini_api_key:f.gem_key.value.trim(), anthropic_api_key:f.ant_key.value.trim()}};
  for (const p of ['youtube','instagram','tiktok','x']){
    data[p] = {aktif: f[p+'_aktif'].checked, yol: f[p+'_yol'].value};
  }
  data.youtube.gizlilik = f.youtube_gizlilik.value; data.youtube.client_secret = f.youtube_secret.value;
  data.instagram.ig_user_id = f.ig_id.value; data.instagram.access_token = f.ig_token.value;
  data.tiktok.gizlilik = f.tiktok_gizlilik.value;
  await post('/api/hesaplar', data); location.reload();
}
async function testAi(btn){
  btn.disabled = true; const m = document.getElementById('ai-msg'); m.textContent='Kaydediliyor ve deneniyor…';
  const f = btn.form;
  await post('/api/hesaplar', {yapay_zeka:{gemini_api_key:f.gem_key.value.trim(), anthropic_api_key:f.ant_key.value.trim()}});
  const r = await post('/api/test_ai', {}); m.textContent = r.mesaj; btn.disabled=false;
}
async function testUp(btn){
  btn.disabled = true; const m = document.getElementById('up-msg'); m.textContent='Deneniyor…';
  const r = await post('/api/test_upload_post', {}); m.textContent = r.mesaj; btn.disabled=false;
}
"""


def page(title: str, tab: str, body: str) -> str:
    return f"""<!DOCTYPE html><html lang="tr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{escape(title)}</title>
<style>{CSS}</style></head><body>
<header><h1><span></span>AI Trend Stüdyosu</h1>
<nav><a href="/" class="{'on' if tab == 'onay' else ''}">Onay Masası</a>
<a href="/hesaplar" class="{'on' if tab == 'hesap' else ''}">Hesaplar</a></nav></header>
<main>{body}</main><script>{JS}</script></body></html>"""


def render_queue() -> str:
    acc = load_accounts()
    vids = list_videos()
    if not vids:
        return page("Onay Masası", "onay", '<div class="empty">Henüz video yok. Önce <code>python run_daily.py</code> çalıştır.</div>')
    status_map = {p: platform_status(p, acc) for p in PLATFORMS}
    any_ready = any(ok for ok, _ in status_map.values())
    out = []
    if not any_ready:
        out.append('<div class="note">Henüz bağlı sosyal medya hesabı yok. Videoyu yine de onaylayabilirsin; '
                   'hesapları <a href="/hesaplar">Hesaplar</a> sayfasından bağladığında "Tekrar gönder" ile paylaşılır.</div>')
    for m in vids:
        vid = escape(m["id"])
        label, cls = DURUM.get(m.get("durum", ""), (m.get("durum", ""), "muted"))
        plats = []
        for p, info in PLATFORMS.items():
            ok, why = status_map[p]
            done = m.get("paylasim_sonuclari", {}).get(p, {}).get("ok")
            checked = "checked" if ok and not done else ""
            plats.append(f'<label class="plat {"" if ok else "off"}"><input type="checkbox" name="plat" value="{p}" {checked}>'
                         f'<span>{info["ad"]}<small>{"Paylaşıldı" if done else escape(why)}</small></span></label>')
        checks = "".join(f"<li>{escape(str(c))}</li>" for c in m.get("dogrulanacaklar", [])) or "<li>—</li>"
        srcs = "".join(f'<li><a href="{escape(s.get("url", ""))}" target="_blank" rel="noopener">{escape(s.get("baslik", ""))}</a></li>'
                       for s in m.get("kaynaklar", [])) or "<li>—</li>"
        results = "".join(
            f'<li>{escape(PLATFORMS.get(p, {}).get("ad", p))}: {"✓" if r.get("ok") else "✗"} {escape(r.get("mesaj", ""))}'
            + (f' · <a href="{escape(r["url"])}" target="_blank" rel="noopener">aç</a>' if r.get("url") else "") + "</li>"
            for p, r in m.get("paylasim_sonuclari", {}).items())
        state = m.get("durum")
        if state == "onay_bekliyor":
            buttons = (f'<button class="primary" onclick="decide(\'{vid}\',\'onayla\',this)">Onayla ve paylaş</button>'
                       f'<button onclick="decide(\'{vid}\',\'reddet\',this)">Reddet</button>')
        elif state in ("onaylandi", "kismen"):
            buttons = f'<button class="primary" onclick="decide(\'{vid}\',\'onayla\',this)">Tekrar gönder</button>'
        elif state == "reddedildi":
            buttons = f'<button onclick="decide(\'{vid}\',\'geri_al\',this)">Onaya geri al</button>'
        else:
            buttons = ""
        out.append(f"""
<section class="card" id="c-{vid}">
  <video src="/media/{escape(m["video"])}#t=0.8" controls playsinline preload="metadata"></video>
  <div>
    <span class="pill {cls}">{escape(label)}</span>
    <span class="pill muted">{'🇬🇧 English' if m.get('dil') == 'en' else '🇹🇷 Türkçe'}</span>
    <h2>{escape(m.get('baslik', ''))}</h2>
    <div class="meta"><span>{m.get('sure_sn', 0)} sn</span><span>Ses: {escape(m.get('ses', ''))} ({escape(m.get('tts_motoru', ''))})</span>
      <span>{escape(m.get('olusturma', '')[:16].replace('T', ' '))}</span></div>
    <label for="yt-{vid}">YouTube başlığı</label><input type="text" id="yt-{vid}" name="yt" value="{escape(m.get('youtube_baslik', ''))}">
    <label for="d-{vid}">Açıklama (tüm platformlar)</label><textarea id="d-{vid}" name="desc">{escape(m.get('aciklama', ''))}</textarea>
    <h3>Nereye gitsin?</h3><div class="plats">{''.join(plats)}</div>
    <h3>Yayından önce doğrula</h3><ul>{checks}</ul>
    <h3>Kaynaklar</h3><ul>{srcs}</ul>
    <details><summary>Seslendirme metni</summary><p>{escape(m.get('senaryo', ''))}</p></details>
    {f'<h3>Paylaşım sonuçları</h3><ul class="res">{results}</ul>' if results else ''}
    <div class="btns">{buttons}</div>
  </div>
</section>""")
    return page("Onay Masası", "onay", "".join(out))


def render_accounts() -> str:
    a = load_accounts()

    def opt(val, cur, label=None):
        return f'<option value="{val}" {"selected" if val == cur else ""}>{label or val}</option>'

    rows = []
    for p, info in PLATFORMS.items():
        ok, why = platform_status(p, a)
        yol_opts = "".join(opt(y, a[p].get("yol"), "Upload-Post" if y == "upload_post" else "Doğrudan API") for y in info["yollar"])
        rows.append(f"""<div class="row"><strong>{info['ad']}</strong>
<label style="margin:0"><input type="checkbox" name="{p}_aktif" {"checked" if a[p].get("aktif") else ""}> Aktif</label>
<div><select name="{p}_yol" aria-label="{info['ad']} bağlantı yolu">{yol_opts}</select>
<small class="pill {'ok' if ok else 'muted'}" style="margin-top:6px">{escape(why)}</small></div></div>""")
    body = f"""
<form class="acc" onsubmit="saveAcc(event)">
  <h2>Hesaplar</h2>
  <p>Bilgiler sadece bu bilgisayarda, <code>data/hesaplar.json</code> dosyasında saklanır.</p>
  <label for="kanal_adi">Kanal adı (videonun köşesinde görünür)</label>
  <input type="text" id="kanal_adi" name="kanal_adi" placeholder="@kanaladin" value="{escape(a.get('kanal_adi', ''))}">

  <h3>1 · Yapay zekâ (haberleri seçer, senaryoyu yazar)</h3>
  <div class="grid2">
    <div><label for="gem_key">Gemini API anahtarı (ücretsiz)</label><input type="password" id="gem_key" name="gem_key" value="{escape(a.get('yapay_zeka', {}).get('gemini_api_key', ''))}"></div>
    <div><label for="ant_key">Anthropic API anahtarı (isteğe bağlı, ücretli)</label><input type="password" id="ant_key" name="ant_key" value="{escape(a.get('yapay_zeka', {}).get('anthropic_api_key', ''))}"></div>
  </div>
  <div class="btns"><button type="button" onclick="testAi(this)">Yapay zekâyı test et</button><span id="ai-msg" class="msg"></span></div>

  <h3>2 · Upload-Post (önerilen: tek anahtarla tüm platformlar)</h3>
  <div class="grid2">
    <div><label for="up_key">API anahtarı</label><input type="password" id="up_key" name="up_key" value="{escape(a['upload_post'].get('api_key', ''))}"></div>
    <div><label for="up_user">Profil (kullanıcı) adı</label><input type="text" id="up_user" name="up_user" value="{escape(a['upload_post'].get('kullanici', ''))}"></div>
  </div>
  <div class="btns"><button type="button" onclick="testUp(this)">Bağlantıyı test et</button><span id="up-msg" class="msg"></span></div>

  <h3>3 · Platformlar</h3>
  {''.join(rows)}

  <h3>Platform ayarları</h3>
  <div class="grid2">
    <div><label for="youtube_gizlilik">YouTube görünürlük</label><select id="youtube_gizlilik" name="youtube_gizlilik">
      {opt('public', a['youtube'].get('gizlilik'), 'Herkese açık')}{opt('unlisted', a['youtube'].get('gizlilik'), 'Liste dışı')}{opt('private', a['youtube'].get('gizlilik'), 'Gizli')}</select></div>
    <div><label for="youtube_secret">YouTube client_secret (yalnızca doğrudan API)</label><input type="text" id="youtube_secret" name="youtube_secret" value="{escape(a['youtube'].get('client_secret', ''))}"></div>
    <div><label for="ig_id">Instagram kullanıcı ID (yalnızca doğrudan API)</label><input type="text" id="ig_id" name="ig_id" value="{escape(a['instagram'].get('ig_user_id', ''))}"></div>
    <div><label for="ig_token">Instagram erişim anahtarı (yalnızca doğrudan API)</label><input type="password" id="ig_token" name="ig_token" value="{escape(a['instagram'].get('access_token', ''))}"></div>
    <div><label for="tiktok_gizlilik">TikTok görünürlük</label><select id="tiktok_gizlilik" name="tiktok_gizlilik">
      {opt('PUBLIC_TO_EVERYONE', a['tiktok'].get('gizlilik'), 'Herkese açık')}{opt('FOLLOWER_OF_CREATOR', a['tiktok'].get('gizlilik'), 'Takipçiler')}{opt('SELF_ONLY', a['tiktok'].get('gizlilik'), 'Sadece ben')}</select></div>
  </div>
  <div class="btns"><button class="primary" type="submit">Kaydet</button></div>
</form>
<div class="acc"><h2>Bilmen gerekenler</h2><ul>
  <li><b>X (Twitter):</b> X API'sinde artık ücretsiz paylaşım yok; Upload-Post ücretsiz planı X'i içeriyor.</li>
  <li><b>TikTok:</b> Upload-Post'ta TikTok ücretsiz planda yok, Basic planla açılıyor. Kendi TikTok uygulamanla yaparsan TikTok denetimi bitene kadar videolar sadece sana görünür.</li>
  <li><b>YouTube doğrudan API:</b> Ücretsiz, ama Google denetimi bitene kadar videolar gizli yüklenir; Studio'dan elle açabilirsin.</li>
  <li><b>Instagram doğrudan API:</b> İşletme/İçerik Üretici hesabı + bağlı Facebook sayfası + Meta geliştirici uygulaması gerekir.</li>
  <li><b>Yapay zekâ etiketi:</b> Seslendirme yapay olduğu için platformların "yapay zekâ ile oluşturuldu" etiketini açık tutman önerilir.</li>
</ul></div>"""
    return page("Hesaplar", "hesap", body)


# ---------------- Sunucu ----------------
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # Konsolu sessiz tut
        pass

    def _send(self, code: int, body: bytes, ctype: str = "text/html; charset=utf-8", extra: dict | None = None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False).encode(), "application/json; charset=utf-8")

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/":
            return self._send(200, render_queue().encode())
        if path == "/hesaplar":
            return self._send(200, render_accounts().encode())
        if path.startswith("/media/"):
            return self._media(path[len("/media/"):])
        self._send(404, b"Bulunamadi")

    def _media(self, name: str):
        """<video> etiketinin ileri-geri sarabilmesi için Range desteğiyle dosya sunar."""
        f = VIDEOS / name
        if not re.match(r"^[\w\-]+\.mp4$", name) or not f.exists():
            return self._send(404, b"Yok")
        size = f.stat().st_size
        rng = self.headers.get("Range")
        start, end = 0, size - 1
        if rng and rng.startswith("bytes="):
            a, _, b = rng[6:].partition("-")
            start = int(a) if a else 0
            end = int(b) if b else size - 1
        end = min(end, size - 1)
        with open(f, "rb") as fh:
            fh.seek(start)
            data = fh.read(end - start + 1)
        headers = {"Accept-Ranges": "bytes"}
        if rng:
            headers["Content-Range"] = f"bytes {start}-{end}/{size}"
        self._send(206 if rng else 200, data, mimetypes.guess_type(name)[0] or "video/mp4", headers)

    def do_POST(self):
        path = urlparse(self.path).path
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or b"{}")
        if path == "/api/hesaplar":
            acc = load_accounts()
            for k, v in body.items():
                if isinstance(v, dict) and isinstance(acc.get(k), dict):
                    acc[k].update(v)
                else:
                    acc[k] = v
            save_accounts(acc)
            return self._json({"ok": True})
        if path == "/api/test_ai":
            from trendbot.llm import LLMError, complete, resolve_provider
            try:
                prov = resolve_provider(CFG["llm"])
                out = complete("Sadece geçerli JSON döndür.", 'Şunu aynen döndür: {"durum":"tamam"}', CFG["llm"])
                ok = "tamam" in out
                return self._json({"ok": ok, "mesaj": f"Bağlantı başarılı ({prov})" if ok else f"Beklenmeyen cevap: {out[:80]}"})
            except LLMError as e:
                return self._json({"ok": False, "mesaj": str(e)[:200]})
            except Exception as e:  # noqa: BLE001
                return self._json({"ok": False, "mesaj": f"{e.__class__.__name__}: {str(e)[:150]}"})
        if path == "/api/test_upload_post":
            from trendbot.publishers.upload_post import test_connection
            acc = load_accounts()
            if not acc["upload_post"].get("api_key"):
                return self._json({"ok": False, "mesaj": "Önce API anahtarını girip kaydet."})
            ok, msg = test_connection(acc)
            return self._json({"ok": ok, "mesaj": msg})
        if path in ("/api/onayla", "/api/reddet", "/api/geri_al"):
            return self._decide(path.rsplit("/", 1)[-1], body)
        self._json({"ok": False, "mesaj": "Bilinmeyen istek"}, 404)

    def _decide(self, action: str, body: dict):
        with LOCK:
            m = load_meta(body.get("id", ""))
            if not m:
                return self._json({"ok": False, "mesaj": "Video bulunamadı"}, 404)
            m["youtube_baslik"] = body.get("youtube_baslik", m.get("youtube_baslik", ""))
            m["aciklama"] = body.get("aciklama", m.get("aciklama", ""))
            m["karar_zamani"] = datetime.now().isoformat(timespec="seconds")
            if action == "reddet":
                m["durum"] = "reddedildi"
                save_meta(m)
                return self._json({"ok": True})
            if action == "geri_al":
                m["durum"] = "onay_bekliyor"
                save_meta(m)
                return self._json({"ok": True})
            # Onay: seçilen platformlara gönder
            platforms = [p for p in body.get("platforms", []) if p in PLATFORMS]
            results = publish_all(VIDEOS / m["video"], m, platforms, load_accounts(), print) if platforms else {}
            m.setdefault("paylasim_sonuclari", {}).update(results)
            oks = [r.get("ok") for r in m["paylasim_sonuclari"].values()]
            m["durum"] = "paylasildi" if oks and all(oks) else ("kismen" if any(oks) else "onaylandi")
            save_meta(m)
            print(f"[{m['durum']}] {m['baslik']}: " + ", ".join(f"{p}={'OK' if r.get('ok') else r.get('mesaj')}" for p, r in results.items()))
            return self._json({"ok": True, "sonuclar": results})


def main():
    VIDEOS.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    url = f"http://127.0.0.1:{PORT}"
    print(f"Onay Masası açık: {url}  (kapatmak için Ctrl+C)")
    if "--acma" not in sys.argv:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nKapatıldı.")


if __name__ == "__main__":
    main()
