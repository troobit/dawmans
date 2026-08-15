"""`PdfLoader` — the `vendor-manual` half of the loader seam (12.4).

One store, one loader, one order of stages. Everything downstream of `LoadResult` is shared
with `data/symptom-triage`'s `TriageLoader`, which is what makes 12.2 structural rather than
a set of `if kind ==` branches, and 12.4 a consequence of there being exactly one PDF loader.

The stage order is load-bearing and is the reason this module exists as a thing separate
from the stages it calls:

- **Glyph repair before sectioning before language.** A run of `ð ñ ô õ` inside English
  prose skews a language identifier, and the APC guide has exactly that on its English
  pages, so the text is repaired first. Anchoring then needs to see the whole document
  before anything is dropped, so sectioning precedes selection.
- **Furniture marks, later stages clear.** Stage 3 can consult neither a section anchor nor
  a table region, so it only marks; stage 5 clears the mark on anchored lines and stage 7
  inside detected tables, and stage 7 drops what is still marked.

Three of the six rejection reasons are decided here — a source with no text layer (3.3), one
over the unmappable-character threshold (5.5), and one with no English content (4.5). Each
excludes that source and reports it; the run still succeeds (1.6).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pymupdf

from dawmans.corpus.discover import SourceIdentity, StoreScan, parse_filename, scan_manuals
from dawmans.corpus.loader import Discovered, LoadResult, Rejection
from dawmans.corpus.pdf.extract import Document, extract_document
from dawmans.corpus.pdf.furniture import mark_furniture
from dawmans.corpus.pdf.glyphs import document_symbol_families, embedded_names, repair_document
from dawmans.corpus.pdf.language import Detector, select_english
from dawmans.corpus.pdf.sections import derive_regions, section_map
from dawmans.corpus.pdf.units import assemble
from dawmans.records import HardwareApplicability, SourceRecord

#: What a source's `SourceRecord` carries for chunk count before it has been chunked. The
#: shard build owns the real value and rewrites the record with it; nothing between here and
#: there reads this field.
UNCHUNKED = 0


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


@dataclass(frozen=True)
class PdfLoader:
    """`manuals/` behind the `SourceLoader` protocol."""

    root: Path
    #: Injected by the language tests and by an offline run; `None` builds the lingua
    #: detector on first use, and only for a source declared `multi`.
    detector: Detector | None = None
    #: The ingestion timestamp, injectable so a test does not have to freeze the clock.
    now: Callable[[], str] = field(default=_utc_now)

    def scan(self) -> StoreScan:
        """The store's whole discovery set, including what it rejected by name (1.5, 2.5)."""
        return scan_manuals(self.root)

    def discover(self) -> Iterable[Discovered]:
        return self.scan().sources

    def load(self, d: Discovered) -> LoadResult:
        identity = parse_filename(d.origin.name)
        if identity is None:  # discovery rejects these, so reaching here is a caller error
            raise ValueError(f"{d.origin.name} does not match the filename convention (2.1)")

        document = extract_document(d.origin)
        audit: dict[str, Any] = {"pages": document.page_count, "low_text": document.low_text}
        if not document.has_text_layer:
            return self._rejected(
                identity,
                document,
                audit,
                Rejection(
                    reason="no-text-layer", detail="no extracted text outside page furniture"
                ),
            )

        audit["furniture_lines"] = mark_furniture(document)

        glyphs = repair_document(document, names=self._glyph_names(d.origin, document))
        audit["glyphs"] = glyphs.to_dict()
        if glyphs.rejection is not None:
            return self._rejected(identity, document, audit, glyphs.rejection)

        mapping = section_map(document)
        spans = derive_regions(document, mapping)
        audit["sections"] = mapping.to_dict()
        audit["anchors"] = dict(Counter(span.anchor for span in spans))

        selection = select_english(document, lang=identity.lang, detector=self.detector)
        audit["language"] = selection.to_dict()
        if selection.rejection is not None:
            return self._rejected(identity, document, audit, selection.rejection)

        regions = list(assemble(document, mapping, spans=spans))
        audit["units"] = sum(len(region.units) for region in regions)
        return LoadResult(record=self._record(identity, document), regions=regions, audit=audit)

    def _glyph_names(self, origin: Path, document: Document) -> dict[tuple[str, int], str]:
        """Path 1 of glyph repair, which needs the PDF's own font programmes.

        The families come from the span model, which is already in memory, and the file is
        reopened only where it holds a symbol font at all: walking Live 12's 1009 pages to
        discover that it does not costs 5.2 s of a 60 s rebuild.
        """
        families = document_symbol_families(document)
        if not families:
            return {}
        with pymupdf.open(origin) as doc:
            return embedded_names(doc, families)

    def _record(self, identity: SourceIdentity, document: Document) -> SourceRecord:
        return SourceRecord(
            kind="vendor-manual",
            source_id=identity.source_id,
            vendor=identity.vendor,
            product=identity.product,
            doctype=identity.doctype,
            lang=identity.lang,
            doc_version=identity.doc_version,
            display_name=identity.display_name,
            # 11.2: applicability is declared in `rig.yaml`, never inferred from content. With
            # no declaration the source is assumed to describe the product it is named for,
            # and `rig.py` replaces this where one exists.
            hardware_applicability=HardwareApplicability(
                status="assumed", device=identity.source_id
            ),
            page_count=document.page_count,
            ingested_at=self.now(),
            chunk_count=UNCHUNKED,
            low_text=document.low_text,
        )

    def _rejected(
        self,
        identity: SourceIdentity,
        document: Document,
        audit: dict[str, Any],
        rejection: Rejection,
    ) -> LoadResult:
        """A rejection excludes one source and is reported; the run still succeeds (1.6).

        The record and the audit are still produced: `index/audits/<slug>.json` is written
        whether a source committed a shard or was rejected, and the reason has to be in it.
        """
        audit["rejection"] = {"reason": rejection.reason, "detail": rejection.detail}
        return LoadResult(
            record=self._record(identity, document),
            regions=[],
            rejection=rejection,
            audit=audit,
        )


__all__ = ["UNCHUNKED", "PdfLoader"]
