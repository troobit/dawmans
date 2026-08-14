// Passage expansion and open-at-source (requirements 5.5–5.11, 5.18; design
// "Citations" and "The engine client"; CONTRACTS §3a). Expansion goes through
// the passage store — components fetch nothing themselves — and openAtSource
// is two branches and no third: a plain link to the served document at
// `#page=N` for a vendor manual, the in-place expansion plus the copyable
// `entry_location` for an authored entry.

import { cleanup, fireEvent, render, screen } from '@testing-library/svelte';
import { tick } from 'svelte';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { Citation, Passage } from '../engine/records';
import { Turn } from '../engine/turn.svelte';
import { PassageStore } from '../state/passages.svelte';
import CitationList from './CitationList.svelte';

afterEach(() => {
	cleanup();
	vi.useRealTimers();
	document.body.innerHTML = '';
});

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

const authoredCitation: Citation = {
	kind: 'authored-triage',
	source_id: 'authored/triage',
	display_name: 'Symptom triage notes',
	passage_id: 'authored/triage#no-sound',
	section_title: 'No sound from a track',
	hardware_applicability: { status: 'assumed' },
	degraded: false,
	has_figures: false,
	entry_location: 'triage/no-sound.md:12'
};

function passageFor(citation: Citation, overrides: Partial<Passage> = {}): Passage {
	return {
		passage_id: citation.passage_id,
		source_id: citation.source_id,
		section_title: citation.section_title,
		text: 'The manual’s own words, verbatim.',
		degraded: false,
		has_figures: false,
		...overrides
	};
}

function emit(turn: Turn, event: string, data: unknown): void {
	turn.applyEvent({ event, data: JSON.stringify(data) });
}

async function renderCited(citation: Citation, passages: PassageStore) {
	const turn = new Turn('no sound', ['live/manual', 'authored/triage']);
	const result = render(CitationList, { props: { turn, passages } });
	emit(turn, 'outcome', { outcome: 'answered' });
	emit(turn, 'body_delta', { text: `Do the thing [[p:${citation.passage_id}]].\n` });
	emit(turn, 'citation', citation);
	emit(turn, 'done', { complete: true });
	await tick();
	return { turn, ...result };
}

describe('the passage store cache (5.18, design "Citations")', () => {
	it('fetches a passage once and serves the session cache afterwards', async () => {
		const fetcher = vi.fn().mockResolvedValue(passageFor(vendorCitation));
		const passages = new PassageStore(fetcher);
		passages.prefetch(vendorCitation.passage_id);
		passages.prefetch(vendorCitation.passage_id);
		await vi.waitFor(() =>
			expect(passages.get(vendorCitation.passage_id)?.status).toBe('ready')
		);
		passages.prefetch(vendorCitation.passage_id);
		expect(fetcher).toHaveBeenCalledOnce();
	});

	it('marks a failed fetch and retries it on the next prefetch', async () => {
		const fetcher = vi
			.fn()
			.mockRejectedValueOnce(new Error('unreachable'))
			.mockResolvedValue(passageFor(vendorCitation));
		const passages = new PassageStore(fetcher);
		passages.prefetch(vendorCitation.passage_id);
		await vi.waitFor(() =>
			expect(passages.get(vendorCitation.passage_id)?.status).toBe('failed')
		);
		passages.prefetch(vendorCitation.passage_id);
		await vi.waitFor(() =>
			expect(passages.get(vendorCitation.passage_id)?.status).toBe('ready')
		);
		expect(fetcher).toHaveBeenCalledTimes(2);
	});
});

describe('expansion (5.6, 5.7, 5.9)', () => {
	it('fetches on activation and reveals the passage verbatim, in place, distinguishable from summary text', async () => {
		const fetcher = vi.fn().mockResolvedValue(passageFor(vendorCitation));
		const passages = new PassageStore(fetcher);
		const { container } = await renderCited(vendorCitation, passages);

		await fireEvent.click(screen.getByRole('button', { name: /show passage/i }));
		expect(fetcher).toHaveBeenCalledExactlyOnceWith(vendorCitation.passage_id);
		await vi.waitFor(() => expect(container.querySelector('.passage')).not.toBeNull());

		// Verbatim, inside the entry, and no navigation happened (5.7).
		const passage = container.querySelector('.passage');
		expect(passage?.textContent).toContain('The manual’s own words, verbatim.');
		expect(passage?.closest('.citation-entry')).not.toBeNull();
		expect(window.location.href).toBe('http://localhost/');
	});

	it('expands and collapses through a real button, so the keyboard path is native (5.9)', async () => {
		const passages = new PassageStore(vi.fn().mockResolvedValue(passageFor(vendorCitation)));
		const { container } = await renderCited(vendorCitation, passages);
		const button = screen.getByRole('button', { name: /show passage/i });
		expect(button.getAttribute('aria-expanded')).toBe('false');
		await fireEvent.click(button);
		expect(button.getAttribute('aria-expanded')).toBe('true');
		await fireEvent.click(screen.getByRole('button', { name: /hide passage/i }));
		expect(container.querySelector('.passage')).toBeNull();
	});

	it('prefetches on focus and never on hover (1.12, 5.18)', async () => {
		const fetcher = vi.fn().mockResolvedValue(passageFor(vendorCitation));
		const passages = new PassageStore(fetcher);
		const { container } = await renderCited(vendorCitation, passages);

		await fireEvent.mouseOver(container.querySelector('.citation-entry')!);
		expect(fetcher).not.toHaveBeenCalled();

		// Focus precedes activation by a keystroke, so activation is a cache hit.
		await fireEvent.focus(screen.getByRole('button', { name: /show passage/i }));
		expect(fetcher).toHaveBeenCalledOnce();
		await fireEvent.click(screen.getByRole('button', { name: /show passage/i }));
		expect(fetcher).toHaveBeenCalledOnce();
	});

	it('shows the working indicator past 300 ms on a cache miss, never an empty area (5.18)', async () => {
		vi.useFakeTimers();
		const passages = new PassageStore(vi.fn().mockReturnValue(new Promise<Passage>(() => {})));
		const { container } = await renderCited(vendorCitation, passages);

		await fireEvent.click(screen.getByRole('button', { name: /show passage/i }));
		vi.advanceTimersByTime(299);
		await tick();
		expect(container.querySelector('.passage-working')).toBeNull();
		vi.advanceTimersByTime(2);
		await tick();
		expect(container.querySelector('.passage-working')?.textContent).toMatch(/fetching/i);
	});

	it('restores the citation element’s viewport offset on collapse via its rect, not scrollY (5.8)', async () => {
		const passages = new PassageStore(vi.fn().mockResolvedValue(passageFor(vendorCitation)));
		const { container } = await renderCited(vendorCitation, passages);
		const entry = container.querySelector('.citation-entry') as HTMLElement;
		// The entry sat at 100 before expanding; content above grew while
		// streaming continued, so it sits at 160 when collapsed.
		vi.spyOn(entry, 'getBoundingClientRect')
			.mockReturnValueOnce({ top: 100 } as DOMRect)
			.mockReturnValueOnce({ top: 160 } as DOMRect);
		const scrollBy = vi.spyOn(window, 'scrollBy').mockImplementation(() => {});

		await fireEvent.click(screen.getByRole('button', { name: /show passage/i }));
		await fireEvent.click(screen.getByRole('button', { name: /hide passage/i }));
		await vi.waitFor(() => expect(scrollBy).toHaveBeenCalledWith(0, 60));
	});
});

describe('degraded and unavailable passages (5.10, 5.11)', () => {
	it('marks a degraded passage as containing unreadable characters, distinctly from unavailable', async () => {
		const passages = new PassageStore(
			vi.fn().mockResolvedValue(passageFor(vendorCitation, { degraded: true }))
		);
		const { container } = await renderCited(vendorCitation, passages);
		await fireEvent.click(screen.getByRole('button', { name: /show passage/i }));
		await vi.waitFor(() => expect(container.querySelector('.degraded-mark')).not.toBeNull());
		expect(container.querySelector('.degraded-mark')?.textContent).toMatch(/could not be read/i);
		expect(container.querySelector('.passage-unavailable')).toBeNull();
		// The text itself still renders; degraded marks it, never withholds it.
		expect(container.querySelector('.passage')?.textContent).toContain('verbatim');
	});

	it('keeps the source, its cited location and the open action when the passage cannot be retrieved', async () => {
		const passages = new PassageStore(vi.fn().mockRejectedValue(new Error('gone')));
		const { container } = await renderCited(vendorCitation, passages);
		await fireEvent.click(screen.getByRole('button', { name: /show passage/i }));
		await vi.waitFor(() =>
			expect(container.querySelector('.passage-unavailable')).not.toBeNull()
		);
		expect(container.querySelector('.passage-unavailable')?.textContent).toMatch(/unavailable/i);
		expect(container.querySelector('.source')?.textContent).toBe('Live 12 Manual');
		expect(container.querySelector('.location')?.textContent).toContain('Routing');
		expect(screen.getByRole('link', { name: /open/i })).toBeTruthy();
		expect(container.querySelector('.degraded-mark')).toBeNull();
	});
});

describe('openAtSource is two branches and no third (5.5)', () => {
	it('opens a vendor manual as a plain link to the served document at exactly #page=N', async () => {
		const passages = new PassageStore(vi.fn());
		await renderCited(vendorCitation, passages);
		const link = screen.getByRole('link', { name: /open/i });
		expect(link.getAttribute('href')).toBe('/sources/live/manual/document#page=312');
		expect(link.getAttribute('target')).toBe('_blank');
		expect(link.getAttribute('rel')).toBe('noopener');
		// A plain link activation: no handler intercepts it, so it cannot break.
		const defaultNotPrevented = await fireEvent.click(link);
		expect(defaultNotPrevented).toBe(true);
	});

	it('keeps the citation’s string form beside the link, so a serve-document 404 degrades to it rather than to a broken action', async () => {
		const passages = new PassageStore(vi.fn());
		const { container } = await renderCited(vendorCitation, passages);
		// Whatever the served document returns in its own tab, this surface
		// still carries the source, section and page as plain text.
		const entry = container.querySelector('.citation-entry');
		expect(entry?.querySelector('.source')?.textContent).toBe('Live 12 Manual');
		expect(entry?.querySelector('.location')?.textContent).toContain('14.2');
		expect(entry?.querySelector('.location')?.textContent).toContain('p312');
	});

	it('opens an authored entry by the in-place expansion with its entry_location copyable, and no link', async () => {
		const writeText = vi.fn().mockResolvedValue(undefined);
		Object.defineProperty(navigator, 'clipboard', {
			value: { writeText },
			configurable: true
		});
		const passages = new PassageStore(vi.fn().mockResolvedValue(passageFor(authoredCitation)));
		const { container } = await renderCited(authoredCitation, passages);

		expect(container.querySelector('a')).toBeNull();
		await fireEvent.click(screen.getByRole('button', { name: /show passage/i }));
		await vi.waitFor(() => expect(container.querySelector('.passage')).not.toBeNull());
		expect(container.querySelector('.entry-location')?.textContent).toContain(
			'triage/no-sound.md:12'
		);
		await fireEvent.click(screen.getByRole('button', { name: /copy/i }));
		expect(writeText).toHaveBeenCalledExactlyOnceWith('triage/no-sound.md:12');
	});

	it('never attempts a file:// URL for either kind', async () => {
		const passages = new PassageStore(vi.fn());
		const vendor = await renderCited(vendorCitation, passages);
		expect(vendor.container.querySelector('a[href^="file:"]')).toBeNull();
		const authored = await renderCited(authoredCitation, passages);
		expect(authored.container.querySelector('a[href^="file:"]')).toBeNull();
	});
});
