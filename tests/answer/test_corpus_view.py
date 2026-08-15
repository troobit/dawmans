"""CorpusView load, refusal and the revision watch — design §What the engine reads.

The load order is load-bearing: manifest first, refusal on an `index_version`
the engine cannot interpret, and a wholesale swap on a `corpus_revision`
change so no answer can mix revisions. The sidecar name is derived by the
slug rule, never spelled — the silent failure 5.13 exists to prevent.
"""

import json
import os

import bm25s
import numpy as np
import pytest

from dawmans.answer.view import (
    INDEX_VERSION,
    CorpusView,
    ViewLoadError,
    ViewWatcher,
    sidecar_name,
)

VECTOR_DIM = 4

SOURCES = [
    {
        "source_id": "ableton/live-12",
        "kind": "vendor-manual",
        "vendor": "ableton",
        "product": "live-12",
        "doctype": "manual",
        "lang": "en",
        "doc_version": "12.0",
        "display_name": "Ableton Live 12 Manual",
        "hardware_applicability": {"device": "ableton/live-12", "status": "confirmed"},
        "page_count": 1009,
        "ingested_at": "2026-08-14T10:00:00Z",
        "chunk_count": 2,
    },
    {
        "source_id": "authored/triage",
        "kind": "authored-triage",
        "display_name": "Symptom triage entries",
        "hardware_applicability": {"status": "assumed"},
        "ingested_at": "2026-08-14T10:00:00Z",
        "chunk_count": 2,
    },
    {
        "source_id": "focusrite/scarlett-solo-4g",
        "kind": "vendor-manual",
        "vendor": "focusrite",
        "product": "scarlett-solo-4g",
        "doctype": "guide",
        "lang": "en",
        "doc_version": "1.0",
        "display_name": "Focusrite Scarlett Solo 4th Gen Guide",
        "hardware_applicability": {"device": "focusrite/scarlett-solo-4g", "status": "confirmed"},
        "page_count": 20,
        "ingested_at": "2026-08-14T10:00:00Z",
        "chunk_count": 1,
    },
]

# Row-ordered, grouped by source in sorted source_id order — the layout the
# corpus commits and the row slices address.
PASSAGES = [
    {
        "passage_id": "ableton/live-12#a001",
        "source_id": "ableton/live-12",
        "section_number": "16.4",
        "section_title": "Track Activator",
        "text": "The Track Activator mutes the track output when off",
    },
    {
        "passage_id": "ableton/live-12#a002",
        "source_id": "ableton/live-12",
        "section_number": "9.2",
        "section_title": "Warp modes",
        "text": "Warp modes stretch audio playback without changing pitch",
    },
    {
        "passage_id": "authored/triage#t001",
        "source_id": "authored/triage",
        "section_title": "No sound from a track",
        "text": "No sound from a track although the meters move",
    },
    {
        "passage_id": "authored/triage#t002",
        "source_id": "authored/triage",
        "section_title": "Crackling audio",
        "text": "Crackling dropouts during playback under load",
    },
    {
        "passage_id": "focusrite/scarlett-solo-4g#f001",
        "source_id": "focusrite/scarlett-solo-4g",
        "section_number": "3",
        "section_title": "Direct Monitor",
        "text": "The DIRECT MONITOR switch routes the input straight to the outputs",
    },
]

GAPS = {
    "owned_but_undocumented": [],
    "documented_but_unconfirmed": [{"source_id": "focusrite/scarlett-solo-4g"}],
}

SIDECAR = {
    "passages": [
        {
            "passage_id": "authored/triage#t001",
            "entry_key": "a41e",
            "symptom": "No sound from a track",
            "devices": [{"id": "ableton/live-12", "revision": None}],
            "source_file": "triage/no-sound-from-track.md",
            "line": 7,
            "causes": [],
        },
        {
            "passage_id": "authored/triage#t002",
            "entry_key": "b52f",
            "symptom": "Crackling audio",
            "devices": [{"id": "focusrite/scarlett-solo-4g", "revision": None}],
            "source_file": "triage/crackling-audio.md",
            "line": 3,
            "causes": [],
        },
    ],
    "report": {"entries": 2, "rejected": 0, "flagged": 0},
}


def build_index(
    root,
    *,
    view="views/aaaa",
    revision="rev-1",
    index_version=INDEX_VERSION,
    source_ids=None,
    sidecar_filename="authored_triage.json",
    vector_rows=None,
):
    """Write a complete index tree and return its root, manifest last."""
    index_dir = root / "index"
    view_dir = index_dir / view
    (view_dir / "reports").mkdir(parents=True, exist_ok=True)

    keep = {s["source_id"] for s in SOURCES} if source_ids is None else set(source_ids)
    sources = [s for s in SOURCES if s["source_id"] in keep]
    passages = [p for p in PASSAGES if p["source_id"] in keep]

    (view_dir / "sources.json").write_text(json.dumps(sources))
    (view_dir / "passages.jsonl").write_text(
        "".join(json.dumps(p) + "\n" for p in passages)
    )

    rows = len(passages) if vector_rows is None else vector_rows
    vectors = np.arange(rows * VECTOR_DIM, dtype=np.float32).reshape(rows, VECTOR_DIM)
    np.save(view_dir / "vectors.npy", vectors)

    tokens = bm25s.tokenize(
        [p["text"] for p in passages], stopwords=None, show_progress=False
    )
    lexical = bm25s.BM25()
    lexical.index(tokens, show_progress=False)
    lexical.save(str(view_dir / "lexical"))

    (view_dir / "gaps.json").write_text(json.dumps(GAPS))

    if any(s["kind"] == "authored-triage" for s in sources):
        entries = [
            e
            for e in SIDECAR["passages"]
            if any(p["passage_id"] == e["passage_id"] for p in passages)
        ]
        (view_dir / "reports" / sidecar_filename).write_text(
            json.dumps({"passages": entries, "report": SIDECAR["report"]})
        )

    manifest_sources = []
    row_start = 0
    for record in sources:
        count = sum(1 for p in passages if p["source_id"] == record["source_id"])
        manifest_sources.append(
            {
                "source_id": record["source_id"],
                "kind": record["kind"],
                "fingerprint": f"sha256:{record['source_id']}",
                "chunk_count": count,
                "row_start": row_start,
                "row_count": count,
            }
        )
        row_start += count

    manifest = {
        "index_version": index_version,
        "view_dir": view,
        "corpus_revision": revision,
        "built_at": "2026-08-14T10:00:00Z",
        "ingestion_version": 7,
        "embedding": {"model": "BAAI/bge-small-en-v1.5", "dim": VECTOR_DIM, "normalised": True},
        "sources": manifest_sources,
    }
    (index_dir / "manifest.json").write_text(json.dumps(manifest))
    return index_dir


def bump_mtime(path):
    """Force a distinct stat without relying on filesystem timestamp granularity."""
    stat = os.stat(path)
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))


class TestLoad:
    def test_reads_the_whole_view(self, tmp_path):
        view = CorpusView.load(build_index(tmp_path))

        assert view.corpus_revision == "rev-1"
        assert view.vectors.shape == (5, VECTOR_DIM)
        assert isinstance(view.vectors, np.memmap)  # mmapped, not read into memory
        assert [p["passage_id"] for p in view.passages] == [p["passage_id"] for p in PASSAGES]
        assert view.passages_by_id["ableton/live-12#a001"]["section_number"] == "16.4"
        assert set(view.sources_by_id) == {s["source_id"] for s in SOURCES}
        assert view.gaps == GAPS
        assert isinstance(view.lexical, bm25s.BM25)
        assert set(view.sidecar) == {"authored/triage#t001", "authored/triage#t002"}
        assert view.sidecar["authored/triage#t001"]["devices"] == [
            {"id": "ableton/live-12", "revision": None}
        ]

    def test_refuses_an_index_version_it_cannot_interpret(self, tmp_path):
        # Manifest first: the refusal names the version and reads nothing else,
        # so the bad-version tree needs no view artefacts at all.
        index_dir = tmp_path / "index"
        index_dir.mkdir()
        (index_dir / "manifest.json").write_text(
            json.dumps({"index_version": INDEX_VERSION + 1, "view_dir": "views/aaaa"})
        )

        with pytest.raises(ViewLoadError, match="index_version"):
            CorpusView.load(index_dir)

    def test_row_or_vector_count_mismatch_fails_loudly(self, tmp_path):
        # A view whose artefacts disagree is partial; nothing partial is served.
        index_dir = build_index(tmp_path, vector_rows=4)

        with pytest.raises(ViewLoadError):
            CorpusView.load(index_dir)


class TestRowSlices:
    def test_slices_come_from_the_manifest(self, tmp_path):
        index_dir = build_index(tmp_path)
        view = CorpusView.load(index_dir)
        manifest = json.loads((index_dir / "manifest.json").read_text())

        for entry in manifest["sources"]:
            expected = slice(entry["row_start"], entry["row_start"] + entry["row_count"])
            assert view.row_slice(entry["source_id"]) == expected

    def test_a_slice_addresses_exactly_its_sources_rows(self, tmp_path):
        view = CorpusView.load(build_index(tmp_path))

        rows = view.passages[view.row_slice("authored/triage")]
        assert [p["source_id"] for p in rows] == ["authored/triage", "authored/triage"]
        assert view.vectors[view.row_slice("authored/triage")].shape == (2, VECTOR_DIM)

    def test_an_unknown_source_id_raises(self, tmp_path):
        view = CorpusView.load(build_index(tmp_path))

        with pytest.raises(KeyError):
            view.row_slice("behringer/x32")


class TestSidecar:
    def test_the_name_is_derived_by_the_slug_rule(self):
        # From the constant `authored/triage`, never spelled — and never hyphenated.
        assert sidecar_name("authored/triage") == "authored_triage.json"

    def test_a_hyphenated_sidecar_fails_loudly_at_load(self, tmp_path):
        # The silent version of this failure serves the view with no device
        # declarations, so every entry stays in scope for every turn — exactly
        # what 5.13 exists to prevent.
        index_dir = build_index(tmp_path, sidecar_filename="authored-triage.json")

        with pytest.raises(ViewLoadError, match="authored_triage.json"):
            CorpusView.load(index_dir)

    def test_a_view_without_the_authored_source_needs_none(self, tmp_path):
        index_dir = build_index(
            tmp_path, source_ids={"ableton/live-12", "focusrite/scarlett-solo-4g"}
        )
        view = CorpusView.load(index_dir)

        assert view.sidecar == {}


class TestRevisionWatch:
    def test_startup_with_no_manifest_is_no_view(self, tmp_path):
        # Gate 1's corpus-empty, not a fault: the corpus honestly has nothing.
        (tmp_path / "index").mkdir()
        watcher = ViewWatcher(tmp_path / "index")

        assert watcher.view is None
        assert watcher.manifest_fault is None

    def test_startup_refusal_propagates(self, tmp_path):
        index_dir = build_index(tmp_path, index_version=INDEX_VERSION + 1)

        with pytest.raises(ViewLoadError, match="index_version"):
            ViewWatcher(index_dir)

    def test_an_unchanged_manifest_keeps_the_view(self, tmp_path):
        watcher = ViewWatcher(build_index(tmp_path))
        view = watcher.view

        watcher.check()
        watcher.check()

        assert watcher.view is view

    def test_a_touch_without_a_revision_change_does_not_swap(self, tmp_path):
        index_dir = build_index(tmp_path)
        watcher = ViewWatcher(index_dir)
        view = watcher.view

        bump_mtime(index_dir / "manifest.json")
        watcher.check()

        assert watcher.view is view

    def test_a_revision_change_swaps_the_view_wholesale(self, tmp_path):
        index_dir = build_index(tmp_path)
        watcher = ViewWatcher(index_dir)
        old = watcher.view

        build_index(
            tmp_path,
            view="views/bbbb",
            revision="rev-2",
            source_ids={"ableton/live-12", "authored/triage"},
        )
        bump_mtime(index_dir / "manifest.json")
        watcher.check()

        new = watcher.view
        assert new is not old
        assert new.corpus_revision == "rev-2"
        # Nothing partial is reused — vectors, lexical, passages, sources,
        # gaps, sidecar — so no answer can mix revisions.
        assert new.vectors is not old.vectors
        assert new.lexical is not old.lexical
        assert new.passages is not old.passages
        assert new.sources_by_id is not old.sources_by_id
        assert new.gaps is not old.gaps
        assert new.sidecar is not old.sidecar
        assert "focusrite/scarlett-solo-4g" not in new.sources_by_id

    def test_an_in_flight_turn_keeps_its_files(self, tmp_path):
        index_dir = build_index(tmp_path)
        watcher = ViewWatcher(index_dir)
        held = watcher.view
        checksum = float(np.sum(held.vectors))

        build_index(tmp_path, view="views/bbbb", revision="rev-2")
        bump_mtime(index_dir / "manifest.json")
        watcher.check()

        # The turn that loaded `held` before the swap still reads its own
        # revision; the corpus deletes superseded views at the next run, not now.
        assert held.corpus_revision == "rev-1"
        assert len(held.passages) == 5
        assert float(np.sum(held.vectors)) == checksum

    def test_an_unreadable_new_manifest_keeps_the_live_view(self, tmp_path):
        index_dir = build_index(tmp_path)
        watcher = ViewWatcher(index_dir)
        view = watcher.view

        (index_dir / "manifest.json").write_text("{not json")
        bump_mtime(index_dir / "manifest.json")
        watcher.check()

        # Never mapped to corpus-empty — the corpus is not empty, and the
        # mismatch is recorded for GET /sources to report.
        assert watcher.view is view
        assert watcher.view is not None
        assert watcher.manifest_fault

    def test_a_new_manifest_with_a_wrong_version_keeps_the_live_view(self, tmp_path):
        index_dir = build_index(tmp_path)
        watcher = ViewWatcher(index_dir)
        view = watcher.view

        build_index(tmp_path, view="views/bbbb", revision="rev-2", index_version=INDEX_VERSION + 1)
        bump_mtime(index_dir / "manifest.json")
        watcher.check()

        assert watcher.view is view
        assert watcher.manifest_fault
        assert "index_version" in watcher.manifest_fault

    def test_a_broken_new_view_keeps_the_live_view(self, tmp_path):
        index_dir = build_index(tmp_path)
        watcher = ViewWatcher(index_dir)
        view = watcher.view

        build_index(
            tmp_path, view="views/bbbb", revision="rev-2", sidecar_filename="authored-triage.json"
        )
        bump_mtime(index_dir / "manifest.json")
        watcher.check()

        # Loud, not silent: the live view keeps serving and the fault names
        # the sidecar the new view should have carried.
        assert watcher.view is view
        assert watcher.manifest_fault
        assert "authored_triage.json" in watcher.manifest_fault

    def test_a_recovered_manifest_clears_the_fault_and_swaps(self, tmp_path):
        index_dir = build_index(tmp_path)
        watcher = ViewWatcher(index_dir)

        (index_dir / "manifest.json").write_text("{not json")
        bump_mtime(index_dir / "manifest.json")
        watcher.check()
        assert watcher.manifest_fault

        build_index(tmp_path, view="views/bbbb", revision="rev-2")
        bump_mtime(index_dir / "manifest.json")
        watcher.check()

        assert watcher.manifest_fault is None
        assert watcher.view.corpus_revision == "rev-2"

    def test_a_removed_manifest_discards_the_view(self, tmp_path):
        index_dir = build_index(tmp_path)
        watcher = ViewWatcher(index_dir)

        (index_dir / "manifest.json").unlink()
        watcher.check()

        assert watcher.view is None

    def test_the_reload_is_run_level_and_never_charged_to_a_turn(self, tmp_path):
        index_dir = build_index(tmp_path)
        watcher = ViewWatcher(index_dir)

        # No reload has happened: the field is absent, not zero.
        assert watcher.corpus_reload_ms is None

        build_index(tmp_path, view="views/bbbb", revision="rev-2")
        bump_mtime(index_dir / "manifest.json")
        watcher.check()

        # The swap is complete before check() returns — before any turn's
        # timer starts — and the cost lands on the run-level watcher figure,
        # not on the view a turn holds.
        assert isinstance(watcher.corpus_reload_ms, float)
        assert watcher.corpus_reload_ms >= 0.0
        assert not hasattr(watcher.view, "corpus_reload_ms")
