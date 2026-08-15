"""The pointer ledger and reject-versus-flag — design 'Reject versus flag'.

2.2 rejects a pointer that never worked; 8.4 flags one that stopped working.
Nothing in the entry distinguishes them and `index/` is derived, so the memory is
`triage/.pointer-ledger.jsonl`: one row per pointer recording that it resolved
and to what.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st
from rendering import Section, entry_file
from sections import CORPUS, DRIFT_AFTER, DRIFT_BEFORE, LIVE, passages

from dawmans.triage.parse import parse_entry
from dawmans.triage.pointers import (
    AUTHORED_SOURCE,
    Ledger,
    LedgerUnparseable,
    SectionIndex,
    check_pointer,
    parse_pointer,
    pointer_key,
)

LIVE_ID = "ableton/live-12"
APC_ID = "akai/apc-key-25"

DRIFTING = f"{LIVE_ID} §18.6"
"""The pointer the `drift/` fixture pair is built around."""

STABLE = f"{LIVE_ID} §18.1"

NOW = "2026-08-15T09:00:00Z"
LATER = "2026-08-16T09:00:00Z"


def index(*names: str) -> SectionIndex:
    return SectionIndex.from_passages(passages(*names or CORPUS))


def pointer(text: str, line: int = 7):
    p = parse_pointer(text, line)
    assert p is not None
    return p


def outcome(text: str, idx: SectionIndex, ledger: Ledger):
    return check_pointer(pointer(text), idx, ledger)


def seeded(*keys_and_ids: tuple[str, list[str]]) -> Ledger:
    """A ledger holding a row for each pointer, as a previous run would leave it."""
    ledger = Ledger.empty()
    for key, passage_ids in keys_and_ids:
        ledger.record(key, passage_ids, entry_keys=[], now=NOW)
    return ledger


def drifted_index() -> SectionIndex:
    """The corpus after the vendor renumbered §18.6 to §18.7 and edited its text."""
    return SectionIndex.from_passages(passages(DRIFT_AFTER))


def stable_index() -> SectionIndex:
    return SectionIndex.from_passages(passages(DRIFT_BEFORE))


# --- Reject versus flag ---------------------------------------------------


def test_no_row_and_unresolved_is_a_rejection():
    """2.2. A first ingestion fails because the author wrote something wrong."""
    result = outcome(DRIFTING, drifted_index(), Ledger.empty())
    assert result.rejected
    assert not result.drifted
    assert result.unresolved is not None


def test_a_row_and_unresolved_is_a_flag_not_a_rejection():
    """8.4. Drift happens with the author absent, and silently withdrawing working
    triage mid-session is worse than serving it marked."""
    ledger = seeded((DRIFTING, ["ableton/live-12#4d7339c32b29d043"]))
    result = outcome(DRIFTING, drifted_index(), ledger)
    assert result.drifted
    assert not result.rejected


def test_a_new_cause_added_to_an_old_entry_still_rejects():
    """The row records the pointer, and a newly typed pointer has none — so 2.2
    still covers the cause added long after the entry was written."""
    ledger = seeded((DRIFTING, ["ableton/live-12#4d7339c32b29d043"]))
    assert outcome(f"{LIVE_ID} §99.99", index(), ledger).rejected


def test_an_unchanged_passage_keeps_resolving_with_no_edit_to_the_entry():
    """8.2, against the `before` half of the pair."""
    result = outcome(DRIFTING, stable_index(), Ledger.empty())
    assert result.ok
    assert not result.rejected and not result.drifted


def test_resolving_again_on_a_later_run_clears_the_flag():
    """8.5. The row is retained through the drift, so restoring the manual is all
    it takes — no edit to the entry, and no ledger surgery."""
    ledger = seeded((DRIFTING, ["ableton/live-12#4d7339c32b29d043"]))
    assert outcome(DRIFTING, drifted_index(), ledger).drifted
    assert outcome(DRIFTING, stable_index(), ledger).ok


def test_a_row_does_not_excuse_a_pointer_at_the_authored_source():
    """2.7 is about what an entry may cite, not about whether it once worked. A
    row for it could never have been written honestly, and if one is there by hand
    it changes nothing."""
    ledger = seeded((f'{AUTHORED_SOURCE} "no sound"', ["authored/triage#0000"]))
    result = outcome(f'{AUTHORED_SOURCE} "no sound"', index(), ledger)
    assert result.rejected
    assert result.unresolved is not None and result.unresolved.reason == "authored-target"


def test_a_removed_source_is_a_flag_where_the_ledger_holds_a_row():
    """8.4's other arm — "the passage's text changed, **or the source was
    removed**". The manual is gone from the view entirely, not renumbered."""
    ledger = seeded((DRIFTING, ["ableton/live-12#4d7339c32b29d043"]))
    empty_corpus = SectionIndex.from_passages([])
    assert outcome(DRIFTING, empty_corpus, ledger).drifted


# --- The key is the pointer alone (Decision 4) ----------------------------


def test_the_key_is_the_source_and_number():
    assert pointer_key(pointer(f"{LIVE_ID} §16.4")) == f"{LIVE_ID} §16.4"


def test_the_key_uses_the_normalised_title_where_there_is_no_number():
    assert pointer_key(pointer(f'{APC_ID} "Shift Functions"')) == f'{APC_ID} "shift functions"'


def test_a_corroborating_title_does_not_change_the_key():
    """The number is the key where there is one, so adding the title the manual
    prints beside it — or letting that title go stale — moves no row."""
    bare = pointer_key(pointer(f"{LIVE_ID} §16.4"))
    assert pointer_key(pointer(f'{LIVE_ID} §16.4 "Soloing and Cueing"')) == bare
    assert pointer_key(pointer(f'{LIVE_ID} §16.4 "Something Else Entirely"')) == bare


@pytest.mark.parametrize(
    "typed", ['"Shift Functions"', '"shift functions"', '"  Shift  Functions "']
)
def test_the_title_key_is_normalised_so_cosmetic_retyping_moves_no_row(typed):
    assert pointer_key(pointer(f"{APC_ID} {typed}")) == f'{APC_ID} "shift functions"'


DEVICE_SETS = [
    ["ableton/live-12"],
    ["ableton/live-12", "akai/apc-key-25"],
    ["ableton/live-12", "alesis/nitro-max", "akai/apc-key-25"],
]

SYMPTOMS = ["No sound from a track", "no sound at all", "A track is silent"]


@given(
    devices=st.sampled_from(DEVICE_SETS),
    symptom=st.sampled_from(SYMPTOMS),
    phrasings=st.lists(st.sampled_from(SYMPTOMS), max_size=3),
)
def test_ledger_keys_do_not_move_when_the_entry_around_them_is_edited(devices, symptom, phrasings):
    """Property — ledger key stability (Decision 4, 8.4).

    Keying on the entry would make adding a device to `devices:` change the key,
    so any pointer that had since drifted would become a 2.2 **rejection**: an
    entry withdrawn mid-session by a cosmetic edit unrelated to pointers.
    """
    text = entry_file(
        devices=devices,
        symptom=symptom,
        phrasings=phrasings,
        sections=[
            Section("The Track Activator is off", check="a check", fixes=[STABLE]),
            Section("Another track is soloed", check="a check", fixes=[DRIFTING]),
        ],
    )
    result = parse_entry(Path("triage/no-sound.md"), text.encode("utf-8"))
    assert result.entry is not None, result.rejection
    keys = [pointer_key(fix) for cause in result.entry.causes for fix in cause.fixes]
    assert keys == [STABLE, DRIFTING]


# --- Property: a pointer that resolved once is only ever a flag -----------

CORPUS_STATES = ["present", "renumbered", "removed"]


@given(
    steps=st.lists(st.sampled_from(CORPUS_STATES), min_size=1, max_size=8),
    entry_edits=st.lists(st.sampled_from(SYMPTOMS), min_size=1, max_size=8),
)
def test_a_pointer_that_resolved_once_is_never_rejected_again(steps, entry_edits):
    """Property — the reject/flag state machine (2.2, 8.4).

    Whatever happens to the manual and to the entry around it afterwards, the
    2.2 rejection is available exactly once: before the pointer has ever worked.
    """
    indexes = {
        "present": stable_index(),
        "renumbered": drifted_index(),
        "removed": SectionIndex.from_passages([]),
    }
    ledger = Ledger.empty()
    ever_resolved = False
    for step, _ in zip(steps, entry_edits * len(steps), strict=False):
        result = check_pointer(pointer(DRIFTING), indexes[step], ledger)
        if ever_resolved:
            assert not result.rejected, f"{step} rejected a pointer that had resolved"
        if result.ok:
            ever_resolved = True
            ledger.record(pointer_key(pointer(DRIFTING)), result.passage_ids, [], NOW)


# --- The file: NDJSON, sorted, written only on transition -----------------


def test_rows_are_ndjson_sorted_by_pointer(tmp_path):
    ledger = seeded(
        (f'{APC_ID} "setup"', ["akai/apc-key-25#aa"]),
        (STABLE, ["ableton/live-12#bb"]),
        (DRIFTING, ["ableton/live-12#cc"]),
    )
    path = tmp_path / ".pointer-ledger.jsonl"
    ledger.write(path)
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert [r["pointer"] for r in rows] == sorted(r["pointer"] for r in rows)
    assert set(rows[0]) == {"pointer", "resolved_at", "passage_ids", "entry_keys"}


def test_a_run_that_changes_nothing_leaves_the_file_byte_identical(tmp_path):
    """`resolved_at` is written only on transition, so an unchanged run leaves the
    working tree clean — which is what makes a committed machine-written file
    tolerable at all."""
    path = tmp_path / ".pointer-ledger.jsonl"
    ids = ["ableton/live-12#4d7339c32b29d043"]
    seeded((DRIFTING, ids)).write(path)
    first = path.read_bytes()

    ledger = Ledger.read(path)
    ledger.record(DRIFTING, ids, entry_keys=[], now=LATER)
    ledger.write(path)
    assert path.read_bytes() == first


def test_resolving_to_different_passages_moves_resolved_at(tmp_path):
    """The transition case: the section it resolves to is not the one the row
    records, so the row is what changed and the timestamp says when."""
    path = tmp_path / ".pointer-ledger.jsonl"
    seeded((DRIFTING, ["ableton/live-12#old"])).write(path)

    ledger = Ledger.read(path)
    ledger.record(DRIFTING, ["ableton/live-12#new"], entry_keys=[], now=LATER)
    ledger.write(path)
    row = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    assert row["resolved_at"] == LATER
    assert row["passage_ids"] == ["ableton/live-12#new"]


def test_rows_are_never_pruned(tmp_path):
    """A row only ever records that a pointer *did* resolve, so a stale row costs
    one line and nothing else — and never deleting is what makes the union merge
    of two machines' ledgers sound."""
    path = tmp_path / ".pointer-ledger.jsonl"
    seeded((DRIFTING, ["ableton/live-12#aa"]), (STABLE, ["ableton/live-12#bb"])).write(path)

    ledger = Ledger.read(path)
    ledger.record(STABLE, ["ableton/live-12#bb"], entry_keys=[], now=LATER)
    ledger.write(path)
    assert {r["pointer"] for r in _rows(path)} == {DRIFTING, STABLE}


def test_entry_keys_are_annotation_and_no_part_of_the_key(tmp_path):
    ledger = Ledger.empty()
    ledger.record(STABLE, ["ableton/live-12#bb"], entry_keys=["a41e"], now=NOW)
    ledger.record(STABLE, ["ableton/live-12#bb"], entry_keys=["b93d"], now=LATER)
    path = tmp_path / ".pointer-ledger.jsonl"
    ledger.write(path)
    assert len(_rows(path)) == 1


def _rows(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


# --- A missing ledger, and an unparseable one -----------------------------


def test_a_missing_ledger_reads_as_empty_and_says_so(tmp_path):
    """Deleting the file re-arms 2.2 for everything. That is the honest
    degradation — the file is the only claim that a pointer once worked — but it
    is not silent: the loader has `missing` to report, or the author meets a wall
    of rejections with nothing explaining them."""
    ledger = Ledger.read(tmp_path / ".pointer-ledger.jsonl")
    assert ledger.missing
    assert not ledger.knows(DRIFTING)
    assert outcome(DRIFTING, drifted_index(), ledger).rejected


def test_an_empty_ledger_file_is_not_a_missing_one(tmp_path):
    path = tmp_path / ".pointer-ledger.jsonl"
    path.write_text("", encoding="utf-8")
    assert not Ledger.read(path).missing


def test_an_unparseable_ledger_is_a_failure_naming_the_file_and_the_line(tmp_path):
    """Not a rejection: no entry is at fault, and continuing would silently re-arm
    2.2 for the whole store and reject entries 8.4 requires be served with a
    mark."""
    path = tmp_path / ".pointer-ledger.jsonl"
    path.write_text(
        f'{{"pointer": "{STABLE}", "resolved_at": "{NOW}", "passage_ids": [], "entry_keys": []}}\n'
        '{"pointer": "ableton/live-12 §18.6", "passage_ids": ["ableton/live-12#4d7\n',
        encoding="utf-8",
    )
    with pytest.raises(LedgerUnparseable) as raised:
        Ledger.read(path)
    assert str(path) in str(raised.value)
    assert "line 2" in str(raised.value)


FIXTURE_STORE = Path(__file__).resolve().parents[1] / "fixtures" / "triage" / "drift"


def test_the_committed_corrupt_fixture_is_the_failure_case():
    """`tests/fixtures/triage/drift/corrupt.pointer-ledger.jsonl` — the hand-edit
    that git's union merge cannot prevent."""
    with pytest.raises(LedgerUnparseable):
        Ledger.read(FIXTURE_STORE / "corrupt.pointer-ledger.jsonl")


def test_the_committed_seeded_fixture_reads():
    ledger = Ledger.read(FIXTURE_STORE / "seeded.pointer-ledger.jsonl")
    assert not ledger.missing
    assert ledger.knows(DRIFTING) and ledger.knows(STABLE)


def test_a_row_missing_a_required_field_is_unparseable(tmp_path):
    path = tmp_path / ".pointer-ledger.jsonl"
    path.write_text('{"pointer": "ableton/live-12 §18.1"}\n', encoding="utf-8")
    with pytest.raises(LedgerUnparseable):
        Ledger.read(path)


# --- validate reads and never writes --------------------------------------


def test_reading_never_writes(tmp_path):
    """`dawmans validate` (5.4) reads the ledger and never writes it, so checking
    work before committing to it cannot promote a broken pointer to "previously
    fine". `read` returns a ledger; only an explicit `write` touches the file."""
    path = tmp_path / ".pointer-ledger.jsonl"
    seeded((DRIFTING, ["ableton/live-12#aa"])).write(path)
    before = path.read_bytes()

    ledger = Ledger.read(path)
    check_pointer(pointer(DRIFTING), drifted_index(), ledger)
    check_pointer(pointer(STABLE), index(LIVE), ledger)
    assert path.read_bytes() == before


def test_checking_a_pointer_does_not_record_it():
    """Recording is the caller's move, under `dawmans ingest` alone. If checking
    recorded, `validate` would promote every pointer it looked at."""
    ledger = Ledger.empty()
    assert check_pointer(pointer(STABLE), index(LIVE), ledger).ok
    assert not ledger.knows(STABLE)
