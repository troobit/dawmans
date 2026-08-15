"""The outcome procedure (design §The outcome procedure, Decision 3).

Totality and disjointness are properties a generator attacks rather than
claims in prose: for any gate state and any provider transcript exactly
one CONTRACTS §6 member, never raised; no engine outcome reachable from a
model line and no content outcome from a gate, except the
framing-unparsed path restricted to answered / refused-not-covered.
"""

from hypothesis import given
from hypothesis import strategies as st

from dawmans.answer.envelope import Outcome, Reason
from dawmans.answer.outcome import (
    FAILURE_KINDS,
    Classified,
    Flight,
    GateState,
    classify,
    in_flight,
    pre_flight,
    required_manual_for,
    resolve_device,
)
from dawmans.answer.parse import CONTENT_OUTCOMES

ENGINE_OUTCOMES = {
    Outcome.NO_SOURCES_SELECTED,
    Outcome.UNKNOWN_SOURCE_ID,
    Outcome.CORPUS_EMPTY,
    Outcome.PROVIDER_UNCONFIGURED,
    Outcome.PROVIDER_UNREACHABLE,
    Outcome.PROVIDER_RATE_LIMITED,
    Outcome.PROVIDER_ERROR,
    Outcome.TIMEOUT,
    Outcome.INCOMPLETE,
    Outcome.CANCELLED,
}

READY = GateState(
    passage_count=100,
    selected_count=2,
    provider_kind="local",
    requires_key=False,
    credential_stored=False,
    requires_ack=False,
    acknowledged=False,
)

gate_states = st.builds(
    GateState,
    passage_count=st.integers(min_value=0, max_value=3),
    unknown_source_ids=st.lists(st.sampled_from(["x/y", "a/b"]), max_size=2).map(tuple),
    selected_count=st.integers(min_value=0, max_value=3),
    provider_kind=st.sampled_from([None, "keyed-hosted", "local", "shared-backend"]),
    requires_key=st.booleans(),
    credential_stored=st.booleans(),
    requires_ack=st.booleans(),
    acknowledged=st.booleans(),
)

flights = st.builds(
    Flight,
    cancelled=st.booleans(),
    streamed=st.booleans(),
    failure=st.sampled_from([None, *FAILURE_KINDS]),
    retry_after=st.one_of(st.none(), st.floats(min_value=0.0, max_value=100.0)),
    provider=st.just("anthropic"),
)

lines = st.one_of(
    st.sampled_from(sorted(CONTENT_OUTCOMES)),
    st.sampled_from([outcome.value for outcome in ENGINE_OUTCOMES]),
    st.text(max_size=30),
    st.none(),
)


class TestTotalityAndDisjointness:
    @given(gate=gate_states, flight=flights, line=lines, covered=st.booleans())
    def test_exactly_one_member_never_raised(self, gate, flight, line, covered):
        result = classify(gate, flight, line, covered=covered)
        assert isinstance(result, Classified)
        assert result.outcome in Outcome

    @given(gate=gate_states, flight=flights, line=lines, covered=st.booleans())
    def test_no_engine_outcome_from_a_model_line(self, gate, flight, line, covered):
        # An engine outcome arrives only when its gate actually fired: on
        # a clean gate state and a clean flight, the model's line cannot
        # produce one — even a line spelling one.
        result = classify(READY, Flight(), line, covered=covered)
        assert result.outcome.value in CONTENT_OUTCOMES

    @given(gate=gate_states, flight=flights, covered=st.booleans())
    def test_no_content_outcome_from_a_gate_except_the_unparsed_pair(self, gate, flight, covered):
        gated = pre_flight(gate) or in_flight(flight)
        if gated is not None:
            assert gated.outcome in ENGINE_OUTCOMES
        else:
            # No gate fired and no valid line: the framing-unparsed path,
            # restricted to the coverage pair and nothing else.
            fallback = classify(gate, flight, "not an outcome", covered=covered)
            assert fallback.outcome in (Outcome.ANSWERED, Outcome.REFUSED_NOT_COVERED)

    @given(line=st.sampled_from(sorted(CONTENT_OUTCOMES)), covered=st.booleans())
    def test_a_valid_line_is_taken_verbatim(self, line, covered):
        assert classify(READY, Flight(), line, covered=covered).outcome == Outcome(line)


class TestPreFlightOrder:
    """Fixed order, first match wins: corpus-empty, unknown-source-id,
    no-sources-selected, provider-unconfigured."""

    def test_corpus_empty_wins_over_everything(self):
        gate = GateState(passage_count=0, unknown_source_ids=("x/y",), selected_count=0)
        assert pre_flight(gate).outcome is Outcome.CORPUS_EMPTY

    def test_unknown_source_id_names_the_id(self):
        gate = GateState(passage_count=10, unknown_source_ids=("made/up",), selected_count=0)
        result = pre_flight(gate)
        assert result.outcome is Outcome.UNKNOWN_SOURCE_ID
        assert "made/up" in result.detail  # named, never silently dropped

    def test_no_sources_selected_covers_a_scope_emptied_by_5_11(self):
        gate = GateState(passage_count=10, selected_count=0, provider_kind=None)
        assert pre_flight(gate).outcome is Outcome.NO_SOURCES_SELECTED

    def test_provider_unconfigured_reasons_in_gate_order(self):
        base = {"passage_count": 10, "selected_count": 1}
        no_kind = GateState(**base, provider_kind=None)
        assert pre_flight(no_kind).reason is Reason.NO_PROVIDER_KIND

        keyless = GateState(
            **base, provider_kind="keyed-hosted", requires_key=True, credential_stored=False
        )
        result = pre_flight(keyless)
        assert result.outcome is Outcome.PROVIDER_UNCONFIGURED
        assert result.reason is Reason.MISSING_CREDENTIAL

        unacknowledged = GateState(
            **base, provider_kind="shared-backend", requires_ack=True, acknowledged=False
        )
        assert pre_flight(unacknowledged).reason is Reason.DISCLOSURE_UNACKNOWLEDGED

    def test_a_configured_keyless_provider_passes_the_gate(self):
        assert pre_flight(READY) is None


class TestInFlightOrder:
    """Cancelled first, then the streamed-output check ahead of every
    error-kind gate, then unreachable, rate-limited, timeout, error."""

    def test_cancelled_beats_a_failure_after_partial_output(self):
        # The in-flight table's row 5 ahead of row 6: a turn both
        # cancelled and failed after partial output classifies cancelled.
        flight = Flight(cancelled=True, streamed=True, failure="error")
        assert in_flight(flight).outcome is Outcome.CANCELLED

    @given(kind=st.sampled_from(sorted(FAILURE_KINDS)))
    def test_incomplete_precedence_whatever_the_failure_kind(self, kind):
        # 6.10: any provider failure after ≥1 streamed token yields
        # incomplete — otherwise "any other provider error" would swallow
        # it and UI 9.14 would have no producer.
        flight = Flight(streamed=True, failure=kind)
        assert in_flight(flight).outcome is Outcome.INCOMPLETE

    def test_unreachable(self):
        assert in_flight(Flight(failure="unreachable")).outcome is Outcome.PROVIDER_UNREACHABLE

    def test_rate_limited_carries_retry_after_unrounded(self):
        result = in_flight(Flight(failure="rate-limited", retry_after=3.4))
        assert result.outcome is Outcome.PROVIDER_RATE_LIMITED
        assert result.retry_after == 3.4  # as the provider stated it

    def test_rate_limited_without_an_interval_invents_none(self):
        assert in_flight(Flight(failure="rate-limited")).retry_after is None

    def test_timeout_names_the_provider_as_the_stalled_component(self):
        result = in_flight(Flight(failure="timeout", provider="anthropic"))
        assert result.outcome is Outcome.TIMEOUT
        assert "anthropic" in result.detail

    def test_a_401_is_authentication_failed(self):
        result = in_flight(Flight(failure="auth"))
        assert result.outcome is Outcome.PROVIDER_ERROR
        assert result.reason is Reason.AUTHENTICATION_FAILED

    def test_any_other_error_is_provider_rejected(self):
        result = in_flight(Flight(failure="error"))
        assert result.outcome is Outcome.PROVIDER_ERROR
        assert result.reason is Reason.PROVIDER_REJECTED

    def test_authentication_failed_is_distinguishable_by_sub_code_alone(self):
        # 6.6: missing-credential (pre-flight) versus authentication-failed
        # (in-flight) differ in outcome and reason — the enumerated codes —
        # never by the wording in detail, which no caller may parse.
        missing = pre_flight(
            GateState(
                passage_count=1, selected_count=1, provider_kind="keyed-hosted", requires_key=True
            )
        )
        rejected = in_flight(Flight(failure="auth"))
        assert (missing.outcome, missing.reason) != (rejected.outcome, rejected.reason)

    def test_a_clean_flight_fires_no_gate(self):
        assert in_flight(Flight()) is None


# The live report is empty (every rig device is documented), so the
# resolver is exercised against a fixture — the field is dormant, not
# removed (CONTRACTS §4e).
GAPS = {
    "owned_but_undocumented": [
        {"device": "focusrite/scarlett-2i2", "display_name": "Focusrite Scarlett 2i2"},
        "behringer/xr18",  # bare-string member shape, as scope.py accepts
    ],
    "documented_but_unconfirmed": [],
}


class TestRequiredDevice:
    def test_a_matching_name_substitutes_canonical_id_and_rig_display_name(self):
        device = resolve_device("Focusrite Scarlett 2i2", GAPS)
        assert device.device == "focusrite/scarlett-2i2"
        assert device.display_name == "Focusrite Scarlett 2i2"

    def test_a_canonical_id_matches_directly(self):
        assert resolve_device("focusrite/scarlett-2i2", GAPS).device == "focusrite/scarlett-2i2"

    def test_a_bare_string_gap_member_resolves(self):
        device = resolve_device("behringer/xr18", GAPS)
        assert device.device == "behringer/xr18"
        assert device.display_name is None

    def test_an_unmatched_name_is_carried_free_form_not_an_error(self):
        device = resolve_device("Roland TR-8S", GAPS)
        assert device.device == "Roland TR-8S"
        assert device.display_name is None


class TestRequiredManual:
    def test_placeholders_sit_inside_the_filename_and_are_listed_exactly(self):
        manual = required_manual_for(resolve_device("Focusrite Scarlett 2i2", GAPS), GAPS)
        assert manual.filename == "focusrite_scarlett-2i2_<doctype>_v<version>_<lang>.pdf"
        assert manual.placeholders == ("doctype", "version", "lang")

    def test_absent_where_the_device_did_not_resolve(self):
        # Vendor and product are the two fields no placeholder can stand
        # in for; a name that is placeholder all the way down is not
        # copyable, so the field is absent and never synthesised.
        assert required_manual_for(resolve_device("Roland TR-8S", GAPS), GAPS) is None

    def test_a_free_form_name_shaped_like_an_id_is_still_absent(self):
        # Presence keys on resolution through the report, never on the
        # name's shape: a slashed name the report does not hold stays
        # free-form and yields no filename.
        assert required_manual_for(resolve_device("roland/tr-8s", GAPS), GAPS) is None
