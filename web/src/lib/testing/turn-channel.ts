// Test harness shared by the thread-store and ask-surface tests: a stubbed
// engine whose turn streams are controllable channels, wired to the abort
// signal the way a real fetch would be. No test needs a provider, a corpus,
// or a key (design "Testing Strategy").

import { vi } from 'vitest';
import type { TurnRequest } from '../engine/client';
import { TURN_STREAM_VERSION } from '../engine/records';
import { TURN_STREAM_HEADER } from '../engine/sse';

export type TurnChannel = {
	response: Response;
	emit(event: string, data: unknown): void;
	close(): void;
	abort(): void;
};

/** A controllable SSE response carrying the turn-stream version header. */
export function sseChannel(): TurnChannel {
	let controller!: ReadableStreamDefaultController<Uint8Array>;
	const stream = new ReadableStream<Uint8Array>({
		start(c) {
			controller = c;
		}
	});
	const response = new Response(stream, {
		headers: { [TURN_STREAM_HEADER]: TURN_STREAM_VERSION }
	});
	const encoder = new TextEncoder();
	return {
		response,
		emit(event, data) {
			controller.enqueue(encoder.encode(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`));
		},
		close() {
			controller.close();
		},
		abort() {
			controller.error(new DOMException('The operation was aborted.', 'AbortError'));
		}
	};
}

export type FakeEngine = {
	submit: ReturnType<typeof vi.fn> &
		((request: TurnRequest, signal?: AbortSignal) => Promise<Response>);
	requests: TurnRequest[];
	channels: TurnChannel[];
};

/** A stubbed submit-question: records every request, one channel per turn. */
export function fakeEngine(): FakeEngine {
	const requests: TurnRequest[] = [];
	const channels: TurnChannel[] = [];
	const submit = vi.fn((request: TurnRequest, signal?: AbortSignal) => {
		requests.push(request);
		const channel = sseChannel();
		channels.push(channel);
		signal?.addEventListener('abort', () => channel.abort());
		return Promise.resolve(channel.response);
	});
	return { submit, requests, channels };
}
