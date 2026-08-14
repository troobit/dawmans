// Scope selection, persistence and decay (requirements §3; design "Scope
// state, persistence and decay"; decision_log Decision 4).
//
// A class instance, not a bare `$state` export: a reassigned module-level
// `$state` is not reactive across the module boundary, because the compiler
// rewrites references per file. Class fields declared `$state` survive it.

export const SCOPE_STORAGE_KEY = 'dawmans.scope';
export const SESSION_MARKER_KEY = 'dawmans.session';

/** 3.6's second clause: a load more than 8 hours after the last submitted question. */
const EIGHT_HOURS_MS = 8 * 60 * 60 * 1000;

/**
 * The persisted record. `known` is the available-source list at the time the
 * scope was last persisted; it decides whether a stored scope "was all
 * available sources" when a new source appears (2.4). `seen` cannot decide
 * that — it updates only on submit, so a narrowing made before any question
 * would read as "everything is new" and be silently widened on reload,
 * breaching 3.5.
 */
type StoredScope = {
	selected: string[];
	seen: string[];
	known: string[];
	lastQuestionAt: number;
	released?: string[];
};

export class ScopeStore {
	#available: string[] = [];
	#seen: string[] = [];
	#lastQuestionAt = 0;
	#selected = $state.raw<string[]>([]);
	#released = $state.raw<string[] | null>(null);

	/** The current scope, as source ids. Mutated only through the methods below. */
	get selected(): readonly string[] {
		return this.#selected;
	}

	/** A narrowing 3.6 released, kept for the one-activation reinstate. */
	get released(): readonly string[] | null {
		return this.#released;
	}

	/** Ids that had been reported by the last submit — newness (2.4) is `∉ seen`. */
	get seen(): readonly string[] {
		return this.#seen;
	}

	/** 3.1: zero sources in scope blocks submission; an empty scope is never sent. */
	get canSubmit(): boolean {
		return this.#selected.length > 0;
	}

	isSelected(id: string): boolean {
		return this.#selected.includes(id);
	}

	/**
	 * Restore the scope against the engine's reported sources, on load.
	 * Implements 3.6–3.8 and the 2.4 admission rule; marks the session.
	 */
	load(availableIds: string[]): void {
		this.#available = [...availableIds];
		const stored = this.#read();
		// The session boundary is `sessionStorage` presence, not a clock:
		// cleared by a browser restart, it survives a reload (Decision 4).
		const sameSession = sessionStorage.getItem(SESSION_MARKER_KEY) !== null;
		sessionStorage.setItem(SESSION_MARKER_KEY, '1');

		if (stored === null) {
			// 3.7: no stored scope starts with all available sources.
			this.#seen = [];
			this.#lastQuestionAt = 0;
			this.#selected = [...availableIds];
			this.#released = null;
			this.#persist();
			return;
		}

		this.#seen = stored.seen;
		this.#lastQuestionAt = stored.lastQuestionAt;

		// 3.8: a stored id the engine no longer reports drops silently — this
		// store's own prune at load time, a different subject from the
		// engine-side prune 3.11 reports with a turn.
		const kept = stored.selected.filter((id) => availableIds.includes(id));

		// 2.4: a source not reported when the scope was stored joins the scope
		// only where that scope covered everything then available; under a
		// narrowing it stays out, one activation away, so a fresh ingestion
		// never silently undoes a deliberate narrowing.
		const wasAll = stored.known
			.filter((id) => availableIds.includes(id))
			.every((id) => kept.includes(id));
		const restored = wasAll ? [...availableIds] : kept;

		// 3.6: either clause — a browser restart or more than 8 hours since the
		// last submitted question — releases a narrowing into `released`. A
		// scope already equal to all available releases nothing, so the notice
		// never appears spuriously (Decision 4).
		const within8h =
			this.#lastQuestionAt === 0 || Date.now() - this.#lastQuestionAt <= EIGHT_HOURS_MS;
		const newSession = !sameSession || !within8h;
		const narrower = restored.length < availableIds.length;

		if (newSession && narrower) {
			this.#selected = [...availableIds];
			// Everything-stale releases nothing worth reinstating.
			this.#released = restored.length > 0 ? restored : null;
		} else {
			this.#selected = restored;
			const carried = stored.released?.filter((id) => availableIds.includes(id)) ?? [];
			this.#released = carried.length > 0 ? carried : null;
		}
		this.#persist();
	}

	/** 2.2: toggle one source in or out of scope. Withdraws any release notice. */
	toggle(id: string): void {
		if (!this.#available.includes(id)) return;
		this.#selected = this.#selected.includes(id)
			? this.#selected.filter((selected) => selected !== id)
			: [...this.#selected, id];
		this.#released = null;
		this.#persist();
	}

	/** 2.8 / 3.2: every available source in scope, in one activation. */
	selectAll(): void {
		this.#selected = [...this.#available];
		this.#released = null;
		this.#persist();
	}

	/** 2.8: no source in scope. Submission is then blocked (3.1). */
	selectNone(): void {
		this.#selected = [];
		this.#released = null;
		this.#persist();
	}

	/** 3.6: reinstate the released narrowing in one activation. */
	reinstate(): void {
		if (this.#released === null) return;
		this.#selected = this.#released.filter((id) => this.#available.includes(id));
		this.#released = null;
		this.#persist();
	}

	/**
	 * Record a submitted question: feeds the 8-hour clause of 3.6 and marks
	 * every currently reported source as seen (2.4 — newness ends at the next
	 * submit, not at render). Never changes the scope itself (3.4).
	 */
	noteQuestionSubmitted(): void {
		this.#lastQuestionAt = Date.now();
		const unseen = this.#available.filter((id) => !this.#seen.includes(id));
		this.#seen = [...this.#seen, ...unseen];
		this.#persist();
	}

	/**
	 * The scope at ask time, as a detached copy: later changes apply only to
	 * the next question (3.9).
	 */
	snapshot(): string[] {
		return [...this.#selected];
	}

	#read(): StoredScope | null {
		const raw = localStorage.getItem(SCOPE_STORAGE_KEY);
		if (raw === null) return null;
		try {
			const parsed: unknown = JSON.parse(raw);
			if (typeof parsed !== 'object' || parsed === null) return null;
			const record = parsed as Record<string, unknown>;
			if (
				!Array.isArray(record.selected) ||
				!Array.isArray(record.seen) ||
				!Array.isArray(record.known)
			) {
				return null;
			}
			return {
				selected: record.selected as string[],
				seen: record.seen as string[],
				known: record.known as string[],
				lastQuestionAt: typeof record.lastQuestionAt === 'number' ? record.lastQuestionAt : 0,
				released: Array.isArray(record.released) ? (record.released as string[]) : undefined
			};
		} catch {
			return null; // 3.7: corrupt is the same as never stored.
		}
	}

	#persist(): void {
		const record: StoredScope = {
			selected: [...this.#selected],
			seen: [...this.#seen],
			known: [...this.#available],
			lastQuestionAt: this.#lastQuestionAt,
			...(this.#released !== null ? { released: [...this.#released] } : {})
		};
		localStorage.setItem(SCOPE_STORAGE_KEY, JSON.stringify(record));
	}
}

/** The one scope on the surface. */
export const scope = new ScopeStore();
