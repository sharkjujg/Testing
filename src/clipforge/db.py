from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .models import Clip

SCHEMA = """
CREATE TABLE IF NOT EXISTS clips (
  id TEXT PRIMARY KEY,
  streamer TEXT NOT NULL,
  title TEXT NOT NULL,
  url TEXT NOT NULL,
  view_count INTEGER NOT NULL,
  duration REAL NOT NULL,
  created_at TEXT NOT NULL,
  rendered_path TEXT,
  first_seen TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS posts (
  clip_id TEXT NOT NULL,
  platform TEXT NOT NULL,
  status TEXT NOT NULL,            -- posted | failed
  attempts INTEGER NOT NULL DEFAULT 0,
  remote_id TEXT,
  error TEXT,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (clip_id, platform)
);
CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Database:
    def __init__(self, path: str | Path):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path))
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    # --- clips -----------------------------------------------------------
    def upsert_clip(self, clip: Clip) -> None:
        self.conn.execute(
            """INSERT INTO clips (id, streamer, title, url, view_count, duration, created_at, first_seen)
               VALUES (?,?,?,?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET view_count=excluded.view_count""",
            (clip.id, clip.streamer, clip.title, clip.url, clip.view_count, clip.duration,
             clip.created_at.isoformat(), _now()),
        )
        self.conn.commit()

    def set_rendered(self, clip_id: str, path: str | Path) -> None:
        self.conn.execute("UPDATE clips SET rendered_path=? WHERE id=?", (str(path), clip_id))
        self.conn.commit()

    def rendered_path(self, clip_id: str) -> Path | None:
        row = self.conn.execute("SELECT rendered_path FROM clips WHERE id=?", (clip_id,)).fetchone()
        if row and row["rendered_path"] and Path(row["rendered_path"]).exists():
            return Path(row["rendered_path"])
        return None

    # --- posts -----------------------------------------------------------
    def is_posted(self, clip_id: str, platform: str) -> bool:
        return self._post_status(clip_id, platform) == "posted"

    def attempts(self, clip_id: str, platform: str) -> int:
        row = self.conn.execute(
            "SELECT attempts FROM posts WHERE clip_id=? AND platform=?", (clip_id, platform)
        ).fetchone()
        return row["attempts"] if row else 0

    def _post_status(self, clip_id: str, platform: str) -> str | None:
        row = self.conn.execute(
            "SELECT status FROM posts WHERE clip_id=? AND platform=?", (clip_id, platform)
        ).fetchone()
        return row["status"] if row else None

    def record_post(self, clip_id: str, platform: str, *, remote_id: str | None = None,
                    error: str | None = None) -> None:
        status = "failed" if error else "posted"
        self.conn.execute(
            """INSERT INTO posts (clip_id, platform, status, attempts, remote_id, error, updated_at)
               VALUES (?,?,?,1,?,?,?)
               ON CONFLICT(clip_id, platform) DO UPDATE SET
                 status=excluded.status, attempts=posts.attempts+1,
                 remote_id=excluded.remote_id, error=excluded.error, updated_at=excluded.updated_at""",
            (clip_id, platform, status, remote_id, error, _now()),
        )
        self.conn.commit()

    def posts_today(self, platform: str) -> int:
        start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        row = self.conn.execute(
            "SELECT COUNT(*) c FROM posts WHERE platform=? AND status='posted' AND updated_at>=?",
            (platform, start.isoformat()),
        ).fetchone()
        return row["c"]

    def recent_posts(self, limit: int = 20) -> list[sqlite3.Row]:
        return self.conn.execute(
            """SELECT p.*, c.title, c.streamer FROM posts p JOIN clips c ON c.id=p.clip_id
               ORDER BY p.updated_at DESC LIMIT ?""", (limit,)
        ).fetchall()

    # --- key/value (rotating OAuth tokens) -------------------------------
    def kv_get(self, key: str) -> str | None:
        row = self.conn.execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
        return row["value"] if row else None

    def kv_set(self, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT INTO kv (key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )
        self.conn.commit()
