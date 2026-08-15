"""The SourceLoader seam: Discovered, LoadResult, Region, Unit.

The two source kinds converge here. A loader turns one store's sources into `Region`s;
everything from `Region` onwards is shared code, which is what makes requirement 12.2
structural rather than a set of `if kind ==` branches, and 12.4 a consequence of there
being exactly one PDF loader.

`TriageLoader` is implemented by `data/symptom-triage` behind this same protocol and is
not written here. This module is interfaces only — no behaviour — so the invariants
noted below are stated for the implementers rather than enforced.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Protocol

from dawmans.records import SourceRecord

#: The closed set of rejection reasons (requirement 1.6, design §Error Handling). A
#: rejection excludes one source, is reported, and the run still succeeds; anything not
#: in this set is a failure and fails the run (1.7).
RejectionReason = Literal[
    "filename-invalid",  # 2.5
    "source-id-collision",  # 2.6
    "no-text-layer",  # 3.3
    "no-english-content",  # 4.5
    "unreadable-text",  # 5.5, over the 2% unmappable threshold
    "authored-invalid",  # 12.6, reported by TriageLoader
]
REJECTION_REASONS: tuple[RejectionReason, ...] = (
    "filename-invalid",
    "source-id-collision",
    "no-text-layer",
    "no-english-content",
    "unreadable-text",
    "authored-invalid",
)


@dataclass(frozen=True, slots=True)
class Rejection:
    """Why one source was excluded, for the run report.

    The set is closed **here**, at construction, rather than checked where a report line
    is rendered. A rejection excludes one source and still reports the run as succeeded
    (1.6), so a condition wrongly dressed as one — a disk error, an out-of-memory — is a
    run that indexed nothing and exited zero. 1.7's failure path exists precisely to catch
    those, and it only holds if this path is unreachable for anything not in 1.6's list.
    """

    reason: RejectionReason
    #: What the report line says beyond the reason — for `filename-invalid`, the
    #: expected pattern; for `source-id-collision`, the colliding files.
    detail: str = ""

    def __post_init__(self) -> None:
        if self.reason not in REJECTION_REASONS:
            raise ValueError(
                f"{self.reason!r} is not one of the rejection reasons {REJECTION_REASONS} "
                f"(requirement 1.6); anything else is a failure and fails the run (1.7)"
            )


@dataclass(frozen=True, slots=True)
class Discovered:
    """One source a loader found in its store, before any of it is read."""

    source_id: str  # "<vendor>/<product>"; the constant "authored/triage" for authored
    fingerprint: str  # sha256 of the source's bytes / of the entry store's canonical form
    origin: Path


@dataclass(frozen=True, slots=True)
class UnitFlags:
    """The per-unit flags that aggregate onto a chunk by OR (design §emission contract).

    `unbacked` is owned by `data/symptom-triage` and is carried through unchanged
    (requirement 12.6).
    """

    degraded: bool = False
    has_figures: bool = False
    unbacked: bool = False


@dataclass(frozen=True, slots=True)
class Unit:
    """The smallest thing the chunker packs: a paragraph, a table row, a procedure."""

    text: str
    #: A unit may cross a page boundary, so both ends are kept: 6.10 forbids splitting a
    #: numbered procedure that fits the cap, and a procedure can start on p11 and end on
    #: p12. One page per unit would force either a 6.10 violation or a citation naming
    #: p11 for text printed on p12. Both are None on a pageless source (12.8).
    page_start: int | None = None
    page_end: int | None = None
    atomic: bool = False  # never split if it fits the cap (6.10, 7.4)
    repeat_on_split: bool = False  # table headings (7.5), the authored symptom statement
    flags: UnitFlags = field(default_factory=UnitFlags)


@dataclass(frozen=True, slots=True)
class Region:
    """Exactly one section, or one titled region (6.5, 6.7).

    `units` is ordered and the chunker preserves that order; no stage reorders units,
    which is what `data/symptom-triage` 1.5 depends on.
    """

    section_number: str | None  # None ⇒ citation renders without one (6.4)
    section_title: str  # the leaf title
    section_path: tuple[str, ...]  # ancestor titles, nearest two; () at top level
    page_start: int | None  # None for a pageless source (12.8)
    page_end: int | None
    inferred: bool  # sectioning came from path C heading styles
    units: list[Unit]
    #: CONTRACTS §2 `entry_location`, on an `authored-triage` region only: the entry's own
    #: `source_file` and line, joined by `TriageLoader`. It is region-scoped because a
    #: region is exactly one entry, and it is carried onto every passage of that region
    #: unchanged — never set, cleared or derived here (12.6), and never an input to
    #: `passage_id` (CONTRACTS §2). None on a `vendor-manual`, which has a page instead.
    entry_location: str | None = None


@dataclass(frozen=True, slots=True)
class LoadResult:
    """Everything one source contributes to a run."""

    record: SourceRecord
    regions: list[Region]
    rejection: Rejection | None = None  # set ⇒ regions empty, run still succeeds (1.6)
    #: Run diagnostics for `index/audits/<slug>.json`: English page ranges, glyph
    #: counts, anchor quality, the rejection reason.
    audit: dict[str, Any] = field(default_factory=dict)
    #: Per-`passage_id` data for the view, committed with the shard and copied into
    #: `views/<hex>/reports/<slug>.json`. None where the loader publishes none.
    sidecar: dict[str, Any] | None = None


class SourceLoader(Protocol):
    """One store's half of the seam.

    The run orchestration needs a **stronger** protocol than this one and declares it
    itself, in `dawmans/cli.py` (Decision 17): `discover()` yields the sources a store
    holds and drops the two other things a scan knows — which sources it *rejected* by
    name (1.5), and whether the store was **available** at all, an absent store being an
    unknown discovery set rather than an empty one (1.4). This protocol stays as the
    design's §The loader protocol states it; `PdfLoader.scan()` is where the wider one is
    satisfied, and `TriageLoader` satisfies it the same way.
    """

    def discover(self) -> Iterable[Discovered]: ...

    def load(self, d: Discovered) -> LoadResult: ...


__all__ = [
    "REJECTION_REASONS",
    "Discovered",
    "LoadResult",
    "Region",
    "Rejection",
    "RejectionReason",
    "SourceLoader",
    "Unit",
    "UnitFlags",
]
