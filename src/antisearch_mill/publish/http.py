"""Tiny HTTP seam so adapters run identically in live, dry-run and tests.

Dry-run swaps the real transport for `RecordingTransport`: every request the
adapter would send is recorded (secrets redacted, bodies summarized) and
answered by a platform-specific responder that mimics the real API. The
recorded list is the publish plan written to out/dry_run/.
"""

from __future__ import annotations

import json as _json
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

import requests

REDACT_HEADERS = {"authorization", "cookie"}


@dataclass
class HttpResponse:
    status: int
    headers: dict[str, str] = field(default_factory=dict)
    body: bytes = b""

    def json(self) -> Any:
        return _json.loads(self.body.decode("utf-8")) if self.body else {}

    def header(self, name: str) -> str:
        lname = name.lower()
        for k, v in self.headers.items():
            if k.lower() == lname:
                return v
        return ""

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300

    @classmethod
    def of_json(cls, status: int, payload: Any, headers: dict[str, str] | None = None) -> "HttpResponse":
        h = {"Content-Type": "application/json", **(headers or {})}
        return cls(status, h, _json.dumps(payload).encode("utf-8"))


@dataclass
class Request:
    method: str
    url: str
    headers: dict[str, str] = field(default_factory=dict)
    params: dict[str, str] | None = None
    json: Any = None
    data: bytes | None = None
    files: dict[str, tuple[str, bytes, str]] | None = None
    form: dict[str, str] | None = None


class Transport(Protocol):
    def send(self, req: Request, timeout: float = 60.0) -> HttpResponse: ...


class HttpError(RuntimeError):
    def __init__(self, req: Request, resp: HttpResponse):
        snippet = resp.body[:300].decode("utf-8", "replace")
        super().__init__(f"{req.method} {req.url} -> {resp.status}: {snippet}")
        self.status = resp.status
        self.response = resp


class RequestsTransport:
    def __init__(self, session: requests.Session | None = None):
        self.session = session or requests.Session()

    def send(self, req: Request, timeout: float = 60.0) -> HttpResponse:
        files = None
        if req.files or req.form:
            files = {k: (None, v) for k, v in (req.form or {}).items()}
            files.update(req.files or {})
        resp = self.session.request(
            req.method,
            req.url,
            headers=req.headers,
            params=req.params,
            json=req.json if files is None else None,
            data=req.data,
            files=files,
            timeout=timeout,
        )
        return HttpResponse(resp.status_code, dict(resp.headers), resp.content)


def _summarize(req: Request) -> dict:
    out: dict[str, Any] = {
        "method": req.method,
        "url": req.url,
        "headers": {k: ("<redacted>" if k.lower() in REDACT_HEADERS else v) for k, v in req.headers.items()},
    }
    if req.params:
        out["params"] = req.params
    if req.json is not None:
        out["json"] = req.json
    if req.data is not None:
        out["body_bytes"] = len(req.data)
    if req.form:
        out["form"] = req.form
    if req.files:
        out["files"] = {k: {"filename": v[0], "bytes": len(v[1]), "type": v[2]} for k, v in req.files.items()}
    return out


class RecordingTransport:
    def __init__(self, responder: Callable[[Request], HttpResponse]):
        self.responder = responder
        self.requests: list[Request] = []
        self.responses: list[HttpResponse] = []

    def send(self, req: Request, timeout: float = 60.0) -> HttpResponse:
        self.requests.append(req)
        resp = self.responder(req)
        self.responses.append(resp)
        return resp

    def plan(self) -> list[dict]:
        steps = []
        for req, resp in zip(self.requests, self.responses):
            step = _summarize(req)
            step["simulated_response"] = {"status": resp.status}
            steps.append(step)
        return steps
