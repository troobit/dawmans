---
references:
    - specs/data/symptom-triage/requirements.md
    - specs/data/symptom-triage/design.md
    - specs/data/symptom-triage/decision_log.md
    - specs/CONTRACTS.md
    - specs/data/manual-corpus/design.md
---
# Symptom Triage

## Phase 1: Entry model and grammar

- [x] 1. Define the triage entry model types <!-- id:f3stq01 -->
  - dawmans/triage/: frozen dataclasses Entry, Cause, DeviceRef, Pointer, Unresolved - the design's Components and Interfaces section verbatim, including Unresolved's closed reason literal and Entry's source_file/line (the two halves of CONTRACTS 2 entry_location).
  - Everything downstream builds against SourceLoader, Discovered, LoadResult, Region, Unit and UnitFlags from dawmans/corpus/loader.py - manual-corpus owns them and nothing here redefines them.
  - Types only - no behaviour, so no preceding test task.
  - Stream: 1
  - Requirements: [1.1](requirements.md#1.1), [1.2](requirements.md#1.2)
  - References: specs/data/manual-corpus/design.md

- [x] 2. Write tests for the entry grammar <!-- id:f3stq02 -->
  - BOM stripped before the frontmatter check; `---` fence required at byte 0; `devices` required, a YAML list, non-empty - frontmatter-missing/-malformed, no-devices and devices-not-a-list each reject, and `devices: ableton/live-12` (a string that iterates as characters) is the devices-not-a-list case.
  - Exactly one H1 is the symptom; `also:` lines split on `;` into phrasings; other preamble prose is retained, never dropped. Keyed lines match case-insensitively after stripping `-`, `*`, `>`, `#`, `**` - `**Check:**`, `- check :` and `CHECK:` are one line - and the emitted text carries the normalised marker.
  - Causes are the H2s in document order; exactly one `check:` per cause; one or more `fix:` lines XOR exactly one `undocumented:` line - both on one cause is cause-fix-and-undocumented; outside 2-6 causes rejects (too-few/too-many), with the closing statement excluded from the count.
  - Closing statement is the final H2 with neither a check nor a fix (Decision 6 - position, no reserved title), and a demotion always emits closing-statement-inferred naming the section: three_causes_last_demoted.md is the fixture. unknown-frontmatter-key flags, not fatal.
  - Property - total parsing: any byte string returns an Entry or a rejection naming the file; never raises, never a half-built entry. Property - cause conservation: causes emitted plus closing-statement-inferred flags equals the total H2 count - stated over the total, not over the H2s that were not the author's closing statement, because Decision 6 turns on the parser being unable to tell those apart and therefore flagging every inferred one.
  - Keyed-line continuation splits by value kind (Decision 7): check: and why: continue until a blank line, a heading or another keyed line; fix:, undocumented: and also: end at their own line, so a note written under a pointer is retained as a note rather than folded into the pointer.
  - Blocked-by: f3stq01 (Define the triage entry model types)
  - Stream: 1
  - Requirements: [1.1](requirements.md#1.1), [1.2](requirements.md#1.2), [1.3](requirements.md#1.3), [1.4](requirements.md#1.4), [1.7](requirements.md#1.7), [2.3](requirements.md#2.3), [4.1](requirements.md#4.1), [5.2](requirements.md#5.2)

- [x] 3. Implement triage/parse.py <!-- id:f3stq03 -->
  - Entry file to Entry plus the canonical rendering; strict only about frontmatter, forgiving in the body (Decision 1). No hand-computed value is ever demanded of the author (1.7).
  - Blocked-by: f3stq02 (Write tests for the entry grammar)
  - Stream: 1
  - Requirements: [1.1](requirements.md#1.1), [1.2](requirements.md#1.2), [1.3](requirements.md#1.3), [1.4](requirements.md#1.4), [1.7](requirements.md#1.7), [2.3](requirements.md#2.3), [4.1](requirements.md#4.1), [5.2](requirements.md#5.2)

## Phase 2: Pointer resolution and the ledger

- [x] 4. Build the section fixtures from the real index <!-- id:f3stq04 -->
  - Extract once and commit: live_sections.json (the ~15 sections the starter set points at, including the section printing `0 dB` that 7.3 depends on), scarlett_sections.json (the DIRECT MONITOR section), apc_sections.json (unnumbered regions, for the title form), split_section.json (one section chunked into three).
  - Requires a locally built index - manual-corpus implemented and its prerequisites met; CI never opens a PDF, exactly as the corpus's extraction snapshots work.
  - Also build the drift/ fixture pair (the same section with edited text plus a seeded ledger) and overlapping_scopes/ (the same symptom scoped [live-12] and [live-12, apc-key-25]).
  - Stream: 1
  - Requirements: [2.1](requirements.md#2.1)
  - References: specs/data/manual-corpus/prerequisites.md

- [x] 5. Write tests for the pointer grammar and section resolution <!-- id:f3stq05 -->
  - Three forms parse: `<source_id> §<number>`, `<source_id> "<title>"`, both together; no page form exists at all (8.1, Decision 3), and a version change alone breaks nothing because source_id carries no version (8.3).
  - Resolution runs against two maps built in one pass over the view's passages.jsonl - (source_id, section_number) and (source_id, normalised title) - each to the section's passage ids in section order; immutable once built, so two runs over one view resolve identically.
  - Title normalisation: casefold, collapse whitespace, strip a leading section number and trailing punctuation; else a unique prefix; two matches is Unresolved(ambiguous-title) with candidates named, never an arbitrary pick. apc_sections.json proves the title form reaches an unnumbered manual.
  - A pointer resolves to all k chunks of a split section (split_section.json); an unknown source is unknown-source; a pointer naming authored/triage is the pointer-authored-target rejection (2.7).
  - Where number and title are both given the number selects and the title corroborates - a disagreement is the title-number-disagreement flag, the free renumbering detector.
  - Blocked-by: f3stq01 (Define the triage entry model types), f3stq04 (Build the section fixtures from the real index)
  - Stream: 1
  - Requirements: [2.1](requirements.md#2.1), [2.7](requirements.md#2.7), [8.1](requirements.md#8.1), [8.3](requirements.md#8.3)

- [x] 6. Implement pointers.py grammar, SectionIndex and resolve <!-- id:f3stq06 -->
  - Nearest-section candidates for the 5.3 message come from the same normalised title index, by edit distance.
  - Blocked-by: f3stq05 (Write tests for the pointer grammar and section resolution)
  - Stream: 1
  - Requirements: [2.1](requirements.md#2.1), [2.7](requirements.md#2.7), [8.1](requirements.md#8.1), [8.3](requirements.md#8.3)

- [x] 7. Write tests for the pointer ledger and reject-versus-flag <!-- id:f3stq07 -->
  - No ledger row and unresolved is a 2.2 rejection naming entry, cause and pointer; a row present and unresolved is an 8.4 flag plus unbacked on the cause, the entry stays ingested, and resolving again on a later run clears the flag (8.5). An unchanged passage keeps resolving with no edit to the entry (8.2, drift/ fixture).
  - The key is the pointer alone - (source_id, section number, or normalised title) - never the entry (Decision 4). Property - ledger key stability: editing an entry's devices: or symptom wording changes no key, so no previously resolving pointer becomes a rejection. Property - reject/flag state machine: over random (ingest, edit entry, edit manual, remove manual, restore) sequences, a pointer that resolved once is only ever a flag afterwards.
  - NDJSON, one row per pointer sorted by pointer; resolved_at written only on transition, so a no-change run leaves the file byte-identical; rows never pruned; entry_keys is annotation, not key.
  - A missing ledger re-arms 2.2 for everything and emits one report line saying so; an unparseable ledger is a failure - non-zero, naming the file and line - never a rejection.
  - dawmans validate reads the ledger and never writes it, so checking work cannot promote a broken pointer to previously-fine.
  - Blocked-by: f3stq06 (Implement pointers.py grammar, SectionIndex and resolve)
  - Stream: 1
  - Requirements: [2.2](requirements.md#2.2), [8.2](requirements.md#8.2), [8.4](requirements.md#8.4), [8.5](requirements.md#8.5)

- [x] 8. Implement the pointer ledger <!-- id:f3stq08 -->
  - triage/.pointer-ledger.jsonl, machine-written and committed, with merge=union set in .gitattributes; append-and-update only under dawmans ingest.
  - Blocked-by: f3stq07 (Write tests for the pointer ledger and reject-versus-flag)
  - Stream: 1
  - Requirements: [2.2](requirements.md#2.2), [8.2](requirements.md#8.2), [8.4](requirements.md#8.4), [8.5](requirements.md#8.5)

## Phase 3: Term check and device scope

- [x] 9. Write tests for term extraction and containment <!-- id:f3stq09 -->
  - The checked span is the cause statement plus its check: value only - why:, loose prose and the closing statement are excluded, the deliberate narrowing that keeps 2.5's causal assertions out of a factual check.
  - Extraction: capitalised runs (`Track Activator`, `DIRECT MONITOR`), with a single-token sentence-start run dropped unless capitalised elsewhere in the entry; numeric literals with optional unit (`0 dB`, `44.1 kHz`). Terms equal to a declared device's id, product token or rig.yaml display_name are discarded, as are tokens under three characters.
  - Containment is case-sensitive at word boundaries for the capitalised class - casefolding would make `Off`, `Monitor` and `MIDI` match trivially - and casefolded at word boundaries for numerics, so `0` never satisfies `10`.
  - Multi-pointer: any pointer's resolution set containing the term satisfies it; the term check sees a split section's concatenation.
  - A miss is a term-not-in-passage flag naming the term and the section, and never sets unbacked (Decision 5 - 2.4 and 8.5 stay the only producers). Property - soundness, one direction only: a cause whose terms are all lifted verbatim with their case from any one pointer's resolution set never flags.
  - Blocked-by: f3stq03 (Implement triage/parse.py), f3stq04 (Build the section fixtures from the real index)
  - Stream: 2
  - Requirements: [2.5](requirements.md#2.5), [2.6](requirements.md#2.6)

- [x] 10. Implement terms.py <!-- id:f3stq0a -->
  - Blocked-by: f3stq09 (Write tests for term extraction and containment)
  - Stream: 2
  - Requirements: [2.5](requirements.md#2.5), [2.6](requirements.md#2.6)

- [x] 11. Write tests for device scope validation <!-- id:f3stq0b -->
  - The six-row table of design 'Device scope': in rig and indexed scopes normally; in rig with no indexed source scopes and reports undocumented-device-scope (4.4 - exercised against a fixture rig, since no live device can produce it); indexed but not in rig scopes with no flag; some-unrecognised flags naming the declaration (4.5); all-unrecognised is the all-devices-unrecognised rejection (the recorded 4.5 deviation - an entry no turn can retrieve is withdrawn at the desk, not embedded unreachable).
  - Identities are matched exactly against rig.yaml device ids and indexed source ids, never fuzzily (4.2); undocumented-claim-invalid rejects an undocumented: line naming a device absent from the rig or one that is indexed (2.3).
  - Revision comparison is exact after casefold and stripping non-alphanumerics: `@mk2` matches `revision: mk2`, `@12-standard` matches `"12 Standard"`, `@suite` does not and flags revision-mismatch (4.6) quoting the rig's value verbatim.
  - Blocked-by: f3stq03 (Implement triage/parse.py)
  - Stream: 2
  - Requirements: [2.3](requirements.md#2.3), [4.2](requirements.md#4.2), [4.4](requirements.md#4.4), [4.5](requirements.md#4.5), [4.6](requirements.md#4.6)

- [x] 12. Implement scope.py validation <!-- id:f3stq0c -->
  - Device declarations against rig.yaml and the corpus's indexed source ids; the flag and rejection vocabulary of design 'Error Handling'.
  - Blocked-by: f3stq0b (Write tests for device scope validation)
  - Stream: 2
  - Requirements: [2.3](requirements.md#2.3), [4.2](requirements.md#4.2), [4.4](requirements.md#4.4), [4.5](requirements.md#4.5), [4.6](requirements.md#4.6)

## Phase 4: Emission, identity and the loader

- [x] 13. Write tests for authored identity and the SourceRecord <!-- id:f3stq0d -->
  - source_id is the constant `authored/triage` per CONTRACTS 1 - 3.1's content-derived clause is the recorded defect, and only its operative half (independent of any filename, 1.8) is tested. display_name is `My Triage Notes`; hardware_applicability is `assumed` unconditionally and nothing in configuration can raise it (CONTRACTS 1 over 3.8's literal text); vendor, product, doctype, lang, doc_version, page_count and low_text are absent - manual-corpus 12.5's constructor refuses them.
  - passage_id is corpus.passage_id("authored/triage", passage_text) - the same function over the same canonical form as a manual passage (3.9).
  - Property - cosmetic invariance: perturbing marker style, blank lines, key casing, line endings, frontmatter key order and pointer targets leaves the ID unchanged (8.2's authored half). Property - sensitivity: any change to symptom, phrasings, preamble, cause statement, check or notes changes it. Property - canonical idempotence: render(parse(render(parse(f)))) == render(parse(f)).
  - Every passage and citation drawn from an entry resolves to this one SourceRecord, which is what carries kind to the user (3.7).
  - Blocked-by: f3stq03 (Implement triage/parse.py)
  - Stream: 1
  - Requirements: [1.8](requirements.md#1.8), [3.1](requirements.md#3.1), [3.7](requirements.md#3.7), [3.8](requirements.md#3.8), [3.9](requirements.md#3.9)

- [x] 14. Implement identity and the SourceRecord construction <!-- id:f3stq0e -->
  - Canonical rendering in parse.py is the hashed text; the record is constructed once per run in loader.py.
  - Blocked-by: f3stq0d (Write tests for authored identity and the SourceRecord)
  - Stream: 1
  - Requirements: [1.8](requirements.md#1.8), [3.1](requirements.md#3.1), [3.7](requirements.md#3.7), [3.8](requirements.md#3.8), [3.9](requirements.md#3.9)

- [x] 15. Write tests for unit emission, splitting and unbacked <!-- id:f3stq0f -->
  - The emission table of design 'Passage emission': symptom + phrasings + preamble first as Unit(repeat_on_split=True); each cause one Unit(atomic=True) in declared order, unmerged and undeduplicated (property - order preservation, 1.5 - the order becomes CONTRACTS 4c rank); closing statement atomic; Region(section_number=None, section_title=symptom, section_path=(), page_start=None, page_end=None, inferred=False) (3.4, 3.5); degraded=False and has_figures=False on every unit (3.6).
  - One passage per entry (Decision 2), split only over the 350-word cap and only between causes. Property - split invariants: every emitted passage contains the symptom exactly once and no cause spans two passages (3.3). Chunk overlap is suppressed for authored regions, or the second chunk carries the symptom twice in hashed, user-visible text.
  - Property - unbacked monotonicity: every passage carrying a 2.3-permitted or drifted cause is flagged and no passage is flagged without one (2.4, 8.5); a split entry marks only the passage carrying the cause; the 2.3 arm is exercised against a fixture rig, no live device being in that state.
  - entry_location is Entry.source_file (repo-relative) plus the H1's line, published with the passage and never contributing to passage_id or entry_key (3.5); alternative phrasings sit in Passage.text so BM25 sees them, fix pointers do not.
  - duplicate-symptom: two entries with the same normalised symptom and intersecting device sets - overlapping_scopes/ - reject both (1.9); intersection, not set equality, or both would ingest and both be retrievable in any Live-scoped turn.
  - Blocked-by: f3stq0e (Implement identity and the SourceRecord construction), f3stq08 (Implement the pointer ledger)
  - Stream: 1
  - Requirements: [1.5](requirements.md#1.5), [1.9](requirements.md#1.9), [2.3](requirements.md#2.3), [2.4](requirements.md#2.4), [3.2](requirements.md#3.2), [3.3](requirements.md#3.3), [3.4](requirements.md#3.4), [3.5](requirements.md#3.5), [3.6](requirements.md#3.6), [8.5](requirements.md#8.5)

- [x] 16. Implement TriageLoader.load emission <!-- id:f3stq0g -->
  - Regions in sorted path order; duplicate detection across the discovered set before emission; per-cause flags from the ledger and 2.3 decisions applied as UnitFlags.unbacked.
  - The overlap suppression for authored regions is a keyed change in dawmans/corpus/chunk.py - the one edit this spec makes to the corpus chunking pipeline, and manual-corpus's ledger does not carry it.
  - Blocked-by: f3stq0f (Write tests for unit emission, splitting and unbacked)
  - Stream: 1
  - Requirements: [1.5](requirements.md#1.5), [1.9](requirements.md#1.9), [2.3](requirements.md#2.3), [2.4](requirements.md#2.4), [3.2](requirements.md#3.2), [3.3](requirements.md#3.3), [3.4](requirements.md#3.4), [3.5](requirements.md#3.5), [3.6](requirements.md#3.6), [8.5](requirements.md#8.5)

## Phase 5: Discovery, sidecar and run integration

- [x] 17. Write tests for discovery and the unconditional load <!-- id:f3stq0h -->
  - Discovery is a recursive scan of triage/**/*.md - nested/live/no-sound.md is found; a .txt beside it gets a report line (the opposite of manuals/, where the skip is silent); dotfiles are exempt so .pointer-ledger.jsonl never warns about itself; filenames carry no meaning. discover() yields 0 or 1 Discovered; fingerprint is sha256 over sorted (relative path, file digest) pairs.
  - load() runs on every ingest regardless of fingerprint - the authored store is exempt from shard skipping, because pointer validity is a function of the manuals too (2.1), and the manifest-into-fingerprint alternative detects drift one run late by construction.
  - An entry added, edited or removed is reflected on the next run with no code, configuration or rebuild (5.1); CorpusView is read-only over the view's passages.jsonl and sources.json and never opens a shard, vector file or PDF, so re-ingesting the authored source re-extracts nothing (5.7). Per-passage vector reuse for unchanged entries is manual-corpus's behaviour - its task e7lsx2q tests it - assumed here as an interface, not re-tested.
  - authored-invalid only when no entry survives, and it deletes the authored shard - otherwise a fully-malformed store keeps serving the previous run's passages while reporting success. An existing empty triage/ is an empty discovery set (shard removed); an absent or unreadable triage/ is an unavailable store (shard retained).
  - Blocked-by: f3stq0g (Implement TriageLoader.load emission)
  - Stream: 1
  - Requirements: [1.6](requirements.md#1.6), [2.1](requirements.md#2.1), [5.1](requirements.md#5.1), [5.7](requirements.md#5.7)

- [x] 18. Implement TriageLoader.discover and the ingest wiring <!-- id:f3stq0i -->
  - Wire TriageLoader into the corpus run as the second SourceLoader: the authored load runs after every vendor shard has committed, so pointers resolve against the passages this run produced, and the fingerprint-skip exemption lives in the run orchestration.
  - Blocked-by: f3stq0h (Write tests for discovery and the unconditional load)
  - Stream: 1
  - Requirements: [1.6](requirements.md#1.6), [2.1](requirements.md#2.1), [5.1](requirements.md#5.1), [5.7](requirements.md#5.7)

- [x] 19. Write tests for the sidecar <!-- id:f3stq0j -->
  - LoadResult.sidecar lands at views/<hex>/reports/authored_triage.json - the corpus's slug rule, underscore not hyphen, or a reader finds nothing, no error is raised, and every entry stays in scope for every turn.
  - Per passage_id: devices (the input to api/answer-engine 5.13's per-passage predicate, 4.3 - this spec filters nothing itself), source_file and line (the entry_location halves), and causes in declared order with statement, check, fix passage_ids, undocumented_device and flags - the source of CONTRACTS 4c Cause records, so 1.5 is load-bearing here too.
  - entry_key is sha256 over the normalised symptom and sorted device ids, an annotation for the report, key of nothing.
  - The report block carries pointers checked/resolved/unresolved/without_pointer (2.8) and one row per rejection and flag with its reason (5.5), the same rows dawmans coverage renders; the unbacked-cause shape (`"fix": [], "undocumented_device": ...`) is asserted against the fixture rig.
  - Blocked-by: f3stq0g (Implement TriageLoader.load emission), f3stq0a (Implement terms.py), f3stq0c (Implement scope.py validation)
  - Stream: 1
  - Requirements: [2.8](requirements.md#2.8), [4.3](requirements.md#4.3), [5.5](requirements.md#5.5)

- [x] 20. Implement the sidecar assembly <!-- id:f3stq0k -->
  - Built in scope.py from the loader's per-entry results; the corpus copies it into the view, so it swaps atomically with the passages it keys.
  - Blocked-by: f3stq0j (Write tests for the sidecar)
  - Stream: 1
  - Requirements: [2.8](requirements.md#2.8), [4.3](requirements.md#4.3), [5.5](requirements.md#5.5)

## Phase 6: Messages, validation and coverage

- [ ] 21. Write tests for validation messages and the rejection taxonomy <!-- id:f3stq0l -->
  - The rejection set is closed - the fifteen reason constants of design 'Error Handling', three of its twelve table rows carrying paired reasons - and one malformed fixture per reason constant proves each message names the file, the symptom and the cause concerned, and says what to change in the entry's own words, never a position or internal error name alone (5.3); pointer messages carry the nearest-section candidates.
  - A rejection excludes one entry; the other entries in the same run still ingest and the run reports succeeded (5.2). Only when no entry survives is the source rejected as authored-invalid.
  - Per-run counts of entries ingested, rejected and flagged, with a reason for each (5.5).
  - Blocked-by: f3stq0g (Implement TriageLoader.load emission), f3stq0c (Implement scope.py validation)
  - Stream: 1
  - Requirements: [5.2](requirements.md#5.2), [5.3](requirements.md#5.3), [5.5](requirements.md#5.5)

- [ ] 22. Implement the validation message rendering <!-- id:f3stq0m -->
  - Blocked-by: f3stq0l (Write tests for validation messages and the rejection taxonomy)
  - Stream: 1
  - Requirements: [5.2](requirements.md#5.2), [5.3](requirements.md#5.3), [5.5](requirements.md#5.5)

- [ ] 23. Write tests for dawmans validate over the entry store <!-- id:f3stq0n -->
  - Validate parses, resolves and term-checks the whole store and reports, while modifying nothing: no index write, no shard, no ledger row, no embedding (5.4) - so it is unaffected by the cold model load either way.
  - A term-not-in-passage miss exits non-zero under validate only, and never under ingest (Decision 5): consequences where the author is present, none where the user is.
  - Blocked-by: f3stq0i (Implement TriageLoader.discover and the ingest wiring), f3stq0m (Implement the validation message rendering), f3stq0a (Implement terms.py)
  - Stream: 1
  - Requirements: [2.6](requirements.md#2.6), [5.4](requirements.md#5.4)

- [ ] 24. Implement the validate integration in cli.py <!-- id:f3stq0o -->
  - The existing dawmans validate gains the entry store; CorpusView and the ledger opened read-only on that path.
  - Blocked-by: f3stq0n (Write tests for dawmans validate over the entry store)
  - Stream: 1
  - Requirements: [2.6](requirements.md#2.6), [5.4](requirements.md#5.4)

- [ ] 25. Write tests for the coverage report <!-- id:f3stq0p -->
  - Rows: every entry with symptom, declared scope, cause count and whether every pointer currently resolves (6.1); every rejection and flag with its reason, covering 100% of the store (6.2); every rig device and software item no entry declares scope for (6.3); every cause permitted without a pointer with the undocumented device it names (6.4, fixture rig); every drift-flagged entry with the source that changed (8.6); every entry scoped only to a device removed from the rig, reported and never deleted (8.7).
  - No percentage anywhere - there is no denominator over symptoms, so the report is an inventory plus the one enumerable gap, the rig side.
  - dawmans coverage renders to stdout and the same rows land in the sidecar's report block, so the report is obtainable without asking a question (6.5) and published where a consumer can read it (6.6 - the publishing half; the consuming half closes when api/answer-engine or the UI names it).
  - Blocked-by: f3stq0k (Implement the sidecar assembly)
  - Stream: 1
  - Requirements: [6.1](requirements.md#6.1), [6.2](requirements.md#6.2), [6.3](requirements.md#6.3), [6.4](requirements.md#6.4), [6.5](requirements.md#6.5), [6.6](requirements.md#6.6), [8.6](requirements.md#8.6), [8.7](requirements.md#8.7)

- [ ] 26. Implement coverage.py and the cli coverage command <!-- id:f3stq0q -->
  - Blocked-by: f3stq0p (Write tests for the coverage report)
  - Stream: 1
  - Requirements: [6.1](requirements.md#6.1), [6.2](requirements.md#6.2), [6.3](requirements.md#6.3), [6.4](requirements.md#6.4), [6.5](requirements.md#6.5), [6.6](requirements.md#6.6), [8.6](requirements.md#8.6), [8.7](requirements.md#8.7)

## Phase 7: Starter set and acceptance

- [ ] 27. Write tests for the starter set <!-- id:f3stq0r -->
  - Each of the five entries satisfies sections 1-4 with no exemption (7.1) and carries the mandated causes: no sound from a track (Track Activator, solo, Monitor Off, Audio To, device chain - 7.2); a track is distorting, with the elimination step naming Saturator, Drum Buss, Overdrive, Vinyl Distortion, Dynamic Tube and Amp as an ordinary cause inside the 2-6 count (7.3); latency when monitoring (buffer size, direct monitoring, monitor mode, Overall Latency - 7.4); a drum pad triggers the wrong sound (transmitted note vs receive note, General MIDI mode, channel mismatch - 7.5); the controller does nothing (Track/Sync/Remote flags, control surface selection, bank position - 7.6).
  - Every fix cites a vendor passage with no 2.3 carve-out in use (7.8) - the direct-monitoring cause points into the Scarlett guide via scarlett_sections.json - and the term check passes over the committed section fixtures, including 7.3's `0 dB` against the section that prints it.
  - Blocked-by: f3stq0g (Implement TriageLoader.load emission), f3stq0a (Implement terms.py)
  - Stream: 1
  - Requirements: [7.1](requirements.md#7.1), [7.2](requirements.md#7.2), [7.3](requirements.md#7.3), [7.4](requirements.md#7.4), [7.5](requirements.md#7.5), [7.6](requirements.md#7.6), [7.8](requirements.md#7.8)

- [ ] 28. Author the five starter entries in triage/ <!-- id:f3stq0s -->
  - Product content that doubles as the grammar's worked examples; section numbers filled from the real index, since 2.2 rejects the whole entry at first ingest if a pointer does not resolve.
  - Blocked-by: f3stq0r (Write tests for the starter set)
  - Stream: 1
  - Requirements: [7.1](requirements.md#7.1), [7.2](requirements.md#7.2), [7.3](requirements.md#7.3), [7.4](requirements.md#7.4), [7.5](requirements.md#7.5), [7.6](requirements.md#7.6), [7.8](requirements.md#7.8)

- [ ] 29. Add the acceptance and timing targets <!-- id:f3stq0t -->
  - 7.7 asks each of the five starter symptoms with the starter set and vendor manuals in scope and asserts an outcome of answered, partially-answered or needs-narrowing, never refused-not-covered or out-of-domain. It needs the real manuals, a built index and the answer engine, so it is a make bench-style integration target that skips when index/ is absent or the answer engine is unavailable (api/answer-engine has no implementation or ledger yet) - the same honest limitation manual-corpus accepts for its 8.1.
  - 5.6: a synthetic 200-entry store ingests and validates in under 5 seconds with every pointer re-checked, measured warm; the cold deviation (the corpus's per-run model load) stands as designed until manual-corpus's lazy-load request lands, and is asserted as such rather than hidden in the budget.
  - Blocked-by: f3stq0o (Implement the validate integration in cli.py), f3stq0s (Author the five starter entries in triage/)
  - Stream: 1
  - Requirements: [5.6](requirements.md#5.6), [7.7](requirements.md#7.7)
