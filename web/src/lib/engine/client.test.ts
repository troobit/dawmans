// Tests for the engine client (requirements 5.5, 5.6, 9.15; design "The
// engine client"). The nine operations of api/answer-engine 9.4 map to their
// routes, all relative — no host and no port hard-coded anywhere (Decision 1).
// No retries: an unasked retry would duplicate a turn or mask the
// provider-unreachable state 9.6 requires the user to see.

import { afterEach, describe, expect, it, vi } from 'vitest';
import {
	EngineRejection,
	clearCredential,
	fetchPassage,
	getProviderStatus,
	listSources,
	serveDocumentHref,
	setCredential,
	setProvider,
	submitQuestion,
	testProvider
} from './client';

type Call = { url: string; init: RequestInit | undefined };

/** Stub fetch, recording every call and answering each with the next response. */
function stubFetch(...responses: Response[]): Call[] {
	const calls: Call[] = [];
	vi.stubGlobal(
		'fetch',
		vi.fn((url: string, init?: RequestInit) => {
			calls.push({ url, init });
			const response = responses.shift();
			if (response === undefined) throw new Error('unexpected fetch');
			return Promise.resolve(response);
		})
	);
	return calls;
}

function json(body: unknown, status = 200): Response {
	return new Response(JSON.stringify(body), {
		status,
		headers: { 'content-type': 'application/json' }
	});
}

afterEach(() => {
	vi.unstubAllGlobals();
});

describe('route mapping', () => {
	it('maps submit-question to POST /turn and returns the unread response', async () => {
		const stream = new Response('event: done\ndata: {"complete":true}\n\n', { status: 200 });
		const calls = stubFetch(stream);
		const response = await submitQuestion({
			conversation_id: null,
			question: 'why is the track silent',
			sources: ['ableton/live-12']
		});
		expect(calls[0].url).toBe('/turn');
		expect(calls[0].init?.method).toBe('POST');
		expect(JSON.parse(calls[0].init?.body as string)).toEqual({
			conversation_id: null,
			question: 'why is the track silent',
			sources: ['ableton/live-12']
		});
		// The client hands the stream back unread: the version check and the
		// frame reading belong to sse.ts, before which no body byte is consumed.
		expect(response.bodyUsed).toBe(false);
	});

	it('maps fetch-passage to GET /passages/{passage_id}, id verbatim', async () => {
		const passage = {
			passage_id: 'ableton/live-12/abc123',
			source_id: 'ableton/live-12',
			section_title: 'Track Activator',
			text: 'To mute the track…',
			degraded: false,
			has_figures: false
		};
		const calls = stubFetch(json(passage));
		const parsed = await fetchPassage('ableton/live-12/abc123');
		// source_id prefixes passage_id (CONTRACTS §1), so the id contains
		// slashes; they are path structure, never percent-encoded away.
		expect(calls[0].url).toBe('/passages/ableton/live-12/abc123');
		expect(calls[0].init?.method ?? 'GET').toBe('GET');
		expect(parsed).toEqual(passage);
	});

	it('maps list-sources to GET /sources and returns records plus both gap reports', async () => {
		const body = {
			sources: [
				{
					kind: 'authored-triage',
					source_id: 'authored/triage',
					display_name: 'My triage notes',
					hardware_applicability: { status: 'assumed' },
					ingested_at: '2026-08-01T00:00:00Z',
					chunk_count: 12
				}
			],
			owned_but_undocumented: [{ device: 'focusrite/scarlett-solo', display_name: 'Scarlett Solo' }],
			documented_but_unconfirmed: [{ source_id: 'akai/apc-key-25', display_name: 'APC Key 25 guide' }]
		};
		const calls = stubFetch(json(body));
		const parsed = await listSources();
		expect(calls[0].url).toBe('/sources');
		expect(parsed).toEqual(body);
	});

	it('maps the five provider operations to their routes and methods', async () => {
		const status = { kind: 'keyed-hosted', model: 'claude-sonnet-5', masked: '…abcd' };
		const calls = stubFetch(
			json(status),
			json(status),
			json(status),
			json({ kind: null, model: undefined, masked: null }),
			json({ reachable: true })
		);
		await getProviderStatus();
		await setProvider({ kind: 'keyed-hosted', model: 'claude-sonnet-5' });
		await setCredential('sk-real-key-value');
		await clearCredential();
		await testProvider();
		expect(calls.map((call) => [call.url, call.init?.method ?? 'GET'])).toEqual([
			['/provider', 'GET'],
			['/provider', 'PUT'],
			['/provider/credential', 'PUT'],
			['/provider/credential', 'DELETE'],
			['/provider/test', 'POST']
		]);
	});

	it('sends the credential only in the PUT body, never in the URL', async () => {
		const calls = stubFetch(json({ kind: 'keyed-hosted', masked: '…alue' }));
		await setCredential('sk-real-key-value');
		expect(calls[0].url).not.toContain('sk-real-key-value');
		expect(calls[0].url).not.toContain('?');
		expect(JSON.parse(calls[0].init?.body as string)).toEqual({ key: 'sk-real-key-value' });
	});

	it('hard-codes no host and no port: every route is relative', async () => {
		const calls = stubFetch(json({ sources: [], owned_but_undocumented: [], documented_but_unconfirmed: [] }));
		await listSources();
		expect(calls[0].url.startsWith('/')).toBe(true);
		expect(calls[0].url).not.toMatch(/^[a-z]+:\/\//);
		expect(serveDocumentHref('ableton/live-12', 5).startsWith('/')).toBe(true);
	});
});

describe('serve-document href (5.5)', () => {
	it('is the route plus the fragment #page=N and nothing else', () => {
		expect(serveDocumentHref('ableton/live-12', 497)).toBe(
			'/sources/ableton/live-12/document#page=497'
		);
	});

	it('appends no zoom, view or text directive — any of them disables the jump in at least one viewer', () => {
		const href = serveDocumentHref('akai/apc-key-25', 12);
		expect(href.endsWith('#page=12')).toBe(true);
		expect(href).not.toContain('&');
		expect(href).not.toContain('zoom');
		expect(href).not.toContain('view');
	});
});

describe('no retries', () => {
	it('a network failure rejects after exactly one attempt', async () => {
		const attempts = vi.fn(() => Promise.reject(new TypeError('fetch failed')));
		vi.stubGlobal('fetch', attempts);
		await expect(listSources()).rejects.toThrow();
		expect(attempts).toHaveBeenCalledTimes(1);
	});

	it('an HTTP failure rejects after exactly one attempt', async () => {
		const calls = stubFetch(json({ rejected: 'origin-not-allowed' }, 403));
		await expect(fetchPassage('x/y/z')).rejects.toBeInstanceOf(EngineRejection);
		expect(calls).toHaveLength(1);
	});
});

describe('non-envelope HTTP failures (9.15)', () => {
	it('a 422 question-too-long surfaces as a typed rejection carrying what was rejected', async () => {
		// api/answer-engine 9.12: {"rejected": "question-too-long", "limit": 1000,
		// "received": N}, and no outcome field — no turn was started.
		stubFetch(json({ rejected: 'question-too-long', limit: 1000, received: 1042 }, 422));
		const failure = await submitQuestion({
			conversation_id: null,
			question: 'x'.repeat(1042),
			sources: ['ableton/live-12']
		}).then(
			() => null,
			(thrown: unknown) => thrown
		);
		expect(failure).toBeInstanceOf(EngineRejection);
		const rejection = failure as EngineRejection;
		expect(rejection.status).toBe(422);
		expect(rejection.rejected).toBe('question-too-long');
		expect(rejection.body).toEqual({ rejected: 'question-too-long', limit: 1000, received: 1042 });
	});

	it('a 403 host/origin rejection surfaces as a typed rejection, distinct from any outcome', async () => {
		stubFetch(json({ rejected: 'origin-not-allowed' }, 403));
		const failure = await listSources().then(
			() => null,
			(thrown: unknown) => thrown
		);
		expect(failure).toBeInstanceOf(EngineRejection);
		const rejection = failure as EngineRejection;
		expect(rejection.status).toBe(403);
		expect(rejection.rejected).toBe('origin-not-allowed');
		// A rejection describes a request, never a turn: nothing on it is an
		// outcome, so it cannot be mistaken for a member of CONTRACTS §6.
		expect('outcome' in rejection).toBe(false);
	});

	it('a rejection body that is not JSON still names the HTTP status', async () => {
		stubFetch(new Response('Internal Server Error', { status: 500 }));
		const failure = await getProviderStatus().then(
			() => null,
			(thrown: unknown) => thrown
		);
		expect(failure).toBeInstanceOf(EngineRejection);
		expect((failure as EngineRejection).rejected).toBe('http-500');
	});
});
