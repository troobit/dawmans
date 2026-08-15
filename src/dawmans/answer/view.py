"""CorpusView: manifest, row slices, revision watch, the triage sidecar.

The merged-view contract is `data/manual-corpus` §Index layout; the load
order and the swap rules are design §What the engine reads and §Corpus
change detection. Manifest first, refusal on an `index_version` the engine
cannot interpret, and a wholesale swap on a `corpus_revision` change —
nothing partial is reused, so no answer can mix revisions.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import bm25s
import numpy as np

INDEX_VERSION = 1
MANIFEST_NAME = "manifest.json"

# CONTRACTS §1 fixes the authored source's id at this constant; its kind is
# what marks a source as publishing the triage sidecar.
AUTHORED_TRIAGE_SOURCE_ID = "authored/triage"
AUTHORED_TRIAGE_KIND = "authored-triage"


def sidecar_name(source_id: str) -> str:
    """The corpus's slug rule — `source_id` with `/` replaced by `_` — derived,
    never spelled: a spelled (or hyphenated) name that drifts from the corpus
    finds nothing, raises nothing, and under 5.13 leaves every entry in scope."""
    return source_id.replace("/", "_") + ".json"


class ViewLoadError(Exception):
    """The view cannot be interpreted; nothing partial is served."""


def _read_manifest(path: Path) -> dict[str, Any]:
    try:
        manifest = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as fault:
        raise ViewLoadError(f"manifest {path} is unreadable: {fault}") from fault
    version = manifest.get("index_version")
    if version != INDEX_VERSION:
        raise ViewLoadError(
            f"index_version {version!r} is not the {INDEX_VERSION} this engine reads; "
            f"refusing to serve — rebuild the index"
        )
    return manifest


@dataclass(frozen=True, eq=False)
class CorpusView:
    """One immutable revision of the merged view. A turn holds the object it
    started with; a swap replaces the holder's reference, never this data."""

    manifest: Mapping[str, Any]
    corpus_revision: str
    view_dir: Path
    sources: tuple[Mapping[str, Any], ...]
    sources_by_id: Mapping[str, Mapping[str, Any]]
    passages: tuple[Mapping[str, Any], ...]
    passages_by_id: Mapping[str, Mapping[str, Any]]
    vectors: np.ndarray
    lexical: bm25s.BM25
    gaps: Mapping[str, Any]
    sidecar: Mapping[str, Mapping[str, Any]]
    _row_slices: Mapping[str, slice]

    def row_slice(self, source_id: str) -> slice:
        """The source's contiguous rows, from manifest.sources — a slice, not a scan."""
        return self._row_slices[source_id]

    @classmethod
    def load(cls, index_dir: Path | str) -> CorpusView:
        index_dir = Path(index_dir)
        return cls.from_manifest(index_dir, _read_manifest(index_dir / MANIFEST_NAME))

    @classmethod
    def from_manifest(cls, index_dir: Path, manifest: Mapping[str, Any]) -> CorpusView:
        view_dir = Path(index_dir) / manifest["view_dir"]
        try:
            sources = tuple(json.loads((view_dir / "sources.json").read_text()))
            passages = tuple(
                json.loads(line)
                for line in (view_dir / "passages.jsonl").read_text().splitlines()
                if line
            )
            vectors = np.load(view_dir / "vectors.npy", mmap_mode="r")
            lexical = bm25s.BM25.load(str(view_dir / "lexical"), show_progress=False)
            gaps = json.loads((view_dir / "gaps.json").read_text())
        except (OSError, json.JSONDecodeError, KeyError, ValueError) as fault:
            raise ViewLoadError(f"view {view_dir} is unreadable: {fault}") from fault

        row_slices = {
            entry["source_id"]: slice(entry["row_start"], entry["row_start"] + entry["row_count"])
            for entry in manifest["sources"]
        }
        total = sum(entry["row_count"] for entry in manifest["sources"])
        if not (len(passages) == total == vectors.shape[0]):
            raise ViewLoadError(
                f"view {view_dir} is partial: manifest names {total} rows, "
                f"passages.jsonl holds {len(passages)}, vectors.npy holds {vectors.shape[0]}"
            )

        sidecar: dict[str, Mapping[str, Any]] = {}
        for record in sources:
            if record["kind"] != AUTHORED_TRIAGE_KIND:
                continue
            path = view_dir / "reports" / sidecar_name(record["source_id"])
            if not path.is_file():
                raise ViewLoadError(
                    f"sidecar {path} is absent for {record['source_id']}; "
                    f"refusing to serve the view with no device declarations"
                )
            try:
                published = json.loads(path.read_text())
            except (OSError, json.JSONDecodeError) as fault:
                raise ViewLoadError(f"sidecar {path} is unreadable: {fault}") from fault
            for entry in published["passages"]:
                sidecar[entry["passage_id"]] = entry

        return cls(
            manifest=manifest,
            corpus_revision=manifest["corpus_revision"],
            view_dir=view_dir,
            sources=sources,
            sources_by_id={record["source_id"]: record for record in sources},
            passages=passages,
            passages_by_id={passage["passage_id"]: passage for passage in passages},
            vectors=vectors,
            lexical=lexical,
            gaps=gaps,
            sidecar=sidecar,
            _row_slices=row_slices,
        )


class ViewWatcher:
    """The stat-based revision watch of design §Corpus change detection.

    `check()` runs before each turn's timer starts, so the ~200 ms reload is
    never charged to a turn: `corpus_reload_ms` is run-level. An in-flight
    turn keeps the `CorpusView` it holds — the swap replaces `self.view`.
    """

    def __init__(self, index_dir: Path | str) -> None:
        self._index_dir = Path(index_dir)
        self._manifest_path = self._index_dir / MANIFEST_NAME
        self.view: CorpusView | None = None
        # Recorded for GET /sources: a new manifest the engine cannot read
        # keeps the live view in place — never corpus-empty, which would be
        # a lie — and this is where the mismatch is reported from.
        self.manifest_fault: str | None = None
        self.corpus_reload_ms: float | None = None
        self._stat: tuple[int, int] | None = None

        stat = self._stat_manifest()
        if stat is not None:
            # Startup refusal propagates: a listener over a view the engine
            # cannot interpret must not accept.
            self.view = CorpusView.load(self._index_dir)
            self._stat = stat

    def _stat_manifest(self) -> tuple[int, int] | None:
        try:
            stat = os.stat(self._manifest_path)
        except FileNotFoundError:
            return None
        return (stat.st_mtime_ns, stat.st_size)

    def check(self) -> None:
        """Swap the view if the corpus changed; ~50 µs when it did not."""
        stat = self._stat_manifest()
        if stat is None:
            # No manifest is the corpus honestly holding nothing — the
            # pre-flight corpus-empty gate, not a fault.
            self.view = None
            self._stat = None
            self.manifest_fault = None
            return
        if stat == self._stat:
            return

        try:
            manifest = _read_manifest(self._manifest_path)
        except ViewLoadError as fault:
            self.manifest_fault = str(fault)
            self._stat = stat
            return

        if self.view is not None and manifest.get("corpus_revision") == self.view.corpus_revision:
            self._stat = stat
            self.manifest_fault = None
            return

        started = time.perf_counter()
        try:
            view = CorpusView.from_manifest(self._index_dir, manifest)
        except ViewLoadError as fault:
            # The new view is not interpretable; the live one keeps serving.
            self.manifest_fault = str(fault)
            self._stat = stat
            return
        self.view = view
        self.corpus_reload_ms = (time.perf_counter() - started) * 1000.0
        self._stat = stat
        self.manifest_fault = None
