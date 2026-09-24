import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from antisearch_mill.cli import main
from antisearch_mill.publish.http import HttpResponse, RecordingTransport
from antisearch_mill.publisher import oauth
from antisearch_mill.publisher.base import PublisherError
from conftest import ROOT, requires_ffmpeg


def test_tiktok_authorize_url():
    url = oauth.authorize_url("tiktok", {"TIKTOK_CLIENT_KEY": "ck"}, state="s1")
    q = {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}
    assert url.startswith("https://www.tiktok.com/v2/auth/authorize/?")
    assert q == {"client_key": "ck", "response_type": "code", "scope": "user.info.basic,video.upload",
                 "redirect_uri": "https://antisearch.ai/", "state": "s1"}


def test_code_from_pasted_url_or_bare_code():
    assert oauth.code_from("https://antisearch.ai/?code=abc%2A%211&state=s") == "abc*!1"
    assert oauth.code_from("abc%2A") == "abc*"
    with pytest.raises(PublisherError, match="refused"):
        oauth.code_from("https://antisearch.ai/?error=access_denied&error_description=user+said+no")


def test_linkedin_exchange_posts_form_fields():
    t = RecordingTransport(lambda req: HttpResponse.of_json(200, {"access_token": "at", "expires_in": 5183999}))
    env = {"LINKEDIN_CLIENT_ID": "cid", "LINKEDIN_CLIENT_SECRET": "sec"}
    body = oauth.exchange("linkedin", "https://antisearch.ai/?code=C0DE&state=x", env, t)
    assert body["access_token"] == "at"
    req = t.requests[0]
    assert req.url == "https://www.linkedin.com/oauth/v2/accessToken"
    assert req.headers["Content-Type"] == "application/x-www-form-urlencoded"
    assert {k: v[0] for k, v in parse_qs(req.data.decode()).items()} == {
        "client_id": "cid", "client_secret": "sec", "code": "C0DE",
        "grant_type": "authorization_code", "redirect_uri": "https://antisearch.ai/"}


def test_exchange_failure_is_clear():
    t = RecordingTransport(lambda req: HttpResponse.of_json(400, {"error": "invalid_grant"}))
    with pytest.raises(PublisherError, match="invalid_grant"):
        oauth.exchange("tiktok", "x", {"TIKTOK_CLIENT_KEY": "k", "TIKTOK_CLIENT_SECRET": "s"}, t)


def test_networks_lists_every_adapter(tmp_path, capsys):
    assert main(["--env-file", str(tmp_path / "none"), "networks"]) == 0
    out = capsys.readouterr().out
    for name in ("bluesky", "threads", "linkedin", "tiktok", "instagram", "reddit", "mastodon"):
        assert name in out
    assert "BLOCKED" in out


@requires_ffmpeg
def test_post_dry_run_end_to_end(tmp_path, capsys, monkeypatch):
    queue = tmp_path / "q.csv"
    queue.write_text(
        "id,category,platforms,caption\n"
        "thing,thing,bluesky,@antisearch.ai\n"
        "dry-shampoo,dry shampoo,tiktok,\n"
        "pizza,pizza,linkedin,\n"
        "espresso-machine,espresso machine,x,\n",
        encoding="utf-8",
    )
    out = tmp_path / "out"
    base = ["--env-file", str(tmp_path / "none"), "--out", str(out)]
    no_pools = tmp_path / "no-pools"
    no_pools.mkdir()
    args = ["post", "--queue", str(queue), "--pools", str(no_pools), "--oracle", "fixture",
            "--fixtures", str(ROOT / "fixtures" / "oracle_fixtures.json")]
    assert main(base + args) == 0
    capsys.readouterr()
    plans = sorted(p.relative_to(out).as_posix() for p in (out / "dry_run_posts").rglob("*.json"))
    assert plans == ["dry_run_posts/bluesky/thing.json", "dry_run_posts/linkedin/pizza.json",
                     "dry_run_posts/tiktok/dry-shampoo.json"]
    tiktok = json.loads((out / "dry_run_posts" / "tiktok" / "dry-shampoo.json").read_text())
    assert tiktok["route"] == "buffer" and tiktok["media"]["public_url"].endswith("/clips/" + Path(tiktok["media"]["path"]).name)
    bsky = json.loads((out / "dry_run_posts" / "bluesky" / "thing.json").read_text())
    assert bsky["caption"] == "@antisearch.ai" and bsky["oracle_source"] == "fixture"
    assert Path(bsky["media"]["path"]).is_file()
    assert not (out / "posts.csv").exists()

    # live with a fixture oracle: approval + creds present, still refused
    for k, v in {"PUBLISHER_LIVE_NETWORKS": "bluesky", "BLUESKY_HANDLE": "h", "BLUESKY_APP_PASSWORD": "p"}.items():
        monkeypatch.setenv(k, v)
    assert main(base + args + ["--live", "--ignore-slots", "--network", "bluesky"]) == 0
    assert "skipped_not_live_oracle" in capsys.readouterr().out
    assert not (out / "posts.csv").exists()


def test_due_is_the_cheap_precheck_for_the_hourly_cron(tmp_path, monkeypatch, capsys):
    from datetime import datetime
    from zoneinfo import ZoneInfo

    import antisearch_mill.publisher.guard as guard

    base = ["--env-file", str(tmp_path / "none"), "due", "--state", str(tmp_path / "posts.csv")]
    monkeypatch.setattr(guard, "now_et", lambda: datetime(2026, 11, 2, 8, 30, tzinfo=ZoneInfo("America/New_York")))
    assert main(base) == 3  # nothing approved
    monkeypatch.setenv("PUBLISHER_LIVE_NETWORKS", "bluesky,tiktok")
    assert main(base) == 3  # 08:30 ET: before the posting day starts
    monkeypatch.setattr(guard, "now_et", lambda: datetime(2026, 11, 2, 9, 7, tzinfo=ZoneInfo("America/New_York")))
    capsys.readouterr()
    assert main(base) == 0
    out = capsys.readouterr().out
    assert "due: bluesky" in out and "tiktok" in out.splitlines()[1] and "0 due" in out.splitlines()[1]
