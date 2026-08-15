"""The shared record shapes are the contract — CONTRACTS §1 and §2.

A spec may not invent a field on a shared record and may not silently drop one, so
these tests assert the field set itself as well as the kind-dependent rules: a field
CONTRACTS marks not applicable to a source's kind is refused rather than defaulted
(9.1, 12.5), and a pageless source's location fields stay absent (12.8).
"""

from __future__ import annotations

import dataclasses

import pytest

from dawmans.records import (
    AUTHORED_SOURCE_ID,
    HardwareApplicability,
    Passage,
    SourceRecord,
)

# The CONTRACTS §1 table, in its own order. Changing this set is an amendment to
# CONTRACTS, never a local edit.
SOURCE_RECORD_FIELDS = {
    "kind",
    "source_id",
    "vendor",
    "product",
    "doctype",
    "lang",
    "doc_version",
    "display_name",
    "hardware_applicability",
    "page_count",
    "ingested_at",
    "chunk_count",
    "low_text",
}

# The CONTRACTS §2 table.
PASSAGE_FIELDS = {
    "passage_id",
    "source_id",
    "section_number",
    "section_title",
    "page_start",
    "page_end",
    "text",
    "degraded",
    "has_figures",
    "unbacked",
    "entry_location",
}

# The fields CONTRACTS §1 marks not applicable to an `authored-triage` source.
NOT_APPLICABLE_TO_AUTHORED = [
    ("vendor", "akai"),
    ("product", "apc-key-25"),
    ("doctype", "user-guide"),
    ("lang", "multi"),
    ("doc_version", "1.0"),
    ("page_count", 24),
    ("low_text", False),
]


def vendor_source(**overrides: object) -> SourceRecord:
    fields: dict[str, object] = {
        "kind": "vendor-manual",
        "source_id": "akai/apc-key-25",
        "vendor": "akai",
        "product": "apc-key-25",
        "doctype": "user-guide",
        "lang": "multi",
        "doc_version": "1.0",
        "display_name": "Akai Apc Key 25",
        "hardware_applicability": HardwareApplicability(status="assumed", device="akai/apc-key-25"),
        "page_count": 24,
        "ingested_at": "2026-08-14T10:00:00Z",
        "chunk_count": 61,
        "low_text": False,
    }
    fields.update(overrides)
    return SourceRecord(**fields)  # type: ignore[arg-type]


def authored_source(**overrides: object) -> SourceRecord:
    fields: dict[str, object] = {
        "kind": "authored-triage",
        "source_id": AUTHORED_SOURCE_ID,
        "display_name": "Studio Triage Notes",
        "hardware_applicability": HardwareApplicability(status="assumed"),
        "ingested_at": "2026-08-14T10:00:00Z",
        "chunk_count": 12,
    }
    fields.update(overrides)
    return SourceRecord(**fields)  # type: ignore[arg-type]


def vendor_passage(**overrides: object) -> Passage:
    fields: dict[str, object] = {
        "passage_id": "akai/apc-key-25#0123456789abcdef",
        "source_id": "akai/apc-key-25",
        "section_number": "1.3.1",
        "section_title": "Connection Diagram",
        "page_start": 5,
        "page_end": 6,
        "text": "Connect the USB cable.",
    }
    fields.update(overrides)
    return Passage(**fields)  # type: ignore[arg-type]


def authored_passage(**overrides: object) -> Passage:
    fields: dict[str, object] = {
        "passage_id": f"{AUTHORED_SOURCE_ID}#fedcba9876543210",
        "source_id": AUTHORED_SOURCE_ID,
        "section_title": "No sound from the pads",
        "text": "Check the track activator.",
        "entry_location": "triage/no-sound.md:12",
    }
    fields.update(overrides)
    return Passage(**fields)  # type: ignore[arg-type]


# --- The record shape is the contract ------------------------------------------------


def test_source_record_carries_exactly_the_contracts_fields() -> None:
    assert {f.name for f in dataclasses.fields(SourceRecord)} == SOURCE_RECORD_FIELDS


def test_passage_carries_exactly_the_contracts_fields() -> None:
    assert {f.name for f in dataclasses.fields(Passage)} == PASSAGE_FIELDS


@pytest.mark.parametrize("build", [vendor_source, authored_source])
def test_source_record_refuses_a_field_outside_the_contract(build) -> None:
    with pytest.raises(TypeError):
        build(applicable_to="akai/apc-key-25-mk2")


def test_passage_refuses_a_field_outside_the_contract() -> None:
    with pytest.raises(TypeError):
        vendor_passage(section_path=("Racks", "Glue Compressor"))


@pytest.mark.parametrize("build", [vendor_source, authored_source, vendor_passage])
def test_records_are_frozen(build) -> None:
    record = build()
    with pytest.raises(AttributeError):
        record.source_id = "akai/other"


# --- Kind-dependent fields (9.1, 12.5) -----------------------------------------------


@pytest.mark.parametrize(("field", "value"), NOT_APPLICABLE_TO_AUTHORED)
def test_authored_source_refuses_a_field_not_applicable_to_its_kind(
    field: str, value: object
) -> None:
    with pytest.raises(ValueError, match=field):
        authored_source(**{field: value})


@pytest.mark.parametrize(("field", "_value"), NOT_APPLICABLE_TO_AUTHORED)
def test_authored_source_leaves_a_field_not_applicable_to_its_kind_absent(
    field: str, _value: object
) -> None:
    assert getattr(authored_source(), field) is None


@pytest.mark.parametrize(("field", "_value"), NOT_APPLICABLE_TO_AUTHORED)
def test_vendor_manual_requires_the_fields_applicable_to_its_kind(
    field: str, _value: object
) -> None:
    with pytest.raises(ValueError, match=field):
        vendor_source(**{field: None})


def test_authored_source_id_is_the_contracts_constant() -> None:
    assert authored_source().source_id == "authored/triage"

    with pytest.raises(ValueError, match="source_id"):
        authored_source(source_id="authored/triage-2026")


def test_authored_source_applicability_is_assumed() -> None:
    assert authored_source().hardware_applicability.status == "assumed"

    with pytest.raises(ValueError, match="hardware_applicability"):
        authored_source(hardware_applicability=HardwareApplicability(status="confirmed"))


def test_source_kind_is_declared_and_closed() -> None:
    with pytest.raises(ValueError, match="kind"):
        vendor_source(kind="vendor-pdf")


# --- Pageless sources (12.8) ----------------------------------------------------------


def test_pageless_passage_leaves_its_location_fields_absent() -> None:
    passage = authored_passage()

    assert passage.section_number is None
    assert passage.page_start is None
    assert passage.page_end is None


@pytest.mark.parametrize(
    ("field", "value"),
    [("section_number", "1.2"), ("page_start", 1), ("page_end", 1)],
)
def test_pageless_passage_refuses_a_synthesised_location(field: str, value: object) -> None:
    with pytest.raises(ValueError, match=field):
        authored_passage(**{field: value})


def test_pageless_passage_carries_its_entry_location() -> None:
    assert authored_passage().entry_location == "triage/no-sound.md:12"

    with pytest.raises(ValueError, match="entry_location"):
        authored_passage(entry_location=None)


@pytest.mark.parametrize("field", ["page_start", "page_end"])
def test_paged_passage_requires_its_pages(field: str) -> None:
    with pytest.raises(ValueError, match=field):
        vendor_passage(**{field: None})


def test_paged_passage_refuses_an_entry_location() -> None:
    with pytest.raises(ValueError, match="entry_location"):
        vendor_passage(entry_location="triage/no-sound.md:12")


def test_unnumbered_document_leaves_the_section_number_absent() -> None:
    assert vendor_passage(section_number=None).section_number is None


def test_page_range_runs_forwards() -> None:
    with pytest.raises(ValueError, match="page_end"):
        vendor_passage(page_start=6, page_end=5)
