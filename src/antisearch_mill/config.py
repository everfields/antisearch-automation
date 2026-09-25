"""Settings resolved from the environment (and an optional `.env` file).

Nothing here is required: every credential is optional so the mill can always
run in dry-run mode. Missing credentials surface in `mill doctor` and in the
publish log, never as a crash.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_ORACLE_URL = "https://antisearch.ai/verdict"


def load_dotenv(path: str | os.PathLike = ".env") -> None:
    """Minimal `.env` loader: KEY=VALUE lines, `#` comments, existing env wins."""
    p = Path(path)
    if not p.is_file():
        return
    for raw in p.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):]
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        os.environ.setdefault(key, value)


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _env_float(name: str, default: float) -> float:
    raw = _env(name)
    return float(raw) if raw else default


@dataclass(frozen=True)
class PlatformCredentials:
    """Credential env var names per platform, grouped into alternative sets.

    A platform is live-capable when every variable of at least one set is present.
    """

    platform: str
    sets: tuple[tuple[str, ...], ...]
    optional: tuple[str, ...] = ()

    def present_set(self) -> tuple[str, ...] | None:
        for names in self.sets:
            if all(_env(n) for n in names):
                return names
        return None

    def missing(self) -> list[str]:
        if self.present_set() is not None:
            return []
        first = self.sets[0]
        return [n for n in first if not _env(n)]


CREDENTIALS: dict[str, PlatformCredentials] = {
    "x": PlatformCredentials(
        "x",
        sets=(
            ("X_API_KEY", "X_API_KEY_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_TOKEN_SECRET"),
            ("X_OAUTH2_ACCESS_TOKEN",),
        ),
    ),
    "linkedin": PlatformCredentials(
        "linkedin",
        sets=(("LINKEDIN_ACCESS_TOKEN", "LINKEDIN_AUTHOR_URN"),),
        optional=("LINKEDIN_VERSION",),
    ),
    "tiktok": PlatformCredentials(
        "tiktok",
        sets=(("TIKTOK_CLIENT_KEY", "TIKTOK_CLIENT_SECRET", "TIKTOK_ACCESS_TOKEN"),),
    ),
    "instagram": PlatformCredentials(
        "instagram",
        sets=(("INSTAGRAM_ACCESS_TOKEN", "INSTAGRAM_BUSINESS_ACCOUNT_ID"),),
    ),
}


@dataclass
class Settings:
    oracle_url: str = DEFAULT_ORACLE_URL
    out_dir: Path = Path("out")
    font_path: str = ""
    oracle_min_interval_s: float = 1.5
    oracle_rate_limit_wait_s: float = 60.0
    linkedin_version: str = "202609"
    extra: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            oracle_url=_env("ANTISEARCH_ORACLE_URL", DEFAULT_ORACLE_URL),
            out_dir=Path(_env("MILL_OUT_DIR", "out")),
            font_path=_env("MILL_FONT"),
            oracle_min_interval_s=_env_float("MILL_ORACLE_MIN_INTERVAL_S", 1.5),
            oracle_rate_limit_wait_s=_env_float("MILL_ORACLE_RATE_LIMIT_WAIT_S", 60.0),
            linkedin_version=_env("LINKEDIN_VERSION", "202609"),
        )


def env(name: str, default: str = "") -> str:
    return _env(name, default)
