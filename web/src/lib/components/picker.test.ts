// The source picker: the selectable list with its marks, the known-gaps group,
// the scope indicator and the collapse behaviour (requirements 2.2, 2.5–2.14,
// 3.3, 3.10, 11.6, 13.4; design "The source picker"). Component tests over
// fresh store instances; the engine is a stubbed GET /sources.

import { cleanup, fireEvent, render, screen } from '@testing-library/svelte';
import { tick } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { SourcesResponse } from '../engine/client';
import type {
	AuthoredTriageSourceRecord,
	SourceRecord,
	VendorManualSourceRecord
} from '../engine/records';
import { KeyRouter } from '../keys';
import { ScopeStore } from '../state/scope.svelte';
import { SourcesStore } from '../state/sources.svelte';
import SourcePicker from './SourcePicker.svelte';

function manual(id: string, over: Partial<VendorManualSourceRecord> = {}): VendorManualSourceRecord {
	const [vendor = 'vendor', product = 'product'] = id.split('/');
	return {
		kind: 'vendor-manual',
		source_id: id,
		display_name: `${vendor} ${product}`,
		vendor,
		product,
		doctype: 'manual',
		lang: 'en',
		doc_version: '1.0',
		page_count: 100,
		low_text: false,
		hardware_applicability: { status: 'confirmed' },
		ingested_at: '2026-08-01T00:00:00Z',
		chunk_count: 12,
		...over
	};
}

function triage(): AuthoredTriageSourceRecord {
	return {
		kind: 'authored-triage',
		source_id: 'authored/triage',
		display_name: 'Your triage notes',
		hardware_applicability: { status: 'assumed' },
		ingested_at: '2026-08-01T00:00:00Z',
		chunk_count: 4
	};
}

function payload(sources: SourceRecord[], over: Partial<SourcesResponse> = {}): SourcesResponse {
	return { sources, owned_but_undocumented: [], documented_but_unconfirmed: [], ...over };
}

function stubSources(body: SourcesResponse): void {
	vi.stubGlobal(
		'fetch',
		vi.fn(() =>
			Promise.resolve(
				new Response(JSON.stringify(body), {
					status: 200,
					headers: { 'content-type': 'application/json' }
				})
			)
		)
	);
}

/** Three sources — the live corpus shape: two manuals and the authored store. */
const THREE = [manual('ableton/live-12'), manual('akai/apc-key-25'), triage()];

async function mount(body: SourcesResponse, router?: KeyRouter) {
	stubSources(body);
	const sources = new SourcesStore();
	await sources.load();
	const scope = new ScopeStore();
	scope.load(sources.ids);
	const result = render(SourcePicker, { props: { sources, scope, ...(router ? { router } : {}) } });
	return { ...result, sources, scope };
}

/**
 * The one expand/collapse control (2.11). The indicator line is its accessible
 * name, which varies by scope state, so it is found by its expandable role.
 */
function indicatorButton(): HTMLButtonElement {
	const button = document.querySelector('button[aria-expanded]');
	if (!(button instanceof HTMLButtonElement)) throw new Error('no indicator control rendered');
	return button;
}

async function expand() {
	await fireEvent.click(indicatorButton());
	await tick();
}

beforeEach(() => {
	localStorage.clear();
	sessionStorage.clear();
});

afterEach(() => {
	cleanup();
	vi.unstubAllGlobals();
	document.body.innerHTML = '';
});

describe('collapse behaviour (2.11)', () => {
	it('is collapsed at rest to the one-line indicator once a scope is chosen', async () => {
		await mount(payload(THREE));
		expect(indicatorButton().getAttribute('aria-expanded')).toBe('false');
		expect(screen.queryAllByRole('checkbox')).toHaveLength(0);
	});

	it('expands and collapses in one activation each', async () => {
		await mount(payload(THREE));
		await expand();
		expect(indicatorButton().getAttribute('aria-expanded')).toBe('true');
		expect(screen.getAllByRole('checkbox')).toHaveLength(3);
		await fireEvent.click(indicatorButton());
		await tick();
		expect(indicatorButton().getAttribute('aria-expanded')).toBe('false');
		expect(screen.queryAllByRole('checkbox')).toHaveLength(0);
	});

	it('collapses on Escape, returning focus to the indicator control (13.3)', async () => {
		const router = new KeyRouter();
		await mount(payload(THREE), router);
		await expand();
		router.handleKeydown(new KeyboardEvent('keydown', { key: 'Escape', cancelable: true }));
		await tick();
		expect(indicatorButton().getAttribute('aria-expanded')).toBe('false');
		expect(document.activeElement).toBe(indicatorButton());
	});
});

describe('the scope indicator (2.5, 2.6, 2.7, 3.3, 3.10, 11.6)', () => {
	it('states all-sources explicitly rather than a bare count (2.7)', async () => {
		const many = [manual('a/1'), manual('b/2'), manual('c/3'), manual('d/4'), manual('e/5')];
		await mount(payload(many));
		expect(indicatorButton().textContent).toMatch(/all 5 sources/i);
	});

	it('names the sources while stating all-in-scope at three or fewer (2.6 with 2.7)', async () => {
		// The live corpus shape: all three in scope — both obligations hold at once.
		await mount(payload(THREE));
		const text = indicatorButton().textContent ?? '';
		expect(text).toMatch(/all in scope/i);
		expect(text).toMatch(/ableton live-12/i);
		expect(text).toMatch(/akai apc-key-25/i);
		expect(text).toMatch(/your triage notes/i);
	});

	it('names the sources rather than counting them at three or fewer (2.6)', async () => {
		const { scope } = await mount(payload([...THREE, manual('alesis/nitro-max')]));
		scope.toggle('alesis/nitro-max');
		await tick();
		const text = indicatorButton().textContent ?? '';
		expect(text).toMatch(/ableton live-12/i);
		expect(text).toMatch(/akai apc-key-25/i);
		expect(text).toMatch(/your triage notes/i);
	});

	it('names a single in-scope source (3.3)', async () => {
		const { scope } = await mount(payload(THREE));
		scope.selectNone();
		scope.toggle('ableton/live-12');
		await tick();
		expect(indicatorButton().textContent).toMatch(/ableton live-12/i);
	});

	it('falls back to n of m above three in scope (2.5)', async () => {
		const many = [manual('a/1'), manual('b/2'), manual('c/3'), manual('d/4'), manual('e/5')];
		const { scope } = await mount(payload(many));
		scope.toggle('e/5');
		await tick();
		expect(indicatorButton().textContent).toMatch(/4 of 5 sources/i);
	});

	it('distinguishes narrowed from all-sources by shape and label, never colour alone (3.10, 11.6)', async () => {
		const { scope, container } = await mount(payload(THREE));
		const glyph = () => container.querySelector('.scope-glyph');
		const allState = glyph()?.textContent;
		const allLabel = indicatorButton().textContent;
		expect(container.querySelector('[data-scope="all"]')).not.toBeNull();

		scope.toggle('authored/triage');
		await tick();
		expect(container.querySelector('[data-scope="narrowed"]')).not.toBeNull();
		// Two non-colour channels move together: the glyph's shape and the wording.
		expect(glyph()?.textContent).not.toBe(allState);
		expect(indicatorButton().textContent).not.toBe(allLabel);
		expect(indicatorButton().textContent).not.toMatch(/all 3/i);
	});
});

describe('toggling sources (2.2, 2.8, 13.4)', () => {
	it('lists every source as an independently toggleable, keyboard-operable checkbox', async () => {
		const { scope } = await mount(payload(THREE));
		await expand();
		for (const record of THREE) {
			const checkbox = screen.getByRole('checkbox', {
				name: new RegExp(record.display_name, 'i')
			}) as HTMLInputElement;
			expect(checkbox.checked).toBe(true);
			await fireEvent.click(checkbox);
			expect(scope.isSelected(record.source_id)).toBe(false);
			await fireEvent.click(checkbox);
			expect(scope.isSelected(record.source_id)).toBe(true);
		}
	});

	it('offers single all and none controls (2.8)', async () => {
		const { scope } = await mount(payload(THREE));
		await expand();
		await fireEvent.click(screen.getByRole('button', { name: /none in scope/i }));
		expect(scope.selected).toHaveLength(0);
		await fireEvent.click(screen.getByRole('button', { name: /all in scope/i }));
		expect([...scope.selected].sort()).toEqual(THREE.map((s) => s.source_id).sort());
	});

	it('carries in/out-of-scope on a filled-versus-hollow marker plus the word (2.14, 11.6)', async () => {
		const { scope, container } = await mount(payload(THREE));
		await expand();
		const entry = () =>
			[...container.querySelectorAll('li.source')].find((li) =>
				li.textContent?.includes('ableton live-12')
			);
		expect(entry()?.querySelector('.scope-marker')?.textContent).toBe('●');
		expect(entry()?.textContent).toMatch(/in scope/i);

		scope.toggle('ableton/live-12');
		await tick();
		expect(entry()?.querySelector('.scope-marker')?.textContent).toBe('○');
		expect(entry()?.textContent).toMatch(/out of scope/i);
	});

	it('exposes an accessible name on every control and state on every toggle (13.4)', async () => {
		await mount(payload(THREE));
		await expand();
		for (const checkbox of screen.getAllByRole('checkbox')) {
			expect((checkbox as HTMLInputElement).labels?.length ?? 0).toBeGreaterThan(0);
		}
		for (const button of screen.getAllByRole('button')) {
			expect(button.textContent?.trim() || button.getAttribute('aria-label')).toBeTruthy();
		}
	});
});

describe('newness marking (2.4)', () => {
	it('marks a source the picker has not seen before, until the next submitted question', async () => {
		const { scope, container } = await mount(payload(THREE));
		await expand();
		// Nothing has been submitted yet: every reported source is new.
		expect(container.querySelectorAll('.mark.new')).toHaveLength(3);

		// Newness ends at the next submit, not at render.
		scope.noteQuestionSubmitted();
		await tick();
		expect(container.querySelectorAll('.mark.new')).toHaveLength(0);
	});

	it('marks only the unseen source where the others were already submitted against', async () => {
		// A prior session: the two manuals seen, then the triage store appears.
		const seenIds = ['ableton/live-12', 'akai/apc-key-25'];
		localStorage.setItem(
			'dawmans.scope',
			JSON.stringify({ selected: seenIds, seen: seenIds, known: seenIds, lastQuestionAt: Date.now() })
		);
		sessionStorage.setItem('dawmans.session', '1');
		const { container } = await mount(payload(THREE));
		await expand();
		const badged = [...container.querySelectorAll('li.source')].filter(
			(li) => li.querySelector('.mark.new') !== null
		);
		expect(badged).toHaveLength(1);
		expect(badged[0]?.textContent).toMatch(/your triage notes/i);
	});
});

describe('the authored-triage source (2.12)', () => {
	it('lists among the manuals with its kind stated, selectable by the same controls', async () => {
		const { scope, container } = await mount(payload(THREE));
		await expand();
		const checkbox = screen.getByRole('checkbox', { name: /your triage notes/i });
		const entry = checkbox.closest('li');
		expect(entry?.classList.contains('source')).toBe(true); // alongside, not apart
		expect(entry?.textContent).toMatch(/your own notes/i); // the kind, stated on the entry
		expect(container.querySelector('.gaps')?.textContent ?? '').not.toMatch(/triage/i);

		// The same controls as any other source — never always-in-scope.
		await fireEvent.click(checkbox);
		expect(scope.isSelected('authored/triage')).toBe(false);
		await fireEvent.click(screen.getByRole('button', { name: /all in scope/i }));
		expect(scope.isSelected('authored/triage')).toBe(true);
	});
});

describe('marked selectable sources (2.10, CONTRACTS §1 low_text)', () => {
	it('names the revision an assumed-applicability source is taken to describe', async () => {
		const assumed = manual('akai/apc-key-25', {
			hardware_applicability: { status: 'assumed', device: 'APC Key 25 (original)' }
		});
		await mount(
			payload([manual('ableton/live-12'), assumed], {
				documented_but_unconfirmed: [{ source_id: assumed.source_id, display_name: assumed.display_name }]
			})
		);
		await expand();
		const entry = screen.getByRole('checkbox', { name: /akai apc-key-25/i }).closest('li');
		expect(entry?.textContent).toMatch(/APC Key 25 \(original\)/);
		expect(entry?.textContent).toMatch(/unconfirmed/i);
	});

	it('marks a sparse text layer on the entry — the whole consumption obligation on low_text', async () => {
		await mount(payload([manual('alesis/nitro-max', { low_text: true }), manual('ableton/live-12')]));
		await expand();
		const sparse = screen.getByRole('checkbox', { name: /alesis nitro-max/i }).closest('li');
		expect(sparse?.textContent).toMatch(/sparse text/i);
		const ordinary = screen.getByRole('checkbox', { name: /ableton live-12/i }).closest('li');
		expect(ordinary?.textContent).not.toMatch(/sparse text/i);
	});
});

describe('known gaps (2.9)', () => {
	it('lists owned-but-undocumented hardware apart and never selectable', async () => {
		const { container } = await mount(
			payload(THREE, {
				owned_but_undocumented: [
					{ device: 'focusrite/scarlett-2i2', display_name: 'Focusrite Scarlett 2i2' }
				]
			})
		);
		await expand();
		const gaps = container.querySelector('.gaps');
		expect(gaps?.textContent).toMatch(/known gaps/i);
		expect(gaps?.textContent).toMatch(/Focusrite Scarlett 2i2/);
		expect(gaps?.querySelectorAll('input, button')).toHaveLength(0); // never selectable
		// Apart from the selectable list: not a checkbox anywhere.
		expect(screen.queryByRole('checkbox', { name: /scarlett/i })).toBeNull();
	});

	it('is omitted entirely, heading included, when the report is empty — the live case', async () => {
		const { container } = await mount(payload(THREE));
		await expand();
		expect(container.querySelector('.gaps')).toBeNull();
		expect(screen.queryByText(/known gaps/i)).toBeNull();
	});
});

describe('the filter (2.13)', () => {
	const many = (count: number) => Array.from({ length: count }, (_, i) => manual(`vendor${i}/product${i}`));

	it('costs no chrome below the threshold', async () => {
		await mount(payload(THREE));
		await expand();
		expect(screen.queryByRole('textbox', { name: /filter/i })).toBeNull();
	});

	it('offers a substring filter over display_name at twelve sources', async () => {
		await mount(payload(many(12)));
		await expand();
		const filter = screen.getByRole('textbox', { name: /filter/i });
		await fireEvent.input(filter, { target: { value: 'product3' } });
		await tick();
		expect(screen.getAllByRole('checkbox')).toHaveLength(1);
		expect(screen.getByRole('checkbox', { name: /vendor3 product3/i })).toBeTruthy();
	});
});
