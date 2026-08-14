"""Shared test setup.

`tools/` holds developer commands rather than an installed package, so it is not on the
import path. `capture_fixture.py` is the one that has assertable behaviour — the page
spec, the label spec and the redaction mask — and the committed fixtures are only as
trustworthy as it is, so the tests import it from here.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"

sys.path.insert(0, str(REPO_ROOT / "tools"))
