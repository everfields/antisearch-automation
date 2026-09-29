"""Instagram, LinkedIn Page and TikTok through Buffer's API, and the GitHub Pages media host."""

import base64
import json
import re

import pytest

from antisearch_mill.publish.http import HttpResponse, RecordingTransport
from antisearch_mill.publisher import Media, PublisherError
from antisearch_mill.publisher.buffer import BufferInstagram, BufferLinkedIn, BufferTikTok, BufferX
from antisearch_mill.publisher.media_host import GitHubPagesHost
from antisearch_mill.publisher.registry import resolve_adapters, route_for

KEY = {"BUFFER_API_KEY": "buf-key"}


@pytest.fixture
def clip(tmp_path):
    p = tmp_path / "dog-1a2b3c4d.mp4"
    p.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"v" * 2000)
    return Media.video(p, 1080, 1920, 3.8, label="dog", public_url="https://everfields.github.io/antisearch-clips/clips/dog-1a2b3c4d.mp4")


def run(cls, env, media, caption="", override=None):
    a = cls(None, env, sleep=lambda s: None)

    def respond(req):
        got = override(req) if override else None
        return got if got is not None else a.dry_run_responder(req)

    a.transport = RecordingTransport(respond)
    return a, a.transport, a.post(media, caption)


def gql(req):
    return req.json["query"], req.json["variables"]


def test_instagram_reel_share_now_with_verdict_thumbnail(clip):
    _, t, res = run(BufferInstagram, {**KEY, "BUFFER_CHANNEL_INSTAGRAM": "ch-ig"}, clip, "@disfrutarbcn")
    query, variables = gql(t.requests[0])
    assert "createPost" in query and t.requests[0].headers["Authorization"] == "Bearer buf-key"
    assert variables["input"] == {
        "channelId": "ch-ig", "text": "@disfrutarbcn", "schedulingType": "automatic", "mode": "shareNow",
        "assets": [{"video": {"url": clip.public_url, "metadata": {"thumbnailOffset": 3500}}}],
        "metadata": {"instagram": {"type": "reel", "shouldShareToFeed": True}},
    }
    assert res.url == "https://instagram.dry.run/p/dry" and res.remote_id == "dry-post"
    assert "buf-key" not in json.dumps(t.plan())


def test_linkedin_has_no_thumbnail_or_metadata_and_finds_its_channel(clip):
    _, t, _ = run(BufferLinkedIn, KEY, clip)
    names = [re.match(r"\s*(?:query|mutation)\s+(\w+)", gql(r)[0]).group(1) for r in t.requests]
    assert names[:3] == ["Orgs", "Channels", "CreatePost"]
    assert gql(t.requests[1])[1] == {"org": "org-dry"}
    payload = gql(t.requests[2])[1]["input"]
    assert payload["channelId"] == "ch-linkedin" and "metadata" not in payload
    assert payload["assets"] == [{"video": {"url": clip.public_url}}]


def test_ambiguous_channels_ask_for_a_pin(clip):
    def two(req):
        if "Channels" in req.json["query"]:
            return HttpResponse.of_json(200, {"data": {"channels": [
                {"id": "a", "name": "a", "service": "tiktok"}, {"id": "b", "name": "b", "service": "tiktok"}]}})
        return None

    with pytest.raises(PublisherError, match="BUFFER_CHANNEL_TIKTOK"):
        run(BufferTikTok, KEY, clip, override=two)


def test_mutation_error_and_publish_error_raise(clip):
    def refused(req):
        if "createPost" in req.json["query"]:
            return HttpResponse.of_json(200, {"data": {"createPost": {"__typename": "MutationError", "message": "video too short"}}})
        return None

    with pytest.raises(PublisherError, match="video too short"):
        run(BufferTikTok, {**KEY, "BUFFER_CHANNEL_TIKTOK": "c"}, clip, override=refused)

    def failed(req):
        if "PostStatus" in req.json["query"]:
            return HttpResponse.of_json(200, {"data": {"post": {"id": "p", "status": "error", "externalLink": None,
                                                                "error": {"message": "reel rejected"}}}})
        return None

    with pytest.raises(PublisherError, match="reel rejected"):
        run(BufferInstagram, {**KEY, "BUFFER_CHANNEL_INSTAGRAM": "c"}, clip, override=failed)


def test_still_sending_is_recorded_as_handed_to_buffer(clip):
    def sending(req):
        if "PostStatus" in req.json["query"]:
            return HttpResponse.of_json(200, {"data": {"post": {"id": "dry-post", "status": "sending", "externalLink": None, "error": None}}})
        return None

    _, _, res = run(BufferTikTok, {**KEY, "BUFFER_CHANNEL_TIKTOK": "c"}, clip, override=sending)
    assert res.url == "buffer:dry-post" and "handed to Buffer" in res.note


def test_graphql_errors_and_missing_public_url(clip, tmp_path):
    def broken(req):
        return HttpResponse.of_json(200, {"errors": [{"message": "Unauthorized"}]})

    with pytest.raises(PublisherError, match="Unauthorized"):
        run(BufferLinkedIn, KEY, clip, override=broken)
    bare = Media.video(clip.path, 1080, 1920, 3.8)
    with pytest.raises(PublisherError, match="public URL"):
        run(BufferLinkedIn, KEY, bare)


HOST_ENV = {"PUBLISHER_MEDIA_REPO": "everfields/antisearch-clips", "PUBLISHER_MEDIA_TOKEN": "gh-token",
            "PUBLISHER_PUBLIC_BASE_URL": "https://everfields.github.io/antisearch-clips"}


def host_run(media, responses):
    seq = iter(responses)
    t = RecordingTransport(lambda req: next(seq))
    return GitHubPagesHost(t, HOST_ENV, sleep=lambda s: None), t


def test_host_commits_the_clip_and_waits_for_pages(clip):
    host, t = host_run(clip, [HttpResponse.of_json(404, {}), HttpResponse.of_json(201, {}),
                              HttpResponse(404), HttpResponse(200)])
    url = host.publish(clip)
    assert url == "https://everfields.github.io/antisearch-clips/clips/dog-1a2b3c4d.mp4"
    get, put, *heads = t.requests
    assert get.url == "https://api.github.com/repos/everfields/antisearch-clips/contents/clips/dog-1a2b3c4d.mp4"
    assert put.method == "PUT" and base64.b64decode(put.json["content"]) == clip.read()
    assert put.json["branch"] == "main" and put.headers["Authorization"] == "Bearer gh-token"
    assert [h.method for h in heads] == ["HEAD", "HEAD"]


def test_host_reuses_an_existing_file_and_fails_if_pages_never_serves(clip):
    host, t = host_run(clip, [HttpResponse.of_json(200, {"sha": "abc"}), HttpResponse(200)])
    host.publish(clip)
    assert [r.method for r in t.requests] == ["GET", "HEAD"]
    host, _ = host_run(clip, [HttpResponse.of_json(200, {})] + [HttpResponse(404)] * 40)
    with pytest.raises(PublisherError, match="not served"):
        host.publish(clip)


def test_native_is_the_default_and_buffer_is_one_switch():
    from antisearch_mill.publisher.linkedin import LinkedInAdapter
    from antisearch_mill.publisher.meta import InstagramAdapter
    from antisearch_mill.publisher.tiktok import TikTokAdapter

    native = resolve_adapters({})
    assert native["instagram"] is InstagramAdapter and native["linkedin"] is LinkedInAdapter
    assert native["tiktok"] is TikTokAdapter and all(a.route == "direct" for a in native.values())
    bridged = resolve_adapters({"PUBLISHER_BRIDGE": "buffer"})
    assert bridged["instagram"] is BufferInstagram and bridged["tiktok"] is BufferTikTok
    assert bridged["x"] is BufferX and bridged["bluesky"].route == "direct"
    mixed = resolve_adapters({"PUBLISHER_BRIDGE": "buffer", "PUBLISHER_ROUTE_INSTAGRAM": "direct"})
    assert mixed["instagram"] is InstagramAdapter and mixed["linkedin"] is BufferLinkedIn
    assert route_for("linkedin", {"PUBLISHER_ROUTE_LINKEDIN": "buffer"}) == "buffer"
    with pytest.raises(ValueError):
        route_for("bluesky", {"PUBLISHER_ROUTE_BLUESKY": "buffer"})
    with pytest.raises(ValueError):
        route_for("tiktok", {"PUBLISHER_BRIDGE": "hootsuite"})


def test_x_sends_plain_text_with_no_assets_and_refuses_media(clip):
    text = Media.text(label="thing")
    _, t, res = run(BufferX, {**KEY, "BUFFER_CHANNEL_X": "ch-x"}, text, "thing\nlove")
    payload = gql(t.requests[0])[1]["input"]
    assert payload["channelId"] == "ch-x" and payload["text"] == "thing\nlove"
    assert payload["assets"] == [] and "thumbnailOffset" not in json.dumps(payload)
    assert res.url == "https://twitter.dry.run/p/dry"
    with pytest.raises(PublisherError, match="cannot post video"):  # founder, 2026-09-29: never media on X
        run(BufferX, {**KEY, "BUFFER_CHANNEL_X": "c"}, clip, "thing\nlove")


def test_x_discovers_the_twitter_channel(clip):
    _, t, _ = run(BufferX, KEY, Media.text(label="thing"), "thing\nlove")
    payload = gql(t.requests[2])[1]["input"]
    assert payload["channelId"] == "ch-twitter"


def test_scheduled_post_uses_custom_time_and_skips_status_polls(clip):
    from datetime import datetime
    from zoneinfo import ZoneInfo

    a = BufferLinkedIn(None, {**KEY, "BUFFER_CHANNEL_LINKEDIN": "ch-li"}, sleep=lambda s: None)
    a.due_at = datetime(2026, 9, 26, 9, 7, tzinfo=ZoneInfo("Europe/Madrid"))
    a.transport = RecordingTransport(a.dry_run_responder)
    res = a.post(clip, "")
    (req,) = a.transport.requests
    payload = req.json["variables"]["input"]
    assert payload["mode"] == "customScheduled" and payload["dueAt"] == "2026-09-26T07:07:00.000Z"
    assert res.state == "scheduled" and "Europe/Madrid" in res.note


def test_places_map_country_rows_to_their_timezone():
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from antisearch_mill.publisher.places import local_morning_after, local_tz

    assert str(local_tz("employer in barcelona")) == "Europe/Madrid"
    assert str(local_tz("employer in new york")) == "America/New_York"
    assert local_tz("company to work for") is None and local_tz("employer in atlantis") is None
    ny = ZoneInfo("America/New_York")
    assert local_morning_after(datetime(2026, 9, 25, 9, 9, tzinfo=ny), ny) is None  # it's that morning: share now
    assert local_morning_after(datetime(2026, 9, 25, 9, 9, tzinfo=ny), ZoneInfo("Asia/Tokyo")) == \
        datetime(2026, 9, 26, 9, 7, tzinfo=ZoneInfo("Asia/Tokyo"))

