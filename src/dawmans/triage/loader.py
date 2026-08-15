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

import hashlib
from collections.abc import Callable, Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from types import MappingProxyType
from typing import Any

from dawmans.corpus.chunk import Chunk, chunk_source
from dawmans.corpus.discover import AUTHORED_STORE, DiscoveryRejection, StoreScan
from dawmans.corpus.loader import Discovered, LoadResult, Region, Rejection, Unit, UnitFlags
from dawmans.records import AUTHORED_SOURCE_ID, HardwareApplicability, SourceRecord
from dawmans.triage.model import (
    Cause,
    Entry,
    EntryRejection,
    Flag,
    entry_key,
    normalised_symptom,
)
from dawmans.triage.parse import parse_entry, render_blocks
from dawmans.triage.pointers import (
    LEDGER_NAME,
    Ledger,
    PointerOutcome,
    SectionIndex,
    check_pointer,
    pointer_key,
    title_disagrees,
)
from dawmans.triage.scope import RigDevice, report, sidecar, validate_scope
from dawmans.triage.terms import Resolution, check_terms, term_flag

#: CONTRACTS §1. It reads in the citation header and in the source picker as the user's own
#: notes rather than as a vendor document (3.1), so a citation renders as
#: `My Triage Notes — No sound from a track`.
DISPLAY_NAME = "My Triage Notes"

#: What the record carries before the source has been chunked, exactly as `PdfLoader` does.
#: The shard build owns the real value and rewrites the record with it. The constant is
#: restated rather than imported: `corpus/pdf/loader.py` imports PyMuPDF, which
#: `manual-corpus` Decision 6 confines to `corpus/pdf/`.
UNCHUNKED = 0

#: The one extension the store admits. Filenames carry no meaning beyond it — not
#: identity (1.8), not scope, not ordering.
ENTRY_SUFFIX = ".md"


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


# --- Discovery -------------------------------------------------------------


def entry_files(store: Path) -> list[Path]:
    """Every entry file, in sorted path order — the order regions are emitted in.

    A **recursive** scan (1.6): a flat glob would make `triage/live/no-sound.md`
    invisible with nothing to report. Dotfiles are exempt at every level so that
    `.pointer-ledger.jsonl`, the machine's own artefact, never presents itself as an
    entry or warns about itself. What a non-`.md` file beside an entry costs is
    `skipped_files`'s to say.
    """
    return sorted(
        path
        for path in store.rglob(f"*{ENTRY_SUFFIX}")
        if path.is_file() and not _hidden(path, store)
    )


def skipped_files(store: Path) -> list[Path]:
    """Every non-entry, non-dotfile in the store — each one a report line.

    The opposite of `manuals/`, where a non-PDF is skipped silently: a `no-sound.txt`
    the author expected to be ingested must not disappear quietly. `manuals/` holds a
    README nobody expects to be indexed; this store holds only what the author wrote to
    be read.
    """
    return sorted(
        path
        for path in store.rglob("*")
        if path.is_file() and path.suffix.lower() != ENTRY_SUFFIX and not _hidden(path, store)
    )


def _hidden(path: Path, store: Path) -> bool:
    """Whether any component below the store begins with a dot.

    Below the store: `triage/` may itself sit under a dotted directory — a worktree
    under `.orbit/`, a checkout under `.cache/` — and that says nothing about the files
    inside it.
    """
    try:
        parts = path.relative_to(store).parts
    except ValueError:  # pragma: no cover — the caller walks the store
        parts = path.parts
    return any(part.startswith(".") for part in parts)


def store_fingerprint(store: Path, files: Sequence[Path]) -> str:
    """sha256 over the sorted `(store-relative path, file digest)` pairs.

    The store's own bytes and nothing else. It still has consumers — the shard meta
    records it and it enters `manifest.corpus_revision`, which `api/answer-engine` 5.10
    reads — but it does **not** gate the load: the authored store's validity is a
    function of the manuals as well as its own text, so `load()` runs unconditionally
    (design §Discovery, fingerprint and the run budget).

    Store-relative rather than absolute, so a clone at another path fingerprints alike;
    the path is in the digest at all so that renaming an entry file is a change, which is
    what makes the shard's recorded fingerprint describe the store it was built from.
    """
    digest = hashlib.sha256()
    for path in sorted(files):
        digest.update(path.relative_to(store).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).hexdigest().encode("utf-8"))
        digest.update(b"\n")
    return f"sha256:{digest.hexdigest()}"


def scan_store(store: Path) -> StoreScan:
    """The store's discovery set for this run — the wider protocol the run declares.

    Discovery reads the store's own directory and nothing else: not the corpus, not the
    rig, not the ledger. That is why it is a function rather than a method — a caller
    that only wants to know what is there does not have to assemble what only `load()`
    needs.

    **An absent or unreadable store is not an empty one** (`manual-corpus` 1.4): the
    discovery set is *unknown*, no shard is removed, and the run reports the store
    unavailable. An existing store holding no entry is an empty set, and its shard goes.
    """
    try:
        list(store.iterdir())
    except OSError:
        return StoreScan(store=AUTHORED_STORE, available=False)

    files = entry_files(store)
    sources = (
        Discovered(
            source_id=AUTHORED_SOURCE_ID,
            fingerprint=store_fingerprint(store, files),
            origin=store,
        ),
    )
    return StoreScan(
        store=AUTHORED_STORE,
        available=True,
        sources=sources if files else (),
        rejections=tuple(_skipped(store, path) for path in skipped_files(store)),
    )


def _skipped(store: Path, path: Path) -> DiscoveryRejection:
    """One non-entry file, as the run report names it.

    `filename-invalid` is `manual-corpus` 1.6's reason for a file in a store whose name
    does not admit it as a source, which is exactly what this is; the closed set admits
    no second spelling of the same fact, and inventing one would put a reason outside
    1.6 on a path 1.7 reserves for failures.
    """
    return DiscoveryRejection(
        origin=path,
        rejection=Rejection(
            reason="filename-invalid",
            detail=(
                f"{store.name}/ holds entries as {ENTRY_SUFFIX} files, and "
                f"{path.relative_to(store).as_posix()} was not read. Rename it, or move it "
                "out of the store."
            ),
        ),
    )


@dataclass(frozen=True)
class CorpusView:
    """What the loader reads of the corpus, and the whole of it (5.7).

    Read-only, and never a vector file, a PDF or anything a manual has to be re-extracted
    or re-chunked to produce (`manual-corpus` 12.4). It is built from the passage and
    source records the view publishes — CONTRACTS §2 and §1, in the JSON form
    `views/<hex>/passages.jsonl` and `sources.json` carry — so the reader speaks the
    view's own contract rather than an internal type. Under `dawmans ingest` those rows
    come from the shards this run has just committed, which are the view about to be
    merged; see decision_log Decision 13 for why they cannot come from the committed
    view directory.
    """

    sections: SectionIndex
    """Built once per run, so every pointer in a run resolves against one corpus."""

    indexed: Collection[str]
    """Every identity the corpus documents — see `scope.validate_scope` (Decision 8)."""

    texts: Mapping[str, str] = MappingProxyType({})
    """`passage_id` → passage text, for the term check (2.6). Empty where the caller
    reads no text, in which case no cause is term-checked: a term found in nothing is
    not evidence that the manual does not print it."""

    @classmethod
    def empty(cls) -> CorpusView:
        """A view of no corpus — for discovery, which reads none."""
        return cls(sections=SectionIndex.from_passages([]), indexed=frozenset())

    @classmethod
    def of(
        cls,
        passages: Iterable[Mapping[str, Any]],
        sources: Iterable[Mapping[str, Any]],
    ) -> CorpusView:
        """One view, from its passage rows and its source records.

        `indexed` is every identity the corpus documents: each `vendor-manual`
        `source_id` **and** the device id it declares under `source_applicability`,
        which `SourceRecord.hardware_applicability` carries (Decision 8). An
        `authored-triage` record is not among them — an entry may not cite the notes
        (2.7), and a device is not documented by being written about.
        """
        rows = list(passages)
        indexed: set[str] = set()
        for record in sources:
            if record.get("kind") != "vendor-manual":
                continue
            indexed.add(str(record["source_id"]))
            applicability = record.get("hardware_applicability") or {}
            device = applicability.get("device")
            if device:
                indexed.add(str(device))

        return cls(
            sections=SectionIndex.from_passages(rows),
            indexed=frozenset(indexed),
            texts=MappingProxyType({str(row["passage_id"]): str(row["text"]) for row in rows}),
        )

    def text(self, passage_id: str) -> str | None:
        return self.texts.get(passage_id)


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

    flags: tuple[Flag, ...] = ()
    """This cause's own flags, which the sidecar publishes beside it. Held per cause
    rather than filtered out of the entry's flags by statement, because two causes of
    one entry may be worded identically and a filter would give each the other's."""


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

    def discover(self) -> Iterable[Discovered]:
        """0 or 1 — the store is one source, whatever number of files it holds."""
        return self.scan().sources

    def scan(self) -> StoreScan:
        """The run's wider protocol: the discovery set, plus what was skipped."""
        return scan_store(self.store)

    def load(self, d: Discovered) -> LoadResult:
        """One region per ingesting entry, in sorted path order.

        Called on **every** ingest, whatever the fingerprint says: 2.1 asks for every
        pointer to be re-checked on every run, and a fingerprint over the store's own
        bytes cannot answer a question about the manuals. The exemption itself lives in
        the run orchestration, which is what passes `always_load` (`cli.ingest`).

        The whole source is rejected as `authored-invalid` only when **no** entry
        survives (`manual-corpus` 12.6): a source with no passages is not a source. The
        corpus deletes the shard of a rejected source, which is what keeps a store whose
        every entry has become malformed from serving the previous run's passages while
        the run reports the rejection and succeeds.
        """
        outcome = self.evaluate()
        record = source_record(ingested_at=self.now())
        block = report(outcome, ledger_missing=self.ledger.missing)

        if not outcome.ingesting:
            return LoadResult(
                record=record,
                regions=[],
                rejection=Rejection(
                    reason="authored-invalid",
                    detail=_invalid_detail(outcome),
                ),
                audit={"report": block},
            )

        regions = [emit(entry) for entry in outcome.ingesting]
        self._record_resolutions(outcome)
        return LoadResult(
            record=record,
            regions=regions,
            audit={"report": block},
            sidecar=sidecar(
                outcome,
                _passage_ids(outcome.ingesting, chunk_source(record, regions)),
                ledger_missing=self.ledger.missing,
            ),
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

        # A rejected entry is excluded, so remarks about it are noise beside the reason
        # it went: its parse flags were collected before anything could reject it.
        excluded = {rejection.source_file for rejection in rejections}
        kept = tuple(flag for flag in flags if flag.source_file not in excluded)

        return StoreOutcome(tuple(outcomes), tuple(rejections), kept)

    def entry_files(self) -> list[Path]:
        """Every entry file of this store, in sorted path order."""
        return entry_files(self.store)

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

        causes: list[CauseOutcome] = []
        for position, cause in enumerate(entry.causes, start=1):
            pointers = tuple(check_pointer(p, self.view.sections, self.ledger) for p in cause.fixes)
            rejected = next((p for p in pointers if p.rejected), None)
            if rejected is not None:
                return EntryOutcome(entry, rejection=_pointer_rejection(entry, cause, rejected))

            drifted = [p for p in pointers if p.drifted]
            flags = [_drift_flag(entry, cause, position, p) for p in drifted]
            flags += [
                _disagreement_flag(entry, cause, position, p)
                for p in pointers
                if p.ok and title_disagrees(p.pointer, self.view.sections)
            ]
            if cause.undocumented_device is not None:
                flags.append(_unbacked_flag(entry, cause, position))
            # The term check runs last and never sets `unbacked` (Decision 5): the
            # pointer resolved, and what failed is a heuristic over an author's prose.
            flags += [
                term_flag(entry, cause, miss)
                for miss in check_terms(
                    entry,
                    cause,
                    self._resolutions(pointers),
                    display_names=self._display_names(entry),
                )
            ]

            causes.append(
                CauseOutcome(
                    cause=cause,
                    pointers=pointers,
                    unbacked=bool(drifted) or cause.undocumented_device is not None,
                    passage_ids=tuple(pid for p in pointers for pid in p.passage_ids),
                    flags=tuple(flags),
                )
            )

        return EntryOutcome(
            entry,
            flags=(*scope.flags, *(flag for cause in causes for flag in cause.flags)),
            scoped=tuple(scope.scoped),
            causes=tuple(causes),
        )

    def _resolutions(self, pointers: Sequence[PointerOutcome]) -> list[Resolution]:
        """What the term check reads: each resolved pointer's passages, in section order.

        A pointer whose passages the view carries no text for contributes nothing rather
        than an empty section, in which every term would be missing. That is the same
        rule `check_terms` applies to a cause with no resolutions at all: silence is not
        evidence that the manual does not print the term.
        """
        resolutions = []
        for outcome in pointers:
            texts = tuple(
                text
                for passage_id in outcome.passage_ids
                if (text := self.view.text(passage_id)) is not None
            )
            if texts:
                resolutions.append(Resolution(label=_pointer_label(outcome), texts=texts))
        return resolutions

    def _display_names(self, entry: Entry) -> list[str]:
        """The `rig.yaml` display names of the entry's **declared** devices.

        The device the owner holds, not the `SourceRecord`'s document name: naming it in
        a cause is the scope restated in prose, not a factual claim about a control.
        """
        declared = {device.id for device in entry.devices}
        return [
            device.display_name
            for device in self.rig
            if device.id in declared and device.display_name
        ]

    def _record_resolutions(self, outcome: StoreOutcome) -> None:
        """Note every pointer that resolved this run, and write only if a row moved.

        Recording happens here and nowhere else, because `load()` is called under
        `dawmans ingest` alone: `dawmans validate` runs the same checks through
        `evaluate()` and so cannot promote a broken pointer to "previously fine" (5.4).

        A pointer resolving to exactly what it resolved to last time moves no row, so a
        run that changes nothing leaves the file byte-identical and the working tree
        clean — the only reason a machine-written committed file is tolerable.
        """
        resolutions: dict[str, tuple[tuple[str, ...], set[str]]] = {}
        for entry_outcome in outcome.ingesting:
            key = entry_key(entry_outcome.entry)
            for cause in entry_outcome.causes:
                for pointer in cause.pointers:
                    if not pointer.ok:
                        continue
                    ids, keys = resolutions.setdefault(
                        pointer_key(pointer.pointer), (pointer.passage_ids, set())
                    )
                    keys.add(key)

        now = self.now()
        moved = False
        for key in sorted(resolutions):
            passage_ids, entry_keys = resolutions[key]
            moved |= self.ledger.record(key, passage_ids, sorted(entry_keys), now)
        if moved:
            self.ledger.write(self.store / LEDGER_NAME)


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


def _passage_ids(
    outcomes: Sequence[EntryOutcome], chunks: Sequence[Chunk]
) -> dict[str, tuple[str, ...]]:
    """Each entry's emitted `passage_id`s, keyed by its `source_file` (4.3).

    The loader has to run the chunker to know them: identifiers are assigned from the
    packed text (3.9) and the seam gives no post-chunk hook, while `LoadResult.sidecar`
    is keyed by `passage_id`. The call is the same pure function over the same regions
    the run will make, so the two agree by construction rather than by a second rule.

    Chunks are grouped by `entry_location`, which is one entry's file and its H1 line and
    is therefore unique across a store: two entries are two files. Grouping by
    `section_title` would collide two entries sharing a symptom in disjoint scopes, which
    1.9 permits.
    """
    grouped: dict[str, list[str]] = {}
    for chunk in chunks:
        location = chunk.passage.entry_location
        assert location is not None  # every authored region carries one
        grouped.setdefault(location, []).append(chunk.passage.passage_id)

    return {
        outcome.entry.source_file.as_posix(): tuple(grouped.get(entry_location(outcome.entry), ()))
        for outcome in outcomes
    }


def _invalid_detail(outcome: StoreOutcome) -> str:
    """Why the whole source went, in terms of the entries that failed."""
    reasons = ", ".join(sorted({rejection.reason for rejection in outcome.rejections}))
    return (
        f"no entry in the store survived validation ({reasons}); the authored source has "
        "no passages and is excluded. Each entry's own reason is reported above."
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


def _disagreement_flag(entry: Entry, cause: Cause, position: int, outcome: PointerOutcome) -> Flag:
    """The number and the title name different sections — the free renumbering detector.

    A flag rather than a rejection: the number still selects, so the cause is still
    backed, and the author wrote both halves themselves.
    """
    pointer = outcome.pointer
    return Flag(
        name="title-number-disagreement",
        source_file=entry.source_file,
        symptom=entry.symptom,
        cause=cause.statement,
        detail=(
            f'cause {position} "{cause.statement}" points at {pointer.source_id} '
            f"§{pointer.section_number}, which the manual now titles differently from "
            f'"{pointer.section_title}". The number selected the section; check the manual '
            "has not renumbered under the entry."
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
    "ENTRY_SUFFIX",
    "UNCHUNKED",
    "CauseOutcome",
    "CorpusView",
    "EntryOutcome",
    "StoreOutcome",
    "TriageLoader",
    "emit",
    "entry_files",
    "entry_location",
    "normalised_symptom",
    "scan_store",
    "skipped_files",
    "source_record",
    "store_fingerprint",
]
