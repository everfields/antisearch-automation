"""Adapters in go-live priority order (fastest to live without phone/business checks first)."""

from __future__ import annotations

from .base import Adapter
from .bluesky import BlueskyAdapter
from .linkedin import LinkedInAdapter
from .mastodon import MastodonAdapter
from .meta import InstagramAdapter, ThreadsAdapter
from .reddit import RedditAdapter
from .tiktok import TikTokAdapter

ADAPTERS: dict[str, type[Adapter]] = {
    a.name: a
    for a in (BlueskyAdapter, ThreadsAdapter, LinkedInAdapter, TikTokAdapter,
              InstagramAdapter, RedditAdapter, MastodonAdapter)
}
