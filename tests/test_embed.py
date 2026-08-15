"""The embedding wrapper and the offline pin — requirement 8.5, design §Offline operation.

`fastembed` is the only network-capable dependency in the package: on first use it fetches
`bge-small-en-v1.5` from Hugging Face. Ingestion must never do that, so two mechanisms run
together and both are asserted here. `HF_HUB_OFFLINE=1` is set in the ingestion process's
own environment, so the library cannot reach the network even when the cache is incomplete;
and the cache is checked before the model is asked for, so an absent one fails immediately
with the one command that populates it rather than by timing out on a socket.

**A missing cache is a failure, not a rejection.** No source is at fault and nothing can be
embedded, so 1.6's closed rejection list has no member for it and the run cannot report
itself as succeeded.

The other thing this module owns is the shape of what it returns. `vectors.npy` is
float32 `(N, 384)`, L2-normalised, and the manifest declares that; a backend returning
anything else would be concatenated into the view under a manifest that lies about it,
which is the silent failure the four-part shard cache key exists to prevent.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import numpy as np
import pytest

from dawmans.corpus.loader import REJECTION_REASONS
from dawmans.index.embed import (
    CACHE_DIR,
    EMBEDDING_DIM,
    FETCH_COMMAND,
    MODEL_NAME,
    Embedder,
    Embedding,
    ModelCacheMissing,
    cache_is_populated,
    load_embedder,
    pin_offline,
)

REPO_ROOT = Path(__file__).resolve().parent.parent

TEXTS = ["the tempo control sets the speed of the transport", "MIDI note 38 is the snare"]


class FakeBackend:
    """Stands in for `fastembed.TextEmbedding`, counting how often it is constructed.

    The count is the point: the cold load measures ~7.2 s, and 8.4 allows 10 s for a whole
    new source, so a load paid per source leaves nothing for the source itself.
    """

    loads = 0

    def __init__(self, model_name: str, cache_dir: str, **kwargs: object) -> None:
        type(self).loads += 1
        self.model_name = model_name
        self.cache_dir = cache_dir
        self.rows: list[list[str]] = []

    def embed(self, texts: list[str], **kwargs: object):  # noqa: ANN201 - a generator, as fastembed's is
        self.rows.append(list(texts))
        # Deliberately unnormalised and float64: the wrapper owns both, not the backend.
        for index, _ in enumerate(texts):
            row = np.zeros(EMBEDDING_DIM, dtype=np.float64)
            row[index % EMBEDDING_DIM] = 3.0
            row[(index + 1) % EMBEDDING_DIM] = 4.0
            yield row


def populated_cache(root: Path) -> Path:
    """A cache directory with the marker `load_embedder` looks for.

    `tokenizer.json` is the marker because it is what the tokeniser is loaded from as well,
    so a cache that satisfies the check is one both halves of the wrapper can use.
    """
    snapshot = root / "models--BAAI--bge-small-en-v1.5" / "snapshots" / "abc123"
    snapshot.mkdir(parents=True)
    (snapshot / "tokenizer.json").write_text("{}")
    return root


@pytest.fixture(autouse=True)
def _reset(monkeypatch: pytest.MonkeyPatch) -> None:
    """Neither the offline pin nor the load count may leak between tests."""
    monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)
    FakeBackend.loads = 0


def fake_fastembed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "fastembed", types.SimpleNamespace(TextEmbedding=FakeBackend))


# --- The offline pin and the cache prerequisite (8.5) -------------------------------------


def test_the_cache_is_the_gitignored_models_directory_at_the_repository_root() -> None:
    """The same directory `make fetch-model` populates and `.gitignore` excludes. If these
    two ever name different places, ingestion fails on a machine that has already fetched."""
    assert CACHE_DIR == REPO_ROOT / "models"


def test_the_offline_pin_is_set_in_the_process_environment() -> None:
    """Not a keyword argument to the library: the design pins the *process* so that no code
    path inside `fastembed` or `huggingface_hub` can reach the network, including one this
    package never calls."""
    pin_offline()

    import os

    assert os.environ["HF_HUB_OFFLINE"] == "1"


def test_an_absent_cache_fails_naming_the_model_the_directory_and_the_command(
    tmp_path: Path,
) -> None:
    """The error has to be actionable on the machine that hit it, which means all three:
    what is missing, where it was looked for, and the one command that puts it there."""
    with pytest.raises(ModelCacheMissing) as raised:
        load_embedder(cache_dir=tmp_path / "absent")

    message = str(raised.value)
    assert MODEL_NAME in message
    assert str(tmp_path / "absent") in message
    assert FETCH_COMMAND in message


def test_the_pin_is_set_even_when_the_cache_check_then_fails(tmp_path: Path) -> None:
    """Ordering: pin first, check second. Pinning after the check would leave a run that
    recovered from the failure able to reach the network on its next attempt."""
    with pytest.raises(ModelCacheMissing):
        load_embedder(cache_dir=tmp_path / "absent")

    import os

    assert os.environ["HF_HUB_OFFLINE"] == "1"


def test_a_missing_cache_has_no_rejection_reason(tmp_path: Path) -> None:
    """1.6's rejection set is closed, and a missing model is not in it: no source is at
    fault and *nothing* can be embedded, so the run fails rather than excluding one source
    and reporting success (1.7)."""
    assert not any("model" in reason or "cache" in reason for reason in REJECTION_REASONS)
    assert not issubclass(ModelCacheMissing, Warning)
    assert not cache_is_populated(tmp_path / "absent")


# --- The model is loaded once per run, not once per source (8.4) --------------------------


def test_the_model_is_loaded_once_and_encoding_never_reloads_it(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The load is what makes 8.4 tight: 7.2 s of a 10 s budget before a page is read. The
    CLI loads once before iterating sources, and this is the half of that the wrapper can
    hold — `encode` touches the loader not at all, however many sources call it."""
    fake_fastembed(monkeypatch)
    embedder = load_embedder(cache_dir=populated_cache(tmp_path))

    for _ in range(3):  # three sources in one run
        embedder.encode(TEXTS)

    assert FakeBackend.loads == 1


def test_the_backend_is_pointed_at_the_cache_and_the_pinned_model(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake_fastembed(monkeypatch)
    cache = populated_cache(tmp_path)

    embedder = load_embedder(cache_dir=cache)

    assert embedder.backend.model_name == MODEL_NAME  # type: ignore[attr-defined]
    assert embedder.backend.cache_dir == str(cache)  # type: ignore[attr-defined]


# --- The shape of what is written to vectors.npy ------------------------------------------


def test_encoding_is_float32_384_dimensional_and_l2_normalised() -> None:
    """What the manifest's `embedding` block declares, asserted against what is returned.
    The backend here yields float64 rows of norm 5, so all three properties are the
    wrapper's doing rather than the model's."""
    matrix = Embedder(FakeBackend(MODEL_NAME, "cache")).encode(TEXTS)

    assert matrix.dtype == np.float32
    assert matrix.shape == (len(TEXTS), EMBEDDING_DIM)
    assert np.allclose(np.linalg.norm(matrix, axis=1), 1.0, atol=1e-6)


def test_encoding_nothing_yields_an_empty_matrix_of_the_right_width() -> None:
    """A source that was rejected, or one whose regions held no text, still has to
    concatenate into `vectors.npy`: an empty `(0,)` array cannot be stacked with `(n, 384)`
    and would fail the merge rather than contributing nothing."""
    matrix = Embedder(FakeBackend(MODEL_NAME, "cache")).encode([])

    assert matrix.shape == (0, EMBEDDING_DIM)
    assert matrix.dtype == np.float32


def test_rows_keep_the_order_of_the_texts_they_encode() -> None:
    """Row `i` of `vectors.npy` is line `i` of `passages.jsonl`, and that correspondence
    starts here. A backend batching out of order would break the view's whole contract."""
    embedder = Embedder(FakeBackend(MODEL_NAME, "cache"))

    together = embedder.encode(TEXTS)
    separately = np.vstack([embedder.encode([text]) for text in TEXTS])

    assert np.allclose(together[0], separately[0])
    assert not np.allclose(together[0], together[1])


def test_a_backend_row_of_the_wrong_width_is_a_failure() -> None:
    """The dimension is declared in the manifest and is a component of the shard cache key.
    A backend returning something else must not reach the view under a manifest saying 384:
    the vectors would be incomparable and nothing about the on-disk shape would say so."""

    class WrongWidth(FakeBackend):
        def embed(self, texts: list[str], **kwargs: object):  # noqa: ANN201
            for _ in texts:
                yield np.ones(128, dtype=np.float32)

    with pytest.raises(ValueError, match="384"):
        Embedder(WrongWidth(MODEL_NAME, "cache")).encode(TEXTS)


def test_the_descriptor_is_the_manifest_embedding_block() -> None:
    """Three of the four shard cache-key components come from here; the fourth is the
    source fingerprint. `normalised` is declared because a reader comparing cosine
    similarity as a dot product depends on it."""
    embedder = Embedder(FakeBackend(MODEL_NAME, "cache"))

    assert embedder.descriptor == Embedding(model=MODEL_NAME, dim=EMBEDDING_DIM)
    assert embedder.descriptor.to_dict() == {
        "model": MODEL_NAME,
        "dim": EMBEDDING_DIM,
        "normalised": True,
    }


def test_a_descriptor_round_trips_through_its_dictionary_form() -> None:
    """Shard metas are read back to decide reuse, so the comparison is between a stored
    dictionary and a live descriptor."""
    stored = Embedding(model=MODEL_NAME, dim=EMBEDDING_DIM).to_dict()

    assert Embedding.from_dict(stored) == Embedding(model=MODEL_NAME, dim=EMBEDDING_DIM)
    assert Embedding.from_dict({}) is None  # a shard predating the key is not reusable


# --- Against the real model, where the machine has fetched it -----------------------------


@pytest.mark.skipif(
    not cache_is_populated(CACHE_DIR),
    reason="the embedding model lives in the models/ cache; populate it with `make fetch-model`",
)
def test_the_real_model_loads_offline_and_returns_the_declared_shape() -> None:
    """The end of 8.5: with the cache present and the process pinned offline, loading and
    encoding both succeed. The model cache is a prerequisite of running ingestion rather
    than a build step, so this is skipped where it is absent."""
    embedder = load_embedder()

    matrix = embedder.encode(TEXTS)

    assert matrix.shape == (len(TEXTS), EMBEDDING_DIM)
    assert matrix.dtype == np.float32
    assert np.allclose(np.linalg.norm(matrix, axis=1), 1.0, atol=1e-5)
    assert embedder.count_tokens("the tempo control") > 0
