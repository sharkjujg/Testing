from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Protocol

from .caption import build_caption
from .config import Config
from .db import Database
from .models import Clip
from .processing.subtitles import write_ass
from .processing.transcribe import Transcriber
from .processing.video import render_vertical
from .publishers.base import Publisher

log = logging.getLogger("clipforge")


class ClipSource(Protocol):
    def fetch_clips(self, login: str, lookback_hours: int, limit: int = 50) -> list[Clip]: ...


@dataclass
class RunSummary:
    discovered: int = 0
    processed: int = 0
    posted: list[tuple[str, str]] = field(default_factory=list)   # (clip_id, platform)
    failed: list[tuple[str, str, str]] = field(default_factory=list)  # (clip_id, platform, error)


def discover(cfg: Config, source: ClipSource, now: datetime | None = None) -> list[Clip]:
    """Top clips across all configured streamers, filtered and ranked."""
    now = now or datetime.now(timezone.utc)
    d = cfg.discovery
    found: list[Clip] = []
    for s in cfg.streamers:
        try:
            clips = source.fetch_clips(s.name, d.lookback_hours)
        except Exception as e:  # one bad streamer must not stop the rest
            log.warning("could not fetch clips for %s: %s", s.name, e)
            continue
        found += [c for c in clips
                  if c.view_count >= s.min_views and d.min_duration <= c.duration <= d.max_duration]
    return sorted(found, key=lambda c: c.score(now), reverse=True)


def _make_subtitles(clip: Clip, raw: Path, cfg: Config, transcriber: Transcriber | None,
                    subs_dir: Path) -> Path | None:
    """Transcribe the clip into an .ass file. Never fatal: no captions beats no post."""
    if transcriber is None or not cfg.subtitles.enabled:
        return None
    try:
        words = transcriber.transcribe(raw)
        if not words:
            log.info("no speech detected in %s; skipping captions", clip.id)
            return None
        return write_ass(words, subs_dir / f"{clip.id}.ass", cfg.subtitles, cfg.processing)
    except Exception as e:
        log.warning("captioning %s failed, rendering without captions: %s", clip.id, e)
        return None


def run_once(
    cfg: Config,
    db: Database,
    source: ClipSource,
    publishers: list[Publisher],
    *,
    download: Callable[[Clip, Path], Path],
    dry_run: bool = False,
    render: Callable[..., Path] = render_vertical,
    transcriber: Transcriber | None = None,
) -> RunSummary:
    summary = RunSummary()
    streamers = {s.name.lower(): s for s in cfg.streamers}
    sched = cfg.schedule
    data = cfg.paths.data_dir

    candidates = discover(cfg, source)
    summary.discovered = len(candidates)

    for clip in candidates:
        if summary.processed >= sched.max_clips_per_run:
            break

        pending = [
            p for p in publishers
            if not db.is_posted(clip.id, p.name)
            and db.attempts(clip.id, p.name) < sched.max_attempts
            and db.posts_today(p.name) + sum(1 for _, pl in summary.posted if pl == p.name)
            < sched.max_posts_per_day
        ]
        if not pending:
            continue

        db.upsert_clip(clip)
        try:
            rendered = db.rendered_path(clip.id)
            if rendered is None:
                raw = download(clip, data / "raw")
                subs = _make_subtitles(clip, raw, cfg, transcriber, data / "subs")
                rendered = render(raw, data / "rendered" / f"{clip.id}.mp4", cfg.processing,
                                  max_seconds=cfg.discovery.max_duration, subtitles=subs)
                db.set_rendered(clip.id, rendered)
        except Exception as e:
            log.error("processing %s failed: %s", clip.id, e)
            for p in pending:
                if not dry_run:
                    db.record_post(clip.id, p.name, error=f"processing: {e}")
                summary.failed.append((clip.id, p.name, str(e)))
            continue

        summary.processed += 1
        caption = build_caption(clip, streamers[clip.streamer], cfg.caption)

        for p in pending:
            if dry_run:
                log.info("[dry-run] would post %s to %s: %s", rendered, p.name, caption.replace("\n", " ")[:100])
                continue
            try:
                remote_id = p.publish(rendered, caption, clip)
            except Exception as e:
                log.error("%s publish of %s failed: %s", p.name, clip.id, e)
                db.record_post(clip.id, p.name, error=str(e))
                summary.failed.append((clip.id, p.name, str(e)))
            else:
                db.record_post(clip.id, p.name, remote_id=remote_id)
                summary.posted.append((clip.id, p.name))
                log.info("posted %s to %s (%s)", clip.id, p.name, remote_id)
    return summary
