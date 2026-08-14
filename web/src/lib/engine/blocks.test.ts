// Tests for the append-only block parser and citation markers (requirements
// 4.2, 4.4, 4.5, 5.17; design "Streaming without reflow"; Decisions 2 and 3).
// A block's type is fixed by its first line within at most 10 characters and
// never revised across any chunk split — a re-typed block moves painted text,
// which is the failure 4.2 names.

import { describe, expect, it } from 'vitest';
import { BlockParser, type Block, type InlineSpan } from './blocks';

/** A parser wired to first-appearance marker numbering, as the turn will wire it. */
function parser(): { parse: BlockParser; order: string[] } {
	const order: string[] = [];
	const parse = new BlockParser((passageId) => {
		let index = order.indexOf(passageId);
		if (index === -1) {
			order.push(passageId);
			index = order.length - 1;
		}
		return index + 1;
	});
	return { parse, order };
}

function parseAll(text: string): Block[] {
	const { parse } = parser();
	parse.append(text);
	parse.end();
	return [...parse.blocks];
}

/** Flatten a span list to a readable signature: markers as ⟨n⟩, keys as ⟦t⟧. */
function spansText(spans: readonly InlineSpan[]): string {
	return spans
		.map((span) =>
			span.kind === 'text' ? span.text : span.kind === 'key' ? `⟦${span.text}⟧` : `⟨${span.index}⟩`
		)
		.join('');
}

function blockText(block: Block): string {
	const head = spansText(block.spans);
	if (block.type === 'conflict') {
		return [head, ...block.readings.map((reading) => spansText(reading.spans))].join('¶');
	}
	return head;
}

describe('block typing from the first line (CONTRACTS §4d)', () => {
	it('recognises every member of the closed set at column 0', () => {
		const blocks = parseAll(
			'## Routing\n' +
				'1. Open the mixer\n' +
				'2. Check the Track Activator\n' +
				'- a bullet\n' +
				'plain prose\n' +
				'\n' +
				'!caveat Suite only\n' +
				'!conflict The manuals disagree\n' +
				'- reading one\n' +
				'- reading two\n'
		);
		expect(blocks.map((block) => block.type)).toEqual([
			'heading',
			'ordered-step',
			'ordered-step',
			'bullet',
			'paragraph',
			'caveat',
			'conflict'
		]);
	});

	it('renders ordered steps as separately identifiable blocks with their numbers (4.5)', () => {
		const blocks = parseAll('1. First\n2. Second\n10. Tenth\n');
		expect(blocks).toHaveLength(3);
		expect(blocks.map((block) => (block.type === 'ordered-step' ? block.number : null))).toEqual([
			1, 2, 10
		]);
	});

	it('separates paragraphs on blank lines and keeps soft-wrapped lines together', () => {
		const blocks = parseAll('one line\nstill the first\n\na second paragraph\n');
		expect(blocks.map((block) => block.type)).toEqual(['paragraph', 'paragraph']);
		expect(blockText(blocks[0])).toBe('one line\nstill the first');
		expect(blockText(blocks[1])).toBe('a second paragraph');
	});

	it('keeps two-space-indented continuations inside the caveat block, in reading order', () => {
		const blocks = parseAll('before\n\n!caveat Needs Suite,\n  not Standard\n\nafter\n');
		expect(blocks.map((block) => block.type)).toEqual(['paragraph', 'caveat', 'paragraph']);
		expect(blockText(blocks[1])).toBe('Needs Suite,\nnot Standard');
	});
});

describe('unknown first lines (4.4)', () => {
	it('renders an unknown sigil line as a paragraph, dropping only the wrapper', () => {
		const blocks = parseAll('!suggest Add the Push manual\n');
		expect(blocks).toEqual([
			{ type: 'paragraph', spans: [{ kind: 'text', text: 'Add the Push manual' }] }
		]);
	});

	it('keeps the text verbatim where the sigil is not identifiable within 10 characters', () => {
		const blocks = parseAll('!supercalifragilistic text\n');
		expect(blocks[0].type).toBe('paragraph');
		// Never emits nothing: every character of the line is retained.
		expect(blockText(blocks[0])).toBe('!supercalifragilistic text');
	});

	it('renders a lone or malformed prefix as a paragraph rather than nothing', () => {
		expect(parseAll('##\n').map(blockText)).toEqual(['##']);
		expect(parseAll('-\n').map(blockText)).toEqual(['-']);
		expect(parseAll('1.\n').map(blockText)).toEqual(['1.']);
		expect(parseAll('#not a heading\n').map(blockText)).toEqual(['#not a heading']);
	});
});

describe('conflict arity is a producer obligation, never a re-type', () => {
	it.each([1, 3])('a !conflict with %i readings stays the conflict it declared itself', (count) => {
		const readings = Array.from({ length: count }, (_, i) => `- reading ${i + 1}\n`).join('');
		const blocks = parseAll(`!conflict Disagreement\n${readings}\n`);
		expect(blocks).toHaveLength(1);
		expect(blocks[0].type).toBe('conflict');
		if (blocks[0].type === 'conflict') expect(blocks[0].readings).toHaveLength(count);
	});

	it('a bullet after the conflict closes belongs to a bullet block, not a reading', () => {
		const blocks = parseAll('!conflict X\n- one\n- two\n\n- an ordinary bullet\n');
		expect(blocks.map((block) => block.type)).toEqual(['conflict', 'bullet']);
	});
});

describe('type fixed within 10 characters, never revised across any chunk split (4.2)', () => {
	const document =
		'## Routing\n1. Open `Options` menu\nsee [[p:abc/1]] and [[p:def/2]]\n\n!caveat Suite only [[p:abc/1]]\n!conflict Two readings\n- first [[p:ghi/3]]\n- second [[p:def/2]]\n';

	it('parses identically whatever the chunk boundaries', () => {
		const whole = parseAll(document);
		for (let split = 1; split < document.length; split++) {
			const { parse } = parser();
			parse.append(document.slice(0, split));
			parse.append(document.slice(split));
			parse.end();
			expect(parse.blocks, `split at ${split}`).toEqual(whole);
		}
	});

	it('never re-types and never rewrites a block once painting has begun', () => {
		const { parse } = parser();
		let previous: { type: string; text: string }[] = [];
		for (const character of document) {
			parse.append(character);
			const current = parse.blocks.map((block) => ({ type: block.type, text: blockText(block) }));
			for (let i = 0; i < previous.length; i++) {
				// A block's type never changes, and its painted text only extends.
				expect(current[i].type).toBe(previous[i].type);
				expect(current[i].text.startsWith(previous[i].text)).toBe(true);
			}
			previous = current;
		}
	});
});

describe('inline key terms (backtick spans)', () => {
	it('renders a backtick span as a discrete key element', () => {
		const blocks = parseAll('press `Ctrl+M` to mute\n');
		expect(blocks[0].spans).toEqual([
			{ kind: 'text', text: 'press ' },
			{ kind: 'key', text: 'Ctrl+M' },
			{ kind: 'text', text: ' to mute' }
		]);
	});

	it('an unclosed backtick is literal text, disproved at the line end', () => {
		expect(parseAll('a `dangling\nnext\n').map(blockText)).toEqual(['a `dangling\nnext']);
	});

	it('an empty pair of backticks is literal text, not an empty key', () => {
		expect(blockText(parseAll('a `` b\n')[0])).toBe('a `` b');
	});
});

describe('citation markers (Decision 3)', () => {
	it('assigns each distinct passage_id the next integer at first appearance', () => {
		const { parse, order } = parser();
		parse.append('see [[p:abc/1]] then [[p:def/2]] and again [[p:abc/1]]\n');
		parse.end();
		expect(parse.blocks[0].spans).toEqual([
			{ kind: 'text', text: 'see ' },
			{ kind: 'marker', passageId: 'abc/1', index: 1 },
			{ kind: 'text', text: ' then ' },
			{ kind: 'marker', passageId: 'def/2', index: 2 },
			{ kind: 'text', text: ' and again ' },
			{ kind: 'marker', passageId: 'abc/1', index: 1 }
		]);
		expect(order).toEqual(['abc/1', 'def/2']);
	});

	it('buffers from [ until complete — the raw marker text is never painted', () => {
		const { parse } = parser();
		parse.append('see [[p:ab');
		// The pending marker is held, not painted: painting it and replacing it
		// later would reflow the line.
		expect(spansText(parse.blocks[0].spans)).toBe('see ');
		parse.append('c/1]] done');
		expect(spansText(parse.blocks[0].spans)).toBe('see ⟨1⟩ done');
	});

	it('a disproved candidate is released as literal text', () => {
		expect(blockText(parseAll('a [bracket] b\n')[0])).toBe('a [bracket] b');
		expect(blockText(parseAll('a [[q:not-ours]] b\n')[0])).toBe('a [[q:not-ours]] b');
		expect(blockText(parseAll('a [[p:half\nnext\n')[0])).toBe('a [[p:half\nnext');
	});

	it('an extra opening bracket does not lose the marker that follows it', () => {
		const blocks = parseAll('a [[[p:abc/1]] b\n');
		expect(blockText(blocks[0])).toBe('a [⟨1⟩ b');
	});

	it('a marker pending at end of stream is released as literal text', () => {
		expect(blockText(parseAll('trailing [[p:abc')[0])).toBe('trailing [[p:abc');
	});

	it('markers inside conflict readings resolve through the same numbering', () => {
		const blocks = parseAll('see [[p:abc/1]]\n\n!conflict X\n- one [[p:def/2]]\n- two [[p:abc/1]]\n');
		const conflict = blocks[1];
		expect(conflict.type).toBe('conflict');
		if (conflict.type === 'conflict') {
			expect(spansText(conflict.readings[0].spans)).toBe('one ⟨2⟩');
			expect(spansText(conflict.readings[1].spans)).toBe('two ⟨1⟩');
		}
	});
});
