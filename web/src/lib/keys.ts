// The keyboard router and the arming registry (requirements 1.1, 1.2, 1.11,
// 6.3, 13.3; design "Keyboard routing and arming"; Decision 5).
//
// One `keydown` listener on `window`. Components register and unregister —
// the question input, overlay regions, an armed digit set — and never handle
// these keys themselves: whether a `2` types the character or selects a
// candidate is not knowable to any single component.
//
// One deliberate departure from the design's decision table as written: an
// armed digit fires even when the target is the question input. 1.1 keeps
// focus resting in that input and arming exists only while it is empty
// (1.10, Decision 5's invariant), so a literal text-entry pass-through would
// make one-keypress selection impossible in the surface's resting state,
// defeating 1.10 and 6.3. Every *other* text-entry target passes through
// untouched.

/** Where focus returns when a region is dismissed (13.3). */
export type Focusable = { focus(): void };

/**
 * The question input, as the router reaches it. `insert` appends into the
 * component's bound state: the keydown already happened on another element,
 * so focusing the input does not deliver the character — `preventDefault`,
 * focus, then append (1.2, Decision 5).
 */
export type InputAdapter = {
	element: HTMLElement;
	focus(): void;
	insert(character: string): void;
};

/** One armed entry; its digit is its position + 1. The component prints the digit (1.11, 11.6). */
export type ArmedEntry = { activate(): void };

/**
 * An overlay region (picker, history, provider, expanded citation): dismissed
 * by Escape, topmost first, returning focus to its opener (13.3).
 */
export type OverlayRegion = { dismiss(): void; opener: Focusable | null };

export class KeyRouter {
	#input: InputAdapter | null = null;
	#armed: readonly ArmedEntry[] | null = null;
	#regions: OverlayRegion[] = [];

	/** Register the question input. Returns the unregister function. */
	registerInput(adapter: InputAdapter): () => void {
		this.#input = adapter;
		return () => {
			if (this.#input === adapter) this.#input = null;
		};
	}

	/**
	 * Arm digits 1–N for the given entries. At most one armed set ever exists —
	 * shortcuts show only on an empty input and a narrowing turn has a question
	 * in flight, so the ambiguous case cannot arise; a second registration is a
	 * bug and throws rather than silently replacing (1.11, Decision 5).
	 * Returns the unregister function; a missed unregister leaves a stale
	 * armed digit, so callers tie it to unmount.
	 */
	arm(entries: readonly ArmedEntry[]): () => void {
		if (this.#armed !== null) {
			throw new Error('an armed set is already registered; at most one may exist (1.11)');
		}
		this.#armed = entries;
		return () => {
			if (this.#armed === entries) this.#armed = null;
		};
	}

	/** Register an open overlay region on the Escape stack. Returns the unregister function. */
	registerRegion(region: OverlayRegion): () => void {
		this.#regions = [...this.#regions, region];
		return () => {
			this.#regions = this.#regions.filter((held) => held !== region);
		};
	}

	/** Whether any overlay region is open — focus is never stolen from one (13.3). */
	get hasOpenRegion(): boolean {
		return this.#regions.length > 0;
	}

	/** The decision table, in order (design "Keyboard routing and arming"). */
	handleKeydown = (event: KeyboardEvent): void => {
		if (event.ctrlKey || event.metaKey || event.altKey) return;

		const target = event.target;
		const inQuestionInput = this.#input !== null && target === this.#input.element;
		if (!inQuestionInput && isTextEntry(target)) return;

		if (event.key === 'Escape') {
			const region = this.#regions.at(-1);
			if (region !== undefined) {
				event.preventDefault();
				region.dismiss();
				region.opener?.focus();
			}
			return;
		}

		if (this.#armed !== null && event.key >= '1' && event.key <= '4') {
			const entry = this.#armed[Number(event.key) - 1];
			if (entry !== undefined) {
				event.preventDefault();
				entry.activate();
				return;
			}
			// A digit beyond the armed set is an ordinary printable (1.11).
		}

		if (inQuestionInput) return; // Native insertion delivers the character.

		if (this.#input !== null && isPrintable(event.key)) {
			event.preventDefault();
			this.#input.focus();
			this.#input.insert(event.key);
		}
	};

	/**
	 * 1.1: window focus restores focus to the question input — unless an
	 * overlay region holds it, since stealing it would break 13.3's
	 * return-focus contract.
	 */
	handleWindowFocus = (): void => {
		if (this.#regions.length > 0) return;
		this.#input?.focus();
	};

	/** Attach both listeners to `window`. Returns the teardown function. */
	install(target: Window): () => void {
		target.addEventListener('keydown', this.handleKeydown);
		target.addEventListener('focus', this.handleWindowFocus);
		return () => {
			target.removeEventListener('keydown', this.handleKeydown);
			target.removeEventListener('focus', this.handleWindowFocus);
		};
	}
}

/** A single-character `key` is a printable character; every named key is longer. */
function isPrintable(key: string): boolean {
	return key.length === 1;
}

/** Input types that take no text; everything else on an `<input>` does. */
const NON_TEXT_INPUT_TYPES = new Set([
	'button',
	'checkbox',
	'radio',
	'submit',
	'reset',
	'range',
	'color', // spelling-ignore — the DOM input type name

	'file',
	'image'
]);

function isTextEntry(target: EventTarget | null): boolean {
	if (target instanceof HTMLTextAreaElement) return true;
	if (target instanceof HTMLInputElement) return !NON_TEXT_INPUT_TYPES.has(target.type);
	return target instanceof HTMLElement && target.isContentEditable;
}

/** The one router on the surface. */
export const keys = new KeyRouter();
