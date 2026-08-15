"""serve-document (9.4, design §The local HTTP surface).

The route takes no path and reads no index it did not load: `source_id`
resolves against sources.json, the filename is rebuilt from that record's
own fields under Decision 2's grammar, and the result is realpath-confined
to the manuals root. The PDF is served inline — an attachment disposition
would download the file and silently defeat `#page=N` — with Range
honoured so a 96 MB manual pages without being fetched whole.
"""

from urllib.parse import quote

import pytest
from corpus_fixtures import make_view, passage, vendor_source
from http_fixtures import APC, LIVE, TRIAGE, StubWatcher, default_view, get, make_app

PDF_BYTES = b"%PDF-1.7 not really a pdf but bytes are bytes" * 40

# Decision 2's grammar, spelled literally: doc_version arrives without the
# leading v (manual-corpus 2.7), so there is one reconstruction rule and
# no `_vv1.0_`.
FILES = {
    LIVE: "ableton_live-12_manual_v1.0_en.pdf",
    APC: "akai_apc-key-25_manual_v1.0_en.pdf",
}


def document_path(source_id):
    return f"/sources/{quote(source_id, safe='/')}/document"


@pytest.fixture
def manuals_root(tmp_path):
    root = tmp_path / "manuals"
    root.mkdir()
    for name in FILES.values():
        (root / name).write_bytes(PDF_BYTES)
    return root


@pytest.fixture
def app(manuals_root):
    return make_app(StubWatcher(default_view()), manuals_root=manuals_root)


class TestServeDocument:
    def test_a_known_vendor_manual_returns_its_pdf_inline(self, app):
        response = get(app, document_path(LIVE))
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/pdf"
        # An attachment disposition downloads the file and silently
        # defeats #page=N; no filename disposition may be set.
        disposition = response.headers.get("content-disposition", "")
        assert "attachment" not in disposition
        assert "filename" not in disposition
        # Streamed bytes, parsed by nothing.
        assert response.content == PDF_BYTES

    def test_the_filename_round_trips_for_every_ingested_vendor_manual(self, app):
        # The fixture files are spelled literally; a second v (`_vv1.0_`)
        # or any other reconstruction drift finds nothing.
        for source_id in FILES:
            assert get(app, document_path(source_id)).status_code == 200, source_id

    def test_range_is_honoured(self, app):
        response = get(app, document_path(LIVE), headers={"range": "bytes=0-9"})
        assert response.status_code == 206
        assert response.content == PDF_BYTES[:10]
        assert response.headers["content-range"] == f"bytes 0-9/{len(PDF_BYTES)}"


class TestNotFound:
    def test_an_authored_triage_id_is_404(self, app):
        # The authored kind has no document; its open-at-source is
        # fetch-passage (9.4).
        response = get(app, document_path(TRIAGE))
        assert response.status_code == 404
        assert response.json()["not_found"]

    def test_an_unknown_id_is_404(self, app):
        assert get(app, document_path("nonexistent/source")).status_code == 404

    def test_a_renamed_file_is_404_so_the_caller_degrades_the_citation(self, app, manuals_root):
        (manuals_root / FILES[APC]).rename(manuals_root / "renamed.pdf")
        response = get(app, document_path(APC))
        assert response.status_code == 404
        assert response.json()["not_found"]


class TestConfinement:
    def test_a_path_shaped_source_id_never_reaches_the_filesystem(self, app):
        # The loaded index is the allowlist: whatever the path parameter
        # carries, an id that is not a key of sources.json resolves to
        # nothing. (httpx may normalise dot segments away first; either
        # way the answer is 404, never a file.)
        for probe in (
            "../../../etc/passwd",
            "..%2F..%2Fetc%2Fpasswd",
            "etc/passwd",
        ):
            response = get(app, f"/sources/{probe}/document")
            assert response.status_code == 404, probe

    def test_a_record_whose_fields_escape_the_root_is_refused(self, tmp_path):
        # sources.json is trusted data, but the confinement does not rely
        # on that: a rebuilt name whose realpath leaves the manuals root
        # is refused even though the file exists outside it.
        root = tmp_path / "manuals"
        root.mkdir()
        (tmp_path / "outside_x_manual_v1.0_en.pdf").write_bytes(PDF_BYTES)
        record = dict(vendor_source("evil/x", "evil/x"))
        record["vendor"] = "../outside"
        record["product"] = "x"
        view = make_view([record], [passage("evil/x#p1", "text")])
        app = make_app(StubWatcher(view), manuals_root=root)
        response = get(app, document_path("evil/x"))
        assert response.status_code == 404
