"""GitHub Pages resilience (founder, 2026-10-06): a TikTok failed when Pages did not serve its clip
within ~30 checks during an Actions incident. The host now waits up to 10 minutes per run with
backoff, and a Pages timeout leaves the job retryable on the next run instead of consuming it."""

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from antisearch_mill.ledger import Job, Ledger
from antisearch_mill.publish.http import HttpResponse, RecordingTransport
from antisearch_mill.publisher.base import Media, PublisherError
from antisearch_mill.publisher.buffer import BufferInstagram, BufferTikTok, BufferX
from antisearch_mill.publisher.guard import FAILED, PostLog
from antisearch_mill.publisher.media_host import (
    MAX_PAGES_RETRIES, PAGES_BUDGET_S, PAGES_POLL_MAX_S, GitHubPagesHost, PagesBudget, PagesNotServed,
)
from antisearch_mill.publisher.run import run_posts
from test_publisher_run import clip
from test_tags import BUFFER_ENV

ET = ZoneInfo("America/New_York")
NOW = datetime(2026, 9, 28, 13, 10, tzinfo=ET)  # TikTok's 13:07 slot (reach)


@pytest.fixture
def media(tmp_path):
    p = tmp_path / "dog-1a2b3c4d.mp4"
    p.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"v" * 64)
    return Media.video(p, 1080, 1920, 10.0)


def _host(heads, budget=None):
    seq = iter([HttpResponse.of_json(200, {"sha": "abc"})] + heads)
    t = RecordingTransport(lambda req: next(seq))
    slept: list[float] = []
    return GitHubPagesHost(t, BUFFER_ENV, sleep=slept.append, budget=budget), t, slept


def test_waits_up_to_ten_minutes_with_backoff_then_raises_retryable(media):
    host, t, slept = _host([HttpResponse(404)] * 200)
    with pytest.raises(PagesNotServed, match="retryable") as exc:
        host.publish(media)
    assert isinstance(exc.value, PublisherError) and exc.value.retryable
    assert sum(slept) == pytest.approx(PAGES_BUDGET_S)  # 10 minutes, not 5
    assert slept[:4] == [10.0, 15.0, 22.5, 33.75] and max(slept) <= PAGES_POLL_MAX_S  # backoff, capped
    assert len(slept) < 20  # far fewer checks than polling every 10 s
    assert PAGES_BUDGET_S <= 10 * 60 < 25 * 60  # inside the 25-minute job timeout


def test_late_pages_still_succeeds(media):
    host, _, slept = _host([HttpResponse(404)] * 8 + [HttpResponse(200)])
    assert host.publish(media).endswith("/clips/dog-1a2b3c4d.mp4")
    assert len(slept) == 8 and sum(slept) > 300  # served after more than the old 5-minute wait


def test_the_budget_is_shared_by_the_whole_run(media):
    budget = PagesBudget()
    first, _, slept1 = _host([HttpResponse(404)] * 200, budget)
    with pytest.raises(PagesNotServed):
        first.publish(media)
    second, t, slept2 = _host([HttpResponse(404)] * 5, budget)
    with pytest.raises(PagesNotServed):
        second.publish(media)
    assert slept2 == [] and [r.method for r in t.requests] == ["GET", "HEAD"]  # one check, no new wait


def _run(tmp_path, pages_ok: bool, now=NOW):
    env = {**BUFFER_ENV, "PUBLISHER_LIVE_NETWORKS": "tiktok"}
    ledger = Ledger(tmp_path / "out")
    log = PostLog(tmp_path / "state" / "posts.csv")
    job = Job("p-dry-shampoo", "dry shampoo", ("tiktok",), notes="pool:vertical")
    row = clip(ledger, job.id, verdict="k18")
    Path(row.clip_path).write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"v" * 200)
    host = GitHubPagesHost(None, env)

    def respond(req):
        if req.method == "HEAD" and not pages_ok:
            return HttpResponse(404)
        if host.handles(req):
            return host.dry_run_responder(req)
        return BufferTikTok(None, env).dry_run_responder(req)

    out = run_posts([job], ledger, log, now=now, live=True, transport=RecordingTransport(respond), env=env,
                    sleep=lambda _s: None, adapters={"instagram": BufferInstagram, "tiktok": BufferTikTok, "x": BufferX})
    return out, log


def test_a_pages_timeout_leaves_the_job_for_the_next_run(tmp_path):
    out, log = _run(tmp_path, pages_ok=False)
    assert [o.status for o in out] == [FAILED] and "not served by Pages" in out[0].detail
    out, log = _run(tmp_path, pages_ok=True, now=NOW.replace(minute=25))  # the next run (catch-up)
    assert [o.status for o in out] == ["published"]
    assert log.latest("p-dry-shampoo")["status"] == "published"


def test_after_max_retries_the_job_stays_failed(tmp_path):
    for _ in range(MAX_PAGES_RETRIES + 1):
        out, _ = _run(tmp_path, pages_ok=False)
        assert [o.status for o in out] == [FAILED]
    out, _ = _run(tmp_path, pages_ok=True)
    assert [o.status for o in out] == ["skipped_failed_before"]


def test_yesterdays_old_style_pages_failure_is_retryable_too(tmp_path):
    log = PostLog(tmp_path / "state" / "posts.csv")
    from antisearch_mill.publisher.guard import PostRow
    log.append(PostRow("p-dry-shampoo", "tiktok", "pending", at="2026-09-27T19:12:59+00:00", category="dry shampoo"))
    log.append(PostRow("p-dry-shampoo", "tiktok", FAILED, at="2026-09-27T19:12:59+00:00", category="dry shampoo",
                       detail="PublisherError: media host: https://x/clips/a.mp4 not served by Pages after 30 checks"))
    out, _ = _run(tmp_path, pages_ok=True)
    assert [o.status for o in out] == ["published"]


def test_other_failures_still_consume_the_job(tmp_path):
    log = PostLog(tmp_path / "state" / "posts.csv")
    from antisearch_mill.publisher.guard import PostRow
    log.append(PostRow("p-dry-shampoo", "tiktok", FAILED, at="2026-09-27T19:12:59+00:00", category="dry shampoo",
                       detail="PublisherError: buffer: tiktok rejected it: None"))
    out, _ = _run(tmp_path, pages_ok=True)
    assert [o.status for o in out] == ["skipped_failed_before"]
