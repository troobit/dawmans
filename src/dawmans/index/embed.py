"""The fastembed wrapper, pinned offline against the models/ cache.

`fastembed` is the only network-capable dependency in the package, and requirement 8.5
says ingestion performs no network access at all. Two mechanisms hold that together
(design §Offline operation):

- `HF_HUB_OFFLINE=1` is set in the ingestion **process's own environment**, so no code
  path inside the library can reach the network, including one this package never calls.
- The cache is checked before the model is asked for, so an absent one fails immediately
  naming the model, the directory and `make fetch-model` rather than timing out.

Populating the cache is a **prerequisite of running ingestion, not a build step**: it is
deliberately outside the ingestion path, run once per machine. A missing cache is
therefore a *failure* and not a rejection — no source is at fault and nothing at all can
be embedded, so 1.6's closed rejection list has no member for it.

The model is loaded **once per run**, before iterating sources. The cold load measures
~7.2 s and 8.4 allows 10 s for a whole new source, so a load paid per source leaves
nothing for the source itself; `Embedder` is passed to the shard build rather than
constructed by it.
"""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import numpy as np

#: Decision 2's model. Its identity is a component of the shard cache key: changing it
#: must re-embed every shard rather than concatenating vectors from two models under a
#: manifest declaring one.
MODEL_NAME = "BAAI/bge-small-en-v1.5"

#: The model's output width, and the second key component. `vectors.npy` is (N, 384).
EMBEDDING_DIM = 384

#: The gitignored cache at the repository root, as `.gitignore` and `tools/fetch_model.py`
#: both name it. `parents[3]` is `src/dawmans/index/embed.py` → the root.
CACHE_DIR = Path(__file__).resolve().parents[3] / "models"

#: The one command that populates it. Named in the failure, because the error is read on
#: a machine that has to act on it.
FETCH_COMMAND = "make fetch-model"

#: What marks a cache as populated. It is also what the tokeniser is loaded from, so a
#: cache passing the check is one both halves of this wrapper can use.
_CACHE_MARKER = "tokenizer.json"


class ModelCacheMissing(RuntimeError):
    """The embedding model is not in the cache and cannot be fetched (8.5).

    A failure, not a rejection: no source is at fault and nothing can be embedded, so the
    run exits non-zero rather than excluding one source and reporting success.
    """


class Backend(Protocol):
    """What this module needs of `fastembed.TextEmbedding` — and no more, so the wrapper
    can be tested without a 67 MB download."""

    def embed(self, texts: list[str], **kwargs: Any) -> Any: ...


@dataclass(frozen=True)
class Embedding:
    """The manifest's `embedding` block, and three of the four shard cache-key components.

    `normalised` is declared rather than assumed: a reader comparing cosine similarity as
    a plain dot product depends on it.
    """

    model: str
    dim: int
    normalised: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {"model": self.model, "dim": self.dim, "normalised": self.normalised}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> Embedding | None:
        """The block a shard meta recorded, or None where it recorded none.

        None is not an error and not a default: a shard written before the block existed
        cannot be shown to match the current model, so it is re-embedded.
        """
        if not data:
            return None
        try:
            return cls(
                model=str(data["model"]),
                dim=int(data["dim"]),
                normalised=bool(data.get("normalised", True)),
            )
        except (KeyError, TypeError, ValueError):
            return None


def pin_offline() -> None:
    """Set `HF_HUB_OFFLINE=1` in this process's environment (8.5).

    Called before the cache check, not after: pinning afterwards would leave a run that
    recovered from the failure able to reach the network on its next attempt.
    """
    os.environ["HF_HUB_OFFLINE"] = "1"


def cache_is_populated(cache_dir: Path = CACHE_DIR) -> bool:
    """Whether `make fetch-model` has been run against this directory."""
    return tokeniser_path(cache_dir) is not None


def tokeniser_path(cache_dir: Path = CACHE_DIR) -> Path | None:
    """The cached vocabulary, or None. The snapshot directory carries a content hash, so
    the file is found rather than spelled."""
    try:
        return next(iter(sorted(cache_dir.rglob(_CACHE_MARKER))), None)
    except OSError:
        return None


class Embedder:
    """One loaded model, for a whole run.

    The wrapper owns the output contract — float32, `EMBEDDING_DIM` wide, L2-normalised —
    rather than trusting the backend to keep it. A backend returning a different width
    must not reach the view under a manifest declaring 384: the vectors would be
    incomparable and nothing about the on-disk shape would say so.
    """

    def __init__(
        self,
        backend: Backend,
        *,
        model_name: str = MODEL_NAME,
        dim: int = EMBEDDING_DIM,
        cache_dir: Path = CACHE_DIR,
    ) -> None:
        self.backend = backend
        self.model_name = model_name
        self.dim = dim
        self.cache_dir = cache_dir
        self._tokeniser: Any | None = None

    @property
    def descriptor(self) -> Embedding:
        """What the manifest and every shard meta record about this model."""
        return Embedding(model=self.model_name, dim=self.dim)

    def encode(self, texts: Sequence[str]) -> np.ndarray:
        """`(len(texts), dim)` float32, L2-normalised, in the order given.

        Order is the view's contract: row `i` of `vectors.npy` is line `i` of
        `passages.jsonl`. An empty input yields `(0, dim)` rather than `(0,)`, so a source
        that contributed no passages still concatenates into the merge.
        """
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)

        rows = np.asarray(list(self.backend.embed(list(texts))), dtype=np.float32)
        if rows.shape != (len(texts), self.dim):
            raise ValueError(
                f"{self.model_name} returned {rows.shape}, not "
                f"({len(texts)}, {self.dim}) — the manifest declares {self.dim}"
            )

        norms = np.linalg.norm(rows, axis=1, keepdims=True)
        return np.divide(rows, np.where(norms == 0.0, 1.0, norms)).astype(np.float32)

    def count_tokens(self, text: str) -> int:
        """The model's own tokeniser, for `chunk.token_budget`.

        Loaded lazily and from the cache directly rather than through `fastembed`, whose
        tokeniser is not part of its published surface. Measuring costs nothing here and
        turns a silent truncation at the 512-token window into a run-report line.
        """
        if self._tokeniser is None:
            from tokenizers import Tokenizer

            path = tokeniser_path(self.cache_dir)
            if path is None:
                raise ModelCacheMissing(_missing_message(self.cache_dir))
            self._tokeniser = Tokenizer.from_file(str(path))
        return len(self._tokeniser.encode(text).ids)


def load_embedder(cache_dir: Path = CACHE_DIR) -> Embedder:
    """Load the model once, for the whole run (8.4, 8.5).

    Pin the process offline, then check the cache, then load. The order is the point: with
    the pin set first, a cache that exists but is incomplete fails inside the library
    rather than fetching what it is short of.
    """
    pin_offline()
    if not cache_is_populated(cache_dir):
        raise ModelCacheMissing(_missing_message(cache_dir))

    from fastembed import TextEmbedding

    backend = TextEmbedding(model_name=MODEL_NAME, cache_dir=str(cache_dir))
    return Embedder(backend, cache_dir=cache_dir)


def _missing_message(cache_dir: Path) -> str:
    return (
        f"{MODEL_NAME} is not in the model cache at {cache_dir}. Ingestion runs offline "
        f"(requirement 8.5) and will not fetch it: run `{FETCH_COMMAND}` once on this "
        f"machine, then ingest again."
    )


__all__ = [
    "CACHE_DIR",
    "EMBEDDING_DIM",
    "FETCH_COMMAND",
    "MODEL_NAME",
    "Backend",
    "Embedder",
    "Embedding",
    "ModelCacheMissing",
    "cache_is_populated",
    "load_embedder",
    "pin_offline",
    "tokeniser_path",
]
