# Shared Contracts: DAWMans

**Status:** governing. Where a per-spec `requirements.md` and this file disagree, this file wins and
the spec is a defect to be reconciled.

DAWMans is split across four specs — [`data/manual-corpus`](data/manual-corpus/requirements.md),
[`data/symptom-triage`](data/symptom-triage/requirements.md),
[`api/answer-engine`](api/answer-engine/requirements.md) and
[`ui/ask-and-source-picker`](ui/ask-and-source-picker/requirements.md). `PROCESS.md` §10 requires a
root overview holding the shared assumptions when a capability is split. This is that overview.

It exists because the three specs were drafted in parallel and diverged at every seam: capabilities
were produced and never consumed, and the same interaction was described two ways. This file defines
the four records that cross a spec boundary, and who owns each field. **A spec may not invent a
field on a shared record, and may not silently drop one.**

**A seam is a seam whether it is a record or a stream.** `DECISIONS.md` Decision 6 catches a
produced-but-unconsumed capability by a join between what one spec emits and what another is obliged
to consume, and that join only ranges over what this file enumerates. So everything crossing a
boundary is enumerated here as a **closed set with a named consumer per member**: the four records
(§1–§4), the turn's event stream (§4b), the block types inside `body` (§4d), the outcome taxonomy
(§6) and the reason vocabulary (§6a). A set closed here may be **amended** here — that is the
mechanism, and it is the only one. Neither side may extend one privately. A member with no stated
obligation against it is a defect **in the table it sits in** — either it gains one or it leaves the
seam — and never a licence for a consumer to drop it.

Where a member's obligation is owed to a criterion that does not exist yet, its row is marked **†**
and names the criterion that must be written. A dagger is a debt recorded in the open, not a
dispensation — and no row carries one today, because Decision 11 landed the criteria in the same
pass as the members. The convention exists so that the next amendment cannot leave the gap silent.

---

## 1. `SourceRecord` — produced by `data/manual-corpus`, consumed by both others

One per ingested **source**, of either kind (§4a). Backs the source picker, the citation, and the
corpus inventory.

| Field | Owner | Notes |
|---|---|---|
| `kind` | corpus | `vendor-manual` or `authored-triage`, per §4a. **Must reach the user** — see §3. No source is indexed without one. |
| `source_id` | corpus | For `vendor-manual`, derived from the filename as `<vendor>/<product>`, stable while the filename is. For `authored-triage`, the **constant** `authored/triage` — the source is a store, not a document, so its identity does not vary with its contents. It must not be content-derived: `source_id` prefixes `passage_id`, so a digest that moved on every edit would orphan the whole citation history. |
| `vendor`, `product`, `doctype`, `lang` | corpus | From the filename fields for `vendor-manual`. Not applicable to `authored-triage`. |
| `doc_version` | corpus | From the filename for `vendor-manual`. **Must reach the user** — see §3. Not applicable to `authored-triage`. |
| `display_name` | corpus | Human-readable, for the picker and citations. Both kinds. |
| `hardware_applicability` | corpus | Which hardware revision this source describes, and whether that is *confirmed* or *assumed*. **Never inferred automatically** — see §5. On `authored-triage` the source-level value is fixed at `assumed`; applicability varies per entry, and an entry's declared devices are passage-level data, not a property of the store. |
| `page_count` | corpus | `vendor-manual` only; a pageless source reports it as not applicable. |
| `ingested_at`, `chunk_count` | corpus | Inventory only. Both kinds. |
| `low_text` | corpus | Text layer present but sparse. Ingested, not rejected. `vendor-manual` only; inventory and picker marking only. |

`page_count`, `ingested_at` and `chunk_count` are **inventory-only** — reported, not required to
reach any other surface. Every other field on this record has a named consumer, and a future audit
should treat an unconsumed one as a defect.

**`vendor`, `product`, `doctype` and `lang` are no longer inventory-only.** With `doc_version` they
reconstruct a `vendor-manual`'s filename under `DECISIONS.md` Decision 2's grammar, which is how the
engine locates the file it serves for open-at-source (§3a) and how it assembles `required_manual`
(§4e). The reconstruction is exact because `data/manual-corpus` derives all five fields *from* that
filename with an anchored expression, and `doc_version` is captured **without** the leading `v` — so
the name is rebuilt as `<vendor>_<product>_<doctype>_v<doc_version>_<lang>.pdf` and never as
`_vv1.0_`. A change to that grammar is now a change to two consumers as well as to the corpus.

**No filesystem path appears on this record.** The engine reconstructs the name above and resolves it
under the store root it is configured with; a path published to the browser would be a field the
browser cannot use, and an invitation to send one back (§3a).

## 2. `Passage` — emitted by `data/manual-corpus`, consumed by `api/answer-engine`

The unit of retrieval and of citation. `data/manual-corpus` emits the record for **both** source
kinds; for `authored-triage` the content and its chunking are specified by
[`data/symptom-triage`](data/symptom-triage/requirements.md), which supplies what the record carries.

**Pageless sources.** `section_number`, `page_start` and `page_end` are absent on an
`authored-triage` passage and SHALL NOT be synthesised, exactly as `section_number` is absent on an
unnumbered document. No criterion may reject a source for lacking them.

| Field | Owner | Notes |
|---|---|---|
| `passage_id` | corpus | **Content-derived and stable across re-ingestion.** Retained history must still resolve after a manual is re-ingested. |
| `source_id` | corpus | |
| `section_number` | corpus | Absent where the document has no numbering; never invented. |
| `section_title`, `page_start`, `page_end` | corpus | |
| `text` | corpus | |
| `degraded` | corpus | Contains characters that could not be repaired. **Must be consumed** — §3 and §4. |
| `has_figures` | corpus | The section contains figures, with their page. **Must be consumed** — §3. |
| `unbacked` | triage | An authored cause that rests on no vendor-manual passage — either none was ever given (a device with no ingested manual) or the pointer has since stopped resolving. The first arm has no instance today, every rig device being documented; the second is live and permanent, since a manual can be replaced under a stable pointer. **Must be consumed** — §3. |
| `entry_location` | triage | Where the entry is written: one opaque display string `<path>:<line>`, the path relative to the repository root and the line the entry's symptom heading sits on. `authored-triage` only; absent on a `vendor-manual`, which has a page instead. **Must be consumed** — §3 and §3a, where it is the open-at-source target for a source that has no page. |

**`entry_location` SHALL NOT contribute to `passage_id`.** The author moves entries between files and
re-lines them on every edit; an id derived from a location would orphan the citation history this
record's stability rule exists to keep resolving. It is data *about* where a passage was written,
never part of what the passage *is*, and nothing may key on it. How it reaches the engine — on the
passage record itself or through the authored sidecar the two `data` specs already exchange — is a
design choice of the producing specs; the obligation that it travel, and be consumed, is here.

## 3. `Citation` — produced by `api/answer-engine`, rendered by `ui/ask-and-source-picker`

Every field here is rendered or actionable. Nothing on this record may dead-end.

| Field | Rendering requirement |
|---|---|
| `source_id`, `display_name` | Shown. |
| `kind` | **Shown inline**, never behind a disclosure, distinguishable in greyscale. The user must be able to see that a claim rested on their own note rather than on the manufacturer's manual. |
| `doc_version` | **Shown inline** for a `vendor-manual`. This is the mk1/mk2 mitigation; it fails if hidden. Absent on a pageless authored source. |
| `unbacked` | **Shown inline** on any cause resting on no manual passage, so a broken or never-provided fix pointer is never presented as documented. |
| `hardware_applicability` | **Shown inline** where applicability is assumed rather than confirmed, not behind a disclosure. |
| `section_number`, `section_title`, `page` | Shown. |
| `passage_id` | Backs passage expansion, and both open-at-source mechanisms of §3a. |
| `degraded` | Expanded passage marked as containing unreadable characters. |
| `has_figures` | Shown as "figure on p*N*" — the sole offset for a text-only index. |
| `entry_location` | `authored-triage` only, copied from §2. Shown on the open-at-source surface of §3a and copyable there in one activation. It is the location slot's **companion, not its replacement**: the pageless rule below still puts the symptom title in the slot, and `entry_location` is never rendered as a section or a page. Absent on a `vendor-manual`. |

**Open at source** is §3a, which replaces the one-paragraph statement this section used to carry.
That paragraph named an action no browser can perform.

**Location fields on a pageless source.** An `authored-triage` citation carries no page and no
section number. These are rendered as absent, never invented — the same rule §2 applies to an
unnumbered document — with the entry's symptom title occupying the location slot.

## 3a. Open at source

Any citation SHALL offer a **one-activation action, reachable by keyboard, that puts the user at the
cited location.** With figures excluded from the index, a citation that is only a string strands the
user in a 1009-page document; and an authored entry the user cannot reach is an entry they cannot
correct at the moment they find it wrong.

The action is **mediated by `api/answer-engine`, never by the browser's own access to the
filesystem.** A tab served over `http://` cannot navigate to a `file://` URL in any current engine,
and nothing in a page can hand a local file to a viewer at a page number. The refusal is silent from
the page's point of view — no exception to catch, no promise to reject — so an action built that way
is not an unavailable control but a **dead** one. Two mechanisms, one per source kind:

| Kind | Mechanism | Contract |
|---|---|---|
| `vendor-manual` | The engine serves the source PDF itself, **same origin** as the surface, inline (no attachment disposition), `Range` honoured so a 96 MB manual pages without being fetched whole. | The surface opens it in a new tab at the fragment **`#page=N` and nothing else**, `N` being the citation's `page`. All three built-in PDF viewers agree on `#page=N` alone; one of them matches only a fragment that *starts* `page=` and truncates at the first `&`, so appending a zoom, a view or a text directive disables the jump there while working elsewhere. Anything richer is a per-engine enhancement and never the contract. |
| `authored-triage` | The entry has no page and no viewer to open. The engine already returns the entry's text through the **existing fetch-passage operation**, addressed by the `passage_id` the citation carries. | The surface reveals the entry **in place**, with `entry_location` shown and copyable in one activation, so the user can correct a wrong entry where it lives. This is the whole of the obligation for this kind. |

**The engine resolves the target; no caller ever supplies a path.** The vendor-manual mechanism is
addressed by `source_id` and the engine rebuilds the filename from that source's own §1 fields — the
index is the allowlist. A loopback endpoint that accepts a filesystem path is the shape every
documented localhost remote-execution failure has had, and no amount of validating `..` and symlinks
makes it safe.

**No operation launches anything outside the browser.** The only verified way to reach a *line* in a
file is an editor-specific invocation the user must have installed and put on their path, so a
mandatory action may not depend on it. Rendering the entry with its location copyable depends on
nothing and satisfies this section on its own. A future editor hook would be an addition, never what
makes this section met.

Serving the document is **one operation beyond the eight `api/answer-engine` 9.4 named**, and the
authored kind adds none. That widening is the defect being repaired: the browser surface's
counterpart assumption is the thing that was wrong, not the criterion that asked for the action.

## 4. `AnswerEnvelope` — produced by `api/answer-engine`, rendered by `ui/ask-and-source-picker`

Every field here is rendered or actionable on the outcomes where it is permitted. Nothing on this
record may dead-end. Applicability is stated per row; a field present on an outcome its row does not
permit is a defect in the producer, never licence for the consumer to render it.

| Field | Notes |
|---|---|
| `outcome` | One of §6. The UI SHALL render every outcome and SHALL NOT invent outcomes the engine cannot emit. |
| `direct_answer` | The actionable answer, first, before qualification. The UI's "≤25 words to the instruction" target depends on the engine producing this; it is not achievable by UI work alone. On `ranked-causes` it is the **rank-1 cause's `check`, stated as an instruction to perform** — never the cause itself. A check is something the user can go and do inside 25 words; asserting the cause would present the first candidate as the answer, which §6 forbids. |
| `body` | An ordered sequence of typed blocks drawn from the **closed set of §4d**, which also fixes the two inline forms. |
| `citations[]` | Per §3. The turn's one citation channel: everything else that cites resolves into it by `passage_id`. |
| `contributing_sources[]` | Which selected sources actually supplied passages. **Rendered** — this is how the user notices a controller question was answered from the Live manual. |
| `uncovered_parts[]` | Named parts of the question the sources did not cover. Rendered subordinate to the answer, not as a refusal. |
| `suggested_sources[]` | At most 3 **unselected** indexed sources likely to hold the answer, ordered by likelihood, each `{source_id, display_name}`. An **addressable value, never a substring of prose**: the consumer offers "add these to scope and re-ask" in one activation, which it cannot do against text it has rendered. Absent — never empty-as-a-claim — where no unselected source is a plausible holder, and absent on `out-of-domain` and `no-manual-for-device`, where the engine has already judged that no ingested source covers the question. |
| `narrowing` | A question plus 2–4 candidates, each selectable in one activation. `needs-narrowing` only. Distinct from `causes[]`: a narrowing candidate is a **control that re-asks**, a cause is a **finding to read**. |
| `causes[]` | The terminal ranked cause list, per §4c. Ordered, at most 4. `ranked-causes` only. |
| `required_device` | On a coverage failure, the device whose documentation would answer it — distinct from naming an ingested source. `no-manual-for-device` only. |
| `required_manual` | The filename to add to `manuals/`, per §4e. `no-manual-for-device` only, and see §4e for the one case in which it is absent there. This is what makes §6's "names the device **and the filename**" implementable: the filename is a request-specific fact, so it travels as its own member and is never recovered by parsing prose. |
| `scope_dropped[]` | `source_id` the engine removed from **this conversation's carried scope** at turn time, because the corpus no longer holds them, each with its `display_name`. **Rendered with the turn** — a prune the user did not perform is never applied silently. Absent where none was dropped. A consumer pruning its *own* stored scope at load time is a different subject and this file requires nothing of it (§4b). |
| `reason` | A closed machine-readable sub-code refining `outcome`, per §6a. Absent where §6a permits none. **Never displayed as prose** — it selects which sentence and which control the consumer renders. |
| `retry_after` | Seconds to wait before retrying, a non-negative number **as the provider stated it**, unrounded. `provider-rate-limited` only, and absent there where the provider stated none — absence is a normal renderable state, not a fault, and the consumer SHALL NOT invent an interval. A consumer MAY round for display; the engine's own retry rule reads the unrounded value. |
| `detail` | The engine's own wording for **this occurrence**, human-readable, rendered only behind the diagnostic disclosure of `ui/ask-and-source-picker` 9.3 and never as the primary message. Permitted on the outcomes that surface as an error state — `provider-unconfigured`, `-unreachable`, `-rate-limited`, `-error`, `timeout`, `incomplete`, `unknown-source-id`, `corpus-empty` — and on any outcome carrying `framing: unparsed`. Absent elsewhere. **Unparsed by contract:** no criterion in any spec may recover a machine fact from it, so the engine stays free to reword it; anything a consumer must act on has its own field here. It SHALL contain no credential material in whole or in part, no stack trace, no raw provider payload, and no filesystem path outside the two store roots. |
| `framing` | `parsed` or `unparsed` — whether the provider's output conformed to the engine's one declared answer format. `unparsed` means `direct_answer` was recovered by fallback rather than framed, so the consumer shows it in the same 9.3 disclosure **and** makes that disclosure available on an otherwise successful turn. It is a parser status, not a duration, so it is not a member of `timings`. |
| `ungrounded` | Set after streaming completes; the UI marks an already-rendered answer rather than withholding it. |
| `timings` | Per-stage **durations**, and nothing else, for verifying the latency budget of §7. |

`reason`, `retry_after`, `detail` and `framing` are **flat optional members of the one envelope**,
addressed identically whatever the outcome. Their applicability is stated in prose above rather than
expressed in the type: nothing structurally prevents a `retry_after` on `answered`, and each new need
costs one row and one amendment here. That is the accepted cost. A polymorphic `details[]` of typed
payloads would express applicability in the type and extend additively, but it requires the consumer
rule *ignore the detail types you do not know* — which legalises produced-but-unconsumed detail by
construction, the exact defect class Decision 6 exists to catch. It earns its cost when the detail
set is open-ended and consumers are many and independently versioned. Here there is one producer, one
consumer, and both ship together.

## 4a. Source kinds

Not every source is a vendor PDF. Two kinds exist, and both flow through the same `SourceRecord`,
`Passage` and `Citation` records — a source's kind changes what it is trusted for, never how it is
cited.

| Kind | Origin | Trusted for |
|---|---|---|
| `vendor-manual` | A manufacturer's PDF, ingested from `manuals/`. | What a control **is** and **does**. Authoritative on fact, silent on practice. |
| `authored-triage` | Written by the user. See [`data/symptom-triage`](data/symptom-triage/requirements.md). | Which documented control to **check**, and in what order, for a given symptom. |

**Why the second kind exists.** Measured against the real corpus: the phrase "gain staging" appears
**zero** times in the 1009-page Live 12 manual, and "troubleshoot" appears twice. Live's manual
documents the Track Activator as *"to mute the track's output, turn off the Track Activator"* — an
instruction for muting, never as a **cause** of silence. A reference manual documents controls, not
practice. So a strictly manual-grounded system cannot answer the two questions a producer most often
asks mid-session, and the narrowing flow in §4 is unimplementable, because no passage contains the
distinguishing conditions it must draw candidates from.

An `authored-triage` source closes that gap without weakening grounding: its entries are retrieved,
ranked and **cited exactly like any other source**, and the UI shows their provenance as authored by
the user rather than by the manufacturer. Every fix an entry points to still cites a vendor manual.

## 4b. The turn stream

`AnswerEnvelope` does not arrive as one document. The submit-question operation returns a stream of
**named events over a single response**, and the envelope is what a conforming consumer has
accumulated when the stream ends. The event set is closed and governed here for the same reason the
record's fields are: an event no consumer is obliged to act on is Decision 6's produced-but-unconsumed
defect, invisible to review only because the seam is a stream rather than a record.

**Every event carries a §3 or §4 field, and `done` is the only exception.** That is the join rule: a
field above with no carrier below is a defect in this table, and an event below carrying nothing from
above is a defect in the producer. The rendering obligation itself is stated **once**, on the field in
§4; the column here names the criterion that discharges it, so the two tables cannot drift into
disagreeing.

| Event | Payload | Carries | Discharged by |
|---|---|---|---|
| `scope_dropped` | `[{source_id, display_name}]` | `scope_dropped[]` | `ui` 3.11 |
| `outcome` | `{outcome, reason?, retry_after?, detail?}` | `outcome`, `reason`, `retry_after`, `detail` | `ui` 9.4 and the outcome table of `ui` §9 |
| `direct_answer` | `{text}` | `direct_answer` | `ui` 4.3 |
| `body_delta` | `{text}` | `body` | `ui` 4.1, 4.4 |
| `citation` | one `Citation` (§3) | `citations[]` | `ui` §5 |
| `cause` | one `Cause` (§4c), in rank order | `causes[]` | `ui` 6.6 |
| `contributing_sources` | `{sources[]}` | `contributing_sources[]` | `ui` 4.7 |
| `uncovered_parts` | `{parts[]}` | `uncovered_parts[]` | `ui` 4.8, 4.9 |
| `suggested_sources` | `[{source_id, display_name}]` | `suggested_sources[]` | `ui` 7.4 |
| `narrowing` | `{question, candidates[]}` | `narrowing` | `ui` §6 |
| `required_device` | `{device, display_name}` | `required_device` | `ui` 7.7 |
| `required_manual` | `{filename, placeholders[]}` | `required_manual` | `ui` 7.7 |
| `ungrounded` | `{ungrounded: true}` | `ungrounded` | `ui` 5.13 |
| `framing` | `{framing: "parsed" \| "unparsed"}` | `framing` | `ui` 9.3 |
| `timings` | per-stage durations | `timings` | `ui` 8.8, 9.3 |
| `done` | `{complete: true}` — **a payload is required**, see below | — (transport) | `ui` 1.6, 4.6 |

**Ordering is part of the contract**, because the consumer paints as it reads. `scope_dropped`, where
present, precedes `outcome`; `outcome` precedes every other event, since it selects the renderer
before the first word is painted; `direct_answer` precedes the first `body_delta`, so first paint
never waits on block-prefix disambiguation; `cause` events arrive in rank order; `ungrounded` follows
the last `body_delta`; `done` is last and occurs exactly once. A `citation` MAY arrive after the
marker that refers to it — the consumer assigns a marker its number at first appearance, so late
arrival costs no reflow. The rest are unordered among themselves.

**Three rules for something a consumer does not know, and they are deliberately different.**

1. **An unknown *event* — ignore it.** A consumer SHALL ignore an event whose name is not in this
   table and SHALL NOT fail the turn on it. *Ignored* forbids failing; it does not forbid logging.
   This is what lets a row be added without breaking a running client. The stream is data: an unknown
   element carries nothing a consumer could salvage.
2. **An unknown `body` block type — drop the wrapper, keep the text** (§4d). `body` is presentation:
   the words under an unknown wrapper are still the answer's own. Emitting nothing — the default in
   comparable markup extensions — would make a `!caveat` about a Suite-only device vanish rather than
   degrade, which is a safety failure and not a cosmetic one.
3. **An unknown `outcome` value — do not ignore it.** It renders as a broken state carrying `detail`
   (`ui` 9.4). An outcome selects the renderer, so a turn whose renderer is unknown cannot be trusted
   to any renderer.

**And the converse of rule 1, which is the half that closes this defect.** A consumer SHALL render or
act on **every** event named in this table, through the field it carries. This has no standard
protocol form: the mechanisms that exist — a producer-set must-understand flag, or a capability
handshake at connect — are dynamic machinery for open ecosystems with independently versioned peers,
and both are disproportionate for one Python producer and one browser consumer shipped from one repo.
So it is enforced by this table and by a consumer-side test asserting one rendering path per governed
event. That is a weaker guarantee than the wire could give, and it is stated rather than implied:
nothing in the protocol detects a consumer that quietly stops rendering `scope_dropped`.

**Two obligations follow from incremental delivery and survive any change to the event set.** They
are the irreducible minimum, and they hold even if the transport is one day replaced.

1. Every field of §3 and §4 the engine produced for a turn SHALL reach the consumer before that turn
   ends, whatever wire form carries it.
2. A turn SHALL carry an **explicit terminal signal**. A stream that stops without one is a failed
   turn on the consumer's side, never a finished one.

**Three mechanics the transport does not supply, so this file must.**

- **`done` carries a payload.** An event with a name and no data line is never dispatched by a
  conforming reader, so a bare `done` may legally vanish.
- **Absence of `done` before the stream ends is a defined failure, not silence.** A stream truncated
  mid-event discards the pending event without error. A consumer reaching end-of-stream without
  `done` SHALL render the turn `incomplete`, retaining and marking what arrived, and SHALL NOT wait.
- **There is no reconnection and no resumption.** Automatic retry, the reconnection-time field and
  the last-event-id header are behaviours of the browser's own `EventSource`, which cannot carry this
  operation's request body and is not used. A stream that breaks is over; recovery is the user
  re-asking. Only disconnect-cancels is inherited from the transport.

**Version token.** The submit-question response declares `dawmans/turn-stream/1` in a response header,
readable before the first body byte. A consumer that does not know the declared version SHALL refuse
the turn and render a broken state naming both versions, rather than half-rendering it. It carries no
`outcome` and is not a member of §6 — no turn is being described. The token is bumped only when the
meaning of an existing event changes; adding an event, or a member to an event's payload, is not such
a change. This matters in development, where `DECISIONS.md` Decision 10 runs the surface behind its
own dev server and a cached bundle can be several revisions old.

**`scope_dropped` and `ui/ask-and-source-picker` 3.8 are not in conflict**, and the appearance that
they are comes from reading them as one subject. 3.8 is the client pruning **its own stored scope** at
load time against the source list — no turn, no event, nothing for the user to learn — and it is
silent because there is nothing to say. `scope_dropped` is the engine reporting that it pruned **the
turn the user just asked**, which is what `api/answer-engine` 5.11 requires be reported "rather than
applying it silently". Both criteria stand as written.

## 4c. `Cause` — a member of `causes[]`

The terminal form of symptom triage: the narrowing limit was reached and the cause is still
ambiguous, so the engine reports what the candidates *are* instead of asking again. It is a different
shape from `narrowing` — its members are not candidates the user picks between to continue a turn,
they are checks the user goes and performs — and it carries three things `narrowing` cannot: an
explicit rank, a per-cause confirming check, and a per-cause fix pointer distinct from the cause's own
citation.

| Field | Notes |
|---|---|
| `rank` | A 1-based integer, **always present**, and **equal to this record's position in `causes[]`**. Rank is shown, so display order and stated rank can never disagree; an absent or free-floating rank would let them. |
| `statement` | The candidate cause. |
| `check` | The observable that would confirm or eliminate it — what the user looks at, not what they conclude. The rank-1 cause's `check` is also what `direct_answer` states as an instruction (§4). |
| `cites[]` | One or more `passage_id`, resolving into the envelope's `citations[]`. The cause's own evidence — on an authored cause these resolve to `authored-triage` citations, and §3 requires that visible inline. |
| `fix_cites[]` | `passage_id` for the **vendor-manual** fix, resolving into the same `citations[]`, rendered as ordinary citations and distinct from the authored cause they belong to. **Empty** where the entry names no fix, where the cause is `unbacked`, or where the fix passage lies outside the turn's selected scope — and where it is empty the cause's own citation carries the `unbacked` mark of §2, which is what the user sees. |

Citations are **referenced by `passage_id`, never nested as records.** `citations[]` is the turn's one
citation channel: the consumer already keys its citation map by `passage_id` and numbers each marker
at first appearance, so a second delivery channel would make §3's inline obligations something to
satisfy twice and give passage expansion two places to look.

Where the causes come from an `authored-triage` entry, `causes[]` preserves that entry's declared
order exactly: nothing sorts, merges, adds or drops. The consumer SHALL show the rank and SHALL NOT
promote `causes[0]` to an answer — a ranked list of four things to check is not a diagnosis, and
rendering its head as one is the failure this shape exists to prevent.

## 4d. `body` block types

`body` is a restricted Markdown subset. Its block set and its inline set are **closed and enumerated
here**, because the producer emits six block kinds and two inline forms, and a consumer told only
"headings, ordered steps, key terms" renders three of them. Every block type is decidable from its
first line at column 0, which is what lets a consumer fix a block's type before painting it and never
re-type or re-flow it afterwards.

| Block | First line | Rendering requirement |
|---|---|---|
| heading | `## ` | A visually distinct, scannable heading. |
| ordered step | `N. ` | Each step a separately identifiable line or block. |
| bullet | `- ` | A list item. |
| paragraph | anything else, blank-line separated | Prose. |
| caveat | `!caveat ` + text, continuations indented two spaces | Rendered **in reading order where it appears**, visually distinct, never behind a disclosure. This is the Live 12 Standard versus Suite warning of §8: a recommendation the user cannot act on. A caveat dropped or hidden is worse than no caveat. |
| conflict | `!conflict ` + text, then **two** `- ` reading lines, each with its own citation markers | Both readings rendered with their separate citations, neither presented as the answer nor chosen for the user. |

Two inline forms, and no others: the citation marker `[[p:<passage_id>]]`, of fixed rendered width,
resolved against `citations[]`; and a **backtick-delimited span** for a key term — a key name or
combination, a parameter name, or a menu path — which is the "key terms" structure §4 has always
required and which the consumer renders as a discrete element. Emphasis, links and images are **not**
in the subset. Their absence is deliberate: the surface's no-reflow rule is met by fixed-width inline
forms, and a link in grounded output is a navigation target with no citation behind it.

**Arity is a producer obligation and never a re-type.** `!conflict` carries exactly two readings.
Where a block arrives with some other count, the consumer renders the readings it received, in place,
as that block — it SHALL NOT re-type a block it has already begun painting, which the no-reflow rule
forbids outright. Stating the arity lets the producer be tested against it; it does not license the
consumer to change its mind mid-block.

**`!suggest` is not a block type.** Source suggestions are `suggested_sources[]` on the envelope (§4),
because the consumer needs each `source_id` as a value it can act on — "add that source to scope and
re-ask in one activation" — and it cannot get one out of a sigil embedded in prose. It joins
`uncovered_parts[]`, `narrowing` and `required_device`, all of which are hoisted out of `body` for
exactly the same reason.

**Unknown blocks degrade; they do not disappear** — §4b rule 2.

## 4e. `required_manual`

`no-manual-for-device` says the question is answerable and the document is missing. §6 requires it to
name the device **and the filename to add**, and `ui/ask-and-source-picker` 7.7 requires that filename
copyable in one activation. The consumer cannot assemble it: the `manuals/` grammar needs a doctype, a
version and a language that a browser has no way to learn. So the filename travels as its own member,
never as a fact the consumer must read out of the answer's prose.

| Field | Notes |
|---|---|
| `filename` | The complete name to add to `manuals/`, in `DECISIONS.md` Decision 2's grammar `<vendor>_<product>_<doctype>_v<version>_<lang>.pdf`, assembled by the engine and copyable in one activation. Any field the engine cannot know is written as its **named placeholder inside the string itself** — for a device newly declared in the rig ahead of its manual, `focusrite_scarlett-2i2_<doctype>_v<version>_<lang>.pdf` — so a partly-known name is still one copy, and its gaps are visible in the same glance. The example is hypothetical by necessity: see the note under §5. |
| `placeholders[]` | The names of the fields left as placeholders, empty where the engine assembled a complete name. This is how the consumer says *which* parts the user must supply from the document they obtain, without splitting a human-facing string on underscores — a split that would break on the `<version>` field's deliberate full-stop exception. |

`required_manual` is present **exactly where `required_device` resolves to a canonical
`<vendor>/<product>` id**, and absent otherwise: vendor and product are the two fields no placeholder
can stand in for, and a name that is placeholder all the way down is not copyable. Where it is absent
the consumer names the convention and the device instead, and synthesises nothing — a wrong filename
is worse than none, because `data/manual-corpus` 2.5 rejects it at ingest for not matching the
pattern and the user learns only from the rejection.

**`required_manual` is dormant today, and both sides SHALL still implement it.** A device resolves
to a canonical id only through the owned-but-undocumented report (`api/answer-engine` design,
`required_device`), and that report is empty now that every rig device is documented — so
`no-manual-for-device` still fires for gear outside the rig, but always with a free-form
`required_device` and no `required_manual`. The field becomes reachable again the moment a device is
added to `rig.yaml` ahead of its manual, which is the ordinary way hardware arrives. Neither side may
treat it as absent by construction: this is an empty set, not a removed member.

**A residual, stated rather than papered over.** Where the engine has never seen the document it
cannot know its doctype, version or language, so `filename` carries placeholders and 7.7's "exact
filename" becomes "the filename with the fields the document supplies". That is the honest limit of
what a device with no ingested manual permits, and 7.7 is amended to it rather than left demanding
something unknowable.

## 5. Hardware applicability

A source may be **present, cited, and wrong for the user's rig.** The ingested Akai guide is Manual
Version 1.0 describing the original APC Key 25; the user owns the mk2, which differs in pads and
shift layer. A confidently cited procedure for the wrong revision is this product's worst failure
mode, and it is worse than a refusal because the citation *increases* the user's confidence.

Therefore: the system SHALL hold a declared rig inventory — the hardware the user owns — separately
from the corpus inventory of what is indexed. It SHALL be able to report **owned-but-undocumented**
and **documented-but-unconfirmed**.

**Only the second has an instance today.** Obtaining the Focusrite Scarlett Solo 4th Gen guide —
the generation confirmed against Live's own log on this machine, not inferred — closed the
owned-but-undocumented gap, and the APC guide remains documented-but-unconfirmed. Every mechanism
resting on the first is therefore **dormant, not deleted**: `required_manual` (§4e), `unbacked`'s
no-manual arm (§2), the engine's device scope and the picker's known-gaps list all keep their
behaviour and are exercised against a declared device with no indexed source, which is what the next
piece of gear will be before its PDF is downloaded. A consumer that hardcodes the empty case is a
defect against this section.

## 6. Outcome taxonomy

The complete set the engine may emit and the UI SHALL render. Neither side may hold a private
member. The set is closed against **private** growth, not against amendment: adding a member is an
amendment to this table and obliges both sides in the same pass. It SHALL NOT be grown to encode a
**refinement** of an existing member — that is what `reason` (§6a) is for, and a taxonomy that swells
one member per distinction stops being a set either side can render exhaustively.

| Outcome | Meaning |
|---|---|
| `answered` | Fully answered from in-scope sources. |
| `partially-answered` | Answered in part; `uncovered_parts[]` names the rest. **Not a refusal** — renders as an answer. |
| `needs-narrowing` | A narrowing question with candidates, in `narrowing`. |
| `ranked-causes` | The narrowing limit was reached and the cause is still ambiguous. `causes[]` carries at most 4 documented candidates in rank order, each with its own citations, its confirming check and its fix citation (§4c). **Neither an answer nor a further question**: no cause is asserted, `causes[0]` SHALL NOT be presented as the answer, and the causes are findings to read rather than controls that re-ask. A member because it is a distinct **renderer** with distinct affordances, not because it refines a failure. |
| `refused-not-covered` | In-scope sources do not cover it; another ingested source might. |
| `out-of-domain` | A technique question, not a control question. A reference manual documents controls, not practice; no ingested manual will ever cover it. Suppresses source suggestions. |
| `no-manual-for-device` | Answerable, but needs a manual not ingested. Names the device in `required_device` and the filename to add in `required_manual` (§4e) — both fields, never facts left in prose. |
| `no-sources-selected` | Defence in depth; the UI does not submit an empty scope. |
| `unknown-source-id` | |
| `corpus-empty` | Nothing ingested yet. |
| `provider-unconfigured` / `-unreachable` / `-rate-limited` / `-error` | Refined by `reason` where §6a scopes one. `-rate-limited` **MAY** carry `retry_after` (§4); a provider need not state an interval, and the absent case is a required rendering rather than a fault. |
| `timeout` | Attributed to the provider, distinct from unreachable. |
| `incomplete` | Synthesis stopped before the answer finished. What was produced is retained and marked. |
| `cancelled` | The caller abandoned the turn — a new question arrived mid-stream, or the user cancelled. |

**17 members.** A rejection that carries **no envelope** is not one of them and never will be: an
over-length question refused before a turn exists, a `Host` or `Origin` refusal, and a stream-version
mismatch (§4b) all describe a request rather than a turn. The consumer renders each as a broken state
naming what was rejected, never as a refusal.

## 6a. Reason vocabulary

`reason` is a constant drawn from a closed set, scoped to the outcomes it may accompany. A taxonomy
of this size cannot distinguish a missing credential from a rejected one, and the answer is a sub-code
beside the outcome rather than a seventeenth and eighteenth member of §6. Values are **lowercase
kebab-case**, at most 63 characters, matching `[a-z][a-z0-9-]*`; never a sentence, never translated,
and never rendered as the user-facing wording, which the consumer states for itself per outcome and
reason. `detail` cannot do this job, because §4 declares it unparsed.

| Outcome | `reason` | Consumer |
|---|---|---|
| `provider-unconfigured` | `no-provider-kind` — no provider kind chosen at all | `ui` 9.5 |
| `provider-unconfigured` | `missing-credential` — a keyed hosted kind chosen with no key stored | `ui` 9.5, produced by `api` 6.6 |
| `provider-unconfigured` | `disclosure-unacknowledged` — the shared backend chosen and its disclosure not acknowledged | `ui` 9.5, produced by `api` 6.15 |
| `provider-error` | `authentication-failed` — the credential was rejected | `ui` 9.10, which offers configuration **in place of** the retry, since retrying the same credential cannot succeed |
| `provider-error` | `provider-rejected` — any other rejection by the provider | `ui` 9.9 |
| every other outcome | absent | — |

Adding a value is an amendment to **this** table. It is never an amendment to §6, which is the point:
the taxonomy stays a size both sides can enumerate, and the distinctions live where they can grow.

## 7. Latency budget

Measured end to end, keypress to first painted token — the only figure the user experiences. Stage
budgets must compose into it, not be stated at incompatible boundaries.

| Stage | p95 |
|---|---|
| Retrieval | 50 ms |
| Session state acquisition | 100 ms, **excluded** from the engine overhead cap below |
| Engine overhead (prompt assembly, citation resolution, framing) | 150 ms |
| Provider time to first token | 1.2 s hosted / 2.5 s local |
| Transport and paint | 100 ms |
| **Keypress → first painted token** | **1.5 s hosted / 2.8 s local** |

The end-to-end figure is a **target** with an acceptance band, per `PROCESS.md` §5: ≤2.0 s hosted and
≤3.5 s local at p95. The stage budgets above are hard, the composed figure converges. A spec stating
that band is conforming, not disagreeing.

A narrowing question SHALL be budgeted as a first-token target consistent with the provider class,
not as a completion target that beats it. A `ranked-causes` turn is budgeted the same way and adds no
stage: assembling `causes[]` from an already-retrieved entry is dictionary work inside the engine
overhead cap.

**Only the turn is on this budget.** The engine's other operations are not stages of it and are never
charged to one; each carries its own bound in `api/answer-engine` §9. Serving a cited document (§3a)
is one of those: a 96 MB PDF is fetched by the browser's viewer, on its own time, after a turn has
settled.

## 8. Known constraints that cross every spec

- **Live 12 Standard, not Suite.** The manual documents the full product. An answer recommending a
  Suite-only device or a Max for Live feature is manual-accurate and useless. It must be flagged.
- **Chunk size is bounded by the embedding window, not by readability alone.** 500 words is ~600
  tokens and overflows a 512-token window, silently truncating the tail of every maximal chunk.
- **Grounding versus reasoning.** Facts SHALL be cited, without exception. Choosing *which
  documented control to check* is reasoning over cited facts and is permitted; it is not "general
  knowledge" and the no-general-knowledge rule SHALL NOT be written so as to forbid it. Without this
  split, symptom triage is simultaneously required and prohibited.
