// The citation list and its inline marks (requirements 5.1–5.4, 5.12–5.17,
// 5.19; CONTRACTS §3; Decision 3). Everything a citation says renders on its
// entry in the list below the answer — "inline" means on the citation, never
// behind a disclosure, and never mid-prose where five caveats would breach
// 11.7 on the first citation.

import { cleanup, fireEvent, render, screen } from '@testing-library/svelte';
import { tick } from 'svelte';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { Citation } from '../engine/records';
import { Turn } from '../engine/turn.svelte';
import AnswerView from './AnswerView.svelte';
import CitationList from './CitationList.svelte';

afterEach(() => {
	cleanup();
	document.body.innerHTML = '';
});

function makeTurn(): Turn {
	return new Turn('no sound', ['live/manual', 'authored/triage']);
}

function emit(turn: Turn, event: string, data: unknown): void {
	turn.applyEvent({ event, data: JSON.stringify(data) });
}

const vendorCitation: Citation = {
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

const unnumberedCitation: Citation = {
	kind: 'vendor-manual',
	source_id: 'akai/apc',
	display_name: 'APC Key 25 Guide',
	passage_id: 'akai/apc#0007',
	section_title: 'Pads and the shift layer',
	hardware_applicability: { device: 'APC Key 25 (original)', status: 'assumed' },
	degraded: false,
	has_figures: true,
	doc_version: '1.0',
	page: 14
};

const authoredCitation: Citation = {
	kind: 'authored-triage',
	source_id: 'authored/triage',
	display_name: 'Symptom triage notes',
	passage_id: 'authored/triage#no-sound',
	section_title: 'No sound from a track',
	hardware_applicability: { status: 'assumed' },
	degraded: false,
	has_figures: false,
	unbacked: true,
	entry_location: 'triage/no-sound.md:12'
};

/** A turn whose body cited the given citations, in marker order. */
async function renderList(...citations: Citation[]) {
	const turn = makeTurn();
	const result = render(CitationList, { props: { turn } });
	emit(turn, 'outcome', { outcome: 'answered' });
	const markers = citations.map((citation) => `[[p:${citation.passage_id}]]`).join(' and ');
	emit(turn, 'body_delta', { text: `See ${markers}.\n` });
	for (const citation of citations) emit(turn, 'citation', citation);
	emit(turn, 'done', { complete: true });
	await tick();
	return { turn, ...result };
}

describe('one entry per marker, in first-appearance order (Decision 3)', () => {
	it('lists entries by marker integer however late their citations arrive', async () => {
		const turn = makeTurn();
		const { container } = render(CitationList, { props: { turn } });
		emit(turn, 'outcome', { outcome: 'answered' });
		emit(turn, 'body_delta', { text: 'Late [[p:akai/apc#0007]] then [[p:live/manual#0001]].\n' });
		// The citation events arrive in the opposite order to the markers.
		emit(turn, 'citation', vendorCitation);
		emit(turn, 'citation', unnumberedCitation);
		emit(turn, 'done', { complete: true });
		await tick();

		const entries = [...container.querySelectorAll('.citation-entry')];
		expect(entries).toHaveLength(2);
		expect(entries[0].querySelector('.entry-number')?.textContent).toBe('1');
		expect(entries[0].textContent).toContain('APC Key 25 Guide');
		expect(entries[1].querySelector('.entry-number')?.textContent).toBe('2');
		expect(entries[1].textContent).toContain('Live 12 Manual');
	});

	it('appends a citation whose marker never appeared in the prose, numbered after the markers', async () => {
		const turn = makeTurn();
		const { container } = render(CitationList, { props: { turn } });
		emit(turn, 'outcome', { outcome: 'answered' });
		emit(turn, 'body_delta', { text: 'One marker [[p:live/manual#0001]].\n' });
		emit(turn, 'citation', vendorCitation);
		emit(turn, 'citation', authoredCitation); // resolved by causes, never by a marker
		emit(turn, 'done', { complete: true });
		await tick();

		const numbers = [...container.querySelectorAll('.entry-number')].map((n) => n.textContent);
		expect(numbers).toEqual(['1', '2']);
	});
});

describe('the location slot (5.1, 5.15)', () => {
	it('renders section_number and section_title as the two fields they are, with the page', async () => {
		const { container } = await renderList(vendorCitation);
		const location = container.querySelector('.location');
		expect(location?.querySelector('.section-number')?.textContent).toBe('14.2');
		expect(location?.querySelector('.section-title')?.textContent).toBe('Routing');
		expect(location?.querySelector('.page')?.textContent).toBe('p312');
	});

	it('shows no invented number for an unnumbered document', async () => {
		const { container } = await renderList(unnumberedCitation);
		const location = container.querySelector('.location');
		expect(location?.querySelector('.section-number')).toBeNull();
		expect(location?.querySelector('.section-title')?.textContent).toBe('Pads and the shift layer');
	});

	it('puts the symptom title in the slot for a pageless authored citation — never 0, never empty (5.15)', async () => {
		const { container } = await renderList(authoredCitation);
		const location = container.querySelector('.location');
		expect(location?.textContent).toContain('No sound from a track');
		expect(location?.querySelector('.page')).toBeNull();
		expect(location?.querySelector('.section-number')).toBeNull();
		expect(location?.textContent).not.toMatch(/\b0\b|p0/);
	});
});

describe('the five inline obligations, with no disclosure in the path (Decision 3)', () => {
	it('renders doc_version inline on a vendor-manual citation (5.2)', async () => {
		const { container } = await renderList(vendorCitation);
		const version = container.querySelector('.doc-version');
		expect(version?.textContent).toBe('v12');
		expect(version?.closest('details')).toBeNull();
	});

	it('states assumed hardware applicability inline, naming the revision described (5.3)', async () => {
		const { container } = await renderList(unnumberedCitation);
		const applicability = container.querySelector('.applicability');
		expect(applicability?.textContent).toContain('APC Key 25 (original)');
		expect(applicability?.textContent).toMatch(/unconfirmed/i);
		expect(applicability?.closest('details')).toBeNull();
	});

	it('says nothing about applicability where it is confirmed', async () => {
		const { container } = await renderList(vendorCitation);
		expect(container.querySelector('.applicability')).toBeNull();
	});

	it('renders "figure on pN" naming the figure page (5.4)', async () => {
		const { container } = await renderList(unnumberedCitation);
		const figures = container.querySelector('.figures');
		expect(figures?.textContent).toBe('figure on p14');
		expect(figures?.closest('details')).toBeNull();
	});

	it('marks an authored citation as the user own note, apart from a manufacturer citation (5.14)', async () => {
		const { container } = await renderList(vendorCitation, authoredCitation);
		const entries = [...container.querySelectorAll('.citation-entry')];
		// The word is the channel that survives greyscale (11.6).
		expect(entries[1].querySelector('.kind')?.textContent).toMatch(/your own note/i);
		expect(entries[1].querySelector('.kind')?.closest('details')).toBeNull();
		expect(entries[0].querySelector('.kind')).toBeNull();
	});

	it('marks an unbacked cause inline — a broken or never-provided fix is never presented as documented (5.16)', async () => {
		const { container } = await renderList(authoredCitation);
		const unbacked = container.querySelector('.unbacked');
		expect(unbacked?.textContent).toMatch(/no manual/i);
		expect(unbacked?.closest('details')).toBeNull();
	});
});

describe('entry_location (5.19)', () => {
	it('shows file and line outside the location slot, never as a section or page', async () => {
		const { container } = await renderList(authoredCitation);
		const entryLocation = container.querySelector('.entry-location');
		expect(entryLocation?.textContent).toContain('triage/no-sound.md:12');
		expect(container.querySelector('.location')?.textContent).not.toContain('triage/no-sound.md');
		expect(entryLocation?.querySelector('.section-number')).toBeNull();
		expect(entryLocation?.querySelector('.page')).toBeNull();
	});

	it('copies the string in a single activation', async () => {
		const writeText = vi.fn().mockResolvedValue(undefined);
		Object.defineProperty(navigator, 'clipboard', {
			value: { writeText },
			configurable: true
		});
		await renderList(authoredCitation);
		await fireEvent.click(screen.getByRole('button', { name: /copy/i }));
		expect(writeText).toHaveBeenCalledExactlyOnceWith('triage/no-sound.md:12');
	});

	it('never renders one for a vendor-manual citation', async () => {
		const { container } = await renderList(vendorCitation);
		expect(container.querySelector('.entry-location')).toBeNull();
	});
});

describe('uncited and ungrounded answers (5.12, 5.13)', () => {
	it('marks a settled answer with no citations as uncited', async () => {
		const turn = makeTurn();
		const { container } = render(CitationList, { props: { turn } });
		emit(turn, 'outcome', { outcome: 'answered' });
		emit(turn, 'body_delta', { text: 'An answer with no markers.\n' });
		emit(turn, 'done', { complete: true });
		await tick();
		expect(container.textContent).toMatch(/uncited/i);
	});

	it('makes no uncited claim while the turn is still streaming', async () => {
		const turn = makeTurn();
		const { container } = render(CitationList, { props: { turn } });
		emit(turn, 'outcome', { outcome: 'answered' });
		emit(turn, 'body_delta', { text: 'Still arriving' });
		await tick();
		expect(container.textContent).not.toMatch(/uncited/i);
	});

	it('marks an ungrounded answer as unverified without withholding the rendered text', async () => {
		const turn = makeTurn();
		render(AnswerView, { props: { turn } });
		emit(turn, 'outcome', { outcome: 'answered' });
		emit(turn, 'body_delta', { text: 'Turn the monitor knob up.\n' });
		emit(turn, 'ungrounded', { ungrounded: true });
		emit(turn, 'done', { complete: true });
		await tick();
		// The text stays on screen (never blanked), with the mark beside it.
		expect(screen.getByText('Turn the monitor knob up.')).toBeTruthy();
		expect(screen.getByText(/unverified/i)).toBeTruthy();
	});
});
