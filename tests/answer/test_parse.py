"""The framing parser (design §Answer shape, Decision 2).

Totality is the headline property: for any byte string, parse() yields a
well-formed result, never raises, and never emits a partial Citation —
the parser emits no Citations at all, only markers for ground.py to
resolve. Line 1 is validated against the seven-member content enum;
anything else is the unparsed path, the honest degradation for a provider
that ignores the framing.
"""

from hypothesis import given
from hypothesis import strategies as st

from dawmans.answer.envelope import Outcome
from dawmans.answer.parse import (
    CONTENT_OUTCOMES,
    Bullet,
    Caveat,
    Conflict,
    Heading,
    OrderedStep,
    Paragraph,
    ParsedAnswer,
    parse,
)

LIVE = "ableton/live-12"
APC = "akai/apc-key-25"
TRIAGE = "authored/triage"

SOURCES = {
    APC: {"source_id": APC, "display_name": "APC Key 25 guide", "kind": "vendor-manual"},
    LIVE: {"source_id": LIVE, "display_name": "Live 12 manual", "kind": "vendor-manual"},
    "alesis/nitro-max": {
        "source_id": "alesis/nitro-max", "display_name": "Nitro Max guide",
        "kind": "vendor-manual",
    },
    "focusrite/scarlett-solo-4g": {
        "source_id": "focusrite/scarlett-solo-4g", "display_name": "Scarlett Solo guide",
        "kind": "vendor-manual",
    },
}

FRAMED = f"""answered
Turn the Track Activator back on — click the dimmed track number. [[p:{LIVE}#a1]]
---
## Why
The `Track Activator` mutes the track's output when off. [[p:{LIVE}#a1]]

1. Look at the mixer for a dimmed track number. [[p:{TRIAGE}#t1]]
2. Click it to re-enable the track. [[p:{LIVE}#a1]]
~uncovered whether direct monitoring is also muted
"""


class TestParserTotality:
    """1.10/1.11: total over bytes."""

    @given(st.binary(max_size=2000))
    def test_any_byte_string_yields_a_well_formed_result(self, data):
        result = parse(data, covered=False)
        assert isinstance(result, ParsedAnswer)
        assert result.outcome in Outcome
        assert result.framing in ("parsed", "unparsed")

    @given(st.text(max_size=2000))
    def test_any_text_yields_a_well_formed_result(self, data):
        result = parse(data, covered=True)
        assert isinstance(result, ParsedAnswer)

    def test_the_empty_stream(self):
        result = parse(b"", covered=False)
        assert result.outcome is Outcome.REFUSED_NOT_COVERED
        assert result.framing == "unparsed"
        assert result.direct_answer is None
        assert result.body == ()


class TestLineOne:
    """The seven-member content enum, and the unparsed path on anything else."""

    def test_the_enum_has_seven_members(self):
        assert len(CONTENT_OUTCOMES) == 7
        assert CONTENT_OUTCOMES == {
            "answered", "partially-answered", "needs-narrowing", "ranked-causes",
            "refused-not-covered", "out-of-domain", "no-manual-for-device",
        }

    def test_a_valid_first_line_is_the_outcome(self):
        result = parse(FRAMED, covered=True)
        assert result.outcome is Outcome.ANSWERED
        assert result.framing == "parsed"

    def test_an_engine_outcome_on_line_one_is_invalid(self):
        # Decision 3: the model can emit no engine-determined member.
        result = parse("timeout\nanswer\n---\nbody", covered=True)
        assert result.framing == "unparsed"
        assert result.outcome is Outcome.ANSWERED  # from coverage, not the line

    def test_unparsed_takes_the_whole_stream_as_body(self):
        stream = "The Track Activator mutes the track.\n\nMore prose here."
        result = parse(stream, covered=True)
        assert result.framing == "unparsed"
        assert len(result.body) == 2
        assert all(isinstance(block, Paragraph) for block in result.body)
        assert "Track Activator mutes" in result.body[0].text

    def test_unparsed_direct_answer_is_the_first_sentence(self):
        result = parse("The Track Activator mutes the track. More prose.", covered=True)
        assert result.direct_answer == "The Track Activator mutes the track."

    def test_unparsed_outcome_is_restricted_to_the_coverage_pair(self):
        # The one overlap between the two sets (design §The outcome
        # procedure): answered or refused-not-covered, nothing else.
        assert parse("gibberish", covered=True).outcome is Outcome.ANSWERED
        assert parse("gibberish", covered=False).outcome is Outcome.REFUSED_NOT_COVERED

    def test_unparsed_hoists_nothing(self):
        # A stream that ignored the framing gets no envelope fields read
        # out of it: needs-narrowing etc. are unreachable on this path, so
        # a hoisted ?narrow could contradict the outcome.
        stream = "prose first line\n?narrow which is it?\n* option one\n* option two\n@device x"
        result = parse(stream, covered=True)
        assert result.narrowing is None
        assert result.required_device is None
        assert result.uncovered_parts is None


class TestOrdering:
    """1.8: outcome precedes direct_answer precedes every body block, in
    the stream itself — line 1, line 2, line 4 onward."""

    def test_direct_answer_is_line_two(self):
        result = parse(FRAMED, covered=True)
        assert result.direct_answer.startswith("Turn the Track Activator back on")

    def test_body_follows_the_separator(self):
        result = parse(FRAMED, covered=True)
        assert isinstance(result.body[0], Heading)
        assert result.body[0].text == "Why"

    def test_a_missing_separator_loses_no_text(self):
        result = parse("answered\ndirect answer\nbody without separator", covered=True)
        assert result.direct_answer == "direct answer"
        assert "body without separator" in result.body[0].text


class TestBlockClassification:
    """CONTRACTS §4d at column 0; an unknown first line degrades to a
    paragraph, never dropped."""

    def test_the_closed_set(self):
        stream = (
            "answered\ndirect\n---\n"
            "## Heading text\n"
            "1. Step one\n"
            "2. Step two\n"
            "- a bullet\n"
            "\n"
            "a paragraph\n"
            "!caveat Suite only\n"
            f"!conflict two readings\n- reading a [[p:{LIVE}#a1]]\n- reading b [[p:{LIVE}#a2]]\n"
        )
        result = parse(stream, covered=True)
        kinds = [type(block) for block in result.body]
        assert kinds == [Heading, OrderedStep, OrderedStep, Bullet, Paragraph, Caveat, Conflict]

    def test_each_ordered_step_is_separately_identifiable(self):
        result = parse("answered\nd\n---\n1. first\n2. second\n3. third", covered=True)
        assert [block.number for block in result.body] == [1, 2, 3]
        assert [block.text for block in result.body] == ["first", "second", "third"]

    def test_an_unknown_first_line_becomes_a_paragraph(self):
        # §4b rule 2 applied engine-side: output the classifier does not
        # recognise is never discarded.
        result = parse("answered\nd\n---\n%%unknown wrapper text", covered=True)
        assert isinstance(result.body[0], Paragraph)
        assert "%%unknown wrapper text" in result.body[0].text

    def test_paragraphs_are_blank_line_separated(self):
        result = parse("answered\nd\n---\nline one\nline two\n\nsecond paragraph", covered=True)
        assert len(result.body) == 2
        assert result.body[0].text == "line one line two"

    def test_caveat_continuations_are_indented_two_spaces(self):
        stream = "answered\nd\n---\n!caveat Wavetable is Suite-only\n  and this rig runs Standard"
        [caveat] = parse(stream, covered=True).body
        assert isinstance(caveat, Caveat)
        assert caveat.text == "Wavetable is Suite-only and this rig runs Standard"

    def test_blocks_carry_their_markers_in_order(self):
        stream = f"answered\nd\n---\nProse. [[p:{LIVE}#a1]] More. [[p:{APC}#x1]]"
        [block] = parse(stream, covered=True).body
        assert block.markers == (f"{LIVE}#a1", f"{APC}#x1")


class TestConflictArity:
    """§4d: exactly two readings is a producer obligation the parser
    checks and reports through framing — never a re-type."""

    def test_two_readings_is_conforming(self):
        stream = f"answered\nd\n---\n!conflict which\n- a [[p:{LIVE}#a1]]\n- b [[p:{APC}#x1]]"
        result = parse(stream, covered=True)
        [conflict] = result.body
        assert result.framing == "parsed"
        # Markers stay inline — like any block's text — and each reading
        # carries its own, so both citations render separately.
        assert [reading.text for reading in conflict.readings] == [
            f"a [[p:{LIVE}#a1]]", f"b [[p:{APC}#x1]]",
        ]
        assert conflict.readings[0].markers == (f"{LIVE}#a1",)
        assert conflict.readings[1].markers == (f"{APC}#x1",)

    def test_wrong_arity_is_reported_through_framing_not_retyped(self):
        stream = "answered\nd\n---\n!conflict which\n- only one reading"
        result = parse(stream, covered=True)
        [conflict] = result.body
        assert isinstance(conflict, Conflict)  # emitted as received, never re-typed
        assert len(conflict.readings) == 1
        assert result.framing == "unparsed"
        assert result.outcome is Outcome.ANSWERED  # the model's line 1 stands


class TestSigilHoists:
    """The sigils never reach a consumer: hoisted to envelope fields, or
    kept as the two §4d blocks."""

    def test_uncovered_hoists(self):
        result = parse(FRAMED, covered=True)
        assert result.uncovered_parts == ("whether direct monitoring is also muted",)
        assert not any("~uncovered" in getattr(block, "text", "") for block in result.body)

    def test_uncovered_is_absent_not_empty(self):
        assert parse("answered\nd\n---\nprose", covered=True).uncovered_parts is None

    def test_narrow_hoists_question_and_candidates(self):
        stream = (
            "needs-narrowing\nCheck which of these applies.\n---\n"
            "?narrow Which do you observe?\n* the meters move\n* the meters are dead"
        )
        result = parse(stream, covered=True)
        assert result.narrowing.question == "Which do you observe?"
        assert [c.label for c in result.narrowing.candidates] == [
            "the meters move", "the meters are dead",
        ]

    def test_cause_blocks_hoist_with_rank_from_emitted_order(self):
        stream = (
            "ranked-causes\nCheck the track number first.\n---\n"
            f"?cause The Track Activator is off [[p:{TRIAGE}#t1]]\n"
            "check: the track number is dimmed\n"
            f"?cause Direct monitoring is on [[p:{TRIAGE}#t1]] [[p:{LIVE}#a1]]\n"
            "check: the DIRECT MONITOR switch is in\n"
        )
        result = parse(stream, covered=True)
        assert [cause.rank for cause in result.causes] == [1, 2]
        assert result.causes[0].statement == "The Track Activator is off"
        assert result.causes[0].check == "the track number is dimmed"
        # Markers hoist into cites[] and leave the prose.
        assert result.causes[0].cites == (f"{TRIAGE}#t1",)
        assert result.causes[1].cites == (f"{TRIAGE}#t1", f"{LIVE}#a1")
        assert "[[p:" not in result.causes[1].statement

    def test_device_hoists(self):
        stream = "no-manual-for-device\nThe interface manual is needed.\n---\n@device Scarlett 2i2"
        assert parse(stream, covered=True).required_device == "Scarlett 2i2"

    def test_suggest_resolves_against_sources(self):
        stream = f"refused-not-covered\nNot covered here.\n---\n!suggest {APC}\n!suggest {LIVE}"
        result = parse(stream, covered=False, sources=SOURCES)
        assert [ref.source_id for ref in result.suggested_sources] == [APC, LIVE]
        assert result.suggested_sources[0].display_name == "APC Key 25 guide"

    def test_a_model_invented_id_is_dropped(self):
        stream = f"refused-not-covered\nd\n---\n!suggest made/up\n!suggest {APC}"
        result = parse(stream, covered=False, sources=SOURCES)
        assert [ref.source_id for ref in result.suggested_sources] == [APC]

    def test_at_most_three_survive_in_emitted_order(self):
        ids = [APC, LIVE, "alesis/nitro-max", "focusrite/scarlett-solo-4g"]
        stream = "refused-not-covered\nd\n---\n" + "\n".join(f"!suggest {i}" for i in ids)
        result = parse(stream, covered=False, sources=SOURCES)
        assert [ref.source_id for ref in result.suggested_sources] == ids[:3]

    def test_no_survivor_means_absent_never_empty(self):
        # 2.5: an empty array asserts the check ran and found nothing —
        # a different claim from making no suggestion.
        stream = "refused-not-covered\nd\n---\n!suggest made/up"
        assert parse(stream, covered=False, sources=SOURCES).suggested_sources is None
        assert parse("refused-not-covered\nd\n---\n", covered=False).suggested_sources is None
