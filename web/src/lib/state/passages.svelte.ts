// The session passage cache (requirements 5.6, 5.11, 5.18; design
// "Citations"). Components fetch nothing themselves — expansion and the
// focus prefetch go through this store, which is what keeps 5.18's cache-hit
// path observable. A passage's text cannot change without a re-ingestion,
// which changes its `passage_id`, so a `ready` entry is valid for the whole
// session and is never refetched.
//
// A class instance holding `$state` fields: a reassigned module-level
// `$state` is not reactive across the module boundary.

import { fetchPassage } from '../engine/client';
import type { Passage } from '../engine/records';

export type PassageState =
	| { status: 'loading' }
	| { status: 'ready'; passage: Passage }
	/** 5.11: the citation keeps its location and its open action; only the body reports unavailable. */
	| { status: 'failed' };

type PassageFetcher = (passageId: string) => Promise<Passage>;

export class PassageStore {
	#entries = $state.raw<ReadonlyMap<string, PassageState>>(new Map());
	readonly #fetch: PassageFetcher;

	constructor(fetcher: PassageFetcher = fetchPassage) {
		this.#fetch = fetcher;
	}

	get(passageId: string): PassageState | undefined {
		return this.#entries.get(passageId);
	}

	/**
	 * Start fetching a passage unless it is already cached or in flight. Called
	 * on focus (never hover, 1.12) and on expansion; a failed entry retries on
	 * the next call, so a citation activated after an outage recovers.
	 */
	prefetch(passageId: string): void {
		const current = this.#entries.get(passageId);
		if (current !== undefined && current.status !== 'failed') return;
		this.#set(passageId, { status: 'loading' });
		this.#fetch(passageId).then(
			(passage) => this.#set(passageId, { status: 'ready', passage }),
			() => this.#set(passageId, { status: 'failed' })
		);
	}

	#set(passageId: string, state: PassageState): void {
		this.#entries = new Map(this.#entries).set(passageId, state);
	}
}

/** The one passage cache on the surface. */
export const passages = new PassageStore();
