"""fetch-passage, list-sources and the gap relay (3.4, 3.5, 9.5–9.7).

GET /passages/{id} is a dict lookup routed on the source_id prefix; it
runs the same stat change check as a turn, so a passage removed by a
re-ingest stops resolving immediately rather than at the next question.
GET /sources relays every 9.5 field for both kinds and both gap reports —
relayed, never derived — and reports an unreadable new manifest while the
live view keeps serving, with no filesystem path in any payload.
"""

from urllib.parse import quote

import numpy as np
from corpus_fixtures import make_view
from http_fixtures import (
    APC,
    LIVE,
    PASSAGES,
    SOURCES,
    TRIAGE,
    StubWatcher,
    default_view,
    get,
    make_app,
)


def passage_path(passage_id):
    return "/passages/" + quote(passage_id, safe="/")


def sources_app():
    watcher = StubWatcher(default_view())
    return make_app(watcher), watcher


class TestFetchPassage:
    def test_a_known_passage_returns_its_record(self):
        app, _ = sources_app()
        response = get(app, passage_path(f"{LIVE}#p1"))
        assert response.status_code == 200
        body = response.json()
        assert body["passage_id"] == f"{LIVE}#p1"
        assert body["source_id"] == LIVE
        assert body["text"] == "The Track Activator mutes the track output"

    def test_an_authored_passage_resolves_the_same_way(self):
        # The authored kind's open-at-source is served here (9.4): there
        # is no separate operation.
        app, _ = sources_app()
        response = get(app, passage_path(f"{TRIAGE}#t1"))
        assert response.status_code == 200
        assert response.json()["source_id"] == TRIAGE

    def test_an_unknown_id_is_404_and_never_a_substitute(self):
        app, _ = sources_app()
        response = get(app, passage_path(f"{LIVE}#p999"))
        assert response.status_code == 404
        body = response.json()
        assert body["not_found"]
        assert "text" not in body

    def test_an_unknown_source_prefix_is_404(self):
        app, _ = sources_app()
        response = get(app, passage_path("nonexistent/source#p1"))
        assert response.status_code == 404

    def test_the_route_runs_the_stat_change_check(self):
        app, watcher = sources_app()
        assert watcher.checks == 0
        get(app, passage_path(f"{LIVE}#p1"))
        assert watcher.checks == 1

    def test_a_passage_removed_by_a_reingest_stops_resolving_immediately(self):
        # The swap is staged the way a re-ingest would: the next check()
        # sees it. No turn runs in between — the route's own check is
        # what makes the removal immediate.
        app, watcher = sources_app()
        assert get(app, passage_path(f"{APC}#p1")).status_code == 200
        shrunk = make_view([SOURCES[0]], PASSAGES[:2], vectors=np.eye(4, dtype=np.float32)[:2])
        watcher.swap(shrunk)
        assert get(app, passage_path(f"{APC}#p1")).status_code == 404

    def test_an_empty_corpus_is_404(self):
        app = make_app(StubWatcher(None))
        assert get(app, passage_path(f"{LIVE}#p1")).status_code == 404


class TestListSources:
    def test_every_source_of_both_kinds_carries_the_9_5_fields(self):
        app, _ = sources_app()
        body = get(app, "/sources").json()
        by_id = {record["source_id"]: record for record in body["sources"]}
        assert set(by_id) == {LIVE, APC, TRIAGE}

        vendor = by_id[LIVE]
        assert vendor["display_name"] == LIVE
        assert vendor["kind"] == "vendor-manual"
        assert vendor["doc_version"] == "1.0"
        assert vendor["hardware_applicability"]["status"] == "confirmed"

        assumed = by_id[APC]
        assert assumed["hardware_applicability"]["status"] == "assumed"

        authored = by_id[TRIAGE]
        assert authored["kind"] == "authored-triage"
        # doc_version where the kind carries one: the authored kind does not.
        assert "doc_version" not in authored
        assert authored["hardware_applicability"]["status"] == "assumed"

    def test_both_gap_reports_are_relayed_verbatim_never_derived(self):
        # The fixture reports carry members the corpus does not imply —
        # a derivation would not reproduce them.
        app, _ = sources_app()
        body = get(app, "/sources").json()
        assert body["owned_but_undocumented"] == [
            {"device": "roland/tr-8s", "display_name": "Roland TR-8S"}
        ]
        unconfirmed = body["documented_but_unconfirmed"]
        assert len(unconfirmed) == 1
        assert unconfirmed[0]["source_id"] == APC
        assert unconfirmed[0]["status"] == "assumed"

    def test_an_empty_owned_but_undocumented_report_is_a_list_not_an_omission(self):
        # It is the sole resolver of a canonical device id and refills the
        # day a device is declared ahead of its manual (9.6).
        view = default_view(gaps={"owned_but_undocumented": [], "documented_but_unconfirmed": []})
        app = make_app(StubWatcher(view))
        body = get(app, "/sources").json()
        assert body["owned_but_undocumented"] == []
        assert body["documented_but_unconfirmed"] == []

    def test_an_empty_corpus_lists_nothing_but_answers(self):
        app = make_app(StubWatcher(None))
        body = get(app, "/sources").json()
        assert body["sources"] == []
        assert body["owned_but_undocumented"] == []
        assert body["documented_but_unconfirmed"] == []

    def test_the_route_runs_the_stat_change_check(self):
        app, watcher = sources_app()
        get(app, "/sources")
        assert watcher.checks == 1


class TestManifestFault:
    def test_an_unreadable_new_manifest_is_reported_while_the_live_view_serves(self):
        app, watcher = sources_app()
        watcher.manifest_fault = (
            "manifest /Users/someone/corpus/index/manifest.json is unreadable: boom"
        )
        body = get(app, "/sources").json()
        assert body["manifest_fault"] is not None
        # The live view keeps serving alongside the report.
        assert len(body["sources"]) == 3

    def test_no_filesystem_path_appears_in_any_payload(self):
        app, watcher = sources_app()
        watcher.manifest_fault = (
            "manifest /Users/someone/corpus/index/manifest.json is unreadable: boom"
        )
        response = get(app, "/sources")
        assert "/Users/someone" not in response.text

    def test_no_fault_reports_none(self):
        app, _ = sources_app()
        assert get(app, "/sources").json()["manifest_fault"] is None
