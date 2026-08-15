"""Citation resolution and the ungrounded rule (3.6, 3.7).

3.6 holds by construction: the turn holds `supplied` — exactly the
passages sent to synthesis, plus any fix passages a narrowing expansion
admitted — and a Citation is assembled only from an entry in it. An
unresolvable marker is stripped from the streamed text (the user is never
shown a dangling reference) and counted. History and state values are
never in `supplied`, which is the structural half of 10.3 and 8.6.

The ungrounded rule is a cheap syntactic proxy for 3.1, evaluated per
body block once the stream completes: no resolved citation AND either a
fact-shaped token — via `dawmans.triage.terms`, reused so the two specs
cannot drift on what counts as a product term — or an ordered-step block,
because an uncited "Click it to re-enable the track" carries no fact
token and is exactly what the user acts on. A prose block that only
orders or eliminates causes over cited facts carries neither, so the
CONTRACTS §8 split holds executably. The stated residual: an uncited
prose block claiming behaviour in entirely lower-case ordinary words
still passes.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any

from dawmans.answer.envelope import Citation
from dawmans.answer.parse import (
    MARKER,
    Block,
    Conflict,
    OrderedStep,
    markers_in,
)
from dawmans.triage import terms

__all__ = [
    "Grounding",
    "build_citation",
    "fact_shaped",
    "ground_turn",
    "is_ungrounded",
    "markers_in",
    "strip_unknown",
]

# A menu path — a token sequence separated by `>` or `→` — is the third
# fact-shaped class; the other two come from dawmans.triage.terms.
_MENU_PATH = re.compile(r"\S+\s*(?:>|→)\s*\S+")


def strip_unknown(text: str, supplied: Mapping[str, Any]) -> tuple[str, int]:
    """Text with every marker that does not resolve removed, and the count."""
    stripped = 0

    def _keep(match: re.Match[str]) -> str:
        nonlocal stripped
        if match.group(1) in supplied:
            return match.group(0)
        stripped += 1
        return ""

    cleaned = MARKER.sub(_keep, text)
    return re.sub(r"\s{2,}", " ", cleaned).strip(), stripped


def build_citation(
    passage: Mapping[str, Any],
    source: Mapping[str, Any],
    *,
    unbacked_for_turn: bool = False,
) -> Citation:
    """The 3.2/3.3/3.8 field copy. Absent stays absent — a pageless
    source's section, page and doc_version are None, never synthesised.

    `unbacked_for_turn` is 7.6's per-turn reading: a cause whose
    fix_cites[] came out empty carries the mark on its citation without
    the passage record ever being touched (Decision 10).
    """
    return Citation(
        passage_id=passage["passage_id"],
        source_id=passage["source_id"],
        display_name=source["display_name"],
        kind=source["kind"],
        hardware_applicability=source["hardware_applicability"]["status"],
        doc_version=source.get("doc_version"),
        section_number=passage.get("section_number"),
        section_title=passage.get("section_title"),
        page=passage.get("page_start"),
        entry_location=passage.get("entry_location"),
        unbacked=bool(passage.get("unbacked", False)) or unbacked_for_turn,
        degraded=bool(passage.get("degraded", False)),
        has_figures=bool(passage.get("has_figures", False)),
    )


def fact_shaped(text: str) -> bool:
    """Arm (a): a numeric literal, a run of two or more Capitalised or
    ALL-CAPS tokens, or a menu path.

    A block with no letter in it states nothing and is never fact-shaped.
    That is not a softening of the rule: a claim about a product is made in
    words, and `2.` on a line of its own is a list marker. Without this,
    every heading a model numbers `## 2.` tripped arm (a) on the bare
    numeral, and the turn-level flag — which the surface shows as a warning
    that the answer may be unsupported — was raised on all five starter
    symptoms, on answers whose every prose block was cited. A warning that
    fires on every answer tells the user nothing.
    """
    if not any(character.isalpha() for character in text):
        return False
    if any(len(run.split()) >= 2 for run in terms.capitalised_runs(text)):
        return True
    if terms.numeric_literals(text):
        return True
    return bool(_MENU_PATH.search(text))


def is_ungrounded(block: Block, supplied: Mapping[str, Any]) -> bool:
    """The 3.7 rule for one block: no resolved citation AND (fact-shaped
    or an ordered step)."""
    if any(marker in supplied for marker in block.markers):
        return False
    if isinstance(block, OrderedStep):
        return True
    return fact_shaped(MARKER.sub("", block.text))


@dataclass(frozen=True)
class Grounding:
    """One turn's output after marker resolution.

    `citations` is in first-appearance order — direct_answer first, then
    blocks — deduped, every member resolving to a supplied passage.
    """

    direct_answer: str | None
    body: tuple[Block, ...]
    citations: tuple[Citation, ...]
    stripped: int  # unresolvable markers removed from the streamed text
    ungrounded: bool  # emitted after the last body delta, never deferred


def _clean_block(block: Block, supplied: Mapping[str, Any]) -> tuple[Block, int]:
    if isinstance(block, Conflict):
        stripped = 0
        readings = []
        for reading in block.readings:
            text, count = strip_unknown(reading.text, supplied)
            stripped += count
            readings.append(replace(reading, text=text, markers=markers_in(text)))
        lead, count = strip_unknown(block.text, supplied)
        stripped += count
        markers = markers_in(lead) + tuple(
            marker for reading in readings for marker in reading.markers
        )
        return replace(block, text=lead, readings=tuple(readings), markers=markers), stripped
    text, stripped = strip_unknown(block.text, supplied)
    return replace(block, text=text, markers=markers_in(text)), stripped


def ground_turn(
    direct_answer: str | None,
    blocks: Sequence[Block],
    supplied: Mapping[str, Mapping[str, Any]],
    sources_by_id: Mapping[str, Mapping[str, Any]],
) -> Grounding:
    """Resolve one turn's markers against `supplied` and assemble its
    citations. Only the output stream is scanned: text that entered the
    prompt as history or state has no path into `citations[]`."""
    stripped = 0
    cited: dict[str, None] = {}

    cleaned_answer = None
    if direct_answer is not None:
        cited.update(dict.fromkeys(m for m in markers_in(direct_answer) if m in supplied))
        cleaned_answer, count = strip_unknown(direct_answer, supplied)
        stripped += count

    cleaned_blocks: list[Block] = []
    for block in blocks:
        cleaned, count = _clean_block(block, supplied)
        stripped += count
        cited.update(dict.fromkeys(cleaned.markers))
        cleaned_blocks.append(cleaned)

    citations = tuple(
        build_citation(supplied[pid], sources_by_id[supplied[pid]["source_id"]]) for pid in cited
    )
    return Grounding(
        direct_answer=cleaned_answer,
        body=tuple(cleaned_blocks),
        citations=citations,
        stripped=stripped,
        ungrounded=any(is_ungrounded(block, supplied) for block in cleaned_blocks),
    )
