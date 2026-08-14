# Decision Log: DAWMans

This is the **cross-cutting meta log**: decisions that shape the project as a whole rather than a
single capability. It is a synthesis, not the primary record — the per-spec `decision_log.md` files
under `specs/<domain>/<capability>/` remain authoritative for detail, and where this file and a
per-spec log disagree, **the per-spec log wins** (see [`PROCESS.md`](PROCESS.md) §9). Reconcile this
log after a capability has landed, rather than hand-merging it mid-flight.

---

## Decision 1: Project domain set

**Date**: 2026-08-14
**Status**: accepted

### Context

[`PROCESS.md`](PROCESS.md) §3 requires every spec to live at `specs/<domain>/<capability>/`, where
the domain comes from a closed, project-specific set. The template ships a generic starter set of
`platform`, `data`, `api`, `ui`, and `ops`, and instructs a new project to confirm or prune it as its
first task. Until that is done, no spec has a convention-correct home.

DAWMans is a single-user tool that answers questions about music-production hardware and software by
grounding the answers in the vendors' own manuals. It runs entirely on the user's own machine: a local
HTTP backend, a browser front end, an offline ingestion step over a folder of PDFs, and outbound calls
to an LLM provider. There is no deployment target, no shared environment, and no infrastructure to
run.

### Decision

DAWMans adopts **four** domains and prunes `ops`:

| Domain | Owns |
|---|---|
| `platform` | app shell, build, packaging, provider key configuration |
| `data` | manual ingestion, chunking, the searchable corpus |
| `api` | local HTTP backend, outbound LLM provider integrations, future Ableton state sources |
| `ui` | the browser surface |

### Rationale

Each of the four retained domains owns a real layer of concern with work already visible in it: there
are PDFs to ingest (`data`), a backend and provider calls to make (`api`), a browser surface to build
(`ui`), and a shell, build, and key-configuration story binding them (`platform`).

`ops` has nothing to own. DAWMans is a localhost webapp for one person; its infrastructure amounts to
"run the build and open a browser", which is exactly the "infra is trivial and lives in `platform`"
prune condition the template names. Keeping an empty domain would invite specs to be filed there to
justify its existence.

### Alternatives Considered

- **Keep all five starter domains**: Retain `ops` unchanged in case infrastructure appears later - Rejected because an `ops` domain with nothing in it invites ceremony: work gets filed under it to make it look inhabited, and the domain set stops describing the project. Adding a domain later is a cheap amendment to this decision, so nothing is lost by pruning now.
- **Collapse `data` into `api`**: Treat ingestion as part of the backend, on the grounds that both are non-UI server-side code - Rejected because they have different cadences and different acceptance bars. Ingestion is offline and batch, judged on extraction fidelity; answering is online and interactive, judged on latency and grounding. Merging them would put two unrelated acceptance bars behind one domain boundary.

### Consequences

**Positive:**
- Every spec folder has an unambiguous home from day one.
- The domain set describes DAWMans as it actually is, rather than the template's generic shape.
- Fewer domains means fewer boundary arguments about where a capability belongs.

**Negative:**
- If real infrastructure appears (hosted deployment, CI beyond lint), `platform` will carry it until this decision is amended to reintroduce `ops`.
- `api` is broad: it spans the inbound local HTTP surface and outbound provider and state integrations, so it may need splitting if either side grows.

### Impact

Fixes the valid values of `<domain>` in every spec path, and therefore the shape of `specs/` and
`OVERVIEW.md`. Amending the set is itself an amendment to this decision (PROCESS.md §10).

---

## Decision 2: Manual filename convention

**Date**: 2026-08-14
**Status**: accepted

### Context

The `manuals/` directory holds the vendor PDFs that DAWMans grounds its answers in. Ingestion reads
that directory, and every answer cites the source it came from, so each file needs a stable identity
that survives re-ingestion and is legible to a human reading a citation.

More manuals are expected — soundcards and other controllers — so ingestion discovers whatever files
are present rather than working from a hardcoded list. That makes the filename itself the input to
source identification, which means it needs a grammar rather than a habit.

### Decision

Manual filenames follow:

```
<vendor>_<product>_<doctype>_v<version>_<lang>.pdf
```

Fields are separated by underscores. Every field except `<version>` is lowercase kebab-case: lowercase
letters, digits, and hyphens only. `lang` is an ISO 639-1 code, or `multi` for a multilingual document.
`product` carries the generation or model where that distinguishes the hardware (`live-12`,
`apc-key-25`, `scarlett-solo-4g`).

`<version>` is an explicit exception with its own grammar: a literal `v` followed by one or more
groups of digits separated by full stops — `v12`, `v1.0`, `v1.1`. The full stop is deliberate and is
not kebab-case. Vendors number their documents with dotted versions, and rewriting `v1.0` as `v1-0`
would make the filename disagree with the version printed on the document's own title page, which is
the one thing a reader checks a citation against.

This convention, and the source ID derived from it, govern **`vendor-manual`** sources only: an
`authored-triage` source (Decision 7) has no vendor filename to parse and takes a source ID derived
from its own content, independent of any filename — see
[`data/manual-corpus`](data/manual-corpus/requirements.md#12.5) 12.5 and
[`CONTRACTS.md`](CONTRACTS.md) §1.

The current three files are:

- `ableton_live-12_reference-manual_v12_en.pdf`
- `akai_apc-key-25_user-guide_v1.0_multi.pdf`
- `alesis_nitro-max_user-guide_v1.1_en.pdf`

### Rationale

The filename is the stable source identity. A source ID derives from `<vendor>/<product>`, and that
ID appears in citations shown to the user and in the source picker — so it has to be both stable
across ingest runs and readable without a lookup table.

Underscores at the field boundary and hyphens inside a field give an unambiguous parse: split on `_`
to get fields, and multi-word values inside a field stay intact. Because ingestion discovers files
rather than reading a list, a well-formed name is the only thing standing between a new PDF and a
correct citation.

### Alternatives Considered

- **Free-form filenames plus a manifest**: Name files however the vendor supplies them and map each to metadata in a manifest file - Rejected because it creates two places to keep in sync, and a renamed or re-downloaded file silently breaks its citations rather than failing loudly.
- **A single hyphen separator throughout**: Use `akai-apc-key-25-user-guide-v1.0-multi.pdf` for a uniform look - Rejected because the vendor/product boundary becomes ambiguous to parse: `akai-apc-key-25` gives no signal about where the vendor ends and the product begins.
- **Encoding device class in the filename**: Add a field such as `controller`, `drum-machine`, or `daw` - Rejected because reclassifying a device would force a rename and therefore change a citation the user may have already seen. Class is metadata, and belongs in the corpus record, not in the source identity.

### Consequences

**Positive:**
- Citations are readable and stable, and derive mechanically from the filename.
- Adding a manual requires no code change and no manifest edit — drop the file in and re-ingest.
- The grammar makes a malformed name obvious on sight and easy to reject at ingest time.

**Negative:**
- Vendor-supplied filenames must be renamed by hand on download, which is a step that can be forgotten.
- A version bump changes the filename, so the corpus must handle the old and new file being distinct entries.
- The convention has no enforcement yet; a badly named file is caught only by whatever validation ingestion chooses to do.
- The convention now carries an exception rather than one uniform rule, so it is marginally harder to validate: `<version>` needs its own pattern, and a single kebab-case regex across all fields would wrongly reject two of the three current manuals.

---

## Decision 3: Manual PDFs are gitignored, never committed

**Date**: 2026-08-14
**Status**: accepted

### Context

The three current manuals total roughly 110MB, dominated by the 96MB Ableton Live 12 reference
manual. They are third-party documents published by Ableton, Akai, and Alesis, and each is available
free from its vendor to anyone who wants it. DAWMans needs them present on disk to build its corpus,
but that is a local requirement, not a distribution requirement.

Git stores binaries in full and forever: once a 96MB PDF is committed, every clone of the repository
pays for it permanently, even after a later deletion. A version bump would add another copy.

### Decision

`manuals/*.pdf` is gitignored and the PDFs are never committed. `manuals/README.md` is tracked and
records which files are expected, their naming, and where to obtain each one from its vendor.

### Rationale

Two independent reasons point the same way. The practical one is repository weight: 110MB of binary
in history, growing with each manual and each version, for files that change rarely and are trivially
re-downloadable. The other is rights: these are copyrighted documents we hold no redistribution
licence for, and committing them to a repository is redistribution regardless of intent.

Tracking a README instead keeps the requirement discoverable — a fresh clone can see exactly which
files it is missing and where to get them — without the repository holding content it should not.

### Alternatives Considered

- **Commit the PDFs**: Vendor everything so a clone is immediately runnable - Rejected on both counts: 110MB of binary permanently in git history, and redistribution of documents we do not own the rights to.
- **Git LFS**: Keep the files nominally in the repository while storing blobs out of band - Rejected because it adds a dependency and a hosting cost for files each user can legitimately download themselves from the vendor, and it does not address the rights problem at all.
- **A fetch script that downloads the manuals**: Automate acquisition so setup stays one command - Rejected for now because vendor download URLs are unstable and often sit behind a product page or a click-through, so the script would break quietly. A documented table in the README is honest about the manual step.

### Consequences

**Positive:**
- The repository stays small and quick to clone.
- No third-party copyrighted material is redistributed.
- The expected corpus is still documented and reviewable in version control.

**Negative:**
- Setup is not one command: a new machine must download three PDFs by hand before ingestion will run.
- Nothing pins the exact document revision, so two machines could ingest subtly different files under the same name.
- The build must fail clearly when `manuals/` is empty, or the failure will look like a bug in ingestion.

---

## Decision 4: MVP is manual-grounded only, with a StateSource seam

**Date**: 2026-08-14
**Status**: accepted, context corrected by Decision 8

### Context

The obvious ambition for DAWMans is a tool that knows what is currently happening in the user's
Ableton session and answers in that context. The MVP does not attempt it: it answers purely from the
manuals. The question is whether to leave any structural room for session state, or to defer the
whole idea.

The route to Live's internal state matters here. The user runs **Live 12 Standard, which does not
include Max for Live** — that ships with Suite only — so the officially supported way to read Live's
state is closed. The remaining options are an undocumented MIDI Remote Script in Python, whose API
Ableton changes between versions with no compatibility guarantee, or reading a saved `.als` project
file, which is gzipped XML and structurally stable but only ever reflects the last save.

> **Correction (2026-08-14).** The Max for Live claim in the paragraph above is wrong, per the
> verified research in [Decision 8](#decision-8-prefer-a-saved-file-and-log-file-state-source-over-a-live-ableton-feed).
> Max for Live is **not Suite-only**: it is included with Suite *or* sold as a paid add-on for
> Standard, and its runtime physically ships inside the Standard bundle, gated by licence alone — so
> no filesystem check can establish whether it is available. The conclusion below is unaffected: the
> add-on is not licensed on this installation, so the supported route is still closed, and
> AbletonOSC is available on Standard but depends on the same undocumented control-surface API this
> decision declines to depend on. Decision 8 refines which implementation lands first.

It is also not yet established that session awareness is needed. Manual-grounded answers may already
resolve most of what the user actually asks.

### Decision

Ship an MVP that answers only from the manual corpus, and define a `StateSource` abstraction in the
architecture so that a `.als` file reader, and later a live feed from Live, can be added as
implementations rather than as a redesign.

### Rationale

The seam is cheap and the retrofit is not. If the answer path is built assuming manuals are the only
grounding input, adding session state later means reworking retrieval, prompt assembly, and citation
handling at once. Defining `StateSource` up front costs an interface and a null implementation, and
buys the ability to add `.als` reading as an additive change.

Holding back the implementation is equally deliberate. The supported route is unavailable on Live 12
Standard, the unsupported route is a moving target across Live versions, and the value of session
awareness is unproven. Building the seam without the implementation keeps the option open at the
lowest possible cost.

### Alternatives Considered

- **Pure Q&A with no seam**: Build the simplest manual-only answer path and revisit state later from scratch - Rejected because retrofitting session state would restructure the answer path rather than extend it, and the seam is a small fraction of that cost.
- **Build live Live-integration now**: Write the MIDI Remote Script and integrate session state into the MVP - Rejected as the highest-risk option available: an undocumented API that changes between Live versions, on a build without Max for Live, in service of a benefit not yet shown to be needed over manual answers alone.
- **Ship `.als` file reading in the MVP**: Take the stable-but-stale middle route immediately - Rejected because last-saved state can contradict what the user is looking at, and an answer grounded in stale state is worse than one that does not claim to know. Better to add it once manual answers are working and the gap is understood.

### Consequences

**Positive:**
- The MVP stays small and ships against a source that is already on disk and fully under our control.
- Session state becomes an additive change behind a defined interface.
- The decision to defer is recorded with its cause, so a future Suite upgrade or a Live API change can reopen it deliberately.

**Negative:**
- `StateSource` is an abstraction with exactly one trivial implementation at MVP, which is speculative generality until the second one arrives.
- The interface is being designed without a real consumer, so it may well need reshaping when `.als` reading is built.
- Users expecting session awareness will find the MVP answers generic questions rather than their questions.

### Impact

Shapes the `api` domain's answer path and the `api/answer-engine` spec, which must define
`StateSource` even though it ships only a null implementation.

---

## Decision 5: Three specs for the MVP, not one

**Date**: 2026-08-14
**Status**: accepted, amended by Decision 7

> **Amendment (2026-08-14).** [Decision 7](#decision-7-add-an-authored-symptom-triage-source-alongside-the-vendor-manuals)
> added a fourth spec, `specs/data/symptom-triage`, after a reality-check found the vendor manuals
> contain no troubleshooting knowledge. The reasoning below is unchanged and the fourth spec follows
> it: an authored triage source is judged on whether its causes resolve real symptoms, which is not
> the extraction-fidelity bar that `data/manual-corpus` is judged on, even though both sit in the
> `data` domain. Read "three" below as "one spec per acceptance bar", which now yields four.

### Context

The MVP spans PDF ingestion, a grounded answer path over an LLM provider, and a browser surface with
an ask box and a source picker. The template's worked example presents an MVP as a single spec under
its dominant domain, and [`PROCESS.md`](PROCESS.md) §10 explicitly warns that splitting a spec before
a forcing function exists is premature.

The counter-pressure is that the three parts are judged on unrelated criteria. Ingestion is right or
wrong on extraction fidelity, measured offline against the source PDFs. The answer path is judged on
latency and on whether answers stay grounded in the cited text. The interface is judged on whether
the answer and its source are glanceable. These are not variations on one acceptance bar.

### Decision

Split the MVP into three specs:

- `specs/data/manual-corpus`
- `specs/api/answer-engine`
- `specs/ui/ask-and-source-picker`

### Rationale

PROCESS.md §3 states that a capability needing two unrelated acceptance bars is two specs; here there
are three. Extraction fidelity, answer latency and grounding, and glanceable legibility cannot be
reviewed against one another, and a single `requirements.md` covering all three would have an
acceptance bar too broad for any reviewer to hold in mind.

Change cadence separates them again. The corpus churns whenever a manual is added or Ableton ships a
Live update; the answer engine changes with provider and retrieval work; the interface settles early
and then moves rarely. Splitting along those lines means routine corpus churn does not reopen the
interface spec.

### Alternatives Considered

- **One bundled MVP spec**: Follow the template's worked example and describe the whole MVP as a single capability - Rejected because one design document spanning PDF parsing to interface layout would carry an acceptance bar too broad to review meaningfully, and every manual added would touch the same document as every interface tweak.
- **Two specs — corpus plus everything else**: Separate the offline ingestion work and keep the online path whole - Rejected because the provider abstraction and the `StateSource` seam (Decision 4) would then sit inside what is nominally a UI spec, where they do not belong and would not be reviewed by the right acceptance bar.

### Consequences

**Positive:**
- Each spec has one acceptance bar that can actually be checked.
- Corpus churn, provider work, and interface work touch disjoint folders, so the specs merge additively across branches (PROCESS.md §9).
- The `api` spec owns the provider abstraction and `StateSource` seam explicitly, rather than by accident of where they were written.

**Negative:**
- PROCESS.md §10 warns against premature splitting, and this split is made on anticipated rather than observed cadence divergence. If the three turn out to change in lockstep, the split will have scattered cross-references for no benefit.
- Three specs means three approval gates before any code is written, which is real front-loaded cost for a single-developer MVP.
- Shared assumptions — the source ID grammar from Decision 2, the answer/citation shape — now live across folder boundaries and must be cross-referenced rather than simply stated once.

### Impact

Fixes the initial shape of `specs/`: three capability folders across the `data`, `api`, and `ui`
domains, each with its own requirements, design, tasks, and decision log.

---

## Decision 6: A shared contracts document governs the spec seams

**Date**: 2026-08-14
**Status**: accepted

### Context

The three MVP specs of Decision 5 were drafted in parallel by separate authors that could not see each
other's work. An adversarial review of the result found 25 defects, 9 of them blocking, and almost all
of them sat at the seams between the specs rather than inside any one of them.

The defects fell into three recognisable shapes. Capabilities were produced and never consumed: the
corpus spec emitted a degraded-text flag, a figure-presence flag, and a report of which sources
actually contributed passages, and no downstream spec rendered any of them. Whole flows were present
in one spec and absent from the other: the narrowing-question flow existed in the engine spec and
appeared nowhere in the UI spec, so the engine could emit a turn the interface had no way to show. And
the same interaction was described two contradictory ways: the UI forbade rendering the exact answer
shape the engine produced for partial coverage, so a conforming engine and a conforming UI could not
both be right.

[`PROCESS.md`](PROCESS.md) §10 prescribes keeping a root overview holding the shared assumptions when
a capability is split. That step was skipped when the split was made, and the defects above are the
damage that followed.

### Decision

[`CONTRACTS.md`](CONTRACTS.md) is governing. It defines the records that cross a spec boundary —
`SourceRecord`, `Passage`, `Citation` and `AnswerEnvelope` — plus the closed outcome taxonomy and the
composed latency budget. A spec may not invent a field on a shared record nor silently drop one, and
where a spec and CONTRACTS disagree, CONTRACTS wins and the spec is the defect.

### Rationale

Every defect the review found was a disagreement about a shared record or a shared flow, and none of
them was visible from inside a single spec. That is a structural gap, not an authoring mistake: three
documents each internally consistent can still contradict one another, and nothing in the per-spec
review process is positioned to notice. A single governing document is the smallest artefact that
gives the seams an owner.

Making it governing rather than advisory is what gives it force. If CONTRACTS were merely a summary,
a spec that disagreed with it would be an ambiguity to debate; because CONTRACTS wins, the same
disagreement is a defect with a known resolution, and reconciliation becomes mechanical.

The closed outcome taxonomy and the composed latency budget are in scope for the same reason as the
records. The engine emitting an outcome the UI does not render is the identical failure as the engine
emitting a field the UI does not read, and stage latency budgets stated at incompatible boundaries do
not compose into the one figure the user actually experiences.

### Alternatives Considered

- **Merge the three specs back into one**: Undo Decision 5 and remove the seams rather than govern them - Rejected because the three acceptance bars remain genuinely different, exactly as Decision 5 described. The split was not the error; the missing root overview was. Merging would trade a solvable reconciliation problem for the unreviewable acceptance bar the split existed to avoid.
- **Let each spec define its own view and reconcile at design time**: Accept divergence during requirements and resolve it when designs are written - Rejected because the review demonstrates that these defects arrive at requirements time and get more expensive after. Design would inherit three incompatible models of the same records and have to relitigate them with more detail attached.
- **A contract test suite instead of a document**: Encode the seams as executable tests - Rejected because tests need an implementation to run against, and these defects must be caught before any code exists. A test suite is a good later complement to CONTRACTS, not a substitute for it.

### Consequences

**Positive:**
- The seams have an owner, and a spec-versus-spec disagreement now has a defined winner instead of being an argument.
- The defects the review found are fixable by editing one document plus the specs that contradict it, rather than by renegotiating three documents against each other.
- New specs inherit the shared records rather than reinventing them, so the failure mode does not recur with the fourth spec.

**Negative:**
- CONTRACTS is a fourth document to keep current, and it goes stale in exactly the way the specs did if reconciliation is skipped again.
- It was itself found incomplete within an hour of being written: it omitted the `cancelled` and `incomplete` outcomes that three acceptance criteria depended on. That is evidence the reconciliation is real work rather than ceremony, and that a first pass over the seams should not be trusted as complete.
- A governing document invites the specs to under-specify by gesturing at CONTRACTS instead of stating what they require, which would move ambiguity rather than remove it.

### Impact

Adds `specs/CONTRACTS.md` as a governing document above all four MVP specs, and makes reconciliation
against it a precondition for any spec being considered approvable.

---

## Decision 7: Add an authored symptom-triage source alongside the vendor manuals

**Date**: 2026-08-14
**Status**: accepted

### Context

A reality-check traced the five questions a producer with this rig would actually ask mid-session. Two
of them answer well, two do not answer at all, and the two that fail are the two most likely to be
asked. The cause is measurable rather than a matter of opinion: the phrase "gain staging" appears
**zero** times across the 1009-page Live 12 manual, and "troubleshoot" appears twice. Live's manual
documents the Track Activator as *"to mute the track's output, turn off the Track Activator"* — an
instruction for muting, and never as a **cause** of unexpected silence.

That is not a defect in Ableton's documentation. A reference manual documents what controls do; it
does not document what good practice is, or which control to suspect when something sounds wrong. No
amount of better retrieval extracts an answer that is not in the corpus.

The gap also made the engine spec internally contradictory. Its narrowing flow required candidates
"drawn from the distinguishing conditions in the retrieved passages", while another criterion forbade
any use of general knowledge. Since no vendor passage contains distinguishing conditions for a
symptom, symptom triage was simultaneously required and prohibited.

### Decision

Introduce a second source kind, `authored-triage`, specified in `specs/data/symptom-triage/`. The user
authors a starter set of five entries covering the symptoms that stop a session
([`symptom-triage`](data/symptom-triage/requirements.md#7.1) 7.1–7.6), and grows the store from there
into the tens to low hundreds its performance budget assumes (5.6, and its Assumptions). Each entry
names the candidate causes ranked by likelihood, the observable check that confirms or eliminates
each one, and a pointer into a vendor-manual passage for the fix. Entries are retrieved, ranked and
cited exactly like any other source, with their
provenance shown as the user rather than the manufacturer.

### Rationale

The failures cluster on diagnostic questions, and a diagnostic question is precisely what a
mid-session glance at this tool is. Shipping a tool that answers reference questions well and
diagnostic questions not at all means failing hardest at the moment the user is most stressed and
least able to go reading.

Authoring the missing knowledge is preferable to inventing it at answer time because it keeps the
grounding property intact. A triage entry is a cited source like any other, written once, reviewable,
and correctable — as opposed to a model reasoning freely about gain staging with no citation behind
it. The fix an entry points to still lands in a vendor manual, so the factual claim at the end of the
chain remains the manufacturer's.

It also resolves the engine's contradiction the right way round. With triage entries in the corpus,
the distinguishing conditions the narrowing flow needs exist as retrievable passages, so the flow
becomes implementable as written without relaxing the no-general-knowledge rule.

### Alternatives Considered

- **Ship manual-only and accept the refusals**: Keep the corpus purely vendor-supplied and let diagnostic questions return a coverage failure - Rejected because the refusals cluster on diagnostic questions, which is exactly what a mid-session glance is. The tool would fail hardest precisely when the user is most stressed, which inverts its purpose.
- **Relax the no-general-knowledge rule and let the model diagnose freely**: Permit uncited reasoning for symptom questions - Rejected because grounding is the product's only differentiator over asking a general chatbot, and a confident wrong answer about gain staging is the specific failure this product exists to avoid.
- **Wait for better manuals**: Defer until a vendor publishes symptom-to-cause documentation - Rejected because no manufacturer publishes that kind of documentation; it is not an oversight that will be corrected. The gap is structural and permanent.

### Consequences

**Positive:**
- The narrowing flow in the engine spec becomes implementable as written, rather than requiring conditions no passage contains.
- The missing Focusrite Scarlett Solo interface knowledge can be covered without possessing that manual at all, since a triage entry describes what to check rather than quoting a document.
- Every factual claim remains cited, so the grounding guarantee is unchanged in kind — only the set of sources grows.

**Negative:**
- The source's quality is bounded by the user's own knowledge: it cannot encode anything the author does not already know, and its blind spots are invisible from inside the system.
- A wrong entry is cited with exactly the same confidence as a manufacturer's manual, so an authoring mistake reads to the user as a documented fact.
- It is roughly a day of writing before the tool is useful for diagnostics, which is real work in front of the payoff rather than behind it.
- It needs maintaining as the rig changes: new hardware, or a Live update that moves a control, silently invalidates entries that still look authoritative.

### Impact

Adds `specs/data/symptom-triage/` under the `data` domain, and adds the source-kind distinction to the
shared records in [`CONTRACTS.md`](CONTRACTS.md) §4a.

---

## Decision 8: Prefer a saved-file and log-file state source over a live Ableton feed

**Date**: 2026-08-14
**Status**: accepted

### Context

Decision 4 deferred session awareness behind a `StateSource` seam on the basis of a rough
understanding of the available routes. Research verified on this machine, which runs Live 12.4.3,
establishes what those routes actually are, and corrects two claims in Decision 4's context.

First, Max for Live. It is a paid add-on for Live Standard, not strictly Suite-only as Decision 4
stated. More awkwardly, the Max for Live runtime physically ships inside the Standard bundle and is
gated by licence alone, so any filesystem check for "is Max for Live installed" returns a false
positive and cannot be used to detect availability.

Second, the file routes. The `.als` project file is confirmed gzipped XML, undocumented by Ableton,
and has drifted between versions — `MasterTrack` became `MainTrack` in Live 12. It carries traps a
naive parser walks straight into: a freeze-sequencer section duplicates the monitoring and armed
values, so a flat search for either returns the wrong one, and mute is stored inverted. Crash-recovery
files are not the fresher alternative they appear to be, because they are a snapshot taken at Live's
launch and can therefore be **older** than the last manual save. Live's `Log.txt`, by contrast, is
plain text appended live, needs nothing installed, and yields the currently open Set's path, the
active audio device, and the per-MIDI-port Track, Sync and Remote flags. As for the live routes:
AbletonOSC is a remote script rather than a Max for Live device, so it needs no Suite licence, but it
drives Live's embedded Python control-surface API, which Ableton does not document and which breaks
between versions. Ableton Link carries tempo, beat, phase and start-stop only — no track state at all
— which closes it as a route entirely.

### Decision

The `StateSource` seam is implemented, when the time comes, first from Live's log file and the saved
`.als` file, both of which are installation-free and stable enough to depend on. A live feed via a
remote script stays designed-for but unbuilt.

### Rationale

The log file and the saved project are the only routes that require nothing to be installed, nothing
to be licensed, and no undocumented runtime API to keep working. Between them they answer the
questions session awareness is actually for — which Set is open, which audio device is active, how the
MIDI ports are configured, and what the track state was at the last save — which is most of the value
at a fraction of the ownership cost.

The staleness objection that Decision 4 raised against `.als` reading still stands, but it is now
bounded rather than absolute: the log file is live, so the parts of the picture that change often
(which Set, which device) are current, and only the track-level detail is as old as the last save. The
crash-recovery finding matters here precisely because it removes the obvious workaround — those files
are not fresher, so there is no shortcut to live track state short of the live feed.

Deferring the live feed is a cost judgement, not a technical impossibility. AbletonOSC is available on
Standard, so licence is no longer the blocker Decision 4 believed it was; the blocker is that it
depends on an undocumented API that breaks between Live versions, and that maintenance is not worth
committing to before manual-grounded answers have been shown insufficient.

### Alternatives Considered

- **Build the live feed first**: Implement session state via AbletonOSC or a hand-written remote script before the file routes - Rejected because it depends on an undocumented control-surface API that breaks between Live versions, and the ongoing ownership cost is not justified before manual answers have been proven insufficient.
- **Buy Max for Live**: Purchase the add-on for Standard and use the supported device API - Rejected because it is a several-hundred-unit purchase in service of a diagnostic nicety, on a single-user tool whose core value does not depend on it.
- **Ableton Link**: Use the published Link protocol as the state source - Rejected because Link carries tempo, beat, phase and start-stop only. It carries no track state whatsoever, so it cannot answer any question this seam exists to answer.
- **Crash-recovery files as a fresher snapshot**: Read Live's recovery data instead of the last save - Rejected on the finding above: the snapshot is taken at launch and can be older than the last manual save, so it is not a fresher source and would sometimes be a worse one.

### Consequences

**Positive:**
- The first implementation of `StateSource` needs nothing installed, nothing licensed, and no Ableton API that can break between versions.
- The live-versus-stale split is honest: the log file supplies what changes often, and the `.als` supplies the rest with a known staleness the answer can qualify itself with.
- The licence question is settled with verified facts, so a future reopening starts from evidence rather than from the incorrect Suite-only assumption in Decision 4.

**Negative:**
- Both routes parse formats Ableton does not document and has already changed once, so a Live update can break them without warning or notice.
- The `.als` traps — duplicated freeze-sequencer values and inverted mute — mean a parser that looks correct can be quietly wrong, and only careful fixtures will catch it.
- Track state is only ever as fresh as the last save, so any answer using it must qualify itself, and a user who has not saved recently gets a picture that contradicts their screen.
- No filesystem check can establish whether Max for Live is licensed, so the system cannot detect that capability and must not try.

### Impact

Refines Decision 4 rather than superseding it: the seam stands, and this fixes which implementation
lands first. Corrects Decision 4's context on Max for Live availability.

---

## Decision 9: The ingested Akai manual does not match the user's controller

**Date**: 2026-08-14
**Status**: accepted

### Context

The ingested `akai_apc-key-25_user-guide_v1.0_multi.pdf` is Manual Version 1.0 and describes the
**original** APC Key 25. The user owns the mk2. This was confirmed not by inference from the version
number but by comparing Live 12's own bundled control-surface scripts, which ship separate definitions
for the two products and declare different capabilities for each. The units differ in their pads and
in the shift layout.

This is the product's worst failure mode, and it is worse than a plain absence of documentation. A
refusal leaves the user where they started; a citation actively increases their confidence in an
answer that is wrong for the hardware in front of them. The corpus cannot tell the difference, because
from its point of view the source is present, parsed, and cited correctly.

The same file has secondary problems that compound it. It is multilingual, with only about five of its
24 pages in English, and its arrow glyphs extract as mojibake — so even where it does apply, the
extracted text is thinner and less reliable than the page count suggests.

### Decision

Sources carry a declared `hardware_applicability` marked either `confirmed` or `assumed`. The system
holds a declared rig inventory, separate from the corpus inventory, so that it can report
**owned-but-undocumented** and **documented-but-unconfirmed** hardware. The correct mk2 guide should
be obtained from akaipro.com to replace the current file.

### Rationale

The mismatch cannot be detected from the corpus alone, because nothing about a well-formed PDF signals
that it describes different hardware from the user's. It only becomes visible when what the user owns
is recorded separately from what has been indexed, and the two are compared. That is why the rig
inventory is a distinct thing rather than a field on the source.

Marking applicability as `confirmed` or `assumed` rather than trying to resolve it automatically is
deliberate. The confirmation for this file came from cross-referencing Live's bundled scripts, which
is not a check the system can perform in general. An honest two-state flag surfaced in the citation
lets the user apply the judgement the system cannot, and costs nothing when applicability is certain.

Replacing the file is the actual fix; the flag is the mitigation that holds until then, and remains
useful afterwards for the next manual whose revision is uncertain.

### Alternatives Considered

- **Treat the current file as good enough**: Accept the mk1 guide on the grounds that much of the layout overlaps - Rejected because the differences fall exactly on the shift layer, and the shift layer is what the button procedures depend on. The overlap is in the parts nobody needs to look up.
- **Remove the APC source entirely until the right manual is obtained**: Drop it from the corpus rather than cite a document for the wrong revision - Rejected because it still answers many questions correctly, and a declared applicability caveat preserves that value while making the risk visible. Removal trades a flagged risk for a guaranteed gap.
- **Infer the revision automatically from the document**: Detect the hardware revision by parsing the manual - Rejected because the confirmation required comparing Live's bundled control-surface scripts, an external source the ingestion path has no reason to know about, and a wrong automatic inference would be marked `confirmed` and be more dangerous than no inference at all.

### Consequences

**Positive:**
- The worst failure mode becomes visible to the user at the point of citation, rather than silently.
- Reporting owned-but-undocumented hardware names the real gap in the corpus — the Scarlett Solo today — instead of leaving it to be discovered by a failed question.
- The flag generalises: every future manual is either confirmed against the owned hardware or explicitly is not.

**Negative:**
- Applicability is declared by hand, so it is only as accurate as the declaration and will drift as hardware changes.
- Until the mk2 guide is obtained, the APC source stays permanently caveated, which erodes trust in citations that are in fact correct.
- The rig inventory is a second inventory to maintain, and one that no automated process can validate.

### Impact

Adds `hardware_applicability` to `SourceRecord` and to the rendered `Citation` in
[`CONTRACTS.md`](CONTRACTS.md) §1, §3 and §5, and adds a declared rig inventory to the `data` domain's
scope.

---

## Decision 10: Python for ingestion and the answer engine, SvelteKit for the browser surface

**Date**: 2026-08-14
**Status**: accepted

### Context

This repository is derived from a stack-agnostic template, and the stack was left as the derived
project's job. [`AGENTS.md`](../AGENTS.md) still carries it as a `TODO`, and `make build`, `make test`
and `make clean` error as unconfigured. Design cannot proceed for any of the four specs while that
holds: a design document has to name what it is designing in.

The load-bearing constraint is that the two hardest parts of DAWMans — layout-preserving PDF text
extraction, and fast local embedding inference — have their strongest ecosystems in Python. The
retrieval research in [`retrieval-approach.md`](../docs/agent-notes/retrieval-approach.md) benchmarked
exactly those Python libraries on this machine, so the numbers the answer engine's latency budget
rests on were obtained from that stack rather than assumed of it.

Against that, [`ui/ask-and-source-picker`](ui/ask-and-source-picker/requirements.md) carries 151
acceptance criteria, including streamed answers, one-key affordances, and measured legibility bands.
That is a real interface with real state, not a set of server-rendered fragments, and it needs a
frontend framework to match.

### Decision

Python owns ingestion (`data/manual-corpus`, `data/symptom-triage`) and the answer engine
(`api/answer-engine`), exposing a loopback HTTP service with streamed responses. SvelteKit owns the
browser surface (`ui/ask-and-source-picker`). Python dependencies and environments are managed with
**uv**, and the SvelteKit side with **pnpm**. A single `make dev` target runs both. Retrieval stays
entirely local and offline; only answer synthesis calls out to a provider.

### Rationale

Each half uses the ecosystem built for it. PDF layout extraction and ONNX inference are Python's
established ground; a streamed, keyboard-driven interface with measured legibility requirements is
the frontend framework's.

The measured retrieval figures carry over unchanged as a result. The 0.011 ms brute-force cosine
scan, the 2.2 ms query embed, and the 1.8 MB index were all measured with this stack, so adopting it
means the answer engine's budget starts from evidence rather than needing re-validation against a
different set of libraries.

The split also costs no extra seam. The boundary between `api` and `ui` is already a spec boundary
governed by [`CONTRACTS.md`](CONTRACTS.md), and it falls exactly where the runtime boundary falls —
so the process boundary sits on a line the specs had drawn anyway.

The package managers are each the fast, lockfile-first choice in their ecosystem, which matters most
on a two-runtime project where the friction of the second toolchain is the main cost this decision
carries. `uv` gives reproducible, lockfile-backed Python environments and subsumes the
virtualenv/pip/pip-tools split into a single tool; `pnpm`'s content-addressed store and strict
dependency resolution stop phantom dependencies — imports that resolve only because something else
pulled the package in — from working at all.

### Alternatives Considered

- **All TypeScript, SvelteKit full-stack**: One language, one process, one dependency manager, and the simplest thing to run - Rejected because PDF layout extraction and ONNX inference are materially weaker in Node, and both are load-bearing. Adopting it would invalidate the benchmarks and force re-validation of the two riskiest components in the project.
- **Python batch index plus a TypeScript app**: Ingestion as a standalone tool emitting a portable index that the app only reads - Rejected as a stack choice because it turns the on-disk index format into a cross-language contract that must be versioned and kept compatible, which is a heavier commitment than the process boundary it replaces. It remains a viable *later* refactor if the ingestion tool ever wants to ship separately.
- **Go backend with an embedded Svelte UI**: A single static binary, and the best operational story of the three - Rejected because Go's PDF text-layout extraction and ONNX bindings are the weakest of the options considered, on precisely the two capabilities the product depends on.

### Consequences

**Positive:**
- Each half uses tooling proven for its job, rather than one stack stretched across both.
- The measured performance figures from the retrieval research carry over without re-validation.
- Retrieval needs no hosted service, which honours the local and FOSS preference recorded in `AGENTS.md`.

**Negative:**
- Two runtimes and two dependency managers on a single-developer project.
- `make dev` has to orchestrate both, and is now a moving part that can fail on its own.
- A contributor needs both toolchains installed before anything runs, and specifically needs `uv` and `pnpm` rather than merely a Python and a Node installation.
- The engine and the UI must be run and debugged as two processes rather than one.

### Impact

Unblocks the design phase for all four specs, fixes what `AGENTS.md` records as the stack, and
determines the `.gitignore`, CI and `Makefile` targets that follow from it.

---
