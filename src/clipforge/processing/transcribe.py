from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from ..config import SubtitlesCfg

log = logging.getLogger("clipforge")


@dataclass(frozen=True)
class Word:
    start: float  # seconds
    end: float
    text: str


class Transcriber(Protocol):
    def transcribe(self, media: Path) -> list[Word]: ...


class WhisperTranscriber:
    """Word-level speech-to-text using faster-whisper (runs locally, no API key)."""

    def __init__(self, cfg: SubtitlesCfg):
        try:
            from faster_whisper import WhisperModel
        except ImportError as e:
            raise RuntimeError(
                "Auto-captions need faster-whisper: pip install -e '.[captions]'"
            ) from e
        self.cfg = cfg
        log.info("loading Whisper model %r (first run downloads it)", cfg.model)
        self.model = WhisperModel(cfg.model, device=cfg.device, compute_type=cfg.compute_type)

    def transcribe(self, media: Path) -> list[Word]:
        segments, info = self.model.transcribe(
            str(media),
            language=self.cfg.language,
            word_timestamps=True,
            vad_filter=True,
        )
        words = [
            Word(w.start, w.end, w.word.strip())
            for seg in segments
            for w in (seg.words or [])
            if w.word.strip()
        ]
        log.info("transcribed %s: %d words (language=%s)", media.name, len(words), info.language)
        return words
