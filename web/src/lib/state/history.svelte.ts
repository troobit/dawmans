// The persisted exchange store (requirements 12.1, 12.7, 12.9; design
// "History"). localStorage, read lazily when the panel first opens — parsing
// 50 exchanges on boot would come out of 8.7's acknowledgement budget for
// nothing on screen at rest. Written on settle, trimmed to the most recent 50;
// a QuotaExceededError drops oldest entries until the write succeeds rather
// than failing the turn.

import type { AnswerEnvelope, Citation } from '../engine/records';
import type { Turn } from '../engine/turn.svelte';

export const HISTORY_STORAGE_KEY = 'dawmans.history';

/** 12.9's target retention depth (band 20–100). */
const RETENTION = 50;

/**
 * One retained exchange, newest first in storage. Citation records only —
 * never passage text, which is refetched on demand and would otherwise
 * dominate the quota.
 */
export type HistoryEntry = {
	question: string;
	envelope: Partial<AnswerEnvelope>;
	citations: Citation[];
	scopeAtAsk: string[];
	askedAt: number;
	/**
	 * 6.7: the thread the exchange belongs to (the client-minted conversation
	 * id, Decision 8) — what lets a narrowing exchange be retained as part of
	 * its thread rather than as a standalone unanswered question.
	 */
	thread?: string;
	/** 12.7: a partial retained under 9.14, never presented as a finished answer. */
	incomplete?: boolean;
};

export class HistoryStore {
	// The cache is a plain field so the lazy read inside the getter mutates no
	// reactive state during render; `#version` is the reactive signal, bumped
	// only from `record()`, which runs in stream handlers.
	#cache: HistoryEntry[] | null = null;
	#version = $state(0);

	/** Retained exchanges, newest first. The first access performs the read (12.1). */
	get entries(): readonly HistoryEntry[] {
		void this.#version;
		if (this.#cache === null) this.#cache = this.#read();
		return this.#cache;
	}

	/**
	 * Retain a finished turn (12.1). Cancelled and failed exchanges are not
	 * retained as answers; a partial retained under 9.14 is marked incomplete
	 * (12.7). Never throws — a full store must not fail the turn.
	 */
	record(turn: Turn, thread?: string | null): void {
		if (turn.userCancelled) return;
		if (turn.envelope.outcome === 'cancelled') return;
		if (turn.renderer === 'error' || turn.renderer === 'broken' || turn.renderer === 'empty-scope')
			return;
		if (turn.state !== 'settled' && turn.state !== 'failed') return;

		const entry: HistoryEntry = {
			question: turn.question,
			envelope: turn.envelope,
			citations: [...turn.citations.values()],
			scopeAtAsk: [...turn.scopeAtAsk],
			askedAt: Date.now(),
			...(thread != null ? { thread } : {}),
			...(turn.incomplete ? { incomplete: true } : {})
		};
		this.#cache = [entry, ...this.entries].slice(0, RETENTION);
		this.#version += 1;
		this.#persist();
	}

	/** 12.6: the entire history in one action; the confirmation step is the panel's. */
	clear(): void {
		this.#cache = [];
		this.#version += 1;
		localStorage.removeItem(HISTORY_STORAGE_KEY);
	}

	#read(): HistoryEntry[] {
		const raw = localStorage.getItem(HISTORY_STORAGE_KEY);
		if (raw === null) return [];
		try {
			const parsed: unknown = JSON.parse(raw);
			return Array.isArray(parsed) ? (parsed as HistoryEntry[]) : [];
		} catch {
			return []; // Corrupt is the same as never stored.
		}
	}

	#persist(): void {
		let entries = this.#cache ?? [];
		for (;;) {
			try {
				localStorage.setItem(HISTORY_STORAGE_KEY, JSON.stringify(entries));
				return;
			} catch {
				// QuotaExceededError: drop the oldest entry and try again; where
				// storage never accepts the write, give up rather than fail the turn.
				if (entries.length === 0) return;
				entries = entries.slice(0, -1);
			}
		}
	}
}

/** The one history on the surface. */
export const history = new HistoryStore();
