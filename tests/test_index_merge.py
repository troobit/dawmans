"""The merge, the manifest and the atomic view commit.

Requirements 8.6, 8.8-8.11, 9.4, 9.6, 11.6 and 12.7; design §Index layout and
§Commit ordering.

The merged view is the **contract `api/answer-engine` reads**, and everything here is one
of the things that spec is allowed to rely on: `manifest.json` exists only when every
artefact it names is complete; row `i` of `vectors.npy` is line `i` of `passages.jsonl`;
the sources are sorted by `source_id` and each carries a `row_start`/`row_count` slice;
`sources.json` carries every `SourceRecord` field and no filesystem path; and
`reports/<slug>.json` is of the same revision as the passages it keys.

Two of these are guarding against failures that produce no error at all. **Sorting** is
one: filesystem iteration order could change `row_start` offsets between two runs over an
identical source set while `corpus_revision` — hashed over *sorted* triples — stayed the
same, leaving a consumer slicing the wrong rows with no way to notice. **The fresh view
directory** is the other: building into the live paths would let a reader that has already
loaded the manifest pair one version's offsets against another version's rows.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from corpusfixtures import (
    StubEmbedder,
    authored_chunks,
    authored_record,
    passage_ids,
    record,
    vendor_chunks,
)
from dawmans.index.build import (
    build_shard,
    collect_views,
    commit_view,
    read_shard,
    read_shards,
)
from dawmans.index.embed import EMBEDDING_DIM
from dawmans.index.lexical import LexicalIndex
from dawmans.index.manifest import (
    INDEX_VERSION,
    IndexVersionMismatch,
    corpus_revision,
    manifest_path,
    read_manifest,
)
from dawmans.records import Passage, SourceRecord

FIRST = "2026-08-15T10:00:00+00:00"
SECOND = "2026-08-15T11:00:00+00:00"
THIRD = "2026-08-15T12:00:00+00:00"


def digest(source_id: str) -> str:
    return "sha256:" + f"{abs(hash(source_id)):064x}"[:64]


def commit(index_root: Path, source_id: str, *, fingerprint: str | None = None, **kwargs):
    source = record(source_id)
    return build_shard(
        index_root,
        record=source,
        chunks=vendor_chunks(source),
        store="manuals",
        fingerprint=fingerprint or digest(source_id),
        embedder=StubEmbedder(),
        ingested_at=FIRST,
        **kwargs,
    )


def commit_authored(
    index_root: Path, *bodies: str, sidecar=None, fingerprint="sha256:aa", **kwargs
):
    chunks = authored_chunks(*bodies)
    return build_shard(
        index_root,
        record=authored_record(),
        chunks=chunks,
        store="triage",
        fingerprint=fingerprint,
        embedder=StubEmbedder(),
        ingested_at=FIRST,
        sidecar=sidecar if sidecar is not None else {passage_ids(chunks)[0]: {"devices": []}},
        **kwargs,
    )


def corpus(index_root: Path) -> None:
    """Three vendor sources committed out of `source_id` order, plus the authored store."""
    for source_id in ("alesis/nitro-max", "ableton/live-12", "akai/apc-key-25"):
        commit(index_root, source_id)
    commit_authored(index_root, "Check the monitor setting.", "Check the input routing.")


# --- Sorting, slices and the row correspondence (8.10) ------------------------------------


def test_the_manifest_sources_are_sorted_by_source_id(tmp_path: Path) -> None:
    """Committed in a different order on purpose. If this derived from filesystem
    iteration, two runs over an identical source set could produce different `row_start`
    offsets under one unchanged `corpus_revision`."""
    corpus(tmp_path)

    commit_view(
        tmp_path, shards=read_shards(tmp_path), embedding=StubEmbedder().descriptor, built_at=FIRST
    )

    ids = [source.source_id for source in read_manifest(tmp_path).sources]
    assert ids == sorted(ids)
    assert ids == ["ableton/live-12", "akai/apc-key-25", "alesis/nitro-max", "authored/triage"]


def test_each_source_slice_addresses_its_own_rows_and_nothing_else(tmp_path: Path) -> None:
    """8.10: restricting matching to a chosen subset of sources reads none of the passages
    of the sources left out, because the restriction is a slice."""
    corpus(tmp_path)
    manifest = commit_view(
        tmp_path, shards=read_shards(tmp_path), embedding=StubEmbedder().descriptor, built_at=FIRST
    )
    view = tmp_path / manifest.view_dir

    lines = [json.loads(line) for line in (view / "passages.jsonl").read_text().splitlines()]
    for source in manifest.sources:
        rows = lines[source.row_start : source.row_start + source.row_count]
        assert len(rows) == source.chunk_count
        assert {row["source_id"] for row in rows} == {source.source_id}

    assert sum(source.row_count for source in manifest.sources) == len(lines)


def test_row_i_of_the_view_vectors_is_line_i_of_its_passages(tmp_path: Path) -> None:
    """The guarantee the whole view rests on. The merge is a plain concatenation in the
    same order, so it holds by construction — and is asserted because nothing downstream
    could detect its failure."""
    corpus(tmp_path)
    manifest = commit_view(
        tmp_path, shards=read_shards(tmp_path), embedding=StubEmbedder().descriptor, built_at=FIRST
    )
    view = tmp_path / manifest.view_dir

    lines = (view / "passages.jsonl").read_text().splitlines()
    with (view / "vectors.npy").open("rb") as handle:
        matrix = np.load(handle)

    assert matrix.shape == (len(lines), EMBEDDING_DIM)
    assert matrix.dtype == np.float32

    offset = next(s.row_start for s in manifest.sources if s.source_id == "akai/apc-key-25")
    shard = read_shard(tmp_path, "akai_apc-key-25")
    assert np.array_equal(matrix[offset : offset + shard.row_count], shard.matrix())


def test_both_kinds_of_matching_are_available_over_the_same_passages(tmp_path: Path) -> None:
    """8.8 in its own terms: neither the dense nor the lexical artefact alone satisfies it,
    so both are built over one passage ordering. Document `i` of the lexical index, row `i`
    of `vectors.npy` and line `i` of `passages.jsonl` are the same passage."""
    corpus(tmp_path)
    manifest = commit_view(
        tmp_path, shards=read_shards(tmp_path), embedding=StubEmbedder().descriptor, built_at=FIRST
    )
    view = tmp_path / manifest.view_dir

    lexical = LexicalIndex.load(view / "lexical")
    lines = [json.loads(line) for line in (view / "passages.jsonl").read_text().splitlines()]

    assert lexical.document_count == len(lines)
    hit, _ = lexical.search("transport")[0]
    assert "transport" in lines[hit]["text"]


def test_the_citation_header_is_lexically_retrievable_and_is_not_in_the_passage_text(
    tmp_path: Path,
) -> None:
    """Decision 2 indexes the header with the text; the text is what the user is shown
    when a citation is expanded, so the header is not repeated there."""
    corpus(tmp_path)
    manifest = commit_view(
        tmp_path, shards=read_shards(tmp_path), embedding=StubEmbedder().descriptor, built_at=FIRST
    )
    view = tmp_path / manifest.view_dir

    lexical = LexicalIndex.load(view / "lexical")
    lines = [json.loads(line) for line in (view / "passages.jsonl").read_text().splitlines()]

    hit, _ = lexical.search("nitro-max")[0]
    assert lines[hit]["source_id"] == "alesis/nitro-max"
    assert all("Nitro-Max —" not in line["text"] for line in lines)


# --- What is readable from the view, with no source PDF (8.9, 9.6, 11.6, 12.7) ------------


def test_every_passage_field_is_readable_and_no_field_is_added(tmp_path: Path) -> None:
    """The view's `passages.jsonl` is the CONTRACTS §2 record and nothing else — the
    shard's own copy carries the citation header beside it, and that stays in the cache."""
    corpus(tmp_path)
    manifest = commit_view(
        tmp_path, shards=read_shards(tmp_path), embedding=StubEmbedder().descriptor, built_at=FIRST
    )

    lines = [
        json.loads(line)
        for line in (tmp_path / manifest.view_dir / "passages.jsonl").read_text().splitlines()
    ]
    expected = {field.name for field in Passage.__dataclass_fields__.values()}

    assert all(set(line) == expected for line in lines)
    authored = [line for line in lines if line["source_id"] == "authored/triage"]
    assert all(line["entry_location"] is not None for line in authored)
    assert all(line["page_start"] is None for line in authored)


def test_every_source_record_field_is_readable_including_kind_and_applicability(
    tmp_path: Path,
) -> None:
    """9.1, 9.6, 11.6 and 12.7 together: a citation can be rendered and its applicability
    judged without opening the document it came from."""
    corpus(tmp_path)
    manifest = commit_view(
        tmp_path, shards=read_shards(tmp_path), embedding=StubEmbedder().descriptor, built_at=FIRST
    )

    sources = json.loads((tmp_path / manifest.view_dir / "sources.json").read_text())
    expected = {field.name for field in SourceRecord.__dataclass_fields__.values()}

    assert all(set(source) == expected for source in sources)
    authored = next(s for s in sources if s["source_id"] == "authored/triage")
    assert authored["kind"] == "authored-triage"
    assert authored["hardware_applicability"]["status"] == "assumed"
    assert authored["page_count"] is None  # not applicable, not invented (12.5)


def test_sources_json_carries_no_filesystem_path(tmp_path: Path) -> None:
    """2.7: a `vendor-manual`'s filename is reconstructed from its own five fields, and a
    published path would be a field the browser cannot use anyway."""
    corpus(tmp_path)
    manifest = commit_view(
        tmp_path, shards=read_shards(tmp_path), embedding=StubEmbedder().descriptor, built_at=FIRST
    )

    text = (tmp_path / manifest.view_dir / "sources.json").read_text()

    assert ".pdf" not in text
    assert str(tmp_path) not in text


def test_the_rig_gap_reports_are_published_into_the_view(tmp_path: Path) -> None:
    """11.6. Written before the manifest rename, like everything else in the view."""
    corpus(tmp_path)
    gaps = {"owned_but_undocumented": [], "documented_but_unconfirmed": ["akai/apc-key-25"]}

    manifest = commit_view(
        tmp_path,
        shards=read_shards(tmp_path),
        embedding=StubEmbedder().descriptor,
        built_at=FIRST,
        gaps=gaps,
    )

    assert json.loads((tmp_path / manifest.view_dir / "gaps.json").read_text()) == gaps


# --- Self-describing artefacts (8.11) ------------------------------------------------------


def test_the_corpus_revision_changes_when_and_only_when_the_content_does(
    tmp_path: Path,
) -> None:
    """One cheap read is what `api/answer-engine` uses to discard cached retrieval state
    (its 5.10), so a revision that moved on an unchanged corpus would throw that state away
    every run, and one that did not move on a changed corpus would keep it forever."""
    corpus(tmp_path)
    shards = read_shards(tmp_path)

    first = commit_view(
        tmp_path, shards=shards, embedding=StubEmbedder().descriptor, built_at=FIRST
    )
    again = commit_view(
        tmp_path, shards=shards, embedding=StubEmbedder().descriptor, built_at=SECOND
    )
    assert again.corpus_revision == first.corpus_revision

    commit(tmp_path, "ableton/live-12", fingerprint="sha256:" + "f" * 64)
    changed = commit_view(
        tmp_path, shards=read_shards(tmp_path), embedding=StubEmbedder().descriptor, built_at=THIRD
    )
    assert changed.corpus_revision != first.corpus_revision


def test_the_revision_is_hashed_over_sorted_triples(tmp_path: Path) -> None:
    """So it is a property of the corpus rather than of the order the shards were read."""
    triples = [("b/two", "sha256:2", 5), ("a/one", "sha256:1", 3)]

    assert corpus_revision(triples) == corpus_revision(list(reversed(triples)))
    assert corpus_revision(triples) != corpus_revision([("b/two", "sha256:2", 6), triples[1]])


def test_a_reader_expecting_a_different_index_version_refuses_to_load(tmp_path: Path) -> None:
    """8.11: it refuses rather than interpreting the files. The fix is a rebuild, which
    costs about half a minute."""
    corpus(tmp_path)
    commit_view(
        tmp_path, shards=read_shards(tmp_path), embedding=StubEmbedder().descriptor, built_at=FIRST
    )

    path = manifest_path(tmp_path)
    data = json.loads(path.read_text())
    data["index_version"] = INDEX_VERSION + 1
    path.write_text(json.dumps(data))

    with pytest.raises(IndexVersionMismatch):
        read_manifest(tmp_path)


def test_a_shard_from_a_different_model_cannot_be_merged_under_this_manifest(
    tmp_path: Path,
) -> None:
    """The failure the four-part cache key exists to prevent, caught again at the merge:
    `vectors.npy` would concatenate vectors from two models under a manifest declaring
    one, and nothing about the on-disk shape would say so."""
    commit(tmp_path, "ableton/live-12")
    source = record("akai/apc-key-25")
    build_shard(
        tmp_path,
        record=source,
        chunks=vendor_chunks(source),
        store="manuals",
        fingerprint=digest("akai/apc-key-25"),
        embedder=StubEmbedder(model="BAAI/bge-base-en-v1.5"),
        ingested_at=FIRST,
    )

    with pytest.raises(ValueError, match="bge-base-en-v1.5"):
        commit_view(
            tmp_path,
            shards=read_shards(tmp_path),
            embedding=StubEmbedder().descriptor,
            built_at=FIRST,
        )


# --- The atomic commit (8.7, design §Commit ordering) -------------------------------------


def test_the_view_is_built_fresh_and_the_manifest_rename_is_the_only_switch(
    tmp_path: Path,
) -> None:
    """A reader sees the old manifest with the old view or the new with the new, never a
    mix. `lexical/` is a directory and cannot be swapped by a file rename at all, which is
    why the whole view is fresh and only the manifest moves."""
    corpus(tmp_path)
    first = commit_view(
        tmp_path, shards=read_shards(tmp_path), embedding=StubEmbedder().descriptor, built_at=FIRST
    )
    before = (tmp_path / first.view_dir / "passages.jsonl").read_bytes()

    commit(tmp_path, "ableton/live-12", fingerprint="sha256:" + "f" * 64)
    second = commit_view(
        tmp_path, shards=read_shards(tmp_path), embedding=StubEmbedder().descriptor, built_at=SECOND
    )

    assert second.view_dir != first.view_dir
    assert (tmp_path / first.view_dir / "passages.jsonl").read_bytes() == before
    assert read_manifest(tmp_path).view_dir == second.view_dir


def test_a_manifest_exists_only_when_every_artefact_it_names_is_complete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The manifest is renamed last, so a run that dies partway leaves the previous one
    live and its abandoned view unnamed."""
    corpus(tmp_path)
    commit_view(
        tmp_path, shards=read_shards(tmp_path), embedding=StubEmbedder().descriptor, built_at=FIRST
    )
    live = read_manifest(tmp_path)

    import dawmans.index.build as build_module

    monkeypatch.setattr(
        build_module.LexicalIndex,
        "build",
        staticmethod(lambda texts: (_ for _ in ()).throw(OSError("boom"))),
    )
    with pytest.raises(OSError):
        commit_view(
            tmp_path,
            shards=read_shards(tmp_path),
            embedding=StubEmbedder().descriptor,
            built_at=SECOND,
        )

    assert read_manifest(tmp_path) == live
    assert (tmp_path / live.view_dir / "passages.jsonl").exists()


def test_views_the_live_manifest_does_not_name_are_deleted_at_the_start_of_the_next_run(
    tmp_path: Path,
) -> None:
    """Not immediately: a reader still working from the previous manifest keeps its files
    until the run after the one that superseded them."""
    corpus(tmp_path)
    first = commit_view(
        tmp_path, shards=read_shards(tmp_path), embedding=StubEmbedder().descriptor, built_at=FIRST
    )
    second = commit_view(
        tmp_path, shards=read_shards(tmp_path), embedding=StubEmbedder().descriptor, built_at=SECOND
    )

    assert (tmp_path / first.view_dir).exists()  # still there, one run later

    collected = collect_views(tmp_path)

    assert collected == [tmp_path / first.view_dir]
    assert not (tmp_path / first.view_dir).exists()
    assert (tmp_path / second.view_dir).exists()


def test_collecting_views_with_no_live_manifest_deletes_nothing(tmp_path: Path) -> None:
    """A missing manifest names no view, and treating that as "name nothing, so delete
    everything" would empty the index on the first run after a failed one."""
    corpus(tmp_path)
    commit_view(
        tmp_path, shards=read_shards(tmp_path), embedding=StubEmbedder().descriptor, built_at=FIRST
    )
    manifest_path(tmp_path).unlink()

    assert collect_views(tmp_path) == []
    assert list((tmp_path / "views").iterdir())


# --- The sidecar: revision pairing and survival through reuse ------------------------------


def test_every_passage_a_sidecar_keys_is_in_the_view_it_sits_in(tmp_path: Path) -> None:
    """The two report directories are named differently on purpose — `audits/` beside the
    views, `reports/` inside one — so a reader resolving the wrong one gets an error rather
    than a well-formed JSON document keyed by something else."""
    corpus(tmp_path)
    manifest = commit_view(
        tmp_path, shards=read_shards(tmp_path), embedding=StubEmbedder().descriptor, built_at=FIRST
    )
    view = tmp_path / manifest.view_dir

    sidecar = json.loads((view / "reports" / "authored_triage.json").read_text())
    present = {
        json.loads(line)["passage_id"]
        for line in (view / "passages.jsonl").read_text().splitlines()
    }

    assert sidecar
    assert set(sidecar) <= present
    assert not (view / "audits").exists()


def test_a_second_run_leaves_the_previous_views_sidecar_byte_identical(tmp_path: Path) -> None:
    """The sidecar is copied into a view that is built fresh, so no sidecar is ever written
    to a view a reader can already see."""
    corpus(tmp_path)
    first = commit_view(
        tmp_path, shards=read_shards(tmp_path), embedding=StubEmbedder().descriptor, built_at=FIRST
    )
    before = (tmp_path / first.view_dir / "reports" / "authored_triage.json").read_bytes()

    edited = authored_chunks("Check the monitor setting.", "Check the routing again.")
    commit_authored(
        tmp_path,
        "Check the monitor setting.",
        "Check the routing again.",
        fingerprint="sha256:bb",
        sidecar={passage_id: {"devices": []} for passage_id in passage_ids(edited)},
    )
    second = commit_view(
        tmp_path, shards=read_shards(tmp_path), embedding=StubEmbedder().descriptor, built_at=SECOND
    )

    assert (tmp_path / first.view_dir / "reports" / "authored_triage.json").read_bytes() == before
    assert (tmp_path / second.view_dir / "reports" / "authored_triage.json").read_bytes() != before


def test_a_run_that_reuses_every_shard_still_produces_a_view_holding_each_sidecar(
    tmp_path: Path,
) -> None:
    """A sidecar produced only by `load()` would be absent from every view built after the
    run that produced it. It is copied from the shard, so a run that called no loader at
    all still publishes it."""
    corpus(tmp_path)
    commit_view(
        tmp_path, shards=read_shards(tmp_path), embedding=StubEmbedder().descriptor, built_at=FIRST
    )

    # A second run in which nothing was re-ingested: the shards are simply read back.
    second = commit_view(
        tmp_path, shards=read_shards(tmp_path), embedding=StubEmbedder().descriptor, built_at=SECOND
    )

    assert (tmp_path / second.view_dir / "reports" / "authored_triage.json").exists()


def test_a_source_whose_loader_publishes_no_sidecar_gets_no_report(tmp_path: Path) -> None:
    """A missing sidecar for a source whose kind is known to publish one is a fault for the
    reader to raise; a vendor manual publishes none and must not get an empty default."""
    corpus(tmp_path)
    manifest = commit_view(
        tmp_path, shards=read_shards(tmp_path), embedding=StubEmbedder().descriptor, built_at=FIRST
    )

    names = sorted(path.name for path in (tmp_path / manifest.view_dir / "reports").iterdir())
    assert names == ["authored_triage.json"]


# --- Audit lifetime -------------------------------------------------------------------------


def test_a_rejected_sources_audit_outlives_the_view_it_accompanied(tmp_path: Path) -> None:
    """The two report locations exist because there are two lifetimes. An audit is a
    diagnostic for one run over one source: inside a view it would be deleted with every
    superseded view, so the diagnostics for the run that rejected a source would be gone by
    the end of the next one."""
    corpus(tmp_path)
    audit = tmp_path / "audits" / "focusrite_scarlett-solo-4g.json"
    audit.parent.mkdir(parents=True, exist_ok=True)
    audit.write_text(json.dumps({"rejection": "no-text-layer"}))

    for stamp in (FIRST, SECOND, THIRD):
        commit_view(
            tmp_path,
            shards=read_shards(tmp_path),
            embedding=StubEmbedder().descriptor,
            built_at=stamp,
        )
        collect_views(tmp_path)

    assert json.loads(audit.read_text())["rejection"] == "no-text-layer"


# --- 8.6: a rebuild from the two stores alone ----------------------------------------------


def test_a_full_rebuild_reproduces_the_index_with_no_other_input(tmp_path: Path) -> None:
    """8.6. The same sources ingested into an empty index root give the same passages, the
    same order and the same corpus revision — so `index/` is derived, gitignored, and its
    remedy for any doubt is deletion."""
    incremental = tmp_path / "incremental"
    rebuild = tmp_path / "rebuild"

    corpus(incremental)
    first = commit_view(
        incremental,
        shards=read_shards(incremental),
        embedding=StubEmbedder().descriptor,
        built_at=FIRST,
    )

    corpus(rebuild)
    second = commit_view(
        rebuild, shards=read_shards(rebuild), embedding=StubEmbedder().descriptor, built_at=SECOND
    )

    assert second.corpus_revision == first.corpus_revision
    assert [s.to_dict() for s in second.sources] == [s.to_dict() for s in first.sources]
    assert (rebuild / second.view_dir / "passages.jsonl").read_bytes() == (
        incremental / first.view_dir / "passages.jsonl"
    ).read_bytes()


def test_an_empty_corpus_still_commits_a_readable_view(tmp_path: Path) -> None:
    """Every source rejected is a run that succeeded with nothing to show for it, and a
    reader must get an empty view rather than an unreadable one."""
    manifest = commit_view(tmp_path, shards=[], embedding=StubEmbedder().descriptor, built_at=FIRST)
    view = tmp_path / manifest.view_dir

    assert manifest.sources == ()
    assert (view / "passages.jsonl").read_text() == ""
    assert json.loads((view / "sources.json").read_text()) == []
    assert LexicalIndex.load(view / "lexical").document_count == 0
    with (view / "vectors.npy").open("rb") as handle:
        assert np.load(handle).shape == (0, EMBEDDING_DIM)
