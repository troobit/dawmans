"""Unit emission, splitting and `unbacked` — design 'Passage emission'.

One passage per entry (Decision 2), split only over the chunker's 350-word cap and only
between causes. The emission table maps the entry's parts onto the corpus loader's own
types, which is what gives 3.3 for free rather than as a rule this spec has to enforce.

Everything here runs the **real** chunker over the emitted regions. Asserting the region
shape alone would leave the two claims that matter — a passage never carries a cause
without its symptom, and no cause is divided — resting on an assumption about how
`chunk_source` packs.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from fixture_rig import INDEXED, RIG
from hypothesis import given, settings
from hypothesis import strategies as st
from rendering import Section, entry_file, prose
from sections import CORPUS, DRIFT_AFTER, LIVE, passages

from dawmans.corpus.chunk import chunk_source
from dawmans.corpus.loader import Discovered
from dawmans.corpus.passage_id import passage_id
from dawmans.records import AUTHORED_SOURCE_ID
from dawmans.triage.loader import (
    CauseOutcome,
    CorpusView,
    EntryOutcome,
    TriageLoader,
    emit,
    entry_location,
    normalised_symptom,
    source_record,
)
from dawmans.triage.parse import parse_entry, render
from dawmans.triage.pointers import Ledger, SectionIndex

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "triage"

LIVE_ID = "ableton/live-12"
APC_ID = "akai/apc-key-25"
DIGITAKT_ID = "elektron/digitakt"
"""In the fixture rig and documented by nothing — 2.3's only permitted shape."""

POINTER = f"{LIVE_ID} §18.1"
DRIFTING = f"{LIVE_ID} §18.6"

NOW = "2026-08-15T09:00:00+00:00"

DISCOVERED = Discovered(source_id=AUTHORED_SOURCE_ID, fingerprint="0" * 64, origin=Path("triage"))


# --- Building a store ------------------------------------------------------


def view(*names: str) -> CorpusView:
    return CorpusView(
        sections=SectionIndex.from_passages(passages(*names or CORPUS)), indexed=INDEXED
    )


def drifted_view() -> CorpusView:
    """Live after the revision that renumbered §18.6 to §18.7 and edited its text.

    The surrounding sections have to come from the *same* corpus as the drifting one, or
    the entry's second pointer — §18.1, which did not move — fails to resolve and the
    fixture tests a missing manual rather than a drifted section.
    """
    rows = [row for row in passages(LIVE) if row["section_number"] != "18.6"]
    return CorpusView(
        sections=SectionIndex.from_passages([*rows, *passages(DRIFT_AFTER)]), indexed=INDEXED
    )


def store(tmp_path: Path, files: dict[str, str]) -> Path:
    root = tmp_path / "triage"
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root


def loader(store_path: Path, *, corpus: CorpusView | None = None, ledger: Ledger | None = None):
    return TriageLoader(
        store=store_path,
        view=corpus or view(),
        rig=RIG,
        ledger=ledger or Ledger.empty(),
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


# --- The region ------------------------------------------------------------


def test_region_is_the_emission_table(tmp_path: Path) -> None:
    (region,) = one_entry(tmp_path, DEFAULT).regions

    assert region.section_number is None  # 3.4: an entry has no numbering
    assert region.section_title == "No sound from a track"
    assert region.section_path == ()  # an entry has no ancestor titles
    assert region.page_start is None and region.page_end is None  # 12.8
    assert region.inferred is False  # the author declared the title
    assert region.entry_location == "triage/entry.md:5"


def test_units_are_the_symptom_then_the_causes(tmp_path: Path) -> None:
    (region,) = one_entry(tmp_path, DEFAULT).regions
    head, *causes = region.units

    assert head.repeat_on_split is True and head.atomic is False
    assert "No sound from a track" in head.text
    assert "also: a track is silent" in head.text  # 3.2: BM25 sees the phrasings
    assert "Work down the list in order." in head.text

    assert len(causes) == 2
    assert all(unit.atomic and not unit.repeat_on_split for unit in causes)
    assert causes[0].text.startswith("The Track Activator is off")
    assert causes[1].text.startswith("Another track is soloed")


def test_the_closing_statement_is_its_own_atomic_unit(tmp_path: Path) -> None:
    text = entry_file(
        devices=[LIVE_ID],
        symptom="No sound from a track",
        sections=[*DEFAULT_BODY, Section("Otherwise, the interface is muted")],
    )
    (region,) = one_entry(tmp_path, text).regions

    assert len(region.units) == 4
    assert region.units[-1].text == "Otherwise, the interface is muted"
    assert region.units[-1].atomic is True


def test_every_unit_is_plain_and_points_at_no_image(tmp_path: Path) -> None:
    """3.6. The text is plain and there is no image content to point at."""
    (region,) = one_entry(tmp_path, DEFAULT).regions
    assert all(not unit.flags.degraded and not unit.flags.has_figures for unit in region.units)


def test_fix_pointers_are_not_in_the_text(tmp_path: Path) -> None:
    """CONTRACTS §2 fixes the field set, so per-cause structure travels in the sidecar;
    keeping the pointers out is also what keeps a retarget from moving `passage_id`."""
    (region,) = one_entry(tmp_path, DEFAULT).regions
    assert POINTER not in "\n".join(unit.text for unit in region.units)


def test_regions_are_in_sorted_path_order(tmp_path: Path) -> None:
    files = {
        "b.md": entry_file(devices=[LIVE_ID], symptom="Second", sections=DEFAULT_BODY),
        "a.md": entry_file(devices=[LIVE_ID], symptom="First", sections=DEFAULT_BODY),
        "nested/c.md": entry_file(devices=[LIVE_ID], symptom="Third", sections=DEFAULT_BODY),
    }
    result = loader(store(tmp_path, files)).load(DISCOVERED)
    assert [region.section_title for region in result.regions] == ["First", "Second", "Third"]


def test_cause_order_is_the_declared_order(tmp_path: Path) -> None:
    """1.5 — the order becomes the `rank` of CONTRACTS §4c, so it is never sorted,
    merged or deduplicated."""
    body = [
        Section("Zulu", check="z", fixes=[POINTER]),
        Section("Alpha", check="a", fixes=[POINTER]),
        Section("Alpha", check="a", fixes=[POINTER]),
    ]
    text = entry_file(devices=[LIVE_ID], symptom="Ordered", sections=body)
    (region,) = one_entry(tmp_path, text).regions

    assert [unit.text.split("\n")[0] for unit in region.units[1:]] == ["Zulu", "Alpha", "Alpha"]


# --- The record and the passages -------------------------------------------


def test_the_load_carries_the_one_record(tmp_path: Path) -> None:
    result = one_entry(tmp_path, DEFAULT)
    assert result.record == source_record(ingested_at=NOW)


def test_an_unsplit_entry_is_one_passage_with_the_canonical_identifier(
    tmp_path: Path,
) -> None:
    """Decision 2 and 3.9 together: one passage per entry, identified by the corpus's
    own function over the canonical rendering."""
    result = one_entry(tmp_path, DEFAULT)
    chunks = chunk_source(result.record, result.regions)

    assert len(chunks) == 1
    entry = loader(store(tmp_path, {"entry.md": DEFAULT})).evaluate().ingesting[0].entry
    assert chunks[0].passage.passage_id == passage_id(AUTHORED_SOURCE_ID, render(entry))
    assert chunks[0].passage.entry_location == "triage/entry.md:5"
    assert chunks[0].passage.section_title == "No sound from a track"


# --- Splitting -------------------------------------------------------------


def long_entry(causes: int = 6, words: int = 90) -> str:
    """An entry over the 350-word cap. Six causes of ~90 words is the shape 1.4 allows
    at its ceiling; the split path is rare but real."""
    body = [
        Section(
            f"Cause number {index}",
            check=" ".join(f"word{index}x{n}" for n in range(words)),
            fixes=[POINTER],
        )
        for index in range(causes)
    ]
    return entry_file(devices=[LIVE_ID], symptom="A long entry", sections=body)


def test_an_oversized_entry_splits(tmp_path: Path) -> None:
    result = one_entry(tmp_path, long_entry())
    chunks = chunk_source(result.record, result.regions)
    assert len(chunks) > 1, "the fixture is meant to exceed the cap"


def test_every_split_passage_carries_the_symptom_exactly_once(tmp_path: Path) -> None:
    """The head unit is `repeat_on_split`, so a continuation opens with the symptom —
    and overlap is not carried as well, or the symptom would appear twice in text that
    is hashed and shown to the user."""
    result = one_entry(tmp_path, long_entry())
    for chunk in chunk_source(result.record, result.regions):
        assert chunk.passage.text.count("A long entry") == 1


def test_no_cause_spans_two_passages(tmp_path: Path) -> None:
    """3.3. Every cause is atomic, so a split falls between causes and never inside one."""
    result = one_entry(tmp_path, long_entry())
    chunks = chunk_source(result.record, result.regions)
    (region,) = result.regions

    for cause in region.units[1:]:
        holding = [c for c in chunks if cause.text in c.passage.text]
        assert len(holding) == 1, f"{cause.text.split()[0]} is in {len(holding)} passages"


def test_a_split_carries_the_repeat_and_nothing_else(tmp_path: Path) -> None:
    """Design §Passage emission asks for overlap to be suppressed on authored regions;
    `manual-corpus` Decision 15 delivers it as "a repeat replaces overlap rather than
    joining it". `Chunk.carried` counts every word copied into a continuation, so
    asserting it equals the symptom block exactly says no overlap was carried as well —
    which would put the symptom into hashed, user-visible text twice."""
    result = one_entry(tmp_path, long_entry())
    chunks = chunk_source(result.record, result.regions)
    (region,) = result.regions
    head_words = len(region.units[0].text.split())

    assert len(chunks) > 1
    assert chunks[0].carried == 0
    for chunk in chunks[1:]:
        assert chunk.carried == head_words


@settings(max_examples=200)
@given(st.lists(st.tuples(prose, st.integers(min_value=1, max_value=120)), min_size=2, max_size=6))
def test_property_split_invariants(parts: list[tuple[str, int]]) -> None:
    """Over entries of every size the cap admits: the symptom is in every passage exactly
    once, and every cause is in exactly one.

    Causes stay under the cap individually, which is the case the invariant is stated for.
    A single cause longer than 350 words is 7.4's own path — the chunker divides it and
    marks every part — and is `manual-corpus`'s to hold, not an entry shape 1.4 produces.
    """
    body = [
        Section(f"Cause {index} {statement}", check=" ".join(["w"] * words), fixes=[POINTER])
        for index, (statement, words) in enumerate(parts)
    ]
    text = entry_file(devices=[LIVE_ID], symptom="A distinctive symptom line", sections=body)

    result = parse_entry(Path("triage/e.md"), text.encode("utf-8"))
    assert result.entry is not None
    region = emit(
        EntryOutcome(
            result.entry,
            causes=tuple(CauseOutcome(cause, (), False, ()) for cause in result.entry.causes),
        )
    )
    chunks = chunk_source(source_record(ingested_at=NOW), [region])

    for chunk in chunks:
        assert chunk.passage.text.count("A distinctive symptom line") == 1
    for unit in region.units[1:]:
        assert sum(unit.text in chunk.passage.text for chunk in chunks) == 1


# --- unbacked --------------------------------------------------------------


def undocumented_entry() -> str:
    """2.3's shape: one cause about gear the rig holds and no manual covers."""
    return entry_file(
        devices=[LIVE_ID, DIGITAKT_ID],
        symptom="The Digitakt is silent",
        sections=[
            Section(
                "The Digitakt output is muted",
                check="the Digitakt's own output level is at zero",
                undocumented=DIGITAKT_ID,
            ),
            Section("Another track is soloed", check="a Solo button is lit", fixes=[POINTER]),
        ],
    )


def test_a_permitted_unbacked_cause_marks_its_own_unit(tmp_path: Path) -> None:
    """2.4. The flag is per unit, so the cause carries it and its neighbour does not."""
    (region,) = one_entry(tmp_path, undocumented_entry()).regions
    head, first, second = region.units

    assert head.flags.unbacked is False
    assert first.flags.unbacked is True
    assert second.flags.unbacked is False


def test_a_permitted_unbacked_cause_is_flagged(tmp_path: Path) -> None:
    outcome = loader(store(tmp_path, {"e.md": undocumented_entry()})).evaluate()
    names = [flag.name for flag in outcome.flags]
    assert "unbacked-cause" in names
    assert outcome.ingesting[0].causes[0].unbacked is True


def test_an_unsplit_entry_marks_the_whole_passage(tmp_path: Path) -> None:
    """The over-marking 2.4 chose: one passage carrying the cause is one flagged passage,
    no worse than 2.4 mandates, and the coverage report names the cause either way."""
    result = one_entry(tmp_path, undocumented_entry())
    (chunk,) = chunk_source(result.record, result.regions)
    assert chunk.passage.unbacked is True


def test_a_backed_entry_is_not_flagged(tmp_path: Path) -> None:
    """No passage is flagged without an unbacked cause — the property's second half."""
    result = one_entry(tmp_path, DEFAULT)
    (chunk,) = chunk_source(result.record, result.regions)
    assert chunk.passage.unbacked is False
    assert all(not unit.flags.unbacked for unit in result.regions[0].units)


def test_a_split_entry_marks_only_the_passage_carrying_the_cause(tmp_path: Path) -> None:
    """8.5's per-passage precision, which is why the flag is on the unit and not the
    region: a long entry with one unbacked cause leaves its other passages clean."""
    filler = " ".join(f"padding{n}" for n in range(180))
    """Two causes of this length exceed the 350-word cap together and neither does alone,
    so the split falls between them and the unbacked third cause lands in the second."""
    text = entry_file(
        devices=[LIVE_ID, DIGITAKT_ID],
        symptom="A long entry with one unbacked cause",
        sections=[
            Section("First cause", check=filler, fixes=[POINTER]),
            Section("Second cause", check=filler, fixes=[POINTER]),
            Section(
                "The Digitakt output is muted",
                check="the Digitakt's own output level is at zero",
                undocumented=DIGITAKT_ID,
            ),
        ],
    )
    result = one_entry(tmp_path, text)
    chunks = chunk_source(result.record, result.regions)
    (region,) = result.regions

    assert len(chunks) > 1
    flagged = [chunk for chunk in chunks if chunk.passage.unbacked]
    assert len(flagged) == 1
    assert region.units[-1].text in flagged[0].passage.text


def test_a_drifted_pointer_marks_its_cause(tmp_path: Path) -> None:
    """8.5's other producer. The ledger says the pointer once resolved, so the entry is
    served with the cause marked rather than withdrawn."""
    ledger = Ledger.empty()
    ledger.record(f"{LIVE_ID} §18.6", ["ableton/live-12#4d7339c32b29d043"], [], NOW)
    text = (FIXTURES / "drift" / "soloed-track.md").read_text(encoding="utf-8")

    result = one_entry(tmp_path, text, corpus=drifted_view(), ledger=ledger)
    (region,) = result.regions

    assert region.units[1].flags.unbacked is True  # the cause pointing at §18.6
    assert region.units[2].flags.unbacked is False


def test_a_pointer_that_never_resolved_rejects_the_entry(tmp_path: Path) -> None:
    """2.2, the same fixture with an empty ledger: no row anywhere, so the author wrote
    the pointer wrong rather than a manual having moved."""
    text = (FIXTURES / "drift" / "soloed-track.md").read_text(encoding="utf-8")
    outcome = loader(store(tmp_path, {"e.md": text}), corpus=drifted_view()).evaluate()

    assert [r.reason for r in outcome.rejections] == ["pointer-unresolved"]
    assert outcome.ingesting == ()
    assert "§18.6" in outcome.rejections[0].detail


def test_the_same_entry_ingests_against_the_undrifted_corpus(tmp_path: Path) -> None:
    text = (FIXTURES / "drift" / "soloed-track.md").read_text(encoding="utf-8")
    result = one_entry(tmp_path, text)
    (region,) = result.regions
    assert all(not unit.flags.unbacked for unit in region.units)


def test_an_authored_target_rejects(tmp_path: Path) -> None:
    """2.7. An entry cites a manual; it cannot cite the notes."""
    text = entry_file(
        devices=[LIVE_ID],
        symptom="Circular",
        sections=[
            Section("A cause", check="c", fixes=['authored/triage "Anything"']),
            Section("Another cause", check="c", fixes=[POINTER]),
        ],
    )
    outcome = loader(store(tmp_path, {"e.md": text})).evaluate()
    assert [r.reason for r in outcome.rejections] == ["pointer-authored-target"]


# --- 1.9, over intersecting scopes -----------------------------------------


def test_overlapping_scopes_reject_both(tmp_path: Path) -> None:
    """Intersection, not set equality: `[live-12]` and `[live-12, apc-key-25]` are not
    equal, and both are retrievable in any Live-scoped turn."""
    root = tmp_path / "triage"
    shutil.copytree(FIXTURES / "overlapping_scopes", root)
    result = loader(root).evaluate()

    assert [r.reason for r in result.rejections] == ["duplicate-symptom"] * 2
    assert result.ingesting == ()
    assert {r.source_file.name for r in result.rejections} == {
        "live-and-apc.md",
        "live-only.md",
    }


def test_a_shared_symptom_in_disjoint_scopes_ingests_both(tmp_path: Path) -> None:
    """1.9 is about being returned for one question, not about writing one sentence
    twice: two devices that share no scope share no turn."""
    files = {
        "live.md": entry_file(
            devices=[LIVE_ID], symptom="A pad triggers the wrong sound", sections=DEFAULT_BODY
        ),
        "apc.md": entry_file(
            devices=[APC_ID],
            symptom="A pad triggers the wrong sound",
            sections=[
                Section("The channel is wrong", check="c", fixes=[f'{APC_ID} "Basic Operation"']),
                Section("The mapping is wrong", check="c", fixes=[POINTER]),
            ],
        ),
    }
    result = loader(store(tmp_path, files)).evaluate()
    assert result.rejections == ()
    assert len(result.ingesting) == 2


def test_the_symptom_comparison_is_normalised(tmp_path: Path) -> None:
    assert normalised_symptom("  No SOUND   from a track ") == "no sound from a track"


def test_a_symptom_opening_with_a_number_keeps_it() -> None:
    """Not `normalise_title`, which strips a leading section number: two symptoms that
    differ only in a leading figure are two symptoms."""
    assert normalised_symptom("0 dB is never reached") != normalised_symptom("dB is never reached")


# --- entry_location --------------------------------------------------------


def test_entry_location_is_published_and_never_hashed(tmp_path: Path) -> None:
    """3.5 and CONTRACTS §2. The same entry at two paths is one identifier and two
    locations."""
    here = one_entry(tmp_path / "one", DEFAULT)
    there = loader(store(tmp_path / "two", {"nested/entry.md": DEFAULT})).load(DISCOVERED)

    (a,) = chunk_source(here.record, here.regions)
    (b,) = chunk_source(there.record, there.regions)

    assert a.passage.entry_location == "triage/entry.md:5"
    assert b.passage.entry_location == "triage/nested/entry.md:5"
    assert a.passage.passage_id == b.passage.passage_id


def test_the_region_and_the_entry_agree_on_the_location(tmp_path: Path) -> None:
    outcome = loader(store(tmp_path, {"entry.md": DEFAULT})).evaluate()
    (region,) = [emit(o) for o in outcome.ingesting]
    assert region.entry_location == entry_location(outcome.ingesting[0].entry)


# --- Rejections leave the rest of the store alone --------------------------


def test_one_bad_entry_does_not_withdraw_the_others(tmp_path: Path) -> None:
    """5.2: a rejection excludes one entry, the rest ingest, the run succeeds."""
    files = {
        "good.md": DEFAULT,
        "bad.md": "no frontmatter at all\n",
    }
    result = loader(store(tmp_path, files)).load(DISCOVERED)
    assert len(result.regions) == 1
    assert result.regions[0].section_title == "No sound from a track"


def test_dotfiles_are_not_entries(tmp_path: Path) -> None:
    """`.pointer-ledger.jsonl` lives in the store and must never present itself as one."""
    root = store(tmp_path, {"entry.md": DEFAULT})
    (root / ".notes.md").write_text("# not an entry\n", encoding="utf-8")
    assert [p.name for p in loader(root).entry_files()] == ["entry.md"]
