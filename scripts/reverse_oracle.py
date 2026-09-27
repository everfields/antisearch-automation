#!/usr/bin/env python3
"""Reverse oracle: see `antisearch_mill.reverse_oracle`. Example:

    python scripts/reverse_oracle.py --state state --live --check-sites
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from antisearch_mill.reverse_oracle import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
