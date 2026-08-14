"""Region[] -> Passage[]: greedy packing to the 350-word cap.

Stage 8, and the whole output of this spec. The design's emission contract — §`Region`/`Unit`
-> `Passage` — says every `Passage` field comes from exactly one rule, and this module is
that table: nothing here invents a field, and `unbacked` and `entry_location` are carried
from the loader untouched (12.6).

Four rules carry the weight:

- **Packing restarts at every region.** 6.7 forbids a chunk spanning two sections, and
  overlap never crosses a region boundary. That is also what confines the blast radius of a
  vendor edit to one section rather than to the rest of the manual (Decision 5).
- **Pages come from the chunk's own units.** A copied heading and carried-over overlap
  contribute their words but not their pages. Without the exclusion a split table's
  continuation chunk records p25-26 from a heading copied off p25 while every row it holds
  is on p26, and CONTRACTS §3's open-at-page lands on a page holding none of the rows quoted
  (6.8).
- **A repeat replaces overlap, never joins it.** Where a chunk copies a `repeat_on_split`
  unit — a table's joined heading (7.5), an authored entry's symptom statement — the repeat
  already gives the continuity overlap exists to provide, and carrying both would put that
  text into the hashed passage twice (`data/symptom-triage` §Passage emission).
- **The citation header is indexed but is not `Passage.text`.** The text is what the user is
  shown when a citation is expanded, and repeating the header there duplicates what the
  citation already renders.

The word cap is an estimate of a token bound, and the estimate is worst for the serialised
table rows this corpus is full of, so `token_budget` measures the real encoded length at
embed time rather than trusting the count (Decision 3).
"""

from __future__ import annotations

import re
from collections import deque
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from dawmans.corpus.loader import Region, Unit
from dawmans.corpus.passage_id import assign_ids
from dawmans.records import Passage, SourceRecord

#: 6.9. Not readability: 500 words measures ~601 tokens against a 512-token embedding
#: window, so the tail of every maximal chunk would be silently invisible to retrieval while
#: still appearing in the text shown to the user (Decision 3).
WORD_CAP = 350

#: How much of the previous chunk a continuation carries, snapped to a sentence boundary so
#: it opens mid-thought rather than mid-sentence.
OVERLAP_WORDS = 50

#: `bge-small-en-v1.5`'s input window, and how close to it a chunk may come before the run
#: report names it. Overflow is not an error but a silent truncation, so it is measured.
TOKEN_WINDOW = 512
TOKEN_MARGIN = 32

#: One line per source line (3.5), so a procedure reads as discrete steps.
UNIT_JOIN = "\n"

_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


class PageRangeError(Exception):
    """A chunk's page falls outside its source's own page range (6.11).

    6.11 says to reject the source, which 1.6's closed rejection list does not admit and
    which would discard a 1009-page primary source over one mis-anchored chunk while
    reporting the run as succeeded. It is a failure instead: the source's previous shard
    stays intact, the offending chunk and page are named, and the run exits non-zero.
    """


@dataclass(frozen=True)
class Chunk:
    """One passage, plus what only the chunker knows about how it was packed."""

    passage: Passage
    #: Embedded and BM25-indexed with the text; never part of `Passage.text`.
    header: str
    #: Every unit contributing text, copied units included. The flags are the OR over these.
    units: tuple[Unit, ...]
    #: Leading words copied in — a repeated heading, or overlap. Removing them from every
    #: chunk of a region and concatenating gives the region's own text back, in order.
    carried: int
    #: 7.4: this chunk carries part of one atomic unit that was itself over the cap.
    partial_unit: bool = False

    @property
    def embedded(self) -> str:
        """What the dense and lexical indexes encode: the citation header, then the text."""
        return f"{self.header}\n{self.passage.text}"


def citation_header(display_name: str, region: Region) -> str:
    """The prefix every chunk is indexed under (design §Chunking).

    The `§` and the number are omitted **entirely** where the region has no number rather
    than rendered as `§None`, which is the common case on an APC region and on every
    authored passage. The ancestor chain is carried because 54 of Live's section titles are
    duplicated across its outline and `Sidechain Parameters` occurs eight times — without
    it, that chunk is indexed with the device name nowhere in it.
    """
    if region.page_start is None:  # pageless authored: an entry has no ancestors (12.8)
        return f"{display_name} — {region.section_title}"

    titles = " › ".join((*region.section_path, region.section_title))
    if region.section_number is None:
        return f"{display_name} — {titles}"
    return f"{display_name} — §{region.section_number} {titles}"


def chunk_source(record: SourceRecord, regions: Sequence[Region]) -> list[Chunk]:
    """Every passage one source contributes, in document order.

    Identifiers are assigned across the whole source rather than per region, because the
    duplicate rule of 6.1 is source-scoped: repeated boilerplate in two sections is two
    passages, and the first in document order keeps the unsuffixed identifier.
    """
    packed = [(region, part) for region in regions for part in _pack(region)]
    ids = assign_ids(record.source_id, [part.text for _, part in packed])
    return [
        _chunk(record, region, part, passage_id)
        for (region, part), passage_id in zip(packed, ids, strict=True)
    ]


def check_pages(record: SourceRecord, chunks: Sequence[Chunk]) -> None:
    """6.11, as a failure rather than a rejection. Skipped entirely for a pageless source:
    12.8 says such a source SHALL NOT be rejected, flagged or delayed by this check."""
    if record.page_count is None:
        return
    for chunk in chunks:
        for page in (chunk.passage.page_start, chunk.passage.page_end):
            if page is not None and not 1 <= page <= record.page_count:
                raise PageRangeError(
                    f"{chunk.passage.passage_id} records page {page}, outside "
                    f"{record.source_id}'s range 1-{record.page_count} (6.11)"
                )


def token_budget(
    chunks: Sequence[Chunk], count: Callable[[str], int]
) -> tuple[list[tuple[str, int]], list[tuple[str, int]]]:
    """`(over, near)` — the chunks whose header-prefixed encoding reaches the window, and
    those within `TOKEN_MARGIN` of it (Decision 3).

    `count` is the embedding model's own tokeniser, which is already loaded at embed time,
    so measuring costs nothing and converts a silent truncation into a report line. A chunk
    that trips it has no automatic remedy — re-splitting would change every `passage_id` in
    its region — so it is reported and left.
    """
    over: list[tuple[str, int]] = []
    near: list[tuple[str, int]] = []
    for chunk in chunks:
        tokens = count(chunk.embedded)
        if tokens >= TOKEN_WINDOW:
            over.append((chunk.passage.passage_id, tokens))
        elif tokens >= TOKEN_WINDOW - TOKEN_MARGIN:
            near.append((chunk.passage.passage_id, tokens))
    return over, near


@dataclass(frozen=True)
class _Part:
    """One packed chunk, before it becomes a `Passage`."""

    text: str
    units: tuple[Unit, ...]  # every contributor, copies included — the flags OR over these
    own: tuple[Unit, ...]  # the page-contributing ones (6.8)
    carried: int
    partial_unit: bool


def _pack(region: Region) -> list[_Part]:
    """Greedy packing within one region (6.7-6.10, 7.4-7.5)."""
    parts: list[_Part] = []
    queue: deque[tuple[Unit, bool]] = deque(
        (unit, False) for unit in region.units if unit.text.split()
    )
    head: tuple[Unit, ...] = ()  # repeated units copied to the front of this chunk
    overlap = ""
    own: list[tuple[Unit, bool]] = []
    carried = 0
    used = 0
    repeats: tuple[Unit, ...] = ()
    running = False  # the previously placed unit was `repeat_on_split`; the run continues

    def place(unit: Unit, partial: bool) -> None:
        """Add a unit to the chunk being packed, and keep the repeat run up to date.

        The bookkeeping belongs here rather than at the top of the loop because a unit that
        does not fit is put back on the queue and seen twice; counting it twice would copy
        one heading into the next chunk two times over.
        """
        nonlocal running, repeats, used
        if unit.repeat_on_split:
            repeats = (*repeats, unit) if running else (unit,)
        running = unit.repeat_on_split
        own.append((unit, partial))
        used += _words(unit.text)

    def start(previous: tuple[Unit, bool]) -> None:
        nonlocal head, overlap, own, carried, used
        head, overlap = _continuation(repeats, previous[0], queue)
        own = []
        carried = sum(_words(unit.text) for unit in head) + _words(overlap)
        used = carried

    while queue:
        unit, partial = queue.popleft()

        if used + _words(unit.text) <= WORD_CAP:
            place(unit, partial)
            continue

        if own:  # close this chunk and try the unit again at the front of the next one
            previous = own[-1]
            parts.append(_part(head, overlap, own, carried))
            queue.appendleft((unit, partial))
            start(previous)
            continue

        # A chunk holding nothing but its carried words still cannot take the unit whole:
        # split it, and mark every part where it was atomic (7.4).
        marked = partial or unit.atomic
        first, rest = _split(unit, WORD_CAP - used)
        place(first, marked)
        parts.append(_part(head, overlap, own, carried))
        queue.appendleft((rest, marked))
        start((first, marked))

    if own:
        parts.append(_part(head, overlap, own, carried))
    return parts


def _continuation(
    repeats: tuple[Unit, ...], previous: Unit, queue: deque[tuple[Unit, bool]]
) -> tuple[tuple[Unit, ...], str]:
    """What the next chunk of this region starts with: a repeat, or overlap, never both.

    The repeats are dropped where the next unit is itself a `repeat_on_split` one — a second
    table starting in the same region — because copying the first table's heading onto rows
    it does not describe is worse than no heading at all. They are dropped again where they
    would leave the chunk no room, which is a heading longer than the cap.

    Overlap is taken only across a non-atomic unit. Across an atomic one it is forbidden
    outright (6.10, 7.4): a table row or a numbered procedure is never partly repeated.
    """
    if queue and queue[0][0].repeat_on_split:
        repeats = ()
    if sum(_words(unit.text) for unit in repeats) >= WORD_CAP:
        repeats = ()
    if repeats:
        return repeats, ""
    return (), "" if previous.atomic else _overlap(previous.text)


def _split(unit: Unit, room: int) -> tuple[Unit, Unit]:
    """The unit's first `room` words and the rest, snapped to a sentence boundary where one
    falls inside the room. Both halves keep the unit's pages and flags: a split row is still
    on the page it was printed on, and still degraded if it held an unmappable span."""
    room = max(room, 1)
    words = unit.text.split()
    cut = _sentence_cut(unit.text, room) or room
    return _replace(unit, " ".join(words[:cut])), _replace(unit, " ".join(words[cut:]))


def _sentence_cut(text: str, room: int) -> int:
    """The largest number of whole sentences that fits in `room` words, in words; 0 where
    the first sentence already exceeds it and there is no boundary to snap to."""
    total = 0
    for sentence in _SENTENCE_END.split(text):
        length = _words(sentence)
        if total + length > room:
            break
        total += length
    return total


def _replace(unit: Unit, text: str) -> Unit:
    return Unit(
        text=text,
        page_start=unit.page_start,
        page_end=unit.page_end,
        atomic=unit.atomic,
        repeat_on_split=unit.repeat_on_split,
        flags=unit.flags,
    )


def _overlap(text: str) -> str:
    """~`OVERLAP_WORDS` trailing words, snapped to a sentence boundary.

    A single sentence longer than the overlap has no boundary to snap to, so it is cut to
    the last `OVERLAP_WORDS` words — a bounded fallback rather than carrying the sentence
    whole and eating the next chunk's room.
    """
    kept: list[str] = []
    total = 0
    for sentence in reversed(_SENTENCE_END.split(text)):
        length = _words(sentence)
        if kept and total + length > OVERLAP_WORDS:
            break
        kept.insert(0, sentence)
        total += length
        if total >= OVERLAP_WORDS:
            break
    joined = " ".join(kept)
    return " ".join(joined.split()[-OVERLAP_WORDS:]) if total > OVERLAP_WORDS else joined


def _part(
    head: tuple[Unit, ...], overlap: str, own: list[tuple[Unit, bool]], carried: int
) -> _Part:
    units = tuple(unit for unit, _ in own)
    return _Part(
        text=_text(head, overlap, units),
        units=(*head, *units),
        own=units,
        carried=carried,
        partial_unit=any(partial for _, partial in own),
    )


def _text(head: Sequence[Unit], overlap: str, own: Sequence[Unit]) -> str:
    lines = [unit.text for unit in head]
    if overlap:
        lines.append(overlap)
    lines.extend(unit.text for unit in own)
    return UNIT_JOIN.join(lines)


def _words(text: str) -> int:
    return len(text.split())


def _chunk(record: SourceRecord, region: Region, part: _Part, passage_id: str) -> Chunk:
    pages = [page for unit in part.own for page in (unit.page_start, unit.page_end) if page]
    return Chunk(
        passage=Passage(
            passage_id=passage_id,
            source_id=record.source_id,
            section_number=region.section_number,
            section_title=region.section_title,
            page_start=min(pages) if pages else None,
            page_end=max(pages) if pages else None,
            text=part.text,
            degraded=any(unit.flags.degraded for unit in part.units),
            has_figures=any(unit.flags.has_figures for unit in part.units),
            unbacked=any(unit.flags.unbacked for unit in part.units),
            entry_location=region.entry_location,
        ),
        header=citation_header(record.display_name, region),
        units=part.units,
        carried=part.carried,
        partial_unit=part.partial_unit,
    )


__all__ = [
    "OVERLAP_WORDS",
    "TOKEN_MARGIN",
    "TOKEN_WINDOW",
    "UNIT_JOIN",
    "WORD_CAP",
    "Chunk",
    "PageRangeError",
    "check_pages",
    "chunk_source",
    "citation_header",
    "token_budget",
]
