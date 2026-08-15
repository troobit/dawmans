// The history store: persisted exchanges (requirements 12.1, 12.7, 12.9;
// design "History"). localStorage, read lazily when the panel first opens;
// written on settle, trimmed to the most recent 50; a QuotaExceededError drops
// oldest entries until the write succeeds rather than failing the turn.
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { Citation } from '../engine/records';
import { Turn } from '../engine/turn.svelte';
import { HISTORY_STORAGE_KEY, HistoryStore, type HistoryEntry } from './history.svelte';

const SCOPE = ['ableton/live-12', 'akai/apc-key-25'];

function citation(passageId: string): Citation {
	return {
		kind: 'vendor-manual',
		source_id: 'ableton/live-12',
		display_name: 'Ableton Live 12',
		passage_id: passageId,
		section_title: 'Track Activator',
		section_number: '15.2',
		hardware_applicability: { status: 'confirmed' },
		degraded: false,
		has_figures: false,
		doc_version: '12',
		page: 312
	};
}

/** A settled, answered turn — the ordinary thing history retains. */
function settledTurn(question = 'why is the track silent'): Turn {
	const turn = new Turn(question, SCOPE);
	turn.state = 'settled';
	turn.renderer = 'answer';
	turn.envelope = {
		outcome: 'answered',
		direct_answer: 'Turn the Track Activator back on.',
		body: 'The Track Activator mutes the track when off. [[p:ableton/live-12#a1]]'
	};
	turn.citations = new Map([['ableton/live-12#a1', citation('ableton/live-12#a1')]]);
	return turn;
}

function entry(question: string, askedAt: number): HistoryEntry {
	return {
		question,
		envelope: { outcome: 'answered', direct_answer: 'x' },
		citations: [],
		scopeAtAsk: SCOPE,
		askedAt
	};
}

function seed(entries: HistoryEntry[]): void {
	localStorage.setItem(HISTORY_STORAGE_KEY, JSON.stringify(entries));
}

function stored(): HistoryEntry[] {
	return JSON.parse(localStorage.getItem(HISTORY_STORAGE_KEY) ?? '[]');
}

beforeEach(() => {
	localStorage.clear();
	vi.restoreAllMocks();
});

describe('lazy read (12.1)', () => {
	it('reads nothing from storage at construction — 50 exchanges parsed on boot would come out of 8.7', () => {
		seed([entry('earlier', 1)]);
		const getItem = vi.spyOn(localStorage, 'getItem');
		new HistoryStore();
		expect(getItem).not.toHaveBeenCalled();
	});

	it('reads the persisted entries on first access', () => {
		seed([entry('earlier', 1)]);
		const store = new HistoryStore();
		const getItem = vi.spyOn(localStorage, 'getItem');
		expect(store.entries).toHaveLength(1);
		expect(store.entries[0].question).toBe('earlier');
		expect(getItem).toHaveBeenCalledWith(HISTORY_STORAGE_KEY);
	});

	it('treats a corrupt stored record as empty history', () => {
		localStorage.setItem(HISTORY_STORAGE_KEY, '{not json');
		const store = new HistoryStore();
		expect(store.entries).toEqual([]);
	});
});

describe('what an entry stores (12.9)', () => {
	it('stores the question, envelope, citation records, scope at ask time and a timestamp — never passage text', () => {
		const store = new HistoryStore();
		store.record(settledTurn());
		const [saved] = stored();
		expect(saved.question).toBe('why is the track silent');
		expect(saved.envelope.outcome).toBe('answered');
		expect(saved.citations).toEqual([citation('ableton/live-12#a1')]);
		expect(saved.scopeAtAsk).toEqual(SCOPE);
		expect(saved.askedAt).toBeGreaterThan(0);
		// The citation record carries no passage text; expansion refetches it.
		expect(Object.keys(saved).sort()).toEqual([
			'askedAt',
			'citations',
			'envelope',
			'question',
			'scopeAtAsk'
		]);
	});

	it('merges with entries persisted by an earlier session, newest first', () => {
		seed([entry('earlier', 1)]);
		const store = new HistoryStore();
		store.record(settledTurn('later'));
		expect(stored().map((e) => e.question)).toEqual(['later', 'earlier']);
	});

	it('trims to the most recent 50 on settle', () => {
		seed(Array.from({ length: 50 }, (_, i) => entry(`q${49 - i}`, 49 - i)));
		const store = new HistoryStore();
		store.record(settledTurn('the 51st'));
		const kept = stored();
		expect(kept).toHaveLength(50);
		expect(kept[0].question).toBe('the 51st');
		// The oldest entry fell off the end.
		expect(kept.map((e) => e.question)).not.toContain('q0');
	});

	it('drops oldest entries on QuotaExceededError until the write succeeds, never failing the turn', () => {
		seed([entry('q3', 3), entry('q2', 2), entry('q1', 1)]);
		const write = localStorage.setItem.bind(localStorage);
		let failures = 2;
		vi.spyOn(localStorage, 'setItem').mockImplementation((key, value) => {
			if (failures > 0) {
				failures -= 1;
				throw new DOMException('quota exceeded', 'QuotaExceededError');
			}
			write(key, value);
		});
		const store = new HistoryStore();
		expect(() => store.record(settledTurn('the new one'))).not.toThrow();
		// 4 entries failed, 3 failed, 2 succeeded: the two oldest were dropped.
		expect(stored().map((e) => e.question)).toEqual(['the new one', 'q3']);
	});

	it('gives up silently when storage never accepts the write', () => {
		vi.spyOn(localStorage, 'setItem').mockImplementation(() => {
			throw new DOMException('quota exceeded', 'QuotaExceededError');
		});
		const store = new HistoryStore();
		expect(() => store.record(settledTurn())).not.toThrow();
	});
});

describe('what is retained (12.7)', () => {
	it('does not retain a user-cancelled exchange', () => {
		const turn = settledTurn();
		turn.userCancelled = true;
		const store = new HistoryStore();
		store.record(turn);
		expect(stored()).toEqual([]);
	});

	it('does not retain an engine-cancelled (abandoned) exchange', () => {
		const turn = settledTurn();
		turn.envelope = { outcome: 'cancelled' };
		turn.renderer = 'cancelled';
		const store = new HistoryStore();
		store.record(turn);
		expect(stored()).toEqual([]);
	});

	it('does not retain a failed exchange as if it were an answer', () => {
		const turn = new Turn('anything', SCOPE);
		turn.state = 'settled';
		turn.envelope = { outcome: 'provider-unreachable' };
		turn.renderer = 'error';
		const store = new HistoryStore();
		store.record(turn);
		expect(stored()).toEqual([]);
	});

	it('does not retain a failed turn with no renderer — a rejection is not an exchange', () => {
		// A 9.15 request rejection or a 9.19 unknown stream version: no outcome
		// ever arrived, nothing was answered.
		const turn = new Turn('anything', SCOPE);
		turn.state = 'failed';
		const store = new HistoryStore();
		store.record(turn);
		expect(stored()).toEqual([]);
	});

	it('does not retain an incomplete turn with nothing in it', () => {
		// The engine died before the first byte: outcome `incomplete` was
		// synthesised, but there is no partial answer for 12.7 to retain.
		const turn = new Turn('anything', SCOPE);
		turn.state = 'failed';
		turn.renderer = 'answer';
		turn.envelope = { outcome: 'incomplete' };
		const store = new HistoryStore();
		store.record(turn);
		expect(stored()).toEqual([]);
	});

	it('retains a partial kept under 9.14, marked incomplete', () => {
		// A stream that dropped mid-answer: the partial text is retained on
		// screen and in history, never presented as a finished answer.
		const turn = new Turn('why is the kick distorting', SCOPE);
		turn.state = 'failed';
		turn.renderer = 'answer';
		turn.envelope = { outcome: 'incomplete', direct_answer: 'Check the gain st' };
		const store = new HistoryStore();
		store.record(turn);
		const [saved] = stored();
		expect(saved.question).toBe('why is the kick distorting');
		expect(saved.incomplete).toBe(true);
	});

	it('does not mark a completed answer incomplete', () => {
		const store = new HistoryStore();
		store.record(settledTurn());
		expect(stored()[0].incomplete).toBeUndefined();
	});
});
