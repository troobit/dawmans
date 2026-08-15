"""Store scanning, fingerprints and removal — requirements 1.1-1.4, 9.2, 9.3, 9.5, 12.3.

The load-bearing test here is the one that distinguishes a **missing** store from an **empty**
one. Removal (1.4) deletes any shard whose `source_id` is not in the current discovery set for
that shard's own store; if an unreadable directory yielded an empty set instead of an unknown
one, an unmounted volume or a renamed folder would delete every authored passage in the index
and report the run as a success.

`data/symptom-triage` owns the authored entry store (12.3), so its scan is built by hand here
exactly as `TriageLoader` would return it. That is also what keeps 9.5 honest: removal is scoped
by the store recorded on the shard, so a source of one kind is never tested against the other
kind's store.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from dawmans.corpus.discover import (
    AUTHORED_STORE,
    MANUALS_STORE,
    StoreScan,
    discover_stores,
    fingerprint,
    fingerprint_changed,
    read_shard_metas,
    remove_absent_sources,
    scan_manuals,
    slug,
)
from dawmans.corpus.loader import Discovered
from dawmans.records import AUTHORED_SOURCE_ID

SHARD_ARTEFACTS = (".passages.jsonl", ".vectors.npy", ".sidecar.json", ".meta.json")


def write_pdf(store: Path, name: str, body: bytes = b"%PDF-1.7\n") -> Path:
    store.mkdir(parents=True, exist_ok=True)
    path = store / name
    path.write_bytes(body)
    return path


def write_shard(index_root: Path, source_id: str, store: str, digest: str = "sha256:old") -> Path:
    """A committed shard, its sidecar and its ingestion audit, as index/build.py leaves them."""
    shards = index_root / "shards"
    audits = index_root / "audits"
    shards.mkdir(parents=True, exist_ok=True)
    audits.mkdir(parents=True, exist_ok=True)

    name = slug(source_id)
    for suffix in SHARD_ARTEFACTS:
        (shards / f"{name}{suffix}").write_text("{}")
    (shards / f"{name}.meta.json").write_text(
        json.dumps(
            {
                "source": {"source_id": source_id, "kind": "vendor-manual"},
                "store": store,
                "fingerprint": digest,
                "ingestion_version": 1,
                "row_count": 12,
            }
        )
    )
    (audits / f"{name}.json").write_text("{}")
    return shards / f"{name}.meta.json"


def shard_paths(index_root: Path, source_id: str) -> list[Path]:
    name = slug(source_id)
    return [index_root / "shards" / f"{name}{suffix}" for suffix in SHARD_ARTEFACTS] + [
        index_root / "audits" / f"{name}.json"
    ]


def authored_scan(*, available: bool = True, present: bool = True) -> StoreScan:
    """What `TriageLoader.discover()` returns — the store is one source, or none."""
    if not available:
        return StoreScan(store=AUTHORED_STORE, available=False)
    entries = Discovered(
        source_id=AUTHORED_SOURCE_ID,
        fingerprint="sha256:entries",
        origin=Path("triage"),
    )
    return StoreScan(store=AUTHORED_STORE, available=True, sources=(entries,) if present else ())


# --- Fingerprints (9.2, 9.3) ----------------------------------------------------------


def test_fingerprint_is_sha256_over_the_file_bytes(tmp_path: Path) -> None:
    body = b"%PDF-1.7\nthe whole document\n"
    path = write_pdf(tmp_path, "alesis_nitro-max_user-guide_v1.1_en.pdf", body)

    assert fingerprint(path) == f"sha256:{hashlib.sha256(body).hexdigest()}"


def test_the_same_bytes_under_two_names_fingerprint_alike(tmp_path: Path) -> None:
    body = b"%PDF-1.7\nidentical\n"
    first = write_pdf(tmp_path, "alesis_nitro-max_user-guide_v1.1_en.pdf", body)
    second = write_pdf(tmp_path, "alesis_nitro-max_user-guide_v1.2_en.pdf", body)

    assert fingerprint(first) == fingerprint(second)


def test_a_changed_file_marks_the_source_for_re_ingestion(tmp_path: Path) -> None:
    store = tmp_path / "manuals"
    write_pdf(store, "alesis_nitro-max_user-guide_v1.1_en.pdf", b"%PDF-1.7\nfirst\n")
    (before,) = scan_manuals(store).sources

    index_root = tmp_path / "index"
    write_shard(index_root, "alesis/nitro-max", MANUALS_STORE, digest=before.fingerprint)
    (meta,) = read_shard_metas(index_root)

    assert not fingerprint_changed(before, meta)

    write_pdf(store, "alesis_nitro-max_user-guide_v1.1_en.pdf", b"%PDF-1.7\nsecond\n")
    (after,) = scan_manuals(store).sources

    assert after.fingerprint != before.fingerprint
    assert fingerprint_changed(after, meta)


def test_a_source_with_no_shard_is_new_work(tmp_path: Path) -> None:
    store = tmp_path / "manuals"
    write_pdf(store, "alesis_nitro-max_user-guide_v1.1_en.pdf")
    (discovered,) = scan_manuals(store).sources

    # 1.2: a PDF not yet in the index is ingested on the next run with no further action.
    assert read_shard_metas(tmp_path / "index") == ()
    assert fingerprint_changed(discovered, None)


# --- A missing store is not an empty store (1.4) --------------------------------------


def test_an_absent_store_is_unavailable(tmp_path: Path) -> None:
    scan = scan_manuals(tmp_path / "manuals")

    assert not scan.available
    assert scan.sources == ()
    assert scan.rejections == ()


def test_a_store_that_is_not_a_directory_is_unavailable(tmp_path: Path) -> None:
    not_a_store = tmp_path / "manuals"
    not_a_store.write_text("this is a file")

    assert not scan_manuals(not_a_store).available


@pytest.mark.skipif(os.geteuid() == 0, reason="root reads a directory whatever its mode")
def test_an_unreadable_store_is_unavailable(tmp_path: Path) -> None:
    store = tmp_path / "manuals"
    write_pdf(store, "alesis_nitro-max_user-guide_v1.1_en.pdf")
    store.chmod(0o000)
    try:
        assert not scan_manuals(store).available
    finally:
        store.chmod(0o700)


def test_an_existing_empty_store_is_available_and_empty(tmp_path: Path) -> None:
    store = tmp_path / "manuals"
    store.mkdir()

    scan = scan_manuals(store)

    assert scan.available
    assert scan.source_ids == frozenset()


def test_an_unavailable_store_removes_no_shard(tmp_path: Path) -> None:
    index_root = tmp_path / "index"
    write_shard(index_root, "alesis/nitro-max", MANUALS_STORE)
    write_shard(index_root, AUTHORED_SOURCE_ID, AUTHORED_STORE)

    removed = remove_absent_sources(
        [scan_manuals(tmp_path / "manuals"), authored_scan(available=False)], index_root
    )

    assert removed == ()
    for source_id in ("alesis/nitro-max", AUTHORED_SOURCE_ID):
        assert all(path.exists() for path in shard_paths(index_root, source_id))


def test_an_empty_store_removes_its_shards(tmp_path: Path) -> None:
    store = tmp_path / "manuals"
    store.mkdir()
    index_root = tmp_path / "index"
    write_shard(index_root, "alesis/nitro-max", MANUALS_STORE)

    (removed,) = remove_absent_sources([scan_manuals(store)], index_root)

    assert removed.source_id == "alesis/nitro-max"
    assert removed.store == MANUALS_STORE


def test_removal_takes_the_shard_its_sidecar_and_its_audit(tmp_path: Path) -> None:
    store = tmp_path / "manuals"
    store.mkdir()
    index_root = tmp_path / "index"
    write_shard(index_root, "alesis/nitro-max", MANUALS_STORE)

    remove_absent_sources([scan_manuals(store)], index_root)

    # An audit whose shard is gone describes nothing, and a sidecar left behind would be
    # copied into the next view keyed to passages that no longer exist.
    assert not any(path.exists() for path in shard_paths(index_root, "alesis/nitro-max"))


def test_a_source_still_in_its_store_is_kept(tmp_path: Path) -> None:
    store = tmp_path / "manuals"
    write_pdf(store, "alesis_nitro-max_user-guide_v1.1_en.pdf")
    index_root = tmp_path / "index"
    write_shard(index_root, "alesis/nitro-max", MANUALS_STORE)

    assert remove_absent_sources([scan_manuals(store)], index_root) == ()
    assert all(path.exists() for path in shard_paths(index_root, "alesis/nitro-max"))


def test_a_rejected_source_is_removed_from_the_index(tmp_path: Path) -> None:
    # The file is present but 2.6 excludes it, so a shard standing under its ID would let an
    # answer cite a source this run refused to index.
    store = tmp_path / "manuals"
    write_pdf(store, "akai_apc-key-25_user-guide_v1.0_multi.pdf")
    write_pdf(store, "akai_apc-key-25_user-guide_v2.0_en.pdf")
    index_root = tmp_path / "index"
    write_shard(index_root, "akai/apc-key-25", MANUALS_STORE)

    (removed,) = remove_absent_sources([scan_manuals(store)], index_root)

    assert removed.source_id == "akai/apc-key-25"


# --- Removal is scoped by the shard's own store (9.5) ---------------------------------


def test_an_authored_shard_survives_an_empty_manuals_store(tmp_path: Path) -> None:
    store = tmp_path / "manuals"
    store.mkdir()
    index_root = tmp_path / "index"
    write_shard(index_root, AUTHORED_SOURCE_ID, AUTHORED_STORE)

    removed = remove_absent_sources([scan_manuals(store), authored_scan()], index_root)

    # An authored source is not an anomaly for being absent from manuals/.
    assert removed == ()
    assert all(path.exists() for path in shard_paths(index_root, AUTHORED_SOURCE_ID))


def test_a_vendor_shard_survives_an_empty_authored_store(tmp_path: Path) -> None:
    store = tmp_path / "manuals"
    write_pdf(store, "alesis_nitro-max_user-guide_v1.1_en.pdf")
    index_root = tmp_path / "index"
    write_shard(index_root, "alesis/nitro-max", MANUALS_STORE)

    removed = remove_absent_sources([scan_manuals(store), authored_scan(present=False)], index_root)

    assert removed == ()


def test_an_emptied_authored_store_removes_only_its_own_shard(tmp_path: Path) -> None:
    store = tmp_path / "manuals"
    write_pdf(store, "alesis_nitro-max_user-guide_v1.1_en.pdf")
    index_root = tmp_path / "index"
    write_shard(index_root, "alesis/nitro-max", MANUALS_STORE)
    write_shard(index_root, AUTHORED_SOURCE_ID, AUTHORED_STORE)

    (removed,) = remove_absent_sources(
        [scan_manuals(store), authored_scan(present=False)], index_root
    )

    assert removed.source_id == AUTHORED_SOURCE_ID
    assert all(path.exists() for path in shard_paths(index_root, "alesis/nitro-max"))


def test_a_shard_from_a_store_this_run_did_not_scan_is_kept(tmp_path: Path) -> None:
    store = tmp_path / "manuals"
    store.mkdir()
    index_root = tmp_path / "index"
    write_shard(index_root, AUTHORED_SOURCE_ID, AUTHORED_STORE)

    # The authored store was never scanned, so its set is unknown — the same rule as an
    # unreadable one, and for the same reason.
    assert remove_absent_sources([scan_manuals(store)], index_root) == ()


# --- Both stores in one run (1.1, 12.3) -----------------------------------------------


def test_discovery_finds_both_stores_in_one_run(tmp_path: Path) -> None:
    store = tmp_path / "manuals"
    write_pdf(store, "ableton_live-12_reference-manual_v12_en.pdf")
    write_pdf(store, "alesis_nitro-max_user-guide_v1.1_en.pdf")

    scans = discover_stores([scan_manuals(store), authored_scan()])

    assert {scan.store for scan in scans} == {MANUALS_STORE, AUTHORED_STORE}
    assert {d.source_id for scan in scans for d in scan.sources} == {
        "ableton/live-12",
        "alesis/nitro-max",
        AUTHORED_SOURCE_ID,
    }


def test_a_newly_added_manual_needs_no_code_or_configuration(tmp_path: Path) -> None:
    store = tmp_path / "manuals"
    write_pdf(store, "alesis_nitro-max_user-guide_v1.1_en.pdf")
    assert len(scan_manuals(store).sources) == 1

    # 1.1: no hard-coded list of expected sources, so a vendor and product never seen before
    # is discovered by the same scan.
    write_pdf(store, "arturia_keystep-37_user-manual_v3.2_multi.pdf")
    assert {d.source_id for d in scan_manuals(store).sources} == {
        "alesis/nitro-max",
        "arturia/keystep-37",
    }


def test_a_manual_claiming_the_authored_identity_rejects_both_stores(tmp_path: Path) -> None:
    store = tmp_path / "manuals"
    write_pdf(store, "authored_triage_notes_v1_en.pdf")

    scans = discover_stores([scan_manuals(store), authored_scan()])

    # The slug rule cannot see this: both stores form `authored_triage`, so the collision is
    # on `source_id` itself and 2.6 rejects it before any slug exists.
    assert all(scan.sources == () for scan in scans)
    reasons = {r.rejection.reason for scan in scans for r in scan.rejections}
    assert reasons == {"source-id-collision"}


def test_one_store_per_source_is_the_ordinary_case(tmp_path: Path) -> None:
    store = tmp_path / "manuals"
    write_pdf(store, "alesis_nitro-max_user-guide_v1.1_en.pdf")

    scans = discover_stores([scan_manuals(store), authored_scan()])

    assert all(scan.rejections == () for scan in scans)


def test_an_unavailable_store_survives_the_run_level_check(tmp_path: Path) -> None:
    scans = discover_stores([scan_manuals(tmp_path / "manuals"), authored_scan(available=False)])

    assert all(not scan.available for scan in scans)


# --- Shard metadata -------------------------------------------------------------------


def test_shard_metas_carry_the_source_id_store_and_fingerprint(tmp_path: Path) -> None:
    index_root = tmp_path / "index"
    write_shard(index_root, "alesis/nitro-max", MANUALS_STORE, digest="sha256:abc")

    (meta,) = read_shard_metas(index_root)

    assert meta.source_id == "alesis/nitro-max"
    assert meta.store == MANUALS_STORE
    assert meta.fingerprint == "sha256:abc"
    assert meta.slug == "alesis_nitro-max"


def test_an_absent_index_has_no_shards(tmp_path: Path) -> None:
    assert read_shard_metas(tmp_path / "index") == ()


def test_an_unreadable_shard_meta_is_left_alone(tmp_path: Path) -> None:
    store = tmp_path / "manuals"
    store.mkdir()
    index_root = tmp_path / "index"
    write_shard(index_root, "alesis/nitro-max", MANUALS_STORE)
    (index_root / "shards" / "alesis_nitro-max.meta.json").write_text("{not json")

    # A meta that cannot be read names no store and no source, so nothing here knows whether
    # its shard is stale. Deleting on a parse error would lose a source to a bug elsewhere.
    assert read_shard_metas(index_root) == ()
    assert remove_absent_sources([scan_manuals(store)], index_root) == ()
    assert (index_root / "shards" / "alesis_nitro-max.passages.jsonl").exists()
