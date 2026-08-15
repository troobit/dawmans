"""Records, regions and a stand-in embedder, for the index tests.

The index stages take `Chunk`s and give back files, so what they need from a fixture is a
plausible `SourceRecord` and some regions — not a PDF. The embedder is a stand-in because
the model cache is a prerequisite of *running* ingestion rather than of testing it (8.5),
and because a deterministic vector per text is what makes per-passage reuse observable:
a copied row and a re-embedded one are then equal, and the count of texts embedded is the
thing under test.
"""

from __future__ import annotations

import hashlib

import numpy as np

from dawmans.corpus.chunk import Chunk, chunk_source
from dawmans.corpus.loader import Region, Unit, UnitFlags
from dawmans.index.embed import EMBEDDING_DIM, MODEL_NAME, Embedding
from dawmans.records import AUTHORED_SOURCE_ID, HardwareApplicability, SourceRecord

PROSE = (
    "The tempo control sets the speed of the transport in beats per minute. "
    "The value is shown in the control bar at the top of the window. "
    "Tap tempo follows the rhythm you play on the key."
)


def record(source_id: str = "ableton/live-12", *, pages: int = 40, chunks: int = 0) -> SourceRecord:
    vendor, product = source_id.split("/")
    return SourceRecord(
        kind="vendor-manual",
        source_id=source_id,
        vendor=vendor,
        product=product,
        doctype="manual",
        lang="en",
        doc_version="12",
        display_name=" ".join(part.title() for part in (vendor, product)),
        hardware_applicability=HardwareApplicability(status="assumed", device=source_id),
        page_count=pages,
        ingested_at="2026-08-15T10:00:00+00:00",
        chunk_count=chunks,
        low_text=False,
    )


def authored_record(*, chunks: int = 0) -> SourceRecord:
    return SourceRecord(
        kind="authored-triage",
        source_id=AUTHORED_SOURCE_ID,
        display_name="Studio triage notes",
        hardware_applicability=HardwareApplicability(status="assumed"),
        ingested_at="2026-08-15T10:00:00+00:00",
        chunk_count=chunks,
    )


def region(*texts: str, page: int = 1, title: str = "The Control Bar") -> Region:
    return Region(
        section_number="2.1",
        section_title=title,
        section_path=("Live Concepts",),
        page_start=page,
        page_end=page,
        inferred=False,
        units=[Unit(text=text, page_start=page, page_end=page) for text in texts],
    )


def authored_region(*texts: str, entry: str = "triage/mixing.yaml:12") -> Region:
    return Region(
        section_number=None,
        section_title="No sound from track 3",
        section_path=(),
        page_start=None,
        page_end=None,
        inferred=False,
        units=[Unit(text=text, flags=UnitFlags()) for text in texts],
        entry_location=entry,
    )


def chunks_of(source: SourceRecord, *regions: Region) -> list[Chunk]:
    return chunk_source(source, list(regions))


def vendor_chunks(source: SourceRecord | None = None, *, body: str = PROSE) -> list[Chunk]:
    source = source or record()
    return chunks_of(source, region(body, page=3), region(body[:60], page=4, title="Tempo"))


def authored_chunks(*bodies: str) -> list[Chunk]:
    source = authored_record()
    return chunks_of(
        source,
        *(authored_region(body, entry=f"triage/e{i}.yaml:1") for i, body in enumerate(bodies)),
    )


def passage_ids(chunks: list[Chunk]) -> list[str]:
    return [chunk.passage.passage_id for chunk in chunks]


class StubEmbedder:
    """Deterministic vectors, and a record of every text it was asked for.

    `encoded` is the assertion surface for 8.3: a reused row costs no entry in it, so
    "re-embedded" and "copied" are distinguishable rather than inferred from timing.
    """

    def __init__(self, *, model: str = MODEL_NAME, dim: int = EMBEDDING_DIM) -> None:
        self.model_name = model
        self.dim = dim
        self.encoded: list[str] = []

    @property
    def descriptor(self) -> Embedding:
        return Embedding(model=self.model_name, dim=self.dim)

    def encode(self, texts: list[str]) -> np.ndarray:
        self.encoded.extend(texts)
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        rows = np.vstack([self._row(text) for text in texts])
        return rows.astype(np.float32)

    def _row(self, text: str) -> np.ndarray:
        digest = hashlib.sha256(f"{self.model_name}|{text}".encode()).digest()
        seed = int.from_bytes(digest[:8], "big")
        row = np.random.default_rng(seed).standard_normal(self.dim)
        return row / np.linalg.norm(row)

    def count_tokens(self, text: str) -> int:
        return len(text.split())
