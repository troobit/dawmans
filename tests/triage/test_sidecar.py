"""The sidecar — design 'The sidecar', 2.8, 4.3, 5.5.

Everything `Passage` cannot carry, keyed by `passage_id`. Two consumers make it a
contract rather than diagnostics: `api/answer-engine` 5.13 reads `devices` as the
per-passage scope predicate — this spec filters nothing itself — and `causes` in declared
order is the source of CONTRACTS §4c's `Cause` records, whose `rank` is that position.

Where it lands is load-bearing and silent when wrong: the corpus writes
`views/<hex>/reports/authored_triage.json` from the slug rule, `source_id` with `/`
replaced by `_`. A reader following a hyphenated name finds nothing, no error is raised,
and under 5.13 no passage declares devices — so every entry stays in scope for every
turn. `test_ingest_wiring.py` asserts the path the corpus actually writes; what is
asserted here is the payload.
"""

from __future__ import annotations

from pathlib import Path

from rendering import Section, entry_file
from stores import (
    DEFAULT,
    DIGITAKT_ID,
    DISCOVERED,
    DRIFTING,
    LIVE_ID,
    NOW,
    POINTER,
    drifted_view,
    loader,
    store,
)

from dawmans.corpus.chunk import chunk_source
from dawmans.triage.model import entry_key
from dawmans.triage.pointers import Ledger

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "triage"


def sidecar_of(tmp_path: Path, files: dict[str, str], **kwargs) -> dict:
    result = loader(store(tmp_path, files), **kwargs).load(DISCOVERED)
    assert result.sidecar is not None
    return result.sidecar


# --- The passage rows ------------------------------------------------------


def test_every_row_is_keyed_by_a_passage_the_run_emitted(tmp_path: Path) -> None:
    """4.3: keyed by the `passage_id` of **every** passage emitted for that entry, and by
    the same identifiers the chunker assigns — not a second minting."""
    root = store(tmp_path, {"entry.md": DEFAULT})
    result = loader(root).load(DISCOVERED)
    emitted = [chunk.passage.passage_id for chunk in chunk_source(result.record, result.regions)]

    assert result.sidecar is not None
    assert [row["passage_id"] for row in result.sidecar["passages"]] == emitted


def test_a_row_carries_the_declared_scope(tmp_path: Path) -> None:
    """The input to `api/answer-engine` 5.13's per-passage predicate (4.3), as declared:
    the revision travels with the id, because a step for another edition is useless."""
    text = entry_file(
        devices=[f"{LIVE_ID}@12-standard", DIGITAKT_ID],
        symptom="No sound from a track",
        sections=[
            Section(
                "The Track Activator is off", check="the track's number is unlit", fixes=[POINTER]
            ),
            Section(
                "Its output is muted", check="its output level is at zero", undocumented=DIGITAKT_ID
            ),
        ],
    )
    (row,) = sidecar_of(tmp_path, {"entry.md": text})["passages"]

    assert row["devices"] == [
        {"id": LIVE_ID, "revision": "12-standard"},
        {"id": DIGITAKT_ID, "revision": None},
    ]


def test_a_row_carries_the_entry_location_halves(tmp_path: Path) -> None:
    """CONTRACTS §2 `entry_location`, which the engine joins as one opaque display string
    and `ui/ask-and-source-picker` 5.19 makes copyable. Repo-relative, and a locator
    rather than an identity — which is why it is here and not in `passage_id`."""
    (row,) = sidecar_of(tmp_path, {"nested/entry.md": DEFAULT})["passages"]

    assert row["source_file"] == "triage/nested/entry.md"
    assert row["line"] == 5


def test_causes_are_in_declared_order_with_their_checks_and_fixes(tmp_path: Path) -> None:
    """1.5 is load-bearing here too: the position becomes CONTRACTS §4c's `rank`."""
    (row,) = sidecar_of(tmp_path, {"entry.md": DEFAULT})["passages"]

    assert [cause["statement"] for cause in row["causes"]] == [
        "The Track Activator is off",
        "Another track is soloed",
    ]
    first = row["causes"][0]
    assert first["check"] == "the track's number is unlit"
    assert first["undocumented_device"] is None
    assert first["flags"] == []
    (fix,) = first["fix"]
    assert fix["source_id"] == LIVE_ID
    assert fix["section"] == "18.1"
    assert fix["passage_ids"] and all(pid.startswith(f"{LIVE_ID}#") for pid in fix["passage_ids"])


def test_the_unbacked_cause_shape(tmp_path: Path) -> None:
    """2.3's state, which no live device is in — exercised against the fixture rig. The
    design names the shape exactly: no fix, the device named, the cause flagged."""
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
    payload = sidecar_of(tmp_path, {"entry.md": text})
    (row,) = payload["passages"]

    assert row["causes"][0]["fix"] == []
    assert row["causes"][0]["undocumented_device"] == DIGITAKT_ID
    assert row["causes"][0]["flags"] == ["unbacked-cause"]
    assert row["causes"][1]["flags"] == []

    (flag,) = [flag for flag in payload["report"]["flags"] if flag["name"] == "unbacked-cause"]
    assert DIGITAKT_ID in flag["detail"]
    assert payload["report"]["flagged"] == 1


def test_entry_key_is_over_the_symptom_and_the_sorted_device_ids(tmp_path: Path) -> None:
    """An annotation and the key of nothing: a stable handle on an entry across a file
    rename, which is why reordering `devices:` or re-casing the symptom moves nothing."""
    one = entry_file(
        devices=[LIVE_ID, DIGITAKT_ID],
        symptom="No sound from a track",
        sections=[
            Section(
                "The Track Activator is off", check="the track's number is unlit", fixes=[POINTER]
            ),
            Section("Another track is soloed", check="a Solo button is lit", fixes=[POINTER]),
        ],
    )
    other = one.replace(
        f"devices: [{LIVE_ID}, {DIGITAKT_ID}]", f"devices: [{DIGITAKT_ID}, {LIVE_ID}]"
    ).replace("# No sound from a track", "# No Sound  From a track")

    first = sidecar_of(tmp_path / "a", {"entry.md": one})["passages"][0]
    second = sidecar_of(tmp_path / "b", {"renamed.md": other})["passages"][0]

    assert first["entry_key"] == second["entry_key"]
    assert first["passage_id"] != second["passage_id"]  # the symptom's wording is hashed


def test_a_split_entry_publishes_every_passage_with_the_whole_entry(tmp_path: Path) -> None:
    """Which passage of a split entry holds which cause is an artefact of the 350-word
    cap and changes under a re-chunk, so a citation's causes must not be truncated by
    where the cap happened to fall."""
    body = [
        Section(
            f"Cause number {index}",
            check=" ".join(f"w{index}x{n}" for n in range(90)),
            fixes=[POINTER],
        )
        for index in range(6)
    ]
    text = entry_file(devices=[LIVE_ID], symptom="A long entry", sections=body)
    rows = sidecar_of(tmp_path, {"entry.md": text})["passages"]

    assert len(rows) > 1
    assert len({row["passage_id"] for row in rows}) == len(rows)
    assert all(len(row["causes"]) == 6 for row in rows)
    assert len({row["entry_key"] for row in rows}) == 1


# --- The report block ------------------------------------------------------


def test_the_pointer_counts(tmp_path: Path) -> None:
    """2.8, over the entries this run ingested."""
    report = sidecar_of(tmp_path, {"entry.md": DEFAULT})["report"]

    assert report["entries"] == 1
    assert report["rejected"] == 0
    assert report["flagged"] == 0
    assert report["pointers"] == {
        "checked": 2,
        "resolved": 2,
        "unresolved": 0,
        "without_pointer": 0,
    }


def test_a_rejection_carries_its_reason_and_names_the_entry(tmp_path: Path) -> None:
    """5.5's reason for each rejection, in the rows `dawmans coverage` renders. The other
    entry still ingests and the run still succeeds (5.2)."""
    broken = entry_file(
        devices=[LIVE_ID],
        symptom="A pad is silent",
        sections=[
            Section("The pad is unassigned", check="nothing lights", fixes=[f"{LIVE_ID} §99.9"]),
            Section("Another track is soloed", check="a Solo button is lit", fixes=[POINTER]),
        ],
    )
    payload = sidecar_of(tmp_path, {"broken.md": broken, "good.md": DEFAULT})

    assert payload["report"]["entries"] == 1
    (rejection,) = payload["report"]["rejections"]
    assert rejection["reason"] == "pointer-unresolved"
    assert rejection["source_file"] == "triage/broken.md"
    assert rejection["symptom"] == "A pad is silent"
    assert rejection["cause"] == "The pad is unassigned"
    assert "§99.9" in rejection["detail"]
    assert len(payload["passages"]) == 1


def test_a_drifted_pointer_is_an_unresolved_pointer_and_a_flag(tmp_path: Path) -> None:
    """8.4: the ledger says it once resolved, so the entry is served with the cause
    marked rather than withdrawn — and the count says a pointer did not resolve."""
    ledger = Ledger.empty()
    ledger.record(DRIFTING, ["ableton/live-12#4d7339c32b29d043"], [], NOW)
    text = (FIXTURES / "drift" / "soloed-track.md").read_text(encoding="utf-8")

    payload = sidecar_of(tmp_path, {"entry.md": text}, corpus=drifted_view(), ledger=ledger)

    assert payload["report"]["pointers"]["unresolved"] == 1
    assert payload["report"]["entries"] == 1
    names = {flag["name"] for flag in payload["report"]["flags"]}
    assert "pointer-drifted" in names
    drifted = [
        cause
        for row in payload["passages"]
        for cause in row["causes"]
        if "pointer-drifted" in cause["flags"]
    ]
    assert drifted


def test_a_missing_ledger_is_reported(tmp_path: Path) -> None:
    """Deleting the file re-arms 2.2 for the whole store. That is the honest degradation,
    but it must not be silent, or the author meets a wall of rejections with nothing
    explaining them."""
    root = store(tmp_path, {"entry.md": DEFAULT})

    present = loader(root, ledger=Ledger.empty())
    missing = loader(root, ledger=Ledger.read(root / ".pointer-ledger.jsonl"))

    assert present.load(DISCOVERED).sidecar["report"]["ledger_missing"] is False
    assert missing.load(DISCOVERED).sidecar["report"]["ledger_missing"] is True


def test_the_report_is_in_the_audit_of_a_rejected_store(tmp_path: Path) -> None:
    """A rejected source commits no shard and therefore no sidecar, and the reasons are
    exactly what someone comes looking for: they stay in `index/audits/`."""
    result = loader(store(tmp_path, {"broken.md": "nothing\n"})).load(DISCOVERED)

    assert result.sidecar is None
    assert result.audit["report"]["rejections"][0]["reason"] == "frontmatter-missing"


def test_entry_key_matches_the_model(tmp_path: Path) -> None:
    """The report and the sidecar agree with the derivation every other reader uses."""
    root = store(tmp_path, {"entry.md": DEFAULT})
    outcome = loader(root).evaluate()
    (row,) = sidecar_of(tmp_path, {"entry.md": DEFAULT})["passages"]

    assert row["entry_key"] == entry_key(outcome.ingesting[0].entry)
