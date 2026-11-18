from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import httpx

from ..models import Clip

HELIX = "https://api.twitch.tv/helix"
TOKEN_URL = "https://id.twitch.tv/oauth2/token"


class TwitchSource:
    """Finds top recent clips for a streamer via the Twitch Helix API."""

    def __init__(self, client_id: str, client_secret: str, client: httpx.Client | None = None):
        if not client_id or not client_secret:
            raise ValueError("TWITCH_CLIENT_ID and TWITCH_CLIENT_SECRET are required")
        self.client_id = client_id
        self.client_secret = client_secret
        self.http = client or httpx.Client(timeout=30)
        self._token: str | None = None
        self._token_expires = 0.0
        self._ids: dict[str, str] = {}

    def _auth_headers(self) -> dict[str, str]:
        if not self._token or time.time() > self._token_expires - 60:
            r = self.http.post(TOKEN_URL, data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "grant_type": "client_credentials",
            })
            r.raise_for_status()
            body = r.json()
            self._token = body["access_token"]
            self._token_expires = time.time() + body.get("expires_in", 3600)
        return {"Authorization": f"Bearer {self._token}", "Client-Id": self.client_id}

    def _broadcaster_id(self, login: str) -> str:
        login = login.lower()
        if login not in self._ids:
            r = self.http.get(f"{HELIX}/users", params={"login": login}, headers=self._auth_headers())
            r.raise_for_status()
            data = r.json()["data"]
            if not data:
                raise LookupError(f"Twitch user not found: {login}")
            self._ids[login] = data[0]["id"]
        return self._ids[login]

    def fetch_clips(self, login: str, lookback_hours: int, limit: int = 50) -> list[Clip]:
        since = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
        r = self.http.get(
            f"{HELIX}/clips",
            params={
                "broadcaster_id": self._broadcaster_id(login),
                "started_at": since.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "first": limit,
            },
            headers=self._auth_headers(),
        )
        r.raise_for_status()
        return [
            Clip(
                id=c["id"],
                streamer=login.lower(),
                title=c["title"],
                url=c["url"],
                view_count=c["view_count"],
                duration=float(c["duration"]),
                created_at=datetime.fromisoformat(c["created_at"].replace("Z", "+00:00")),
                creator_name=c.get("creator_name", ""),
                thumbnail_url=c.get("thumbnail_url", ""),
            )
            for c in r.json()["data"]
        ]
