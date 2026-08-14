"""Fix pointers — the grammar of design 'Fix pointers'.

    fix: <source_id> §<section-number>              ableton/live-12 §16.4
    fix: <source_id> "<section title>"              akai/apc-key-25 "Shift Functions"
    fix: <source_id> §<section-number> "<title>"    title corroborates, does not select

No page form exists: 8.1 forbids page-only addressing and admitting a page even
as a qualifier would reintroduce the breakage 8.3 exists to avoid (Decision 3).

`SectionIndex` and `resolve` are Phase 2 and are not here yet.
"""

from __future__ import annotations

import re

from dawmans.triage.model import Pointer

_POINTER_RE = re.compile(
    r"""^\s*
        (?P<source_id>\S+)                       # the source token
        (?:\s*§\s*(?P<number>[^\s"“”]+))?        # optional §<section-number>
        (?:\s*["“](?P<title>[^"”]*)["”])?        # optional "<section title>"
        \s*$""",
    re.VERBOSE,
)


def parse_pointer(text: str, line: int) -> Pointer | None:
    """Read one `fix:` value, or `None` where it addresses nothing.

    A pointer naming neither a section number nor a section title addresses
    nothing at all, so it is not a pointer. The caller retains the author's text
    and rejects the cause under `cause-missing-fix` if nothing else backs it —
    which keeps the rejection set closed and names the slip at the desk.
    """
    match = _POINTER_RE.match(text)
    if match is None:
        return None
    number = match.group("number")
    title = (match.group("title") or "").strip() or None
    if number is None and title is None:
        return None
    return Pointer(
        source_id=match.group("source_id"),
        section_number=number,
        section_title=title,
        line=line,
    )
