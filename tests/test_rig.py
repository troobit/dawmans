"""The rig inventory and the three gap reports — requirements 11.1–11.7.

`rig.yaml` is the one declared input this spec has that is not a source. It says what the
studio owner **owns**; `manuals/` says what is **documented**. 11.3 keeps them apart on
purpose, and the whole of §11 is the join between them.

The join runs through `hardware_applicability.device` and never through `source_id`
(Decision 9). That looks like a nicety until the Focusrite: the filename's product carries
the generation marker (`scarlett-solo-4g`) and the rig's device id does not
(`scarlett-solo`), so a join on the ID would miss the device, and the device — whose manual
is sitting in `manuals/` — would be reported as owned-but-undocumented with nothing naming
the cause. The declaration is what makes them meet, and 11.7's third report is what makes a
missing declaration visible.

Two of the assertions here are about **emptiness rather than content**. An empty
owned-but-undocumented report is the steady state of a complete corpus (11.4,
`DECISIONS.md` Decision 12), and it is still emitted as an empty member of `gaps.json`: a
consumer that treats absence as equivalent to emptiness breaks silently on the day it
fills, and `api/answer-engine` 9.6 depends on it being the sole resolver of a canonical
device id.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from conftest import REPO_ROOT
from dawmans.corpus.discover import SourceIdentity
from dawmans.corpus.rig import RIG_FILE, Rig, RigDevice, RigError, gap_reports, load_rig
from dawmans.records import AUTHORED_SOURCE_ID, HardwareApplicability, SourceRecord

RIG_YAML = """
devices:
  - id: ableton/live-12
    display_name: Ableton Live 12 Standard
    revision: "12 Standard"
  - id: akai/apc-key-25
    display_name: Akai APC Key 25 mk2
    revision: mk2
  - id: alesis/nitro-max
    display_name: Alesis Nitro Max
  - id: focusrite/scarlett-solo
    display_name: Focusrite Scarlett Solo 4th Gen
    revision: 4th-gen

source_applicability:
  ableton/live-12: {device: ableton/live-12, revision: "12 Standard", status: confirmed}
  focusrite/scarlett-solo-4g:
    {device: focusrite/scarlett-solo, revision: 4th-gen, status: confirmed}
"""


def manual(source_id: str, *, applicability: HardwareApplicability | None = None) -> SourceRecord:
    """A `vendor-manual` record as `PdfLoader` hands it over.

    The default applicability is 11.2's: `assumed` for the product named in the filename,
    never `confirmed`, and never inferred from content. `rig.py` is what replaces it.
    """
    vendor, product = source_id.split("/")
    identity = SourceIdentity(
        vendor=vendor, product=product, doctype="user-guide", doc_version="1.0", lang="en"
    )
    return SourceRecord(
        kind="vendor-manual",
        source_id=source_id,
        vendor=vendor,
        product=product,
        doctype="user-guide",
        lang="en",
        doc_version="1.0",
        display_name=identity.display_name,
        hardware_applicability=applicability
        or HardwareApplicability(status="assumed", device=source_id),
        page_count=24,
        ingested_at="2026-08-15T10:00:00+00:00",
        chunk_count=12,
        low_text=False,
    )


def authored() -> SourceRecord:
    return SourceRecord(
        kind="authored-triage",
        source_id=AUTHORED_SOURCE_ID,
        display_name="Studio triage notes",
        hardware_applicability=HardwareApplicability(status="assumed"),
        ingested_at="2026-08-15T10:00:00+00:00",
        chunk_count=4,
    )


def written(tmp_path: Path, text: str = RIG_YAML) -> Rig:
    path = tmp_path / RIG_FILE
    path.write_text(text, encoding="utf-8")
    return load_rig(path)


def indexed(rig: Rig, *records: SourceRecord) -> list[SourceRecord]:
    """What the run holds after `rig.py` has resolved each record's applicability."""
    return [rig.applied(record) for record in records]


CORPUS = (
    "ableton/live-12",
    "akai/apc-key-25",
    "alesis/nitro-max",
    "focusrite/scarlett-solo-4g",
)


# --- The declared inventory (11.1-11.3) ----------------------------------------------------


def test_the_rig_is_read_from_its_own_file_and_never_derived_from_the_corpus(
    tmp_path: Path,
) -> None:
    """11.3: what is documented is not evidence of what is owned.

    The four devices come from `rig.yaml` alone. Nothing in this module reads `manuals/`,
    and the record list below names a device the rig does not hold without adding it.
    """
    rig = written(tmp_path)

    assert rig.device_ids == {
        "ableton/live-12",
        "akai/apc-key-25",
        "alesis/nitro-max",
        "focusrite/scarlett-solo",
    }

    gaps = gap_reports(rig, indexed(rig, manual("behringer/umc-22")))

    assert rig.device_ids == {
        "ableton/live-12",
        "akai/apc-key-25",
        "alesis/nitro-max",
        "focusrite/scarlett-solo",
    }
    assert "behringer/umc-22" not in {device.id for device in gaps.owned_but_undocumented}


def test_device_ids_take_the_same_shape_as_a_source_id(tmp_path: Path) -> None:
    """Exact matching, never fuzzy: both sides are `<vendor>/<product>` (design §Rig
    inventory). A device id that is not is a declaration error, not something to normalise."""
    rig = written(tmp_path)

    assert all(device.id.count("/") == 1 for device in rig.devices)

    with pytest.raises(RigError, match="<vendor>/<product>"):
        written(tmp_path, "devices:\n  - id: nitro max\n    display_name: Alesis Nitro Max\n")


def test_a_rig_display_name_names_the_device_and_not_the_document(tmp_path: Path) -> None:
    """`rig.yaml`'s `display_name` is the unit the owner holds; `SourceRecord.display_name`
    is the document, derived from the filename. `Ableton Live 12 Standard` against
    `Ableton Live 12` is not a conflict, and neither overwrites the other."""
    rig = written(tmp_path)
    record = rig.applied(manual("ableton/live-12"))

    assert rig.device("ableton/live-12").display_name == "Ableton Live 12 Standard"
    assert record.display_name == "Ableton Live 12"


def test_a_missing_rig_file_is_an_empty_inventory_rather_than_a_crash(tmp_path: Path) -> None:
    """No `rig.yaml` means nothing is declared owned, so there is no gap to report. It is
    not a rejection and not a failure: no source is at fault."""
    rig = load_rig(tmp_path / RIG_FILE)

    assert rig.devices == ()
    assert gap_reports(rig, indexed(rig, manual("akai/apc-key-25"))).owned_but_undocumented == ()


def test_a_rig_declaring_one_device_twice_is_refused(tmp_path: Path) -> None:
    """Two entries under one id would make the revision comparison depend on which was read
    last, and the wrong-revision citation is the failure §11 exists to prevent."""
    with pytest.raises(RigError, match="akai/apc-key-25"):
        written(
            tmp_path,
            "devices:\n"
            "  - id: akai/apc-key-25\n    display_name: Akai APC Key 25\n    revision: mk1\n"
            "  - id: akai/apc-key-25\n    display_name: Akai APC Key 25 mk2\n    revision: mk2\n",
        )


# --- Applicability resolution (11.1, 11.2) -------------------------------------------------


def test_an_undeclared_source_is_assumed_for_the_product_in_its_filename(tmp_path: Path) -> None:
    """11.2, both halves: the fallback device is the filename's product, and the status is
    `assumed`. An undeclared source is unverified, not verified."""
    rig = written(tmp_path)
    record = rig.applied(manual("akai/apc-key-25"))

    assert record.hardware_applicability == HardwareApplicability(
        status="assumed", device="akai/apc-key-25"
    )


def test_nothing_is_ever_confirmed_by_default(tmp_path: Path) -> None:
    """Across the whole corpus, `confirmed` appears exactly where `rig.yaml` declares it."""
    rig = written(tmp_path)
    records = indexed(rig, *(manual(source_id) for source_id in CORPUS))

    confirmed = {r.source_id for r in records if r.hardware_applicability.status == "confirmed"}

    assert confirmed == {"ableton/live-12", "focusrite/scarlett-solo-4g"}


def test_a_declaration_maps_a_source_onto_a_device_its_filename_does_not_name(
    tmp_path: Path,
) -> None:
    """The Focusrite is the worked case for 11.7. The filename's product carries the
    generation marker and the rig's device id does not, so 11.2's default would resolve the
    source to a device that does not exist in the inventory."""
    rig = written(tmp_path)
    record = rig.applied(manual("focusrite/scarlett-solo-4g"))

    assert record.hardware_applicability == HardwareApplicability(
        status="confirmed", device="focusrite/scarlett-solo", revision="4th-gen"
    )


def test_applicability_is_never_read_out_of_the_document(tmp_path: Path) -> None:
    """11.2 and CONTRACTS §5: the value is declared or defaulted, and there is no third
    route. Two records differing only in their content resolve identically."""
    rig = written(tmp_path)
    first = rig.applied(manual("alesis/nitro-max"))
    second = rig.applied(manual("alesis/nitro-max"))

    assert first.hardware_applicability == second.hardware_applicability


def test_the_authored_source_stays_assumed_and_rig_yaml_cannot_set_it(tmp_path: Path) -> None:
    """CONTRACTS §1 fixes the authored store's source-level applicability at `assumed` with
    no device: the store is not about one device, and an entry's declared devices are
    passage-level data this spec neither reads nor derives.

    A `source_applicability` entry keyed on the authored source is therefore refused at
    parse time rather than ignored — silently dropping a declaration leaves the author
    believing it took effect.
    """
    rig = written(tmp_path)
    record = rig.applied(authored())

    assert record.hardware_applicability == HardwareApplicability(status="assumed")

    with pytest.raises(RigError, match=AUTHORED_SOURCE_ID):
        written(
            tmp_path,
            "devices: []\n"
            f"source_applicability:\n"
            f"  {AUTHORED_SOURCE_ID}: "
            "{device: akai/apc-key-25, status: confirmed}\n",
        )


def test_a_declaration_without_a_device_is_refused(tmp_path: Path) -> None:
    """A declaration exists to name the device a source documents. Without one there is
    nothing to join on, and the default it displaces was at least a device id."""
    with pytest.raises(RigError, match="device"):
        written(
            tmp_path,
            "devices: []\nsource_applicability:\n  akai/apc-key-25: {status: confirmed}\n",
        )


# --- owned-but-undocumented (11.4) ---------------------------------------------------------


def test_owned_but_undocumented_is_empty_against_the_real_rig(tmp_path: Path) -> None:
    """11.4's live state: every device in the rig has an indexed source since the Scarlett
    Solo 4th Gen guide was obtained. The empty report is the corpus being complete, not the
    check failing to run — which is why the next test exercises the populated path."""
    rig = written(tmp_path)
    gaps = gap_reports(rig, indexed(rig, *(manual(source_id) for source_id in CORPUS)))

    assert gaps.owned_but_undocumented == ()


def test_a_device_with_no_indexed_source_is_reported_with_its_rig_display_name(
    tmp_path: Path,
) -> None:
    """The populated path, against a fixture rig — the real corpus can no longer produce it.

    `api/answer-engine` resolves a model's free-form `@device` name against this report and
    substitutes the canonical id and the rig display name, so both have to be on the entry.
    """
    rig = written(
        tmp_path,
        "devices:\n"
        "  - id: akai/apc-key-25\n    display_name: Akai APC Key 25 mk2\n    revision: mk2\n"
        "  - id: elektron/digitakt\n    display_name: Elektron Digitakt II\n    revision: ii\n",
    )
    gaps = gap_reports(rig, indexed(rig, manual("akai/apc-key-25")))

    assert gaps.owned_but_undocumented == (
        RigDevice(id="elektron/digitakt", display_name="Elektron Digitakt II", revision="ii"),
    )


def test_owned_but_undocumented_joins_on_the_declared_device(tmp_path: Path) -> None:
    """Both reports compute over `source_applicability.device`, never over `source_id`. On
    a join by source id the Scarlett's manual documents `focusrite/scarlett-solo-4g`, the
    rig holds `focusrite/scarlett-solo`, and the device is reported undocumented with its
    guide sitting in `manuals/`."""
    rig = written(tmp_path)
    gaps = gap_reports(rig, indexed(rig, manual("focusrite/scarlett-solo-4g")))

    assert "focusrite/scarlett-solo" not in {device.id for device in gaps.owned_but_undocumented}


def test_an_authored_source_never_makes_a_device_look_documented(tmp_path: Path) -> None:
    """The exclusion has no live instance and is load-bearing: it is what keeps the report
    honest the moment a device is declared in `rig.yaml` ahead of its manual. A triage entry
    naming that device must not close the gap, which is the case CONTRACTS §5 and
    `api/answer-engine` 9.6 both rest on."""
    rig = written(
        tmp_path,
        "devices:\n  - id: elektron/digitakt\n    display_name: Elektron Digitakt II\n",
    )
    gaps = gap_reports(rig, indexed(rig, authored()))

    assert [device.id for device in gaps.owned_but_undocumented] == ["elektron/digitakt"]


# --- documented-but-unconfirmed (11.5) -----------------------------------------------------


def test_an_assumed_source_for_an_owned_device_is_unconfirmed(tmp_path: Path) -> None:
    """11.5's first arm, and the live instance: the APC guide is Manual Version 1.0
    describing the original unit, the rig holds an mk2, and nothing declares otherwise."""
    rig = written(tmp_path)
    gaps = gap_reports(rig, indexed(rig, *(manual(source_id) for source_id in CORPUS)))

    unconfirmed = {entry.source_id for entry in gaps.documented_but_unconfirmed}

    assert "akai/apc-key-25" in unconfirmed
    assert "ableton/live-12" not in unconfirmed
    assert "focusrite/scarlett-solo-4g" not in unconfirmed


def test_a_confirmed_source_whose_revision_differs_is_still_unconfirmed(tmp_path: Path) -> None:
    """11.5's second arm. `confirmed` says the declaration was checked, not that it matches
    the unit owned, and a confidently cited procedure for the wrong revision is this
    product's worst failure mode (CONTRACTS §5)."""
    rig = written(
        tmp_path,
        "devices:\n"
        "  - id: akai/apc-key-25\n    display_name: Akai APC Key 25 mk2\n    revision: mk2\n"
        "source_applicability:\n"
        "  akai/apc-key-25: {device: akai/apc-key-25, revision: mk1, status: confirmed}\n",
    )
    (entry,) = gap_reports(rig, indexed(rig, manual("akai/apc-key-25"))).documented_but_unconfirmed

    assert entry.source_id == "akai/apc-key-25"
    assert (entry.declared_revision, entry.owned_revision) == ("mk1", "mk2")


def test_revision_comparison_is_casefold_and_strip(tmp_path: Path) -> None:
    """`4th-Gen ` and `4th-gen` are one revision. Anything beyond case and surrounding
    whitespace is a genuine difference and is reported."""
    rig = written(
        tmp_path,
        "devices:\n"
        "  - id: focusrite/scarlett-solo\n"
        "    display_name: Scarlett Solo\n"
        '    revision: " 4th-Gen "\n'
        "source_applicability:\n"
        "  focusrite/scarlett-solo-4g:\n"
        "    {device: focusrite/scarlett-solo, revision: 4th-gen, status: confirmed}\n",
    )
    gaps = gap_reports(rig, indexed(rig, manual("focusrite/scarlett-solo-4g")))

    assert gaps.documented_but_unconfirmed == ()


def test_a_device_declaring_no_revision_matches_a_source_declaring_none(tmp_path: Path) -> None:
    """The Nitro Max case: no revision marker is printed on the unit, so none is declared.
    An absent revision on both sides is agreement, not a difference — otherwise every
    unmarked device reports against every manual for it."""
    rig = written(
        tmp_path,
        "devices:\n  - id: alesis/nitro-max\n    display_name: Alesis Nitro Max\n"
        "source_applicability:\n"
        "  alesis/nitro-max: {device: alesis/nitro-max, status: confirmed}\n",
    )
    gaps = gap_reports(rig, indexed(rig, manual("alesis/nitro-max")))

    assert gaps.documented_but_unconfirmed == ()


def test_documented_but_unconfirmed_is_restricted_to_devices_in_the_rig(tmp_path: Path) -> None:
    """11.5's own qualifier, and it is what keeps the report meaning anything. Without it
    every undeclared source is reported, including manuals for gear the owner does not hold
    — which is legitimate and is the third report's business, not this one's."""
    rig = written(
        tmp_path,
        "devices:\n  - id: akai/apc-key-25\n    display_name: Akai APC Key 25 mk2\n",
    )
    gaps = gap_reports(rig, indexed(rig, manual("behringer/umc-22")))

    assert gaps.documented_but_unconfirmed == ()
    assert [source_id for source_id in gaps.indexed_but_not_owned] == ["behringer/umc-22"]


def test_the_authored_source_is_never_documented_but_unconfirmed(tmp_path: Path) -> None:
    """Its applicability carries no device, so it is in no rig inventory. The status being
    `assumed` is CONTRACTS §1's fixed value rather than a missing declaration, and reporting
    it would ask the owner to confirm something the store cannot state."""
    rig = written(tmp_path)
    gaps = gap_reports(rig, indexed(rig, authored()))

    assert gaps.documented_but_unconfirmed == ()


# --- indexed-but-not-owned (11.7) ----------------------------------------------------------


def test_indexed_but_not_owned_is_empty_against_the_real_rig(tmp_path: Path) -> None:
    rig = written(tmp_path)
    gaps = gap_reports(rig, indexed(rig, *(manual(source_id) for source_id in CORPUS)))

    assert gaps.indexed_but_not_owned == ()


def test_an_undeclared_generation_marker_shows_on_both_reports_at_once(tmp_path: Path) -> None:
    """The diagnostic pairing, and the only thing on either report that separates a missing
    declaration from a genuine gap (Decision 9).

    Drop the Focusrite mapping and the source falls back to 11.2's default device
    `focusrite/scarlett-solo-4g`, which no rig entry holds. The device it documents is then
    reported owned-but-undocumented while its manual is sitting in `manuals/`, and the
    source itself is reported indexed-but-not-owned. A genuine gap produces the first alone;
    a genuinely unowned manual produces the second alone.
    """
    rig = written(tmp_path, RIG_YAML.replace("focusrite/scarlett-solo-4g:", "unused/nothing:"))
    gaps = gap_reports(rig, indexed(rig, *(manual(source_id) for source_id in CORPUS)))

    assert "focusrite/scarlett-solo" in {device.id for device in gaps.owned_but_undocumented}
    assert "focusrite/scarlett-solo-4g" in gaps.indexed_but_not_owned


def test_indexed_but_not_owned_is_not_an_error(tmp_path: Path) -> None:
    """Holding a manual for gear the owner does not own is legitimate — a borrowed unit, a
    device sold on, a manual obtained ahead of the hardware. 11.7 makes it a report line and
    never a rejection, so the reports are still computed and nothing raises."""
    rig = written(tmp_path)
    gaps = gap_reports(rig, indexed(rig, manual("behringer/umc-22")))

    assert gaps.indexed_but_not_owned == ("behringer/umc-22",)
    assert gaps.owned_but_undocumented != ()  # the real rig's four, all undocumented here


def test_the_authored_source_is_never_indexed_but_not_owned(tmp_path: Path) -> None:
    """11.7 names `vendor-manual` sources. The authored store documents no device, so its
    absence from the rig says nothing."""
    rig = written(tmp_path)
    gaps = gap_reports(rig, indexed(rig, authored()))

    assert gaps.indexed_but_not_owned == ()


# --- gaps.json (11.6) ----------------------------------------------------------------------


def test_gaps_json_carries_both_members_even_when_empty(tmp_path: Path) -> None:
    """11.4 states it outright and `api/answer-engine` 9.6 depends on it: an empty report is
    emitted as an empty list rather than omitted. A consumer that distinguishes absent from
    empty breaks on the day it fills, and this is the sole resolver of a canonical device id.
    """
    rig = written(tmp_path)
    payload = gap_reports(rig, indexed(rig, *(manual(s) for s in CORPUS))).to_dict()

    assert set(payload) == {"owned_but_undocumented", "documented_but_unconfirmed"}
    assert payload["owned_but_undocumented"] == []
    assert payload["documented_but_unconfirmed"] != []


def test_gaps_json_never_carries_the_third_report(tmp_path: Path) -> None:
    """CONTRACTS §5 governs two reports with named consumers. indexed-but-not-owned is an
    ingestion-time diagnostic for whoever maintains `rig.yaml`, and that reader is looking
    at the run report; adding a third member would oblige two other specs to render
    something neither has a use for (Decision 9)."""
    rig = written(tmp_path)
    gaps = gap_reports(rig, indexed(rig, manual("behringer/umc-22")))

    assert gaps.indexed_but_not_owned == ("behringer/umc-22",)
    assert "indexed_but_not_owned" not in gaps.to_dict()
    assert "behringer/umc-22" not in str(gaps.to_dict())


def test_gaps_json_carries_the_canonical_id_and_the_rig_display_name(tmp_path: Path) -> None:
    """What `api/answer-engine` 2.10 substitutes a free-form `@device` name for."""
    rig = written(
        tmp_path,
        "devices:\n  - id: elektron/digitakt\n    display_name: Elektron Digitakt II\n"
        "    revision: ii\n",
    )
    payload = gap_reports(rig, []).to_dict()

    assert payload["owned_but_undocumented"] == [
        {"id": "elektron/digitakt", "display_name": "Elektron Digitakt II", "revision": "ii"}
    ]


# --- The committed rig.yaml ----------------------------------------------------------------


def test_the_committed_rig_declares_the_four_devices_and_the_focusrite_mapping() -> None:
    """`rig.yaml` is hand-maintained and committed, unlike the PDFs. The Focusrite mapping
    is mandatory rather than optional (11.7, Decision 9): omit it and the manual is present
    while its device reports as undocumented."""
    rig = load_rig(REPO_ROOT / RIG_FILE)

    assert rig.device_ids == {
        "ableton/live-12",
        "akai/apc-key-25",
        "alesis/nitro-max",
        "focusrite/scarlett-solo",
    }
    assert rig.source_applicability["focusrite/scarlett-solo-4g"] == HardwareApplicability(
        status="confirmed", device="focusrite/scarlett-solo", revision="4th-gen"
    )


def test_the_committed_rig_reports_the_gaps_the_spec_states() -> None:
    """The live state of §11 against the real corpus: nothing owned-but-undocumented,
    nothing indexed-but-not-owned, and the APC guide unconfirmed.

    The Nitro Max is reported alongside the APC. It is undeclared, so 11.2 defaults it to
    `assumed`, and 11.5's first arm fires on `assumed` for a device in the rig regardless of
    whether the revisions agree. The design's worked example lists two `source_applicability`
    entries and names only the APC; that sentence is a defect, recorded as Decision 16 —
    reporting the Nitro Max is what 11.5 asks for, and declaring it `confirmed` on the
    owner's behalf is the inference 11.2 forbids.
    """
    rig = load_rig(REPO_ROOT / RIG_FILE)
    gaps = gap_reports(rig, indexed(rig, *(manual(source_id) for source_id in CORPUS)))

    assert gaps.owned_but_undocumented == ()
    assert gaps.indexed_but_not_owned == ()
    assert [entry.source_id for entry in gaps.documented_but_unconfirmed] == [
        "akai/apc-key-25",
        "alesis/nitro-max",
    ]
