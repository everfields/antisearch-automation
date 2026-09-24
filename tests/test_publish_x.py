import json
from pathlib import Path
from urllib.parse import urlsplit

from antisearch_mill.publish import publish_all
from antisearch_mill.publish.http import HttpResponse, RecordingTransport
from antisearch_mill.publish.x import oauth1_header
from conftest import requires_ffmpeg

X_CREDS = {
    "X_API_KEY": "ck", "X_API_KEY_SECRET": "cs", "X_ACCESS_TOKEN": "tk", "X_ACCESS_TOKEN_SECRET": "ts",
}


def test_oauth1_matches_x_reference_signature():
    # Example from X's "Creating a signature" docs.
    header = oauth1_header(
        "POST",
        "https://api.twitter.com/1.1/statuses/update.json?include_entities=true",
        consumer_key="xvz1evFS4wEEPTGEFPHBog",
        consumer_secret="kAcSOqF21Fu85e7zjz7ZN2U4ZRhfV3WpwPAoE3Z7kBw",
        token="370773112-GmHxMAgYyLbNEtIKZeRNFsMKPR9EyMZeS9weJAEb",
        token_secret="LswwdoUaIvS8ltyTt5jkRh4J50vUPVVHtR2YPi5kE",
        params={"status": "Hello Ladies + Gentlemen, a signed OAuth request!"},
        nonce="kYjzVBB8Y0ZFabxSWbWovY3uYSQ2pTgmZeNu2VS4cg",
        timestamp="1318622958",
    )
    assert 'oauth_signature="hCtSmYh%2BiHYCEqBWrE7C7hYmtUk%3D"' in header


def sandbox(processing_states=("in_progress", "succeeded"), tweet_status=201):
    """A scripted stand-in for api.x.com that behaves like the real flow."""
    states = list(processing_states)

    def respond(req):
        path = urlsplit(req.url).path
        if path == "/2/media/upload/initialize":
            return HttpResponse.of_json(200, {"data": {"id": "777", "expires_after_secs": 86400}})
        if path == "/2/media/upload/777/append":
            return HttpResponse(204)
        if path == "/2/media/upload/777/finalize":
            return HttpResponse.of_json(200, {"data": {"id": "777", "processing_info": {"state": "pending", "check_after_secs": 1}}})
        if path == "/2/media/upload":
            state = states.pop(0)
            return HttpResponse.of_json(200, {"data": {"processing_info": {"state": state, "check_after_secs": 1}}})
        if path == "/2/tweets":
            if tweet_status != 201:
                return HttpResponse.of_json(tweet_status, {"title": "Forbidden", "status": tweet_status})
            return HttpResponse.of_json(201, {"data": {"id": "1999", "text": ""}})
        return HttpResponse.of_json(404, {})

    return RecordingTransport(respond)


@requires_ffmpeg
def test_dry_run_plans_full_flow_without_credentials(produced):
    rows = publish_all(produced, platforms={"x"})
    (row,) = rows
    assert row.status == "dry_run_ok" and row.mode == "dry-run"
    assert "credentials missing" in row.detail
    plan = json.loads(Path(row.artifact).read_text())
    urls = [(r["method"], urlsplit(r["url"]).path) for r in plan["requests"]]
    assert urls[0] == ("POST", "/2/media/upload/initialize")
    assert urls[-1] == ("POST", "/2/tweets")
    assert all(r["headers"]["Authorization"] == "<redacted>" for r in plan["requests"])
    assert (plan["media"]["width"], plan["media"]["height"]) == (720, 1280)
    assert plan["capture"] == "synthetic-oracle"


@requires_ffmpeg
def test_live_sandbox_publishes_and_is_idempotent(produced, monkeypatch):
    for k, v in X_CREDS.items():
        monkeypatch.setenv(k, v)
    t = sandbox()
    (row,) = publish_all(produced, live=True, platforms={"x"}, transport=t, sleep=lambda s: None)
    assert row.status == "published", row.detail
    assert row.remote_id == "1999"
    assert row.remote_url == "https://x.com/i/web/status/1999"

    paths = [urlsplit(r.url).path for r in t.requests]
    assert paths == [
        "/2/media/upload/initialize", "/2/media/upload/777/append", "/2/media/upload/777/finalize",
        "/2/media/upload", "/2/media/upload", "/2/tweets",
    ]
    assert all(r.headers["Authorization"].startswith("OAuth ") for r in t.requests)
    init = t.requests[0].json
    assert init["media_type"] == "video/mp4" and init["media_category"] == "tweet_video"
    assert init["total_bytes"] == sum(len(f[1]) for r in t.requests for f in (r.files or {}).values())
    assert t.requests[-1].json == {"media": {"media_ids": ["777"]}}

    t2 = sandbox()
    (again,) = publish_all(produced, live=True, platforms={"x"}, transport=t2, sleep=lambda s: None)
    assert again.status == "skipped_already_published" and again.remote_id == "1999"
    assert t2.requests == []


@requires_ffmpeg
def test_live_caption_goes_into_text(produced, monkeypatch):
    monkeypatch.setenv("X_OAUTH2_ACCESS_TOKEN", "user-token")
    row = produced.clips()[0]
    row.caption = "gtm caption"
    produced.upsert_clip(row)
    t = sandbox(processing_states=("succeeded",))
    (res,) = publish_all(produced, live=True, platforms={"x"}, transport=t, sleep=lambda s: None)
    assert res.status == "published"
    assert t.requests[0].headers["Authorization"] == "Bearer user-token"
    assert t.requests[-1].json["text"] == "gtm caption"


@requires_ffmpeg
def test_live_without_credentials_is_skipped_not_crashed(produced):
    t = sandbox()
    (row,) = publish_all(produced, live=True, platforms={"x"}, transport=t, sleep=lambda s: None)
    assert row.status == "skipped_missing_credentials"
    assert "X_API_KEY" in row.detail
    assert t.requests == []


@requires_ffmpeg
def test_live_refuses_fixture_verdicts(produced, monkeypatch):
    for k, v in X_CREDS.items():
        monkeypatch.setenv(k, v)
    row = produced.clips()[0]
    row.oracle_source = "fixture"
    produced.upsert_clip(row)
    t = sandbox()
    (res,) = publish_all(produced, live=True, platforms={"x"}, transport=t, sleep=lambda s: None)
    assert res.status == "skipped_not_live_oracle"
    assert t.requests == []


@requires_ffmpeg
def test_live_api_error_is_logged_as_failed(produced, monkeypatch):
    for k, v in X_CREDS.items():
        monkeypatch.setenv(k, v)
    t = sandbox(processing_states=("succeeded",), tweet_status=403)
    (row,) = publish_all(produced, live=True, platforms={"x"}, transport=t, sleep=lambda s: None)
    assert row.status == "failed"
    assert "403" in row.detail
    assert produced.publish_rows()[-1]["status"] == "failed"
