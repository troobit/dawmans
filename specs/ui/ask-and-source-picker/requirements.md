# Requirements: Ask and Source Picker

**Domain:** `ui` · **Capability:** ask and source picker
**Mode:** full spec with iterative (target-and-band) criteria — see [`PROCESS.md`](../../PROCESS.md) §5

Shared records, the outcome taxonomy, and the latency budget are governed by
[`CONTRACTS.md`](../../CONTRACTS.md). Where this file and that one disagree, that one wins.

## Purpose

DAWMans answers home-studio questions strictly from its ingested sources — the gear manuals, and
the user's own authored triage notes (`CONTRACTS.md` §4a). This spec owns the **browser surface**:
asking a question, choosing which sources are in scope, reading the answer, and checking the
source's own words behind every claim.

## Usage context

This context is the reason for nearly every criterion below and outranks feature richness in any
trade-off:

- Ableton Live is full-screen on the main monitor. DAWMans is a browser tab on a **second screen**.
- The user is **producing music** — often with a guitar in hand or hands on the APC controller.
  They glance across, they do not sit and read. Hands-free matters; **hands-full matters more**,
  because typing forty characters costs an instrument put down.
- They are interrupted and impatient. **Speed-to-answer and legibility at a glance win** over
  completeness, configurability, and visual flourish.
- The room is often dimly lit; a dark interface is the default assumption.

## Scope

**In scope:** the ask input and its one-key starters, the source picker and the corpus gaps it
exposes, answer rendering (including partial answers and narrowing questions), citation inspection
and opening the cited source, waiting/error states across the whole outcome taxonomy, provider
configuration by provider kind, question history, legibility and accessibility targets.

**Out of scope — referenced, never restated here:**

- **`data/manual-corpus`** — PDF acquisition, parsing, chunking, indexing, and what counts as a
  "source". This surface never reads the corpus directly; everything it knows about sources arrives
  through the answer engine.
- **`data/symptom-triage`** — what an authored triage entry contains, how it is written, and what
  makes it valid. This surface renders its citations and lists it in the picker; it never authors
  or edits it.
- **`api/answer-engine`** — retrieval, grounding, synthesis, citation generation, narrowing
  judgement, and the judgement that the selected sources do not contain an answer. This spec defines
  how those outcomes are *presented*, not how they are *reached*.

## How to read the acceptance criteria

Two kinds of criterion appear, and each is marked:

- **[B] Behavioural** — hard pass/fail. It is either true of the running system or it is a defect.
- **[T] Target-and-band** — an iterative criterion per `PROCESS.md` §5. It states a *target* and an
  *acceptance band*. Work converges on the target and stops once inside the band; landing mid-band
  is "done", and the conscious trade-off is recorded in `decision_log.md`. These are verified by
  observing real output (screenshots, a stand-back test, a contrast measurement), not by assertion.

---

## 1. Asking a Question

**User Story:** As a producer mid-session, I want to land in the DAWMans tab and start typing —
or press one key — so that a question costs me seconds rather than a change of posture.

**Acceptance Criteria:**

1. <a name="1.1"></a>**[B]** WHEN the ask surface is loaded or regains window focus, the system
   SHALL place keyboard focus in the question input without requiring a pointer click.
2. <a name="1.2"></a>**[B]** WHEN the user types a printable character while focus is anywhere on
   the ask surface that is not already a text-entry field, AND no single-key selection is armed
   ([1.11](#1.11)), the system SHALL move focus to the question input and retain that character as
   the first character typed.
3. <a name="1.3"></a>**[B]** The system SHALL submit the question on a single unmodified Enter
   keypress, and SHALL insert a line break instead of submitting when Enter is pressed with the
   Shift modifier.
4. <a name="1.4"></a>**[B]** WHEN a question is submitted, the system SHALL retain the submitted
   text in an inspectable, re-editable form so that the user never has to retype a question after
   an error, a cancellation, or a scope change.
5. <a name="1.5"></a>**[B]** WHEN the question input is empty or contains only whitespace, the
   system SHALL take no action on submit and SHALL NOT contact the answer engine.
6. <a name="1.6"></a>**[B]** WHEN an answer has finished streaming, the system SHALL return
   keyboard focus to an empty question input, ready for the next question, without discarding the
   answer just rendered.
7. <a name="1.7"></a>**[B]** The system SHALL treat a question asked while a previous answer is on
   screen as a **follow-up** to that answer, and SHALL provide a single control — reachable by both
   keyboard and pointer — that discards the current thread and starts a fresh, context-free
   question.
8. <a name="1.8"></a>**[B]** WHEN a follow-up is in effect, the system SHALL indicate on screen
   that the question will be interpreted in the context of the preceding exchange.
9. <a name="1.9"></a>**[B]** WHILE an answer is streaming, the system SHALL provide a keyboard-
   reachable control that stops generation, and SHALL retain whatever text had already arrived.
10. <a name="1.10"></a>**[B]** WHILE the question input is empty, the system SHALL present a fixed
    set of **symptom shortcuts** — at minimum *no sound*, *distorting*, *latency*, and *wrong drum
    sound* — each of which submits a question in a single keypress, so that the commonest questions
    cost one key and one hand rather than a typed sentence. Each shortcut SHALL also be activatable
    by pointer and by normal keyboard navigation.
11. <a name="1.11"></a>**[B]** WHERE number keys 1–4 are armed for selection — a narrowing candidate
    list ([6.3](#6.3)), or the symptom shortcuts of [1.10](#1.10) on an empty input — the system
    SHALL treat an unmodified 1–4 keypress as that selection rather than capturing it per
    [1.2](#1.2), SHALL show on screen which keys are armed, and SHALL leave every other printable
    character capturing normally.
12. <a name="1.12"></a>**[B]** The system SHALL cost nothing to leave: WHEN the ask surface loses
    window focus (the user returns to the DAW), the system SHALL continue streaming to completion,
    SHALL retain the answer, the question text, and the scope unchanged, and SHALL keep the
    working/finished/broken state legible without focus. Nothing needed to read or act on an answer
    SHALL depend on hover or on the tab holding focus.
13. <a name="1.13"></a>**[T]** Every action needed to ask, narrow, cancel, widen scope, and open a
    citation SHALL be reachable by keyboard. **Target:** zero pointer use required for the core
    loop. **Band:** at most one secondary action (provider configuration) may require pointer use.

---

## 2. Seeing and Choosing Sources

**User Story:** As a user with several gear manuals ingested, I want to pick which manuals a
question is asked against — and to see what my corpus is missing — so that an Ableton question is
not answered from a drum-module manual and a gap does not cost me a question to discover.

**Acceptance Criteria:**

1. <a name="2.1"></a>**[B]** The system SHALL display the list of available sources as reported by
   `api/answer-engine`'s list-sources operation — the only counterpart this browser page can reach —
   showing each source's `display_name`, and SHALL NOT assume any fixed number of sources.
2. <a name="2.2"></a>**[B]** The system SHALL allow each source to be independently toggled in or
   out of scope, and each toggle SHALL be operable by keyboard alone.
3. <a name="2.3"></a>**[B]** WHEN the set of available sources reported by the engine changes (a
   source of either kind is added or removed, `CONTRACTS.md` §4a), the system SHALL reflect the
   change on the next load of the ask surface without any change to the interface itself.
4. <a name="2.4"></a>**[B]** WHEN a source the picker has not seen before appears, the system SHALL
   mark it visibly as new until the user next submits a question. It SHALL be placed **in scope**
   only WHERE the stored scope was *all* available sources; WHERE a narrowed scope is in force the
   new source SHALL stay out of scope, with a control that adds it in one activation — a newly
   ingested manual SHALL NOT silently undo a narrowing the user made on purpose (§3).
5. <a name="2.5"></a>**[B]** The system SHALL display a scope indicator that remains visible while
   the user is asking *and* while an answer is being read, stating how many sources are in scope out
   of how many are available.
6. <a name="2.6"></a>**[B]** WHEN three or fewer sources are in scope, the scope indicator SHALL
   name them rather than only counting them.
7. <a name="2.7"></a>**[B]** WHEN all available sources are in scope, the scope indicator SHALL say
   so explicitly rather than showing a bare count.
8. <a name="2.8"></a>**[B]** The system SHALL provide single controls that place **all** sources in
   scope and that place **none** in scope.
9. <a name="2.9"></a>**[B]** WHERE the engine reports hardware the user owns for which no manual is
   ingested (**owned-but-undocumented**, `CONTRACTS.md` §5), the system SHALL name that hardware in
   the picker as a known gap, listed apart from the selectable sources and never selectable, so that
   the absence is visible without spending a question on it.
10. <a name="2.10"></a>**[B]** WHERE a source's `hardware_applicability` is *assumed* rather than
    *confirmed* (**documented-but-unconfirmed**), the system SHALL mark that source in the picker,
    naming the hardware revision that source is taken to describe — the revision a `vendor-manual`
    states, or the one an authored entry assumes — so that the mismatch is known before the question
    is asked rather than only in the citation ([5.3](#5.3)).
11. <a name="2.11"></a>**[B]** The picker SHALL be collapsible to the single-line scope indicator of
    [2.5](#2.5) and SHALL be collapsed at rest once a scope has been chosen; expanding and
    collapsing SHALL each cost one activation from the keyboard. The chrome-to-content ratio in
    [11.8](#11.8) is measured **collapsed**; the no-scrolling target in [2.13](#2.13) is measured
    **expanded**.
12. <a name="2.12"></a>**[B]** WHERE the engine reports a source whose kind is `authored-triage`
    (`CONTRACTS.md` §4a) — the user's own symptom-to-cause notes rather than a manufacturer's
    document — the system SHALL list it in the picker **alongside** the manuals, SHALL state its
    kind on its entry so it is not mistaken for vendor documentation, and SHALL make it selectable
    and deselectable by exactly the same controls as any other source ([2.2](#2.2), [2.8](#2.8)).
    It SHALL NOT be rendered as a corpus gap ([2.9](#2.9)), as unselectable, or as always in scope.
13. <a name="2.13"></a>**[T]** The picker SHALL remain usable as the corpus grows. **Target:** all
    sources visible without scrolling up to 12 sources when expanded, and a text filter offered
    beyond that. **Band:** no scrolling required up to at least 8 sources; a filter offered at or
    before 16.
14. <a name="2.14"></a>**[T]** In-scope versus out-of-scope SHALL be distinguishable at a glance
    from across the room. **Target:** correct read of which sources are in scope within 1 second at
    1.5 m, without reading any body text. **Band:** correct read within 2 seconds at 1.2 m. The
    distinction SHALL NOT rely on colour alone (see [11.6](#11.6)).

---

## 3. Scope State, Edge Cases, and Persistence

**User Story:** As a returning user, I want the scope I chose to still be in force while I am
working, but not to ambush me next week with a refusal from a narrowing I have forgotten.

**Position taken:** an empty scope **blocks** submission rather than silently auto-selecting all
sources. Auto-selecting would quietly override a narrowing the user made on purpose, and sending an
empty scope to the engine would return a misleading "not found". Blocking with a one-press fix is
both honest and fast. The same reasoning bounds persistence in the other direction: a narrowing is
an in-session act, so it **decays** at the start of a new session ([3.6](#3.6)) rather than silently
governing a question asked days later mid-take.

**Acceptance Criteria:**

1. <a name="3.1"></a>**[B]** WHEN zero sources are in scope, the system SHALL NOT submit a question
   to the answer engine.
2. <a name="3.2"></a>**[B]** WHEN zero sources are in scope, the system SHALL state that no sources
   are selected and SHALL offer a control that places all sources in scope in a single activation,
   preserving any question text already typed.
3. <a name="3.3"></a>**[B]** WHEN exactly one source is in scope, the system SHALL name that source
   in the scope indicator and SHALL submit questions against it without further confirmation.
4. <a name="3.4"></a>**[B]** The system SHALL retain the current scope across successive questions
   within a session; asking a question SHALL NOT reset, widen, or narrow the scope.
5. <a name="3.5"></a>**[B]** The system SHALL persist the scope locally across page reloads within a
   session and SHALL restore it on the next load of that session.
6. <a name="3.6"></a>**[B]** WHEN a new session begins — the first load after a browser restart, or
   a load more than 8 hours after the last submitted question — AND the stored scope is narrower
   than all available sources, the system SHALL restore scope to **all available sources**, SHALL
   state that the previous narrowing was released, and SHALL offer a control that reinstates it in
   one activation.
7. <a name="3.7"></a>**[B]** WHEN no scope has ever been stored, the system SHALL start with all
   available sources in scope.
8. <a name="3.8"></a>**[B]** WHEN a persisted scope refers to a source the engine no longer reports,
   the system SHALL drop that entry silently and SHALL restore the remaining scope.
9. <a name="3.9"></a>**[B]** WHEN the scope changes while an answer is on screen, the system SHALL
   leave that answer intact and SHALL apply the new scope only to the next question.
10. <a name="3.10"></a>**[B]** WHILE a narrowed scope is in force, the system SHALL render the scope
    indicator in a state visibly distinct from the all-sources state; and WHEN the engine names an
    out-of-scope source as a likely holder of the answer ([7.4](#7.4)), the system SHALL attribute
    the gap to the narrowing then in force rather than presenting it as an absence of documentation.

---

## 4. Reading the Answer

**User Story:** As someone glancing across a room mid-take, I want the answer to start appearing
immediately and to be shaped so the instruction is the first thing I see, so that I can act and get
back to playing.

**Acceptance Criteria:**

1. <a name="4.1"></a>**[B]** WHEN the answer engine streams a response, the system SHALL render
   partial content progressively as it arrives rather than waiting for the complete answer.
2. <a name="4.2"></a>**[B]** WHILE content is streaming, the system SHALL NOT change the vertical
   position of text that has already been rendered, except in response to the user scrolling.
3. <a name="4.3"></a>**[B]** The system SHALL render the envelope's `direct_answer` first, with
   supporting detail and citations following it, in the order supplied by `api/answer-engine`.
4. <a name="4.4"></a>**[B]** The system SHALL render structural markers supplied in the answer body
   (headings, ordered steps, key terms) as visually distinct scannable elements rather than as an
   undifferentiated block of prose.
5. <a name="4.5"></a>**[B]** WHEN an answer contains a sequence of steps, the system SHALL render
   each step as a separately identifiable line or block.
6. <a name="4.6"></a>**[B]** WHEN streaming completes, the system SHALL mark the answer as
   finished in a way distinguishable from the streaming state (see [8.4](#8.4)).
7. <a name="4.7"></a>**[B]** WHEN an answer completes, the system SHALL name its
   `contributing_sources` — the in-scope sources that actually supplied passages — distinctly from
   the sources that were merely in scope, so that a controller question answered wholly from the
   Live manual is visible as such.
8. <a name="4.8"></a>**[B]** WHEN the engine returns `partially-answered`, the system SHALL render
   the answered part as a normal answer under this section, SHALL render each entry of
   `uncovered_parts[]` **visually subordinate** to it, and SHALL NOT present the exchange as a
   refusal (§7) or an error (§9).
9. <a name="4.9"></a>**[B]** WHEN a partial answer names an uncovered part, the system SHALL offer a
   control that re-asks **the uncovered part alone** in a single activation — widening scope to any
   sources the engine names for it — while leaving the answered part on screen.
10. <a name="4.10"></a>**[T]** The actionable instruction SHALL be readable without scrolling or
    hunting. **Target:** the first actionable instruction appears within the first rendered line of
    the answer and within the first 25 words. **Band:** within the first 3 rendered lines and 40
    words, and always within the initial viewport of a 1280×800 browser window.
11. <a name="4.11"></a>**[T]** Answer text SHALL be set at a comfortable measure. **Target:** 70
    characters per line. **Band:** 55–90 characters per line at default window width.
12. <a name="4.12"></a>**[T]** Key combinations SHALL be readable from the playing position —
    "what's the shortcut for X" is the most frequent well-grounded question this tool gets.
    **Target:** every key name and combination in an answer rendered as a discrete key-styled
    element, with modifier keys named as the manual names them, correctly read at 1.5 m without
    leaning in. **Band:** correctly read at 1.2 m; never set smaller than body text
    ([11.1](#11.1)).

---

## 5. Citations and Checking the Manual

**User Story:** As a user who does not want to be told something plausible and wrong, I want to see
the manual's own words behind a claim and be one keypress from the actual page, so that I can trust
or reject the summary in seconds.

**Acceptance Criteria:**

1. <a name="5.1"></a>**[B]** The system SHALL display, for each citation supplied by
   `api/answer-engine`, the source display name, the page number, and the `section_number` and
   `section_title` as the two separate fields they are (`CONTRACTS.md` §3). WHERE the source supplies
   only one of the two — an unnumbered document has no `section_number` — the system SHALL render
   the one present and SHALL NOT invent the other. A source with no pages is governed by
   [5.15](#5.15).
2. <a name="5.2"></a>**[B]** WHERE a citation carries a `doc_version` — a `vendor-manual` does, an
   authored source does not — the system SHALL display it **inline** with the citation and never
   behind a disclosure, because an answer drawn from a v1.0 guide must say so where the user is
   already looking.
3. <a name="5.3"></a>**[B]** WHERE a citation's `hardware_applicability` is *assumed* rather than
   *confirmed*, the system SHALL state **inline** with that citation which hardware revision the
   document describes and that its applicability to the user's rig is unconfirmed. This SHALL NOT be
   placed behind a disclosure.
4. <a name="5.4"></a>**[B]** WHERE a citation carries `has_figures`, the system SHALL render "figure
   on p*N*" with the citation, naming the figure's page.
5. <a name="5.5"></a>**[B]** Every citation SHALL offer a **one-activation action that opens the
   cited source at the cited location**, reachable by keyboard (`CONTRACTS.md` §3): for a
   `vendor-manual`, the source PDF at the cited page, so that a citation is never a dead-end string
   in a 1009-page document; for an `authored-triage` source, which has no pages, the entry itself,
   so that a wrong entry can be corrected at the moment it is discovered.
6. <a name="5.6"></a>**[B]** WHEN a citation is expanded, the system SHALL fetch the underlying
   passage from the engine's fetch-passage operation using the citation's `passage_id` — the passage
   text does not arrive with the answer — and SHALL display it verbatim, visually distinguishable
   from DAWMans' own summary text.
7. <a name="5.7"></a>**[B]** WHEN a citation is expanded, the system SHALL reveal the passage in
   place, without navigating away from the answer.
8. <a name="5.8"></a>**[B]** WHEN an expanded citation is collapsed, the system SHALL restore the
   reading position the user had before expanding it.
9. <a name="5.9"></a>**[B]** Citations SHALL be focusable, expandable, and openable at their cited
   location ([5.5](#5.5)) by keyboard alone.
10. <a name="5.10"></a>**[B]** WHERE an expanded passage is flagged `degraded`, the system SHALL
    mark it as containing characters that could not be read from the PDF, so that mojibake is not
    mistaken for the manual's own wording.
11. <a name="5.11"></a>**[B]** WHEN a citation's underlying passage cannot be retrieved, the system
    SHALL state that the passage is unavailable and SHALL still display the source, its cited
    location ([5.1](#5.1), [5.15](#5.15)) and the open-at-source action of [5.5](#5.5), rather than
    hiding the citation or rendering an empty area.
12. <a name="5.12"></a>**[B]** WHEN an answer arrives with no citations at all, the system SHALL
    mark the answer as uncited rather than presenting it as if it were grounded.
13. <a name="5.13"></a>**[B]** WHEN the engine sets `ungrounded` after streaming completes, the
    system SHALL mark the answer already on screen as unverified — stating that at least one claim
    has no resolvable citation — and SHALL NOT withhold, blank, or delete the rendered text.
14. <a name="5.14"></a>**[B]** WHERE a citation's source kind is `authored-triage`
    (`CONTRACTS.md` §4a), the system SHALL mark it **inline** with the citation, and never behind a
    disclosure, as the user's own note rather than manufacturer documentation — so that an answer
    resting on something the user wrote is visible as such without expanding anything. Authored and
    manufacturer citations SHALL be distinguishable from each other at rest, by a channel that
    survives greyscale ([11.6](#11.6)).
15. <a name="5.15"></a>**[B]** WHERE a citation's source has no pages — an `authored-triage` source
    (`CONTRACTS.md` §3) — the system SHALL render the entry's symptom title in the location slot of
    [5.1](#5.1), and SHALL render page and section number as absent rather than inventing either.
16. <a name="5.16"></a>**[B]** WHERE a citation carries `unbacked` — an authored cause resting on no
    vendor-manual passage, because none was ever supplied (a device with no ingested manual) or the
    pointer has stopped resolving (`CONTRACTS.md` §2) — the system SHALL mark it **inline** with the
    citation and never behind a disclosure, so that a broken or never-provided fix is never
    presented as documented.
17. <a name="5.17"></a>**[T]** Citation markers SHALL be findable without disrupting reading.
    **Target:** a citation marker is locatable within 2 seconds of deciding to check a claim, while
    contributing no more visual weight than the body text it sits beside. **Band:** markers legible
    at the reading distance in [11.2](#11.2) and never larger than body text.
18. <a name="5.18"></a>**[T]** Expanding a citation SHALL feel immediate. **Target:** passage text
    painted within 150 ms of activation, against the engine's ≤ 50 ms p95 fetch. **Band:** ≤ 300 ms;
    beyond that a working indicator ([8.2](#8.2)) appears rather than an empty area.

---

## 6. When the Question Needs Narrowing

**User Story:** As a producer who asks "the kick is distorting", I want DAWMans to ask me the one
question that separates the causes, and let me answer it with a single key, so that narrowing costs
a keystroke rather than a retyped question.

**Acceptance Criteria:**

1. <a name="6.1"></a>**[B]** WHEN the engine returns `needs-narrowing`, the system SHALL render the
   narrowing question and its candidates as the response to that turn, visually distinct from an
   answer (§4), a coverage failure (§7), and an error (§9).
2. <a name="6.2"></a>**[B]** The system SHALL render each of the 2–4 candidates as a separately
   activatable control, numbered in the order the engine supplied them, and SHALL NOT reorder,
   merge, or add candidates.
3. <a name="6.3"></a>**[B]** WHILE a candidate list awaits selection, the system SHALL select the
   corresponding candidate on a single unmodified number keypress **1–4**, and SHALL equally allow
   selection by normal keyboard navigation and by pointer. The armed keys SHALL be indicated on
   screen per [1.11](#1.11).
4. <a name="6.4"></a>**[B]** WHEN a candidate is selected, the system SHALL submit it as a
   **follow-up turn** in the current thread ([1.7](#1.7)) against the unchanged scope, and SHALL
   keep the narrowing question and the chosen candidate visible in that thread.
5. <a name="6.5"></a>**[B]** The system SHALL allow the user to ignore the narrowing question —
   typing a free-text reply or an entirely new question — without first dismissing the candidate
   list, and typing a printable character other than an armed digit SHALL begin that reply
   ([1.2](#1.2)).
6. <a name="6.6"></a>**[B]** WHEN the engine returns a **ranked list of candidate causes** instead
   of a further narrowing question, the system SHALL render the causes in the engine's order, each
   with its citations (§5), the check that would confirm or eliminate it, and the vendor-manual
   citation for the fix, rendered as an ordinary citation (§5) and distinct from the authored cause
   it belongs to ([5.14](#5.14)). WHERE the engine supplies no fix citation, the cause SHALL carry
   the `unbacked` mark of [5.16](#5.16) rather than simply appearing without one. The system SHALL
   show the ranking and SHALL NOT present the first cause as the answer.
7. <a name="6.7"></a>**[B]** The system SHALL retain a narrowing exchange in history (§12) as part
   of the thread it belongs to, and SHALL NOT retain it as a standalone unanswered question.
8. <a name="6.8"></a>**[T]** A narrowing question SHALL arrive at least as fast as an answer would.
   **Target:** the **first token of the narrowing question painted** within the keypress-to-first-
   token target of [8.8](#8.8) — 1.5 s hosted, 2.8 s local. **Band:** the acceptance band of
   [8.8](#8.8). This is a first-token target and not a completion target (`CONTRACTS.md` §7,
   `api/answer-engine` 7.3): the narrowing question SHALL NOT be held back until its candidates are
   complete.

---

## 7. When the Manuals Do Not Cover It

**User Story:** As a user who narrowed the scope, I want to be told plainly that the answer is not
in what I picked and be offered the manual that probably holds it, so that one keypress fixes it —
and when nothing ingested will ever hold it, I want to be told that instead of retrying.

**Acceptance Criteria:**

1. <a name="7.1"></a>**[B]** WHEN the engine returns `refused-not-covered`, the system SHALL state
   plainly that the in-scope sources do not cover the question and SHALL NOT render a synthesised
   answer alongside it. This criterion applies to `refused-not-covered` **only**; a
   `partially-answered` result renders as an answer per [4.8](#4.8).
2. <a name="7.2"></a>**[B]** A coverage-failure state SHALL be visually distinct from an error state
   (§9), from a narrowing question (§6), and from a normal answer.
3. <a name="7.3"></a>**[B]** The state SHALL name the sources that were in scope when the question
   was asked.
4. <a name="7.4"></a>**[B]** WHEN the engine names one or more out-of-scope sources that may contain
   the answer, the system SHALL offer a control that adds those sources to scope and re-asks the
   same question in a single activation.
5. <a name="7.5"></a>**[B]** WHEN no candidate source is suggested and out-of-scope sources exist,
   the system SHALL offer a control that widens scope to all sources and re-asks the same question
   in a single activation — EXCEPT for the `out-of-domain` and `no-manual-for-device` outcomes,
   where the engine has already judged that no ingested manual covers the question and the control
   SHALL be suppressed rather than costing the user a turn.
6. <a name="7.6"></a>**[B]** WHEN the engine returns `out-of-domain`, the system SHALL state that
   the question is about technique rather than a documented control and that no ingested source —
   neither a manual nor the authored triage notes — covers it, SHALL suppress source suggestions
   and widen-and-retry, and SHALL leave the question re-editable ([1.4](#1.4)).
7. <a name="7.7"></a>**[B]** WHEN the engine returns `no-manual-for-device`, the system SHALL name
   the `required_device` and the **exact filename** to add to `manuals/` in the convention that
   directory's README documents, in a form copyable in one activation, and SHALL state that
   ingestion must be re-run for it to take effect.
8. <a name="7.8"></a>**[B]** WHEN all available sources were already in scope, the system SHALL say
   so and SHALL NOT offer widen-and-retry; it SHALL instead offer the next action available to it —
   the device-and-filename action of [7.7](#7.7) where a required device was named, and otherwise
   re-editing the question ([1.4](#1.4)) — so that the state never dead-ends ([9.2](#9.2)).
9. <a name="7.9"></a>**[B]** WHEN a widen-and-retry is performed, the scope change SHALL persist per
   [3.5](#3.5) — the retry SHALL NOT silently revert the scope afterwards — and the widened scope
   SHALL itself decay per [3.6](#3.6) at the next session.
10. <a name="7.10"></a>**[B]** Every control offered by this section SHALL be reachable by keyboard
    from the state itself, without traversing the source picker.

---

## 8. Waiting: Working, Finished, Broken

**User Story:** As someone glancing across the room, I want to tell in one look whether DAWMans is
thinking, done, or broken, so that I do not stand there waiting on something that already failed.

**Acceptance Criteria:**

1. <a name="8.1"></a>**[B]** WHEN a question is submitted, the system SHALL render a visible state
   change acknowledging the submission before any response is received from the answer engine.
2. <a name="8.2"></a>**[B]** WHILE waiting for the first content of a response, the system SHALL
   display a continuously animated or otherwise unmistakably live working indicator, distinct from
   any static element on the surface.
3. <a name="8.3"></a>**[B]** WHILE waiting, the system SHALL keep the submitted question visible on
   screen.
4. <a name="8.4"></a>**[B]** The system SHALL render **working**, **finished**, and **broken** as
   three mutually distinguishable states, each signalled by at least two independent channels
   (for example shape and text), never by colour alone.
5. <a name="8.5"></a>**[B]** WHEN the wait for first content exceeds the threshold in
   [8.10](#8.10), the system SHALL supplement the working indicator with plain text stating that the
   answer is taking longer than usual, and SHALL offer a cancel control.
6. <a name="8.6"></a>**[B]** WHEN a request is cancelled by the user, the system SHALL return to a
   ready state with the question text preserved, and SHALL NOT present the partial output as a
   finished answer. A `cancelled` outcome the engine reports for any other reason renders per
   [9.16](#9.16).
7. <a name="8.7"></a>**[T]** Submission SHALL feel instant regardless of engine latency.
   **Target:** visible acknowledgement within 100 ms of the submit keypress. **Band:** ≤ 150 ms,
   measured from keypress to first painted state change on the development machine.
8. <a name="8.8"></a>**[T]** **Keypress to first painted answer token** — the only latency figure
   the user actually experiences, and the one the engine's stage budgets must compose into
   (`CONTRACTS.md` §7). **Target:** 1.5 s at p95 with a hosted provider, 2.8 s at p95 with a local
   provider, measured from the submit keypress to the first token of the response painted on screen.
   **Band:** ≤ 2.0 s hosted, ≤ 3.5 s local at p95; a breach is attributed using the engine's
   per-turn timings before any work is done on this surface. `CONTRACTS.md` §7 states 1.5 s / 2.8 s
   and states no band: those figures are the **target** here and the band is this criterion's
   acceptance band under `PROCESS.md` §5, not a relaxation of the contract. `CONTRACTS.md` §7 should
   record that band so the two do not read as a disagreement.
9. <a name="8.9"></a>**[T]** **Transport and paint** — the one stage of [8.8](#8.8) this surface
   owns, from the engine's first token arriving in the browser to that token painted on screen.
   **Target:** ≤ 100 ms at p95, the figure `CONTRACTS.md` §7 assigns to this surface and that
   `api/answer-engine` 4.1 budgets for. **Band:** ≤ 150 ms at p95, measured against the engine's
   per-turn timings. This is not the submission acknowledgement of [8.7](#8.7), which is measured
   from the keypress and precedes any engine response.
10. <a name="8.10"></a>**[T]** The "taking longer than usual" threshold ([8.5](#8.5)) SHALL be tuned
    **per provider class**, because a local provider is legitimately slower than a hosted one.
    **Target:** 3 seconds after submission for a hosted provider, 5 seconds for a local provider.
    **Band:** 2.5–4 s hosted, 4–8 s local; in both cases the threshold MUST sit above that class's
    observed median time-to-first-token so that a normal turn never trips it.
11. <a name="8.11"></a>**[T]** State SHALL be readable from the playing position. **Target:**
    working / finished / broken correctly identified within 1 second at 1.5 m without reading body
    text. **Band:** within 2 seconds at 1.2 m.

---

## 9. Errors

**User Story:** As a user whose setup is half-configured, I want to be told what is wrong and what
to do about it in one screen, so that I fix it instead of reading a stack trace.

**Acceptance Criteria:**

1. <a name="9.1"></a>**[B]** The system SHALL NOT display raw exception text, stack traces, or raw
   payloads as its primary error message.
2. <a name="9.2"></a>**[B]** Every error state SHALL state what happened in plain language and
   SHALL offer at least one next action, presented as an activatable control where an in-app action
   exists.
3. <a name="9.3"></a>**[B]** The system SHALL make underlying diagnostic detail available behind an
   explicit disclosure on every error state, for debugging.
4. <a name="9.4"></a>**[B]** The system SHALL render every outcome in the taxonomy of
   `CONTRACTS.md` §6 and SHALL NOT present an outcome the engine cannot emit. An outcome it does not
   recognise SHALL be rendered as a broken state carrying the engine's own wording, rather than
   being discarded or shown as an answer.
5. <a name="9.5"></a>**[B]** WHEN the engine reports `provider-unconfigured`, the system SHALL state
   which case it is — no provider chosen at all, or a **keyed hosted** provider chosen without a key
   — and SHALL offer a control that opens provider configuration (§10) directly, preserving the
   typed question. A configured **local** provider or the **shared backend** SHALL NEVER be reported
   as unconfigured on account of having no key ([10.3](#10.3)).
6. <a name="9.6"></a>**[B]** WHEN the engine reports `provider-unreachable`, the system SHALL name
   the configured provider, SHALL distinguish this from a coverage failure (§7), SHALL preserve the
   question, and SHALL offer a retry control.
7. <a name="9.7"></a>**[B]** WHEN the engine reports `timeout`, the system SHALL state that the
   **provider** stalled, attributing the stall to it and rendering it distinctly from
   `provider-unreachable` — the engine draws that distinction deliberately and this surface SHALL
   NOT collapse the two — SHALL preserve the question, and SHALL offer a retry control.
8. <a name="9.8"></a>**[B]** WHEN the engine reports `provider-rate-limited`, the system SHALL state
   that the provider is rate-limiting and SHALL render the **retry-after value** as a concrete wait,
   counting it down where one is supplied and enabling the retry control when it elapses. WHERE no
   retry-after is supplied, the system SHALL say so rather than inventing an interval.
9. <a name="9.9"></a>**[B]** WHEN the engine reports `provider-error`, the system SHALL state that
   the provider failed or rejected the request — distinctly from `provider-unreachable`
   ([9.6](#9.6)) and from `timeout` ([9.7](#9.7)) — SHALL carry the engine's own wording for it in
   the diagnostic disclosure of [9.3](#9.3), SHALL preserve the question, and SHALL offer a retry
   control.
10. <a name="9.10"></a>**[B]** WHERE a `provider-error` is caused by an invalid or expired
    credential, the system SHALL say so specifically and SHALL offer a control that opens provider
    configuration (§10) in place of the retry of [9.9](#9.9), since a retry on the same credential
    cannot succeed.
11. <a name="9.11"></a>**[B]** WHEN the engine reports `unknown-source-id`, the system SHALL name
    the identifier that was rejected, SHALL drop it from the stored scope ([3.8](#3.8)), and SHALL
    offer to re-ask against the remaining scope in one activation.
12. <a name="9.12"></a>**[B]** WHEN the engine reports `no-sources-selected` despite
    [3.1](#3.1), the system SHALL render it as the empty-scope state of [3.2](#3.2) rather than as
    an unexplained failure.
13. <a name="9.13"></a>**[B]** WHEN the engine reports `corpus-empty`, or reports no available
    sources at all, the system SHALL state that no sources of either kind are ingested — neither a
    vendor manual nor an authored triage source (`CONTRACTS.md` §4a) — SHALL name the directory
    manuals go in and the ingestion step to run, and SHALL disable submission until at least one
    source is reported.
14. <a name="9.14"></a>**[B]** WHEN the engine reports `incomplete` — synthesis stopped before the
    answer finished — or a response otherwise fails part-way through streaming, the system SHALL
    retain the partial text, SHALL mark it explicitly as incomplete rather than as a finished answer
    ([4.6](#4.6)), and SHALL offer a retry.
15. <a name="9.15"></a>**[B]** The system SHALL NOT submit a question longer than **1000
    characters** — the limit `api/answer-engine` 9.9 enforces — and SHALL state the limit and the
    length typed while the question remains editable ([1.4](#1.4)). WHERE the engine nevertheless
    rejects a request as malformed, which carries no outcome and no answer envelope and so is not
    covered by [9.4](#9.4), the system SHALL render it as a broken state naming what was rejected
    and SHALL NOT present it as a refusal (§7).
16. <a name="9.16"></a>**[B]** WHEN the engine reports `cancelled` for a turn the user did not
    cancel — a new question arrived while the previous turn was still streaming, or the connection
    dropped — the system SHALL retain whatever text arrived and mark that turn as abandoned,
    distinctly from `incomplete` ([9.14](#9.14)) and from an error, and SHALL NOT disturb the turn
    that replaced it. A cancellation the user initiated renders per [8.6](#8.6).
17. <a name="9.17"></a>**[B]** No error message SHALL contain any part of a configured provider key.
18. <a name="9.18"></a>**[T]** Errors SHALL be legible at a glance under the same conditions as
    answers. **Target:** the error's one-line summary and its action are both readable at the
    distance in [11.2](#11.2) without expanding anything. **Band:** summary readable at that
    distance; the action readable within one step closer.

---

## 10. Provider Configuration

**User Story:** As the sole operator of this local app, I want to point DAWMans at my own hosted
key, at a model running on this machine, or at the shared backend — and to know before I ask
anything which of those sends my question off the machine.

**Position taken:** configuration is expressed in terms of **provider kind**, not "the key". Two of
the three supported kinds need no user key at all, and a surface built around a key field reports a
perfectly good local provider as broken.

**Acceptance Criteria:**

1. <a name="10.1"></a>**[B]** The system SHALL provide a configuration surface where the provider
   **kind** is chosen from those the engine supports — a user-keyed hosted provider, a locally-run
   model, or the shared public backend — and SHALL request credential entry only for the keyed
   hosted kind.
2. <a name="10.2"></a>**[B]** The configuration surface SHALL be reachable from the ask surface
   without losing any typed question or the current scope.
3. <a name="10.3"></a>**[B]** WHERE a local provider is selected, the system SHALL NOT request or
   require a key, and SHALL report the provider as configured once its endpoint or model is chosen.
4. <a name="10.4"></a>**[B]** WHERE the shared public backend is selected, the system SHALL display
   the engine's required disclosure that **question text and retrieved passages leave the machine**,
   before the first turn is sent to it, SHALL require an explicit acknowledgement to proceed, and
   SHALL keep that disclosure readable on the configuration surface thereafter.
5. <a name="10.5"></a>**[B]** WHILE a key is being entered, the system SHALL mask the characters by
   default and MAY offer an explicit, momentary reveal control for the value being typed.
6. <a name="10.6"></a>**[B]** ONCE a key has been saved, the system SHALL NEVER display it in full
   again, and SHALL NEVER pre-populate any input with the stored value.
7. <a name="10.7"></a>**[B]** After configuration is saved, the system SHALL indicate the configured
   provider kind, the provider, and — for a keyed hosted provider — at most the final four
   characters of the key. The indication SHALL reflect the engine's reported provider status, not
   the browser's stored settings.
8. <a name="10.8"></a>**[B]** The system SHALL allow a stored key to be replaced or cleared, and
   clearing SHALL take effect on the next submission.
9. <a name="10.9"></a>**[B]** The system SHALL NOT place any key in the page title, the URL, browser
   history, or the question history (§12).
10. <a name="10.10"></a>**[B]** The configuration surface SHALL offer a check that reports whether
    the configured provider is reachable **as configured** — with the stored key for a keyed hosted
    provider, at its endpoint for a local model, at the shared backend otherwise — reporting
    reachable or not reachable without echoing any credential.
11. <a name="10.11"></a>**[B]** WHEN configuration is saved, the system SHALL return the user to the
    ask surface with the previously typed question and scope intact.

---

## 11. Legibility and Glanceability (iterative targets)

**User Story:** As a user two metres from the second screen in a dim room, I want to read the answer
without leaning in, so that "glance across" actually works.

Every criterion in this section is a **[T]** target-and-band criterion, verified by observing real
output — a measured contrast reading, a screenshot at scale, or a stand-back test — and not by
assertion. Where a band is exceeded deliberately, the trade-off is recorded in `decision_log.md`.

**Acceptance Criteria:**

1. <a name="11.1"></a>**[T]** Body text size. **Target:** 18 px effective size at default zoom on a
   27-inch 1440p display. **Band:** 16–22 px. Nothing that must be read to act on an answer may fall
   below 16 px; secondary metadata (page numbers, timestamps) may go to 14 px but no lower.
2. <a name="11.2"></a>**[T]** Reading distance. **Target:** answer body text read comfortably at
   1.5 m from a 27-inch display at 100% zoom. **Band:** 1.2–1.5 m. Verified by a stand-back test,
   not calculation alone.
3. <a name="11.3"></a>**[T]** Body text contrast. **Target:** ≥ 8:1 against its background.
   **Band:** ≥ 7:1 (WCAG AAA) for body and answer text; ≥ 4.5:1 for every other text element
   including secondary metadata and disabled-looking states. No text below 4.5:1 anywhere.
4. <a name="11.4"></a>**[T]** Non-text indicator contrast. **Target:** ≥ 4.5:1 for state
   indicators, focus rings, and source in/out-of-scope markers. **Band:** ≥ 3:1.
5. <a name="11.5"></a>**[T]** Dark interface. **Target:** a dark default appearance with page
   background relative luminance ≤ 0.05 and text lighter than background. **Band:** background
   relative luminance ≤ 0.08; avoid maximal-white text on maximal-black background, which reads as
   harsh in a dim room. A light appearance is not required for MVP (§ Non-Goals).
6. <a name="11.6"></a>**[T]** Colour independence. **Target:** every state distinction (in scope /
   out of scope, working / finished / broken, cited / uncited, authored / manufacturer citation
   ([5.14](#5.14)), backed / unbacked cause ([5.16](#5.16)), armed / not armed number keys) remains
   correct in greyscale. **Band:** correct
   in greyscale for all of those distinctions; verified by viewing a greyscale screenshot.
7. <a name="11.7"></a>**[T]** Reading budget before action. **Target:** the user reads no more than
   25 words to reach the actionable instruction (see [4.10](#4.10)). **Band:** ≤ 40 words.
8. <a name="11.8"></a>**[T]** Chrome-to-content ratio. **Target:** at rest, with the picker
   collapsed per [2.11](#2.11), the answer and question occupy ≥ 70% of the viewport height on a
   1280×800 window, with the scope indicator and any configuration entry point sharing the
   remainder. **Band:** ≥ 60%.
9. <a name="11.9"></a>**[T]** Motion. **Target:** no animation other than the working indicator and
   the arrival of streamed text. **Band:** any additional motion completes within 200 ms and never
   moves already-read text ([4.2](#4.2)).

**Known trade-offs — recorded, not to be satisfied twice.** Two pairs of criteria pull against each
other at their band edges, and the resolution belongs in `decision_log.md` rather than in a further
criterion:

- **[11.3](#11.3) versus [11.5](#11.5).** An 8:1 body target against a background at the dark end of
  11.5's band drives text toward maximal white, which 11.5 explicitly warns against. Resolve by
  lifting the background within 11.5's band rather than by pushing text to pure white.
- **[13.8](#13.8) versus [11.3](#11.3).** A disabled control that holds 4.5:1 does not *look*
  disabled by contrast alone. Disabledness is therefore carried by a non-contrast channel (label,
  shape, absence of a focus ring), so the contrast floor holds without the state becoming
  ambiguous — [11.6](#11.6) already requires that reading to survive greyscale.

---

## 12. History of Questions

**User Story:** As a producer who asks the same handful of things across a week, I want to find what
I asked earlier without re-asking, so that a repeat question costs nothing.

**Position taken:** history **is** retained and re-findable, but deliberately thin — a reverse-
chronological list of past questions that re-displays the stored answer. Retention is nearly free
and the same questions genuinely recur mid-session ("what did that shortcut do again"). What is
*excluded* is the feature richness that would cost glance-speed: no tagging, no folders, no export,
no full-text search UI beyond a simple filter.

**Acceptance Criteria:**

1. <a name="12.1"></a>**[B]** The system SHALL retain completed question-and-answer exchanges
   locally, surviving page reload and browser restart.
2. <a name="12.2"></a>**[B]** The system SHALL present retained exchanges in reverse-chronological
   order, showing at minimum the question text and when it was asked.
3. <a name="12.3"></a>**[B]** WHEN a retained exchange is selected, the system SHALL re-display the
   stored answer, including its citations, without re-querying the answer engine.
4. <a name="12.4"></a>**[B]** WHEN a retained exchange is re-displayed, the system SHALL show which
   sources were in scope when it was originally asked.
5. <a name="12.5"></a>**[B]** The system SHALL offer a control that re-asks a retained question
   against the *current* scope. That re-ask SHALL begin a **new conversation** — not a follow-up to
   whatever thread is on screen — and SHALL produce a new exchange rather than overwriting the old
   one. Continuing an existing thread remains available by typing the question as a follow-up
   ([1.7](#1.7)).
6. <a name="12.6"></a>**[B]** The system SHALL allow the entire history to be cleared in one
   action, with a confirmation step.
7. <a name="12.7"></a>**[B]** The system SHALL NOT retain cancelled or failed exchanges as if they
   were answers; a partial answer retained per [9.14](#9.14) SHALL be marked incomplete in history.
8. <a name="12.8"></a>**[B]** History SHALL NOT occupy the ask surface by default; it SHALL be
   reachable in one activation and dismissible in one activation.
9. <a name="12.9"></a>**[T]** Retention depth. **Target:** the most recent 50 exchanges retained.
   **Band:** 20–100, bounded so that stored history never delays the ask surface becoming
   interactive beyond the budget in [8.7](#8.7).

---

## 13. Accessibility Basics

**User Story:** As a user operating with hands on a controller or a guitar, and sometimes in poor
light, I want the whole surface to work from the keyboard with clearly visible focus, so that the
interface never becomes the obstacle.

**Acceptance Criteria:**

1. <a name="13.1"></a>**[B]** Every interactive element SHALL be reachable and operable by keyboard
   alone, in a focus order that follows the visual order of the surface.
2. <a name="13.2"></a>**[B]** The currently focused element SHALL carry a visible focus indicator
   that meets the contrast target in [11.4](#11.4) and is not conveyed by colour alone.
3. <a name="13.3"></a>**[B]** The system SHALL NOT trap keyboard focus; any surface that takes focus
   (source picker, configuration, history, expanded citation) SHALL be dismissible from the
   keyboard, returning focus to the element that opened it.
4. <a name="13.4"></a>**[B]** Every control SHALL expose an accessible name, and every toggle SHALL
   expose its current on/off state to assistive technology.
5. <a name="13.5"></a>**[B]** WHEN a response begins streaming, completes, fails, returns a
   coverage failure (§7), returns a **partial answer** ([4.8](#4.8)), or returns a **narrowing
   question** (§6), the system SHALL announce the state change to assistive technology without
   repeatedly announcing every streamed fragment. A narrowing announcement SHALL include the
   candidates and that number keys select them ([6.3](#6.3)).
6. <a name="13.6"></a>**[B]** WHEN the operating system requests reduced motion, the system SHALL
   replace animated indicators with non-animated equivalents that still satisfy [8.4](#8.4).
7. <a name="13.7"></a>**[B]** The layout SHALL remain usable and free of horizontal scrolling when
   browser text size is increased to 200%.
8. <a name="13.8"></a>**[B]** All contrast requirements in §11 SHALL hold for interactive states
   (hover, focus, active, disabled) as well as at rest.

---

## Non-Goals

These were considered and deliberately excluded from this capability. They are recorded so a future
reader knows they were weighed, not overlooked.

- **Native desktop application or always-on-top overlay.** Rejected for MVP: a localhost browser tab
  on a second screen already sits beside the DAW, and a native shell adds packaging and distribution
  cost before the answer quality is proven. A later native shell remains possible, so this spec
  avoids depending on browser-only assumptions where a cheap alternative exists — but the shell
  itself is out of scope here. Returning window focus to Live is one of the things only such a shell
  could do; [1.12](#1.12) states what the browser tab can guarantee instead.
- **Speech recognition of DAWMans' own.** DAWMans ships no speech recognition and no spoken answers.
  The question input is an ordinary text field, so the operating system's own dictation works in it
  if the user wants it; the app neither bundles, requires, nor tunes any recogniser, because a
  studio is a microphone-live environment and a recognition failure mid-take costs more than typing.
  The one-keypress symptom shortcuts ([1.10](#1.10)) are this spec's answer to hands-full asking.
- **Mobile or tablet application.** Rejected: the usage context is a second monitor beside a DAW.
  Responsive behaviour below tablet width is not a goal.
- **PDF ingestion, parsing, or an in-app manual reader.** Owned by `data/manual-corpus`. This
  surface shows cited passages and hands the cited source off to be opened at its cited location —
  the operating system's PDF viewer for a vendor manual, the entry itself for an authored triage
  source ([5.5](#5.5)); it does not render, page through, or search whole documents itself.
- **Retrieval, grounding, synthesis quality, citation generation, or the narrowing judgement.**
  Owned by `api/answer-engine`. This spec renders what that engine emits.
- **Declaring or editing the rig inventory.** The picker *surfaces* owned-but-undocumented gear
  ([2.9](#2.9)) and unconfirmed applicability ([2.10](#2.10)); declaring what hardware the user owns
  happens outside this browser surface.
- **Multi-user support, accounts, authentication, or sharing.** Single local operator.
- **A light appearance / theme switching.** The room is dim; a dark default is the design position
  for MVP.
- **General web search or ungrounded fallback answers.** DAWMans answers from its ingested sources —
  vendor manuals and the user's own authored triage notes, both cited (`CONTRACTS.md` §4a) — or says
  it cannot. An answer from the triage source is not a fallback: it is grounded and cited like any
  other, and marked as the user's own ([5.14](#5.14)). What remains excluded is anything uncited,
  which would destroy the trust the citation model is built on.
- **Authoring or editing the triage source.** The picker selects it ([2.12](#2.12)), citations
  attribute it ([5.14](#5.14)), and the open-at-source action hands a wrong entry off to be
  corrected where it lives ([5.5](#5.5)); writing and validating its entries belong to
  `data/symptom-triage` and happen outside this browser surface.
- **Exporting, printing, or annotating answers.**
- **In-app corpus management (adding, removing, or re-ingesting manuals from the browser).** The
  surface names the file to add ([7.7](#7.7)); adding it and re-running ingestion happen outside.

---

## Assumptions and Risks

**Assumptions**

- A single trusted local user on macOS, on `localhost`, with no authentication boundary inside the
  application.
- **`api/answer-engine`'s loopback HTTP service is this surface's only counterpart.** Everything it
  knows arrives through the eight operations that engine names (`api/answer-engine` 9.4):
  submit-question (streaming), fetch-passage by identifier, list-sources, get-provider-status,
  set-provider (choosing a provider kind), set-credential, clear-credential, and test-provider
  (reachability without a turn). The last four back §10. It never reads the corpus, the index, or
  the filesystem.
- The engine emits exactly the outcome taxonomy of `CONTRACTS.md` §6 and the envelope fields of §4,
  and this surface consumes them without extension or invention.
- A provider may be a keyed hosted provider, a locally-run model, or the shared public backend. **A
  user key is not always present, and its absence is not a misconfiguration.**
- A cited source can be opened at its cited location from outside this surface ([5.5](#5.5)): the
  operating system can open a local PDF at a given page, with the files remaining in `manuals/`
  under the names their source identity was derived from; and an authored triage entry can be
  opened at the entry itself, where it can be corrected.
- The second screen is at least 1280×800 of usable browser viewport at 100% zoom.
- Three vendor manuals exist today (Ableton Live 12 reference manual, Akai APC Key 25 user guide,
  Alesis Nitro Max drum module user guide), joined by the user's authored triage source; more will
  follow. Nothing in this spec may assume that count, or that every source is a manual
  ([2.12](#2.12)).

**Risks**

- **Provider key at rest.** A key stored locally by a keyless local app is recoverable by anything
  with filesystem access. [10.6](#10.6)–[10.9](#10.9) prevent the key being read *off the screen*;
  they do not make local storage secure. If a stronger posture is wanted, it is a `platform`
  concern, not a UI one.
- **End-to-end latency is mostly not ours.** [8.8](#8.8) is the figure the user experiences, but the
  only stage of it this surface owns is the 100 ms of transport and paint in [8.9](#8.9);
  [8.7](#8.7) is submission acknowledgement, which is a different measurement. If provider
  time-to-first-token is consistently poor, no UI work here fixes it, and [8.10](#8.10) will need
  retuning per provider class against observed data.
- **The trip back to Live is unbudgeted.** Reading the answer costs a glance across, and resuming
  work costs a click into Ableton to restore its keyboard focus. That round trip appears in no
  latency budget in this spec or in `CONTRACTS.md` §7, and it may dominate the numbers those budgets
  do cover. [1.12](#1.12) minimises it; it does not measure it.
- **Open-at-source can dead-end outside the app.** [5.5](#5.5) depends on a vendor manual's PDF
  still being present under its expected name and on the viewer honouring a page target, and on an
  authored entry still being where the citation says it is. When either fails the citation must
  degrade to its string form rather than to a broken action.
- **Provenance marking costs glance budget too.** [5.14](#5.14) puts an inline "your own note"
  marker on every authored citation and [5.16](#5.16) an inline "no manual behind this" marker on
  every unbacked cause, on top of the applicability caveat above, and all of them compete with
  [11.7](#11.7)'s 25-word reading budget. Provenance wins on trust, but it has to be carried by
  compact markers rather than sentences.
- **Scope decay cuts both ways.** [3.6](#3.6) protects the user from a forgotten narrowing, but it
  also discards a narrowing that was deliberate and long-lived. The one-activation reinstate is the
  mitigation; if users reinstate constantly, the 8-hour boundary is wrong.
- **Applicability caveats cost glance budget.** [5.3](#5.3) puts "describes the original APC Key 25,
  unconfirmed for your rig" inline on every affected citation. Repeated across an answer this
  competes directly with [11.7](#11.7)'s 25-word reading budget; the caveat wins on correctness, but
  its wording must stay short.
- **Coverage-failure quality is inherited.** [7.4](#7.4) depends on the engine suggesting a
  plausible out-of-scope source. If suggestions are poor, the widen-and-retry loop trains the user
  to simply select all sources always — which would make the picker decorative and is the signal to
  revisit this design.
- **Legibility targets are judgement-verified.** The §11 bands are measurable but need real
  observation (stand-back test, greyscale screenshot, contrast reading); they cannot be fully
  asserted in automated tests, so they can silently drift as the interface changes.
- **Single-key affordances versus typing.** [1.11](#1.11) reserves 1–4 whenever candidates or
  symptom shortcuts are armed, so a question the user intends to begin with a digit needs the input
  focused first. The visible arming indicator is the mitigation; if this bites in practice, the
  shortcut keys move rather than the capture rule.
- **Follow-up context versus scope.** [1.7](#1.7) makes a question a follow-up by default. If the
  user changes scope mid-thread ([3.9](#3.9)), the follow-up context and the new scope may
  disagree; the resulting behaviour is the answer engine's to define and may confuse.
- **History growth.** [12.9](#12.9) bounds retention, but stored answers include cited passages and
  may grow faster than expected; the bound may need lowering to protect [8.7](#8.7).
