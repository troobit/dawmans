"""The five starter entries — 7.1-7.6 and 7.8.

The one test module that reads the **committed** entry store rather than a store built
in `tmp_path`: `triage/` is product content, and 7.1 makes it a deliverable. It is
evaluated against the committed section fixtures with the **real** `rig.yaml`, so what
runs in CI is the real store against real vendor prose with `manuals/` absent — and with
an **empty ledger**, which is the first-ingest case where an unresolved pointer rejects
the whole entry (2.2) rather than flagging it.

Two failure modes are worth telling apart when this module goes red:

- A **rejection** or an unresolved pointer means an entry points at a section the fixture
  corpus does not hold. Either the pointer is wrong, or the fixtures need re-cutting —
  `tools/extract_section_fixtures.py` lists the sections the starter set points at, and
  the two lists are meant to be kept in step.
- A **`term-not-in-passage` flag** means a cause makes a factual claim its cited section
  does not print (2.6). That is the check earning its keep: reword the cause in the
  manual's own vocabulary, or point at the section that documents the control.

The mandated causes of 7.2-7.6 are asserted on the cause **span** — the statement plus its
`check:` — because that is the span 2.6 checks and the span a reader is answered with. The
assertions name the control rather than the sentence, so an author may rewrite the prose
around it without failing a test about the requirement.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sections import CORPUS
from stores import SOURCES, passages

from dawmans.corpus.rig import RIG_FILE, load_rig
from dawmans.triage.loader import CorpusView, EntryOutcome, StoreOutcome, TriageLoader
from dawmans.triage.model import Entry
from dawmans.triage.pointers import Ledger
from dawmans.triage.terms import terms

ROOT = Path(__file__).resolve().parents[2]
STORE = ROOT / "triage"

NO_SOUND = "triage/no-sound-from-track.md"
DISTORTING = "triage/track-is-distorting.md"
LATENCY = "triage/latency-when-monitoring.md"
DRUM_PAD = "triage/drum-pad-triggers-wrong-sound.md"
CONTROLLER = "triage/controller-does-nothing.md"

STARTER_SET = {
    NO_SOUND: "No sound from a track",  # 7.2
    DISTORTING: "A track is distorting",  # 7.3
    LATENCY: "Latency when monitoring",  # 7.4
    DRUM_PAD: "A drum pad triggers the wrong sound",  # 7.5
    CONTROLLER: "The controller does nothing",  # 7.6
}

SCARLETT_ID = "focusrite/scarlett-solo-4g"

DELIBERATE_DISTORTION = (
    "Saturator",
    "Drum Buss",
    "Overdrive",
    "Vinyl Distortion",
    "Dynamic Tube",
    "Amp",
)
"""7.3's elimination step, verbatim: the documented content that would otherwise dominate
retrieval for the word "distortion"."""


@pytest.fixture(scope="module")
def view() -> CorpusView:
    return CorpusView.of(passages(*CORPUS), SOURCES)


@pytest.fixture(scope="module")
def outcome(view: CorpusView) -> StoreOutcome:
    """The committed store, evaluated as a first ingest against the fixture corpus."""
    loader = TriageLoader(
        store=STORE,
        view=view,
        rig=load_rig(ROOT / RIG_FILE).devices,
        ledger=Ledger.empty(),
        root=ROOT,
    )
    return loader.evaluate()


def entry_of(outcome: StoreOutcome, source_file: str) -> EntryOutcome:
    for result in outcome.outcomes:
        if result.entry.source_file.as_posix() == source_file:
            return result
    raise AssertionError(f"{source_file} is not in the store")


def spans(result: EntryOutcome) -> list[str]:
    """Each cause as the term check reads it: the statement and its `check:`."""
    return [f"{cause.statement}\n{cause.check}" for cause in result.entry.causes]


def mentions(result: EntryOutcome, phrase: str) -> bool:
    return any(phrase in span for span in spans(result))


# --- The set exists, and every entry of it ingests (7.1) --------------------


def test_the_store_holds_one_entry_for_each_of_the_five_symptoms(outcome: StoreOutcome) -> None:
    """7.1: an initial entry store containing, at minimum, one entry for each of
    7.2-7.6. The file names carry no meaning (1.8) — they are named here only so that a
    failure says which entry went missing."""
    found = {
        result.entry.source_file.as_posix(): result.entry.symptom for result in outcome.outcomes
    }

    assert found == STARTER_SET


def test_every_starter_entry_ingests_on_a_first_run(outcome: StoreOutcome) -> None:
    """7.1's "with no exemption", read through 2.2: with no ledger row anywhere, a
    pointer that does not resolve rejects its entry outright. A store that ships red
    here would refuse the five questions this source exists to answer."""
    assert outcome.rejections == ()
    assert len(outcome.ingesting) == len(STARTER_SET)


def test_the_only_flags_are_the_closing_statements(outcome: StoreOutcome) -> None:
    """Every entry closes with an "Otherwise" section, and Decision 6 identifies a
    closing statement by position rather than by title — so each one is reported as
    inferred. That flag is the design's chosen cost of having no reserved title; any
    *other* flag here is a defect in the entry, and `term-not-in-passage` above all,
    which is 2.6 catching a factual claim its section does not print."""
    raised = {flag.name for flag in outcome.flags}

    assert raised == {"closing-statement-inferred"}
    assert len(outcome.flags) == len(STARTER_SET)


def test_the_term_check_has_something_to_check(outcome: StoreOutcome) -> None:
    """The guard on the assertion above. A store whose causes named no control at all
    would raise no term flag either, and would pass every test in this module while
    grounding nothing — so the extractor is asked what it found, and it has to have
    found the controls the requirements name."""
    extracted = {
        term
        for result in outcome.ingesting
        for cause in result.entry.causes
        for term in terms(result.entry, cause)
    }

    assert {"Track Activator", "Solo", "Monitor", "Overall Latency", "General MIDI"} <= extracted


# --- §1-§4, with no exemption (7.1) ----------------------------------------


@pytest.mark.parametrize("source_file", sorted(STARTER_SET))
def test_each_entry_declares_between_two_and_six_ranked_causes(
    outcome: StoreOutcome, source_file: str
) -> None:
    """1.1 and 1.4. The closing statement is excluded from the count by position
    (Decision 6), so an entry of five causes plus an "Otherwise" is five."""
    entry: Entry = entry_of(outcome, source_file).entry

    assert 2 <= len(entry.causes) <= 6
    assert entry.closing is not None, "each starter entry closes with what to do next"


@pytest.mark.parametrize("source_file", sorted(STARTER_SET))
def test_each_cause_carries_a_check_and_a_resolving_fix(
    outcome: StoreOutcome, source_file: str
) -> None:
    """1.2 and 7.8: every cause has an observable check and a fix pointer, and every
    pointer resolves to at least one vendor passage. 2.3's carve-out admits no device
    today — all four manuals are ingested — so no cause may use it (7.8)."""
    result = entry_of(outcome, source_file)

    for cause, checked in zip(result.entry.causes, result.causes, strict=True):
        assert cause.check.strip(), f'"{cause.statement}" has no check'
        assert cause.fixes, f'"{cause.statement}" has no fix pointer'
        assert cause.undocumented_device is None, f'"{cause.statement}" claims 2.3'
        assert checked.passage_ids, f'"{cause.statement}" points at nothing'
        assert not checked.unbacked, f'"{cause.statement}" is unbacked'


@pytest.mark.parametrize("source_file", sorted(STARTER_SET))
def test_each_entry_is_scoped_to_devices_the_rig_declares(
    outcome: StoreOutcome, source_file: str
) -> None:
    """4.1 and 4.2: a scope declaration, in the identities `rig.yaml` and the corpus
    use. `scoped` is what the sidecar publishes to `api/answer-engine` 5.13 as the
    per-passage predicate; an entry that reached it empty would be in scope for every
    turn, which is 4.3's failure rather than its rule."""
    result = entry_of(outcome, source_file)
    rig_ids = {device.id for device in load_rig(ROOT / RIG_FILE).devices}

    assert result.scoped
    assert set(result.scoped) <= rig_ids


def test_the_alternative_phrasings_are_written_the_way_the_question_is_asked(
    outcome: StoreOutcome,
) -> None:
    """1.3's optional `also:` lines, carried in `Passage.text` so BM25 sees them. They
    are the only mitigation for the assumption that the author asks in the vocabulary
    they wrote in, so every starter entry offers some."""
    for result in outcome.ingesting:
        assert result.entry.phrasings, f"{result.entry.source_file} offers no phrasings"


# --- The mandated causes, one requirement at a time ------------------------


def test_no_sound_from_a_track_names_the_five_causes_7_2_requires(outcome: StoreOutcome) -> None:
    """7.2: the Track Activator off; another track soloed; Monitor set to Off; the
    output routed to nothing; a device in the chain deactivated. The routing cause is
    worded `Audio/MIDI To`, which is what Live's own In/Out section prints — `Audio To`
    appears nowhere in the routing chapter, and 2.6 is the check that says so."""
    result = entry_of(outcome, NO_SOUND)

    assert len(result.entry.causes) == 5
    assert mentions(result, "Track Activator")
    assert mentions(result, "soloed") and mentions(result, "Solo")
    assert mentions(result, "Monitor") and mentions(result, "Off")
    assert mentions(result, "Audio/MIDI To")
    assert mentions(result, "Activator toggle")


def test_a_track_is_distorting_carries_the_elimination_step_as_an_ordinary_cause(
    outcome: StoreOutcome,
) -> None:
    """7.3's elimination step names all six deliberate distortion devices, and it counts
    toward 1.4's 2-6 rather than sitting outside the ranking: it is the cause an answer
    has to eliminate before the retrieved chapter about Saturator becomes the answer to
    "why is my kick distorting"."""
    result = entry_of(outcome, DISTORTING)

    elimination = [
        span for span in spans(result) if all(name in span for name in DELIBERATE_DISTORTION)
    ]
    assert len(elimination) == 1, "one cause names all six devices"
    assert 2 <= len(result.entry.causes) <= 6


def test_a_track_is_distorting_names_a_gain_stage_a_device_output_and_the_limiter(
    outcome: StoreOutcome,
) -> None:
    """The other three causes 7.3 requires: clipping at a named gain stage — the Input
    Channel meter, which is where an interface's signal arrives — a device's output
    above `0 dB`, and the master limiter."""
    result = entry_of(outcome, DISTORTING)

    assert mentions(result, "Input Channel")
    assert mentions(result, "0 dB")
    assert mentions(result, "Limiter") and mentions(result, "Gain Reduction")


def test_the_zero_db_claim_cites_the_section_that_prints_it(
    outcome: StoreOutcome, view: CorpusView
) -> None:
    """7.3's numeric claim, and the reason the term check keeps its numeric class: `0 dB`
    is a factual assertion only the manual is entitled to make, and §18.1.1 is the
    section that prints it. Asserted against the passage text rather than against the
    flag list, so it stays true if the extractor's numeric rules ever loosen."""
    result = entry_of(outcome, DISTORTING)

    cited = [
        view.text(passage_id) or ""
        for cause, checked in zip(result.entry.causes, result.causes, strict=True)
        for passage_id in checked.passage_ids
        if "0 dB" in f"{cause.statement}\n{cause.check}"
    ]

    assert cited, "no cause claims `0 dB`"
    assert any("0 dB" in text for text in cited)


def test_latency_when_monitoring_names_the_four_causes_7_4_requires(
    outcome: StoreOutcome,
) -> None:
    """7.4: buffer size; direct monitoring on the interface; the track's monitor mode;
    the Overall Latency adjustment."""
    result = entry_of(outcome, LATENCY)

    assert mentions(result, "buffer size")
    assert mentions(result, "Direct Monitor")
    assert mentions(result, "Monitor") and mentions(result, "In")
    assert mentions(result, "Overall Latency")


def test_the_direct_monitoring_cause_cites_the_scarlett_guide(outcome: StoreOutcome) -> None:
    """7.8 with no exemption, on the cause that used to be 2.4's worked example. The
    Scarlett Solo 4th Gen guide documents DIRECT MONITOR, so the cause needs a pointer
    like any other and is rejected without one — the case has moved from the unbacked
    side of 2.3 to the backed side."""
    result = entry_of(outcome, LATENCY)

    cited = {
        pointer.source_id
        for cause in result.entry.causes
        if "Direct Monitor" in cause.statement
        for pointer in cause.fixes
    }

    assert cited == {SCARLETT_ID}


def test_a_drum_pad_triggers_the_wrong_sound_names_the_three_causes_7_5_requires(
    outcome: StoreOutcome,
) -> None:
    """7.5: the transmitted note against the Drum Rack pad's receive note; the module's
    General MIDI mode; a channel mismatch. Two of the three are documented by the drum
    module and by nothing else, which is why the module's own manual is cited."""
    result = entry_of(outcome, DRUM_PAD)

    assert mentions(result, "MIDI note number") and mentions(result, "Receive note")
    assert mentions(result, "General MIDI")
    assert mentions(result, "Channel 10") and mentions(result, "another channel")


def test_the_general_midi_cause_cites_the_module_that_has_the_mode(
    outcome: StoreOutcome,
) -> None:
    """The control the fix operates is on the module, so the module's manual is what
    documents it. Citing Live's Drum Rack section instead would resolve, pass the term
    check on `General MIDI`, and cite a manual about a different control — which is the
    failure 2.6 cannot catch and this assertion can."""
    result = entry_of(outcome, DRUM_PAD)

    cited = {
        pointer.source_id
        for cause in result.entry.causes
        if "General MIDI" in cause.statement
        for pointer in cause.fixes
    }

    assert cited == {"alesis/nitro-max"}


def test_the_controller_does_nothing_names_the_three_causes_7_6_requires(
    outcome: StoreOutcome,
) -> None:
    """7.6: the Track, Sync and Remote flags for that input or output; the control
    surface selection; track selection against the controller's bank position."""
    result = entry_of(outcome, CONTROLLER)

    assert mentions(result, "Track, Sync and Remote")
    assert mentions(result, "Control Surface")
    assert mentions(result, "bank") and mentions(result, "Session View")


def test_the_controller_entry_declares_the_revision_the_rig_holds(
    outcome: StoreOutcome,
) -> None:
    """4.6: an entry may constrain its scope to a revision, and a declaration that
    disagrees with the rig is flagged. The APC is the case the requirement was written
    for — an mk2 on the desk, the mk1 guide in the corpus — so the starter set declares
    it and the absence of `revision-mismatch` above is what says it matches."""
    result = entry_of(outcome, CONTROLLER)
    declared = {device.id: device.revision for device in result.entry.devices}

    assert declared["akai/apc-key-25"] == "mk2"
