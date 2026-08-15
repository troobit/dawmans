"""Fix pointers — the grammar of design 'Fix pointers', and their resolution.

    fix: <source_id> §<section-number>              ableton/live-12 §16.4
    fix: <source_id> "<section title>"              akai/apc-key-25 "Shift Functions"
    fix: <source_id> §<section-number> "<title>"    title corroborates, does not select

No page form exists: 8.1 forbids page-only addressing and admitting a page even
as a qualifier would reintroduce the breakage 8.3 exists to avoid (Decision 3).

**A pointer addresses a section and resolves to the ordered set of passages that
section produced.** Where the section split into *k* chunks it resolves to all
*k*: which chunk holds the sentence about the control is an artefact of the
chunker's word cap and changes under a re-chunk, so nothing here picks one.

Resolution reads a `SectionIndex` built in one pass over a view's
`passages.jsonl` and nothing else — no shard, no vector file, no PDF, and no
`SourceRecord`. That last exclusion is 8.3: `doc_version` lives on the record, so
replacing Live 12 with Live 12.1 cannot move a pointer on its own.
"""

from __future__ import annotations

import difflib
import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from dawmans.triage.model import Pointer, Unresolved

#: CONTRACTS §1. A pointer naming it is 2.7's rejection, not a lookup: an entry
#: may not cite another entry, and the check precedes every other one so that the
#: author is told what is actually wrong rather than "unknown source".
AUTHORED_SOURCE = "authored/triage"

#: How many nearest sections the 5.3 message offers. Three is enough to cover a
#: typo, a renumbering and a half-remembered title without becoming a listing.
CANDIDATES = 3

_POINTER_RE = re.compile(
    r"""^\s*
        (?P<source_id>\S+)                       # the source token
        (?:\s*§\s*(?P<number>[^\s"“”]+))?        # optional §<section-number>
        (?:\s*["“](?P<title>[^"”]*)["”])?        # optional "<section title>"
        \s*$""",
    re.VERBOSE,
)

_LEADING_NUMBER = re.compile(r"^\d+(?:\.\d+)*\.?\s+")
_TRAILING_PUNCTUATION = re.compile(r"[\s.,:;!?…]+$")
_WHITESPACE = re.compile(r"\s+")


def parse_pointer(text: str, line: int) -> Pointer | None:
    """Read one `fix:` value, or `None` where it addresses nothing.

    A pointer naming neither a section number nor a section title addresses
    nothing at all, so it is not a pointer. The caller retains the author's text
    and rejects the cause under `cause-missing-fix` if nothing else backs it —
    which keeps the rejection set closed and names the slip at the desk.
    """
    match = _POINTER_RE.match(text)
    if match is None:
        return None
    number = match.group("number")
    title = (match.group("title") or "").strip() or None
    if number is None and title is None:
        return None
    return Pointer(
        source_id=match.group("source_id"),
        section_number=number,
        section_title=title,
        line=line,
    )


def normalise_title(title: str) -> str:
    """The form the title map is keyed on.

    Casefold, collapse whitespace, strip a leading section number and trailing
    punctuation. The leading number matters because Live prints its titles with
    the number attached, so an author who copies one out of the manual types
    `18.1 The Live Mixer` and means the section the manual calls `The Live Mixer`.
    """
    without_number = _LEADING_NUMBER.sub("", title.strip())
    collapsed = _WHITESPACE.sub(" ", without_number)
    return _TRAILING_PUNCTUATION.sub("", collapsed).casefold()


@dataclass(frozen=True)
class _Section:
    """One section of one source, and the passages it produced, in section order."""

    source_id: str
    number: str | None
    title: str
    passage_ids: tuple[str, ...]

    @property
    def label(self) -> str:
        return f"§{self.number} {self.title}" if self.number else self.title


@dataclass(frozen=True)
class SectionIndex:
    """Two maps over one view, built once per run and never mutated.

    `(source_id, section_number)` and `(source_id, normalised title)`, each to the
    section's passage ids **in section order**. Resolution is pure and order-stable,
    so two runs over one view resolve identically — which is what makes a rebuilt
    index safe to compare against a committed ledger.

    A title that two sections share maps to both, and resolving it is ambiguous
    rather than arbitrary: 54 of Live's section titles are duplicated across its
    outline, so picking the first would cite the wrong one silently.
    """

    _by_number: Mapping[tuple[str, str], _Section]
    _by_title: Mapping[tuple[str, str], tuple[_Section, ...]]
    _sources: frozenset[str]

    @classmethod
    def from_passages(cls, rows: Iterable[Mapping[str, object]]) -> SectionIndex:
        """One pass over `passages.jsonl`. Row order is section order and is kept."""
        sections: dict[tuple[str, str | None, str], list[str]] = {}
        for row in rows:
            key = (
                str(row["source_id"]),
                None if row["section_number"] is None else str(row["section_number"]),
                str(row["section_title"]),
            )
            sections.setdefault(key, []).append(str(row["passage_id"]))

        by_number: dict[tuple[str, str], _Section] = {}
        by_title: dict[tuple[str, str], list[_Section]] = {}
        for (source_id, number, title), passage_ids in sections.items():
            section = _Section(source_id, number, title, tuple(passage_ids))
            if number is not None:
                by_number[(source_id, number)] = section
            by_title.setdefault((source_id, normalise_title(title)), []).append(section)

        return cls(
            _by_number=MappingProxyType(by_number),
            _by_title=MappingProxyType({k: tuple(v) for k, v in by_title.items()}),
            _sources=frozenset(source_id for source_id, _, _ in sections),
        )

    def knows(self, source_id: str) -> bool:
        return source_id in self._sources

    def by_number(self, source_id: str, number: str) -> _Section | None:
        return self._by_number.get((source_id, number))

    def titles(self, source_id: str) -> list[str]:
        """Every normalised title the source carries, for the prefix rule and the
        nearest-section candidates. Sorted, so a message reads the same twice."""
        return sorted(title for sid, title in self._by_title if sid == source_id)

    def by_title(self, source_id: str, normalised: str) -> tuple[_Section, ...]:
        return self._by_title.get((source_id, normalised), ())

    def numbers(self, source_id: str) -> list[str]:
        return sorted(number for sid, number in self._by_number if sid == source_id)


def resolve(p: Pointer, idx: SectionIndex) -> list[str] | Unresolved:
    """The pointer's passage ids in section order, or why it addresses none.

    Where both a number and a title are given the **number selects** and the title
    only corroborates: a stale title cannot move a pointer off the section its
    number names. `title_disagrees` reports the mismatch as a flag.
    """
    if p.source_id == AUTHORED_SOURCE:
        return _unresolved(p, "authored-target")
    if not idx.knows(p.source_id):
        return _unresolved(p, "unknown-source")

    if p.section_number is not None:
        section = idx.by_number(p.source_id, p.section_number)
        if section is None:
            nearest = _nearest(p.section_number, idx.numbers(p.source_id))
            return _unresolved(p, "no-such-section", [f"§{number}" for number in nearest])
        return list(section.passage_ids)

    assert p.section_title is not None  # the grammar admits no pointer with neither
    return _by_title(p, idx, normalise_title(p.section_title))


def _by_title(p: Pointer, idx: SectionIndex, normalised: str) -> list[str] | Unresolved:
    """Exact first, then a unique prefix. Exact first is what keeps a title that
    *is* a section from falling through to the prefix rule and reporting itself
    ambiguous against the longer titles it happens to prefix."""
    exact = idx.by_title(p.source_id, normalised)
    if len(exact) == 1:
        return list(exact[0].passage_ids)
    if exact:
        return _ambiguous(p, exact)

    prefixed = [
        section
        for title in idx.titles(p.source_id)
        if title.startswith(normalised)
        for section in idx.by_title(p.source_id, title)
    ]
    if len(prefixed) == 1:
        return list(prefixed[0].passage_ids)
    if prefixed:
        return _ambiguous(p, prefixed)

    nearest = _nearest(normalised, idx.titles(p.source_id))
    titles = {normalise_title(t): t for t in _display_titles(idx, p.source_id)}
    return _unresolved(p, "no-such-section", [titles.get(t, t) for t in nearest])


def _display_titles(idx: SectionIndex, source_id: str) -> list[str]:
    return [
        section.title
        for normalised in idx.titles(source_id)
        for section in idx.by_title(source_id, normalised)
    ]


def _ambiguous(p: Pointer, sections: Sequence[_Section]) -> Unresolved:
    """Two matches is unresolved with the candidates named, never an arbitrary pick."""
    return _unresolved(p, "ambiguous-title", sorted({section.label for section in sections}))


def _nearest(typed: str, known: Sequence[str]) -> list[str]:
    """Nearest sections by edit distance, for the 5.3 message. Offered in the form
    the author typed — a number for a number, a title for a title — so the message
    is a correction to what they wrote rather than a listing of the manual."""
    return difflib.get_close_matches(typed, known, n=CANDIDATES, cutoff=0.6)


def _unresolved(p: Pointer, reason: str, candidates: Sequence[str] = ()) -> Unresolved:
    return Unresolved(pointer=p, reason=reason, candidates=list(candidates))  # type: ignore[arg-type]


def title_disagrees(p: Pointer, idx: SectionIndex) -> bool:
    """Whether a pointer's number and title name different sections (the flag).

    The cheapest renumbering detector available and free to the author: they wrote
    both, the manual renumbered, and the pair no longer agrees. A flag rather than
    a rejection, because the number still resolves and the entry is still good.

    False where there is nothing to disagree with — one of the two absent, or a
    number that names no section, where the flag would be noise on top of the real
    message.
    """
    if p.section_number is None or p.section_title is None:
        return False
    section = idx.by_number(p.source_id, p.section_number)
    if section is None:
        return False
    return normalise_title(section.title) != normalise_title(p.section_title)


# --- The ledger -----------------------------------------------------------

#: Beside the entries it remembers, and committed. `.gitattributes` sets
#: `merge=union` on it: a single JSON object cannot be merged by git, and "never
#: hand-edited" is unenforceable in exactly the situation git demands it.
LEDGER_NAME = ".pointer-ledger.jsonl"

_ROW_FIELDS = ("pointer", "resolved_at", "passage_ids", "entry_keys")


def pointer_key(p: Pointer) -> str:
    """The ledger key: the **pointer alone** (Decision 4).

    `(source_id, section number, or normalised title where there is no number)`.
    Verification is a property of the pointer's target, not of the entry holding
    it: keying on the entry — the symptom plus its device set — would make adding
    a device to `devices:` change the key, so any pointer that had since drifted
    would become a 2.2 rejection, withdrawing an entry mid-session over a
    cosmetic edit unrelated to pointers.

    The number wins where there is one, so adding the title the manual prints
    beside it, or letting that title go stale, moves no row.
    """
    if p.section_number is not None:
        return f"{p.source_id} §{p.section_number}"
    assert p.section_title is not None
    return f'{p.source_id} "{normalise_title(p.section_title)}"'


class LedgerUnparseable(RuntimeError):
    """The ledger will not parse — a **failure**, not a rejection.

    No entry is at fault, and continuing would silently re-arm 2.2 for the whole
    store and reject entries 8.4 requires be served with a mark. The run exits
    non-zero naming the file and the offending line.
    """


@dataclass(frozen=True)
class LedgerRow:
    """One pointer that resolved, and what it resolved to."""

    pointer: str
    resolved_at: str
    passage_ids: tuple[str, ...]
    entry_keys: tuple[str, ...]
    """An annotation for the coverage report, and no part of the key."""

    def to_json(self) -> str:
        return json.dumps(
            {
                "pointer": self.pointer,
                "resolved_at": self.resolved_at,
                "passage_ids": list(self.passage_ids),
                "entry_keys": list(self.entry_keys),
            },
            ensure_ascii=False,
        )


class Ledger:
    """Append-and-update over the NDJSON rows of design §Reject versus flag.

    `read` is **read-only** — no row is added and no `resolved_at` moved — so
    `dawmans validate` cannot promote a pointer to "previously fine" just by
    looking at it. Only `dawmans ingest` calls `record`, and `record` writes only
    on transition, so a run that changes nothing leaves the file byte-identical
    and the working tree clean.

    Rows are **never pruned**. A row only ever records that a pointer *did*
    resolve, so a stale row costs one line and nothing else — and never deleting
    is what makes the union merge of two machines' ledgers sound.
    """

    def __init__(self, rows: Iterable[LedgerRow] = (), *, missing: bool = False) -> None:
        self._rows: dict[str, LedgerRow] = {row.pointer: row for row in rows}
        self._missing = missing

    @classmethod
    def empty(cls) -> Ledger:
        return cls()

    @classmethod
    def read(cls, path: Path) -> Ledger:
        """Every row, or an empty ledger that knows it is missing.

        Deleting the file re-arms 2.2 for everything. That is the honest
        degradation, since the file is the only claim that a pointer once worked,
        but it must not be silent: `missing` is what the run report says so from.
        """
        try:
            text = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return cls(missing=True)

        rows = []
        for number, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            rows.append(_read_row(path, number, line))
        return cls(rows)

    @property
    def missing(self) -> bool:
        return self._missing

    def knows(self, key: str) -> bool:
        """Whether this pointer has ever resolved — the whole question 2.2 asks."""
        return key in self._rows

    def row(self, key: str) -> LedgerRow | None:
        return self._rows.get(key)

    def record(
        self,
        key: str,
        passage_ids: Sequence[str],
        entry_keys: Sequence[str],
        now: str,
    ) -> bool:
        """Note that a pointer resolved. True where the row actually moved.

        `resolved_at` moves **only on transition** — a first resolution, or a
        resolution to passages other than the ones the row records, which is what
        a resolution after a drift looks like from here. A pointer that resolves
        to exactly what it resolved to last time changes nothing, and the file it
        is written back to is byte-identical.
        """
        existing = self._rows.get(key)
        ids = tuple(passage_ids)
        if existing is not None and existing.passage_ids == ids:
            return False
        self._rows[key] = LedgerRow(key, now, ids, tuple(entry_keys))
        return True

    def write(self, path: Path) -> None:
        """One row per line, sorted by pointer, so a diff shows the rows that changed."""
        lines = [self._rows[key].to_json() for key in sorted(self._rows)]
        path.write_text("".join(line + "\n" for line in lines), encoding="utf-8")


def _read_row(path: Path, number: int, line: str) -> LedgerRow:
    try:
        data = json.loads(line)
    except json.JSONDecodeError as error:
        raise LedgerUnparseable(f"{path} line {number} is not JSON: {error.msg}") from error
    missing = [field for field in _ROW_FIELDS if field not in data]
    if missing:
        raise LedgerUnparseable(f"{path} line {number} is missing {', '.join(missing)}")
    return LedgerRow(
        pointer=str(data["pointer"]),
        resolved_at=str(data["resolved_at"]),
        passage_ids=tuple(str(i) for i in data["passage_ids"]),
        entry_keys=tuple(str(k) for k in data["entry_keys"]),
    )


# --- Reject versus flag ---------------------------------------------------


@dataclass(frozen=True)
class PointerOutcome:
    """What one pointer means for its cause on this run."""

    pointer: Pointer
    passage_ids: tuple[str, ...]
    unresolved: Unresolved | None
    previously_resolved: bool

    @property
    def ok(self) -> bool:
        return self.unresolved is None

    @property
    def drifted(self) -> bool:
        """8.4: a flag plus `unbacked` on the cause, and the entry stays ingested."""
        return self.unresolved is not None and self.previously_resolved

    @property
    def rejected(self) -> bool:
        """2.2 (or 2.7): the pointer never worked, so the author wrote it wrong."""
        return self.unresolved is not None and not self.previously_resolved


def check_pointer(p: Pointer, idx: SectionIndex, ledger: Ledger) -> PointerOutcome:
    """Resolve, then ask the ledger whether this is a rejection or a flag.

    Checking never records: recording is the caller's move under `dawmans ingest`
    alone, so `dawmans validate` can run this over the whole store without
    promoting a single pointer.

    An `authored-target` is a rejection whatever the ledger says. 2.7 is about
    what an entry may cite, not about whether it once worked, and a row for one
    could never have been written honestly.
    """
    result = resolve(p, idx)
    if not isinstance(result, Unresolved):
        return PointerOutcome(p, tuple(result), None, ledger.knows(pointer_key(p)))
    previously = result.reason != "authored-target" and ledger.knows(pointer_key(p))
    return PointerOutcome(p, (), result, previously)


__all__ = [
    "AUTHORED_SOURCE",
    "LEDGER_NAME",
    "Ledger",
    "LedgerRow",
    "LedgerUnparseable",
    "PointerOutcome",
    "SectionIndex",
    "check_pointer",
    "normalise_title",
    "parse_pointer",
    "pointer_key",
    "resolve",
    "title_disagrees",
]
