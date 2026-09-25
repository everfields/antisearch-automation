"""Each own-publisher adapter against a mocked HTTP API (no network, no tokens)."""

import dataclasses
import json
from urllib.parse import parse_qs, urlsplit

import pytest

from antisearch_mill.publish.http import HttpResponse, RecordingTransport
from antisearch_mill.publisher import ADAPTERS, Media, PublisherError
from antisearch_mill.publisher.base import DRAFTED, PUBLISHED
from antisearch_mill.publisher.bluesky import BlueskyAdapter, mention_facets
from antisearch_mill.publisher.linkedin import LinkedInAdapter
from antisearch_mill.publisher.mastodon import MastodonAdapter
from antisearch_mill.publisher.meta import InstagramAdapter, ThreadsAdapter
from antisearch_mill.publisher.reddit import RedditAdapter
from antisearch_mill.publisher.tiktok import TikTokAdapter


@pytest.fixture
def video(tmp_path):
    clip = tmp_path / "thing-abc123.mp4"
    clip.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"v" * 5000)
    poster = tmp_path / "thing-abc123.png"
    poster.write_bytes(b"\x89PNG\r\n\x1a\n" + b"p" * 800)
    return Media.video(clip, 1080, 1920, 3.8, poster=poster, label="thing")


@pytest.fixture
def image(video):
    return Media.image(video.poster, 1080, 1920, label="thing")


def run(cls, env, media, caption="", override=None, key=""):
    a = cls(None, env, sleep=lambda s: None, now=lambda: 1_790_000_000.0, idempotency_key=key)
    base = a.dry_run_responder

    def respond(req):
        got = override(req) if override else None
        return got if got is not None else base(req)

    t = RecordingTransport(respond)
    a.transport = t
    return a, t, a.post(media, caption)


def path(req):
    return urlsplit(req.url).path


def form(req):
    return {k: v[0] for k, v in parse_qs(req.data.decode()).items()}


BSKY = {"BLUESKY_HANDLE": "antisearch.ai", "BLUESKY_APP_PASSWORD": "app-pass"}


def test_bluesky_video_goes_through_the_video_service(video):
    _, t, res = run(BlueskyAdapter, BSKY, video, "@antisearch.ai")
    steps = [(r.method, urlsplit(r.url).netloc, path(r).rsplit("/", 1)[-1]) for r in t.requests]
    assert steps == [
        ("POST", "bsky.social", "com.atproto.server.createSession"),
        ("GET", "pds.dry.run", "com.atproto.server.getServiceAuth"),
        ("POST", "video.bsky.app", "app.bsky.video.uploadVideo"),
        ("GET", "video.bsky.app", "app.bsky.video.getJobStatus"),
        ("POST", "pds.dry.run", "com.atproto.repo.createRecord"),
    ]
    auth = t.requests[1].params
    assert auth["aud"] == "did:web:pds.dry.run" and auth["lxm"] == "com.atproto.repo.uploadBlob"
    upload = t.requests[2]
    assert upload.headers["Authorization"] == "Bearer service-token"
    assert upload.params == {"did": "did:plc:dryrun", "name": "thing-abc123.mp4"}
    assert upload.data == video.read()
    record = t.requests[-1].json["record"]
    assert record["embed"]["$type"] == "app.bsky.embed.video"
    assert record["embed"]["aspectRatio"] == {"width": 1080, "height": 1920}
    assert record["text"] == "@antisearch.ai"
    assert record["facets"][0]["index"] == {"byteStart": 0, "byteEnd": 14}
    assert record["facets"][0]["features"][0]["did"] == "did:plc:dryrun"
    assert res.url == "https://bsky.app/profile/antisearch.ai/post/3dryrun" and res.state == PUBLISHED
    assert "app-pass" not in json.dumps(t.plan())


def test_bluesky_already_processed_video_reuses_blob(video):
    def override(req):
        if path(req).endswith("uploadVideo"):
            return HttpResponse.of_json(409, {"error": "already_exists", "jobId": "j", "blob": {"ref": "old"}})
        return None

    _, t, _ = run(BlueskyAdapter, BSKY, video, override=override)
    assert not any(path(r).endswith("getJobStatus") for r in t.requests)
    assert t.requests[-1].json["record"]["embed"]["video"] == {"ref": "old"}


def test_bluesky_video_needs_confirmed_email(video):
    def override(req):
        if path(req).endswith("createSession"):
            return HttpResponse.of_json(200, {"did": "did:plc:x", "handle": "h", "accessJwt": "j", "emailConfirmed": False})
        return None

    with pytest.raises(PublisherError, match="confirmed account email"):
        run(BlueskyAdapter, BSKY, video, override=override)


def test_bluesky_takes_only_the_frozen_clip(image, tmp_path):
    with pytest.raises(PublisherError, match="cannot post image"):
        run(BlueskyAdapter, BSKY, image)
    long = Media.video(tmp_path / "x.mp4", 1080, 1920, 8.5)
    (tmp_path / "x.mp4").write_bytes(b"v")
    with pytest.raises(PublisherError, match="9:16"):
        run(BlueskyAdapter, BSKY, long)
    square = Media.video(tmp_path / "x.mp4", 1080, 1080, 3.8)
    with pytest.raises(PublisherError, match="9:16"):
        run(BlueskyAdapter, BSKY, square)


def test_bluesky_brand_tag_becomes_a_real_mention(video):
    _, t, _ = run(BlueskyAdapter, BSKY, video, "@1password.com")
    resolve = next(r for r in t.requests if path(r).endswith("resolveHandle"))
    assert resolve.params == {"handle": "1password.com"} and urlsplit(resolve.url).netloc == "bsky.social"
    facet = t.requests[-1].json["record"]["facets"][0]
    assert facet["index"] == {"byteStart": 0, "byteEnd": 14}
    assert facet["features"][0]["did"] == "did:plc:dryrunbrand"


def test_bluesky_refuses_a_dead_tag(video):
    def override(req):
        if path(req).endswith("resolveHandle"):
            return HttpResponse.of_json(400, {"error": "InvalidRequest", "message": "Unable to resolve handle"})
        return None

    with pytest.raises(PublisherError, match="does not resolve"):
        _, t, _ = run(BlueskyAdapter, BSKY, video, "@notacompany.example", override=override)


def test_mention_facets_use_utf8_byte_offsets():
    assert mention_facets("ñ @a.b", {"a.b": "did:x"})[0]["index"] == {"byteStart": 3, "byteEnd": 7}
    assert mention_facets("thing", {"a.b": "did:x"}) == []


META = {"PUBLISHER_PUBLIC_BASE_URL": "https://media.antisearch.example/clips/"}


def test_threads_container_polls_then_publishes(video):
    states = iter(["IN_PROGRESS", "IN_PROGRESS", "FINISHED"])

    def override(req):
        if req.method == "GET" and req.params.get("fields", "").startswith("status"):
            return HttpResponse.of_json(200, {"status": next(states)})
        return None

    env = {**META, "THREADS_USER_ID": "42", "THREADS_ACCESS_TOKEN": "th-token"}
    _, t, res = run(ThreadsAdapter, env, video, "thing", override=override)
    create = t.requests[0]
    assert path(create) == "/v1.0/42/threads"
    assert create.params["media_type"] == "VIDEO"
    assert create.params["video_url"] == "https://media.antisearch.example/clips/thing-abc123.mp4"
    assert create.params["text"] == "thing"
    assert sum(1 for r in t.requests if r.params.get("fields", "").startswith("status")) == 3
    publish = next(r for r in t.requests if path(r).endswith("threads_publish"))
    assert publish.params["creation_id"] == "17890000000000001"
    assert res.url == "https://threads.dry.run/p/dry-run"
    assert "th-token" not in json.dumps(t.plan())


def test_instagram_reels_and_error_state(video):
    env = {**META, "INSTAGRAM_BUSINESS_ACCOUNT_ID": "17841", "INSTAGRAM_ACCESS_TOKEN": "ig"}
    hosted = dataclasses.replace(video, public_url="https://everfields.github.io/antisearch-clips/clips/thing-abc123.mp4")
    _, t, _ = run(InstagramAdapter, env, hosted, "@antisearch")
    create = t.requests[0].params
    assert t.requests[0].url == "https://graph.instagram.com/v24.0/17841/media"
    assert create["media_type"] == "REELS" and create["caption"] == "@antisearch"
    assert create["video_url"] == hosted.public_url and create["share_to_feed"] == "true" and create["thumb_offset"] == "3500"

    def failing(req):
        if req.method == "GET" and req.params.get("fields", "").startswith("status_code"):
            return HttpResponse.of_json(200, {"status_code": "ERROR", "error_message": "bad codec"})
        return None

    with pytest.raises(PublisherError, match="bad codec"):
        run(InstagramAdapter, env, video, override=failing)


def test_meta_needs_a_public_base_url(video):
    with pytest.raises(PublisherError, match="PUBLISHER_PUBLIC_BASE_URL"):
        run(ThreadsAdapter, {"THREADS_USER_ID": "1", "THREADS_ACCESS_TOKEN": "t"}, video)


def test_instagram_is_reels_only(image):
    with pytest.raises(PublisherError, match="cannot post image"):
        run(InstagramAdapter, {**META, "INSTAGRAM_BUSINESS_ACCOUNT_ID": "1", "INSTAGRAM_ACCESS_TOKEN": "t"}, image)


def test_linkedin_posts_as_the_antisearch_page_by_default(video):
    _, t, _ = run(LinkedInAdapter, {"LINKEDIN_ACCESS_TOKEN": "li"}, video)
    assert t.requests[0].json["initializeUploadRequest"]["owner"] == "urn:li:organization:99258814"
    assert t.requests[-1].json["author"] == "urn:li:organization:99258814"
    _, t, _ = run(LinkedInAdapter, {"LINKEDIN_ACCESS_TOKEN": "li", "LINKEDIN_ORGANIZATION_ID": "42"}, video)
    assert t.requests[-1].json["author"] == "urn:li:organization:42"


def test_linkedin_image_post(image):
    env = {"LINKEDIN_ACCESS_TOKEN": "li", "LINKEDIN_AUTHOR_URN": "urn:li:organization:9"}
    _, t, res = run(LinkedInAdapter, env, image)
    assert [path(r) for r in t.requests][0] == "/rest/images"
    put = t.requests[1]
    assert put.method == "PUT" and put.headers["Content-Type"] == "image/png" and "Authorization" not in put.headers
    post = t.requests[-1].json
    assert post["author"] == "urn:li:organization:9"
    assert post["content"] == {"media": {"id": "urn:li:image:C5F10AQDRYRUN00"}}
    assert res.url == "https://www.linkedin.com/feed/update/urn:li:share:dry-run/"


def test_linkedin_refresh_token_mints_access_token(video):
    env = {"LINKEDIN_REFRESH_TOKEN": "r", "LINKEDIN_CLIENT_ID": "cid", "LINKEDIN_CLIENT_SECRET": "sec",
           "LINKEDIN_AUTHOR_URN": "urn:li:person:abc"}

    def override(req):
        if path(req) == "/oauth/v2/accessToken":
            return HttpResponse.of_json(200, {"access_token": "fresh", "expires_in": 5183999})
        return None

    _, t, _ = run(LinkedInAdapter, env, video, override=override)
    assert form(t.requests[0]) == {"grant_type": "refresh_token", "refresh_token": "r",
                                   "client_id": "cid", "client_secret": "sec"}
    assert t.requests[1].headers["Authorization"] == "Bearer fresh"


TIKTOK = {"TIKTOK_CLIENT_KEY": "ck", "TIKTOK_CLIENT_SECRET": "cs", "TIKTOK_REFRESH_TOKEN": "rt"}


def test_tiktok_inbox_draft_is_the_default(video):
    a, t, res = run(TikTokAdapter, TIKTOK, video, "@antisearch")
    assert [path(r) for r in t.requests] == [
        "/v2/oauth/token/", "/v2/post/publish/inbox/video/init/", "/video/", "/v2/post/publish/status/fetch/",
    ]
    assert form(t.requests[0])["grant_type"] == "refresh_token"
    size = video.size
    assert t.requests[1].json == {"source_info": {"source": "FILE_UPLOAD", "video_size": size,
                                                  "chunk_size": size, "total_chunk_count": 1}}
    put = t.requests[2]
    assert put.headers["Content-Range"] == f"bytes 0-{size - 1}/{size}" and put.data == video.read()
    assert t.requests[1].headers["Authorization"] == "Bearer act.dry"
    assert res.state == DRAFTED and "tap Post" in res.note
    assert any("rotated" in w for w in a.warnings)


def test_tiktok_direct_is_self_only_until_audited(video):
    env = {**TIKTOK, "TIKTOK_MODE": "direct"}
    _, t, res = run(TikTokAdapter, env, video, "@antisearch")
    init = next(r for r in t.requests if path(r) == "/v2/post/publish/video/init/")
    assert init.json["post_info"]["privacy_level"] == "SELF_ONLY"
    assert init.json["post_info"]["title"] == "@antisearch"
    assert res.state == PUBLISHED and "SELF_ONLY" in res.note

    with pytest.raises(PublisherError, match="not offered"):
        run(TikTokAdapter, {**env, "TIKTOK_PRIVACY_LEVEL": "PUBLIC_TO_EVERYONE"}, video)


def test_tiktok_api_error_and_video_only(video, image):
    def override(req):
        if path(req).endswith("/inbox/video/init/"):
            return HttpResponse.of_json(200, {"error": {"code": "spam_risk_too_many_pending_share", "message": "5 max"}})
        return None

    with pytest.raises(PublisherError, match="spam_risk"):
        run(TikTokAdapter, TIKTOK, video, override=override)
    with pytest.raises(PublisherError, match="cannot post image"):
        run(TikTokAdapter, TIKTOK, image)


REDDIT = {"REDDIT_CLIENT_ID": "id", "REDDIT_CLIENT_SECRET": "sec", "REDDIT_USERNAME": "antisearch", "REDDIT_PASSWORD": "pw"}


def test_reddit_video_upload_then_submit(video):
    _, t, res = run(RedditAdapter, REDDIT, video)
    token = t.requests[0]
    assert token.headers["Authorization"].startswith("Basic ") and form(token)["grant_type"] == "password"
    s3 = [r for r in t.requests if "amazonaws" in r.url]
    assert len(s3) == 2 and list(s3[0].files) == ["file"] and s3[0].form["key"] == "rte_images/dryrun"
    submit = form(t.requests[-1])
    assert submit["kind"] == "video" and submit["sr"] == "u_antisearch" and submit["title"] == "thing"
    assert submit["url"].startswith("https://") and submit["video_poster_url"].startswith("https://")
    assert t.requests[-1].headers["User-Agent"].startswith("antisearch-publisher")
    assert res.url == "https://www.reddit.com/user/antisearch/submitted/"
    assert "pw" not in json.dumps(t.plan())


def test_reddit_submit_errors_raise(video):
    def override(req):
        if path(req) == "/api/submit":
            return HttpResponse.of_json(200, {"json": {"errors": [["SUBREDDIT_NOTALLOWED", "no", "sr"]]}})
        return None

    with pytest.raises(PublisherError, match="SUBREDDIT_NOTALLOWED"):
        run(RedditAdapter, REDDIT, video, override=override)


def test_mastodon_waits_for_media_and_sends_idempotency_key(video):
    polls = iter([HttpResponse.of_json(206, {"id": "1", "url": None}),
                  HttpResponse.of_json(200, {"id": "1", "url": "https://files/x.mp4"})])

    def override(req):
        if path(req).startswith("/api/v1/media/"):
            return next(polls)
        return None

    env = {"MASTODON_BASE_URL": "https://mastodon.social/", "MASTODON_ACCESS_TOKEN": "tok"}
    _, t, res = run(MastodonAdapter, env, video, "thing", override=override, key="antisearch-thing")
    assert list(t.requests[0].files) == ["file"]
    assert sum(1 for r in t.requests if path(r).startswith("/api/v1/media/")) == 2
    status = t.requests[-1]
    assert status.headers["Idempotency-Key"] == "antisearch-thing"
    assert status.json == {"status": "thing", "media_ids": ["110000000000000001"], "visibility": "public"}
    assert res.url.endswith("/110000000000000002")


@pytest.mark.parametrize("name", list(ADAPTERS))
def test_every_dry_run_responder_completes_a_video_post(name, video):
    cls = ADAPTERS[name]
    _, _, res = run(cls, cls.placeholder_env(), video)
    assert res.url and res.remote_id


def test_priority_order():
    assert list(ADAPTERS) == ["bluesky", "threads", "linkedin", "tiktok", "instagram", "reddit", "mastodon"]
