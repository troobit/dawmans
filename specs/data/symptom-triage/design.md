# Design: Symptom Triage

**Domain:** `data` · **Capability:** symptom-triage · **Status:** draft

Implements [`requirements.md`](requirements.md) against [`CONTRACTS.md`](../../CONTRACTS.md)
(governing). Criteria are referenced by ID and not restated.

## Overview

A committed folder of hand-written Markdown entries — one file per symptom, YAML frontmatter for the
machine-readable fields — is loaded by a second `SourceLoader` behind the seam
[`data/manual-corpus`](../manual-corpus/design.md) already defines, and emitted as ordinary
`Passage` records. The load-bearing work is not the parsing: it is resolving each cause's fix
pointer into the ingested vendor corpus on every run, and deciding whether a pointer that does not
resolve is the author's mistake (reject, 2.2) or the manual moving underneath a working entry
(flag, 8.4).

---

## Architecture

### Dependencies on `data/manual-corpus`

Every specific this spec rests on is named here, so a change there is traceable to what it breaks.
All of these are present in that design as it now stands.

| Depended-on specific | Named in | Used for | Consequence if it changes |
|---|---|---|---|
| `SourceLoader`, `Discovered`, `LoadResult`, `Region`, `Unit`, `UnitFlags` | §The loader protocol | `TriageLoader` is the second loader | this spec's whole emission path |
| chunker preserves `Region.units` order | §The loader protocol | 1.5 | cause ranking silently reordered |
| `Unit.atomic` + `repeat_on_split` | §The loader seam | 3.3 split-between-causes, symptom repeated | 3.3 needs special-casing in the chunker |
| `UnitFlags.unbacked` carried through untouched (12.6) | §Emission contract | 2.4, 8.5 | the flag cannot reach `Citation` |
| `passage_id(source_id, text)` in `corpus/passage_id.py` | §Passage identity | 3.9 | authored IDs diverge from manual IDs |
| `<slug>` = `source_id` with `/` replaced by `_`, giving `authored_triage` | §Source identity and discovery | the sidecar's filename | the sidecar's reader finds nothing |
| `views/<hex>/passages.jsonl` + `sources.json`, located via `manifest.view_dir` | §Index layout | pointer resolution input **under `dawmans validate`**; under `dawmans ingest` the same rows are read from the committed shards through `read_shards`, `passage_to_dict` and `record_to_dict` ([Decision 13](decision_log.md)) | resolution needs a new read path |
| `LoadResult.sidecar` published at `views/<hex>/reports/<slug>.json`, copied in from the shard by the merge | §Index layout, Decision 8 | the sidecar's location and its atomic swap | the sidecar pairs with an arbitrary view again (§The sidecar) |
| the authored load runs **after every vendor shard has committed** | §Stages, orderings | 2.1 — resolution reads the passages this run produced | pointers resolve against a stale corpus |
| per-`passage_id` vector reuse via the authored shard meta's `vectors` map | §Incremental behaviour | 5.6 | every run re-embeds every entry |
| the pageless citation header omits `§` and the number entirely | §Chunking | 3.4 | every authored chunk is embedded with a literal `§None` |
| `rig.yaml` device ids and `revision` values | §Rig inventory | 4.2, 4.6 | scope validation loses its vocabulary |
| `authored-triage` `hardware_applicability` fixed at `assumed`, nothing in `rig.yaml` setting it | §Rig inventory | 3.8 | see §Requirements defects |

Two requests were made on that design. The first has landed; the second remains open. Both are named
at their point of use below:

1. **The sidecar must move inside the view directory** and join the merged view's read contract —
   `views/<hex>/reports/<slug>.json`, not `index/reports/<slug>.json`. **Landed**: `manual-corpus`
   §Index layout now splits the report channel, publishing view sidecars inside the view and keeping
   the per-run ingestion audits at `index/audits/<slug>.json`, with its Decision 8 recording why
   (§The sidecar).
2. **The per-run model load must become lazy-on-first-embed**, so an authored-only ingest that
   re-embeds nothing never loads the model (§Discovery, fingerprint and the run budget). Still open.

### The store on disk

`triage/` at the repository root, sibling to `manuals/` (1.6). It is **committed**: `.gitignore`
excludes `manuals/*.pdf`, not the folder itself, and needs no change. Discovery is a recursive scan
of `triage/**/*.md` on every run, with no index file (1.6, 1.7); a flat glob would make
`triage/live/no-sound.md` invisible with nothing to report. A non-`.md`, non-dotfile there is
skipped **with** a report line — the opposite of `manuals/`, where the skip is silent — because a
`no-sound.txt` the author expected to be ingested must not disappear quietly. Dotfiles are exempt so
that `.pointer-ledger.jsonl`, the machine's own artefact, does not warn about itself every run.
Filenames and directory names carry no meaning: not identity (1.8), not scope, not ordering.

### Entry grammar

```markdown
triage/no-sound-from-track.md

---
devices: [ableton/live-12, focusrite/scarlett-solo]
---

# No sound from a track

also: track is silent; can't hear track 3

## The Track Activator is off
check: the track's number is dimmed in the mixer
fix: ableton/live-12 §16.4

## Another track is soloed
check: a blue S is lit on any track
why: one glance, and it is the commonest cause after the activator
fix: ableton/live-12 §16.5

## Direct monitoring is on at the interface
check: the DIRECT MONITOR button is lit
fix: focusrite/scarlett-solo-4g §<the section covering DIRECT MONITOR>

## The buffer size is too high for tracking
check: latency is audible when playing in, but the recording lines up on playback
fix: ableton/live-12 §1.2 "Audio Preferences"

## Otherwise
Check the master track before assuming this track is at fault.
```

Two things in that example are worth reading twice. **`devices` names rig device ids and `fix:`
names source ids, and for the Focusrite the two differ** — `focusrite/scarlett-solo` against
`focusrite/scarlett-solo-4g`, because the vendor sells the generation as part of the product name
and the rig does not (`DECISIONS.md` Decision 2). Neither is a typo for the other and the author
writes both. **The direct-monitoring cause carries a `fix:`, not an `undocumented:`**, because the
Scarlett Solo 4th Gen guide is ingested; its section number is the author's to fill, and 2.2 rejects
the whole entry at first ingest if the pointer does not resolve. `undocumented:` is the alternative
key and is admissible only for a rig device with no ingested source — a state no device is in today
(2.3), so it appears in no starter entry.

| Construct | Rule |
|---|---|
| byte order mark | a UTF-8 BOM is stripped before anything else, so `---` at byte 3 is still frontmatter at byte 0 |
| frontmatter | required, `---`-fenced YAML at byte 0. `devices` required, a **YAML list**, non-empty (4.1). Any other key is flagged, not fatal |
| device identity | `<vendor>/<product>`, optionally `@<revision>` (4.6) — `akai/apc-key-25@mk2`, `ableton/live-12@12-standard` |
| symptom | the single `#` H1. Any count other than one is a rejection |
| preamble | lines between the H1 and the first H2. `also:` lines are `;`-separated alternative phrasings (1.3); any other prose is retained and emitted with the symptom unit, so nothing there disappears unreported |
| cause | each `##` H2. Document order **is** the likelihood ranking (1.1); nothing re-orders it (1.5) |
| `check:` | exactly one per cause (1.2) |
| fix | one or more `fix:` lines, **or** exactly one `undocumented:` line naming a device (2.3). Both on one cause is a rejection — the two are alternatives, and a cause claiming a device is undocumented while pointing into a manual is not a slip a default can resolve |
| `why:`, loose prose, `###`+ | optional, anywhere in a cause; retained in the passage text, with keyed-line markers normalised (1.3) |
| closing statement | the final H2 carrying neither `check:` nor a fix line. Not a cause; excluded from the 2–6 count (1.4) |

A keyed line is matched case-insensitively after stripping leading `-`, `*`, `>`, `#` and `**`, so
`**Check:**`, `- check :` and `CHECK:` are one line. A **free-text** value — `check:` and `why:` —
continues until a blank line, a heading or another keyed line, because those wrap as the author
types them. A **`fix:`, `undocumented:` or `also:`** value is complete on its own line and never
continues ([Decision 7](decision_log.md)): each has its own grammar that ends at the line, so prose
written underneath one is prose and is retained as such. The emitted text carries the **normalised**
marker (`check:`), not the author's, which is what makes marker style invisible to `passage_id`
(§Identity).

Position, not vocabulary, identifies the closing statement, so there is no reserved title to
remember ([Decision 6](decision_log.md)). The cost: a final section meant as a cause that lost
*both* its check and its fix reads as a note, so an entry of three causes whose last loses both
parses as two causes plus a note — inside 1.4's band, so nothing rejects, the cause vanishes from
the ranked list `api/answer-engine` 7.2 and 7.6 consume, and 1.5 forbids losing a cause that way.
A demoted section therefore **always** emits a `closing-statement-inferred` flag naming it, so the
demotion is never silent. Losing only the fix — the likelier slip — still rejects under 1.2.

Requirement 7.3's elimination step needs no construct of its own: "the distortion is deliberate" is
an ordinary cause whose check names the distortion devices in the chain and whose fix points at the
Live manual's section for one of them. It counts toward the 2–6 limit.

### Fix pointers

```
fix: <source_id> §<section-number>              ableton/live-12 §16.4
fix: <source_id> "<section title>"              akai/apc-key-25 "Shift Functions"
fix: <source_id> §<section-number> "<title>"    title corroborates, does not select
```

The title form is not a convenience: the APC Key 25 guide has no numbering at all
(`manual-corpus` 6.4), so a number-only syntax could not point into a third of the corpus. **No page
form exists** — 8.1 forbids page-only addressing, and admitting a page even as a qualifier would
reintroduce the breakage 8.3 exists to avoid.

Resolution runs against `(source_id, section_number) → passages` and
`(source_id, normalised title) → passages` maps built in one pass over the view's `passages.jsonl`.
The source token must name an indexed `vendor-manual`; an `authored-triage` target is a rejection
(2.7) and an unknown source an unresolved pointer. A number matches exactly after `§` is stripped. A
title matches on the normalised form (casefold, collapse whitespace, strip a leading section number
and trailing punctuation), else on a unique prefix; two matches is unresolved with the candidates
named, never an arbitrary pick. Where both are given the number selects and the title corroborates —
a disagreement is a **flag**, the cheapest renumbering detector available and free to the author.

**A pointer addresses a section, and resolves to the ordered set of passages that section produced.**
Where the section split into *k* chunks it resolves to all *k*, the cause carries all of them, and
the engine cites whichever it retrieves. Nothing here picks one chunk: which chunk holds the sentence
about the control is an artefact of the 350-word cap and changes under a re-chunk.

### The term check (2.6)

The checked span is the **cause statement plus its `check:` value**. Two term classes are extracted:

- **Capitalised runs** — consecutive Capitalised or ALL-CAPS tokens (`Track Activator`,
  `DIRECT MONITOR`). A single-token run at a sentence start is dropped unless the token also appears
  capitalised elsewhere in the entry.
- **Numeric literals** with an optional unit (`0 dB`, `-12 dB`, `44.1 kHz`).

Terms equal to a declared device's id, product token, or `rig.yaml` `display_name` — the device the
owner holds, not the `SourceRecord`'s document name — are discarded, as are tokens under three
characters.

**Containment is case-sensitive at word boundaries for the capitalised class**, and casefolded only
for the numeric class. Case-insensitive matching would make the check close to vacuous: terms are
extracted *because* they are capitalised, so `Audio To` casefolds to `audio to` and matches almost
any routing prose, and `Off`, `Monitor`, `MIDI` and `Live` match trivially. The manuals print
control names capitalised too, so the case-sensitive test is the one that actually discriminates.
Numerals are casefolded because unit case varies (`kHz`, `khz`) and are matched at word boundaries
so `0` does not satisfy `10`.

The numeric class is kept although it is where false positives concentrate: 7.3's mandated cause
("a device's output above 0 dB") passes only if the pointed-at section prints that value. That is a
constraint on the starter set, pinned by `live_sections.json`, not a reason to drop the class — a
numeric claim no passage prints is exactly the claim 2.6 exists to catch.

**Multi-pointer semantics.** A cause may carry several `fix:` lines. Containment is satisfied when
**any** pointer's resolution set contains the term; a term backed by one of two cited sections is
backed. Drift is the other way round: **any** drifted pointer flags the cause and sets `unbacked`,
because a cause is only as documented as its weakest citation.

`why:`, loose prose and the closing statement are **excluded** from the check. This is a deliberate
narrowing of 2.6, whose scope is "in a cause" and therefore includes `why:`; 2.5 entitles the author
to an unsupported *causal* assertion, not to an unsupported factual one. The risk is named rather
than hidden: a factual claim written into a `why:` line escapes the check.

A miss is a **flag naming the term and the section**, and does **not** set `unbacked`: the pointer
resolved, and what failed is a heuristic over an author's prose whose false-positive rate cannot be
bounded. 2.4 and 8.5 remain the only two producers of `unbacked`. To close the gap that leaves —
an unmarked factual claim shipping — **`dawmans validate` exits non-zero on a term miss**. The
author is present at validate time, which is the same argument 2.2 rests on, and a non-zero exit
costs a re-read rather than a caveat on every citation drawn from the passage.

### Passage emission

**One passage per entry** (3.3), splitting only when the entry exceeds the chunker's 350-word cap.
An entry of five causes runs to roughly 150 words, so the split path is rare but real. Mapping onto
the corpus loader's types, which gives 3.3 for free:

| Entry part | Emitted as |
|---|---|
| symptom + `also:` phrasings + preamble prose | `Unit(repeat_on_split=True)` — first, so a split passage never carries a cause without its symptom |
| each cause: statement, `check:`, `why:`, prose | one `Unit(atomic=True)` — never split within a cause |
| closing statement | one `Unit(atomic=True)` |
| — | `Region(section_number=None, section_title=<symptom>, section_path=(), page_start=None, page_end=None, inferred=False)` (3.4, 3.5) |
| a cause under 2.3, or with a drifted pointer | `UnitFlags.unbacked` on that cause's unit (2.4, 8.5) |

`section_path` is empty because an entry has no ancestor titles, and `inferred` is `False` because
the section title is declared by the author, not recovered from heading styles. Every authored unit
carries `degraded=False` and `has_figures=False` (3.6): the text is plain and there is no image
content to point at.

**Chunk overlap is suppressed for authored regions.** The corpus chunker carries ~50 words of
overlap within a region, and the symptom unit is `repeat_on_split` rather than `atomic`, so a split
entry's second chunk would otherwise carry the symptom twice — in text that is hashed into
`passage_id` and shown to the user when the citation is expanded. The repeat rule already gives the
continuity overlap exists to provide.

Alternative phrasings sit in `Passage.text` rather than in metadata precisely so BM25 sees them. Fix
pointers do **not**: CONTRACTS §2 fixes the field set, so per-cause structure travels in a sidecar
(below), which also keeps a pointer retarget from changing the passage's identity.

Because the flag is per-unit, a split entry marks only the passage carrying the unbacked cause and
an unsplit entry marks the whole thing — the over-marking 2.4 chose, no worse than it mandates, and
the coverage report names the cause in both cases (6.4).

### Identity

`source_id` is the constant **`authored/triage`** (CONTRACTS §1; 3.1's content-derived reading is a
requirements defect, see below), and `passage_id` is
`corpus.passage_id("authored/triage", passage_text)` — the same function over the same canonical
form, so authored and manual IDs behave identically under re-ingestion.

The whole `SourceRecord` (3.1, 3.2, 3.7, 5.1, 5.5), constructed once per run:

| Field | Value |
|---|---|
| `kind` | `authored-triage` (CONTRACTS §4a) |
| `source_id` | `authored/triage` — the constant, per CONTRACTS §1 |
| `display_name` | `My Triage Notes` — reads in the citation header and the picker as the user's own notes, never as a vendor document (3.1). It is the header's `{display_name}`, so it renders as `My Triage Notes — No sound from a track` |
| `hardware_applicability` | **`assumed`, unconditionally.** Fixed by CONTRACTS §1; nothing reads it from configuration and nothing can raise it (3.8 is a defect, see below) |
| `ingested_at`, `chunk_count` | from the run, inventory only |
| `vendor`, `product`, `doctype`, `lang`, `doc_version`, `page_count`, `low_text` | **absent.** Not applicable to this kind; `manual-corpus` 12.5's constructor refuses a value for each of them |

Every passage and citation drawn from an entry resolves to this one record (3.7), which is what
carries `kind` to the user.

**The canonical rendering hashed is `passage_text` itself** — the text the chunker emits and the UI
shows. There is no second canonical form: `corpus.passage_id` canonicalises NFC, collapses
whitespace and strips, which frees blank lines and CRLF, and marker style is already normalised by
the parser before the text is built (§Entry grammar). What the text contains is the symptom, the
alternative phrasings and preamble, and the causes' statements, checks, why-notes and prose, in
order. Excluded, each deliberately:

| Excluded | Because |
|---|---|
| frontmatter, including its key order | a device added to scope must not orphan the entry's history |
| fix pointers | retargeting after a manual renumbers is the frequent maintenance event, and must not orphan history — the argument `manual-corpus` uses for excluding `section_number` |
| the file's name and path | 1.8 |
| authoring cosmetics | marker style, blank lines, CRLF — normalised by the parser or by `passage_id`'s own canonicalisation |

`manual-corpus`'s duplicate-suffixing rule (`.2 … .k` for byte-identical chunks within a source)
cannot fire here: 1.9 rejects two entries with the same symptom in intersecting scope, and two
entries differing anywhere in their text hash differently. The ordering-dependence that rule guards
against is therefore not reachable on this source.

**Editing one cause changes the whole entry's ID**, because the entry is the passage. Other entries
are untouched — that is the point of one file per symptom. A citation held in retained UI history
then fails to resolve, and must render as no-longer-available rather than resolving to the edited
text: the author edited the entry because it was wrong, and silently reattaching the old citation to
the corrected text is the one outcome worse than a dead link.

### Device scope

Frontmatter `devices` → validated → published per `passage_id` in the sidecar → consumed by
`api/answer-engine` 5.12–5.13 as the per-passage predicate. This spec filters nothing itself (4.3).

| Declared device | Result |
|---|---|
| in `rig.yaml` and indexed as a `vendor-manual` | scoped normally |
| in `rig.yaml`, no indexed source — **no device today** | scoped, and reported as applying to an undocumented device (4.4) |
| indexed as a `vendor-manual`, not in `rig.yaml` | scoped normally, no flag |
| in neither, and the entry declares at least one device that *is* recognised | flag naming the declaration (4.5); the entry still ingests |
| in neither, and **every** declared device is unrecognised | rejection (`all-devices-unrecognised`) |
| `@revision` differing from the rig device's `revision` | flag (4.6) |

"Indexed" in that table means **every identity the corpus documents** — each indexed `vendor-manual`
`source_id` together with the device id it declares under `source_applicability` — not the source
ids alone (Decision 8). The two differ wherever a filename carries a generation marker the rig id
does not, which is `manual-corpus` §Rig inventory's worked Focusrite case, and matching source ids
alone would put today's `focusrite/scarlett-solo` declaration on the second row while its guide sits
in the corpus.

The third row exists because 4.5's condition is "neither in the rig inventory **nor** an ingested
source", and an ingested source absent from `rig.yaml` satisfies neither branch of the flag: it is a
device removed under 8.7, or a manual added ahead of its rig entry. Flagging it would be a warning
4.5 does not authorise.

The fifth row deviates from 4.5's literal "flag" and is recorded below as a defect. An entry none of
whose devices is recognised is excluded from **every** turn under 5.13 for as long as the typo
survives, while still being embedded and still occupying a row: unreachable, unreported at the point
of use, and costing budget. A rejection names the typo at the desk.

Revision comparison is **exact after casefolding and stripping non-alphanumerics** —
`@mk2` against `revision: mk2` matches, `@12-standard` against `revision: "12 Standard"` matches,
`@suite` does not. Loose either-contains matching would let `@12` and even `@s` satisfy
`12 Standard`, which defeats 4.6's mk1/mk2 case. The flag message quotes the rig's value verbatim,
so correcting a declaration is a copy rather than a guess.

`api/answer-engine` 5.12 puts every owned-but-undocumented rig device into the turn's device scope
unconditionally, so an entry for such a device survives 5.13's filter although no source for it can
be selected. That is why 2.3's allowance and 4.4's report suffice, and no pseudo-source is
registered for undocumented gear. The set is empty today — this was written of the Scarlett Solo,
whose guide has since been ingested — and the argument is unchanged: it is what keeps an entry
reachable in the window between declaring a device and obtaining its manual.

### Reject versus flag, with no memory

2.2 rejects a pointer that never worked; 8.4 flags one that stopped working. Nothing in the entry
distinguishes them, and `index/` is derived and deleted by a rebuild, so it cannot be the memory.

The memory is **`triage/.pointer-ledger.jsonl`** — machine-written, committed, one row per **pointer**
recording that it resolved and to what.

- The key is the **pointer alone**: `(source_id, section number, or normalised title where there is
  no number)`, serialised as `ableton/live-12 §16.4` or `akai/apc-key-25 "shift functions"`.
  Verification is a property of the pointer's target, not of the entry holding it. Keying on the
  entry — the symptom plus its device set — would make adding a device to `devices:` change the key,
  so any pointer that had since drifted would become a 2.2 **rejection**: an entry withdrawn
  mid-session by a cosmetic edit unrelated to pointers.
- A pointer with **no ledger row** has never been verified by anyone ⇒ unresolved is a **rejection**
  (2.2). This still covers a new cause added to an old entry: the row records the pointer, and a
  newly typed pointer has none.
- A pointer **with** a row ⇒ unresolved is a **flag** plus `unbacked` on its cause (8.4, 8.5), the
  entry stays ingested, and the row is retained so a later resolution clears the flag (8.5).
- Rows are **never pruned**. A row only ever records that a pointer *did* resolve, so a stale row
  costs one line and nothing else, and never deleting is what makes the union merge below sound.
- Deleting the file re-arms 2.2 for everything. That is the honest degradation, since the file is
  the only claim that a pointer once worked, but it is not silent: a missing ledger emits one report
  line saying so, or the author meets a wall of rejections with nothing explaining them.

**Format and merge behaviour.** The ledger is newline-delimited JSON — one
`{"pointer", "resolved_at", "passage_ids", "entry_keys"}` object per line, sorted by pointer — with
`.gitattributes` setting `merge=union` on it. A single JSON object cannot be merged by git, and
"never hand-edited" is unenforceable in exactly the situation git demands it. One row per line plus
union merge makes two machines' additions combine without a conflict, and sorting keeps the diff to
the rows that changed. `resolved_at` is written **only on transition** — first resolution, or
resolution after a drift — so a run that changes nothing leaves the file byte-identical and the
working tree clean. `entry_keys` is an annotation for the coverage report, not part of the key.

**An unparseable ledger is a failure, not a rejection.** No entry is at fault, and continuing would
silently re-arm 2.2 for the whole store and reject entries 8.4 requires be served with a mark. The
run exits non-zero naming the file and the offending line.

`dawmans validate` (5.4) reads the ledger and never writes it, so checking work before committing to
it cannot promote a broken pointer to "previously fine".

### Discovery, fingerprint and the run budget

`Discovered.fingerprint` is sha256 over the sorted `(relative path, file digest)` pairs — the store's
own bytes and nothing else. It still has consumers: the shard meta records it, and it enters
`manifest.corpus_revision`, which `api/answer-engine` 5.10 reads. What it does **not** do is gate the
load.

**The authored store is exempt from fingerprint-based shard skipping: `load()` runs on every
ingest, unconditionally.** 2.1 asks for pointer resolution to be verified on every run, and a
fingerprint cannot deliver that, because the authored source's validity is a function of the manuals
as well as its own text. Folding `manifest.corpus_revision` into the fingerprint does not fix it and
is worse than doing nothing: the manifest is written **last** while discovery runs **first**, so at
run *n* the value read is run *(n−1)*'s. The fingerprint is unchanged, the shard is reused, `load()`
never runs, and no pointer is re-checked — drift is detected exactly one run late. It also feeds
back: the authored fingerprint feeds `corpus_revision`, so one manual edit would trip
`api/answer-engine` 5.10 on two consecutive runs.

Running unconditionally costs nothing. Parsing, resolving and term-checking 200 entries is a single
pass over ~1,000 vendor passages plus ~1,200 substring tests — comfortably under a second — and the
per-`passage_id` vector map in the authored shard meta already removes the embedding cost for every
entry whose text did not change.

**5.6 is met warm and is not met cold**, and 5.6 carries no warm/cold qualifier while a fresh clone
is always cold: `manual-corpus` measures a 7.2 s model load, which the corpus CLI pays once per run
before iterating sources. There is a real remedy, and it is the second outstanding request above: if
every authored `passage_id` is present in the shard meta's `vectors` map, the authored shard needs
**no** embedding at all, so a lazy-on-first-embed model load means an authored-only ingest never
loads the model and 5.6 holds cold as well as warm. Until that change is made, the deviation stands
as stated — met warm, exceeded cold by the model load — rather than being met by qualifying the
criterion. `dawmans validate` embeds nothing and is unaffected either way.

An entry added, edited or removed is reflected on the next run with no rebuild (5.1) because
discovery is a directory scan (§The store on disk) and `load()` is unconditional; nothing about the
store is compiled in, and no configuration names an entry.

### Coverage without a taxonomy

There is no enumerable universe of symptoms, so the report has no denominator and states **no
percentage**. It is an inventory of what exists plus the one gap that *is* enumerable — the rig side
(6.3). Rows: every entry with symptom, scope, cause count and pointer health (6.1); every rejection
and flag with its reason (6.2, and 5.5's per-run reasons); rig devices no entry mentions (6.3);
causes without a pointer and the device each names (6.4); entries flagged for drift with the source
that changed (8.6); entries scoped only to a device that has left the rig (8.7).

`dawmans coverage` renders it to stdout and writes it into the sidecar's `report` block (6.5).
**6.6 is not satisfiable from this side alone.** `api/answer-engine` 9.6 relays the
owned-but-undocumented report, which is a different payload with a different owner; nothing in that
spec or in `ui/ask-and-source-picker` yet consumes a triage coverage report. Publishing it in the
sidecar puts it where a consumer can read it; 6.6 closes when a criterion there names it.

### Module placement

Inside `dawmans/triage/`, the package `manual-corpus` reserves for this spec.

```
src/dawmans/triage/
  loader.py     TriageLoader — the SourceLoader for kind authored-triage
  parse.py      entry file → Entry; canonical rendering
  pointers.py   pointer grammar, the section index, resolution, the ledger
  terms.py      2.6 extraction and containment
  scope.py      device declarations against rig.yaml; the sidecar
  coverage.py   the §6 report
```

`dawmans/cli.py` gains `coverage`; its existing `validate` gains the entry store.

---

## Components and Interfaces

```python
class TriageLoader:                       # satisfies corpus SourceLoader
    def __init__(self, store: Path, corpus: CorpusView, rig: Rig, ledger: Ledger): ...
    def discover(self) -> Iterable[Discovered]: ...   # 0 or 1 — the store is one source
    def load(self, d: Discovered) -> LoadResult: ...  # regions in sorted path order, sidecar in .sidecar

@dataclass(frozen=True)
class Entry:
    symptom: str; phrasings: list[str]; preamble: str
    devices: list[DeviceRef]
    causes: list[Cause]                   # declared order, never sorted
    closing: str | None
    source_file: Path                     # repo-relative, e.g. triage/no-sound-from-track.md
    line: int                             # the H1's line; with source_file, CONTRACTS §2 entry_location

@dataclass(frozen=True)
class Cause:
    statement: str; check: str; notes: str
    fixes: list[Pointer]                  # empty ⇔ undocumented_device is set (2.3)
    undocumented_device: str | None

@dataclass(frozen=True)
class DeviceRef:
    id: str                               # "<vendor>/<product>", matched exactly against rig.yaml
    revision: str | None                  # the @suffix, compared per §Device scope

@dataclass(frozen=True)
class Pointer:
    source_id: str
    section_number: str | None            # at least one of these two is set
    section_title: str | None             # raw; normalised on lookup
    line: int                             # for the 5.3 message

@dataclass(frozen=True)
class Unresolved:
    pointer: Pointer
    reason: Literal["unknown-source", "no-such-section", "ambiguous-title", "authored-target"]
    candidates: list[str]                 # nearest sections, for the 5.3 message; [] where none apply
```

Behavioural contracts the signatures do not carry:

| Type | Contract |
|---|---|
| `SectionIndex` | built once per run from the view's `passages.jsonl`; two maps, `(source_id, section_number)` and `(source_id, normalised title)`, each to the section's passage ids **in section order**. Immutable once built; resolution is pure and order-stable, so two runs over one view resolve identically |
| `Ledger` | append-and-update over the NDJSON rows of §Reject versus flag. `read()` under `dawmans validate` is **read-only** — no row is added, no `resolved_at` moved — so validating cannot promote a pointer to "previously fine". Only `dawmans ingest` writes, and only on transition. An unparseable file raises rather than returning an empty ledger |
| `CorpusView` | ~~**read-only** over `views/<hex>/passages.jsonl` and `sources.json`, located through `manifest.view_dir`. It never opens a shard, a vector file or a PDF~~ — **superseded by [Decision 13](decision_log.md)**, which keeps every clause but the source of the rows: under `dawmans ingest` they are read from the `vendor-manual` shards **this run has committed**, because the view this run will publish does not exist until the merge, which runs after every loader. `dawmans validate` runs outside a run and reads them from `views/<hex>/`. Read-only either way, and no vector file, PDF, extraction, chunking or embedding (5.7, `manual-corpus` 12.4), so re-ingesting the authored source cannot re-extract, re-chunk or re-index a manual. One corpus is read for the whole run, so every pointer in a run resolves against one consistent set of passages |

```python
def resolve(p: Pointer, idx: SectionIndex) -> list[str] | Unresolved   # passage_ids, in section order
def terms(cause: Cause) -> list[str]                                   # 2.6 extraction
```

`load` never rewrites an entry file; the ledger is its only mutable output.

---

## Data Models

### The sidecar — `index/views/<hex>/reports/<slug>.json`

Everything `Passage` cannot carry, keyed by `passage_id`. Written by the corpus from
`LoadResult.sidecar`, and **read by `api/answer-engine`**, which promotes that channel from
diagnostic output to a contract — which is why `manual-corpus` now separates it from the ingestion
audit it used to share a file with.

`<slug>` is the corpus's own rule — `source_id` with `/` replaced by `_` — so the file is
`authored_triage.json`. Naming it literally, and hyphenating it, is a silent failure: the corpus
writes `authored_triage.json`, a reader following a hyphenated name finds nothing, no error is
raised, and under 5.13 no passage declares devices, so **every entry stays in scope for every turn**.

It sits **inside the view directory**, not beside it. `manifest.json`'s rename is the only switch
`manual-corpus` provides, and a sidecar written in place pairs arbitrarily with whichever view a
reader has loaded — dropping entries from turns they apply to, or admitting entries scoped to other
gear. Inside `views/<hex>/` it commits and swaps atomically with the passages it keys.

This was the first outstanding request on `manual-corpus`, and it has **landed**. That design's
§Index layout splits the report channel by lifetime: view sidecars go inside the view at
`views/<hex>/reports/<slug>.json`, per-run ingestion audits stay beside it at
`index/audits/<slug>.json`, and its Decision 8 records the split. One consequence reaches this spec:
the sidecar is committed as a shard artefact and copied into the view by the merge, so it survives
shard reuse. That costs nothing here — this store's `load()` runs on every ingest (§Discovery,
fingerprint and the run budget), so its sidecar is regenerated every run regardless — but it means
the revision guarantee does not rest on that fact.

```json
{"passages": [
  {"passage_id": "authored/triage#9f3c1a…",
   "entry_key": "a41e…",
   "symptom": "No sound from a track",
   "devices": [{"id": "ableton/live-12", "revision": null}],
   "source_file": "triage/no-sound-from-track.md", "line": 7,
   "causes": [
     {"statement": "The Track Activator is off",
      "check": "the track's number is dimmed in the mixer",
      "fix": [{"source_id": "ableton/live-12", "section": "16.4",
               "passage_ids": ["ableton/live-12#4b12…"]}],
      "undocumented_device": null, "flags": []},
     {"statement": "Direct monitoring is on at the interface",
      "check": "the DIRECT MONITOR switch is pushed in",
      "fix": [{"source_id": "focusrite/scarlett-solo-4g", "section": "…",
               "passage_ids": ["focusrite/scarlett-solo-4g#9ae0…"]}],
      "undocumented_device": null, "flags": []}]}],
 "report": {"entries": 5, "rejected": 0, "flagged": 0,
            "pointers": {"checked": 14, "resolved": 14, "unresolved": 0, "without_pointer": 0},
            "rejections": [], "flags": []}}
```

Every cause in the starter set is backed, so this payload shows no `unbacked-cause`. The shape it
takes when one is not — the state 2.3 admits and no device is in today — is
`"fix": [], "undocumented_device": "<rig device id>", "flags": ["unbacked-cause"]`, with a matching
`report.flags` row whose `detail` reads `<rig device id> has no ingested source`, `flagged`
incremented and `without_pointer` counting it. That path is exercised against a fixture rig, since
the live one cannot produce it.

`devices` here is the input to the 5.13 predicate; `causes` in order is the input to
`api/answer-engine` 7.2 and 7.6, which need the ranked list with its checks and fix citations, not
just the passage text. The pointer counts are 2.8. `rejections` and `flags` carry one row per
occurrence with its reason, which is what 5.5 asks for beyond the counts; they hold the same rows
`dawmans coverage` renders (§Coverage).

**`source_file` and `line` now have a named consumer, and it is a governed one.** They are the two
halves of CONTRACTS §2 `entry_location`, which the engine joins as the one opaque display string
`triage/no-sound-from-track.md:7` and puts on every authored `Citation` (CONTRACTS §3), where
`ui/ask-and-source-picker` 5.19 shows it and makes it copyable. That is the whole of the
open-at-source action for a pageless source (CONTRACTS §3a): no browser mechanism reaches a line in
a file, so the entry is revealed in place — through the passage the citation already addresses — and
its location is handed to the user rather than to a launcher. The label this design has carried since
it was written is therefore true rather than aspirational.

Two consequences. **`source_file` is repo-relative and that root is now fixed** (3.5): the string is
user-visible and pasted into an editor, so it may not drift to store-relative later. And
`entry_location` is a **locator, not an identity** — it moves whenever the author edits the file
above the heading — so it stays out of `passage_id` and `entry_key` derivation, exactly as
CONTRACTS §2 requires and as §Identity already computes them.

The `causes` array acquires a second governed consumer at the same time: it is the source of
CONTRACTS §4c's `Cause` records, whose `rank` is the declared position. 1.5's "never re-order" is now
load-bearing on `api/answer-engine` 7.6 and `ui/ask-and-source-picker` 6.6 as well as on retrieval.

`entry_key` — sha256 over the normalised symptom and the sorted device ids — is an annotation, not
a key of anything: it gives the report a stable handle on an entry across a file rename. 1.9's own
test is broader than key equality and is stated in §Error Handling: same normalised symptom,
**intersecting** device sets. Exact set equality would let the same symptom scoped `[live-12]` and
`[live-12, apc-key-25]` both ingest, both be retrievable in any Live-scoped turn, and no duplicate
be reported — which is the outcome 1.9 exists to prevent.

### The ledger — `triage/.pointer-ledger.jsonl`

Newline-delimited, one row per pointer, sorted by pointer.

```json
{"pointer": "ableton/live-12 §16.4", "resolved_at": "2026-08-14T10:00:00Z", "passage_ids": ["ableton/live-12#4b12…"], "entry_keys": ["a41e…"]}
{"pointer": "akai/apc-key-25 \"shift functions\"", "resolved_at": "2026-08-14T10:00:00Z", "passage_ids": ["akai/apc-key-25#77aa…"], "entry_keys": ["b93d…"]}
```

---

## Error Handling

Per **entry**, not per source: a rejection excludes one entry, the rest ingest, the run succeeds
(5.2). The whole source is rejected as `authored-invalid` (`manual-corpus` 12.6) only when no entry
survives, since a source with no passages is not a source.

| Rejection | Raised when | Criterion |
|---|---|---|
| `frontmatter-missing` / `-malformed` | no `---` fence at byte 0 after BOM stripping, or YAML that will not parse | 4.1 |
| `no-devices` | `devices` absent or empty | 4.1 |
| `devices-not-a-list` | `devices` parses to anything but a list — `devices: ableton/live-12` is valid YAML, is a non-empty string, and iterates as characters | 4.1, 4.2 |
| `no-symptom` | any count of H1s other than one | 1.1 |
| `too-few-causes` / `too-many-causes` | outside 2–6 | 1.1, 1.4 |
| `cause-missing-check` / `cause-missing-fix` | a cause lacking one, and not the closing statement | 1.2 |
| `cause-fix-and-undocumented` | one cause carrying both a `fix:` line and an `undocumented:` line | 2.3 |
| `pointer-unresolved` | no ledger row and it does not resolve | 2.2 |
| `pointer-authored-target` | the pointer names `authored/triage` | 2.7 |
| `undocumented-claim-invalid` | `undocumented:` names a device absent from the rig, or one that *is* indexed | 2.3 |
| `all-devices-unrecognised` | no declared device is in the rig or indexed — the entry could never be retrieved | 4.5 (deviation, see below) |
| `duplicate-symptom` | two entries share a normalised symptom and their device sets intersect — **both** rejected | 1.9 |

Flags, all leaving the entry ingested: `pointer-drifted` (8.4, sets `unbacked`), `unbacked-cause`
(2.3/2.4, sets `unbacked`), `term-not-in-passage` (2.6), `unknown-device` (4.5),
`revision-mismatch` (4.6), `title-number-disagreement`, `undocumented-device-scope` (4.4),
~~`orphaned-scope` (8.7)~~, `closing-statement-inferred`, `unknown-frontmatter-key`.

`orphaned-scope` is **superseded by [Decision 15](decision_log.md)**: 8.7's orphaned entry is a
**coverage row** (§Coverage without a taxonomy) rather than a flag, because §Device scope's third row
forbids flagging the device it would be about. The constant stays in the closed vocabulary as that
row's name, and nothing raises it as a `Flag`.

**Failures**, which exit non-zero rather than rejecting an entry: an unparseable ledger (§Reject
versus flag), and a term miss under `dawmans validate` only (§The term check). `dawmans validate`
additionally exits non-zero on a **rejection** ([Decision 14](decision_log.md)); 5.2's "the run
reports succeeded" governs `dawmans ingest`, which is the run that serves the other entries.

**`authored-invalid` deletes the authored shard.** Without that, a rejected source produces no
shard, the merge reads whatever shards exist, and re-ingestion replaces a shard only on success — so
a store in which every entry has become malformed keeps serving the previous run's passages while
the run reports the rejection and succeeds. Deleting the shard makes the rejection visible in the
index rather than only in the report. The store's own presence follows `manual-corpus`'s rule: an
existing but empty `triage/` is an **empty discovery set** and its shard is removed; an absent or
unreadable `triage/` is an **unavailable store** and its shard is retained.

Messages name the file, the symptom and the cause, and say what to change (5.3):

```
triage/no-sound-from-track.md — "No sound from a track"
  rejected: cause 2 "Another track is soloed" points at ableton/live-12 §16.5,
  which is not a section of that manual. Nearest: §16.4 "The Mixer",
  §16.7 "Mixing with Groups". Correct the pointer or drop the cause.

triage/kick-distorting.md — "A track is distorting"
  flagged: cause 1 says "Drum Buss" but ableton/live-12 §24.2 "Saturator"
  does not contain that term. Point at the section that documents it.
```

Nearest-section suggestions come from the same normalised title index, by edit distance.

---

## Requirements defects to reconcile

Four places where the requirements and CONTRACTS cannot both be satisfied as written.

1. **3.1's "source ID derived from the source's own content".** CONTRACTS §1 governs and fixes the
   constant `authored/triage`: a content digest prefixes every `passage_id`, so it would orphan the
   whole citation history on every edit to any entry — the opposite of 3.9 and 8.2. A declared
   constant satisfies the clause's operative half, "independent of any filename". 3.1 is the defect.
2. **3.8's "`assumed` unless the author has explicitly declared it confirmed".** CONTRACTS §1 fixes
   the source-level value at `assumed` with no exception, and `manual-corpus` §Rig inventory states
   that nothing in `rig.yaml` sets it. Implementing 3.8 literally would mean a user writing
   `authored/triage: {status: confirmed}` obtains `confirmed` applicability on their own notes,
   which is the claim CONTRACTS §5 exists to prevent. Implemented as an unconditional `assumed`
   (§Identity). 3.8 is the defect.
3. **8.1 requires a pointer to identify its target by "the identity of the passage".** Read
   literally that is a `passage_id`, which 1.7 forbids the author from hand-computing, and which a
   re-chunk would break. Section-level addressing satisfies 8.1's *purpose* — a stable target that
   is not a page — and its own stated reason, "page numbers move between document versions; passage
   identity does not". It is not, however, a reading of 8.1's words. Either 8.1 says "the identity
   of the section" or 1.7 admits a computed value.
4. **4.5 requires a flag where every declared device is unrecognised.** Implemented as a rejection
   (§Device scope): such an entry is unretrievable in every turn under `api/answer-engine` 5.13 for
   as long as the typo survives, so a flag leaves it costing budget and reaching nobody. The
   deviation is confined to the all-unrecognised case; *some* unrecognised still flags, as 4.5 says.

---

## Testing Strategy

`pytest` + `hypothesis`, per `manual-corpus`.

### Genuine invariants (property-based)

Generators produce the `Entry` **model** and render it to Markdown, rather than generating Markdown
text — the reverse direction cannot state what the expected parse is.

| Property | Guarantee | Criteria |
|---|---|---|
| Order preservation | for any entry, the emitted causes are the declared causes, in order, unmerged and undeduplicated | 1.5 |
| Cause conservation | the number of causes emitted plus the number of `closing-statement-inferred` flags equals the **total** number of H2s, so no section ever leaves the parse unaccounted for. It is stated over the total rather than over the H2s that were not the author's closing statement because the parser cannot tell those apart — that is the whole of Decision 6, which is why it flags every inferred closing statement | 1.5 |
| Total parsing | for **any** byte string, the parser returns an `Entry` or a rejection naming the file; it never raises and never returns a half-built entry | 5.2 |
| Cosmetic invariance of `passage_id` | perturbing marker style, blank lines, key casing, line endings, frontmatter key order and pointer targets leaves the ID unchanged | 3.9, 8.2 |
| `passage_id` sensitivity | any change to symptom, phrasings, preamble, cause statement, check or notes changes the ID | 3.9 |
| Canonical idempotence | `render(parse(render(parse(f)))) == render(parse(f))` | 3.9 |
| Split invariants | for an over-cap entry, every emitted passage contains the symptom exactly once and no cause spans two passages | 3.3 |
| `unbacked` monotonicity | every passage carrying a 2.3 or 8.4 cause is flagged; no passage is flagged without one | 2.4, 8.5 |
| Term-check soundness | a cause whose terms are all lifted verbatim, with their case, from any one of its pointers' resolution sets never raises `term-not-in-passage` | 2.6 |
| Ledger key stability | editing an entry's `devices:` or its symptom wording changes no ledger key, so no previously resolving pointer becomes a 2.2 rejection | 2.2, 8.4 |
| Reject/flag state machine | over random sequences of (ingest, edit an entry, edit a manual, remove a manual, restore it), a pointer that resolved at least once is never again a rejection, only a flag — and resolving again clears it | 2.2, 8.4, 8.5 |

The reject/flag rule is a function of history, only wrong after a particular sequence of runs, and
no example test reaches those sequences. Term-check soundness is stated in one direction only,
deliberately — recall is a heuristic, not an invariant, and asserting it would pin the extractor's
false-negative rate as if it were a contract.

**Not** properties, and written as examples: that `§16.4` and `"Shift Functions"` parse; that
`**Check:**` is recognised; that a duplicate rejects both entries; the five starter entries.

### Fixtures

| Fixture | Asserts |
|---|---|
| `triage/*.md`, the five starter entries (7.2–7.6) | product content that doubles as the grammar's worked examples. Every fix cites a vendor passage with no exception (7.8): 2.3's carve-out admits no device now that all four manuals are ingested, so the direct-monitoring cause points into the Scarlett guide like any other |
| `scarlett_sections.json` — the sections the direct-monitoring cause points at | the same offline pointer resolution as `live_sections.json`, for the manual that closed the last corpus gap |
| `live_sections.json` — section numbers, titles and text slices for the ~15 sections the starter set points at, extracted once from the real index and committed | pointer resolution and the term check run in CI with `manuals/` absent, exactly as the corpus's extraction snapshots do; includes the section printing `0 dB` that 7.3's cause depends on |
| `apc_sections.json` — unnumbered regions | the title form resolves where no section number exists |
| `split_section.json` — one section chunked into three | a pointer resolves to all three, and the term check sees their concatenation |
| `three_causes_last_demoted.md` | an entry of three causes whose last loses both its check and its fix parses as two causes plus a note, and emits `closing-statement-inferred` naming the demoted section rather than dropping it silently |
| `overlapping_scopes/` — the same symptom scoped `[live-12]` and `[live-12, apc-key-25]` | both rejected under 1.9: intersecting scopes, not identical ones |
| `nested/live/no-sound.md` | a subdirectory entry is discovered; a `.txt` beside it reports; `.pointer-ledger.jsonl` does not |
| malformed entries, one per rejection reason | message names file, symptom and cause; the other entries in the same run still ingest |
| `drift/` — the same section with edited text, plus a seeded ledger | first run rejects with no ledger row; seeded run flags and sets `unbacked`; restoring the text clears it; a hand-corrupted ledger fails the run |

7.7 needs the real manuals and a built index, so it is a `make bench`-style integration target that
skips when `index/` is absent — the same honest limitation `manual-corpus` accepts for its 8.1.
