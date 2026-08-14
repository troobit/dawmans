"""Conversation state (§10, 7.4, 7.5, 5.11).

History, carried scope, the narrowing counter and the corpus-change prune
are all in-memory per process (10.7): a fresh store is a restart, and
nothing here touches disk. The conversation holds no passage text at all —
retrieval re-runs every turn (10.2), so "passages from now-deselected
sources are not retained" (10.5) is structural, and the test asserts the
structure rather than a behaviour that could silently grow a cache.
"""

from corpus_fixtures import make_view, passage, vendor_source

from dawmans.answer.conversation import (
    HISTORY_TURNS,
    Conversation,
    ConversationStore,
)
from dawmans.answer.envelope import Outcome, SourceRef
from dawmans.answer.outcome import GateState, pre_flight

LIVE = "ableton/live-12"
APC = "akai/apc-key-25"

SOURCES = [
    vendor_source(LIVE, LIVE, page_count=1009),
    vendor_source(APC, APC, page_count=5),
]

PASSAGES = [
    passage(f"{LIVE}#p1", "The Track Activator mutes the track output"),
    passage(f"{APC}#p1", "Hold SHIFT and press a pad to select a scene"),
]

VIEW = make_view(SOURCES, PASSAGES)


def conversation(scope=(LIVE, APC), view=VIEW):
    held = ConversationStore().get(None)
    held.set_scope(scope, view)
    return held


class TestHistory:
    def test_last_six_turns_are_retained_oldest_dropped(self):
        held = conversation()
        for n in range(HISTORY_TURNS + 1):
            held.record_turn(f"question {n}", Outcome.ANSWERED, f"answer {n}")
        lines = held.history_lines()
        assert len(lines) == HISTORY_TURNS == 6
        assert not any("question 0" in line for line in lines)
        assert any("question 1" in line for line in lines)

    def test_history_carries_question_and_answer_for_interpretation(self):
        # 10.1: the lines are what prompt assembly hands the model to
        # interpret a follow-up, so both halves of the exchange are present.
        held = conversation()
        held.record_turn("what does the Track Activator do", Outcome.ANSWERED, "It mutes the track")
        [line] = held.history_lines()
        assert "what does the Track Activator do" in line
        assert "It mutes the track" in line

    def test_engine_failure_turns_do_not_enter_history(self):
        # A timed-out turn produced no answer to interpret; only content
        # outcomes become history.
        held = conversation()
        held.record_turn("a question", Outcome.TIMEOUT, "")
        held.record_turn("a question", Outcome.CANCELLED, "")
        assert held.history_lines() == ()

    def test_conversation_holds_no_passage_state(self):
        # 10.2/10.5 structurally: there is nowhere to retain a passage, so
        # a new turn cannot reuse the previous turn's, changed or unchanged.
        held = conversation()
        held.record_turn("q", Outcome.ANSWERED, "a")
        assert not any("passage" in name for name in vars(held))


class TestStore:
    def test_new_conversation_discards_prior_turns(self):
        # 10.6: null conversation_id starts fresh — distinct identity,
        # empty history, whatever an earlier conversation accumulated.
        store = ConversationStore()
        first = store.get(None)
        first.set_scope((LIVE,), VIEW)
        first.record_turn("q", Outcome.ANSWERED, "a")
        second = store.get(None)
        assert second.id != first.id
        assert second.history_lines() == ()

    def test_known_id_returns_the_same_conversation(self):
        store = ConversationStore()
        held = store.get(None)
        assert store.get(held.id) is held

    def test_fresh_store_is_a_restart_with_nothing_retained(self):
        # 10.7: state is in-memory per process. A stale id arriving after a
        # restart finds no history — the conversation starts over.
        old_store = ConversationStore()
        held = old_store.get(None)
        held.record_turn("q", Outcome.ANSWERED, "a")
        revived = ConversationStore().get(held.id)
        assert revived.history_lines() == ()


class TestCarriedScope:
    def test_scope_persists_until_the_caller_changes_it(self):
        held = conversation(scope=(LIVE,))
        held.record_turn("q", Outcome.ANSWERED, "a")
        assert held.scope == (LIVE,)

    def test_mid_conversation_change_applies_from_the_next_turn(self):
        # 10.5: the new set replaces the old wholesale; the deselected
        # source is gone from the scope the next turn reads.
        held = conversation(scope=(LIVE, APC))
        held.set_scope((APC,), VIEW)
        assert held.scope == (APC,)


class TestFollowUpQuery:
    def test_a_narrowing_answer_retrieves_with_original_plus_answer(self):
        # 7.4: never the previous turn's passages — the query itself is
        # rebuilt from the original question and the answer just given.
        held = conversation()
        held.record_turn("no sound from track 3", Outcome.NEEDS_NARROWING, "Which do you observe?")
        query = held.retrieval_query("the track number is dimmed")
        assert query == "no sound from track 3 the track number is dimmed"

    def test_second_narrowing_answer_still_carries_the_original_question(self):
        held = conversation()
        held.record_turn("no sound from track 3", Outcome.NEEDS_NARROWING, "First question?")
        held.record_turn("neither of those", Outcome.NEEDS_NARROWING, "Second question?")
        query = held.retrieval_query("the meters still move")
        assert query == "no sound from track 3 the meters still move"

    def test_an_ordinary_follow_up_retrieves_with_the_question_alone(self):
        held = conversation()
        held.record_turn("what mutes a track", Outcome.ANSWERED, "The Track Activator")
        assert held.retrieval_query("and the return track?") == "and the return track?"


class TestScopePrune:
    def test_removed_source_drops_from_scope_and_is_reported(self):
        # 5.11: reported through scope_dropped with the display name the
        # scope captured — the removed source is no longer in the view to
        # ask — never applied silently.
        held = conversation(scope=(LIVE, APC))
        shrunk = make_view([SOURCES[0]], [PASSAGES[0]])
        dropped = held.prune_scope(shrunk)
        assert dropped == (SourceRef(source_id=APC, display_name=APC),)
        assert held.scope == (LIVE,)

    def test_prune_with_nothing_removed_reports_nothing(self):
        held = conversation(scope=(LIVE,))
        assert held.prune_scope(VIEW) == ()
        assert held.scope == (LIVE,)

    def test_pruning_the_last_source_yields_no_sources_selected(self):
        # An emptied scope reaches the caller as no-sources-selected via
        # the pre-flight gate, not as a silent all-sources fallback (5.2).
        held = conversation(scope=(APC,))
        shrunk = make_view([SOURCES[0]], [PASSAGES[0]])
        held.prune_scope(shrunk)
        assert held.scope == ()
        gated = pre_flight(GateState(passage_count=1, selected_count=len(held.scope)))
        assert gated is not None
        assert gated.outcome is Outcome.NO_SOURCES_SELECTED


class TestNarrowingCounter:
    def test_counter_increments_across_consecutive_narrowing_turns(self):
        held = conversation()
        assert held.narrowing_count == 0
        held.record_turn("no sound", Outcome.NEEDS_NARROWING, "Which?")
        assert held.narrowing_count == 1
        held.record_turn("neither", Outcome.NEEDS_NARROWING, "Then which?")
        assert held.narrowing_count == 2

    def test_counter_resets_on_an_answer(self):
        # The mechanism 7.5 rides on: prompt assembly reads this counter,
        # and an answer ends the symptom.
        held = conversation()
        held.record_turn("no sound", Outcome.NEEDS_NARROWING, "Which?")
        held.record_turn("the activator", Outcome.ANSWERED, "Turn it back on")
        assert held.narrowing_count == 0
        assert held.retrieval_query("next question") == "next question"

    def test_ranked_causes_is_an_answer_for_the_counter(self):
        held = conversation()
        held.record_turn("no sound", Outcome.NEEDS_NARROWING, "Which?")
        held.record_turn("neither", Outcome.NEEDS_NARROWING, "Then which?")
        held.record_turn("still neither", Outcome.RANKED_CAUSES, "Check the activator first")
        assert held.narrowing_count == 0

    def test_engine_failures_leave_the_counter_alone(self):
        # A timeout mid-symptom neither asks nor answers; the consecutive
        # count survives it.
        held = conversation()
        held.record_turn("no sound", Outcome.NEEDS_NARROWING, "Which?")
        held.record_turn("neither", Outcome.TIMEOUT, "")
        assert held.narrowing_count == 1


def test_conversation_is_not_shared_between_ids():
    store = ConversationStore()
    one, two = store.get(None), store.get(None)
    one.set_scope((LIVE,), VIEW)
    two.set_scope((APC,), VIEW)
    one.record_turn("q", Outcome.NEEDS_NARROWING, "n?")
    assert isinstance(one, Conversation) and isinstance(two, Conversation)
    assert two.narrowing_count == 0
    assert two.scope == (APC,)
