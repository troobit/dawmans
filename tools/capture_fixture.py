"""Dump a manual's extraction to JSON — the committed fixtures of `tests/fixtures/`.

`manuals/` is gitignored: the vendor PDFs are copyrighted documents kept locally and never
committed, so **no test may open one**. The fixtures are therefore committed extraction
snapshots, which also pins the extractor's output as an explicit input to every downstream
test: a change to extraction shows up as a diff in these files rather than as a surprise in
a chunking test.

    make fixtures                                   # recapture the committed set
    uv run python tools/capture_fixture.py --list    # what that set is, and why
    uv run python tools/capture_fixture.py manuals/x.pdf --pages 3-6 --out /tmp/x.json

Two capture modes:

- **Full** keeps span geometry, font names, sizes, flags and text.
- **Redacted** (`--redact`) keeps geometry, fonts and a language label, and masks the text:
  letters become `x`/`X` and digits `0`, punctuation and spacing are left alone. The APC
  guide is the case that needs it — full span text for its 24 pages would commit
  substantially the whole guide. Masking rather than dropping the text is deliberate: word
  counts, line lengths, dot-leader runs and the alphabetic-token ratio all survive it, and
  those are what the furniture, sectioning and language stages actually measure. No word
  of the source survives it.

The language label is ground truth supplied here by hand (`--label`), not something a
detector produced: a redacted fixture cannot exercise a language identifier, so the
phase-4 tests drive selection from the label and assert the selection machinery.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

from dawmans.corpus.pdf.extract import Block, Document, Line, Page, Span, extract_document

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MANUALS = REPO_ROOT / "manuals"
DEFAULT_OUT_DIR = REPO_ROOT / "tests" / "fixtures"

LIVE = "ableton_live-12_reference-manual_v12_en.pdf"
APC = "akai_apc-key-25_user-guide_v1.0_multi.pdf"
NITRO = "alesis_nitro-max_user-guide_v1.1_en.pdf"


@dataclass(frozen=True)
class Capture:
    """One committed fixture: where it comes from and what it is for."""

    name: str
    source: str
    pages: str
    asserts: str
    #: `slice` keeps the outline entries landing in the captured pages, `none` keeps the
    #: outline out entirely. `none` is what a path B or path C fixture needs: all four
    #: reference manuals carry an embedded outline, so a fixture standing for a document
    #: without one has to withhold it (decision_log.md Decision 10).
    toc: str = "slice"
    redact: bool = False
    labels: str = ""


#: The committed set. The page numbers are physical 1-based indices into the vendor PDFs
#: named in `prerequisites.md`, and they are the reason this list exists rather than a
#: README: recapturing has to land on the same pages.
FIXTURES: tuple[Capture, ...] = (
    Capture(
        name="nitro_max_p25",
        source=NITRO,
        pages="25",
        asserts=(
            "all 19 trigger-to-note pairs recoverable with their printed pairings; the "
            "heading joined from three physical lines; ragged rows placed by x-position "
            "(7.1-7.3, 7.6)"
        ),
    ),
    Capture(
        name="apc_p14_arrows",
        source=APC,
        pages="14",
        asserts=(
            "the Wingdings3 run at U+00F0/F1/F4/F5 repairs to arrows, and the genuine "
            "French o-circumflex set in the body face on the same page is left alone "
            "(5.1-5.3). The design names this fixture apc_p3_arrows against a genuine "
            "Spanish n-tilde; in v1.0 of the guide p3 carries no symbol font at all, and "
            "no page holds both the arrows and a real n-tilde. p14 is stronger than the "
            "case the design asked for: U+00F4 appears twice on it, once as a Wingdings3 "
            "arrow and once as a French letter, so character-keyed detection corrupts the "
            "French word and only the font test tells them apart"
        ),
    ),
    Capture(
        name="apc_pages",
        source=APC,
        pages="1-24",
        redact=True,
        # Page 1 prints the guide's own language index, so its labels are per block:
        # blocks 1-2 are empty, then the six title/range pairs. That page is deliberately
        # never parsed by the ingestion code — it is exactly the per-manual structure 4.2
        # forbids depending on — but a fixture has to say what is on it.
        labels=(
            "1.3=en,1.4=en,1.5=es,1.6=es,1.7=fr,1.8=fr,1.9=it,1.10=it,1.11=de,1.12=de,"
            "1.13=en,1.14=en,3-6=en,7-10=es,11-14=fr,15-18=it,19-22=de,23=en"
        ),
        asserts=(
            "English pp3-6 and p23 selected, pp7-22 excluded, with no page range in the "
            "code (4.2-4.6). Redacted: 24 pages of span text would commit substantially "
            "the whole guide"
        ),
    ),
    Capture(
        name="live_toc_slice",
        source=LIVE,
        pages="470-473,584-592",
        asserts=(
            "outline entries anchor to in-body headings and text is attributed to the "
            "right section where two share a page (6.3, 6.6); the parent chain survives, "
            "which is what keeps 28.21.1 'Sidechain Parameters' — one of eight — under "
            "'Glue Compressor'. The first range crosses the 23/24 chapter boundary"
        ),
    ),
    Capture(
        name="live_contents_p13",
        source=LIVE,
        pages="13",
        asserts=(
            "a printed contents page is detected and contributes no chunks while "
            "remaining in page_count and the 4.4 audit (6.5). Live's contents pages carry "
            "no dot leaders: the page numbers are a separate right-hand column of bare "
            "numerals, extracted ahead of the titles. Path B's dot-leader test does not "
            "fire here — the Nitro Max contents page is the one that has leaders — so "
            "this fixture is what stops that being discovered in production"
        ),
    ),
    Capture(
        name="live_procedure_pagebreak",
        source=LIVE,
        pages="158-159",
        asserts=(
            "a numbered procedure whose steps 1-4 are on p158 and step 5 on p159 stays "
            "one chunk with page_start 158 and page_end 159 (6.8, 6.10). The design "
            "names p11-p12 illustratively; this is the real instance. Note the "
            "enumerators are set in a left gutter and extract after the step text, so "
            "only row assembly on geometry puts them back"
        ),
    ),
    Capture(
        name="apc_no_toc",
        source=APC,
        pages="3-4",
        toc="none",
        asserts=(
            "no outline and no contents page yields the heading-style path, unnumbered "
            "regions, and a citation rendered with no section number (6.4)"
        ),
    ),
    Capture(
        name="cover_only",
        source=LIVE,
        pages="1",
        toc="none",
        asserts=(
            "a title plus a strapline — 'Ableton Live 12 Manual' over 'for Windows and "
            "Mac' — fails path C's quality gate and yields one titled region, not two "
            "spanning the whole document (6.5)"
        ),
    ),
    Capture(
        name="furniture_pages",
        source=NITRO,
        pages="23-26",
        asserts=(
            "a repeated page number in the band is suppressed; the numeric cells inside "
            "p25's detected table are not (3.6)"
        ),
    ),
)


#: The rejection cases (design §Error Handling). None of them can be captured from the
#: reference corpus — a manual that trips them is one nobody would ship — so they are
#: built here instead, in the same snapshot form so the same loader reads them.
REJECTION_DIR = "rejections"

#: 5.5's threshold. The fixture sits above it on purpose; the arithmetic is asserted in
#: the test rather than trusted here.
UNMAPPABLE_LIMIT = 0.02


def synthetic_rejections() -> dict[str, dict]:
    """The four rejection fixtures: two span models and one table of filenames."""
    scanned = Document(
        page_count=2,
        pages=[
            Page(number=number, width=595.0, height=842.0, images=[(0.0, 0.0, 595.0, 842.0)])
            for number in (1, 2)
        ],
    )

    # ~3% of the characters are in a symbol font with no mapping, over 5.5's 2%.
    prose = "Connect the interface and set the input gain until the meter stays green. "
    rows = []
    for index in range(12):
        top = 100.0 + index * 14.0
        rows.append(
            Line(
                bbox=(72.0, top, 520.0, top + 11.0),
                spans=[
                    Span(
                        text=prose, bbox=(72.0, top, 500.0, top + 11.0), font="Helvetica", size=10.0
                    )
                ],
            )
        )
    # The code points are deliberately *not* the APC guide's 0xF0/F1/F4/F5: those are in
    # the glyph corruption table and repair to arrows, which is not a rejection. These four
    # are the same font with no entry anywhere — path 3, the unmappable case 5.5 counts.
    symbols = Line(
        bbox=(72.0, 280.0, 100.0, 291.0),
        spans=[
            Span(text="ÐÑÒÓ" * 8, bbox=(72.0, 280.0, 100.0, 291.0), font="Wingdings3", size=10.0)
        ],
    )
    unreadable = Document(
        page_count=1,
        pages=[
            Page(
                number=1,
                width=595.0,
                height=842.0,
                blocks=[Block(bbox=(72.0, 100.0, 520.0, 300.0), lines=[*rows, symbols])],
            )
        ],
    )

    return {
        "image_only": {
            "asserts": "no embedded text layer at all is the `no-text-layer` rejection (3.3)",
            **scanned.to_dict(),
        },
        "unreadable_text": {
            "asserts": (
                "unmappable characters over 2% of the extracted text layer is the "
                "`unreadable-text` rejection (5.5). The denominator is every extracted "
                "character, counted after furniture suppression and before language "
                "selection. The symbol run is a Wingdings3 code point the corruption "
                "table does not hold, since a repaired run is not a rejection"
            ),
            **unreadable.to_dict(),
        },
        "filenames": {
            "asserts": (
                "the two discovery rejections (2.5, 2.6). `collision` holds two names "
                "that resolve to one source_id, and every member of the group is rejected"
            ),
            "filename_invalid": [
                "nitro max user guide.pdf",
                "alesis_nitro-max_user-guide_1.1_en.pdf",
                "alesis_nitro-max_user-guide_v1.1_english.pdf",
                "Alesis_Nitro-Max_User-Guide_v1.1_en.pdf",
                "alesis__nitro-max_user-guide_v1.1_en.pdf",
                "alesis_nitro-max_user-guide_v1.1_en.PDF",
            ],
            "collision": [
                "alesis_nitro-max_user-guide_v1.1_en.pdf",
                "alesis_nitro-max_reference-manual_v2.0_en.pdf",
            ],
        },
    }


def parse_pages(spec: str) -> list[int]:
    """`25`, `3-6`, `470-473,584-592` — physical 1-based, in the order given."""
    pages: list[int] = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            first, last = (int(value) for value in part.split("-", 1))
            pages.extend(range(first, last + 1))
        else:
            pages.append(int(part))
    return pages


def parse_labels(spec: str) -> dict[tuple[int, int | None], str]:
    """`3-6=en,7-10=es,1.1=en` — a language label per page range, or per block of a page.

    The per-block form is for the APC front page, which prints its own language index and
    so carries six languages in six blocks. Block numbers are 1-based in extraction order.
    """
    labels: dict[tuple[int, int | None], str] = {}
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        target, _, code = part.partition("=")
        if "." in target:
            page, _, block = target.partition(".")
            labels[(int(page), int(block))] = code
        elif "-" in target:
            first, last = (int(value) for value in target.split("-", 1))
            for page in range(first, last + 1):
                labels[(page, None)] = code
        else:
            labels[(int(target), None)] = code
    return labels


def mask(text: str) -> str:
    """Letters to `x`/`X`, digits to `0`; punctuation and whitespace untouched.

    Every measure the later stages take — word counts, line lengths, the dot-leader run,
    the ratio of alphabetic to non-alphabetic tokens — survives this. No word does.

    The test is `str.isalpha()` rather than `[a-zA-Z]`, which would leave `á`, `ñ` and `ü`
    standing: on a multilingual guide those are the very characters that identify the
    language of the line they are in.
    """
    return "".join("0" if character.isdigit() else _mask_letter(character) for character in text)


def _mask_letter(character: str) -> str:
    if not character.isalpha():
        return character
    return "X" if character.isupper() else "x"


def redact(document: Document, labels: dict[tuple[int, int | None], str]) -> None:
    for page in document.pages:
        for index, block in enumerate(page.blocks, start=1):
            block.lang = labels.get((page.number, index)) or labels.get((page.number, None))
            for line in block.lines:
                for span in line.spans:
                    span.text = mask(span.text)


def capture(
    pdf: Path,
    pages: list[int],
    *,
    toc: str = "slice",
    redacted: bool = False,
    labels: str = "",
    asserts: str = "",
) -> dict:
    document = extract_document(pdf, pages=pages)
    if redacted:
        redact(document, parse_labels(labels))

    wanted = set(pages)
    if toc == "none":
        document.toc = []
    elif toc == "slice":
        document.toc = [entry for entry in document.toc if entry.page in wanted]

    snapshot = document.to_dict()
    # Provenance first, so the head of the file says where it came from and what it is
    # for. `Document.from_dict` ignores both.
    return {
        "captured_from": pdf.name,
        "captured_pages": sorted(wanted),
        "redacted": redacted,
        "asserts": asserts,
        **snapshot,
    }


def _nested(value: object) -> bool:
    """Whether `value` holds a dictionary anywhere inside it."""
    if isinstance(value, dict):
        return True
    if isinstance(value, list):
        return any(_nested(item) for item in value)
    return False


def _render(value: object, level: int = 0) -> str:
    """Pretty JSON, except that a leaf object goes on one line.

    A span is `{"text": …, "bbox": […], "font": …}` with nothing nested in it, so it
    renders as one line and a fixture stays diffable at half the size: `indent=1`
    throughout puts each of a span's five keys on its own line and doubles the file.
    """
    pad = " " * level
    if isinstance(value, dict):
        if not any(_nested(item) for item in value.values()):
            return json.dumps(value, ensure_ascii=False)
        items = [
            f"{pad} {json.dumps(key)}: {_render(item, level + 1)}" for key, item in value.items()
        ]
        return "{\n" + ",\n".join(items) + f"\n{pad}}}"
    if isinstance(value, list):
        if not any(_nested(item) for item in value):
            return json.dumps(value, ensure_ascii=False)
        items = [f"{pad} {_render(item, level + 1)}" for item in value]
        return "[\n" + ",\n".join(items) + f"\n{pad}]"
    return json.dumps(value, ensure_ascii=False)


def write(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_render(payload) + "\n", encoding="utf-8")
    return path


def write_rejections(out_dir: Path) -> list[Path]:
    written = []
    for name, payload in synthetic_rejections().items():
        path = write(out_dir / REJECTION_DIR / f"{name}.json", payload)
        written.append(path)
        print(f"{path.relative_to(REPO_ROOT)}")
    return written


def capture_all(manuals: Path, out_dir: Path) -> list[Path]:
    written = []
    for fixture in FIXTURES:
        pdf = manuals / fixture.source
        if not pdf.exists():
            raise SystemExit(
                f"{pdf} is missing. The vendor PDFs are gitignored and supplied per "
                f"machine — see specs/data/manual-corpus/prerequisites.md."
            )
        payload = capture(
            pdf,
            parse_pages(fixture.pages),
            toc=fixture.toc,
            redacted=fixture.redact,
            labels=fixture.labels,
            asserts=fixture.asserts,
        )
        path = write(out_dir / f"{fixture.name}.json", payload)
        written.append(path)
        print(f"{path.relative_to(REPO_ROOT)}  {len(payload['pages'])} pages")
    written.extend(write_rejections(out_dir))
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("pdf", nargs="?", type=Path, help="the PDF to capture")
    parser.add_argument("--pages", default="1", help="physical 1-based, e.g. 25 or 3-6,12")
    parser.add_argument("--out", type=Path, help="where to write the snapshot")
    parser.add_argument("--toc", choices=("slice", "all", "none"), default="slice")
    parser.add_argument("--redact", action="store_true", help="mask the text, keep the geometry")
    parser.add_argument("--label", default="", help="language labels, e.g. 3-6=en,7-10=es")
    parser.add_argument("--all", action="store_true", help="recapture the committed fixture set")
    parser.add_argument(
        "--rejections",
        action="store_true",
        help="write only the synthetic rejection fixtures, which need no manuals/",
    )
    parser.add_argument("--list", action="store_true", help="list the committed fixture set")
    parser.add_argument("--manuals", type=Path, default=DEFAULT_MANUALS)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    args = parser.parse_args(argv)

    if args.list:
        for fixture in FIXTURES:
            mode = "redacted" if fixture.redact else "full"
            print(f"{fixture.name:26} {fixture.source} pp{fixture.pages} [{mode}]")
            print(f"{'':26} {fixture.asserts}")
        return 0

    if args.rejections:
        write_rejections(args.out_dir)
        return 0

    if args.all:
        capture_all(args.manuals, args.out_dir)
        return 0

    if args.pdf is None or args.out is None:
        parser.error("a PDF and --out are required unless --all or --list is given")

    payload = capture(
        args.pdf,
        parse_pages(args.pages),
        toc=args.toc,
        redacted=args.redact,
        labels=args.label,
    )
    write(args.out, payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
