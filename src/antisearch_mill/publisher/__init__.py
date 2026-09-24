"""Own publisher: official APIs only, no browser, no middleman. Dry-run by default."""

from ..publish.http import RequestsTransport, Transport
from .base import IMAGE, VIDEO, Adapter, Media, PostResult, PublisherError
from .registry import ADAPTERS


def adapter(network: str, transport: Transport | None = None, **kwargs) -> Adapter:
    """Live adapter: `adapter("bluesky").post(Media.video(...), "@antisearch.ai") -> PostResult(url, ...)`.

    No guard runs here; `mill post` (run.run_posts) is the path that enforces the locks.
    """
    return ADAPTERS[network](transport or RequestsTransport(), **kwargs)


__all__ = ["ADAPTERS", "IMAGE", "VIDEO", "Adapter", "Media", "PostResult", "PublisherError", "adapter"]
