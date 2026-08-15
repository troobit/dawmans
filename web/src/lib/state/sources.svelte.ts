// Available sources plus both gap reports (requirements 2.1, 2.3, 2.9, 2.10,
// 9.13; design "The source picker" and "Error Handling"). Everything this
// surface knows about sources arrives through GET /sources — no fixed count
// anywhere, and an added or removed source of either kind is reflected on the
// next load with no change to the interface.
//
// A class instance, not a bare `$state` export — a reassigned module-level
// `$state` is not reactive across the module boundary.

import { listSources } from '../engine/client';
import type { RequiredDevice, SourceRecord, SourceRef } from '../engine/records';

/**
 * `engine-unreachable` is GET /sources failing — the picker reports it and
 * submission is blocked; it never renders as an empty picker. `corpus-empty`
 * is the engine answering that nothing is ingested (9.13) — a different
 * subject, though it too disables submission until a source is reported.
 */
export type SourcesState = 'loading' | 'ready' | 'engine-unreachable' | 'corpus-empty';

export class SourcesStore {
	#state = $state<SourcesState>('loading');
	#sources = $state.raw<SourceRecord[]>([]);
	#ownedUndocumented = $state.raw<RequiredDevice[]>([]);
	#documentedUnconfirmed = $state.raw<SourceRef[]>([]);

	get state(): SourcesState {
		return this.#state;
	}

	/** Every reported source, of both kinds, in the engine's order (2.1, 2.12). */
	get sources(): readonly SourceRecord[] {
		return this.#sources;
	}

	/**
	 * 2.9: hardware the user owns with no ingested manual — the known-gaps
	 * group, never selectable. Empty is the live case (CONTRACTS §5); the
	 * populated path renders from the payload, never from a constant.
	 */
	get ownedUndocumented(): readonly RequiredDevice[] {
		return this.#ownedUndocumented;
	}

	/** 2.10: sources whose `hardware_applicability` is assumed, as the engine reports them. */
	get documentedUnconfirmed(): readonly SourceRef[] {
		return this.#documentedUnconfirmed;
	}

	/** The id list that feeds the scope store's load (3.7, 3.8, 2.4). */
	get ids(): string[] {
		return this.#sources.map((source) => source.source_id);
	}

	/** Anything short of a ready source list blocks submission (9.13). */
	get blocksSubmission(): boolean {
		return this.#state !== 'ready';
	}

	/** The engine-reported name for the scope indicator (2.6, 3.3). */
	displayName(id: string): string | undefined {
		return this.#sources.find((source) => source.source_id === id)?.display_name;
	}

	/**
	 * Fetch the source list. A failure — network or non-OK — is the
	 * engine-unreachable state, distinct from the engine answering that the
	 * corpus is empty; the store never conflates the two (9.13).
	 */
	async load(): Promise<void> {
		try {
			const response = await listSources();
			this.#sources = response.sources;
			this.#ownedUndocumented = response.owned_undocumented;
			this.#documentedUnconfirmed = response.documented_unconfirmed;
			this.#state = response.sources.length === 0 ? 'corpus-empty' : 'ready';
		} catch {
			this.#state = 'engine-unreachable';
		}
	}
}

/** The one source list on the surface. */
export const sources = new SourcesStore();
