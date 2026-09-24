import json
from pathlib import Path

import pytest

from antisearch_mill.publish import publish_all
from antisearch_mill.publish.http import RecordingTransport
from conftest import requires_ffmpeg

pytestmark = requires_ffmpeg


def exploding(req):  # pragma: no cover - must never be called
    raise AssertionError(f"stub touched the network: {req.method} {req.url}")


@pytest.mark.parametrize("live", [False, True])
@pytest.mark.parametrize("platform", ["tiktok", "instagram"])
def test_stub_only_writes_a_draft(produced, platform, live):
    t = RecordingTransport(exploding)
    (row,) = publish_all(produced, live=live, platforms={platform}, transport=t)
    assert row.status == "draft_logged" and row.mode == "draft"
    assert t.requests == []
    draft = json.loads(Path(row.artifact).read_text())
    assert draft["platform"] == platform
    assert draft["capture"] == "synthetic-oracle"
    assert draft["verdict"] == "asics superblast 2"
    assert draft["validation_problems"] == []
    assert Path(row.artifact).parent == produced.out_dir / "drafts" / platform
