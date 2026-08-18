// Tests for the turn reducer and outcome totality (requirements 3.11, 4.3,
// 4.6, 5.12, 5.13, 6.6, 9.4; design "SSE framing and the turn reducer").
//
// One rendering path per CONTRACTS §4b event — the consumer-side test §4b
// itself mandates, since nothing on the wire detects a client that quietly
// stops rendering `scope_dropped`. A governed event with no path fails here,
// not in review.

import { describe, expect, it } from 'vitest';
import type { Cause, Citation, Outcome, TurnEvent } from './records';
import type { SseFrame, StreamEnd } from './sse';
import { RENDERER_FOR_OUTCOME, Turn, rendererFor } from './turn.svelte';

function frame(event: string, data: unknown): SseFrame {
	return { event, data: JSON.stringify(data) };
}

function makeTurn(): Turn {
	return new Turn('why is the track silent', ['ableton/live-12', 'authored/triage']);
}

const CITATION: Citation = {
	kind: 'vendor-manual',
	source_id: 'ableton/live-12',
	display_name: 'Ableton Live 12',
	passage_id: 'ableton/live-12/abc',
	section_number: '15.2',
	section_title: 'Track Activator',
	hardware_applicability: { status: 'confirmed' },
	degraded: false,
	has_figures: false,
	doc_version: '12',
	page: 497
};

const CAUSE: Cause = {
	rank: 1,
	statement: 'The Track Activator is off',
	check: 'Look at the Track Activator on the silent track',
	cites: ['authored/triage/t1'],
	fix_cites: ['ableton/live-12/abc']
};

async function* streamOf(frames: SseFrame[], end: StreamEnd): AsyncGenerator<SseFrame, StreamEnd> {
	for (const item of frames) yield item;
	return end;
}

describe('one rendering path per CONTRACTS §4b event', () => {
	// Typed over the governed set: an event added to records.ts without a row
	// here fails the type check, and a row with no observable effect fails the
	// assertion — the consumer-side coverage §4b mandates.
	const coverage: {
		[E in TurnEvent as E['event']]: { data: E['data']; observed: (turn: Turn) => boolean };
	} = {
		scope_dropped: {
			data: [{ source_id: 'gone/source', display_name: 'A removed manual' }],
			observed: (turn) => turn.envelope.scope_dropped?.[0].source_id === 'gone/source'
		},
		outcome: {
			data: { outcome: 'answered' },
			observed: (turn) => turn.envelope.outcome === 'answered' && turn.renderer === 'answer'
		},
		direct_answer: {
			data: { text: 'Turn the Track Activator back on.' },
			observed: (turn) => turn.envelope.direct_answer === 'Turn the Track Activator back on.'
		},
		body_delta: {
			data: { text: 'The activator mutes the track.' },
			observed: (turn) => turn.blocks.length > 0
		},
		citation: {
			data: CITATION,
			observed: (turn) => turn.citations.get(CITATION.passage_id) !== undefined
		},
		cause: {
			data: CAUSE,
			observed: (turn) => turn.envelope.causes?.[0].statement === CAUSE.statement
		},
		contributing_sources: {
			data: { sources: ['ableton/live-12'] },
			observed: (turn) => turn.envelope.contributing_sources?.[0] === 'ableton/live-12'
		},
		uncovered_parts: {
			data: { parts: ['the return track'] },
			observed: (turn) => turn.envelope.uncovered_parts?.[0] === 'the return track'
		},
		suggested_sources: {
			data: [{ source_id: 'akai/apc-key-25', display_name: 'APC Key 25 guide' }],
			observed: (turn) => turn.envelope.suggested_sources?.[0].source_id === 'akai/apc-key-25'
		},
		narrowing: {
			data: { question: 'Which track?', candidates: [
					{ label: 'An audio track', value: 'audio' },
					{ label: 'A MIDI track', value: 'MIDI' }
				] },
			observed: (turn) => turn.envelope.narrowing?.candidates.length === 2
		},
		required_device: {
			data: { device: 'focusrite/scarlett-solo', display_name: 'Scarlett Solo' },
			observed: (turn) => turn.envelope.required_device?.device === 'focusrite/scarlett-solo'
		},
		required_manual: {
			data: { filename: 'focusrite_scarlett-solo_<doctype>_v<version>_<lang>.pdf', placeholders: ['doctype', 'version', 'lang'] },
			observed: (turn) => turn.envelope.required_manual?.placeholders.length === 3
		},
		ungrounded: {
			data: { ungrounded: true },
			observed: (turn) => turn.envelope.ungrounded === true
		},
		framing: {
			data: { framing: 'unparsed' },
			observed: (turn) => turn.envelope.framing === 'unparsed'
		},
		timings: {
			data: {
				retrieval_ms: 40,
				state_acquisition_ms: 80,
				engine_overhead_ms: 120,
				first_token_ms: 900,
				completion_ms: 4000
			},
			observed: (turn) => turn.envelope.timings?.retrieval_ms === 40
		},
		done: {
			data: { complete: true },
			observed: (turn) => turn.state === 'settled'
		}
	};

	it.each(Object.entries(coverage))('%s discharges into the turn', (event, row) => {
		const turn = makeTurn();
		turn.applyEvent(frame(event, row.data));
		expect(row.observed(turn)).toBe(true);
	});
});

describe('outcome totality (9.4)', () => {
	it('maps all 17 members of the CONTRACTS §6 union to a renderer', () => {
		// RENDERER_FOR_OUTCOME is Record<Outcome, …>, so an 18th member fails
		// the type check; this pins the count and that no member is broken.
		expect(Object.keys(RENDERER_FOR_OUTCOME)).toHaveLength(17);
		for (const outcome of Object.keys(RENDERER_FOR_OUTCOME) as Outcome[]) {
			expect(rendererFor(outcome)).not.toBe('broken');
		}
	});

	it('renders an outcome outside the union as a broken state carrying detail', () => {
		const turn = makeTurn();
		turn.applyEvent(
			frame('outcome', { outcome: 'transcended', detail: 'engine 2.0 emitted a novel outcome' })
		);
		expect(turn.renderer).toBe('broken');
		expect(turn.envelope.detail).toBe('engine 2.0 emitted a novel outcome');
		// Deliberately the opposite of the unknown event, which is ignored.
	});

	it('ignores an unknown event name and never fails the turn (9.19)', () => {
		const turn = makeTurn();
		turn.applyEvent(frame('sparkline', { novel: true }));
		expect(turn.renderer).toBeNull();
		turn.applyEvent(frame('outcome', { outcome: 'answered' }));
		turn.applyEvent(frame('done', { complete: true }));
		expect(turn.state).toBe('settled');
		expect(turn.renderer).toBe('answer');
	});
});

describe('ordering honoured', () => {
	it('outcome fixes the renderer before the first word paints', () => {
		const turn = makeTurn();
		turn.applyEvent(frame('outcome', { outcome: 'needs-narrowing' }));
		expect(turn.renderer).toBe('narrowing');
		expect(turn.blocks).toHaveLength(0);
	});

	it('carries reason, retry_after and detail with the outcome, painting the error state once', () => {
		const turn = makeTurn();
		turn.applyEvent(
			frame('outcome', {
				outcome: 'provider-rate-limited',
				retry_after: 12.5,
				detail: 'HTTP 429 from the provider'
			})
		);
		expect(turn.envelope.outcome).toBe('provider-rate-limited');
		expect(turn.envelope.retry_after).toBe(12.5);
		expect(turn.envelope.detail).toBe('HTTP 429 from the provider');
		expect(turn.renderer).toBe('error');
	});

	it('direct_answer precedes body and renders first (4.3)', () => {
		const turn = makeTurn();
		turn.applyEvent(frame('outcome', { outcome: 'answered' }));
		turn.applyEvent(frame('direct_answer', { text: 'Turn the Track Activator back on.' }));
		expect(turn.envelope.direct_answer).toBe('Turn the Track Activator back on.');
		expect(turn.blocks).toHaveLength(0);
		turn.applyEvent(frame('body_delta', { text: 'The activator mutes output.' }));
		expect(turn.blocks).toHaveLength(1);
	});

	it('the first event of any kind moves acknowledged to streaming (8.2)', () => {
		const turn = makeTurn();
		expect(turn.state).toBe('acknowledged');
		turn.applyEvent(frame('scope_dropped', []));
		expect(turn.state).toBe('streaming');
	});

	it('done settles the turn (4.6)', () => {
		const turn = makeTurn();
		turn.applyEvent(frame('outcome', { outcome: 'answered' }));
		turn.applyEvent(frame('done', { complete: true }));
		expect(turn.state).toBe('settled');
		expect(turn.incomplete).toBe(false);
	});

	it('causes arrive in rank order: rank equals array position (6.6)', () => {
		const turn = makeTurn();
		turn.applyEvent(frame('outcome', { outcome: 'ranked-causes' }));
		turn.applyEvent(frame('cause', CAUSE));
		turn.applyEvent(frame('cause', { ...CAUSE, rank: 2, statement: 'The input is muted' }));
		const causes = turn.envelope.causes ?? [];
		expect(causes).toHaveLength(2);
		causes.forEach((cause, position) => expect(cause.rank).toBe(position + 1));
	});
});

describe("scope_dropped is the engine's prune, never the user's own narrowing (3.11)", () => {
	it('fills scope_dropped[] for the turn and leaves the asked scope untouched', () => {
		const turn = makeTurn();
		turn.applyEvent(frame('scope_dropped', [{ source_id: 'gone/source', display_name: 'Gone' }]));
		expect(turn.envelope.scope_dropped).toEqual([{ source_id: 'gone/source', display_name: 'Gone' }]);
		// The prune is reported with the turn; the scope the user asked with is
		// not rewritten to look like their own choice.
		expect(turn.scopeAtAsk).toEqual(['ableton/live-12', 'authored/triage']);
	});
});

describe('marks on rendered text', () => {
	it('ungrounded marks text already on screen without blanking it (5.13)', () => {
		const turn = makeTurn();
		turn.applyEvent(frame('outcome', { outcome: 'answered' }));
		turn.applyEvent(frame('body_delta', { text: 'Set the monitor to Auto.' }));
		const painted = turn.blocks;
		turn.applyEvent(frame('ungrounded', { ungrounded: true }));
		expect(turn.envelope.ungrounded).toBe(true);
		expect(turn.blocks).toEqual(painted);
	});

	it('a settled turn with no citations is uncited (5.12)', () => {
		const turn = makeTurn();
		turn.applyEvent(frame('outcome', { outcome: 'answered' }));
		turn.applyEvent(frame('done', { complete: true }));
		expect(turn.uncited).toBe(true);
	});

	it('a settled turn with citations is not uncited', () => {
		const turn = makeTurn();
		turn.applyEvent(frame('outcome', { outcome: 'answered' }));
		turn.applyEvent(frame('citation', CITATION));
		turn.applyEvent(frame('done', { complete: true }));
		expect(turn.uncited).toBe(false);
	});

	it('is not uncited before it settles — absence of citations is not yet a claim', () => {
		const turn = makeTurn();
		turn.applyEvent(frame('outcome', { outcome: 'answered' }));
		expect(turn.uncited).toBe(false);
	});
});

describe('citation map and marker order', () => {
	it('keys citations by passage_id and numbers markers at first appearance', () => {
		const turn = makeTurn();
		turn.applyEvent(frame('outcome', { outcome: 'answered' }));
		turn.applyEvent(
			frame('body_delta', { text: 'see [[p:ableton/live-12/abc]] and [[p:authored/triage/t1]]' })
		);
		expect(turn.markers).toEqual(['ableton/live-12/abc', 'authored/triage/t1']);
		expect(turn.markerIndex('ableton/live-12/abc')).toBe(1);
		expect(turn.markerIndex('authored/triage/t1')).toBe(2);
	});

	it('a citation arriving after its marker resolves to the already-printed integer', () => {
		const turn = makeTurn();
		turn.applyEvent(frame('outcome', { outcome: 'answered' }));
		turn.applyEvent(frame('body_delta', { text: 'see [[p:ableton/live-12/abc]] now' }));
		const before = turn.markerIndex(CITATION.passage_id);
		turn.applyEvent(frame('citation', CITATION));
		// Late resolution costs no reflow: the printed integer is unchanged.
		expect(turn.markerIndex(CITATION.passage_id)).toBe(before);
		expect(turn.citations.get(CITATION.passage_id)).toEqual(CITATION);
	});
});

describe('end of stream without done (9.14)', () => {
	it('yields incomplete, never a settled turn, retaining the partial text', async () => {
		const turn = makeTurn();
		await turn.consume(
			streamOf(
				[
					frame('outcome', { outcome: 'answered' }),
					frame('body_delta', { text: 'Set the monitor to' })
				],
				{ complete: false }
			)
		);
		expect(turn.state).not.toBe('settled');
		expect(turn.incomplete).toBe(true);
		expect(turn.blocks).toHaveLength(1);
	});

	it('fills outcome incomplete where none arrived, so the turn still has a renderer', async () => {
		const turn = makeTurn();
		await turn.consume(streamOf([frame('direct_answer', { text: 'Half an answer' })], { complete: false }));
		expect(turn.envelope.outcome).toBe('incomplete');
		expect(turn.renderer).toBe('answer');
		expect(turn.incomplete).toBe(true);
	});

	it('a stream that ends with done settles normally through consume', async () => {
		const turn = makeTurn();
		await turn.consume(
			streamOf(
				[frame('outcome', { outcome: 'answered' }), frame('done', { complete: true })],
				{ complete: true }
			)
		);
		expect(turn.state).toBe('settled');
		expect(turn.incomplete).toBe(false);
	});
});
