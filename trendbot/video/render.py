"""9:16 (1080x1920) hareketli video çizimi.

Her kare Pillow ile çizilip doğrudan ffmpeg'e akıtılır (geçici görüntü dosyası yok).
İzleyiciyi ekranda tutan öğeler:
  - Sürekli kayan, renkli arka plan + yukarı süzülen parçacıklar
  - Sahne başına büyük "bant" başlık: zıplayarak girer, hafifçe nefes alır, kayarak çıkar
  - Sahne tipine özel süsler: dönen ışın patlaması (rakam), dev soru işareti (soru),
    nabız gibi atan "TAKİP ET" (kapanış), ilk saniyede flaş + sarsıntı (hook)
  - Kelime kelime yanan karaoke altyazı
  - Üstte ilerleme çubuğu (izleyici videonun ne kadar kaldığını görür)
"""
from __future__ import annotations

import math
import random
import subprocess
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Callable

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from ..config import ROOT
from .ffmpeg import ffmpeg_exe

W, H, FPS = 1080, 1920, 30
FONT_DIR = ROOT / "assets" / "fonts"
ACCENTS = [(255, 77, 61), (255, 214, 10), (61, 220, 255), (150, 128, 255), (61, 255, 154)]
HILITE = (255, 214, 10)
BG_TOP, BG_BOT = (9, 11, 24), (40, 14, 58)
INK = (14, 14, 20)

HEADLINE_Y = 760      # Başlık bandının merkezi
SUBTITLE_Y = 1290     # Altyazının üst kenarı (platform arayüzünün altta kapladığı alanın üstünde)


# ---------------- Veri ----------------
@dataclass
class Scene:
    tip: str                     # hook | bilgi | rakam | soru | kapanis
    ekran: str                   # Ekrandaki büyük yazı
    start: float
    end: float
    words: list[tuple[str, float, float]] = field(default_factory=list)  # mutlak zamanlar
    accent: tuple = ACCENTS[0]


@dataclass
class Timeline:
    scenes: list[Scene]
    total: float


# ---------------- Yardımcılar ----------------
def tr_upper(s: str) -> str:
    """Türkçe büyük harf: i -> İ, ı -> I."""
    return s.replace("i", "İ").replace("ı", "I").upper()


def upper(s: str, lang: str = "tr") -> str:
    """Dile göre büyük harf (İngilizcede 'i' -> 'I')."""
    return tr_upper(s) if lang == "tr" else s.upper()


LABELS = {"tr": {"follow": "TAKİP ET"}, "en": {"follow": "FOLLOW"}}


def ease_out_back(x: float) -> float:
    x = min(max(x, 0.0), 1.0)
    c1, c3 = 1.70158, 2.70158
    return 1 + c3 * (x - 1) ** 3 + c1 * (x - 1) ** 2


def ease_out_cubic(x: float) -> float:
    x = min(max(x, 0.0), 1.0)
    return 1 - (1 - x) ** 3


def _first_font(candidates: list[str]) -> str | None:
    for c in candidates:
        try:
            ImageFont.truetype(c, 10)
            return c
        except OSError:
            continue
    return None


_FALLBACK_BOLD = ["arialbd.ttf", "Arial Bold.ttf", "DejaVuSans-Bold.ttf",
                  "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]


@lru_cache(maxsize=64)
def font_display(size: int) -> ImageFont.FreeTypeFont:
    path = _first_font([str(FONT_DIR / "Anton-Regular.ttf")] + _FALLBACK_BOLD)
    return ImageFont.truetype(path, size) if path else ImageFont.load_default(size)


@lru_cache(maxsize=64)
def font_body(size: int, weight: str = "ExtraBold") -> ImageFont.FreeTypeFont:
    var = FONT_DIR / "Montserrat-Variable.ttf"
    if var.exists():
        f = ImageFont.truetype(str(var), size)
        try:
            f.set_variation_by_name(weight)
        except Exception:  # noqa: BLE001
            pass
        return f
    path = _first_font(_FALLBACK_BOLD)
    return ImageFont.truetype(path, size) if path else ImageFont.load_default(size)


def text_w(font, s: str) -> int:
    b = font.getbbox(s)
    return b[2] - b[0]


def wrap(font, text: str, max_w: int) -> list[str]:
    lines, cur = [], ""
    for word in text.split():
        trial = f"{cur} {word}".strip()
        if text_w(font, trial) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


# ---------------- Statik katmanlar (bir kez hazırlanır) ----------------
def build_background(seed: int) -> np.ndarray:
    """Ekrandan büyük bir arka plan: dikey degrade + bulanık renk lekeleri + ince ızgara."""
    rng = random.Random(seed)
    bw, bh = int(W * 1.3), int(H * 1.3)
    y = np.linspace(0, 1, bh, dtype=np.float32)[:, None]
    col = np.array(BG_TOP, np.float32) * (1 - y) + np.array(BG_BOT, np.float32) * y
    base = Image.fromarray(np.broadcast_to(col[:, None, :], (bh, bw, 3)).astype(np.uint8))

    blobs = Image.new("RGBA", (bw // 4, bh // 4), (0, 0, 0, 0))  # Küçük çiz, büyüt (hızlı bulanıklık)
    d = ImageDraw.Draw(blobs)
    for i in range(6):
        cx, cy = rng.randint(0, bw // 4), rng.randint(0, bh // 4)
        r = rng.randint(60, 130)
        c = ACCENTS[i % len(ACCENTS)]
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=c + (70,))
    blobs = blobs.filter(ImageFilter.GaussianBlur(40)).resize((bw, bh), Image.BICUBIC)
    base = Image.alpha_composite(base.convert("RGBA"), blobs)

    grid = Image.new("RGBA", (bw, bh), (0, 0, 0, 0))
    g = ImageDraw.Draw(grid)
    for x in range(0, bw, 90):
        g.line([(x, 0), (x, bh)], fill=(255, 255, 255, 9), width=1)
    for yy in range(0, bh, 90):
        g.line([(0, yy), (bw, yy)], fill=(255, 255, 255, 9), width=1)
    return np.asarray(Image.alpha_composite(base, grid).convert("RGB"))


def headline_layer(text: str, accent: tuple, lang: str = "tr") -> Image.Image:
    """Poster tarzı 'bant' başlık. Son satır vurgu renginde."""
    text = upper(text.strip(), lang) or " "
    max_w = 900
    size, lines = 80, [text]
    for s in range(176, 79, -6):
        f = font_display(s)
        ls = wrap(f, text, max_w)
        if len(ls) <= 3 and all(text_w(f, line) <= max_w for line in ls):
            size, lines = s, ls
            break
    f = font_display(size)
    pad_x, pad_y = 28, int(size * 0.12)
    line_h = int(size * 1.18)
    width = max(text_w(f, line) for line in lines) + pad_x * 2 + 40
    height = line_h * len(lines) + pad_y * 2 + 40
    layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for i, line in enumerate(lines):
        tw = text_w(f, line)
        x = (width - tw) // 2
        y = 20 + i * line_h
        tape = accent if i == len(lines) - 1 else (255, 255, 255)
        # Gölge + bant
        d.rectangle([x - pad_x + 10, y + 10, x + tw + pad_x + 10, y + line_h - 6 + 10], fill=(0, 0, 0, 110))
        d.rectangle([x - pad_x, y, x + tw + pad_x, y + line_h - 6], fill=tape + (255,))
        top_off = f.getbbox(line)[1]
        d.text((x, y + (line_h - 6 - size) // 2 - top_off + int(size * 0.08)), line, font=f, fill=INK)
    return layer.rotate(2.2, resample=Image.BICUBIC, expand=True)


def burst_layer(accent: tuple, size: int = 1500) -> Image.Image:
    layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    c = size / 2
    for k in range(18):
        a0 = k * 2 * math.pi / 18
        a1 = a0 + math.pi / 18
        d.polygon([(c, c), (c + c * math.cos(a0), c + c * math.sin(a0)),
                   (c + c * math.cos(a1), c + c * math.sin(a1))], fill=accent + (38,))
    return layer


def question_layer(accent: tuple) -> Image.Image:
    f = font_display(900)
    layer = Image.new("RGBA", (700, 1100), (0, 0, 0, 0))
    ImageDraw.Draw(layer).text((90, -40), "?", font=f, fill=accent + (60,),
                               stroke_width=10, stroke_fill=accent + (140,))
    return layer


# ---------------- Altyazı ----------------
@dataclass
class Chunk:
    words: list[tuple[str, float, float]]
    start: float
    end: float


def build_chunks(scenes: list[Scene], max_words: int = 3, max_chars: int = 22) -> list[Chunk]:
    chunks: list[Chunk] = []
    for s in scenes:
        cur: list = []
        for w in s.words:
            text_len = sum(len(x[0]) + 1 for x in cur) + len(w[0])
            if cur and (len(cur) >= max_words or text_len > max_chars):
                chunks.append(Chunk(cur, cur[0][1], w[1]))
                cur = []
            cur.append(w)
            if w[0][-1:] in ".!?…":
                chunks.append(Chunk(cur, cur[0][1], w[2] + 0.15))
                cur = []
        if cur:
            chunks.append(Chunk(cur, cur[0][1], cur[-1][2] + 0.25))
    return chunks


def draw_subtitle(img: Image.Image, chunk: Chunk, t: float) -> None:
    f = font_body(82)
    space = text_w(f, " ")
    widths = [text_w(f, w[0]) for w in chunk.words]
    # Satırlara böl (en fazla 2)
    rows, cur, cur_w = [], [], 0
    for i, wd in enumerate(widths):
        if cur and cur_w + space + wd > 880:
            rows.append(cur)
            cur, cur_w = [], 0
        cur.append(i)
        cur_w += wd + (space if len(cur) > 1 else 0)
    rows.append(cur)
    appear = ease_out_cubic((t - chunk.start) / 0.12)
    y = SUBTITLE_Y + int((1 - appear) * 30)
    d = ImageDraw.Draw(img)
    for row in rows:
        row_w = sum(widths[i] for i in row) + space * (len(row) - 1)
        x = (W - row_w) // 2
        for i in row:
            word, ws, we = chunk.words[i]
            active = ws <= t < (chunk.words[i + 1][1] if i + 1 < len(chunk.words) else chunk.end)
            bounce = -int(10 * max(0.0, 1 - (t - ws) / 0.12)) if active else 0
            d.text((x, y + bounce), word, font=f, fill=HILITE if active else (255, 255, 255),
                   stroke_width=8, stroke_fill=(0, 0, 0))
            x += widths[i] + space
        y += 104


# ---------------- Kare çizimi ----------------
class Renderer:
    def __init__(self, tl: Timeline, meta: dict, seed: int = 7):
        self.tl, self.meta = tl, meta
        self.bg = build_background(seed)
        self.bh, self.bw = self.bg.shape[:2]
        self.lang = meta.get("dil", "tr")
        self.heads = [headline_layer(s.ekran, s.accent, self.lang) for s in tl.scenes]
        self.head_bottom = [HEADLINE_Y + h.height // 2 for h in self.heads]  # Alt öğeler buna göre yerleşir
        self.bursts = {i: burst_layer(s.accent) for i, s in enumerate(tl.scenes) if s.tip == "rakam"}
        self.questions = {i: question_layer(s.accent) for i, s in enumerate(tl.scenes) if s.tip == "soru"}
        self.chunks = build_chunks(tl.scenes)
        rng = random.Random(seed)
        self.particles = [(rng.uniform(0, W), rng.uniform(0, H), rng.uniform(20, 70), rng.randint(2, 5))
                          for _ in range(45)]
        self.handle = (meta.get("kanal_adi") or "").strip() or "sinyal"
        from ..brand import draw_icon
        self.logo = draw_icon(46)  # Köşedeki marka simgesi
        self.category = upper(meta.get("kategori") or "", self.lang)
        self.source = meta.get("kaynak_notu") or ""

    def scene_at(self, t: float) -> int:
        idx = 0
        for i, s in enumerate(self.tl.scenes):
            if t >= s.start:
                idx = i
        return idx

    def frame(self, t: float) -> Image.Image:
        tl = self.tl
        si = self.scene_at(t)
        sc = tl.scenes[si]
        lt = t - sc.start

        # 1) Kayan arka plan
        ox = int((self.bw - W) / 2 * (1 + 0.9 * math.sin(t * 0.32)))
        oy = int((self.bh - H) / 2 * (1 + 0.9 * math.cos(t * 0.21)))
        img = Image.fromarray(self.bg[oy:oy + H, ox:ox + W])
        d = ImageDraw.Draw(img)

        # 2) Süzülen parçacıklar
        for x, y0, sp, r in self.particles:
            y = (y0 - sp * t) % H
            xx = x + 12 * math.sin(t + y0)
            d.ellipse([xx - r, y - r, xx + r, y + r], fill=(110, 110, 170))

        # 3) Sahne süsleri (başlığın arkasında)
        if si in self.bursts:
            b = self.bursts[si].rotate(lt * 25, resample=Image.BILINEAR)
            img.paste(b, (W // 2 - b.width // 2, HEADLINE_Y - b.height // 2), b)
        if si in self.questions:
            q = self.questions[si].rotate(8 * math.sin(lt * 2.4), resample=Image.BILINEAR, expand=False)
            img.paste(q, (W - q.width + 120, HEADLINE_Y - q.height // 2 - 60), q)

        # 4) Başlık bandı: giriş animasyonu + nefes + çıkış
        head = self.heads[si]
        if sc.tip == "hook":
            scale = 1.45 - 0.45 * ease_out_cubic(lt / 0.3)
        else:
            scale = 0.55 + 0.45 * ease_out_back(lt / 0.38)
        scale *= 1 + 0.018 * math.sin(lt * 3.1) + 0.025 * min(1.0, lt / max(0.5, sc.end - sc.start))
        alpha = min(1.0, lt / 0.12)
        dx = 0.0
        dy = 8 * math.sin(lt * 2.0)
        is_last = si == len(tl.scenes) - 1
        out_left = sc.end - t
        if not is_last and out_left < 0.14:
            k = 1 - out_left / 0.14
            dx -= 380 * k * k
            alpha *= 1 - k
        if sc.tip == "hook" and lt < 0.45:  # sarsıntı
            amp = 16 * (1 - lt / 0.45)
            dx += random.uniform(-amp, amp)
            dy += random.uniform(-amp, amp)
        hw, hh = max(1, int(head.width * scale)), max(1, int(head.height * scale))
        lay = head.resize((hw, hh), Image.BILINEAR)
        if alpha < 0.999:
            lay.putalpha(lay.getchannel("A").point(lambda v, a=alpha: int(v * a)))
        img.paste(lay, (int(W / 2 - hw / 2 + dx), int(HEADLINE_Y - hh / 2 + dy)), lay)

        # 5) Sahneye özel ön öğeler
        if sc.tip == "bilgi":
            info = [i for i, s in enumerate(tl.scenes) if s.tip == "bilgi"]
            n, cur = len(info), info.index(si)
            total_w = n * 34 - 12
            x0 = (W - total_w) // 2
            for k in range(n):
                fill = sc.accent if k == cur else (255, 255, 255)
                r = 11 if k == cur else 7
                cx = x0 + k * 34 + 11
                yy = self.head_bottom[si] + 40
                d.ellipse([cx - r, yy - r, cx + r, yy + r], fill=fill)
        if sc.tip == "kapanis":
            pulse = 1 + 0.07 * math.sin(lt * 7)
            f = font_body(int(58 * pulse))
            label = LABELS.get(self.lang, LABELS["tr"])["follow"]
            tw = text_w(f, label)
            bw_, bh_ = tw + 90, int(110 * pulse)
            x0, y0 = (W - bw_) // 2, min(SUBTITLE_Y - 90, self.head_bottom[si] + 90) - bh_ // 2
            d.rounded_rectangle([x0, y0, x0 + bw_, y0 + bh_], radius=bh_ // 2, fill=sc.accent)
            top = f.getbbox(label)[1]
            d.text((x0 + 45, y0 + (bh_ - (f.getbbox(label)[3] - top)) // 2 - top), label, font=f, fill=INK)

        # 6) Karaoke altyazı
        for ch in self.chunks:
            if ch.start <= t < ch.end:
                draw_subtitle(img, ch, t)
                break

        # 7) Üst bilgi: ilerleme çubuğu, kanal adı, kategori
        d.rectangle([0, 0, W, 12], fill=(40, 40, 60))
        d.rectangle([0, 0, int(W * min(1.0, t / tl.total)), 12], fill=sc.accent)
        small = font_body(34, "Bold")
        tw = text_w(small, self.handle)
        d.rounded_rectangle([56, 66, 56 + tw + 104, 132], radius=33, fill=(0, 0, 0))
        img.paste(self.logo, (72, 76), self.logo)
        d.text((134, 99), self.handle, font=small, fill=(255, 255, 255), anchor="lm")
        if self.category:
            tw = text_w(small, self.category)
            x1 = W - 56
            d.rounded_rectangle([x1 - tw - 70, 70, x1, 128], radius=29, fill=sc.accent)
            blink = (255, 255, 255) if int(t * 2) % 2 == 0 else sc.accent
            d.ellipse([x1 - tw - 52, 90, x1 - tw - 34, 108], fill=blink)
            d.text((x1 - tw - 24, 99), self.category, font=small, fill=INK, anchor="lm")
        if self.source:
            sf = font_body(28, "Medium")
            src = self.source if text_w(sf, self.source) < 960 else self.source[:60] + "…"
            d.text((W // 2, H - 120), src, font=sf, fill=(175, 175, 200), anchor="mm")

        # 8) Sahne geçişlerinde flaş (hook'ta güçlü)
        flash = 0.0
        if sc.tip == "hook" and lt < 0.22:
            flash = 0.85 * (1 - lt / 0.22)
        elif si > 0 and lt < 0.08:
            flash = 0.25 * (1 - lt / 0.08)
        if flash > 0:
            arr = np.asarray(img, dtype=np.float32)
            img = Image.fromarray((arr * (1 - flash) + 255 * flash).astype(np.uint8))
        return img


def render(tl: Timeline, meta: dict, audio_wav: Path, out_mp4: Path,
           log: Callable[[str], None] = print, preset: str = "veryfast") -> Path:
    r = Renderer(tl, meta)
    n = int(math.ceil(tl.total * FPS))
    cmd = [ffmpeg_exe(), "-y", "-loglevel", "error",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
           "-i", str(audio_wav),
           "-c:v", "libx264", "-preset", preset, "-crf", "21", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", str(out_mp4)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    try:
        for i in range(n):
            proc.stdin.write(r.frame(i / FPS).tobytes())
            if i and i % (FPS * 10) == 0:
                log(f"    video: {i // FPS}/{int(tl.total)} sn")
    finally:
        proc.stdin.close()
        proc.wait()
    if proc.returncode != 0:
        raise RuntimeError("ffmpeg video kodlaması başarısız oldu")
    return out_mp4
