#!/usr/bin/env python3
"""Fetch public TikTok profile fields from the profile page JSON (no login)."""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass

import requests

UA = {"User-Agent": "Mozilla/5.0 (compatible; antisearch-mill/0.1; +https://github.com/everfields)"}


@dataclass(frozen=True)
class Profile:
    handle: str
    unique_id: str
    nickname: str
    verified: bool
    follower_count: int | None
    error: str | None = None


def fetch_profile(handle: str, session: requests.Session | None = None) -> Profile:
    h = handle.lstrip("@").strip()
    sess = session or requests.Session()
    url = f"https://www.tiktok.com/@{h}"
    try:
        r = sess.get(url, headers=UA, timeout=25)
        r.raise_for_status()
    except requests.RequestException as exc:
        return Profile(h, h, "", False, None, str(exc))
    m = re.search(
        r'<script id="__UNIVERSAL_DATA_FOR_REHYDRATION__"[^>]*>(.*?)</script>',
        r.text,
        re.DOTALL,
    )
    if not m:
        return Profile(h, h, "", False, None, "no rehydration json")
    try:
        data = json.loads(m.group(1))
        user = (
            data.get("__DEFAULT_SCOPE__", {})
            .get("webapp.user-detail", {})
            .get("userInfo", {})
            .get("user", {})
        )
        stats = (
            data.get("__DEFAULT_SCOPE__", {})
            .get("webapp.user-detail", {})
            .get("userInfo", {})
            .get("stats", {})
        )
        if not user:
            return Profile(h, h, "", False, None, "user block missing (404 or private)")
        return Profile(
            h,
            str(user.get("uniqueId") or h),
            str(user.get("nickname") or ""),
            bool(user.get("verified")),
            int(stats.get("followerCount")) if stats.get("followerCount") is not None else None,
        )
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        return Profile(h, h, "", False, None, f"parse error: {exc}")


def main(argv: list[str] | None = None) -> int:
    for arg in (argv or sys.argv[1:]):
        p = fetch_profile(arg)
        print(json.dumps(p.__dict__, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
