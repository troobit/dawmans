// The waiting states, thresholds and perf marks (requirements §8, 11.9, 13.5,
// 13.6; design "The turn, client-side", "Legibility, colour and motion";
// Decisions 2 and 7). Acknowledgement is synchronous in the submit handler;
// the working indicator is live, sits below the thread, and escalates past a
// per-provider-class threshold; reduced motion swaps the animation for an
// elapsed-seconds counter excluded from the announcement region; the marks
// measure 8.8 and 8.9 client-side. Real-provider p95 measurement is the
// iterative loop, not this suite.

import { cleanup, fireEvent, render, screen } from '@testing-library/svelte';
import { tick } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { measures, SLOW_THRESHOLD_MS } from '../state/perf.svelte';
import { ScopeStore } from '../state/scope.svelte';
import { ThreadStore } from '../state/thread.svelte';
import { fakeEngine, type FakeEngine } from '../testing/turn-channel';
import ThreadView from './ThreadView.svelte';

const ALL_SOURCES = ['live/manual', 'authored/triage'];

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

/** The channel of the most recent submit; the stub creates it synchronously. */
function lastChannel() {
	const channel = engine.channels.at(-1);
	if (channel === undefined) throw new Error('no turn was submitted');
	return channel;
}

describe('acknowledgement (8.1, 8.7)', () => {
	it('enters acknowledged synchronously in the submit handler, before fetch is called', () => {
		// Decision: the acknowledgement paint never waits on the network, so the
		// state must exist by the time the engine is first contacted.
		let stateAtFetch: string | undefined;
		const observed: ThreadStore = new ThreadStore({
			scope,
			submit: vi.fn((request, signal) => {
				stateAtFetch = observed.turns.at(-1)?.state;
				return engine.submit(request, signal);
			})
		});

		const turn = observed.submit('no sound');
		expect(turn).not.toBeNull();
		expect(stateAtFetch).toBe('acknowledged');
		// Synchronously acknowledged on return, before any await.
		expect(turn!.state).toBe('acknowledged');
	});

	it('paints the acknowledged turn — question and working state — before any engine response', async () => {
		const { container } = render(ThreadView, { props: { thread, scope } });
		thread.submit('no sound');
		await tick();
		// No event has been emitted on the channel: the engine has said nothing.
		expect(container.textContent).toContain('no sound');
		expect(container.querySelector('.state')?.textContent).toMatch(/working/i);
	});
});

describe('the working indicator (8.2, 8.3, Decision 2)', () => {
	it('shows an unmistakably live indicator while waiting for first content', async () => {
		const { container } = render(ThreadView, { props: { thread, scope } });
		thread.submit('no sound');
		await tick();
		const indicator = container.querySelector('.working-indicator');
		expect(indicator).not.toBeNull();
		// Live by animation in the default case (Decision 7 covers reduced motion).
		expect(indicator?.querySelector('[data-animated="true"]')).not.toBeNull();
	});

	it('sits below the thread, so its removal cannot shift painted text', async () => {
		const { container } = render(ThreadView, { props: { thread, scope } });
		thread.submit('no sound');
		await tick();
		const turnElement = container.querySelector('.turn')!;
		const indicator = container.querySelector('.working-indicator')!;
		expect(
			turnElement.compareDocumentPosition(indicator) & Node.DOCUMENT_POSITION_FOLLOWING
		).toBeTruthy();
	});

	it('keeps the submitted question visible while waiting (8.3)', async () => {
		const { container } = render(ThreadView, { props: { thread, scope } });
		thread.submit('why is the kick distorting?');
		await tick();
		expect(container.querySelector('.question')?.textContent).toContain(
			'why is the kick distorting?'
		);
	});

	it('is replaced the moment first content exists', async () => {
		const { container } = render(ThreadView, { props: { thread, scope } });
		thread.submit('no sound');
		await tick();
		const channel = lastChannel();
		channel.emit('outcome', { outcome: 'answered' });
		channel.emit('direct_answer', { text: 'Unmute the master track.' });
		await vi.waitFor(() => {
			expect(document.querySelector('.working-indicator')).toBeNull();
		});
		// The arriving text itself is the liveness now; nothing was lost.
		expect(container.textContent).toContain('Unmute the master track.');
	});

	it('does not exist at rest', () => {
		const { container } = render(ThreadView, { props: { thread, scope } });
		expect(container.querySelector('.working-indicator')).toBeNull();
	});
});

describe('working, finished and broken are mutually distinguishable (8.4, 8.11)', () => {
	async function stateChannels(): Promise<{ shape: string; label: string }> {
		await tick();
		const shape = document.querySelector('.state-shape');
		const label = document.querySelector('.state');
		expect(shape).not.toBeNull();
		expect(label).not.toBeNull();
		return { shape: shape!.textContent!.trim(), label: label!.textContent!.trim() };
	}

	it('signals each state by shape and text — two channels, never colour alone', async () => {
		// Working.
		render(ThreadView, { props: { thread, scope } });
		thread.submit('no sound');
		const working = await stateChannels();
		cleanup();
		document.body.innerHTML = '';

		// Finished.
		engine = fakeEngine();
		thread = new ThreadStore({ scope, submit: engine.submit });
		render(ThreadView, { props: { thread, scope } });
		thread.submit('no sound');
		let channel = lastChannel();
		channel.emit('outcome', { outcome: 'answered' });
		channel.emit('direct_answer', { text: 'Unmute.' });
		channel.emit('done', { complete: true });
		channel.close();
		await vi.waitFor(() => expect(thread.turns.at(-1)?.state).toBe('settled'));
		const finished = await stateChannels();
		cleanup();
		document.body.innerHTML = '';

		// Broken: the stream ends without done and without an arrived answer.
		engine = fakeEngine();
		thread = new ThreadStore({ scope, submit: engine.submit });
		render(ThreadView, { props: { thread, scope } });
		thread.submit('no sound');
		channel = lastChannel();
		channel.emit('outcome', { outcome: 'provider-unreachable' });
		channel.close();
		await vi.waitFor(() => expect(thread.turns.at(-1)?.state).toBe('failed'));
		const broken = await stateChannels();

		// Pairwise distinct on both channels.
		for (const [a, b] of [
			[working, finished],
			[working, broken],
			[finished, broken]
		]) {
			expect(a.shape).not.toBe(b.shape);
			expect(a.label).not.toBe(b.label);
		}
	});
});

describe('the per-provider-class threshold (8.5, 8.10)', () => {
	it('holds hosted at 3 s and local at 5 s, local above hosted, within the 8.10 bands', () => {
		// The tuning constants themselves: bands 2.5–4 s hosted, 4–8 s local.
		// Sitting above the class's observed median is the iterative loop's check.
		expect(SLOW_THRESHOLD_MS.hosted).toBe(3000);
		expect(SLOW_THRESHOLD_MS.local).toBe(5000);
		expect(SLOW_THRESHOLD_MS.hosted).toBeGreaterThanOrEqual(2500);
		expect(SLOW_THRESHOLD_MS.hosted).toBeLessThanOrEqual(4000);
		expect(SLOW_THRESHOLD_MS.local).toBeGreaterThanOrEqual(4000);
		expect(SLOW_THRESHOLD_MS.local).toBeLessThanOrEqual(8000);
		expect(SLOW_THRESHOLD_MS.local).toBeGreaterThan(SLOW_THRESHOLD_MS.hosted);
	});

	it('supplements with plain "taking longer than usual" text and a cancel control past the hosted threshold', async () => {
		vi.useFakeTimers();
		const { container } = render(ThreadView, {
			props: { thread, scope, providerClass: 'hosted' }
		});
		thread.submit('no sound');
		await tick();

		vi.advanceTimersByTime(2000);
		await tick();
		expect(container.textContent).not.toMatch(/taking longer than usual/i);
		expect(screen.queryByRole('button', { name: /cancel/i })).toBeNull();

		vi.advanceTimersByTime(1000);
		await tick();
		expect(container.textContent).toMatch(/taking longer than usual/i);
		expect(screen.getByRole('button', { name: /cancel/i })).toBeTruthy();
	});

	it('holds the local threshold at 5 s — a normal local wait never trips the hosted one', async () => {
		vi.useFakeTimers();
		const { container } = render(ThreadView, {
			props: { thread, scope, providerClass: 'local' }
		});
		thread.submit('no sound');
		await tick();

		vi.advanceTimersByTime(4000);
		await tick();
		expect(container.textContent).not.toMatch(/taking longer than usual/i);

		vi.advanceTimersByTime(1000);
		await tick();
		expect(container.textContent).toMatch(/taking longer than usual/i);
	});

	it('measures the threshold from each turn, not from the first — a follow-up mid-wait resets it', async () => {
		vi.useFakeTimers();
		const { container } = render(ThreadView, {
			props: { thread, scope, providerClass: 'hosted' }
		});
		thread.submit('no sound');
		await tick();

		// A follow-up while the first turn is still awaiting first content.
		vi.advanceTimersByTime(2000);
		await tick();
		thread.submit('still no sound');
		await tick();

		// 8.10: 3 s after *this* submission — the earlier turn's 2 s do not count.
		vi.advanceTimersByTime(2000);
		await tick();
		expect(container.textContent).not.toMatch(/taking longer than usual/i);

		vi.advanceTimersByTime(1000);
		await tick();
		expect(container.textContent).toMatch(/taking longer than usual/i);
	});

	it('cancel returns to ready with the question preserved, never presenting partial output as finished (8.6)', async () => {
		vi.useFakeTimers();
		render(ThreadView, { props: { thread, scope, providerClass: 'hosted' } });
		thread.submit('no sound');
		await tick();
		vi.advanceTimersByTime(3000);
		await tick();

		await fireEvent.click(screen.getByRole('button', { name: /cancel/i }));
		await vi.waitFor(async () => {
			await tick();
			expect(thread.active).toBeNull();
		});
		// Ready again, question preserved for re-editing.
		expect(thread.draft).toBe('no sound');
		// Never presented as finished.
		expect(document.querySelector('.state')?.textContent).not.toMatch(/finished/i);
		expect(document.querySelector('.state')?.textContent).toMatch(/stopped/i);
	});
});

describe('reduced motion (13.6, 11.9, Decision 7)', () => {
	it('replaces the animation with an elapsed-seconds counter paired with the static shape', async () => {
		vi.useFakeTimers();
		const { container } = render(ThreadView, {
			props: { thread, scope, reducedMotion: true }
		});
		thread.submit('no sound');
		await tick();

		const indicator = container.querySelector('.working-indicator')!;
		// No animation anywhere under reduced motion.
		expect(indicator.querySelector('[data-animated="true"]')).toBeNull();
		// The static shape still carries 8.4's shape channel.
		expect(indicator.querySelector('.state-shape')).not.toBeNull();

		// The counter is live without motion: it ticks once per second.
		const counter = indicator.querySelector('.elapsed');
		expect(counter).not.toBeNull();
		expect(counter?.textContent).toMatch(/\b0\b/);
		vi.advanceTimersByTime(3000);
		await tick();
		expect(indicator.querySelector('.elapsed')?.textContent).toMatch(/\b3\b/);
	});

	it('excludes the counter from the announcement region, so it never announces each tick', async () => {
		vi.useFakeTimers();
		const { container } = render(ThreadView, {
			props: { thread, scope, reducedMotion: true }
		});
		thread.submit('no sound');
		await tick();
		lastChannel().emit('outcome', { outcome: 'answered' });
		await tick();
		await tick();

		const region = container.querySelector('[aria-live="polite"]')!;
		const counter = container.querySelector('.elapsed');
		expect(counter).not.toBeNull();
		expect(region.contains(counter)).toBe(false);

		const announced = region.textContent;
		vi.advanceTimersByTime(2000);
		await tick();
		// Ticks change the counter, never the announcement.
		expect(region.textContent).toBe(announced);
	});

	it('carries no animation anywhere beyond the working indicator (11.9)', async () => {
		const { container } = render(ThreadView, { props: { thread, scope } });
		thread.submit('no sound');
		await tick();
		for (const animated of container.querySelectorAll('[data-animated="true"]')) {
			expect(animated.closest('.working-indicator')).not.toBeNull();
		}
	});
});

describe('announcements (13.5)', () => {
	it('holds exactly one polite region, and the streamed body stays aria-live off with aria-busy', async () => {
		const { container } = render(ThreadView, { props: { thread, scope } });
		thread.submit('no sound');
		await tick();
		const regions = container.querySelectorAll('[aria-live="polite"]');
		expect(regions).toHaveLength(1);

		const channel = lastChannel();
		channel.emit('outcome', { outcome: 'answered' });
		channel.emit('body_delta', { text: 'Check the master fader.' });
		await vi.waitFor(() => {
			expect(document.querySelector('.answer')).not.toBeNull();
		});
		const body = container.querySelector('.answer')!;
		expect(body.getAttribute('aria-live')).toBe('off');
		expect(body.getAttribute('aria-busy')).toBe('true');

		channel.emit('done', { complete: true });
		channel.close();
		await vi.waitFor(() => expect(thread.turns.at(-1)?.state).toBe('settled'));
		await tick();
		expect(container.querySelector('.answer')?.getAttribute('aria-busy')).not.toBe('true');
	});

	it('announces streaming once, not every fragment', async () => {
		const { container } = render(ThreadView, { props: { thread, scope } });
		thread.submit('no sound');
		await tick();
		const channel = lastChannel();
		channel.emit('outcome', { outcome: 'answered' });
		channel.emit('body_delta', { text: 'First fragment. ' });
		await vi.waitFor(() => {
			expect(container.querySelector('[aria-live="polite"]')?.textContent).toMatch(/streaming/i);
		});
		const announced = container.querySelector('[aria-live="polite"]')!.textContent;

		channel.emit('body_delta', { text: 'Second fragment. ' });
		channel.emit('body_delta', { text: 'Third fragment.' });
		await vi.waitFor(() => {
			expect(document.body.textContent).toContain('Third fragment.');
		});
		expect(container.querySelector('[aria-live="polite"]')!.textContent).toBe(announced);
	});

	it('announces completion and failure distinctly, once each', async () => {
		const { container } = render(ThreadView, { props: { thread, scope } });
		thread.submit('no sound');
		await tick();
		let channel = lastChannel();
		channel.emit('outcome', { outcome: 'answered' });
		channel.emit('done', { complete: true });
		channel.close();
		await vi.waitFor(() => {
			expect(container.querySelector('[aria-live="polite"]')?.textContent).toMatch(/finished/i);
		});

		thread.submit('still no sound');
		await tick();
		channel = lastChannel();
		channel.emit('outcome', { outcome: 'provider-unreachable' });
		channel.close();
		await vi.waitFor(() => {
			expect(container.querySelector('[aria-live="polite"]')?.textContent).toMatch(/failed/i);
		});
	});

	it('announces a coverage failure as its own state change', async () => {
		const { container } = render(ThreadView, { props: { thread, scope } });
		thread.submit('no sound');
		await tick();
		const channel = lastChannel();
		channel.emit('outcome', { outcome: 'refused-not-covered' });
		channel.emit('done', { complete: true });
		channel.close();
		await vi.waitFor(() => {
			expect(container.querySelector('[aria-live="polite"]')?.textContent).toMatch(/not cover/i);
		});
	});

	it('announces a partial answer as partial, not as finished', async () => {
		const { container } = render(ThreadView, { props: { thread, scope } });
		thread.submit('no sound');
		await tick();
		const channel = lastChannel();
		channel.emit('outcome', { outcome: 'partially-answered' });
		channel.emit('direct_answer', { text: 'Half of it.' });
		channel.emit('uncovered_parts', { parts: ['the other half'] });
		channel.emit('done', { complete: true });
		channel.close();
		await vi.waitFor(() => {
			expect(container.querySelector('[aria-live="polite"]')?.textContent).toMatch(/partial/i);
		});
	});

	it('announces narrowing with its candidates and that digits select them', async () => {
		const { container } = render(ThreadView, { props: { thread, scope } });
		thread.submit('no sound');
		await tick();
		const channel = lastChannel();
		channel.emit('outcome', { outcome: 'needs-narrowing' });
		channel.emit('narrowing', {
			question: 'Which output has no sound?',
			candidates: [
				{ label: 'The master meter moves', value: 'the master bus' },
				{ label: 'One track meter moves', value: 'a single track' }
			]
		});
		channel.emit('done', { complete: true });
		channel.close();
		await vi.waitFor(() => {
			const text = container.querySelector('[aria-live="polite"]')?.textContent ?? '';
			// The labels, which is what the controls read on screen — an
			// announcement of the `value` would name something not rendered.
			expect(text).toContain('The master meter moves');
			expect(text).toContain('One track meter moves');
			expect(text).toMatch(/number key|digit/i);
		});
	});
});

describe('perf marks (8.7–8.9; design "Measurement")', () => {
	it('stamps submit at construction, in the submit handler', () => {
		const before = performance.now();
		const turn = thread.submit('no sound')!;
		expect(turn.marks.submit).toBeGreaterThanOrEqual(before);
		expect(turn.marks.submit).toBeLessThanOrEqual(performance.now());
	});

	it('stamps firstByte when the first content event leaves the reader, and never again', async () => {
		const turn = thread.submit('no sound')!;
		const channel = lastChannel();
		// outcome is not content: the 8.8 measurement lands on direct_answer.
		channel.emit('outcome', { outcome: 'answered' });
		await vi.waitFor(() => expect(turn.state).toBe('streaming'));
		expect(turn.marks.firstByte).toBeUndefined();

		channel.emit('direct_answer', { text: 'Unmute the master track.' });
		await vi.waitFor(() => expect(turn.marks.firstByte).toBeDefined());
		const first = turn.marks.firstByte;

		channel.emit('body_delta', { text: 'More.' });
		await vi.waitFor(() => expect(turn.envelope.body).toContain('More.'));
		expect(turn.marks.firstByte).toBe(first);
	});

	it('stamps firstPaint in a requestAnimationFrame after the content is in the DOM', async () => {
		render(ThreadView, { props: { thread, scope } });
		const turn = thread.submit('no sound')!;
		const channel = lastChannel();
		channel.emit('outcome', { outcome: 'answered' });
		channel.emit('direct_answer', { text: 'Unmute the master track.' });
		await vi.waitFor(() => expect(turn.marks.firstPaint).toBeDefined());
		expect(turn.marks.firstPaint!).toBeGreaterThanOrEqual(turn.marks.firstByte!);
	});

	it('computes 8.8 as firstPaint − submit and 8.9 as firstPaint − firstByte', () => {
		expect(measures({ submit: 100, firstByte: 500, firstPaint: 560 })).toEqual({
			submitToFirstPaint: 460,
			firstByteToFirstPaint: 60
		});
		// Absent marks yield absent measures — never zero, never invented.
		expect(measures({ submit: 100 })).toEqual({});
		expect(measures({ submit: 100, firstByte: 500 })).toEqual({});
	});
});
