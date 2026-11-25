"""Tarayıcıda açılan, tek dosyalık HTML çıktısı.

- İnternet gerekmez (yazı tipleri yoksa sistem fontu kullanılır).
- Hook / senaryo / altyazı / açıklama için "Kopyala" düğmeleri.
- [SENİN NOTUN] alanı ve "Doğrula" kutucukları tarayıcıda (localStorage) hatırlanır.
"""
from __future__ import annotations

import json
from datetime import datetime
from html import escape
from pathlib import Path

from .models import Item

AYLAR = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
         "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]

CSS = """
:root{
  /* Yayın akışı (rundown) kâğıdı: mürekkep lacivert + kayıt kırmızısı */
  --bg:#f3f2ee; --panel:#ffffff; --ink:#16181d; --muted:#5d636e; --line:#dcdad3;
  --accent:#d6342b; --accent-soft:#fbe6e3; --ok:#1f7a4d; --ok-soft:#e2f2e9; --warn:#a86300; --warn-soft:#fbefd9;
  --display:"Barlow Condensed","Arial Narrow",system-ui,sans-serif;
  --body:"IBM Plex Sans",system-ui,-apple-system,"Segoe UI",sans-serif;
  --mono:"IBM Plex Mono",ui-monospace,Consolas,monospace;
  color-scheme:light;
}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
  --bg:#121418; --panel:#1b1e24; --ink:#eceae4; --muted:#9aa0aa; --line:#2c3038;
  --accent:#ff5a4e; --accent-soft:#3a1d1b; --ok:#5cc792; --ok-soft:#173326; --warn:#f0b04a; --warn-soft:#3a2c14; color-scheme:dark;}}
:root[data-theme="dark"]{
  --bg:#121418; --panel:#1b1e24; --ink:#eceae4; --muted:#9aa0aa; --line:#2c3038;
  --accent:#ff5a4e; --accent-soft:#3a1d1b; --ok:#5cc792; --ok-soft:#173326; --warn:#f0b04a; --warn-soft:#3a2c14; color-scheme:dark;}
*{box-sizing:border-box}
html,body{margin:0}
body{background:var(--bg);color:var(--ink);font:15px/1.6 var(--body)}
a{color:inherit}
.wrap{max-width:1180px;margin:0 auto;padding:24px 20px 64px;display:grid;grid-template-columns:240px 1fr;gap:28px}
header.top{grid-column:1/-1;display:flex;flex-wrap:wrap;align-items:flex-end;justify-content:space-between;gap:12px;border-bottom:3px solid var(--ink);padding-bottom:12px}
.top h1{font:700 40px/1 var(--display);letter-spacing:.01em;margin:0;text-transform:uppercase}
.top h1 .rec{display:inline-block;width:12px;height:12px;border-radius:50%;background:var(--accent);margin-right:10px;vertical-align:middle}
.stats{display:flex;flex-wrap:wrap;gap:6px 16px;color:var(--muted);font:13px var(--mono)}
.stats b{color:var(--ink);font-weight:600}
.banner{grid-column:1/-1;background:var(--warn-soft);color:var(--warn);border-radius:6px;padding:8px 12px;font-size:14px}
nav.rundown{position:sticky;top:16px;align-self:start;display:flex;flex-direction:column;gap:6px}
nav.rundown .lbl{font:600 12px var(--mono);color:var(--muted);text-transform:uppercase;letter-spacing:.08em;margin-bottom:4px}
nav.rundown a{display:grid;grid-template-columns:28px 1fr auto;gap:8px;align-items:center;text-decoration:none;padding:8px 10px;border-radius:6px;background:var(--panel);border:1px solid var(--line)}
nav.rundown a:hover,nav.rundown a:focus-visible{border-color:var(--ink);outline:none}
nav.rundown .n{font:700 20px var(--display);color:var(--accent)}
nav.rundown .t{font-size:13px;line-height:1.3}
nav.rundown .d{font:12px var(--mono);color:var(--muted)}
nav.rundown a.done{opacity:.55}
nav.rundown a.done .t{text-decoration:line-through}
main{display:flex;flex-direction:column;gap:28px;min-width:0}
article.topic{background:var(--panel);border:1px solid var(--line);border-radius:10px;overflow:hidden}
.slug{display:flex;flex-wrap:wrap;align-items:center;gap:10px;padding:14px 18px;border-bottom:1px solid var(--line)}
.slug .num{font:700 34px/1 var(--display);color:var(--accent);min-width:34px}
.slug h2{font:700 26px/1.1 var(--display);margin:0;flex:1 1 260px;text-wrap:balance}
.pill{font:600 12px var(--mono);padding:3px 8px;border-radius:999px;background:var(--bg);color:var(--muted);white-space:nowrap}
.pill.ok{background:var(--ok-soft);color:var(--ok)}
.pill.warn{background:var(--warn-soft);color:var(--warn)}
.status{display:flex;align-items:center;gap:6px;font-size:13px;color:var(--muted);cursor:pointer}
.body{display:grid;grid-template-columns:1fr 230px;gap:24px;padding:18px}
.col{display:flex;flex-direction:column;gap:18px;min-width:0}
h3{font:600 12px var(--mono);text-transform:uppercase;letter-spacing:.08em;color:var(--muted);margin:0 0 6px;display:flex;align-items:center;justify-content:space-between;gap:8px}
.sec p{margin:0;max-width:65ch}
.hook{font:700 24px/1.2 var(--display);border-left:4px solid var(--accent);padding:4px 0 4px 12px;margin:0;text-wrap:balance}
.script{background:var(--bg);border-radius:8px;padding:14px 16px;font-size:16px;line-height:1.7;white-space:pre-wrap;max-width:68ch}
.note{border:2px dashed var(--accent);border-radius:8px;padding:12px 14px;background:var(--accent-soft)}
.note label{font:700 13px var(--mono);color:var(--accent);display:block;margin-bottom:6px}
.note textarea{width:100%;min-height:72px;resize:vertical;border:1px solid var(--line);border-radius:6px;padding:8px 10px;font:14px/1.5 var(--body);background:var(--panel);color:var(--ink)}
.copy{font:600 12px var(--mono);border:1px solid var(--line);background:var(--panel);color:var(--ink);border-radius:5px;padding:3px 9px;cursor:pointer;text-transform:none;letter-spacing:0}
.copy:hover,.copy:focus-visible{border-color:var(--ink);outline:none}
.copy.ok{color:var(--ok);border-color:var(--ok)}
ul.plain{margin:0;padding-left:18px}
ul.checks{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:4px}
ul.checks label{display:flex;gap:8px;align-items:flex-start;cursor:pointer}
ul.checks input{margin-top:5px}
.tags{font:13px var(--mono);color:var(--muted);margin-top:6px}
.src a{text-decoration-color:var(--line);text-underline-offset:3px}
.src small{color:var(--muted)}
/* 9:16 telefon önizlemesi */
.phone{aspect-ratio:9/16;border-radius:18px;background:#0d0f12;color:#fff;position:relative;overflow:hidden;border:6px solid #2a2d33;display:flex;flex-direction:column;justify-content:flex-start;padding:28px 14px}
.phone .ttl{font:800 26px/1.05 var(--display);text-transform:uppercase;background:var(--accent);padding:6px 8px;align-self:flex-start;text-wrap:balance}
.phone .sub{margin-top:8px;font:600 13px/1.3 var(--body);background:rgba(255,255,255,.92);color:#111;padding:4px 7px;align-self:flex-start}
.phone .cap{position:absolute;left:10px;right:10px;bottom:22%;text-align:center;font:800 17px/1.2 var(--body);text-shadow:0 2px 6px #000}
.phone .hint{position:absolute;bottom:8px;left:0;right:0;text-align:center;font:10px var(--mono);color:#8a8f98}
.subs{font:12px/1.6 var(--mono);background:var(--bg);border-radius:8px;padding:10px 12px;max-height:260px;overflow:auto;margin:0;white-space:pre}
.backup{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:16px 18px}
.backup h2{font:700 22px var(--display);margin:0 0 10px;text-transform:uppercase}
.tbl{overflow-x:auto}
table{border-collapse:collapse;width:100%;font-size:14px}
td,th{padding:7px 8px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
th{font:600 12px var(--mono);color:var(--muted);text-transform:uppercase}
td.num{font-variant-numeric:tabular-nums;font-family:var(--mono);white-space:nowrap}
@media (max-width:900px){.wrap{grid-template-columns:1fr}nav.rundown{position:static}.body{grid-template-columns:1fr}.phone{max-width:230px}}
@media (prefers-reduced-motion:reduce){*{transition:none!important}}
"""

JS = """
(function(){
  var KEY = document.body.dataset.key;
  function load(){ try{ return JSON.parse(localStorage.getItem(KEY)||"{}"); }catch(e){ return {}; } }
  function save(s){ try{ localStorage.setItem(KEY, JSON.stringify(s)); }catch(e){} }
  var state = load();

  // Kopyala düğmeleri
  document.querySelectorAll("button.copy").forEach(function(b){
    b.addEventListener("click", function(){
      var el = document.getElementById(b.dataset.target);
      var text = el.value !== undefined && el.tagName === "TEXTAREA" ? el.value : el.innerText;
      var done = function(){ var old=b.textContent; b.textContent="Kopyalandı"; b.classList.add("ok");
        setTimeout(function(){ b.textContent=old; b.classList.remove("ok"); }, 1400); };
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(done, function(){ fallback(text); done(); });
      } else { fallback(text); done(); }
    });
  });
  function fallback(text){
    var t=document.createElement("textarea"); t.value=text; document.body.appendChild(t); t.select();
    try{ document.execCommand("copy"); }catch(e){} t.remove();
  }

  // Notlar, doğrulama kutucukları ve "çekildi" durumu tarayıcıda hatırlanır
  document.querySelectorAll("[data-save]").forEach(function(el){
    var k = el.dataset.save;
    if (el.type === "checkbox") {
      el.checked = !!state[k];
      el.addEventListener("change", function(){ state[k]=el.checked; save(state); sync(); });
    } else {
      if (state[k]) el.value = state[k];
      el.addEventListener("input", function(){ state[k]=el.value; save(state); });
    }
  });
  function sync(){
    document.querySelectorAll("nav.rundown a").forEach(function(a){
      a.classList.toggle("done", !!state["done-"+a.dataset.i]);
    });
  }
  sync();
})();
"""


def _tr_date(d: datetime) -> str:
    return f"{d.day} {AYLAR[d.month - 1]} {d.year}"


def _list(values) -> list[str]:
    if isinstance(values, str):
        return [values] if values.strip() else []
    return [v for v in (values or []) if str(v).strip()]


def _duration_pill(sec: int) -> str:
    cls = "ok" if 22 <= sec <= 31 else "warn"
    return f'<span class="pill {cls}" title="Hedef en fazla 30 sn">~{sec} sn</span>'


def _english_html(i: int, en) -> str:
    """İngilizce sürüm: kopyalanabilir senaryo ve açıklama."""
    if not isinstance(en, dict) or not en.get("senaryo"):
        return ""
    cap = (en.get("paylasim_aciklamasi", "") + "\n\n" + " ".join(_list(en.get("hashtagler")))).strip()
    return (f'<details class="sec" open><summary><h3 style="display:inline">English version · '
            f'{escape(str(en.get("baslik", "")))}</h3></summary>'
            f'<h3>Script <button class="copy" data-target="en-scr-{i}">Kopyala</button></h3>'
            f'<div class="script" id="en-scr-{i}">{escape(str(en.get("senaryo", "")))}</div>'
            f'<h3>Caption <button class="copy" data-target="en-cap-{i}">Kopyala</button></h3>'
            f'<p id="en-cap-{i}" style="white-space:pre-wrap">{escape(cap)}</p></details>')


def _topic_html(i: int, t: dict) -> str:
    e = lambda k: escape(str(t.get(k, "") or ""))  # noqa: E731
    checks = "".join(
        f'<li><label><input type="checkbox" data-save="chk-{i}-{j}"> {escape(str(c))}</label></li>'
        for j, c in enumerate(_list(t.get("dogrulanacaklar")))
    ) or "<li><small>Belirtilmedi</small></li>"
    visuals = "".join(f"<li>{escape(str(v))}</li>" for v in _list(t.get("gorsel_onerileri"))) or "<li>—</li>"
    sources = "".join(
        f'<li><a href="{escape(s["url"])}" target="_blank" rel="noopener">{escape(s["baslik"])}</a> '
        f'<small>· {escape(s["kaynak"])}</small>'
        + (f' · <a href="{escape(s["tartisma"])}" target="_blank" rel="noopener"><small>tartışma</small></a>'
           if s.get("tartisma") and s["tartisma"] != s["url"] else "")
        + "</li>"
        for s in t.get("kaynaklar", [])
    ) or "<li>—</li>"
    tags = " ".join(_list(t.get("hashtagler")))
    caption_text = (t.get("paylasim_aciklamasi", "") + ("\n\n" + tags if tags else "")).strip()
    subs = t.get("altyazi_satirlari", [])

    return f"""
<article class="topic" id="konu-{i}">
  <div class="slug">
    <span class="num">{i:02d}</span>
    <h2>{e('baslik')}</h2>
    <span class="pill">{e('kategori')}</span>
    {_duration_pill(t.get('tahmini_sure_sn', 0))}
    <label class="status"><input type="checkbox" data-save="done-{i}"> Çekildi</label>
  </div>
  <div class="body">
    <div class="col">
      <div class="sec"><h3>Ne oldu?</h3><p>{e('ne_oldu')}</p></div>
      <div class="sec"><h3>Neden önemli?</h3><p>{e('neden_onemli')}</p></div>
      <div class="sec"><h3>Hook · ilk 2 saniye <button class="copy" data-target="hook-{i}">Kopyala</button></h3>
        <p class="hook" id="hook-{i}">{e('hook')}</p></div>
      <div class="sec"><h3>Senaryo · {t.get('kelime_sayisi', 0)} kelime <button class="copy" data-target="scr-{i}">Kopyala</button></h3>
        <div class="script" id="scr-{i}">{e('senaryo')}</div></div>
      <div class="note"><label for="note-{i}">[SENİN NOTUN / ÖRNEĞİN]</label>
        <textarea id="note-{i}" data-save="note-{i}" placeholder="Kendi yorumun, denediğin örnek, ekran kaydı fikri..."></textarea></div>
      <div class="sec"><h3>Yayından önce doğrula</h3><ul class="checks">{checks}</ul></div>
      <div class="sec"><h3>Görsel / kurgu önerileri</h3><ul class="plain">{visuals}</ul></div>
      <div class="sec"><h3>Paylaşım açıklaması <button class="copy" data-target="cap-{i}">Kopyala</button></h3>
        <p id="cap-{i}" style="white-space:pre-wrap">{escape(caption_text)}</p></div>
      {_english_html(i, t.get("en"))}
      <div class="sec src"><h3>Kaynaklar</h3><ul class="plain">{sources}</ul></div>
    </div>
    <div class="col">
      <div class="sec"><h3>Ekran önizleme</h3>
        <div class="phone" aria-label="9:16 ekran yazısı önizlemesi">
          <span class="ttl">{e('ekran_basligi')}</span>
          <span class="sub">{e('ekran_alt_metin')}</span>
          <span class="cap">{escape(subs[0]) if subs else ''}</span>
          <span class="hint">9:16 · taslak</span>
        </div></div>
      <div class="sec"><h3>Altyazı satırları <button class="copy" data-target="sub-{i}">Kopyala</button></h3>
        <pre class="subs" id="sub-{i}">{escape(chr(10).join(subs))}</pre></div>
    </div>
  </div>
</article>"""


def write_html(path: Path, topics: list[dict], candidates: list[Item], stats: dict,
               banner: str = "") -> None:
    now = datetime.now()
    nav = "".join(
        f'<a href="#konu-{i}" data-i="{i}"><span class="n">{i:02d}</span>'
        f'<span class="t">{escape(str(t.get("baslik", "")))}</span>'
        f'<span class="d">{t.get("tahmini_sure_sn", 0)}s</span></a>'
        for i, t in enumerate(topics, 1)
    )
    articles = "".join(_topic_html(i, t) for i, t in enumerate(topics, 1))

    used = {x for t in topics for x in t.get("aday_idleri", [])}
    backups = [c for c in candidates if c.id not in used][:12]
    rows = "".join(
        f'<tr><td><a href="{escape(c.url)}" target="_blank" rel="noopener">{escape(c.title)}</a></td>'
        f'<td>{escape(", ".join(c.all_sources()))}</td><td class="num">{c.score}</td></tr>'
        for c in backups
    )
    backup_html = (f'<section class="backup"><h2>Yedek adaylar</h2><div class="tbl"><table>'
                   f'<thead><tr><th>Haber</th><th>Kaynak</th><th>Puan</th></tr></thead>'
                   f'<tbody>{rows}</tbody></table></div></section>') if rows else ""
    banner_html = f'<div class="banner">{escape(banner)}</div>' if banner else ""
    key = f"aitrend-{path.stem}"

    page = f"""<!DOCTYPE html>
<html lang="tr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>AI Trendleri {escape(_tr_date(now))}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@600;700;800&family=IBM+Plex+Mono:wght@400;600&family=IBM+Plex+Sans:wght@400;600&display=swap" rel="stylesheet">
<style>{CSS}</style></head>
<body data-key="{escape(key)}">
<div class="wrap">
  <header class="top">
    <h1><span class="rec"></span>AI Trendleri · {escape(_tr_date(now))}</h1>
    <div class="stats"><span>Taranan <b>{stats.get('toplam', 0)}</b></span>
      <span>Yeni <b>{stats.get('yeni', 0)}</b></span><span>Aday <b>{len(candidates)}</b></span>
      <span>Model <b>{escape(str(stats.get('model', '-')))}</b></span><span>{now:%H:%M}</span></div>
  </header>
  {banner_html}
  <nav class="rundown" aria-label="Konu akışı"><span class="lbl">Akış · {len(topics)} konu</span>{nav}</nav>
  <main>{articles}{backup_html}</main>
</div>
<script>{JS}</script>
</body></html>"""
    path.write_text(page, encoding="utf-8")
