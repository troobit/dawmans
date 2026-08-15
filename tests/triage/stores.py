"""Test support: an entry store on disk, and the loader that reads it.

The corpus a `TriageLoader` is given here is built from `tests/fixtures/sections/*.json`
— slices of a real view — so pointer resolution and the term check run with `manuals/`
absent, no PDF opened and no embedding model loaded. `view()` carries the passage
**text** as well as the section maps, because the term check reads it.
"""

from __future__ import annotations

from pathlib import Path

from fixture_rig import RIG
from rendering import Section, entry_file
from sections import CORPUS, DRIFT_AFTER, LIVE, passages

from dawmans.corpus.loader import Discovered
from dawmans.records import AUTHORED_SOURCE_ID
from dawmans.triage.loader import CorpusView, TriageLoader
from dawmans.triage.pointers import Ledger

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "triage"

LIVE_ID = "ableton/live-12"
APC_ID = "akai/apc-key-25"
DIGITAKT_ID = "elektron/digitakt"
"""In the fixture rig and documented by nothing — 2.3's only permitted shape."""

POINTER = f"{LIVE_ID} §18.1"
DRIFTING = f"{LIVE_ID} §18.6"

NOW = "2026-08-15T09:00:00+00:00"

DISCOVERED = Discovered(source_id=AUTHORED_SOURCE_ID, fingerprint="0" * 64, origin=Path("triage"))

SOURCES = [
    {
        "kind": "vendor-manual",
        "source_id": source_id,
        "hardware_applicability": {"status": "assumed", "device": device},
    }
    for source_id, device in (
        ("ableton/live-12", "ableton/live-12"),
        ("akai/apc-key-25", "akai/apc-key-25"),
        ("focusrite/scarlett-solo-4g", "focusrite/scarlett-solo"),
        ("alesis/nitro-max", "alesis/nitro-max"),
        ("roland/tr-8s", "roland/tr-8s"),
    )
]
"""The source records the fixture corpus stands for, in the shape `sources.json` carries."""


def view(*names: str) -> CorpusView:
    return CorpusView.of(passages(*names or CORPUS), SOURCES)


def drifted_view() -> CorpusView:
    """Live after the revision that renumbered §18.6 to §18.7 and edited its text.

    The surrounding sections have to come from the *same* corpus as the drifting one, or
    the entry's second pointer — §18.1, which did not move — fails to resolve and the
    fixture tests a missing manual rather than a drifted section.
    """
    rows = [row for row in passages(LIVE) if row["section_number"] != "18.6"]
    return CorpusView.of([*rows, *passages(DRIFT_AFTER)], SOURCES)


def store(tmp_path: Path, files: dict[str, str]) -> Path:
    root = tmp_path / "triage"
    root.mkdir(parents=True, exist_ok=True)
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root


def loader(
    store_path: Path, *, corpus: CorpusView | None = None, ledger: Ledger | None = None
) -> TriageLoader:
    return TriageLoader(
        store=store_path,
        view=corpus if corpus is not None else view(),
        rig=RIG,
        ledger=ledger if ledger is not None else Ledger.empty(),
        now=lambda: NOW,
    )


def one_entry(tmp_path: Path, text: str, **kwargs):
    """The `LoadResult` of a store holding exactly one entry file."""
    return loader(store(tmp_path, {"entry.md": text}), **kwargs).load(DISCOVERED)


DEFAULT_BODY = [
    Section("The Track Activator is off", check="the track's number is unlit", fixes=[POINTER]),
    Section("Another track is soloed", check="a Solo button is lit", fixes=[POINTER]),
]

DEFAULT = entry_file(
    devices=[LIVE_ID],
    symptom="No sound from a track",
    sections=DEFAULT_BODY,
    phrasings=["a track is silent"],
    preamble=["Work down the list in order."],
)
