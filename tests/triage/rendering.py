"""Test support: build entry files from the model, and generate them.

Generators produce the entry **model** and render it to Markdown rather than
generating Markdown text, per design 'Testing Strategy': the reverse direction
cannot state what the expected parse is.
"""

from __future__ import annotations

import string
from dataclasses import dataclass, field

from hypothesis import strategies as st


@dataclass
class Section:
    """One `##` section as an author would write it.

    `check` or `fixes` may be empty, which is how a section becomes a closing
    statement (Decision 6) or a rejection.
    """

    statement: str
    check: str | None = None
    fixes: list[str] = field(default_factory=list)
    undocumented: str | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def is_closing(self) -> bool:
        """The design's rule, applied by the author's intent rather than by position."""
        return self.check is None and not self.fixes and self.undocumented is None


def render_section(section: Section) -> str:
    lines = [f"## {section.statement}"]
    if section.check is not None:
        lines.append(f"check: {section.check}")
    for fix in section.fixes:
        lines.append(f"fix: {fix}")
    if section.undocumented is not None:
        lines.append(f"undocumented: {section.undocumented}")
    lines.extend(section.notes)
    return "\n".join(lines)


def entry_file(
    *,
    devices: list[str],
    symptom: str,
    sections: list[Section],
    phrasings: list[str] | None = None,
    preamble: list[str] | None = None,
    frontmatter_extra: dict[str, str] | None = None,
    bom: bool = False,
) -> str:
    """Render a well-formed entry file. Malformed cases are written out literally."""
    front = [f"devices: [{', '.join(devices)}]"]
    for key, value in (frontmatter_extra or {}).items():
        front.append(f"{key}: {value}")

    body = [f"# {symptom}"]
    if phrasings:
        body.append(f"also: {'; '.join(phrasings)}")
    body.extend(preamble or [])
    for section in sections:
        body.append("")
        body.append(render_section(section))

    text = "---\n" + "\n".join(front) + "\n---\n\n" + "\n".join(body) + "\n"
    return ("﻿" + text) if bom else text


# --- Strategies -----------------------------------------------------------

_SAFE = string.ascii_letters + string.digits + " "

prose = st.text(alphabet=_SAFE, min_size=1, max_size=24).map(str.strip).filter(bool)
"""Text with no Markdown, no `:` and no `;`, so a round trip is about the grammar."""

device_ids = st.sampled_from(
    ["ableton/live-12", "akai/apc-key-25", "alesis/nitro-max", "focusrite/scarlett-solo"]
)

pointer_text = st.sampled_from(
    ["ableton/live-12 §16.4", 'akai/apc-key-25 "Shift Functions"', "alesis/nitro-max §3.1"]
)


@st.composite
def sections(draw: st.DrawFn, *, allow_degenerate: bool = False) -> Section:
    """A cause, or — when `allow_degenerate` — a section missing its check and fix."""
    statement = draw(prose)
    if allow_degenerate and draw(st.booleans()):
        return Section(statement=statement, notes=draw(st.lists(prose, max_size=2)))
    return Section(
        statement=statement,
        check=draw(prose),
        fixes=draw(st.lists(pointer_text, min_size=1, max_size=2)),
        notes=draw(st.lists(prose, max_size=2)),
    )


@st.composite
def entry_files(draw: st.DrawFn, *, allow_degenerate: bool = False) -> tuple[str, int]:
    """An entry file and the number of `##` sections it contains."""
    section_list = draw(
        st.lists(sections(allow_degenerate=allow_degenerate), min_size=1, max_size=7)
    )
    text = entry_file(
        devices=draw(st.lists(device_ids, min_size=1, max_size=3, unique=True)),
        symptom=draw(prose),
        sections=section_list,
        phrasings=draw(st.lists(prose, max_size=3)),
        preamble=draw(st.lists(prose, max_size=2)),
    )
    return text, len(section_list)
