"""The CONTRACTS §3/§4 records and the §6/§6a enums.

The field sets and both enums are closed by CONTRACTS: a field outside the
tables cannot be set (frozen dataclasses) and an outcome or reason
outside §6/§6a cannot be constructed. Absent means None — never an empty
string, never synthesised.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal


class Outcome(StrEnum):
    """CONTRACTS §6 — 17 members, 7 content and 10 engine-determined."""

    ANSWERED = "answered"
    PARTIALLY_ANSWERED = "partially-answered"
    NEEDS_NARROWING = "needs-narrowing"
    RANKED_CAUSES = "ranked-causes"
    REFUSED_NOT_COVERED = "refused-not-covered"
    OUT_OF_DOMAIN = "out-of-domain"
    NO_MANUAL_FOR_DEVICE = "no-manual-for-device"
    NO_SOURCES_SELECTED = "no-sources-selected"
    UNKNOWN_SOURCE_ID = "unknown-source-id"
    CORPUS_EMPTY = "corpus-empty"
    PROVIDER_UNCONFIGURED = "provider-unconfigured"
    PROVIDER_UNREACHABLE = "provider-unreachable"
    PROVIDER_RATE_LIMITED = "provider-rate-limited"
    PROVIDER_ERROR = "provider-error"
    TIMEOUT = "timeout"
    INCOMPLETE = "incomplete"
    CANCELLED = "cancelled"


class Reason(StrEnum):
    """CONTRACTS §6a — the closed sub-code vocabulary refining an outcome."""

    NO_PROVIDER_KIND = "no-provider-kind"
    MISSING_CREDENTIAL = "missing-credential"
    DISCLOSURE_UNACKNOWLEDGED = "disclosure-unacknowledged"
    AUTHENTICATION_FAILED = "authentication-failed"
    PROVIDER_REJECTED = "provider-rejected"


VENDOR_MANUAL = "vendor-manual"
AUTHORED_TRIAGE = "authored-triage"

# On a pageless authored source these are absent; on any source, absent is
# None and never "".
_OPTIONAL_STR_FIELDS = ("doc_version", "section_number", "section_title", "entry_location")
_VENDOR_ONLY_FIELDS = ("doc_version", "section_number", "page")


@dataclass(frozen=True)
class Citation:
    """CONTRACTS §3 — every field is rendered or actionable."""

    passage_id: str
    source_id: str
    display_name: str
    kind: str  # "vendor-manual" | "authored-triage" (§4a)
    hardware_applicability: str  # "confirmed" | "assumed"
    doc_version: str | None = None
    section_number: str | None = None
    section_title: str | None = None
    page: int | None = None
    entry_location: str | None = None  # authored-triage only
    unbacked: bool = False
    degraded: bool = False
    has_figures: tuple[int, ...] = ()  # pages carrying figures; empty = none

    def __post_init__(self) -> None:
        if self.kind not in (VENDOR_MANUAL, AUTHORED_TRIAGE):
            raise ValueError(f"kind must be {VENDOR_MANUAL!r} or {AUTHORED_TRIAGE!r}: {self.kind!r}")
        for name in _OPTIONAL_STR_FIELDS:
            if getattr(self, name) == "":
                raise ValueError(f"{name} is absent as None, never an empty string")
        if self.kind == AUTHORED_TRIAGE:
            for name in _VENDOR_ONLY_FIELDS:
                if getattr(self, name) is not None:
                    raise ValueError(f"{name} is never synthesised on an authored-triage citation")
        elif self.entry_location is not None:
            raise ValueError("entry_location belongs to authored-triage citations only")


@dataclass(frozen=True)
class Cause:
    """CONTRACTS §4c — one member of causes[] on a ranked-causes turn."""

    rank: int
    statement: str
    check: str
    cites: tuple[str, ...]
    fix_cites: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.rank, int) or isinstance(self.rank, bool) or self.rank < 1:
            raise ValueError(f"rank is a 1-based integer, always present: {self.rank!r}")
        for name in ("cites", "fix_cites"):
            for passage_id in getattr(self, name):
                if not isinstance(passage_id, str):
                    raise TypeError(
                        f"{name} carries passage_id strings resolving into citations[], "
                        f"never nested citation records: {passage_id!r}"
                    )


@dataclass(frozen=True)
class SourceRef:
    """A {source_id, display_name} pair — suggested_sources[] and scope_dropped[] members."""

    source_id: str
    display_name: str


@dataclass(frozen=True)
class NarrowingCandidate:
    """One selectable candidate: the label is a cause's check, the value its statement."""

    label: str
    value: str


@dataclass(frozen=True)
class Narrowing:
    """CONTRACTS §4 narrowing — a question plus candidates, needs-narrowing only."""

    question: str
    candidates: tuple[NarrowingCandidate, ...]


@dataclass(frozen=True)
class RequiredDevice:
    """CONTRACTS §4b {device, display_name} — no-manual-for-device only."""

    device: str  # canonical <vendor>/<product> id, or the model's free-form name
    display_name: str | None = None


@dataclass(frozen=True)
class RequiredManual:
    """CONTRACTS §4e — the filename to add to manuals/, no-manual-for-device only."""

    filename: str
    placeholders: tuple[str, ...] = ()


@dataclass(frozen=True)
class Timings:
    """CONTRACTS §4 timings — per-stage durations, and nothing else."""

    retrieval_ms: float | None = None
    state_acquisition_ms: float | None = None
    engine_overhead_ms: float | None = None
    first_token_ms: float | None = None
    completion_ms: float | None = None
    corpus_reload_ms: float | None = None  # run-level, not a stage of a turn


@dataclass(frozen=True)
class AnswerEnvelope:
    """CONTRACTS §4 — what a conforming consumer has accumulated when the stream ends."""

    outcome: Outcome
    direct_answer: str | None = None
    body: tuple = ()  # ordered §4d blocks; typed by parse.py
    citations: tuple[Citation, ...] = ()
    contributing_sources: tuple[str, ...] = ()
    uncovered_parts: tuple[str, ...] | None = None
    suggested_sources: tuple[SourceRef, ...] | None = None  # absent, never empty-as-a-claim
    narrowing: Narrowing | None = None
    causes: tuple[Cause, ...] | None = None
    required_device: RequiredDevice | None = None
    required_manual: RequiredManual | None = None
    scope_dropped: tuple[SourceRef, ...] | None = None
    reason: Reason | None = None
    retry_after: float | None = None  # unrounded, as the provider stated it
    detail: str | None = None
    framing: Literal["parsed", "unparsed"] | None = None
    ungrounded: bool = False
    timings: Timings | None = None

    def __post_init__(self) -> None:
        Outcome(self.outcome)
        if self.reason is not None:
            Reason(self.reason)
        if self.framing not in (None, "parsed", "unparsed"):
            raise ValueError(f"framing is 'parsed' or 'unparsed': {self.framing!r}")
        if self.retry_after is not None and self.retry_after < 0:
            raise ValueError(f"retry_after is non-negative: {self.retry_after!r}")
        if self.causes is not None:
            for position, member in enumerate(self.causes, start=1):
                if member.rank != position:
                    raise ValueError(
                        f"a cause's rank equals its position in causes[]: "
                        f"rank {member.rank} at position {position}"
                    )
