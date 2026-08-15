"""Device scope and the sidecar — design 'Device scope', 'The sidecar', 'Error Handling'.

An entry's `devices:` frontmatter is validated against two vocabularies, the rig
inventory and the corpus, and then **published** (4.3). Nothing here filters:
`api/answer-engine` 5.13 evaluates the per-passage predicate, and this spec's
obligation ends at handing it the declaration. `sidecar` is that publication —
everything `Passage` cannot carry, keyed by `passage_id`, assembled from the
loader's per-entry results and copied into the view by the corpus.

Identities are matched **exactly** (4.2). A near miss is a typo to be named, not
a device to be guessed at, and the whole point of sharing `<vendor>/<product>`
with `source_id` is that no fuzzy step is needed.

`rig.yaml`, its record and the `source_applicability` mapping belong to
`data/manual-corpus`. This module states only what it reads of them — see
`RigDevice` and `validate_scope`'s `indexed` — so nothing here redefines a type
that spec owns.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

from dawmans.triage.model import DeviceRef, Entry, EntryRejection, Flag, entry_key

if TYPE_CHECKING:  # the outcome types are the loader's, and it imports this module
    from dawmans.triage.loader import CauseOutcome, EntryOutcome, StoreOutcome


class RigDevice(Protocol):
    """The fields of a `rig.yaml` device this spec reads.

    `id` and `revision` are scope validation's. `display_name` is read by the rig
    reports and by the term check, which discards a term naming the device the owner
    holds; it is declared here because this is where the spec states what it reads of a
    rig device, not because this module reads it.
    """

    id: str
    revision: str | None
    display_name: str | None


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

    for position, cause in enumerate(entry.causes, start=1):
        claim = cause.undocumented_device
        if claim is None:
            continue
        # The cause is named in the message as well as on the record, in the form every
        # other cause-level message uses: 5.3 is about what reaches the author, and the
        # header above this line carries the file and the symptom but not the cause.
        where = f'cause {position} "{cause.statement}"'
        if claim in indexed:
            return reject(
                "undocumented-claim-invalid",
                f"{where} is marked `undocumented: {claim}`, but that device is documented by "
                "an ingested manual. Cite the section instead with a `fix:` line.",
                cause=cause.statement,
            )
        if claim not in revisions:
            return reject(
                "undocumented-claim-invalid",
                f"{where} is marked `undocumented: {claim}`, but that device is not in the rig "
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


# --- The sidecar ----------------------------------------------------------


def sidecar(
    outcome: StoreOutcome,
    passage_ids: Mapping[str, Sequence[str]],
    *,
    report: Mapping[str, Any],
) -> dict[str, Any]:
    """Everything `Passage` cannot carry, keyed by `passage_id` — design 'The sidecar'.

    Written by the corpus to `views/<hex>/reports/authored_triage.json`, inside the view
    and not beside it, so it commits and swaps atomically with the passages it keys.
    `<slug>` is the corpus's own rule, `source_id` with `/` replaced by `_`: hyphenating
    it is a silent failure, because a reader finds nothing, no error is raised, and under
    `api/answer-engine` 5.13 no passage declares devices — so every entry stays in scope
    for every turn.

    `passage_ids` maps an entry's `source_file` to the passages it emitted. **Every row
    an entry produced carries the entry's whole declaration** (4.3), including its causes
    in declared order: which passage of a split entry holds which cause is an artefact of
    the 350-word cap and changes under a re-chunk, so a consumer reading the causes of a
    citation must not get a list truncated by where the cap fell.

    `report` is the block the caller has already built, not one assembled here: the run
    writes the same block to its audit, and building it twice would let the two disagree.
    """
    return {
        "passages": [
            {"passage_id": passage_id, **_entry_row(entry_outcome)}
            for entry_outcome in outcome.ingesting
            for passage_id in passage_ids.get(entry_outcome.entry.source_file.as_posix(), ())
        ],
        "report": dict(report),
    }


def report(
    outcome: StoreOutcome,
    *,
    ledger_missing: bool = False,
    coverage: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """The run's counts and one row per rejection and per flag (2.8, 5.5).

    `coverage` is the §6 report's own rows, which land in this block so that the report
    is obtainable without asking a question (6.5) and published where a consumer can
    read it (6.6). They are passed in rather than computed here: they need the rig, and
    `triage.coverage` owns their shape — this module renders the run's own verdict.

    The pointer counts describe the entries this run **ingested**: a pointer that cost
    its entry its place is reported by that entry's rejection row, which names the entry,
    the cause and the pointer (2.2), and counting it again as unresolved would report one
    fault twice.
    """
    checked = [
        pointer
        for entry_outcome in outcome.ingesting
        for cause in entry_outcome.causes
        for pointer in cause.pointers
    ]
    without_pointer = sum(
        1
        for entry_outcome in outcome.ingesting
        for cause in entry_outcome.causes
        if cause.cause.undocumented_device is not None
    )
    return {
        "entries": len(outcome.ingesting),
        "rejected": len(outcome.rejections),
        # Counted over the store's flags rather than over `EntryOutcome.flags`, which
        # carries only the flags raised while evaluating the entry: a parse flag —
        # `unknown-frontmatter-key`, `closing-statement-inferred` — is collected before
        # any entry outcome exists, and an entry carrying one is an entry to look at.
        "flagged": len({flag.source_file for flag in outcome.flags}),
        "pointers": {
            "checked": len(checked),
            "resolved": sum(1 for pointer in checked if pointer.ok),
            # Every unresolved pointer that survives is a drifted one: an unresolved
            # pointer with no ledger row rejected its entry (2.2, 8.4).
            "unresolved": sum(1 for pointer in checked if not pointer.ok),
            "without_pointer": without_pointer,
        },
        "rejections": [
            {
                "reason": rejection.reason,
                "source_file": rejection.source_file.as_posix(),
                "symptom": rejection.symptom,
                "cause": rejection.cause,
                "detail": rejection.detail,
            }
            for rejection in outcome.rejections
        ],
        "flags": [
            {
                "name": flag.name,
                "source_file": flag.source_file.as_posix(),
                "symptom": flag.symptom,
                "cause": flag.cause,
                "detail": flag.detail,
            }
            for flag in outcome.flags
        ],
        # Deleting the ledger re-arms 2.2 for the whole store, and that must not be
        # silent: the author would otherwise meet a wall of rejections with nothing
        # explaining them.
        "ledger_missing": ledger_missing,
        # `{}` where the caller passed none, never absent: a consumer reading the block
        # gets the key either way, and an empty report is a statement while a missing
        # one is not (the rule `gaps.json` follows for the same reason).
        "coverage": dict(coverage) if coverage is not None else {},
    }


def _entry_row(outcome: EntryOutcome) -> dict[str, Any]:
    """One entry, as every passage it emitted publishes it.

    `entry_key` is an annotation and the key of nothing — a stable handle on an entry
    across a file rename. `source_file` and `line` are the two halves of CONTRACTS §2
    `entry_location`, a locator rather than an identity, which is why neither enters
    `passage_id` or `entry_key`.
    """
    entry = outcome.entry
    return {
        "entry_key": entry_key(entry),
        "symptom": entry.symptom,
        "devices": [{"id": device.id, "revision": device.revision} for device in entry.devices],
        "source_file": entry.source_file.as_posix(),
        "line": entry.line,
        "causes": [_cause_row(cause) for cause in outcome.causes],
    }


def _cause_row(outcome: CauseOutcome) -> dict[str, Any]:
    """One cause, in declared order — the source of CONTRACTS §4c's `Cause` records.

    The position in this list is that record's `rank`, which is why 1.5's "never
    re-order" is load-bearing on `api/answer-engine` 7.6 and `ui/ask-and-source-picker`
    6.6 as well as on retrieval.
    """
    cause = outcome.cause
    return {
        "statement": cause.statement,
        "check": cause.check,
        "fix": [
            {
                "source_id": pointer.pointer.source_id,
                # The number where the author gave one, the title where they did not:
                # one field, because a pointer addresses one section either way.
                "section": pointer.pointer.section_number or pointer.pointer.section_title,
                "passage_ids": list(pointer.passage_ids),
            }
            for pointer in outcome.pointers
        ],
        "undocumented_device": cause.undocumented_device,
        "flags": [flag.name for flag in outcome.flags],
    }


__all__ = [
    "RigDevice",
    "ScopeResult",
    "report",
    "sidecar",
    "validate_scope",
]
