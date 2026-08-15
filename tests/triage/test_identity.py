"""Authored identity and the `SourceRecord` — design 'Identity'.

Two claims, and everything here is one of them. The record is fixed by CONTRACTS §1
rather than derived from the store, and the identifier is
`corpus.passage_id("authored/triage", passage_text)` — the same function over the same
canonical form as a manual passage (3.9), so authored and manual identifiers behave
identically under re-ingestion.

The properties state what the identifier must and must not move under. Cosmetic
invariance is 8.2's authored half; sensitivity is its converse, and without it an
implementation hashing a constant would pass every invariance test written.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st
from rendering import Section, entry_file, prose, rebuild

from dawmans.corpus.passage_id import passage_id
from dawmans.records import AUTHORED_SOURCE_ID, VENDOR_MANUAL_ONLY_FIELDS, SourceRecord
from dawmans.triage.loader import DISPLAY_NAME, UNCHUNKED, entry_location, source_record
from dawmans.triage.model import Entry
from dawmans.triage.parse import parse_entry, render, render_blocks

ENTRY_PATH = Path("triage/no-sound-from-track.md")

LIVE_ID = "ableton/live-12"
POINTER = f"{LIVE_ID} §18.6"

INGESTED_AT = "2026-08-15T00:00:00+00:00"

BODY = [
    Section("The Track Activator is off", check="look at the track's activator", fixes=[POINTER]),
    Section("Another track is soloed", check="look for a lit Solo button", fixes=[POINTER]),
]


def entry_of(text: str, path: Path = ENTRY_PATH) -> Entry:
    result = parse_entry(path, text.encode("utf-8"))
    assert result.rejection is None, f"fixture did not parse: {result.rejection}"
    assert result.entry is not None
    return result.entry


def identity(entry: Entry) -> str:
    """The design's statement, applied literally: the function, the constant, the text."""
    return passage_id(AUTHORED_SOURCE_ID, render(entry))


DEFAULT = entry_file(devices=[LIVE_ID], symptom="No sound from a track", sections=BODY)


# --- The SourceRecord ------------------------------------------------------


def test_record_is_the_contracts_constants() -> None:
    record = source_record(ingested_at=INGESTED_AT)

    assert record.kind == "authored-triage"
    assert record.source_id == AUTHORED_SOURCE_ID == "authored/triage"
    assert record.display_name == DISPLAY_NAME == "My Triage Notes"
    assert record.hardware_applicability.status == "assumed"
    assert record.ingested_at == INGESTED_AT
    assert record.chunk_count == UNCHUNKED


def test_record_omits_every_vendor_manual_field() -> None:
    """12.5's constructor refuses a value for each; none is defaulted into place."""
    record = source_record(ingested_at=INGESTED_AT)
    for name in VENDOR_MANUAL_ONLY_FIELDS:
        assert getattr(record, name) is None, name


@pytest.mark.parametrize("name", VENDOR_MANUAL_ONLY_FIELDS)
def test_a_vendor_manual_field_cannot_be_synthesised(name: str) -> None:
    with pytest.raises(ValueError, match=f"{name} is not applicable"):
        dataclasses.replace(source_record(ingested_at=INGESTED_AT), **{name: "anything"})


def test_applicability_cannot_be_raised_above_assumed() -> None:
    """CONTRACTS §1 over 3.8's literal text: the store is not about one device, so
    nothing in configuration can promote it to `confirmed`."""
    record = source_record(ingested_at=INGESTED_AT)
    with pytest.raises(ValueError, match="fixed at 'assumed'"):
        dataclasses.replace(
            record,
            hardware_applicability=dataclasses.replace(
                record.hardware_applicability, status="confirmed"
            ),
        )


def test_source_id_is_the_constant_and_not_the_filename() -> None:
    """1.8's operative half. 3.1's content-derived clause is the recorded defect; what is
    tested is that no filename reaches the identity."""
    here = entry_of(DEFAULT, Path("triage/no-sound-from-track.md"))
    moved = entry_of(DEFAULT, Path("triage/nested/live/renamed.md"))

    assert identity(here) == identity(moved)
    assert source_record(ingested_at=INGESTED_AT).source_id == AUTHORED_SOURCE_ID


def test_chunk_count_is_the_run_s_to_supply() -> None:
    assert source_record(ingested_at=INGESTED_AT, chunk_count=3).chunk_count == 3


def test_one_record_serves_the_whole_store() -> None:
    """3.7: every passage and citation drawn from an entry resolves to this one record,
    which is what carries `kind` to the user. Two calls in one run agree in every field."""
    first = source_record(ingested_at=INGESTED_AT)
    second = source_record(ingested_at=INGESTED_AT)
    assert first == second
    assert isinstance(first, SourceRecord)


# --- entry_location --------------------------------------------------------


def test_entry_location_is_path_and_line() -> None:
    entry = entry_of(DEFAULT, Path("triage/nested/live/no-sound.md"))
    assert entry_location(entry) == f"triage/nested/live/no-sound.md:{entry.line}"


def test_entry_location_does_not_reach_the_identity() -> None:
    """CONTRACTS §2 states it outright: the author moves entries between files."""
    here = entry_of(DEFAULT, Path("triage/no-sound.md"))
    there = entry_of(DEFAULT, Path("triage/nested/no-sound.md"))

    assert entry_location(here) != entry_location(there)
    assert identity(here) == identity(there)


# --- The identifier is the corpus's own function ---------------------------


def test_identity_is_the_corpus_function_over_the_canonical_form() -> None:
    entry = entry_of(DEFAULT)
    assert identity(entry) == passage_id("authored/triage", render(entry))
    assert identity(entry).startswith("authored/triage#")


def test_the_canonical_form_is_the_blocks_the_loader_emits() -> None:
    """There is no second canonical form (§Identity). `render` joins the same blocks the
    emission table turns into units, so the hashed text is the passage text."""
    entry = entry_of(DEFAULT)
    blocks = render_blocks(entry)

    assert blocks.blocks == (blocks.head, *blocks.causes)
    assert render(entry) == "\n\n".join(blocks.blocks)
    # The chunker joins units with "\n" rather than "\n\n"; `passage_id` collapses
    # whitespace runs before hashing, so the two carry one identifier.
    assert passage_id(AUTHORED_SOURCE_ID, "\n".join(blocks.blocks)) == identity(entry)


# --- Cosmetic invariance (8.2's authored half) -----------------------------

MARKER_STYLE = f"""\
---
devices: [{LIVE_ID}]
---

# No sound from a track

## The Track Activator is off
**Check:** look at the track's activator
fix: {POINTER}

## Another track is soloed
- CHECK : look for a lit Solo button
> **fix**: {POINTER}
"""
"""`DEFAULT`'s content under every marker style the grammar tolerates. The parser emits
the normalised marker, so this and `DEFAULT` are one canonical rendering."""

COSMETIC = {
    "marker style": MARKER_STYLE,
    "blank lines": DEFAULT.replace("\n## ", "\n\n\n## "),
    "line endings": DEFAULT.replace("\n", "\r\n"),
    "a byte-order mark": "﻿" + DEFAULT,
    "trailing whitespace": DEFAULT.replace("\n", "   \n"),
}


@pytest.mark.parametrize("what", sorted(COSMETIC))
def test_cosmetics_do_not_move_the_identifier(what: str) -> None:
    assert identity(entry_of(COSMETIC[what])) == identity(entry_of(DEFAULT)), what


def test_frontmatter_key_order_and_scope_do_not_move_it() -> None:
    """A device added to `devices:` must not orphan the entry's history."""
    widened = entry_file(
        devices=[LIVE_ID, "akai/apc-key-25"],
        symptom="No sound from a track",
        sections=BODY,
        frontmatter_extra={"note": "anything"},
    )
    assert identity(entry_of(widened)) == identity(entry_of(DEFAULT))


def test_retargeting_a_pointer_does_not_move_it() -> None:
    """Retargeting after a manual renumbers is the frequent maintenance event, and it
    must not orphan the citation history — the argument the corpus uses for excluding
    `section_number` from a manual passage's identity."""
    retargeted = entry_file(
        devices=[LIVE_ID],
        symptom="No sound from a track",
        sections=[
            dataclasses.replace(BODY[0], fixes=[f"{LIVE_ID} §18.7"]),
            dataclasses.replace(BODY[1], fixes=['akai/apc-key-25 "Shift Functions"']),
        ],
    )
    assert identity(entry_of(retargeted)) == identity(entry_of(DEFAULT))


# --- Sensitivity -----------------------------------------------------------

SENSITIVE = {
    "the symptom": entry_file(devices=[LIVE_ID], symptom="No sound at all", sections=BODY),
    "a phrasing": entry_file(
        devices=[LIVE_ID], symptom="No sound from a track", sections=BODY, phrasings=["silence"]
    ),
    "the preamble": entry_file(
        devices=[LIVE_ID],
        symptom="No sound from a track",
        sections=BODY,
        preamble=["Work down the list in order."],
    ),
    "a cause statement": entry_file(
        devices=[LIVE_ID],
        symptom="No sound from a track",
        sections=[dataclasses.replace(BODY[0], statement="The track is deactivated"), BODY[1]],
    ),
    "a check": entry_file(
        devices=[LIVE_ID],
        symptom="No sound from a track",
        sections=[dataclasses.replace(BODY[0], check="look at the activator switch"), BODY[1]],
    ),
    "a note": entry_file(
        devices=[LIVE_ID],
        symptom="No sound from a track",
        sections=[dataclasses.replace(BODY[0], notes=["why: it silences the track"]), BODY[1]],
    ),
    "a closing statement": entry_file(
        devices=[LIVE_ID],
        symptom="No sound from a track",
        sections=[*BODY, Section("Otherwise, check the audio interface")],
    ),
    "the cause order": entry_file(
        devices=[LIVE_ID], symptom="No sound from a track", sections=[BODY[1], BODY[0]]
    ),
}


@pytest.mark.parametrize("what", sorted(SENSITIVE))
def test_content_changes_move_the_identifier(what: str) -> None:
    assert identity(entry_of(SENSITIVE[what])) != identity(entry_of(DEFAULT)), what


# --- Properties ------------------------------------------------------------


@st.composite
def entries(draw: st.DrawFn) -> Entry:
    """A well-formed entry, drawn through the model and rendered — never as text."""
    causes = draw(
        st.lists(
            st.builds(
                Section,
                statement=prose,
                check=prose,
                fixes=st.just([POINTER]),
                notes=st.lists(prose, max_size=2),
            ),
            min_size=2,
            max_size=4,
        )
    )
    text = entry_file(
        devices=draw(st.lists(st.just(LIVE_ID), min_size=1, max_size=1)),
        symptom=draw(prose),
        sections=causes,
        phrasings=draw(st.lists(prose, max_size=2)),
        preamble=draw(st.lists(prose, max_size=2)),
    )
    result = parse_entry(ENTRY_PATH, text.encode("utf-8"))
    assume(result.entry is not None)
    assert result.entry is not None
    return result.entry


@settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
@given(entries())
def test_property_canonical_idempotence(entry: Entry) -> None:
    """`render ∘ parse ∘ rebuild` is a fixed point.

    Task 13 states this as `render(parse(render(parse(f)))) == render(parse(f))`, which
    cannot hold: `render` excludes the frontmatter and the fix pointers, so its output is
    not an entry file and re-parsing it rejects. `rebuild` re-supplies exactly what the
    rendering drops — see its docstring and decision_log Decision 11 — so what is asserted
    is what the literal form was reaching for: the canonical form of an entry does not
    move when the entry is written out and read back.
    """
    once = render(entry)
    twice = render(entry_of(rebuild(entry)))
    assert twice == once


@settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
@given(entries())
def test_property_identity_follows_the_canonical_form(entry: Entry) -> None:
    """Two entries carry one identifier exactly where they carry one rendering."""
    assert identity(entry) == passage_id(AUTHORED_SOURCE_ID, render(entry))
    assert identity(entry) == identity(entry_of(rebuild(entry)))


@settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
@given(entries(), prose)
def test_property_a_changed_symptom_changes_the_identifier(entry: Entry, symptom: str) -> None:
    assume(symptom != entry.symptom)
    assert identity(dataclasses.replace(entry, symptom=symptom)) != identity(entry)
