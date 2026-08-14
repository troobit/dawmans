// The engine client: the nine operations api/answer-engine 9.4 names, mapped
// to the routes its design fixes (design "The engine client"). Stateless typed
// wrappers returning parsed records — no state, no retries, no fetching from
// components. Every route is relative: the page shares the engine's origin
// (Decision 1), so no host and no port exist to hard-code.
//
// No retries anywhere: a retry the user did not ask for would either duplicate
// a turn or mask the provider-unreachable state 9.6 requires the user to see.

import type { Passage, RequiredDevice, SourceRecord, SourceRef } from './records';

/**
 * A non-envelope HTTP failure (ui 9.15): a 422 question-too-long or a 403
 * host/origin rejection describes a **request**, not a turn — it carries no
 * outcome and is not a member of CONTRACTS §6. `rejected` is the engine's
 * machine-readable name for what was rejected.
 */
export class EngineRejection extends Error {
	constructor(
		readonly status: number,
		readonly rejected: string,
		readonly body: unknown
	) {
		super(`engine rejected the request: ${rejected}`);
		this.name = 'EngineRejection';
	}
}

async function rejectionFrom(response: Response): Promise<EngineRejection> {
	let body: unknown = null;
	try {
		body = await response.json();
	} catch {
		// A non-JSON failure body carries nothing machine-readable.
	}
	const rejected =
		typeof body === 'object' && body !== null && typeof (body as { rejected?: unknown }).rejected === 'string'
			? (body as { rejected: string }).rejected
			: `http-${response.status}`;
	return new EngineRejection(response.status, rejected, body);
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
	const response = await fetch(path, init);
	if (!response.ok) throw await rejectionFrom(response);
	return (await response.json()) as T;
}

function jsonInit(method: string, body: unknown): RequestInit {
	return {
		method,
		headers: { 'content-type': 'application/json' },
		body: JSON.stringify(body)
	};
}

/** The submit-question body (api/answer-engine design): `conversation_id: null` starts a conversation. */
export type TurnRequest = {
	conversation_id: string | null;
	question: string;
	sources: string[];
};

/**
 * `GET /sources` (api 9.5–9.7): every record of both kinds, plus the two gap
 * reports of CONTRACTS §5. Both reports are lists that may be empty — empty is
 * a normal value, never elided (the owned-but-undocumented report is empty
 * today and a consumer that hardcodes that is a defect against §5).
 */
export type SourcesResponse = {
	sources: SourceRecord[];
	owned_undocumented: RequiredDevice[];
	documented_unconfirmed: SourceRef[];
};

/**
 * `GET /provider` (api 6.13, ui 10.7): the engine's reported status. A stored
 * key is represented only by `masked` — "…" plus its final four characters —
 * and by nothing else, anywhere, ever.
 */
export type ProviderStatus = {
	kind: string | null;
	model?: string;
	masked: string | null;
	requires_disclosure_ack?: boolean;
};

/** `POST /provider/test` (ui 10.10): reachability as configured; no synthesis, no credential echoed. */
export type ProviderTest = {
	reachable: boolean;
	detail?: string;
};

/**
 * submit-question: `POST /turn`. Returns the response **unread** — the
 * turn-stream version check and the frame reading are sse.ts's, and both
 * happen before any body byte is consumed. `signal` is how the user cancels
 * (1.9); disconnect-cancels is the one thing inherited from the transport.
 */
export async function submitQuestion(request: TurnRequest, signal?: AbortSignal): Promise<Response> {
	const response = await fetch('/turn', { ...jsonInit('POST', request), signal });
	if (!response.ok) throw await rejectionFrom(response);
	return response;
}

/** fetch-passage: `GET /passages/{passage_id}`. The id contains slashes (CONTRACTS §1); they are path structure. */
export function fetchPassage(passageId: string): Promise<Passage> {
	return requestJson<Passage>(`/passages/${passageId}`);
}

/** list-sources: `GET /sources`. */
export function listSources(): Promise<SourcesResponse> {
	return requestJson<SourcesResponse>('/sources');
}

/** get-provider-status: `GET /provider`. */
export function getProviderStatus(): Promise<ProviderStatus> {
	return requestJson<ProviderStatus>('/provider');
}

/** set-provider: `PUT /provider` — kind and model; applies from the next turn. */
export function setProvider(provider: { kind: string; model?: string }): Promise<ProviderStatus> {
	return requestJson<ProviderStatus>('/provider', jsonInit('PUT', provider));
}

/**
 * set-credential: `PUT /provider/credential`. The key travels only in this
 * body — never a query string, never a URL (10.9) — and comes back masked.
 */
export function setCredential(key: string): Promise<ProviderStatus> {
	return requestJson<ProviderStatus>('/provider/credential', jsonInit('PUT', { key }));
}

/** clear-credential: `DELETE /provider/credential` — effective on the next submission (10.8). */
export function clearCredential(): Promise<ProviderStatus> {
	return requestJson<ProviderStatus>('/provider/credential', { method: 'DELETE' });
}

/** test-provider: `POST /provider/test`. */
export function testProvider(): Promise<ProviderTest> {
	return requestJson<ProviderTest>('/provider/test', { method: 'POST' });
}

/**
 * serve-document: the href for a vendor-manual citation's open-at-source
 * action (5.5, CONTRACTS §3a). The route plus the fragment `#page=N` and
 * **nothing else**: one built-in viewer matches only a fragment that starts
 * `page=` and truncates at the first `&`, so appending a zoom, view or text
 * directive silently disables the jump there. Opening it is a plain link
 * activation — the browser fetches the PDF itself; no operation here.
 */
export function serveDocumentHref(sourceId: string, page: number): string {
	return `/sources/${sourceId}/document#page=${page}`;
}
