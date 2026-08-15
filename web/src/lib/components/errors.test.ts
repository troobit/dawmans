// The error states (requirements §9; CONTRACTS §6/§6a; design "Coverage
// failure, errors, and the outcome table" and "Error Handling"). Every state
// speaks plainly and offers an action; branching keys on `outcome` and the
// `reason` sub-code, never on the wording in `detail`, which renders only
// behind the 9.3 disclosure — alongside `framing`, `timings` and the client's
// per-turn marks, and nothing else.

import { cleanup, fireEvent, render, screen } from '@testing-library/svelte';
import { tick } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { EngineRejection } from '../engine/client';
import { TURN_STREAM_VERSION } from '../engine/records';
import { UnknownStreamVersionError } from '../engine/sse';
import { ScopeStore } from '../state/scope.svelte';
import { ThreadStore } from '../state/thread.svelte';
import { fakeEngine, type FakeEngine } from '../testing/turn-channel';
import ThreadView from './ThreadView.svelte';

const ALL_SOURCES = ['live/manual', 'ghost/manual', 'authored/triage'];

let engine: FakeEngine;
let scope: ScopeStore;
let thread: ThreadStore;

beforeEach(() => {
	localStorage.clear();
	sessionStorage.clear();
	engine = fakeEngine();
	scope = new ScopeStore();
	scope.load(ALL_SOURCES);
	thread = new ThreadStore({ scope, submit: engine.submit });
});

afterEach(() => {
	vi.useRealTimers();
	cleanup();
	document.body.innerHTML = '';
});

/** Enough microtask turns for the channel's frames to drain, timer-free. */
async function flush(): Promise<void> {
	for (let i = 0; i < 20; i += 1) await Promise.resolve();
	await tick();
}

/** Submit and settle a turn whose outcome event carries the given payload. */
async function settle(
	outcome: Record<string, unknown>,
	events: Array<[string, unknown]> = [],
	props: Record<string, unknown> = {},
	question = 'why is the kick distorting?'
) {
	const result = render(ThreadView, { props: { thread, scope, ...props } });
	thread.submit(question);
	await flush();
	const channel = engine.channels.at(-1)!;
	channel.emit('outcome', outcome);
	for (const [event, data] of events) channel.emit(event, data);
	channel.emit('done', { complete: true });
	channel.close();
	await flush();
	return result;
}

/** Submit a turn whose engine call rejects with the given error. */
async function reject(error: unknown, question = 'no sound') {
	const failing = new ThreadStore({ scope, submit: vi.fn(() => Promise.reject(error)) });
	const result = render(ThreadView, { props: { thread: failing, scope } });
	failing.submit(question);
	await vi.waitFor(() => expect(failing.turns.at(-1)?.state).toBe('failed'));
	await tick();
	return { ...result, thread: failing };
}

describe('plain language and at least one action (9.1, 9.2, 9.18)', () => {
	it('never shows raw exception text as the primary message, and always offers an action', async () => {
		const { container } = await settle({
			outcome: 'provider-unreachable',
			detail: 'ECONNREFUSED 127.0.0.1:11434\n  at TCPConnectWrap.afterConnect'
		});
		const summary = container.querySelector('.error .summary');
		expect(summary).not.toBeNull();
		expect(summary?.textContent).not.toContain('ECONNREFUSED');
		expect(summary?.textContent).not.toContain('TCPConnectWrap');
		// 9.18: the one-line summary and an activatable control, both in the state.
		expect(container.querySelectorAll('.error button').length).toBeGreaterThan(0);
	});
});

describe('the diagnostic disclosure (9.3)', () => {
	it('renders exactly detail, framing and timings plus the per-turn marks — never the request', async () => {
		const timings = {
			retrieval_ms: 12,
			state_acquisition_ms: 3,
			engine_overhead_ms: 8,
			first_token_ms: 900,
			completion_ms: 2100
		};
		const { container } = await settle(
			{ outcome: 'provider-error', reason: 'provider-rejected', detail: 'upstream 500: model overloaded' },
			[
				['framing', { framing: 'unparsed' }],
				['timings', timings]
			]
		);
		const disclosure = container.querySelector('details.diagnostics');
		expect(disclosure).not.toBeNull();
		expect(disclosure?.textContent).toContain('upstream 500: model overloaded');
		expect(disclosure?.textContent).toContain('unparsed');
		expect(disclosure?.textContent).toContain('retrieval_ms');
		expect(disclosure?.textContent).toContain('12');
		expect(disclosure?.textContent).toMatch(/submit/i);
		// Nothing else: the question never appears in diagnostics (9.17 is structural).
		expect(disclosure?.textContent).not.toContain('why is the kick distorting?');
	});

	it('is available on a successful turn carrying framing: unparsed', async () => {
		const { container } = await settle({ outcome: 'answered' }, [
			['direct_answer', { text: 'Unmute the master track.' }],
			['framing', { framing: 'unparsed' }]
		]);
		expect(container.querySelector('.answer')).not.toBeNull();
		expect(container.querySelector('details.diagnostics')).not.toBeNull();
	});

	it('is absent from a clean answered turn', async () => {
		const { container } = await settle({ outcome: 'answered' }, [
			['direct_answer', { text: 'Unmute the master track.' }]
		]);
		expect(container.querySelector('details.diagnostics')).toBeNull();
	});
});

describe('provider-unconfigured keys on the reason sub-code (9.5)', () => {
	it.each([
		['no-provider-kind', /no provider/i],
		['missing-credential', /key|credential/i],
		['disclosure-unacknowledged', /disclosure|acknowledg/i]
	] as const)('states the %s case from the sub-code, never the detail wording', async (reason, wording) => {
		const onconfigure = vi.fn();
		const { container } = await settle(
			// The detail deliberately describes a different case: the branch must
			// key on the sub-code alone.
			{ outcome: 'provider-unconfigured', reason, detail: 'everything is fine actually' },
			[],
			{ onconfigure }
		);
		expect(container.querySelector('.error .summary')?.textContent).toMatch(wording);

		// The control opens provider configuration, preserving the typed question.
		await fireEvent.click(screen.getByRole('button', { name: /provider|configur/i }));
		expect(onconfigure).toHaveBeenCalledOnce();
		expect(thread.draft).toBe('why is the kick distorting?');
	});
});

describe('provider-unreachable (9.6)', () => {
	it('names the provider, offers retry, and is distinct from a coverage failure', async () => {
		const { container } = await settle(
			{ outcome: 'provider-unreachable' },
			[],
			{ providerName: 'Ollama' }
		);
		expect(container.querySelector('.error .summary')?.textContent).toContain('Ollama');
		expect(container.querySelector('.coverage-failure')).toBeNull();

		await fireEvent.click(screen.getByRole('button', { name: /retry/i }));
		expect(engine.requests).toHaveLength(2);
		expect(engine.requests[1].question).toBe('why is the kick distorting?');
	});
});

describe('timeout attributes the stall to the provider, apart from unreachable (9.7)', () => {
	it('says the provider stalled and offers retry', async () => {
		const { container } = await settle({ outcome: 'timeout' }, [], { providerName: 'Ollama' });
		const summary = container.querySelector('.error .summary')?.textContent ?? '';
		expect(summary).toMatch(/stall/i);
		expect(summary).not.toMatch(/unreachable/i);
		expect(screen.getByRole('button', { name: /retry/i })).toBeTruthy();
	});
});

describe('provider-rate-limited (9.8)', () => {
	it('counts retry_after down and enables retry when it elapses', async () => {
		vi.useFakeTimers();
		const { container } = await settle({ outcome: 'provider-rate-limited', retry_after: 4 });
		const retry = screen.getByRole('button', { name: /retry/i }) as HTMLButtonElement;
		expect(retry.disabled).toBe(true);
		expect(container.querySelector('.error')?.textContent).toMatch(/4/);

		vi.advanceTimersByTime(2000);
		await tick();
		expect(container.querySelector('.error')?.textContent).toMatch(/2/);
		expect((screen.getByRole('button', { name: /retry/i }) as HTMLButtonElement).disabled).toBe(
			true
		);

		vi.advanceTimersByTime(2000);
		await tick();
		expect((screen.getByRole('button', { name: /retry/i }) as HTMLButtonElement).disabled).toBe(
			false
		);
	});

	it('says so honestly when the provider gave no interval — never inventing one, never a fault', async () => {
		const { container } = await settle({ outcome: 'provider-rate-limited' });
		const state = container.querySelector('.error')!;
		expect(state.textContent).toMatch(/rate.?limit/i);
		expect(state.textContent).toMatch(/did not (say|state)|no interval|not say how long/i);
		// No invented countdown, and retry is immediately available.
		expect((screen.getByRole('button', { name: /retry/i }) as HTMLButtonElement).disabled).toBe(
			false
		);
	});
});

describe('provider-error (9.9, 9.10)', () => {
	it('provider-rejected states the rejection with detail behind the disclosure, and retries', async () => {
		const { container } = await settle({
			outcome: 'provider-error',
			reason: 'provider-rejected',
			detail: 'model refused the sampling parameters'
		});
		const summary = container.querySelector('.error .summary')?.textContent ?? '';
		expect(summary).toMatch(/failed|rejected/i);
		expect(summary).not.toContain('model refused the sampling parameters');
		expect(container.querySelector('details.diagnostics')?.textContent).toContain(
			'model refused the sampling parameters'
		);
		expect(screen.getByRole('button', { name: /retry/i })).toBeTruthy();
	});

	it('authentication-failed offers configuration in place of retry, keyed on the sub-code alone', async () => {
		const onconfigure = vi.fn();
		const { container } = await settle(
			{ outcome: 'provider-error', reason: 'authentication-failed', detail: 'try again later' },
			[],
			{ onconfigure }
		);
		expect(container.querySelector('.error .summary')?.textContent).toMatch(
			/credential|key|authentication/i
		);
		// A retry on the same credential cannot succeed: configuration instead.
		expect(screen.queryByRole('button', { name: /retry/i })).toBeNull();
		await fireEvent.click(screen.getByRole('button', { name: /provider|configur/i }));
		expect(onconfigure).toHaveBeenCalledOnce();
	});
});

describe('unknown-source-id (9.11)', () => {
	it('names the rejected id, drops it from the stored scope, and re-asks the remainder in one activation', async () => {
		const { container } = await settle({ outcome: 'unknown-source-id' }, [
			['scope_dropped', [{ source_id: 'ghost/manual', display_name: 'Ghost Manual' }]]
		]);
		expect(container.querySelector('.error')?.textContent).toContain('Ghost Manual');
		// Dropped from the stored scope (3.8).
		expect(scope.isSelected('ghost/manual')).toBe(false);

		await fireEvent.click(screen.getByRole('button', { name: /re-ask/i }));
		expect(engine.requests).toHaveLength(2);
		expect(engine.requests[1].question).toBe('why is the kick distorting?');
		expect(engine.requests[1].sources).not.toContain('ghost/manual');
		expect(engine.requests[1].sources).toContain('live/manual');
	});

	it('drops once — a later re-selection by the user is not vetoed', async () => {
		await settle({ outcome: 'unknown-source-id' }, [
			['scope_dropped', [{ source_id: 'ghost/manual', display_name: 'Ghost Manual' }]]
		]);
		expect(scope.isSelected('ghost/manual')).toBe(false);

		// 3.8/9.11 describe a one-time drop, not a standing suppression: with the
		// turn still on screen, putting the source back must stick.
		scope.toggle('ghost/manual');
		await tick();
		expect(scope.isSelected('ghost/manual')).toBe(true);
	});
});

describe('no-sources-selected renders as the empty-scope state (9.12)', () => {
	it('is the 3.2 state with select-all, never an unexplained failure', async () => {
		const { container } = await settle({ outcome: 'no-sources-selected' });
		const state = container.querySelector('.empty-scope');
		expect(state).not.toBeNull();
		expect(state?.textContent).toMatch(/no sources/i);
		expect(container.querySelector('.error')).toBeNull();

		await fireEvent.click(screen.getByRole('button', { name: /select all/i }));
		for (const id of ALL_SOURCES) expect(scope.isSelected(id)).toBe(true);
	});
});

describe('corpus-empty (9.13)', () => {
	it('names the manuals/ directory and the ingestion step, with nothing to retry', async () => {
		const { container } = await settle({ outcome: 'corpus-empty' });
		const state = container.querySelector('.error')!;
		expect(state.textContent).toContain('manuals/');
		expect(state.textContent).toMatch(/ingest/i);
		// A retry against an empty corpus is not an action; none is offered.
		expect(screen.queryByRole('button', { name: /retry/i })).toBeNull();
	});
});

describe('incomplete retains and marks the partial text with a retry (9.14)', () => {
	it('handles the engine-reported incomplete outcome', async () => {
		const { container } = await settle({ outcome: 'incomplete' }, [
			['body_delta', { text: 'The first half of the answer.' }]
		]);
		expect(container.textContent).toContain('The first half of the answer.');
		expect(container.querySelector('.incomplete-note')).not.toBeNull();
		await fireEvent.click(screen.getByRole('button', { name: /retry/i }));
		expect(engine.requests).toHaveLength(2);
		expect(engine.requests[1].question).toBe('why is the kick distorting?');
	});

	it('handles a stream that drops mid-answer without done', async () => {
		const { container } = render(ThreadView, { props: { thread, scope } });
		thread.submit('no sound');
		await flush();
		const channel = engine.channels.at(-1)!;
		channel.emit('outcome', { outcome: 'answered' });
		channel.emit('body_delta', { text: 'What arrived before the drop.' });
		channel.close();
		await vi.waitFor(() => expect(thread.turns.at(-1)?.state).toBe('failed'));
		await tick();

		expect(container.textContent).toContain('What arrived before the drop.');
		expect(container.querySelector('.incomplete-note')).not.toBeNull();
		expect(screen.getByRole('button', { name: /retry/i })).toBeTruthy();
	});
});

describe('a malformed-request rejection is broken, never a refusal (9.15)', () => {
	it('names what was rejected', async () => {
		const { container } = await reject(
			new EngineRejection(422, 'question-too-long', { rejected: 'question-too-long' })
		);
		const state = container.querySelector('.broken');
		expect(state).not.toBeNull();
		expect(state?.textContent).toContain('question-too-long');
		expect(container.querySelector('.coverage-failure')).toBeNull();
		expect(container.querySelectorAll('.broken button').length).toBeGreaterThan(0);
	});
});

describe('an engine-reported cancelled the user did not issue is abandoned (9.16)', () => {
	it('retains the text, marks it apart from incomplete and error, and leaves the replacing turn alone', async () => {
		const { container } = render(ThreadView, { props: { thread, scope } });
		thread.submit('no sound');
		await flush();
		const first = engine.channels.at(-1)!;
		first.emit('outcome', { outcome: 'answered' });
		first.emit('body_delta', { text: 'Superseded text.' });
		await flush();

		// A new question arrives; the engine cancels the previous turn itself.
		thread.submit('still no sound');
		await flush();
		first.emit('outcome', { outcome: 'cancelled' });
		first.emit('done', { complete: true });
		first.close();
		const second = engine.channels.at(-1)!;
		second.emit('outcome', { outcome: 'answered' });
		second.emit('direct_answer', { text: 'Check the master bus.' });
		second.emit('done', { complete: true });
		second.close();
		await vi.waitFor(() => expect(thread.turns.at(-1)?.state).toBe('settled'));
		await tick();

		// The abandoned turn: text retained, marked, not an error, not incomplete.
		const abandoned = container.querySelectorAll('.turn')[0];
		expect(abandoned.textContent).toContain('Superseded text.');
		expect(abandoned.querySelector('.abandoned-note')).not.toBeNull();
		expect(abandoned.querySelector('.error')).toBeNull();
		expect(abandoned.querySelector('.incomplete-note')).toBeNull();
		// The replacing turn is undisturbed.
		const replacing = container.querySelectorAll('.turn')[1];
		expect(replacing.textContent).toContain('Check the master bus.');
		expect(replacing.querySelector('.abandoned-note')).toBeNull();
	});
});

describe('no message contains any part of a key (9.17)', () => {
	it('keeps a leaked-looking detail out of every primary message', async () => {
		const { container } = await settle({
			outcome: 'provider-error',
			reason: 'provider-rejected',
			detail: 'auth header sk-live-abc123 rejected'
		});
		expect(container.querySelector('.error .summary')?.textContent).not.toContain('sk-live-abc123');
		// Structural: the renderer composes from fixed wording and typed fields;
		// the engine's own wording stays behind the disclosure.
		expect(container.querySelector('details.diagnostics')?.textContent).toContain(
			'sk-live-abc123'
		);
	});
});

describe('an unknown turn-stream version renders broken naming both versions (9.19)', () => {
	it('names the declared and the known version', async () => {
		const { container } = await reject(
			new UnknownStreamVersionError('dawmans/turn-stream/2', TURN_STREAM_VERSION)
		);
		const state = container.querySelector('.broken');
		expect(state).not.toBeNull();
		expect(state?.textContent).toContain('dawmans/turn-stream/2');
		expect(state?.textContent).toContain(TURN_STREAM_VERSION);
	});
});

describe('an outcome outside the taxonomy renders broken carrying detail (9.4)', () => {
	it('is never trusted to a renderer, and its detail sits behind the disclosure', async () => {
		const { container } = await settle({
			outcome: 'quantum-flux',
			detail: 'a member from the future'
		});
		expect(container.querySelector('.broken')).not.toBeNull();
		expect(container.querySelector('.answer')).toBeNull();
		expect(container.querySelector('details.diagnostics')?.textContent).toContain(
			'a member from the future'
		);
	});
});
