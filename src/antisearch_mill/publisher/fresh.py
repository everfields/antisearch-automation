"""Remux a master for upload: new container timestamps, same pictures.

The visual encode stays bit-exact. Platforms that banned accounts for identical
files were hashing the container, not the frames. This copies the streams and
writes a fresh creation_time plus an upload token. No filter, no pixel change.
"""

from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path


def looks_like_mp4(path: Path) -> bool:
    try:
        head = path.read_bytes()[:12]
    except OSError:
        return False
    return len(head) >= 8 and b"ftyp" in head


def remux_args(src: Path, dst: Path, when: datetime, token: str) -> list[str]:
    stamp = when.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    return [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(src),
        "-map", "0", "-c", "copy",
        "-map_metadata", "-1",
        "-metadata", f"creation_time={stamp}",
        "-metadata", f"comment=upload={token}",
        "-movflags", "+faststart",
        str(dst),
    ]


def remux_fresh(src: Path, dst: Path, when: datetime, token: str) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(remux_args(src, dst, when, token), capture_output=True, text=True)
    if proc.returncode != 0 or not dst.is_file():
        tail = "\n".join((proc.stderr or "").strip().splitlines()[-8:])
        raise RuntimeError(tail or f"ffmpeg remux failed ({proc.returncode})")
