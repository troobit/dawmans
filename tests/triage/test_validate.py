"""`dawmans validate` over the entry store — 5.4, 2.6, and Decision 5.

Validate is the author's loop: it parses, resolves and term-checks the whole store
against the committed view and reports, **while modifying nothing**. That is 5.4's
whole point — checking work before committing to it — and it is what keeps the
command from promoting a broken pointer to "previously fine" (design §Reject versus
flag): no index write, no shard, no ledger row, no embedding.

Two exit codes are load-bearing:

- **A term miss exits non-zero here and never under ingest** (Decision 5, design §The
  term check). The author is present at validate time, so the consequence costs a
  re-read; the user is present at ingest time, so it costs nothing there.
- **A rejection exits non-zero here too.** 5.2's "the run reports succeeded" is about
  the ingestion run: an entry excluded still leaves the corpus servable. `validate`
  is the command asked whether the store is right, and answering "yes" while naming
  an entry that will not be served is the one answer it must not give.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from rendering import Section, entry_file
from runs import ENTRY, RIG, StubManuals, run, write
from stores import LIVE_ID, POINTER

from dawmans import cli
from dawmans.corpus.rig import RIG_FILE
from dawmans.triage.pointers import LEDGER_NAME

TERM_MISS = entry_file(
    devices=[LIVE_ID],
    symptom="A track is distorting",
    sections=[
        # `Drum Buss` is a real Live device and §18.1 "The Live Mixer" does not print
        # it: a factual claim resting on a pointer that does not carry it (2.6).
        Section("A device is clipping", check="the Drum Buss meter is red", fixes=[POINTER]),
        Section("The input gain is too high", check="the meter is red", fixes=[POINTER]),
    ],
)


def validate(root: Path) -> tuple[int, list[str]]:
    return cli.run_validate(root / "index", root=root)


def snapshot(root: Path) -> dict[str, bytes]:
    """Every file under `root`, by relative path — the whole of what a run may write."""
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def rig_file(root: Path) -> None:
    """The real `rig.yaml` beside the store, since `validate` reads it from disk."""
    devices = "\n".join(
        f"  - id: {device.id}\n    display_name: {device.display_name}\n"
        f"    revision: {device.revision}"
        for device in RIG.devices
    )
    (root / RIG_FILE).write_text(f"devices:\n{devices}\n", encoding="utf-8")


@pytest.fixture
def ingested(tmp_path: Path) -> Path:
    """A committed index over the fixture manuals, with one well-formed entry in it."""
    write(tmp_path, {"no-sound.md": ENTRY})
    rig_file(tmp_path)
    run(tmp_path)
    return tmp_path


# --- The store is validated (5.4) -----------------------------------------


def test_validate_reports_the_entry_store_beside_the_index(ingested: Path) -> None:
    """The counts line of 5.5, over the same store `ingest` would read."""
    code, lines = validate(ingested)

    assert code == 0, lines
    assert "1 entry ingested, 0 rejected, 0 flagged" in lines


def test_validate_resolves_pointers_against_the_committed_view(ingested: Path) -> None:
    """The view is read through `manifest.view_dir`, which is the only switch the
    corpus provides: a pointer resolves against the passages a reader would retrieve,
    not against a shard that may not have been merged."""
    write(ingested, {"second.md": TERM_MISS})

    code, lines = validate(ingested)

    assert code == 1
    # Both entries parsed and both resolved; what failed is the term check alone.
    assert "2 entries ingested, 0 rejected, 1 flagged" in lines


def test_validate_reads_an_entry_added_since_the_last_ingest(ingested: Path) -> None:
    """5.1 from the author's side: the store is a directory, read on every command."""
    write(
        ingested,
        {
            "bad.md": entry_file(
                devices=[LIVE_ID],
                symptom="A pad triggers the wrong sound",
                sections=[
                    Section("the pad is unmapped", check="the note is wrong", fixes=[POINTER]),
                    Section("the channel is wrong", check="the meter is still", fixes=[POINTER]),
                ],
                frontmatter_extra={"unknown": "x"},
            )
        },
    )

    code, lines = validate(ingested)

    assert code == 0, lines
    assert "2 entries ingested, 0 rejected, 1 flagged" in lines


def test_a_rejection_is_named_and_fails_the_command(ingested: Path) -> None:
    """5.3's message, on the command whose whole purpose is to deliver it before the
    author has committed anything."""
    broken = ENTRY.replace(POINTER, f"{LIVE_ID} §18.16").replace(
        "# No sound from a track", "# No sound from a return"
    )
    write(ingested, {"broken.md": broken})

    code, lines = validate(ingested)

    assert code == 1
    text = " ".join(" ".join(lines).split())
    assert "triage/broken.md" in text
    assert "§18.16" in text
    assert "Nearest:" in text


# --- It modifies nothing (5.4) --------------------------------------------


def test_validate_writes_nothing_at_all(ingested: Path) -> None:
    """No index write, no shard, no view, no ledger row. Snapshotted over the whole
    tree rather than over the files this implementation happens to touch."""
    before = snapshot(ingested)

    code, _ = validate(ingested)

    assert code == 0
    assert snapshot(ingested) == before


def test_validate_never_writes_the_ledger_even_where_a_pointer_resolves(
    ingested: Path,
) -> None:
    """Recording is `dawmans ingest`'s move alone. Validating a store whose ledger has
    been deleted must not re-create it: the file is the claim that a pointer once
    resolved, and only a run that served the entry may make that claim."""
    (ingested / "triage" / LEDGER_NAME).unlink()

    code, lines = validate(ingested)

    assert not (ingested / "triage" / LEDGER_NAME).exists()
    assert code == 0, lines
    assert any(LEDGER_NAME in line for line in lines), "a missing ledger is never silent"


def test_validate_loads_no_embedding_model(ingested: Path, monkeypatch) -> None:
    """5.4 again, and the reason the cold model load does not reach this command: an
    embedder is loaded to *write* vectors, and validate writes nothing."""

    def refuse() -> None:
        raise AssertionError("validate loaded the embedding model")

    monkeypatch.setattr(cli, "load_embedder", refuse)

    code, _ = validate(ingested)

    assert code == 0


# --- The term miss, and where its consequence falls (Decision 5) ----------


def test_a_term_miss_exits_non_zero_under_validate(ingested: Path) -> None:
    """The gap 2.6's flag leaves is closed here, where the author is present: a
    non-zero exit costs a re-read rather than a caveat on every citation."""
    write(ingested, {"distorting.md": TERM_MISS})

    code, lines = validate(ingested)

    assert code == 1
    text = " ".join(" ".join(lines).split())
    assert "Drum Buss" in text


def test_the_same_term_miss_never_fails_an_ingestion_run(ingested: Path) -> None:
    """Consequences where the author is, none where the user is. The entry is served,
    the cause is not marked `unbacked` — the pointer resolved — and the run succeeds."""
    write(ingested, {"distorting.md": TERM_MISS})

    result, _ = run(ingested)

    assert result.exit_code == 0
    assert result.report.succeeded


def test_a_flag_that_is_not_a_term_miss_leaves_validate_at_zero(ingested: Path) -> None:
    """Only the term miss is promoted. A drifted pointer is 8.4's flag: the entry is
    served with the cause marked unbacked, and that is the state the design chose over
    withdrawing working triage — so validate reports it and does not fail on it."""
    run(ingested, manuals=StubManuals(dropped=(POINTER,)))

    code, lines = validate(ingested)

    text = " ".join(" ".join(lines).split())
    assert "resolved on an earlier run and does not now" in text
    assert code == 0, lines


# --- The failures -----------------------------------------------------------


def test_an_unparseable_ledger_fails_validate_naming_the_line(ingested: Path) -> None:
    """A failure, not a rejection: no entry is at fault, and reading on would re-arm
    2.2 for the whole store."""
    (ingested / "triage" / LEDGER_NAME).write_text("{not json\n", encoding="utf-8")

    code, lines = validate(ingested)

    assert code == 1
    assert any("line 1" in line for line in lines)


def test_an_absent_store_is_reported_rather_than_failing(ingested: Path) -> None:
    """An absent store is an unknown discovery set (1.4), not a fault of the index."""
    for path in (ingested / "triage").iterdir():
        path.unlink()
    (ingested / "triage").rmdir()

    code, lines = validate(ingested)

    assert code == 0
    assert any("triage" in line for line in lines)


def test_validate_still_reports_the_index_first(ingested: Path) -> None:
    """The command answers about both, and the index is what a reader loads first."""
    _, lines = validate(ingested)

    assert "corpus_revision" in " ".join(lines)


def test_a_missing_manifest_is_reported_without_reading_the_store(tmp_path: Path) -> None:
    """Nothing can be validated against a view that does not exist: every pointer would
    report as unresolved, which says nothing about the entries."""
    write(tmp_path, {"no-sound.md": ENTRY})

    code, lines = validate(tmp_path)

    assert code == 1
    assert "no manifest" in "\n".join(lines)
    assert not any("ingested," in line for line in lines)


# --- The command line -------------------------------------------------------


def test_the_command_passes_its_root_to_the_store(ingested: Path, capsys) -> None:
    """`--root` is where `triage/` and `rig.yaml` live. A validate that read the index
    alone would exit zero over a store it never opened."""
    write(ingested, {"distorting.md": TERM_MISS})

    code = cli.main(["--root", str(ingested), "validate"])

    assert code == 1
    assert "Drum Buss" in capsys.readouterr().out
