# Specs Overview: DAWMans

**Generated index.** Regenerated from the folders under `specs/`, never hand-merged — see
[`PROCESS.md`](PROCESS.md) §9. On a merge conflict, regenerate rather than resolve. Everything
below is derived from the files actually present; nothing is anticipated.

**Generated:** 2026-08-14 · **Specs:** 4 · **Anchored acceptance criteria:** 402 · **ADRs:** 30 per-spec + 10 cross-cutting

---

## What DAWMans is

DAWMans is a localhost webapp that answers home-studio questions **strictly from the user's own
sources** — the vendor manuals for their gear plus an authored symptom-triage source they write
themselves — with every factual claim cited to a section and a page, and with NotebookLM-style
per-source scoping so the user chooses which sources may ground a given answer. It is built for one
person, on one machine, glancing at a second screen mid-session: the rig is **Ableton Live 12
Standard, an Akai APC Key 25 mk2, a Focusrite Scarlett Solo and an Alesis Nitro Max, on macOS**. It
answers from the manual corpus only; session awareness sits behind a defined but unbuilt
`StateSource` seam (DECISIONS Decision 4, refined by Decision 8).

## Governing documents

| Document | Standing |
|---|---|
| [`PROCESS.md`](PROCESS.md) | The process source of truth: how specs are written, gated, and turned into code. Kept as shipped by the template. |
| [`CONTRACTS.md`](CONTRACTS.md) | **Governing** for anything crossing a spec boundary — `SourceRecord`, `Passage`, `Citation`, `AnswerEnvelope`, the source kinds, the closed outcome taxonomy, the composed latency budget. Where a spec and CONTRACTS disagree, **CONTRACTS wins and the spec is the defect**. A spec may not invent a field on a shared record nor silently drop one. |
| [`DECISIONS.md`](DECISIONS.md) | The cross-cutting meta log — ten ADRs shaping the project as a whole. It is a synthesis: per-spec `decision_log.md` files remain **authoritative for detail**, and where the two disagree the per-spec log wins. |
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

All four are at **requirements and design complete, tasks not started**. Each design has been
reviewed and repaired; none has a `tasks.md` ledger yet, so nothing is ready for implementation.

| Path | Domain | Capability | What it delivers | Phase | Criteria |
|---|---|---|---|---|---|
| [`data/manual-corpus/`](data/manual-corpus/requirements.md) | `data` | manual-corpus | Ingestion only: turns a folder of vendor PDFs and the authored triage source into a queryable, citable corpus — discovery, extraction fidelity, English selection, glyph repair, section-aware chunking with citation metadata, index build, inventory, and the rig-versus-corpus applicability report. | requirements ✅ · design ✅ · tasks ⬜ | 82 |
| [`data/symptom-triage/`](data/symptom-triage/requirements.md) | `data` | symptom-triage | The `authored-triage` source kind: symptom-to-cause entries the studio owner writes, each with ranked candidate causes, an observable check per cause, and a fix pointer into a vendor manual — plus the grounding rules, authoring loop, coverage reporting, starter set and drift handling. | requirements ✅ · design ✅ · tasks ⬜ | 60 |
| [`api/answer-engine/`](api/answer-engine/requirements.md) | `api` | answer-engine | The middle layer: retrieval over ingested chunks, grounding and honest refusal, citation assembly, source scoping, the pluggable provider abstraction and credential handling, the `StateSource` seam, and the localhost-only HTTP contract. Speed is the headline property. | requirements ✅ · design ✅ · tasks ⬜ | 109 |
| [`ui/ask-and-source-picker/`](ui/ask-and-source-picker/requirements.md) | `ui` | ask-and-source-picker | The browser surface: the ask input and its one-key starters, the source picker and the corpus gaps it exposes, answer and narrowing rendering, citation inspection and open-at-page, waiting and error states across the whole outcome taxonomy, provider configuration, history, legibility and accessibility. | requirements ✅ · design ✅ · tasks ⬜ | 151 |

Criterion counts are the `<a name=` anchors in each `requirements.md`.

---

## Per-spec detail

### `specs/data/manual-corpus/`

- **Files present:** `requirements.md`, `design.md`, `decision_log.md` (7 ADRs).
- **Missing:** `tasks.md`.
- 12 requirement sections, 82 anchored criteria. Owns `SourceRecord` and `Passage` from
  [`CONTRACTS.md`](CONTRACTS.md) §1–§2. Reference corpus: roughly 1068 pages across three manuals.
- Explicit non-goals include OCR, image understanding, non-English content, automatic manual
  acquisition, and inferring hardware applicability from a document's contents.

### `specs/data/symptom-triage/`

- **Files present:** `requirements.md`, `design.md`, `decision_log.md` (6 ADRs).
- **Missing:** `tasks.md`.
- 8 requirement sections, 60 anchored criteria. Header declares status *draft*.
- Exists because the manuals cannot answer diagnostic questions: "gain staging" appears **zero**
  times in the 1009-page Live 12 manual and "troubleshoot" appears twice (DECISIONS Decision 7).
  §7 specifies a five-symptom starter set as the acceptance test for the source.

### `specs/api/answer-engine/`

- **Files present:** `requirements.md`, `design.md`, `decision_log.md` (10 ADRs).
- **Missing:** `tasks.md`.
- 10 requirement sections, 109 anchored criteria. Header declares status *draft*.
- Produces `Citation` and `AnswerEnvelope` ([`CONTRACTS.md`](CONTRACTS.md) §3–§4) and may emit only
  the outcomes in §6 of that file. Must define `StateSource` while shipping a null implementation
  (Decision 4).

### `specs/ui/ask-and-source-picker/`

- **Files present:** `requirements.md`, `design.md`, `decision_log.md` (7 ADRs).
- **Missing:** `tasks.md`.
- 13 requirement sections, 151 anchored criteria — **126 behavioural [B]** and **25 target-and-band
  [T]**, the latter run as the iterative loop of [`PROCESS.md`](PROCESS.md) §5.
- Renders every outcome in the taxonomy and may invent none. Usage context (second screen, hands
  full, dim room) outranks feature richness in any trade-off.

Every spec now carries a `decision_log.md` — 30 per-spec ADRs against the 10 cross-cutting ones in
[`DECISIONS.md`](DECISIONS.md). No spec carries a `tasks.md`. There are no `specs/bugfixes/` folders
and no `prerequisites.md` or `smolspec.md` files.

---

## State of play

**What exists**

- Four `requirements.md` documents in EARS, criteria individually anchored, across three of the
  four domains.
- Four `design.md` documents, each reviewed and repaired against the review findings.
- One governing shared-contract document covering the seams between them.
- Ten cross-cutting ADRs in `DECISIONS.md` and 30 per-spec ADRs, all *accepted*.

**What is next**

- **CONTRACTS amendments first.** Each design ends with a *Requirements defects to reconcile*
  section, and several of those are the same seam found from both ends. They are listed below as
  open items; reconciling them is a precondition for the task phase, because a task ledger written
  against an unreconciled contract encodes the defect.
- The **task phase** for each of the four specs (`/starwave-tasks`), each behind its own approval
  gate. Nothing is ready for implementation.
- `CONTRACTS.md` records that its own first pass was found incomplete within an hour of being
  written (Decision 6). Reconciling each design against it is a precondition for approval, not a
  formality.

**Known open items**

| Item | Detail |
|---|---|
| `platform` has no spec | Decision 1 gives it provider key configuration, the app shell, and the build. Nothing owns them today. |
| Wrong Akai manual ingested | `akai_apc-key-25_user-guide_v1.0_multi.pdf` documents the **original** APC Key 25; the rig has the **mk2**, which differs in pads and shift layer (Decision 9). Mitigated by declared `hardware_applicability` shown inline on citations; the real fix is obtaining the mk2 guide from akaipro.com. |
| No Focusrite Scarlett Solo manual | The interface is owned but undocumented — the standing example of the *owned-but-undocumented* report required by [`CONTRACTS.md`](CONTRACTS.md) §5. |
| Triage starter entries unwritten | `data/symptom-triage` §7 specifies five starter entries (no sound from a track, a track distorting, monitoring latency, drum pad triggers the wrong sound, controller does nothing). None are authored yet, so the diagnostic questions the source exists to answer still refuse. |

**Open contract defects.** Each was found from both ends of its seam — named in the design of the
spec that produces it *and* the one that consumes it. Each needs a `CONTRACTS.md` amendment before
the task phase, since none can be settled by one spec alone.

| Defect | Seam | Detail |
|---|---|---|
| Ranked cause list has no representation | `api/answer-engine` ↔ `ui/ask-and-source-picker` | `AnswerEnvelope` carries `narrowing` and nothing else; the answer framing has no sigil for a ranked cause list. Yet answer-engine 7.6 requires ≤4 ranked causes with citations and checks, and UI 6.6 renders exactly that, showing the rank. Either §4 gains `causes[]` or the framing gains a sigil. |
| Error detail has no envelope field | `api/answer-engine` ↔ `ui/ask-and-source-picker` | §6 asserts `rate-limited` "carries a retry-after" while §4's field table lists neither it nor any field for the engine's own error wording or a credential rejection. UI 9.3, 9.8, 9.9 and 9.10 each need one. |
| Open-at-source is unbuildable as specified | `data/symptom-triage` → `api/answer-engine` → `ui/ask-and-source-picker` | §3 makes a one-activation open action mandatory on any citation, but a browser tab cannot reach `file://` from `http://` nor open a viewer at a page. symptom-triage already publishes the entry's file and line for nobody. Needs engine routes, taking it past the eight operations the UI spec assumes. |
| `body` block types ungoverned | `api/answer-engine` ↔ `ui/ask-and-source-picker` | §4 defines `body` as "headings, ordered steps, key terms" and UI 4.4 renders those three, but `!caveat`, `!conflict` and `!suggest` ride in it with no grammar and no criterion rendering them. `!suggest`'s `source_id` must be addressable for UI 7.4. |
| No SSE event set is governed | `api/answer-engine` ↔ `ui/ask-and-source-picker` | `scope_dropped` and `framing` are produced with no consumer obliged to render them — the produced-but-unconsumed class Decision 6 exists to catch, invisible here because the seam is a stream rather than a record. |
| Triage sidecar written outside the view | `data/manual-corpus` → `api/answer-engine` | The corpus writes `index/reports/<slug>.json` beside the views; the engine needs it inside the view directory so sidecar and passages share a revision. `data/symptom-triage` lists the move as its first outstanding request. **Blocking** — the engine design does not hold until it lands. |
