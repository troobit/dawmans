"""The per-source shard: the cache key, per-passage reuse and rollback.

Requirements 8.3, 8.4, 8.7, 9.3 and 9.4; design §Incremental behaviour and §Commit
ordering.

A shard is the unit of incremental work. It is reused **only when all four of
`fingerprint`, `ingestion_version`, `embedding.model` and `embedding.dim` match**, and the
first two tests below are the reason the key is not just the fingerprint. Both failures a
fingerprint-only key allows are silent:

- Changing the embedding model reuses every shard, so `vectors.npy` concatenates vectors
  from two models under a manifest declaring one. The on-disk *shape* is unchanged, so
  `index_version` does not catch it and nothing errors — the vectors are simply
  incomparable.
- A bug fixed in table assembly or chunking changes no PDF byte, so the fix reaches
  nothing. That defeats §8's own user story: "adding a manual **or fixing an ingestion
  bug** never becomes a chore."

Rollback (8.7) is scoped to the failing source: artefacts are written to `.tmp` and moved
with `os.replace`, a failed source's `.tmp` files are deleted and its previous shard is
left untouched, and a source that succeeded in the same run commits and stays queryable.
"""

from __future__ import annotations

import json
from dataclasses import replace
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
    CacheKey,
    ShardWriteFailed,
    build_shard,
    read_shard,
    shard_paths,
)
from dawmans.index.embed import EMBEDDING_DIM, Embedding
from dawmans.version import INGESTION_VERSION

FINGERPRINT = "sha256:" + "a" * 64
CHANGED = "sha256:" + "b" * 64
BUILT_AT = "2026-08-15T10:00:00+00:00"
LATER = "2026-08-16T11:00:00+00:00"


def commit(
    index_root: Path,
    *,
    source=None,
    chunks=None,
    embedder=None,
    fingerprint: str = FINGERPRINT,
    store: str = "manuals",
    ingested_at: str = BUILT_AT,
    **kwargs,
):
    source = source or record()
    return build_shard(
        index_root,
        record=source,
        chunks=chunks if chunks is not None else vendor_chunks(source),
        store=store,
        fingerprint=fingerprint,
        embedder=embedder or StubEmbedder(),
        ingested_at=ingested_at,
        **kwargs,
    )


# --- The four artefacts -------------------------------------------------------------------


def test_a_shard_writes_its_four_artefacts_under_the_source_slug(tmp_path: Path) -> None:
    """`<slug>` is `source_id` with its single `/` replaced by `_`, one rule for both
    kinds. The sidecar is absent because this loader publishes none."""
    shard = commit(tmp_path)

    assert shard.slug == "ableton_live-12"
    names = sorted(path.name for path in (tmp_path / "shards").iterdir())
    assert names == [
        "ableton_live-12.meta.json",
        "ableton_live-12.passages.jsonl",
        "ableton_live-12.vectors.npy",
    ]


def test_the_meta_carries_the_record_the_store_and_the_whole_cache_key(tmp_path: Path) -> None:
    """9.1 works off cached shards, so the full `SourceRecord` is in the meta rather than
    re-derived; the store is there so removal is scoped by the store the source was
    discovered in (9.5) rather than by the scan that happens to be running."""
    commit(tmp_path)

    meta = json.loads((tmp_path / "shards" / "ableton_live-12.meta.json").read_text())

    assert meta["source"]["source_id"] == "ableton/live-12"
    assert meta["source"]["kind"] == "vendor-manual"
    assert meta["store"] == "manuals"
    assert meta["fingerprint"] == FINGERPRINT
    assert meta["ingestion_version"] == INGESTION_VERSION
    assert meta["embedding"] == StubEmbedder().descriptor.to_dict()
    assert meta["row_count"] == meta["source"]["chunk_count"]
    assert meta["ingested_at"] == BUILT_AT


def test_row_i_of_the_shard_vectors_is_line_i_of_its_passages(tmp_path: Path) -> None:
    """The correspondence the merged view extends. It has to hold per shard first, because
    the merge is a plain concatenation and cannot repair an ordering."""
    embedder = StubEmbedder()
    shard = commit(tmp_path, embedder=embedder)

    read = read_shard(tmp_path, shard.slug)
    assert read is not None
    passages = read.passages()
    matrix = read.matrix()
    indexed = list(embedder.encoded)  # what was embedded, in the order it was asked for

    assert matrix.shape == (len(passages), EMBEDDING_DIM)
    assert matrix.dtype == np.float32
    for index, passage in enumerate(passages):
        assert indexed[index].endswith(passage.text)
        assert np.allclose(matrix[index], StubEmbedder().encode([indexed[index]])[0])


def test_the_record_written_to_the_meta_carries_the_final_chunk_count(tmp_path: Path) -> None:
    """The loader cannot know it — the chunker has not run when it returns — so the shard
    build owns it, and the inventory then reads it off the cached meta."""
    chunks = vendor_chunks()
    shard = commit(tmp_path, chunks=chunks)

    assert shard.record.chunk_count == len(chunks)
    assert shard.record.ingested_at == BUILT_AT


def test_the_citation_header_is_indexed_and_is_not_part_of_the_passage_text(
    tmp_path: Path,
) -> None:
    """Decision 2: every chunk is embedded and BM25-indexed with its header. The header is
    not in `Passage.text`, which is what the user is shown when a citation is expanded."""
    embedder = StubEmbedder()
    commit(tmp_path, embedder=embedder)

    assert all("Ableton Live-12 — §2.1" in text for text in embedder.encoded)
    passages = read_shard(tmp_path, "ableton_live-12").passages()
    assert all("Ableton Live-12 — §2.1" not in passage.text for passage in passages)


# --- The four-part cache key (8.3, 9.3) ---------------------------------------------------


def key(**overrides) -> CacheKey:
    base = {
        "fingerprint": FINGERPRINT,
        "ingestion_version": INGESTION_VERSION,
        "embedding": Embedding(model="BAAI/bge-small-en-v1.5", dim=EMBEDDING_DIM),
    }
    return CacheKey(**{**base, **overrides})


def test_a_shard_is_reused_only_when_all_four_components_match(tmp_path: Path) -> None:
    shard = commit(tmp_path)

    assert shard.reusable(key())


def test_a_changed_fingerprint_re_ingests_the_source(tmp_path: Path) -> None:
    """9.3: the source's bytes differ from the ones the shard was built from."""
    shard = commit(tmp_path)

    assert not shard.reusable(key(fingerprint=CHANGED))


def test_a_bumped_ingestion_version_re_ingests_though_no_pdf_byte_changed(
    tmp_path: Path,
) -> None:
    """The silent failure a fingerprint-only key allows: a fix to table assembly or
    chunking reaches nothing, because the PDF it was fixed for is byte-identical."""
    shard = commit(tmp_path)

    assert not shard.reusable(key(ingestion_version=INGESTION_VERSION + 1))


@pytest.mark.parametrize(
    "embedding",
    [
        Embedding(model="BAAI/bge-base-en-v1.5", dim=EMBEDDING_DIM),
        Embedding(model="BAAI/bge-small-en-v1.5", dim=768),
    ],
)
def test_a_changed_embedding_model_or_dimension_re_embeds_the_shard(
    tmp_path: Path, embedding: Embedding
) -> None:
    """The other silent failure: reuse here would concatenate vectors from two models into
    one `vectors.npy` under a manifest declaring one of them. The on-disk shape is
    unchanged, so `index_version` cannot catch it and nothing errors."""
    shard = commit(tmp_path)

    assert not shard.reusable(key(embedding=embedding))


def test_a_shard_meta_predating_the_embedding_block_is_not_reusable(tmp_path: Path) -> None:
    """Absent is not "matches". A shard written before the key existed cannot be shown to
    have come from this model, so it is rebuilt rather than assumed."""
    commit(tmp_path)
    path = tmp_path / "shards" / "ableton_live-12.meta.json"
    meta = json.loads(path.read_text())
    del meta["embedding"]
    path.write_text(json.dumps(meta))

    assert not read_shard(tmp_path, "ableton_live-12").reusable(key())


def test_reading_an_absent_or_unparseable_shard_yields_nothing(tmp_path: Path) -> None:
    """No shard is a change by definition — the source is new (1.2). An unparseable one is
    the same answer: it cannot be shown to match, so it is rebuilt."""
    assert read_shard(tmp_path, "ableton_live-12") is None

    commit(tmp_path)
    (tmp_path / "shards" / "ableton_live-12.meta.json").write_text("{ not json")
    assert read_shard(tmp_path, "ableton_live-12") is None


def test_ingested_at_is_the_time_the_shard_was_built_and_survives_reuse(tmp_path: Path) -> None:
    """It answers "when was this source last actually ingested", which is what makes
    "skipped as unchanged" meaningful in the inventory (1.5). Stamping a reused shard with
    the current run would make every source look freshly ingested."""
    commit(tmp_path, ingested_at=BUILT_AT)

    # A later run that reuses the shard does not rewrite it, so nothing restamps it.
    shard = read_shard(tmp_path, "ableton_live-12")
    assert shard.reusable(key())
    assert shard.record.ingested_at == BUILT_AT
    assert shard.ingested_at == BUILT_AT


# --- Per-passage vector reuse, for the authored store (8.3) -------------------------------


def test_an_authored_shard_records_a_row_for_every_passage(tmp_path: Path) -> None:
    """`passage_id` is content-derived, so an unedited entry's ID is unchanged by
    definition: the reuse key already exists and the map is only the row it points at."""
    chunks = authored_chunks("Check the track's monitor setting.", "Check the input routing.")
    shard = commit(
        tmp_path, source=authored_record(), chunks=chunks, store="triage", fingerprint=FINGERPRINT
    )

    assert shard.vectors == dict(zip(passage_ids(chunks), range(len(chunks)), strict=True))


def test_a_vendor_shard_records_no_vector_map(tmp_path: Path) -> None:
    """One PDF is one document and a changed fingerprint invalidates all of it, so the
    map would be ~40 KB of meta per manual that nothing reads."""
    assert commit(tmp_path).vectors == {}


def test_editing_one_entry_re_embeds_only_that_entry(tmp_path: Path) -> None:
    """The reason the authored shard carries the map at all: re-embedding every entry
    because one was edited is what `data/symptom-triage` cannot afford. The shard is still
    rewritten wholesale, so 9.4 is unaffected."""
    first = authored_chunks("Check the monitor setting.", "Check the input routing.")
    previous = commit(
        tmp_path, source=authored_record(), chunks=first, store="triage", fingerprint=FINGERPRINT
    )

    edited = authored_chunks("Check the monitor setting.", "Check the input routing twice.")
    embedder = StubEmbedder()
    commit(
        tmp_path,
        source=authored_record(),
        chunks=edited,
        store="triage",
        fingerprint=CHANGED,
        embedder=embedder,
        previous=previous,
    )

    assert len(embedder.encoded) == 1
    assert "twice" in embedder.encoded[0]


def test_a_reused_row_is_the_row_the_previous_shard_held(tmp_path: Path) -> None:
    """Copied, not approximated. The unedited entry's vector must be bit-identical or the
    incremental path has quietly diverged from the rebuild it optimises."""
    first = authored_chunks("Check the monitor setting.", "Check the input routing.")
    previous = commit(
        tmp_path, source=authored_record(), chunks=first, store="triage", fingerprint=FINGERPRINT
    )
    before = previous.matrix()[0].copy()

    edited = authored_chunks("Check the monitor setting.", "Check the input routing twice.")
    shard = commit(
        tmp_path,
        source=authored_record(),
        chunks=edited,
        store="triage",
        fingerprint=CHANGED,
        previous=previous,
    )

    assert np.array_equal(shard.matrix()[0], before)


def test_changing_the_embedding_model_re_embeds_every_authored_row(tmp_path: Path) -> None:
    """The three key components that are not per-passage — `ingestion_version`,
    `embedding.model`, `embedding.dim` — invalidate **every** row when they change, map or
    no map."""
    chunks = authored_chunks("Check the monitor setting.", "Check the input routing.")
    previous = commit(
        tmp_path, source=authored_record(), chunks=chunks, store="triage", fingerprint=FINGERPRINT
    )

    embedder = StubEmbedder(model="BAAI/bge-base-en-v1.5")
    commit(
        tmp_path,
        source=authored_record(),
        chunks=chunks,
        store="triage",
        fingerprint=FINGERPRINT,
        embedder=embedder,
        previous=previous,
    )

    assert len(embedder.encoded) == len(chunks)


def test_a_bumped_ingestion_version_re_embeds_every_authored_row(tmp_path: Path) -> None:
    chunks = authored_chunks("Check the monitor setting.", "Check the input routing.")
    previous = commit(
        tmp_path, source=authored_record(), chunks=chunks, store="triage", fingerprint=FINGERPRINT
    )
    stale = replace(previous, ingestion_version=INGESTION_VERSION - 1)

    embedder = StubEmbedder()
    commit(
        tmp_path,
        source=authored_record(),
        chunks=chunks,
        store="triage",
        fingerprint=FINGERPRINT,
        embedder=embedder,
        previous=stale,
    )

    assert len(embedder.encoded) == len(chunks)


def test_re_ingestion_leaves_no_passage_of_the_superseded_version(tmp_path: Path) -> None:
    """9.4. The shard is rewritten wholesale — nothing merges from anywhere else — so a
    removed entry cannot survive in the index even though its vector row was reusable."""
    first = authored_chunks("Check the monitor setting.", "Check the input routing.")
    previous = commit(
        tmp_path, source=authored_record(), chunks=first, store="triage", fingerprint=FINGERPRINT
    )

    kept = authored_chunks("Check the monitor setting.")
    shard = commit(
        tmp_path,
        source=authored_record(),
        chunks=kept,
        store="triage",
        fingerprint=CHANGED,
        previous=previous,
    )

    ids = {passage.passage_id for passage in shard.passages()}
    assert ids == set(passage_ids(kept))
    assert shard.matrix().shape[0] == 1


# --- The sidecar ---------------------------------------------------------------------------


def test_a_sidecar_is_committed_beside_the_passages_it_keys(tmp_path: Path) -> None:
    """It is a **shard** artefact that the merge copies into the view, not something the
    loader writes into a view: a reused shard runs no loader, so a sidecar produced only by
    `load()` would be absent from every view built after the run that produced it."""
    chunks = authored_chunks("Check the monitor setting.")
    sidecar = {passage_ids(chunks)[0]: {"devices": ["ableton/live-12"]}}

    shard = commit(
        tmp_path,
        source=authored_record(),
        chunks=chunks,
        store="triage",
        fingerprint=FINGERPRINT,
        sidecar=sidecar,
    )

    assert shard.sidecar() == sidecar
    assert (tmp_path / "shards" / "authored_triage.sidecar.json").exists()


def test_a_shard_without_a_sidecar_writes_none(tmp_path: Path) -> None:
    shard = commit(tmp_path)

    assert shard.sidecar() is None
    assert not (tmp_path / "shards" / "ableton_live-12.sidecar.json").exists()


# --- Rollback, scoped to the failing source (8.7) ------------------------------------------


class Exploding(StubEmbedder):
    def encode(self, texts: list[str]) -> np.ndarray:
        raise RuntimeError("the model fell over")


def test_a_failed_source_keeps_its_previous_shard_and_leaves_no_tmp_files(
    tmp_path: Path,
) -> None:
    """8.7: the index retains none of the failed attempt's chunks and every one of the
    previously indexed ones, unchanged. Artefacts go to `.tmp` and are moved with
    `os.replace`, so a half-written shard is never at a name the merge reads."""
    good = commit(tmp_path)
    before = (tmp_path / "shards" / "ableton_live-12.passages.jsonl").read_bytes()

    with pytest.raises(ShardWriteFailed):
        commit(tmp_path, fingerprint=CHANGED, embedder=Exploding())

    assert (tmp_path / "shards" / "ableton_live-12.passages.jsonl").read_bytes() == before
    assert read_shard(tmp_path, good.slug).fingerprint == FINGERPRINT
    assert not list((tmp_path / "shards").glob("*.tmp"))


def test_a_source_that_succeeded_in_the_same_run_commits_and_stays_queryable(
    tmp_path: Path,
) -> None:
    """Rollback is scoped to the failing source. There is no abort-on-first-failure path:
    the remaining sources are processed and what they wrote stands."""
    with pytest.raises(ShardWriteFailed):
        commit(tmp_path, source=record("akai/apc-key-25"), embedder=Exploding())

    survivor = commit(tmp_path, source=record("alesis/nitro-max"))

    assert read_shard(tmp_path, "akai_apc-key-25") is None
    assert read_shard(tmp_path, survivor.slug) is not None


def test_a_failure_partway_through_leaves_no_artefact_of_the_new_attempt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The vectors are written after the passages, so a failure between the two is the
    case that would otherwise leave a shard whose row count disagrees with its lines."""
    import numpy as numpy_module

    def explode(*args: object, **kwargs: object) -> None:
        raise OSError("the disk went away")

    monkeypatch.setattr(numpy_module, "save", explode)

    with pytest.raises(ShardWriteFailed):
        commit(tmp_path)

    assert not (tmp_path / "shards").exists() or not list((tmp_path / "shards").iterdir())


def test_the_temporary_names_are_the_committed_names_with_a_suffix(tmp_path: Path) -> None:
    """`os.replace` is atomic only within a filesystem, so the temporary sits beside its
    destination rather than in a system temporary directory."""
    paths = shard_paths(tmp_path, "ableton_live-12")

    assert paths.passages.parent == tmp_path / "shards"
    assert paths.tmp(paths.passages).name == "ableton_live-12.passages.jsonl.tmp"


# --- 8.3's own statement: only the new source is ingested ---------------------------------


def test_a_new_source_leaves_every_unchanged_shard_untouched(tmp_path: Path) -> None:
    """8.3 and 8.4: adding one manual re-extracts, re-chunks and re-indexes nothing else.
    The reuse decision is the whole of it — an unchanged source's loader is never called,
    so the cost of the run is the new source plus the merge."""
    for source_id in ("ableton/live-12", "akai/apc-key-25"):
        commit(tmp_path, source=record(source_id))
    before = {path.name: path.stat().st_mtime_ns for path in (tmp_path / "shards").iterdir()}

    loaded: list[str] = []
    for source_id in ("ableton/live-12", "akai/apc-key-25", "alesis/nitro-max"):
        slug = source_id.replace("/", "_")
        shard = read_shard(tmp_path, slug)
        if shard is not None and shard.reusable(key()):
            continue
        loaded.append(source_id)  # only here does a loader open anything
        commit(tmp_path, source=record(source_id))

    assert loaded == ["alesis/nitro-max"]
    after = {path.name: path.stat().st_mtime_ns for path in (tmp_path / "shards").iterdir()}
    assert all(after[name] == mtime for name, mtime in before.items())
