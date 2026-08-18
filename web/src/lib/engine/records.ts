// CONTRACTS §1–§4e and §6/§6a as types — the only place in this surface they are
// written down. No field added, none dropped. Optionality follows the contract's
// own rules, and absent is absent: never empty string, zero, or an empty array
// standing in for "nothing" — an empty `suggested_sources[]` would claim the
// engine looked and found nothing, a different claim from making no suggestion.
// The one deliberate exception is `Cause.fix_cites[]`, whose empty array is a
// meaning §4c assigns ("the entry names no fix").

/** §4a. A source's kind changes what it is trusted for, never how it is cited. */
export type SourceKind = 'vendor-manual' | 'authored-triage';

/**
 * §1/§5. Which hardware the source describes, and whether that is declared
 * (`confirmed`) or defaulted from the filename (`assumed`). On the
 * `authored-triage` source the status is fixed at `assumed` and no device is
 * carried — applicability varies per entry, not per store.
 */
export type HardwareApplicability = {
	device?: string;
	status: 'confirmed' | 'assumed';
};

type SourceRecordCommon = {
	source_id: string;
	display_name: string;
	hardware_applicability: HardwareApplicability;
	/** Inventory only (§1): reported, not required to reach any other surface. */
	ingested_at: string;
	/** Inventory only (§1). */
	chunk_count: number;
};

/**
 * §1. The five filename fields reconstruct the manual's filename under
 * DECISIONS Decision 2's grammar (`doc_version` captured without the leading
 * `v`); no filesystem path ever appears on the record.
 */
export type VendorManualSourceRecord = SourceRecordCommon & {
	kind: 'vendor-manual';
	vendor: string;
	product: string;
	doctype: string;
	lang: string;
	doc_version: string;
	page_count: number;
	/** Text layer present but sparse; ingested, not rejected. Picker marking only. */
	low_text: boolean;
};

/**
 * §1. The store, not a document: `source_id` is the constant
 * `authored/triage`, and none of the filename fields apply.
 */
export type AuthoredTriageSourceRecord = SourceRecordCommon & {
	kind: 'authored-triage';
};

/** §1. One per ingested source, of either kind. */
export type SourceRecord = VendorManualSourceRecord | AuthoredTriageSourceRecord;

/**
 * §2. The unit of retrieval and of citation. `passage_id` is content-derived
 * and stable across re-ingestion; `entry_location` never contributes to it.
 */
export type Passage = {
	passage_id: string;
	source_id: string;
	/** Absent where the document has no numbering, and on a pageless source; never invented. */
	section_number?: string;
	section_title: string;
	/** Absent on a pageless (`authored-triage`) source; never synthesised. */
	page_start?: number;
	page_end?: number;
	text: string;
	/** Contains characters that could not be repaired. */
	degraded: boolean;
	/** The chunk contains figures — the sole offset for a text-only index. */
	has_figures: boolean;
	/**
	 * Triage-owned (§2): an authored cause resting on no vendor-manual passage.
	 * `authored-triage` only.
	 */
	unbacked?: boolean;
	/**
	 * Where the entry is written: one opaque display string `<path>:<line>`.
	 * `authored-triage` only; nothing may key on it.
	 */
	entry_location?: string;
};

type CitationCommon = {
	source_id: string;
	display_name: string;
	/** Backs passage expansion and both open-at-source mechanisms of §3a. */
	passage_id: string;
	section_title: string;
	/** §3: shown inline where applicability is assumed rather than confirmed. */
	hardware_applicability: HardwareApplicability;
	/** Expanded passage marked as containing unreadable characters. */
	degraded: boolean;
	/** Shown as "figure on pN". */
	has_figures: boolean;
	/** §3: shown inline on any cause resting on no manual passage. */
	unbacked?: boolean;
	section_number?: string;
};

/** §3. `doc_version` shown inline is the mk1/mk2 mitigation; it fails if hidden. */
export type VendorManualCitation = CitationCommon & {
	kind: 'vendor-manual';
	doc_version: string;
	/** The open-at-source target: the served PDF at fragment `#page=N` and nothing else (§3a). */
	page: number;
};

/**
 * §3. Pageless: page and section render as absent — never invented — with the
 * entry's symptom title occupying the location slot. `entry_location` is the
 * slot's companion, not its replacement, and is copyable in one activation (§3a).
 */
export type AuthoredTriageCitation = CitationCommon & {
	kind: 'authored-triage';
	entry_location: string;
};

/** §3. Every field is rendered or actionable; nothing on this record may dead-end. */
export type Citation = VendorManualCitation | AuthoredTriageCitation;

/**
 * §6. The complete outcome taxonomy — 17 members, closed against private growth.
 * The renderer is a total function over this union, so an added member fails
 * the type check rather than at runtime.
 */
export type Outcome =
	| 'answered'
	| 'partially-answered'
	| 'needs-narrowing'
	| 'ranked-causes'
	| 'refused-not-covered'
	| 'out-of-domain'
	| 'no-manual-for-device'
	| 'no-sources-selected'
	| 'unknown-source-id'
	| 'corpus-empty'
	| 'provider-unconfigured'
	| 'provider-unreachable'
	| 'provider-rate-limited'
	| 'provider-error'
	| 'timeout'
	| 'incomplete'
	| 'cancelled';

/**
 * §6a. A closed machine sub-code refining `outcome`, scoped to the outcomes it
 * may accompany; never displayed as prose — it selects which sentence and which
 * control the consumer renders.
 */
export type Reason =
	// provider-unconfigured
	| 'no-provider-kind'
	| 'missing-credential'
	| 'disclosure-unacknowledged'
	// provider-error
	| 'authentication-failed'
	| 'provider-rejected';

/**
 * §4c. A member of `causes[]`: a finding to read, not a candidate the user
 * picks between — the distinction that keeps it apart from `narrowing`.
 */
export type Cause = {
	/** 1-based, always present, equal to this record's position in `causes[]`. */
	rank: number;
	statement: string;
	/** The observable that would confirm or eliminate it — what the user looks at. */
	check: string;
	/** One or more `passage_id`, resolving into the envelope's `citations[]`. */
	cites: string[];
	/**
	 * `passage_id` for the vendor-manual fix. Empty — a meaning, not a claim of
	 * absence — where the entry names no fix, the cause is `unbacked`, or the fix
	 * passage lies outside the turn's selected scope.
	 */
	fix_cites: string[];
};

/**
 * §4. One selectable candidate. The engine builds these from the triage entry's
 * causes rather than from model output (`api/answer-engine` decision_log
 * Decision 9): `label` is the cause's `check` — an observable the user can look
 * at, and so the text of the control — and `value` is the cause `statement`,
 * which is what a selection submits as the follow-up question. The two are not
 * interchangeable, and a candidate is not a bare string.
 */
export type NarrowingCandidate = {
	label: string;
	value: string;
};

/** §4. A question plus 2–4 candidates, each selectable in one activation. `needs-narrowing` only. */
export type Narrowing = {
	question: string;
	candidates: NarrowingCandidate[];
};

/** §4/§4b. An addressable source reference, never a substring of prose. */
export type SourceRef = {
	source_id: string;
	display_name: string;
};

/** §4. The device whose documentation would answer it. `no-manual-for-device` only. */
export type RequiredDevice = {
	device: string;
	display_name: string;
};

/**
 * §4e. The filename to add to `manuals/`, assembled by the engine; a field the
 * engine cannot know is written as its named placeholder inside the string.
 * Dormant today, still implemented: an empty set, not a removed member.
 */
export type RequiredManual = {
	filename: string;
	/** The fields left as placeholders; empty where the name is complete. */
	placeholders: string[];
};

/** §4. Whether the provider's output conformed to the engine's declared answer format. */
export type Framing = 'parsed' | 'unparsed';

/**
 * §4. Per-stage durations, and nothing else. `corpus_reload_ms` is a run-level
 * timing, not a stage of the turn.
 */
export type Timings = {
	retrieval_ms: number;
	state_acquisition_ms: number;
	engine_overhead_ms: number;
	first_token_ms: number;
	completion_ms: number;
	corpus_reload_ms?: number;
};

/**
 * §4. The envelope a conforming consumer has accumulated when the turn stream
 * ends. Applicability of each optional member is scoped to particular outcomes
 * by the contract's prose; a field present on an outcome its row does not
 * permit is a defect in the producer, never licence to render it.
 */
export type AnswerEnvelope = {
	outcome: Outcome;
	/** The actionable answer, first, before qualification. On `ranked-causes`, the rank-1 cause's `check` stated as an instruction. */
	direct_answer?: string;
	/** An ordered sequence of typed blocks drawn from the closed set of §4d. */
	body?: string;
	/** The turn's one citation channel: everything else that cites resolves into it by `passage_id`. */
	citations?: Citation[];
	/** Which selected sources actually supplied passages, as `source_id`. */
	contributing_sources?: string[];
	/** Named parts of the question the sources did not cover; subordinate to the answer, not a refusal. */
	uncovered_parts?: string[];
	/** At most 3 unselected indexed sources, ordered by likelihood. Absent — never empty-as-a-claim. */
	suggested_sources?: SourceRef[];
	/** `needs-narrowing` only. */
	narrowing?: Narrowing;
	/** The terminal ranked cause list, ordered, at most 4. `ranked-causes` only. */
	causes?: Cause[];
	/** `no-manual-for-device` only. */
	required_device?: RequiredDevice;
	/** `no-manual-for-device` only, and absent where the device did not resolve to a canonical id (§4e). */
	required_manual?: RequiredManual;
	/** Sources the engine removed from this conversation's carried scope at turn time. Rendered with the turn; absent where none was dropped. */
	scope_dropped?: SourceRef[];
	/** §6a. Absent where §6a permits none. */
	reason?: Reason;
	/** Seconds, unrounded, as the provider stated it. `provider-rate-limited` only, and absent there where the provider stated none. */
	retry_after?: number;
	/** The engine's own wording for this occurrence; unparsed by contract, rendered only behind the 9.3 disclosure. */
	detail?: string;
	framing?: Framing;
	/** Set after streaming completes; marks an already-rendered answer, never withholds it. */
	ungrounded?: true;
	timings?: Timings;
};

/**
 * §4b. The turn stream's sixteen governed events. Every event carries a §3 or
 * §4 field, `done` excepted; the rendering obligation lives on the field in §4.
 * An unknown event name is ignored; an unknown `outcome` renders broken; an
 * unknown body block keeps its text and loses only its wrapper.
 */
export type TurnEvent =
	| { event: 'scope_dropped'; data: SourceRef[] }
	| {
			event: 'outcome';
			data: { outcome: Outcome; reason?: Reason; retry_after?: number; detail?: string };
	  }
	| { event: 'direct_answer'; data: { text: string } }
	| { event: 'body_delta'; data: { text: string } }
	| { event: 'citation'; data: Citation }
	| { event: 'cause'; data: Cause }
	| { event: 'contributing_sources'; data: { sources: string[] } }
	| { event: 'uncovered_parts'; data: { parts: string[] } }
	| { event: 'suggested_sources'; data: SourceRef[] }
	| { event: 'narrowing'; data: Narrowing }
	| { event: 'required_device'; data: RequiredDevice }
	| { event: 'required_manual'; data: RequiredManual }
	| { event: 'ungrounded'; data: { ungrounded: true } }
	| { event: 'framing'; data: { framing: Framing } }
	| { event: 'timings'; data: Timings }
	/** A payload is required: a data-less SSE event is never dispatched, so a bare `done` may legally vanish. */
	| { event: 'done'; data: { complete: true } };

/**
 * §4d. The closed block set of `body`, each decidable from its first line at
 * column 0 — which is what lets the renderer fix a block's type before painting
 * it and never re-type or re-flow it afterwards.
 */
export type BlockType =
	| 'heading' // `## `
	| 'ordered-step' // `N. `
	| 'bullet' // `- `
	| 'paragraph' // anything else, blank-line separated
	| 'caveat' // `!caveat ` — rendered in reading order, never behind a disclosure
	| 'conflict'; // `!conflict ` — two readings, neither chosen for the user

/**
 * §4b. Declared by the submit-question response before the first body byte; a
 * consumer that does not know the declared version refuses the turn (ui 9.19).
 */
export const TURN_STREAM_VERSION = 'dawmans/turn-stream/1';
