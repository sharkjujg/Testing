from __future__ import annotations

from .config import CaptionCfg, StreamerCfg
from .models import Clip

MAX_LEN = 2200  # TikTok and Instagram caption limit


def build_caption(clip: Clip, streamer: StreamerCfg, cfg: CaptionCfg) -> str:
    seen: set[str] = set()
    tags: list[str] = []
    for t in [*streamer.hashtags, streamer.name, *cfg.hashtags]:
        t = t.lstrip("#").strip().lower()
        if t and t not in seen:
            seen.add(t)
            tags.append(f"#{t}")
    text = cfg.template.format(
        title=clip.title.strip(),
        streamer=streamer.name,
        creator=clip.creator_name,
        hashtags=" ".join(tags),
    )
    return text if len(text) <= MAX_LEN else text[: MAX_LEN - 1] + "…"
