"""The coverage report — §6, 8.6 and 8.7.

There is no enumerable universe of symptoms, so the report has **no denominator and
states no percentage**. It is an inventory of what exists plus the one gap that is
enumerable, the rig side (6.3): every entry with its scope, cause count and pointer
health; every rejection and flag, so the report covers the whole store rather than
only what was ingested (6.2); every rig device no entry declares scope for; every
cause 2.3 permits to carry no pointer; every entry whose pointer has drifted (8.6);
and every entry scoped only to gear the rig no longer holds (8.7) — reported, and
never deleted.

The same rows land in the sidecar's `report` block, which is what makes the report
obtainable without asking a question (6.5) and puts it where a consumer can read it
(6.6's publishing half).
"""

from __future__ import annotations

from pathlib import Path

from fixture_rig import RIG
from rendering import Section, entry_file
from stores import (
    APC_ID,
    DEFAULT,
    DIGITAKT_ID,
    DISCOVERED,
    DRIFTING,
    LIVE_ID,
    POINTER,
    drifted_view,
    loader,
    store,
)

from dawmans import cli
from dawmans.triage.coverage import coverage
from dawmans.triage.model import Pointer
from dawmans.triage.pointers import Ledger, LedgerRow, pointer_key

TR8S = "roland/tr-8s"
"""Documented by an ingested manual and absent from the fixture rig — 8.7's shape:
gear removed from the inventory, with its entries still in the store."""


def cause(statement: str, *, fix: str = POINTER) -> Section:
    return Section(statement, check="the track's number is unlit", fixes=[fix])


TWO_CAUSES = [cause("the track is deactivated"), cause("another track is soloed")]


def entry(symptom: str, *, devices: list[str] | None = None, sections=None) -> str:
    return entry_file(
        devices=devices or [LIVE_ID],
        symptom=symptom,
        sections=sections or TWO_CAUSES,
    )


def report_of(tmp_path: Path, files: dict[str, str], **kwargs):
    store_path = store(tmp_path, files)
    return coverage(loader(store_path, **kwargs).evaluate(), RIG)


def text_of(report) -> str:
    return " ".join(" ".join(report.lines()).split())


def seeded_ledger() -> Ledger:
    """A ledger that has seen the drifting pointer, so it flags rather than rejects."""
    pointer = Pointer(source_id=LIVE_ID, section_number="18.6", section_title=None, line=1)
    return Ledger([LedgerRow(pointer_key(pointer), "2026-08-01T00:00:00Z", ("gone",), ())])


DRIFTED_ENTRY = entry_file(
    devices=[LIVE_ID],
    symptom="a track is silent",
    sections=[cause("the track is soloed elsewhere", fix=DRIFTING), cause("the track is muted")],
)


# --- 6.1: every entry, with its scope, its causes and its pointer health ---


def test_an_entry_row_carries_its_symptom_scope_and_cause_count(tmp_path: Path) -> None:
    report = report_of(tmp_path, {"no-sound.md": DEFAULT})

    (row,) = report.entries
    assert row.symptom == "No sound from a track"
    assert row.source_file == "triage/no-sound.md"
    assert row.devices == (LIVE_ID,)
    assert row.causes == 2
    assert row.pointers_resolve is True


def test_an_entry_row_says_when_a_pointer_no_longer_resolves(tmp_path: Path) -> None:
    """ "Currently resolves" is this run's answer, not a recorded one: the pointer is
    re-checked on every pass, which is the whole of 2.1."""
    report = report_of(
        tmp_path,
        {"drifting.md": DRIFTED_ENTRY},
        corpus=drifted_view(),
        ledger=seeded_ledger(),
    )

    (row,) = report.entries
    assert row.pointers_resolve is False


def test_a_rejected_entry_is_not_an_entry_row(tmp_path: Path) -> None:
    """It is a rejection row instead. An entry that will not be served is not part of
    the inventory of what the store covers."""
    report = report_of(tmp_path, {"good.md": DEFAULT, "bad.md": "# no frontmatter\n"})

    assert [row.source_file for row in report.entries] == ["triage/good.md"]
    assert [r.source_file.as_posix() for r in report.rejections] == ["triage/bad.md"]


# --- 6.2: the report covers the whole store -------------------------------


def test_every_file_in_the_store_is_accounted_for(tmp_path: Path) -> None:
    """100% of the store, which is 6.2's actual measure — not a percentage of an
    unknowable universe of symptoms."""
    files = {
        "good.md": DEFAULT,
        "bad.md": "# no frontmatter\n",
        "flagged.md": entry("a track is distorting", devices=[LIVE_ID, "ableton/live-11"]),
    }
    report = report_of(tmp_path, files)

    accounted = {row.source_file for row in report.entries}
    accounted |= {r.source_file.as_posix() for r in report.rejections}
    assert accounted == {f"triage/{name}" for name in files}


def test_every_rejection_and_flag_is_rendered_with_its_reason(tmp_path: Path) -> None:
    files = {"good.md": DEFAULT, "bad.md": "# no frontmatter\n"}
    files["flagged.md"] = entry("a track is distorting", devices=[LIVE_ID, "ableton/live-11"])
    report = report_of(tmp_path, files)

    text = text_of(report)
    assert "rejected: an entry starts with a `---` fence" in text
    assert "flagged: `devices:` names `ableton/live-11`" in text


def test_the_report_states_no_percentage(tmp_path: Path) -> None:
    """There is no denominator over symptoms. A number with a `%` beside it here would
    be a completeness claim nobody can make (design §Coverage without a taxonomy)."""
    report = report_of(tmp_path, {"good.md": DEFAULT, "bad.md": "# no frontmatter\n"})

    assert "%" not in text_of(report)


# --- 6.3: the one enumerable gap, the rig side ----------------------------


def test_rig_devices_no_entry_declares_scope_for_are_listed(tmp_path: Path) -> None:
    report = report_of(tmp_path, {"no-sound.md": DEFAULT})

    assert LIVE_ID not in report.uncovered_devices
    assert DIGITAKT_ID in report.uncovered_devices
    assert APC_ID in report.uncovered_devices


def test_a_device_scoped_only_by_a_rejected_entry_is_still_uncovered(
    tmp_path: Path,
) -> None:
    """The entry is not served, so the device has no triage covering it. Counting a
    rejected entry's declarations would report a gap as closed by an entry no question
    can reach."""
    files = {
        "no-sound.md": DEFAULT,
        "apc.md": entry("a pad is unlit", devices=[APC_ID], sections=[cause("only one cause")]),
    }
    report = report_of(tmp_path, files)

    assert APC_ID in report.uncovered_devices


def test_the_rig_side_is_the_only_gap_the_report_enumerates(tmp_path: Path) -> None:
    """Every rig device covered means an empty list, not a claim of completeness."""
    devices = [device.id for device in RIG]
    report = report_of(tmp_path, {"all.md": entry("a track is silent", devices=devices)})

    assert report.uncovered_devices == ()


# --- 6.4: causes 2.3 permits to carry no pointer --------------------------


def test_a_cause_without_a_pointer_is_reported_with_the_device_it_names(
    tmp_path: Path,
) -> None:
    """The fixture rig, because the live one cannot produce this row: every device the
    real rig holds is documented today."""
    text = entry(
        "no sound from the sampler",
        devices=[LIVE_ID, DIGITAKT_ID],
        sections=[
            cause("the track is deactivated"),
            Section("its output is muted", check="the level is at zero", undocumented=DIGITAKT_ID),
        ],
    )
    report = report_of(tmp_path, {"sampler.md": text})

    (row,) = report.causes_without_pointer
    assert row.source_file == "triage/sampler.md"
    assert row.symptom == "no sound from the sampler"
    assert row.cause == "its output is muted"
    assert row.device == DIGITAKT_ID


def test_a_backed_cause_is_not_reported_as_unbacked(tmp_path: Path) -> None:
    report = report_of(tmp_path, {"no-sound.md": DEFAULT})

    assert report.causes_without_pointer == ()


# --- 8.6: drift, with the source that changed -----------------------------


def test_a_drifted_entry_is_listed_with_the_source_that_changed(tmp_path: Path) -> None:
    """8.6. The source is what the author has to go and look at: the manual moved, and
    the entry is still being served with the cause marked unbacked (8.5)."""
    report = report_of(
        tmp_path,
        {"drifting.md": DRIFTED_ENTRY},
        corpus=drifted_view(),
        ledger=seeded_ledger(),
    )

    (row,) = report.drifted
    assert row.source_file == "triage/drifting.md"
    assert row.cause == "the track is soloed elsewhere"
    assert row.source_id == LIVE_ID
    assert row.pointer == DRIFTING


def test_a_drifted_entry_is_still_an_entry_row(tmp_path: Path) -> None:
    """It is served, so it is inventory as well as drift — the two rows are different
    questions about the same entry."""
    report = report_of(
        tmp_path,
        {"drifting.md": DRIFTED_ENTRY},
        corpus=drifted_view(),
        ledger=seeded_ledger(),
    )

    assert len(report.entries) == 1
    assert len(report.drifted) == 1


# --- 8.7: gear the rig no longer holds ------------------------------------


def test_an_entry_scoped_only_to_a_device_outside_the_rig_is_reported(
    tmp_path: Path,
) -> None:
    """8.7. The device left `rig.yaml` and the entry stayed behind; it may also be a
    manual that arrived ahead of its rig entry, which is why this is a report and not
    a rejection."""
    report = report_of(tmp_path, {"drums.md": entry("a drum sound is missing", devices=[TR8S])})

    (row,) = report.orphaned
    assert row.source_file == "triage/drums.md"
    assert row.devices == (TR8S,)


def test_an_orphaned_entry_is_never_deleted(tmp_path: Path) -> None:
    """8.7's second half, which is the load-bearing one: it still ingests, still emits
    a passage, and is still in the inventory."""
    result = loader(
        store(tmp_path, {"drums.md": entry("a drum sound is missing", devices=[TR8S])})
    ).load(DISCOVERED)

    assert result.rejection is None
    assert len(result.regions) == 1


def test_an_entry_with_one_device_still_in_the_rig_is_not_orphaned(tmp_path: Path) -> None:
    """Only an entry scoped **entirely** to gear that has gone. One live device is
    enough to keep the entry answering questions about the rig as it now stands."""
    report = report_of(
        tmp_path, {"drums.md": entry("a drum sound is missing", devices=[TR8S, LIVE_ID])}
    )

    assert report.orphaned == ()


# --- 6.5 and 6.6: where the report is obtainable --------------------------


def test_the_same_rows_land_in_the_sidecar_report_block(tmp_path: Path) -> None:
    """6.5 and 6.6's publishing half: the report is written where a consumer reads it,
    keyed to the view it describes, rather than existing only on a terminal."""
    files = {"no-sound.md": DEFAULT, "bad.md": "# no frontmatter\n"}
    store_path = store(tmp_path, files)
    result = loader(store_path).load(DISCOVERED)

    assert result.sidecar is not None
    published = result.sidecar["report"]["coverage"]
    assert published == coverage(loader(store_path).evaluate(), RIG).to_dict()
    assert published["entries"][0]["symptom"] == "No sound from a track"


def test_the_report_block_carries_the_rejections_beside_the_coverage_rows(
    tmp_path: Path,
) -> None:
    """The rejection and flag rows are the report block's own (5.5) and are not copied
    into the coverage rows: one file, one copy of each row, and the two together are
    6.2's whole store."""
    result = loader(store(tmp_path, {"good.md": DEFAULT, "bad.md": "# no fence\n"})).load(
        DISCOVERED
    )

    assert result.sidecar is not None
    block = result.sidecar["report"]
    assert [row["reason"] for row in block["rejections"]] == ["frontmatter-missing"]
    assert "rejections" not in block["coverage"]


def test_dawmans_coverage_renders_the_report_to_stdout(tmp_path: Path, capsys) -> None:
    """6.5: obtainable without asking a question, and outside a session."""
    from runs import ENTRY, run, write

    write(tmp_path, {"no-sound.md": ENTRY})
    run(tmp_path)

    code = cli.main(["--root", str(tmp_path), "coverage"])

    out = capsys.readouterr().out
    assert code == 0
    assert "No sound from a track" in out
    assert "%" not in out


def test_dawmans_coverage_writes_nothing(tmp_path: Path) -> None:
    """A report is a reading of the store, not a run over it: no ledger row, no shard,
    no view — the same rule `dawmans validate` follows (5.4)."""
    from runs import ENTRY, run, write

    write(tmp_path, {"no-sound.md": ENTRY})
    run(tmp_path)
    before = {
        path.relative_to(tmp_path).as_posix(): path.read_bytes()
        for path in sorted(tmp_path.rglob("*"))
        if path.is_file()
    }

    cli.main(["--root", str(tmp_path), "coverage"])

    after = {
        path.relative_to(tmp_path).as_posix(): path.read_bytes()
        for path in sorted(tmp_path.rglob("*"))
        if path.is_file()
    }
    assert after == before
