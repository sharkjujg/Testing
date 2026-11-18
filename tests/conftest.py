from datetime import datetime, timedelta, timezone

import pytest

from clipforge.config import Config
from clipforge.db import Database
from clipforge.models import Clip


@pytest.fixture
def cfg(tmp_path):
    return Config.model_validate({
        "streamers": [{"name": "kaicenat", "min_views": 1000, "hashtags": ["kai"]}],
        "paths": {"data_dir": str(tmp_path / "data")},
        "schedule": {"max_clips_per_run": 2, "max_posts_per_day": 5},
    })


@pytest.fixture
def db():
    return Database(":memory:")


def make_clip(id="c1", views=5000, duration=30.0, age_h=3, streamer="kaicenat", title="Insane play"):
    return Clip(id=id, streamer=streamer, title=title, url=f"https://clips.twitch.tv/{id}",
                view_count=views, duration=duration,
                created_at=datetime.now(timezone.utc) - timedelta(hours=age_h), creator_name="viewer")
