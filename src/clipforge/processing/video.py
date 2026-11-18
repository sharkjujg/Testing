from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from ..config import ProcessingCfg


def build_filter(cfg: ProcessingCfg) -> str:
    """ffmpeg filter graph producing a [v] stream sized width x height."""
    w, h = cfg.width, cfg.height
    if cfg.layout == "crop":
        return f"[0:v]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1[v]"
    # blur: sharp 16:9 clip centred over a blurred, zoomed copy of itself
    return (
        f"[0:v]split=2[bg][fg];"
        f"[bg]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},boxblur=40:5[bgb];"
        f"[fg]scale={w}:-2[fgs];"
        f"[bgb][fgs]overlay=(W-w)/2:(H-h)/2,setsar=1[v]"
    )


def render_vertical(src: Path, dst: Path, cfg: ProcessingCfg, max_seconds: float = 60) -> Path:
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg not found on PATH")
    dst.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", str(src),
        "-filter_complex", build_filter(cfg),
        "-map", "[v]", "-map", "0:a?",
        "-t", str(max_seconds),
        "-c:v", "libx264", "-preset", cfg.preset, "-crf", str(cfg.crf), "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart",
        str(dst),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {proc.stderr.strip()[-500:]}")
    return dst
