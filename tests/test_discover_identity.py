"""The filename grammar and the identity it yields — requirements 2.1–2.7, 1.3, 12.5.

The grammar is a **published convention two other specs reproduce** (2.7): `api/answer-engine`
rebuilds a filename to serve the PDF behind a citation's open-at-source action, and again to
assemble `required_manual` for a device with no ingested source. So the round-trip is asserted as a
property here, not as a handful of examples, and `doc_version` is stored without its leading `v` so
that one reconstruction rule holds for every consumer.

The grammar applies to `vendor-manual` sources only (12.5). An `authored-triage` source has no
filename to derive an identity from and is never tested against it.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from dawmans.corpus.discover import (
    FILENAME_GRAMMAR,
    SourceIdentity,
    parse_filename,
    scan_manuals,
    slug,
)
from dawmans.records import AUTHORED_SOURCE_ID

# The reference corpus, plus the version forms 2.2 admits beyond it.
ACCEPTED = [
    (
        "ableton_live-12_reference-manual_v12_en.pdf",
        SourceIdentity(
            vendor="ableton",
            product="live-12",
            doctype="reference-manual",
            doc_version="12",
            lang="en",
        ),
    ),
    (
        "akai_apc-key-25_user-guide_v1.0_multi.pdf",
        SourceIdentity(
            vendor="akai",
            product="apc-key-25",
            doctype="user-guide",
            doc_version="1.0",
            lang="multi",
        ),
    ),
    (
        "alesis_nitro-max_user-guide_v1.1_en.pdf",
        SourceIdentity(
            vendor="alesis",
            product="nitro-max",
            doctype="user-guide",
            doc_version="1.1",
            lang="en",
        ),
    ),
    (
        "focusrite_scarlett-solo-4g_user-guide_v4.0_en.pdf",
        SourceIdentity(
            vendor="focusrite",
            product="scarlett-solo-4g",
            doctype="user-guide",
            doc_version="4.0",
            lang="en",
        ),
    ),
    (
        "roland_tr-8s_owners-manual_v2.10.3_ja.pdf",
        SourceIdentity(
            vendor="roland",
            product="tr-8s",
            doctype="owners-manual",
            doc_version="2.10.3",
            lang="ja",
        ),
    ),
]

REJECTED = [
    pytest.param("Ableton_live-12_reference-manual_v12_en.pdf", id="uppercase-vendor"),
    pytest.param("ableton_live-12_reference-manual_v12_EN.pdf", id="uppercase-lang"),
    pytest.param("ableton_live-12_reference-manual_v12_en.PDF", id="uppercase-extension"),
    pytest.param("ableton_live-12_reference-manual_12_en.pdf", id="version-without-v"),
    pytest.param("ableton_live-12_reference-manual_v_en.pdf", id="version-empty"),
    pytest.param("ableton_live-12_reference-manual_v12._en.pdf", id="version-trailing-stop"),
    pytest.param("ableton_live-12_reference-manual_v1-2_en.pdf", id="version-kebab"),
    pytest.param("ableton_live-12_v12_en.pdf", id="doctype-missing"),
    pytest.param("x_ableton_live-12_reference-manual_v12_en.pdf", id="field-extra"),
    pytest.param("ableton_live 12_reference-manual_v12_en.pdf", id="space-in-field"),
    pytest.param("ableton_live--12_reference-manual_v12_en.pdf", id="double-hyphen"),
    pytest.param("ableton_-live-12_reference-manual_v12_en.pdf", id="leading-hyphen"),
    pytest.param("ableton_live-12-_reference-manual_v12_en.pdf", id="trailing-hyphen"),
    pytest.param("ableton_live-12_reference-manual_v12_eng.pdf", id="lang-three-letters"),
    pytest.param("ableton_live-12_reference-manual_v12_multilingual.pdf", id="lang-word"),
    pytest.param("ableton_live-12_reference-manual_v12_en.pdf.bak", id="extension-trailing"),
    pytest.param("manuals/ableton_live-12_reference-manual_v12_en.pdf", id="path-not-name"),
    pytest.param("live-12.pdf", id="fields-missing"),
]

KEBAB = st.from_regex(r"\A[a-z0-9]+(?:-[a-z0-9]+)*\Z", fullmatch=True)
VERSION = st.from_regex(r"\A[0-9]+(?:\.[0-9]+)*\Z", fullmatch=True)
LANG = st.sampled_from(["en", "de", "fr", "es", "ja", "multi"])


def write_pdf(store: Path, name: str) -> Path:
    path = store / name
    path.write_bytes(b"%PDF-1.7\n" + name.encode())
    return path


# --- The grammar (2.1-2.3) ------------------------------------------------------------


@pytest.mark.parametrize(("name", "identity"), ACCEPTED, ids=[n for n, _ in ACCEPTED])
def test_grammar_accepts_the_convention(name: str, identity: SourceIdentity) -> None:
    assert parse_filename(name) == identity


@pytest.mark.parametrize("name", REJECTED)
def test_grammar_rejects_a_name_outside_the_convention(name: str) -> None:
    assert parse_filename(name) is None


# --- The round trip two other specs depend on (2.4, 2.7) ------------------------------


@pytest.mark.parametrize("name", [n for n, _ in ACCEPTED])
def test_an_accepted_name_is_rebuilt_from_its_own_fields(name: str) -> None:
    identity = parse_filename(name)
    assert identity is not None
    assert identity.filename == name


@given(vendor=KEBAB, product=KEBAB, doctype=KEBAB, version=VERSION, lang=LANG)
def test_round_trip_holds_for_every_accepted_name(
    vendor: str, product: str, doctype: str, version: str, lang: str
) -> None:
    name = f"{vendor}_{product}_{doctype}_v{version}_{lang}.pdf"
    identity = parse_filename(name)

    assert identity is not None
    assert identity.filename == name
    # The `v` is the grammar's, not the field's: rebuilding from `doc_version` must never
    # produce `_vv1.0_` (CONTRACTS §1).
    assert not identity.doc_version.startswith("v")
    assert f"v{identity.doc_version}" in name


def test_doc_version_is_stored_without_its_leading_v() -> None:
    identity = parse_filename("akai_apc-key-25_user-guide_v1.0_multi.pdf")
    assert identity is not None
    assert identity.doc_version == "1.0"


# --- Identity derived from the name (2.4) ---------------------------------------------


@pytest.mark.parametrize(
    ("name", "source_id"),
    [
        ("ableton_live-12_reference-manual_v12_en.pdf", "ableton/live-12"),
        ("akai_apc-key-25_user-guide_v1.0_multi.pdf", "akai/apc-key-25"),
        ("focusrite_scarlett-solo-4g_user-guide_v4.0_en.pdf", "focusrite/scarlett-solo-4g"),
    ],
)
def test_source_id_is_vendor_over_product_and_carries_no_version(name: str, source_id: str) -> None:
    identity = parse_filename(name)
    assert identity is not None
    # Replacing v12 with v12.1 must not orphan an authored fix pointer (triage 8.3), so the
    # version field is outside the ID even where the product name itself carries digits.
    assert identity.source_id == source_id


@pytest.mark.parametrize(
    ("name", "display_name"),
    [
        ("ableton_live-12_reference-manual_v12_en.pdf", "Ableton Live 12"),
        ("akai_apc-key-25_user-guide_v1.0_multi.pdf", "Akai Apc Key 25"),
        ("alesis_nitro-max_user-guide_v1.1_en.pdf", "Alesis Nitro Max"),
    ],
)
def test_display_name_is_the_title_cased_vendor_and_product(name: str, display_name: str) -> None:
    identity = parse_filename(name)
    assert identity is not None
    # The version is its own SourceRecord field and CONTRACTS §3 shows it inline, so
    # folding it in here would render it twice.
    assert identity.display_name == display_name


@given(vendor=KEBAB, product=KEBAB, doctype=KEBAB, version=VERSION, lang=LANG)
def test_the_version_never_reaches_the_source_id(
    vendor: str, product: str, doctype: str, version: str, lang: str
) -> None:
    identity = parse_filename(f"{vendor}_{product}_{doctype}_v{version}_{lang}.pdf")
    assert identity is not None
    assert identity.source_id == f"{vendor}/{product}"


# --- The slug (design §Source identity and discovery) ---------------------------------


def test_slug_replaces_the_single_separator_with_an_underscore() -> None:
    assert slug("ableton/live-12") == "ableton_live-12"
    assert slug(AUTHORED_SOURCE_ID) == "authored_triage"


def test_slug_is_injective_where_a_hyphen_would_collide() -> None:
    # The grammar forbids `_` inside vendor and product but allows `-`, so `/`->`-` maps
    # two legal source IDs onto one shard while `/`->`_` keeps them apart.
    assert slug("a/b-c") != slug("a-b/c")
    assert "a/b-c".replace("/", "-") == "a-b/c".replace("/", "-")


# --- Discovery outcomes for the store (1.3, 2.5, 2.6) ---------------------------------


def test_a_scan_discovers_every_well_named_pdf(tmp_path: Path) -> None:
    write_pdf(tmp_path, "ableton_live-12_reference-manual_v12_en.pdf")
    write_pdf(tmp_path, "alesis_nitro-max_user-guide_v1.1_en.pdf")

    scan = scan_manuals(tmp_path)

    assert scan.available
    assert {d.source_id for d in scan.sources} == {"ableton/live-12", "alesis/nitro-max"}
    assert scan.rejections == ()


def test_a_malformed_name_is_rejected_with_the_offending_name_and_the_pattern(
    tmp_path: Path,
) -> None:
    write_pdf(tmp_path, "Live 12 Manual.pdf")

    (rejected,) = scan_manuals(tmp_path).rejections

    assert rejected.rejection.reason == "filename-invalid"
    assert rejected.origin.name == "Live 12 Manual.pdf"
    assert FILENAME_GRAMMAR in rejected.rejection.detail


def test_a_malformed_name_indexes_nothing(tmp_path: Path) -> None:
    write_pdf(tmp_path, "Live 12 Manual.pdf")
    assert scan_manuals(tmp_path).sources == ()


def test_two_files_resolving_to_one_source_id_reject_both(tmp_path: Path) -> None:
    write_pdf(tmp_path, "akai_apc-key-25_user-guide_v1.0_multi.pdf")
    write_pdf(tmp_path, "akai_apc-key-25_user-guide_v2.0_en.pdf")

    scan = scan_manuals(tmp_path)

    # Silently indexing one of them is the failure 2.6 names.
    assert scan.sources == ()
    assert {r.rejection.reason for r in scan.rejections} == {"source-id-collision"}
    assert {r.origin.name for r in scan.rejections} == {
        "akai_apc-key-25_user-guide_v1.0_multi.pdf",
        "akai_apc-key-25_user-guide_v2.0_en.pdf",
    }
    assert all("akai/apc-key-25" in r.rejection.detail for r in scan.rejections)


def test_a_collision_leaves_the_other_sources_alone(tmp_path: Path) -> None:
    write_pdf(tmp_path, "akai_apc-key-25_user-guide_v1.0_multi.pdf")
    write_pdf(tmp_path, "akai_apc-key-25_user-guide_v2.0_en.pdf")
    write_pdf(tmp_path, "alesis_nitro-max_user-guide_v1.1_en.pdf")

    scan = scan_manuals(tmp_path)

    assert [d.source_id for d in scan.sources] == ["alesis/nitro-max"]


@pytest.mark.parametrize("name", ["README.md", "notes.txt", ".DS_Store", "cover.png"])
def test_a_non_pdf_is_skipped_with_no_report_line(tmp_path: Path, name: str) -> None:
    (tmp_path / name).write_text("not a manual")
    write_pdf(tmp_path, "alesis_nitro-max_user-guide_v1.1_en.pdf")

    scan = scan_manuals(tmp_path)

    # 1.3: skipped silently, and the run is not failed by it.
    assert scan.rejections == ()
    assert [d.source_id for d in scan.sources] == ["alesis/nitro-max"]


def test_a_subdirectory_is_not_a_source(tmp_path: Path) -> None:
    (tmp_path / "archive").mkdir()
    write_pdf(tmp_path / "archive", "alesis_nitro-max_user-guide_v1.1_en.pdf")

    scan = scan_manuals(tmp_path)

    assert scan.sources == ()
    assert scan.rejections == ()


# --- The grammar is for vendor manuals only (12.5) ------------------------------------


def test_the_authored_source_id_is_not_a_filename_and_is_never_parsed_as_one() -> None:
    # An authored-triage source has no filename: its identity is the CONTRACTS §1
    # constant, which the grammar neither accepts nor is asked about.
    assert parse_filename(f"{AUTHORED_SOURCE_ID}.pdf") is None
    assert parse_filename("authored_triage_notes_v1_en.pdf") is not None


def test_a_manual_claiming_the_authored_identity_resolves_onto_it(tmp_path: Path) -> None:
    # Legal grammar, and it lands on the authored store's own identity. One store's scan
    # cannot see that; the run-level collision check is what rejects it (test_discover_stores).
    write_pdf(tmp_path, "authored_triage_notes_v1_en.pdf")

    (discovered,) = scan_manuals(tmp_path).sources

    assert discovered.source_id == AUTHORED_SOURCE_ID
