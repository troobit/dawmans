// Integration over the assembled page (tasks 45/46; requirements 1.13, 10.2,
// 10.11; design "Testing Strategy"). Full turns travel the real path — client
// → sse → reducer → renderer — against the fake engine server; nothing here
// drives a Turn directly. The keyboard-only core loop, the region transitions
// and CONTRACTS §4b's event coverage are asserted at this integrated level so
// a wiring gap cannot pass the unit suites and still drop an event.

import { cleanup, fireEvent, render, screen, within } from '@testing-library/svelte';
import { tick } from 'svelte';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { vi } from 'vitest';
import type { ProviderStatus, SourcesResponse } from '$lib/engine/client';
import type {
	AuthoredTriageSourceRecord,
	Citation,
	Passage,
	TurnEvent,
	VendorManualSourceRecord
} from '$lib/engine/records';
import { KeyRouter } from '$lib/keys';
import { HistoryStore } from '$lib/state/history.svelte';
import { ProviderStore } from '$lib/state/provider.svelte';
import { ScopeStore, SCOPE_STORAGE_KEY } from '$lib/state/scope.svelte';
import { SourcesStore } from '$lib/state/sources.svelte';
import { ThreadStore } from '$lib/state/thread.svelte';
import { installFakeEngine, type FakeEngineOptions } from '$lib/testing/fake-server';
import Page from './+page.svelte';

// ---------------------------------------------------------------------------
// Fixtures: the live corpus shape — two manuals and the authored store.

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
		doc_version: '12',
		page_count: 700,
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

const THREE: SourcesResponse = {
	sources: [manual('ableton/live-12'), manual('akai/apc-key-25'), triage()],
	owned_but_undocumented: [],
	documented_but_unconfirmed: []
};

const LOCAL_PROVIDER: ProviderStatus = { kind: 'local', model: 'ollama/llama', masked: null };

const VENDOR_CITE: Citation = {
	kind: 'vendor-manual',
	source_id: 'ableton/live-12',
	display_name: 'ableton live-12',
	passage_id: 'ableton/live-12-0001',
	section_number: '14.2',
	section_title: 'Routing',
	hardware_applicability: { status: 'confirmed' },
	degraded: false,
	has_figures: false,
	doc_version: '12',
	page: 312
};

const VENDOR_PASSAGE: Passage = {
	passage_id: 'ableton/live-12-0001',
	source_id: 'ableton/live-12',
	section_number: '14.2',
	section_title: 'Routing',
	page_start: 312,
	page_end: 312,
	text: 'Set the monitor switch to Auto.',
	degraded: false,
	has_figures: false
};

// ---------------------------------------------------------------------------
// Harness

/**
 * SSE frames travel entirely on microtasks with the stub channel, but the
 * full client → sse → reducer path spends several per frame — a short flush
 * leaves a many-event turn still streaming. Deep is cheap; shallow is flaky.
 */
async function flush(): Promise<void> {
	for (let index = 0; index < 200; index += 1) await Promise.resolve();
	await tick();
}

async function mountPage(options: FakeEngineOptions = {}) {
	const server = installFakeEngine({
		sources: THREE,
		provider: LOCAL_PROVIDER,
		passages: [VENDOR_PASSAGE],
		...options
	});
	const router = new KeyRouter();
	const sources = new SourcesStore();
	const scope = new ScopeStore();
	const history = new HistoryStore();
	const provider = new ProviderStore();
	const thread = new ThreadStore({ scope, history });
	const result = render(Page, {
		props: { sources, scope, thread, history, provider, router }
	});
	await flush(); // the mount loads sources → scope, and the provider status
	return { server, router, sources, scope, history, provider, thread, ...result };
}

type Harness = Awaited<ReturnType<typeof mountPage>>;

function askInput(): HTMLTextAreaElement {
	return screen.getByRole('textbox', { name: 'Ask a question' }) as HTMLTextAreaElement;
}

/** Submit a question from the keyboard and play the scripted events at the engine. */
async function ask(
	harness: Harness,
	question: string,
	events: readonly { event: string; data: unknown }[],
	{ close = true }: { close?: boolean } = {}
): Promise<void> {
	harness.thread.draft = question;
	await tick();
	await fireEvent.keyDown(askInput(), { key: 'Enter' });
	await flush();
	const channel = harness.server.lastChannel();
	for (const { event, data } of events) channel.emit(event, data);
	if (close) channel.close();
	await flush();
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

// ---------------------------------------------------------------------------

describe('assembly: one surface, loaded from the engine', () => {
	it('renders the scope bar, the thread, and the ask input once the sources load', async () => {
		await mountPage();
		expect(screen.getByText(/All in scope:/)).toBeTruthy();
		expect(screen.getByRole('region', { name: 'Conversation' })).toBeTruthy();
		expect(askInput()).toBeTruthy();
		expect(screen.getByRole('button', { name: 'History' })).toBeTruthy();
		expect(screen.getByRole('button', { name: 'Provider configuration' })).toBeTruthy();
	});

	it('reports the engine unreachable — never an empty picker — and blocks submission (9.13)', async () => {
		const harness = await mountPage({ failSources: true });
		expect(screen.getByText(/engine could not be reached/i)).toBeTruthy();
		expect(screen.queryByRole('textbox', { name: 'Ask a question' })).toBeNull();
		// 9.2: no state dead-ends; the retry recovers once the engine answers.
		harness.server.failSources = false;
		await fireEvent.click(screen.getByRole('button', { name: /retry/i }));
		await flush();
		expect(screen.getByText(/All in scope:/)).toBeTruthy();
		expect(askInput()).toBeTruthy();
	});

	it('renders corpus-empty as the engine answering nothing is ingested, naming manuals/ (9.13)', async () => {
		await mountPage({
			sources: { sources: [], owned_but_undocumented: [], documented_but_unconfirmed: [] }
		});
		expect(screen.getByText(/manuals\//)).toBeTruthy();
		expect(screen.queryByRole('textbox', { name: 'Ask a question' })).toBeNull();
	});

	it('states a released narrowing with a one-activation reinstate (3.6)', async () => {
		// A narrowed scope stored by an earlier session: no session marker exists.
		localStorage.setItem(
			SCOPE_STORAGE_KEY,
			JSON.stringify({
				selected: ['ableton/live-12'],
				seen: ['ableton/live-12', 'akai/apc-key-25', 'authored/triage'],
				known: ['ableton/live-12', 'akai/apc-key-25', 'authored/triage'],
				lastQuestionAt: Date.now()
			})
		);
		const harness = await mountPage();
		expect(harness.scope.selected).toHaveLength(3);
		expect(screen.getByText(/released/i)).toBeTruthy();
		await fireEvent.click(screen.getByRole('button', { name: /reinstate/i }));
		await tick();
		expect([...harness.scope.selected]).toEqual(['ableton/live-12']);
	});
});

describe('full turns through client → sse → reducer → renderer', () => {
	it('renders an answered turn: direct answer first, blocks, citation entry, finished state', async () => {
		const harness = await mountPage();
		await ask(harness, 'no sound from live', [
			{ event: 'outcome', data: { outcome: 'answered' } },
			{ event: 'direct_answer', data: { text: 'Unmute the master track.' } },
			{
				event: 'body_delta',
				data: { text: '1. Open the routing panel.\nCheck the mutes [[p:ableton/live-12-0001]].\n' }
			},
			{ event: 'citation', data: VENDOR_CITE },
			{ event: 'done', data: { complete: true } }
		]);
		expect(screen.getByText('Unmute the master track.')).toBeTruthy();
		expect(document.querySelector('.step')?.textContent).toContain('Open the routing panel.');
		expect(document.querySelector('.citation-entry')?.textContent).toContain('ableton live-12');
		expect(document.querySelector('.state')?.textContent).toBe('finished');
	});

	it('renders a partial answer with its uncovered parts subordinate to the answer (4.8)', async () => {
		const harness = await mountPage();
		await ask(harness, 'no sound and my pad colours', [
			{ event: 'outcome', data: { outcome: 'partially-answered' } },
			{ event: 'direct_answer', data: { text: 'Unmute the master track.' } },
			{ event: 'uncovered_parts', data: { parts: ['pad colours'] } },
			{ event: 'done', data: { complete: true } }
		]);
		const uncovered = document.querySelector('.uncovered');
		expect(uncovered?.textContent).toContain('pad colours');
		expect(screen.getByRole('button', { name: /re-ask: pad colours/i })).toBeTruthy();
	});

	it('renders a narrowing turn with its candidates numbered in engine order (§6)', async () => {
		const harness = await mountPage();
		await ask(harness, 'no sound', [
			{ event: 'outcome', data: { outcome: 'needs-narrowing' } },
			{
				event: 'narrowing',
				data: { question: 'No sound from where?', candidates: [
						{ label: 'Live shows no output', value: 'From Live' },
						{ label: 'The APC pads are unlit', value: 'From the APC' }
					] }
			},
			{ event: 'done', data: { complete: true } }
		]);
		const narrowing = document.querySelector('.narrowing');
		expect(narrowing?.textContent).toContain('No sound from where?');
		const digits = [...(narrowing?.querySelectorAll('kbd') ?? [])].map((k) => k.textContent);
		expect(digits).toEqual(['1', '2']);
	});

	it('renders ranked causes in array order, never as armed digit controls (6.6)', async () => {
		const harness = await mountPage();
		await ask(harness, 'distorting', [
			{ event: 'outcome', data: { outcome: 'ranked-causes' } },
			{ event: 'direct_answer', data: { text: 'Check the input gain first.' } },
			{
				event: 'cause',
				data: {
					rank: 1,
					statement: 'Input gain too hot',
					check: 'the input meter',
					cites: ['ableton/live-12-0001'],
					fix_cites: []
				}
			},
			{
				event: 'cause',
				data: {
					rank: 2,
					statement: 'Master limiter engaged',
					check: 'the master chain',
					cites: [],
					fix_cites: []
				}
			},
			{ event: 'citation', data: VENDOR_CITE },
			{ event: 'done', data: { complete: true } }
		]);
		const causes = [...document.querySelectorAll('.cause')];
		expect(causes).toHaveLength(2);
		expect(causes[0].textContent).toContain('Input gain too hot');
		expect(causes[0].querySelector('button')).toBeNull();
		expect(causes[0].querySelector('kbd')).toBeNull();
	});

	it('renders a coverage failure whose add-and-re-ask widens scope and re-submits (7.4)', async () => {
		const harness = await mountPage();
		// Narrow the scope so the suggestion is out of scope.
		harness.scope.selectNone();
		harness.scope.toggle('ableton/live-12');
		await tick();
		await ask(harness, 'wrong drum sound', [
			{ event: 'outcome', data: { outcome: 'refused-not-covered' } },
			{
				event: 'suggested_sources',
				data: [{ source_id: 'akai/apc-key-25', display_name: 'akai apc-key-25' }]
			},
			{ event: 'done', data: { complete: true } }
		]);
		expect(document.querySelector('.coverage-failure')).toBeTruthy();
		await fireEvent.click(screen.getByRole('button', { name: /add akai apc-key-25 and re-ask/i }));
		await flush();
		expect(harness.scope.isSelected('akai/apc-key-25')).toBe(true);
		expect(harness.server.requests).toHaveLength(2);
		expect(harness.server.requests[1].question).toBe('wrong drum sound');
	});

	it('renders no-manual-for-device with the copyable filename (7.7)', async () => {
		const harness = await mountPage();
		await ask(harness, 'my volca keys detunes', [
			{ event: 'outcome', data: { outcome: 'no-manual-for-device' } },
			{ event: 'required_device', data: { device: 'korg/volca-keys', display_name: 'Volca Keys' } },
			{
				event: 'required_manual',
				data: { filename: 'korg_volca-keys_manual_v1.0_en.pdf', placeholders: [] }
			},
			{ event: 'done', data: { complete: true } }
		]);
		expect(screen.getByText(/korg_volca-keys_manual_v1\.0_en\.pdf/)).toBeTruthy();
		expect(screen.getByRole('button', { name: /copy filename/i })).toBeTruthy();
	});

	const ERROR_OUTCOMES: [string, Record<string, unknown>, RegExp][] = [
		// 9.5: the wording keys on the reason sub-code, never on detail.
		['provider-unconfigured', { reason: 'no-provider-kind' }, /no provider is chosen/i],
		['provider-unreachable', {}, /could not reach/i],
		['timeout', {}, /stalled/i],
		['provider-rate-limited', { retry_after: 30 }, /retry in 30 s/i],
		['provider-error', { reason: 'authentication-failed' }, /rejected the stored credential/i],
		['provider-error', {}, /failed or rejected/i]
	];

	it.each(ERROR_OUTCOMES)(
		'renders %s as an error state with its wording and an action (§9)',
		async (outcome, extra, wording) => {
			const harness = await mountPage();
			await ask(harness, 'no sound', [
				{ event: 'outcome', data: { outcome, ...extra } },
				{ event: 'done', data: { complete: true } }
			]);
			const error = document.querySelector('.error');
			expect(error).toBeTruthy();
			expect(error?.textContent).toMatch(wording);
			expect(error?.querySelector('button')).toBeTruthy();
		}
	);

	it('renders corpus-empty naming manuals/ and the ingestion step — no in-app control exists', async () => {
		const harness = await mountPage();
		await ask(harness, 'no sound', [
			{ event: 'outcome', data: { outcome: 'corpus-empty' } },
			{ event: 'done', data: { complete: true } }
		]);
		const error = document.querySelector('.error');
		expect(error?.textContent).toMatch(/manuals\//);
		expect(error?.textContent).toMatch(/ingestion/i);
	});

	it('renders no-sources-selected as the blocked state, never as a failure (9.12)', async () => {
		const harness = await mountPage();
		await ask(harness, 'no sound', [
			{ event: 'outcome', data: { outcome: 'no-sources-selected' } },
			{ event: 'done', data: { complete: true } }
		]);
		expect(document.querySelector('.empty-scope')).toBeTruthy();
		expect(document.querySelector('.error')).toBeNull();
	});

	it('renders an unknown outcome as a broken state carrying detail (9.4)', async () => {
		const harness = await mountPage();
		await ask(harness, 'no sound', [
			{ event: 'outcome', data: { outcome: 'mystery', detail: 'engine detail text' } },
			{ event: 'done', data: { complete: true } }
		]);
		expect(document.querySelector('.error.broken')).toBeTruthy();
		expect(document.querySelector('details.diagnostics')?.textContent).toContain(
			'engine detail text'
		);
	});

	it('marks a stream that ends without done incomplete, retaining what arrived (9.14)', async () => {
		const harness = await mountPage();
		await ask(
			harness,
			'no sound',
			[
				{ event: 'outcome', data: { outcome: 'answered' } },
				{ event: 'direct_answer', data: { text: 'Unmute the master track.' } }
			],
			{ close: true } // closed with no done event
		);
		expect(screen.getByText('Unmute the master track.')).toBeTruthy();
		expect(screen.getByText(/incomplete/i)).toBeTruthy();
		expect(screen.getByRole('button', { name: 'Retry' })).toBeTruthy();
	});

	it('returns a stopped turn to a ready state with the question preserved (8.6)', async () => {
		const harness = await mountPage();
		await ask(
			harness,
			'no sound from live',
			[
				{ event: 'outcome', data: { outcome: 'answered' } },
				{ event: 'body_delta', data: { text: 'Check the ' } }
			],
			{ close: false }
		);
		await fireEvent.click(screen.getByRole('button', { name: 'Stop' }));
		await flush();
		expect(document.querySelector('.state')?.textContent).toBe('stopped');
		expect(harness.thread.draft).toBe('no sound from live');
	});
});

describe('the keyboard-only core loop (1.13)', () => {
	it('captures a printable key from anywhere into the question input (1.2)', async () => {
		const harness = await mountPage();
		(document.activeElement as HTMLElement | null)?.blur();
		await fireEvent.keyDown(window, { key: 'n' });
		expect(harness.thread.draft).toBe('n');
		expect(document.activeElement).toBe(askInput());
	});

	it('asks, narrows by digit, and follows up in the same conversation (6.3, 6.4)', async () => {
		const harness = await mountPage();
		await ask(harness, 'no sound', [
			{ event: 'outcome', data: { outcome: 'needs-narrowing' } },
			{
				event: 'narrowing',
				data: { question: 'No sound from where?', candidates: [
						{ label: 'Live shows no output', value: 'From Live' },
						{ label: 'The APC pads are unlit', value: 'From the APC' }
					] }
			},
			{ event: 'done', data: { complete: true } }
		]);
		await fireEvent.keyDown(window, { key: '2' });
		await flush();
		expect(harness.server.requests).toHaveLength(2);
		expect(harness.server.requests[1].question).toBe('From the APC');
		// 6.4: a follow-up in the same conversation, not a new one.
		expect(harness.server.requests[1].conversation_id).not.toBeNull();
	});

	it('widens scope from the picker and dismisses it with Escape back to its opener (13.3)', async () => {
		const harness = await mountPage();
		harness.scope.selectNone();
		harness.scope.toggle('ableton/live-12');
		await tick();
		const indicator = document.querySelector('button[aria-expanded]') as HTMLButtonElement;
		await fireEvent.click(indicator);
		await tick();
		await fireEvent.click(screen.getByRole('button', { name: 'All in scope' }));
		await tick();
		expect(harness.scope.selected).toHaveLength(3);
		await fireEvent.keyDown(window, { key: 'Escape' });
		await tick();
		expect(indicator.getAttribute('aria-expanded')).toBe('false');
		expect(document.activeElement).toBe(indicator);
	});

	it('expands a citation in place and offers open-at-source at exactly #page=N (5.5, 5.6)', async () => {
		const harness = await mountPage();
		await ask(harness, 'no sound', [
			{ event: 'outcome', data: { outcome: 'answered' } },
			{ event: 'direct_answer', data: { text: 'Unmute the master track.' } },
			{ event: 'body_delta', data: { text: 'Check the mutes [[p:ableton/live-12-0001]].\n' } },
			{ event: 'citation', data: VENDOR_CITE },
			{ event: 'done', data: { complete: true } }
		]);
		await fireEvent.click(screen.getByRole('button', { name: 'Show passage' }));
		await flush();
		expect(screen.getByText('Set the monitor switch to Auto.')).toBeTruthy();
		const open = screen.getByRole('link', { name: /open manual at p312/i });
		expect(open.getAttribute('href')).toBe('/sources/ableton/live-12/document#page=312');
		expect(open.getAttribute('target')).toBe('_blank');
	});
});

describe('region transitions preserve the question and the scope (10.2, 10.11)', () => {
	async function narrowAndDraft(harness: Harness): Promise<void> {
		harness.thread.draft = 'why is the master silent';
		harness.scope.selectNone();
		harness.scope.toggle('ableton/live-12');
		await tick();
	}

	it('into and out of history, dismissed with Escape back to its opener (12.8, 13.3)', async () => {
		const harness = await mountPage();
		await narrowAndDraft(harness);
		const opener = screen.getByRole('button', { name: 'History' });
		await fireEvent.click(opener);
		await tick();
		expect(screen.getByRole('region', { name: 'History' })).toBeTruthy();
		await fireEvent.keyDown(window, { key: 'Escape' });
		await tick();
		expect(screen.queryByRole('region', { name: 'History' })).toBeNull();
		expect(document.activeElement).toBe(opener);
		expect(harness.thread.draft).toBe('why is the master silent');
		expect([...harness.scope.selected]).toEqual(['ableton/live-12']);
	});

	it('into and out of provider configuration via save, question and scope intact (10.11)', async () => {
		const harness = await mountPage();
		await narrowAndDraft(harness);
		await fireEvent.click(screen.getByRole('button', { name: 'Provider configuration' }));
		await tick();
		const config = screen.getByRole('region', { name: 'Provider configuration' });
		await fireEvent.click(within(config).getByLabelText('Local model on this machine'));
		await tick();
		const model = within(config).getByLabelText('Endpoint or model');
		await fireEvent.input(model, { target: { value: 'ollama/llama3' } });
		await fireEvent.click(within(config).getByRole('button', { name: 'Save' }));
		await flush();
		expect(screen.queryByRole('region', { name: 'Provider configuration' })).toBeNull();
		expect(harness.thread.draft).toBe('why is the master silent');
		expect([...harness.scope.selected]).toEqual(['ableton/live-12']);
	});

	it('dismisses provider configuration with Escape back to its opener (13.3)', async () => {
		await mountPage();
		const opener = screen.getByRole('button', { name: 'Provider configuration' });
		await fireEvent.click(opener);
		await tick();
		expect(screen.getByRole('region', { name: 'Provider configuration' })).toBeTruthy();
		await fireEvent.keyDown(window, { key: 'Escape' });
		await tick();
		expect(screen.queryByRole('region', { name: 'Provider configuration' })).toBeNull();
		expect(document.activeElement).toBe(opener);
	});
});

describe('the shared-backend disclosure gates the first turn (10.4)', () => {
	it('blocks submission until the disclosure is acknowledged, then submits', async () => {
		const harness = await mountPage({
			provider: { kind: 'shared-backend', masked: null }
		});
		expect(screen.getByText(/leave the machine|leave this machine/i)).toBeTruthy();
		harness.thread.draft = 'no sound';
		await tick();
		await fireEvent.keyDown(askInput(), { key: 'Enter' });
		await flush();
		expect(harness.server.requests).toHaveLength(0);

		await fireEvent.click(screen.getByRole('button', { name: 'Open provider configuration' }));
		await tick();
		const config = screen.getByRole('region', { name: 'Provider configuration' });
		await fireEvent.click(within(config).getByRole('button', { name: /acknowledge/i }));
		await tick();
		await fireEvent.keyDown(window, { key: 'Escape' });
		await tick();

		await fireEvent.keyDown(askInput(), { key: 'Enter' });
		await flush();
		expect(harness.server.requests).toHaveLength(1);
		expect(harness.server.requests[0].question).toBe('no sound');
	});
});

describe('CONTRACTS §4b: every governed event discharges into something visible', () => {
	it('drives all sixteen events through real turns and finds each on screen', async () => {
		const harness = await mountPage();

		// Turn 1 — the answered family carries ten of the sixteen.
		await ask(harness, 'no sound from live', [
			{
				event: 'scope_dropped',
				data: [{ source_id: 'gone/source', display_name: 'A Removed Manual' }]
			},
			{ event: 'outcome', data: { outcome: 'partially-answered' } },
			{ event: 'direct_answer', data: { text: 'Unmute the master track.' } },
			{ event: 'body_delta', data: { text: 'Check the mutes [[p:ableton/live-12-0001]].\n' } },
			{ event: 'citation', data: VENDOR_CITE },
			{ event: 'contributing_sources', data: { sources: ['ableton/live-12'] } },
			{ event: 'uncovered_parts', data: { parts: ['pad colours'] } },
			{ event: 'ungrounded', data: { ungrounded: true } },
			{ event: 'framing', data: { framing: 'unparsed' } },
			{
				event: 'timings',
				data: {
					retrieval_ms: 12,
					state_acquisition_ms: 3,
					engine_overhead_ms: 8,
					first_token_ms: 420,
					completion_ms: 1800
				}
			},
			{ event: 'done', data: { complete: true } }
		]);

		// Turn 2 — narrowing.
		await ask(harness, 'still no sound', [
			{ event: 'outcome', data: { outcome: 'needs-narrowing' } },
			{
				event: 'narrowing',
				data: { question: 'No sound from where?', candidates: [
						{ label: 'Live shows no output', value: 'From Live' },
						{ label: 'The APC pads are unlit', value: 'From the APC' }
					] }
			},
			{ event: 'done', data: { complete: true } }
		]);

		// Turn 3 — ranked causes.
		await fireEvent.keyDown(window, { key: '1' });
		await flush();
		harness.server.lastChannel().emit('outcome', { outcome: 'ranked-causes' });
		harness.server.lastChannel().emit('cause', {
			rank: 1,
			statement: 'Input gain too hot',
			check: 'the input meter',
			cites: [],
			fix_cites: []
		});
		harness.server.lastChannel().emit('done', { complete: true });
		harness.server.lastChannel().close();
		await flush();

		// Turn 4 — the coverage family carries the remaining three.
		await ask(harness, 'my volca keys detunes', [
			{ event: 'outcome', data: { outcome: 'no-manual-for-device' } },
			{ event: 'required_device', data: { device: 'korg/volca-keys', display_name: 'Volca Keys' } },
			{
				event: 'required_manual',
				data: { filename: 'korg_volca-keys_manual_v1.0_en.pdf', placeholders: ['doc_version'] }
			},
			{ event: 'suggested_sources', data: [] },
			{ event: 'done', data: { complete: true } }
		]);

		// One visible discharge per governed event; the Record over the union is
		// the totality guard — a seventeenth event fails the type check here.
		const discharged: Record<TurnEvent['event'], () => void> = {
			scope_dropped: () => expect(screen.getByText(/A Removed Manual/)).toBeTruthy(),
			outcome: () => expect(document.querySelector('.uncovered')).toBeTruthy(),
			direct_answer: () => expect(screen.getByText('Unmute the master track.')).toBeTruthy(),
			body_delta: () => expect(screen.getByText(/check the mutes/i)).toBeTruthy(),
			citation: () => expect(document.querySelector('.citation-entry')).toBeTruthy(),
			cause: () => expect(document.querySelector('.cause')?.textContent).toContain('Input gain'),
			contributing_sources: () =>
				expect(document.querySelector('.contributing')?.textContent).toMatch(/answered from/i),
			uncovered_parts: () =>
				expect(document.querySelector('.uncovered')?.textContent).toContain('pad colours'),
			suggested_sources: () =>
				// Rendered through 7.4's add-and-re-ask control on the coverage turn;
				// an empty array asserts nothing was invented for it.
				expect(document.querySelector('.coverage-failure')).toBeTruthy(),
			narrowing: () =>
				expect(document.querySelector('.narrowing')?.textContent).toContain(
					'No sound from where?'
				),
			required_device: () => expect(screen.getAllByText(/volca keys/i).length).toBeGreaterThan(0),
			required_manual: () =>
				expect(screen.getByText(/korg_volca-keys_manual_v1\.0_en\.pdf/)).toBeTruthy(),
			ungrounded: () => expect(document.querySelector('.ungrounded')).toBeTruthy(),
			framing: () =>
				// 9.3: unparsed framing opens the disclosure on a successful turn too.
				expect(document.querySelector('details.diagnostics')).toBeTruthy(),
			timings: () =>
				expect(document.querySelector('details.diagnostics')?.textContent).toContain(
					'retrieval_ms: 12'
				),
			done: () =>
				expect(
					[...document.querySelectorAll('.state')].map((state) => state.textContent)
				).toContain('finished')
		};
		for (const assertion of Object.values(discharged)) assertion();
	});
});
