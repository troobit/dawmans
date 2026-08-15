"""Device scope derivation (5.12) and the passage predicate (5.13).

The scope is derived over source kind: vendor manuals carry applicability at
the source level, authored entries carry it per passage in the sidecar, and
the authored source itself contributes nothing — reading a device off it
would yield None and poison the set. The predicate is a filter, never a
ranking input (design §Device scope).
"""

from corpus_fixtures import (
    EMPTY_GAPS,
    make_view,
    passage,
    sidecar_entry,
    triage_source,
    vendor_source,
)

from dawmans.answer.scope import device_scope, in_device_scope

SOURCES = [
    vendor_source("ableton/live-12", "ableton/live-12", page_count=1009),
    vendor_source("akai/apc-key-25", "akai/apc-key-25", page_count=5, status="assumed"),
    # The device id deliberately differs from the source id: scope reads
    # hardware_applicability.device, never the source id.
    vendor_source("focusrite/scarlett-solo-4g", "focusrite/scarlett-solo", page_count=20),
    triage_source(),
]

PASSAGES = [
    passage("ableton/live-12#l1", "The Track Activator mutes the track output"),
    passage("akai/apc-key-25#a1", "Hold SHIFT and press a pad to select a scene"),
    passage("focusrite/scarlett-solo-4g#s1", "The DIRECT MONITOR switch routes input to output"),
    passage("authored/triage#t1", "No sound from a track although the meters move"),
    passage("authored/triage#t2", "Crackling under load points at the buffer or the interface"),
    passage("authored/triage#t3", "The mixer's USB return channel is muted"),
    passage("authored/triage#t4", "Check the master cue mix before anything else"),
    passage("authored/triage#t5", "The new interface's direct monitor blend is fully wet"),
]

SIDECAR = [
    sidecar_entry("authored/triage#t1", ["ableton/live-12"]),
    sidecar_entry("authored/triage#t2", ["focusrite/scarlett-solo"]),
    # A device with neither an ingested manual nor a gap entry: unreachable
    # in every scope until either exists.
    sidecar_entry("authored/triage#t3", ["behringer/x32"]),
    # t4 declares nothing — no sidecar entry — and is scoped by source alone.
    sidecar_entry("authored/triage#t5", ["focusrite/scarlett-2i2"]),
]

# The Decision 12 dormancy: the live corpus's owned-but-undocumented report
# is empty, so the non-empty case runs against this fixture report only.
GAPS_WITH_2I2 = {
    "owned_but_undocumented": [
        {"device": "focusrite/scarlett-2i2", "display_name": "Focusrite Scarlett 2i2"}
    ],
    "documented_but_unconfirmed": [],
}


def build_view(gaps=EMPTY_GAPS):
    return make_view(SOURCES, PASSAGES, gaps=gaps, sidecar=SIDECAR)


class TestDeviceScope:
    def test_selected_vendor_devices_unioned_with_the_gaps(self):
        view = build_view(gaps=GAPS_WITH_2I2)

        scope = device_scope(view, ["ableton/live-12", "authored/triage"])

        # The authored source contributes nothing — no None in the set — and
        # the gap device is admitted although no source for it is selectable.
        assert scope == {"ableton/live-12", "focusrite/scarlett-2i2"}

    def test_scope_reads_the_applicability_device_not_the_source_id(self):
        view = build_view()

        scope = device_scope(view, ["focusrite/scarlett-solo-4g"])

        assert scope == {"focusrite/scarlett-solo"}

    def test_no_vendor_manual_selected_widens_to_every_indexed_device(self):
        # A triage-only turn is asking about the rig, not about a document:
        # the scope is every indexed vendor-manual device plus the gaps,
        # derivable from sources.json and gaps.json alone — rig.yaml is
        # never read and the view carries nothing from it.
        view = build_view(gaps=GAPS_WITH_2I2)

        scope = device_scope(view, ["authored/triage"])

        assert scope == {
            "ableton/live-12",
            "akai/apc-key-25",
            "focusrite/scarlett-solo",
            "focusrite/scarlett-2i2",
        }

    def test_the_union_is_computed_although_the_live_report_is_empty(self):
        # Decision 12 dormancy: with the live (empty) report the union adds
        # nothing; the moment a fixture report declares a device, the same
        # union admits it. No code path special-cases the empty report.
        view_live = build_view()
        view_gap = build_view(gaps=GAPS_WITH_2I2)

        assert "focusrite/scarlett-2i2" not in device_scope(view_live, ["ableton/live-12"])
        assert "focusrite/scarlett-2i2" in device_scope(view_gap, ["ableton/live-12"])


class TestPassagePredicate:
    def test_a_disjoint_declaration_excludes_the_passage(self):
        view = build_view()
        scope = device_scope(view, ["ableton/live-12"])

        # Filter, never merely ranked lower: the predicate is boolean and
        # device-match closeness is not computed anywhere (5.13 permits it
        # for ranking; there is no evaluation set to tune it with).
        verdict = in_device_scope(view, "authored/triage#t2", scope)
        assert verdict is False

    def test_a_declared_device_in_scope_admits_the_passage(self):
        view = build_view()
        scope = device_scope(view, ["ableton/live-12"])

        assert in_device_scope(view, "authored/triage#t1", scope) is True

    def test_a_passage_declaring_none_is_scoped_by_its_source_alone(self):
        view = build_view()
        scope = device_scope(view, ["ableton/live-12"])

        # No sidecar entry — a vendor passage, or an authored one declaring
        # nothing — passes on source membership alone.
        assert in_device_scope(view, "ableton/live-12#l1", scope) is True
        assert in_device_scope(view, "authored/triage#t4", scope) is True

    def test_selecting_the_triage_source_does_not_put_every_entry_in_scope(self):
        # data/symptom-triage 4.3: one selected source, yet an entry whose
        # declared device is neither documented nor a gap stays unreachable.
        view = build_view()
        scope = device_scope(view, ["authored/triage"])

        assert in_device_scope(view, "authored/triage#t1", scope) is True
        assert in_device_scope(view, "authored/triage#t2", scope) is True
        assert in_device_scope(view, "authored/triage#t3", scope) is False

    def test_a_gap_device_entry_is_reachable_in_every_scope(self):
        # 2.10: the entry written for the undocumented device must stay
        # retrievable although no source for that device is selectable.
        view = build_view(gaps=GAPS_WITH_2I2)

        for selected in (["ableton/live-12"], ["authored/triage"]):
            scope = device_scope(view, selected)
            assert in_device_scope(view, "authored/triage#t5", scope) is True
