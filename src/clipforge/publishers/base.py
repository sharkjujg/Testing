from __future__ import annotations

from pathlib import Path
from typing import Protocol

from ..models import Clip


class PublishError(RuntimeError):
    pass


class Publisher(Protocol):
    name: str

    def publish(self, video: Path, caption: str, clip: Clip) -> str:
        """Upload + publish the video. Returns the platform's id for the post."""
        ...
