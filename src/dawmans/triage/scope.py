"""Device scope — design 'Device scope' and 'Error Handling'.

An entry's `devices:` frontmatter is validated against two vocabularies, the rig
inventory and the corpus, and then **published** (4.3). Nothing here filters:
`api/answer-engine` 5.13 evaluates the per-passage predicate, and this spec's
obligation ends at handing it the declaration.

Identities are matched **exactly** (4.2). A near miss is a typo to be named, not
a device to be guessed at, and the whole point of sharing `<vendor>/<product>`
with `source_id` is that no fuzzy step is needed.

`rig.yaml`, its record and the `source_applicability` mapping belong to
`data/manual-corpus`. This module states only what it reads of them — see
`RigDevice` and `validate_scope`'s `indexed` — so nothing here redefines a type
that spec owns.
"""

from __future__ import annotations

from collections.abc import Collection, Sequence
from dataclasses import dataclass
from typing import Protocol

from dawmans.triage.model import DeviceRef, Entry, EntryRejection, Flag


class RigDevice(Protocol):
    """The two fields of a `rig.yaml` device that scope validation reads.

    `display_name` is the rig reports' and the term check's, not this module's.
    """

    id: str
    revision: str | None


@dataclass(frozen=True)
class ScopeResult:
    """A rejection excludes the entry; flags and a scope accompany one that ingests."""

    scoped: list[str]
    """Declared device ids in declared order, revisions dropped — the identities
    5.13 matches. Empty on a rejection."""

    rejection: EntryRejection | None
    flags: list[Flag]


def validate_scope(
    entry: Entry,
    rig: Sequence[RigDevice],
    indexed: Collection[str],
) -> ScopeResult:
    """Apply the six rows of design 'Device scope', plus 2.3's `undocumented:` claim.

    `indexed` is every identity the corpus documents: each indexed vendor-manual
    `source_id` **and** the device id it declares under `source_applicability`
    (Decision 8). The two differ wherever a filename carries a generation marker
    the rig id does not — `focusrite/scarlett-solo-4g` against
    `focusrite/scarlett-solo` — and matching source ids alone would report a
    device as undocumented while its guide sits in the corpus.
    """
    revisions = _rig_revisions(rig)
    flags: list[Flag] = []

    def flag(name, detail: str, cause: str | None = None) -> None:
        flags.append(
            Flag(
                name=name,
                source_file=entry.source_file,
                detail=detail,
                symptom=entry.symptom,
                cause=cause,
            )
        )

    def reject(reason, detail: str, cause: str | None = None) -> ScopeResult:
        return ScopeResult(
            scoped=[],
            rejection=EntryRejection(
                reason=reason,
                source_file=entry.source_file,
                detail=detail,
                symptom=entry.symptom,
                cause=cause,
            ),
            flags=[],
        )

    unrecognised = [d for d in entry.devices if d.id not in revisions and d.id not in indexed]
    if unrecognised and len(unrecognised) == len(entry.devices):
        named = ", ".join(f"`{d.id}`" for d in unrecognised)
        return reject(
            "all-devices-unrecognised",
            f"no device in `devices:` is in the rig inventory or an ingested source: {named}. "
            "An entry none of whose devices is recognised is returned for no question at all. "
            "Correct the identities, or add the device to `rig.yaml`.",
        )

    for device in entry.devices:
        in_rig = device.id in revisions
        if not in_rig and device.id not in indexed:
            flag(
                "unknown-device",
                f"`devices:` names `{device.id}`, which is neither in the rig inventory nor an "
                "ingested source. Correct the identity, or add the device to `rig.yaml`.",
            )
            continue
        if in_rig and device.id not in indexed:
            flag(
                "undocumented-device-scope",
                f"applies to `{device.id}`, which is in the rig inventory with no ingested "
                "manual. The entry still applies; no vendor passage can back a cause about it.",
            )
        if in_rig:
            _check_revision(device, revisions[device.id], flag)

    for cause in entry.causes:
        claim = cause.undocumented_device
        if claim is None:
            continue
        if claim in indexed:
            return reject(
                "undocumented-claim-invalid",
                f"the cause is marked `undocumented: {claim}`, but that device is documented by "
                "an ingested manual. Cite the section instead with a `fix:` line.",
                cause=cause.statement,
            )
        if claim not in revisions:
            return reject(
                "undocumented-claim-invalid",
                f"the cause is marked `undocumented: {claim}`, but that device is not in the rig "
                "inventory. 2.3 permits an unbacked cause only for gear the rig records and no "
                "manual covers.",
                cause=cause.statement,
            )

    return ScopeResult(scoped=[d.id for d in entry.devices], rejection=None, flags=flags)


def _rig_revisions(rig: Sequence[RigDevice]) -> dict[str, str | None]:
    """Device id → declared revision. The first entry for an id wins.

    A duplicated id is `rig.yaml`'s own defect and `data/manual-corpus` reports
    it; taking the first keeps scope validation deterministic either way.
    """
    revisions: dict[str, str | None] = {}
    for device in rig:
        revisions.setdefault(device.id, device.revision)
    return revisions


def _check_revision(device: DeviceRef, rig_revision: str | None, flag) -> None:
    """4.6, compared exactly after casefolding and stripping non-alphanumerics.

    `@mk2` against `revision: mk2` matches and `@12-standard` against
    `"12 Standard"` matches, while `@suite` does not. Either-contains matching
    would let `@12` and even `@s` satisfy `12 Standard`, which is the mk1/mk2
    case 4.6 exists for. The message quotes the rig's value **verbatim**, so
    correcting a declaration is a copy rather than a guess.
    """
    if device.revision is None:
        return
    if _normalise_revision(device.revision) == _normalise_revision(rig_revision or ""):
        return
    held = f"`{rig_revision}`" if rig_revision else "no revision at all"
    flag(
        "revision-mismatch",
        f"`devices:` constrains `{device.id}` to `{device.revision}`, but the rig inventory "
        f"records {held} for that device. A step for another edition is useless on this rig.",
    )


def _normalise_revision(value: str) -> str:
    return "".join(character for character in value.casefold() if character.isalnum())
