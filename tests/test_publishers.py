import httpx
import pytest

from clipforge.config import HostingCfg, InstagramCfg, Secrets, TikTokCfg
from clipforge.publishers.base import PublishError
from clipforge.publishers.hosting import PublicHost
from clipforge.publishers.instagram import InstagramPublisher
from clipforge.publishers.tiktok import TikTokPublisher

from conftest import make_clip


@pytest.fixture
def video(tmp_path):
    p = tmp_path / "c1.mp4"
    p.write_bytes(b"0" * 1000)
    return p


def test_tiktok_flow_with_token_refresh(db, video):
    seen = []
    state = {"polls": 0, "init_calls": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append((req.method, req.url.path))
        if req.url.path == "/v2/oauth/token/":
            return httpx.Response(200, json={"access_token": "NEW", "refresh_token": "NEWR"})
        if req.url.path == "/v2/post/publish/video/init/":
            state["init_calls"] += 1
            if req.headers["authorization"] == "Bearer OLD":
                return httpx.Response(200, json={"error": {"code": "access_token_invalid", "message": "x"}})
            import json
            body = json.loads(req.content)
            assert body["source_info"]["video_size"] == 1000
            assert body["post_info"]["privacy_level"] == "SELF_ONLY"
            return httpx.Response(200, json={"data": {"publish_id": "p1", "upload_url": "https://upload.tiktok/u"},
                                             "error": {"code": "ok"}})
        if req.url.host == "upload.tiktok":
            assert req.headers["content-range"] == "bytes 0-999/1000"
            return httpx.Response(201)
        if req.url.path == "/v2/post/publish/status/fetch/":
            state["polls"] += 1
            st = "PROCESSING_UPLOAD" if state["polls"] == 1 else "PUBLISH_COMPLETE"
            return httpx.Response(200, json={"data": {"status": st}, "error": {"code": "ok"}})
        raise AssertionError(req.url)

    pub = TikTokPublisher(TikTokCfg(), Secrets(tiktok_access_token="OLD", tiktok_refresh_token="R"), db,
                          client=httpx.Client(transport=httpx.MockTransport(handler)), sleep=lambda s: None)
    assert pub.publish(video, "hi #fyp", make_clip()) == "p1"
    assert db.kv_get("tiktok_access_token") == "NEW" and db.kv_get("tiktok_refresh_token") == "NEWR"
    assert state["init_calls"] == 2


def test_tiktok_error_raises(db, video):
    h = lambda req: httpx.Response(200, json={"error": {"code": "spam_risk", "message": "no"}})  # noqa: E731
    pub = TikTokPublisher(TikTokCfg(), Secrets(tiktok_access_token="T"), db,
                          client=httpx.Client(transport=httpx.MockTransport(h)), sleep=lambda s: None)
    with pytest.raises(PublishError, match="spam_risk"):
        pub.publish(video, "x", make_clip())


def test_instagram_flow(tmp_path, video):
    calls = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(req.url.path)
        if req.url.path.endswith("/123/media"):
            assert b"video_url=https%3A%2F%2Fcdn.example.com%2Fc1.mp4" in req.content
            assert b"media_type=REELS" in req.content
            return httpx.Response(200, json={"id": "cont1"})
        if req.url.path.endswith("/cont1"):
            code = "IN_PROGRESS" if calls.count(req.url.path) == 1 else "FINISHED"
            return httpx.Response(200, json={"status_code": code})
        if req.url.path.endswith("/123/media_publish"):
            return httpx.Response(200, json={"id": "media9"})
        raise AssertionError(req.url)

    host = PublicHost(HostingCfg(local_dir=tmp_path / "pub", base_url="https://cdn.example.com/"))
    pub = InstagramPublisher(InstagramCfg(), Secrets(instagram_user_id="123", instagram_access_token="t"), host,
                             client=httpx.Client(transport=httpx.MockTransport(handler)), sleep=lambda s: None)
    assert pub.publish(video, "cap", make_clip()) == "media9"
    assert (tmp_path / "pub" / "c1.mp4").exists()


def test_instagram_processing_error(tmp_path, video):
    def handler(req):
        if req.url.path.endswith("/media"):
            return httpx.Response(200, json={"id": "c"})
        return httpx.Response(200, json={"status_code": "ERROR", "status": "bad codec"})

    host = PublicHost(HostingCfg(local_dir=tmp_path / "pub", base_url="https://x.com"))
    pub = InstagramPublisher(InstagramCfg(), Secrets(instagram_user_id="1", instagram_access_token="t"), host,
                             client=httpx.Client(transport=httpx.MockTransport(handler)), sleep=lambda s: None)
    with pytest.raises(PublishError, match="bad codec"):
        pub.publish(video, "c", make_clip())
