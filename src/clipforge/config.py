from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field, model_validator


class StreamerCfg(BaseModel):
    name: str
    min_views: int = 1000
    hashtags: list[str] = Field(default_factory=list)


class DiscoveryCfg(BaseModel):
    lookback_hours: int = 24
    min_duration: float = 8
    max_duration: float = 60


class ProcessingCfg(BaseModel):
    layout: Literal["blur", "crop"] = "blur"
    width: int = 1080
    height: int = 1920
    crf: int = 20
    preset: str = "veryfast"


class CaptionCfg(BaseModel):
    template: str = "{title} 🔥 (clip from @{streamer} on Twitch)\n\n{hashtags}"
    hashtags: list[str] = Field(default_factory=lambda: ["fyp", "twitch", "gaming"])


class TikTokCfg(BaseModel):
    enabled: bool = False
    privacy_level: str = "SELF_ONLY"
    disable_comment: bool = False
    disable_duet: bool = False
    disable_stitch: bool = False


class InstagramCfg(BaseModel):
    enabled: bool = False
    share_to_feed: bool = True


class PlatformsCfg(BaseModel):
    tiktok: TikTokCfg = Field(default_factory=TikTokCfg)
    instagram: InstagramCfg = Field(default_factory=InstagramCfg)


class HostingCfg(BaseModel):
    local_dir: Path = Path("data/public")
    base_url: str | None = None


class ScheduleCfg(BaseModel):
    interval_minutes: int = 60
    max_clips_per_run: int = 3
    max_posts_per_day: int = 5
    max_attempts: int = 3


class PathsCfg(BaseModel):
    data_dir: Path = Path("data")


class Config(BaseModel):
    streamers: list[StreamerCfg]
    discovery: DiscoveryCfg = Field(default_factory=DiscoveryCfg)
    processing: ProcessingCfg = Field(default_factory=ProcessingCfg)
    caption: CaptionCfg = Field(default_factory=CaptionCfg)
    platforms: PlatformsCfg = Field(default_factory=PlatformsCfg)
    hosting: HostingCfg = Field(default_factory=HostingCfg)
    schedule: ScheduleCfg = Field(default_factory=ScheduleCfg)
    paths: PathsCfg = Field(default_factory=PathsCfg)

    @model_validator(mode="after")
    def _check(self) -> "Config":
        if not self.streamers:
            raise ValueError("config needs at least one streamer")
        if self.platforms.instagram.enabled and not self.hosting.base_url:
            raise ValueError("platforms.instagram needs hosting.base_url (Instagram fetches the video by URL)")
        return self


@dataclass(frozen=True)
class Secrets:
    twitch_client_id: str = ""
    twitch_client_secret: str = ""
    tiktok_client_key: str = ""
    tiktok_client_secret: str = ""
    tiktok_access_token: str = ""
    tiktok_refresh_token: str = ""
    instagram_user_id: str = ""
    instagram_access_token: str = ""

    @classmethod
    def from_env(cls) -> "Secrets":
        g = lambda k: os.environ.get(k, "")  # noqa: E731
        return cls(
            twitch_client_id=g("TWITCH_CLIENT_ID"),
            twitch_client_secret=g("TWITCH_CLIENT_SECRET"),
            tiktok_client_key=g("TIKTOK_CLIENT_KEY"),
            tiktok_client_secret=g("TIKTOK_CLIENT_SECRET"),
            tiktok_access_token=g("TIKTOK_ACCESS_TOKEN"),
            tiktok_refresh_token=g("TIKTOK_REFRESH_TOKEN"),
            instagram_user_id=g("INSTAGRAM_USER_ID"),
            instagram_access_token=g("INSTAGRAM_ACCESS_TOKEN"),
        )


def load_config(path: str | Path) -> Config:
    load_dotenv()
    with open(path, encoding="utf-8") as f:
        return Config.model_validate(yaml.safe_load(f))
