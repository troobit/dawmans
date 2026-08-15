"""The vendor-manual load path — requirement 12.4 and the stage order.

`PdfLoader` is the only loader that opens a PDF, and everything downstream of the
`LoadResult` it returns is shared with `data/symptom-triage`'s loader. That is what makes
12.2 structural rather than a set of `if kind ==` branches: these tests assert the seam's
shape and the ordering the design calls load-bearing, not the stages themselves — each of
those has its own module and its own tests.

`manuals/` is gitignored and no test may open a reference PDF, so the PDFs here are written
by `tests/pdfgen.py`.
"""

from __future__ import annotations

from pathlib import Path

from dawmans.corpus.discover import fingerprint
from dawmans.corpus.loader import Discovered, SourceLoader
from dawmans.corpus.pdf.loader import UNCHUNKED, PdfLoader
from pdfgen import Image, Page, Text, lines, write_pdf

PROSE = (
    "The tempo control sets the speed of the transport in beats per minute, and the value "
    "is shown in the control bar at the top of the window."
)

SPANISH = (
    "El control de tempo ajusta la velocidad del transporte en pulsaciones por minuto, y "
    "el valor se muestra en la barra de control en la parte superior de la ventana."
)


def store(
    tmp_path: Path, pages: list[Page], name: str = "alesis_nitro-max_guide_v1_en.pdf"
) -> Path:
    root = tmp_path / "manuals"
    root.mkdir(exist_ok=True)
    write_pdf(root / name, pages)
    return root


def only(loader: PdfLoader) -> Discovered:
    (found,) = loader.discover()
    return found


def test_the_loader_satisfies_the_source_loader_protocol() -> None:
    """12.2: the seam is a protocol, and `TriageLoader` implements the same one. The
    annotation is the check a type checker makes; these are the two calls the run makes."""
    loader: SourceLoader = PdfLoader(root=Path("manuals"))

    assert callable(loader.discover)
    assert callable(loader.load)


def test_a_source_loads_into_regions_of_units(tmp_path: Path) -> None:
    """3.5: one text line per source line, so a paragraph reaches the chunker as it was
    printed rather than as one reflowed string."""
    root = store(tmp_path, [Page(texts=lines("Setting Up", "The tempo control sets the speed."))])
    loader = PdfLoader(root=root)

    result = loader.load(only(loader))

    assert result.rejection is None
    assert [unit.text for region in result.regions for unit in region.units] == [
        "Setting Up\nThe tempo control sets the speed."
    ]


def test_the_record_comes_from_the_filename_and_the_document(tmp_path: Path) -> None:
    """2.4: every `SourceRecord` field but the page count is read off the name, and the
    version is not folded into the display name — CONTRACTS §3 renders it separately."""
    root = store(tmp_path, [Page(texts=lines(PROSE)), Page(texts=lines(PROSE))])
    loader = PdfLoader(root=root, now=lambda: "2026-08-15T00:00:00+00:00")

    record = loader.load(only(loader)).record

    assert record.kind == "vendor-manual"
    assert record.source_id == "alesis/nitro-max"
    assert record.display_name == "Alesis Nitro Max"
    assert record.doc_version == "1"
    assert record.page_count == 2
    assert record.ingested_at == "2026-08-15T00:00:00+00:00"
    assert record.chunk_count == UNCHUNKED


def test_applicability_is_assumed_and_never_inferred_from_content(tmp_path: Path) -> None:
    """11.2: the rig declares which hardware a source describes. With no declaration the
    source is assumed to describe the product it is named for, and `rig.yaml` overrides it."""
    root = store(tmp_path, [Page(texts=lines(PROSE))])
    loader = PdfLoader(root=root)

    applicability = loader.load(only(loader)).record.hardware_applicability

    assert applicability.status == "assumed"
    assert applicability.device == "alesis/nitro-max"


def test_a_page_number_is_dropped_and_the_prose_is_not(tmp_path: Path) -> None:
    """The whole mark-then-clear chain, end to end: stage 3 marks the repeated numeral,
    nothing claims it back, and stage 7 drops it."""
    root = store(
        tmp_path,
        [
            Page(texts=(*lines(PROSE), Text(text="1", x=300.0, y=760.0))),
            Page(texts=(*lines(PROSE), Text(text="2", x=300.0, y=760.0))),
        ],
    )
    loader = PdfLoader(root=root)

    result = loader.load(only(loader))

    texts = [unit.text for region in result.regions for unit in region.units]
    assert texts and "1" not in texts and "2" not in texts


def test_a_source_with_no_text_layer_is_rejected(tmp_path: Path) -> None:
    """3.3: rejected and reported, not indexed as empty."""
    root = store(tmp_path, [Page(images=(Image(x=50.0, y=50.0, width=400.0, height=400.0),))])
    loader = PdfLoader(root=root)

    result = loader.load(only(loader))

    assert result.rejection is not None
    assert result.rejection.reason == "no-text-layer"
    assert result.regions == []
    assert result.record.source_id == "alesis/nitro-max"
    assert result.audit["rejection"]["reason"] == "no-text-layer"


def test_a_source_with_no_english_content_is_rejected(tmp_path: Path) -> None:
    """4.5. Detection runs only because the filename declares `multi` (4.2)."""
    root = store(
        tmp_path,
        [Page(texts=lines(SPANISH, SPANISH))],
        name="alesis_nitro-max_guide_v1_multi.pdf",
    )
    loader = PdfLoader(root=root, detector=lambda text: ("es", 0.99))

    result = loader.load(only(loader))

    assert result.rejection is not None
    assert result.rejection.reason == "no-english-content"
    assert result.regions == []


def test_a_declared_language_skips_detection_entirely(tmp_path: Path) -> None:
    """4.1: anything but `multi` is that language by declaration, so a detector that would
    reject every block is never consulted."""

    def never(text: str) -> tuple[str, float]:
        raise AssertionError("the detector is not called for a declared language")

    root = store(tmp_path, [Page(texts=lines(PROSE))])
    loader = PdfLoader(root=root, detector=never)

    assert loader.load(only(loader)).rejection is None


def test_the_audit_carries_what_each_stage_learned(tmp_path: Path) -> None:
    """The per-source ingestion audit of design §Stages: it is written whether the source
    committed a shard or was rejected, so every stage's diagnostics belong in it."""
    root = store(tmp_path, [Page(texts=lines("Setting Up", PROSE))])
    loader = PdfLoader(root=root)

    audit = loader.load(only(loader)).audit

    assert set(audit) >= {
        "pages",
        "low_text",
        "furniture_lines",
        "glyphs",
        "sections",
        "anchors",
        "language",
        "units",
    }
    assert audit["language"]["english_pages"] == [[1, 1]]


def test_discovery_reports_the_store_and_its_fingerprints(tmp_path: Path) -> None:
    """9.2: a source is identified by the sha256 of its bytes, and the loader hands the
    same `Discovered` back that change detection compares against the shard meta."""
    root = store(tmp_path, [Page(texts=lines(PROSE))])
    loader = PdfLoader(root=root)

    found = only(loader)

    assert found.source_id == "alesis/nitro-max"
    assert found.fingerprint == fingerprint(root / "alesis_nitro-max_guide_v1_en.pdf")
    assert loader.scan().available


def test_a_missing_store_is_not_an_empty_store(tmp_path: Path) -> None:
    """1.4 through the seam: an unmounted `manuals/` yields no sources and reports itself
    unavailable, and the caller is what must not delete a shard on the strength of it."""
    loader = PdfLoader(root=tmp_path / "absent")

    assert list(loader.discover()) == []
    assert not loader.scan().available
