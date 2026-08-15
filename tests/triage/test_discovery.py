"""Discovery and the unconditional load — design §The store on disk, §Discovery.

The store is **one source** however many files it holds, so `discover()` yields nought or
one. What a scan has to be right about is narrower than it looks:

- it is **recursive**, or `triage/live/no-sound.md` is invisible with nothing to report;
- a non-`.md` file gets a **report line** — the opposite of `manuals/`, where the skip is
  silent — because a `no-sound.txt` the author expected to be ingested must not disappear
  quietly, while a dotfile is exempt so the machine's own ledger does not warn about
  itself every run;
- an **absent** store is not an **empty** one: the first is an unknown discovery set that
  removes nothing, the second is an empty one that removes the shard.

`load()` runs on every ingest whatever the fingerprint says (2.1). The exemption itself
lives in the run orchestration and is asserted in `test_ingest_wiring.py`; what is
asserted here is the half this module owns — that nothing in the loader consults the
fingerprint it is handed.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest
from rendering import Section, entry_file
from stores import DEFAULT, DIGITAKT_ID, LIVE_ID, POINTER, loader, store, view

from dawmans.corpus.discover import AUTHORED_STORE
from dawmans.corpus.loader import Discovered
from dawmans.records import AUTHORED_SOURCE_ID
from dawmans.triage.loader import (
    CorpusView,
    entry_files,
    scan_store,
    skipped_files,
    store_fingerprint,
)
from dawmans.triage.pointers import LEDGER_NAME

STALE = Discovered(source_id=AUTHORED_SOURCE_ID, fingerprint="sha256:stale", origin=Path("triage"))
"""A fingerprint from another store entirely: the loader never reads it."""


def second_entry(symptom: str = "A track is distorting") -> str:
    return entry_file(
        devices=[LIVE_ID],
        symptom=symptom,
        sections=[
            Section("The gain is too high", check="the meter is red", fixes=[POINTER]),
            Section("A device is clipping", check="its output meter is red", fixes=[POINTER]),
        ],
    )


# --- The scan --------------------------------------------------------------


def test_the_scan_is_recursive(tmp_path: Path) -> None:
    """1.6. A flat glob makes a subdirectory entry invisible with nothing to report."""
    root = store(tmp_path, {"nested/live/no-sound.md": DEFAULT, "top.md": second_entry()})

    assert [path.relative_to(root).as_posix() for path in entry_files(root)] == [
        "nested/live/no-sound.md",
        "top.md",
    ]


def test_a_non_entry_file_gets_a_report_line(tmp_path: Path) -> None:
    """The opposite of `manuals/`, where a non-PDF is skipped in silence."""
    root = store(tmp_path, {"nested/live/no-sound.md": DEFAULT, "nested/live/no-sound.txt": "x"})

    scan = scan_store(root)

    (rejection,) = scan.rejections
    assert rejection.origin == root / "nested" / "live" / "no-sound.txt"
    assert rejection.rejection.reason == "filename-invalid"
    assert "no-sound.txt" in rejection.rejection.detail
    assert ".md" in rejection.rejection.detail  # what to rename it to


def test_a_dotfile_is_neither_discovered_nor_reported(tmp_path: Path) -> None:
    """The ledger is the machine's own artefact and must not warn about itself."""
    root = store(tmp_path, {"entry.md": DEFAULT})
    (root / LEDGER_NAME).write_text("{}\n", encoding="utf-8")
    (root / ".DS_Store").write_text("x", encoding="utf-8")
    (root / ".drafts").mkdir()
    (root / ".drafts" / "half-written.md").write_text("nothing here parses", encoding="utf-8")

    scan = scan_store(root)

    assert scan.rejections == ()
    assert entry_files(root) == [root / "entry.md"]
    assert skipped_files(root) == []


def test_the_store_is_one_source_however_many_files(tmp_path: Path) -> None:
    """`discover()` yields 0 or 1, and the identity is the CONTRACTS §1 constant (1.8)."""
    root = store(tmp_path, {"a.md": DEFAULT, "b.md": second_entry(), "nested/c.md": second_entry()})

    (discovered,) = scan_store(root).sources

    assert discovered.source_id == AUTHORED_SOURCE_ID
    assert discovered.origin == root


def test_an_existing_empty_store_is_an_empty_discovery_set(tmp_path: Path) -> None:
    """Available with no source: its shard goes, because the store really is empty."""
    root = tmp_path / "triage"
    root.mkdir()

    scan = scan_store(root)

    assert scan.store == AUTHORED_STORE
    assert scan.available is True
    assert scan.sources == ()


def test_a_store_holding_only_a_non_entry_is_empty_and_reported(tmp_path: Path) -> None:
    root = store(tmp_path, {"notes.txt": "not an entry"})

    scan = scan_store(root)

    assert scan.available is True
    assert scan.sources == ()
    assert len(scan.rejections) == 1


def test_an_absent_store_is_unavailable(tmp_path: Path) -> None:
    """Not an empty set: an unmounted volume must not delete every authored passage."""
    scan = scan_store(tmp_path / "triage")

    assert scan.available is False
    assert scan.sources == ()


@pytest.mark.skipif(os.geteuid() == 0, reason="root reads a directory whatever its mode")
def test_an_unreadable_store_is_unavailable(tmp_path: Path) -> None:
    root = store(tmp_path, {"entry.md": DEFAULT})
    root.chmod(0o000)
    try:
        assert scan_store(root).available is False
    finally:
        root.chmod(0o755)


# --- The fingerprint -------------------------------------------------------


def digest_of(root: Path, names: list[str]) -> str:
    """The rule stated independently: sha256 over the sorted (relative path, digest) pairs."""
    running = hashlib.sha256()
    for name in sorted(names):
        body = (root / name).read_bytes()
        running.update(name.encode("utf-8"))
        running.update(b"\0")
        running.update(hashlib.sha256(body).hexdigest().encode("utf-8"))
        running.update(b"\n")
    return f"sha256:{running.hexdigest()}"


def test_the_fingerprint_is_over_the_sorted_path_and_digest_pairs(tmp_path: Path) -> None:
    root = store(tmp_path, {"b.md": DEFAULT, "nested/a.md": second_entry()})

    (discovered,) = scan_store(root).sources

    assert discovered.fingerprint == digest_of(root, ["b.md", "nested/a.md"])


def test_the_fingerprint_is_the_stores_own_bytes_and_nothing_else(tmp_path: Path) -> None:
    """Same entries, another path, another clock: the same fingerprint."""
    first = store(tmp_path / "one", {"entry.md": DEFAULT})
    second = store(tmp_path / "two", {"entry.md": DEFAULT})

    assert store_fingerprint(first, entry_files(first)) == store_fingerprint(
        second, entry_files(second)
    )


def test_the_fingerprint_moves_on_an_edit_an_addition_a_removal_and_a_rename(
    tmp_path: Path,
) -> None:
    root = store(tmp_path, {"entry.md": DEFAULT})
    seen = {store_fingerprint(root, entry_files(root))}

    (root / "second.md").write_text(second_entry(), encoding="utf-8")
    seen.add(store_fingerprint(root, entry_files(root)))

    (root / "second.md").write_text(second_entry("A pad is silent"), encoding="utf-8")
    seen.add(store_fingerprint(root, entry_files(root)))

    (root / "second.md").rename(root / "third.md")
    seen.add(store_fingerprint(root, entry_files(root)))

    (root / "third.md").unlink()
    assert store_fingerprint(root, entry_files(root)) in seen  # back to the first store
    assert len(seen) == 4


def test_a_dotfile_is_outside_the_fingerprint(tmp_path: Path) -> None:
    """The ledger is written *by* the run. Inside the fingerprint, every run that
    recorded a pointer would change the store's identity on the next one."""
    root = store(tmp_path, {"entry.md": DEFAULT})
    before = store_fingerprint(root, entry_files(root))

    (root / LEDGER_NAME).write_text('{"pointer": "x"}\n', encoding="utf-8")

    assert store_fingerprint(root, entry_files(root)) == before


# --- The load --------------------------------------------------------------


def test_the_load_reads_the_store_and_not_the_fingerprint(tmp_path: Path) -> None:
    """2.1: the authored store is exempt from fingerprint-based skipping, so nothing in
    the loader may consult the fingerprint it is handed."""
    root = store(tmp_path, {"entry.md": DEFAULT})

    result = loader(root).load(STALE)

    assert result.rejection is None
    assert [region.section_title for region in result.regions] == ["No sound from a track"]


def test_an_entry_added_or_removed_is_reflected_with_no_rebuild(tmp_path: Path) -> None:
    """5.1. Discovery is a directory scan and `load()` is unconditional; nothing about
    the store is compiled in and no configuration names an entry."""
    root = store(tmp_path, {"entry.md": DEFAULT})
    one = loader(root)

    (root / "second.md").write_text(second_entry(), encoding="utf-8")
    assert len(one.load(STALE).regions) == 2

    (root / "entry.md").unlink()
    assert [region.section_title for region in one.load(STALE).regions] == ["A track is distorting"]


def test_a_store_where_no_entry_survives_is_authored_invalid(tmp_path: Path) -> None:
    """12.6. A source with no passages is not a source, and the corpus deletes its shard —
    otherwise a store whose every entry has become malformed keeps serving the previous
    run's passages while the run reports the rejection and succeeds."""
    root = store(tmp_path, {"broken.md": "# No frontmatter here\n", "also.md": "nothing\n"})

    result = loader(root).load(STALE)

    assert result.rejection is not None
    assert result.rejection.reason == "authored-invalid"
    assert result.regions == []
    assert result.sidecar is None
    assert result.audit["report"]["entries"] == 0
    assert result.audit["report"]["rejected"] == 2


def test_one_surviving_entry_keeps_the_source(tmp_path: Path) -> None:
    """5.2: a rejection excludes one entry, the rest ingest, the run succeeds."""
    root = store(tmp_path, {"broken.md": "# No frontmatter\n", "good.md": DEFAULT})

    result = loader(root).load(STALE)

    assert result.rejection is None
    assert len(result.regions) == 1
    assert result.audit["report"]["rejected"] == 1


def test_the_term_check_reads_the_views_text(tmp_path: Path) -> None:
    """The check is over the passages the view carries, and a claim no cited section
    prints is flagged (2.6) without ever setting `unbacked` (Decision 5)."""
    text = entry_file(
        devices=[LIVE_ID],
        symptom="No sound from a track",
        sections=[
            Section(
                "The Kazoo Enable button is off", check="the Kazoo Enable is unlit", fixes=[POINTER]
            ),
            Section("Another track is soloed", check="a Solo button is lit", fixes=[POINTER]),
        ],
    )
    root = store(tmp_path, {"entry.md": text})

    outcome = loader(root).evaluate()

    (entry_outcome,) = outcome.ingesting
    assert [flag.name for flag in outcome.flags] == ["term-not-in-passage"]
    assert "Kazoo Enable" in outcome.flags[0].detail
    assert all(not cause.unbacked for cause in entry_outcome.causes)


def test_a_cause_is_unchecked_where_the_view_carries_no_text(tmp_path: Path) -> None:
    """Silence is not evidence that the manual does not print the term: a view read
    without its passage text checks nothing rather than flagging everything."""
    textless = view()
    root = store(tmp_path, {"entry.md": DEFAULT})

    outcome = loader(
        root, corpus=CorpusView(sections=textless.sections, indexed=textless.indexed)
    ).evaluate()

    assert [flag.name for flag in outcome.flags] == []


def test_an_undocumented_cause_is_counted_without_a_pointer(tmp_path: Path) -> None:
    """2.8's fourth count, over 2.3's carve-out — exercised against the fixture rig,
    since no live device is in that state."""
    text = entry_file(
        devices=[LIVE_ID, DIGITAKT_ID],
        symptom="The Digitakt is silent",
        sections=[
            Section(
                "Its output is muted", check="its output level is at zero", undocumented=DIGITAKT_ID
            ),
            Section("Another track is soloed", check="a Solo button is lit", fixes=[POINTER]),
        ],
    )
    root = store(tmp_path, {"entry.md": text})

    report = loader(root).load(STALE).audit["report"]

    assert report["pointers"] == {
        "checked": 1,
        "resolved": 1,
        "unresolved": 0,
        "without_pointer": 1,
    }
