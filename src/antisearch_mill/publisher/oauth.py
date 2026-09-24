"""One-time OAuth helpers: authorize URL for a human to open, then code -> tokens.

The human opens the URL on their own device (residential IP), approves, and pastes
back the URL they land on. The exchange runs anywhere (it's a server-to-server
call) and prints tokens to store as secrets.
"""

from __future__ import annotations

import secrets
from urllib.parse import parse_qs, unquote, urlencode, urlsplit

from ..publish.http import Transport
from .base import PublisherError, form_request

DEFAULT_REDIRECT = "https://antisearch.ai/"

PROVIDERS = {
    "tiktok": {
        "authorize": "https://www.tiktok.com/v2/auth/authorize/",
        "token": "https://open.tiktokapis.com/v2/oauth/token/",
        "client_id_param": "client_key",
        "client_id_env": "TIKTOK_CLIENT_KEY",
        "client_secret_env": "TIKTOK_CLIENT_SECRET",
        "scope": "user.info.basic,video.upload,video.publish",
    },
    "linkedin": {
        "authorize": "https://www.linkedin.com/oauth/v2/authorization",
        "token": "https://www.linkedin.com/oauth/v2/accessToken",
        "client_id_param": "client_id",
        "client_id_env": "LINKEDIN_CLIENT_ID",
        "client_secret_env": "LINKEDIN_CLIENT_SECRET",
        "scope": "w_organization_social",
    },
}


def _need(env: dict[str, str], name: str) -> str:
    value = (env.get(name) or "").strip()
    if not value:
        raise PublisherError(f"{name} is not set")
    return value


def authorize_url(provider: str, env: dict[str, str], *, scope: str = "", redirect_uri: str = "", state: str = "") -> str:
    p = PROVIDERS[provider]
    params = {
        p["client_id_param"]: _need(env, p["client_id_env"]),
        "response_type": "code",
        "scope": scope or p["scope"],
        "redirect_uri": redirect_uri or env.get("PUBLISHER_OAUTH_REDIRECT_URI") or DEFAULT_REDIRECT,
        "state": state or secrets.token_urlsafe(12),
    }
    return f"{p['authorize']}?{urlencode(params)}"


def code_from(pasted: str) -> str:
    """Accept the bare code or the whole redirected URL."""
    pasted = pasted.strip()
    if "://" in pasted or pasted.startswith("?"):
        query = parse_qs(urlsplit(pasted).query)
        if "error" in query:
            raise PublisherError(f"authorization refused: {query.get('error_description', query['error'])[0]}")
        if "code" not in query:
            raise PublisherError("no code= in the pasted URL")
        return query["code"][0]
    return unquote(pasted)


def exchange(provider: str, pasted: str, env: dict[str, str], transport: Transport, *, redirect_uri: str = "") -> dict:
    p = PROVIDERS[provider]
    fields = {
        p["client_id_param"]: _need(env, p["client_id_env"]),
        "client_secret": _need(env, p["client_secret_env"]),
        "code": code_from(pasted),
        "grant_type": "authorization_code",
        "redirect_uri": redirect_uri or env.get("PUBLISHER_OAUTH_REDIRECT_URI") or DEFAULT_REDIRECT,
    }
    resp = transport.send(form_request("POST", p["token"], fields))
    body = resp.json() if resp.body else {}
    if not resp.ok or "access_token" not in body:
        raise PublisherError(f"{provider} token exchange failed ({resp.status}): {body}")
    return body
