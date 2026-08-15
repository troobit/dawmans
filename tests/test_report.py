"""The per-run report and the per-source ingestion audits — 1.5-1.7, 4.4, 5.4, 9.1, 9.5, 11.7.

Two artefacts with two lifetimes, and the distinction is the whole of this module. The
**run report** describes one run and is written to the terminal; the **ingestion audit** at
`index/audits/<slug>.json` describes one source and outlives the view it accompanied
(design §Index layout).

The load-bearing assertion here is the outcome taxonomy. A *rejection* is one of six named
conditions (1.6): it excludes one source, is reported, and the run still succeeds. A
*failure* is anything else (1.7): the run continues through the remaining sources and exits
non-zero at the end. The two are not degrees of the same thing — reporting a disk error as a
rejection would make a run that indexed nothing report success — so the set is closed at
construction rather than checked at the point of rendering.

11.7's indexed-but-not-owned line is here on sufferance: `rig.py` computes it and this
module only renders it. It is never an error and never in `gaps.json`, and the tests below
assert both of those against a stub value.
"""

from __future__ import annotations

import json
from dataclasses import fields
from pathlib import Path

import pytest

from corpusfixtures import authored_record, record
from dawmans.corpus.discover import FILENAME_GRAMMAR, MANUALS_STORE, scan_manuals, slug
from dawmans.corpus.loader import REJECTION_REASONS, Rejection
from dawmans.corpus.pdf.sections import ANCHOR_PAGE_ONLY, ANCHOR_TITLE
from dawmans.records import VENDOR_MANUAL_ONLY_FIELDS, SourceRecord
from dawmans.report import (
    NOT_APPLICABLE,
    Failure,
    RunReport,
    SourceOutcome,
    StoreAnomaly,
    audit_path,
    inventory_lines,
    inventory_row,
    read_audit,
    write_audit,
)

# What `PdfLoader` hands over for a source that reached the end of the pipeline, in that
# module's own keys: the 4.4 English page ranges, the 5.4 glyph counts, and the anchor
# quality of the section map. The shape is `PdfLoader`'s, not this module's — a report that
# renamed the loader's keys would drift from them silently.
AUDIT = {
    "pages": 24,
    "low_text": False,
    "furniture_lines": 46,
    "glyphs": {
        "glyph_spans_repaired": 118,
        "glyph_spans_degraded": 2,
        "unmappable_char_ratio": 0.0,
    },
    "sections": {"path": "outline", "sections": 31, "numbered": True},
    "anchors": {ANCHOR_TITLE: 28, ANCHOR_PAGE_ONLY: 3},
    "language": {
        "english_pages": [[3, 6], [23, 23]],
        "excluded_pages": [[7, 22]],
        "partial_pages": [3],
    },
    "units": 214,
}


def ingested(source_id: str = "ableton/live-12") -> SourceOutcome:
    return SourceOutcome(source_id=source_id, store=MANUALS_STORE, outcome="ingested")


def rejected(source_id: str, reason: str, detail: str = "") -> SourceOutcome:
    return SourceOutcome(
        source_id=source_id,
        store=MANUALS_STORE,
        outcome="rejected",
        rejection=Rejection(reason=reason, detail=detail),  # type: ignore[arg-type]
    )


# --- 1.5: every source is named with what became of it -----------------------------------


def test_every_source_is_reported_as_ingested_skipped_or_rejected() -> None:
    report = RunReport(
        outcomes=(
            ingested("ableton/live-12"),
            SourceOutcome(source_id="akai/apc-key-25", store=MANUALS_STORE, outcome="skipped"),
            rejected("alesis/nitro-max", "no-text-layer"),
        )
    )

    text = "\n".join(report.lines())
    assert "ableton/live-12" in text
    assert "akai/apc-key-25" in text
    assert "alesis/nitro-max" in text
    # The three verbs 1.5 names, each against its own source and not merely present.
    assert report.line_for("ableton/live-12").endswith("ingested")
    assert report.line_for("akai/apc-key-25").endswith("skipped as unchanged")
    assert "no-text-layer" in report.line_for("alesis/nitro-max")


def test_a_filename_invalid_rejection_reports_the_expected_pattern(tmp_path: Path) -> None:
    """2.5's report line is useless without the grammar: the whole point is to say what
    the name should have been, and the name that was is already on screen."""
    (tmp_path / "Live 12 Manual.pdf").write_bytes(b"%PDF-1.7\n")
    scan = scan_manuals(tmp_path)

    report = RunReport(
        outcomes=tuple(SourceOutcome.of(r, store=scan.store) for r in scan.rejections)
    )

    line = report.lines()[0]
    assert "filename-invalid" in line
    assert FILENAME_GRAMMAR in line


def test_a_rejection_names_the_file_when_the_name_yielded_no_identity(tmp_path: Path) -> None:
    """A `filename-invalid` source has no `source_id` — it never got one. Reporting it as
    an unnamed rejection would leave the owner unable to find the file."""
    (tmp_path / "whatever.pdf").write_bytes(b"%PDF-1.7\n")
    scan = scan_manuals(tmp_path)

    outcome = SourceOutcome.of(scan.rejections[0], store=scan.store)

    assert outcome.source_id is None
    assert "whatever.pdf" in outcome.line()


# --- 1.6/1.7: the rejection set is closed -------------------------------------------------


def test_the_six_rejection_reasons_are_the_whole_set() -> None:
    assert set(REJECTION_REASONS) == {
        "filename-invalid",
        "source-id-collision",
        "no-text-layer",
        "no-english-content",
        "unreadable-text",
        "authored-invalid",
    }


@pytest.mark.parametrize("reason", REJECTION_REASONS)
def test_each_listed_reason_is_reportable_as_a_rejection(reason: str) -> None:
    assert rejected("akai/apc-key-25", reason).rejection.reason == reason  # type: ignore[union-attr]


@pytest.mark.parametrize("reason", ["disk-full", "out-of-memory", "", "rejected", "no_text_layer"])
def test_an_unlisted_condition_cannot_be_reported_as_a_rejection(reason: str) -> None:
    """The closed set is enforced where a `Rejection` is built, not where one is rendered.

    A disk error reported as a rejection is a run that indexed nothing and exited zero —
    1.7's failure path exists precisely so that cannot happen, and it only holds if the
    other path is unreachable for anything not in 1.6's list.
    """
    with pytest.raises(ValueError) as error:
        Rejection(reason=reason)  # type: ignore[arg-type]
    assert "filename-invalid" in str(error.value)  # the message names the set


def test_a_run_with_rejections_and_no_failures_succeeds() -> None:
    report = RunReport(outcomes=(ingested(), rejected("akai/apc-key-25", "no-english-content")))

    assert report.succeeded
    assert report.exit_code == 0


def test_a_failure_fails_the_run_and_every_failure_is_listed() -> None:
    """1.7 has no abort-on-first-failure path, so a second failure is not a detail the
    first one hides: both sources are named and both messages survive to the report."""
    report = RunReport(
        outcomes=(ingested("ableton/live-12"),),
        failures=(
            Failure(source_id="akai/apc-key-25", message="chunk page 91 is outside pages 1-24"),
            Failure(source_id="alesis/nitro-max", message="MemoryError while embedding"),
        ),
    )

    assert not report.succeeded
    assert report.exit_code == 1
    text = "\n".join(report.lines())
    assert "chunk page 91 is outside pages 1-24" in text
    assert "MemoryError while embedding" in text


def test_a_rejected_source_does_not_become_a_failure() -> None:
    report = RunReport(outcomes=(rejected("alesis/nitro-max", "unreadable-text"),))

    assert report.failures == ()
    assert report.exit_code == 0


def test_an_outcome_is_rejected_exactly_when_it_carries_a_rejection() -> None:
    with pytest.raises(ValueError):
        SourceOutcome(source_id="a/b", store=MANUALS_STORE, outcome="rejected")
    with pytest.raises(ValueError):
        SourceOutcome(
            source_id="a/b",
            store=MANUALS_STORE,
            outcome="ingested",
            rejection=Rejection(reason="no-text-layer"),
        )


# --- the ingestion audit ------------------------------------------------------------------


def test_the_audit_is_written_under_the_source_slug(tmp_path: Path) -> None:
    path = write_audit(tmp_path, "ableton/live-12", AUDIT)

    assert path == tmp_path / "audits" / f"{slug('ableton/live-12')}.json"
    assert path.parent.name == "audits"  # never `reports/`, which is the view's (§Index layout)


def test_the_audit_carries_the_english_ranges_glyph_counts_and_anchor_quality(
    tmp_path: Path,
) -> None:
    write_audit(tmp_path, "ableton/live-12", AUDIT)

    written = read_audit(tmp_path, "ableton/live-12")
    assert written is not None
    assert written["language"] == AUDIT["language"]  # 4.4
    assert written["glyphs"] == AUDIT["glyphs"]  # 5.4
    assert written["anchors"] == AUDIT["anchors"]  # 6.6 anchor quality


def test_a_rejected_source_still_gets_an_audit_carrying_its_reason(tmp_path: Path) -> None:
    """The diagnostics for a rejection are the only record of *why*, and a rejected source
    commits no shard — so an audit written only on success would be written only where it
    is least needed."""
    rejection = Rejection(reason="no-english-content", detail="0 of 24 pages were English")

    write_audit(tmp_path, "akai/apc-key-25", {"pages": 24}, rejection=rejection)

    written = read_audit(tmp_path, "akai/apc-key-25")
    assert written is not None
    assert written["rejection"] == {
        "reason": "no-english-content",
        "detail": "0 of 24 pages were English",
    }


def test_an_audit_always_carries_the_rejection_key_even_when_there_is_none(
    tmp_path: Path,
) -> None:
    """Absent and null are different to a reader, and only one of them is a statement.
    The same rule `gaps.json` follows for an empty report (11.4)."""
    write_audit(tmp_path, "ableton/live-12", AUDIT)

    written = read_audit(tmp_path, "ableton/live-12")
    assert written is not None
    assert "rejection" in written
    assert written["rejection"] is None


def test_writing_an_audit_does_not_mutate_the_loader_s_dict(tmp_path: Path) -> None:
    audit = dict(AUDIT)

    write_audit(tmp_path, "ableton/live-12", audit, rejection=Rejection(reason="no-text-layer"))

    assert audit == AUDIT


def test_an_absent_audit_reads_as_none(tmp_path: Path) -> None:
    assert read_audit(tmp_path, "ableton/live-12") is None
    assert audit_path(tmp_path, "ableton/live-12").exists() is False


def test_an_audit_is_rewritten_in_place_when_its_source_is_re_ingested(tmp_path: Path) -> None:
    write_audit(tmp_path, "ableton/live-12", {"pages": 24})
    write_audit(tmp_path, "ableton/live-12", {"pages": 1009})

    written = read_audit(tmp_path, "ableton/live-12")
    assert written is not None
    assert written["pages"] == 1009
    assert list((tmp_path / "audits").iterdir()) == [audit_path(tmp_path, "ableton/live-12")]


# --- 9.1: the inventory is the CONTRACTS §1 table and nothing else ------------------------


def test_the_inventory_row_holds_every_source_record_field_and_adds_none() -> None:
    """9.1 names *that* table, not a copy of it. A row derived from the record's own
    fields cannot drift from CONTRACTS §1; a hand-written key list silently can."""
    row = inventory_row(record("ableton/live-12"))

    assert set(row) == {f.name for f in fields(SourceRecord)}


def test_a_field_not_applicable_to_the_kind_is_reported_as_not_applicable() -> None:
    """The authored store has no filename and no pages. Reporting `lang` as `en` or
    `page_count` as 0 would be inventing a value for a field CONTRACTS §1 marks not
    applicable, which is exactly what 9.1 forbids."""
    row = inventory_row(authored_record())

    for name in VENDOR_MANUAL_ONLY_FIELDS:
        assert row[name] == NOT_APPLICABLE, name
    assert row["kind"] == "authored-triage"
    assert row["source_id"] == "authored/triage"


def test_a_vendor_manual_reports_real_values_for_the_same_fields() -> None:
    row = inventory_row(record("akai/apc-key-25", pages=24, chunks=31))

    assert NOT_APPLICABLE not in row.values()
    assert row["page_count"] == 24
    assert row["chunk_count"] == 31


def test_the_english_ranges_are_reported_alongside_the_inventory_not_inside_the_record() -> None:
    """9.1's last sentence: the 4.4 audit travels with the inventory as an ingestion
    report. Putting it on the record would add a field to CONTRACTS §1."""
    source = record("ableton/live-12")

    assert "language" not in inventory_row(source)
    text = "\n".join(inventory_lines([source], audits={"ableton/live-12": AUDIT}))
    assert "3-6" in text and "23" in text  # included
    assert "7-22" in text  # excluded


def test_the_applicability_renders_its_status_first_and_not_as_a_repr() -> None:
    """`assumed` is the part that matters — 11.5 exists because it means nobody has
    checked — and a dataclass repr buries it in the middle of a field list."""
    source = record("akai/apc-key-25")

    line = next(
        line
        for line in inventory_lines([source])
        if line.strip().startswith("hardware_applicability:")
    )

    assert line.strip() == "hardware_applicability: assumed for akai/apc-key-25"
    assert "HardwareApplicability(" not in line


def test_an_inventory_without_audits_still_renders_every_source() -> None:
    lines = inventory_lines([record("ableton/live-12"), authored_record()])

    text = "\n".join(lines)
    assert "ableton/live-12" in text
    assert "authored/triage" in text


# --- 9.5: anomalies, per store and in both directions -------------------------------------


def test_anomalies_are_reported_per_store_in_both_directions() -> None:
    report = RunReport(
        anomalies=(
            StoreAnomaly(
                store=MANUALS_STORE,
                in_store_not_indexed=("alesis/nitro-max",),
                indexed_not_in_store=("akai/apc-key-25",),
            ),
            StoreAnomaly(store="triage", in_store_not_indexed=(), indexed_not_in_store=()),
        )
    )

    text = "\n".join(report.lines())
    assert "alesis/nitro-max" in text
    assert "akai/apc-key-25" in text
    assert MANUALS_STORE in text


def test_an_anomaly_line_names_the_store_it_was_found_in() -> None:
    """9.5's own qualifier: an authored source is not an anomaly for being absent from
    `manuals/`. A line that named neither store would read as if it were."""
    anomaly = StoreAnomaly(
        store="triage", in_store_not_indexed=("authored/triage",), indexed_not_in_store=()
    )

    assert "triage" in "\n".join(anomaly.lines())
    assert MANUALS_STORE not in "\n".join(anomaly.lines())


def test_a_store_with_no_anomalies_reports_nothing() -> None:
    quiet = StoreAnomaly(store=MANUALS_STORE, in_store_not_indexed=(), indexed_not_in_store=())

    assert quiet.lines() == []


def test_an_anomaly_is_not_a_failure() -> None:
    """9.5 is a report, not a gate. A source in `manuals/` and absent from the index is
    already reported as rejected by 1.5; failing the run again on the same fact would make
    a rejection fail the run through the back door."""
    report = RunReport(
        anomalies=(
            StoreAnomaly(
                store=MANUALS_STORE,
                in_store_not_indexed=("alesis/nitro-max",),
                indexed_not_in_store=(),
            ),
        )
    )

    assert report.exit_code == 0


# --- 11.7: rendered here, computed in rig.py ----------------------------------------------


def test_indexed_but_not_owned_is_named_in_the_run_report() -> None:
    report = RunReport(
        outcomes=(ingested("focusrite/scarlett-solo-4g"),),
        indexed_but_not_owned=("focusrite/scarlett-solo-4g",),
    )

    assert "focusrite/scarlett-solo-4g" in "\n".join(report.lines())


def test_indexed_but_not_owned_is_never_an_error() -> None:
    """A manual for gear the owner does not hold is not a fault in the run. It is a
    prompt to add a `source_applicability` declaration or a device to `rig.yaml`."""
    report = RunReport(indexed_but_not_owned=("focusrite/scarlett-solo-4g",))

    assert report.succeeded
    assert report.exit_code == 0
    assert report.failures == ()


def test_indexed_but_not_owned_is_never_written_to_gaps_json(tmp_path: Path) -> None:
    """CONTRACTS §5 governs two reports with named consumers. A third member in the
    published payload would oblige two other specs to render something neither wants."""
    from dawmans.corpus.rig import GapReports

    gaps = GapReports(indexed_but_not_owned=("focusrite/scarlett-solo-4g",)).to_dict()
    (tmp_path / "gaps.json").write_text(json.dumps(gaps))

    assert set(gaps) == {"owned_but_undocumented", "documented_but_unconfirmed"}
    assert "focusrite/scarlett-solo-4g" not in (tmp_path / "gaps.json").read_text()


def test_the_report_renders_the_value_it_is_given_and_computes_nothing() -> None:
    """A stub value is enough: `rig.py` owns the join and this module owns the line."""
    report = RunReport(
        outcomes=(ingested("ableton/live-12"),), indexed_but_not_owned=("not/a-real-device",)
    )

    assert "not/a-real-device" in "\n".join(report.lines())
