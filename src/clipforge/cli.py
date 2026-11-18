from __future__ import annotations

import argparse
import logging
import sys
import time

from .config import Config, Secrets, load_config
from .db import Database
from .pipeline import discover, run_once
from .publishers.hosting import PublicHost
from .publishers.instagram import InstagramPublisher
from .publishers.tiktok import TikTokPublisher
from .sources.download import download_clip
from .sources.twitch import TwitchSource

log = logging.getLogger("clipforge")


def _build(cfg: Config):
    secrets = Secrets.from_env()
    db = Database(cfg.paths.data_dir / "clipforge.db")
    source = TwitchSource(secrets.twitch_client_id, secrets.twitch_client_secret)
    publishers = []
    if cfg.platforms.tiktok.enabled:
        publishers.append(TikTokPublisher(cfg.platforms.tiktok, secrets, db))
    if cfg.platforms.instagram.enabled:
        publishers.append(InstagramPublisher(cfg.platforms.instagram, secrets, PublicHost(cfg.hosting)))
    return db, source, publishers


def cmd_discover(cfg: Config, args) -> int:
    _, source, _ = _build(cfg)
    for c in discover(cfg, source)[: args.limit]:
        print(f"{c.view_count:>8} views  {c.duration:>4.0f}s  {c.streamer:<12} {c.title}  <{c.url}>")
    return 0


def cmd_run(cfg: Config, args) -> int:
    db, source, publishers = _build(cfg)
    if not publishers and not args.dry_run:
        print("No platforms enabled in config.", file=sys.stderr)
        return 1
    s = run_once(cfg, db, source, publishers, download=download_clip, dry_run=args.dry_run)
    print(f"discovered={s.discovered} processed={s.processed} posted={len(s.posted)} failed={len(s.failed)}")
    return 1 if s.failed else 0


def cmd_watch(cfg: Config, args) -> int:
    db, source, publishers = _build(cfg)
    while True:
        try:
            run_once(cfg, db, source, publishers, download=download_clip)
        except Exception:
            log.exception("run failed")
        time.sleep(cfg.schedule.interval_minutes * 60)


def cmd_status(cfg: Config, args) -> int:
    db = Database(cfg.paths.data_dir / "clipforge.db")
    for r in db.recent_posts(args.limit):
        err = f"  ({r['error']})" if r["error"] else ""
        print(f"{r['updated_at'][:19]}  {r['platform']:<9} {r['status']:<7} {r['streamer']}: {r['title']}{err}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="clipforge", description=__doc__)
    p.add_argument("-c", "--config", default="config.yaml")
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("discover", help="list the top clips that would be picked")
    d.add_argument("--limit", type=int, default=15)
    d.set_defaults(fn=cmd_discover)

    r = sub.add_parser("run", help="find, render and post clips once")
    r.add_argument("--dry-run", action="store_true", help="render but do not post or record posts")
    r.set_defaults(fn=cmd_run)

    w = sub.add_parser("watch", help="run forever on the configured interval")
    w.set_defaults(fn=cmd_watch)

    s = sub.add_parser("status", help="show recent posts")
    s.add_argument("--limit", type=int, default=20)
    s.set_defaults(fn=cmd_status)

    args = p.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    return args.fn(load_config(args.config), args)


if __name__ == "__main__":
    raise SystemExit(main())
