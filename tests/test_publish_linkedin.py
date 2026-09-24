import json
from pathlib import Path
from urllib.parse import urlsplit

from antisearch_mill.publish import publish_all
from antisearch_mill.publish.http import HttpResponse, RecordingTransport
from conftest import requires_ffmpeg

pytestmark = requires_ffmpeg

URN = "urn:li:video:C5F10AQTEST"


def sandbox(part_size=20_000, statuses=("PROCESSING", "AVAILABLE"), post_status=201):
    statuses = list(statuses)

    def respond(req):
        parts = urlsplit(req.url)
        if parts.path == "/rest/videos" and parts.query == "action=initializeUpload":
            size = req.json["initializeUploadRequest"]["fileSizeBytes"]
            instr = [
                {"uploadUrl": f"https://www.linkedin.com/dms-uploads/T/{i}", "firstByte": s,
                 "lastByte": min(s + part_size, size) - 1}
                for i, s in enumerate(range(0, size, part_size))
            ]
            return HttpResponse.of_json(200, {"value": {"video": URN, "uploadInstructions": instr, "uploadToken": "tok"}})
        if parts.netloc == "www.linkedin.com" and req.method == "PUT":
            return HttpResponse(200, {"ETag": f'"etag-{parts.path.rsplit("/", 1)[-1]}"'})
        if parts.path == "/rest/videos" and parts.query == "action=finalizeUpload":
            return HttpResponse(200)
        if parts.path.startswith("/rest/videos/"):
            return HttpResponse.of_json(200, {"id": URN, "status": statuses.pop(0)})
        if parts.path == "/rest/posts":
            if post_status != 201:
                return HttpResponse.of_json(post_status, {"message": "nope"})
            return HttpResponse(201, {"x-restli-id": "urn:li:share:123"})
        return HttpResponse.of_json(404, {})

    return RecordingTransport(respond)


def creds(monkeypatch):
    monkeypatch.setenv("LINKEDIN_ACCESS_TOKEN", "li-token")
    monkeypatch.setenv("LINKEDIN_AUTHOR_URN", "urn:li:organization:42")


def test_dry_run_plan(produced):
    (row,) = publish_all(produced, platforms={"linkedin"})
    assert row.status == "dry_run_ok"
    plan = json.loads(Path(row.artifact).read_text())
    methods = [(r["method"], urlsplit(r["url"]).path) for r in plan["requests"]]
    assert methods[0] == ("POST", "/rest/videos")
    assert methods[-1] == ("POST", "/rest/posts")
    assert (plan["media"]["width"], plan["media"]["height"]) == (1080, 1920)
    assert plan["credentials_missing"] == ["LINKEDIN_ACCESS_TOKEN", "LINKEDIN_AUTHOR_URN"]


def test_live_sandbox_multipart_upload(produced, monkeypatch):
    creds(monkeypatch)
    t = sandbox()
    (row,) = publish_all(produced, live=True, platforms={"linkedin"}, transport=t, sleep=lambda s: None)
    assert row.status == "published", row.detail
    assert row.remote_id == "urn:li:share:123"
    assert row.remote_url == "https://www.linkedin.com/feed/update/urn:li:share:123/"

    puts = [r for r in t.requests if r.method == "PUT"]
    size = Path(produced.clips()[0].clip_path).stat().st_size
    assert len(puts) >= 2
    assert sum(len(r.data) for r in puts) == size
    assert all("Authorization" not in r.headers for r in puts)

    api_calls = [r for r in t.requests if r.method != "PUT"]
    for r in api_calls:
        assert r.headers["Authorization"] == "Bearer li-token"
        assert r.headers["X-Restli-Protocol-Version"] == "2.0.0"
        assert r.headers["LinkedIn-Version"] == "202609"

    fin = next(r for r in t.requests if "finalizeUpload" in r.url).json["finalizeUploadRequest"]
    assert fin == {"video": URN, "uploadToken": "tok", "uploadedPartIds": [f"etag-{i}" for i in range(len(puts))]}

    post = t.requests[-1].json
    assert post["author"] == "urn:li:organization:42"
    assert post["content"] == {"media": {"id": URN}}
    assert post["lifecycleState"] == "PUBLISHED"


def test_processing_failure(produced, monkeypatch):
    creds(monkeypatch)
    t = sandbox(statuses=("PROCESSING_FAILED",))
    (row,) = publish_all(produced, live=True, platforms={"linkedin"}, transport=t, sleep=lambda s: None)
    assert row.status == "failed" and "processing failed" in row.detail
    assert not any(urlsplit(r.url).path == "/rest/posts" for r in t.requests)


def test_missing_credentials_skip(produced):
    t = sandbox()
    (row,) = publish_all(produced, live=True, platforms={"linkedin"}, transport=t, sleep=lambda s: None)
    assert row.status == "skipped_missing_credentials"
    assert t.requests == []
