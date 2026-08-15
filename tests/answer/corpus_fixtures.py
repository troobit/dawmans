"""In-memory CorpusView builders for the retrieval-stage tests.

`test_corpus_view.py` exercises the disk contract; everything downstream of
load operates on the loaded view alone (design §Retrieval), so these tests
build a `CorpusView` directly and skip the file round-trip.

Vectors default to one-hot rows: with unit rows, `vectors @ q` reads the
query's component for each row, so a test states every cosine directly in
the query vector it passes to retrieval.
"""

from pathlib import Path

import bm25s
import numpy as np

from dawmans.answer.view import CorpusView


def vendor_source(source_id, device, *, page_count=100, status="confirmed"):
    vendor, _, product = source_id.partition("/")
    return {
        "source_id": source_id,
        "kind": "vendor-manual",
        "vendor": vendor,
        "product": product,
        "doctype": "manual",
        "lang": "en",
        "doc_version": "1.0",
        "display_name": source_id,
        "hardware_applicability": {"device": device, "status": status},
        "page_count": page_count,
        "ingested_at": "2026-08-14T10:00:00Z",
    }


def triage_source(source_id="authored/triage"):
    # CONTRACTS §1: source-level applicability fixed at `assumed`, no device —
    # entry applicability is passage-level data in the sidecar.
    return {
        "source_id": source_id,
        "kind": "authored-triage",
        "display_name": "Symptom triage entries",
        "hardware_applicability": {"status": "assumed"},
        "ingested_at": "2026-08-14T10:00:00Z",
    }


def passage(passage_id, text, **fields):
    source_id = passage_id.rsplit("#", 1)[0]
    return {"passage_id": passage_id, "source_id": source_id, "text": text, **fields}


def sidecar_entry(passage_id, devices, **fields):
    return {
        "passage_id": passage_id,
        "entry_key": passage_id.rsplit("#", 1)[1],
        "symptom": fields.pop("symptom", "a symptom"),
        "devices": [{"id": device, "revision": None} for device in devices],
        "source_file": "triage/entry.md",
        "line": 1,
        "causes": fields.pop("causes", []),
        **fields,
    }


EMPTY_GAPS = {"owned_but_undocumented": [], "documented_but_unconfirmed": []}


def make_view(sources, passages, *, gaps=EMPTY_GAPS, sidecar=(), vectors=None):
    """Build one immutable CorpusView from in-memory records.

    `passages` must arrive grouped by source in row order, as the merged
    view commits them; row slices are derived from that grouping.
    """
    row_slices = {}
    for row, record in enumerate(passages):
        source_id = record["source_id"]
        held = row_slices.get(source_id)
        if held is None:
            row_slices[source_id] = slice(row, row + 1)
        else:
            assert held.stop == row, f"passages for {source_id} are not contiguous"
            row_slices[source_id] = slice(held.start, row + 1)

    if vectors is None:
        vectors = np.eye(len(passages), dtype=np.float32)
    vectors = np.asarray(vectors, dtype=np.float32)
    assert vectors.shape[0] == len(passages)

    tokens = bm25s.tokenize(
        [record["text"] for record in passages], stopwords=None, show_progress=False
    )
    lexical = bm25s.BM25()
    lexical.index(tokens, show_progress=False)

    sources = tuple(dict(record, chunk_count=0) for record in sources)
    manifest = {
        "index_version": 1,
        "view_dir": "views/test",
        "corpus_revision": "rev-test",
        "sources": [
            {
                "source_id": source_id,
                "row_start": rows.start,
                "row_count": rows.stop - rows.start,
            }
            for source_id, rows in row_slices.items()
        ],
    }
    return CorpusView(
        manifest=manifest,
        corpus_revision="rev-test",
        view_dir=Path("."),
        sources=sources,
        sources_by_id={record["source_id"]: record for record in sources},
        passages=tuple(passages),
        passages_by_id={record["passage_id"]: record for record in passages},
        vectors=vectors,
        lexical=lexical,
        gaps=gaps,
        sidecar={entry["passage_id"]: entry for entry in sidecar},
        _row_slices=row_slices,
    )
