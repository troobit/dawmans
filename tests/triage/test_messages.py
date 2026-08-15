"""Validation messages and the rejection taxonomy — 5.2, 5.3, 5.5.

Three things are asserted here, and the first is what makes the other two mean
anything:

- **The rejection set is closed.** Design 'Error Handling' names fifteen reason
  constants across twelve table rows, three of which carry paired reasons. `CASES`
  holds one malformed entry per constant, and the store built from all of them
  produces exactly that set — no sixteenth reason, and no constant that nothing
  can reach.
- **Every message is one the author can act on** (5.3): it names the file, the
  symptom where the parse got far enough to know it, and the cause where the fault
  is in one, and it says what to change in the entry's own words. Never a position
  or an internal error name alone — the reason constants are not printed at all.
- **A rejection costs one entry** (5.2). Sixteen malformed files sit beside two
  well-formed ones in a single store, and the run still emits both good entries and
  reports success; only when nothing survives is the source itself rejected.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from rendering import Section, entry_file
from stores import DEFAULT, DIGITAKT_ID, DISCOVERED, LIVE_ID, POINTER, loader, store

from dawmans.triage import messages
from dawmans.triage.model import RejectionReason
from dawmans.triage.pointers import LEDGER_NAME

REASONS: tuple[RejectionReason, ...] = (
    "frontmatter-missing",
    "frontmatter-malformed",
    "no-devices",
    "devices-not-a-list",
    "no-symptom",
    "too-few-causes",
    "too-many-causes",
    "cause-missing-check",
    "cause-missing-fix",
    "cause-fix-and-undocumented",
    "pointer-unresolved",
    "pointer-authored-target",
    "undocumented-claim-invalid",
    "all-devices-unrecognised",
    "duplicate-symptom",
)
"""The fifteen constants of design 'Error Handling', restated so a reason added to
the model without a message and a fixture fails here rather than passing silently."""


def cause(statement: str, *, fix: str = POINTER) -> Section:
    """A well-formed cause, worded in lower case so no term check fires on it.

    The term check is a different subject with its own tests; a statement written
    `The Track Activator is off` here would add `term-not-in-passage` flags to
    stores whose point is the rejection they carry.
    """
    return Section(statement, check="the track's number is unlit", fixes=[fix])


def body(*statements: str) -> list[Section]:
    return [cause(statement) for statement in statements]


TWO_CAUSES = body("the track is deactivated", "another track is soloed")


def malformed(symptom: str, sections: list[Section], **kwargs) -> str:
    return entry_file(devices=[LIVE_ID], symptom=symptom, sections=sections, **kwargs)


@dataclass(frozen=True)
class Case:
    """One malformed entry, and what its message has to name."""

    reason: RejectionReason
    name: str
    text: str
    symptom: str | None = None
    """None where the parse rejects before it can know the symptom — the message
    names the file, which is the only handle the author has been given."""

    cause: str | None = None
    """The cause statement, where the fault is in one cause rather than the entry."""


NO_SOUND = "no sound from a track"

CASES: tuple[Case, ...] = (
    Case(
        "frontmatter-missing",
        "no-fence.md",
        f"# {NO_SOUND} on the master\n\n"
        f"## the track is deactivated\ncheck: it is unlit\nfix: {POINTER}\n",
    ),
    Case(
        "frontmatter-malformed",
        "unclosed-fence.md",
        f"---\ndevices: [{LIVE_ID}]\n\n# {NO_SOUND} after a crash\n",
    ),
    Case(
        "no-devices",
        "no-devices.md",
        f"---\ntitle: an entry\n---\n\n# {NO_SOUND} in a new set\n",
    ),
    Case(
        "devices-not-a-list",
        "devices-a-string.md",
        f"---\ndevices: {LIVE_ID}\n---\n\n# {NO_SOUND} on one channel\n",
    ),
    Case(
        "no-symptom",
        "two-symptoms.md",
        f"---\ndevices: [{LIVE_ID}]\n---\n\n"
        f"# {NO_SOUND} in session view\n\n# and in arrangement view\n",
    ),
    Case(
        "too-few-causes",
        "one-cause.md",
        malformed(f"{NO_SOUND} while recording", body("the track is deactivated")),
        symptom=f"{NO_SOUND} while recording",
    ),
    Case(
        "too-many-causes",
        "seven-causes.md",
        malformed(
            f"{NO_SOUND} anywhere",
            body(*(f"the {word} is wrong" for word in "one two three four five six seven".split())),
        ),
        symptom=f"{NO_SOUND} anywhere",
    ),
    Case(
        "cause-missing-check",
        "no-check.md",
        malformed(
            f"{NO_SOUND} on playback",
            [Section("the track is deactivated", fixes=[POINTER]), *TWO_CAUSES],
        ),
        symptom=f"{NO_SOUND} on playback",
        cause="the track is deactivated",
    ),
    Case(
        "cause-missing-fix",
        "no-fix.md",
        malformed(
            f"{NO_SOUND} through the interface",
            [Section("the monitor is off", check="the meter is still"), *TWO_CAUSES],
        ),
        symptom=f"{NO_SOUND} through the interface",
        cause="the monitor is off",
    ),
    Case(
        "cause-fix-and-undocumented",
        "fix-and-undocumented.md",
        malformed(
            f"{NO_SOUND} from the pads",
            [
                Section(
                    "the pad is muted",
                    check="the pad is unlit",
                    fixes=[POINTER],
                    undocumented=DIGITAKT_ID,
                ),
                *TWO_CAUSES,
            ],
        ),
        symptom=f"{NO_SOUND} from the pads",
        cause="the pad is muted",
    ),
    Case(
        "pointer-unresolved",
        "bad-section.md",
        malformed(
            f"{NO_SOUND} in a group",
            [cause("the group is deactivated", fix=f"{LIVE_ID} §18.16"), *TWO_CAUSES],
        ),
        symptom=f"{NO_SOUND} in a group",
        cause="the group is deactivated",
    ),
    Case(
        "pointer-authored-target",
        "cites-the-notes.md",
        malformed(
            f"{NO_SOUND} in a return",
            [cause("the return is deactivated", fix="authored/triage §1"), *TWO_CAUSES],
        ),
        symptom=f"{NO_SOUND} in a return",
        cause="the return is deactivated",
    ),
    Case(
        "undocumented-claim-invalid",
        "documented-device.md",
        malformed(
            f"{NO_SOUND} from a clip",
            [
                Section("the clip is empty", check="the slot is blank", undocumented=LIVE_ID),
                *TWO_CAUSES,
            ],
        ),
        symptom=f"{NO_SOUND} from a clip",
        cause="the clip is empty",
    ),
    Case(
        "all-devices-unrecognised",
        "unknown-devices.md",
        entry_file(
            devices=["ableton/live-11"],
            symptom=f"{NO_SOUND} on the old version",
            sections=TWO_CAUSES,
        ),
        symptom=f"{NO_SOUND} on the old version",
    ),
    Case(
        "duplicate-symptom",
        "duplicate-a.md",
        malformed(f"{NO_SOUND} twice over", TWO_CAUSES),
        symptom=f"{NO_SOUND} twice over",
    ),
    Case(
        "duplicate-symptom",
        "duplicate-b.md",
        entry_file(
            devices=[LIVE_ID, "akai/apc-key-25"],
            symptom=f"{NO_SOUND} twice over",
            sections=body("the controller is unmapped", "the bank is wrong"),
        ),
        symptom=f"{NO_SOUND} twice over",
    ),
)
"""One malformed entry per reason constant, plus 1.9's second file: the duplicate is
the one rejection that takes two entries to produce, and both of them are rejected."""

SECOND_GOOD = entry_file(
    devices=[LIVE_ID],
    symptom="a track is distorting",
    sections=body("a device is clipping", "the input gain is too high"),
)


def evaluated(tmp_path: Path):
    """The whole taxonomy in one store, beside two entries that are well-formed."""
    files = {case.name: case.text for case in CASES}
    files["good.md"] = DEFAULT
    files["good-2.md"] = SECOND_GOOD
    return loader(store(tmp_path, files)).evaluate()


def rejection_for(outcome, reason: RejectionReason):
    found = [r for r in outcome.rejections if r.reason == reason]
    assert found, f"nothing produced {reason}"
    return found[0]


def flat(lines: list[str]) -> str:
    """The message as one whitespace-normalised string, so wrapping is invisible."""
    return " ".join(" ".join(lines).split())


# --- The taxonomy is closed (design 'Error Handling') ----------------------


def test_the_store_produces_every_reason_constant_and_no_other(tmp_path: Path) -> None:
    """Fifteen constants, fifteen fixtures. A reason no fixture reaches is a reason
    with no message behind it; a sixteenth reason is one outside the closed set."""
    outcome = evaluated(tmp_path)

    assert {rejection.reason for rejection in outcome.rejections} == set(REASONS)


def test_each_fixture_is_rejected_for_its_own_reason(tmp_path: Path) -> None:
    """Per file, so a fixture that rejects for the right reason by accident fails."""
    outcome = evaluated(tmp_path)
    by_file = {r.source_file.name: r.reason for r in outcome.rejections}

    assert by_file == {case.name: case.reason for case in CASES}


# --- 5.3: a message the author can act on ---------------------------------


def test_every_message_names_the_file(tmp_path: Path) -> None:
    """The only handle that always exists — a frontmatter rejection has no symptom."""
    outcome = evaluated(tmp_path)

    for rejection in outcome.rejections:
        assert rejection.source_file.as_posix() in flat(messages.lines(rejection))


def test_every_message_names_the_symptom_and_the_cause_concerned(tmp_path: Path) -> None:
    """5.3, per fixture: where the parse knew the symptom the message carries it, and
    where the fault is in one cause the message names that cause."""
    outcome = evaluated(tmp_path)
    by_file = {r.source_file.name: r for r in outcome.rejections}

    for case in CASES:
        text = flat(messages.lines(by_file[case.name]))
        if case.symptom is not None:
            assert case.symptom in text, f"{case.reason} does not name the symptom"
        if case.cause is not None:
            assert case.cause in text, f"{case.reason} does not name the cause"


def test_no_message_is_an_internal_error_name(tmp_path: Path) -> None:
    """5.3's floor: the reason constants are the program's vocabulary, not the
    author's, and none of them is printed at all."""
    outcome = evaluated(tmp_path)

    # Over the detail rather than the whole block: a file the author happened to name
    # after the fault is their word for it, not the program's.
    for rejection in outcome.rejections:
        assert rejection.reason not in rejection.detail
        assert len(rejection.detail.split()) > 8, "a message is prose, not a token"


def test_a_pointer_message_offers_the_nearest_sections(tmp_path: Path) -> None:
    """The 5.3 example verbatim: the number that does not resolve, and the numbers
    that do, so the correction is a copy rather than a search through the manual."""
    outcome = evaluated(tmp_path)
    text = flat(messages.lines(rejection_for(outcome, "pointer-unresolved")))

    assert f"{LIVE_ID} §18.16" in text
    assert "Nearest:" in text
    assert "§18.1" in text


def test_a_duplicate_message_names_the_other_file_and_the_shared_device(
    tmp_path: Path,
) -> None:
    """1.9 rejects both and picks neither, so each message has to say what it clashed
    with — the file, and the device the two scopes share."""
    outcome = evaluated(tmp_path)
    text = flat(messages.lines(rejection_for(outcome, "duplicate-symptom")))

    assert "duplicate-b.md" in text or "duplicate-a.md" in text
    assert LIVE_ID in text


def test_a_flag_reads_as_a_remark_rather_than_a_withdrawal(tmp_path: Path) -> None:
    """The design's second worked message. `flagged:` is the whole difference on
    screen, and it is the difference between an entry served and an entry gone."""
    text = entry_file(
        devices=[LIVE_ID],
        symptom="a track is distorting",
        sections=[
            Section("a device is clipping", check="the Drum Buss meter is red", fixes=[POINTER]),
            cause("the input gain is too high"),
        ],
    )
    outcome = loader(store(tmp_path, {"entry.md": text})).evaluate()

    (flag,) = [f for f in outcome.flags if f.name == "term-not-in-passage"]
    lines = messages.lines(flag)
    assert lines[0] == 'triage/entry.md — "a track is distorting"'
    assert flat(lines[1:]).startswith("flagged:")
    assert "Drum Buss" in flat(lines)


def test_a_message_block_leads_with_the_file_and_the_symptom(tmp_path: Path) -> None:
    """The design's layout: one header line, then the indented prose beneath it."""
    outcome = evaluated(tmp_path)
    lines = messages.lines(rejection_for(outcome, "pointer-unresolved"))

    assert lines[0] == f'triage/bad-section.md — "{NO_SOUND} in a group"'
    assert all(line.startswith("  ") for line in lines[1:])
    assert lines[1].lstrip().startswith("rejected:")


def test_a_message_with_no_symptom_names_the_file_alone(tmp_path: Path) -> None:
    """A frontmatter rejection happens before the H1 is read. Inventing a symptom
    would be a claim about a file that never stated one."""
    outcome = evaluated(tmp_path)
    lines = messages.lines(rejection_for(outcome, "frontmatter-missing"))

    assert lines[0] == "triage/no-fence.md"


# --- 5.2: a rejection costs one entry -------------------------------------


def test_the_other_entries_in_the_run_still_ingest(tmp_path: Path) -> None:
    """Sixteen malformed files, two good ones, and the good ones are served."""
    outcome = evaluated(tmp_path)

    assert sorted(o.entry.source_file.name for o in outcome.ingesting) == ["good-2.md", "good.md"]


def test_the_run_succeeds_with_rejections_in_it(tmp_path: Path) -> None:
    """5.2: the source is not rejected while an entry survives, and the run reports
    success. One bad entry costs the author that entry and nothing else."""
    files = {case.name: case.text for case in CASES}
    files["good.md"] = DEFAULT
    result = loader(store(tmp_path, files)).load(DISCOVERED)

    assert result.rejection is None
    assert len(result.regions) == 1


def test_only_a_store_where_nothing_survives_rejects_the_source(tmp_path: Path) -> None:
    """`authored-invalid`: a source with no passages is not a source, and the detail
    names the reasons rather than leaving the store looking empty."""
    files = {case.name: case.text for case in CASES}
    result = loader(store(tmp_path, files)).load(DISCOVERED)

    assert result.rejection is not None
    assert result.rejection.reason == "authored-invalid"


# --- 5.5: the per-run counts, with a reason for each ----------------------


def test_the_run_counts_entries_ingested_rejected_and_flagged(tmp_path: Path) -> None:
    """The counts line. Ingested is entries, not passages: an entry over the chunker's
    cap is one entry the author wrote and one row in the report."""
    outcome = evaluated(tmp_path)
    line = messages.counts(outcome)

    assert line == f"2 entries ingested, {len(CASES)} rejected, 0 flagged"


def test_the_report_carries_a_reason_for_every_rejection_and_flag(tmp_path: Path) -> None:
    """5.5's second half. The counts alone say how much went wrong; the blocks say
    what, and the report is the two together."""
    files = {case.name: case.text for case in CASES}
    files["good.md"] = DEFAULT
    files["flagged.md"] = entry_file(
        devices=[LIVE_ID, "ableton/live-11"],
        symptom="a track is distorting",
        sections=body("a device is clipping", "the input gain is too high"),
    )
    outcome = loader(store(tmp_path, files)).evaluate()
    lines = messages.store_lines(outcome)

    assert lines[0] == f"2 entries ingested, {len(CASES)} rejected, 1 flagged"
    text = flat(lines)
    for rejection in outcome.rejections:
        assert rejection.detail.split(".")[0] in text
    for flag in outcome.flags:
        assert flag.detail.split(".")[0] in text


def test_a_flagged_entry_is_counted_once_however_many_flags_it_carries(
    tmp_path: Path,
) -> None:
    """5.5 counts entries, and an entry with two remarks about it is one entry the
    author has to look at."""
    text = entry_file(
        devices=[LIVE_ID, "ableton/live-11", "akai/apc-key-49"],
        symptom="a track is distorting",
        sections=body("a device is clipping", "the input gain is too high"),
    )
    outcome = loader(store(tmp_path, {"entry.md": text})).evaluate()

    assert len(outcome.flags) == 2
    assert messages.counts(outcome) == "1 entry ingested, 0 rejected, 1 flagged"


def test_a_missing_ledger_says_so_in_one_line(tmp_path: Path) -> None:
    """Deleting the ledger re-arms 2.2 for the whole store. That must not be silent:
    the author would otherwise meet a wall of rejections with nothing explaining them."""
    outcome = loader(store(tmp_path, {"good.md": DEFAULT})).evaluate()
    lines = messages.store_lines(outcome, ledger_missing=True)

    assert any(LEDGER_NAME in line for line in lines)
    assert not any(LEDGER_NAME in line for line in messages.store_lines(outcome))
