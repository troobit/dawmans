// The event → Turn reducer (design "SSE framing and the turn reducer" and
// "The turn, client-side"). Append-only: it fills `Partial<AnswerEnvelope>` as
// CONTRACTS §4b's sixteen events arrive, holds the citation map keyed by
// `passage_id` and the marker order list, and never amends what is painted.
//
// Three unknown-member rules, deliberately different (CONTRACTS §4b): an
// unknown event name is ignored and never fails the turn; an unknown outcome
// renders as a broken state carrying `detail` (9.4); an unknown body block
// keeps its text and loses only its wrapper (blocks.ts).
//
// A class instance holding `$state` fields: a reassigned module-level `$state`
// is not reactive across the module boundary.

import { markFirstByte, type TurnMarks } from '../state/perf.svelte';
import { BlockParser, type Block } from './blocks';
import type { AnswerEnvelope, Citation, Outcome, TurnEvent } from './records';
import type { SseFrame, StreamEnd } from './sse';

/**
 * `acknowledged` is entered synchronously in the submit handler, before fetch
 * is called, so the acknowledgement paint never waits on the network (8.7).
 * `streaming` begins on the first SSE event of any kind. `failed` is a stream
 * that ended without `done` — never a settled turn (9.14).
 */
export type TurnState = 'acknowledged' | 'streaming' | 'settled' | 'failed';

/** The renderer families of the design's outcome table. `broken` is 9.4's unknown-outcome state. */
export type TurnRenderer =
	| 'answer'
	| 'narrowing'
	| 'ranked-causes'
	| 'coverage-failure'
	| 'empty-scope'
	| 'error'
	| 'cancelled'
	| 'broken';

/**
 * Every outcome in CONTRACTS §6 maps to exactly one renderer, as a total
 * function: adding a member to the union without a row here fails the type
 * check rather than at runtime (9.4).
 */
export const RENDERER_FOR_OUTCOME: Record<Outcome, TurnRenderer> = {
	answered: 'answer',
	'partially-answered': 'answer',
	'needs-narrowing': 'narrowing',
	'ranked-causes': 'ranked-causes',
	'refused-not-covered': 'coverage-failure',
	'out-of-domain': 'coverage-failure',
	'no-manual-for-device': 'coverage-failure',
	'no-sources-selected': 'empty-scope',
	'unknown-source-id': 'error',
	'corpus-empty': 'error',
	'provider-unconfigured': 'error',
	'provider-unreachable': 'error',
	'provider-rate-limited': 'error',
	'provider-error': 'error',
	timeout: 'error',
	incomplete: 'answer',
	cancelled: 'cancelled'
};

/** Total over the union; an outcome the engine cannot emit renders broken (9.4). */
export function rendererFor(outcome: Outcome | (string & {})): TurnRenderer {
	return RENDERER_FOR_OUTCOME[outcome as Outcome] ?? 'broken';
}

/**
 * One rendering path per governed event: the mapped type ranges over
 * CONTRACTS §4b's event set, so an event added to records.ts without a
 * handler fails the type check — the consumer-side half of §4b's join rule.
 */
type Handlers = {
	[E in TurnEvent as E['event']]: (turn: Turn, data: E['data']) => void;
};

export class Turn {
	readonly question: string;
	/** A detached copy: scope changes mid-answer touch only the next turn (3.9). */
	readonly scopeAtAsk: readonly string[];
	/**
	 * Per-turn marks for 8.7–8.9 and the 9.3 disclosure; `submit` is stamped at
	 * construction, in the submit handler. Reactive so the working indicator can
	 * leave the moment first content exists and the disclosure never shows stale
	 * marks (perf.svelte.ts stamps the rest).
	 */
	marks: TurnMarks = $state({ submit: 0 });

	state = $state<TurnState>('acknowledged');
	/** Fixed by the `outcome` event before the first word paints; null while unknown. */
	renderer = $state<TurnRenderer | null>(null);
	envelope = $state.raw<Partial<AnswerEnvelope>>({});
	blocks = $state.raw<readonly Block[]>([]);
	/** The turn's one citation channel, keyed by passage_id (CONTRACTS §4c). */
	citations = $state.raw<ReadonlyMap<string, Citation>>(new Map());
	/** passage_id in order of first appearance; a marker's printed integer is its position + 1. */
	markers = $state.raw<readonly string[]>([]);
	/** Set by the cancel control (1.9): the client knows who cancelled, the engine does not (9.16). */
	userCancelled = false;

	readonly #parser: BlockParser;

	constructor(question: string, scopeAtAsk: readonly string[]) {
		this.question = question;
		this.scopeAtAsk = [...scopeAtAsk];
		this.marks.submit = performance.now();
		this.#parser = new BlockParser((passageId) => this.#assignMarker(passageId));
	}

	/** 9.14: the stream ended without `done` — partial, never finished. */
	get incomplete(): boolean {
		return this.state === 'failed' || this.envelope.outcome === 'incomplete';
	}

	/** 5.12: a settled answer with no citations is uncited. Not a claim before settling. */
	get uncited(): boolean {
		return this.state === 'settled' && this.citations.size === 0;
	}

	/** The printed integer for a passage_id, stable from first appearance (Decision 3). */
	markerIndex(passageId: string): number | undefined {
		const index = this.markers.indexOf(passageId);
		return index === -1 ? undefined : index + 1;
	}

	/**
	 * Apply one dispatched frame. An event name outside CONTRACTS §4b is
	 * ignored and never fails the turn; a payload that does not parse carries
	 * nothing a consumer could salvage and is ignored the same way.
	 */
	applyEvent(frame: SseFrame): void {
		if (this.state === 'acknowledged') this.state = 'streaming';
		const handler = (HANDLERS as Record<string, (turn: Turn, data: unknown) => void>)[frame.event];
		if (handler === undefined) return;
		let data: unknown;
		try {
			data = JSON.parse(frame.data);
		} catch {
			return;
		}
		handler(this, data);
	}

	/**
	 * Drain a turn's event stream into this turn. End of stream without `done`
	 * is a defined failure: the partial text is retained and marked, never
	 * presented as settled (9.14). Transport errors — including the unknown
	 * stream version refusal of 9.19 — propagate to the caller.
	 */
	async consume(events: AsyncGenerator<SseFrame, StreamEnd>): Promise<void> {
		let end: StreamEnd;
		for (;;) {
			const next = await events.next();
			if (next.done === true) {
				end = next.value;
				break;
			}
			this.applyEvent(next.value);
		}
		if (!end.complete && this.state !== 'settled') {
			this.#flushBlocks();
			this.state = 'failed';
			if (this.envelope.outcome === undefined) {
				this.envelope = { ...this.envelope, outcome: 'incomplete' };
				this.renderer = RENDERER_FOR_OUTCOME.incomplete;
			}
		}
	}

	#assignMarker(passageId: string): number {
		const existing = this.markers.indexOf(passageId);
		if (existing !== -1) return existing + 1;
		this.markers = [...this.markers, passageId];
		return this.markers.length;
	}

	#appendBody(text: string): void {
		this.#parser.append(text);
		this.envelope = { ...this.envelope, body: (this.envelope.body ?? '') + text };
		this.#snapshotBlocks();
	}

	#flushBlocks(): void {
		this.#parser.end();
		this.#snapshotBlocks();
	}

	/**
	 * Replace by append, never mutate in place: blocks are `$state.raw`
	 * (design, Data Models). The parser streams into its last block until that
	 * block closes, so the last block is the one whose contents may differ from
	 * the previous snapshot — it is cloned to a fresh reference or the renderer,
	 * comparing referentially, would never repaint the growing block (4.1).
	 * Every earlier block is closed and final, and keeps its reference.
	 */
	#snapshotBlocks(): void {
		const parsed = this.#parser.blocks;
		const last = parsed[parsed.length - 1];
		this.blocks = last === undefined ? [] : [...parsed.slice(0, -1), structuredClone(last)];
	}

	#merge(fields: Partial<AnswerEnvelope>): void {
		this.envelope = { ...this.envelope, ...fields };
	}

	// One handler per CONTRACTS §4b event; the `Handlers` mapped type is what
	// makes the coverage total at compile time. Static so the handlers reach
	// the class's private members.
	static readonly handlers: Handlers = {
		scope_dropped: (turn, data) => turn.#merge({ scope_dropped: data }),
		outcome: (turn, data) => {
			// reason, retry_after and detail travel with the outcome, so an
			// error state paints once rather than being amended.
			turn.#merge({
				outcome: data.outcome,
				...(data.reason !== undefined ? { reason: data.reason } : {}),
				...(data.retry_after !== undefined ? { retry_after: data.retry_after } : {}),
				...(data.detail !== undefined ? { detail: data.detail } : {})
			});
			turn.renderer = rendererFor(data.outcome);
		},
		direct_answer: (turn, data) => {
			// The first content event: the 8.8/8.9 measurement lands here.
			markFirstByte(turn.marks);
			turn.#merge({ direct_answer: data.text });
		},
		body_delta: (turn, data) => {
			markFirstByte(turn.marks);
			turn.#appendBody(data.text);
		},
		citation: (turn, data) => {
			turn.citations = new Map(turn.citations).set(data.passage_id, data);
		},
		cause: (turn, data) => turn.#merge({ causes: [...(turn.envelope.causes ?? []), data] }),
		contributing_sources: (turn, data) => turn.#merge({ contributing_sources: data.sources }),
		uncovered_parts: (turn, data) => turn.#merge({ uncovered_parts: data.parts }),
		suggested_sources: (turn, data) => turn.#merge({ suggested_sources: data }),
		narrowing: (turn, data) => turn.#merge({ narrowing: data }),
		required_device: (turn, data) => turn.#merge({ required_device: data }),
		required_manual: (turn, data) => turn.#merge({ required_manual: data }),
		// 5.13: marks text already on screen; the painted blocks are untouched.
		ungrounded: (turn) => turn.#merge({ ungrounded: true }),
		framing: (turn, data) => turn.#merge({ framing: data.framing }),
		timings: (turn, data) => turn.#merge({ timings: data }),
		done: (turn) => {
			turn.#flushBlocks();
			turn.state = 'settled';
		}
	};
}

const HANDLERS = Turn.handlers;
