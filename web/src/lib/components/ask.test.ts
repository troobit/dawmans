// The ask input, the symptom shortcuts and the thread shell (requirements
// §1, 3.2, 9.15; design "Surfaces" and "Keyboard routing and arming").
// Component tests over fresh store instances and a fresh router per test;
// the engine is the stubbed channel of turn-channel.ts.

import { cleanup, fireEvent, render, screen } from '@testing-library/svelte';
import { tick } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { KeyRouter } from '../keys';
import { ScopeStore } from '../state/scope.svelte';
import { QUESTION_LIMIT, ThreadStore } from '../state/thread.svelte';
import { fakeEngine, type FakeEngine } from '../testing/turn-channel';
import AskSurface, { SYMPTOM_SHORTCUTS } from './AskSurface.svelte';
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
	scope.load(['src/a', 'src/b']);
	thread = new ThreadStore({ scope, submit: engine.submit });
	router = new KeyRouter();
});

afterEach(() => {
	cleanup();
	document.body.innerHTML = '';
});

function renderAsk() {
	const result = render(AskSurface, { props: { thread, scope, router } });
	const textarea = screen.getByRole('textbox', { name: /ask/i }) as HTMLTextAreaElement;
	return { ...result, textarea };
}

async function type(text: string) {
	thread.draft = text;
	await tick();
}

/** The channel serving the most recent submission, once the fetch has resolved. */
async function lastChannel() {
	await vi.waitFor(() => expect(engine.channels.length).toBeGreaterThan(0));
	return engine.channels[engine.channels.length - 1];
}

describe('focus (1.1, 1.2)', () => {
	it('lands in the question input on load without a click', async () => {
		const { textarea } = renderAsk();
		await tick();
		expect(document.activeElement).toBe(textarea);
	});

	it('returns to the question input on window focus', async () => {
		const { textarea } = renderAsk();
		await tick();
		const elsewhere = document.createElement('button');
		document.body.appendChild(elsewhere);
		elsewhere.focus();
		window.dispatchEvent(new FocusEvent('focus'));
		expect(document.activeElement).toBe(textarea);
	});

	it('captures a printable typed elsewhere into the input (1.2)', async () => {
		const { textarea } = renderAsk();
		await tick();
		const elsewhere = document.createElement('button');
		document.body.appendChild(elsewhere);
		elsewhere.focus();
		document.body.dispatchEvent(
			new KeyboardEvent('keydown', { key: 'w', bubbles: true, cancelable: true })
		);
		await tick();
		expect(thread.draft).toBe('w');
		expect(document.activeElement).toBe(textarea);
	});
});

describe('submission (1.3, 1.5)', () => {
	it('submits on a single unmodified Enter', async () => {
		const { textarea } = renderAsk();
		await type('no sound at all');
		await fireEvent.keyDown(textarea, { key: 'Enter' });
		expect(engine.submit).toHaveBeenCalledOnce();
		expect(engine.requests[0].question).toBe('no sound at all');
		expect(thread.draft).toBe('');
	});

	it('inserts a line break instead of submitting on Shift+Enter', async () => {
		const { textarea } = renderAsk();
		await type('first line');
		const passedThrough = await fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: true });
		expect(passedThrough).toBe(true); // default not prevented: the browser inserts the break
		expect(engine.submit).not.toHaveBeenCalled();
	});

	it('does nothing on a whitespace-only submit and contacts no engine', async () => {
		const { textarea } = renderAsk();
		await type('   \n ');
		await fireEvent.keyDown(textarea, { key: 'Enter' });
		expect(engine.submit).not.toHaveBeenCalled();
		expect(thread.turns).toHaveLength(0);
	});
});

describe('symptom shortcuts (1.10, 1.11)', () => {
	it('renders the four shortcuts on an empty input, each with its armed digit', async () => {
		renderAsk();
		await tick();
		expect(SYMPTOM_SHORTCUTS).toEqual(['no sound', 'distorting', 'latency', 'wrong drum sound']);
		for (const [index, label] of SYMPTOM_SHORTCUTS.entries()) {
			const button = screen.getByRole('button', { name: new RegExp(`${index + 1}.*${label}`) });
			expect(button).toBeTruthy();
		}
	});

	it('submits in one keypress via the arming registry', async () => {
		const { textarea } = renderAsk();
		await tick();
		// Focus rests in the input (1.1); the keypress must still select.
		textarea.dispatchEvent(new KeyboardEvent('keydown', { key: '1', bubbles: true, cancelable: true }));
		await tick();
		expect(engine.submit).toHaveBeenCalledOnce();
		expect(engine.requests[0].question).toBe('no sound');
	});

	it('submits equally by pointer', async () => {
		renderAsk();
		await tick();
		await fireEvent.click(screen.getByRole('button', { name: /distorting/ }));
		expect(engine.requests[0]?.question).toBe('distorting');
	});

	it('disappears and disarms once the input is not empty', async () => {
		renderAsk();
		await type('why');
		expect(screen.queryByRole('button', { name: /no sound/ })).toBeNull();
		document.body.dispatchEvent(
			new KeyboardEvent('keydown', { key: '1', bubbles: true, cancelable: true })
		);
		await tick();
		expect(engine.submit).not.toHaveBeenCalled();
		expect(thread.draft).toBe('why1'); // the digit types normally (1.11)
	});

	it('is not offered while a turn is streaming', async () => {
		renderAsk();
		await type('no sound');
		thread.submit();
		await tick();
		expect(screen.queryByRole('button', { name: /distorting/ })).toBeNull();
	});
});

describe('empty scope blocks submission (3.2)', () => {
	it('states it, offers select-all in one activation, and preserves the text', async () => {
		scope.selectNone();
		const { textarea } = renderAsk();
		await type('kick is distorting');
		await fireEvent.keyDown(textarea, { key: 'Enter' });
		expect(engine.submit).not.toHaveBeenCalled();
		expect(screen.getByText(/no sources are selected/i)).toBeTruthy();
		await fireEvent.click(screen.getByRole('button', { name: /select all/i }));
		expect(scope.canSubmit).toBe(true);
		expect(thread.draft).toBe('kick is distorting');
		expect(screen.queryByText(/no sources are selected/i)).toBeNull();
	});
});

describe('the 1000-character limit (9.15)', () => {
	it('blocks the submit, states the limit and the typed length, and stays editable', async () => {
		const { textarea } = renderAsk();
		await type('x'.repeat(QUESTION_LIMIT + 25));
		await fireEvent.keyDown(textarea, { key: 'Enter' });
		expect(engine.submit).not.toHaveBeenCalled();
		const notice = screen.getByText(new RegExp(`${QUESTION_LIMIT}`));
		expect(notice.textContent).toContain(String(QUESTION_LIMIT + 25));
		expect(textarea.disabled).toBe(false);
	});
});

describe('follow-ups and the fresh thread (1.7, 1.8)', () => {
	it('indicates a follow-up and starts a context-free thread in one control', async () => {
		renderAsk();
		await type('no sound');
		thread.submit();
		await tick();
		expect(screen.getByText(/follow-up/i)).toBeTruthy();
		await fireEvent.click(screen.getByRole('button', { name: /new question/i }));
		expect(thread.turns).toHaveLength(0);
		expect(screen.queryByText(/follow-up/i)).toBeNull();
	});
});

describe('stopping a streaming answer (1.9, 8.6)', () => {
	it('offers a keyboard-reachable stop that retains the text and restores the question', async () => {
		const { textarea } = renderAsk();
		await type('no sound');
		thread.submit();
		const channel = await lastChannel();
		channel.emit('body_delta', { text: 'What arrived so far' });
		const turn = thread.turns[0];
		await vi.waitFor(() => expect(turn.state).toBe('streaming'));
		await tick();

		const stop = screen.getByRole('button', { name: /stop/i });
		await fireEvent.click(stop);
		await vi.waitFor(() => expect(thread.busy).toBe(false));
		expect(turn.envelope.body).toBe('What arrived so far'); // retained (1.9)
		expect(thread.draft).toBe('no sound'); // ready state, question preserved (8.6)
		expect(document.activeElement).toBe(textarea);
	});
});

describe('completion (1.6)', () => {
	it('returns focus to an empty input without discarding the answer', async () => {
		const { textarea } = renderAsk();
		await type('no sound');
		await fireEvent.keyDown(textarea, { key: 'Enter' });
		const elsewhere = document.createElement('button');
		document.body.appendChild(elsewhere);
		elsewhere.focus();

		const channel = await lastChannel();
		channel.emit('outcome', { outcome: 'answered' });
		channel.emit('direct_answer', { text: 'Unmute the master track.' });
		channel.emit('done', {});
		channel.close();
		await vi.waitFor(() => expect(thread.turns[0].state).toBe('settled'));
		await tick();
		expect(document.activeElement).toBe(textarea);
		expect(thread.draft).toBe('');
		expect(thread.turns[0].envelope.direct_answer).toBe('Unmute the master track.');
	});
});

describe('losing window focus changes nothing (1.12)', () => {
	it('streams to completion and retains everything while blurred', async () => {
		const { textarea } = renderAsk();
		await type('no sound');
		await fireEvent.keyDown(textarea, { key: 'Enter' });
		window.dispatchEvent(new FocusEvent('blur'));
		const channel = await lastChannel();
		channel.emit('outcome', { outcome: 'answered' });
		channel.emit('body_delta', { text: 'The whole answer.' });
		channel.emit('done', {});
		channel.close();
		await vi.waitFor(() => expect(thread.turns[0].state).toBe('settled'));
		expect(thread.turns[0].envelope.body).toBe('The whole answer.');
		expect(thread.turns[0].question).toBe('no sound');
		expect(scope.selected).toEqual(['src/a', 'src/b']);
	});
});

describe('the thread shell (1.4)', () => {
	it('keeps the submitted text inspectable and re-editable', async () => {
		render(ThreadView, { props: { thread } });
		thread.submit('kick is distorting');
		await tick();
		const question = screen.getByRole('button', { name: /kick is distorting/ });
		await fireEvent.click(question);
		expect(thread.draft).toBe('kick is distorting');
	});

	it('renders the arrived answer text of a settled turn', async () => {
		render(ThreadView, { props: { thread } });
		thread.submit('no sound');
		const channel = await lastChannel();
		channel.emit('outcome', { outcome: 'answered' });
		channel.emit('direct_answer', { text: 'Unmute the master track.' });
		channel.emit('body_delta', { text: 'The routing panel hides mutes.' });
		channel.emit('done', {});
		channel.close();
		await vi.waitFor(() => expect(thread.turns[0].state).toBe('settled'));
		await tick();
		expect(screen.getByText('Unmute the master track.')).toBeTruthy();
		expect(screen.getByText(/routing panel hides mutes/)).toBeTruthy();
	});

	it('distinguishes a user stop from an engine abandonment (8.6, 9.16)', async () => {
		render(ThreadView, { props: { thread } });
		thread.submit('no sound');
		await lastChannel();
		thread.stop();
		await vi.waitFor(() => expect(thread.busy).toBe(false));
		await tick();
		expect(screen.getByText(/stopped/i)).toBeTruthy();

		thread.submit('again');
		const channel = await lastChannel();
		channel.emit('outcome', { outcome: 'cancelled' });
		channel.emit('done', {});
		channel.close();
		await vi.waitFor(() => expect(thread.turns[1].state).toBe('settled'));
		await tick();
		expect(screen.getByText(/abandoned/i)).toBeTruthy();
	});
});
