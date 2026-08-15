"""Loading `tests/fixtures/sections/*.json` — slices of a real index.

The fixtures were cut once from a locally built view by
`tools/extract_section_fixtures.py` and committed, so pointer resolution runs in
CI with `manuals/` absent, no PDF opened and no embedding model loaded. See
`tests/fixtures/README.md`.

Nothing here mints a `passage_id` or invents a section: a fixture is a slice of a
view, and `data/manual-corpus` owns what a view contains.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "sections"

SCHEMA = "dawmans.triage.sections/1"


def passages(*names: str) -> list[dict[str, Any]]:
    """The passage rows of one or more fixtures, concatenated in the order given.

    Concatenating is how a multi-source index is assembled: the real view is a
    plain concatenation of shards in `source_id` order, so a fixture index built
    the same way exercises resolution against the shape it will actually meet.
    """
    rows: list[dict[str, Any]] = []
    for name in names:
        payload = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
        assert payload["schema"] == SCHEMA, f"{name} is {payload['schema']}, not {SCHEMA}"
        rows.extend(payload["passages"])
    return rows


LIVE = "live_sections.json"
SCARLETT = "scarlett_sections.json"
APC = "apc_sections.json"
ALESIS = "alesis_sections.json"
SPLIT = "split_section.json"
DRIFT_BEFORE = "drift/before.json"
DRIFT_AFTER = "drift/after.json"

CORPUS = (LIVE, SCARLETT, APC, ALESIS)
"""The four manuals a pointer can name, as one index — the whole rig's documentation.

The starter set points into all four: 7.5's General MIDI and channel causes are documented
by the drum module and by nothing else, so a corpus of three would reject that entry rather
than resolve it (2.2).
"""
