"""SourceRecord and Passage — the CONTRACTS §1 and §2 types.

`specs/CONTRACTS.md` is governing: no field here is added to those two tables and none
is dropped. The kind-dependent fields are typed `| None`, and the constructors refuse a
value for a field the record's kind marks not applicable rather than defaulting one
into place (requirements 9.1, 12.5, 12.8).

Both records are keyword-only so they read in the CONTRACTS table's own order, and
frozen so a downstream stage cannot quietly amend what a source or a passage says.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

#: CONTRACTS §1 fixes the authored store's identity at this constant. It is a store
#: rather than a document, and `source_id` prefixes `passage_id`, so an identity that
#: moved with its contents would orphan the citation history on every edit.
AUTHORED_SOURCE_ID = "authored/triage"

SourceKind = Literal["vendor-manual", "authored-triage"]
SOURCE_KINDS: tuple[SourceKind, ...] = ("vendor-manual", "authored-triage")

ApplicabilityStatus = Literal["confirmed", "assumed"]
APPLICABILITY_STATUSES: tuple[ApplicabilityStatus, ...] = ("confirmed", "assumed")

#: The CONTRACTS §1 fields that apply to a `vendor-manual` and not to an
#: `authored-triage` source, which has no filename to derive them from and no pages.
VENDOR_MANUAL_ONLY_FIELDS = (
    "vendor",
    "product",
    "doctype",
    "lang",
    "doc_version",
    "page_count",
    "low_text",
)


@dataclass(frozen=True, slots=True, kw_only=True)
class HardwareApplicability:
    """Which hardware revision a source describes, and how well that is known.

    This is the shape of a `rig.yaml` `source_applicability` entry: the rig device the
    source documents, the revision it describes, and whether that is confirmed or
    assumed. It is never inferred from content (requirement 11.2, CONTRACTS §5); where
    no declaration exists the caller supplies `assumed` for the filename's product.
    """

    status: ApplicabilityStatus
    device: str | None = None
    revision: str | None = None

    def __post_init__(self) -> None:
        if self.status not in APPLICABILITY_STATUSES:
            raise ValueError(f"status must be one of {APPLICABILITY_STATUSES}, not {self.status!r}")


@dataclass(frozen=True, slots=True, kw_only=True)
class SourceRecord:
    """One ingested source, of either kind — CONTRACTS §1."""

    kind: SourceKind
    source_id: str
    vendor: str | None = None
    product: str | None = None
    doctype: str | None = None
    lang: str | None = None
    doc_version: str | None = None
    display_name: str
    hardware_applicability: HardwareApplicability
    page_count: int | None = None
    ingested_at: str  # ISO-8601 UTC, the time the source was last actually ingested
    chunk_count: int
    low_text: bool | None = None

    def __post_init__(self) -> None:
        if self.kind not in SOURCE_KINDS:
            raise ValueError(f"kind must be one of {SOURCE_KINDS}, not {self.kind!r}")

        if self.kind == "authored-triage":
            self._refuse_vendor_manual_fields()
            if self.source_id != AUTHORED_SOURCE_ID:
                raise ValueError(
                    f"an authored-triage source_id is the constant {AUTHORED_SOURCE_ID!r} "
                    f"(CONTRACTS §1), not {self.source_id!r}"
                )
            if self.hardware_applicability.status != "assumed":
                raise ValueError(
                    "an authored-triage hardware_applicability is fixed at 'assumed' "
                    "(CONTRACTS §1): the store is not about one device"
                )
        else:
            self._require_vendor_manual_fields()

    def _refuse_vendor_manual_fields(self) -> None:
        for name in VENDOR_MANUAL_ONLY_FIELDS:
            if getattr(self, name) is not None:
                raise ValueError(
                    f"{name} is not applicable to an authored-triage source and SHALL NOT "
                    f"be synthesised (requirement 12.5)"
                )

    def _require_vendor_manual_fields(self) -> None:
        for name in VENDOR_MANUAL_ONLY_FIELDS:
            if getattr(self, name) is None:
                raise ValueError(f"{name} is required on a vendor-manual source")


@dataclass(frozen=True, slots=True, kw_only=True)
class Passage:
    """The unit of retrieval and of citation — CONTRACTS §2.

    `unbacked` and `entry_location` are owned by `data/symptom-triage`; this package
    carries both unchanged and never sets, clears or derives them (requirement 12.6).

    A pageless source carries no `section_number`, `page_start` or `page_end`, and they
    are never synthesised (12.8). CONTRACTS §2 makes the page and the entry location
    alternatives — an authored passage "has no page instead" — so the two rules are
    enforced together, keyed on the constant `authored/triage` source ID that §1 fixes
    for the one pageless kind that exists.
    """

    passage_id: str
    source_id: str
    section_number: str | None = None
    section_title: str
    page_start: int | None = None
    page_end: int | None = None
    text: str
    degraded: bool = False
    has_figures: bool = False
    unbacked: bool = False
    entry_location: str | None = None

    def __post_init__(self) -> None:
        if self.source_id == AUTHORED_SOURCE_ID:
            self._check_pageless()
        else:
            self._check_paged()

    def _check_pageless(self) -> None:
        for name in ("section_number", "page_start", "page_end"):
            if getattr(self, name) is not None:
                raise ValueError(
                    f"{name} is absent on a passage from a pageless source and SHALL NOT "
                    f"be synthesised (requirement 12.8)"
                )
        if self.entry_location is None:
            raise ValueError(
                "entry_location is required on an authored-triage passage: it is the "
                "open-at-source target for a source that has no page (CONTRACTS §3a)"
            )

    def _check_paged(self) -> None:
        for name in ("page_start", "page_end"):
            if getattr(self, name) is None:
                raise ValueError(f"{name} is required on a passage from a source with pages")
        if self.page_end < self.page_start:  # type: ignore[operator]
            raise ValueError(f"page_end {self.page_end} precedes page_start {self.page_start}")
        if self.entry_location is not None:
            raise ValueError(
                "entry_location is absent on a vendor-manual passage, which has a page "
                "instead (CONTRACTS §2)"
            )


__all__ = [
    "APPLICABILITY_STATUSES",
    "AUTHORED_SOURCE_ID",
    "SOURCE_KINDS",
    "VENDOR_MANUAL_ONLY_FIELDS",
    "ApplicabilityStatus",
    "HardwareApplicability",
    "Passage",
    "SourceKind",
    "SourceRecord",
]
