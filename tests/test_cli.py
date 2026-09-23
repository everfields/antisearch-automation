import csv
import json
import os

import pytest

from antisearch_mill.cli import main
from conftest import ROOT, requires_ffmpeg


@requires_ffmpeg
def test_offline_end_to_end_dry_run(tmp_path, capsys):
    out = str(tmp_path / "out")
    queue = str(ROOT / "queue" / "sample_queue.csv")
    fixtures = str(ROOT / "fixtures" / "oracle_fixtures.json")
    no_env = str(tmp_path / "absent.env")

    base = ["--env-file", no_env, "--out", out]
    assert main(base + ["produce", "--queue", queue, "--oracle", "fixture", "--fixtures", fixtures, "--limit", "2"]) == 0
    assert main(base + ["publish"]) == 0
    assert main(base + ["verify"]) == 0
    assert main(base + ["status"]) == 0
    assert main(base + ["sheet"]) == 0

    with open(os.path.join(out, "clips.csv"), newline="") as fh:
        clips = list(csv.DictReader(fh))
    assert len(clips) == 2
    for c in clips:
        assert c["capture"] == "synthetic-oracle"
        assert c["oracle_source"] == "fixture"
        assert os.path.isfile(c["clip_path"]) and os.path.isfile(c["poster_path"])
        assert float(c["duration_s"]) <= 4.0
        assert (c["width"], c["height"]) == ("1080", "1920")

    with open(os.path.join(out, "publish.csv"), newline="") as fh:
        pubs = list(csv.DictReader(fh))
    assert {(p["platform"], p["status"]) for p in pubs} == {
        ("x", "dry_run_ok"), ("linkedin", "dry_run_ok"),
        ("tiktok", "draft_logged"), ("instagram", "draft_logged"),
    }
    assert len(pubs) == 8

    events = [json.loads(l) for l in open(os.path.join(out, "logs", "mill.jsonl"))]
    assert events and all(e["capture"] == "synthetic-oracle" for e in events)

    capsys.readouterr()
    assert main(base + ["produce", "--queue", queue, "--oracle", "fixture", "--fixtures", fixtures, "--limit", "2"]) == 0
    assert "skipped" in capsys.readouterr().out

    # Fixture verdicts are never published live, credentials or not.
    assert main(base + ["publish", "--live", "--platform", "x"]) == 0
    with open(os.path.join(out, "publish.csv"), newline="") as fh:
        last = list(csv.DictReader(fh))[-2:]
    assert {p["status"] for p in last} == {"skipped_not_live_oracle"}


def test_publish_without_clips_is_a_clear_error(tmp_path, capsys):
    assert main(["--env-file", str(tmp_path / "x"), "--out", str(tmp_path), "publish"]) == 2
    assert "run `mill produce` first" in capsys.readouterr().err


def test_bad_queue_is_a_clear_error(tmp_path, capsys):
    q = tmp_path / "q.csv"
    q.write_text("id,category\nbad id,x\n")
    assert main(["--env-file", str(tmp_path / "x"), "--out", str(tmp_path), "produce", "--queue", str(q)]) == 2
    assert "bad id" in capsys.readouterr().err


def test_dotenv_loader(tmp_path, monkeypatch):
    from antisearch_mill.config import load_dotenv

    env = tmp_path / ".env"
    env.write_text("# c\nexport MILL_T1='a b'\nMILL_T2=\"x\"\nMILL_T3=kept\n")
    monkeypatch.setenv("MILL_T3", "already")
    for k in ("MILL_T1", "MILL_T2"):
        monkeypatch.delenv(k, raising=False)
    load_dotenv(env)
    assert os.environ["MILL_T1"] == "a b"
    assert os.environ["MILL_T2"] == "x"
    assert os.environ["MILL_T3"] == "already"
    for k in ("MILL_T1", "MILL_T2"):
        monkeypatch.delenv(k)


@pytest.mark.skipif(os.environ.get("MILL_TEST_NETWORK") != "1", reason="set MILL_TEST_NETWORK=1 to hit the live oracle")
def test_live_oracle_round_trip():
    from antisearch_mill.oracle import LiveOracle

    v = LiveOracle("https://antisearch.ai/verdict").ask("best running shoes")
    assert v.source == "live" and v.verdict and v.verdict == v.verdict.lower()
