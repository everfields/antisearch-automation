"""X is plain text only (founder, 2026-09-29): no alternation, no media, whatever PUBLISHER_X_FORMAT says."""

import csv
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from antisearch_mill.ledger import Job, Ledger
from antisearch_mill.publish.http import RecordingTransport
from antisearch_mill.publisher.buffer import BufferX
from antisearch_mill.publisher.guard import PostLog, PostRow
from antisearch_mill.publisher.media_host import GitHubPagesHost
from antisearch_mill.publisher.run import run_posts
from test_publisher_run import clip

ET = ZoneInfo("America/New_York")
ENV = {
    "BUFFER_API_KEY": "k", "BUFFER_CHANNEL_X": "ch-x", "PUBLISHER_MEDIA_REPO": "everfields/antisearch-clips",
    "PUBLISHER_MEDIA_TOKEN": "t", "PUBLISHER_PUBLIC_BASE_URL": "https://everfields.github.io/antisearch-clips",
    "PUBLISHER_LIVE_NETWORKS": "x", "PUBLISHER_CADENCE": "reach", "PUBLISHER_RAMP": "off", "PUBLISHER_JITTER": "off",
}


def _run(tmp_path, ledger, log, job, now, env, verdict="kagi"):
    row = clip(ledger, job.id, verdict=verdict)
    Path(row.clip_path).write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"v" * 200)
    host = GitHubPagesHost(None, env, sleep=lambda _s: None)
    t = RecordingTransport(lambda r: host.dry_run_responder(r) if host.handles(r) else BufferX(None, env).dry_run_responder(r))
    out = run_posts([job], ledger, log, now=now, live=True, transport=t, env=env, sleep=lambda _s: None,
                    adapters={"x": BufferX})
    create = [r.json["variables"]["input"] for r in t.requests if "createPost" in (r.json or {}).get("query", "")]
    uploads = [r for r in t.requests if "api.github.com" in r.url]
    return out, create, uploads


def test_every_x_post_is_plain_text_every_slot_every_day(tmp_path):
    ledger = Ledger(tmp_path / "out")
    log = PostLog(tmp_path / "state" / "posts.csv")
    posts = iter([("search engine", "kagi"), ("browser", "brave"), ("phone", "iphone 17 pro max"),
                  ("programming language", "python")])
    for d in range(2):
        for hour, minute in ((9, 10), (16, 10)):
            now = datetime(2026, 9, 28, hour, minute, tzinfo=ET) + timedelta(days=d)
            category, verdict = next(posts)
            job = Job(f"p-{category.replace(' ', '-')}", category, ("x",), notes="pool:vertical")
            out, create, uploads = _run(tmp_path, ledger, log, job, now, ENV, verdict)
            assert out[0].status == "published", out[0].detail
            (payload,) = create
            assert payload["assets"] == [] and not uploads  # no media, nothing hosted
            assert payload["text"] == f"{category}\n{verdict}"
    rows = [r for r in log.rows() if r["status"] == "published"]
    assert [r["format"] for r in rows] == ["text"] * 4


@pytest.mark.parametrize("old", ["video", "alternate", "text", "thread"])
def test_the_old_format_switch_no_longer_changes_anything(tmp_path, old):
    ledger = Ledger(tmp_path / "out")
    log = PostLog(tmp_path / "state" / "posts.csv")
    out, create, uploads = _run(tmp_path, ledger, log, Job("p-a", "browser", ("x",)),
                                datetime(2026, 9, 28, 9, 10, tzinfo=ET), {**ENV, "PUBLISHER_X_FORMAT": old})
    assert out[0].status == "published" and create[0]["assets"] == [] and not uploads
    assert log.rows()[-1]["format"] == "text"


def test_the_x_route_takes_text_only_and_needs_no_media_host():
    from antisearch_mill.publisher.base import Media, VIDEO

    assert BufferX.kinds == frozenset({"text"})
    assert BufferX.missing({"BUFFER_API_KEY": "k"}) == []
    with pytest.raises(Exception, match="plain text only"):
        BufferX(None, ENV)._post(Media.video("x.mp4", 1080, 1920, 5.0), "browser\nbrave")
    assert VIDEO not in BufferX.kinds


def test_an_old_posts_csv_grows_the_new_columns_once(tmp_path):
    path = tmp_path / "posts.csv"
    path.write_text("job_id,network,status,clip_id,verdict,remote_id,url,detail,at,category\n"
                    "s-red-flag,tiktok,published,c1,controlling behavior,b1,buffer:b1,,2026-09-26T17:18:28+00:00,red flag\n",
                    encoding="utf-8")
    log = PostLog(path)
    log.append(PostRow("p-a", "x", "published", "c2", "kagi", at="2026-09-28T13:10:00+00:00", category="search engine",
                       caption="search engine\nkagi", format="text"))
    with path.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert list(rows[0]) == ["job_id", "network", "status", "clip_id", "verdict", "remote_id", "url", "detail", "at",
                             "category", "caption", "format"]
    assert rows[0]["verdict"] == "controlling behavior" and rows[0]["format"] == ""
    assert (rows[1]["format"], rows[1]["caption"]) == ("text", "search engine\nkagi")
    log.append(PostRow("p-b", "x", "pending", format="video"))
    assert path.read_text(encoding="utf-8").count("job_id") == 1
