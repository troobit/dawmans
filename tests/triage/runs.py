"""Test support: a real ingestion run over the committed section fixtures.

`manuals/` is stood in for by `StubManuals`, which rebuilds one region per fixture
section, so the passages a run commits are chunked from real vendor prose with no PDF
opened and no extraction performed. The authored store is the **real** `TriageLoader`
behind `cli.TriageStore`, which is the point: what these runs exercise is the wiring.

Extracted from `test_ingest_wiring.py` when the `dawmans validate` tests needed the
same index — a command that reads a committed view has to have one to read.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from rendering import Section, entry_file
from sections import CORPUS, passages
from stores import LIVE_ID, POINTER

from corpusfixtures import StubEmbedder
from dawmans.cli import TriageStore, ingest
from dawmans.corpus.discover import MANUALS_STORE, StoreScan, slug
from dawmans.corpus.loader import Discovered, LoadResult, Region, Unit
from dawmans.corpus.rig import Rig, RigDevice
from dawmans.index.manifest import read_manifest
from dawmans.records import AUTHORED_SOURCE_ID, HardwareApplicability, SourceRecord

RIG = Rig(
    devices=(
        RigDevice(id=LIVE_ID, display_name="Ableton Live 12", revision="12 Standard"),
        RigDevice(id="akai/apc-key-25", display_name="APC Key 25", revision="mk2"),
        RigDevice(id="focusrite/scarlett-solo", display_name="Scarlett Solo", revision="4th-gen"),
    )
)

ENTRY = entry_file(
    devices=[LIVE_ID],
    symptom="No sound from a track",
    sections=[
        Section("The Track Activator is off", check="the track's number is unlit", fixes=[POINTER]),
        Section("Another track is soloed", check="a Solo button is lit", fixes=[POINTER]),
    ],
)


@dataclass
class StubManuals:
    """`manuals/` rebuilt from the committed section fixtures — one region per section.

    The passages the run commits are chunked from the fixtures' own text, so a pointer
    resolves against real section numbers and the term check reads real vendor prose,
    with no PDF opened and no extraction run.
    """

    dropped: tuple[str, ...] = ()
    """Sections to withhold, for the drift case: the manual moved under the entry."""

    loaded: list[str] = field(default_factory=list)

    def sections(self) -> dict[str, list[Region]]:
        by_source: dict[str, dict[tuple[str | None, str], list[str]]] = {}
        for row in passages(*CORPUS):
            key = (row["section_number"], row["section_title"])
            if f"{row['source_id']} §{row['section_number']}" in self.dropped:
                continue
            by_source.setdefault(row["source_id"], {}).setdefault(key, []).append(row["text"])

        return {
            source_id: [
                Region(
                    section_number=number,
                    section_title=title,
                    section_path=(),
                    page_start=1,
                    page_end=1,
                    inferred=False,
                    units=[Unit(text=text, page_start=1, page_end=1) for text in texts],
                )
                for (number, title), texts in sections.items()
            ]
            for source_id, sections in by_source.items()
        }

    def scan(self) -> StoreScan:
        return StoreScan(
            store=MANUALS_STORE,
            available=True,
            sources=tuple(
                Discovered(
                    source_id=source_id,
                    fingerprint=f"sha256:{source_id}:{len(self.dropped)}",
                    origin=Path("manuals") / f"{slug(source_id)}.pdf",
                )
                for source_id in sorted(self.sections())
            ),
        )

    def load(self, d: Discovered) -> LoadResult:
        self.loaded.append(d.source_id)
        vendor, product = d.source_id.split("/")
        record = SourceRecord(
            kind="vendor-manual",
            source_id=d.source_id,
            vendor=vendor,
            product=product,
            doctype="manual",
            lang="en",
            doc_version="1",
            display_name=f"{vendor.title()} {product.title()}",
            hardware_applicability=HardwareApplicability(status="assumed", device=d.source_id),
            page_count=400,
            ingested_at="2026-08-15T10:00:00+00:00",
            chunk_count=0,
            low_text=False,
        )
        return LoadResult(record=record, regions=self.sections()[d.source_id], audit={})


def run(root: Path, *, manuals: StubManuals | None = None) -> tuple:
    manuals = manuals if manuals is not None else StubManuals()
    index_root = root / "index"
    result = ingest(
        index_root,
        vendor=manuals,
        authored=TriageStore(root=root, index_root=index_root, rig=RIG),
        embedder=StubEmbedder(),
        rig=RIG,
    )
    return result, manuals


def write(root: Path, files: dict[str, str]) -> Path:
    store = root / "triage"
    store.mkdir(parents=True, exist_ok=True)
    for name, text in files.items():
        path = store / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return store


def view_of(index_root: Path) -> Path:
    manifest = read_manifest(index_root)
    assert manifest is not None
    return index_root / manifest.view_dir


def authored_rows(index_root: Path) -> list[dict]:
    lines = (view_of(index_root) / "passages.jsonl").read_text(encoding="utf-8").splitlines()
    rows = [json.loads(line) for line in lines]
    return [row for row in rows if row["source_id"] == AUTHORED_SOURCE_ID]
