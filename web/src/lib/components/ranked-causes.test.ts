// The ranked-causes renderer (requirements 6.6, 5.16; CONTRACTS §4c; design
// "Narrowing and ranked causes"). Causes are findings to read, never the
// digit-armed controls of a narrowing question — the affordance split is the
// only thing keeping the two candidate-bearing shapes apart. Citations resolve
// through the turn's one citation map by passage_id; there is no second
// channel.

import { cleanup, render } from '@testing-library/svelte';
import { tick } from 'svelte';
import { afterEach, describe, expect, it } from 'vitest';
import type { Cause, Citation } from '../engine/records';
import { Turn } from '../engine/turn.svelte';
import ThreadView from './ThreadView.svelte';
import { ThreadStore } from '../state/thread.svelte';
import { ScopeStore } from '../state/scope.svelte';
import { fakeEngine } from '../testing/turn-channel';
import { vi, beforeEach } from 'vitest';

beforeEach(() => {
	localStorage.clear();
	sessionStorage.clear();
});

afterEach(() => {
	cleanup();
	document.body.innerHTML = '';
});

const authoredCitation: Citation = {
	kind: 'authored-triage',
	source_id: 'authored/triage',
	display_name: 'Your triage notes',
	passage_id: 'authored/triage#no-sound-01',
	section_title: 'No sound from a track',
	hardware_applicability: { status: 'assumed' },
	degraded: false,
	has_figures: false,
	entry_location: 'triage/no-sound.md:12'
};

const fixCitation: Citation = {
	kind: 'vendor-manual',
	source_id: 'live/manual',
	display_name: 'Live 12 Manual',
	passage_id: 'live/manual#0007',
	section_number: '14.2',
	section_title: 'Routing',
	hardware_applicability: { status: 'confirmed' },
	degraded: false,
	has_figures: false,
	doc_version: '12',
	page: 312
};

const causes: Cause[] = [
	{
		rank: 1,
		statement: 'The Track Activator is off',
		check: 'Look at the Track Activator on the silent track',
		cites: [authoredCitation.passage_id],
		fix_cites: [fixCitation.passage_id]
	},
	{
		rank: 2,
		statement: 'The monitor knob is down',
		check: 'Look at the interface monitor knob position',
		cites: [authoredCitation.passage_id],
		fix_cites: []
	}
];

function emit(turn: Turn, event: string, data: unknown): void {
	turn.applyEvent({ event, data: JSON.stringify(data) });
}

/** A settled ranked-causes turn, rendered through the thread shell. */
async function renderCauses(list: Cause[] = causes) {
	const engine = fakeEngine();
	const scope = new ScopeStore();
	scope.load(['live/manual', 'authored/triage']);
	const thread = new ThreadStore({ scope, submit: engine.submit });
	const result = render(ThreadView, { props: { thread } });
	const turn = thread.submit('no sound')!;
	await vi.waitFor(() => expect(engine.channels).toHaveLength(1));
	emit(turn, 'outcome', { outcome: 'ranked-causes' });
	emit(turn, 'direct_answer', { text: list[0].check });
	for (const cause of list) emit(turn, 'cause', cause);
	emit(turn, 'citation', authoredCitation);
	emit(turn, 'citation', fixCitation);
	emit(turn, 'done', { complete: true });
	await tick();
	return { turn, thread, ...result };
}

describe('causes render in array order with rank shown (6.6)', () => {
	it('shows every cause in order, each with its rank, statement and check', async () => {
		const { container } = await renderCauses();
		const rendered = [...container.querySelectorAll('.cause')];
		expect(rendered).toHaveLength(2);
		causes.forEach((cause, index) => {
			expect(rendered[index].textContent).toContain(String(cause.rank));
			expect(rendered[index].textContent).toContain(cause.statement);
			expect(rendered[index].textContent).toContain(cause.check);
		});
	});
});

describe('findings to read, not controls (6.6 versus 6.2/6.3)', () => {
	it('renders no activatable candidate controls and no armed digits', async () => {
		const { container } = await renderCauses();
		const region = container.querySelector('.ranked-causes');
		expect(region).not.toBeNull();
		// Not the narrowing shape: no candidate buttons, no kbd digit chrome.
		expect(container.querySelector('.narrowing')).toBeNull();
		expect(region?.querySelector('.cause button')).toBeNull();
		expect(region?.querySelector('.cause kbd')).toBeNull();
	});
});

describe('the first cause is never the answer (6.6, 4.3)', () => {
	it('paints the rank-1 check as direct_answer, ahead of the causes, and never promotes the cause', async () => {
		const { container } = await renderCauses();
		const direct = container.querySelector('.direct');
		expect(direct?.textContent).toBe(causes[0].check);
		// The instruction, not the cause statement, leads the turn.
		expect(direct?.textContent).not.toContain(causes[0].statement);
		const first = container.querySelector('.cause');
		expect(
			direct!.compareDocumentPosition(first!) & Node.DOCUMENT_POSITION_FOLLOWING
		).toBeTruthy();
		// The ranking is shown; nothing renders cause 1 as a settled diagnosis.
		expect(first?.textContent).toContain('1');
	});
});

describe('citations resolve through the turn map (6.6, CONTRACTS §4c)', () => {
	it('marks each cause with the shared citation numbers of its cites and fix_cites', async () => {
		const { container } = await renderCauses();
		// One citation channel: the list below the answer numbers the records.
		const listNumbers = [...container.querySelectorAll('.citation-entry .entry-number')].map(
			(entry) => entry.textContent
		);
		expect(listNumbers).toEqual(['1', '2']);

		const rendered = [...container.querySelectorAll('.cause')];
		// Cause 1 cites the authored entry (1) and its fix (2).
		const markers = [...rendered[0].querySelectorAll('.marker')].map((m) => m.textContent);
		expect(markers).toContain('1');
		expect(markers).toContain('2');
	});

	it('renders the citations once, in the shared list — no second citation channel', async () => {
		const { container } = await renderCauses();
		const entries = container.querySelectorAll('.citation-entry');
		expect(entries).toHaveLength(2);
	});

	it('renders the fix as an ordinary vendor citation, distinct from the authored cause (5.14)', async () => {
		const { container } = await renderCauses();
		const entries = [...container.querySelectorAll('.citation-entry')];
		const authored = entries.find((entry) => entry.textContent?.includes('Your triage notes'));
		const fix = entries.find((entry) => entry.textContent?.includes('Live 12 Manual'));
		expect(authored?.textContent).toContain('your own note');
		expect(fix?.textContent).toContain('v12');
		expect(fix?.textContent).not.toContain('your own note');
	});
});

describe('an empty fix_cites[] carries the unbacked mark (5.16)', () => {
	it('marks the fixless cause, and only that cause', async () => {
		const { container } = await renderCauses();
		const rendered = [...container.querySelectorAll('.cause')];
		expect(rendered[0].textContent).not.toMatch(/no manual behind this/i);
		expect(rendered[1].textContent).toMatch(/no manual behind this/i);
	});
});
