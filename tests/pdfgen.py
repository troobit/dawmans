"""A minimal PDF writer, for tests that need a PDF the extractor can open.

`manuals/` is gitignored and no test may open a reference PDF, so the extraction tests
build their own. They cannot build them with PyMuPDF: it is AGPL and confined to
`dawmans/corpus/pdf/` (decision_log.md Decision 6), and `pyproject.toml` bans the import
everywhere else. So the handful of constructs those tests need — a text layer at known
coordinates in a named base-14 font, and image XObjects with no text beside them — are
written here by hand.

Coordinates are given **from the top of the page**, the way PyMuPDF reports bounding
boxes, and converted to PDF's bottom-left origin on the way out. A `Text`'s `y` is its
baseline.

This is deliberately the smallest thing that produces a file MuPDF reads: uncompressed
streams, no encryption, no compression, one xref table.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

#: The base-14 fonts, which need no embedding. PyMuPDF reports the `BaseFont` name as
#: the span's font, so a test can assert on these names directly.
HELVETICA = "Helvetica"
HELVETICA_BOLD = "Helvetica-Bold"
TIMES_ROMAN = "Times-Roman"
COURIER = "Courier"


@dataclass(frozen=True)
class Text:
    """One line of text, drawn with its baseline `y` points below the page top."""

    text: str
    x: float
    y: float
    size: float = 10.0
    font: str = HELVETICA


@dataclass(frozen=True)
class Image:
    """A placed image. `resolution` squared pixels of `colour`, scaled into the box.

    The pixels are uncompressed `DeviceRGB`, so the file grows with `resolution` — which
    is the point: requirement 10.4 says a manual's images cost file size and nothing else.
    """

    x: float
    y: float
    width: float
    height: float
    colour: tuple[int, int, int] = (200, 30, 30)
    resolution: int = 8


@dataclass(frozen=True)
class Page:
    texts: tuple[Text, ...] = ()
    images: tuple[Image, ...] = ()
    width: float = 612.0
    height: float = 792.0


@dataclass
class _Objects:
    """The PDF body: objects numbered from 1, serialised in order."""

    bodies: list[bytes] = field(default_factory=list)

    def add(self, body: bytes) -> int:
        self.bodies.append(body)
        return len(self.bodies)


def _escape(text: str) -> bytes:
    out = text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")
    return out.encode("cp1252", errors="replace")


def _content_stream(page: Page, images: dict[int, str], fonts: dict[str, str]) -> bytes:
    parts: list[bytes] = []
    for index, image in enumerate(page.images):
        bottom = page.height - image.y - image.height
        parts.append(
            f"q {image.width:.2f} 0 0 {image.height:.2f} {image.x:.2f} {bottom:.2f} cm "
            f"/{images[index]} Do Q".encode("ascii")
        )
    for text in page.texts:
        parts.append(
            b"BT /"
            + fonts[text.font].encode("ascii")
            + f" {text.size:.2f} Tf 1 0 0 1 {text.x:.2f} {page.height - text.y:.2f} Tm ".encode(
                "ascii"
            )
            + b"("
            + _escape(text.text)
            + b") Tj ET"
        )
    return b"\n".join(parts)


def _stream_object(dictionary: str, payload: bytes) -> bytes:
    head = f"<<{dictionary} /Length {len(payload)}>>\nstream\n".encode("ascii")
    return head + payload + b"\nendstream"


def pdf_bytes(pages: list[Page]) -> bytes:
    """One PDF holding `pages`, in order. An empty `texts` is a page with no text layer."""
    objects = _Objects()
    catalogue = objects.add(b"")  # reserved: the object numbers are needed before the bodies
    pages_node = objects.add(b"")

    font_names = sorted({text.font for page in pages for text in page.texts})
    font_refs = {}
    for index, name in enumerate(font_names):
        number = objects.add(
            f"<</Type /Font /Subtype /Type1 /BaseFont /{name} /Encoding /WinAnsiEncoding>>".encode(
                "ascii"
            )
        )
        font_refs[name] = (f"F{index}", number)

    page_numbers: list[int] = []
    for page in pages:
        image_refs: dict[int, tuple[str, int]] = {}
        for index, image in enumerate(page.images):
            side = max(1, image.resolution)
            pixels = bytes(image.colour) * (side * side)
            number = objects.add(
                _stream_object(
                    f"/Type /XObject /Subtype /Image /Width {side} /Height {side} "
                    f"/ColorSpace /DeviceRGB /BitsPerComponent 8",
                    pixels,
                )
            )
            image_refs[index] = (f"Im{index}", number)

        payload = _content_stream(
            page,
            {index: name for index, (name, _) in image_refs.items()},
            {name: alias for name, (alias, _) in font_refs.items()},
        )
        contents = objects.add(_stream_object("", payload))

        font_entries = " ".join(
            f"/{alias} {number} 0 R" for _, (alias, number) in sorted(font_refs.items())
        )
        image_entries = " ".join(
            f"/{alias} {number} 0 R" for alias, number in sorted(image_refs.values())
        )
        resources = f"<</Font <<{font_entries}>> /XObject <<{image_entries}>>>>"
        page_numbers.append(
            objects.add(
                (
                    f"<</Type /Page /Parent {pages_node} 0 R "
                    f"/MediaBox [0 0 {page.width:.2f} {page.height:.2f}] "
                    f"/Resources {resources} /Contents {contents} 0 R>>"
                ).encode("ascii")
            )
        )

    objects.bodies[catalogue - 1] = f"<</Type /Catalog /Pages {pages_node} 0 R>>".encode("ascii")
    kids = " ".join(f"{number} 0 R" for number in page_numbers)
    objects.bodies[pages_node - 1] = (
        f"<</Type /Pages /Kids [{kids}] /Count {len(page_numbers)}>>".encode("ascii")
    )

    out = bytearray(b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for number, body in enumerate(objects.bodies, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode("ascii") + body + b"\nendobj\n"

    start = len(out)
    out += f"xref\n0 {len(offsets) + 1}\n".encode("ascii")
    out += b"0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode("ascii")
    out += (
        f"trailer\n<</Size {len(offsets) + 1} /Root {catalogue} 0 R>>\nstartxref\n{start}\n".encode(
            "ascii"
        )
    )
    out += b"%%EOF\n"
    return bytes(out)


def write_pdf(path: Path, pages: list[Page]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(pdf_bytes(pages))
    return path


def lines(
    *bodies: str,
    x: float = 72.0,
    top: float = 100.0,
    leading: float = 14.0,
    size: float = 10.0,
    font: str = HELVETICA,
) -> tuple[Text, ...]:
    """Successive lines down the page, the way a paragraph or a procedure is set."""
    return tuple(
        Text(text=body, x=x, y=top + index * leading, size=size, font=font)
        for index, body in enumerate(bodies)
    )
