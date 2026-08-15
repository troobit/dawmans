"""INGESTION_VERSION — the shard cache-key component."""

from __future__ import annotations

#: Bumped **by hand** whenever a change to any stage from extraction through chunking
#: could alter a chunk's text or its metadata. A shard is reused only when this matches
#: the value recorded in its meta, so forgetting to bump it means a fixed ingestion bug
#: reaches nothing: no PDF byte changed, so the fingerprint alone would reuse every
#: shard. The remedy for a forgotten bump is the same as for `index_version` — delete
#: `index/` and rebuild.
INGESTION_VERSION = 1

__all__ = ["INGESTION_VERSION"]
