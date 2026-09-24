"""Own publisher contract: one adapter per network, `post(media, caption) -> PostResult`.

Adapters talk to each network's official API through the mill's HTTP seam
(`publish/http.py`), so live runs, dry-runs and tests run the same code.
Credentials only ever come from environment variables.
"""

from __future__ import annotations

import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Mapping, TypeVar
from urllib.parse import quote, urlencode

from ..publish.http import HttpError, HttpResponse, Request, Transport

VIDEO = "video"
IMAGE = "image"
PUBLISHED = "published"
DRAFTED = "drafted"

T = TypeVar("T")


class PublisherError(RuntimeError):
    pass


@dataclass(frozen=True)
class Media:
    path: Path
    kind: str
    mime: str
    width: int
    height: int
    duration_s: float = 0.0
    poster: Path | None = None
    label: str = ""  # the bare input the verdict answers; used where a network demands a title

    @property
    def size(self) -> int:
        return self.path.stat().st_size

    def read(self) -> bytes:
        return self.path.read_bytes()

    @classmethod
    def video(cls, path: str | Path, width: int, height: int, duration_s: float,
              poster: str | Path | None = None, label: str = "") -> "Media":
        return cls(Path(path), VIDEO, "video/mp4", width, height, duration_s,
                   Path(poster) if poster else None, label)

    @classmethod
    def image(cls, path: str | Path, width: int, height: int, label: str = "") -> "Media":
        p = Path(path)
        mime = "image/jpeg" if p.suffix.lower() in (".jpg", ".jpeg") else "image/png"
        return cls(p, IMAGE, mime, width, height, label=label)


@dataclass(frozen=True)
class PostResult:
    url: str
    remote_id: str
    state: str = PUBLISHED  # published | drafted (waits for a human tap inside the network's app)
    note: str = ""


class Adapter(ABC):
    name: str = ""
    env_sets: tuple[tuple[str, ...], ...] = ()
    optional_env: tuple[str, ...] = ()
    kinds: frozenset[str] = frozenset({VIDEO, IMAGE})
    blocked: str = ""  # why live posting can't happen today even though the code is done
    cannot: str = ""  # what the free / unaudited API cannot do, stated plainly

    def __init__(
        self,
        transport: Transport | None = None,
        env: Mapping[str, str] | None = None,
        *,
        sleep: Callable[[float], None] = time.sleep,
        now: Callable[[], float] = time.time,
        idempotency_key: str = "",
    ):
        self.transport = transport
        self.env = dict(os.environ if env is None else env)
        self.sleep = sleep
        self.now = now
        self.idempotency_key = idempotency_key
        self.warnings: list[str] = []

    @classmethod
    def all_env(cls) -> tuple[str, ...]:
        names = [n for s in cls.env_sets for n in s] + list(cls.optional_env)
        return tuple(dict.fromkeys(names))

    @classmethod
    def missing(cls, env: Mapping[str, str]) -> list[str]:
        for names in cls.env_sets:
            if all((env.get(n) or "").strip() for n in names):
                return []
        return [n for n in cls.env_sets[0] if not (env.get(n) or "").strip()]

    @classmethod
    def placeholder_env(cls) -> dict[str, str]:
        return {n: (f"https://{n.lower().replace('_', '-')}.dry.run" if n.endswith("_URL") else f"DRY_RUN_{n}")
                for n in cls.env_sets[0]}

    def var(self, name: str, default: str = "") -> str:
        return (self.env.get(name) or default).strip()

    def send(self, req: Request) -> HttpResponse:
        assert self.transport is not None, "adapter has no transport"
        resp = self.transport.send(req)
        if not resp.ok:
            raise HttpError(req, resp)
        return resp

    def iso_now(self) -> str:
        return datetime.fromtimestamp(self.now(), timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")

    def poll(self, fetch: Callable[[], T | None], *, attempts: int, interval: float, what: str) -> T:
        for i in range(attempts):
            got = fetch()
            if got is not None:
                return got
            if i < attempts - 1:
                self.sleep(interval)
        raise PublisherError(f"{self.name}: {what} not ready after {attempts} polls")

    def post(self, media: Media, caption: str) -> PostResult:
        if media.kind not in self.kinds:
            raise PublisherError(f"{self.name} cannot post {media.kind} (supports: {', '.join(sorted(self.kinds))})")
        return self._post(media, caption.strip())

    @abstractmethod
    def _post(self, media: Media, caption: str) -> PostResult: ...

    @abstractmethod
    def dry_run_responder(self, req: Request) -> HttpResponse: ...


def form_request(method: str, url: str, fields: Mapping[str, str], headers: Mapping[str, str] | None = None) -> Request:
    """application/x-www-form-urlencoded body (the transport's `form` is multipart)."""
    return Request(
        method, url,
        headers={**(headers or {}), "Content-Type": "application/x-www-form-urlencoded"},
        data=urlencode(dict(fields)).encode(),
    )


def public_url(base: str, media: Media) -> str:
    return f"{base.rstrip('/')}/{quote(media.path.name)}"
