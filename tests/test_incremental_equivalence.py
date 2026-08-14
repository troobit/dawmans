"""Incremental ingestion equals a full rebuild — requirements 8.3, 8.7, 9.4.

Everything the incremental path does is an optimisation of one thing: reading both stores
and building the index from scratch (8.6). The danger is that it quietly stops being that.
A reuse decision keyed on too little leaves a stale shard in the view; one that removes too
eagerly drops a source; a merge that is not a plain concatenation of the committed shards
lets an edit half-apply. None of those produce an error — they produce an index that is
merely *wrong*, and every other test in this suite checks one run at a time and so cannot
see it.

So this property runs a random add/edit/remove script over a random source set, one
ingestion per step, and then rebuilds the final state into an empty index root. The two
must agree on every byte of `passages.jsonl` and every row of `vectors.npy`: same
passages, same order, same vectors.

The loader here is a stand-in — a body of text in, regions out — because what is under
test is the shard cache, the removal rule and the merge, none of which can tell a PDF from
anything else. That is 12.2 being structural rather than a claim.
"""

from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path

import numpy as np
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from corpusfixtures import StubEmbedder, chunks_of, record, region
from dawmans.corpus.discover import StoreScan, remove_absent_sources, slug
from dawmans.corpus.loader import Discovered
from dawmans.index.build import (
    CacheKey,
    build_shard,
    collect_views,
    commit_view,
    read_shard,
    read_shards,
)

SOURCE_IDS = ["ableton/live-12", "akai/apc-key-25", "alesis/nitro-max", "focusrite/scarlett-solo"]

#: Bodies long enough to pack into more than one chunk for some, one for others, so a
#: script exercises both the single-chunk and the multi-chunk shard.
BODIES = [
    "The tempo control sets the speed of the transport in beats per minute.",
    "Trigger 38 is the snare and trigger 39 is the closed hi-hat on the kit.",
    "The Dry/Wet control sets how much of the processed signal is heard. " * 12,
    "Turn the knob to make the sound quieter as the phrase ends. " * 30,
]

STORE = "manuals"

# (source_id, body) — a body of None is a removal, which is a no-op where the source is
# not in the store, exactly as a removal from the real store would be.
steps = st.lists(
    st.tuples(st.sampled_from(SOURCE_IDS), st.one_of(st.sampled_from(BODIES), st.none())),
    min_size=1,
    max_size=8,
)


def fingerprint(body: str) -> str:
    return f"sha256:{hashlib.sha256(body.encode()).hexdigest()}"


def scan(store: dict[str, str]) -> StoreScan:
    """The store's discovery set, as `manuals/` would report it."""
    return StoreScan(
        store=STORE,
        available=True,
        sources=tuple(
            Discovered(source_id=source_id, fingerprint=fingerprint(body), origin=Path(source_id))
            for source_id, body in sorted(store.items())
        ),
    )


def ingest(index_root: Path, store: dict[str, str], embedder: StubEmbedder, run: int) -> None:
    """One ingestion run, in the order the CLI performs it.

    Collect the superseded views, discover, remove what the store no longer holds, ingest
    only the sources whose cache key does not match, then merge and rename the manifest.
    """
    collect_views(index_root)
    scanned = scan(store)
    remove_absent_sources([scanned], index_root)

    for discovered in scanned.sources:
        key = CacheKey.of(discovered.fingerprint, embedder)
        shard = read_shard(index_root, slug(discovered.source_id))
        if shard is not None and shard.reusable(key):
            continue  # the loader is not called at all: 8.3

        source = record(discovered.source_id)
        body = store[discovered.source_id]
        build_shard(
            index_root,
            record=source,
            chunks=chunks_of(source, region(body, page=3)),
            store=STORE,
            fingerprint=discovered.fingerprint,
            embedder=embedder,
            ingested_at=f"2026-08-15T10:{run:02d}:00+00:00",
        )

    commit_view(
        index_root,
        shards=read_shards(index_root),
        embedding=embedder.descriptor,
        built_at=f"2026-08-15T11:{run:02d}:00+00:00",
    )


def view_bytes(index_root: Path) -> tuple[bytes, np.ndarray]:
    from dawmans.index.manifest import read_manifest

    manifest = read_manifest(index_root)
    assert manifest is not None
    view = index_root / manifest.view_dir
    with (view / "vectors.npy").open("rb") as handle:
        return (view / "passages.jsonl").read_bytes(), np.load(handle)


@given(script=steps)
@settings(max_examples=30, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_incremental_ingestion_yields_the_same_view_as_a_full_rebuild(
    script: list[tuple[str, str | None]],
) -> None:
    """The property the whole incremental path is an optimisation of.

    Vectors are compared as well as passages, because the cache key's three non-fingerprint
    components exist to stop a stale *vector* surviving a change no passage text records —
    a difference `passages.jsonl` alone cannot show.
    """
    store: dict[str, str] = {}

    with (
        tempfile.TemporaryDirectory() as incremental_dir,
        tempfile.TemporaryDirectory() as rebuild_dir,
    ):
        incremental = Path(incremental_dir)
        embedder = StubEmbedder()

        for run, (source_id, body) in enumerate(script):
            if body is None:
                store.pop(source_id, None)
            else:
                store[source_id] = body
            ingest(incremental, store, embedder, run)

        rebuild = Path(rebuild_dir)
        ingest(rebuild, store, StubEmbedder(), run=0)

        incremental_passages, incremental_vectors = view_bytes(incremental)
        rebuild_passages, rebuild_vectors = view_bytes(rebuild)

        assert incremental_passages == rebuild_passages
        assert np.array_equal(incremental_vectors, rebuild_vectors)


@given(script=steps)
@settings(max_examples=20, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_a_removed_source_leaves_nothing_behind(script: list[tuple[str, str | None]]) -> None:
    """1.4 and 9.4 together: a source gone from its store takes its shard, its sidecar and
    its audit with it, and no passage of it survives in the next view."""
    store: dict[str, str] = {}

    with tempfile.TemporaryDirectory() as directory:
        index_root = Path(directory)
        embedder = StubEmbedder()
        for run, (source_id, body) in enumerate(script):
            if body is None:
                store.pop(source_id, None)
            else:
                store[source_id] = body
            ingest(index_root, store, embedder, run)

        passages, _ = view_bytes(index_root)
        present = {source_id for source_id in SOURCE_IDS if f'"{source_id}#' in passages.decode()}

        assert present == set(store)
        assert {shard.source_id for shard in read_shards(index_root)} == set(store)
