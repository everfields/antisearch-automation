"""Adapters in go-live priority order, and the route each network takes."""

from __future__ import annotations

from typing import Mapping

from .base import Adapter
from .bluesky import BlueskyAdapter
from .buffer import BUFFER_ROUTES
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

# Instagram, the LinkedIn Page and TikTok go through Buffer until their own APIs open to us.
DEFAULT_ROUTES = {"instagram": "buffer", "linkedin": "buffer", "tiktok": "buffer"}


def route_for(network: str, env: Mapping[str, str]) -> str:
    raw = (env.get(f"PUBLISHER_ROUTE_{network.upper()}") or DEFAULT_ROUTES.get(network, "direct")).strip().lower()
    if raw not in ("direct", "buffer") or (raw == "buffer" and network not in BUFFER_ROUTES):
        raise ValueError(f"PUBLISHER_ROUTE_{network.upper()}={raw!r} is not a route for {network}")
    return raw


def resolve_adapters(env: Mapping[str, str]) -> dict[str, type[Adapter]]:
    return {n: (BUFFER_ROUTES[n] if route_for(n, env) == "buffer" else cls) for n, cls in ADAPTERS.items()}
