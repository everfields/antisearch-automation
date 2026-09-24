"""Adapters in go-live priority order, and the route each network takes.

Native (our own adapter, the network's official API) is the default everywhere.
Buffer free is a temporary bridge, used only where a native gate hasn't cleared:
`PUBLISHER_BRIDGE=buffer` routes Instagram, LinkedIn and TikTok through Buffer at once,
unset removes Buffer entirely, and `PUBLISHER_ROUTE_<NETWORK>` overrides one network.
"""

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


def route_for(network: str, env: Mapping[str, str]) -> str:
    explicit = (env.get(f"PUBLISHER_ROUTE_{network.upper()}") or "").strip().lower()
    bridge = (env.get("PUBLISHER_BRIDGE") or "").strip().lower()
    if bridge not in ("", "off", "none", "buffer"):
        raise ValueError(f"PUBLISHER_BRIDGE={bridge!r}; use buffer or leave it unset")
    raw = explicit or ("buffer" if bridge == "buffer" and network in BUFFER_ROUTES else "direct")
    if raw not in ("direct", "buffer") or (raw == "buffer" and network not in BUFFER_ROUTES):
        raise ValueError(f"PUBLISHER_ROUTE_{network.upper()}={raw!r} is not a route for {network}")
    return raw


def resolve_adapters(env: Mapping[str, str]) -> dict[str, type[Adapter]]:
    return {n: (BUFFER_ROUTES[n] if route_for(n, env) == "buffer" else cls) for n, cls in ADAPTERS.items()}
