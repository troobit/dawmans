"""Genuine invariants of the entry grammar — design 'Testing Strategy'."""

from __future__ import annotations

from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st
from rendering import Section, entry_file, entry_files, sections

from dawmans.triage.parse import parse_entry

ENTRY_PATH = Path("triage/generated.md")


@given(st.binary(max_size=400))
@settings(max_examples=400)
def test_total_parsing(data: bytes):
    """For any byte string the parser returns an entry or a rejection naming the
    file. It never raises, and never returns a half-built entry (5.2)."""
    result = parse_entry(ENTRY_PATH, data)
    assert (result.entry is None) != (result.rejection is None)
    if result.rejection is not None:
        assert result.rejection.source_file == ENTRY_PATH
        assert result.rejection.detail


@given(st.text(max_size=400))
@settings(max_examples=400)
def test_total_parsing_over_text(text: str):
    result = parse_entry(ENTRY_PATH, text.encode("utf-8"))
    assert (result.entry is None) != (result.rejection is None)


@given(entry_files(allow_degenerate=True))
@settings(max_examples=200)
def test_a_rendered_entry_never_raises_and_never_half_builds(case: tuple[str, int]):
    text, _ = case
    result = parse_entry(ENTRY_PATH, text.encode("utf-8"))
    assert (result.entry is None) != (result.rejection is None)


@st.composite
def conserving_entry_files(draw: st.DrawFn) -> tuple[str, int]:
    """2–6 causes, optionally followed by a section carrying neither key.

    That trailing section is the whole of the demotion space: mid-document
    sections missing both keys reject under 1.2 and never reach this rule.
    """
    section_list = draw(st.lists(sections(), min_size=2, max_size=6))
    if draw(st.booleans()):
        section_list.append(Section(statement="Otherwise", notes=["Check the master."]))
    text = entry_file(
        devices=["ableton/live-12"],
        symptom="No sound from a track",
        sections=section_list,
    )
    return text, len(section_list)


@given(conserving_entry_files())
@settings(max_examples=200)
def test_cause_conservation(case: tuple[str, int]):
    """Causes emitted plus `closing-statement-inferred` flags equals the H2 count.

    The parser cannot tell a genuine closing statement from a demoted cause —
    that is the whole of Decision 6 — so it flags every inferred closing
    statement and this identity is what makes 1.5 auditable: no `##` section
    ever leaves the parse unaccounted for.
    """
    text, h2_count = case
    result = parse_entry(ENTRY_PATH, text.encode("utf-8"))
    assert result.rejection is None, f"unexpected rejection: {result.rejection}"
    inferred = [f for f in result.flags if f.name == "closing-statement-inferred"]
    assert len(result.entry.causes) + len(inferred) == h2_count


@given(sections(), sections(), sections())
@settings(max_examples=100)
def test_a_demoted_cause_is_never_lost_silently(a: Section, b: Section, c: Section):
    """Three causes whose last loses both keys parse as two plus a flagged note."""
    demoted = Section(statement=c.statement, notes=c.notes)
    text = entry_file(
        devices=["ableton/live-12"],
        symptom="No sound from a track",
        sections=[a, b, demoted],
    )
    result = parse_entry(ENTRY_PATH, text.encode("utf-8"))
    assert result.rejection is None
    assert len(result.entry.causes) == 2
    inferred = [f for f in result.flags if f.name == "closing-statement-inferred"]
    assert len(inferred) == 1
    assert demoted.statement in inferred[0].detail
