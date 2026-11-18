from __future__ import annotations

import time
from pathlib import Path
from typing import Callable

import httpx

from ..config import InstagramCfg, Secrets
from ..models import Clip
from .base import PublishError
from .hosting import PublicHost

GRAPH = "https://graph.facebook.com/v21.0"


class InstagramPublisher:
    """Instagram Graph API Reels publishing (Business/Creator accounts)."""

    name = "instagram"

    def __init__(self, cfg: InstagramCfg, secrets: Secrets, host: PublicHost,
                 client: httpx.Client | None = None,
                 sleep: Callable[[float], None] = time.sleep,
                 poll_timeout: float = 300):
        if not secrets.instagram_user_id or not secrets.instagram_access_token:
            raise ValueError("INSTAGRAM_USER_ID and INSTAGRAM_ACCESS_TOKEN are required")
        self.cfg, self.secrets, self.host = cfg, secrets, host
        self.http = client or httpx.Client(timeout=60)
        self.sleep = sleep
        self.poll_timeout = poll_timeout

    def _check(self, r: httpx.Response) -> dict:
        body = r.json()
        if r.status_code >= 400 or "error" in body:
            raise PublishError(f"Instagram API error: {body.get('error', body)}")
        return body

    def publish(self, video: Path, caption: str, clip: Clip) -> str:
        uid, token = self.secrets.instagram_user_id, self.secrets.instagram_access_token
        video_url = self.host.expose(video)

        container = self._check(self.http.post(f"{GRAPH}/{uid}/media", data={
            "media_type": "REELS",
            "video_url": video_url,
            "caption": caption,
            "share_to_feed": str(self.cfg.share_to_feed).lower(),
            "access_token": token,
        }))["id"]

        deadline = time.monotonic() + self.poll_timeout
        while True:
            st = self._check(self.http.get(f"{GRAPH}/{container}", params={
                "fields": "status_code,status", "access_token": token,
            }))
            code = st.get("status_code")
            if code == "FINISHED":
                break
            if code in ("ERROR", "EXPIRED"):
                raise PublishError(f"Instagram processing {code}: {st.get('status')}")
            if time.monotonic() > deadline:
                raise PublishError(f"Instagram processing timed out in state {code}")
            self.sleep(5)

        return self._check(self.http.post(f"{GRAPH}/{uid}/media_publish", data={
            "creation_id": container, "access_token": token,
        }))["id"]
