"""Prompt assembly and the history budget (design §Answer shape, Decision 8).

Cache ordering is the contract under test: the static system prompt is the
cache prefix, and passages, history and question follow in that order in
the varying half. History is counted locally with an injected tokeniser —
no provider SDK call occurs before stream() — and the narrowing counter is
carried into assembly, because without that carriage 7.5 has no mechanism.
"""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from dawmans.answer.prompt import (
    HISTORY_MARGIN,
    HISTORY_TOKEN_BUDGET,
    SYSTEM_PROMPT,
    assemble,
    bounded_history,
)

LIVE = "ableton/live-12"
TRIAGE = "authored/triage"

SOURCES = {
    LIVE: {"source_id": LIVE, "kind": "vendor-manual", "display_name": "Live 12 manual"},
    TRIAGE: {"source_id": TRIAGE, "kind": "authored-triage", "display_name": "Triage notes"},
}

PASSAGES = [
    {"passage_id": f"{LIVE}#a1", "source_id": LIVE,
     "text": "The Track Activator mutes the track output"},
    {"passage_id": f"{TRIAGE}#t1", "source_id": TRIAGE,
     "text": "No sound from a track although the meters move"},
]

NOW = datetime(2026, 8, 15, 12, 0, 0, tzinfo=UTC)


def count_words(text):
    return len(text.split())


def assembled(**overrides):
    kwargs = {
        "question": "Why is track 3 silent?",
        "passages": PASSAGES,
        "sources_by_id": SOURCES,
        "count_tokens": count_words,
        "now": NOW,
    }
    kwargs.update(overrides)
    return assemble(**kwargs)


def state_value(key, value, *, age_s=1.0, origin_kind="live"):
    return SimpleNamespace(
        key=key,
        value=value,
        observed_at=NOW - timedelta(seconds=age_s),
        origin="test-source",
        origin_kind=origin_kind,
    )


class TestSystemPrompt:
    """The static prefix carries the framing spec and every standing rule."""

    def test_declares_the_framing_and_the_seven_content_outcomes(self):
        assert "dawmans/answer-framing/1" in SYSTEM_PROMPT
        for outcome in (
            "answered", "partially-answered", "needs-narrowing", "ranked-causes",
            "refused-not-covered", "out-of-domain", "no-manual-for-device",
        ):
            assert outcome in SYSTEM_PROMPT

    def test_carries_the_grounding_rule_with_the_facts_versus_reasoning_split(self):
        # 2.6 / CONTRACTS §8: facts are cited without exception; choosing
        # which documented control to check is reasoning over cited facts
        # and must not be forbidden by the same sentence.
        assert "citation" in SYSTEM_PROMPT
        assert "reasoning" in SYSTEM_PROMPT

    def test_carries_the_length_caps_and_the_procedure_rule(self):
        assert "400" in SYSTEM_PROMPT  # 1.6
        assert "25" in SYSTEM_PROMPT  # 1.9
        assert "ordered steps" in SYSTEM_PROMPT  # 1.5

    def test_carries_every_sigil_and_both_inline_forms(self):
        for token in ("~uncovered", "?narrow", "?cause", "@device",
                      "!suggest", "!caveat", "!conflict", "[[p:"):
            assert token in SYSTEM_PROMPT
        assert "backtick" in SYSTEM_PROMPT

    def test_carries_the_edition_caveat_direction(self):
        # 1.12: Live 12 Standard — a Suite-only or Max for Live
        # recommendation is flagged in reading position.
        assert "Suite" in SYSTEM_PROMPT
        assert "Max for Live" in SYSTEM_PROMPT

    def test_carries_the_kind_trust_split(self):
        # 1.13 / CONTRACTS §4a: vendor-manual for what a control is and
        # does, authored-triage for which control to check and in what order.
        assert "vendor-manual" in SYSTEM_PROMPT
        assert "authored-triage" in SYSTEM_PROMPT

    def test_refusal_is_directed_without_speculation(self):
        assert "speculat" in SYSTEM_PROMPT  # 2.1

    def test_out_of_domain_is_a_responsiveness_test_with_the_entry_carve_out(self):
        # 2.8/2.9: responsive to intent, not topically similar; an authored
        # entry that covers the question means never out-of-domain.
        assert "responsive" in SYSTEM_PROMPT
        assert "never out-of-domain" in SYSTEM_PROMPT

    def test_suggestions_are_forbidden_outright_on_out_of_domain(self):
        # 2.9 suppresses 2.3 at the prompt, not at the parser.
        assert "On out-of-domain, emit no !suggest lines" in SYSTEM_PROMPT

    def test_the_no_xml_instruction_is_present(self):
        assert "Do not include internal or system XML tags" in SYSTEM_PROMPT

    def test_no_do_not_think_instruction_anywhere(self):
        # Design §Answer shape: a "do not think"/"do not reason"
        # instruction measurably worsens the tag leak.
        lowered = SYSTEM_PROMPT.casefold()
        for phrase in ("do not think", "don't think", "do not reason", "don't reason"):
            assert phrase not in lowered


class TestCacheOrdering:
    """System (cached) → passages → history → question."""

    def test_system_is_the_static_prompt_verbatim(self):
        assert assembled().system is SYSTEM_PROMPT

    def test_passages_precede_history_precede_question(self):
        prompt = assembled(history=("Q: earlier question\nA: earlier answer",))
        passages_at = prompt.user.index(PASSAGES[0]["passage_id"])
        history_at = prompt.user.index("earlier question")
        question_at = prompt.user.index("Why is track 3 silent?")
        assert passages_at < history_at < question_at

    def test_passages_carry_their_markers_and_source_kind(self):
        prompt = assembled()
        assert f"[[p:{LIVE}#a1]]" in prompt.user
        assert "vendor-manual" in prompt.user
        assert "authored-triage" in prompt.user


class TestRoster:
    """2.3–2.5: the unselected-source roster is metadata only, so 2.4
    holds by construction — no passage content exists to be quoted."""

    def test_roster_carries_the_four_fields(self):
        roster = [{
            "source_id": "akai/apc-key-25",
            "display_name": "APC Key 25 guide",
            "product": "apc-key-25",
            "kind": "vendor-manual",
        }]
        prompt = assembled(roster=roster)
        for value in ("akai/apc-key-25", "APC Key 25 guide", "apc-key-25", "vendor-manual"):
            assert value in prompt.user

    def test_roster_is_metadata_only(self):
        # A record arriving with content-bearing fields sheds them: the
        # roster is source_id, display_name, product, kind and nothing else.
        roster = [{
            "source_id": "akai/apc-key-25",
            "display_name": "APC Key 25 guide",
            "product": "apc-key-25",
            "kind": "vendor-manual",
            "text": "SENTINEL-PASSAGE-CONTENT",
            "page_count": 5,
        }]
        prompt = assembled(roster=roster)
        assert "SENTINEL-PASSAGE-CONTENT" not in prompt.user

    def test_no_roster_block_when_every_source_is_selected(self):
        assert "Unselected sources" not in assembled().user


class TestHistory:
    """10.3 and 10.8: history is uncitable context, bounded locally."""

    def test_history_enters_in_a_block_marked_uncitable(self):
        prompt = assembled(history=("Q: earlier question\nA: earlier answer",))
        history_block = prompt.user[prompt.user.index("History"):]
        assert "not citable" in history_block

    def test_no_history_block_without_history(self):
        assert "History" not in assembled().user

    def test_budget_drops_oldest_first(self):
        # Ten turns of 100 tokens against 800 × (1 − 10%) = 720: the newest
        # seven fit, the oldest three drop.
        history = tuple(f"turn-{n} " + "word " * 99 for n in range(10))
        kept = bounded_history(history, count_words)
        assert kept == history[3:]

    def test_budget_keeps_original_order(self):
        history = ("oldest " * 10, "middle " * 10, "newest " * 10)
        assert bounded_history(history, count_words) == history

    def test_a_single_over_budget_turn_is_dropped_not_kept(self):
        over = "word " * (HISTORY_TOKEN_BUDGET * 2)
        assert bounded_history((over,), count_words) == ()

    def test_the_margin_is_ten_percent_of_the_budget(self):
        # Decision 8: the resident tokeniser under-counts against the
        # provider's, so the 800 is enforced at 720.
        assert HISTORY_TOKEN_BUDGET == 800
        assert HISTORY_MARGIN == 0.10
        exactly_at_margin = "word " * 720
        one_past = "word " * 721
        assert bounded_history((exactly_at_margin,), count_words) == (exactly_at_margin,)
        assert bounded_history((one_past,), count_words) == ()


class TestStateBlock:
    """8.5–8.7, 8.10: a separate labelled block with origin and age."""

    def test_values_carry_origin_and_age(self):
        prompt = assembled(state=SimpleNamespace(
            values=(state_value("track.3.monitor", "off", age_s=2.0),), acquired_at=NOW
        ))
        assert "track.3.monitor" in prompt.user
        assert "test-source" in prompt.user
        assert "2" in prompt.user[prompt.user.index("track.3.monitor"):]

    def test_state_is_separate_from_history(self):
        prompt = assembled(
            history=("Q: earlier question\nA: earlier answer",),
            state=SimpleNamespace(values=(state_value("audio.device", "Scarlett"),), acquired_at=NOW),
        )
        assert prompt.user.index("Session state") != prompt.user.index("History")

    def test_staleness_direction_for_saved_file_origin(self):
        prompt = assembled(state=SimpleNamespace(
            values=(state_value("track.3.monitor", "off", origin_kind="saved-file"),),
            acquired_at=NOW,
        ))
        assert "may not reflect the current project" in prompt.user

    def test_staleness_direction_for_values_older_than_60s(self):
        prompt = assembled(state=SimpleNamespace(
            values=(state_value("track.3.monitor", "off", age_s=61.0),), acquired_at=NOW
        ))
        assert "may not reflect the current project" in prompt.user

    def test_no_staleness_direction_for_fresh_live_values(self):
        prompt = assembled(state=SimpleNamespace(
            values=(state_value("track.3.monitor", "off", age_s=2.0),), acquired_at=NOW
        ))
        assert "may not reflect the current project" not in prompt.user

    def test_conflict_direction_marks_the_state_side_uncited(self):
        # 8.10: state versus manual is a !conflict with the state side
        # attributed to session state and carrying no citation marker.
        prompt = assembled(state=SimpleNamespace(
            values=(state_value("track.3.monitor", "off"),), acquired_at=NOW
        ))
        state_block = prompt.user[prompt.user.index("Session state"):]
        assert "!conflict" in state_block
        assert "no citation" in state_block

    def test_no_state_block_without_state(self):
        assert "Session state" not in assembled().user


class TestNarrowingCounter:
    """7.5: at the limit the prompt forbids ?narrow and directs the
    terminal form — without this carriage the counter is inert."""

    def test_at_the_limit_narrow_is_forbidden_and_ranked_causes_directed(self):
        prompt = assembled(narrowing_count=2)
        assert "Do not emit ?narrow" in prompt.user
        assert "ranked-causes" in prompt.user

    def test_below_the_limit_no_terminal_direction(self):
        for count in (0, 1):
            assert "Do not emit ?narrow" not in assembled(narrowing_count=count).user
