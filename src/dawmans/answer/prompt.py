"""System prompt, framing spec, passage and history budget.

Cache ordering is the load-bearing structure (design §Anthropic provider
specifics): the static system prompt is the cache prefix, and everything
that varies per turn — passages, the unselected-source roster, state,
history, question — sits after the breakpoint, in that order.

The history budget is counted locally with the tokeniser already resident
for retrieval (Decision 8): no provider SDK call occurs before stream(),
so a local turn cannot leak by oversight and prompt assembly stays
provider-agnostic. The count is an estimate against the provider's own
tokeniser, so the 800-token budget is enforced with a 10% margin;
count_tokens is reserved for offline `make bench` calibration.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

# 10.8: fixed, self-imposed — not a model limit, so being conservative
# costs a little history and risks nothing.
HISTORY_TOKEN_BUDGET = 800
HISTORY_MARGIN = 0.10

# 8.7: a saved-file origin, or a value older than this, may not reflect
# the current project.
STATE_STALE_AFTER_S = 60.0

# The four fields the roster may carry — metadata only, so 2.4 holds by
# construction: no unselected source's content exists anywhere in the turn.
_ROSTER_FIELDS = ("source_id", "display_name", "product", "kind")

# Design §Answer shape: stated generically, and never accompanied by any
# "do not think" / "do not reason" instruction, which measurably worsens
# the tag leak.
_NO_XML = "Do not include internal or system XML tags in your response."

SYSTEM_PROMPT = f"""\
You answer questions about the user's DAW and hardware from supplied manual passages.

Respond in the format dawmans/answer-framing/1 and no other:
- Line 1: exactly one outcome token, bare: answered, partially-answered, needs-narrowing, \
ranked-causes, refused-not-covered, out-of-domain, or no-manual-for-device.
- Line 2: the direct answer — one line reaching its first actionable instruction within 25 words, \
before any qualification, caveat or restatement.
- Line 3: ---
- After: the body. At most 400 words in total.

Body blocks, each decided by its first character at column 0:
- `## ` heading, `N. ` ordered step, `- ` bullet, blank-line-separated paragraphs.
- `!caveat ` + text (continuations indented two spaces): a recommendation depending on a Live \
edition or add-on the rig lacks. The rig runs Live 12 Standard: flag any Suite-only device or \
Max for Live feature this way, in the reading position it qualifies.
- `!conflict ` + text, then exactly two `- ` reading lines, each with its own citation markers: \
passages that conflict, both readings shown, neither chosen.
- `~uncovered ` + text: one named part of the question the passages do not cover.
- `?narrow ` + the question, then 2-4 `* ` candidate lines: one narrowing question instead of an \
answer, only when the symptom is too vague for a single documented cause and you were not \
given candidate causes.
- `?cause ` + the candidate cause, then a `check: ` line naming the observable that confirms or \
eliminates it: one block per cause, most likely first, only on a ranked-causes turn.
- `@device ` + the device whose documentation would answer the question, on no-manual-for-device.
- `!suggest ` + one unselected source_id from the roster likely to hold the answer, ordered by \
likelihood, at most 3, only on a refusal or partial answer. Emit none when no listed source is a \
plausible holder. On out-of-domain, emit no !suggest lines.

Inline forms, and no others: the citation marker [[p:passage_id]] copied exactly from a supplied \
passage, and a backtick-delimited span for a key term — a key name or combination, a parameter \
name, or a menu path. No other emphasis, no links, no images.

Grounding:
- Facts are cited, without exception. Every statement of product behaviour, setting, value or \
procedure step carries a citation marker from a supplied passage. State no product fact — \
behaviour, parameter name, menu path, key command or numeric value — that no supplied passage \
carries, under any condition, including when asked to.
- Choosing which documented control to check, and in what order, is reasoning over cited facts: \
it is permitted and it is not general knowledge. Every fact the reasoning rests on carries its \
citation.
- A vendor-manual passage is authoritative for what a control is and does. An authored-triage \
passage is authoritative for which documented control to check, and in what order, for a given \
symptom — never present its causal claim as though the manufacturer stated it.
- When the question asks for a procedure, answer as ordered steps, each step cited.
- When the passages do not cover the question, say so plainly and do not speculate: emit \
refused-not-covered rather than an answer built from weak matches.

Outcome choice — judge whether the passages are responsive to the question's intent, not merely \
topically similar to it:
- A question about what a documented control is or does, answered by a passage: answered. \
Supported only in part: partially-answered, with ~uncovered naming the rest.
- The same kind of question with no passage stating the answer: refused-not-covered.
- A question about how to achieve a production outcome — a technique question — where the \
passages share vocabulary but state no cause or procedure for it, and no authored-triage passage \
matches: out-of-domain. A reference manual documents controls, not practice; no ingested manual \
will ever cover it. If an authored-triage passage does cover the question, answer from it — \
never out-of-domain.
- A question answerable from documentation for a device with neither a manual nor an authored \
entry supplied: no-manual-for-device, with @device.

{_NO_XML}
"""


class StateValueLike(Protocol):
    """The StateSource seam's value shape (8.5), duck-typed so prompt
    assembly does not depend on the provider/state modules."""

    key: str
    value: Any
    observed_at: datetime
    origin: str
    origin_kind: str


class StateSnapshotLike(Protocol):
    values: Sequence[StateValueLike]
    acquired_at: datetime


@dataclass(frozen=True)
class AssembledPrompt:
    """system is the cache prefix; user is everything after the breakpoint."""

    system: str
    user: str


def bounded_history(history: Sequence[str], count_tokens: Callable[[str], int]) -> tuple[str, ...]:
    """10.8: oldest turns drop first until the newest fit the budget.

    The budget is enforced at 800 × (1 − 10%): the resident tokeniser is
    not the provider's, and the margin covers the under-count.
    """
    budget = HISTORY_TOKEN_BUDGET * (1 - HISTORY_MARGIN)
    kept: list[str] = []
    spent = 0
    for turn in reversed(history):
        spent += count_tokens(turn)
        if spent > budget:
            break
        kept.append(turn)
    return tuple(reversed(kept))


def _passages_block(
    passages: Sequence[Mapping[str, Any]], sources_by_id: Mapping[str, Mapping[str, Any]]
) -> str:
    lines = ["## Passages", "Cite with the marker exactly as given."]
    for passage in passages:
        source = sources_by_id[passage["source_id"]]
        lines.append(f"\n[[p:{passage['passage_id']}]] {source['display_name']} ({source['kind']})")
        lines.append(passage["text"])
    return "\n".join(lines)


def _roster_block(roster: Sequence[Mapping[str, Any]]) -> str:
    lines = [
        "## Unselected sources",
        (
            "Indexed but not in scope for this turn. Names only — no content. "
            "These are the only valid !suggest targets."
        ),
    ]
    for record in roster:
        fields = {name: record.get(name) for name in _ROSTER_FIELDS}
        lines.append(
            f"- {fields['source_id']} | {fields['display_name']} "
            f"| {fields['product'] or ''} | {fields['kind']}"
        )
    return "\n".join(lines)


def _state_block(state: StateSnapshotLike, now: datetime) -> str:
    lines = [
        "## Session state",
        (
            "Observed values from the user's project — not passages, never citable. "
            "When you use one, attribute it to session state. Where a value contradicts "
            "a passage, report both as a !conflict with the state side attributed to "
            "session state and carrying no citation marker."
        ),
    ]
    stale = False
    for value in state.values:
        age_s = (now - value.observed_at).total_seconds()
        stale = stale or value.origin_kind == "saved-file" or age_s > STATE_STALE_AFTER_S
        lines.append(
            f"- {value.key} = {value.value} "
            f"(origin: {value.origin}, {value.origin_kind}, age: {age_s:.0f}s)"
        )
    if stale:
        # 8.7: emitted by the model as a !caveat in the answer.
        lines.append(
            "Some values are from a saved file or older than 60 s: state in the answer, "
            "as a !caveat, that they may not reflect the current project."
        )
    return "\n".join(lines)


# 7.5: carried into assembly rather than merely recorded — the outcome is
# model-chosen, so nothing else in the design can stop a third question.
_TERMINAL_DIRECTION = (
    "## Narrowing limit reached\n"
    "Two narrowing questions have already been asked for this symptom. "
    "Do not emit ?narrow. If the cause is still ambiguous, emit ranked-causes with "
    "one ?cause block per candidate, most likely first. On ranked-causes, line 2 "
    "states the most likely cause's check as an instruction to perform — never "
    "assert the cause itself."
)

NARROWING_LIMIT = 2


def assemble(
    question: str,
    passages: Sequence[Mapping[str, Any]],
    sources_by_id: Mapping[str, Mapping[str, Any]],
    *,
    roster: Sequence[Mapping[str, Any]] = (),
    history: Sequence[str] = (),
    state: StateSnapshotLike | None = None,
    narrowing_count: int = 0,
    count_tokens: Callable[[str], int],
    now: datetime | None = None,
) -> AssembledPrompt:
    """One turn's prompt: static system, then passages → roster → state →
    history → question. Only the passages-before-history-before-question
    ordering is contractual (the cache layout); the middle blocks sit with
    the varying content because every one of them varies per turn."""
    now = now if now is not None else datetime.now(UTC)
    blocks = [_passages_block(passages, sources_by_id)]
    if roster:
        blocks.append(_roster_block(roster))
    if state is not None and state.values:
        blocks.append(_state_block(state, now))
    kept = bounded_history(history, count_tokens)
    if kept:
        blocks.append(
            "## History (context only — not citable)\n"
            "Earlier turns, oldest first. Use them to interpret the question. "
            "No statement here is a citable fact and none carries a marker.\n\n" + "\n\n".join(kept)
        )
    if narrowing_count >= NARROWING_LIMIT:
        blocks.append(_TERMINAL_DIRECTION)
    blocks.append(f"## Question\n{question}")
    return AssembledPrompt(system=SYSTEM_PROMPT, user="\n\n".join(blocks))
