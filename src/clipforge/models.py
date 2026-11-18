from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Clip:
    id: str
    streamer: str  # Twitch login the clip was discovered for
    title: str
    url: str
    view_count: int
    duration: float
    created_at: datetime  # timezone-aware (UTC)
    creator_name: str = ""
    thumbnail_url: str = ""

    def score(self, now: datetime) -> float:
        """Views, decayed by age, so fresh fast-growing clips rank first."""
        age_hours = max((now - self.created_at).total_seconds() / 3600, 0.0)
        return self.view_count / (age_hours + 2) ** 1.2
