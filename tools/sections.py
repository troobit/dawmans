"""Find real manual sections to point a triage entry's `fix:` at.

Authoring an entry means naming a section that exists. `data/symptom-triage` 2.2
rejects the whole entry at first ingest if a pointer does not resolve, and 2.6
flags a cause naming a control that does not appear in the passage it points to.
Both failures are cheap to avoid and expensive to discover: this prints pointers
copied from the committed index rather than remembered, in the exact `fix:`
syntax an entry uses.

    uv run python tools/sections.py monitor        # sections mentioning "monitor"
    uv run python tools/sections.py --titles solo  # match titles only
    uv run python tools/sections.py --list         # every source, with counts
    uv run python tools/sections.py --source akai/apc-key-25

Stdlib only, and it reads the committed view directly rather than importing the
package: an agent authoring an entry may be in an environment with neither extra
installed, and this has to work there.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INDEX = ROOT / "index"

# 2.7: an authored pointer may not ground another authored passage, so the
# authored store is never a candidate and is dropped rather than listed.
AUTHORED_SOURCE_ID = "authored/triage"


class NoIndex(RuntimeError):
    """No committed view to read. Naming the fix beats naming the fault."""


def load_passages(index_dir: Path = INDEX) -> list[dict]:
    manifest_path = index_dir / "manifest.json"
    if not manifest_path.is_file():
        raise NoIndex(
            f"no manifest at {manifest_path} — run `uv run dawmans ingest` first "
            f"(and `make fetch-model` once, if you have not)"
        )
    manifest = json.loads(manifest_path.read_text())
    passages = index_dir / manifest["view_dir"] / "passages.jsonl"
    if not passages.is_file():
        raise NoIndex(f"{passages} is named by the manifest and absent — re-run ingestion")
    with passages.open() as handle:
        return [json.loads(line) for line in handle if line.strip()]


def pointer(passage: dict) -> str:
    """The `fix:` form of one passage, paste-ready.

    A section with no number is addressed by title alone: Decision 3 admits both
    forms and forbids a page, and the number is what selects where there is one.
    """
    number = passage.get("section_number")
    title = passage.get("section_title") or ""
    source = passage["source_id"]
    if number:
        return f'fix: {source} §{number} "{title}"'
    return f'fix: {source} "{title}"'


def matches(passage: dict, term: str, *, titles_only: bool) -> bool:
    needle = term.lower()
    if needle in (passage.get("section_title") or "").lower():
        return True
    if titles_only:
        return False
    return needle in (passage.get("text") or "").lower()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="sections.py", description=__doc__.splitlines()[0], allow_abbrev=False
    )
    parser.add_argument("term", nargs="*", help="text to find in a section title or body")
    parser.add_argument(
        "--titles", action="store_true", help="match section titles only, not passage text"
    )
    parser.add_argument("--source", help="restrict to one source id, e.g. ableton/live-12")
    parser.add_argument("--list", action="store_true", help="list sources and section counts")
    parser.add_argument("--limit", type=int, default=40, help="results to print (default 40)")
    args = parser.parse_args(argv)

    try:
        passages = load_passages()
    except NoIndex as error:
        print(str(error), file=sys.stderr)
        return 1

    passages = [p for p in passages if p["source_id"] != AUTHORED_SOURCE_ID]

    if args.list or not args.term:
        counts: dict[str, int] = {}
        for passage in passages:
            counts[passage["source_id"]] = counts.get(passage["source_id"], 0) + 1
        print("Sources in the committed index — pass a term to search them:\n")
        for source_id, count in sorted(counts.items()):
            print(f"  {source_id:<32} {count:>5} passages")
        return 0

    if args.source:
        passages = [p for p in passages if p["source_id"] == args.source]
        if not passages:
            print(f"no source {args.source!r} in the index — run with --list", file=sys.stderr)
            return 1

    term = " ".join(args.term)
    hits = [p for p in passages if matches(p, term, titles_only=args.titles)]

    if not hits:
        where = "titles" if args.titles else "titles or text"
        print(f"nothing matching {term!r} in any section's {where}.")
        print("A control the manuals never name cannot carry a fix pointer; 2.3 covers")
        print("only a rig device with no ingested source at all.")
        return 1

    # Deduplicate to one line per section: a long section spans several passages
    # and the pointer addresses the section, not the passage.
    seen: dict[str, dict] = {}
    for passage in hits:
        seen.setdefault(pointer(passage), passage)

    print(f"{len(seen)} section(s) matching {term!r}:\n")
    for line, passage in list(seen.items())[: args.limit]:
        print(f"  {line}")
        if not args.titles:
            print(f"      …{_excerpt(passage.get('text') or '', term)}…")
    if len(seen) > args.limit:
        print(f"\n  ({len(seen) - args.limit} more — narrow the term or raise --limit)")

    print("\nCheck the text really documents the control before pointing a cause at it:")
    print("2.6 flags a cause naming a term the pointed-at passage does not contain.")
    return 0


def _excerpt(text: str, term: str, width: int = 90) -> str:
    at = text.lower().find(term.lower())
    if at < 0:
        return text[:width].replace("\n", " ")
    start = max(0, at - width // 3)
    return text[start : start + width].replace("\n", " ")


if __name__ == "__main__":
    sys.exit(main())
