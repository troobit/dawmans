// The sources store: available sources and both gap reports (requirements 2.1,
// 2.3, 2.4, 2.9, 2.10, 9.13; design "The source picker" and "Error Handling").
// Everything comes from GET /sources — no fixed source count anywhere.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type {
	AuthoredTriageSourceRecord,
	SourceRecord,
	VendorManualSourceRecord
} from '../engine/records';
import type { SourcesResponse } from '../engine/client';
import { ScopeStore } from './scope.svelte';
import { SourcesStore } from './sources.svelte';

function manual(
	id: string,
	over: Partial<VendorManualSourceRecord> = {}
): VendorManualSourceRecord {
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
	return { sources, owned_undocumented: [], documented_unconfirmed: [], ...over };
}

function stubSources(...bodies: (SourcesResponse | Response)[]): void {
	vi.stubGlobal(
		'fetch',
		vi.fn(() => {
			const next = bodies.shift();
			if (next === undefined) throw new Error('unexpected fetch');
			const response =
				next instanceof Response
					? next
					: new Response(JSON.stringify(next), {
							status: 200,
							headers: { 'content-type': 'application/json' }
						});
			return Promise.resolve(response);
		})
	);
}

beforeEach(() => {
	localStorage.clear();
	sessionStorage.clear();
});

afterEach(() => {
	vi.unstubAllGlobals();
});

describe('loading from the engine (2.1, 2.3)', () => {
	it('exposes every reported source of both kinds with its display_name', async () => {
		stubSources(payload([manual('ableton/live-12'), triage()]));
		const store = new SourcesStore();
		await store.load();
		expect(store.state).toBe('ready');
		expect(store.sources.map((s) => s.source_id)).toEqual(['ableton/live-12', 'authored/triage']);
		expect(store.sources.map((s) => s.display_name)).toEqual([
			'ableton live-12',
			'Your triage notes'
		]);
	});

	it('assumes no fixed source count: an added and a removed source are reflected on the next load', async () => {
		stubSources(
			payload([manual('ableton/live-12'), manual('akai/apc-key-25')]),
			payload([manual('ableton/live-12'), manual('alesis/nitro-max'), triage()])
		);
		const store = new SourcesStore();
		await store.load();
		expect(store.ids).toEqual(['ableton/live-12', 'akai/apc-key-25']);

		await store.load(); // the next load of the ask surface
		expect(store.ids).toEqual(['ableton/live-12', 'alesis/nitro-max', 'authored/triage']);
	});

	it('names a source by id for the scope indicator', async () => {
		stubSources(payload([manual('ableton/live-12', { display_name: 'Ableton Live 12' })]));
		const store = new SourcesStore();
		await store.load();
		expect(store.displayName('ableton/live-12')).toBe('Ableton Live 12');
		expect(store.displayName('gone/source')).toBeUndefined();
	});
});

describe('gap reports (2.9, 2.10)', () => {
	it('carries a populated owned-but-undocumented report from a fixture payload', async () => {
		// The empty report is the live case (CONTRACTS §5); the populated path
		// must come from the payload, never be hardcoded empty.
		stubSources(
			payload([manual('ableton/live-12')], {
				owned_undocumented: [{ device: 'focusrite/scarlett-2i2', display_name: 'Scarlett 2i2' }]
			})
		);
		const store = new SourcesStore();
		await store.load();
		expect(store.ownedUndocumented).toEqual([
			{ device: 'focusrite/scarlett-2i2', display_name: 'Scarlett 2i2' }
		]);
	});

	it('exposes the empty owned-but-undocumented report as empty, the live case today', async () => {
		stubSources(payload([manual('ableton/live-12')]));
		const store = new SourcesStore();
		await store.load();
		expect(store.ownedUndocumented).toEqual([]);
	});

	it('carries the documented-but-unconfirmed report', async () => {
		stubSources(
			payload([manual('akai/apc-key-25')], {
				documented_unconfirmed: [{ source_id: 'akai/apc-key-25', display_name: 'akai apc-key-25' }]
			})
		);
		const store = new SourcesStore();
		await store.load();
		expect(store.documentedUnconfirmed).toEqual([
			{ source_id: 'akai/apc-key-25', display_name: 'akai apc-key-25' }
		]);
	});

	it('carries assumed hardware_applicability with the revision it describes, and low_text (2.10)', async () => {
		stubSources(
			payload([
				manual('akai/apc-key-25', {
					hardware_applicability: { status: 'assumed', device: 'APC Key 25 (original)' }
				}),
				manual('alesis/nitro-max', { low_text: true })
			])
		);
		const store = new SourcesStore();
		await store.load();
		const [apc, nitro] = store.sources;
		expect(apc.hardware_applicability).toEqual({
			status: 'assumed',
			device: 'APC Key 25 (original)'
		});
		expect(nitro.kind === 'vendor-manual' && nitro.low_text).toBe(true);
	});
});

describe('engine unreachable versus corpus-empty (9.13)', () => {
	it('blocks submission before any load has completed', () => {
		const store = new SourcesStore();
		expect(store.state).toBe('loading');
		expect(store.blocksSubmission).toBe(true);
	});

	it('reports the engine unreachable when GET /sources fails, never an empty picker', async () => {
		vi.stubGlobal(
			'fetch',
			vi.fn(() => Promise.reject(new TypeError('fetch failed')))
		);
		const store = new SourcesStore();
		await store.load();
		expect(store.state).toBe('engine-unreachable');
		expect(store.state).not.toBe('corpus-empty');
		expect(store.blocksSubmission).toBe(true);
	});

	it('treats a non-OK response as unreachable too, not as an empty corpus', async () => {
		stubSources(new Response('{}', { status: 500 }));
		const store = new SourcesStore();
		await store.load();
		expect(store.state).toBe('engine-unreachable');
		expect(store.blocksSubmission).toBe(true);
	});

	it('reports corpus-empty when the engine answers with no sources at all', async () => {
		// The engine answering that nothing is ingested — a different state from
		// the engine being unreachable, and it too disables submission.
		stubSources(payload([]));
		const store = new SourcesStore();
		await store.load();
		expect(store.state).toBe('corpus-empty');
		expect(store.blocksSubmission).toBe(true);
	});

	it('recovers to ready on a later successful load', async () => {
		vi.stubGlobal(
			'fetch',
			vi.fn(() => Promise.reject(new TypeError('fetch failed')))
		);
		const store = new SourcesStore();
		await store.load();
		expect(store.state).toBe('engine-unreachable');

		stubSources(payload([manual('ableton/live-12')]));
		await store.load();
		expect(store.state).toBe('ready');
		expect(store.blocksSubmission).toBe(false);
	});
});

describe('newness against the scope store (2.4)', () => {
	// Newness is `source_id ∉ seen[]`; the seen list belongs to the scope store
	// and updates on the next submit, never on render.
	const LIVE = 'ableton/live-12';
	const APC = 'akai/apc-key-25';
	const NEW = 'alesis/nitro-max';

	async function loadBoth(scopeSeed: { selected: string[]; seen: string[]; known: string[] }) {
		localStorage.setItem(
			'dawmans.scope',
			JSON.stringify({ ...scopeSeed, lastQuestionAt: Date.now() })
		);
		sessionStorage.setItem('dawmans.session', '1');
		stubSources(payload([manual(LIVE), manual(APC), manual(NEW)]));
		const sources = new SourcesStore();
		await sources.load();
		const scope = new ScopeStore();
		scope.load(sources.ids);
		return { sources, scope };
	}

	it('a source stays new until the next submit, not until it is rendered', async () => {
		const { scope } = await loadBoth({ selected: [LIVE, APC], seen: [LIVE, APC], known: [LIVE, APC] });
		// Rendering the picker changes nothing; the id is still unseen.
		expect(scope.seen).not.toContain(NEW);
		scope.noteQuestionSubmitted();
		expect(scope.seen).toContain(NEW);
	});

	it('a new source enters scope where the stored scope was all available sources', async () => {
		const { scope } = await loadBoth({ selected: [LIVE, APC], seen: [LIVE, APC], known: [LIVE, APC] });
		expect([...scope.selected].sort()).toEqual([LIVE, NEW, APC].sort());
	});

	it('a new source stays out of a narrowed scope, one activation from joining', async () => {
		const { scope } = await loadBoth({ selected: [LIVE], seen: [LIVE, APC], known: [LIVE, APC] });
		expect([...scope.selected]).toEqual([LIVE]);
		scope.toggle(NEW); // the one-activation add
		expect([...scope.selected].sort()).toEqual([LIVE, NEW].sort());
	});
});
