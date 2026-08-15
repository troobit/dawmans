"""Cut `tests/fixtures/sections/*.json` from a locally built index (task 4).

Pointer resolution and the term check have to run in CI with `manuals/` absent, exactly as
`manual-corpus` runs its extraction snapshots: the sections the starter set points at are
extracted **once** from the real view and committed, and nothing in the test suite opens a
PDF or loads the embedding model.

Run it against a view built by `dawmans ingest`:

    uv run python tools/extract_section_fixtures.py <index>/views/<hex>

Re-running it is how the fixtures are refreshed when the corpus is rebuilt; it is not part
of any test run, and `make test` never invokes it.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

SCHEMA = "dawmans.triage.sections/1"

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "sections"

LIVE = "ableton/live-12"
APC = "akai/apc-key-25"
SCARLETT = "focusrite/scarlett-solo-4g"
ALESIS = "alesis/nitro-max"

#: The Live sections the starter set (7.2-7.6) points at, by section number. Numbers
#: rather than titles because a pointer that names both is selected by the number and only
#: corroborated by the title, and because 54 of Live's titles are duplicated.
LIVE_SECTIONS: tuple[tuple[str, str], ...] = (
    # 7.2 — no sound from a track
    ("18.1", "the Track Activator"),
    ("18.6", "another track soloed"),
    ("17.1", "the track's Monitor set to Off, and the Overall Latency adjustment"),
    ("17", "the Audio/MIDI To chooser — the track's output routed elsewhere"),
    ("23.2.1", "the device chain or a device in it deactivated"),
    # 7.3 — a track is distorting
    ("17.2", "the Input Channel meter, which is where clipping arrives"),
    ("18.1.1", "the mixer's gain stages, and the section printing `0 dB`"),
    ("28.24", "the master limiter"),
    ("28.34", "Saturator — a deliberate distortion device, for the elimination step"),
    ("28.12", "Drum Buss — deliberate distortion"),
    ("28.27", "Overdrive — deliberate distortion"),
    ("28.41", "Vinyl Distortion — deliberate distortion"),
    ("28.13", "Dynamic Tube — deliberate distortion"),
    ("28.1", "Amp — deliberate distortion"),
    # 7.4 — latency when monitoring
    ("39.5", "buffer size"),
    # 7.5 — a drum pad triggers the wrong sound
    ("24.6", "the Drum Rack pad's Receive note"),
    ("17.3.1", "the MIDI port the module is heard on"),
    # 7.6 — the controller does nothing
    ("17.3.1.1", "Track, on its own"),
    ("17.3.1.2", "Sync, on its own"),
    ("17.3.1.3", "Remote, on its own"),
    ("33.1.1", "the control surface selection"),
    ("33.1.2", "the control surface selection, set by hand"),
)

#: The Nitro Max sections 7.5 points at. The drum module's own manual is the only place
#: General MIDI mode and the pads' note numbers are documented, and 7.8 admits no
#: exception: pointing 7.5's General MIDI cause at Live's Drum Rack section instead would
#: cite a manual that documents a different control.
ALESIS_SECTIONS: tuple[tuple[str, str], ...] = (
    ("4.4", "General MIDI Mode, and the channel the module sends on"),
    ("5.2", "the note number each pad transmits"),
)

#: One section chunked into three: a pointer resolves to all three and the term check sees
#: their concatenation. It is a starter-set section too, so the split is not a synthetic case.
SPLIT_SECTION = "28.24"

#: The section the `drift/` pair is cut from — 7.2's "another track soloed" cause.
DRIFT_SECTION = "18.6"

#: What the vendor's next revision did to it, applied to the `after` half of the pair: the
#: section was renumbered and its text rewritten, which is 8.4's "the passage's text
#: changed" as it actually arrives. `§18.6` therefore resolves in `before` and not in
#: `after`, with the source still present — the flag case, not the removal case.
DRIFT_NUMBER = "18.7"
DRIFT_EDITS = (
    (f"{DRIFT_SECTION} Soloing", f"{DRIFT_NUMBER} Soloing"),
    ("mutes all other tracks", "mutes every other track"),
)
"""The printed heading follows the renumbering, and one phrase is rewritten the way a
technical writer rewrites one: the section still says what it said. A sweeping
substring replacement would leave the fixture reading like nothing the vendor would
ship, and a fixture nobody believes is a fixture nobody maintains."""


def read_view(view: Path) -> list[dict[str, Any]]:
    lines = (view / "passages.jsonl").read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def by_number(rows: Iterable[dict[str, Any]], source_id: str, number: str) -> list[dict[str, Any]]:
    """One section's passages, in view order — which is section order (design §SectionIndex)."""
    return [r for r in rows if r["source_id"] == source_id and r["section_number"] == number]


def unnumbered(rows: Iterable[dict[str, Any]], source_id: str) -> list[dict[str, Any]]:
    return [r for r in rows if r["source_id"] == source_id and r["section_number"] is None]


def write(
    name: str, *, captured_from: str, asserts: str, passages: Sequence[dict[str, Any]]
) -> None:
    path = FIXTURES / name
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": SCHEMA,
        "captured_from": captured_from,
        "asserts": asserts,
        "passages": list(passages),
    }
    path.write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{path.relative_to(FIXTURES.parents[2])}: {len(passages)} passages")


def _sections(
    rows: Sequence[dict[str, Any]],
    source_id: str,
    wanted: Sequence[tuple[str, str]],
    view: Path,
) -> list[dict[str, Any]]:
    """One manual's wanted sections, concatenated in the order they are listed.

    A section that is not in the view is a hard stop rather than a short fixture: a
    starter-set pointer with nothing behind it would reject its whole entry at first
    ingest (2.2), and a fixture missing it would report that as a test failure about
    resolution rather than about the fixture.
    """
    out: list[dict[str, Any]] = []
    for number, why in wanted:
        section = by_number(rows, source_id, number)
        if not section:
            raise SystemExit(
                f"{source_id} §{number} ({why}) is not in {view} — refusing a short fixture"
            )
        out.extend(section)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("view", type=Path, help="a committed view directory, index/views/<hex>")
    view = parser.parse_args().view
    rows = read_view(view)

    live = _sections(rows, LIVE, LIVE_SECTIONS, view)
    write(
        "live_sections.json",
        captured_from=f"{LIVE} (Ableton Live 12 Reference Manual v12)",
        asserts=(
            "pointer resolution and the term check over the sections the starter set points at, "
            "including 18.1.1, which prints `0 dB` (7.3)"
        ),
        passages=live,
    )

    scarlett = [
        r
        for r in rows
        if r["source_id"] == SCARLETT and "direct monitor" in r["section_title"].casefold()
    ]
    if not scarlett:
        raise SystemExit(f"no DIRECT MONITOR section in {SCARLETT}")
    write(
        "scarlett_sections.json",
        captured_from=f"{SCARLETT} (Focusrite Scarlett Solo 4th Gen User Guide v4.0)",
        asserts=(
            "the direct-monitoring cause of 7.4 resolves in the manual that closed the last "
            "corpus gap"
        ),
        passages=scarlett,
    )

    write(
        "apc_sections.json",
        captured_from=f"{APC} (Akai APC Key 25 User Guide v1.0)",
        asserts="the title form resolves where the manual carries no section numbers at all",
        passages=unnumbered(rows, APC),
    )

    write(
        "alesis_sections.json",
        captured_from=f"{ALESIS} (Alesis Nitro Max User Guide v1.1)",
        asserts="7.5's General MIDI and channel causes resolve in the drum module's own manual",
        passages=_sections(rows, ALESIS, ALESIS_SECTIONS, view),
    )

    split = by_number(rows, LIVE, SPLIT_SECTION)
    if len(split) < 3:
        raise SystemExit(
            f"{LIVE} §{SPLIT_SECTION} is {len(split)} passages, not the 3 the fixture needs"
        )
    write(
        "split_section.json",
        captured_from=f"{LIVE} §{SPLIT_SECTION}",
        asserts="a pointer at a split section resolves to all of its chunks, in section order",
        passages=split,
    )

    write_drift(rows)
    return 0


def _revised(text: str) -> str:
    for old, new in DRIFT_EDITS:
        text = text.replace(old, new)
    return text


def write_drift(rows: Sequence[dict[str, Any]]) -> None:
    """The `drift/` pair — one section before and after a vendor revision (8.4, 8.5).

    The `after` half is derived here rather than hand-written so the two halves cannot fall
    out of step: it is the `before` half with the section renumbered and the text edited,
    and its `passage_id`s are left as they were extracted. The identifiers are not
    recomputed, because a fixture is a slice of a view and nothing in this repository may
    mint a `passage_id` for a vendor manual — `manual-corpus` owns that (CONTRACTS §1).
    """
    before = by_number(rows, LIVE, DRIFT_SECTION)
    if not before:
        raise SystemExit(f"{LIVE} §{DRIFT_SECTION} is not in the view")

    after = [{**p, "section_number": DRIFT_NUMBER, "text": _revised(p["text"])} for p in before]
    if all(a["text"] == b["text"] for a, b in zip(after, before, strict=True)):
        raise SystemExit(
            f"the drift edits no longer touch §{DRIFT_SECTION} — the pair would be equal"
        )

    write(
        "drift/before.json",
        captured_from=f"{LIVE} §{DRIFT_SECTION}",
        asserts=(
            f"the pointer `{LIVE} §{DRIFT_SECTION}` resolves, and the seeded ledger row "
            "records these passage ids"
        ),
        passages=before,
    )
    write(
        "drift/after.json",
        captured_from=(
            f"{LIVE} §{DRIFT_SECTION}, renumbered to §{DRIFT_NUMBER} with its text edited"
        ),
        asserts=(
            "the same pointer no longer resolves with the source still present: a rejection on a "
            "first run (2.2) and a flag plus `unbacked` where the ledger holds a row (8.4, 8.5)"
        ),
        passages=after,
    )


if __name__ == "__main__":
    raise SystemExit(main())
