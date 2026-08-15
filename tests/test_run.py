"""A full ingestion run, end to end — 1.5-1.7, 8.6, 9.1, 9.6, 12.2, 12.3, 12.6, 12.7.

The corpus here is synthetic and both loaders are stubs, which is the point: what is under
test is the **orchestration**, not the PDF stages. A stub `TriageLoader` stands in for
`data/symptom-triage`, so the seam is exercised by something this spec does not own — a
run that only ever saw `PdfLoader` would prove nothing about 12.2.

Three properties carry the weight:

- **Convergence (12.2).** Both kinds reach the chunker as `Region`s and are chunked,
  embedded, sharded and inventoried by the same calls. The assertion is on the artefacts:
  the authored source's passages sit in the same `passages.jsonl`, its record in the same
  `sources.json`, its rows in the same `vectors.npy`.
- **Pass ordering.** The authored load runs after every vendor shard commits, so a fix
  pointer whose target text *this* run repaired resolves. The stub records what it could
  see when it was asked, which is the only way to observe the ordering from outside.
- **Carriage (12.6).** `unbacked` and `entry_location` arrive from the loader and reach the
  emitted `Passage` unchanged. This spec neither sets, clears nor derives them, and a test
  that only checked they were *present* would pass against code that recomputed them.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pytest

from corpusfixtures import PROSE, StubEmbedder, authored_record, record
from dawmans.cli import ingest, run_inventory, run_validate
from dawmans.corpus.discover import AUTHORED_STORE, MANUALS_STORE, StoreScan, slug
from dawmans.corpus.loader import Discovered, LoadResult, Region, Rejection, Unit, UnitFlags
from dawmans.corpus.rig import Rig, RigDevice
from dawmans.index.build import read_shards
from dawmans.index.manifest import read_manifest
from dawmans.records import AUTHORED_SOURCE_ID, HardwareApplicability
from dawmans.report import read_audit

# --- the two stub stores ------------------------------------------------------------------


@dataclass
class StubVendorStore:
    """`manuals/` behind the run's `Store` protocol, without a PDF in sight.

    The PDF stages have their own tests. What this has to be faithful about is the shape
    of what a loader hands back: a record, regions, an audit, and a rejection or none.
    """

    sources: dict[str, list[Region]] = field(default_factory=dict)
    rejections: dict[str, Rejection] = field(default_factory=dict)
    fingerprints: dict[str, str] = field(default_factory=dict)
    available: bool = True
    discovery_rejections: tuple = ()
    loaded: list[str] = field(default_factory=list)

    def scan(self) -> StoreScan:
        return StoreScan(
            store=MANUALS_STORE,
            available=self.available,
            sources=tuple(
                Discovered(
                    source_id=source_id,
                    fingerprint=self.fingerprints.get(source_id, f"sha256:{source_id}"),
                    origin=Path("manuals") / f"{slug(source_id)}.pdf",
                )
                for source_id in sorted(self.sources | self.rejections)
            ),
            rejections=self.discovery_rejections,
        )

    def load(self, d: Discovered) -> LoadResult:
        self.loaded.append(d.source_id)
        source = record(d.source_id, pages=40)
        rejection = self.rejections.get(d.source_id)
        if rejection is not None:
            return LoadResult(record=source, regions=[], rejection=rejection, audit={"pages": 40})
        return LoadResult(
            record=source,
            regions=self.sources[d.source_id],
            audit={
                "pages": 40,
                "language": {
                    "english_pages": [[1, 40]],
                    "excluded_pages": [],
                    "partial_pages": [],
                },
                "glyphs": {"glyph_spans_repaired": 3, "glyph_spans_degraded": 0},
            },
        )


@dataclass
class StubTriageStore:
    """`data/symptom-triage`'s half of the seam, as far as this spec can see it.

    It resolves each entry's fix pointer against the **committed vendor shards** and sets
    `unbacked` from the result, which is what makes the pass ordering observable: the
    passages it can see when `load()` is called are this run's or the previous run's, and
    nothing else about the run distinguishes the two.
    """

    index_root: Path
    #: symptom -> (body text, the vendor text the fix points at)
    entries: dict[str, tuple[str, str]] = field(default_factory=dict)
    available: bool = True
    invalid: Rejection | None = None
    #: The line the first entry sits on. The author re-lines entries on every edit, and
    #: `entry_location` moving must not move a `passage_id` (CONTRACTS §2).
    first_line: int = 1
    #: Every vendor passage text the loader could see, in the order it was asked.
    saw: list[str] = field(default_factory=list)

    def scan(self) -> StoreScan:
        if not self.available:
            return StoreScan(store=AUTHORED_STORE, available=False)
        digest = f"sha256:{sorted(self.entries)}"
        return StoreScan(
            store=AUTHORED_STORE,
            available=True,
            sources=(
                Discovered(
                    source_id=AUTHORED_SOURCE_ID,
                    fingerprint=digest,
                    origin=Path("triage"),
                ),
            ),
        )

    def load(self, d: Discovered) -> LoadResult:
        if self.invalid is not None:
            return LoadResult(
                record=authored_record(), regions=[], rejection=self.invalid, audit={}
            )

        backing = {
            passage.text
            for shard in read_shards(self.index_root)
            if shard.record.kind == "vendor-manual"
            for passage in shard.passages()
        }
        self.saw.extend(sorted(backing))

        regions = []
        entries = enumerate(sorted(self.entries.items()), start=self.first_line)
        for line, (symptom, (body, points_at)) in entries:
            resolved = any(points_at in text for text in backing)
            regions.append(
                Region(
                    section_number=None,
                    section_title=symptom,
                    section_path=(),
                    page_start=None,
                    page_end=None,
                    inferred=False,
                    units=[Unit(text=body, flags=UnitFlags(unbacked=not resolved))],
                    entry_location=f"triage/notes.md:{line}",
                )
            )
        return LoadResult(
            record=authored_record(),
            regions=regions,
            audit={"entries": len(regions)},
            sidecar={"entries": len(regions)},
        )


def vendor_region(text: str, *, title: str = "The Control Bar", page: int = 3) -> Region:
    return Region(
        section_number="2.1",
        section_title=title,
        section_path=("Live Concepts",),
        page_start=page,
        page_end=page,
        inferred=False,
        units=[Unit(text=text, page_start=page, page_end=page)],
    )


@pytest.fixture
def corpus(tmp_path: Path) -> tuple[Path, StubVendorStore, StubTriageStore]:
    index_root = tmp_path / "index"
    vendor = StubVendorStore(
        sources={
            "ableton/live-12": [vendor_region(PROSE)],
            "akai/apc-key-25": [vendor_region(PROSE[:80], title="Pads", page=7)],
        }
    )
    authored = StubTriageStore(
        index_root=index_root,
        entries={"No sound from track 3": ("Check the track is not soloed.", "tempo control")},
    )
    return index_root, vendor, authored


def view_of(index_root: Path) -> Path:
    manifest = read_manifest(index_root)
    assert manifest is not None
    return index_root / manifest.view_dir


def passages_of(index_root: Path) -> list[dict]:
    lines = (view_of(index_root) / "passages.jsonl").read_text().splitlines()
    return [json.loads(line) for line in lines]


# --- 12.2: both kinds converge and are handled by the same code ---------------------------


def test_both_kinds_reach_the_same_view(corpus) -> None:
    index_root, vendor, authored = corpus

    result = ingest(index_root, vendor=vendor, authored=authored, embedder=StubEmbedder())

    assert result.report.succeeded
    kinds = {row["source_id"]: row["kind"] for row in _sources(index_root)}
    assert kinds == {
        "ableton/live-12": "vendor-manual",
        "akai/apc-key-25": "vendor-manual",
        AUTHORED_SOURCE_ID: "authored-triage",
    }


def test_the_authored_source_is_chunked_embedded_and_sharded_like_a_manual(corpus) -> None:
    """Not "an authored source is also indexed" but "by the same calls": its passages are
    lines of the same file, its rows are rows of the same matrix, and the manifest slices
    it the same way."""
    index_root, vendor, authored = corpus

    ingest(index_root, vendor=vendor, authored=authored, embedder=StubEmbedder())

    manifest = read_manifest(index_root)
    assert manifest is not None
    rows = sum(source.row_count for source in manifest.sources)
    with (view_of(index_root) / "vectors.npy").open("rb") as handle:
        vectors = np.load(handle)
    assert vectors.shape == (rows, StubEmbedder().dim)
    assert len(passages_of(index_root)) == rows

    authored_slice = next(s for s in manifest.sources if s.source_id == AUTHORED_SOURCE_ID)
    assert authored_slice.row_count >= 1
    assert authored_slice.kind == "authored-triage"  # 12.7


def test_the_authored_source_is_inventoried_with_the_manuals(corpus) -> None:
    """9.1 and 12.2 together: one inventory, both kinds, and the kind-dependent fields
    reported as not applicable rather than invented."""
    index_root, vendor, authored = corpus
    ingest(index_root, vendor=vendor, authored=authored, embedder=StubEmbedder())

    code, lines = run_inventory(index_root)

    assert code == 0
    text = "\n".join(lines)
    assert AUTHORED_SOURCE_ID in text
    assert "ableton/live-12" in text
    assert "not applicable" in text  # the authored store's page_count, lang, doc_version…


def test_the_run_is_reproducible_from_the_two_stores_alone(corpus) -> None:
    """8.6: `index/` is derived. Deleting it and running again yields the same passages."""
    index_root, vendor, authored = corpus
    ingest(index_root, vendor=vendor, authored=authored, embedder=StubEmbedder())
    first = [row["passage_id"] for row in passages_of(index_root)]

    import shutil

    shutil.rmtree(index_root)
    ingest(index_root, vendor=vendor, authored=authored, embedder=StubEmbedder())

    assert [row["passage_id"] for row in passages_of(index_root)] == first


# --- pass ordering: the authored load sees this run's vendor shards ------------------------


def test_the_authored_load_runs_after_every_vendor_shard_commits(corpus) -> None:
    index_root, vendor, authored = corpus

    ingest(index_root, vendor=vendor, authored=authored, embedder=StubEmbedder())

    # The stub recorded every vendor passage committed at the moment it was asked. Both
    # manuals are there, so neither shard was still pending when the authored load ran.
    assert any("tempo control" in text for text in authored.saw)
    assert any(text.startswith(PROSE[:40]) for text in authored.saw)
    assert len(authored.saw) == 2
    assert vendor.loaded == ["ableton/live-12", "akai/apc-key-25"]


def test_a_pointer_whose_target_this_run_repaired_is_not_flagged_unbacked(
    tmp_path: Path,
) -> None:
    """The ordering exists for exactly this case. Run one indexes text the pointer does not
    match, so the entry is `unbacked`. Run two repairs the manual's text; if the authored
    load ran first it would still resolve against run one's passages and stay flagged."""
    index_root = tmp_path / "index"
    vendor = StubVendorStore(
        sources={"ableton/live-12": [vendor_region("The tmpo cntrl sets the speed.")]},
        fingerprints={"ableton/live-12": "sha256:before"},
    )
    authored = StubTriageStore(
        index_root=index_root,
        entries={"Wrong tempo": ("Check the tempo control.", "tempo control")},
    )

    ingest(index_root, vendor=vendor, authored=authored, embedder=StubEmbedder())
    assert _authored_passages(index_root)[0]["unbacked"] is True

    # The glyph repair lands: the manual now carries the text the pointer names.
    vendor.sources["ableton/live-12"] = [vendor_region("The tempo control sets the speed.")]
    vendor.fingerprints["ableton/live-12"] = "sha256:after"
    ingest(index_root, vendor=vendor, authored=authored, embedder=StubEmbedder())

    assert _authored_passages(index_root)[0]["unbacked"] is False


# --- 12.6: unbacked and entry_location are carried, never derived --------------------------


def test_unbacked_and_entry_location_reach_the_passage_unchanged(tmp_path: Path) -> None:
    index_root = tmp_path / "index"
    vendor = StubVendorStore(sources={"ableton/live-12": [vendor_region(PROSE)]})
    authored = StubTriageStore(
        index_root=index_root,
        entries={
            "Backed entry": ("Check the tempo.", "tempo control"),
            "Unbacked entry": ("Check the cabling.", "no manual says this"),
        },
    )

    ingest(index_root, vendor=vendor, authored=authored, embedder=StubEmbedder())

    by_title = {row["section_title"]: row for row in _authored_passages(index_root)}
    assert by_title["Backed entry"]["unbacked"] is False
    assert by_title["Unbacked entry"]["unbacked"] is True
    # The locations are the loader's own strings, at the loader's own lines.
    assert by_title["Backed entry"]["entry_location"] == "triage/notes.md:1"
    assert by_title["Unbacked entry"]["entry_location"] == "triage/notes.md:2"


def test_the_entry_location_does_not_enter_the_passage_id(tmp_path: Path) -> None:
    """CONTRACTS §2: the author re-lines entries on every edit, and an id derived from a
    location would orphan the citation history the stability rule exists to keep."""
    index_root = tmp_path / "index"
    vendor = StubVendorStore(sources={"ableton/live-12": [vendor_region(PROSE)]})
    authored = StubTriageStore(
        index_root=index_root, entries={"A symptom": ("The body text.", "tempo control")}
    )

    ingest(index_root, vendor=vendor, authored=authored, embedder=StubEmbedder())
    before = [row["passage_id"] for row in _authored_passages(index_root)]
    assert _authored_passages(index_root)[0]["entry_location"] == "triage/notes.md:1"

    # The same entry, moved down the file. Only `entry_location` differs.
    authored.first_line = 84
    ingest(index_root, vendor=vendor, authored=authored, embedder=StubEmbedder())

    assert _authored_passages(index_root)[0]["entry_location"] == "triage/notes.md:84"
    assert [row["passage_id"] for row in _authored_passages(index_root)] == before


# --- 1.5-1.7: a rejection excludes one source and the run still succeeds -------------------


def test_a_rejected_source_is_excluded_reported_and_the_run_succeeds(tmp_path: Path) -> None:
    index_root = tmp_path / "index"
    vendor = StubVendorStore(
        sources={"ableton/live-12": [vendor_region(PROSE)]},
        rejections={"akai/apc-key-25": Rejection(reason="no-english-content", detail="0 of 24")},
    )

    result = ingest(index_root, vendor=vendor, embedder=StubEmbedder())

    assert result.report.succeeded
    assert result.exit_code == 0
    assert "no-english-content" in result.report.line_for("akai/apc-key-25")
    indexed = {row["source_id"] for row in _sources(index_root)}
    assert indexed == {"ableton/live-12"}


def test_the_remaining_sources_stay_queryable_after_a_rejection(tmp_path: Path) -> None:
    """1.6's "continue with the remaining sources" is about the *index*, not the loop: the
    view a rejection leaves behind has to be readable, not merely written."""
    index_root = tmp_path / "index"
    vendor = StubVendorStore(
        sources={"ableton/live-12": [vendor_region(PROSE)]},
        rejections={"akai/apc-key-25": Rejection(reason="no-text-layer")},
    )

    ingest(index_root, vendor=vendor, embedder=StubEmbedder())

    code, lines = run_validate(index_root)
    assert code == 0, lines
    assert (view_of(index_root) / "lexical").exists()
    assert len(passages_of(index_root)) >= 1


def test_a_rejected_source_leaves_an_audit_carrying_its_reason(tmp_path: Path) -> None:
    index_root = tmp_path / "index"
    vendor = StubVendorStore(
        sources={"ableton/live-12": [vendor_region(PROSE)]},
        rejections={"akai/apc-key-25": Rejection(reason="unreadable-text", detail="3.1%")},
    )

    ingest(index_root, vendor=vendor, embedder=StubEmbedder())

    audit = read_audit(index_root, "akai/apc-key-25")
    assert audit is not None
    assert audit["rejection"] == {"reason": "unreadable-text", "detail": "3.1%"}


def test_a_source_rejected_after_it_was_indexed_loses_its_shard(tmp_path: Path) -> None:
    """Otherwise the run reports the rejection, succeeds, and keeps serving the previous
    run's passages — a source excluded in the report and present in the index."""
    index_root = tmp_path / "index"
    vendor = StubVendorStore(
        sources={
            "ableton/live-12": [vendor_region(PROSE)],
            "akai/apc-key-25": [vendor_region("Pad text", title="Pads", page=4)],
        }
    )
    ingest(index_root, vendor=vendor, embedder=StubEmbedder())
    assert "akai/apc-key-25" in {row["source_id"] for row in _sources(index_root)}

    del vendor.sources["akai/apc-key-25"]
    vendor.rejections["akai/apc-key-25"] = Rejection(reason="no-english-content")
    vendor.fingerprints["akai/apc-key-25"] = "sha256:changed"
    ingest(index_root, vendor=vendor, embedder=StubEmbedder())

    assert "akai/apc-key-25" not in {row["source_id"] for row in _sources(index_root)}


def test_an_authored_invalid_source_is_a_rejection_and_not_a_failure(tmp_path: Path) -> None:
    """12.6: the authored store's validity is `data/symptom-triage`'s to decide, and what
    it reports invalid is a rejection here."""
    index_root = tmp_path / "index"
    vendor = StubVendorStore(sources={"ableton/live-12": [vendor_region(PROSE)]})
    authored = StubTriageStore(
        index_root=index_root, invalid=Rejection(reason="authored-invalid", detail="cause 2")
    )

    result = ingest(index_root, vendor=vendor, authored=authored, embedder=StubEmbedder())

    assert result.report.succeeded
    assert "authored-invalid" in result.report.line_for(AUTHORED_SOURCE_ID)
    assert AUTHORED_SOURCE_ID not in {row["source_id"] for row in _sources(index_root)}


def test_a_failure_fails_the_run_without_stopping_it(tmp_path: Path) -> None:
    """1.7: no abort-on-first-failure. The source after the broken one is still indexed."""
    index_root = tmp_path / "index"

    class Broken(StubVendorStore):
        def load(self, d: Discovered) -> LoadResult:
            if d.source_id == "akai/apc-key-25":
                raise MemoryError("no room for the span model")
            return super().load(d)

    vendor = Broken(
        sources={
            "ableton/live-12": [vendor_region(PROSE)],
            "akai/apc-key-25": [vendor_region("Pads")],
            "alesis/nitro-max": [vendor_region("Triggers", page=25)],
        }
    )

    result = ingest(index_root, vendor=vendor, embedder=StubEmbedder())

    assert not result.report.succeeded
    assert result.exit_code == 1
    assert "no room for the span model" in "\n".join(result.report.lines())
    indexed = {row["source_id"] for row in _sources(index_root)}
    assert indexed == {"ableton/live-12", "alesis/nitro-max"}


def test_a_chunk_outside_the_page_range_is_a_failure_and_keeps_the_previous_shard(
    tmp_path: Path,
) -> None:
    """6.11 as design §Error Handling resolves it: a failure, not a rejection. Rejecting
    would discard a 1009-page source over one mis-anchored chunk and report success."""
    index_root = tmp_path / "index"
    vendor = StubVendorStore(sources={"ableton/live-12": [vendor_region(PROSE, page=3)]})
    ingest(index_root, vendor=vendor, embedder=StubEmbedder())
    before = [row["passage_id"] for row in passages_of(index_root)]

    vendor.sources["ableton/live-12"] = [vendor_region(PROSE, page=9001)]
    vendor.fingerprints["ableton/live-12"] = "sha256:misanchored"
    result = ingest(index_root, vendor=vendor, embedder=StubEmbedder())

    assert result.exit_code == 1
    assert "9001" in "\n".join(result.report.lines())
    assert [row["passage_id"] for row in passages_of(index_root)] == before


# --- the run's other outputs ---------------------------------------------------------------


def test_the_authored_store_is_never_skipped_as_unchanged(corpus) -> None:
    """`data/symptom-triage` §Discovery exempts the authored store from fingerprint-based
    skipping, and the exemption is what makes the pass ordering mean anything: the store's
    validity is a function of the *manuals* as well as its own text, so a fingerprint over
    its own bytes cannot say whether a pointer still resolves. Skipped, `unbacked` would
    describe the run before last."""
    index_root, vendor, authored = corpus
    ingest(index_root, vendor=vendor, authored=authored, embedder=StubEmbedder())
    seen = len(authored.saw)

    # Nothing in either store changed, so every vendor shard is reused.
    result = ingest(index_root, vendor=vendor, authored=authored, embedder=StubEmbedder())

    assert result.report.line_for("ableton/live-12").endswith("skipped as unchanged")
    assert result.report.line_for(AUTHORED_SOURCE_ID).endswith("ingested")
    assert len(authored.saw) > seen  # the loader ran again and re-resolved its pointers


def test_an_unchanged_source_is_skipped_and_its_audit_is_left_alone(corpus) -> None:
    """A reused shard's audit describes the run that produced it. Restamping it would make
    the diagnostics claim a measurement this run never took."""
    index_root, vendor, authored = corpus
    ingest(index_root, vendor=vendor, authored=authored, embedder=StubEmbedder())
    first = read_audit(index_root, "ableton/live-12")

    vendor.sources["ableton/live-12"] = [vendor_region("Entirely different text")]
    # …but the fingerprint is unchanged, so the run must not look.
    result = ingest(index_root, vendor=vendor, authored=authored, embedder=StubEmbedder())

    assert result.report.line_for("ableton/live-12").endswith("skipped as unchanged")
    assert read_audit(index_root, "ableton/live-12") == first


def test_gaps_json_is_written_into_the_view(corpus) -> None:
    index_root, vendor, authored = corpus
    rig = Rig(devices=(RigDevice(id="alesis/nitro-max", display_name="Alesis Nitro Max"),))

    ingest(index_root, vendor=vendor, authored=authored, embedder=StubEmbedder(), rig=rig)

    gaps = json.loads((view_of(index_root) / "gaps.json").read_text())
    assert set(gaps) == {"owned_but_undocumented", "documented_but_unconfirmed"}
    assert [device["id"] for device in gaps["owned_but_undocumented"]] == ["alesis/nitro-max"]


def test_a_rig_declaration_reaches_the_index_without_rebuilding_any_shard(
    tmp_path: Path,
) -> None:
    """The case the join exists for, and the one a build-time application silently loses:
    editing `rig.yaml` changes no source byte, so every shard is reused and no loader runs.
    Applied at build time, the new declaration would not reach the index until something
    unrelated happened to change the manual."""
    index_root = tmp_path / "index"
    vendor = StubVendorStore(
        sources={"focusrite/scarlett-solo-4g": [vendor_region("Direct Monitor", page=5)]}
    )
    owned = RigDevice(
        id="focusrite/scarlett-solo", display_name="Scarlett Solo 4th Gen", revision="4th-gen"
    )

    # Run one: the device is owned, the manual's product carries the generation marker the
    # device id does not, and nothing declares they are the same thing.
    first = ingest(index_root, vendor=vendor, embedder=StubEmbedder(), rig=Rig(devices=(owned,)))
    assert first.gaps.indexed_but_not_owned == ("focusrite/scarlett-solo-4g",)
    assert [d.id for d in first.gaps.owned_but_undocumented] == ["focusrite/scarlett-solo"]

    # Run two: the declaration is added and nothing else changes.
    declared = Rig(
        devices=(owned,),
        source_applicability={
            "focusrite/scarlett-solo-4g": HardwareApplicability(
                status="confirmed", device="focusrite/scarlett-solo", revision="4th-gen"
            )
        },
    )
    second = ingest(index_root, vendor=vendor, embedder=StubEmbedder(), rig=declared)

    assert second.report.line_for("focusrite/scarlett-solo-4g").endswith("skipped as unchanged")
    assert second.gaps.indexed_but_not_owned == ()
    assert second.gaps.owned_but_undocumented == ()
    published = {row["source_id"]: row["hardware_applicability"] for row in _sources(index_root)}
    assert published["focusrite/scarlett-solo-4g"]["device"] == "focusrite/scarlett-solo"
    assert published["focusrite/scarlett-solo-4g"]["status"] == "confirmed"


def test_indexed_but_not_owned_is_reported_and_the_run_still_succeeds(corpus) -> None:
    """11.7: both manuals document devices no `rig.yaml` declares. Reported, never fatal."""
    index_root, vendor, authored = corpus

    result = ingest(index_root, vendor=vendor, authored=authored, embedder=StubEmbedder())

    assert set(result.gaps.indexed_but_not_owned) == {"ableton/live-12", "akai/apc-key-25"}
    assert result.report.succeeded
    text = "\n".join(result.report.lines())
    assert "ableton/live-12" in text


def test_an_unavailable_authored_store_removes_nothing(corpus) -> None:
    """1.4: an absent store is an unknown discovery set, not an empty one. Treating them
    alike deletes every authored passage when a volume fails to mount, and succeeds."""
    index_root, vendor, authored = corpus
    ingest(index_root, vendor=vendor, authored=authored, embedder=StubEmbedder())
    assert AUTHORED_SOURCE_ID in {row["source_id"] for row in _sources(index_root)}

    authored.available = False
    result = ingest(index_root, vendor=vendor, authored=authored, embedder=StubEmbedder())

    assert AUTHORED_SOURCE_ID in {row["source_id"] for row in _sources(index_root)}
    assert AUTHORED_STORE in "\n".join(result.report.lines())


def test_a_source_removed_from_its_store_leaves_the_index(corpus) -> None:
    index_root, vendor, authored = corpus
    ingest(index_root, vendor=vendor, authored=authored, embedder=StubEmbedder())

    del vendor.sources["akai/apc-key-25"]
    ingest(index_root, vendor=vendor, authored=authored, embedder=StubEmbedder())

    assert "akai/apc-key-25" not in {row["source_id"] for row in _sources(index_root)}


def test_validate_reports_a_missing_manifest_rather_than_guessing(tmp_path: Path) -> None:
    code, lines = run_validate(tmp_path / "index")

    assert code == 1
    assert "no manifest" in "\n".join(lines)


# --- helpers -------------------------------------------------------------------------------


def _sources(index_root: Path) -> list[dict]:
    return json.loads((view_of(index_root) / "sources.json").read_text())


def _authored_passages(index_root: Path) -> list[dict]:
    return [row for row in passages_of(index_root) if row["source_id"] == AUTHORED_SOURCE_ID]
