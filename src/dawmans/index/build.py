"""Shard build, merge, and the atomic manifest commit.

A **shard** is one source's contribution to the index and the unit of incremental work:
`shards/<slug>.passages.jsonl`, `.vectors.npy`, an optional `.sidecar.json`, and a
`.meta.json` carrying the full `SourceRecord`, the store the source was discovered in, and
the cache key. A shard is reused only when **all four** of `fingerprint`,
`ingestion_version`, `embedding.model` and `embedding.dim` match (design §Incremental
behaviour); keying on the fingerprint alone is silently wrong twice over, and both ways
are asserted in `tests/test_index_build.py`.

**Commit ordering is what makes 8.7 hold.** Artefacts are written to `.tmp` beside their
destinations and moved into place with `os.replace`, one source at a time, with the meta
moved last — a partly committed set carries no meta and therefore reads as no shard at
all. A source that fails leaves its `.tmp` files, which are deleted, and its previous
shard untouched; a source that succeeded in the same run commits and stays queryable.

The merge is deliberately dull: the view is a plain concatenation of the committed shards
in `source_id` order. Re-ingestion replaces a source's shard wholesale, which is 9.4,
because nothing merges from anywhere else.
"""

from __future__ import annotations

import json
import os
import shutil
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from dawmans.corpus.chunk import Chunk
from dawmans.corpus.discover import slug
from dawmans.index.embed import Embedder, Embedding
from dawmans.index.lexical import LexicalIndex
from dawmans.index.manifest import (
    VIEW_DIR,
    IndexVersionMismatch,
    Manifest,
    SourceSlice,
    corpus_revision,
    read_manifest,
    view_name,
    write_manifest,
)
from dawmans.records import HardwareApplicability, Passage, SourceRecord
from dawmans.version import INGESTION_VERSION

SHARD_DIR = "shards"
AUDIT_DIR = "audits"

#: Written beside the destination, not in a system temporary directory: `os.replace` is
#: atomic only within one filesystem.
TMP_SUFFIX = ".tmp"


class ShardWriteFailed(RuntimeError):
    """One source failed partway through its shard build (8.7).

    Its `.tmp` artefacts have been deleted and its previous shard is untouched. The run
    continues with the remaining sources and exits non-zero; there is no
    abort-on-first-failure path.
    """


# --- The on-disk form of the CONTRACTS records ---------------------------------------------


def record_to_dict(record: SourceRecord) -> dict[str, Any]:
    """Every CONTRACTS §1 field, including the ones this source's kind marks not
    applicable — 9.1 wants them reported as not applicable, and `None` is how JSON says
    that without inventing a value."""
    return asdict(record)


def record_from_dict(data: Mapping[str, Any]) -> SourceRecord:
    fields = dict(data)
    fields["hardware_applicability"] = HardwareApplicability(**fields["hardware_applicability"])
    return SourceRecord(**fields)


def passage_to_dict(passage: Passage) -> dict[str, Any]:
    return asdict(passage)


def passage_from_dict(data: Mapping[str, Any]) -> Passage:
    return Passage(**data)


def _write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False))
            handle.write("\n")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


# --- The cache key ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CacheKey:
    """What a shard has to match to be reused (8.3, 9.3).

    The fingerprint is the source's bytes; the other three are the identity of the process
    that produced the shard. Both halves are needed. Without the fingerprint a changed
    manual is never re-read; without the rest, changing the embedding model reuses every
    shard and `vectors.npy` concatenates vectors from two models under a manifest
    declaring one — the on-disk shape is unchanged, so `index_version` does not catch it.
    """

    fingerprint: str
    ingestion_version: int = INGESTION_VERSION
    embedding: Embedding | None = None

    @classmethod
    def of(cls, fingerprint: str, embedder: Embedder, version: int = INGESTION_VERSION) -> CacheKey:
        return cls(
            fingerprint=fingerprint, ingestion_version=version, embedding=embedder.descriptor
        )


@dataclass(frozen=True)
class ShardPaths:
    """Where one shard's four artefacts live, and where their temporaries go."""

    root: Path
    slug: str

    @property
    def passages(self) -> Path:
        return self.root / f"{self.slug}.passages.jsonl"

    @property
    def vectors(self) -> Path:
        return self.root / f"{self.slug}.vectors.npy"

    @property
    def sidecar(self) -> Path:
        return self.root / f"{self.slug}.sidecar.json"

    @property
    def meta(self) -> Path:
        return self.root / f"{self.slug}.meta.json"

    def tmp(self, path: Path) -> Path:
        return path.with_name(path.name + TMP_SUFFIX)


def shard_paths(index_root: Path, name: str) -> ShardPaths:
    return ShardPaths(root=index_root / SHARD_DIR, slug=name)


@dataclass(frozen=True)
class Shard:
    """One committed shard, as its meta describes it.

    The passages and the vectors are read on demand: the merge needs them, the reuse
    decision does not, and a run that skips every source should touch nothing but the
    metas.
    """

    paths: ShardPaths
    record: SourceRecord
    store: str
    fingerprint: str
    ingestion_version: int
    #: None where the meta predates the block. Absent is not "matches": a shard that
    #: cannot be shown to have come from this model is rebuilt rather than assumed.
    embedding: Embedding | None
    ingested_at: str
    row_count: int
    #: `passage_id` → row index, on a shard whose reuse is per passage. Empty otherwise;
    #: see §Incremental behaviour on why the vendor unit is the whole shard.
    vectors: dict[str, int]

    @property
    def slug(self) -> str:
        return self.paths.slug

    @property
    def source_id(self) -> str:
        return self.record.source_id

    def reusable(self, key: CacheKey) -> bool:
        """All four components, or the source is ingested again."""
        return (
            self.fingerprint == key.fingerprint
            and self.ingestion_version == key.ingestion_version
            and self.embedding is not None
            and self.embedding == key.embedding
        )

    def entries(self) -> list[tuple[Passage, str]]:
        """Each passage with the citation header it is indexed under.

        **The shard's `passages.jsonl` is a cache, not the view's contract.** Its lines
        carry the header beside the passage; the view's carry the CONTRACTS §2 record and
        nothing else. The header has to be on disk somewhere: Decision 2 indexes it with
        the text, `Region.section_path` is part of it, and §2 has no field for that — so a
        reused shard could not be re-indexed without it, and a reused shard is the normal
        case.
        """
        return [
            (passage_from_dict(row["passage"]), row["header"])
            for row in _read_jsonl(self.paths.passages)
        ]

    def passages(self) -> list[Passage]:
        return [passage for passage, _ in self.entries()]

    def matrix(self) -> np.ndarray:
        with self.paths.vectors.open("rb") as handle:
            return np.load(handle)

    def sidecar(self) -> dict[str, Any] | None:
        """The per-`passage_id` data this source's loader published, or None.

        It is a shard artefact rather than something written straight into a view because
        a reused shard runs no loader: a sidecar produced only by `load()` would be absent
        from every view built after the run that produced it.
        """
        if not self.paths.sidecar.exists():
            return None
        return json.loads(self.paths.sidecar.read_text(encoding="utf-8"))


def read_shard(index_root: Path, name: str) -> Shard | None:
    """The committed shard under this slug, or None where there is none to trust.

    An unparseable meta reads as absent rather than raising: it names no store and no
    source, so nothing can tell whether its shard is stale, and the source is simply
    ingested again over the top of it.
    """
    paths = shard_paths(index_root, name)
    try:
        meta = json.loads(paths.meta.read_text(encoding="utf-8"))
        record = record_from_dict(meta["source"])
        return Shard(
            paths=paths,
            record=record,
            store=meta["store"],
            fingerprint=meta["fingerprint"],
            ingestion_version=int(meta["ingestion_version"]),
            embedding=Embedding.from_dict(meta.get("embedding")),
            ingested_at=meta["ingested_at"],
            row_count=int(meta["row_count"]),
            vectors={str(key): int(row) for key, row in meta.get("vectors", {}).items()},
        )
    except (OSError, ValueError, KeyError, TypeError):
        return None


def read_shards(index_root: Path) -> list[Shard]:
    """Every committed shard, sorted by `source_id`.

    Sorting is load-bearing and is done here rather than left to the caller: filesystem
    iteration order could otherwise change `row_start` offsets between two runs over an
    identical source set while `corpus_revision` — hashed over *sorted* triples — stayed
    the same, leaving a consumer slicing the wrong rows.
    """
    try:
        metas = sorted((index_root / SHARD_DIR).glob("*.meta.json"))
    except OSError:
        return []
    shards = [read_shard(index_root, path.name.removesuffix(".meta.json")) for path in metas]
    return sorted((shard for shard in shards if shard is not None), key=lambda s: s.source_id)


def build_shard(
    index_root: Path,
    *,
    record: SourceRecord,
    chunks: Sequence[Chunk],
    store: str,
    fingerprint: str,
    embedder: Embedder,
    sidecar: Mapping[str, Any] | None = None,
    previous: Shard | None = None,
    ingested_at: str | None = None,
    ingestion_version: int = INGESTION_VERSION,
    vector_map: bool | None = None,
) -> Shard:
    """Write one source's shard, atomically (8.7, 9.4).

    The shard is rewritten **wholesale**, which is 9.4: no chunk of the superseded version
    can survive, because the merge reads shards and nothing else. Per-passage reuse
    (below) changes what is embedded, never what is written.

    `vector_map` decides whether the meta records a `passage_id` → row map. It defaults to
    the authored store, where one source holds many independent entries and re-embedding
    all of them because one was edited is what `data/symptom-triage` cannot afford. A
    vendor manual is one document whose fingerprint invalidates all of it, so the map
    would be metadata nothing reads.
    """
    paths = shard_paths(index_root, slug(record.source_id))
    paths.root.mkdir(parents=True, exist_ok=True)

    stamped = replace(
        record,
        chunk_count=len(chunks),
        ingested_at=ingested_at or datetime.now(UTC).isoformat(timespec="seconds"),
    )
    if vector_map is None:
        vector_map = record.kind == "authored-triage"

    pending: list[Path] = []
    try:
        rows = _embed(chunks, embedder, previous, ingestion_version)

        moves: list[tuple[Path, Path]] = []
        passages_tmp = paths.tmp(paths.passages)
        pending.append(passages_tmp)
        _write_jsonl(
            passages_tmp,
            (
                {"passage": passage_to_dict(chunk.passage), "header": chunk.header}
                for chunk in chunks
            ),
        )
        moves.append((passages_tmp, paths.passages))

        vectors_tmp = paths.tmp(paths.vectors)
        pending.append(vectors_tmp)
        with vectors_tmp.open("wb") as handle:
            np.save(handle, rows)
        moves.append((vectors_tmp, paths.vectors))

        if sidecar is not None:
            sidecar_tmp = paths.tmp(paths.sidecar)
            pending.append(sidecar_tmp)
            sidecar_tmp.write_text(json.dumps(sidecar, ensure_ascii=False), encoding="utf-8")
            moves.append((sidecar_tmp, paths.sidecar))

        vectors = (
            {chunk.passage.passage_id: index for index, chunk in enumerate(chunks)}
            if vector_map
            else {}
        )
        meta = {
            "source": record_to_dict(stamped),
            "store": store,
            "fingerprint": fingerprint,
            "ingestion_version": ingestion_version,
            "embedding": embedder.descriptor.to_dict(),
            "ingested_at": stamped.ingested_at,
            "row_count": len(chunks),
            "vectors": vectors,
        }
        meta_tmp = paths.tmp(paths.meta)
        pending.append(meta_tmp)
        meta_tmp.write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
        moves.append((meta_tmp, paths.meta))

        # The meta moves last: a partly committed set carries none and reads as no shard.
        for source, destination in moves:
            os.replace(source, destination)
    except Exception as error:
        for path in pending:
            path.unlink(missing_ok=True)
        raise ShardWriteFailed(f"{record.source_id}: {error}") from error

    return Shard(
        paths=paths,
        record=stamped,
        store=store,
        fingerprint=fingerprint,
        ingestion_version=ingestion_version,
        embedding=embedder.descriptor,
        ingested_at=stamped.ingested_at,
        row_count=len(chunks),
        vectors=vectors,
    )


def _embed(
    chunks: Sequence[Chunk],
    embedder: Embedder,
    previous: Shard | None,
    ingestion_version: int,
) -> np.ndarray:
    """One row per chunk, reusing the previous shard's row where the passage is unchanged.

    `passage_id` is content-derived, so an unedited entry's ID is unchanged by definition —
    the reuse key already exists and the map only says which row it was. The three key
    components that are not per-passage invalidate **every** row when they change, which is
    the whole point of checking them before the map is consulted.

    What is embedded is `chunk.embedded`: the citation header and then the text
    (Decision 2). The header is never part of `Passage.text`.
    """
    dim = embedder.descriptor.dim
    rows = np.zeros((len(chunks), dim), dtype=np.float32)

    reusable: dict[str, int] = {}
    prior: np.ndarray | None = None
    if (
        previous is not None
        and previous.vectors
        and previous.ingestion_version == ingestion_version
        and previous.embedding == embedder.descriptor
    ):
        reusable = previous.vectors
        prior = previous.matrix()

    fresh_slots: list[int] = []
    fresh_texts: list[str] = []
    for index, chunk in enumerate(chunks):
        row = reusable.get(chunk.passage.passage_id)
        if prior is not None and row is not None and 0 <= row < prior.shape[0]:
            rows[index] = prior[row]
        else:
            fresh_slots.append(index)
            fresh_texts.append(chunk.embedded)

    if fresh_texts:
        encoded = embedder.encode(fresh_texts)
        for slot, index in enumerate(fresh_slots):
            rows[index] = encoded[slot]
    return rows


# --- The merge and the atomic view commit --------------------------------------------------


def commit_view(
    index_root: Path,
    *,
    shards: Sequence[Shard],
    embedding: Embedding,
    built_at: str | None = None,
    gaps: Mapping[str, Any] | None = None,
    ingestion_version: int = INGESTION_VERSION,
) -> Manifest:
    """Merge the committed shards into a fresh view and rename the manifest into place.

    The merge is a **plain concatenation** of the shards in `source_id` order, and that is
    9.4: re-ingestion replaces a source's shard wholesale, so no chunk of a superseded
    version can survive, because nothing merges from anywhere else.

    The view is built into a directory no reader can be holding and is never modified
    after it is complete. Building into the live paths would let a reader that had already
    loaded the manifest pair one version's `row_start`/`row_count` against another
    version's rows; and `lexical/` is a directory, which cannot be swapped by a single file
    rename at all. `manifest.json` is renamed last, so that rename is the only switch.
    """
    ordered = sorted(shards, key=lambda shard: shard.source_id)
    for shard in ordered:
        if shard.embedding != embedding:
            raise ValueError(
                f"{shard.source_id}'s shard was embedded with "
                f"{shard.embedding.model if shard.embedding else 'an unrecorded model'}, not "
                f"{embedding.model} — merging them would concatenate vectors from two models "
                f"under a manifest declaring one"
            )

    stamp = built_at or datetime.now(UTC).isoformat(timespec="seconds")
    revision = corpus_revision(
        [(shard.source_id, shard.fingerprint, shard.row_count) for shard in ordered]
    )
    view = _fresh_view(index_root, revision, stamp)

    passages: list[dict[str, Any]] = []
    indexed: list[str] = []
    matrices: list[np.ndarray] = []
    sources: list[SourceSlice] = []
    records: list[dict[str, Any]] = []

    for shard in ordered:
        start = len(passages)
        for passage, header in shard.entries():
            passages.append(passage_to_dict(passage))
            indexed.append(f"{header}\n{passage.text}")
        matrices.append(shard.matrix())
        records.append(record_to_dict(shard.record))
        sources.append(
            SourceSlice(
                source_id=shard.source_id,
                kind=shard.record.kind,
                fingerprint=shard.fingerprint,
                chunk_count=shard.record.chunk_count,
                row_start=start,
                row_count=len(passages) - start,
            )
        )

    _write_jsonl(view / "passages.jsonl", passages)
    (view / "sources.json").write_text(
        json.dumps(records, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    with (view / "vectors.npy").open("wb") as handle:
        np.save(handle, _stack(matrices, embedding.dim))

    # Decision 2: both indexes are built over the citation-header-prefixed text, in one
    # ordering, so document `i`, row `i` and line `i` are the same passage.
    LexicalIndex.build(indexed).save(view / "lexical")

    (view / "gaps.json").write_text(
        json.dumps(gaps if gaps is not None else {}, ensure_ascii=False, indent=1), encoding="utf-8"
    )

    reports = view / "reports"
    reports.mkdir(exist_ok=True)
    for shard in ordered:
        sidecar = shard.sidecar()
        if sidecar is not None:
            (reports / f"{shard.slug}.json").write_text(
                json.dumps(sidecar, ensure_ascii=False, indent=1), encoding="utf-8"
            )

    manifest = Manifest(
        view_dir=str(view.relative_to(index_root)),
        corpus_revision=revision,
        built_at=stamp,
        ingestion_version=ingestion_version,
        embedding=embedding,
        sources=tuple(sources),
    )
    write_manifest(index_root, manifest)
    return manifest


def _stack(matrices: Sequence[np.ndarray], dim: int) -> np.ndarray:
    """One `(N, dim)` float32 array. An empty corpus is `(0, dim)`, not `(0,)`: a reader
    that loads it should get no rows of the right width rather than an array it cannot
    index."""
    populated = [matrix for matrix in matrices if matrix.size]
    if not populated:
        return np.zeros((0, dim), dtype=np.float32)
    return np.vstack(populated).astype(np.float32)


def _fresh_view(index_root: Path, revision: str, built_at: str) -> Path:
    """A directory no committed view occupies, created empty.

    An existing one can only be the wreckage of a run that died before renaming its
    manifest — the name folds in `built_at` — and building over it would mix two runs'
    artefacts under one manifest.
    """
    attempt = 0
    while True:
        view = index_root / VIEW_DIR / view_name(revision, built_at, attempt)
        if not view.exists():
            view.mkdir(parents=True)
            return view
        attempt += 1


def collect_views(index_root: Path) -> list[Path]:
    """Delete every view the live manifest does not name, and say which went.

    Called at the **start** of a run, not at the end of the one that superseded them: a
    reader still working from the previous manifest keeps its files until then. A missing
    manifest names no view and collects nothing — treating that as "delete everything"
    would empty the index on the first run after a failed one.
    """
    try:
        manifest = read_manifest(index_root)
    except IndexVersionMismatch:
        return []
    if manifest is None:
        return []

    live = index_root / manifest.view_dir
    try:
        candidates = sorted(path for path in (index_root / VIEW_DIR).iterdir() if path.is_dir())
    except OSError:
        return []

    collected = [path for path in candidates if path != live]
    for path in collected:
        shutil.rmtree(path)
    return collected


__all__ = [
    "AUDIT_DIR",
    "SHARD_DIR",
    "TMP_SUFFIX",
    "CacheKey",
    "Shard",
    "ShardPaths",
    "ShardWriteFailed",
    "build_shard",
    "collect_views",
    "commit_view",
    "passage_from_dict",
    "passage_to_dict",
    "read_shard",
    "read_shards",
    "record_from_dict",
    "record_to_dict",
    "shard_paths",
]
