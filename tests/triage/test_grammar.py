"""The entry grammar — design 'Entry grammar' and 'Error Handling'.

Strict about frontmatter, forgiving in the body (Decision 1). Nothing here asks
the author for a hand-computed value (1.7).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from rendering import Section, entry_file

from dawmans.triage.parse import parse_entry, render

ENTRY_PATH = Path("triage/no-sound-from-track.md")
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "triage"


def parse(text: str, path: Path = ENTRY_PATH):
    return parse_entry(path, text.encode("utf-8"))


def rejection_of(text: str, path: Path = ENTRY_PATH):
    result = parse(text, path)
    assert result.rejection is not None, "expected a rejection"
    assert result.entry is None, "a rejection never returns a half-built entry"
    return result.rejection


def entry_of(text: str, path: Path = ENTRY_PATH):
    result = parse(text, path)
    assert result.rejection is None, f"unexpected rejection: {result.rejection}"
    assert result.entry is not None
    return result.entry


def cause(statement: str, check: str = "a check", fix: str = "ableton/live-12 §16.4") -> Section:
    return Section(statement=statement, check=check, fixes=[fix])


def well_formed(**overrides) -> str:
    kwargs = {
        "devices": ["ableton/live-12"],
        "symptom": "No sound from a track",
        "sections": [cause("The Track Activator is off"), cause("Another track is soloed")],
    }
    kwargs.update(overrides)
    return entry_file(**kwargs)


# --- Frontmatter (4.1) ----------------------------------------------------


def test_bom_is_stripped_before_the_frontmatter_check():
    """A UTF-8 BOM makes `---` start at byte 3; it is still frontmatter at byte 0."""
    assert entry_of(well_formed()).symptom == "No sound from a track"
    with_bom = well_formed()
    assert entry_of("﻿" + with_bom).symptom == "No sound from a track"


def test_fence_must_be_at_byte_zero():
    assert rejection_of("\n" + well_formed()).reason == "frontmatter-missing"


def test_frontmatter_absent_is_rejected():
    assert rejection_of("# No sound\n\n## A cause\n").reason == "frontmatter-missing"


def test_unterminated_fence_is_malformed():
    text = "---\ndevices: [ableton/live-12]\n\n# No sound from a track\n"
    assert rejection_of(text).reason == "frontmatter-malformed"


def test_unparseable_yaml_is_malformed():
    text = "---\ndevices: [ableton/live-12\n  bad: -\n---\n\n# No sound\n"
    assert rejection_of(text).reason == "frontmatter-malformed"


def test_frontmatter_that_is_not_a_mapping_is_malformed():
    text = "---\n- ableton/live-12\n---\n\n# No sound\n"
    assert rejection_of(text).reason == "frontmatter-malformed"


def test_devices_absent_is_no_devices():
    text = "---\ntitle: whatever\n---\n\n# No sound\n"
    assert rejection_of(text).reason == "no-devices"


@pytest.mark.parametrize("value", ["[]", "", "~"])
def test_devices_empty_is_no_devices(value: str):
    text = f"---\ndevices: {value}\n---\n\n# No sound\n"
    assert rejection_of(text).reason == "no-devices"


def test_devices_as_a_string_is_devices_not_a_list():
    """`devices: ableton/live-12` is valid YAML, is non-empty, and iterates as characters."""
    text = "---\ndevices: ableton/live-12\n---\n\n# No sound\n"
    assert rejection_of(text).reason == "devices-not-a-list"


def test_devices_as_a_mapping_is_devices_not_a_list():
    text = "---\ndevices:\n  ableton/live-12: yes\n---\n\n# No sound\n"
    assert rejection_of(text).reason == "devices-not-a-list"


def test_unknown_frontmatter_key_flags_and_does_not_reject():
    result = parse(well_formed(frontmatter_extra={"colour": "blue"}))
    assert result.entry is not None
    assert [f.name for f in result.flags] == ["unknown-frontmatter-key"]
    assert "colour" in result.flags[0].detail


def test_device_revision_suffix_is_split_off():
    entry = entry_of(well_formed(devices=["akai/apc-key-25@mk2", "ableton/live-12"]))
    assert [(d.id, d.revision) for d in entry.devices] == [
        ("akai/apc-key-25", "mk2"),
        ("ableton/live-12", None),
    ]


# --- Symptom and preamble (1.1, 1.3) --------------------------------------


def test_the_single_h1_is_the_symptom_and_its_line_is_recorded():
    entry = entry_of(well_formed())
    assert entry.symptom == "No sound from a track"
    assert entry.line == 5
    assert entry.source_file == ENTRY_PATH


@pytest.mark.parametrize("headings", [[], ["# One", "# Two"]])
def test_any_h1_count_other_than_one_is_no_symptom(headings: list[str]):
    body = "\n".join(headings)
    text = f"---\ndevices: [ableton/live-12]\n---\n\n{body}\n\n## A cause\ncheck: c\nfix: x/y §1\n"
    assert rejection_of(text).reason == "no-symptom"


def test_also_lines_split_on_semicolons():
    entry = entry_of(well_formed(phrasings=["track is silent", "can't hear track 3"]))
    assert entry.phrasings == ["track is silent", "can't hear track 3"]


def test_multiple_also_lines_accumulate():
    text = well_formed(preamble=["also: one; two", "also: three"])
    assert entry_of(text).phrasings == ["one", "two", "three"]


def test_other_preamble_prose_is_retained():
    entry = entry_of(well_formed(preamble=["This one bites during tracking."]))
    assert "This one bites during tracking." in entry.preamble


def test_prose_before_the_h1_is_retained_rather_than_dropped():
    text = well_formed().replace("# No sound", "A note the author left above.\n\n# No sound", 1)
    assert "A note the author left above." in entry_of(text).preamble


# --- Keyed lines (1.3) ----------------------------------------------------


@pytest.mark.parametrize(
    "marker", ["check:", "Check:", "CHECK:", "- check :", "**Check:**", "> check:"]
)
def test_keyed_lines_match_case_insensitively_after_stripping_markers(marker: str):
    text = well_formed(
        sections=[
            Section(
                statement="The Track Activator is off",
                check=None,
                fixes=["ableton/live-12 §16.4"],
                notes=[f"{marker} the number is dimmed"],
            ),
            cause("Another track is soloed"),
        ]
    )
    entry = entry_of(text)
    assert entry.causes[0].check == "the number is dimmed"


def test_the_emitted_text_carries_the_normalised_marker():
    """Marker style is the author's; what is hashed and shown is `check:` (§Identity)."""
    text = well_formed(
        sections=[
            Section(
                statement="The Track Activator is off",
                check=None,
                fixes=["ableton/live-12 §16.4"],
                notes=["**Check:** the number is dimmed", "- WHY : it is the commonest cause"],
            ),
            cause("Another track is soloed"),
        ]
    )
    rendering = render(entry_of(text))
    assert "check: the number is dimmed" in rendering
    assert "**Check:**" not in rendering
    assert "why: it is the commonest cause" in rendering


def test_a_value_continues_until_a_blank_line_a_heading_or_another_keyed_line():
    text = well_formed(
        sections=[
            Section(
                statement="The Track Activator is off",
                check=None,
                fixes=["ableton/live-12 §16.4"],
                notes=["check: the number is dimmed", "in the mixer strip", "", "loose prose"],
            ),
            cause("Another track is soloed"),
        ]
    )
    entry = entry_of(text)
    assert entry.causes[0].check == "the number is dimmed in the mixer strip"
    assert "loose prose" in entry.causes[0].notes


def test_prose_under_a_fix_line_is_prose_and_does_not_break_the_pointer():
    """A pointer is complete on its own line (Decision 7), so a note written
    beneath one is retained rather than swallowed into the pointer."""
    text = well_formed(
        sections=[
            Section(
                statement="The buffer size is too high",
                check="latency is audible when playing in",
                fixes=['ableton/live-12 §1.2 "Audio Preferences"'],
                notes=["Raising it again after tracking is fine."],
            ),
            cause("Another track is soloed"),
        ]
    )
    first = entry_of(text).causes[0]
    assert first.fixes[0].section_number == "1.2"
    assert "Raising it again after tracking is fine." in first.notes


def test_prose_under_an_also_line_is_preamble_and_is_not_a_phrasing():
    text = well_formed(
        phrasings=["track is silent"],
        preamble=["This one bites during tracking."],
    )
    entry = entry_of(text)
    assert entry.phrasings == ["track is silent"]
    assert entry.preamble == "This one bites during tracking."


# --- Causes (1.1, 1.2, 1.4, 1.5) ------------------------------------------


def test_causes_are_the_h2s_in_document_order():
    text = well_formed(sections=[cause("First"), cause("Second"), cause("Third")])
    assert [c.statement for c in entry_of(text).causes] == ["First", "Second", "Third"]


def test_a_second_check_line_is_retained_as_a_note_rather_than_rejecting():
    """Forgiving in the body: nothing the author wrote disappears, and the set of
    rejection reasons stays closed."""
    text = well_formed(
        sections=[
            Section(
                statement="The Track Activator is off",
                check="the number is dimmed",
                fixes=["ableton/live-12 §16.4"],
                notes=["check: and the meter is still"],
            ),
            cause("Another track is soloed"),
        ]
    )
    entry = entry_of(text)
    assert entry.causes[0].check == "the number is dimmed"
    assert "check: and the meter is still" in entry.causes[0].notes


def test_a_cause_without_a_check_is_rejected():
    text = well_formed(
        sections=[
            Section(statement="The Track Activator is off", fixes=["ableton/live-12 §16.4"]),
            cause("Another track is soloed"),
        ]
    )
    rejection = rejection_of(text)
    assert rejection.reason == "cause-missing-check"
    assert rejection.cause == "The Track Activator is off"
    assert rejection.symptom == "No sound from a track"


def test_a_cause_without_a_fix_is_rejected():
    text = well_formed(
        sections=[
            Section(statement="The Track Activator is off", check="the number is dimmed"),
            cause("Another track is soloed"),
        ]
    )
    assert rejection_of(text).reason == "cause-missing-fix"


def test_a_cause_carrying_both_a_fix_and_an_undocumented_line_is_rejected():
    text = well_formed(
        sections=[
            Section(
                statement="Direct monitoring is on",
                check="the DIRECT MONITOR button is lit",
                fixes=["focusrite/scarlett-solo-4g §2.1"],
                undocumented="focusrite/scarlett-solo",
            ),
            cause("Another track is soloed"),
        ]
    )
    assert rejection_of(text).reason == "cause-fix-and-undocumented"


def test_an_undocumented_cause_carries_no_pointers():
    text = well_formed(
        sections=[
            Section(
                statement="Direct monitoring is on",
                check="the DIRECT MONITOR button is lit",
                undocumented="focusrite/scarlett-solo",
            ),
            cause("Another track is soloed"),
        ]
    )
    first = entry_of(text).causes[0]
    assert first.fixes == []
    assert first.undocumented_device == "focusrite/scarlett-solo"


def test_fewer_than_two_causes_is_rejected():
    text = well_formed(sections=[cause("The Track Activator is off")])
    assert rejection_of(text).reason == "too-few-causes"


def test_more_than_six_causes_is_rejected():
    text = well_formed(sections=[cause(f"Cause {n}") for n in range(7)])
    assert rejection_of(text).reason == "too-many-causes"


def test_the_closing_statement_is_excluded_from_the_cause_count():
    sections = [cause(f"Cause {n}") for n in range(6)]
    sections.append(Section(statement="Otherwise", notes=["Check the master track."]))
    entry = entry_of(well_formed(sections=sections))
    assert len(entry.causes) == 6
    assert entry.closing is not None


# --- The closing statement (Decision 6) -----------------------------------


def test_the_final_h2_with_neither_a_check_nor_a_fix_is_the_closing_statement():
    text = well_formed(
        sections=[
            cause("The Track Activator is off"),
            cause("Another track is soloed"),
            Section(statement="Otherwise", notes=["Check the master track."]),
        ]
    )
    result = parse(text)
    assert result.entry is not None
    assert len(result.entry.causes) == 2
    assert "Otherwise" in result.entry.closing
    assert "Check the master track." in result.entry.closing


def test_a_closing_statement_always_emits_closing_statement_inferred_naming_the_section():
    """Position, not vocabulary, identifies it, so the inference is never silent —
    including where the author genuinely meant one (Decision 6)."""
    text = well_formed(
        sections=[
            cause("The Track Activator is off"),
            cause("Another track is soloed"),
            Section(statement="Otherwise", notes=["Check the master track."]),
        ]
    )
    flags = [f for f in parse(text).flags if f.name == "closing-statement-inferred"]
    assert len(flags) == 1
    assert "Otherwise" in flags[0].detail


def test_three_causes_whose_last_loses_both_parses_as_two_causes_plus_a_note():
    fixture = FIXTURES / "three_causes_last_demoted.md"
    result = parse_entry(Path("triage/metronome.md"), fixture.read_bytes())
    assert result.rejection is None
    assert len(result.entry.causes) == 2
    assert "The master track is muted" in result.entry.closing
    flags = [f for f in result.flags if f.name == "closing-statement-inferred"]
    assert len(flags) == 1
    assert "The master track is muted" in flags[0].detail


def test_a_section_losing_both_in_the_middle_is_a_cause_and_rejects():
    """The rule is positional: only the final section can be demoted."""
    text = well_formed(
        sections=[
            cause("The Track Activator is off"),
            Section(statement="A stray note"),
            cause("Another track is soloed"),
        ]
    )
    rejection = rejection_of(text)
    assert rejection.reason == "cause-missing-check"
    assert rejection.cause == "A stray note"


def test_losing_only_the_fix_still_rejects():
    text = well_formed(
        sections=[
            cause("The Track Activator is off"),
            cause("Another track is soloed"),
            Section(statement="The master track is muted", check="the master is dimmed"),
        ]
    )
    assert rejection_of(text).reason == "cause-missing-fix"


# --- Fix pointer lines ----------------------------------------------------


def test_the_section_number_form_parses():
    text = well_formed(
        sections=[cause("A", fix="ableton/live-12 §16.4"), cause("Another track is soloed")]
    )
    pointer = entry_of(text).causes[0].fixes[0]
    assert (pointer.source_id, pointer.section_number, pointer.section_title) == (
        "ableton/live-12",
        "16.4",
        None,
    )


def test_the_section_title_form_parses():
    text = well_formed(
        sections=[
            cause("A", fix='akai/apc-key-25 "Shift Functions"'),
            cause("Another track is soloed"),
        ]
    )
    pointer = entry_of(text).causes[0].fixes[0]
    assert (pointer.source_id, pointer.section_number, pointer.section_title) == (
        "akai/apc-key-25",
        None,
        "Shift Functions",
    )


def test_both_forms_together_parse():
    text = well_formed(
        sections=[
            cause("A", fix='ableton/live-12 §1.2 "Audio Preferences"'),
            cause("Another track is soloed"),
        ]
    )
    pointer = entry_of(text).causes[0].fixes[0]
    assert pointer.section_number == "1.2"
    assert pointer.section_title == "Audio Preferences"


def test_several_fix_lines_give_several_pointers_in_order():
    text = well_formed(
        sections=[
            Section(
                statement="A",
                check="c",
                fixes=["ableton/live-12 §16.4", "ableton/live-12 §16.5"],
            ),
            cause("Another track is soloed"),
        ]
    )
    assert [p.section_number for p in entry_of(text).causes[0].fixes] == ["16.4", "16.5"]


def test_a_pointer_line_carries_its_own_line_number_for_the_message():
    entry = entry_of(well_formed())
    assert entry.causes[0].fixes[0].line == 9


def test_a_fix_line_naming_neither_a_section_nor_a_title_is_retained_but_is_not_a_pointer():
    text = well_formed(
        sections=[
            Section(statement="A", check="c", fixes=["ableton/live-12"]),
            cause("Another track is soloed"),
        ]
    )
    rejection = rejection_of(text)
    assert rejection.reason == "cause-missing-fix"
    assert "ableton/live-12" in rejection.detail


# --- Every rejection names the file (5.2, 5.3) ----------------------------


@pytest.mark.parametrize(
    "text",
    [
        "not an entry at all",
        "---\ndevices: []\n---\n# S\n",
        "---\ndevices: [a/b]\n---\n",
    ],
)
def test_every_rejection_names_the_file(text: str):
    rejection = rejection_of(text, Path("triage/nested/thing.md"))
    assert rejection.source_file == Path("triage/nested/thing.md")
    assert rejection.detail


# --- The canonical rendering ----------------------------------------------


def test_the_rendering_excludes_frontmatter_fix_pointers_and_the_filename():
    entry = entry_of(well_formed(devices=["akai/apc-key-25@mk2"]))
    rendering = render(entry)
    assert "devices" not in rendering
    assert "apc-key-25" not in rendering
    assert "16.4" not in rendering
    assert "no-sound-from-track" not in rendering


def test_the_rendering_carries_the_symptom_phrasings_preamble_causes_and_closing():
    text = well_formed(
        phrasings=["track is silent"],
        preamble=["This one bites during tracking."],
        sections=[
            cause("The Track Activator is off", check="the number is dimmed"),
            cause("Another track is soloed", check="a blue S is lit"),
            Section(statement="Otherwise", notes=["Check the master track."]),
        ],
    )
    rendering = render(entry_of(text))
    for fragment in (
        "No sound from a track",
        "also: track is silent",
        "This one bites during tracking.",
        "The Track Activator is off",
        "check: the number is dimmed",
        "Another track is soloed",
        "Check the master track.",
    ):
        assert fragment in rendering
