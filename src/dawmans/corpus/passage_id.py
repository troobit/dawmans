"""The content-derived passage identifier of requirement 6.1.

`passage_id = f"{source_id}#{sha256(canonical(text))[:16]}"` and nothing else enters the
digest. Each exclusion answers a way the identifier could otherwise break: a section number
or a page breaks on a point release that renumbers or repaginates (`data/symptom-triage`
8.3); a document version, fingerprint or timestamp breaks on any re-ingestion at all (6.1);
a chunk index breaks when an earlier chunk is inserted. `entry_location` is excluded by
CONTRACTS §2 itself — the author moves entries between files, so it is a locator and not an
identity. The reasoning is decision_log Decision 5.

`source_id` is carried as a **visible prefix** rather than hashed. Cross-source collisions
are then impossible by construction, and `fetch-passage` routes on the prefix without a
lookup.

Canonicalisation is NFC plus whitespace collapsing, and no more: a re-extraction differing
only in line wrapping or Unicode composition carries no meaning and must not orphan every
citation in the retained UI history at once. Case is **not** folded — 3.1 preserves casing
and two chunks differing only in case are genuinely different text.

Determinism is a property of the whole pipeline rather than of this function, and is tested
end to end over the same PDF bytes.
"""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from collections.abc import Iterable
from unicodedata import normalize as normalised  # spelling-ignore: the stdlib's own name

#: 64 bits. At ~1,200 chunks the accidental collision probability is ~4 × 10⁻¹⁴, and real
#: duplicates are handled deterministically by the suffix rule below regardless.
DIGEST_LENGTH = 16

_WHITESPACE = re.compile(r"\s+")


def canonical(text: str) -> str:
    """The form the digest is taken over: NFC, whitespace runs collapsed, stripped."""
    return _WHITESPACE.sub(" ", normalised("NFC", text)).strip()


def passage_id(source_id: str, text: str) -> str:
    """The identifier of one chunk of one source (6.1)."""
    digest = hashlib.sha256(canonical(text).encode("utf-8")).hexdigest()
    return f"{source_id}#{digest[:DIGEST_LENGTH]}"


def assign_ids(source_id: str, texts: Iterable[str]) -> list[str]:
    """One identifier per chunk, in document order, unique within the source.

    Where k > 1 chunks share a digest — repeated boilerplate — the **first in document
    order keeps the unsuffixed identifier** and the 2nd…kth take `.2 … .k`. The asymmetry
    is deliberate: suffixing all k would mean that a source newly acquiring a second copy
    of some boilerplate destroys the stable identifier of the first copy, whose text did
    not change, so a citation held in retained UI history stops resolving because of an
    edit elsewhere in the document. That would breach 6.1 and `data/symptom-triage` 8.2.
    """
    seen: Counter[str] = Counter()
    assigned = []
    for text in texts:
        base = passage_id(source_id, text)
        seen[base] += 1
        assigned.append(base if seen[base] == 1 else f"{base}.{seen[base]}")
    return assigned


__all__ = ["DIGEST_LENGTH", "assign_ids", "canonical", "passage_id"]
