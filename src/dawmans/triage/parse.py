"""Entry file → `Entry`, plus the canonical rendering — design 'Entry grammar'.

Strict about the frontmatter, forgiving in the body (Decision 1): a typing
mistake mid-session costs a flag rather than a parse failure, and no
hand-computed value is ever demanded of the author (1.7).

Parsing is **total** (5.2): every byte string yields either an `Entry` or an
`EntryRejection` naming the file. Nothing here raises, and nothing here returns
a half-built entry.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from dawmans.triage.model import (
    Cause,
    DeviceRef,
    Entry,
    EntryRejection,
    Flag,
    Pointer,
    RejectionReason,
)
from dawmans.triage.pointers import parse_pointer

MIN_CAUSES = 2
MAX_CAUSES = 6
"""1.4's band. A list longer than six is a reference chapter, not a triage order."""

KNOWN_FRONTMATTER_KEYS = frozenset({"devices"})

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")

_KEYED_RE = re.compile(
    r"^[\s>#*-]*"  # bullets, quote markers, emphasis, hashes
    r"(?P<key>check|fix|undocumented|also|why)"
    r"\**\s*:\s*\**\s*"  # the colon, tolerating bold either side
    r"(?P<value>.*)$",
    re.IGNORECASE,
)
"""`**Check:**`, `- check :` and `CHECK:` are one line (design 'Entry grammar')."""

SINGLE_LINE_KEYS = frozenset({"fix", "undocumented", "also"})
"""Keys whose value never continues onto the next line (Decision 7).

`check:` and `why:` are free text and wrap as an author writes them. A pointer,
a device name and a `;`-separated phrasing list are each complete on their own
line, so prose written under one is prose, not part of the value.
"""


@dataclass(frozen=True)
class ParseResult:
    """Exactly one of `entry` and `rejection` is set."""

    entry: Entry | None
    rejection: EntryRejection | None
    flags: list[Flag]


@dataclass
class _Section:
    """One `##` section, before the closing-statement rule has been applied."""

    statement: str
    line: int
    check: str | None = None
    fixes: list[Pointer] = field(default_factory=list)
    undocumented: str | None = None
    notes: list[str] = field(default_factory=list)
    has_fix_line: bool = False
    has_undocumented_line: bool = False
    unreadable_fixes: list[str] = field(default_factory=list)

    @property
    def is_closing(self) -> bool:
        """Neither a check nor a fix line — the closing statement's shape (Decision 6)."""
        return self.check is None and not self.has_fix_line and not self.has_undocumented_line


def parse_entry(source_file: Path, data: bytes) -> ParseResult:
    """Read one entry file. `source_file` is repo-relative and is held stable (3.5)."""
    text = data.decode("utf-8", errors="replace")
    if text.startswith("﻿"):
        text = text[1:]
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")

    def reject(reason: RejectionReason, detail: str, **named: str | None) -> ParseResult:
        return ParseResult(
            entry=None,
            rejection=EntryRejection(
                reason=reason, source_file=source_file, detail=detail, **named
            ),
            flags=[],
        )

    front, body_start, failure = _read_frontmatter(lines)
    if failure is not None:
        return reject(*failure)

    devices, failure = _read_devices(front)
    if failure is not None:
        return reject(*failure)

    flags = [
        Flag(
            name="unknown-frontmatter-key",
            source_file=source_file,
            detail=f'the frontmatter key "{key}" is not one this entry format reads',
        )
        for key in sorted(set(front) - KNOWN_FRONTMATTER_KEYS)
    ]

    symptom, symptom_line, phrasings, preamble, sections = _read_body(lines, body_start)
    if symptom is None:
        return reject(
            "no-symptom",
            "an entry needs exactly one `# ` heading, which is its symptom. "
            f"This file has {sum(1 for line in lines[body_start:] if _heading_level(line) == 1)}.",
        )

    closing = None
    if sections and sections[-1].is_closing:
        last = sections.pop()
        closing = "\n".join([last.statement, *last.notes]).strip()
        flags.append(
            Flag(
                name="closing-statement-inferred",
                source_file=source_file,
                symptom=symptom,
                detail=(
                    f'the final section "{last.statement}" carries neither a check nor a fix, '
                    "so it is read as a closing statement rather than a cause"
                ),
            )
        )

    if len(sections) < MIN_CAUSES:
        return reject(
            "too-few-causes",
            f"an entry needs at least {MIN_CAUSES} candidate causes and this one has "
            f"{len(sections)}. Add a cause, or give the last section a check and a fix.",
            symptom=symptom,
        )
    if len(sections) > MAX_CAUSES:
        return reject(
            "too-many-causes",
            f"an entry may declare at most {MAX_CAUSES} candidate causes and this one has "
            f"{len(sections)}. A longer list is a reference chapter, not a triage order.",
            symptom=symptom,
        )

    for position, section in enumerate(sections, start=1):
        failure = _check_cause(position, section)
        if failure is not None:
            reason, detail = failure
            return reject(reason, detail, symptom=symptom, cause=section.statement)

    entry = Entry(
        symptom=symptom,
        phrasings=phrasings,
        preamble=preamble,
        devices=devices,
        causes=[
            Cause(
                statement=section.statement,
                check=section.check or "",
                notes="\n".join(section.notes).strip(),
                fixes=section.fixes,
                undocumented_device=section.undocumented,
            )
            for section in sections
        ],
        closing=closing,
        source_file=source_file,
        line=symptom_line,
    )
    return ParseResult(entry=entry, rejection=None, flags=flags)


def render(entry: Entry) -> str:
    """The canonical rendering — the text that is hashed and the text the user sees.

    There is no second canonical form (design §Identity). Excluded, each
    deliberately: the frontmatter, so adding a device does not orphan the
    entry's history; the fix pointers, so retargeting after a renumbering does
    not either; the file's name and path (1.8); and authoring cosmetics, which
    the parser has already normalised.
    """
    blocks: list[str] = []

    head = [entry.symptom]
    if entry.phrasings:
        head.append("also: " + "; ".join(entry.phrasings))
    if entry.preamble:
        head.append(entry.preamble)
    blocks.append("\n".join(head))

    for cause in entry.causes:
        block = [cause.statement, f"check: {cause.check}"]
        if cause.notes:
            block.append(cause.notes)
        blocks.append("\n".join(block))

    if entry.closing:
        blocks.append(entry.closing)

    return "\n\n".join(blocks)


# --- Frontmatter ----------------------------------------------------------


def _read_frontmatter(
    lines: list[str],
) -> tuple[dict, int, tuple[RejectionReason, str] | None]:
    """Return the frontmatter mapping and the line index the body starts at."""
    if not lines or lines[0].strip() != "---":
        return (
            {},
            0,
            (
                "frontmatter-missing",
                "an entry starts with a `---` fence at the very first line, holding at least "
                "`devices:`. Add one above the symptom heading.",
            ),
        )

    closing = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if closing is None:
        return (
            {},
            0,
            (
                "frontmatter-malformed",
                "the frontmatter opens with `---` but never closes. Add a `---` line below "
                "`devices:`.",
            ),
        )

    try:
        front = yaml.safe_load("\n".join(lines[1:closing]))
    except Exception as error:  # a total parser: no YAML input may raise out of here
        return ({}, 0, ("frontmatter-malformed", f"the frontmatter is not readable YAML: {error}"))

    if front is None:
        front = {}
    if not isinstance(front, dict):
        return (
            {},
            0,
            (
                "frontmatter-malformed",
                "the frontmatter must be a block of `key: value` lines, not a bare list or value.",
            ),
        )
    return front, closing + 1, None


def _read_devices(front: dict) -> tuple[list[DeviceRef], tuple[RejectionReason, str] | None]:
    """`devices` is required, a YAML list, and non-empty (4.1)."""
    if "devices" not in front or front["devices"] is None:
        return (
            [],
            (
                "no-devices",
                "the frontmatter has no `devices:`. Name the devices and software this entry "
                "applies to, as a list.",
            ),
        )

    raw = front["devices"]
    if not isinstance(raw, list):
        return (
            [],
            (
                "devices-not-a-list",
                "`devices:` must be a YAML list — `devices: [ableton/live-12]`. Written as a "
                "bare value it reads as a single string and iterates as characters.",
            ),
        )
    if not raw:
        return (
            [],
            (
                "no-devices",
                "`devices:` is empty. Name at least one device or software this entry applies to.",
            ),
        )
    if any(not isinstance(item, str) for item in raw):
        return (
            [],
            (
                "devices-not-a-list",
                "every entry in `devices:` is a `<vendor>/<product>` identity, optionally with "
                "an `@revision` suffix.",
            ),
        )
    return [_device_ref(item) for item in raw], None


def _device_ref(raw: str) -> DeviceRef:
    identity, _, revision = raw.strip().partition("@")
    return DeviceRef(id=identity.strip(), revision=revision.strip() or None)


# --- The body -------------------------------------------------------------


def _heading_level(line: str) -> int:
    match = _HEADING_RE.match(line)
    return len(match.group(1)) if match else 0


def _read_body(
    lines: list[str], start: int
) -> tuple[str | None, int, list[str], str, list[_Section]]:
    """Scan the body into the symptom, the preamble and the `##` sections."""
    if sum(1 for line in lines[start:] if _heading_level(line) == 1) != 1:
        return None, 0, [], "", []

    symptom = ""
    symptom_line = 0
    phrasings: list[str] = []
    preamble: list[str] = []
    sections: list[_Section] = []

    pending_key: str | None = None
    pending_value: list[str] = []
    pending_line = 0

    def flush() -> None:
        nonlocal pending_key, pending_value
        if pending_key is None:
            return
        value = " ".join(part for part in pending_value if part).strip()
        _absorb(pending_key, value, pending_line, sections, phrasings, preamble)
        pending_key, pending_value = None, []

    for offset, line in enumerate(lines[start:]):
        number = start + offset + 1
        heading = _HEADING_RE.match(line)
        level = len(heading.group(1)) if heading else 0

        if level == 1:
            flush()
            symptom, symptom_line = heading.group(2), number
            continue
        if level == 2:
            flush()
            sections.append(_Section(statement=heading.group(2), line=number))
            continue

        keyed = _KEYED_RE.match(line)
        if keyed is not None:
            flush()
            key = keyed.group("key").lower()
            value = keyed.group("value").strip()
            if key in SINGLE_LINE_KEYS:
                _absorb(key, value, number, sections, phrasings, preamble)
                continue
            pending_key = key
            pending_value = [value]
            pending_line = number
            continue

        prose = heading.group(2).strip() if heading else line.strip()
        if not prose:
            flush()
            continue
        if pending_key is not None:
            pending_value.append(prose)
            continue
        if sections:
            sections[-1].notes.append(prose)
        else:
            preamble.append(prose)

    flush()
    return symptom, symptom_line, phrasings, "\n".join(preamble).strip(), sections


def _absorb(
    key: str,
    value: str,
    line: int,
    sections: list[_Section],
    phrasings: list[str],
    preamble: list[str],
) -> None:
    """Place one keyed line, retaining what has no home rather than dropping it."""
    if not sections:
        if key == "also":
            phrasings.extend(part.strip() for part in value.split(";") if part.strip())
        else:
            preamble.append(f"{key}: {value}")
        return

    section = sections[-1]
    if key == "check":
        if section.check is None:
            section.check = value
            return
    elif key == "fix":
        section.has_fix_line = True
        pointer = parse_pointer(value, line)
        if pointer is not None:
            section.fixes.append(pointer)
            return
        section.unreadable_fixes.append(value)
    elif key == "undocumented":
        section.has_undocumented_line = True
        if section.undocumented is None:
            section.undocumented = value
            return

    # `why:`, `also:`, a second `check:` and an unreadable `fix:` are all retained
    # in the passage text, carrying the normalised marker rather than the author's.
    section.notes.append(f"{key}: {value}")


def _check_cause(position: int, section: _Section) -> tuple[RejectionReason, str] | None:
    """1.2 and 2.3, in the order design 'Error Handling' lists them."""
    where = f'cause {position} "{section.statement}"'
    if section.check is None:
        return (
            "cause-missing-check",
            f"{where} has no `check:` line. Give one observation that confirms or eliminates it.",
        )
    if section.has_fix_line and section.has_undocumented_line:
        return (
            "cause-fix-and-undocumented",
            f"{where} carries both a `fix:` and an `undocumented:` line. They are alternatives: "
            "keep the fix, or drop it and name the device that has no manual.",
        )
    if not section.fixes and section.undocumented is None:
        unreadable = ", ".join(f'"{text}"' for text in section.unreadable_fixes)
        if unreadable:
            return (
                "cause-missing-fix",
                f"{where} has a `fix:` line naming neither a section nor a title: {unreadable}. "
                'Write `fix: <source_id> §<number>` or `fix: <source_id> "<title>"`.',
            )
        return (
            "cause-missing-fix",
            f"{where} has no `fix:` line. Point it at the manual section that documents the "
            "control, or name an undocumented device with `undocumented:`.",
        )
    return None
