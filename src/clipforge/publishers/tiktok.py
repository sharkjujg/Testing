from __future__ import annotations

import time
from pathlib import Path
from typing import Callable

import httpx

from ..config import Secrets, TikTokCfg
from ..db import Database
from ..models import Clip
from .base import PublishError

API = "https://open.tiktokapis.com"
MAX_SINGLE_CHUNK = 64 * 1024 * 1024  # clips are small; we upload in one chunk


class TikTokPublisher:
    """TikTok Content Posting API (Direct Post, FILE_UPLOAD).

    Note: until your TikTok app passes audit, posts are forced to SELF_ONLY.
    """

    name = "tiktok"

    def __init__(self, cfg: TikTokCfg, secrets: Secrets, db: Database,
                 client: httpx.Client | None = None,
                 sleep: Callable[[float], None] = time.sleep,
                 poll_timeout: float = 300):
        self.cfg, self.secrets, self.db = cfg, secrets, db
        self.http = client or httpx.Client(timeout=120)
        self.sleep = sleep
        self.poll_timeout = poll_timeout

    # --- tokens (rotated on refresh, so persisted in the db) -------------
    def _access(self) -> str:
        return self.db.kv_get("tiktok_access_token") or self.secrets.tiktok_access_token

    def _refresh_token(self) -> str:
        return self.db.kv_get("tiktok_refresh_token") or self.secrets.tiktok_refresh_token

    def refresh(self) -> None:
        r = self.http.post(f"{API}/v2/oauth/token/", data={
            "client_key": self.secrets.tiktok_client_key,
            "client_secret": self.secrets.tiktok_client_secret,
            "grant_type": "refresh_token",
            "refresh_token": self._refresh_token(),
        })
        body = r.json()
        if r.status_code != 200 or "access_token" not in body:
            raise PublishError(f"TikTok token refresh failed: {body}")
        self.db.kv_set("tiktok_access_token", body["access_token"])
        if body.get("refresh_token"):
            self.db.kv_set("tiktok_refresh_token", body["refresh_token"])

    def _call(self, path: str, payload: dict) -> dict:
        for attempt in (1, 2):
            r = self.http.post(
                f"{API}{path}",
                json=payload,
                headers={"Authorization": f"Bearer {self._access()}",
                         "Content-Type": "application/json; charset=UTF-8"},
            )
            body = r.json()
            code = body.get("error", {}).get("code", "ok")
            if code == "access_token_invalid" and attempt == 1:
                self.refresh()
                continue
            if code != "ok":
                raise PublishError(f"TikTok {path}: {body['error']}")
            return body["data"]
        raise PublishError("unreachable")

    # --- publishing ------------------------------------------------------
    def publish(self, video: Path, caption: str, clip: Clip) -> str:
        size = video.stat().st_size
        if size > MAX_SINGLE_CHUNK:
            raise PublishError(f"{video.name} is {size} bytes; limit for single upload is {MAX_SINGLE_CHUNK}")
        init = self._call("/v2/post/publish/video/init/", {
            "post_info": {
                "title": caption,
                "privacy_level": self.cfg.privacy_level,
                "disable_comment": self.cfg.disable_comment,
                "disable_duet": self.cfg.disable_duet,
                "disable_stitch": self.cfg.disable_stitch,
            },
            "source_info": {
                "source": "FILE_UPLOAD",
                "video_size": size,
                "chunk_size": size,
                "total_chunk_count": 1,
            },
        })
        publish_id, upload_url = init["publish_id"], init["upload_url"]

        r = self.http.put(upload_url, content=video.read_bytes(), headers={
            "Content-Type": "video/mp4",
            "Content-Range": f"bytes 0-{size - 1}/{size}",
        })
        if r.status_code not in (200, 201, 206):
            raise PublishError(f"TikTok upload failed: HTTP {r.status_code} {r.text[:200]}")

        deadline = time.monotonic() + self.poll_timeout
        while True:
            status = self._call("/v2/post/publish/status/fetch/", {"publish_id": publish_id})
            state = status.get("status")
            if state == "PUBLISH_COMPLETE":
                return publish_id
            if state == "FAILED":
                raise PublishError(f"TikTok publish failed: {status.get('fail_reason')}")
            if time.monotonic() > deadline:
                raise PublishError(f"TikTok publish timed out in state {state}")
            self.sleep(5)
