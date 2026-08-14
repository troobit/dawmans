// The conversation on screen (requirements 1.4–1.9, 1.12, 3.1, 9.15; design
// "Surfaces" and "The turn, client-side"). Submission goes through the scope
// store's block and the turn state machine; the turn lives in a fetch stream
// that has no relationship to window focus — nothing here listens to blur,
// focus or visibility (1.12).
//
// A class instance, not a bare `$state` export — a reassigned module-level
// `$state` is not reactive across the module boundary.

import { EngineRejection, submitQuestion, type TurnRequest } from '../engine/client';
import { turnEvents, UnknownStreamVersionError } from '../engine/sse';
import { Turn } from '../engine/turn.svelte';
import { history, type HistoryStore } from './history.svelte';
import { scope, type ScopeStore } from './scope.svelte';

/** 9.15: the limit api/answer-engine 9.12 enforces, enforced client-side first. */
export const QUESTION_LIMIT = 1000;

type ScopeLike = Pick<ScopeStore, 'canSubmit' | 'snapshot' | 'noteQuestionSubmitted'>;
type HistoryLike = Pick<HistoryStore, 'record'>;
type SubmitFn = (request: TurnRequest, signal?: AbortSignal) => Promise<Response>;

export class ThreadStore {
	/**
	 * The question being composed. Held here rather than in the input component
	 * so the router's manual insert (1.2), a re-edit from the thread (1.4) and
	 * a stop restoring the question (8.6) all reach the same text.
	 */
	draft = $state('');

	#turns = $state.raw<readonly Turn[]>([]);
	/**
	 * Decision 8: the engine issues no conversation id, so the thread mints its
	 * own after the first turn is accepted. The first turn of a thread carries
	 * null — the specced way to start a conversation — and every follow-up
	 * carries the one minted id.
	 */
	#conversationId: string | null = null;
	#controller: AbortController | null = null;
	readonly #failures = new WeakMap<Turn, unknown>();

	/** 1.6: the component focuses the emptied input when a turn settles. */
	onSettled: (() => void) | null = null;

	readonly #scope: ScopeLike;
	readonly #history: HistoryLike | null;
	readonly #submit: SubmitFn;

	constructor(deps: { scope: ScopeLike; history?: HistoryLike; submit?: SubmitFn }) {
		this.#scope = deps.scope;
		this.#history = deps.history ?? null;
		this.#submit = deps.submit ?? submitQuestion;
	}

	/** The turns on screen, oldest first. */
	get turns(): readonly Turn[] {
		return this.#turns;
	}

	/** The turn still being answered, if any. */
	get active(): Turn | null {
		const last = this.#turns.at(-1) ?? null;
		return last !== null && (last.state === 'acknowledged' || last.state === 'streaming')
			? last
			: null;
	}

	get busy(): boolean {
		return this.active !== null;
	}

	/** 1.7: a question asked while an exchange is on screen is a follow-up. */
	get isFollowUp(): boolean {
		return this.#turns.length > 0;
	}

	/** A settled narrowing question awaits its selection — the digits are its (6.3, Decision 5). */
	get awaitingNarrowing(): boolean {
		const last = this.#turns.at(-1);
		return last !== undefined && last.state === 'settled' && last.renderer === 'narrowing';
	}

	/** 9.15: over the client-enforced limit; the component states limit and length. */
	get overLimit(): boolean {
		return this.draft.length > QUESTION_LIMIT;
	}

	/** The transport failure behind a `failed` turn, for the error renderer (9.15, 9.19). */
	failureOf(turn: Turn): unknown {
		return this.#failures.get(turn);
	}

	/**
	 * Submit a question — the draft by default, or an explicit one (a symptom
	 * shortcut, a narrowing candidate). Guards in order: empty or whitespace
	 * does nothing and contacts no engine (1.5); zero scope blocks (3.1); over
	 * the limit blocks with the text preserved (9.15). The turn enters
	 * `acknowledged` synchronously, before any fetch, so the acknowledgement
	 * paint never waits on the network (8.7).
	 */
	submit(question?: string): Turn | null {
		const fromDraft = question === undefined;
		const text = question ?? this.draft;
		if (text.trim() === '') return null;
		if (!this.#scope.canSubmit) return null;
		if (text.length > QUESTION_LIMIT) return null;

		const turn = new Turn(text, this.#scope.snapshot());
		this.#turns = [...this.#turns, turn];
		if (fromDraft) this.draft = '';
		this.#scope.noteQuestionSubmitted();
		void this.#run(turn);
		return turn;
	}

	/** 1.9 / 8.6: stop generation, retaining whatever text arrived. */
	stop(): void {
		const turn = this.active;
		if (turn === null) return;
		turn.userCancelled = true;
		this.#controller?.abort();
	}

	/** 1.7: discard the thread; the next question is context-free. The draft survives. */
	clear(): void {
		const active = this.active;
		if (active !== null) {
			active.userCancelled = true;
			this.#controller?.abort();
		}
		this.#turns = [];
		this.#conversationId = null;
	}

	async #run(turn: Turn): Promise<void> {
		const controller = new AbortController();
		this.#controller = controller;
		try {
			const response = await this.#submit(
				{
					conversation_id: this.#conversationId,
					question: turn.question,
					sources: [...turn.scopeAtAsk]
				},
				controller.signal
			);
			if (this.#conversationId === null) this.#conversationId = crypto.randomUUID();
			await turn.consume(turnEvents(response));
		} catch (error) {
			if (turn.userCancelled) {
				// 8.6: the client knows who cancelled — the engine does not (9.16).
				// The turn ends as cancelled with everything that arrived retained.
				turn.applyEvent({ event: 'outcome', data: JSON.stringify({ outcome: 'cancelled' }) });
				turn.applyEvent({ event: 'done', data: '{}' });
			} else {
				// A request rejection (9.15) or unknown stream version (9.19)
				// describes no turn and synthesises no outcome; any other
				// transport failure mid-stream is `incomplete` (9.14).
				this.#failures.set(turn, error);
				const rejection =
					error instanceof EngineRejection || error instanceof UnknownStreamVersionError;
				if (!rejection && turn.envelope.outcome === undefined) {
					turn.applyEvent({ event: 'outcome', data: JSON.stringify({ outcome: 'incomplete' }) });
				}
				turn.applyEvent({ event: 'done', data: '{}' }); // flush what arrived
				turn.state = 'failed';
			}
		}
		if (this.#controller === controller) this.#controller = null;
		this.#history?.record(turn);
		if (turn.state === 'settled' && turn.envelope.outcome !== 'cancelled') {
			this.onSettled?.();
		}
	}
}

/** The one thread on the surface. */
export const thread = new ThreadStore({ scope, history });
