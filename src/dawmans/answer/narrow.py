"""Triage sidecar to ranked candidates and fix expansion (7.2, 7.6).

The entry path is engine-built (Decision 9): where retrieval admits an
`authored-triage` passage, the candidate list and the terminal `causes[]`
come from that entry's causes in the entry's own order — label from `check`,
value from `statement` — and the model is not asked for candidates at all.
The `?narrow` and `?cause` sigils exist only for the no-entry fallback,
which lives in the prompt and parser, not here.

Fix pointers are resolved against the view and filtered through the turn's
source scope (Decision 10): a fix whose passage lies outside the selected
set is never admitted to `supplied`; its cause is carried as unbacked *for
this turn* and the holding source is named through 2.3's suggestion path.
The expansion bound is over resolved passages, not pointers — one section
pointer yields every chunk that section produced — and excess drops in
cause order, within a cause in section order, so the highest-ranked cause
keeps its first chunk before any lower cause is served.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from dawmans.answer.envelope import Cause, Narrowing, NarrowingCandidate
from dawmans.answer.retrieve import DEFAULT_CONFIG
from dawmans.answer.scope import device_scope, in_device_scope
from dawmans.answer.view import CorpusView

# 7.2 fixes the candidate band: a narrowing question offers between 2 and 4
# concrete candidates, and `causes[]` carries at most 4 (7.6).
NARROWING_MIN = 2
CAUSES_MAX = 4


def matched_entry(view: CorpusView, supplied_ids: Iterable[str]) -> Mapping[str, Any] | None:
    """The first supplied passage that keys the sidecar, in supplied order.

    `supplied` arrives in fused rank order, so where several triage entries
    were retrieved the best-ranked one drives the narrowing.
    """
    for passage_id in supplied_ids:
        entry = view.sidecar.get(passage_id)
        if entry is not None:
            return entry
    return None


@dataclass(frozen=True)
class CauseExpansion:
    """One taken cause with its fix resolution under the turn's scope."""

    statement: str
    check: str
    fix_in_scope: tuple[str, ...]  # resolved and in scope, section order
    fix_cites: tuple[str, ...]  # the subset that resolves into citations[]
    out_of_scope_sources: tuple[str, ...]  # holding sources the scope excluded

    @property
    def unbacked_for_turn(self) -> bool:
        """Empty `fix_cites` — unnamed, out of scope, or cap-dropped —
        means the cause's citation carries the unbacked mark this turn.
        The engine reads the authored flag and never sets it; this is a
        per-turn reading, not a mutation of the entry (Decision 10)."""
        return not self.fix_cites


@dataclass(frozen=True)
class EntryExpansion:
    """A matched entry's first ≤4 causes, expanded and scope-filtered."""

    passage_id: str
    symptom: str
    causes: tuple[CauseExpansion, ...]  # entry order, never resorted
    admitted: tuple[str, ...]  # fix passages to add to supplied, bounded
    suggested_source_ids: tuple[str, ...]  # for 2.3's suggestion path


def expand_entry(
    view: CorpusView,
    passage_id: str,
    selected_source_ids: Iterable[str],
    *,
    already_supplied: Iterable[str] = (),
    cap: int = DEFAULT_CONFIG.narrowing_cap,
) -> EntryExpansion | None:
    """Steps 1–4 of design §Narrowing: sidecar lookup, the first 2–4 causes,
    and scope-filtered fix expansion under the turn's passage cap.

    `already_supplied` is what retrieval already put in the turn; it counts
    against `cap` and is cited without being re-admitted.
    """
    entry = view.sidecar.get(passage_id)
    if entry is None:
        return None

    selected = frozenset(selected_source_ids)
    scope = device_scope(view, selected)
    supplied = set(already_supplied)
    budget = max(0, cap - len(supplied))

    admitted: list[str] = []
    causes: list[CauseExpansion] = []
    suggested: dict[str, None] = {}
    for member in entry["causes"][:CAUSES_MAX]:
        in_scope: list[str] = []
        out_sources: dict[str, None] = {}
        for pointer in member["fix"]:
            if pointer["source_id"] not in selected:
                out_sources[pointer["source_id"]] = None
                continue
            for fix_id in pointer["passage_ids"]:
                if fix_id in view.passages_by_id and in_device_scope(view, fix_id, scope):
                    in_scope.append(fix_id)

        # Admission in cause order, within a cause in section order — the
        # pointer's passage_ids arrive in section order from the sidecar.
        cites: dict[str, None] = {}
        for fix_id in in_scope:
            if fix_id in supplied or fix_id in admitted:
                cites[fix_id] = None
            elif len(admitted) < budget:
                admitted.append(fix_id)
                cites[fix_id] = None

        causes.append(
            CauseExpansion(
                statement=member["statement"],
                check=member["check"],
                fix_in_scope=tuple(in_scope),
                fix_cites=tuple(cites),
                out_of_scope_sources=tuple(out_sources),
            )
        )
        suggested.update(out_sources)

    return EntryExpansion(
        passage_id=passage_id,
        symptom=entry["symptom"],
        causes=tuple(causes),
        admitted=tuple(admitted),
        suggested_source_ids=tuple(suggested),
    )


def build_narrowing(
    expansion: EntryExpansion,
    *,
    state_supplies: Callable[[NarrowingCandidate], bool] | None = None,
) -> Narrowing | None:
    """The narrowing question, engine-built from the entry (Decision 9).

    A candidate whose value session state already supplies is removed
    (7.8) — executable only because the candidates are engine-built; the
    engine cannot suppress a question the model chose to ask. Fewer than
    two candidates left means no question: 7.2's band is 2–4, and a
    one-candidate question discriminates nothing.
    """
    candidates = tuple(
        NarrowingCandidate(label=member.check, value=member.statement)
        for member in expansion.causes
    )
    if state_supplies is not None:
        candidates = tuple(c for c in candidates if not state_supplies(c))
    if len(candidates) < NARROWING_MIN:
        return None
    return Narrowing(
        question=f'Which of these do you observe for "{expansion.symptom}"?',
        candidates=candidates,
    )


def build_causes(expansion: EntryExpansion) -> tuple[Cause, ...]:
    """The terminal `causes[]` (7.6), engine-built on the entry path.

    The entry's ranking is preserved exactly — nothing reorders, merges,
    adds or drops, and state suppression does not apply: it is a
    narrowing-question concern. `cites[]` is the entry passage itself;
    `fix_cites[]` is what the scope filter and the cap let through, so
    every id resolves into the turn's `citations[]`.
    """
    return tuple(
        Cause(
            rank=position,
            statement=member.statement,
            check=member.check,
            cites=(expansion.passage_id,),
            fix_cites=member.fix_cites,
        )
        for position, member in enumerate(expansion.causes, start=1)
    )
