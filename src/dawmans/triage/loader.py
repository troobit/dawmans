"""`TriageLoader` — the entry store behind `manual-corpus`'s `SourceLoader` seam.

Identity and emission, which are one subject: the text a `Unit` carries is the text
`corpus.passage_id` hashes, and `parse.render_blocks` is the single construction of it
(design §Identity, "there is no second canonical form").

Two things this module deliberately does **not** do:

- **It mints no identifier.** `chunk_source` assigns every `passage_id` from the packed
  text, so an authored passage is identified by the same function over the same canonical
  form as a manual passage (3.9). A second minting here would be a second rule to keep in
  step with the chunker's packing.
- **It suppresses no overlap.** Design §Passage emission asks for it, and the corpus
  chunker already delivers it for any region whose first unit is `repeat_on_split`:
  `manual-corpus` Decision 15 states the rule as "a repeat replaces overlap rather than
  joining it", which reaches this case without the chunker knowing what kind of source it
  has (12.2). See decision_log Decision 12 — the edit task 16 reserved here was made
  upstream, generalised, and making it again would double the symptom in hashed text.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Collection, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from dawmans.corpus.loader import Discovered, LoadResult, Region, Unit, UnitFlags
from dawmans.records import AUTHORED_SOURCE_ID, HardwareApplicability, SourceRecord
from dawmans.triage.model import Cause, Entry, EntryRejection, Flag
from dawmans.triage.parse import parse_entry, render_blocks
from dawmans.triage.pointers import Ledger, PointerOutcome, SectionIndex, check_pointer
from dawmans.triage.scope import RigDevice, validate_scope

#: CONTRACTS §1. It reads in the citation header and in the source picker as the user's own
#: notes rather than as a vendor document (3.1), so a citation renders as
#: `My Triage Notes — No sound from a track`.
DISPLAY_NAME = "My Triage Notes"

#: What the record carries before the source has been chunked, exactly as `PdfLoader` does.
#: The shard build owns the real value and rewrites the record with it. The constant is
#: restated rather than imported: `corpus/pdf/loader.py` imports PyMuPDF, which
#: `manual-corpus` Decision 6 confines to `corpus/pdf/`.
UNCHUNKED = 0

_WHITESPACE = re.compile(r"\s+")


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def source_record(*, ingested_at: str, chunk_count: int = UNCHUNKED) -> SourceRecord:
    """The one record every authored passage and citation resolves to (3.7).

    Every field is fixed by design §Identity and CONTRACTS §1 rather than read from the
    store, and the two that are not — the timestamp and the chunk count — are inventory.
    `hardware_applicability` is `assumed` unconditionally and nothing in configuration can
    raise it: the store is not about one device, and 3.8's literal text is a recorded
    defect. `vendor`, `product`, `doctype`, `lang`, `doc_version`, `page_count` and
    `low_text` are not passed at all — `manual-corpus` 12.5's constructor refuses a value
    for each of them rather than defaulting one into place.
    """
    return SourceRecord(
        kind="authored-triage",
        source_id=AUTHORED_SOURCE_ID,
        display_name=DISPLAY_NAME,
        hardware_applicability=HardwareApplicability(status="assumed"),
        ingested_at=ingested_at,
        chunk_count=chunk_count,
    )


def entry_location(entry: Entry) -> str:
    """CONTRACTS §2: one opaque `<path>:<line>` display string, the path repo-relative.

    Published with the passage and never hashed. The author moves entries between files,
    so it is a locator and not an identity — `render_blocks` excludes both halves.
    """
    return f"{entry.source_file.as_posix()}:{entry.line}"


def normalised_symptom(symptom: str) -> str:
    """The form 1.9 compares two entries on: casefolded, whitespace runs collapsed.

    Deliberately **not** `pointers.normalise_title`, which also strips a leading section
    number: a symptom may legitimately open with one — "0 dB is never reached" — and
    stripping it would collide two symptoms that differ.
    """
    return _WHITESPACE.sub(" ", symptom).strip().casefold()


@dataclass(frozen=True)
class CorpusView:
    """What the loader reads of the corpus, and the whole of it (5.7).

    Read-only, and never a shard, a vector file or a PDF, so re-ingesting the authored
    source cannot re-extract, re-chunk or re-index a manual (`manual-corpus` 12.4). Stated
    here as the two things Phase 4 reads, in the way `scope.RigDevice` states the two
    fields it reads: the reader that builds one from `views/<hex>/` is the run wiring's.
    """

    sections: SectionIndex
    """Built once per run, so every pointer in a run resolves against one corpus."""

    indexed: Collection[str]
    """Every identity the corpus documents — see `scope.validate_scope` (Decision 8)."""


@dataclass(frozen=True)
class CauseOutcome:
    """One cause of an ingesting entry, after its pointers have been checked."""

    cause: Cause
    pointers: tuple[PointerOutcome, ...]
    unbacked: bool
    """2.4 and 8.5, the only two producers of the mark: a cause 2.3 permits to carry no
    pointer, and a cause whose pointer has drifted. A term miss never sets it (Decision 5)."""

    passage_ids: tuple[str, ...]
    """Every passage the cause's pointers resolve to, in pointer then section order."""


@dataclass(frozen=True)
class EntryOutcome:
    """One entry file that parsed, and what the run decided about it."""

    entry: Entry
    rejection: EntryRejection | None = None
    flags: tuple[Flag, ...] = ()
    scoped: tuple[str, ...] = ()
    causes: tuple[CauseOutcome, ...] = ()

    @property
    def ingested(self) -> bool:
        return self.rejection is None


@dataclass(frozen=True)
class StoreOutcome:
    """The whole store's verdict, before any of it is emitted.

    Separate from `LoadResult` because the rejections and flags outlive emission: the
    sidecar's report block and `dawmans validate` both read them, and `validate` emits no
    passages at all.
    """

    outcomes: tuple[EntryOutcome, ...]
    """Every entry that parsed, in sorted path order — rejected ones included."""

    rejections: tuple[EntryRejection, ...]
    """Parse rejections and entry rejections together, in sorted path order."""

    flags: tuple[Flag, ...]

    @property
    def ingesting(self) -> tuple[EntryOutcome, ...]:
        return tuple(outcome for outcome in self.outcomes if outcome.ingested)


@dataclass(frozen=True)
class TriageLoader:
    """`triage/` behind the `SourceLoader` protocol."""

    store: Path
    view: CorpusView
    rig: Sequence[RigDevice]
    ledger: Ledger
    #: The repository root the entries' `source_file` is stated relative to (3.5).
    root: Path | None = None
    #: The ingestion timestamp, injectable so a test does not have to freeze the clock.
    now: Callable[[], str] = field(default=_utc_now)

    def load(self, d: Discovered) -> LoadResult:
        """One region per ingesting entry, in sorted path order."""
        outcome = self.evaluate()
        return LoadResult(
            record=source_record(ingested_at=self.now()),
            regions=[emit(entry) for entry in outcome.ingesting],
        )

    def evaluate(self) -> StoreOutcome:
        """Parse, deduplicate, scope and pointer-check the whole store.

        Duplicate detection runs across the discovered set **before** any entry is
        evaluated on its own, because 1.9 rejects both members of a pair and neither is at
        fault in isolation.
        """
        entries: list[Entry] = []
        rejections: list[EntryRejection] = []
        flags: list[Flag] = []

        for path in self.entry_files():
            result = parse_entry(self._relative(path), path.read_bytes())
            if result.rejection is not None:
                rejections.append(result.rejection)
                continue
            assert result.entry is not None  # parse_entry sets exactly one of the two
            flags.extend(result.flags)
            entries.append(result.entry)

        duplicates = _duplicate_rejections(entries)
        outcomes = [
            EntryOutcome(entry, rejection=duplicates[index])
            if index in duplicates
            else self._evaluate(entry)
            for index, entry in enumerate(entries)
        ]
        for outcome in outcomes:
            if outcome.rejection is not None:
                rejections.append(outcome.rejection)
            flags.extend(outcome.flags)

        return StoreOutcome(tuple(outcomes), tuple(rejections), tuple(flags))

    def entry_files(self) -> list[Path]:
        """Every entry file, in sorted path order — the order regions are emitted in.

        Dotfiles are exempt so `.pointer-ledger.jsonl` never presents itself as an entry.
        What a non-`.md` file beside an entry costs is `discover`'s to say.
        """
        return sorted(
            path
            for path in self.store.rglob("*.md")
            if path.is_file() and not any(part.startswith(".") for part in path.parts)
        )

    def _relative(self, path: Path) -> Path:
        root = self.root if self.root is not None else self.store.parent
        try:
            return path.relative_to(root)
        except ValueError:
            return path

    def _evaluate(self, entry: Entry) -> EntryOutcome:
        scope = validate_scope(entry, self.rig, self.view.indexed)
        if scope.rejection is not None:
            return EntryOutcome(entry, rejection=scope.rejection)

        flags = list(scope.flags)
        causes: list[CauseOutcome] = []
        for position, cause in enumerate(entry.causes, start=1):
            pointers = tuple(check_pointer(p, self.view.sections, self.ledger) for p in cause.fixes)
            rejected = next((p for p in pointers if p.rejected), None)
            if rejected is not None:
                return EntryOutcome(entry, rejection=_pointer_rejection(entry, cause, rejected))

            drifted = [p for p in pointers if p.drifted]
            flags.extend(_drift_flag(entry, cause, position, p) for p in drifted)
            if cause.undocumented_device is not None:
                flags.append(_unbacked_flag(entry, cause, position))

            causes.append(
                CauseOutcome(
                    cause=cause,
                    pointers=pointers,
                    unbacked=bool(drifted) or cause.undocumented_device is not None,
                    passage_ids=tuple(pid for p in pointers for pid in p.passage_ids),
                )
            )

        return EntryOutcome(
            entry,
            flags=tuple(flags),
            scoped=tuple(scope.scoped),
            causes=tuple(causes),
        )


def emit(outcome: EntryOutcome) -> Region:
    """One entry as one region — the emission table of design §Passage emission.

    The symptom block leads and is `repeat_on_split`, so a split entry never carries a
    cause without its symptom; every cause is `atomic`, so no cause is ever divided across
    two passages (3.3). `section_number`, `page_start` and `page_end` are absent because an
    entry has no numbering and no pages (3.4, 12.8); `section_path` is empty because an
    entry has no ancestor titles; `inferred` is False because the author declared the
    title rather than a heading style recovering it. Every unit is plain text pointing at
    no image, so `degraded` and `has_figures` are False throughout (3.6).
    """
    entry = outcome.entry
    blocks = render_blocks(entry)

    units = [Unit(text=blocks.head, repeat_on_split=True)]
    units.extend(
        Unit(text=text, atomic=True, flags=UnitFlags(unbacked=cause.unbacked))
        for text, cause in zip(blocks.causes, outcome.causes, strict=True)
    )
    if blocks.closing is not None:
        units.append(Unit(text=blocks.closing, atomic=True))

    return Region(
        section_number=None,
        section_title=entry.symptom,
        section_path=(),
        page_start=None,
        page_end=None,
        inferred=False,
        units=units,
        entry_location=entry_location(entry),
    )


def _duplicate_rejections(entries: Sequence[Entry]) -> dict[int, EntryRejection]:
    """1.9, over **intersecting** device sets rather than equal ones.

    Set equality passes `overlapping_scopes/` and ships both entries: one scoped
    `[live-12]` and one scoped `[live-12, apc-key-25]` are both retrievable in any
    Live-scoped turn. Both are rejected and the duplication reported, because nothing here
    says which the author meant to keep.
    """
    groups: dict[str, list[int]] = {}
    for index, entry in enumerate(entries):
        groups.setdefault(normalised_symptom(entry.symptom), []).append(index)

    rejections: dict[int, EntryRejection] = {}
    for indices in groups.values():
        if len(indices) < 2:
            continue
        for index in indices:
            devices = _device_ids(entries[index])
            clashing = [
                other
                for other in indices
                if other != index and devices & _device_ids(entries[other])
            ]
            if not clashing:
                continue
            entry = entries[index]
            shared = sorted(devices & set().union(*(_device_ids(entries[o]) for o in clashing)))
            files = ", ".join(entries[o].source_file.as_posix() for o in sorted(clashing))
            rejections[index] = EntryRejection(
                reason="duplicate-symptom",
                source_file=entry.source_file,
                symptom=entry.symptom,
                detail=(
                    f'the symptom "{entry.symptom}" is also declared by {files}, and the two '
                    f"scopes share {', '.join(f'`{d}`' for d in shared)}. Both are rejected: "
                    "one question would return both entries, and nothing here says which you "
                    "meant to keep. Merge them, or narrow one entry's `devices:`."
                ),
            )
    return rejections


def _device_ids(entry: Entry) -> set[str]:
    return {device.id for device in entry.devices}


def _pointer_rejection(entry: Entry, cause: Cause, outcome: PointerOutcome) -> EntryRejection:
    """2.2 and 2.7 — a pointer with no ledger row that does not resolve.

    A pointer that once resolved is 8.4's flag instead, which `PointerOutcome` has already
    decided; reaching here means the ledger has never seen this pointer, so the author
    wrote it wrong rather than a manual having moved under it.
    """
    unresolved = outcome.unresolved
    assert unresolved is not None  # `rejected` is false without one
    position = entry.causes.index(cause) + 1
    label = _pointer_label(outcome)

    if unresolved.reason == "authored-target":
        detail = (
            f'cause {position} "{cause.statement}" points at {label}, which is the entry '
            "store itself. An entry cites a manual; it cannot cite the notes. Point at the "
            "vendor section, or mark the cause `undocumented:` if no manual covers it."
        )
        return EntryRejection(
            reason="pointer-authored-target",
            source_file=entry.source_file,
            symptom=entry.symptom,
            cause=cause.statement,
            detail=detail,
        )

    nearest = f" Nearest: {', '.join(unresolved.candidates)}." if unresolved.candidates else ""
    reasons = {
        "unknown-source": "which names no ingested manual",
        "no-such-section": "which is not a section of that manual",
        "ambiguous-title": "which names more than one section of that manual",
    }
    return EntryRejection(
        reason="pointer-unresolved",
        source_file=entry.source_file,
        symptom=entry.symptom,
        cause=cause.statement,
        detail=(
            f'cause {position} "{cause.statement}" points at {label}, '
            f"{reasons[unresolved.reason]}.{nearest} Correct the pointer or drop the cause."
        ),
    )


def _drift_flag(entry: Entry, cause: Cause, position: int, outcome: PointerOutcome) -> Flag:
    """8.4: the pointer resolved before and does not now, so a manual moved under it."""
    return Flag(
        name="pointer-drifted",
        source_file=entry.source_file,
        symptom=entry.symptom,
        cause=cause.statement,
        detail=(
            f'cause {position} "{cause.statement}" points at {_pointer_label(outcome)}, which '
            "resolved on an earlier run and does not now. The entry is still served, with the "
            "cause marked as unbacked. Retarget the pointer at the section as it now reads."
        ),
    )


def _unbacked_flag(entry: Entry, cause: Cause, position: int) -> Flag:
    """2.3/2.4: the cause is about gear the rig holds and no manual covers."""
    return Flag(
        name="unbacked-cause",
        source_file=entry.source_file,
        symptom=entry.symptom,
        cause=cause.statement,
        detail=(
            f'cause {position} "{cause.statement}" is marked '
            f"`undocumented: {cause.undocumented_device}`, so no vendor passage backs it. "
            "The entry is served with the cause marked as unbacked."
        ),
    )


def _pointer_label(outcome: PointerOutcome) -> str:
    """The pointer as the author wrote it, for the 5.3 message."""
    pointer = outcome.pointer
    if pointer.section_number is not None:
        return f"{pointer.source_id} §{pointer.section_number}"
    return f'{pointer.source_id} "{pointer.section_title}"'


__all__ = [
    "DISPLAY_NAME",
    "UNCHUNKED",
    "CauseOutcome",
    "CorpusView",
    "EntryOutcome",
    "StoreOutcome",
    "TriageLoader",
    "emit",
    "entry_location",
    "normalised_symptom",
    "source_record",
]
