"""The CONTRACTS §3/§4/§4c/§4e records and the §6/§6a enums, field for field.

CONTRACTS closes these sets: a field outside the tables must be unsettable, an
outcome outside §6 unconstructable — the caller cannot render an outcome the
engine has not named.
"""

import dataclasses

import pytest

from dawmans.answer.envelope import (
    AnswerEnvelope,
    Cause,
    Citation,
    Outcome,
    Reason,
    RequiredManual,
)

CONTRACTS_S3_FIELDS = {
    "source_id",
    "display_name",
    "kind",
    "doc_version",
    "unbacked",
    "hardware_applicability",
    "section_number",
    "section_title",
    "page",
    "passage_id",
    "degraded",
    "has_figures",
    "entry_location",
}

CONTRACTS_S4_FIELDS = {
    "outcome",
    "direct_answer",
    "body",
    "citations",
    "contributing_sources",
    "uncovered_parts",
    "suggested_sources",
    "narrowing",
    "causes",
    "required_device",
    "required_manual",
    "scope_dropped",
    "reason",
    "retry_after",
    "detail",
    "framing",
    "ungrounded",
    "timings",
}

CONTRACTS_S6_OUTCOMES = {
    # the seven content outcomes
    "answered",
    "partially-answered",
    "needs-narrowing",
    "ranked-causes",
    "refused-not-covered",
    "out-of-domain",
    "no-manual-for-device",
    # the ten engine-determined outcomes
    "no-sources-selected",
    "unknown-source-id",
    "corpus-empty",
    "provider-unconfigured",
    "provider-unreachable",
    "provider-rate-limited",
    "provider-error",
    "timeout",
    "incomplete",
    "cancelled",
}

CONTRACTS_S6A_REASONS = {
    "no-provider-kind",
    "missing-credential",
    "disclosure-unacknowledged",
    "authentication-failed",
    "provider-rejected",
}


def field_names(cls) -> set[str]:
    return {f.name for f in dataclasses.fields(cls)}


def vendor_citation(**overrides) -> Citation:
    values = {
        "passage_id": "ableton/live-12#4b12a1",
        "source_id": "ableton/live-12",
        "display_name": "Ableton Live 12 Manual",
        "kind": "vendor-manual",
        "hardware_applicability": "confirmed",
        "doc_version": "12.0",
        "section_number": "16.2",
        "section_title": "Track Activator",
        "page": 412,
    }
    return Citation(**values | overrides)


def authored_citation(**overrides) -> Citation:
    values = {
        "passage_id": "authored/triage#9f3c1a",
        "source_id": "authored/triage",
        "display_name": "Symptom triage notes",
        "kind": "authored-triage",
        "hardware_applicability": "assumed",
        "section_title": "No sound from one track",
        "entry_location": "triage/audio.md:41",
    }
    return Citation(**values | overrides)


def cause(**overrides) -> Cause:
    values = {
        "rank": 1,
        "statement": "The Track Activator is off.",
        "check": "Look at the mixer for a dimmed track number.",
        "cites": ("authored/triage#9f3c1a",),
        "fix_cites": ("ableton/live-12#4b12a1",),
    }
    return Cause(**values | overrides)


class TestFieldSetsAreExactlyTheContractsTables:
    def test_citation_is_contracts_s3(self):
        assert field_names(Citation) == CONTRACTS_S3_FIELDS

    def test_envelope_is_contracts_s4(self):
        assert field_names(AnswerEnvelope) == CONTRACTS_S4_FIELDS

    def test_cause_is_contracts_s4c(self):
        assert field_names(Cause) == {"rank", "statement", "check", "cites", "fix_cites"}

    def test_required_manual_is_contracts_s4e(self):
        assert field_names(RequiredManual) == {"filename", "placeholders"}

    @pytest.mark.parametrize("record", [Citation, AnswerEnvelope, Cause, RequiredManual])
    def test_no_field_outside_the_tables_can_be_set(self, record):
        with pytest.raises(TypeError):
            record(severity="high")

    def test_records_are_frozen(self):
        envelope = AnswerEnvelope(outcome=Outcome.ANSWERED)
        with pytest.raises(dataclasses.FrozenInstanceError):
            envelope.outcome = Outcome.CANCELLED
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
            envelope.severity = "high"


class TestFlatOptionalEnvelopeMembers:
    def test_reason_retry_after_detail_and_framing_default_absent(self):
        envelope = AnswerEnvelope(outcome=Outcome.ANSWERED)
        assert envelope.reason is None
        assert envelope.retry_after is None
        assert envelope.detail is None
        assert envelope.framing is None

    def test_all_four_are_flat_members_of_the_one_envelope(self):
        envelope = AnswerEnvelope(
            outcome=Outcome.PROVIDER_RATE_LIMITED,
            retry_after=3.4,
            detail="the provider stated a retry interval",
            framing="unparsed",
            reason=None,
        )
        # unrounded, as the provider stated it: rounding before the ≤3 s
        # comparison would change which retry branch runs
        assert envelope.retry_after == 3.4

    def test_retry_after_is_non_negative(self):
        with pytest.raises(ValueError):
            AnswerEnvelope(outcome=Outcome.PROVIDER_RATE_LIMITED, retry_after=-1.0)

    def test_framing_is_parsed_or_unparsed_only(self):
        with pytest.raises(ValueError):
            AnswerEnvelope(outcome=Outcome.ANSWERED, framing="half-parsed")


class TestPagelessCitation:
    def test_location_fields_absent_on_authored_triage(self):
        citation = authored_citation()
        assert citation.section_number is None
        assert citation.page is None
        assert citation.doc_version is None

    @pytest.mark.parametrize("name", ["doc_version", "section_number", "section_title"])
    def test_absent_is_never_an_empty_string(self, name):
        with pytest.raises(ValueError):
            vendor_citation(**{name: ""})
        with pytest.raises(ValueError):
            authored_citation(entry_location="")

    @pytest.mark.parametrize(
        "synthesised",
        [{"doc_version": "1.0"}, {"section_number": "3.1"}, {"page": 7}],
    )
    def test_never_synthesised_on_authored_triage(self, synthesised):
        with pytest.raises(ValueError):
            authored_citation(**synthesised)

    def test_entry_location_present_on_authored_triage_only(self):
        assert authored_citation().entry_location == "triage/audio.md:41"
        with pytest.raises(ValueError):
            vendor_citation(entry_location="triage/audio.md:41")

    def test_kind_always_present_and_closed(self):
        with pytest.raises(TypeError):
            Citation(
                passage_id="p",
                source_id="s",
                display_name="d",
                hardware_applicability="assumed",
            )
        with pytest.raises(ValueError):
            vendor_citation(kind="pdf")


class TestCause:
    def test_rank_always_present(self):
        with pytest.raises(TypeError):
            Cause(statement="s", check="c", cites=("p",))

    def test_rank_is_a_one_based_integer(self):
        with pytest.raises(ValueError):
            cause(rank=0)

    def test_rank_equals_position_in_causes(self):
        AnswerEnvelope(
            outcome=Outcome.RANKED_CAUSES,
            causes=(cause(rank=1), cause(rank=2)),
        )
        with pytest.raises(ValueError):
            AnswerEnvelope(
                outcome=Outcome.RANKED_CAUSES,
                causes=(cause(rank=2), cause(rank=1)),
            )

    @pytest.mark.parametrize("name", ["cites", "fix_cites"])
    def test_cites_are_passage_id_lists_never_nested_citations(self, name):
        with pytest.raises(TypeError):
            cause(**{name: (authored_citation(),)})


class TestClosedEnums:
    def test_outcome_is_exactly_the_17_members_of_contracts_s6(self):
        assert {member.value for member in Outcome} == CONTRACTS_S6_OUTCOMES
        assert len(Outcome) == 17

    def test_reason_is_exactly_the_5_values_of_contracts_s6a(self):
        assert {member.value for member in Reason} == CONTRACTS_S6A_REASONS
        assert len(Reason) == 5

    def test_an_unlisted_outcome_cannot_be_constructed(self):
        with pytest.raises(ValueError):
            Outcome("nearly-answered")
        with pytest.raises(ValueError):
            AnswerEnvelope(outcome="nearly-answered")

    def test_an_unlisted_reason_cannot_be_constructed(self):
        with pytest.raises(ValueError):
            Reason("quota-exceeded")
        with pytest.raises(ValueError):
            AnswerEnvelope(outcome=Outcome.PROVIDER_ERROR, reason="quota-exceeded")
