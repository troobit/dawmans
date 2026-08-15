"""The coverage report — §6, 8.6 and 8.7.

**There is no denominator.** No enumerable universe of symptoms exists, so the report
states no percentage anywhere: it is an inventory of what the store holds, plus the one
gap that *is* enumerable — the rig side (6.3). A "78% covered" here would be a
completeness claim over a set nobody can write down, and the risk the requirements
already name is precisely that an entry's cause list can never be shown to be complete.

Six row sets, each answering a different question about the same store:

| Rows | Asks |
|---|---|
| `entries` | what is covered, with scope, cause count and pointer health (6.1) |
| `rejections`, `flags` | what went wrong, so the report covers 100% of the store (6.2) |
| `uncovered_devices` | which rig gear no entry speaks for (6.3) |
| `causes_without_pointer` | which causes 2.3 permits to go unbacked, and for what (6.4) |
| `drifted` | which entries a manual moved under, and which manual (8.6) |
| `orphaned_scope` | which entries are scoped only to gear the rig no longer holds (8.7) |

`dawmans coverage` renders them to stdout, and `to_dict()` puts the same rows in the
sidecar's `report` block, which is what makes the report obtainable without asking a
question (6.5) and publishes it where a consumer can read it (6.6's publishing half;
the consuming half closes when `api/answer-engine` or the UI names it).

**`orphaned_scope` is reported here rather than flagged at ingest**, although design
§Error Handling lists `orphaned-scope` among the flags. The device-scope table's third
row is explicit that a device documented by an ingested manual and absent from
`rig.yaml` scopes with **no** flag — it is gear removed under 8.7 or a manual that
arrived ahead of its rig entry, and 4.5 authorises no warning about it. 8.7 asks for a
report, and this is the report. See decision_log Decision 15.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from dawmans.triage import messages
from dawmans.triage.model import EntryRejection, Flag

if TYPE_CHECKING:  # both are owned elsewhere and neither imports this module
    from dawmans.triage.loader import EntryOutcome, StoreOutcome
    from dawmans.triage.scope import RigDevice


@dataclass(frozen=True)
class EntryRow:
    """One entry the store serves (6.1)."""

    source_file: str
    symptom: str
    devices: tuple[str, ...]
    """The declared scope, in declared order and without revisions — what 5.13 matches."""

    causes: int
    pointers_resolve: bool
    """Whether every fix pointer of every cause resolves **on this run**. Re-checked
    each pass rather than remembered, which is the whole of 2.1; a cause 2.3 permits to
    carry no pointer has none to fail, and is reported by `causes_without_pointer`."""

    def line(self) -> str:
        health = "every pointer resolves" if self.pointers_resolve else "a pointer does not resolve"
        causes = "1 cause" if self.causes == 1 else f"{self.causes} causes"
        return (
            f'{self.source_file} — "{self.symptom}"  {", ".join(self.devices)}  {causes}  {health}'
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_file": self.source_file,
            "symptom": self.symptom,
            "devices": list(self.devices),
            "causes": self.causes,
            "pointers_resolve": self.pointers_resolve,
        }


@dataclass(frozen=True)
class UnbackedRow:
    """One cause carrying no fix pointer, and the device that excuses it (6.4)."""

    source_file: str
    symptom: str
    cause: str
    device: str

    def line(self) -> str:
        return f'{self.source_file} — "{self.symptom}"  cause "{self.cause}"  {self.device}'

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_file": self.source_file,
            "symptom": self.symptom,
            "cause": self.cause,
            "device": self.device,
        }


@dataclass(frozen=True)
class DriftRow:
    """One cause whose pointer stopped resolving, and the source that changed (8.6)."""

    source_file: str
    symptom: str
    cause: str
    pointer: str
    source_id: str
    """The source that moved — what the author has to go and read."""

    def line(self) -> str:
        return f'{self.source_file} — "{self.symptom}"  cause "{self.cause}"  {self.pointer}'

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_file": self.source_file,
            "symptom": self.symptom,
            "cause": self.cause,
            "pointer": self.pointer,
            "source_id": self.source_id,
        }


@dataclass(frozen=True)
class OrphanRow:
    """One entry scoped only to gear the rig no longer holds (8.7). Never deleted."""

    source_file: str
    symptom: str
    devices: tuple[str, ...]

    def line(self) -> str:
        return f'{self.source_file} — "{self.symptom}"  {", ".join(self.devices)}'

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_file": self.source_file,
            "symptom": self.symptom,
            "devices": list(self.devices),
        }


@dataclass(frozen=True)
class Coverage:
    """The whole report, as rows. Rendering is `lines()`; publishing is `to_dict()`."""

    entries: tuple[EntryRow, ...]
    rejections: tuple[EntryRejection, ...]
    flags: tuple[Flag, ...]
    uncovered_devices: tuple[str, ...]
    causes_without_pointer: tuple[UnbackedRow, ...]
    drifted: tuple[DriftRow, ...]
    orphaned: tuple[OrphanRow, ...]

    def lines(self) -> list[str]:
        """The report as the owner reads it at their desk (6.5).

        Every heading is printed whether or not it has rows, and an empty one says
        `none`. Absent and empty are different statements, and only the second is one
        the report is entitled to make — the same rule `gaps.json` follows.
        """
        rendered = [
            messages.counts_of(
                len(self.entries),
                len(self.rejections),
                len({flag.source_file for flag in self.flags}),
            ),
            "",
            *_section("entries (6.1)", [row.line() for row in self.entries]),
            *_section(
                "rejected and flagged (6.2)",
                [line for item in (*self.rejections, *self.flags) for line in messages.lines(item)],
            ),
            *_section("rig gear no entry covers (6.3)", list(self.uncovered_devices)),
            *_section(
                "causes with no fix pointer (6.4)",
                [row.line() for row in self.causes_without_pointer],
            ),
            *_section("pointers that have drifted (8.6)", [row.line() for row in self.drifted]),
            *_section(
                "entries scoped only to gear outside the rig (8.7)",
                [row.line() for row in self.orphaned],
            ),
        ]
        return rendered

    def to_dict(self) -> dict[str, Any]:
        """The rows the sidecar's `report` block carries beside its own.

        The rejection and flag rows are **not** repeated here: the block already
        carries one row per rejection and per flag with its reason (5.5), and a second
        copy in the same file would be two things to keep in step. The two together are
        6.2's whole store.
        """
        return {
            "entries": [row.to_dict() for row in self.entries],
            "uncovered_devices": list(self.uncovered_devices),
            "causes_without_pointer": [row.to_dict() for row in self.causes_without_pointer],
            "drifted": [row.to_dict() for row in self.drifted],
            "orphaned_scope": [row.to_dict() for row in self.orphaned],
        }


def coverage(outcome: StoreOutcome, rig: Sequence[RigDevice]) -> Coverage:
    """The §6 report over one evaluation of the store.

    Pure over what it is handed: the run decides, and this states what it decided.
    A report that recomputed its own inputs could disagree with the run it describes.
    """
    ingesting = outcome.ingesting
    return Coverage(
        entries=tuple(_entry_row(entry) for entry in ingesting),
        rejections=outcome.rejections,
        flags=outcome.flags,
        uncovered_devices=_uncovered(ingesting, rig),
        causes_without_pointer=tuple(_unbacked_rows(ingesting)),
        drifted=tuple(_drift_rows(ingesting)),
        orphaned=tuple(_orphan_rows(ingesting, rig)),
    )


def _entry_row(outcome: EntryOutcome) -> EntryRow:
    entry = outcome.entry
    return EntryRow(
        source_file=entry.source_file.as_posix(),
        symptom=entry.symptom,
        devices=tuple(device.id for device in entry.devices),
        causes=len(entry.causes),
        pointers_resolve=all(pointer.ok for cause in outcome.causes for pointer in cause.pointers),
    )


def _uncovered(outcomes: Sequence[EntryOutcome], rig: Sequence[RigDevice]) -> tuple[str, ...]:
    """6.3, over the entries the store actually serves.

    A rejected entry's declarations do not close a gap: the entry reaches no question,
    so the gear it named has no triage covering it.
    """
    declared = {device.id for outcome in outcomes for device in outcome.entry.devices}
    return tuple(device.id for device in rig if device.id not in declared)


def _unbacked_rows(outcomes: Sequence[EntryOutcome]):
    for outcome in outcomes:
        for cause in outcome.causes:
            device = cause.cause.undocumented_device
            if device is not None:
                yield UnbackedRow(
                    source_file=outcome.entry.source_file.as_posix(),
                    symptom=outcome.entry.symptom,
                    cause=cause.cause.statement,
                    device=device,
                )


def _drift_rows(outcomes: Sequence[EntryOutcome]):
    """8.6, per drifted pointer: one cause may cite two sections and lose one of them."""
    for outcome in outcomes:
        for cause in outcome.causes:
            for pointer in cause.pointers:
                if not pointer.drifted:
                    continue
                yield DriftRow(
                    source_file=outcome.entry.source_file.as_posix(),
                    symptom=outcome.entry.symptom,
                    cause=cause.cause.statement,
                    pointer=_label(pointer.pointer),
                    source_id=pointer.pointer.source_id,
                )


def _orphan_rows(outcomes: Sequence[EntryOutcome], rig: Sequence[RigDevice]):
    """8.7: an entry **none** of whose devices is in the rig any more.

    An empty inventory declares no removal — `rig.yaml` absent is "nothing is declared
    owned" (`manual-corpus` §Rig inventory), not "everything has been taken away", and
    reporting every entry as orphaned on a machine with no rig file would bury the rows
    that mean something.
    """
    held = {device.id for device in rig}
    if not held:
        return
    for outcome in outcomes:
        devices = tuple(device.id for device in outcome.entry.devices)
        if any(device in held for device in devices):
            continue
        yield OrphanRow(
            source_file=outcome.entry.source_file.as_posix(),
            symptom=outcome.entry.symptom,
            devices=devices,
        )


def _label(pointer) -> str:
    if pointer.section_number is not None:
        return f"{pointer.source_id} §{pointer.section_number}"
    return f'{pointer.source_id} "{pointer.section_title}"'


def _section(title: str, rows: Sequence[str]) -> list[str]:
    """One heading and its rows, or the heading and `none`.

    Printed empty rather than omitted: "no entry is scoped to gear that has left the
    rig" is a statement the report is entitled to make, and a missing heading is not.
    """
    body = [f"  {row}" for row in rows] if rows else ["  none"]
    return [title, *body, ""]


__all__ = [
    "Coverage",
    "DriftRow",
    "EntryRow",
    "OrphanRow",
    "UnbackedRow",
    "coverage",
]
