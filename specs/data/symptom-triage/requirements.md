# Requirements: Symptom Triage

**Domain:** `data` · **Capability:** symptom-triage · **Status:** draft

## Purpose

DAWMans answers strictly from what it has ingested. This spec owns the second source kind of
[`CONTRACTS.md`](../../CONTRACTS.md) §4a — **`authored-triage`**: a hand-written symptom-to-cause
knowledge source that the studio owner maintains, ingested, retrieved and cited exactly like a
vendor manual.

It exists because the manuals cannot answer the questions actually asked mid-session. Measured
against the real corpus: the phrase **"gain staging" appears zero times** in the 1009-page Ableton
Live 12 reference manual, and **"troubleshoot" appears twice**. Live's manual documents the Track
Activator as *"to mute the track's output, turn off the Track Activator"* — an instruction for
muting, never as a **cause** of silence. A reference manual documents what a control **is** and
**does**; it does not document what good practice is, nor which control to suspect when something
is wrong. Consequently a strictly manual-grounded system refuses the two questions a producer asks
most often — *"why is my kick distorting"*, *"no sound from track 3"* — and the answer engine's
narrowing flow is unimplementable as specified, because it requires candidates "drawn from the
distinguishing conditions in the retrieved passages" and no passage in the corpus contains such
conditions.

This source closes that gap **without weakening grounding**. Entries are retrieved, ranked and
cited like any other source; their provenance is visibly the user rather than the manufacturer; and
every fix an entry points to still cites a vendor manual passage. The entry supplies the *causal
link* — which documented control to check, and in what order. The manual still supplies every
*fact* about what that control does.

**In scope:** the structure of a triage entry, the grounding rules that keep it honest, its
ingestion into `Passage` records, the declaration of which gear an entry applies to, the authoring
and validation loop, coverage reporting, an initial set of entries, and what happens to an entry's
pointers when the manuals underneath it change.

**Out of scope (owned elsewhere):** PDF discovery, extraction, chunking and the corpus inventory
belong to [`data/manual-corpus`](../manual-corpus/requirements.md) and are **not restated here**;
retrieval, ranking, narrowing and answer synthesis belong to
[`api/answer-engine`](../../api/answer-engine/requirements.md); rendering provenance and citations
belongs to [`ui/ask-and-source-picker`](../../ui/ask-and-source-picker/requirements.md).
[`CONTRACTS.md`](../../CONTRACTS.md) is governing; where this spec and it disagree, it wins.

## Terms

- **Entry** — one symptom and its ranked candidate causes. The unit an author writes, and the unit
  of retrieval and citation.
- **Symptom** — the observable complaint an entry answers, phrased as a producer would say it.
- **Cause** — one candidate explanation for a symptom, carrying its check and its fix pointer.
- **Check** — an observation the user can make on screen or on the hardware that confirms or
  eliminates a cause, with no interpretation required.
- **Fix pointer** — the reference from a cause to the vendor-manual passage that documents the
  control the fix operates.
- **Scope declaration** — the devices and software an entry applies to.
- **Rejection / failure** — as defined by [`data/manual-corpus`](../manual-corpus/requirements.md):
  a rejection is expected and per-entry, and the run still succeeds; a failure is unexpected and
  fails the run.

---

## 1. Entry Structure

**User Story:** As the studio owner, I want to write down what I check when something is wrong, in
a plain text file at the desk, so that capturing a hard-won diagnosis takes a minute rather than a
tooling exercise.

**Acceptance Criteria:**

1. <a name="1.1"></a>The system SHALL require every entry to carry: one symptom statement, a scope
   declaration ([§4](#4-scope-declaration)), and at least two candidate causes in an explicit order
   of likelihood, most likely first.
2. <a name="1.2"></a>The system SHALL require every cause to carry: a statement of the cause, one
   observable check that confirms or eliminates it, and a fix pointer ([§2](#2-grounding-discipline)).
3. <a name="1.3"></a>The system SHALL treat as optional, and SHALL ingest an entry without them:
   alternative phrasings of the symptom, an explanation of why a cause is ordered where it is,
   free-text notes, and a closing statement of what to do when every cause is eliminated.
4. <a name="1.4"></a>The system SHALL require an entry to declare between 2 and 6 candidate causes,
   and SHALL reject an entry with more. A list longer than six is a reference chapter, not a
   triage order, and destroys the ranking that makes the entry useful.
5. <a name="1.5"></a>The system SHALL preserve the author's declared cause order exactly, and SHALL
   NOT re-order, merge or deduplicate causes during ingestion.
6. <a name="1.6"></a>The system SHALL hold entries in a location the author owns, sibling to the
   manuals directory, and SHALL discover them by scanning it on every ingestion run rather than
   from any hard-coded list of expected entries.
7. <a name="1.7"></a>The system SHALL require the entry store to have all of the following
   properties, and SHALL NOT require any other tool to author or edit an entry:
   - **plain text**, readable and editable in any text editor, on a laptop, mid-session;
   - **line-oriented**, so that a change to one entry shows as a small, reviewable difference;
   - **independently editable per entry**, so that adding or removing one entry does not require
     touching another;
   - **self-describing**, with the structure of [1.1](#1.1)–[1.2](#1.2) visible in the text itself
     and no separate registry, index or database the author must keep in step;
   - **free of hand-computed values** — the author SHALL NOT be required to mint identifiers,
     compute offsets, or maintain cross-reference numbering by hand.
8. <a name="1.8"></a>The system SHALL derive an entry's stable identity from its own declared
   content, and SHALL NOT require the author to supply an identifier.
9. <a name="1.9"></a>WHEN two entries declare the same symptom within the same scope, the system
   SHALL reject both and report the duplication, rather than silently retrieving one of them.

## 2. Grounding Discipline

**User Story:** As the studio owner, I want my own notes held to the same evidential standard as
the manuals, so that this file does not quietly become the place where folklore accumulates and
gets cited back to me as fact.

**Acceptance Criteria:**

1. <a name="2.1"></a>The system SHALL require every cause's fix pointer to resolve to a real passage
   in an ingested `vendor-manual` source, and SHALL verify that resolution on every ingestion run
   rather than only when the entry is first added.
2. <a name="2.2"></a>WHEN an entry is ingested for the first time and any of its fix pointers does
   not resolve, the system SHALL **reject that entry**, name the entry, the cause and the pointer,
   and continue ingesting the remaining entries. Rejection is correct here and flagging is not: the
   author is present, and an entry that has never resolved has never been verified by anyone.
3. <a name="2.3"></a>The system SHALL permit a cause with no fix pointer **only** where the cause
   names a device that is in the rig inventory and has no ingested source (today, the Focusrite
   Scarlett Solo), and SHALL require such a cause to declare that device explicitly.
4. <a name="2.4"></a>WHEN a cause is permitted under [2.3](#2.3), the system SHALL set `unbacked`
   (CONTRACTS §2) on every passage carrying that cause, so that a citation drawn from it is marked
   as resting on no vendor manual ([§3](#3-citation-and-provenance)). "Check DIRECT MONITOR on the
   interface" is a legitimate triage step for hardware whose manual the corpus does not hold;
   presenting it as documented is not. WHERE a passage carries several causes ([3.3](#3.3)) and only
   some of them are unbacked, the system SHALL still set the flag and SHALL name the unbacked cause
   in the coverage report ([6.4](#6.4)): over-marking a passage costs the user a caveat, whereas
   under-marking presents an uncited step as documented.
5. <a name="2.5"></a>The system SHALL permit an entry to assert a **causal** relationship that no
   manual states — that a given control, when in a given state, produces the symptom. This is the
   entry's purpose and SHALL NOT be treated as an ungrounded claim, per CONTRACTS §8's split
   between grounding and reasoning.
6. <a name="2.6"></a>The system SHALL require any claim about **what a control does, what it is
   called, where it is, or what values it takes** to rest on the cause's fix pointer, and SHALL
   flag an entry naming a control, parameter or numeric value in a cause that does not appear in
   the passage that cause points to, identifying the term that does not appear. This check is what
   separates a causal assertion the author is entitled to make from a factual assertion only the
   manual is entitled to make.
7. <a name="2.7"></a>The system SHALL reject an entry whose fix pointer resolves to another
   `authored-triage` passage. An authored source SHALL NOT ground an authored source.
8. <a name="2.8"></a>The system SHALL report, per ingestion run, the number of pointers checked,
   resolved, unresolved, and permitted-without-a-pointer under [2.3](#2.3).

## 3. Citation and Provenance

**User Story:** As the studio owner, I want to see at a glance whether an answer rested on Ableton's
manual or on a note I wrote myself, so that I can weigh it accordingly without opening anything.

**Acceptance Criteria:**

1. <a name="3.1"></a>The system SHALL register the authored entries as a single source of kind
   `authored-triage`, with a `SourceRecord` per CONTRACTS §1 whose source ID is derived from the
   source's own content and is independent of any filename, and whose display name identifies the
   source as the user's own triage notes rather than a manufacturer document.
2. <a name="3.2"></a>The system SHALL emit `Passage` records per CONTRACTS §2 for every ingested
   entry, carrying the same field set as any other passage, so that retrieval, ranking and citation
   treat a triage passage identically to a manual passage.
3. <a name="3.3"></a>The system SHALL emit one passage per entry where the entry fits within the
   maximum chunk size; WHEN it does not, the system SHALL split between causes, never within a
   cause, and SHALL repeat the symptom statement in each resulting passage so that a cause is never
   retrieved without the symptom it belongs to.
4. <a name="3.4"></a>The system SHALL set each passage's `section_title` to the entry's symptom
   statement, and SHALL record **no** `section_number`: an authored source has no numbering, and
   CONTRACTS §2 forbids inventing one.
5. <a name="3.5"></a>The system SHALL record no `page_start` and no `page_end` for an authored
   passage and SHALL NOT synthesise either, per CONTRACTS §2's rule for pageless sources. It SHALL
   supply the entry's symptom statement as the location the citation carries, and the entry itself
   as the target the one-activation action of CONTRACTS §3 resolves to in place of a PDF page. How
   both are rendered is CONTRACTS §3's rule and is not restated here.
6. <a name="3.6"></a>The system SHALL record every authored passage as not `degraded` and without
   figures: authored text is plain, is written by the user, and has no image content to point at.
7. <a name="3.7"></a>The system SHALL resolve every passage and citation drawn from an entry to the
   `SourceRecord` of [3.1](#3.1), so that the `kind` CONTRACTS §1 requires to reach the user is
   available on all of them. How provenance is rendered is CONTRACTS §3's rule and is not restated
   here.
8. <a name="3.8"></a>The system SHALL record one source-level `hardware_applicability` (CONTRACTS
   §1) on the `SourceRecord` of [3.1](#3.1), being `assumed` unless the author has explicitly
   declared it confirmed, and SHALL NOT derive `confirmed` from an entry's declared device matching
   the rig inventory. A name match is an automatic inference, which CONTRACTS §1 forbids and
   [`data/manual-corpus`](../manual-corpus/requirements.md#11.2) 11.2 forbids again: an undeclared
   source is unverified, not verified. Because [3.1](#3.1) registers every entry under a single
   `SourceRecord`, this value cannot vary per entry; the devices an entry declares are carried
   separately as passage-level data under [4.3](#4.3).
9. <a name="3.9"></a>The system SHALL give every authored passage a content-derived `passage_id`
   satisfying the stability contract of CONTRACTS §2, so that a citation held in retained history
   still resolves after the entries are re-ingested.

## 4. Scope Declaration

**User Story:** As the studio owner, I want an entry about Live's routing to stay out of the way
when I ask about the drum module, so that triage narrows the problem instead of widening it.

**Acceptance Criteria:**

1. <a name="4.1"></a>The system SHALL require every entry to declare the devices and software it
   applies to, and SHALL reject an entry with no scope declaration.
2. <a name="4.2"></a>The system SHALL require a scope declaration to name devices and software using
   the same identities the rig inventory and the corpus inventory use, so that a declaration can be
   matched rather than guessed at.
3. <a name="4.3"></a>The system SHALL carry each entry's declared scope as passage-level data, keyed
   by the `passage_id` of every passage emitted for that entry, and SHALL publish it to
   [`api/answer-engine`](../../api/answer-engine/requirements.md#5-source-scoping) as the input to
   the **per-passage scope predicate** that spec's §5 evaluates.
   WHERE the engine evaluates that predicate, an entry none of whose declared devices or software is
   in scope for a turn SHALL be **excluded from retrieval for that turn, not merely ranked lower**:
   a triage entry for hardware the question is not about widens the problem rather than narrowing
   it, and ranking it lower still admits it under the per-source floor of `api/answer-engine` 5.6.
   This spec's obligation ends at publishing the declaration. It cannot filter within a selected
   source itself, because the engine's grounding scope is a set of selected source IDs and
   [3.1](#3.1) registers every entry under one of them.
4. <a name="4.4"></a>The system SHALL permit an entry to declare scope on a device that is in the
   rig inventory but has no ingested source, and SHALL report every such entry as applying to an
   undocumented device.
5. <a name="4.5"></a>WHEN an entry declares a device or software that is neither in the rig
   inventory nor an ingested source, the system SHALL flag the entry and name the unrecognised
   declaration, so that a typo does not silently produce an entry that can never be retrieved.
6. <a name="4.6"></a>The system SHALL permit an entry to constrain its scope to an edition or
   revision — Live 12 Standard as distinct from Suite, an APC Key 25 mk2 as distinct from the
   original — and SHALL flag an entry whose declared edition is not the edition in the rig
   inventory. A triage step that names a Suite-only or Max for Live device is useless on this rig
   (CONTRACTS §8).

## 5. Authoring Workflow and Validation

**User Story:** As the studio owner, I want to fix a wrong entry between takes and have the fix live
immediately, and I want to be told what is wrong in words I can act on rather than in the
vocabulary of the program.

**Acceptance Criteria:**

1. <a name="5.1"></a>WHEN an entry is added, edited or removed, the next ingestion run SHALL reflect
   the change with no code change, no configuration change and no rebuild of the application.
2. <a name="5.2"></a>The system SHALL treat a malformed or unresolvable entry as a **rejection**: it
   SHALL exclude that entry, report the reason, ingest every other entry, and still report the run
   as succeeded. One bad entry SHALL NOT cost the user the other entries.
3. <a name="5.3"></a>The system SHALL identify every validation message by the entry's symptom
   statement and, where applicable, the cause concerned, and SHALL state what is wrong and what to
   change in terms of the entry's own content. A message SHALL NOT consist solely of a position or
   an internal error name.
4. <a name="5.4"></a>The system SHALL be able to validate the entry store and report the result
   **without** modifying the index, so that an author can check work before committing to it.
5. <a name="5.5"></a>The system SHALL report, per run, the number of entries ingested, rejected and
   flagged, with a reason for each rejection and each flag.
6. <a name="5.6"></a>The system SHALL complete ingestion and validation of an entry store of up to
   200 entries in under 5 seconds, including re-checking every fix pointer ([2.1](#2.1)).
7. <a name="5.7"></a>The system SHALL re-ingest the authored source without re-extracting,
   re-chunking or re-indexing any vendor manual.

## 6. Coverage Reporting

**User Story:** As the studio owner, I want to see which symptoms I have covered while I am at my
desk with time to write, not discover the gap at 1 a.m. with a track half-finished.

**Acceptance Criteria:**

1. <a name="6.1"></a>The system SHALL report every entry with its symptom, its declared scope, its
   number of causes, and whether every one of its fix pointers currently resolves.
2. <a name="6.2"></a>The system SHALL report every entry that was rejected or flagged, with the
   reason, so that the report covers 100% of the entry store rather than only what was ingested.
3. <a name="6.3"></a>The system SHALL report every device and software item in the rig inventory for
   which no entry declares scope.
4. <a name="6.4"></a>The system SHALL report every cause permitted without a fix pointer under
   [2.3](#2.3), with the undocumented device it names.
5. <a name="6.5"></a>The system SHALL make the report obtainable without asking a question, so that
   coverage can be reviewed outside a session.
6. <a name="6.6"></a>The system SHALL publish the report alongside the corpus inventory to
   `api/answer-engine` and `ui/ask-and-source-picker`.

## 7. The Starter Set

**User Story:** As the studio owner, I want the tool to be useful on the first day for the things
that actually stop a session, so that its first answer is not a refusal.

**Acceptance Criteria:**

1. <a name="7.1"></a>The system SHALL ship an initial entry store containing, at minimum, one entry
   for each of [7.2](#7.2)–[7.6](#7.6), each satisfying [§1](#1-entry-structure)–[§4](#4-scope-declaration)
   with no exemption.
2. <a name="7.2"></a>The starter set SHALL include an entry for **no sound from a track**, whose
   candidate causes include: the Track Activator off; another track soloed; the track's Monitor set
   to Off; Audio To routed to nothing; and the device chain or a device in it deactivated.
3. <a name="7.3"></a>The starter set SHALL include an entry for **a track is distorting**, whose
   candidate causes include: clipping at a named gain stage; a device's output above 0 dB; and the
   master limiter. The entry SHALL additionally carry an elimination step naming the deliberate
   distortion devices — Saturator, Drum Buss, Overdrive, Vinyl Distortion, Dynamic Tube and Amp —
   as the documented content that will otherwise dominate retrieval for the word "distortion", so
   that an answer does not offer a distortion device as the cause of unwanted distortion.
4. <a name="7.4"></a>The starter set SHALL include an entry for **latency when monitoring**, whose
   candidate causes include: buffer size; direct monitoring on the audio interface; the track's
   monitor mode; and the Overall Latency adjustment.
5. <a name="7.5"></a>The starter set SHALL include an entry for **a drum pad triggers the wrong
   sound**, whose candidate causes include: the pad's transmitted MIDI note against the drum rack
   pad's receive note; the module's General MIDI mode; and a MIDI channel mismatch.
6. <a name="7.6"></a>The starter set SHALL include an entry for **the controller does nothing**,
   whose candidate causes include: the Track, Sync and Remote flags for that input or output; the
   control surface selection; and track selection against the controller's bank position.
7. <a name="7.7"></a>WHEN each of the five symptoms in [7.2](#7.2)–[7.6](#7.6) is asked with the
   starter set and the vendor manuals in scope, the system SHALL produce an outcome of `answered`,
   `partially-answered` or `needs-narrowing`, and SHALL NOT produce `refused-not-covered` or
   `out-of-domain`. Refusing these five is the failure this source exists to remove, and it is the
   acceptance test for the set.
8. <a name="7.8"></a>Every fix in the starter set SHALL cite a vendor manual passage, except where
   [2.3](#2.3) applies.

## 8. Maintenance and Drift

**User Story:** As the studio owner, I want an entry I wrote a year ago to still work after I
replace a manual with a newer version, and to be told rather than misled when it does not.

**Acceptance Criteria:**

1. <a name="8.1"></a>The system SHALL require a fix pointer to identify its target by the source's
   stable source ID and the identity of the passage, and SHALL NOT accept a pointer expressed only
   as a page number. Page numbers move between document versions; passage identity does not.
2. <a name="8.2"></a>WHEN a vendor manual is re-ingested and the pointed-at passage's text is
   unchanged, the pointer SHALL continue to resolve with no edit to the entry.
3. <a name="8.3"></a>WHEN a vendor manual is replaced by a different document version of the same
   product, the system SHALL NOT treat the version change alone as breaking a pointer: source
   identity does not carry the document version, and a passage whose text is unchanged retains its
   identity.
4. <a name="8.4"></a>WHEN a previously resolving pointer stops resolving — the passage's text
   changed, or the source was removed — the system SHALL **flag** the entry rather than reject it,
   naming the entry, the cause and the source, and SHALL keep the rest of the entry ingested and
   retrievable. This is deliberately weaker than [2.2](#2.2): a first ingestion fails because the
   author wrote something wrong, whereas drift happens with the author absent, and silently
   withdrawing working triage mid-session is worse than serving it marked.
5. <a name="8.5"></a>WHEN a cause is flagged under [8.4](#8.4), the system SHALL set `unbacked`
   (CONTRACTS §2) on every passage carrying that cause, by the same rule as [2.4](#2.4), so that a
   citation drawn from it cannot present a broken fix as documented. WHEN the pointer resolves again
   on a later run, the system SHALL clear the flag.
6. <a name="8.6"></a>The system SHALL list every entry flagged under [8.4](#8.4) in the coverage
   report ([§6](#6-coverage-reporting)), with the source that changed.
7. <a name="8.7"></a>WHEN a device is removed from the rig inventory, the system SHALL report every
   entry scoped only to that device, and SHALL NOT delete it.

---

## Non-Goals

- **A general knowledge base.** This source holds symptom-to-cause triage for one rig. It is not a
  place for arbitrary notes, project logs, tips, or anything not shaped as symptom and causes.
- **A forum or community corpus.** Nothing imports entries from the web, a vendor's support pages,
  or another user. Entries are written by the studio owner, which is exactly why they are shown as
  the studio owner's.
- **A substitute for a missing vendor manual.** Where a manual exists and could be ingested, the
  answer is to add the PDF, not to paraphrase it into an entry. [2.3](#2.3) is a narrow allowance
  for hardware whose manual the corpus does not hold, not a route around ingestion.
- **Technique and creative advice.** A question about how to make a sound remains `out-of-domain`;
  this source does not make it answerable.
- **Session state.** An entry says what to check; it does not know whether track 3's monitor is
  actually off. That is the `StateSource` seam in `api/answer-engine`.
- **Retrieval, ranking and narrowing.** This spec guarantees the entries and their order exist and
  are citable; choosing and asking is `api/answer-engine`.
- **Automation.** Nothing here changes a DAW setting or a hardware control; entries describe checks
  for a human to perform.

## Assumptions and Risks

- **Risk — the source is only as good as the author.** Every entry encodes one person's
  understanding of their rig. A cause the owner has never encountered will not be listed, and the
  coverage report ([§6](#6-coverage-reporting)) can show that an entry exists but never that its
  cause list is complete. This bound is structural and cannot be validated away.
- **Risk — a wrong entry is cited with the same confidence as a manual.** [§2](#2-grounding-discipline)
  constrains factual claims and [§3](#3-citation-and-provenance) makes provenance visible, but
  neither can tell that a causal assertion is false. An entry claiming the wrong cause will be
  ranked, cited and read as authoritative. Visible provenance mitigates this; it does not fix it,
  and this is the most serious risk in this spec.
- **Risk — the term check in [2.6](#2.6) is shallow.** Verifying that a named control appears in the
  pointed-at passage catches vocabulary drift and copy-paste errors. It does not catch an entry that
  points at a real passage about a real control for a cause that control cannot produce.
- **Risk — maintenance burden grows with the rig.** New gear, a Live upgrade, or a replaced
  interface can invalidate entries that still resolve perfectly well. Nothing expires an entry, and
  drift detection ([§8](#8-maintenance-and-drift)) only sees changes in the *manuals*, not changes
  in the *studio*.
- **Risk — likelihood ordering is a judgement.** [1.1](#1.1) requires an order and [1.5](#1.5)
  preserves it, but nothing measures whether it is right, and it directly shapes what the narrowing
  flow asks first.
- **Assumption — `api/answer-engine` supplies a per-passage scope predicate.** [4.3](#4.3) publishes
  each entry's declared scope, but the filtering itself happens in the engine, whose grounding scope
  is otherwise a set of selected source IDs. Until that predicate exists, every entry in the
  authored source is retrievable whenever the source is selected, and scope declarations affect only
  the reports of [§6](#6-coverage-reporting).
- **Assumption — the rig inventory is maintained by hand**, per
  [`data/manual-corpus`](../manual-corpus/requirements.md) §11. Scope validation ([4.5](#4.5)) and
  the undocumented-device allowance ([2.3](#2.3)) both depend on it being current.
- **Assumption — the entry store stays small**, in the tens to low hundreds of entries. The 5-second
  budget in [5.6](#5.6) assumes that, and a store an order of magnitude larger would need
  incremental behaviour rather than a full re-check per run.
- **Assumption — entries are the owner's own writing and can be committed**, unlike the vendor PDFs
  in `manuals/`, which are copyrighted and gitignored. The entry store therefore travels with the
  repository while the corpus does not.
- **Assumption — the author writes in English, in the vocabulary they will later ask in.** Matching
  a colloquial question to an entry depends on the entry's own wording; the optional alternative
  phrasings in [1.3](#1.3) are the only mitigation, and they are optional.
