// The narrowing renderer (requirements 6.1–6.5, 6.7, 6.8; design "Narrowing
// and ranked causes"). Turns are driven through a ThreadStore over the stubbed
// engine because narrowing is about submission: a candidate selection is a
// follow-up turn in the same thread, and the digits go through the router's
// arming registry, never through a component handler (Decision 5).

import { cleanup, fireEvent, render, screen } from '@testing-library/svelte';
import { tick } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { NarrowingCandidate } from '../engine/records';
import { KeyRouter } from '../keys';
import { HistoryStore } from '../state/history.svelte';
import { ScopeStore } from '../state/scope.svelte';
import { ThreadStore } from '../state/thread.svelte';
import { fakeEngine, type FakeEngine, type TurnChannel } from '../testing/turn-channel';
import AskSurface from './AskSurface.svelte';
import ThreadView from './ThreadView.svelte';

let engine: FakeEngine;
let scope: ScopeStore;
let thread: ThreadStore;
let router: KeyRouter;

beforeEach(() => {
	localStorage.clear();
	sessionStorage.clear();
	engine = fakeEngine();
	scope = new ScopeStore();
	scope.load(['live/manual', 'akai/apc']);
	thread = new ThreadStore({ scope, submit: engine.submit });
	router = new KeyRouter();
});

afterEach(() => {
	cleanup();
	document.body.innerHTML = '';
});

// `{label, value}` as the engine sends them: label is the cause's `check` and
// is what the control reads, value is the cause `statement` and is what a
// selection submits (`api/answer-engine` design §Narrowing step 3).
const CANDIDATES = [
	{ label: 'The kick channel meter is clipping', value: 'The kick itself is clipping' },
	{ label: 'The master meter is clipping', value: 'The master bus is clipping' }
];

/** The channel serving the most recent submission, once the fetch has resolved. */
async function lastChannel(): Promise<TurnChannel> {
	await vi.waitFor(() => expect(engine.channels.length).toBeGreaterThan(0));
	return engine.channels[engine.channels.length - 1];
}

/** Submit a question and settle it as a narrowing turn. */
async function settleNarrowing(
	candidates: NarrowingCandidate[] = CANDIDATES
): Promise<void> {
	thread.submit('the kick is distorting');
	const channel = await lastChannel();
	channel.emit('outcome', { outcome: 'needs-narrowing' });
	channel.emit('narrowing', { question: 'Is the clipping on the kick channel alone?', candidates });
	channel.emit('done', { complete: true });
	channel.close();
	await vi.waitFor(() => expect(thread.turns.at(-1)?.state).toBe('settled'));
	await tick();
}

function pressDigit(digit: string): void {
	document.body.dispatchEvent(
		new KeyboardEvent('keydown', { key: digit, bubbles: true, cancelable: true })
	);
}

describe('the narrowing state is its own renderer (6.1)', () => {
	it('renders the question and candidates, visually distinct from an answer', async () => {
		const { container } = render(ThreadView, { props: { thread, scope, router } });
		await settleNarrowing();

		const narrowing = container.querySelector('.narrowing');
		expect(narrowing).not.toBeNull();
		expect(narrowing?.textContent).toContain('Is the clipping on the kick channel alone?');
		for (const candidate of CANDIDATES) {
			expect(narrowing?.textContent).toContain(candidate.label);
		}
		// Not the answer renderer, not a coverage failure, not an error.
		expect(container.querySelector('.answer')).toBeNull();
		expect(container.querySelector('.coverage-failure')).toBeNull();
		expect(container.querySelector('.error')).toBeNull();
	});

	it('renders an answered turn through the answer renderer, not this one', async () => {
		const { container } = render(ThreadView, { props: { thread, scope, router } });
		thread.submit('no sound');
		const channel = await lastChannel();
		channel.emit('outcome', { outcome: 'answered' });
		channel.emit('done', { complete: true });
		channel.close();
		await vi.waitFor(() => expect(thread.turns[0].state).toBe('settled'));
		await tick();
		expect(container.querySelector('.answer')).not.toBeNull();
		expect(container.querySelector('.narrowing')).toBeNull();
	});
});

describe('candidates are numbered controls in engine order (6.2)', () => {
	it('renders each candidate as a separately activatable control, in order, none added', async () => {
		const { container } = render(ThreadView, { props: { thread, scope, router } });
		await settleNarrowing();

		const buttons = [...container.querySelectorAll('.narrowing .candidates button')];
		expect(buttons).toHaveLength(CANDIDATES.length);
		buttons.forEach((button, index) => {
			expect(button.textContent).toContain(CANDIDATES[index].label);
			expect(button.textContent).toContain(String(index + 1));
		});
	});
});

describe('the candidate shape the engine actually sends', () => {
	// Regression, bugfix `narrowing-candidate-shape`. The engine sends
	// `candidates[]` as `{label, value}` records — `answer/narrow.py:160`, label
	// from the cause's `check`, value from its `statement`, per
	// `api/answer-engine` design §Narrowing step 3 and decision_log Decision 9.
	// This side typed them `string[]`, so 6.2's controls rendered
	// "[object Object]" and 6.4 submitted an object as the follow-up question.
	//
	// The payload is written the way the engine emits it, not through the
	// `CANDIDATES` fixture above: that fixture is what hid the drift.
	const ENGINE_CANDIDATES = [
		{ label: 'The kick channel meter is clipping', value: 'The kick itself is clipping' },
		{ label: 'The master meter is clipping', value: 'The master bus is clipping' }
	];

	async function settleEngineNarrowing(): Promise<void> {
		thread.submit('the kick is distorting');
		const channel = await lastChannel();
		channel.emit('outcome', { outcome: 'needs-narrowing' });
		channel.emit('narrowing', {
			question: 'Is the clipping on the kick channel alone?',
			candidates: ENGINE_CANDIDATES
		});
		channel.emit('done', { complete: true });
		channel.close();
		await vi.waitFor(() => expect(thread.turns.at(-1)?.state).toBe('settled'));
		await tick();
	}

	it('renders each candidate by its label, never as a stringified object (6.2)', async () => {
		const { container } = render(ThreadView, { props: { thread, scope, router } });
		await settleEngineNarrowing();

		const buttons = [...container.querySelectorAll('.narrowing .candidates button')];
		expect(buttons).toHaveLength(ENGINE_CANDIDATES.length);
		buttons.forEach((button, index) => {
			expect(button.textContent).toContain(ENGINE_CANDIDATES[index].label);
			expect(button.textContent).not.toContain('[object Object]');
		});
	});

	it('submits the selected candidate’s value as the follow-up question (6.4)', async () => {
		render(ThreadView, { props: { thread, scope, router } });
		render(AskSurface, { props: { thread, scope, router } });
		await settleEngineNarrowing();

		pressDigit('2');
		await tick();
		expect(engine.requests).toHaveLength(2);
		expect(engine.requests[1].question).toBe(ENGINE_CANDIDATES[1].value);
	});
});

describe('selection by digit, navigation and pointer (6.3)', () => {
	it('selects a candidate on a single unmodified digit through the arming registry', async () => {
		render(ThreadView, { props: { thread, scope, router } });
		render(AskSurface, { props: { thread, scope, router } });
		await settleNarrowing();

		pressDigit('2');
		await tick();
		expect(engine.requests).toHaveLength(2);
		expect(engine.requests[1].question).toBe(CANDIDATES[1].value);
	});

	it('indicates the armed digits on screen once the list awaits selection (1.11)', async () => {
		const { container } = render(ThreadView, { props: { thread, scope, router } });
		await settleNarrowing();
		const digits = [...container.querySelectorAll('.narrowing .candidates kbd')];
		expect(digits.map((digit) => digit.textContent)).toEqual(['1', '2']);
	});

	it('selects equally by pointer', async () => {
		render(ThreadView, { props: { thread, scope, router } });
		await settleNarrowing();
		await fireEvent.click(screen.getByRole('button', { name: /master meter/i }));
		expect(engine.requests).toHaveLength(2);
		expect(engine.requests[1].question).toBe(CANDIDATES[1].value);
	});

	it('disarms once the selection is made', async () => {
		render(ThreadView, { props: { thread, scope, router } });
		render(AskSurface, { props: { thread, scope, router } });
		await settleNarrowing();
		await fireEvent.click(screen.getByRole('button', { name: /kick channel meter/i }));
		await tick();
		pressDigit('2');
		await tick();
		// The digit no longer selects; only the two submissions exist.
		expect(engine.requests).toHaveLength(2);
	});
});

describe('selection is a follow-up turn in the current thread (6.4)', () => {
	it('submits against the unchanged scope, in the same conversation', async () => {
		render(ThreadView, { props: { thread, scope, router } });
		await settleNarrowing();
		await fireEvent.click(screen.getByRole('button', { name: /kick channel meter/i }));

		expect(engine.requests).toHaveLength(2);
		expect(engine.requests[1].sources).toEqual(engine.requests[0].sources);
		// The same thread: the first turn started the conversation, the
		// follow-up carries its minted id (Decision 8).
		expect(engine.requests[1].conversation_id).not.toBeNull();
		expect(thread.turns).toHaveLength(2);
	});

	it('keeps the narrowing question and the chosen candidate visible in the thread', async () => {
		const { container } = render(ThreadView, { props: { thread, scope, router } });
		await settleNarrowing();
		await fireEvent.click(screen.getByRole('button', { name: /kick channel meter/i }));
		await tick();

		// The narrowing turn stays painted, question and candidates included.
		expect(container.textContent).toContain('Is the clipping on the kick channel alone?');
		// The chosen candidate is visible as the follow-up turn's question.
		const questions = [...container.querySelectorAll('.question')];
		expect(questions.some((question) => question.textContent?.includes(CANDIDATES[0].value))).toBe(
			true
		);
	});
});

describe('ignoring the question with free text (6.5)', () => {
	it('a printable other than an armed digit begins a reply without dismissing the list', async () => {
		const { container } = render(ThreadView, { props: { thread, scope, router } });
		render(AskSurface, { props: { thread, scope, router } });
		await settleNarrowing();

		const elsewhere = document.createElement('button');
		document.body.appendChild(elsewhere);
		elsewhere.focus();
		document.body.dispatchEvent(
			new KeyboardEvent('keydown', { key: 'w', bubbles: true, cancelable: true })
		);
		await tick();

		expect(thread.draft).toBe('w');
		// The candidate list is still on screen and still armed.
		expect(container.querySelectorAll('.narrowing .candidates button')).toHaveLength(2);
		pressDigit('1');
		await tick();
		expect(engine.requests).toHaveLength(2);
		expect(engine.requests[1].question).toBe(CANDIDATES[0].value);
	});
});

describe('history retention (6.7)', () => {
	it('retains the narrowing exchange as part of its thread, never standalone', async () => {
		const history = new HistoryStore();
		thread = new ThreadStore({ scope, history, submit: engine.submit });
		render(ThreadView, { props: { thread, scope, router } });
		await settleNarrowing();
		await fireEvent.click(screen.getByRole('button', { name: /kick channel meter/i }));
		const channel = await lastChannel();
		channel.emit('outcome', { outcome: 'answered' });
		channel.emit('direct_answer', { text: 'Lower the kick clip gain.' });
		channel.emit('done', { complete: true });
		channel.close();
		await vi.waitFor(() => expect(thread.turns[1].state).toBe('settled'));

		// Both exchanges retained, newest first, tied to the one thread.
		expect(history.entries).toHaveLength(2);
		expect(history.entries[1].envelope.outcome).toBe('needs-narrowing');
		expect(history.entries[0].thread).toBeDefined();
		expect(history.entries[1].thread).toBe(history.entries[0].thread);
	});
});

describe('the question is not held back (6.8)', () => {
	it('paints the narrowing question while the turn is still streaming', async () => {
		const { container } = render(ThreadView, { props: { thread, scope, router } });
		thread.submit('the kick is distorting');
		const channel = await lastChannel();
		channel.emit('outcome', { outcome: 'needs-narrowing' });
		channel.emit('narrowing', {
			question: 'Is the clipping on the kick channel alone?',
			candidates: CANDIDATES
		});
		await vi.waitFor(() => expect(thread.turns[0].state).toBe('streaming'));
		await tick();

		// No `done` yet: the question is on screen before the turn settles.
		expect(container.textContent).toContain('Is the clipping on the kick channel alone?');
	});
});
