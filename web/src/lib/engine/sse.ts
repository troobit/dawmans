// The SSE frame reader over a ReadableStream (design "SSE framing and the
// turn reducer"; requirements 4.1, 9.14, 9.19). Streaming is `fetch` +
// ReadableStream, not EventSource — EventSource cannot POST the question and
// scope. Nothing of EventSource's processing model is inherited: there is no
// reconnection, no resumption, no retry field and no last-event-id; a stream
// that breaks is over, and recovery is the user re-asking (CONTRACTS §4b).

import { TURN_STREAM_VERSION } from './records';

/**
 * The response header carrying the turn-stream version token. CONTRACTS §4b
 * and api/answer-engine 9.15 fix the token (`dawmans/turn-stream/1`) but not
 * the header's name; this constant is where the two sides must agree.
 */
export const TURN_STREAM_HEADER = 'dawmans-turn-stream';

/** One dispatched SSE frame. `data` is the raw string; the reducer parses it. */
export type SseFrame = { event: string; data: string };

/** What the stream's end said: `complete` is whether an explicit `done` event was dispatched. */
export type StreamEnd = { complete: boolean };

/**
 * 9.19: the engine declared a turn-stream version this surface does not know.
 * No turn is being described — the broken state names both versions and
 * carries no outcome.
 */
export class UnknownStreamVersionError extends Error {
	constructor(
		readonly declared: string | null,
		readonly known: string
	) {
		super(
			declared === null
				? `the engine declared no turn-stream version; this surface knows ${known}`
				: `the engine declared turn-stream version ${declared}; this surface knows ${known}`
		);
		this.name = 'UnknownStreamVersionError';
	}
}

/**
 * Yield `{event, data}` per dispatched frame. UTF-8 is decoded incrementally
 * (`TextDecoder` with `{stream: true}`): a multi-byte character split across
 * two network chunks would otherwise paint as U+FFFD — indistinguishable from
 * a `degraded` passage (Decision 2). Frames split on blank lines; an event
 * with no data line is never dispatched, so a bare `done` may legally vanish
 * (CONTRACTS §4b); a frame truncated mid-event is discarded silently.
 */
export async function* readFrames(stream: ReadableStream<Uint8Array>): AsyncGenerator<SseFrame, void> {
	const decoder = new TextDecoder();
	const reader = stream.getReader();
	let buffered = '';
	try {
		for (;;) {
			const { done, value } = await reader.read();
			if (done) return;
			buffered += decoder.decode(value, { stream: true });
			for (;;) {
				const boundary = buffered.search(/\n\n|\r\n\r\n/);
				if (boundary === -1) break;
				const raw = buffered.slice(0, boundary);
				buffered = buffered.slice(boundary + (buffered[boundary] === '\r' ? 4 : 2));
				const frame = parseFrame(raw);
				if (frame !== null) yield frame;
			}
		}
	} finally {
		reader.releaseLock();
	}
}

function parseFrame(raw: string): SseFrame | null {
	let event = 'message';
	const data: string[] = [];
	for (const line of raw.split(/\r?\n/)) {
		if (line.startsWith('event:')) event = line.slice(6).replace(/^ /, '');
		else if (line.startsWith('data:')) data.push(line.slice(5).replace(/^ /, ''));
		// Comments (`:`) and every other field — id, retry — are ignored: they
		// belong to EventSource's reconnection machinery, which does not exist here.
	}
	if (data.length === 0) return null;
	return { event, data: data.join('\n') };
}

/**
 * The turn's event stream: checks the version header **before the body is
 * read** — an unknown version refuses the whole turn by name rather than
 * half-rendering it (9.19) — then yields frames until `done`, which is last
 * and occurs exactly once. Returns whether `done` was dispatched: end of
 * stream without it is a defined failure the reducer renders as `incomplete`,
 * never a settled turn (9.14).
 */
export async function* turnEvents(response: Response): AsyncGenerator<SseFrame, StreamEnd> {
	const declared = response.headers.get(TURN_STREAM_HEADER);
	if (declared !== TURN_STREAM_VERSION) {
		throw new UnknownStreamVersionError(declared, TURN_STREAM_VERSION);
	}
	if (response.body === null) return { complete: false };
	for await (const frame of readFrames(response.body)) {
		yield frame;
		if (frame.event === 'done') return { complete: true };
	}
	return { complete: false };
}
