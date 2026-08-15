"""`dawmans ingest`, `dawmans validate`, `dawmans inventory` — and the run orchestration.

The run is the design's §Stages in order, and three of those orderings are load-bearing
rather than incidental:

- **Superseded views are collected first**, not at the end of the run that superseded
  them, so a reader still working from the previous manifest keeps its files until then.
- **The embedding model is loaded once, before any source is iterated.** The cold load is
  7.2 s and 8.4 allows 10 s for a new ≤50-page source; loading per source would spend the
  budget on a constant.
- **The authored load runs after every vendor shard commits.** `TriageLoader` resolves each
  fix pointer against a vendor passage and sets `unbacked` from the result, so loading it
  earlier resolves pointers against the *previous* run's text — flagging entries whose
  targets this run repaired, and missing the ones it broke.

Everything from `Region` onwards is one code path for both kinds. There is no `if kind ==`
here beyond the two the records themselves carry, and that is 12.2: an authored source is
chunked, embedded, sharded and inventoried by the same calls a manual is.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Protocol

from dawmans.corpus.chunk import Chunk, chunk_source
from dawmans.corpus.discover import (
    Discovered,
    StoreScan,
    discover_stores,
    read_shard_metas,
    remove_absent_sources,
    slug,
)
from dawmans.corpus.loader import LoadResult
from dawmans.corpus.pdf.loader import PdfLoader
from dawmans.corpus.rig import RIG_FILE, GapReports, Rig, gap_reports, load_rig
from dawmans.index.build import (
    CacheKey,
    Shard,
    build_shard,
    collect_views,
    commit_view,
    read_shard,
    read_shards,
    shard_paths,
)
from dawmans.index.embed import Embedder, load_embedder
from dawmans.index.manifest import IndexVersionMismatch, Manifest, read_manifest
from dawmans.records import SourceRecord
from dawmans.report import (
    Failure,
    RunReport,
    SourceOutcome,
    StoreAnomaly,
    inventory_lines,
    read_audit,
    write_audit,
)

#: `index/` beside `manuals/` at the repository root. Gitignored and derived: 8.6 rebuilds
#: all of it from the two stores with no other input.
INDEX_DIR = "index"
MANUALS_DIR = "manuals"


class Store(Protocol):
    """What the run needs of a loader, which is more than the seam's `SourceLoader`.

    `scan()` rather than `discover()`, because the run has to report what a store rejected
    by name (1.5) and has to distinguish an **unavailable** store from an empty one: an
    absent or unreadable store is an unknown discovery set and removes nothing, while an
    existing empty one removes its shards (1.4). `discover()` alone flattens both away.
    """

    def scan(self) -> StoreScan: ...

    def load(self, d: Discovered) -> LoadResult: ...


@dataclass(frozen=True)
class RunResult:
    """One ingestion run: what to print, and what it committed."""

    report: RunReport
    #: None where the run committed no view — the merge itself failed.
    manifest: Manifest | None = None
    gaps: GapReports = field(default_factory=GapReports)

    @property
    def exit_code(self) -> int:
        return self.report.exit_code


def ingest(
    index_root: Path,
    *,
    vendor: Store,
    authored: Store | None = None,
    embedder: Embedder,
    rig: Rig | None = None,
    built_at: str | None = None,
) -> RunResult:
    """Run every stage, in the one order the design allows, and report what happened.

    `vendor` and `authored` are separate parameters rather than a list because their order
    is a constraint and not a convention: the authored load must see this run's committed
    vendor shards. A list would make that order a property of how the caller happened to
    write it down.
    """
    rig = rig if rig is not None else Rig()

    collect_views(index_root)  # before anything is built, never after

    scans = [vendor.scan()]
    if authored is not None:
        scans.append(authored.scan())
    scans = list(discover_stores(scans))
    remove_absent_sources(scans, index_root)

    outcomes: list[SourceOutcome] = []
    failures: list[Failure] = []
    # (loader, scan, always_load). The authored store is exempt from fingerprint-based
    # skipping — `data/symptom-triage` §Discovery: its validity is a function of the
    # *manuals* as well as its own text, so a fingerprint over its own bytes cannot say
    # whether a pointer still resolves. Skipping it would leave `unbacked` describing the
    # run before last. The flag is passed rather than tested on `source_id` so the
    # exemption is a property of the store, not of a constant.
    stores: list[tuple[Store, StoreScan, bool]] = [(vendor, scans[0], False)]
    if authored is not None:
        stores.append((authored, scans[1], True))

    for loader, scan, always_load in stores:
        outcomes += [SourceOutcome.of(r, store=scan.store) for r in scan.rejections]
        for discovered in scan.sources:
            outcome, failure = _ingest_source(
                index_root,
                loader=loader,
                discovered=discovered,
                store=scan.store,
                embedder=embedder,
                always_load=always_load,
            )
            if outcome is not None:
                outcomes.append(outcome)
            if failure is not None:
                failures.append(failure)

    # The rig is applied **here**, at the merge, and not when a shard is built. A
    # `rig.yaml` edit changes no source byte, so every shard is reused and no loader runs —
    # applied at build time, a new `source_applicability` declaration would not reach the
    # index until something unrelated happened to change the manual. The shard keeps the
    # loader's own 11.2 default and the view carries the joined value, which is also the
    # honest split: the shard is what the *document* said, `rig.yaml` is what the *owner*
    # says, and only the second is a declaration this run can act on.
    shards = [replace(shard, record=rig.applied(shard.record)) for shard in read_shards(index_root)]
    gaps = gap_reports(rig, [shard.record for shard in shards])
    manifest: Manifest | None = None
    try:
        manifest = commit_view(
            index_root,
            shards=shards,
            embedding=embedder.descriptor,
            built_at=built_at,
            gaps=gaps.to_dict(),
        )
    except Exception as error:  # noqa: BLE001 — one failure line beats a traceback
        failures.append(Failure(message=f"the merge failed: {error}"))

    report = RunReport(
        outcomes=tuple(outcomes),
        failures=tuple(failures),
        anomalies=_anomalies(scans, index_root),
        unavailable_stores=tuple(scan.store for scan in scans if not scan.available),
        indexed_but_not_owned=gaps.indexed_but_not_owned,
    )
    return RunResult(report=report, manifest=manifest, gaps=gaps)


def _ingest_source(
    index_root: Path,
    *,
    loader: Store,
    discovered: Discovered,
    store: str,
    embedder: Embedder,
    always_load: bool = False,
) -> tuple[SourceOutcome | None, Failure | None]:
    """One source, from its shard cache key to its committed shard or its rejection.

    A **failure** here costs this source and nothing else: its previous shard is left
    intact, the reason is collected, and the caller moves to the next source. There is no
    abort-on-first-failure path (1.7).

    `always_load` runs the loader whatever the cache key says. It costs nothing where it is
    used: the per-`passage_id` vector map in the authored shard's meta already removes the
    embedding cost for every entry whose text did not change, so an unchanged store is
    re-parsed and re-resolved but not re-embedded.
    """
    name = slug(discovered.source_id)
    try:
        existing = read_shard(index_root, name)
        if not always_load and _reusable(existing, discovered, embedder):
            # The audit is deliberately **not** rewritten: it describes the run that
            # produced the shard, and restamping it would make the diagnostics claim a
            # measurement this run never took.
            return SourceOutcome(
                source_id=discovered.source_id, store=store, outcome="skipped"
            ), None

        result = loader.load(discovered)
        write_audit(index_root, discovered.source_id, result.audit, rejection=result.rejection)

        if result.rejection is not None:
            # 1.6's "exclude that source from the index" is the shard going, not merely a
            # line in the report. Left in place, a store whose every entry has become
            # malformed keeps serving the previous run's passages while the run reports
            # the rejection and succeeds.
            _drop_shard(index_root, name)
            return (
                SourceOutcome(
                    source_id=discovered.source_id,
                    store=store,
                    outcome="rejected",
                    rejection=result.rejection,
                    origin=discovered.origin,
                ),
                None,
            )

        # Not `rig.applied(...)`: the shard records what the *document* said (11.2's
        # default), and the merge joins it against `rig.yaml`. See `ingest`.
        record = result.record
        chunks = chunk_source(record, result.regions)
        _check_pages(record, chunks)
        build_shard(
            index_root,
            record=record,
            chunks=chunks,
            store=store,
            fingerprint=discovered.fingerprint,
            embedder=embedder,
            sidecar=result.sidecar,
            previous=existing,
        )
    except Exception as error:  # noqa: BLE001 — 1.7: any other reason is a failure
        return None, Failure(source_id=discovered.source_id, message=str(error) or repr(error))

    return SourceOutcome(source_id=discovered.source_id, store=store, outcome="ingested"), None


def _reusable(shard: Shard | None, discovered: Discovered, embedder: Embedder) -> bool:
    """Whether this run can skip the source entirely (8.3, 9.3).

    All four cache-key components, not just the fingerprint: a fixed ingestion bug or a
    changed embedding model alters no byte of the PDF and must still reach the index.
    """
    return shard is not None and shard.reusable(CacheKey.of(discovered.fingerprint, embedder))


def _drop_shard(index_root: Path, name: str) -> None:
    """Delete a rejected source's shard, and keep its audit.

    The audit stays because it is the only record of *why* the source was excluded, and a
    rejection is exactly the moment someone comes looking for it. The shard goes because
    1.6's "exclude that source from the index" is the passages going, not merely a line in
    the report.
    """
    paths = shard_paths(index_root, name)
    for path in (paths.passages, paths.vectors, paths.sidecar, paths.meta):
        path.unlink(missing_ok=True)


def _check_pages(record: SourceRecord, chunks: Sequence[Chunk]) -> None:
    """6.11, as a **failure** rather than a rejection (design §Error Handling).

    6.11 says to reject the source; 1.6's closed list does not admit the reason, and
    rejection is the wrong outcome anyway — it discards a 1009-page primary source over one
    mis-anchored chunk while reporting the run as succeeded. As a failure it keeps the
    previous shard, names the chunk and the page, and exits non-zero. Skipped entirely for
    a pageless source (12.8).
    """
    if record.page_count is None:
        return
    for chunk in chunks:
        for page in (chunk.passage.page_start, chunk.passage.page_end):
            if page is not None and not 1 <= page <= record.page_count:
                raise ValueError(
                    f"chunk {chunk.passage.passage_id} is anchored to page {page}, outside "
                    f"{record.source_id}'s pages 1-{record.page_count} (6.11)"
                )


def _anomalies(scans: Sequence[StoreScan], index_root: Path) -> tuple[StoreAnomaly, ...]:
    """9.5, per store and in both directions.

    Per store, and scoped by the store recorded **on the shard**, so 9.5's "SHALL NOT test
    a source of one kind against the other kind's store" holds by construction rather than
    by remembering to filter.
    """
    indexed: dict[str, set[str]] = {}
    for meta in read_shard_metas(index_root):
        indexed.setdefault(meta.store, set()).add(meta.source_id)

    return tuple(
        StoreAnomaly(
            store=scan.store,
            in_store_not_indexed=tuple(sorted(scan.source_ids - indexed.get(scan.store, set()))),
            indexed_not_in_store=tuple(sorted(indexed.get(scan.store, set()) - scan.source_ids)),
        )
        for scan in scans
    )


# --- the commands -------------------------------------------------------------------------


def run_ingest(root: Path, *, index_root: Path | None = None) -> RunResult:
    """`dawmans ingest` over the real stores.

    The authored store is `data/symptom-triage`'s to supply; until that spec's loader
    exists there is one store, and the run is the same code either way (12.2).
    """
    index_root = index_root or root / INDEX_DIR
    return ingest(
        index_root,
        vendor=PdfLoader(root=root / MANUALS_DIR),
        embedder=load_embedder(),
        rig=load_rig(root / RIG_FILE),
    )


def run_validate(index_root: Path) -> tuple[int, list[str]]:
    """Read the committed index back the way `api/answer-engine` would, and say what breaks.

    A version mismatch is reported rather than interpreted: 8.11 requires a reader whose
    expected version differs to refuse to load, and the fix is a rebuild.
    """
    try:
        manifest = read_manifest(index_root)
    except IndexVersionMismatch as error:
        return 1, [f"{index_root}: {error}"]
    if manifest is None:
        return 1, [f"{index_root}: no manifest — nothing has been committed here"]

    view = index_root / manifest.view_dir
    missing = [
        name
        for name in ("passages.jsonl", "sources.json", "vectors.npy", "gaps.json", "lexical")
        if not (view / name).exists()
    ]
    if missing:
        return 1, [
            f"{manifest.view_dir}: {name} is named by the manifest and absent" for name in missing
        ]

    rows = sum(source.row_count for source in manifest.sources)
    return 0, [
        f"{manifest.view_dir}  {len(manifest.sources)} sources, {rows} passages",
        f"corpus_revision {manifest.corpus_revision}",
        f"embedding {manifest.embedding.model} ({manifest.embedding.dim})",
    ]


def run_inventory(index_root: Path) -> tuple[int, list[str]]:
    """9.1 over the committed view, with each source's 4.4 English ranges beside it."""
    try:
        manifest = read_manifest(index_root)
    except IndexVersionMismatch as error:
        return 1, [f"{index_root}: {error}"]
    if manifest is None:
        return 1, [f"{index_root}: no manifest — nothing has been committed here"]

    records = [shard.record for shard in read_shards(index_root)]
    audits = {
        record.source_id: audit
        for record in records
        if (audit := read_audit(index_root, record.source_id)) is not None
    }
    return 0, inventory_lines(records, audits=audits)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="dawmans", description=__doc__.splitlines()[0])
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="the repository root holding manuals/, rig.yaml and index/",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("ingest", help="ingest both stores and commit a view")
    commands.add_parser("validate", help="read the committed index back and report what breaks")
    commands.add_parser("inventory", help="report every indexed source (9.1)")

    args = parser.parse_args(argv)
    index_root = args.root / INDEX_DIR

    if args.command == "ingest":
        result = run_ingest(args.root)
        _print(result.report.lines())
        return result.exit_code

    code, lines = (run_validate if args.command == "validate" else run_inventory)(index_root)
    _print(lines)
    return code


def _print(lines: Iterable[str]) -> None:
    for line in lines:
        print(line)


__all__ = [
    "INDEX_DIR",
    "MANUALS_DIR",
    "RunResult",
    "Store",
    "ingest",
    "main",
    "run_ingest",
    "run_inventory",
    "run_validate",
]


if __name__ == "__main__":
    sys.exit(main())
