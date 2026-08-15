"""Device scope validation — design 'Device scope' and 'Error Handling'.

The six rows of that section's table, the exact-match rule (4.2), the
`undocumented:` claim (2.3) and revision comparison (4.6). This spec filters
nothing itself: it validates the declaration and publishes it (4.3).
"""

from __future__ import annotations

from pathlib import Path

from fixture_rig import INDEXED, RIG, FixtureRigDevice
from rendering import Section, entry_file

from dawmans.triage.parse import parse_entry
from dawmans.triage.scope import validate_scope

ENTRY_PATH = Path("triage/no-sound-from-track.md")


def cause(statement: str) -> Section:
    return Section(statement, check="a check", fixes=["ableton/live-12 §16.4"])


DEFAULT_SECTIONS = [cause("The Track Activator is off"), cause("Another track is soloed")]
"""Two causes: 1.4's floor, so every fixture parses before scope sees it."""


def entry_with(devices: list[str], sections: list[Section] | None = None):
    text = entry_file(
        devices=devices,
        symptom="No sound from a track",
        sections=sections or DEFAULT_SECTIONS,
    )
    result = parse_entry(ENTRY_PATH, text.encode("utf-8"))
    assert result.rejection is None, f"fixture did not parse: {result.rejection}"
    assert result.entry is not None
    return result.entry


def scope_of(devices: list[str], sections: list[Section] | None = None, rig=RIG, indexed=INDEXED):
    return validate_scope(entry_with(devices, sections), rig, indexed)


def flag_names(result) -> list[str]:
    return [flag.name for flag in result.flags]


def only_flag(result):
    assert result.rejection is None, f"unexpected rejection: {result.rejection}"
    assert len(result.flags) == 1, f"expected one flag, got {flag_names(result)}"
    return result.flags[0]


UNDOCUMENTED_STATEMENT = "The interface is not passing audio"


def claims_undocumented(device: str) -> list[Section]:
    """A well-formed entry whose second cause takes 2.3's carve-out."""
    return [
        cause("The Track Activator is off"),
        Section(UNDOCUMENTED_STATEMENT, check="a check", undocumented=device),
    ]


# --- The six rows of design 'Device scope' --------------------------------


def test_a_device_in_the_rig_and_documented_scopes_with_no_flag():
    """Row 1. The ordinary case: the entry ingests and says nothing."""
    result = scope_of(["ableton/live-12"])
    assert result.rejection is None
    assert result.flags == []
    assert result.scoped == ["ableton/live-12"]


def test_a_rig_device_with_no_indexed_source_scopes_and_is_reported():
    """Row 2 (4.4). It still scopes — the report is what 4.4 asks for, not a withdrawal."""
    result = scope_of(["elektron/digitakt"])
    flag = only_flag(result)
    assert flag.name == "undocumented-device-scope"
    assert "elektron/digitakt" in flag.detail
    assert result.scoped == ["elektron/digitakt"]


def test_a_documented_device_absent_from_the_rig_scopes_with_no_flag():
    """Row 3. 4.5's condition is 'neither', so an ingested source satisfies neither branch.

    It is a device removed under 8.7, or a manual added ahead of its rig entry.
    Flagging it would be a warning 4.5 does not authorise.
    """
    result = scope_of(["roland/tr-8s"])
    assert result.rejection is None
    assert result.flags == []
    assert result.scoped == ["roland/tr-8s"]


def test_one_unrecognised_device_among_recognised_ones_flags_and_still_ingests():
    """Row 4 (4.5). The flag names the declaration, so the typo is fixable by reading it."""
    result = scope_of(["ableton/live-12", "ableton/live-11"])
    flag = only_flag(result)
    assert flag.name == "unknown-device"
    assert "ableton/live-11" in flag.detail
    assert result.scoped == ["ableton/live-12", "ableton/live-11"]


def test_every_unrecognised_device_is_a_rejection():
    """Row 5 — the recorded 4.5 deviation.

    An entry no turn can retrieve is withdrawn at the desk rather than embedded
    unreachable, costing budget and reaching nobody.
    """
    result = scope_of(["ableton/live-11", "akai/apc-key-49"])
    assert result.rejection is not None
    assert result.rejection.reason == "all-devices-unrecognised"
    assert result.rejection.source_file == ENTRY_PATH
    assert result.rejection.symptom == "No sound from a track"
    assert "ableton/live-11" in result.rejection.detail
    assert "akai/apc-key-49" in result.rejection.detail


def test_a_rejected_entry_carries_no_flags_and_no_scope():
    """A rejection excludes the entry, so remarks about it are noise (5.2, 5.5)."""
    result = scope_of(["elektron/digitakt-2@mk1"])
    assert result.rejection is not None
    assert result.flags == []
    assert result.scoped == []


def test_a_declared_revision_the_rig_does_not_hold_flags():
    """Row 6 (4.6). A Suite-only step is useless on a Standard rig (CONTRACTS §8)."""
    flag = only_flag(scope_of(["ableton/live-12@suite"]))
    assert flag.name == "revision-mismatch"


# --- Exact matching, never fuzzy (4.2) ------------------------------------


def test_a_prefix_of_a_rig_identity_is_unrecognised():
    """`ableton/live-1` is not `ableton/live-12`: matched, not guessed at."""
    result = scope_of(["ableton/live-12", "ableton/live-1"])
    assert only_flag(result).name == "unknown-device"


def test_identity_matching_is_case_sensitive():
    """Identities are the corpus's own, and the corpus's are lowercase."""
    result = scope_of(["ableton/live-12", "Ableton/Live-12"])
    assert only_flag(result).name == "unknown-device"


def test_a_superstring_of_a_rig_identity_is_unrecognised():
    result = scope_of(["ableton/live-12", "ableton/live-12-lite"])
    assert only_flag(result).name == "unknown-device"


# --- Revision comparison (4.6) --------------------------------------------


def test_a_revision_equal_to_the_rig_value_matches():
    assert scope_of(["akai/apc-key-25@mk2"]).flags == []


def test_a_revision_matches_after_casefolding_and_stripping_punctuation():
    """`@12-standard` against `revision: "12 Standard"` is the same edition."""
    assert scope_of(["ableton/live-12@12-standard"]).flags == []
    assert scope_of(["ableton/live-12@12Standard"]).flags == []
    assert scope_of(["focusrite/scarlett-solo@4thgen"]).flags == []


def test_a_revision_mismatch_quotes_the_rig_value_verbatim():
    """Correcting the declaration is a copy rather than a guess."""
    flag = only_flag(scope_of(["ableton/live-12@suite"]))
    assert flag.name == "revision-mismatch"
    assert "12 Standard" in flag.detail, "the rig's value, not its normalised form"
    assert "suite" in flag.detail


def test_a_partial_revision_does_not_satisfy_a_longer_one():
    """Either-contains matching would let `@12` and even `@s` satisfy `12 Standard`."""
    assert only_flag(scope_of(["ableton/live-12@12"])).name == "revision-mismatch"
    assert only_flag(scope_of(["ableton/live-12@s"])).name == "revision-mismatch"


def test_a_revision_declared_where_the_rig_declares_none_flags():
    """`alesis/nitro-max` has no revision marker, so there is no edition to agree with."""
    flag = only_flag(scope_of(["alesis/nitro-max@mk2"]))
    assert flag.name == "revision-mismatch"
    assert "alesis/nitro-max" in flag.detail


def test_no_declared_revision_never_flags():
    """4.6 permits constraining the scope; it does not require it."""
    assert scope_of(["ableton/live-12", "alesis/nitro-max"]).flags == []


def test_a_revision_on_a_device_outside_the_rig_has_nothing_to_compare():
    """The comparison is against the rig device's revision, and there is none."""
    assert scope_of(["roland/tr-8s@mk2"]).flags == []


def test_an_unrecognised_device_flags_once_and_not_also_for_its_revision():
    result = scope_of(["ableton/live-12", "ableton/live-11@suite"])
    assert flag_names(result) == ["unknown-device"]


# --- The `undocumented:` claim (2.3) --------------------------------------


def test_an_undocumented_claim_naming_a_rig_device_with_no_source_is_valid():
    """2.3's carve-out: a cause may go unbacked where no manual exists to back it."""
    result = scope_of(["elektron/digitakt"], claims_undocumented("elektron/digitakt"))
    assert result.rejection is None
    assert flag_names(result) == ["undocumented-device-scope"]


def test_an_undocumented_claim_naming_a_device_absent_from_the_rig_rejects():
    result = scope_of(["ableton/live-12"], claims_undocumented("elektron/digitakt-2"))
    assert result.rejection is not None
    assert result.rejection.reason == "undocumented-claim-invalid"
    assert "elektron/digitakt-2" in result.rejection.detail
    assert result.rejection.cause == UNDOCUMENTED_STATEMENT


def test_an_undocumented_claim_naming_an_indexed_device_rejects():
    """The manual is sitting in the corpus: the cause must cite it (2.2)."""
    result = scope_of(["ableton/live-12"], claims_undocumented("ableton/live-12"))
    assert result.rejection is not None
    assert result.rejection.reason == "undocumented-claim-invalid"
    assert "ableton/live-12" in result.rejection.detail


def test_an_undocumented_claim_naming_an_indexed_source_id_rejects():
    """Naming the source rather than the device documents it just as well."""
    result = scope_of(["ableton/live-12"], claims_undocumented("focusrite/scarlett-solo-4g"))
    assert result.rejection is not None
    assert result.rejection.reason == "undocumented-claim-invalid"


def test_the_undocumented_claim_is_checked_on_a_cause_that_is_not_the_last():
    sections = list(reversed(claims_undocumented("elektron/digitakt-2")))
    result = scope_of(["ableton/live-12"], sections)
    assert result.rejection is not None
    assert result.rejection.reason == "undocumented-claim-invalid"


def test_an_unrecognised_scope_is_rejected_before_its_undocumented_claim():
    """Both rejections apply; the entry gets one, and unreachability is the wider fault."""
    result = scope_of(["ableton/live-11"], claims_undocumented("elektron/digitakt-2"))
    assert result.rejection is not None
    assert result.rejection.reason == "all-devices-unrecognised"


# --- The published declaration (4.3) --------------------------------------


def test_the_scope_is_the_declared_ids_in_declared_order_without_revisions():
    """The engine's 5.13 predicate matches device identities; `@suite` is not one."""
    result = scope_of(["akai/apc-key-25@mk2", "ableton/live-12"])
    assert result.scoped == ["akai/apc-key-25", "ableton/live-12"]


def test_an_empty_rig_leaves_indexed_devices_recognised():
    """The rig is hand-maintained and may lag the corpus; that is row 3, not a rejection."""
    result = scope_of(["ableton/live-12"], rig=())
    assert result.rejection is None
    assert result.flags == []


def test_an_empty_corpus_leaves_rig_devices_recognised_and_undocumented():
    """The first ingest, before any manual is indexed."""
    result = scope_of(["ableton/live-12"], indexed=frozenset())
    assert flag_names(result) == ["undocumented-device-scope"]


def test_a_rig_device_shadowed_by_no_source_still_compares_its_revision():
    """4.4 and 4.6 are independent: an undocumented device can still be the wrong edition."""
    result = scope_of(["elektron/digitakt@mk2"])
    assert sorted(flag_names(result)) == ["revision-mismatch", "undocumented-device-scope"]


def test_the_first_rig_entry_for_a_device_wins():
    """A duplicated id in `rig.yaml` is that file's defect; scope stays deterministic."""
    rig = (
        FixtureRigDevice("ableton/live-12", "12 Standard"),
        FixtureRigDevice("ableton/live-12", "12 Suite"),
    )
    flag = only_flag(scope_of(["ableton/live-12@suite"], rig=rig))
    assert "12 Standard" in flag.detail


def test_every_flag_and_rejection_names_the_entry_file():
    """5.3: a message the author can act on names what it is about."""
    flagged = scope_of(["ableton/live-12@suite"])
    assert all(flag.source_file == ENTRY_PATH for flag in flagged.flags)
    assert all(flag.symptom == "No sound from a track" for flag in flagged.flags)
    rejected = scope_of(["ableton/live-11"])
    assert rejected.rejection is not None
    assert rejected.rejection.source_file == ENTRY_PATH
