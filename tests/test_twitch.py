import httpx

from clipforge.sources.twitch import TwitchSource


def test_fetch_clips_parses_response():
    def handler(req):
        if req.url.host == "id.twitch.tv":
            return httpx.Response(200, json={"access_token": "t", "expires_in": 3600})
        if req.url.path == "/helix/users":
            return httpx.Response(200, json={"data": [{"id": "42"}]})
        assert req.url.params["broadcaster_id"] == "42"
        assert req.headers["client-id"] == "cid"
        return httpx.Response(200, json={"data": [{
            "id": "Abc", "title": "t", "url": "https://clips.twitch.tv/Abc", "view_count": 99,
            "duration": 28.5, "created_at": "2026-11-18T10:00:00Z", "creator_name": "v", "thumbnail_url": ""}]})

    src = TwitchSource("cid", "sec", client=httpx.Client(transport=httpx.MockTransport(handler)))
    [c] = src.fetch_clips("KaiCenat", 24)
    assert (c.id, c.view_count, c.duration, c.streamer) == ("Abc", 99, 28.5, "kaicenat")
    assert c.created_at.tzinfo is not None
