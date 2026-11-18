from __future__ import annotations

import re
from pathlib import Path

from ..config import ProcessingCfg, SubtitlesCfg
from .transcribe import Word

MAX_GAP = 0.8  # seconds of silence that forces a new caption line


def chunk_words(words: list[Word], max_words: int, max_chars: int) -> list[list[Word]]:
    """Group words into short on-screen caption lines."""
    chunks: list[list[Word]] = []
    cur: list[Word] = []
    for w in words:
        if cur:
            too_long = len(" ".join(x.text for x in cur + [w])) > max_chars
            gap = w.start - cur[-1].end
            if len(cur) >= max_words or too_long or gap > MAX_GAP:
                chunks.append(cur)
                cur = []
        cur.append(w)
    if cur:
        chunks.append(cur)
    return chunks


def _ass_time(t: float) -> str:
    cs = round(max(t, 0) * 100)
    h, rem = divmod(cs, 360000)
    m, rem = divmod(rem, 6000)
    s, cs = divmod(rem, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _ass_color(hex_rgb: str) -> str:
    """'#RRGGBB' -> ASS '&H00BBGGRR'."""
    h = hex_rgb.lstrip("#")
    if not re.fullmatch(r"[0-9a-fA-F]{6}", h):
        raise ValueError(f"bad colour {hex_rgb!r}, expected #RRGGBB")
    return f"&H00{h[4:6]}{h[2:4]}{h[0:2]}".upper()


def _escape(text: str) -> str:
    return text.replace("\\", "").replace("{", "(").replace("}", ")").replace("\n", " ")


def build_ass(words: list[Word], sub: SubtitlesCfg, proc: ProcessingCfg) -> str:
    """ASS document with one karaoke line per chunk: the spoken word lights up."""
    style = (
        f"Style: Default,{sub.font},{sub.font_size},"
        f"{_ass_color(sub.highlight_color)},{_ass_color(sub.text_color)},"  # primary=highlighted, secondary=not yet spoken
        f"&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,{sub.outline},2,2,60,60,{sub.margin_bottom},1"
    )
    lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        f"PlayResX: {proc.width}",
        f"PlayResY: {proc.height}",
        "WrapStyle: 2",
        "",
        "[V4+ Styles]",
        "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,"
        "Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,"
        "Alignment,MarginL,MarginR,MarginV,Encoding",
        style,
        "",
        "[Events]",
        "Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text",
    ]
    for chunk in chunk_words(words, sub.max_words, sub.max_chars):
        parts = []
        for i, w in enumerate(chunk):
            nxt = chunk[i + 1].start if i + 1 < len(chunk) else w.end
            cs = max(round((nxt - w.start) * 100), 1)
            text = _escape(w.text.upper() if sub.uppercase else w.text)
            parts.append(f"{{\\kf{cs}}}{text}")
        start, end = chunk[0].start, max(chunk[-1].end, chunk[0].start + 0.2)
        lines.append(f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},Default,,0,0,0,,{' '.join(parts)}")
    return "\n".join(lines) + "\n"


def write_ass(words: list[Word], dest: Path, sub: SubtitlesCfg, proc: ProcessingCfg) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(build_ass(words, sub, proc), encoding="utf-8")
    return dest
