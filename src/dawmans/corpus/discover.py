"""Both source stores: the 2.1 filename grammar, source identity, fingerprints.

Stage 1 of the run. It reads directories and nothing else: a source's bytes are hashed, but
no PDF is opened and no text is extracted until a source has an identity and has survived the
collision check.

The filename grammar (2.1-2.3) is a **published convention two other specs reproduce** (2.7).
`api/answer-engine` rebuilds the name from a `SourceRecord`'s own fields to serve the PDF behind
a citation's open-at-source action (CONTRACTS §3a), and again to assemble `required_manual` for a
device with no ingested source (CONTRACTS §4e). The expression below is therefore a bijection and
`doc_version` is captured **without** its leading `v`, so the inverse is exactly
`f"{vendor}_{product}_{doctype}_v{doc_version}_{lang}.pdf"` for every reader. Changing it is a
change to those consumers.

It applies to `vendor-manual` sources only (12.5). An `authored-triage` source is a store rather
than a document: its identity is the CONTRACTS §1 constant `authored/triage` and nothing here
parses it.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace
from pathlib import Path

from dawmans.corpus.loader import Discovered, Rejection

#: The store a `vendor-manual` is discovered in, recorded on its shard so that removal and the
#: 9.5 anomaly reports never test a source of one kind against the other kind's store.
MANUALS_STORE = "manuals"
#: The authored entry store, whose location and form `data/symptom-triage` owns (12.3).
AUTHORED_STORE = "triage"

#: Everything `index/build.py` commits for one source, all of it keyed by the same slug.
SHARD_SUFFIXES = (".passages.jsonl", ".vectors.npy", ".sidecar.json", ".meta.json")

#: What a rejected filename is reported against (2.5).
FILENAME_GRAMMAR = "<vendor>_<product>_<doctype>_v<version>_<lang>.pdf"

# Lowercase kebab-case, with no empty segment at either end and no doubled separator.
_KEBAB = "[a-z0-9]+(?:-[a-z0-9]+)*"

#: The grammar as one anchored expression. The `<version>` field is the deliberate exception to
#: kebab-case (2.2): vendors number manual revisions with full stops, and two of the reference
#: corpus's four sources do. Digits are `[0-9]` rather than `\d` so that a decimal digit from
#: another script cannot enter a name two other specs must rebuild byte for byte.
FILENAME_PATTERN = re.compile(
    "^(?P<vendor>" + _KEBAB + ")"
    "_(?P<product>" + _KEBAB + ")"
    "_(?P<doctype>" + _KEBAB + ")"
    r"_v(?P<doc_version>[0-9]+(?:\.[0-9]+)*)"
    r"_(?P<lang>[a-z]{2}|multi)\.pdf$"
)


@dataclass(frozen=True)
class SourceIdentity:
    """What a `vendor-manual`'s filename says it is (2.4)."""

    vendor: str
    product: str
    doctype: str
    #: Without the leading `v`, so `filename` below never produces `_vv1.0_` (2.7).
    doc_version: str
    lang: str

    @property
    def source_id(self) -> str:
        """`<vendor>/<product>`. The version is deliberately outside it, so replacing v12
        with v12.1 does not orphan an authored fix pointer (`data/symptom-triage` 8.3)."""
        return f"{self.vendor}/{self.product}"

    @property
    def display_name(self) -> str:
        """The title-cased vendor and product: `Ableton Live 12`.

        The version is **not** appended: `doc_version` is its own `SourceRecord` field and
        CONTRACTS §3 shows it inline on the citation, so folding it in renders it twice.
        """
        words = f"{self.vendor} {self.product}".replace("-", " ").split()
        return " ".join(word.title() for word in words)

    @property
    def filename(self) -> str:
        """The inverse of the grammar — the one reconstruction rule every consumer runs."""
        return f"{self.vendor}_{self.product}_{self.doctype}_v{self.doc_version}_{self.lang}.pdf"


def parse_filename(name: str) -> SourceIdentity | None:
    """The identity a name yields, or None where it does not match the convention (2.5).

    `name` is a bare filename: the expression is anchored at both ends, so a path does not
    match.
    """
    match = FILENAME_PATTERN.match(name)
    if match is None:
        return None
    return SourceIdentity(**match.groupdict())


def slug(source_id: str) -> str:
    """The on-disk name of a source's shard, its ingestion audit and its view sidecar.

    `/`->`_` and never `/`->`-`: the grammar forbids `_` inside `vendor` and `product` but
    allows `-`, so a hyphen would map `a/b-c` and `a-b/c` onto one shard. One rule covers both
    kinds — `authored/triage` gives `authored_triage`.
    """
    return source_id.replace("/", "_")


def fingerprint(path: Path) -> str:
    """sha256 over the file's bytes — the content fingerprint of 9.2.

    Read in blocks: the Live 12 manual is 96 MB of screenshots and there is no reason to hold
    it in memory to hash it.
    """
    with path.open("rb") as handle:
        digest = hashlib.file_digest(handle, "sha256")
    return f"sha256:{digest.hexdigest()}"


@dataclass(frozen=True)
class DiscoveryRejection:
    """One source excluded at discovery, for the run report (1.5, 1.6)."""

    origin: Path
    rejection: Rejection
    #: Absent where the name yielded no identity to name it by.
    source_id: str | None = None


@dataclass(frozen=True)
class StoreScan:
    """One store's discovery set for this run.

    **A missing store is not an empty store.** Where `available` is False the set is *unknown*:
    no shard from this store is removed and the run reports the store unavailable. Only a store
    that exists and holds no sources yields an empty set and therefore removes its shards.
    Without the distinction an unmounted volume deletes every authored passage and reports
    success.
    """

    store: str
    available: bool
    sources: tuple[Discovered, ...] = ()
    rejections: tuple[DiscoveryRejection, ...] = ()

    @property
    def source_ids(self) -> frozenset[str]:
        """The identities this store currently holds. A rejected source is not among them:
        it is excluded from the index, so a shard standing under its ID describes nothing the
        run is willing to cite."""
        return frozenset(d.source_id for d in self.sources)


def scan_manuals(root: Path) -> StoreScan:
    """Discover every `vendor-manual` in `manuals/` (1.1-1.3, 2.5, 2.6, 9.2)."""
    try:
        entries = sorted(path for path in root.iterdir() if path.is_file())
    except OSError:
        return StoreScan(store=MANUALS_STORE, available=False)

    identities: dict[Path, SourceIdentity] = {}
    rejections: list[DiscoveryRejection] = []
    for path in entries:
        if path.suffix.lower() != ".pdf":
            continue  # 1.3: skipped silently, and `manuals/README.md` is the standing case
        identity = parse_filename(path.name)
        if identity is None:
            rejections.append(
                DiscoveryRejection(
                    origin=path,
                    rejection=Rejection(
                        reason="filename-invalid",
                        detail=f"{path.name} does not match {FILENAME_GRAMMAR}",
                    ),
                )
            )
            continue
        identities[path] = identity

    # 2.6 is detected by grouping on `source_id` **before any work**: nothing is hashed, let
    # alone opened, on behalf of a source that is about to be rejected.
    by_source_id: dict[str, list[Path]] = {}
    for path, identity in identities.items():
        by_source_id.setdefault(identity.source_id, []).append(path)

    sources: list[Discovered] = []
    for source_id, paths in by_source_id.items():
        if len(paths) > 1:
            rejections.extend(_collision(source_id, paths))
            continue
        (path,) = paths
        sources.append(Discovered(source_id=source_id, fingerprint=fingerprint(path), origin=path))

    return StoreScan(
        store=MANUALS_STORE,
        available=True,
        sources=tuple(sorted(sources, key=lambda d: d.source_id)),
        rejections=tuple(sorted(rejections, key=lambda r: r.origin)),
    )


def _collision(source_id: str, paths: Iterable[Path]) -> list[DiscoveryRejection]:
    """Every member of the group is rejected — silently indexing one is what 2.6 forbids."""
    names = ", ".join(sorted(path.name for path in paths))
    return [
        DiscoveryRejection(
            origin=path,
            source_id=source_id,
            rejection=Rejection(
                reason="source-id-collision",
                detail=f"{source_id} is claimed by {names}",
            ),
        )
        for path in paths
    ]


def discover_stores(scans: Iterable[StoreScan]) -> tuple[StoreScan, ...]:
    """The run's view of every store, with one identity claimed twice rejected in both (2.6).

    Each store scans itself — `manuals/` here, the authored entry store by the loader
    `data/symptom-triage` supplies (12.3) — so a source of one kind is never tested against the
    other kind's store. The one thing a single scan cannot see is a `source_id` two stores both
    claim: `authored_triage_notes_v1_en.pdf` is legal grammar and lands on the authored store's
    own constant identity. That collides on `source_id` itself, before any slug is formed, and
    the slug rule cannot catch it because both sides form the same slug from the same ID.
    """
    scanned = tuple(scans)
    claimed: dict[str, list[StoreScan]] = {}
    for scan in scanned:
        for source_id in scan.source_ids:
            claimed.setdefault(source_id, []).append(scan)
    contested = {source_id for source_id, holders in claimed.items() if len(holders) > 1}
    if not contested:
        return scanned

    resolved = []
    for scan in scanned:
        kept = tuple(d for d in scan.sources if d.source_id not in contested)
        rejected = tuple(
            DiscoveryRejection(
                origin=d.origin,
                source_id=d.source_id,
                rejection=Rejection(
                    reason="source-id-collision",
                    detail=(
                        f"{d.source_id} is claimed by the "
                        + " and ".join(sorted(s.store for s in claimed[d.source_id]))
                        + " stores"
                    ),
                ),
            )
            for d in scan.sources
            if d.source_id in contested
        )
        resolved.append(replace(scan, sources=kept, rejections=scan.rejections + rejected))
    return tuple(resolved)


@dataclass(frozen=True)
class ShardMeta:
    """What `shards/<slug>.meta.json` says about the source its shard holds.

    Only the three fields removal and change detection need are read here; `index/build.py`
    owns the rest of the record, including the cache key's other three components.
    """

    slug: str
    source_id: str
    store: str
    fingerprint: str
    path: Path


def read_shard_metas(index_root: Path) -> tuple[ShardMeta, ...]:
    """Every committed shard's meta. A meta that cannot be read is not reported.

    Silence is deliberate: an unparseable meta names no store and no source, so nothing can
    tell whether its shard is stale, and removal on a parse error would lose a source to a bug
    somewhere else. It is left for `index/build.py` to overwrite on the next ingestion.
    """
    try:
        paths = sorted((index_root / "shards").glob("*.meta.json"))
    except OSError:
        return ()

    metas = []
    for path in paths:
        try:
            meta = json.loads(path.read_text())
            source_id = meta["source"]["source_id"]
            store = meta["store"]
            digest = meta["fingerprint"]
        except (OSError, ValueError, KeyError, TypeError):
            continue
        metas.append(
            ShardMeta(
                slug=path.name.removesuffix(".meta.json"),
                source_id=source_id,
                store=store,
                fingerprint=digest,
                path=path,
            )
        )
    return tuple(metas)


def fingerprint_changed(discovered: Discovered, meta: ShardMeta | None) -> bool:
    """Whether this source's bytes differ from the ones its shard was built from (9.3).

    The fingerprint is one of the four components of the shard cache key; `index/build.py`
    holds the other three (`ingestion_version` and the embedding model and dimension), because
    a fixed ingestion bug changes no PDF byte and must still reach the index. No shard at all is
    a change by definition — the source is new (1.2).
    """
    return meta is None or meta.fingerprint != discovered.fingerprint


@dataclass(frozen=True)
class Removal:
    """One source deleted from the index because its store no longer holds it (1.4)."""

    source_id: str
    store: str
    slug: str
    paths: tuple[Path, ...]


def remove_absent_sources(scans: Sequence[StoreScan], index_root: Path) -> tuple[Removal, ...]:
    """Delete every shard whose source is gone from the store it was discovered in (1.4).

    Two rules keep this from deleting more than it should. Removal is scoped by the store
    **recorded on the shard**, so 9.5's "do not test a source of one kind against the other
    kind's store" holds by construction. And a store whose discovery set is unknown — absent,
    unreadable, or simply not scanned this run — removes nothing: only a store that exists and
    holds no sources yields an empty set and therefore removes its shards.

    A shard goes with its sidecar and its ingestion audit. An audit whose shard no longer
    exists describes nothing, and a sidecar left behind would be copied into the next view
    keyed to passages that are gone.
    """
    known = {scan.store: scan.source_ids for scan in scans if scan.available}

    removed = []
    for meta in read_shard_metas(index_root):
        source_ids = known.get(meta.store)
        if source_ids is None or meta.source_id in source_ids:
            continue
        paths = tuple(
            path
            for path in (
                *(index_root / "shards" / f"{meta.slug}{suffix}" for suffix in SHARD_SUFFIXES),
                index_root / "audits" / f"{meta.slug}.json",
            )
            if path.exists()
        )
        for path in paths:
            path.unlink()
        removed.append(
            Removal(source_id=meta.source_id, store=meta.store, slug=meta.slug, paths=paths)
        )
    return tuple(removed)


__all__ = [
    "AUTHORED_STORE",
    "FILENAME_GRAMMAR",
    "FILENAME_PATTERN",
    "MANUALS_STORE",
    "SHARD_SUFFIXES",
    "DiscoveryRejection",
    "Removal",
    "ShardMeta",
    "SourceIdentity",
    "StoreScan",
    "discover_stores",
    "fingerprint",
    "fingerprint_changed",
    "parse_filename",
    "read_shard_metas",
    "remove_absent_sources",
    "scan_manuals",
    "slug",
]
