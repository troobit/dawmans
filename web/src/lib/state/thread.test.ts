// The thread store: the conversation on screen (requirements 1.4–1.9, 1.12,
// 3.1, 9.15; design "The turn, client-side" and "Surfaces"). Submission goes
// through the scope store's block and the turn state machine; the fetch stream
// has no relationship to window focus.

import { describe, expect, it, vi } from 'vitest';
import { fakeEngine } from '../testing/turn-channel';
import { QUESTION_LIMIT, ThreadStore } from './thread.svelte';

/** A fake scope store: two sources in scope unless narrowed here. */
function fakeScope(selected: string[] = ['src/a', 'src/b']) {
	return {
		selected,
		get canSubmit() {
			return this.selected.length > 0;
		},
		snapshot() {
			return [...this.selected];
		},
		noteQuestionSubmitted: vi.fn()
	};
}

/** A thread whose engine is a controllable channel; returns both ends. */
function makeThread(scope = fakeScope()) {
	const engine = fakeEngine();
	const record = vi.fn();
	const thread = new ThreadStore({ scope, history: { record }, submit: engine.submit });
	return { thread, scope, ...engine, record };
}

/** The channel serving the most recent submission, once the fetch has resolved. */
async function lastChannel(harness: ReturnType<typeof makeThread>) {
	await vi.waitFor(() => expect(harness.channels.length).toBeGreaterThan(0));
	return harness.channels[harness.channels.length - 1];
}

describe('submission guards', () => {
	it('an empty or whitespace-only submit does nothing and contacts no engine (1.5)', () => {
		const harness = makeThread();
		expect(harness.thread.submit('')).toBeNull();
		harness.thread.draft = '   \n\t ';
		expect(harness.thread.submit()).toBeNull();
		expect(harness.submit).not.toHaveBeenCalled();
		expect(harness.thread.turns).toHaveLength(0);
		expect(harness.thread.draft).toBe('   \n\t '); // typed text preserved
	});

	it('a zero-source scope blocks submission and preserves the typed text (3.1, 3.2)', () => {
		const harness = makeThread(fakeScope([]));
		harness.thread.draft = 'why is there no sound';
		expect(harness.thread.submit()).toBeNull();
		expect(harness.submit).not.toHaveBeenCalled();
		expect(harness.thread.draft).toBe('why is there no sound');
	});

	it('a question over 1000 characters is not submitted (9.15)', () => {
		const harness = makeThread();
		harness.thread.draft = 'x'.repeat(QUESTION_LIMIT + 1);
		expect(harness.thread.overLimit).toBe(true);
		expect(harness.thread.submit()).toBeNull();
		expect(harness.submit).not.toHaveBeenCalled();
		expect(harness.thread.draft).toHaveLength(QUESTION_LIMIT + 1); // still editable
	});

	it('a question of exactly 1000 characters submits', () => {
		const harness = makeThread();
		harness.thread.draft = 'x'.repeat(QUESTION_LIMIT);
		expect(harness.thread.submit()).not.toBeNull();
		expect(harness.submit).toHaveBeenCalledOnce();
	});
});

describe('a submitted turn', () => {
	it('is acknowledged synchronously, before any network activity (8.7)', () => {
		const harness = makeThread();
		harness.thread.draft = 'no sound from the drum module';
		const turn = harness.thread.submit();
		expect(turn?.state).toBe('acknowledged');
		expect(harness.thread.turns).toHaveLength(1);
	});

	it('retains the submitted text on the turn and empties the draft (1.4)', () => {
		const harness = makeThread();
		harness.thread.draft = 'kick is distorting';
		const turn = harness.thread.submit();
		expect(turn?.question).toBe('kick is distorting');
		expect(harness.thread.draft).toBe('');
	});

	it('carries the scope snapshot of ask time and notes the submission (3.9)', () => {
		const harness = makeThread();
		const turn = harness.thread.submit('latency');
		expect(turn?.scopeAtAsk).toEqual(['src/a', 'src/b']);
		expect(harness.scope.noteQuestionSubmitted).toHaveBeenCalledOnce();
		expect(harness.requests[0].sources).toEqual(['src/a', 'src/b']);
	});

	it('an explicit question (a shortcut) leaves the draft alone', () => {
		const harness = makeThread();
		harness.thread.draft = '';
		harness.thread.submit('no sound');
		expect(harness.thread.draft).toBe('');
	});
});

describe('conversation continuity (1.7, Decision 8)', () => {
	it('starts a conversation with null and follows up with one minted id', async () => {
		const harness = makeThread();
		harness.thread.submit('no sound');
		const first = await lastChannel(harness);
		first.emit('outcome', { outcome: 'answered' });
		first.emit('done', {});
		first.close();
		await vi.waitFor(() => expect(harness.thread.turns[0].state).toBe('settled'));

		harness.thread.submit('what about the hi-hat');
		await vi.waitFor(() => expect(harness.requests).toHaveLength(2));
		harness.thread.submit('and the snare');
		await vi.waitFor(() => expect(harness.requests).toHaveLength(3));

		expect(harness.requests[0].conversation_id).toBeNull();
		expect(harness.requests[1].conversation_id).not.toBeNull();
		expect(harness.requests[2].conversation_id).toBe(harness.requests[1].conversation_id);
	});

	it('is a follow-up exactly while an exchange is on screen (1.7)', () => {
		const harness = makeThread();
		expect(harness.thread.isFollowUp).toBe(false);
		harness.thread.submit('no sound');
		expect(harness.thread.isFollowUp).toBe(true);
	});

	it('clear() discards the thread and the next question is context-free (1.7)', async () => {
		const harness = makeThread();
		harness.thread.submit('no sound');
		await lastChannel(harness);
		harness.thread.draft = 'half-typed follow-up';
		harness.thread.clear();
		expect(harness.thread.turns).toHaveLength(0);
		expect(harness.thread.draft).toBe('half-typed follow-up'); // typed text survives
		harness.thread.submit('fresh question');
		await vi.waitFor(() => expect(harness.requests).toHaveLength(2));
		expect(harness.requests[1].conversation_id).toBeNull();
	});
});

describe('stopping and completion', () => {
	it('a user stop retains whatever text arrived and ends the turn as cancelled (1.9, 8.6)', async () => {
		const harness = makeThread();
		const turn = harness.thread.submit('no sound')!;
		const channel = await lastChannel(harness);
		channel.emit('direct_answer', { text: 'Check the master fader.' });
		channel.emit('body_delta', { text: 'The output routing may' });
		await vi.waitFor(() => expect(turn.state).toBe('streaming'));

		harness.thread.stop();
		await vi.waitFor(() => expect(harness.thread.busy).toBe(false));
		expect(turn.userCancelled).toBe(true);
		expect(turn.envelope.outcome).toBe('cancelled');
		expect(turn.envelope.direct_answer).toBe('Check the master fader.');
		expect(turn.envelope.body).toContain('The output routing may');
		expect(harness.thread.turns).toHaveLength(1); // the turn stays inspectable
	});

	it('stop with nothing streaming does nothing', () => {
		const harness = makeThread();
		expect(() => harness.thread.stop()).not.toThrow();
	});

	it('an engine cancellation is not a user stop (9.16)', async () => {
		const harness = makeThread();
		const turn = harness.thread.submit('no sound')!;
		const channel = await lastChannel(harness);
		channel.emit('body_delta', { text: 'partial' });
		channel.emit('outcome', { outcome: 'cancelled' });
		channel.emit('done', {});
		channel.close();
		await vi.waitFor(() => expect(turn.state).toBe('settled'));
		expect(turn.userCancelled).toBe(false);
		expect(turn.envelope.outcome).toBe('cancelled');
		expect(turn.envelope.body).toBe('partial');
	});

	it('done settles the turn, records history, and calls onSettled (1.6, 12.1)', async () => {
		const harness = makeThread();
		const onSettled = vi.fn();
		harness.thread.onSettled = onSettled;
		const turn = harness.thread.submit('no sound')!;
		const channel = await lastChannel(harness);
		channel.emit('outcome', { outcome: 'answered' });
		channel.emit('direct_answer', { text: 'Unmute the master track.' });
		channel.emit('done', {});
		channel.close();
		await vi.waitFor(() => expect(turn.state).toBe('settled'));
		// 6.7: recorded with the thread it belongs to — the minted conversation id.
		expect(harness.record).toHaveBeenCalledWith(turn, expect.any(String));
		expect(onSettled).toHaveBeenCalledOnce();
		// 1.6: the answer just rendered is not discarded.
		expect(harness.thread.turns).toHaveLength(1);
		expect(turn.envelope.direct_answer).toBe('Unmute the master track.');
	});

	it('a stream that drops without done fails the turn and keeps the partial text (9.14)', async () => {
		const harness = makeThread();
		const turn = harness.thread.submit('no sound')!;
		const channel = await lastChannel(harness);
		channel.emit('body_delta', { text: 'half an answer' });
		await vi.waitFor(() => expect(turn.state).toBe('streaming'));
		channel.close();
		await vi.waitFor(() => expect(turn.state).toBe('failed'));
		expect(turn.incomplete).toBe(true);
		expect(turn.envelope.body).toBe('half an answer');
	});

	it('a transport failure mid-stream fails the turn as incomplete (9.14)', async () => {
		const harness = makeThread();
		const turn = harness.thread.submit('no sound')!;
		const channel = await lastChannel(harness);
		channel.emit('body_delta', { text: 'half' });
		await vi.waitFor(() => expect(turn.state).toBe('streaming'));
		channel.abort(); // the connection dropping, not a user stop
		await vi.waitFor(() => expect(turn.state).toBe('failed'));
		expect(turn.userCancelled).toBe(false);
		expect(turn.envelope.outcome).toBe('incomplete');
		expect(turn.envelope.body).toBe('half');
	});
});

describe('losing window focus changes nothing (1.12)', () => {
	it('the stream runs to completion while the window is blurred', async () => {
		const harness = makeThread();
		const turn = harness.thread.submit('no sound')!;
		const channel = await lastChannel(harness);
		// The user returns to the DAW: nothing on the thread listens to focus.
		window.dispatchEvent(new FocusEvent('blur'));
		document.dispatchEvent(new Event('visibilitychange'));
		channel.emit('outcome', { outcome: 'answered' });
		channel.emit('body_delta', { text: 'Answer text.' });
		channel.emit('done', {});
		channel.close();
		await vi.waitFor(() => expect(turn.state).toBe('settled'));
		expect(turn.envelope.body).toBe('Answer text.');
		expect(turn.question).toBe('no sound');
		expect(turn.scopeAtAsk).toEqual(['src/a', 'src/b']);
	});
});
