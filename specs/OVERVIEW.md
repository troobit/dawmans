# Specs Overview: DAWMans

**Generated index.** Regenerated from the folders under `specs/`, never hand-merged — see
[`PROCESS.md`](PROCESS.md) §9. On a merge conflict, regenerate rather than resolve. Everything
below is derived from the files actually present; nothing is anticipated.

**Generated:** 2026-08-15 · **Specs:** 4 · **Anchored acceptance criteria:** 409 · **ADRs:** 48 per-spec + 12 cross-cutting · **Task ledgers:** 4 of 4

---

## What DAWMans is

DAWMans is a localhost webapp that answers home-studio questions **strictly from the user's own
sources** — the vendor manuals for their gear plus an authored symptom-triage source they write
themselves — with every factual claim cited to a section and a page, and with NotebookLM-style
per-source scoping so the user chooses which sources may ground a given answer. It is built for one
person, on one machine, glancing at a second screen mid-session: the rig is **Ableton Live 12
Standard, an Akai APC Key 25 mk2, a Focusrite Scarlett Solo 4th Gen and an Alesis Nitro Max, on
macOS** — all four now documented by an ingested manual. It
answers from the manual corpus only; session awareness sits behind a defined but unbuilt
`StateSource` seam (DECISIONS Decision 4, refined by Decision 8).

## Governing documents

| Document | Standing |
|---|---|
| [`PROCESS.md`](PROCESS.md) | The process source of truth: how specs are written, gated, and turned into code. Kept as shipped by the template. |
| [`CONTRACTS.md`](CONTRACTS.md) | **Governing** for anything crossing a spec boundary — the four records, the turn's SSE event set, the `body` block types, the open-at-source mechanism, the closed outcome taxonomy and its reason vocabulary, the composed latency budget. Where a spec and CONTRACTS disagree, **CONTRACTS wins and the spec is the defect**. A spec may not invent a field on a shared record nor silently drop one. |
| [`DECISIONS.md`](DECISIONS.md) | The cross-cutting meta log — twelve ADRs shaping the project as a whole. It is a synthesis: per-spec `decision_log.md` files remain **authoritative for detail**, and where the two disagree the per-spec log wins. |
| `OVERVIEW.md` (this file) | Generated index. Regenerate; do not hand-merge. |

## Domains

Four domains, with `ops` pruned (DECISIONS Decision 1). The set is closed — adding to it is an
amendment to that decision, not an ad-hoc `mkdir`.

| Domain | Owns | Specs |
|---|---|---|
| `platform` | App shell, build, packaging, **provider key configuration** | **none — see the open gap below** |
| `data` | Manual ingestion, chunking, the searchable corpus | 2 |
| `api` | Local HTTP backend, outbound LLM provider integrations, future Ableton state sources | 1 |
| `ui` | The browser surface | 1 |

> **Open gap — `platform` has no spec.** Decision 1 assigns provider key configuration to
> `platform`, but no `specs/platform/` folder exists. That work is currently described only from
> the two sides that consume it: `api/answer-engine` §6 (provider abstraction and credential
> handling) and `ui/ask-and-source-picker` §10 (the configuration surface, by provider kind).
> Nothing owns the shell, the build, or where a key is actually stored on the machine.

## Specs

All four are at **requirements and design complete**. Each design has been reviewed and repaired, and
all four now carry a `tasks.md` ledger. Two are being built: `data/manual-corpus` is **fully
implemented** — all 45 tasks across all 8 phases — and `data/symptom-triage` is through its first
four phases, 16 of 29. `api/answer-engine` and `ui/ask-and-source-picker` have ledgers and no
implementation yet.

| Path | Domain | Capability | What it delivers | Phase | Criteria |
|---|---|---|---|---|---|
| [`data/manual-corpus/`](data/manual-corpus/requirements.md) | `data` | manual-corpus | Ingestion only: turns a folder of vendor PDFs and the authored triage source into a queryable, citable corpus — discovery, extraction fidelity, English selection, glyph repair, section-aware chunking with citation metadata, index build, inventory, and the rig-versus-corpus applicability report. | requirements ✅ · design ✅ · tasks ✅ (45 of 45 — phases 1–8) | 84 |
| [`data/symptom-triage/`](data/symptom-triage/requirements.md) | `data` | symptom-triage | The `authored-triage` source kind: symptom-to-cause entries the studio owner writes, each with ranked candidate causes, an observable check per cause, and a fix pointer into a vendor manual — plus the grounding rules, authoring loop, coverage reporting, starter set and drift handling. | requirements ✅ · design ✅ · tasks 🔶 (16 of 29 — phases 1–4) | 60 |
| [`api/answer-engine/`](api/answer-engine/requirements.md) | `api` | answer-engine | The middle layer: retrieval over ingested chunks, grounding and honest refusal, citation assembly, source scoping, the pluggable provider abstraction and credential handling, the `StateSource` seam, and the localhost-only HTTP contract. Speed is the headline property. | requirements ✅ · design ✅ · tasks ⬜ (0 of 45 — 9 phases) | 111 |
| [`ui/ask-and-source-picker/`](ui/ask-and-source-picker/requirements.md) | `ui` | ask-and-source-picker | The browser surface: the ask input and its one-key starters, the source picker and the corpus gaps it exposes, answer and narrowing rendering, citation inspection and open-at-page, waiting and error states across the whole outcome taxonomy, provider configuration, history, legibility and accessibility. | requirements ✅ · design ✅ · tasks ⬜ (0 of 47 — 9 phases) | 154 |

Criterion counts are the `<a name=` anchors in each `requirements.md`.

---

## Per-spec detail

### `specs/data/manual-corpus/`

- **Files present:** `requirements.md`, `design.md`, `decision_log.md` (19 ADRs), `tasks.md`,
  `prerequisites.md`. A complete file set, as `api/answer-engine`'s now is.
- 12 requirement sections, 84 anchored criteria. Owns `SourceRecord` and `Passage` from
  [`CONTRACTS.md`](CONTRACTS.md) §1–§2, and publishes the filename grammar two other specs now
  reconstruct (2.7). Reference corpus: roughly 1107 pages across four manuals.
- **Ledger:** 45 tasks over 8 phases, test-then-implement throughout, two work streams — **all
  complete**. Phase 1 — the `dawmans` package scaffold, the CONTRACTS §1/§2 records and the loader
  seam — phase 2 — the filename grammar, both source stores and shard removal — phase 3 — PDF
  extraction, the span model and the committed extraction fixtures — phase 4 — furniture marking,
  glyph repair and English selection — phase 5 — the section map, TOC anchoring, row and table
  assembly, and unit assembly behind the `PdfLoader` seam — phase 6 — chunking and passage
  identity — phase 7 — the embedding wrapper and its offline pin, the lexical index, the per-source
  shard with its four-part cache key, and the merge behind the manifest rename — and phase 8 — the
  rig inventory and its two gap reports, the per-run report and per-source audits, `dawmans ingest`
  / `validate` / `inventory` with the run orchestration, and the timing tests behind `make bench`.
  `prerequisites.md` records what no task can do: place the four gitignored PDFs, run
  `make fetch-model` once, and declare the Focusrite applicability mapping 11.7 makes mandatory.
  All three are done, and the committed `rig.yaml` carries that mapping.
- Explicit non-goals include OCR, image understanding, non-English content, automatic manual
  acquisition, and inferring hardware applicability from a document's contents.

### `specs/data/symptom-triage/`

- **Files present:** `requirements.md`, `design.md`, `decision_log.md` (12 ADRs), `tasks.md`.
- **Missing:** `prerequisites.md` — the two things no task here can do for itself are
  `data/manual-corpus`'s, and its `prerequisites.md` records them.
- 8 requirement sections, 60 anchored criteria. Header declares status *draft*.
- **Ledger:** 29 tasks over 7 phases, test-then-implement, one work stream — **16 done, phases 1–4**.
  Phase 1 — the entry model, the grammar and the canonical rendering — phase 2 — pointer resolution,
  the section index cut from a real view, and the committed pointer ledger that separates 2.2's
  rejection from 8.4's flag — phase 3 — device scope validation against the rig and the term
  check — and phase 4 — authored identity, the `SourceRecord` CONTRACTS §1 fixes, and
  `TriageLoader.load`'s region emission. Phase 5 (discovery, the sidecar and the run wiring) is next.
- Exists because the manuals cannot answer diagnostic questions: "gain staging" appears **zero**
  times in the 1009-page Live 12 manual and "troubleshoot" appears twice (DECISIONS Decision 7).
  §7 specifies a five-symptom starter set as the acceptance test for the source, and it is task 23.

### `specs/api/answer-engine/`

- **Files present:** `requirements.md`, `design.md`, `decision_log.md` (10 ADRs), `tasks.md`,
  `prerequisites.md`.
- **Ledger:** 45 tasks over 9 phases, none started.
- 10 requirement sections, 111 anchored criteria. Header declares status *draft*.
- Produces `Citation` and `AnswerEnvelope` ([`CONTRACTS.md`](CONTRACTS.md) §3–§4) and may emit only
  the outcomes in §6 of that file. Must define `StateSource` while shipping a null implementation
  (Decision 4).

### `specs/ui/ask-and-source-picker/`

- **Files present:** `requirements.md`, `design.md`, `decision_log.md` (7 ADRs), `tasks.md`.
- **Ledger:** 47 tasks over 9 phases, none started.
- 13 requirement sections, 154 anchored criteria — **129 behavioural [B]** and **25 target-and-band
  [T]**, the latter run as the iterative loop of [`PROCESS.md`](PROCESS.md) §5.
- Renders every outcome in the taxonomy and may invent none. Usage context (second screen, hands
  full, dim room) outranks feature richness in any trade-off.

Every spec carries a `decision_log.md` — 48 per-spec ADRs against the 12 cross-cutting ones in
[`DECISIONS.md`](DECISIONS.md) — and a `tasks.md`. Two carry a `prerequisites.md`, naming what no
task can do for itself. There are no `specs/bugfixes/` folders and no `smolspec.md` files.

---

## State of play

**What exists**

- Four `requirements.md` documents in EARS, criteria individually anchored, across three of the
  four domains.
- Four `design.md` documents, each reviewed and repaired against the review findings.
- One governing shared-contract document covering the seams between them.
- Twelve cross-cutting ADRs in `DECISIONS.md` and 48 per-spec ADRs, all *accepted*.
- **Four `tasks.md` ledgers, one per spec.** `data/manual-corpus` and `api/answer-engine` also carry
  a `prerequisites.md` naming what no task can do for itself.
- `data/manual-corpus` **fully implemented — all 45 tasks, all 8 phases.** The package, the
  shared records, both source stores, PDF extraction and the committed extraction fixtures, the
  text-conditioning stages — furniture marking, glyph repair and English content selection — the
  structural stages that turn a span model into `Region[]` (the section map and its three paths, TOC
  anchoring, row and table assembly, unit assembly and the `vendor-manual` load path), the
  chunker that turns `Region[]` into the `Passage` records the index is built from, with the
  content-derived passage identity a retained citation resolves through, the index build
  itself — the offline-pinned embedding wrapper, the lexical index whose tokeniser keeps
  `Dry/Wet` and `4th-gen` retrievable, the per-source shard reused only when all four of
  fingerprint, ingestion version and embedding model and dimension match, and the merge into a
  fresh view committed by renaming `manifest.json` last — and finally the rig inventory with its
  two gap reports, the per-run report and per-source ingestion audits, and `dawmans ingest` /
  `validate` / `inventory` over the whole stage order.
- **A working ingestion tool.** `dawmans ingest` runs against the real four-manual corpus: 4 sources,
  1431 passages, a full cold rebuild in ~43 s against 8.1's 60 s budget, and the gap reports come out
  as the design predicts — owned-but-undocumented empty, indexed-but-not-owned empty, and
  documented-but-unconfirmed naming the APC and the Nitro Max (`data/manual-corpus` Decision 16).
- `data/symptom-triage` **through phases 1–4, 16 of 29 tasks.** The entry model and its total
  parser, the canonical rendering, pointer resolution against a section index cut from a real view,
  the committed pointer ledger that separates a pointer that never worked from one that stopped,
  device scope validation against the rig, the term check, and now authored identity and the region
  emission behind `manual-corpus`'s loader seam.

**What is next**

- **The contract amendment has landed.** Decision 11 amended `CONTRACTS.md` — adding §3a, §4b–§4e
  and §6a, and rewriting §4, §6 and §7 — and reconciled all four specs against it in the same pass.
  Six defects closed; the table below records what closed each. That was the precondition for the
  task phase, and it is met.
- **`data/symptom-triage` phases 5–7** — discovery and the unconditional load, the per-`passage_id`
  sidecar, the validation messages, the coverage report, and the five starter entries §7 makes the
  acceptance test for the source. It is the spec that unblocks the rest: `manual-corpus` calls its
  `TriageLoader` behind the loader seam and today runs with one store, the end-to-end tests standing
  a stub in its place. Phase 4 landing means the loader now exists to wire in.
- **`api/answer-engine` and `ui/ask-and-source-picker` implementation.** Both have ledgers — 45 and
  47 tasks — and neither is started.
- **A closed gap made four mechanisms dormant** (Decision 12). Obtaining the Scarlett Solo 4th Gen
  guide documented the last undocumented device in the rig, so the owned-but-undocumented report is
  empty — and with it `required_manual`, the engine's device-scope union, triage's `unbacked` causes
  and the picker's known-gaps group. All four stay implemented and are tested against a fixture rig;
  the specs now say so where they used to name the Scarlett.
- **One contract defect remains and is not one of the six.** `CONTRACTS.md` §7 allots the concurrent
  retrieval-and-state stage retrieval's 50 ms, while `api/answer-engine` bounds that gather by the
  100 ms state timeout — the longest member. It composes today only because the null state source
  returns immediately, and it blocks `LogTailStateSource` rather than the MVP.
- `CONTRACTS.md` records that its own first pass was found incomplete within an hour of being
  written (Decision 6). Its second pass was found incomplete in six places, which is the same
  evidence: reconciling a design against it is real work, not a formality.

**Known open items**

| Item | Detail |
|---|---|
| `platform` has no spec | Decision 1 gives it provider key configuration, the app shell, and the build. Nothing owns them today. |
| Wrong Akai manual ingested | `akai_apc-key-25_user-guide_v1.0_multi.pdf` documents the **original** APC Key 25; the rig has the **mk2**, which differs in pads and shift layer (Decision 9). Mitigated by declared `hardware_applicability` shown inline on citations; the real fix is obtaining the mk2 guide from akaipro.com. |
| No live owned-but-undocumented case | Every rig device is documented since the Scarlett Solo 4th Gen guide was ingested, so that report is empty and four mechanisms reading from it are dormant (Decision 12). They stay specified and are exercised against a fixture rig; the risk is untested-in-anger code, not a missing gap. |
| Scarlett applicability must be declared by hand | `focusrite_scarlett-solo-4g_…` yields source id `focusrite/scarlett-solo-4g` while `rig.yaml` declares `focusrite/scarlett-solo`. Omit the `source_applicability` mapping and the manual is present while its device reports as undocumented. `data/manual-corpus` 11.7 names the omission in the run report; nothing prevents it. **Declared** in the committed `rig.yaml`, and the live run now resolves it. |
| Nitro Max reports as unconfirmed | `rig.yaml` declares no `source_applicability` for the Nitro Max, so under 11.2 its guide is `assumed` for a device the rig holds and 11.5 reports it alongside the APC — two sources where the design's worked example says one (`data/manual-corpus` Decision 16). The remedy is one line, after someone checks the guide against the unit; writing it now would fabricate a verification. |
| Triage starter entries unwritten | `data/symptom-triage` §7 specifies five starter entries (no sound from a track, a track distorting, monitoring latency, drum pad triggers the wrong sound, controller does nothing). None are authored yet, so the diagnostic questions the source exists to answer still refuse. |

**Contract defects.** Each was found from both ends of its seam — named in the design of the spec
that produces it *and* the one that consumes it — and none could be settled by one spec alone. All
six are **closed** by [Decision 11](DECISIONS.md), which amended `CONTRACTS.md` and reconciled the
four specs against it. They are kept here with what closed each, because the history is the evidence
that the reconciliation was owed.

| Defect | Seam | Closed by |
|---|---|---|
| Ranked cause list has no representation | `api/answer-engine` ↔ `ui/ask-and-source-picker` | §4c `Cause` and the `ranked-causes` outcome (§6), carrying `causes[]` with an explicit `rank` equal to array position, a per-cause `check`, and `cites[]`/`fix_cites[]` as `passage_id` into the turn's one `citations[]`. `direct_answer` states the rank-1 cause's check as an instruction, so the first cause is never presented as the answer. answer-engine 7.6 and UI 6.6 amended to it. |
| Error detail has no envelope field | `api/answer-engine` ↔ `ui/ask-and-source-picker` | Four flat §4 members — `reason` (closed per-outcome vocabulary, §6a), `retry_after` (unrounded seconds, **may** accompany rate-limited), `detail` (per-occurrence wording, **unparsed by contract**, content-bounded) and `framing`. §6's retry-after assertion weakened to MAY. UI 9.3, 9.5, 9.8, 9.9, 9.10 keyed on the sub-code, never on the wording. |
| Open-at-source is unbuildable as specified | `data/symptom-triage` → `api/answer-engine` → `ui/ask-and-source-picker` | §3a: engine-mediated, never `file://`. A vendor manual is served inline by **one** new operation and opened at `#page=N` and nothing else; an authored entry reuses `GET /passages/{id}`, which already existed, plus the new `entry_location` on §2 and §3 — which is symptom-triage's `source_file` and `line` finally acquiring a consumer. No editor launcher. The UI's eight-operation assumption was the defect and now names the operation list. |
| `body` block types ungoverned | `api/answer-engine` ↔ `ui/ask-and-source-picker` | §4d names the closed set — heading, ordered step, bullet, paragraph, `!caveat`, `!conflict` — **and the two inline forms**, the citation marker and the key-term span, so "key terms" survives as a governed structure. `!suggest` left `body` entirely for `suggested_sources[]`, an addressable value for UI 7.4. An unknown block keeps its text and loses its wrapper. |
| No SSE event set is governed | `api/answer-engine` ↔ `ui/ask-and-source-picker` | §4b: sixteen events, each carrying a named §3/§4 field except `done`, with ordering, a version token, the three mechanics SSE does not supply, and both halves of the unknown-member rule. `scope_dropped` discharges into new UI 3.11 and `framing` into UI 9.3. §4b also states why UI 3.8 and answer-engine 5.11 were never in conflict. |
| `no-manual-for-device` never produces the filename | `api/answer-engine` ↔ `ui/ask-and-source-picker` | §4e `required_manual`: the assembled `filename` with named placeholders written **inside the string**, plus `placeholders[]` so the surface can say which parts the user supplies without splitting a human-facing value. answer-engine 2.10 and UI 7.7 amended. **Residual:** the engine cannot know the doctype, version or language of a document it has never seen, so 7.7 no longer demands an *exact* filename, and `required_manual` is absent altogether where the device does not resolve to a canonical id. **And that is now every case**: the only resolver is the owned-but-undocumented report, which went empty days after this closed (Decision 12). The field has never been emitted, so this seam is governed but unverified against a real payload. |

**Also closed, earlier and without an amendment.** *Triage sidecar written outside the view*
(`data/manual-corpus` → `api/answer-engine`) was the one blocking item here and is settled:
`data/manual-corpus` Decision 8 splits the report channel, publishing view sidecars at
`views/<hex>/reports/<slug>.json` inside the view and keeping per-run ingestion audits at
`index/audits/<slug>.json`. It needed no `CONTRACTS.md` amendment.

**Still open on these seams**, and recorded rather than closed:

| Item | Detail |
|---|---|
| §7's concurrent stage does not compose | `CONTRACTS.md` §7 allots retrieval-and-state 50 ms; the engine bounds that gather by the 100 ms state timeout. Holds today only because the null state source returns immediately. Blocks `LogTailStateSource`. |
| The static mount has no criterion | Serving `web/build` at `/` is what makes the surface same-origin and lets the engine keep its strict `Origin` guard. It is in the engine's route table and in no criterion; 9.4 names operations and a mount is not one. |
| A suggestion is not tied to the part that motivated it | UI 4.9 re-asks an uncovered part "widening scope to any sources the engine names for it", but `suggested_sources[]` is envelope-level, so the re-ask widens to every suggestion. Hoisting the value made this *fixable* for the first time; closing it needs an association nobody has asked for yet. |
