// The scope store: selection, persistence and decay (requirements §3, design
// "Scope state, persistence and decay", decision_log Decision 4).
import { beforeEach, describe, expect, it } from 'vitest';
import { ScopeStore, SCOPE_STORAGE_KEY, SESSION_MARKER_KEY } from './scope.svelte';

const LIVE = 'ableton/live-12';
const APC = 'akai/apc-key-25';
const TRIAGE = 'authored/triage';
const ALL = [LIVE, APC, TRIAGE];

const HOUR_MS = 60 * 60 * 1000;

type StoredSeed = {
	selected: string[];
	seen?: string[];
	known?: string[];
	lastQuestionAt?: number;
	released?: string[];
};

/** Seed the persisted record; defaults describe an ordinary, fully-caught-up store. */
function seed(record: StoredSeed): void {
	localStorage.setItem(
		SCOPE_STORAGE_KEY,
		JSON.stringify({ seen: ALL, known: ALL, lastQuestionAt: Date.now(), ...record })
	);
}

/** The session marker survives a reload and is cleared by a browser restart. */
function markSameSession(): void {
	sessionStorage.setItem(SESSION_MARKER_KEY, '1');
}

function loadFresh(available: string[] = ALL): ScopeStore {
	const store = new ScopeStore();
	store.load(available);
	return store;
}

function stored(): StoredSeed {
	return JSON.parse(localStorage.getItem(SCOPE_STORAGE_KEY) ?? 'null');
}

function sorted(ids: readonly string[]): string[] {
	return [...ids].sort();
}

beforeEach(() => {
	localStorage.clear();
	sessionStorage.clear();
});

describe('first load', () => {
	it('starts with all available sources when no scope was ever stored (3.7)', () => {
		const store = loadFresh();
		expect(sorted(store.selected)).toEqual(sorted(ALL));
		expect(store.released).toBeNull();
		expect(store.canSubmit).toBe(true);
	});

	it('treats a corrupt stored record as never stored (3.7)', () => {
		localStorage.setItem(SCOPE_STORAGE_KEY, '{not json');
		markSameSession();
		const store = loadFresh();
		expect(sorted(store.selected)).toEqual(sorted(ALL));
		expect(store.released).toBeNull();
	});

	it('marks the session on load, so a reload reads as the same session (Decision 4)', () => {
		expect(sessionStorage.getItem(SESSION_MARKER_KEY)).toBeNull();
		loadFresh();
		expect(sessionStorage.getItem(SESSION_MARKER_KEY)).not.toBeNull();
	});
});

describe('persistence within a session (3.5)', () => {
	it('restores a narrowed scope on reload within a session', () => {
		const first = loadFresh();
		first.noteQuestionSubmitted();
		first.toggle(APC);
		first.toggle(TRIAGE);
		expect(sorted(first.selected)).toEqual([LIVE]);

		const reloaded = loadFresh(); // session marker still present
		expect(sorted(reloaded.selected)).toEqual([LIVE]);
		expect(reloaded.released).toBeNull();
	});

	it('restores a narrowing made before any question was ever submitted', () => {
		// `seen` only updates on submit (2.4), so nothing has been seen yet —
		// the narrowing must still survive a reload.
		const first = loadFresh();
		first.selectNone();
		first.toggle(LIVE);

		const reloaded = loadFresh();
		expect(sorted(reloaded.selected)).toEqual([LIVE]);
		expect(reloaded.released).toBeNull();
	});

	it('persists every scope change immediately', () => {
		const store = loadFresh();
		store.toggle(TRIAGE);
		expect(sorted(stored().selected)).toEqual(sorted([LIVE, APC]));
	});
});

describe('stale stored ids (3.8)', () => {
	it('drops a stored id the engine no longer reports, silently', () => {
		seed({
			selected: [LIVE, 'gone/source'],
			seen: [...ALL, 'gone/source'],
			known: [...ALL, 'gone/source']
		});
		markSameSession();
		const store = loadFresh();
		expect(sorted(store.selected)).toEqual([LIVE]);
		// A different subject from 3.11's engine-side prune: nothing is reported.
		expect(store.released).toBeNull();
	});
});

describe('scope decay at a session boundary (3.6, Decision 4)', () => {
	it('releases a narrowing on the first load after a browser restart, however recent the last question', () => {
		// The boundary is sessionStorage presence, not a clock: lastQuestionAt
		// is minutes old, and the absent marker alone triggers the release.
		seed({ selected: [LIVE], lastQuestionAt: Date.now() - 5 * 60 * 1000 });
		const store = loadFresh();
		expect(sorted(store.selected)).toEqual(sorted(ALL));
		expect(sorted(store.released ?? [])).toEqual([LIVE]);
	});

	it('releases a narrowing when the last question is over 8 hours old, within the same session', () => {
		seed({ selected: [LIVE], lastQuestionAt: Date.now() - 8 * HOUR_MS - 60_000 });
		markSameSession();
		const store = loadFresh();
		expect(sorted(store.selected)).toEqual(sorted(ALL));
		expect(sorted(store.released ?? [])).toEqual([LIVE]);
	});

	it('does not release within 8 hours of the last question in the same session', () => {
		seed({ selected: [LIVE], lastQuestionAt: Date.now() - 7 * HOUR_MS });
		markSameSession();
		const store = loadFresh();
		expect(sorted(store.selected)).toEqual([LIVE]);
		expect(store.released).toBeNull();
	});

	it('releases nothing when the stored scope already equals all available, so the notice never appears spuriously', () => {
		seed({ selected: ALL }); // no session marker: a browser restart
		const store = loadFresh();
		expect(sorted(store.selected)).toEqual(sorted(ALL));
		expect(store.released).toBeNull();
	});

	it('reinstates the released narrowing in one activation', () => {
		seed({ selected: [LIVE] });
		const store = loadFresh();
		store.reinstate();
		expect(sorted(store.selected)).toEqual([LIVE]);
		expect(store.released).toBeNull();
		expect(sorted(stored().selected ?? [])).toEqual([LIVE]);
	});

	it('keeps the release notice across a reload within the new session', () => {
		seed({ selected: [LIVE] });
		loadFresh(); // releases, persists, marks the session
		const reloaded = loadFresh();
		expect(sorted(reloaded.selected)).toEqual(sorted(ALL));
		expect(sorted(reloaded.released ?? [])).toEqual([LIVE]);
	});

	it('withdraws the release notice on a deliberate scope change', () => {
		seed({ selected: [LIVE] });
		const store = loadFresh();
		store.toggle(APC);
		expect(store.released).toBeNull();
	});
});

describe('questions and scope', () => {
	it('keeps scope unchanged across successive questions (3.4)', () => {
		const store = loadFresh();
		store.toggle(APC);
		const before = sorted(store.selected);
		store.noteQuestionSubmitted();
		store.noteQuestionSubmitted();
		expect(sorted(store.selected)).toEqual(before);
		expect(stored().lastQuestionAt).toBeGreaterThan(0);
	});

	it('leaves the scope captured at ask time untouched by later changes (3.9)', () => {
		const store = loadFresh();
		const atAsk = store.snapshot();
		store.toggle(LIVE);
		expect(sorted(atAsk)).toEqual(sorted(ALL));
		expect(sorted(store.selected)).toEqual(sorted([APC, TRIAGE]));
	});
});

describe('empty scope (3.1, 3.2)', () => {
	it('blocks submission at zero sources in scope — the client never sends an empty scope', () => {
		const store = loadFresh();
		store.selectNone();
		expect(store.selected).toHaveLength(0);
		expect(store.canSubmit).toBe(false);
	});

	it('places all sources in scope in a single activation', () => {
		const store = loadFresh();
		store.selectNone();
		store.selectAll();
		expect(sorted(store.selected)).toEqual(sorted(ALL));
		expect(store.canSubmit).toBe(true);
	});
});

describe('widen-and-retry (7.9)', () => {
	it('persists like any scope change and decays at the next session', () => {
		const store = loadFresh();
		store.selectNone();
		store.toggle(LIVE);
		// The engine suggested APC; widen-and-retry adds it and never reverts it.
		store.toggle(APC);
		expect(sorted(stored().selected)).toEqual(sorted([LIVE, APC]));

		sessionStorage.clear(); // browser restart
		const next = loadFresh();
		expect(sorted(next.selected)).toEqual(sorted(ALL));
		expect(sorted(next.released ?? [])).toEqual(sorted([LIVE, APC]));
	});
});

describe('a newly reported source (2.4)', () => {
	it('enters scope where the stored scope was all available sources', () => {
		seed({ selected: [LIVE, APC], seen: [LIVE, APC], known: [LIVE, APC] });
		markSameSession();
		const store = loadFresh(ALL); // TRIAGE newly reported
		expect(sorted(store.selected)).toEqual(sorted(ALL));
	});

	it('stays out of scope under a narrowed scope, one activation away from joining', () => {
		seed({ selected: [LIVE], seen: [LIVE, APC], known: [LIVE, APC] });
		markSameSession();
		const store = loadFresh(ALL);
		expect(sorted(store.selected)).toEqual([LIVE]);
		store.toggle(TRIAGE); // the one-activation add
		expect(sorted(store.selected)).toEqual(sorted([LIVE, TRIAGE]));
	});

	it('stays new until the next submit: noteQuestionSubmitted marks every available id seen', () => {
		seed({ selected: [LIVE], seen: [LIVE, APC], known: [LIVE, APC] });
		markSameSession();
		const store = loadFresh(ALL);
		expect(store.seen).not.toContain(TRIAGE);
		store.noteQuestionSubmitted();
		expect(sorted(store.seen)).toEqual(sorted(ALL));
		expect(sorted(stored().seen ?? [])).toEqual(sorted(ALL));
	});
});
