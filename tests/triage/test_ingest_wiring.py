"""`TriageLoader` inside a real ingestion run — 1.6, 2.1, 5.1, 5.7.

`tests/test_run.py` exercises the orchestration against a *stub* authored store, which is
what makes 12.2 structural rather than a claim about one loader. This is the other half:
the real `TriageLoader` behind the same seam, so the three things only the wiring can be
wrong about are observable.

- **The pass ordering.** The authored load runs after every vendor shard has committed,
  so a pointer resolves against the passages *this* run produced. A first run over an
  empty index would otherwise reject every entry under 2.2 for pointing at a manual that
  was ingested moments earlier.
- **The exemption.** The authored store is not skipped on an unchanged fingerprint, so a
  manual edited underneath a working entry is caught on the next run rather than one run
  late (design §Discovery, fingerprint and the run budget).
- **Where the sidecar lands.** `views/<hex>/reports/authored_triage.json` — the corpus's
  slug rule, underscore and not hyphen. A reader following the wrong name finds nothing
  and no error is raised.

The vendor store is a stub over the committed section fixtures, so no PDF is opened; the
embedder is the deterministic stand-in the index tests use. Both live in `runs.py`, which
`test_validate.py` shares — a command that reads a committed view has to have one.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from rendering import Section, entry_file
from runs import ENTRY, StubManuals, authored_rows, run, view_of, write
from stores import LIVE_ID, POINTER

from dawmans.records import AUTHORED_SOURCE_ID
from dawmans.triage.pointers import LEDGER_NAME

# --- The pass ordering -----------------------------------------------------


def test_a_first_run_resolves_against_the_manuals_it_has_just_ingested(tmp_path: Path) -> None:
    """2.1. The authored load runs after every vendor shard commits, so an entry written
    against a manual ingested by the same run is not rejected for pointing at nothing."""
    write(tmp_path, {"no-sound.md": ENTRY})

    result, _ = run(tmp_path)

    assert result.report.succeeded
    assert result.report.line_for(AUTHORED_SOURCE_ID).endswith("ingested")
    assert len(authored_rows(tmp_path / "index")) == 1


def test_the_sidecar_lands_inside_the_view_under_the_slug(tmp_path: Path) -> None:
    """`views/<hex>/reports/authored_triage.json`: underscore, not hyphen, and inside the
    view so it swaps atomically with the passages it keys."""
    write(tmp_path, {"no-sound.md": ENTRY})

    run(tmp_path)

    path = view_of(tmp_path / "index") / "reports" / "authored_triage.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    emitted = {row["passage_id"] for row in authored_rows(tmp_path / "index")}
    assert {row["passage_id"] for row in payload["passages"]} == emitted
    assert payload["report"]["entries"] == 1


def test_the_ledger_is_written_and_a_no_change_run_leaves_it_byte_identical(
    tmp_path: Path,
) -> None:
    """`record` writes only on transition, so a run that changes nothing leaves the
    working tree clean — the only reason a committed machine-written file is tolerable."""
    store = write(tmp_path, {"no-sound.md": ENTRY})

    run(tmp_path)
    first = (store / LEDGER_NAME).read_bytes()
    run(tmp_path)

    assert POINTER in first.decode("utf-8")  # one row per pointer, keyed by the pointer
    assert (store / LEDGER_NAME).read_bytes() == first


# --- The exemption ---------------------------------------------------------


def test_the_authored_store_is_never_skipped_as_unchanged(tmp_path: Path) -> None:
    """A fingerprint over the store's own bytes cannot say whether a pointer still
    resolves, so the authored source is exempt from shard skipping — while the manuals,
    whose bytes did not change either, are skipped."""
    write(tmp_path, {"no-sound.md": ENTRY})
    run(tmp_path)

    result, manuals = run(tmp_path)

    assert result.report.line_for(AUTHORED_SOURCE_ID).endswith("ingested")
    assert result.report.line_for(LIVE_ID).endswith("skipped as unchanged")
    assert manuals.loaded == []  # 5.7: no manual is re-extracted or re-chunked


def test_a_manual_moving_under_a_working_entry_is_caught_on_the_next_run(
    tmp_path: Path,
) -> None:
    """8.4 end to end. The entry once resolved, so it is served with the cause marked
    unbacked rather than withdrawn (8.5), and the run still succeeds."""
    write(tmp_path, {"no-sound.md": ENTRY})
    run(tmp_path)

    result, _ = run(tmp_path, manuals=StubManuals(dropped=(POINTER,)))

    assert result.report.succeeded
    rows = authored_rows(tmp_path / "index")
    assert len(rows) == 1
    assert rows[0]["unbacked"] is True

    payload = json.loads(
        (view_of(tmp_path / "index") / "reports" / "authored_triage.json").read_text("utf-8")
    )
    assert payload["report"]["pointers"]["unresolved"] == 2
    assert {flag["name"] for flag in payload["report"]["flags"]} == {"pointer-drifted"}


# --- 5.1: the store is read on every run -----------------------------------


def test_an_entry_added_between_runs_is_ingested(tmp_path: Path) -> None:
    write(tmp_path, {"no-sound.md": ENTRY})
    run(tmp_path)

    write(
        tmp_path,
        {
            "nested/distorting.md": entry_file(
                devices=[LIVE_ID],
                symptom="A track is distorting",
                sections=[
                    Section("The gain is too high", check="the meter is red", fixes=[POINTER]),
                    Section("A device is clipping", check="its meter is red", fixes=[POINTER]),
                ],
            )
        },
    )
    result, _ = run(tmp_path)

    assert result.report.succeeded
    assert len(authored_rows(tmp_path / "index")) == 2


def test_an_entry_removed_between_runs_leaves_the_index(tmp_path: Path) -> None:
    store = write(tmp_path, {"no-sound.md": ENTRY})
    run(tmp_path)

    (store / "no-sound.md").unlink()
    result, _ = run(tmp_path)

    assert result.report.succeeded
    assert authored_rows(tmp_path / "index") == []


def test_a_store_whose_every_entry_is_malformed_stops_serving_the_previous_run(
    tmp_path: Path,
) -> None:
    """`authored-invalid` deletes the shard. Left in place, the store would keep serving
    the previous run's passages while the run reported the rejection and succeeded."""
    store = write(tmp_path, {"no-sound.md": ENTRY})
    run(tmp_path)
    assert authored_rows(tmp_path / "index")

    (store / "no-sound.md").write_text("# No frontmatter at all\n", encoding="utf-8")
    result, _ = run(tmp_path)

    assert result.report.succeeded  # a rejection is reported, and the run still succeeds
    assert "authored-invalid" in result.report.line_for(AUTHORED_SOURCE_ID)
    assert authored_rows(tmp_path / "index") == []


def test_an_absent_store_retains_the_authored_shard(tmp_path: Path) -> None:
    """An absent store is an unknown discovery set, not an empty one (1.4)."""
    store = write(tmp_path, {"no-sound.md": ENTRY})
    run(tmp_path)

    shutil.rmtree(store)  # the ledger goes with it — the whole store is gone
    result, _ = run(tmp_path)

    assert result.report.succeeded
    assert "triage" in result.report.unavailable_stores
    assert len(authored_rows(tmp_path / "index")) == 1


def test_an_unparseable_ledger_fails_the_run_and_keeps_the_shard(tmp_path: Path) -> None:
    """A failure, not a rejection: no entry is at fault, and continuing would re-arm 2.2
    for the whole store and reject entries 8.4 requires be served with a mark."""
    store = write(tmp_path, {"no-sound.md": ENTRY})
    run(tmp_path)

    (store / LEDGER_NAME).write_text("{not json\n", encoding="utf-8")
    result, _ = run(tmp_path)

    assert result.exit_code == 1
    assert any("line 1" in failure.message for failure in result.report.failures)
    assert len(authored_rows(tmp_path / "index")) == 1  # the previous shard stands
