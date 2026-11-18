import pytest
from pydantic import ValidationError

from clipforge.caption import build_caption
from clipforge.config import CaptionCfg, Config, StreamerCfg
from clipforge.pipeline import discover, run_once

from conftest import make_clip


class FakeSource:
    def __init__(self, clips):
        self.clips = clips

    def fetch_clips(self, login, lookback_hours, limit=50):
        return self.clips


class FakePublisher:
    def __init__(self, name="tiktok", fail=False):
        self.name, self.fail, self.calls = name, fail, []

    def publish(self, video, caption, clip):
        self.calls.append((video, caption, clip.id))
        if self.fail:
            raise RuntimeError("boom")
        return f"remote-{clip.id}"


def fake_download(clip, dest):
    dest.mkdir(parents=True, exist_ok=True)
    p = dest / f"{clip.id}.mp4"
    p.write_bytes(b"raw")
    return p


def fake_render(src, dst, cfg, max_seconds=60):
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(b"rendered")
    return dst


def test_config_requires_streamers_and_instagram_url():
    with pytest.raises(ValidationError):
        Config.model_validate({"streamers": []})
    with pytest.raises(ValidationError):
        Config.model_validate({"streamers": [{"name": "x"}], "platforms": {"instagram": {"enabled": True}}})


def test_discover_filters_and_ranks(cfg):
    clips = [
        make_clip("fresh", views=4000, age_h=1),
        make_clip("old", views=4000, age_h=20),
        make_clip("few", views=10),
        make_clip("long", duration=120),
        make_clip("short", duration=2),
    ]
    assert [c.id for c in discover(cfg, FakeSource(clips))] == ["fresh", "old"]


def test_caption_dedupes_hashtags_and_truncates():
    clip = make_clip(title="Wow")
    cap = build_caption(clip, StreamerCfg(name="KaiCenat", hashtags=["#Kai", "fyp"]),
                        CaptionCfg(template="{title} {hashtags}", hashtags=["FYP", "twitch"]))
    assert cap == "Wow #kai #fyp #kaicenat #twitch"
    long = build_caption(make_clip(title="x" * 5000), StreamerCfg(name="a"), CaptionCfg(template="{title}"))
    assert len(long) == 2200


def test_run_posts_once_and_dedupes(cfg, db):
    pub = FakePublisher()
    src = FakeSource([make_clip("a"), make_clip("b", views=9000)])
    s = run_once(cfg, db, src, [pub], download=fake_download, render=fake_render)
    assert sorted(c for c, _ in s.posted) == ["a", "b"]
    assert "#kaicenat" in pub.calls[0][1]
    s2 = run_once(cfg, db, src, [pub], download=fake_download, render=fake_render)
    assert s2.posted == [] and len(pub.calls) == 2


def test_dry_run_records_nothing_and_reuses_render(cfg, db):
    pub = FakePublisher()
    src = FakeSource([make_clip("a")])
    run_once(cfg, db, src, [pub], download=fake_download, render=fake_render, dry_run=True)
    assert pub.calls == [] and not db.is_posted("a", "tiktok")
    assert db.rendered_path("a") is not None
    run_once(cfg, db, src, [pub], download=fake_download, render=fake_render)
    assert db.is_posted("a", "tiktok")


def test_failures_are_retried_up_to_max_attempts(cfg, db):
    pub = FakePublisher(fail=True)
    src = FakeSource([make_clip("a")])
    for _ in range(5):
        run_once(cfg, db, src, [pub], download=fake_download, render=fake_render)
    assert len(pub.calls) == cfg.schedule.max_attempts


def test_daily_limit(cfg, db):
    cfg.schedule.max_posts_per_day = 1
    pub = FakePublisher()
    src = FakeSource([make_clip("a"), make_clip("b")])
    s = run_once(cfg, db, src, [pub], download=fake_download, render=fake_render)
    assert len(s.posted) == 1
