"""rig.yaml, hardware applicability, and the two gap reports.

`rig.yaml` sits at the repository root beside `manuals/`, hand-maintained and committed —
the PDFs are neither. It is the one declared input this spec has that is not a source, and
11.3 keeps it apart from the corpus inventory on purpose: **what is documented is not
evidence of what is owned.** Nothing here reads `manuals/`.

The join between the two inventories runs through `hardware_applicability.device` and never
through `source_id` (Decision 9). The Focusrite is why: its filename's product carries the
generation marker (`scarlett-solo-4g`) and the rig's device id does not
(`scarlett-solo`), so a join on the ID would miss the device and report it undocumented
with its manual sitting in `manuals/`. The `source_applicability` declaration is what makes
them meet, and it is mandatory rather than optional wherever the two ids differ.

Three reports come out of that join, and only two of them are published. `gaps.json`
carries owned-but-undocumented (11.4) and documented-but-unconfirmed (11.5), because
CONTRACTS §5 governs two reports with named consumers. indexed-but-not-owned (11.7) is an
ingestion-time diagnostic for whoever maintains this file and stays in the run report.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import yaml

from dawmans.records import AUTHORED_SOURCE_ID, HardwareApplicability, SourceRecord

#: The declared rig inventory, at the repository root beside `manuals/`.
RIG_FILE = "rig.yaml"

#: Device ids take the same `<vendor>/<product>` shape as a `source_id`, so matching is
#: exact and never fuzzy (design §Rig inventory).
_DEVICE_ID_SHAPE = "<vendor>/<product>"


class RigError(ValueError):
    """`rig.yaml` says something the rig join cannot act on.

    A **failure**, not a rejection: 1.6's rejection list is per source and no source is at
    fault here. The file is hand-written and committed, so a mistake in it is loud at the
    top of the run rather than a silently wrong report at the end of it.
    """


@dataclass(frozen=True)
class RigDevice:
    """One piece of hardware the studio owner holds (11.3)."""

    id: str
    #: Names the **device**, not the document. `SourceRecord.display_name` is derived from
    #: the filename, and `Ableton Live 12 Standard` against `Ableton Live 12` is not a
    #: conflict. This one appears only in the gap reports.
    display_name: str
    #: Absent where the unit declares no revision marker, as the Nitro Max does not.
    revision: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "display_name": self.display_name, "revision": self.revision}


@dataclass(frozen=True)
class Unconfirmed:
    """One indexed source documenting an owned device without confirming the revision.

    Both revisions travel because the two arms of 11.5 are not the same finding: an
    `assumed` source has never been checked, while a `confirmed` one whose revision differs
    was checked against a different unit.
    """

    source_id: str
    display_name: str
    device: str
    status: str
    declared_revision: str | None
    owned_revision: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "display_name": self.display_name,
            "device": self.device,
            "status": self.status,
            "declared_revision": self.declared_revision,
            "owned_revision": self.owned_revision,
        }


@dataclass(frozen=True)
class Rig:
    """The declared inventory, and the source-to-device declarations that join it."""

    devices: tuple[RigDevice, ...] = ()
    #: `source_id` -> the applicability that source's document carries. Absent means
    #: 11.2's default applies: `assumed` for the product named in the filename.
    source_applicability: Mapping[str, HardwareApplicability] = field(default_factory=dict)

    @property
    def device_ids(self) -> frozenset[str]:
        return frozenset(device.id for device in self.devices)

    def device(self, device_id: str | None) -> RigDevice | None:
        return next((d for d in self.devices if d.id == device_id), None)

    def applicability_for(self, record: SourceRecord) -> HardwareApplicability:
        """The applicability this run records for one source (11.1, 11.2).

        An `authored-triage` source is left alone: CONTRACTS §1 fixes its source-level
        value at `assumed` with no device, and `from_dict` refuses a declaration for it, so
        there is nothing here to apply.
        """
        if record.kind == "authored-triage":
            return record.hardware_applicability
        return self.source_applicability.get(record.source_id, record.hardware_applicability)

    def applied(self, record: SourceRecord) -> SourceRecord:
        """The record with its declared applicability in place of the loader's default.

        The loader sets `assumed` for the filename's own product (11.2) because it has no
        access to this file; where a declaration exists it replaces that, and where none
        does the default stands. Nothing reads the document to decide (11.2, CONTRACTS §5).
        """
        applicability = self.applicability_for(record)
        if applicability == record.hardware_applicability:
            return record
        return replace(record, hardware_applicability=applicability)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> Rig:
        if data is None:
            return cls()
        if not isinstance(data, Mapping):
            raise RigError(f"{RIG_FILE} must be a mapping, not {type(data).__name__}")
        return cls(
            devices=_devices(data.get("devices")),
            source_applicability=_applicability(data.get("source_applicability")),
        )


def load_rig(path: Path) -> Rig:
    """Read the declared inventory.

    An absent file is an **empty inventory**, not an error: nothing is declared owned, so
    there is no gap to report and no source is at fault. An unreadable or malformed one is
    a `RigError`, because it is a claim the run cannot act on rather than an absent claim.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return Rig()
    except OSError as error:
        raise RigError(f"{path} could not be read: {error}") from error

    try:
        return Rig.from_dict(yaml.safe_load(text))
    except yaml.YAMLError as error:
        raise RigError(f"{path} is not readable YAML: {error}") from error


def _devices(raw: Any) -> tuple[RigDevice, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, Sequence) or isinstance(raw, str):
        raise RigError("devices must be a list")

    devices: list[RigDevice] = []
    seen: set[str] = set()
    for entry in raw:
        if not isinstance(entry, Mapping):
            raise RigError(f"each device is a mapping, not {type(entry).__name__}")
        device_id = entry.get("id")
        if not isinstance(device_id, str) or not _is_device_id(device_id):
            raise RigError(f"device id {device_id!r} is not of the form {_DEVICE_ID_SHAPE}")
        if device_id in seen:
            raise RigError(
                f"{device_id} is declared twice: the revision comparison would depend on "
                f"which entry was read last"
            )
        seen.add(device_id)
        display_name = entry.get("display_name")
        if not isinstance(display_name, str) or not display_name.strip():
            raise RigError(f"{device_id} declares no display_name")
        devices.append(
            RigDevice(
                id=device_id,
                display_name=display_name,
                revision=_text(entry.get("revision")),
            )
        )
    return tuple(devices)


def _applicability(raw: Any) -> dict[str, HardwareApplicability]:
    if raw is None:
        return {}
    if not isinstance(raw, Mapping):
        raise RigError("source_applicability must be a mapping of source_id to a declaration")

    declared: dict[str, HardwareApplicability] = {}
    for source_id, entry in raw.items():
        if source_id == AUTHORED_SOURCE_ID:
            raise RigError(
                f"{AUTHORED_SOURCE_ID} takes no source_applicability: CONTRACTS §1 fixes the "
                f"authored store's source-level value at 'assumed' with no device, because the "
                f"store is not about one device"
            )
        if not isinstance(entry, Mapping):
            raise RigError(f"{source_id}'s declaration is a mapping, not {type(entry).__name__}")
        device = _text(entry.get("device"))
        if device is None:
            raise RigError(
                f"{source_id}'s declaration names no device: there is nothing for the rig "
                f"join to match on, and the 11.2 default it displaces was at least a device id"
            )
        status = entry.get("status", "assumed")
        try:
            declared[source_id] = HardwareApplicability(
                status=status, device=device, revision=_text(entry.get("revision"))
            )
        except ValueError as error:
            raise RigError(f"{source_id}: {error}") from error
    return declared


def _is_device_id(value: str) -> bool:
    vendor, _, product = value.partition("/")
    return value.strip() == value and bool(vendor) and bool(product) and "/" not in product


def _text(value: Any) -> str | None:
    """YAML gives `12` for an unquoted revision; the comparison is on text either way."""
    if value is None:
        return None
    return str(value)


@dataclass(frozen=True)
class GapReports:
    """The three reports of §11, of which `to_dict` publishes two."""

    owned_but_undocumented: tuple[RigDevice, ...] = ()
    documented_but_unconfirmed: tuple[Unconfirmed, ...] = ()
    #: 11.7, the run report only. A manual for gear the owner does not hold is not a gap in
    #: the rig, CONTRACTS §5 governs two reports, and adding a third member to a published
    #: payload would oblige two other specs to render something neither has a use for.
    indexed_but_not_owned: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        """`views/<hex>/gaps.json` (11.6).

        **Both members are always present, empty or not.** 11.4 requires the empty report
        to be emitted rather than omitted, and `api/answer-engine` 9.6 depends on it: it is
        the sole resolver of a canonical device id, so a consumer that treats absence as
        equivalent to emptiness breaks silently on the day it fills.
        """
        return {
            "owned_but_undocumented": [device.to_dict() for device in self.owned_but_undocumented],
            "documented_but_unconfirmed": [
                entry.to_dict() for entry in self.documented_but_unconfirmed
            ],
        }


def gap_reports(rig: Rig, records: Iterable[SourceRecord]) -> GapReports:
    """Compute all three reports over the run's resolved records (11.4, 11.5, 11.7).

    They are computed together because the first and third are complements over the same
    key, and that pairing is the only thing on either report distinguishing a **missing
    declaration** from a genuine gap: an undeclared generation marker puts the device on
    owned-but-undocumented and the source on indexed-but-not-owned at the same time, while
    a real gap produces the first alone and a genuinely unowned manual the second alone.

    `records` are the records **as this run will index them**, so `Rig.applied` has already
    run over each. Both reports compute over `hardware_applicability.device` and never over
    `source_id`.
    """
    indexed = list(records)
    owned = rig.device_ids

    # 11.4 excludes the authored store: a triage entry naming a device must not make that
    # device look documented, which is the case CONTRACTS §5 and `api/answer-engine` 9.6
    # both rest on. It has no live instance and is what keeps the report honest the moment
    # a device is declared ahead of its manual.
    documented = {
        record.hardware_applicability.device for record in indexed if record.kind == "vendor-manual"
    }

    unconfirmed = []
    for record in sorted(indexed, key=lambda r: r.source_id):
        applicability = record.hardware_applicability
        device = rig.device(applicability.device)
        if device is None:
            continue  # 11.5's own qualifier: only devices in the rig inventory
        if applicability.status == "confirmed" and not _differs(
            applicability.revision, device.revision
        ):
            continue
        unconfirmed.append(
            Unconfirmed(
                source_id=record.source_id,
                display_name=record.display_name,
                device=device.id,
                status=applicability.status,
                declared_revision=applicability.revision,
                owned_revision=device.revision,
            )
        )

    return GapReports(
        owned_but_undocumented=tuple(
            device for device in rig.devices if device.id not in documented
        ),
        documented_but_unconfirmed=tuple(unconfirmed),
        indexed_but_not_owned=tuple(
            sorted(
                record.source_id
                for record in indexed
                if record.kind == "vendor-manual"
                and record.hardware_applicability.device not in owned
            )
        ),
    )


def _differs(declared: str | None, owned: str | None) -> bool:
    """Revision comparison is casefold-and-strip (design §Rig inventory).

    Two absent revisions agree: the Nitro Max declares no revision marker, and treating
    absence as a difference would report every unmarked device against every manual for it.
    """
    return _normalised(declared) != _normalised(owned)


def _normalised(revision: str | None) -> str:
    return (revision or "").strip().casefold()


__all__ = [
    "RIG_FILE",
    "GapReports",
    "Rig",
    "RigDevice",
    "RigError",
    "Unconfirmed",
    "gap_reports",
    "load_rig",
]
