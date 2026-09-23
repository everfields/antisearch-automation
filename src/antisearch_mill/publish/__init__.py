"""Publish adapters + run loop. Dry-run is the default everywhere."""

from __future__ import annotations

import time
from dataclasses import asdict
from typing import Callable

from ..ledger import Ledger, PublishRow
from .base import DRAFT, DRY_RUN, LIVE, PublishContext, Publisher
from .http import RequestsTransport, Transport
from .linkedin import LinkedInPublisher
from .stubs import InstagramStub, TikTokStub
from .x import XPublisher

PUBLISHERS: dict[str, type[Publisher]] = {
    "x": XPublisher,
    "linkedin": LinkedInPublisher,
    "tiktok": TikTokStub,
    "instagram": InstagramStub,
}


def publish_all(
    ledger: Ledger,
    *,
    live: bool = False,
    platforms: set[str] | None = None,
    clip_ids: set[str] | None = None,
    transport: Transport | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> list[PublishRow]:
    mode = LIVE if live else DRY_RUN
    results: list[PublishRow] = []
    live_transport = transport or (RequestsTransport() if live else None)
    for clip in ledger.clips():
        if clip_ids and clip.clip_id not in clip_ids:
            continue
        for platform in clip.platform_list:
            if platforms and platform not in platforms:
                continue
            publisher = PUBLISHERS[platform]()
            ctx = PublishContext(ledger=ledger, mode=mode, transport=live_transport, sleep=sleep)
            row = publisher.publish(clip, ctx)
            ledger.append_publish(row)
            ledger.log(f"publish.{row.status}", **{k: v for k, v in asdict(row).items() if k != "capture"})
            results.append(row)
    return results


__all__ = ["DRAFT", "DRY_RUN", "LIVE", "PUBLISHERS", "publish_all"]
