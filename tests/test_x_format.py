"""X format A/B: alternate the silent video and the two-line text post, record the format, lock later."""

import csv
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from antisearch_mill.ledger import Job, Ledger
from antisearch_mill.publish.http import RecordingTransport
from antisearch_mill.publisher.buffer import BufferX
from antisearch_mill.publisher.guard import PostLog, PostRow, x_format, x_post_format
from antisearch_mill.publisher.media_host import GitHubPagesHost
from antisearch_mill.publisher.run import run_posts
from test_publisher_run import clip

ET = ZoneInfo("America/New_York")
ENV = {
    "BUFFER_API_KEY": "k", "BUFFER_CHANNEL_X": "ch-x", "PUBLISHER_MEDIA_REPO": "everfields/antisearch-clips",
    "PUBLISHER_MEDIA_TOKEN": "t", "PUBLISHER_PUBLIC_BASE_URL": "https://everfields.github.io/antisearch-clips",
    "PUBLISHER_LIVE_NETWORKS": "x", "PUBLISHER_CADENCE": "reach", "PUBLISHER_RAMP": "off", "PUBLISHER_JITTER": "off",
}


def test_flag_defaults_to_alternate_and_locks():
    assert x_format({}) == "alternate"
    assert x_format({"PUBLISHER_X_FORMAT": "Video"}) == "video"
    assert x_format({"PUBLISHER_X_FORMAT": "text"}) == "text"
    with pytest.raises(ValueError, match="PUBLISHER_X_FORMAT"):
        x_format({"PUBLISHER_X_FORMAT": "thread"})
    assert {x_post_format({"PUBLISHER_X_FORMAT": "video"}, date(2026, 9, 28), n) for n in (0, 1)} == {"video"}


def test_alternate_is_one_of_each_a_day_and_swaps_the_first_slot_daily():
    week = [date(2026, 9, 28) + timedelta(days=d) for d in range(7)]
    days = [(x_post_format({}, d, 0), x_post_format({}, d, 1)) for d in week]
    assert all(sorted(pair) == ["text", "video"] for pair in days)
    firsts = [pair[0] for pair in days]
    assert all(a != b for a, b in zip(firsts, firsts[1:]))  # the morning slot alternates too
    assert firsts.count("video") in (3, 4) and firsts.count("text") in (3, 4)


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


def test_a_week_of_alternate_posts_records_both_formats_in_posts_csv(tmp_path):
    ledger = Ledger(tmp_path / "out")
    log = PostLog(tmp_path / "state" / "posts.csv")
    seen = []
    posts = iter([("search engine", "kagi"), ("browser", "brave"), ("phone", "iphone 17 pro max"), ("programming language", "python")])
    for d in range(2):
        for hour, minute in ((9, 10), (16, 10)):
            now = datetime(2026, 9, 28, hour, minute, tzinfo=ET) + timedelta(days=d)
            category, verdict = next(posts)
            job = Job(f"p-{category.replace(' ', '-')}", category, ("x",), notes="pool:vertical")
            out, create, uploads = _run(tmp_path, ledger, log, job, now, ENV, verdict)
            assert out[0].status == "published", out[0].detail
            (payload,) = create
            if payload["assets"]:
                assert payload["assets"] == [{"video": {"url": payload["assets"][0]["video"]["url"]}}]
                assert payload["text"] == "" and uploads  # silent phone video, bare caption, clip hosted
                seen.append("video")
            else:
                assert payload["text"] == f"{category}\n{verdict}" and not uploads
                seen.append("text")
    assert seen.count("video") == 2 and seen.count("text") == 2
    assert seen[0] != seen[2]  # day two opens with the other format
    rows = [r for r in log.rows() if r["status"] == "published"]
    assert [r["format"] for r in rows] == seen
    assert all(r["format"] for r in log.rows())  # pending rows are tagged too


def test_locked_video_and_text(tmp_path):
    for mode in ("video", "text"):
        ledger = Ledger(tmp_path / mode / "out")
        log = PostLog(tmp_path / mode / "state" / "posts.csv")
        out, create, _ = _run(tmp_path, ledger, log, Job("p-a", "browser", ("x",)),
                              datetime(2026, 9, 28, 9, 10, tzinfo=ET), {**ENV, "PUBLISHER_X_FORMAT": mode})
        assert out[0].status == "published"
        assert bool(create[0]["assets"]) is (mode == "video")
        assert log.rows()[-1]["format"] == mode


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


def test_bad_x_format_fails_before_a_run(tmp_path, monkeypatch, capsys):
    from antisearch_mill.cli import main

    monkeypatch.setenv("PUBLISHER_X_FORMAT", "thread")
    code = main(["--env-file", str(tmp_path / "absent.env"), "--out", str(tmp_path / "out"), "post",
                 "--state", str(tmp_path / "posts.csv")])
    assert code == 2 and "PUBLISHER_X_FORMAT" in capsys.readouterr().err
