"""manifest.json: index_version, corpus_revision, the per-source row slices.

`manifest.json` is the index's only switch. It exists **only when every artefact it names
is complete**, it is renamed into place last, and a reader therefore sees either the old
manifest with the old view or the new manifest with the new view — never a mix
(design §Commit ordering).

Two of its fields make the artefacts self-describing (8.11). `index_version` is an integer
bumped whenever the on-disk shape changes, and a reader expecting a different one MUST
refuse to load rather than interpret the files. `corpus_revision` is a hash over the
sorted `(source_id, fingerprint, chunk_count)` triples, so `api/answer-engine` can detect
a corpus change with one cheap read rather than by diffing the corpus (its 5.10).

**`sources` is sorted by `source_id`, and the sorting is load-bearing.** If the order came
from filesystem iteration, `row_start` offsets could differ between two runs over an
identical source set while `corpus_revision` — hashed over *sorted* triples — stayed the
same, so a consumer keyed on the revision would keep stale offsets and slice the wrong
rows.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dawmans.index.embed import Embedding

#: Bumped whenever the on-disk shape changes. The fix for a mismatch is a rebuild.
INDEX_VERSION = 1

MANIFEST_NAME = "manifest.json"
VIEW_DIR = "views"


class IndexVersionMismatch(RuntimeError):
    """The artefacts were written by a different on-disk shape (8.11).

    Raised rather than tolerated: a reader that interpreted them anyway would misread
    them, which is exactly what a self-describing artefact exists to prevent.
    """


@dataclass(frozen=True)
class SourceSlice:
    """One source's rows in the merged view.

    `row_start` and `row_count` are what make restricting matching to a chosen subset of
    sources a slice rather than a scan (8.10).
    """

    source_id: str
    kind: str
    fingerprint: str
    chunk_count: int
    row_start: int
    row_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "kind": self.kind,
            "fingerprint": self.fingerprint,
            "chunk_count": self.chunk_count,
            "row_start": self.row_start,
            "row_count": self.row_count,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> SourceSlice:
        return cls(
            source_id=str(data["source_id"]),
            kind=str(data["kind"]),
            fingerprint=str(data["fingerprint"]),
            chunk_count=int(data["chunk_count"]),
            row_start=int(data["row_start"]),
            row_count=int(data["row_count"]),
        )


@dataclass(frozen=True)
class Manifest:
    """What one committed view is, and how to read it."""

    view_dir: str
    corpus_revision: str
    built_at: str
    ingestion_version: int
    embedding: Embedding
    sources: tuple[SourceSlice, ...]
    index_version: int = INDEX_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "index_version": self.index_version,
            "view_dir": self.view_dir,
            "corpus_revision": self.corpus_revision,
            "built_at": self.built_at,
            "ingestion_version": self.ingestion_version,
            "embedding": self.embedding.to_dict(),
            "sources": [source.to_dict() for source in self.sources],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Manifest:
        version = int(data["index_version"])
        if version != INDEX_VERSION:
            raise IndexVersionMismatch(
                f"index_version {version} was written by a different on-disk shape; this "
                f"reader expects {INDEX_VERSION}. Delete index/ and rebuild."
            )
        embedding = Embedding.from_dict(data["embedding"])
        if embedding is None:
            raise IndexVersionMismatch("the manifest declares no embedding model")
        return cls(
            index_version=version,
            view_dir=str(data["view_dir"]),
            corpus_revision=str(data["corpus_revision"]),
            built_at=str(data["built_at"]),
            ingestion_version=int(data["ingestion_version"]),
            embedding=embedding,
            sources=tuple(SourceSlice.from_dict(source) for source in data["sources"]),
        )


def corpus_revision(triples: Sequence[tuple[str, str, int]]) -> str:
    """`sha256` over the **sorted** `(source_id, fingerprint, chunk_count)` triples.

    Sorted, so the revision is a property of the corpus and not of the order the shards
    happened to be read in. It changes when and only when the indexed content changes,
    which is what lets a consumer discard cached retrieval state on one cheap read.
    """
    canonical = json.dumps(sorted(triples), separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def view_name(revision: str, built_at: str, attempt: int = 0) -> str:
    """The directory a run's view is built into.

    The revision alone would name the same directory for two runs over identical content,
    and a view is never modified after it is complete — so `built_at` is folded in, and
    `attempt` exists for the one case that leaves: a run that died before renaming its
    manifest, whose abandoned directory must not be built over.
    """
    seed = f"{revision}|{built_at}|{attempt}"
    return hashlib.sha256(seed.encode()).hexdigest()[:16]


def manifest_path(index_root: Path) -> Path:
    return index_root / MANIFEST_NAME


def read_manifest(index_root: Path) -> Manifest | None:
    """The live manifest, or None where no run has committed one.

    A manifest written by a different `index_version` raises rather than returning None:
    absent and unreadable are different answers, and only one of them is a rebuild.
    """
    path = manifest_path(index_root)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return Manifest.from_dict(data)


def write_manifest(index_root: Path, manifest: Manifest) -> None:
    """Rename `manifest.json` into place — the last thing a run does.

    Everything the manifest names is already complete when this is called, so the rename
    is the only switch a reader can observe.
    """
    index_root.mkdir(parents=True, exist_ok=True)
    path = manifest_path(index_root)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(manifest.to_dict(), ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)


__all__ = [
    "INDEX_VERSION",
    "MANIFEST_NAME",
    "VIEW_DIR",
    "IndexVersionMismatch",
    "Manifest",
    "SourceSlice",
    "corpus_revision",
    "manifest_path",
    "read_manifest",
    "view_name",
    "write_manifest",
]
