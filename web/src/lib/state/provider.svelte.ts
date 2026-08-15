// Provider status and configuration (requirements §10; design "Provider
// configuration"). The store renders only what GET /provider reports — the
// engine's status, never the browser's stored settings (10.7) — and holds the
// one piece of state that is legitimately local: the shared-backend disclosure
// acknowledgement, stored against the backend's identity so that changing
// backend re-arms it (10.4).
//
// A class instance, not a bare `$state` export — a reassigned module-level
// `$state` is not reactive across the module boundary.

import {
	clearCredential,
	getProviderStatus,
	setCredential,
	setProvider,
	testProvider,
	type ProviderStatus,
	type ProviderTest
} from '../engine/client';

export const DISCLOSURE_ACK_KEY = 'dawmans.disclosure-ack';

/** `unreachable` is GET /provider failing — a transport state, not a §6 outcome. */
export type ProviderState = 'loading' | 'ready' | 'unreachable';

export class ProviderStore {
	#state = $state<ProviderState>('loading');
	#status = $state.raw<ProviderStatus | null>(null);
	// Bumped on acknowledge so `disclosureAcknowledged` re-reads localStorage.
	#ackVersion = $state(0);

	get state(): ProviderState {
		return this.#state;
	}

	/** The engine's reported status — the only thing 10.7 lets the indication render. */
	get status(): ProviderStatus | null {
		return this.#status;
	}

	/**
	 * What the disclosure acknowledgement is stored against (10.4): the backend
	 * the engine reports, not a constant — changing backend changes the identity.
	 */
	get backendIdentity(): string | null {
		if (this.#status?.kind == null) return null;
		return `${this.#status.kind}:${this.#status.model ?? ''}`;
	}

	get disclosureAcknowledged(): boolean {
		void this.#ackVersion;
		const identity = this.backendIdentity;
		return identity !== null && localStorage.getItem(DISCLOSURE_ACK_KEY) === identity;
	}

	/** 10.4: record the explicit acknowledgement against the current backend. */
	acknowledgeDisclosure(): void {
		const identity = this.backendIdentity;
		if (identity === null) return;
		localStorage.setItem(DISCLOSURE_ACK_KEY, identity);
		this.#ackVersion += 1;
	}

	/**
	 * 10.4: the first turn is blocked while the shared backend's disclosure is
	 * unacknowledged. Never true for a keyed hosted or local provider.
	 */
	get blocksFirstTurn(): boolean {
		return this.#status?.kind === 'shared-backend' && !this.disclosureAcknowledged;
	}

	/** get-provider-status. A failure is the engine unreachable, not a status. */
	async load(): Promise<void> {
		try {
			this.#status = await getProviderStatus();
			this.#state = 'ready';
		} catch {
			this.#state = 'unreachable';
		}
	}

	/** set-provider: kind first, model or endpoint where the kind takes one (10.1, 10.3). */
	async choose(kind: string, model?: string): Promise<void> {
		this.#status = await setProvider({ kind, ...(model !== undefined ? { model } : {}) });
	}

	/** set-credential: the key travels only in this operation's body (10.9). */
	async saveCredential(key: string): Promise<void> {
		this.#status = await setCredential(key);
	}

	/** clear-credential: effective on the next submission (10.8). */
	async clearKey(): Promise<void> {
		this.#status = await clearCredential();
	}

	/** test-provider: reachable as configured, no credential echoed (10.10). */
	test(): Promise<ProviderTest> {
		return testProvider();
	}
}

/** The one provider status on the surface. */
export const provider = new ProviderStore();
