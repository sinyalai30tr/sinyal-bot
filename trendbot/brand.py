"""Sinyal marka görselleri: simge, profil fotoğrafı, YouTube kapağı.

Logo kodla çizilir (yayın dalgası: bir noktadan yayılan üç renkli yay).
Çalıştır:  python -m trendbot.brand   ->  assets/logo/ altına PNG'leri yazar.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .config import ROOT

LOGO_DIR = ROOT / "assets" / "logo"
FONT_DIR = ROOT / "assets" / "fonts"

NIGHT = (18, 13, 34)
WHITE = (243, 240, 250)
DARK_ARCS = [(255, 77, 61), (255, 214, 10), (61, 220, 255)]   # Koyu zemin: kırmızı, sarı, camgöbeği
LIGHT_ARCS = [(232, 56, 42), (242, 154, 0), (10, 156, 196)]   # Açık zemin: bir ton koyu


def draw_icon(size: int, arcs=DARK_ARCS, dot=WHITE, bg=None, pad: float = 0.0) -> Image.Image:
    """Simgeyi `size` piksel kare olarak çizer (4x büyük çizip küçültür = pürüzsüz kenarlar).
    Geometri logodaki SVG ile aynı: 120 birimlik alanda merkez (28,92), yarıçaplar 82/58/34."""
    ss = 4
    S = size * ss
    img = Image.new("RGBA", (S, S), bg + (255,) if bg else (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    inner = S * (1 - 2 * pad)
    k = inner / 120.0
    ox = oy = S * pad
    cx, cy = ox + 28 * k, oy + 92 * k
    width = 12 * k
    for r, color in zip((82, 58, 34), arcs):
        rr = r * k
        box = [cx - rr - width / 2, cy - rr - width / 2, cx + rr + width / 2, cy + rr + width / 2]
        d.arc(box, start=270, end=360, fill=color, width=int(width))
        for px, py in ((cx, cy - rr), (cx + rr, cy)):  # Yuvarlak uçlar
            d.ellipse([px - width / 2, py - width / 2, px + width / 2, py + width / 2], fill=color)
    dr = 11 * k
    d.ellipse([cx - dr, cy - dr, cx + dr, cy + dr], fill=dot)
    return img.resize((size, size), Image.LANCZOS)


def _font(size: int, weight: int, name: str = "Unbounded-Variable.ttf") -> ImageFont.FreeTypeFont:
    f = ImageFont.truetype(str(FONT_DIR / name), size)
    try:
        f.set_variation_by_axes([weight])
    except Exception:  # noqa: BLE001
        pass
    return f


def profile_picture(size: int = 1080) -> Image.Image:
    """Instagram / YouTube profil fotoğrafı. Platformlar daire kırptığı için simge ortada ve küçük."""
    img = Image.new("RGB", (size, size), NIGHT)
    icon = draw_icon(int(size * 0.62))
    off = (size - icon.width) // 2
    img.paste(icon, (off - int(size * 0.02), off + int(size * 0.01)), icon)
    return img


def youtube_banner() -> Image.Image:
    """2560x1440 kanal kapağı. Her cihazda görünen güvenli alan ortadaki 1546x423."""
    W, H = 2560, 1440
    img = Image.new("RGB", (W, H), NIGHT)
    d = ImageDraw.Draw(img)
    # Arka planda çok soluk büyük dalgalar (dekor)
    big = draw_icon(1500, arcs=[(40, 28, 70), (34, 25, 60), (29, 22, 52)], dot=(29, 22, 52))
    img.paste(big, (W - 1250, -160), big)
    # Güvenli alan içinde logo + slogan
    icon = draw_icon(300)
    word = _font(210, 700)
    tag = _font(58, 500, "Montserrat-Variable.ttf")
    text = "sinyal"
    tw = d.textbbox((0, 0), text, font=word)
    w_word = tw[2] - tw[0]
    total = 300 + 50 + w_word
    x0 = (W - total) // 2
    yc = H // 2 - 30
    img.paste(icon, (x0, yc - 170), icon)
    d.text((x0 + 350, yc - 40), text, font=word, fill=WHITE, anchor="ls")
    d.text((x0 + 356, yc + 60), "Yapay zekâ gündemi, 30 saniyede", font=tag, fill=(201, 194, 221), anchor="ls")
    return img


def build_all() -> list[Path]:
    LOGO_DIR.mkdir(parents=True, exist_ok=True)
    out = []
    p = LOGO_DIR / "sinyal-profil-1080.png"
    profile_picture().save(p, optimize=True)
    out.append(p)
    p = LOGO_DIR / "sinyal-youtube-kapak-2560x1440.png"
    youtube_banner().save(p, optimize=True)
    out.append(p)
    p = LOGO_DIR / "sinyal-simge-512.png"          # Şeffaf zeminli simge (koyu zemin için)
    draw_icon(512).save(p, optimize=True)
    out.append(p)
    p = LOGO_DIR / "sinyal-simge-acik-zemin-512.png"
    draw_icon(512, arcs=LIGHT_ARCS, dot=NIGHT).save(p, optimize=True)
    out.append(p)
    return out


if __name__ == "__main__":
    for path in build_all():
        print("yazıldı:", path)
