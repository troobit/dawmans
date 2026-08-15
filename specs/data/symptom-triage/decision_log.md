# Decision Log: Symptom Triage

Enhanced Nygard ADR entries for the load-bearing choices in [`design.md`](design.md).

---

## Decision 1: Markdown with YAML frontmatter, one file per symptom

**Date**: 2026-08-14
**Status**: accepted

### Context

Requirement 1.7 fixes the properties of the entry store — plain text, line-oriented, independently
editable per entry, self-describing, and free of hand-computed values — without naming a format.
The store is written by one person at a desk, often mid-session with a track half-finished, and edited
under the same conditions. It also has machine-read fields (the scope declaration of §4) that must be
parsed exactly.

### Decision

Entries are Markdown files in `triage/`, one per symptom, each with a `---`-fenced YAML frontmatter
block for the machine-read fields and Markdown headings for the symptom and its causes.

### Rationale

The two halves of an entry have different readers, and this format serves each in its own
vocabulary: the scope declaration is a parsed list, and the symptom and causes are prose an author
edits without thinking about syntax. Nothing in the body is quoted, escaped or indented, so a typing
mistake mid-session costs a flag rather than a parse failure. One file per symptom is the part with
the most operational weight: adding an entry touches no other entry, a diff shows exactly the cause
that changed, and a merge conflict cannot arrive in a file being edited under pressure.

### Alternatives Considered

- **TOML, one file per symptom**: Well-specified typing and unambiguous parsing - Rejected because
  every cause becomes a quoted string in an array of tables. The check and fix text is the part
  written fastest and least carefully, and TOML puts quoting and escaping rules exactly there.
- **A single combined YAML file**: One document, one parse, no discovery step - Rejected because
  every edit touches the same file, so diffs are noisy, a merge conflict lands on the file being
  edited mid-session, and the whole store is at risk from one indentation slip.
- **Frontmatter only, causes as YAML inside it**: Uniform parsing for the whole entry - Rejected for
  the same quoting reason as TOML, with the added cost that the entry stops being readable as prose,
  which is what 1.7's "self-describing" asks for.

### Consequences

**Positive:**
- An entry is readable and editable in any text editor with no tool and no schema to consult.
- Per-file granularity gives 1.8's identity, 1.9's duplicate detection and git-level isolation with
  no registry.
- The parser only has to be strict about frontmatter; the body is recognised forgivingly.

**Negative:**
- Two syntaxes in one file, so two classes of parse error and two message styles.
- Markdown is under-specified, so the grammar's tolerances (which line forms count as `check:`) are
  this spec's invention rather than a standard, and must be pinned by test.
- Discovery is a directory scan on every run, which a single file would not need.

---

## Decision 2: One passage per entry, not one per cause

**Date**: 2026-08-14
**Status**: accepted

### Context

`Passage` is the unit of retrieval and of citation, and `unbacked` (CONTRACTS §2) sits on it. Causes
are per-entry. Emitting one passage per cause would put the flag exactly where the unbacked claim
is; emitting one per entry marks causes that are perfectly well grounded.

### Decision

One `Passage` per entry, split between causes only when the entry exceeds the chunker's word cap
(3.3). Per-cause structure travels in a sidecar keyed by `passage_id`, not as passages.

### Rationale

`api/answer-engine` 7.2 and 7.6 consume the *ranked list* of causes with the symptom they belong to;
a cause retrieved alone is a fragment with no ranking and no symptom. Per-cause passages would also
put five near-identical short passages from one entry into competition with each other under 5.6's
per-source floor, crowding out the manual passages the fix depends on. 2.4 and 8.5 already chose
over-marking over under-marking, which settles the cost this decision incurs: the flag reaches the
user as one extra caveat on an answer that does contain an unbacked step.

### Alternatives Considered

- **One passage per cause**: Precise `unbacked`, finer retrieval - Rejected because it loses the
  entry's ranking, which 1.1 and 1.5 exist to preserve and 7.2 consumes, and because it multiplies
  each entry into several competing passages under the per-source retrieval floor.
- **One passage per entry plus one per cause, both indexed**: Precision for the flag, ranking for
  the entry - Rejected as double-indexing the same text: identical content under two IDs makes
  citation ambiguous and doubles the entry's retrieval weight.

### Consequences

**Positive:**
- The retrieval unit matches the authoring unit and the citation unit, so nothing has to be
  reassembled at answer time.
- 3.3's split rule falls out of the corpus chunker's existing atomic/repeat machinery.

**Negative:**
- An entry with one unbacked cause is marked entirely, so a user sees the caveat on four sound
  causes as well as the fifth.
- The whole entry's `passage_id` changes when any one cause is edited (see Decision 3's
  consequences), where per-cause passages would have preserved the others.
- Per-cause data needs a channel outside `Passage`, which CONTRACTS §2 forbids extending.

---

## Decision 3: Fix pointers address a section by number or title, never a page

**Date**: 2026-08-14
**Status**: accepted

### Context

Every cause needs a reference into the vendor corpus that the author can type from memory at the
desk (1.7), that survives a manual being replaced by a later version of the same document (8.3), and
that a resolver can check on every run (2.1). Two of the three reference manuals are numbered; the
APC Key 25 guide has no numbering at all.

### Decision

`fix: <source_id> §<section-number>`, or `fix: <source_id> "<section title>"`, or both. A pointer
resolves to the ordered set of passages that section produced. No page form exists, and the author
is never asked for a `passage_id`.

### Rationale

8.1 rules out page-only addressing, and admitting a page even as a qualifier would reintroduce the
breakage 8.3 exists to prevent. The title form is not a convenience: without it, no cause could
point into an unnumbered manual, which is a third of the corpus. Resolving to the whole section
rather than a single chunk keeps pointers stable across a re-chunk — which chunk holds the sentence
about a control is an artefact of the 350-word cap, not a property of the manual.

### Alternatives Considered

- **A pasted `passage_id`**: Exact, unambiguous, no resolution step - Rejected because it is a
  hand-copied opaque value (against 1.7), and because it is *less* durable than a section reference:
  any text edit in the manual orphans it, where a section reference survives.
- **Page-and-line addressing**: Precise and easy to read off the PDF - Rejected by 8.1; page numbers
  move between document versions and would break every pointer on a point release.
- **Free-text references checked by search**: The author writes what they like; the resolver finds
  the best-matching passage - Rejected because it always resolves to something. A grounding check
  that cannot fail is not a check.

### Consequences

**Positive:**
- A pointer is typed from what the citation already shows the author, with no lookup.
- Section-level resolution is stable across re-chunking and across manual point releases.
- A number plus a title gives a free renumbering detector, at no authoring cost.

**Negative:**
- Ambiguous section titles resolve to nothing and must be reported with candidates, which is more
  work than picking the first match.
- A pointer's resolution set can be several passages, so the term check runs over their concatenation
  and can pass on a term that appears in a neighbouring chunk of the same section.

---

## Decision 4: A committed pointer ledger distinguishes rejection from drift

**Date**: 2026-08-14
**Status**: accepted

### Context

2.2 rejects an entry whose pointer has never resolved; 8.4 flags one whose pointer used to resolve
and no longer does. The two cases look identical at the moment of failure, and the system has no
memory of whether a pointer ever worked. `index/` cannot supply it: it is derived and is deleted by
a rebuild, so the first rebuild after a manual changes would reject entries that 8.4 requires be
served with a mark.

### Decision

Record each **pointer** that resolves in `triage/.pointer-ledger.jsonl`, keyed on the pointer alone —
`(source_id, section number, or normalised title)` — machine-written and committed. No ledger row
means never verified, so an unresolved pointer is a rejection; a row present means it worked once,
so an unresolved pointer is a flag plus `unbacked`. The file is newline-delimited JSON, one row per
line sorted by pointer, with `merge=union` set in `.gitattributes`; rows are never pruned;
`resolved_at` is written only on transition; an unparseable ledger fails the run. `dawmans validate`
reads the ledger and never writes it.

### Rationale

The distinction the requirements draw is about the author's presence, and the ledger is the only
durable record of a moment when the author was present and the pointer worked. Committing it makes
that record survive a clone and a rebuild, which is exactly when the 1 a.m. scenario 8.4 describes
occurs.

The key is the pointer because **verification is a property of the pointer's target, not of the
entry holding it**. Keying on the entry — its normalised symptom plus device set — turns a cosmetic
edit into a mass rejection: adding a device to `devices:` changes the key, so every pointer in that
entry loses its row, and any one that has since drifted becomes a 2.2 rejection instead of an 8.4
flag. The entry is then withdrawn mid-session by an edit that had nothing to do with pointers. 2.2
still does its work under pointer keying, because a row only ever records a pointer that *did*
resolve, and a newly typed pointer has none.

The format follows from the file being committed. A single JSON object cannot be merged by git, and
"never hand-edited" is unenforceable in exactly the situation git demands it; one row per line plus
a union merge makes two machines' additions combine without a conflict. Never pruning is what keeps
the union merge sound — a merge strategy that only adds cannot be paired with a rule that deletes.
Writing `resolved_at` only on transition keeps a no-change run's diff empty.

### Alternatives Considered

- **Key on `entry_key`, the normalised symptom plus device set**: Survives a file rename and a
  re-chunk, and detects the 1.9 duplicate with the same value - Rejected because a scope edit
  changes the key and prunes the entry's rows, converting drift flags into rejections; the entry is
  withdrawn for an unrelated edit. `entry_key` is retained as a report annotation only.
- **Keep the memory in `index/`**: No new artefact, no repository noise - Rejected because a
  rebuild deletes it, so a drifted entry would be rejected rather than flagged in precisely the
  situation 8.4 was written for.
- **No memory at all — always flag**: Simple, never withdraws working triage - Rejected because it
  discards 2.2, which is the only mechanism that catches a typed pointer at the moment the author can
  fix it; a permanently flagged entry that never worked is folklore with a caveat on it.
- **No memory at all — always reject**: Simple, maximally strict - Rejected because it withdraws
  working triage mid-session for a change the author did not make and cannot see.
- **Infer from whether the source is still indexed**: A removed manual means drift, a missing
  section means a typo - Rejected because a renumbered section is indistinguishable from a mistyped
  one under that test, and renumbering is the common case.

### Consequences

**Positive:**
- Both criteria are satisfied with one small file and no per-entry bookkeeping by the author.
- No entry edit can change a ledger key, so no edit to an entry can convert a drift flag into a
  rejection.
- Deleting the file re-arms 2.2 for everything, which is the correct degradation when the claim that
  a pointer once worked has been lost — and the deletion is reported rather than silent.

**Negative:**
- Verification is coarser than the entry: a pointer verified by one entry counts as verified for a
  different entry that later adopts the same pointer, so a genuinely new cause reusing a
  known-good pointer gets an 8.4 flag where 2.2 would have rejected it. This is the price of not
  keying on the entry, and it errs towards serving marked triage rather than withdrawing it.
- Verification is also inherited across machines and clones: an entry verified once on the author's
  machine is treated as verified everywhere, even against a different copy of the manuals.
- A machine-written file in the repository is in the merge path. Union merge resolves concurrent
  additions but never deletes, so the file only grows and can retain a row for a pointer no entry
  holds; and a corrupted file stops the run rather than degrading, which is loud but costs the run.
- A pointer that resolved to the *wrong* section and was later corrected in the manual is flagged
  rather than rejected, because the ledger records that it resolved, not that it was right.

---

## Decision 5: A failed term check flags but does not set `unbacked`

**Date**: 2026-08-14
**Status**: accepted

### Context

2.6 requires a control name, parameter or numeric value in a cause to appear in the passage that
cause points at, and requires a miss to be flagged. It does not say whether the miss also sets
`unbacked` (CONTRACTS §2), and there is a real argument that it should: a factual claim the pointed-at
passage does not support is exactly what the flag exists to mark.

### Decision

A `term-not-in-passage` miss is reported in the coverage report and leaves `unbacked` clear. 2.4 and
8.5 remain the only two producers of `unbacked`. It does, however, make `dawmans validate` exit
non-zero, so the check has consequences where the author is present and none where the user is.

### Rationale

The term extractor is a heuristic over an author's prose: capitalisation is inconsistent, control
names are paraphrased, and a term can appear in a neighbouring chunk of the same section. Its
false-positive rate is unknown and cannot be bounded by design. `unbacked` renders inline on every
citation drawn from the passage (CONTRACTS §3), so wiring a noisy signal to it would put a caveat on
sound entries and teach the user to ignore the caveat in the two cases where it is precise.

### Alternatives Considered

- **Set `unbacked` on a term miss**: Strictest reading of 2.6, no unsupported claim escapes marking -
  Rejected because it spends the product's scarcest signal on a heuristic, and the requirements' own
  risk register already records this check as shallow.
- **Reject the entry on a term miss**: Forces the author to fix it - Rejected because 2.6 says flag,
  and because a false positive would then cost the user a working entry.

### Consequences

**Positive:**
- `unbacked` keeps a precise meaning — no vendor passage backs this cause — that the UI can render
  without qualification.
- A noisy check can be tuned without changing what the user sees on a citation.

**Negative:**
- An entry making a factual claim its pointer does not support is ingested, retrievable and cited
  with no user-visible mark; only the coverage report and the `validate` exit code show it.
- A false positive costs a non-zero `validate` and a re-read, so a noisy extractor becomes an
  authoring irritation rather than a user-facing one.

---

## Decision 6: The closing statement is identified by position, not by a reserved title

**Date**: 2026-08-14
**Status**: accepted

### Context

1.3 makes "a closing statement of what to do when every cause is eliminated" an optional part of an
entry, and 1.4 excludes it from the 2–6 cause count. Nothing in the requirements says how the parser
tells it apart from a cause. Both are `##` sections in the same document, and the entry format has
no reserved vocabulary anywhere else.

### Decision

The closing statement is the **final** `##` section carrying neither a `check:` line nor a fix line.
No title is reserved. A section demoted to a closing statement by this rule always emits a
`closing-statement-inferred` flag naming it.

### Rationale

A reserved title is a value the author must remember and spell exactly, in a format whose whole
premise (Decision 1) is that the body needs no syntax. Position plus absence of both keyed lines
uses what is already there. The rule's real cost is that it is silent when wrong: a final section
meant as a cause that has lost *both* its check and its fix is read as a note, so an entry of three
causes becomes two plus a note — inside 1.4's band, nothing rejects, the cause vanishes from the
ranked list `api/answer-engine` 7.2 and 7.6 consume, and 1.5 forbids exactly that. The mandatory
flag is what makes the inference visible; without it the rule would be unacceptable. Losing only the
fix, the likelier slip, still rejects under 1.2 and never reaches this path.

### Alternatives Considered

- **A reserved title (`## Otherwise`, `## If none of these`)**: Unambiguous, no inference, no flag
  needed - Rejected because it is a hand-maintained magic value in a format that otherwise has none,
  and a misspelling turns the note into a cause that rejects for missing a check — a worse message
  than the one it avoids.
- **A frontmatter key (`closing: …`)**: Machine-exact, parsed by the same strict path as `devices` -
  Rejected because it moves prose the author writes last into the block they write first, and puts
  the one free-text paragraph of the entry behind YAML quoting, which Decision 1 rejected for the
  cause text for the same reason.
- **No closing statement construct at all**: Trailing prose folds into the last cause - Rejected
  because 1.3 names it as an optional part, and folding it in attaches advice about *every* cause to
  the least likely one, which is where a split entry would then carry it.

### Consequences

**Positive:**
- The grammar keeps no reserved words, so nothing has to be remembered or spelled exactly.
- The demotion is always reported, so 1.5's guarantee is auditable rather than assumed.

**Negative:**
- A well-formed entry whose author genuinely meant a closing statement still emits a flag, so the
  flag is common and carries no severity — it is an inventory line, not a warning.
- The rule is positional, so a closing statement written between two causes is parsed as a cause and
  rejects for a missing check.

---

## Decision 7: Only free-text keyed values continue onto the next line

**Date**: 2026-08-14
**Status**: accepted

### Context

The grammar of [`design.md`](design.md) §Entry grammar originally gave one continuation rule for
every keyed line: a value runs until a blank line, a heading or another keyed line. Implementing the
parser showed what that costs on the two keys whose value is not free text. An author who writes

```markdown
## The buffer size is too high for tracking
check: latency is audible when playing in
fix: ableton/live-12 §1.2 "Audio Preferences"
Raising it again after tracking is fine.
```

has the trailing note folded into the pointer, which then addresses nothing. The cause is rejected
under `cause-missing-fix`, or — once the resolver exists — under 2.2, and the message names a
pointer the author never typed. The same happens to a preamble line written under an `also:` list,
where it silently becomes part of the last alternative phrasing.

### Decision

`check:` and `why:` continue until a blank line, a heading or another keyed line. `fix:`,
`undocumented:` and `also:` are complete on their own line; a following prose line is prose, retained
in the preamble or in the cause's notes.

### Rationale

The split falls out of what the values are. `check:` and `why:` are sentences the author writes at
speed and wraps wherever the editor wraps them, so continuation is what they mean. The other three
each have a grammar that ends at the line: a pointer is one of Decision 3's three forms, an
`undocumented:` value is a single device id, and `also:` is a `;`-separated list whose separator is
already explicit. Nothing is gained by letting them run on, and what is lost is exactly the case
Decision 1 exists to prevent — a typing habit costing a parse failure rather than a flag.

It also keeps the rejection honest. Under the single rule the reported reason is about the pointer,
so the message points the author at a line that is correct, and the line that caused it is the one
not mentioned.

### Alternatives Considered

- **Keep one continuation rule for every key**: One sentence of grammar, nothing to remember -
  Rejected because it makes an ordinary note under a `fix:` line reject the entry, with a message
  naming the wrong line. This was found by the cause-conservation property, not by an example.
- **End every value at its own line, including `check:`**: Simpler still, and uniform the other way -
  Rejected because a check is the entry's one substantial sentence and is the value most likely to
  wrap; truncating it at the first newline would drop half of what the author wrote, which 1.3's
  "retained, never dropped" forbids.
- **Require a blank line before any prose**: Uniform rule, author-enforced - Rejected because it is
  an invisible whitespace requirement in a format whose premise is that the body needs no syntax,
  and its failure mode is silent.

### Consequences

**Positive:**
- A note written under a fix pointer costs nothing, which is how the format is actually used.
- Pointer parsing sees exactly one line, so its grammar and its error messages stay local.
- `also:` keeps its `;` separator as the only way to add a phrasing, so the phrasing list cannot
  grow by accident.

**Negative:**
- The grammar now has two continuation rules rather than one, and which key gets which is a fact to
  look up rather than derive.
- A genuinely long `fix:` line cannot be wrapped, so an unusually long section title has to sit on
  one line.

---

## Decision 8: Scope recognition matches documented device identities, not source ids alone

**Date**: 2026-08-15
**Status**: accepted

### Context

Design 'Device scope' classifies each declared device against two vocabularies: `rig.yaml`'s device
ids, and what the corpus has indexed. The tasks phrase the second as "indexed source ids", and taken
literally that is `SourceRecord.source_id`.

The two are not the same vocabulary. `data/manual-corpus` §Rig inventory carries the worked case:
the Focusrite guide's filename product is `scarlett-solo-4g` and the rig device id is
`scarlett-solo`, joined by a `source_applicability` declaration. Under the literal reading, an entry
declaring `focusrite/scarlett-solo` — the identity `rig.yaml` publishes and 4.2 tells the author to
use — matches no source id, so it takes the 4.4 row and is reported as applying to an undocumented
device while its guide sits in the corpus. That contradicts this design's own statement that the
owned-but-undocumented set "is empty today ... this was written of the Scarlett Solo, whose guide
has since been ingested", and it contradicts `manual-corpus`'s rule that both gap reports compute
over `source_applicability.device` rather than over `source_id`.

### Decision

`validate_scope`'s `indexed` argument is the set of every identity the corpus documents: each
indexed vendor-manual `source_id` **and** the device id that source declares under
`source_applicability`. A declared device is documented if it is in that set.

### Rationale

It is the reading under which the design's own claims about today's rig hold, and it is the same
key `manual-corpus` computes its two gap reports over — one vocabulary for "what the corpus
documents", used by both specs. Keeping the source ids in the set as well costs nothing and honours
4.2: `focusrite/scarlett-solo-4g` names a real ingested source, and an author who writes it has
named something that exists, not made a typo.

Matching stays exact in both halves (4.2). The union is a wider vocabulary, never a fuzzier match.

### Alternatives Considered

- **Source ids only, as the task text reads literally**: The narrowest input and the least this spec
  has to know about the corpus - Rejected because it makes today's Scarlett declaration take the 4.4
  row, producing a standing false report of an undocumented device and, by 4.5's "neither" wording,
  turning a rig-absent device documented under a generation-marked source id into a spurious
  `unknown-device` flag.
- **Applicability device ids only, dropping the source ids**: Exactly `manual-corpus`'s gap-report
  key, with no union - Rejected because `focusrite/scarlett-solo-4g` is an ingested source and 4.5
  flags a declaration that is "neither in the rig inventory nor an ingested source". Naming a real
  source is not the typo 4.5 exists to catch.
- **Resolve the declaration through the mapping before matching**: Map a declared id to its
  applicability device, then compare - Rejected because it is a resolution step, not a match, and
  4.2's point is that the identities are shared so no such step is needed. It also has no answer
  where a device is documented by two sources.

### Consequences

**Positive:**
- The design's stated fact — an empty owned-but-undocumented set today — holds against the
  implementation rather than against a reading of it.
- `undocumented-claim-invalid` catches the 2.3 claim whether the author names the device or the
  source documenting it, so the carve-out cannot be taken by naming the other identity.
- Both specs compute "what the corpus documents" the same way, so the two gap reports and this
  spec's 4.4 row cannot disagree.

**Negative:**
- The caller must build the set from the corpus rather than passing `sources.json`'s keys, so the
  wiring in the loader (task 18) carries a small assembly step this spec has to get right.
- A `source_applicability` declaration missing its generation marker silently narrows the
  vocabulary, and the symptom is a 4.4 report rather than an error — the same failure mode
  `manual-corpus` accepts for its indexed-but-not-owned report.

### Impact

`triage/scope.py` and the loader wiring that supplies its `indexed` argument. No change to the
rejection or flag vocabularies, and none to `rig.yaml` or `manual-corpus`.

---

## Decision 9: A ledger transition is detected by comparing passage ids

**Date**: 2026-08-15
**Status**: accepted

### Context

The design requires `resolved_at` be written **only on transition** — "first resolution, or
resolution after a drift" — so that a run changing nothing leaves `triage/.pointer-ledger.jsonl`
byte-identical and the working tree clean. A machine-written file that is also committed is only
tolerable on that condition.

It does not say how a run recognises "resolution after a drift". The ledger deliberately carries no
drifted marker: a row records that a pointer *did* resolve and nothing else, which is what makes
rows safe never to prune and safe to merge as a union. A run meeting a resolving pointer with a row
already present therefore cannot tell, from the row's existence alone, whether it is looking at an
ordinary unchanged run or at a recovery from a drift a previous run flagged.

### Decision

A transition is a row whose `passage_ids` differ from what the pointer resolves to now — or the
absence of a row at all. `Ledger.record` rewrites the row, moving `resolved_at`, in exactly those
two cases, and reports whether it did.

### Rationale

The passage ids *are* the record of what was verified, and drift is by definition a change in what
the pointer addresses. A section that was renumbered and rewritten produces different passages, so
a pointer resolving again after the manual is revised resolves to ids the row does not hold — the
transition, observable from the row itself without a second field to keep in step with it.

The degenerate case comes out right rather than merely tolerable: a manual restored to exactly its
previous state resolves to exactly the previous ids, so nothing transitioned, nothing is written,
and the file stays byte-identical. The flag clears because the pointer resolves, which is what 8.5
asks for — it never asked for a ledger write.

### Alternatives Considered

- **A `drifted` field on the row**: mark the row when a run flags it, clear it when the pointer
  resolves again - rejected because it makes the ledger stateful about the *present* rather than a
  record of the past. Two machines with union-merged ledgers would then hold rows disagreeing about
  a current condition, and no merge rule resolves that; a union of "did resolve" rows is always
  sound.
- **Move `resolved_at` on every successful resolution**: the simplest possible rule - rejected
  because it rewrites the file on every run, so an ingest that changed nothing dirties the working
  tree and the author cannot tell a real ledger change from noise in `git diff`. That defeats the
  reason the file is committed at all.
- **Compare a hash of the resolved passages' text**: more directly "did the text change" - rejected
  because a `passage_id` is already content-derived (`manual-corpus` 3.9), so the ids carry that
  information, and reading passage text here would make resolution depend on more of the view than
  the two maps it is specified to read.

### Consequences

**Positive:**
- No field exists that a run could forget to clear, so the ledger cannot hold a stale drift mark.
- A no-change run is byte-identical, which is what keeps the committed file honest in review.
- Rows stay pure records of the past, so the `merge=union` rule in `.gitattributes` remains sound.
- Recovery from drift needs no edit to the entry and no ledger surgery — restoring the manual is
  the whole fix.

**Negative:**
- A re-chunk that changes passage ids without changing what the section says reads as a transition
  and moves `resolved_at`. The row stays correct and nothing is flagged, but the timestamp
  overstates what happened.
- The ledger cannot report *when* a pointer drifted, only when it last resolved. Requirement 8.6
  lists flagged entries in the coverage report from the current run's outcome, so nothing needs that
  history today.

### Impact

`triage/pointers.py` — `Ledger.record` and its return value. No change to the row schema, to the key
rule of Decision 4, or to the reject-versus-flag decision itself.

---
