"""Shared builders for the local HTTP surface tests.

Requests run through httpx's ASGITransport against the guarded app, with
a loopback base URL so the Host check passes by default — each test that
probes the guard overrides headers explicitly. The watcher is a stub with
the same seam as `ViewWatcher` (`view`, `check()`, `manifest_fault`,
`corpus_reload_ms`) plus `swap()` so a test can stage the next revision
the way a re-ingest would.
"""

import asyncio

import httpx
from corpus_fixtures import make_view, passage, sidecar_entry, triage_source, vendor_source

PORT = 8722
BASE = f"http://127.0.0.1:{PORT}"

LIVE = "ableton/live-12"
APC = "akai/apc-key-25"
TRIAGE = "authored/triage"

SOURCES = [
    vendor_source(LIVE, LIVE, page_count=1009),
    vendor_source(APC, APC, page_count=5, status="assumed"),
    triage_source(),
]

PASSAGES = [
    passage(f"{LIVE}#p1", "The Track Activator mutes the track output"),
    passage(f"{LIVE}#p2", "Click the dimmed track number to re-enable the track"),
    passage(f"{APC}#p1", "Hold SHIFT and press a pad to select a scene"),
    passage(f"{TRIAGE}#t1", "No sound from a track although the meters move"),
]

ENTRY = sidecar_entry(
    f"{TRIAGE}#t1",
    [LIVE],
    symptom="No sound from a track",
    causes=[
        {
            "statement": "The Track Activator is off",
            "check": "the track number is dimmed in the mixer",
            "fix": [{"source_id": LIVE, "section": "16.4", "passage_ids": [f"{LIVE}#p2"]}],
            "undocumented_device": None,
            "flags": [],
        },
        {
            "statement": "The scene is not launched",
            "check": "no pad is lit on the controller",
            "fix": [{"source_id": APC, "section": "3.1", "passage_ids": [f"{APC}#p1"]}],
            "undocumented_device": None,
            "flags": [],
        },
    ],
)

# The reports as data/manual-corpus publishes them: relayed, never derived,
# so the fixture deliberately carries members the corpus does not imply.
GAPS = {
    "owned_but_undocumented": [{"device": "roland/tr-8s", "display_name": "Roland TR-8S"}],
    "documented_but_unconfirmed": [
        {"source_id": APC, "display_name": APC, "status": "assumed", "owned_revision": "mk2"}
    ],
}

_UNSET = object()


class StubWatcher:
    """The ViewWatcher seam without the disk: swap-on-check, plus the
    fault and reload fields GET /sources relays."""

    def __init__(self, view):
        self.view = view
        self.manifest_fault = None
        self.corpus_reload_ms = None
        self.checks = 0
        self._pending = _UNSET

    def swap(self, view):
        self._pending = view

    def check(self):
        self.checks += 1
        if self._pending is not _UNSET:
            self.view = self._pending
            self._pending = _UNSET


def default_view(*, gaps=GAPS):
    return make_view(SOURCES, PASSAGES, gaps=gaps, sidecar=[ENTRY])


def make_app(watcher, **kwargs):
    from dawmans.answer.http.app import create_app

    return create_app(watcher=watcher, port=PORT, **kwargs)


def request(app, method, path, *, headers=None, json_body=None, base_url=BASE):
    async def go():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url=base_url) as client:
            return await client.request(method, path, headers=headers, json=json_body)

    return asyncio.run(go())


def get(app, path, **kwargs):
    return request(app, "GET", path, **kwargs)
