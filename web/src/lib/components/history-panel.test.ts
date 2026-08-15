// The history panel (requirements 12.2–12.6, 12.8; design "History"): the
// region over the history store — re-display from storage with no engine
// query, re-ask against the current scope as a new conversation, and clear-all
// behind a confirmation step. Component tests over fresh stores; the engine is
// the stubbed channel of turn-channel.ts where a turn is actually run.

import { cleanup, fireEvent, render, screen } from '@testing-library/svelte';
import { tick } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { Citation } from '../engine/records';
import { KeyRouter } from '../keys';
import { HISTORY_STORAGE_KEY, HistoryStore, type HistoryEntry } from '../state/history.svelte';
import { ScopeStore } from '../state/scope.svelte';
import { ThreadStore } from '../state/thread.svelte';
import { fakeEngine, type FakeEngine } from '../testing/turn-channel';
import HistoryPanel from './HistoryPanel.svelte';

const SCOPE = ['ableton/live-12', 'akai/apc-key-25'];

const NAMES: Record<string, string> = {
	'ableton/live-12': 'Ableton Live 12',
	'akai/apc-key-25': 'Akai APC Key 25',
	'authored/triage': 'Your triage notes'
};

/** The panel needs only names for the stored scope (12.4). */
const sources = {
	get ids() {
		return Object.keys(NAMES);
	},
	displayName: (id: string) => NAMES[id]
};

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

function entry(question: string, askedAt: number, over: Partial<HistoryEntry> = {}): HistoryEntry {
	return {
		question,
		envelope: {
			outcome: 'answered',
			direct_answer: `Answer to: ${question}`,
			body: 'The Track Activator mutes the track when off.'
		},
		citations: [citation('ableton/live-12#a1')],
		scopeAtAsk: SCOPE,
		askedAt,
		...over
	};
}

function seed(entries: HistoryEntry[]): void {
	localStorage.setItem(HISTORY_STORAGE_KEY, JSON.stringify(entries));
}

let engine: FakeEngine;
let scope: ScopeStore;
let history: HistoryStore;
let thread: ThreadStore;

beforeEach(() => {
	localStorage.clear();
	sessionStorage.clear();
	engine = fakeEngine();
	scope = new ScopeStore();
	scope.load([...SCOPE, 'authored/triage']);
	history = new HistoryStore();
	thread = new ThreadStore({ scope, history, submit: engine.submit });
});

afterEach(() => {
	cleanup();
	vi.unstubAllGlobals();
	document.body.innerHTML = '';
});

function renderPanel(extra: Record<string, unknown> = {}) {
	return render(HistoryPanel, { props: { history, thread, sources, ...extra } });
}

describe('the retained list (12.2)', () => {
	it('lists entries in reverse-chronological order with question and when it was asked', () => {
		const older = new Date('2026-08-14T09:00:00Z').getTime();
		const newer = new Date('2026-08-15T10:30:00Z').getTime();
		seed([entry('why is the track silent', newer), entry('kick is distorting', older)]);
		const { container } = renderPanel();

		const items = [...container.querySelectorAll('li.entry')];
		expect(items).toHaveLength(2);
		expect(items[0].textContent).toContain('why is the track silent'); // newest first
		expect(items[1].textContent).toContain('kick is distorting');

		const times = [...container.querySelectorAll('time')];
		expect(times.map((time) => time.getAttribute('datetime'))).toEqual([
			new Date(newer).toISOString(),
			new Date(older).toISOString()
		]);
	});

	it('marks an incomplete exchange rather than presenting it as an answer (12.7)', () => {
		seed([entry('half answered', Date.now(), { incomplete: true })]);
		const { container } = renderPanel();
		expect(container.querySelector('li.entry')?.textContent).toMatch(/incomplete/i);
	});
});

describe('re-display (12.3, 12.4)', () => {
	it('re-displays the stored answer with its citations and no engine query', async () => {
		const fetchSpy = vi.fn(() => {
			throw new Error('the panel must not query the engine to re-display (12.3)');
		});
		vi.stubGlobal('fetch', fetchSpy);
		seed([entry('why is the track silent', Date.now())]);
		renderPanel();

		await fireEvent.click(screen.getByRole('button', { name: /why is the track silent/ }));
		expect(screen.getByText('Answer to: why is the track silent')).toBeTruthy();
		expect(screen.getByText(/Track Activator mutes the track/)).toBeTruthy();
		expect(screen.getByText('p312')).toBeTruthy(); // the citation's location, from storage
		expect(fetchSpy).not.toHaveBeenCalled();
	});

	it('shows the scope in force when the exchange was asked (12.4)', async () => {
		seed([entry('why is the track silent', Date.now())]);
		renderPanel();
		await fireEvent.click(screen.getByRole('button', { name: /why is the track silent/ }));
		const scopeLine = screen.getByText(/scope at ask/i);
		expect(scopeLine.textContent).toContain('Ableton Live 12');
		expect(scopeLine.textContent).toContain('Akai APC Key 25');
	});
});

describe('re-ask (12.5)', () => {
	it('runs against the current scope as a new conversation, producing a new exchange', async () => {
		seed([entry('why is the track silent', new Date('2026-08-14T09:00:00Z').getTime())]);

		// An existing thread, mid-conversation: a re-ask must not follow it up.
		thread.submit('unrelated earlier question');
		await vi.waitFor(() => expect(engine.channels).toHaveLength(1));
		engine.channels[0].emit('outcome', { outcome: 'answered' });
		engine.channels[0].emit('done', {});
		engine.channels[0].close();
		await vi.waitFor(() => expect(thread.busy).toBe(false));

		// The current scope is narrower than the stored one.
		scope.selectNone();
		scope.toggle('authored/triage');

		renderPanel();
		await fireEvent.click(screen.getByRole('button', { name: /why is the track silent/ }));
		await fireEvent.click(screen.getByRole('button', { name: /re-ask/i }));

		await vi.waitFor(() => expect(engine.requests).toHaveLength(2));
		expect(engine.requests[1]).toEqual({
			conversation_id: null, // a new conversation, never a follow-up (12.5)
			question: 'why is the track silent',
			sources: ['authored/triage'] // the current scope, not the stored one
		});

		// A new exchange is produced; the old one is not overwritten.
		engine.channels[1].emit('outcome', { outcome: 'answered' });
		engine.channels[1].emit('direct_answer', { text: 'A fresh answer.' });
		engine.channels[1].emit('done', {});
		engine.channels[1].close();
		await vi.waitFor(() => expect(history.entries).toHaveLength(3));
		expect(history.entries[0].question).toBe('why is the track silent');
		expect(history.entries[0].envelope.direct_answer).toBe('A fresh answer.');
		expect(
			history.entries.filter((held) => held.question === 'why is the track silent')
		).toHaveLength(2);
	});
});

describe('clearing history (12.6)', () => {
	it('clears everything in one action behind a confirmation step', async () => {
		seed([entry('one', 2), entry('two', 1)]);
		renderPanel();

		await fireEvent.click(screen.getByRole('button', { name: /clear history/i }));
		// The confirmation step: nothing deleted yet.
		expect(history.entries).toHaveLength(2);

		await fireEvent.click(screen.getByRole('button', { name: /delete all/i }));
		expect(history.entries).toHaveLength(0);
		expect(localStorage.getItem(HISTORY_STORAGE_KEY)).toBeNull();
		expect(screen.queryByText(/one/)).toBeNull();
	});

	it('keeps everything when the confirmation is declined', async () => {
		seed([entry('one', 2)]);
		renderPanel();
		await fireEvent.click(screen.getByRole('button', { name: /clear history/i }));
		await fireEvent.click(screen.getByRole('button', { name: /keep/i }));
		expect(history.entries).toHaveLength(1);
		expect(screen.queryByRole('button', { name: /delete all/i })).toBeNull();
	});
});

describe('off the ask surface (12.8)', () => {
	it('is dismissible in one activation, by control and by Escape', async () => {
		const onclose = vi.fn();
		const router = new KeyRouter();
		seed([entry('one', 1)]);
		renderPanel({ router, onclose });
		await tick();

		await fireEvent.click(screen.getByRole('button', { name: /close/i }));
		expect(onclose).toHaveBeenCalledOnce();

		router.handleKeydown(new KeyboardEvent('keydown', { key: 'Escape', cancelable: true }));
		expect(onclose).toHaveBeenCalledTimes(2);
	});
});
