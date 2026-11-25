"""ffmpeg yolunu bulur. Sistemde yoksa `imageio-ffmpeg` paketinin içindekini kullanır
(Windows'ta ayrıca ffmpeg kurmaya gerek kalmaz)."""
from __future__ import annotations

import shutil
import subprocess
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def ffmpeg_exe() -> str:
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError as e:  # pragma: no cover
        raise RuntimeError("ffmpeg bulunamadı. `pip install imageio-ffmpeg` çalıştır.") from e


def to_wav(src: Path, dst: Path, sr: int = 44100) -> Path:
    """Herhangi bir ses dosyasını mono WAV'a çevirir."""
    subprocess.run([ffmpeg_exe(), "-y", "-loglevel", "error", "-i", str(src),
                    "-ac", "1", "-ar", str(sr), "-c:a", "pcm_s16le", str(dst)], check=True)
    return dst
