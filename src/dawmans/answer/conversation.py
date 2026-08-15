"""History, carried scope, the narrowing counter (§10, 7.4, 7.5, 5.11).

Everything here is in-memory per process and discarded on restart (10.7).
A conversation holds no passage text anywhere — retrieval re-runs every
turn (10.2), so 10.5's "passages from now-deselected sources are not
retained" is structural rather than a cache-invalidation discipline.

Follow-up query assembly lives here: a turn answering a narrowing question
retrieves with the original symptom question plus the answer just given
(7.4), never with the previous turn's passages. The per-symptom
consecutive-narrowing counter is the mechanism 7.5 rides on — prompt
assembly carries it into the terminal direction — and it resets on any
content outcome that is an answer, while an engine failure (timeout,
cancelled) neither asks nor answers and leaves it alone.
"""

from __future__ import annotations

from collections.abc import Iterable
from uuid import uuid4

from dawmans.answer.envelope import Outcome, SourceRef
from dawmans.answer.parse import CONTENT_OUTCOMES
from dawmans.answer.view import CorpusView

# 10.1: the last six turns are retained and used to interpret a follow-up.
HISTORY_TURNS = 6


class Conversation:
    """One conversation's state: bounded history, carried scope, counter."""

    def __init__(self, conversation_id: str) -> None:
        self.id = conversation_id
        # (question, answer) pairs, oldest first, content outcomes only.
        self._turns: list[tuple[str, str]] = []
        # source_id -> display_name, in the caller's order. The name is
        # captured when the scope is set because 5.11 reports a *removed*
        # source, which the pruning view can no longer be asked about.
        self._scope: dict[str, str] = {}
        self.narrowing_count = 0
        self._symptom_question: str | None = None
        self._awaiting_narrowing = False

    # -- carried scope (10.4, 10.5, 5.11) --------------------------------

    @property
    def scope(self) -> tuple[str, ...]:
        return tuple(self._scope)

    def set_scope(self, source_ids: Iterable[str], view: CorpusView) -> None:
        """Replace the carried set wholesale — 10.5 retains nothing from a
        now-deselected source, and there is nothing here to retain."""
        self._scope = {
            source_id: str(view.sources_by_id.get(source_id, {}).get("display_name", source_id))
            for source_id in source_ids
        }

    def prune_scope(self, view: CorpusView) -> tuple[SourceRef, ...]:
        """5.11: drop carried sources the corpus no longer holds and report
        them — a turn-time prune the user did not perform is never silent."""
        dropped = tuple(
            SourceRef(source_id=source_id, display_name=display_name)
            for source_id, display_name in self._scope.items()
            if source_id not in view.sources_by_id
        )
        for member in dropped:
            del self._scope[member.source_id]
        return dropped

    # -- follow-up interpretation (10.1, 7.4) ----------------------------

    def history_lines(self) -> tuple[str, ...]:
        """The last six exchanges, oldest first, rendered for the prompt's
        context-only history block (10.3 non-citability is prompt.py's)."""
        return tuple(f"Q: {question}\nA: {answer}" for question, answer in self._turns)

    def retrieval_query(self, question: str) -> str:
        """7.4: answering a narrowing question re-retrieves with the
        original question plus the answer; any other turn with the
        question alone."""
        if self._awaiting_narrowing and self._symptom_question is not None:
            return f"{self._symptom_question} {question}"
        return question

    # -- recording (10.1, 7.5) -------------------------------------------

    def record_turn(self, question: str, outcome: Outcome, answer: str) -> None:
        """Fold one finished turn in. Engine-determined outcomes produced
        no exchange to interpret and are not history; they also neither
        ask nor answer, so the narrowing counter survives them."""
        if outcome.value not in CONTENT_OUTCOMES:
            return
        self._turns.append((question, answer))
        del self._turns[:-HISTORY_TURNS]
        if outcome is Outcome.NEEDS_NARROWING:
            if self.narrowing_count == 0:
                self._symptom_question = question
            self.narrowing_count += 1
            self._awaiting_narrowing = True
        else:
            self.narrowing_count = 0
            self._symptom_question = None
            self._awaiting_narrowing = False


class ConversationStore:
    """In-memory conversations, keyed by id. A fresh store is a restart:
    nothing is persisted, so a stale id simply starts over (10.7)."""

    def __init__(self) -> None:
        self._conversations: dict[str, Conversation] = {}

    def get(self, conversation_id: str | None) -> Conversation:
        """The named conversation, or a new one where the id is null
        (10.6) or unknown — an id from before a restart finds no history."""
        if conversation_id is None:
            conversation_id = uuid4().hex
        held = self._conversations.get(conversation_id)
        if held is None:
            held = Conversation(conversation_id)
            self._conversations[conversation_id] = held
        return held
