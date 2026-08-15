"""The per-run report and the per-source ingestion audits.

Two artefacts with two lifetimes (design §Index layout). The **run report** describes one
run, is written to the terminal, and is gone when the terminal scrolls. The **ingestion
audit** at `index/audits/<slug>.json` describes one *source* — its English page ranges
(4.4), its glyph counts (5.4), its anchor quality, and its rejection reason — and is keyed
to that source's shard: rewritten only when the source is re-ingested, surviving the shard
being reused, and still readable after the view it accompanied has been collected.

Nothing here decides anything. The outcome of a source is decided by the stage that
produced it, the 11.7 line is computed by `corpus/rig.py`, and the 9.5 anomalies are
computed from the store scans; this module renders what it is handed and writes the audit
file. That is deliberate — a report that recomputed its own inputs could disagree with the
run it claims to describe.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any, Literal

from dawmans.corpus.discover import AUDIT_DIR, DiscoveryRejection, slug
from dawmans.corpus.loader import Rejection
from dawmans.records import VENDOR_MANUAL_ONLY_FIELDS, HardwareApplicability, SourceRecord

#: What the inventory prints for a field CONTRACTS §1 marks not applicable to a source's
#: kind. 9.1 requires it reported as such rather than given an invented value: `lang` as
#: `en` or `page_count` as `0` on the authored store would each be a claim nobody made.
NOT_APPLICABLE = "not applicable"

Outcome = Literal["ingested", "skipped", "rejected"]
OUTCOMES: tuple[Outcome, ...] = ("ingested", "skipped", "rejected")

_VERBS: Mapping[str, str] = {
    "ingested": "ingested",
    "skipped": "skipped as unchanged",
}


@dataclass(frozen=True)
class SourceOutcome:
    """What became of one source in this run (1.5)."""

    store: str
    outcome: Outcome
    #: None where the source never acquired an identity — a `filename-invalid` rejection
    #: is rejected *for* having no parseable name, so there is nothing to name it by.
    source_id: str | None = None
    rejection: Rejection | None = None
    #: The file the source was found as. The only handle a nameless rejection leaves the
    #: owner, so it is what its line prints.
    origin: Path | None = None

    def __post_init__(self) -> None:
        if self.outcome not in OUTCOMES:
            raise ValueError(f"outcome must be one of {OUTCOMES}, not {self.outcome!r}")
        if (self.outcome == "rejected") != (self.rejection is not None):
            raise ValueError(
                "a rejected source carries its rejection and an ingested or skipped one "
                "carries none (1.5, 1.6): the reason is what the report line exists for"
            )

    @classmethod
    def of(cls, rejection: DiscoveryRejection, *, store: str) -> SourceOutcome:
        """The outcome for a source discovery already rejected (2.5, 2.6)."""
        return cls(
            store=store,
            outcome="rejected",
            source_id=rejection.source_id,
            rejection=rejection.rejection,
            origin=rejection.origin,
        )

    @property
    def name(self) -> str:
        if self.source_id is not None:
            return self.source_id
        return self.origin.name if self.origin is not None else "<unnamed source>"

    def line(self) -> str:
        if self.rejection is None:
            return f"{self.name}  {_VERBS[self.outcome]}"
        line = f"{self.name}  rejected: {self.rejection.reason}"
        # For `filename-invalid` the detail is the expected pattern, which is the whole
        # point of the line: the name that was is already on screen, the name that should
        # have been is not.
        return f"{line} — {self.rejection.detail}" if self.rejection.detail else line


@dataclass(frozen=True)
class Failure:
    """One source that failed for a reason outside 1.6's closed set (1.7).

    Listed, never fatal on its own: the run continues through the remaining sources and
    exits non-zero at the end, so a failure costs one source rather than the corpus.
    """

    message: str
    source_id: str | None = None

    def line(self) -> str:
        who = self.source_id or "run"
        return f"failed: {who} — {self.message}"


@dataclass(frozen=True)
class StoreAnomaly:
    """9.5, for one store and in both directions.

    Per store because 9.5 forbids testing a source of one kind against the other kind's
    store: an authored source is not an anomaly for being absent from `manuals/`. The
    store's name is on every line for the same reason.
    """

    store: str
    in_store_not_indexed: tuple[str, ...] = ()
    indexed_not_in_store: tuple[str, ...] = ()

    def lines(self) -> list[str]:
        return [
            *(
                f"{self.store}: {source_id} is present in the store and absent from the index"
                for source_id in self.in_store_not_indexed
            ),
            *(
                f"{self.store}: {source_id} is indexed and absent from the store"
                for source_id in self.indexed_not_in_store
            ),
        ]


@dataclass(frozen=True)
class RunReport:
    """One ingestion run, as the owner reads it.

    `exit_code` is driven by `failures` alone. A rejection is a reported exclusion and the
    run still succeeds (1.6); an anomaly is a report rather than a gate — a source in
    `manuals/` and absent from the index is already reported as rejected by 1.5, and
    failing the run again on the same fact would make a rejection fail it by the back door.
    """

    outcomes: tuple[SourceOutcome, ...] = ()
    failures: tuple[Failure, ...] = ()
    anomalies: tuple[StoreAnomaly, ...] = ()
    #: A store whose discovery set is unknown. Not an anomaly and not a failure: nothing
    #: was removed on its behalf and nothing is claimed about what it holds.
    unavailable_stores: tuple[str, ...] = ()
    #: 11.7, supplied by `corpus/rig.py`. Never an error, never in `gaps.json` — it is a
    #: prompt to add a `source_applicability` declaration or a device to `rig.yaml`.
    indexed_but_not_owned: tuple[str, ...] = ()

    @property
    def succeeded(self) -> bool:
        return not self.failures

    @property
    def exit_code(self) -> int:
        return 0 if self.succeeded else 1

    def line_for(self, source_id: str) -> str:
        for outcome in self.outcomes:
            if outcome.source_id == source_id:
                return outcome.line()
        raise KeyError(f"{source_id} has no outcome in this run")

    def lines(self) -> list[str]:
        lines = [outcome.line() for outcome in self.outcomes]
        lines += [
            f"{store}: store unavailable — no shard removed" for store in self.unavailable_stores
        ]
        for anomaly in self.anomalies:
            lines += anomaly.lines()
        lines += [
            f"{source_id} is indexed and its device is not in rig.yaml"
            for source_id in self.indexed_but_not_owned
        ]
        lines += [failure.line() for failure in self.failures]
        return lines


# --- the ingestion audit ------------------------------------------------------------------


def audit_path(index_root: Path, source_id: str) -> Path:
    return index_root / AUDIT_DIR / f"{slug(source_id)}.json"


def write_audit(
    index_root: Path,
    source_id: str,
    audit: Mapping[str, Any],
    *,
    rejection: Rejection | None = None,
) -> Path:
    """Write one source's audit as that source finishes, committed shard or not.

    A rejected source commits no shard, so an audit written only on success would be
    written only where it is least needed: the diagnostics are the sole record of *why*
    the source was excluded.

    `rejection` is always recorded, as `null` where there is none. Absent and null are
    different to a reader and only one of them is a statement — the same rule `gaps.json`
    follows for an empty report (11.4).

    A **reused** shard's audit is not rewritten, and that is the caller's rule to keep:
    the audit describes the run that produced the shard, and stamping this run's date on
    diagnostics it did not produce would make the file lie about when it was measured.
    """
    payload = dict(audit)
    payload["rejection"] = (
        None if rejection is None else {"reason": rejection.reason, "detail": rejection.detail}
    )

    path = audit_path(index_root, source_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)
    return path


def read_audit(index_root: Path, source_id: str) -> dict[str, Any] | None:
    """This source's audit, or None where none was written."""
    try:
        return json.loads(audit_path(index_root, source_id).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


# --- 9.1, the inventory -------------------------------------------------------------------


def inventory_row(record: SourceRecord) -> dict[str, Any]:
    """Every field of the CONTRACTS §1 table, and no field of this module's own.

    Derived from the record's own fields rather than a hand-written key list, because 9.1
    names *that* table and not a copy of it: a list here would drift from CONTRACTS §1
    silently, and a derived row cannot.
    """
    absent: frozenset[str] = frozenset()
    if record.kind == "authored-triage":
        absent = frozenset(VENDOR_MANUAL_ONLY_FIELDS)
    return {
        field.name: NOT_APPLICABLE if field.name in absent else getattr(record, field.name)
        for field in fields(record)
    }


def inventory_lines(
    records: Iterable[SourceRecord],
    *,
    audits: Mapping[str, Mapping[str, Any]] | None = None,
) -> list[str]:
    """The inventory, with each `vendor-manual`'s 4.4 English ranges beside it.

    Beside, not inside: 9.1's last sentence makes the page-range audit an *ingestion
    report* rather than a field of the record, and putting it on the row would add a field
    to CONTRACTS §1.
    """
    audits = audits or {}
    lines: list[str] = []
    for record in records:
        row = inventory_row(record)
        lines.append(f"{row['source_id']}  {row['kind']}")
        lines += [f"    {name}: {_render(value)}" for name, value in row.items()]
        lines += [f"    {line}" for line in _english_lines(audits.get(record.source_id))]
    return lines


def _english_lines(audit: Mapping[str, Any] | None) -> list[str]:
    """The 4.4 audit: which pages were included, which excluded, which only in part.

    All three, always, when the audit is present. A partial page is inside a range on the
    included line, so listing it separately is the only thing that makes a sub-page
    selection visible rather than hidden inside a whole-page range.
    """
    language = (audit or {}).get("language")
    if not isinstance(language, Mapping):
        return []
    return [
        f"english pages: {_ranges(language.get('english_pages'))}",
        f"excluded pages: {_ranges(language.get('excluded_pages'))}",
        f"partial pages: {_pages(language.get('partial_pages'))}",
    ]


def _ranges(spans: Any) -> str:
    if not spans:
        return "none"
    bounds = (tuple(span) for span in spans)
    return ", ".join(str(a) if a == b else f"{a}-{b}" for a, b in bounds)


def _pages(pages: Any) -> str:
    return ", ".join(str(page) for page in pages) if pages else "none"


def _render(value: Any) -> str:
    """One field, as a person reads it.

    `hardware_applicability` is the only structured field on the record, and its dataclass
    repr is the wrong thing to print at someone: the status is the part that matters —
    11.5 exists because `assumed` means nobody has checked — and it is the part a repr
    buries in the middle.
    """
    if isinstance(value, HardwareApplicability):
        parts = [value.status]
        if value.device is not None:
            parts.append(f"for {value.device}")
        if value.revision is not None:
            parts.append(f"revision {value.revision}")
        return " ".join(parts)
    return str(value)


__all__ = [
    "AUDIT_DIR",
    "NOT_APPLICABLE",
    "OUTCOMES",
    "Failure",
    "Outcome",
    "RunReport",
    "SourceOutcome",
    "StoreAnomaly",
    "audit_path",
    "inventory_lines",
    "inventory_row",
    "read_audit",
    "write_audit",
]
