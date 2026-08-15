"""Validation messages — design 'Error Handling', 5.2, 5.3, 5.5.

The rendering, and only the rendering. Every message's *words* are written where the
fault is found — `parse`, `scope`, `pointers`, `terms` and `loader` each phrase their
own rejections and flags in the entry's own terms, because that is where the entry's
own terms are known. What is here is the two lines the design prints them in:

    triage/no-sound-from-track.md — "No sound from a track"
      rejected: cause 2 "Another track is soloed" points at ableton/live-12 §16.5,
      which is not a section of that manual. Nearest: §16.4 "The Mixer". Correct the
      pointer or drop the cause.

The header names the file and the symptom; the block says what is wrong and what to
change. A reason constant is the program's vocabulary and never appears — 5.3 forbids
a message that is an internal error name, and the closed set is the taxonomy's shape
rather than anything to print at an author. `rejected:` against `flagged:` is the
whole difference on screen between an entry withdrawn and an entry served with a
remark, which is the distinction 5.2 and 8.4 turn on.

The counts line is 5.5, over **entries**: an entry the chunker split is one entry the
author wrote, and an entry carrying three flags is one entry to look at.
"""

from __future__ import annotations

import textwrap
from typing import TYPE_CHECKING

from dawmans.triage.model import EntryRejection, Flag
from dawmans.triage.pointers import LEDGER_NAME

if TYPE_CHECKING:  # the outcome type is the loader's, and it renders through this module
    from dawmans.triage.loader import StoreOutcome

#: Wrapped so a long message reads as prose rather than as one line off the terminal.
#: The wrap is presentation only: no message depends on where it falls.
WIDTH = 92
INDENT = "  "


def header(item: EntryRejection | Flag) -> str:
    """The file, and the symptom where the entry got far enough to declare one.

    A frontmatter rejection happens before the H1 is read, so there is no symptom to
    name and none is invented: the file is the whole handle the author has.
    """
    path = item.source_file.as_posix()
    if item.symptom is None:
        return path
    return f'{path} — "{item.symptom}"'


def lines(item: EntryRejection | Flag) -> list[str]:
    """One rejection or flag, as the author reads it (5.3)."""
    verb = "rejected" if isinstance(item, EntryRejection) else "flagged"
    return [header(item), *_wrapped(f"{verb}: {item.detail}")]


def counts(outcome: StoreOutcome) -> str:
    """5.5's first half: entries ingested, rejected and flagged, for this run."""
    # Flagged is counted by file, so an entry carrying three remarks is one entry to
    # look at — and so a parse flag, raised before any entry outcome exists, counts
    # like any other.
    return counts_of(
        len(outcome.ingesting),
        len(outcome.rejections),
        len({flag.source_file for flag in outcome.flags}),
    )


def counts_of(ingested: int, rejected: int, flagged: int) -> str:
    """The counts line itself, so the coverage report says it the same way."""
    return (
        f"{ingested} {'entry' if ingested == 1 else 'entries'} ingested, "
        f"{rejected} rejected, {flagged} flagged"
    )


def store_lines(outcome: StoreOutcome, *, ledger_missing: bool = False) -> list[str]:
    """The whole of 5.5: the counts, then a reason for each rejection and each flag.

    The missing-ledger line comes first among the reasons because it explains all of
    them at once: with no ledger, every pointer is checked as one that has never
    resolved, and an author who deleted the file meets a wall of 2.2 rejections with
    nothing else on screen accounting for it.
    """
    rendered = [counts(outcome)]
    if ledger_missing:
        rendered += _wrapped(
            f"{LEDGER_NAME} is not in the store, so no pointer is known to have resolved "
            "before and a pointer that does not resolve now is rejected rather than "
            "flagged. Restore the file to keep an entry whose manual has moved."
        )
    for rejection in outcome.rejections:
        rendered += lines(rejection)
    for flag in outcome.flags:
        rendered += lines(flag)
    return rendered


def _wrapped(text: str) -> list[str]:
    return textwrap.wrap(
        text,
        width=WIDTH,
        initial_indent=INDENT,
        subsequent_indent=INDENT,
        break_long_words=False,
        break_on_hyphens=False,
    )


__all__ = [
    "INDENT",
    "WIDTH",
    "counts",
    "counts_of",
    "header",
    "lines",
    "store_lines",
]
