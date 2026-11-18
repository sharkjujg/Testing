# clipforge

Automatically find a big streamer's best recent Twitch clips, reformat them to vertical 9:16, and post them to **TikTok** and **Instagram Reels**.

```
Twitch Helix API ──► rank & filter ──► yt-dlp download ──► ffmpeg 9:16 render ──► caption ──► TikTok / Instagram
                          └──────────────── SQLite: dedupe, retries, daily limits ────────────────┘
```

## Quick start

Requires Python 3.11+ and `ffmpeg` on your PATH.

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e '.[dev,captions]'   # drop ',captions' if you don't want Whisper auto-captions
cp .env.example .env              # fill in API credentials
cp config.example.yaml config.yaml  # pick streamers / platforms

clipforge discover                # see which clips would be picked
clipforge run --dry-run           # download + render, but don't post
clipforge run                     # post for real (once)
clipforge watch                   # loop forever every schedule.interval_minutes
clipforge status                  # recent posts
pytest                            # run tests
```

## How it works

- **Discovery** (`sources/twitch.py`, `pipeline.discover`): pulls each streamer's clips from the last `lookback_hours`, drops those under `min_views` or outside the duration window, and ranks by `views / (age_hours + 2)^1.2` so fresh, fast-growing clips win.
- **Render** (`processing/video.py`): `blur` layout puts the 16:9 clip over a blurred copy of itself; `crop` centre-crops. H.264/AAC, 1080x1920, `faststart`.
- **Auto-captions** (`processing/transcribe.py`, `processing/subtitles.py`): when `subtitles.enabled`, [faster-whisper](https://github.com/SYSTRAN/faster-whisper) transcribes each clip locally (no API key, word-level timestamps). Words are grouped into short lines and written as an ASS karaoke file so each word lights up as it's spoken, then burned in during the ffmpeg render, placed above the TikTok/IG UI overlay. The model downloads on first use (`small` by default; use `base` or `tiny` on slow CPUs). If transcription fails or no speech is found, the clip is still posted without captions.
- **Post captions** (`caption.py`): template + de-duplicated hashtags, credits the streamer.
- **Publishing** (`publishers/`): one adapter per platform behind a tiny `Publisher` protocol, so adding YouTube Shorts is one new file.
- **State** (`db.py`): a clip is never posted twice to a platform; failures retry up to `max_attempts`; `max_posts_per_day` is enforced per platform. Rotating TikTok tokens are stored in the db.

## Platform setup (the slow part)

**Twitch**: register an app at <https://dev.twitch.tv/console>, put the client id/secret in `.env`.

**TikTok** (Content Posting API):
1. Create an app at <https://developers.tiktok.com>, add the *Content Posting API* product and `video.publish` scope.
2. Run the OAuth flow once for the account you post to and put the tokens in `.env`.
3. Until TikTok **audits** your app, every post is forced private (`SELF_ONLY`). Apply for audit before expecting public posts, then set `privacy_level: PUBLIC_TO_EVERYONE`.

**Instagram** (Graph API Reels):
1. Needs an Instagram **Business/Creator** account linked to a Facebook Page, and a long-lived access token with `instagram_content_publish`.
2. Instagram downloads the video from a **public https URL**. Serve `hosting.local_dir` at `hosting.base_url` (nginx/Caddy, a tunnel, or a bucket sync) and set both in `config.yaml`.

## Read this before posting other people's content

- Clips belong to the streamer/clip creator. **Get the streamer's permission** (or run this *for* the streamer / their editors) and credit them. Re-uploading without consent risks copyright strikes and account bans on all three platforms.
- TikTok and Instagram penalise bulk, repetitive, unmodified reposts. Keep `max_posts_per_day` low and consider adding commentary, captions or edits.
- Respect each platform's API terms and rate limits.

## Roadmap ideas

- Facecam/gameplay split layout for a more TikTok-native look
- Chat-activity spike detection for clips that don't exist yet (cut from VODs)
- LLM-written titles/hooks, YouTube Shorts adapter, review-before-post queue
