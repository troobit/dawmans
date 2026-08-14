// The append-only block parser over CONTRACTS §4d's closed set (design
// "Streaming without reflow"; Decisions 2 and 3). A block's type is decided by
// its first line — every member is identifiable at column 0 — and never
// revised: the parser holds a line only until its prefix is decidable (at most
// 10 characters, the longest prefix being `!conflict `), fixes the type, and
// streams the remainder into that block. A block already on screen is never
// re-typed and never re-flowed; painted text only ever extends.
//
// The two inline forms, and no others (CONTRACTS §4d): the citation marker
// `[[p:<passage_id>]]`, buffered from `[` until complete or disproved and
// painted as its first-appearance integer immediately; and a backtick span for
// a key term. Emphasis, links and images are deliberately absent.

/** The longest decidable prefix, `!conflict `. A new longer sigil must move this with it. */
const PREFIX_LIMIT = '!conflict '.length;
const MARKER_OPEN = '[[p:';
/** A runaway candidate this long is no marker; release it as text. */
const MARKER_LIMIT = 256;

export type InlineSpan =
	| { kind: 'text'; text: string }
	/** A key term (backtick span): a key name or combination, a parameter, or a menu path. */
	| { kind: 'key'; text: string }
	/** A citation marker, painted as its integer; width never changes when the citation resolves (Decision 3). */
	| { kind: 'marker'; passageId: string; index: number };

export type Reading = { spans: InlineSpan[] };

export type Block =
	| { type: 'heading'; spans: InlineSpan[] }
	| { type: 'ordered-step'; number: number; spans: InlineSpan[] }
	| { type: 'bullet'; spans: InlineSpan[] }
	| { type: 'paragraph'; spans: InlineSpan[] }
	| { type: 'caveat'; spans: InlineSpan[] }
	| { type: 'conflict'; spans: InlineSpan[]; readings: Reading[] };

/**
 * Returns the printed 1-based integer for a passage_id. The turn owns the
 * first-appearance order (its marker list is what the citation list renders
 * from), so assignment is injected rather than kept here.
 */
export type MarkerAssign = (passageId: string) => number;

export class BlockParser {
	#blocks: Block[] = [];
	/** The block still accepting continuation lines; heading, step and bullet close at their line end. */
	#open: Block | null = null;
	/** Where inline content currently lands: a block's spans or a conflict reading's. */
	#target: InlineSpan[] | null = null;
	#atLineStart = true;
	/** The undecided line prefix — held, never painted, until the type is fixed. */
	#prefix = '';
	#inline: 'text' | 'marker' | 'key' = 'text';
	/** The buffered marker or key candidate — held, never painted, until complete or disproved. */
	#pending = '';

	constructor(private readonly assignMarker: MarkerAssign) {}

	get blocks(): readonly Block[] {
		return this.#blocks;
	}

	append(text: string): void {
		for (const character of text) {
			if (this.#atLineStart) this.#feedLineStart(character);
			else this.#feedContent(character);
		}
	}

	/** The turn ended: release anything still buffered. Never emits nothing (4.4). */
	end(): void {
		if (this.#atLineStart) {
			// A line the stream ended before its prefix was decidable is prose.
			if (this.#prefix !== '') this.#beginParagraph(this.#prefix);
		}
		if (this.#inline !== 'text') this.#releasePending();
	}

	// ---- line starts: deciding a block's type at column 0 ----------------

	#feedLineStart(character: string): void {
		if (character === '\n') {
			if (this.#prefix === '') {
				// A blank line closes whatever block was still accepting lines.
				this.#open = null;
				this.#target = null;
				return;
			}
			// The line ended before its prefix was decidable — `##`, `1.`, `-`,
			// a bare sigil. None matched its full form, so it is prose (4.4).
			this.#beginParagraph(this.#prefix);
			this.#prefix = '';
			this.#endLine();
			return;
		}

		this.#prefix += character;
		const decision = this.#decide(this.#prefix);
		if (decision === null) {
			if (this.#prefix.length >= PREFIX_LIMIT) {
				// 10 characters without a match: the type is fixed as paragraph,
				// text verbatim — the sigil could not be identified in bound.
				const remainder = this.#prefix;
				this.#prefix = '';
				this.#atLineStart = false;
				this.#beginParagraph('');
				this.#stream(remainder);
			}
			return;
		}

		this.#prefix = '';
		this.#atLineStart = false;
		decision();
	}

	/**
	 * Decide the block type from the buffered prefix, or return null while it
	 * is still undecidable. The returned thunk begins the block and streams
	 * whatever of the line followed the prefix.
	 */
	#decide(prefix: string): (() => void) | null {
		// A caveat's continuation lines are indented two spaces.
		if (this.#open?.type === 'caveat' && prefix[0] === ' ') {
			if (prefix === ' ') return null;
			if (prefix === '  ') {
				const caveat = this.#open;
				return () => {
					this.#target = caveat.spans;
					this.#appendText('\n');
				};
			}
			// A single space then something else: not a continuation, and not a
			// prefix of anything — prose.
			return () => this.#beginParagraph(prefix);
		}

		if (prefix === '## ') return () => this.#begin({ type: 'heading', spans: [] });
		if (prefix === '#' || prefix === '##') return null;

		if (prefix === '- ') {
			// Inside an open conflict, `- ` is a reading; anywhere else a bullet.
			if (this.#open?.type === 'conflict') {
				const conflict = this.#open;
				return () => {
					const reading: Reading = { spans: [] };
					conflict.readings.push(reading);
					this.#target = reading.spans;
				};
			}
			return () => this.#begin({ type: 'bullet', spans: [] });
		}
		if (prefix === '-') return null;

		if (/^\d+\.?$/.test(prefix)) return null;
		const step = /^(\d+)\. $/.exec(prefix);
		if (step !== null) {
			return () => this.#begin({ type: 'ordered-step', number: Number(step[1]), spans: [] });
		}

		if (prefix[0] === '!') {
			if (prefix === '!caveat ') return () => this.#begin({ type: 'caveat', spans: [] });
			if (prefix === '!conflict ')
				return () => this.#begin({ type: 'conflict', spans: [], readings: [] });
			if ('!caveat '.startsWith(prefix) || '!conflict '.startsWith(prefix)) return null;
			// An unknown sigil: drop the wrapper it does not know and keep the
			// text (CONTRACTS §4b rule 2) — decidable once the sigil token ends.
			if (prefix.endsWith(' ')) return () => this.#beginParagraph('');
			return null;
		}

		// Anything else is prose from its first character.
		return () => this.#beginParagraph(prefix);
	}

	#begin(block: Block): void {
		this.#blocks.push(block);
		this.#open = block;
		this.#target = block.spans;
	}

	/** Begin — or continue, across a soft line break — a paragraph. */
	#beginParagraph(text: string): void {
		this.#atLineStart = false;
		if (this.#open?.type === 'paragraph') {
			this.#target = this.#open.spans;
			this.#appendText('\n');
		} else {
			const paragraph: Block = { type: 'paragraph', spans: [] };
			this.#blocks.push(paragraph);
			this.#open = paragraph;
			this.#target = paragraph.spans;
		}
		if (text !== '') this.#stream(text);
	}

	#endLine(): void {
		if (this.#inline !== 'text') this.#releasePending();
		// Paragraphs, caveats and conflicts accept further lines; a heading,
		// step or bullet is complete at its line end.
		if (
			this.#open !== null &&
			(this.#open.type === 'heading' ||
				this.#open.type === 'ordered-step' ||
				this.#open.type === 'bullet')
		) {
			this.#open = null;
		}
		this.#target = null;
		this.#atLineStart = true;
	}

	// ---- inline content: text, markers and key terms ---------------------

	#feedContent(character: string): void {
		if (this.#inline === 'marker') {
			this.#feedMarker(character);
			return;
		}
		if (this.#inline === 'key') {
			this.#feedKey(character);
			return;
		}
		if (character === '\n') {
			this.#endLine();
			return;
		}
		if (character === '[') {
			this.#inline = 'marker';
			this.#pending = '[';
			return;
		}
		if (character === '`') {
			this.#inline = 'key';
			this.#pending = '`';
			return;
		}
		this.#appendText(character);
	}

	#feedMarker(character: string): void {
		if (character === '\n') {
			this.#releasePending();
			this.#endLine();
			return;
		}
		const candidate = this.#pending + character;
		const inOpener = candidate.length <= MARKER_OPEN.length;
		const viable = inOpener
			? MARKER_OPEN.startsWith(candidate)
			: candidate.length <= MARKER_LIMIT &&
				// A lone `]` may only be the first half of the closing pair.
				!(candidate[candidate.length - 2] === ']' && character !== ']');
		if (!viable) {
			this.#releasePending();
			this.#feedContent(character);
			return;
		}
		this.#pending = candidate;
		if (!inOpener && candidate.endsWith(']]')) {
			const passageId = candidate.slice(MARKER_OPEN.length, -2);
			if (passageId === '') {
				this.#releasePending();
				return;
			}
			this.#pending = '';
			this.#inline = 'text';
			// Painted as its integer immediately, before the citation event
			// arrives; the number is assigned at first appearance and its width
			// never changes on late resolution (Decision 3).
			this.#target?.push({ kind: 'marker', passageId, index: this.assignMarker(passageId) });
		}
	}

	#feedKey(character: string): void {
		if (character === '\n') {
			this.#releasePending();
			this.#endLine();
			return;
		}
		if (character === '`') {
			const text = this.#pending.slice(1);
			this.#pending = '';
			this.#inline = 'text';
			// An empty pair of backticks is literal text, not an empty key.
			if (text === '') this.#appendText('``');
			else this.#target?.push({ kind: 'key', text });
			return;
		}
		this.#pending += character;
	}

	/**
	 * A candidate was disproved: its first character is literal text, and the
	 * rest re-scans — `[[[p:…` must not lose the marker behind the stray bracket.
	 */
	#releasePending(): void {
		const buffered = this.#pending;
		this.#pending = '';
		this.#inline = 'text';
		if (buffered === '') return;
		this.#appendText(buffered[0]);
		for (const character of buffered.slice(1)) this.#feedContent(character);
	}

	#appendText(text: string): void {
		if (this.#target === null) return;
		const last = this.#target[this.#target.length - 1];
		if (last !== undefined && last.kind === 'text') last.text += text;
		else this.#target.push({ kind: 'text', text });
	}

	#stream(text: string): void {
		for (const character of text) this.#feedContent(character);
	}
}
