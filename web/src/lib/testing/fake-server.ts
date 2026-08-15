// The fake SSE server standing in for the whole engine (design "Testing
// Strategy"): a global-fetch stub covering every route client.ts reaches, so
// integration tests exercise the real client → sse → reducer → renderer path
// with no provider, corpus or key. Turn streams are the controllable channels
// of turn-channel.ts, one per POST /turn, wired to the abort signal the way a
// real fetch would be.

import { vi } from 'vitest';
import type { ProviderStatus, SourcesResponse, TurnRequest } from '../engine/client';
import type { Passage } from '../engine/records';
import { sseChannel, type TurnChannel } from './turn-channel';

export type FakeEngineServer = {
	/** Every POST /turn body, in arrival order. */
	requests: TurnRequest[];
	/** One controllable stream per POST /turn, same order as `requests`. */
	channels: TurnChannel[];
	/** What GET /sources answers; mutable between loads. */
	sources: SourcesResponse;
	/** What GET /provider answers; PUT /provider and the credential routes update it. */
	provider: ProviderStatus;
	/** What GET /passages/{id} resolves, keyed by passage_id. */
	passages: Map<string, Passage>;
	/** While true, GET /sources fails at the transport — flip to let a retry recover. */
	failSources: boolean;
	/** The channel for the most recent turn. */
	lastChannel(): TurnChannel;
};

export type FakeEngineOptions = {
	sources?: SourcesResponse;
	provider?: ProviderStatus;
	passages?: Passage[];
	/** GET /sources fails at the transport — the engine-unreachable state (9.13). */
	failSources?: boolean;
};

const EMPTY_SOURCES: SourcesResponse = {
	sources: [],
	owned_undocumented: [],
	documented_unconfirmed: []
};

function json(body: unknown): Response {
	return new Response(JSON.stringify(body), {
		status: 200,
		headers: { 'content-type': 'application/json' }
	});
}

/**
 * Stub global fetch with the fake engine. Callers pair it with
 * `vi.unstubAllGlobals()` in afterEach.
 */
export function installFakeEngine(options: FakeEngineOptions = {}): FakeEngineServer {
	const server: FakeEngineServer = {
		requests: [],
		channels: [],
		sources: options.sources ?? EMPTY_SOURCES,
		provider: options.provider ?? { kind: null, masked: null },
		passages: new Map((options.passages ?? []).map((passage) => [passage.passage_id, passage])),
		failSources: options.failSources ?? false,
		lastChannel() {
			const channel = this.channels.at(-1);
			if (channel === undefined) throw new Error('no turn has been submitted');
			return channel;
		}
	};

	vi.stubGlobal('fetch', (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
		const url = new URL(
			typeof input === 'string' ? input : input instanceof URL ? input.href : input.url,
			'http://localhost'
		);
		const method = init?.method ?? 'GET';
		const path = url.pathname;

		if (method === 'POST' && path === '/turn') {
			server.requests.push(JSON.parse(String(init?.body)) as TurnRequest);
			const channel = sseChannel();
			server.channels.push(channel);
			init?.signal?.addEventListener('abort', () => channel.abort());
			return Promise.resolve(channel.response);
		}
		if (method === 'GET' && path === '/sources') {
			if (server.failSources) return Promise.reject(new TypeError('fetch failed'));
			return Promise.resolve(json(server.sources));
		}
		if (path === '/provider/credential') {
			if (method === 'PUT') {
				const { key } = JSON.parse(String(init?.body)) as { key: string };
				server.provider = { ...server.provider, masked: `…${key.slice(-4)}` };
				return Promise.resolve(json(server.provider));
			}
			if (method === 'DELETE') {
				server.provider = { ...server.provider, masked: null };
				return Promise.resolve(json(server.provider));
			}
		}
		if (path === '/provider/test' && method === 'POST') {
			return Promise.resolve(json({ reachable: true }));
		}
		if (path === '/provider') {
			if (method === 'PUT') {
				const body = JSON.parse(String(init?.body)) as { kind: string; model?: string };
				server.provider = { ...server.provider, kind: body.kind, model: body.model };
				return Promise.resolve(json(server.provider));
			}
			return Promise.resolve(json(server.provider));
		}
		if (method === 'GET' && path.startsWith('/passages/')) {
			const passage = server.passages.get(path.slice('/passages/'.length));
			if (passage === undefined) return Promise.resolve(new Response('{}', { status: 404 }));
			return Promise.resolve(json(passage));
		}
		return Promise.resolve(new Response('{}', { status: 404 }));
	});

	return server;
}
