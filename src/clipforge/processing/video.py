from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from ..config import ProcessingCfg


SUBS_NAME = "subs.ass"


def build_filter(cfg: ProcessingCfg, subtitles: Path | None = None) -> str:
    """ffmpeg filter graph producing a [v] stream sized width x height.

    If `subtitles` is given it is burned in last, by bare filename: the caller must
    run ffmpeg in the directory holding it (see render_vertical), which avoids
    ffmpeg's fragile filter-path escaping.
    """
    w, h = cfg.width, cfg.height
    burn = f",ass={SUBS_NAME}" if subtitles else ""
    if cfg.layout == "crop":
        return f"[0:v]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1{burn}[v]"
    # blur: sharp 16:9 clip centred over a blurred, zoomed copy of itself
    return (
        f"[0:v]split=2[bg][fg];"
        f"[bg]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},boxblur=40:5[bgb];"
        f"[fg]scale={w}:-2[fgs];"
        f"[bgb][fgs]overlay=(W-w)/2:(H-h)/2,setsar=1{burn}[v]"
    )


def render_vertical(src: Path, dst: Path, cfg: ProcessingCfg, max_seconds: float = 60,
                    subtitles: Path | None = None) -> Path:
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg not found on PATH")
    dst.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="clipforge-") as tmp:
        if subtitles:
            shutil.copyfile(subtitles, Path(tmp) / SUBS_NAME)
        return _run_ffmpeg(src.resolve(), dst.resolve(), cfg, max_seconds, subtitles, Path(tmp))


def _run_ffmpeg(src: Path, dst: Path, cfg: ProcessingCfg, max_seconds: float,
                subtitles: Path | None, workdir: Path) -> Path:
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", str(src),
        "-filter_complex", build_filter(cfg, subtitles),
        "-map", "[v]", "-map", "0:a?",
        "-t", str(max_seconds),
        "-c:v", "libx264", "-preset", cfg.preset, "-crf", str(cfg.crf), "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart",
        str(dst),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=workdir)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {proc.stderr.strip()[-500:]}")
    return dst
