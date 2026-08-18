// The answer renderer (requirements 3.11, 4.1, 4.3–4.9, 4.12; design
// "Streaming without reflow" and the outcome table). Most tests drive a bare
// Turn through applyEvent — the reducer is the renderer's whole input; the
// re-ask and finished-state tests go through a ThreadStore over the stubbed
// engine because they exercise submission and settling.

import { cleanup, fireEvent, render, screen } from '@testing-library/svelte';
import { tick } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { Citation } from '../engine/records';
import { Turn } from '../engine/turn.svelte';
import { ScopeStore } from '../state/scope.svelte';
import { ThreadStore } from '../state/thread.svelte';
import { fakeEngine, type FakeEngine } from '../testing/turn-channel';
import AnswerView from './AnswerView.svelte';
import ThreadView from './ThreadView.svelte';

afterEach(() => {
	cleanup();
	document.body.innerHTML = '';
});

function makeTurn(question = 'no sound'): Turn {
	return new Turn(question, ['live/manual', 'akai/apc']);
}

function emit(turn: Turn, event: string, data: unknown): void {
	turn.applyEvent({ event, data: JSON.stringify(data) });
}

const liveCitation: Citation = {
	kind: 'vendor-manual',
	source_id: 'live/manual',
	display_name: 'Live 12 Manual',
	passage_id: 'live/manual#0001',
	section_number: '14.2',
	section_title: 'Routing',
	hardware_applicability: { status: 'confirmed' },
	degraded: false,
	has_figures: false,
	doc_version: '12',
	page: 312
};

describe('progressive rendering (4.1)', () => {
	it('paints partial content as it arrives, before the turn settles', async () => {
		const turn = makeTurn();
		render(AnswerView, { props: { turn } });
		emit(turn, 'outcome', { outcome: 'answered' });
		emit(turn, 'body_delta', { text: 'Check the monitor ' });
		await tick();
		expect(screen.getByText(/check the monitor/i)).toBeTruthy();
		expect(turn.state).toBe('streaming');

		// A later delta extends the same paragraph already on screen.
		emit(turn, 'body_delta', { text: 'switch on the interface.' });
		await tick();
		expect(screen.getByText(/check the monitor switch on the interface\./i)).toBeTruthy();
	});
});

describe('direct answer first (4.3)', () => {
	it('renders direct_answer ahead of the body blocks in DOM order', async () => {
		const turn = makeTurn();
		const { container } = render(AnswerView, { props: { turn } });
		emit(turn, 'outcome', { outcome: 'answered' });
		emit(turn, 'direct_answer', { text: 'Unmute the master track.' });
		emit(turn, 'body_delta', { text: 'The routing panel hides mutes.\n' });
		await tick();

		const direct = screen.getByText('Unmute the master track.');
		const body = screen.getByText(/routing panel hides mutes/);
		expect(container.contains(direct)).toBe(true);
		expect(direct.compareDocumentPosition(body) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
	});
});

describe('the closed block set renders visually distinct (4.4, 4.5)', () => {
	const body = [
		'## Routing',
		'1. Open the routing panel.',
		'2. Check the monitor switch.',
		'- Also check the master fader.',
		'Plain prose about the signal path.',
		'!caveat External Audio Effect needs Live Suite.',
		'!conflict The manuals disagree about phantom power.',
		'- Leave phantom power on [[p:live/manual#0001]]',
		'- Switch phantom power off [[p:focusrite/solo#0002]]',
		''
	].join('\n');

	async function renderBody() {
		const turn = makeTurn();
		const result = render(AnswerView, { props: { turn } });
		emit(turn, 'outcome', { outcome: 'answered' });
		emit(turn, 'body_delta', { text: body });
		await tick();
		return { turn, ...result };
	}

	it('renders a heading as a heading element', async () => {
		await renderBody();
		expect(screen.getByRole('heading', { name: 'Routing' })).toBeTruthy();
	});

	it('renders each ordered step as a separately identifiable element (4.5)', async () => {
		const { container } = await renderBody();
		const steps = container.querySelectorAll('.step');
		expect(steps).toHaveLength(2);
		expect(steps[0].textContent).toContain('1.');
		expect(steps[0].textContent).toContain('Open the routing panel.');
		expect(steps[1].textContent).toContain('2.');
		expect(steps[1].textContent).toContain('Check the monitor switch.');
	});

	it('renders bullets and paragraphs as distinct elements', async () => {
		const { container } = await renderBody();
		expect(container.querySelector('.bullet')?.textContent).toContain('master fader');
		const paragraphs = [...container.querySelectorAll('.paragraph')];
		expect(paragraphs.some((p) => p.textContent?.includes('signal path'))).toBe(true);
	});

	it('renders !caveat in reading position, visually distinct, never behind a disclosure (4.4)', async () => {
		const { container } = await renderBody();
		const caveat = container.querySelector('.caveat');
		expect(caveat).not.toBeNull();
		expect(caveat?.textContent).toContain('needs Live Suite');
		// The word channel survives greyscale (11.6).
		expect(caveat?.textContent).toMatch(/caveat/i);
		// Never behind a disclosure: no <details> anywhere on the path.
		expect(caveat?.closest('details')).toBeNull();
		// Reading position: after the prose it follows in the body.
		const prose = screen.getByText(/signal path/);
		expect(prose.compareDocumentPosition(caveat!) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
	});

	it('renders !conflict with both readings and their separate citations, neither chosen (4.4)', async () => {
		const { container } = await renderBody();
		const conflict = container.querySelector('.conflict');
		expect(conflict).not.toBeNull();
		expect(conflict?.textContent).toContain('disagree about phantom power');
		const readings = conflict!.querySelectorAll('.reading');
		expect(readings).toHaveLength(2);
		expect(readings[0].textContent).toContain('Leave phantom power on');
		expect(readings[1].textContent).toContain('Switch phantom power off');
		// Each reading carries its own marker integer.
		expect(readings[0].querySelector('.marker')?.textContent).toBe('1');
		expect(readings[1].querySelector('.marker')?.textContent).toBe('2');
		// Neither is presented as the answer.
		expect(conflict?.querySelector('.direct')).toBeNull();
	});
});

describe('key terms render as discrete key-styled elements (4.12)', () => {
	it('renders backtick spans as <kbd>, named as the manual names them', async () => {
		const turn = makeTurn();
		const { container } = render(AnswerView, { props: { turn } });
		emit(turn, 'outcome', { outcome: 'answered' });
		emit(turn, 'body_delta', { text: 'Hold `Shift` and press `Tab` to fold the device.\n' });
		await tick();
		const keys = [...container.querySelectorAll('kbd')];
		expect(keys.map((key) => key.textContent)).toEqual(['Shift', 'Tab']);
	});
});

describe('citation markers (Decision 3)', () => {
	it('paints the first-appearance integer immediately and keeps it when the citation lands late', async () => {
		const turn = makeTurn();
		const { container } = render(AnswerView, { props: { turn } });
		emit(turn, 'outcome', { outcome: 'answered' });
		emit(turn, 'body_delta', { text: 'Turn up the monitor knob [[p:live/manual#0001]].\n' });
		await tick();
		expect(container.querySelector('.marker')?.textContent).toBe('1');

		emit(turn, 'citation', liveCitation);
		await tick();
		expect(container.querySelector('.marker')?.textContent).toBe('1');
	});

	it('renders the citation entry while the body still streams — 5.8 expects it usable mid-stream', async () => {
		// A citation event interleaved with body deltas paints its entry below
		// the growing body: 4.2's no-reflow guarantee is the streamed prose's
		// (design "Streaming without reflow"), and the 5.8 rect-based restore
		// exists precisely because content above an entry grows while streaming.
		const turn = makeTurn();
		const { container } = render(AnswerView, { props: { turn } });
		emit(turn, 'outcome', { outcome: 'answered' });
		emit(turn, 'body_delta', { text: 'Turn up the monitor knob [[p:live/manual#0001]].\n' });
		emit(turn, 'citation', liveCitation);
		await tick();
		expect(container.querySelector('.citations')?.textContent).toContain('Live 12 Manual');
	});
});

describe('contributing sources (4.7)', () => {
	it('names the sources that supplied passages, distinctly from the merely-in-scope', async () => {
		const turn = makeTurn(); // scope at ask: live/manual and akai/apc
		const { container } = render(AnswerView, { props: { turn } });
		emit(turn, 'outcome', { outcome: 'answered' });
		emit(turn, 'citation', liveCitation);
		emit(turn, 'contributing_sources', { sources: ['live/manual'] });
		emit(turn, 'done', { complete: true });
		await tick();

		const contributing = container.querySelector('.contributing');
		expect(contributing?.textContent).toMatch(/answered from/i);
		expect(contributing?.textContent).toContain('Live 12 Manual');
		// akai/apc was merely in scope; it supplied nothing and is not named here.
		expect(contributing?.textContent).not.toContain('akai/apc');
	});
});

describe('partial answers (4.8, 4.9)', () => {
	let engine: FakeEngine;
	let scope: ScopeStore;
	let thread: ThreadStore;

	beforeEach(() => {
		localStorage.clear();
		sessionStorage.clear();
		engine = fakeEngine();
		scope = new ScopeStore();
		scope.load(['live/manual', 'akai/apc']);
		scope.toggle('akai/apc'); // a deliberate narrowing: live/manual only
		thread = new ThreadStore({ scope, submit: engine.submit });
	});

	it('renders as an answer with each uncovered part visually subordinate — never a refusal or error (4.8)', async () => {
		const turn = makeTurn();
		const { container } = render(AnswerView, { props: { turn } });
		emit(turn, 'outcome', { outcome: 'partially-answered' });
		emit(turn, 'direct_answer', { text: 'Lower the clip gain on the kick.' });
		emit(turn, 'uncovered_parts', { parts: ['mapping the kick to the APC'] });
		emit(turn, 'done', { complete: true });
		await tick();

		expect(turn.renderer).toBe('answer');
		expect(screen.getByText('Lower the clip gain on the kick.')).toBeTruthy();
		const uncovered = container.querySelector('.uncovered');
		expect(uncovered?.textContent).toContain('mapping the kick to the APC');
		// Subordinate to the answer, after it in reading order.
		const direct = screen.getByText('Lower the clip gain on the kick.');
		expect(direct.compareDocumentPosition(uncovered!) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
		expect(uncovered?.textContent).not.toMatch(/refused|error/i);
	});

	it('re-asks an uncovered part alone in one activation, widening to the engine-named sources (4.9)', async () => {
		const turn = thread.submit('why is the kick distorting and how do I map it to the APC?')!;
		render(AnswerView, { props: { turn, thread, scope } });
		await vi.waitFor(() => expect(engine.channels).toHaveLength(1));
		const channel = engine.channels[0];
		channel.emit('outcome', { outcome: 'partially-answered' });
		channel.emit('direct_answer', { text: 'Lower the clip gain on the kick.' });
		channel.emit('uncovered_parts', { parts: ['mapping the kick to the APC'] });
		channel.emit('suggested_sources', [{ source_id: 'akai/apc', display_name: 'APC Key 25 Guide' }]);
		channel.emit('done', { complete: true });
		channel.close();
		await vi.waitFor(() => expect(turn.state).toBe('settled'));
		await tick();

		await fireEvent.click(screen.getByRole('button', { name: /re-ask/i }));
		expect(engine.requests).toHaveLength(2);
		// The uncovered part alone, not the original question.
		expect(engine.requests[1].question).toBe('mapping the kick to the APC');
		// Widened to the source the engine named, and the widening persists (7.9).
		expect(engine.requests[1].sources).toContain('akai/apc');
		expect(scope.isSelected('akai/apc')).toBe(true);
		// The answered part stays on screen.
		expect(screen.getByText('Lower the clip gain on the kick.')).toBeTruthy();
	});
});

describe('dropped scope reported with the turn (3.11)', () => {
	// The notice is ThreadView's, above the renderer switch: the prune is
	// turn-level and can accompany any outcome, not only an answer.
	async function mountThread() {
		localStorage.clear();
		sessionStorage.clear();
		const engine = fakeEngine();
		const scope = new ScopeStore();
		scope.load(['live/manual', 'old/manual']);
		const thread = new ThreadStore({ scope, submit: engine.submit });
		const { container } = render(ThreadView, { props: { thread } });
		thread.submit('no sound');
		await vi.waitFor(() => expect(engine.channels).toHaveLength(1));
		return { container, channel: engine.channels[0] };
	}

	it('names the dropped sources and states the corpus no longer holds them', async () => {
		const { container, channel } = await mountThread();
		channel.emit('scope_dropped', [{ source_id: 'old/manual', display_name: 'Old Synth Manual' }]);
		channel.emit('outcome', { outcome: 'answered' });
		await vi.waitFor(() => expect(container.querySelector('.scope-dropped')).not.toBeNull());

		const notice = container.querySelector('.scope-dropped');
		expect(notice?.textContent).toContain('Old Synth Manual');
		expect(notice?.textContent).toMatch(/no longer holds/i);
		// The engine's prune, never presented as the user's own narrowing.
		expect(notice?.textContent).not.toMatch(/you (removed|narrowed|deselected)/i);
	});

	it('accompanies a non-answer outcome just the same', async () => {
		const { container, channel } = await mountThread();
		channel.emit('scope_dropped', [{ source_id: 'old/manual', display_name: 'Old Synth Manual' }]);
		channel.emit('outcome', { outcome: 'needs-narrowing' });
		channel.emit('narrowing', { question: 'Which device?', candidates: [
				{ label: 'Live shows no signal', value: 'Live' },
				{ label: 'The APC shows no signal', value: 'the APC' }
			] });
		await vi.waitFor(() => expect(container.querySelector('.scope-dropped')).not.toBeNull());
		expect(container.querySelector('.scope-dropped')?.textContent).toContain('Old Synth Manual');
	});
});

describe('finished is distinguishable from streaming (4.6)', () => {
	it('marks the settled answer differently from the streaming state', async () => {
		localStorage.clear();
		sessionStorage.clear();
		const engine = fakeEngine();
		const scope = new ScopeStore();
		scope.load(['live/manual']);
		const thread = new ThreadStore({ scope, submit: engine.submit });
		render(ThreadView, { props: { thread } });

		thread.submit('no sound');
		await vi.waitFor(() => expect(engine.channels).toHaveLength(1));
		const channel = engine.channels[0];
		channel.emit('outcome', { outcome: 'answered' });
		channel.emit('body_delta', { text: 'Unmute the master track.\n' });
		await vi.waitFor(() => expect(thread.turns[0].state).toBe('streaming'));
		await tick();
		// The per-turn state label; the 13.5 announcer is a separate channel.
		expect(document.querySelector('.state')?.textContent).toMatch(/working…/);
		expect(document.querySelector('.state')?.textContent).not.toMatch(/finished/);

		channel.emit('done', { complete: true });
		channel.close();
		await vi.waitFor(() => expect(thread.turns[0].state).toBe('settled'));
		await tick();
		expect(document.querySelector('.state')?.textContent).toMatch(/finished/);
		expect(document.querySelector('.state')?.textContent).not.toMatch(/working…/);
	});
});
