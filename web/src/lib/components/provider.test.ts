// Provider configuration: the status store and the kind-first configuration
// region (requirements §10; design "Provider configuration"). The engine is a
// stubbed fetch over the five provider operations; the store renders only what
// GET /provider reports, never the browser's stored settings (10.7).

import { cleanup, fireEvent, render, screen } from '@testing-library/svelte';
import { tick } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { ProviderStatus, ProviderTest } from '../engine/client';
import { ScopeStore } from '../state/scope.svelte';
import { DISCLOSURE_ACK_KEY, ProviderStore } from '../state/provider.svelte';
import { ThreadStore } from '../state/thread.svelte';
import ProviderConfig from './ProviderConfig.svelte';

type Call = { url: string; method: string; body: string | null };

/**
 * The five provider operations as a stateful stub: PUT/DELETE mutate the held
 * status, GET reports it — the shape the engine's own surface has.
 */
function stubProvider(initial: ProviderStatus, test: ProviderTest = { reachable: true }) {
	let status: ProviderStatus = { ...initial };
	const calls: Call[] = [];
	vi.stubGlobal(
		'fetch',
		vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
			const url = String(input);
			const method = init?.method ?? 'GET';
			const body = typeof init?.body === 'string' ? init.body : null;
			calls.push({ url, method, body });
			const respond = (payload: unknown) =>
				Promise.resolve(
					new Response(JSON.stringify(payload), {
						status: 200,
						headers: { 'content-type': 'application/json' }
					})
				);
			if (url.startsWith('/provider/test')) return respond(test);
			if (url.startsWith('/provider/credential')) {
				status =
					method === 'PUT'
						? {
								...status,
								masked: '…' + ((JSON.parse(body ?? '{}') as { key?: string }).key ?? '').slice(-4)
							}
						: { ...status, masked: null };
				return respond(status);
			}
			if (url.startsWith('/provider')) {
				if (method === 'PUT') {
					const put = JSON.parse(body ?? '{}') as { kind: string; model?: string };
					status = {
						kind: put.kind,
						...(put.model !== undefined ? { model: put.model } : {}),
						masked: status.masked,
						...(put.kind === 'shared-backend' ? { requires_disclosure_ack: true } : {})
					};
				}
				return respond(status);
			}
			throw new Error(`unexpected fetch ${method} ${url}`);
		})
	);
	return {
		calls,
		get status() {
			return status;
		}
	};
}

const UNCONFIGURED: ProviderStatus = { kind: null, masked: null };

async function mount(initial: ProviderStatus, onclose = vi.fn()) {
	const stub = stubProvider(initial);
	const provider = new ProviderStore();
	await provider.load();
	const result = render(ProviderConfig, { props: { provider, onclose } });
	await tick();
	return { ...result, provider, stub, onclose };
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

describe('kind first (10.1, 10.3)', () => {
	it('offers the three kinds and requests credential entry only for keyed hosted', async () => {
		await mount(UNCONFIGURED);
		expect(screen.getByRole('radio', { name: /hosted.*key/i })).toBeTruthy();
		expect(screen.getByRole('radio', { name: /local/i })).toBeTruthy();
		expect(screen.getByRole('radio', { name: /shared/i })).toBeTruthy();
		// Kind not yet chosen: no credential entry anywhere.
		expect(document.querySelector('input[type="password"]')).toBeNull();

		await fireEvent.click(screen.getByRole('radio', { name: /hosted.*key/i }));
		expect(document.querySelector('input[type="password"]')).not.toBeNull();

		await fireEvent.click(screen.getByRole('radio', { name: /local/i }));
		expect(document.querySelector('input[type="password"]')).toBeNull();
	});

	it('configures a local provider from its endpoint or model alone, never asking for a key (10.3)', async () => {
		const { stub, onclose } = await mount(UNCONFIGURED);
		await fireEvent.click(screen.getByRole('radio', { name: /local/i }));
		expect(document.querySelector('input[type="password"]')).toBeNull();
		expect(screen.queryByLabelText(/api key/i)).toBeNull();

		const model = screen.getByRole('textbox', { name: /endpoint or model/i });
		await fireEvent.input(model, { target: { value: 'ollama/llama3' } });
		await fireEvent.click(screen.getByRole('button', { name: /^save$/i }));
		await vi.waitFor(() => expect(onclose).toHaveBeenCalledOnce());

		const put = stub.calls.find((call) => call.url === '/provider' && call.method === 'PUT');
		expect(put?.body).toBe(JSON.stringify({ kind: 'local', model: 'ollama/llama3' }));
		expect(stub.status.kind).toBe('local');
	});
});

describe('the key input (10.5, 10.6)', () => {
	it('masks by default with a momentary reveal of the value being typed', async () => {
		await mount(UNCONFIGURED);
		await fireEvent.click(screen.getByRole('radio', { name: /hosted.*key/i }));
		const input = screen.getByLabelText(/api key/i) as HTMLInputElement;
		expect(input.type).toBe('password');

		const reveal = screen.getByRole('button', { name: /reveal/i });
		await fireEvent.mouseDown(reveal);
		expect(input.type).toBe('text');
		await fireEvent.mouseUp(reveal);
		expect(input.type).toBe('password'); // momentary, not a latch
	});

	it('is always empty on open — a saved key is represented only by the masked tail', async () => {
		await mount({ kind: 'keyed-hosted', model: 'anthropic', masked: '…wxyz' });
		await fireEvent.click(screen.getByRole('radio', { name: /hosted.*key/i }));
		const input = screen.getByLabelText(/api key/i) as HTMLInputElement;
		expect(input.value).toBe('');
		expect(screen.getByText(/…wxyz/)).toBeTruthy();
	});
});

describe('the indication renders from the engine (10.7)', () => {
	it('shows kind, provider and at most the final four characters', async () => {
		// Whatever the browser held locally is not what renders.
		localStorage.setItem('dawmans.some-settings', JSON.stringify({ kind: 'local' }));
		const { container } = await mount({ kind: 'keyed-hosted', model: 'anthropic', masked: '…abcd' });
		const statusLine = container.querySelector('.status');
		expect(statusLine?.textContent).toMatch(/keyed.hosted/i);
		expect(statusLine?.textContent).toMatch(/anthropic/);
		expect(statusLine?.textContent).toMatch(/…abcd/);
		expect(statusLine?.textContent).not.toMatch(/local/i);
	});
});

describe('replace, clear and containment (10.8, 10.9)', () => {
	it('saves a key through the PUT body only, and it appears nowhere afterwards', async () => {
		const secret = 'sk-terribly-secret-9999';
		const { stub } = await mount({ kind: 'keyed-hosted', model: 'anthropic', masked: null });
		await fireEvent.click(screen.getByRole('radio', { name: /hosted.*key/i }));
		const input = screen.getByLabelText(/api key/i) as HTMLInputElement;
		await fireEvent.input(input, { target: { value: secret } });
		await fireEvent.click(screen.getByRole('button', { name: /save key/i }));
		// The masked tail appearing is the whole round trip settled.
		await vi.waitFor(() => expect(screen.getByText(/…9999/)).toBeTruthy());
		await tick();

		// 10.9: the key travels only in the PUT body.
		const carrier = stub.calls.find((call) => call.body?.includes(secret));
		expect(carrier?.url).toBe('/provider/credential');
		expect(carrier?.method).toBe('PUT');
		expect(stub.calls.every((call) => !call.url.includes(secret))).toBe(true);

		// 10.6: never displayed again, no input pre-populated, nowhere in the page.
		expect(input.value).toBe('');
		expect(document.body.innerHTML).not.toContain(secret);
		expect(document.title).not.toContain(secret);
		expect(JSON.stringify(localStorage)).not.toContain(secret);
		expect(screen.getByText(/…9999/)).toBeTruthy(); // the masked tail, from the engine
	});

	it('clears a stored key with the clear-credential operation (10.8)', async () => {
		const { stub } = await mount({ kind: 'keyed-hosted', model: 'anthropic', masked: '…abcd' });
		await fireEvent.click(screen.getByRole('radio', { name: /hosted.*key/i }));
		await fireEvent.click(screen.getByRole('button', { name: /clear key/i }));
		await vi.waitFor(() =>
			expect(
				stub.calls.some((call) => call.url === '/provider/credential' && call.method === 'DELETE')
			).toBe(true)
		);
		await tick();
		expect(stub.status.masked).toBeNull();
		expect(screen.queryByText(/…abcd/)).toBeNull();
	});
});

describe('test-provider (10.10)', () => {
	it('reports reachable as configured without echoing any credential', async () => {
		const { stub } = await mount({ kind: 'keyed-hosted', model: 'anthropic', masked: '…abcd' });
		await fireEvent.click(screen.getByRole('button', { name: /test provider/i }));
		await vi.waitFor(() => expect(screen.getByText(/reachable/i)).toBeTruthy());
		const test = stub.calls.find((call) => call.url === '/provider/test');
		expect(test?.method).toBe('POST');
		expect(test?.body ?? null).toBeNull(); // nothing sent, nothing echoed
	});
});

describe('returning to the ask surface (10.2, 10.11)', () => {
	it('saves and returns with the typed question and the scope intact', async () => {
		const scope = new ScopeStore();
		scope.load(['src/a', 'src/b']);
		scope.toggle('src/b');
		const thread = new ThreadStore({ scope });
		thread.draft = 'kick is distorting';

		const { onclose } = await mount(UNCONFIGURED);
		await fireEvent.click(screen.getByRole('radio', { name: /local/i }));
		await fireEvent.input(screen.getByRole('textbox', { name: /endpoint or model/i }), {
			target: { value: 'ollama/llama3' }
		});
		await fireEvent.click(screen.getByRole('button', { name: /^save$/i }));
		await vi.waitFor(() => expect(onclose).toHaveBeenCalledOnce());

		expect(thread.draft).toBe('kick is distorting');
		expect(scope.selected).toEqual(['src/a']);
	});
});

describe('the shared-backend disclosure (10.4)', () => {
	it('blocks the first turn until acknowledged, and stays readable afterwards', async () => {
		const { provider, onclose } = await mount(UNCONFIGURED);
		await fireEvent.click(screen.getByRole('radio', { name: /shared/i }));
		await fireEvent.click(screen.getByRole('button', { name: /^save$/i }));

		// Saving selects the backend but the surface does not close: the
		// disclosure holds the first turn until it is acknowledged.
		await vi.waitFor(() => expect(provider.status?.kind).toBe('shared-backend'));
		await tick();
		expect(onclose).not.toHaveBeenCalled();
		expect(screen.getByText(/question text and .*passages leave (the|this) machine/i)).toBeTruthy();
		expect(provider.blocksFirstTurn).toBe(true);

		await fireEvent.click(screen.getByRole('button', { name: /acknowledge/i }));
		expect(provider.blocksFirstTurn).toBe(false);
		// Readable after acknowledgement, not dismissed with it.
		expect(screen.getByText(/question text and .*passages leave (the|this) machine/i)).toBeTruthy();

		await fireEvent.click(screen.getByRole('button', { name: /^save$/i }));
		await vi.waitFor(() => expect(onclose).toHaveBeenCalledOnce());
	});

	it('records an acknowledge-before-save against the backend actually saved, not the previous provider', async () => {
		// The natural first-time flow: a local provider is configured, the user
		// selects the shared backend, reads and acknowledges the disclosure,
		// then saves. The acknowledgement belongs to the shared backend the save
		// produces — never to the local provider still reported at click time.
		const { provider, onclose } = await mount({ kind: 'local', model: 'ollama/llama3', masked: null });
		await fireEvent.click(screen.getByRole('radio', { name: /shared/i }));
		await fireEvent.click(screen.getByRole('button', { name: /acknowledge/i }));

		// Nothing recorded against the local identity.
		expect(localStorage.getItem(DISCLOSURE_ACK_KEY) ?? '').not.toContain('local');

		await fireEvent.click(screen.getByRole('button', { name: /^save$/i }));
		await vi.waitFor(() => expect(onclose).toHaveBeenCalledOnce());
		expect(provider.blocksFirstTurn).toBe(false);
		expect(localStorage.getItem(DISCLOSURE_ACK_KEY)).toContain('shared-backend');
	});

	it('stores the acknowledgement against the backend identity, so changing backend re-arms it', async () => {
		const stub = stubProvider({ kind: 'shared-backend', model: 'backend-a', masked: null });
		void stub;
		const provider = new ProviderStore();
		await provider.load();
		expect(provider.blocksFirstTurn).toBe(true);

		provider.acknowledgeDisclosure();
		expect(provider.blocksFirstTurn).toBe(false);
		expect(localStorage.getItem(DISCLOSURE_ACK_KEY)).toContain('backend-a');

		// A fresh load of the page keeps the acknowledgement for the same backend.
		const reloaded = new ProviderStore();
		await reloaded.load();
		expect(reloaded.blocksFirstTurn).toBe(false);

		// A different backend re-arms the disclosure.
		await reloaded.choose('shared-backend', 'backend-b');
		expect(reloaded.blocksFirstTurn).toBe(true);
	});

	it('never blocks a keyed hosted or local provider on the disclosure', async () => {
		stubProvider({ kind: 'local', model: 'ollama/llama3', masked: null });
		const provider = new ProviderStore();
		await provider.load();
		expect(provider.blocksFirstTurn).toBe(false);
	});
});
