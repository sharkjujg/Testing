from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from ..models import Clip


def download_clip(clip: Clip, dest_dir: Path) -> Path:
    """Download a Twitch clip with yt-dlp; returns the mp4 path."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    out = dest_dir / f"{clip.id}.mp4"
    if out.exists() and out.stat().st_size > 0:
        return out
    cmd = [
        sys.executable, "-m", "yt_dlp",
        "--quiet", "--no-warnings", "--no-playlist",
        "-f", "best[ext=mp4]/best",
        "--merge-output-format", "mp4",
        "-o", str(out),
        clip.url,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0 or not out.exists():
        raise RuntimeError(f"yt-dlp failed for {clip.url}: {proc.stderr.strip()[-500:]}")
    return out
