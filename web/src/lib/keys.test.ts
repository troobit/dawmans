// The keyboard router and arming registry (requirements 1.1, 1.2, 1.11, 13.3;
// design "Keyboard routing and arming"; Decision 5). The decision table is
// asserted in its stated order; the named failure mode — a missed unregister
// leaving a stale armed digit — has its own assertion.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { KeyRouter } from './keys';

let router: KeyRouter;
let uninstall: () => void;
let textarea: HTMLTextAreaElement;
let inserted: string[];

beforeEach(() => {
	router = new KeyRouter();
	uninstall = router.install(window);
	textarea = document.createElement('textarea');
	document.body.appendChild(textarea);
	inserted = [];
});

afterEach(() => {
	uninstall();
	document.body.innerHTML = '';
});

/** Register the question input with an adapter that records manual insertions. */
function registerInput(): () => void {
	return router.registerInput({
		element: textarea,
		focus: () => textarea.focus(),
		insert: (character) => inserted.push(character)
	});
}

/** Dispatch a bubbling keydown on `target` so the window listener sees it. */
function press(key: string, target: EventTarget = document.body, init: KeyboardEventInit = {}) {
	const event = new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true, ...init });
	target.dispatchEvent(event);
	return event;
}

describe('the decision table, in order', () => {
	it('passes a keypress through while a modifier is held', () => {
		registerInput();
		for (const init of [{ ctrlKey: true }, { metaKey: true }, { altKey: true }]) {
			const event = press('a', document.body, init);
			expect(event.defaultPrevented).toBe(false);
		}
		expect(inserted).toEqual([]);
		expect(document.activeElement).not.toBe(textarea);
	});

	it('passes a printable through when the target is another text-entry field', () => {
		registerInput();
		const other = document.createElement('input');
		document.body.appendChild(other);
		other.focus();
		const event = press('a', other);
		expect(event.defaultPrevented).toBe(false);
		expect(inserted).toEqual([]);
		expect(document.activeElement).toBe(other);
	});

	it('passes an armed digit through when the target is another text-entry field', () => {
		registerInput();
		const activate = vi.fn();
		router.arm([{ activate }]);
		const other = document.createElement('input');
		document.body.appendChild(other);
		other.focus();
		const event = press('1', other);
		expect(activate).not.toHaveBeenCalled();
		expect(event.defaultPrevented).toBe(false);
	});

	it('Escape dismisses the topmost region and returns focus to its opener (13.3)', () => {
		const openerA = document.createElement('button');
		const openerB = document.createElement('button');
		document.body.append(openerA, openerB);
		const dismissA = vi.fn();
		const dismissB = vi.fn();
		router.registerRegion({ dismiss: dismissA, opener: openerA });
		const unregisterB = router.registerRegion({ dismiss: dismissB, opener: openerB });

		const first = press('Escape');
		expect(dismissB).toHaveBeenCalledOnce();
		expect(dismissA).not.toHaveBeenCalled();
		expect(document.activeElement).toBe(openerB);
		expect(first.defaultPrevented).toBe(true);

		unregisterB();
		press('Escape');
		expect(dismissA).toHaveBeenCalledOnce();
		expect(document.activeElement).toBe(openerA);
	});

	it('Escape passes through when no region is open', () => {
		registerInput();
		const event = press('Escape');
		expect(event.defaultPrevented).toBe(false);
		expect(inserted).toEqual([]);
	});

	it('a digit 1–4 activates the armed entry while a set is armed (1.11)', () => {
		registerInput();
		const entries = [vi.fn(), vi.fn(), vi.fn()];
		router.arm(entries.map((activate) => ({ activate })));
		const event = press('2');
		expect(entries[1]).toHaveBeenCalledOnce();
		expect(entries[0]).not.toHaveBeenCalled();
		expect(entries[2]).not.toHaveBeenCalled();
		expect(event.defaultPrevented).toBe(true);
		expect(inserted).toEqual([]);
	});

	it('an armed digit activates even when focus rests in the question input', () => {
		// The resting state: 1.1 keeps focus in the (empty) input, and arming
		// exists only while it is empty, so one keypress must still select.
		registerInput();
		const activate = vi.fn();
		router.arm([{ activate }]);
		textarea.focus();
		const event = press('1', textarea);
		expect(activate).toHaveBeenCalledOnce();
		expect(event.defaultPrevented).toBe(true);
		expect(inserted).toEqual([]);
	});

	it('a digit activates nothing while no set is armed — it types normally', () => {
		registerInput();
		const event = press('1');
		expect(event.defaultPrevented).toBe(true);
		expect(document.activeElement).toBe(textarea);
		expect(inserted).toEqual(['1']);
	});

	it('a digit beyond the armed set length types normally (1.11)', () => {
		registerInput();
		const entries = [vi.fn(), vi.fn()];
		router.arm(entries.map((activate) => ({ activate })));
		press('3');
		expect(entries[0]).not.toHaveBeenCalled();
		expect(entries[1]).not.toHaveBeenCalled();
		expect(inserted).toEqual(['3']);
	});

	it('any other printable captures normally while a set is armed (1.11, 6.5)', () => {
		registerInput();
		const activate = vi.fn();
		router.arm([{ activate }]);
		press('a');
		expect(activate).not.toHaveBeenCalled();
		expect(document.activeElement).toBe(textarea);
		expect(inserted).toEqual(['a']);
	});

	it('a printable focuses the input and inserts the character manually (1.2)', () => {
		registerInput();
		const event = press('x');
		// preventDefault then append: the keydown already happened on another
		// element, so focusing the input does not deliver the character.
		expect(event.defaultPrevented).toBe(true);
		expect(document.activeElement).toBe(textarea);
		expect(inserted).toEqual(['x']);
		expect(textarea.value).toBe('');
	});

	it('a printable typed in the question input itself passes through natively', () => {
		registerInput();
		textarea.focus();
		const event = press('x', textarea);
		expect(event.defaultPrevented).toBe(false);
		expect(inserted).toEqual([]);
	});

	it('a non-printable key passes through', () => {
		registerInput();
		for (const key of ['ArrowDown', 'Tab', 'F1', 'Enter']) {
			const event = press(key);
			expect(event.defaultPrevented).toBe(false);
		}
		expect(inserted).toEqual([]);
	});

	it('a printable passes through while no input is registered', () => {
		const event = press('x');
		expect(event.defaultPrevented).toBe(false);
	});
});

describe('the arming registry invariant', () => {
	it('holds at most one armed set ever', () => {
		router.arm([{ activate: vi.fn() }]);
		expect(() => router.arm([{ activate: vi.fn() }])).toThrow();
	});

	it('accepts a new set once the previous one unregisters', () => {
		const disarm = router.arm([{ activate: vi.fn() }]);
		disarm();
		expect(() => router.arm([{ activate: vi.fn() }])).not.toThrow();
	});

	it('unregistering clears the registration — no stale armed digit', () => {
		// The named failure mode: a missed unregister would leave `1` armed.
		registerInput();
		const activate = vi.fn();
		const disarm = router.arm([{ activate }]);
		disarm();
		press('1');
		expect(activate).not.toHaveBeenCalled();
		expect(inserted).toEqual(['1']);
	});

	it('unregistering the input stops capture', () => {
		const unregister = registerInput();
		unregister();
		const event = press('x');
		expect(event.defaultPrevented).toBe(false);
		expect(inserted).toEqual([]);
	});

	it('unregistering a region removes it from the Escape stack', () => {
		const dismiss = vi.fn();
		const unregister = router.registerRegion({ dismiss, opener: null });
		unregister();
		press('Escape');
		expect(dismiss).not.toHaveBeenCalled();
	});
});

describe('window focus restoration (1.1)', () => {
	it('restores focus to the input on window focus', () => {
		registerInput();
		window.dispatchEvent(new FocusEvent('focus'));
		expect(document.activeElement).toBe(textarea);
	});

	it('does not steal focus while an overlay region is open (13.3)', () => {
		registerInput();
		const opener = document.createElement('button');
		document.body.appendChild(opener);
		opener.focus();
		router.registerRegion({ dismiss: vi.fn(), opener });
		window.dispatchEvent(new FocusEvent('focus'));
		expect(document.activeElement).toBe(opener);
	});
});

describe('install and teardown', () => {
	it('removes both listeners on teardown', () => {
		registerInput();
		uninstall();
		const event = press('x');
		expect(event.defaultPrevented).toBe(false);
		expect(inserted).toEqual([]);
		window.dispatchEvent(new FocusEvent('focus'));
		expect(document.activeElement).not.toBe(textarea);
		// Re-install for afterEach symmetry.
		uninstall = router.install(window);
	});
});
