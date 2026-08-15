"""The two targets that measure the source rather than a unit of it — 7.7 and 5.6.

**7.7 is the acceptance test for the whole spec**: each of the five starter symptoms,
asked with the starter set and the vendor manuals in scope, must come back `answered`,
`partially-answered` or `needs-narrowing` and never `refused-not-covered` or
`out-of-domain`. Refusing those five is the failure this source exists to remove. It needs
the real manuals, a built index **and** the answer engine, and `api/answer-engine` has no
implementation yet — so it is a `make bench` target that skips, the same honest limitation
`manual-corpus` accepts for its 8.1. What *can* run today is its corpus-side precondition:
the five entries are in the committed view, retrievable, and carrying their causes. A
refusal cannot be ruled out from here, but a refusal caused by the entry never reaching the
index can be, and that is this spec's half of 7.7.

**5.6 is a budget**: 200 entries ingested and validated in under 5 seconds with every fix
pointer re-checked (2.1). It is met **warm** and not met **cold**, exactly as designed —
the corpus loads its embedding model once per run, before iterating sources, and that load
alone is budgeted at 7.2 s in `manual-corpus`. The deviation is asserted here rather than
hidden inside the 5 s: the timed runs are warm, and a separate test pins the structural
fact that produces the cold cost. When `manual-corpus`'s lazy-on-first-embed request lands,
that test is what will fail, and 5.6's cold arm can be claimed in the same pass.

The budgets are stated as budgets rather than as measurements, per `tests/test_timing.py`:
a timing test that asserts last week's number fails on a slower runner and teaches everyone
to ignore it.
"""

from __future__ import annotations

import importlib.util
import json
import time
from pathlib import Path

import pytest
from rendering import Section, entry_file
from runs import run, view_of, write
from stores import LIVE_ID, POINTER
from test_starter_set import STARTER_SET

from corpusfixtures import StubEmbedder
from dawmans import cli
from dawmans.corpus.discover import slug
from dawmans.index.manifest import read_manifest
from dawmans.records import AUTHORED_SOURCE_ID

ROOT = Path(__file__).resolve().parents[2]
MANUALS = ROOT / "manuals"
INDEX = ROOT / "index"

#: 5.6, over a store of 200 entries, measured with the embedding model resident.
STORE_BUDGET_S = 5.0
SYNTHETIC_ENTRIES = 200

#: The engine that answers a question. `api/answer-engine` places it here (that design's
#: §Module placement); until the package exists, 7.7 has nothing to ask.
ENGINE = "dawmans.answer"

#: 7.7's own list. `ranked-causes` is a fourth non-refusal outcome that CONTRACTS §6 has
#: since added and that 7.7's closed list predates: if the engine answers these five with
#: it, the requirement wants amending in the open, not a test quietly widened.
ANSWERING = frozenset({"answered", "partially-answered", "needs-narrowing"})
REFUSING = frozenset({"refused-not-covered", "out-of-domain"})

SECOND_POINTER = f"{LIVE_ID} §18.6"


# --- 7.7: the five symptoms, asked -----------------------------------------


def committed_view() -> Path:
    """The repository's own index, or a skip. 7.7 is about the real corpus."""
    if not list(MANUALS.glob("*.pdf")):
        pytest.skip("manuals/ holds no PDFs — see specs/data/manual-corpus/prerequisites.md")
    manifest = read_manifest(INDEX)
    if manifest is None:
        pytest.skip("no committed index — run `dawmans ingest` first")
    return INDEX / manifest.view_dir


@pytest.mark.bench
@pytest.mark.parametrize("source_file", sorted(STARTER_SET))
def test_each_starter_symptom_is_in_the_committed_view(source_file: str) -> None:
    """7.7's precondition, and the half this spec owns: an entry that never reached the
    index is refused whatever the engine does. The passage is looked up by the symptom,
    because 3.4 sets `section_title` to it, and the sidecar row is what carries the
    entry's devices to the engine's per-passage predicate (4.3)."""
    view = committed_view()
    symptom = STARTER_SET[source_file]

    rows = [
        json.loads(line)
        for line in (view / "passages.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    authored = [row for row in rows if row["source_id"] == AUTHORED_SOURCE_ID]
    mine = [row for row in authored if row["section_title"] == symptom]
    assert mine, f"{symptom} is not in {view}"

    sidecar = json.loads(
        (view / "reports" / f"{slug(AUTHORED_SOURCE_ID)}.json").read_text(encoding="utf-8")
    )
    published = {row["passage_id"]: row for row in sidecar["passages"]}
    for row in mine:
        entry = published[row["passage_id"]]
        assert entry["source_file"] == source_file
        assert entry["devices"], "an entry with no devices is in scope for every turn"
        assert entry["causes"], "a symptom with no causes cannot narrow anything"
        assert all(cause["fix"] for cause in entry["causes"]), "7.8: every fix is cited"


@pytest.mark.bench
def test_the_five_starter_symptoms_are_answered_rather_than_refused() -> None:
    """7.7 itself. It asks the engine, so it needs the engine: `dawmans.answer` does not
    exist yet, and neither does the provider configuration a synthesis turn requires.

    When it does, this test asks each of the five symptoms with the starter set and the
    vendor manuals in scope, over `POST /turn` — the engine's own surface — and asserts
    the outcome is in `ANSWERING` and in neither member of `REFUSING`. A
    `provider-unconfigured` or other provider outcome is a skip rather than a failure:
    7.7 is about coverage, and a missing API key says nothing about it.
    """
    committed_view()
    if importlib.util.find_spec(ENGINE) is None:
        pytest.skip(f"{ENGINE} has no implementation yet — 7.7 is unrunnable, not failing")
    pytest.skip(f"{ENGINE} exists: wire this to POST /turn and assert the outcome")


# --- 5.6: 200 entries, ingested and validated ------------------------------


def synthetic_store(root: Path, count: int = SYNTHETIC_ENTRIES) -> None:
    """`count` entries of two causes each, so every run re-checks `2 * count` pointers.

    The symptoms differ, which is not decoration: 1.9 rejects two entries sharing a
    symptom within intersecting scope, and a store of 200 copies would measure the
    duplicate path rather than the ingestion path.
    """
    write(
        root,
        {
            f"synthetic-{number:03d}.md": entry_file(
                devices=[LIVE_ID],
                symptom=f"Synthetic symptom {number:03d}",
                sections=[
                    Section(
                        "The Track Activator is off",
                        check="the Track Activator switch is unlit",
                        fixes=[POINTER],
                    ),
                    Section(
                        "Another track is soloed",
                        check="a Solo switch is lit on some other track",
                        fixes=[SECOND_POINTER],
                    ),
                ],
            )
            for number in range(count)
        },
    )


def test_two_hundred_entries_ingest_inside_the_budget(tmp_path: Path) -> None:
    """5.6, with the model resident — which is how the CLI arranges it, loading once per
    run before iterating sources. The embedder here is a stub, so what is measured is the
    parse, the resolution of all 400 pointers, the term check, emission and the shard and
    merge the entries pass through. Real vectors are `manual-corpus`'s budget and its
    per-`passage_id` reuse already removes them for an entry whose text did not change."""
    synthetic_store(tmp_path)

    start = time.perf_counter()
    result, _ = run(tmp_path)
    elapsed = time.perf_counter() - start

    assert result.report.succeeded, result.report.lines()
    assert elapsed < STORE_BUDGET_S, (
        f"{elapsed:.1f}s to ingest {SYNTHETIC_ENTRIES} entries, against 5.6's {STORE_BUDGET_S}s"
    )


def test_every_pointer_is_re_checked_within_that_budget(tmp_path: Path) -> None:
    """The clause that makes the budget mean something: 5.6 counts a run that re-checks
    **every** fix pointer (2.1), not one that trusts a fingerprint. A run that skipped the
    authored shard would come in far under 5 s and detect no drift at all."""
    synthetic_store(tmp_path)

    run(tmp_path)

    sidecar = json.loads(
        (view_of(tmp_path / "index") / "reports" / f"{slug(AUTHORED_SOURCE_ID)}.json").read_text(
            encoding="utf-8"
        )
    )
    report = sidecar["report"]

    assert report["entries"] == SYNTHETIC_ENTRIES
    assert report["pointers"]["checked"] == 2 * SYNTHETIC_ENTRIES
    assert report["pointers"]["resolved"] == report["pointers"]["checked"]


def test_two_hundred_entries_validate_inside_the_budget(tmp_path: Path) -> None:
    """The other half of 5.6, and the half an author waits on. `dawmans validate` embeds
    nothing (5.4), so it is unaffected by the cold model load either way — it re-parses,
    re-resolves and term-checks the whole store against the committed view."""
    synthetic_store(tmp_path)
    run(tmp_path)

    start = time.perf_counter()
    code, lines = cli.run_validate(tmp_path / "index", root=tmp_path)
    elapsed = time.perf_counter() - start

    assert code == 0, lines
    assert f"{SYNTHETIC_ENTRIES} entries ingested" in " ".join(lines)
    assert elapsed < STORE_BUDGET_S, (
        f"{elapsed:.1f}s to validate {SYNTHETIC_ENTRIES} entries, against 5.6's {STORE_BUDGET_S}s"
    )


def test_the_cold_deviation_is_the_run_s_model_load_and_not_this_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Why 5.6 is met warm and not cold, asserted structurally rather than timed.

    `dawmans ingest` loads the embedding model **before** it reaches any loader, so an
    authored-only run — no manual changed, every entry's vector reusable — still pays it,
    and `manual-corpus` budgets that load at 7.2 s. Nothing in this spec can avoid it: the
    authored store's `load()` runs on every ingest by design (2.1), and it is the caller
    that decides when the model appears.

    This test fails when the lazy-on-first-embed request lands, which is precisely when
    5.6's cold arm becomes claimable and this file should say so instead.
    """
    loaded: list[str] = []

    def load_embedder() -> StubEmbedder:
        loaded.append("model")
        return StubEmbedder()

    monkeypatch.setattr(cli, "load_embedder", load_embedder)
    (tmp_path / "manuals").mkdir()
    write(
        tmp_path,
        {
            "entry.md": entry_file(
                devices=[LIVE_ID],
                symptom="No sound from a track",
                sections=[
                    Section(
                        "The Track Activator is off",
                        check="the switch is unlit",
                        fixes=[POINTER],
                    ),
                    Section(
                        "Another track is soloed",
                        check="a Solo switch is lit",
                        fixes=[POINTER],
                    ),
                ],
            )
        },
    )

    cli.run_ingest(tmp_path)

    assert loaded == ["model"], "the model is loaded once per run, whatever the run has to do"
