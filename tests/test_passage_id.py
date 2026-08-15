"""Passage identity — requirement 6.1 and decision_log Decision 5.

The passage ID is the one thing in this spec a user can hold across a restart: the UI keeps
prior exchanges, and a citation in that history must still resolve after its source is
re-ingested (6.1). `data/symptom-triage` raises the bar again — a fix pointer has to survive
a manual being replaced by a different document version of the same product (its 8.2-8.3).

Everything below follows from that. The digest covers the chunk's body text and nothing
else, so a point release that renumbers sections or moves pages changes no ID; whitespace
and Unicode composition are normalised away, because a re-extraction differing only in line
wrapping would otherwise orphan every citation at once; case is kept, because 3.1 keeps
casing and two chunks differing only in case are different text.

**Determinism is a property of the pipeline, not of the hash.** A stage that iterated a set,
keyed on insertion order or consulted the clock would move chunk boundaries and therefore
IDs while `passage_id` stayed correct, so the guarantee is tested end to end over the same
PDF bytes rather than by re-hashing one string.
"""

from __future__ import annotations

from pathlib import Path
from unicodedata import normalize as normalised  # spelling-ignore: the stdlib's own name

from hypothesis import given
from hypothesis import strategies as st

from dawmans.corpus.chunk import chunk_source
from dawmans.corpus.loader import Region, Unit, UnitFlags
from dawmans.corpus.passage_id import assign_ids, canonical, passage_id
from dawmans.corpus.pdf.loader import PdfLoader
from dawmans.records import AUTHORED_SOURCE_ID, HardwareApplicability, SourceRecord
from pdfgen import Page, lines, write_pdf

SOURCE = "ableton/live-12"

# Real sentences, because the chunker packs by word count and the overlap snaps to a
# sentence boundary; nonsense of the right length would exercise neither.
PROSE = (
    "The tempo control sets the speed of the transport in beats per minute. "
    "The value is shown in the control bar at the top of the window. "
    "Tap tempo follows the rhythm you play on the key."
)

text = st.text(min_size=1).filter(lambda value: value.strip())


def record(source_id: str = SOURCE, *, doc_version: str = "12", pages: int = 40) -> SourceRecord:
    return SourceRecord(
        kind="vendor-manual",
        source_id=source_id,
        vendor=source_id.split("/")[0],
        product=source_id.split("/")[1],
        doctype="manual",
        lang="en",
        doc_version=doc_version,
        display_name="Ableton Live 12",
        hardware_applicability=HardwareApplicability(status="assumed", device=source_id),
        page_count=pages,
        ingested_at="2026-08-15T10:00:00+00:00",
        chunk_count=0,
        low_text=False,
    )


def authored_record() -> SourceRecord:
    return SourceRecord(
        kind="authored-triage",
        source_id=AUTHORED_SOURCE_ID,
        display_name="Triage notes",
        hardware_applicability=HardwareApplicability(status="assumed"),
        ingested_at="2026-08-15T10:00:00+00:00",
        chunk_count=0,
    )


def region(
    *bodies: str,
    number: str | None = "24.1",
    title: str = "An Overview of Racks",
    page: int = 11,
) -> Region:
    return Region(
        section_number=number,
        section_title=title,
        section_path=("Racks",),
        page_start=page,
        page_end=page,
        inferred=False,
        units=[Unit(text=body, page_start=page, page_end=page) for body in bodies],
    )


def ids(source: SourceRecord, *regions: Region) -> list[str]:
    return [chunk.passage.passage_id for chunk in chunk_source(source, regions)]


# --- The digest: what is in it and what is not ------------------------------------------------


def test_the_source_id_is_a_visible_prefix_and_is_not_hashed() -> None:
    """Decision 5: carrying it in the clear makes cross-source collisions impossible by
    construction and lets `fetch-passage` route on the prefix without a lookup."""
    value = passage_id(SOURCE, PROSE)

    prefix, _, digest = value.partition("#")
    assert prefix == SOURCE
    assert len(digest) == 16
    assert passage_id("akai/apc-key-25", PROSE).endswith(f"#{digest}")


@given(body=text)
def test_the_id_is_a_pure_function_of_the_canonical_text(body: str) -> None:
    """6.1: re-ingesting a source yields the same ID for every chunk whose text is
    unchanged. Two texts with the same canonical form are the same text."""
    assert passage_id(SOURCE, body) == passage_id(SOURCE, canonical(body))


@given(body=text)
def test_whitespace_runs_collapse(body: str) -> None:
    """A re-extraction differing only in line wrapping - a plausible consequence of a
    library upgrade - must not orphan every citation in the retained history at once."""
    rewrapped = "\n  ".join(body.split(" "))

    assert passage_id(SOURCE, rewrapped) == passage_id(SOURCE, " ".join(body.split()))


def test_the_nfc_form_is_not_a_different_passage() -> None:
    """Unicode composition carries no meaning here: `ô` decomposed and composed are the
    same printed character and must not be two passages."""
    composed = "Réglage du tempo"
    decomposed = normalised("NFD", composed)

    assert decomposed != composed
    assert passage_id(SOURCE, decomposed) == passage_id(SOURCE, composed)


def test_case_is_preserved() -> None:
    """3.1 keeps casing, so two chunks differing only in case are genuinely different
    text. Folding here would merge a heading with its own body line."""
    assert passage_id(SOURCE, "Tempo Control") != passage_id(SOURCE, "tempo control")


@given(body=text, extra=st.text(min_size=1).filter(lambda value: value.strip()))
def test_any_text_change_alters_the_id(body: str, extra: str) -> None:
    """The other half of 6.1: an edit mints a new ID, because the text changed."""
    edited = f"{body} {extra}"

    if canonical(edited) != canonical(body):
        assert passage_id(SOURCE, edited) != passage_id(SOURCE, body)


# --- Metadata invariance (6.1, triage 8.2-8.3) -------------------------------------------------


def test_the_document_version_never_enters_the_digest() -> None:
    """triage 8.3: replacing v12 with v12.1 must not orphan an authored fix pointer. The
    version sits outside `source_id` for the same reason."""
    body = region(PROSE)

    assert ids(record(doc_version="12"), body) == ids(record(doc_version="12.1"), body)


def test_page_offsets_never_enter_the_digest() -> None:
    """A reflowed or repaginated revision moves every page number in the document."""
    on_page_11 = region(PROSE, page=11)
    on_page_54 = region(PROSE, page=54)

    assert ids(record(), on_page_11) == ids(record(), on_page_54)


def test_section_numbers_and_titles_never_enter_the_digest() -> None:
    """Live point releases renumber sections. An identity holding the number would break on
    a routine manual update, silently flagging every authored entry as unbacked."""
    before = region(PROSE, number="24.1", title="An Overview of Racks")
    after = region(PROSE, number="25.3", title="Racks Overview")

    assert ids(record(), before) == ids(record(), after)


def test_entry_location_never_enters_the_digest() -> None:
    """CONTRACTS §2 states it directly: the author moves entries between files, and the
    location is a locator rather than an identity."""
    source = authored_record()
    units = [Unit(text=PROSE, flags=UnitFlags(unbacked=True))]

    def entry(location: str) -> Region:
        return Region(
            section_number=None,
            section_title="No sound from a track",
            section_path=(),
            page_start=None,
            page_end=None,
            inferred=False,
            units=units,
            entry_location=location,
        )

    moved = ids(source, entry("triage/no-sound.md:7"))

    assert moved == ids(source, entry("triage/archive/no-sound.md:114"))


# --- Uniqueness and the duplicate rule ---------------------------------------------------------


def test_ids_are_pairwise_distinct_within_a_source() -> None:
    """Byte-identical chunks included: the retained history addresses one passage, so two
    passages may not answer to one ID."""
    boilerplate = "Refer to the safety instructions before use."
    chunks = chunk_source(
        record(),
        [
            region(boilerplate, page=3),
            region(PROSE, page=11),
            region(boilerplate, page=57, number="41.2", title="Safety"),
        ],
    )

    values = [chunk.passage.passage_id for chunk in chunks]

    assert len(set(values)) == len(values)


def test_a_duplicate_takes_the_suffix_and_the_first_keeps_the_bare_id() -> None:
    """Decision 5, and it is asymmetric on purpose."""
    boilerplate = "Refer to the safety instructions before use."

    first, second, third = assign_ids(SOURCE, [boilerplate, boilerplate, boilerplate])

    assert first == passage_id(SOURCE, boilerplate)
    assert (second, third) == (f"{first}.2", f"{first}.3")


def test_a_new_duplicate_leaves_the_pre_existing_id_unchanged() -> None:
    """Duplicate stability (design §Property-based tests). Suffixing all k occurrences
    would mean that newly acquiring a second copy of some boilerplate destroys the stable
    ID of the first copy, whose text did not change - a citation held in retained UI
    history stops resolving because of an edit somewhere else in the document."""
    boilerplate = "Refer to the safety instructions before use."
    before = assign_ids(SOURCE, [boilerplate, PROSE])
    after = assign_ids(SOURCE, [boilerplate, PROSE, boilerplate])

    assert after[: len(before)] == before


def test_a_duplicate_introduced_earlier_promotes_and_is_the_known_cost() -> None:
    """The negative consequence Decision 5 accepts, pinned so it is a decision rather than
    a surprise: order is document order, so a duplicate inserted *before* an existing one
    takes the bare ID and the existing chunk becomes `.2`."""
    boilerplate = "Refer to the safety instructions before use."
    before = assign_ids(SOURCE, [PROSE, boilerplate])
    after = assign_ids(SOURCE, [boilerplate, PROSE, boilerplate])

    assert after[0] == before[1]
    assert after[2] == f"{before[1]}.2"


@given(bodies=st.lists(text, min_size=1, max_size=12))
def test_assignment_is_unique_and_order_dependent_only(bodies: list[str]) -> None:
    values = assign_ids(SOURCE, bodies)

    assert len(set(values)) == len(values)
    assert all(value.startswith(f"{SOURCE}#") for value in values)


# --- Determinism over the whole pipeline (6.1) -------------------------------------------------


def manual(path: Path) -> Path:
    """A synthetic manual with enough text to split a region and repeat a line, so the
    chunker's own ordering is exercised rather than a single-chunk document."""
    body = [
        "The tempo control sets the speed of the transport in beats per minute.",
        "The value is shown in the control bar at the top of the window.",
        "Tap tempo follows the rhythm you play on the key.",
        "Refer to the safety instructions before use.",
    ]
    return write_pdf(
        path,
        [
            Page(texts=lines("Setting Up", *body)),
            Page(texts=lines("Transport", *body, "Refer to the safety instructions before use.")),
        ],
    )


def ingested(root: Path) -> list[tuple[str, str]]:
    loader = PdfLoader(root=root, now=lambda: "2026-08-15T10:00:00+00:00")
    (found,) = loader.discover()
    result = loader.load(found)
    chunks = chunk_source(result.record, result.regions)
    return [(chunk.passage.passage_id, chunk.passage.text) for chunk in chunks]


def test_the_same_bytes_ingested_twice_yield_the_same_passages(tmp_path: Path) -> None:
    """Run determinism (design §Property-based tests): the whole pipeline is a pure
    function of the PDF bytes. A stage that iterated a set or keyed on a dictionary's
    insertion order would change chunk boundaries, and therefore IDs, while `passage_id`
    stayed correct - which is why this is asserted end to end."""
    first = tmp_path / "one" / "ableton_live-12_manual_v12_en.pdf"
    second = tmp_path / "two" / "ableton_live-12_manual_v12_en.pdf"
    manual(first)
    second.parent.mkdir(parents=True, exist_ok=True)
    second.write_bytes(first.read_bytes())

    passages = ingested(first.parent)

    assert passages
    assert passages == ingested(second.parent)
    assert passages == ingested(first.parent)


def test_the_same_bytes_at_a_different_version_yield_the_same_ids(tmp_path: Path) -> None:
    """triage 8.3 end to end: a v12 -> v12.1 replacement of the same document keeps every
    fix pointer resolving, because nothing outside the body text is hashed."""
    first = tmp_path / "one" / "ableton_live-12_manual_v12_en.pdf"
    second = tmp_path / "two" / "ableton_live-12_manual_v12.1_en.pdf"
    manual(first)
    second.parent.mkdir(parents=True, exist_ok=True)
    second.write_bytes(first.read_bytes())

    assert ingested(first.parent) == ingested(second.parent)
