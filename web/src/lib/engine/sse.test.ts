// Tests for the SSE frame reader (requirements 4.1, 9.14, 9.19; design "SSE
// framing and the turn reducer"; Decision 2). Frames split across chunk
// boundaries reassemble; a multi-byte character split across two network
// chunks never paints as U+FFFD; the dawmans/turn-stream/* header is checked
// before the body is read; end-of-stream without `done` reports incomplete.

import { describe, expect, it } from 'vitest';
import { TURN_STREAM_VERSION } from './records';
import {
	TURN_STREAM_HEADER,
	UnknownStreamVersionError,
	readFrames,
	turnEvents,
	type SseFrame
} from './sse';

const encoder = new TextEncoder();

/** A byte stream delivering exactly the given chunks, in order. */
function chunkStream(chunks: (string | Uint8Array)[]): ReadableStream<Uint8Array> {
	return new ReadableStream<Uint8Array>({
		start(controller) {
			for (const chunk of chunks) {
				controller.enqueue(typeof chunk === 'string' ? encoder.encode(chunk) : chunk);
			}
			controller.close();
		}
	});
}

function turnResponse(chunks: (string | Uint8Array)[], version = TURN_STREAM_VERSION): Response {
	return new Response(chunkStream(chunks), {
		status: 200,
		headers: { 'content-type': 'text/event-stream', [TURN_STREAM_HEADER]: version }
	});
}

/** Drain an async generator, returning both what it yielded and what it returned. */
async function drain<T, R>(generator: AsyncGenerator<T, R>): Promise<{ yielded: T[]; returned: R }> {
	const yielded: T[] = [];
	for (;;) {
		const next = await generator.next();
		if (next.done) return { yielded, returned: next.value };
		yielded.push(next.value);
	}
}

describe('frame parsing', () => {
	it('yields one {event, data} per frame', async () => {
		const { yielded } = await drain(
			readFrames(chunkStream(['event: outcome\ndata: {"outcome":"answered"}\n\nevent: done\ndata: {"complete":true}\n\n']))
		);
		expect(yielded).toEqual([
			{ event: 'outcome', data: '{"outcome":"answered"}' },
			{ event: 'done', data: '{"complete":true}' }
		]);
	});

	it('reassembles a frame split across chunk boundaries — including mid-field', async () => {
		const { yielded } = await drain(
			readFrames(
				chunkStream(['event: body', '_delta\nda', 'ta: {"text":"Turn the ', 'Track Activator on"}\n', '\n'])
			)
		);
		expect(yielded).toEqual([{ event: 'body_delta', data: '{"text":"Turn the Track Activator on"}' }]);
	});

	it('never yields U+FFFD for a multi-byte character split across two chunks', async () => {
		// "…" is three UTF-8 bytes; split it between network chunks. Decoded
		// naively per chunk it would paint as U+FFFD — indistinguishable from a
		// degraded passage (Decision 2).
		const bytes = encoder.encode('event: body_delta\ndata: {"text":"wait…done"}\n\n');
		const splitAt = bytes.indexOf(0xe2) + 1; // inside the "…" sequence
		const { yielded } = await drain(
			readFrames(chunkStream([bytes.slice(0, splitAt), bytes.slice(splitAt)]))
		);
		expect(yielded[0].data).toContain('wait…done');
		expect(yielded[0].data).not.toContain('�');
	});

	it('joins multiple data lines with a newline', async () => {
		const { yielded } = await drain(
			readFrames(chunkStream(['event: body_delta\ndata: line one\ndata: line two\n\n']))
		);
		expect(yielded).toEqual([{ event: 'body_delta', data: 'line one\nline two' }]);
	});

	it('never dispatches an event with no data line — a bare done may legally vanish', async () => {
		const { yielded } = await drain(
			readFrames(chunkStream(['event: done\n\nevent: outcome\ndata: {"outcome":"answered"}\n\n']))
		);
		expect(yielded).toEqual([{ event: 'outcome', data: '{"outcome":"answered"}' }]);
	});

	it('discards a frame truncated mid-event silently', async () => {
		// A stream that ends inside a frame discards the pending event without
		// error (CONTRACTS §4b) — detecting the loss is the done-tracking below.
		const { yielded } = await drain(
			readFrames(chunkStream(['event: outcome\ndata: {"outcome":"answered"}\n\nevent: body_delta\ndata: {"text":"half']))
		);
		expect(yielded).toEqual([{ event: 'outcome', data: '{"outcome":"answered"}' }]);
	});

	it('tolerates CRLF line endings and comment lines', async () => {
		const { yielded } = await drain(
			readFrames(chunkStream([': keep-alive\r\n\r\nevent: outcome\r\ndata: {"outcome":"answered"}\r\n\r\n']))
		);
		expect(yielded).toEqual([{ event: 'outcome', data: '{"outcome":"answered"}' }]);
	});
});

describe('turnEvents', () => {
	it('checks the turn-stream header before reading the body', async () => {
		const response = turnResponse(
			['event: outcome\ndata: {"outcome":"answered"}\n\n'],
			'dawmans/turn-stream/2'
		);
		const failure = await drain(turnEvents(response)).then(
			() => null,
			(thrown: unknown) => thrown
		);
		expect(failure).toBeInstanceOf(UnknownStreamVersionError);
		// The refusal happened before any body byte was consumed.
		expect(response.bodyUsed).toBe(false);
	});

	it('an unknown version refuses the turn naming both versions', async () => {
		const failure = await drain(turnEvents(turnResponse([], 'dawmans/turn-stream/9'))).then(
			() => null,
			(thrown: unknown) => thrown
		);
		const refusal = failure as UnknownStreamVersionError;
		expect(refusal.declared).toBe('dawmans/turn-stream/9');
		expect(refusal.known).toBe(TURN_STREAM_VERSION);
		expect(refusal.message).toContain('dawmans/turn-stream/9');
		expect(refusal.message).toContain(TURN_STREAM_VERSION);
	});

	it('a missing version header refuses the turn the same way', async () => {
		const response = new Response(chunkStream([]), { status: 200 });
		const failure = await drain(turnEvents(response)).then(
			() => null,
			(thrown: unknown) => thrown
		);
		expect(failure).toBeInstanceOf(UnknownStreamVersionError);
		expect((failure as UnknownStreamVersionError).declared).toBeNull();
	});

	it('an unknown event name is yielded through and never fails the turn', async () => {
		// The ignore itself is the reducer's (CONTRACTS §4b rule 1); the reader's
		// obligation is that an unknown name neither throws nor ends the stream.
		const { yielded, returned } = await drain(
			turnEvents(
				turnResponse([
					'event: outcome\ndata: {"outcome":"answered"}\n\n',
					'event: sparkline\ndata: {"novel":true}\n\n',
					'event: done\ndata: {"complete":true}\n\n'
				])
			)
		);
		expect(yielded.map((frame: SseFrame) => frame.event)).toEqual(['outcome', 'sparkline', 'done']);
		expect(returned.complete).toBe(true);
	});

	it('end-of-stream without done reports complete: false — never a settled turn', async () => {
		const { returned } = await drain(
			turnEvents(turnResponse(['event: outcome\ndata: {"outcome":"answered"}\n\n']))
		);
		expect(returned.complete).toBe(false);
	});

	it('stops at done: done is last and occurs exactly once', async () => {
		const { yielded, returned } = await drain(
			turnEvents(
				turnResponse([
					'event: done\ndata: {"complete":true}\n\nevent: body_delta\ndata: {"text":"late"}\n\n'
				])
			)
		);
		expect(yielded.map((frame: SseFrame) => frame.event)).toEqual(['done']);
		expect(returned.complete).toBe(true);
	});
});
