"""The triage entry model — design.md 'Components and Interfaces'.

Types, and the two derivations over them that every other module needs.
Everything downstream of an `Entry` builds against `SourceLoader`, `Discovered`,
`LoadResult`, `Region`, `Unit` and `UnitFlags` from `dawmans/corpus/loader.py`:
`data/manual-corpus` owns those and nothing here redefines them.

The rejection and flag vocabularies live here rather than in `parse` so that
`parse`, `pointers`, `scope` and `coverage` can all name them without importing
one another. `normalised_symptom` and `entry_key` are here for the same reason:
they are functions of the model's own fields, and `loader` (1.9's duplicate test)
and `scope` (the sidecar's annotation) both need them without importing each
other.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

# --- The entry ------------------------------------------------------------


@dataclass(frozen=True)
class DeviceRef:
    """One device declared in an entry's `devices:` frontmatter."""

    id: str
    """`<vendor>/<product>`, matched exactly against `rig.yaml`."""

    revision: str | None
    """The `@` suffix, compared per design 'Device scope'."""


@dataclass(frozen=True)
class Pointer:
    """A cause's fix pointer, addressing a section of a vendor manual.

    Never a page: 8.1 forbids page-only addressing and Decision 3 admits no page
    form at all. At least one of `section_number` and `section_title` is set.
    """

    source_id: str
    section_number: str | None
    section_title: str | None
    """Raw, as the author typed it; normalised on lookup."""

    line: int
    """The `fix:` line in the entry file, for the 5.3 message."""


@dataclass(frozen=True)
class Unresolved:
    """The outcome of a pointer that does not address a passage."""

    pointer: Pointer
    reason: Literal["unknown-source", "no-such-section", "ambiguous-title", "authored-target"]
    candidates: list[str]
    """Nearest sections, for the 5.3 message; empty where none apply."""


@dataclass(frozen=True)
class Cause:
    """One candidate explanation for a symptom, with its check and its fix."""

    statement: str
    check: str
    notes: str
    """`why:` lines, loose prose and `###`+ headings, with markers normalised."""

    fixes: list[Pointer]
    """Empty if and only if `undocumented_device` is set (2.3)."""

    undocumented_device: str | None


@dataclass(frozen=True)
class Entry:
    """One symptom and its ranked candidate causes — the unit an author writes."""

    symptom: str
    phrasings: list[str]
    preamble: str
    devices: list[DeviceRef]
    causes: list[Cause]
    """Declared order, never sorted: it becomes the `rank` of CONTRACTS §4c (1.5)."""

    closing: str | None
    source_file: Path
    """Repo-relative, e.g. `triage/no-sound-from-track.md`. Held stable (3.5)."""

    line: int
    """The H1's line. With `source_file`, the two halves of CONTRACTS §2 `entry_location`."""


# --- Rejections and flags -------------------------------------------------

RejectionReason = Literal[
    "frontmatter-missing",
    "frontmatter-malformed",
    "no-devices",
    "devices-not-a-list",
    "no-symptom",
    "too-few-causes",
    "too-many-causes",
    "cause-missing-check",
    "cause-missing-fix",
    "cause-fix-and-undocumented",
    "pointer-unresolved",
    "pointer-authored-target",
    "undocumented-claim-invalid",
    "all-devices-unrecognised",
    "duplicate-symptom",
]
"""The closed set of design 'Error Handling'. Anything outside it is a failure, not a rejection."""

FlagName = Literal[
    "pointer-drifted",
    "unbacked-cause",
    "term-not-in-passage",
    "unknown-device",
    "revision-mismatch",
    "title-number-disagreement",
    "undocumented-device-scope",
    "orphaned-scope",
    "closing-statement-inferred",
    "unknown-frontmatter-key",
]
"""The closed set of design 'Error Handling'. Every one leaves the entry ingested."""


@dataclass(frozen=True)
class EntryRejection:
    """One entry excluded from the run. The run itself still succeeds (5.2)."""

    reason: RejectionReason
    source_file: Path
    detail: str
    """What is wrong and what to change, in the entry's own words (5.3)."""

    symptom: str | None = None
    cause: str | None = None


@dataclass(frozen=True)
class Flag:
    """One remark about an entry that stays ingested."""

    name: FlagName
    source_file: Path
    detail: str
    symptom: str | None = None
    cause: str | None = None


# --- Derived identities ---------------------------------------------------

_WHITESPACE = re.compile(r"\s+")


def normalised_symptom(symptom: str) -> str:
    """The form 1.9 compares two entries on: casefolded, whitespace runs collapsed.

    Deliberately **not** `pointers.normalise_title`, which also strips a leading
    section number: a symptom may legitimately open with one — "0 dB is never
    reached" — and stripping it would collide two symptoms that differ.
    """
    return _WHITESPACE.sub(" ", symptom).strip().casefold()


def entry_key(entry: Entry) -> str:
    """sha256 over the normalised symptom and the sorted device ids.

    An **annotation**, and the key of nothing: it gives the coverage report and
    the ledger's `entry_keys` a stable handle on an entry across a file rename.
    It is not `passage_id`, which is content-derived, and it is not 1.9's
    duplicate test, which is broader — same normalised symptom and *intersecting*
    device sets, not equal ones.

    The device ids are sorted and deduplicated so that reordering `devices:`
    moves no handle; the revision suffix is excluded for the same reason 1.9's
    test excludes it, the scope being the set of devices the entry applies to.
    """
    digest = hashlib.sha256()
    digest.update(normalised_symptom(entry.symptom).encode("utf-8"))
    for device_id in sorted({device.id for device in entry.devices}):
        digest.update(b"\n")
        digest.update(device_id.encode("utf-8"))
    return digest.hexdigest()
