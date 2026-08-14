// The coverage-failure states (requirements §7, 3.10, 9.2; CONTRACTS §4e;
// design "Coverage failure, errors, and the outcome table"). One renderer,
// three outcomes, and a per-outcome action table: add-and-re-ask from
// addressable suggestions, widen-all where no suggestion exists, both
// suppressed where the engine has already judged no ingested manual covers
// the question, and the copyable filename of the dormant `required_manual` —
// exercised against fixture payloads, never hardcoded absent.

import { cleanup, fireEvent, render, screen } from '@testing-library/svelte';
import { tick } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ScopeStore, SCOPE_STORAGE_KEY } from '../state/scope.svelte';
import { ThreadStore } from '../state/thread.svelte';
import { fakeEngine, type FakeEngine, type TurnChannel } from '../testing/turn-channel';
import ThreadView from './ThreadView.svelte';

const ALL_SOURCES = ['live/manual', 'akai/apc', 'alesis/nitro', 'authored/triage'];
const NAMES: Record<string, string> = {
	'live/manual': 'Live 12 Manual',
	'akai/apc': 'APC Key 25 Guide',
	'alesis/nitro': 'Nitro Max Guide',
	'authored/triage': 'Your triage notes'
};

/** The sources the picker knows, as the coverage renderer needs them (7.5, 7.8). */
const sourcesLike = {
	ids: ALL_SOURCES,
	displayName: (id: string) => NAMES[id]
};

let engine: FakeEngine;
let scope: ScopeStore;
let thread: ThreadStore;

beforeEach(() => {
	localStorage.clear();
	sessionStorage.clear();
	engine = fakeEngine();
	scope = new ScopeStore();
	scope.load(ALL_SOURCES);
	thread = new ThreadStore({ scope, submit: engine.submit });
});

afterEach(() => {
	cleanup();
	document.body.innerHTML = '';
});

/** Narrow the scope to the given ids. */
function narrowTo(ids: string[]): void {
	for (const id of ALL_SOURCES) {
		if (scope.isSelected(id) !== ids.includes(id)) scope.toggle(id);
	}
}

async function lastChannel(): Promise<TurnChannel> {
	await vi.waitFor(() => expect(engine.channels.length).toBeGreaterThan(0));
	return engine.channels[engine.channels.length - 1];
}

/** Submit and settle a turn with the given outcome and extra events. */
async function settle(
	outcome: string,
	events: Array<[string, unknown]> = [],
	question = 'why is the kick distorting?'
) {
	const result = render(ThreadView, { props: { thread, scope, sources: sourcesLike } });
	thread.submit(question);
	const channel = await lastChannel();
	channel.emit('outcome', { outcome });
	for (const [event, data] of events) channel.emit(event, data);
	channel.emit('done', { complete: true });
	channel.close();
	await vi.waitFor(() => expect(thread.turns.at(-1)?.state).toBe('settled'));
	await tick();
	return result;
}

describe('refused-not-covered states the failure plainly (7.1, 7.2, 7.3)', () => {
	it('states that the in-scope sources do not cover it, with no synthesised answer', async () => {
		narrowTo(['live/manual']);
		const { container } = await settle('refused-not-covered');
		const state = container.querySelector('.coverage-failure');
		expect(state).not.toBeNull();
		expect(state?.textContent).toMatch(/do(es)? not cover/i);
		// No synthesised answer beside it, and not the answer renderer.
		expect(container.querySelector('.answer')).toBeNull();
		expect(container.querySelector('.direct')).toBeNull();
		// Distinct from a narrowing question and an error.
		expect(container.querySelector('.narrowing')).toBeNull();
		expect(container.querySelector('.error')).toBeNull();
	});

	it('names the sources that were in scope at ask time (7.3)', async () => {
		narrowTo(['live/manual', 'akai/apc']);
		const { container } = await settle('refused-not-covered');
		const state = container.querySelector('.coverage-failure');
		expect(state?.textContent).toContain('Live 12 Manual');
		expect(state?.textContent).toContain('APC Key 25 Guide');
		expect(state?.textContent).not.toContain('Nitro Max Guide');
	});
});

describe('suggested sources add and re-ask in one activation (7.4)', () => {
	it('adds the named sources to scope and re-asks the same question', async () => {
		narrowTo(['live/manual']);
		await settle('refused-not-covered', [
			['suggested_sources', [{ source_id: 'akai/apc', display_name: 'APC Key 25 Guide' }]]
		]);

		await fireEvent.click(screen.getByRole('button', { name: /APC Key 25 Guide/ }));
		expect(engine.requests).toHaveLength(2);
		expect(engine.requests[1].question).toBe('why is the kick distorting?');
		expect(engine.requests[1].sources).toContain('akai/apc');
		expect(engine.requests[1].sources).toContain('live/manual');
		expect(scope.isSelected('akai/apc')).toBe(true);
	});

	it('attributes the gap to the narrowing in force, not to missing documentation (3.10)', async () => {
		narrowTo(['live/manual']);
		const { container } = await settle('refused-not-covered', [
			['suggested_sources', [{ source_id: 'akai/apc', display_name: 'APC Key 25 Guide' }]]
		]);
		const state = container.querySelector('.coverage-failure');
		expect(state?.textContent).toMatch(/narrow/i);
		expect(state?.textContent).not.toMatch(/not documented|missing documentation/i);
	});
});

describe('widen-all where nothing is suggested (7.5, 7.9)', () => {
	it('offers widen-to-all-and-re-ask when out-of-scope sources exist', async () => {
		narrowTo(['live/manual']);
		await settle('refused-not-covered');

		await fireEvent.click(screen.getByRole('button', { name: /widen|all sources/i }));
		expect(engine.requests).toHaveLength(2);
		expect(engine.requests[1].question).toBe('why is the kick distorting?');
		expect([...engine.requests[1].sources].sort()).toEqual([...ALL_SOURCES].sort());
	});

	it('persists the widened scope rather than reverting it (7.9)', async () => {
		narrowTo(['live/manual']);
		await settle('refused-not-covered');
		await fireEvent.click(screen.getByRole('button', { name: /widen|all sources/i }));

		for (const id of ALL_SOURCES) expect(scope.isSelected(id)).toBe(true);
		// Persisted, so it survives a reload and decays per session (3.5, 3.6).
		const stored = JSON.parse(localStorage.getItem(SCOPE_STORAGE_KEY)!) as { selected: string[] };
		expect([...stored.selected].sort()).toEqual([...ALL_SOURCES].sort());
	});

	it('suppresses widen-all on out-of-domain and no-manual-for-device (7.5)', async () => {
		narrowTo(['live/manual']);
		await settle('out-of-domain');
		expect(screen.queryByRole('button', { name: /widen|all sources/i })).toBeNull();
		cleanup();

		engine = fakeEngine();
		thread = new ThreadStore({ scope, submit: engine.submit });
		await settle('no-manual-for-device', [
			['required_device', { device: 'boss/rc-505', display_name: 'Boss RC-505' }]
		]);
		expect(screen.queryByRole('button', { name: /widen|all sources/i })).toBeNull();
	});
});

describe('out-of-domain (7.6)', () => {
	it('states technique-not-control wording and leaves the question re-editable', async () => {
		const { container } = await settle('out-of-domain', [], 'how do I gain-stage a mix?');
		const state = container.querySelector('.coverage-failure');
		expect(state?.textContent).toMatch(/technique/i);
		expect(state?.textContent).toMatch(/not (a )?documented control/i);
		// No suggestion and no widen control.
		expect(screen.queryByRole('button', { name: /widen|all sources|re-ask/i })).toBeNull();

		// Re-editable in one activation: the question lands back in the draft.
		await fireEvent.click(screen.getByRole('button', { name: /edit/i }));
		expect(thread.draft).toBe('how do I gain-stage a mix?');
	});
});

describe('no-manual-for-device (7.7)', () => {
	it('names the device and that ingestion must re-run', async () => {
		const { container } = await settle('no-manual-for-device', [
			['required_device', { device: 'boss/rc-505', display_name: 'Boss RC-505' }]
		]);
		const state = container.querySelector('.coverage-failure');
		expect(state?.textContent).toContain('Boss RC-505');
		expect(state?.textContent).toMatch(/ingest/i);
	});

	it('renders the required_manual filename copyable in one activation (fixture — the field is dormant)', async () => {
		const writeText = vi.fn().mockResolvedValue(undefined);
		Object.defineProperty(navigator, 'clipboard', {
			value: { writeText },
			configurable: true
		});
		const filename = 'boss_rc-505_<doctype>_v<version>_<lang>.pdf';
		const { container } = await settle('no-manual-for-device', [
			['required_device', { device: 'boss/rc-505', display_name: 'Boss RC-505' }],
			['required_manual', { filename, placeholders: ['doctype', 'version', 'lang'] }]
		]);

		expect(container.querySelector('.coverage-failure')?.textContent).toContain(filename);
		await fireEvent.click(screen.getByRole('button', { name: /copy/i }));
		expect(writeText).toHaveBeenCalledExactlyOnceWith(filename);
	});

	it('names the placeholder fields from placeholders[], never by splitting the filename', async () => {
		const { container } = await settle('no-manual-for-device', [
			['required_device', { device: 'behringer/umc404hd', display_name: 'Behringer UMC404HD' }],
			// The filename would split into more fields; only the listed one is owed.
			['required_manual', { filename: 'behringer_umc404hd_<doctype>_v1.0_en.pdf', placeholders: ['doctype'] }]
		]);
		const fields = container.querySelector('.placeholders');
		expect(fields?.textContent).toContain('doctype');
		expect(fields?.textContent).not.toContain('version');
		expect(fields?.textContent).not.toContain('lang');
	});

	it('synthesises nothing where required_manual is absent — names the convention and the device', async () => {
		const { container } = await settle('no-manual-for-device', [
			['required_device', { device: 'boss/rc-505', display_name: 'Boss RC-505' }]
		]);
		const state = container.querySelector('.coverage-failure');
		// The manuals/ naming convention and the device, no invented name.
		expect(state?.textContent).toContain('<vendor>_<product>_<doctype>_v<version>_<lang>.pdf');
		expect(state?.textContent).toContain('Boss RC-505');
		expect(screen.queryByRole('button', { name: /copy/i })).toBeNull();
	});
});

describe('all sources already in scope (7.8, 9.2)', () => {
	it('says so, drops widen, and falls through to re-editing the question', async () => {
		const { container } = await settle('refused-not-covered');
		const state = container.querySelector('.coverage-failure');
		expect(state?.textContent).toMatch(/already in scope|every available source/i);
		expect(screen.queryByRole('button', { name: /widen|all sources/i })).toBeNull();

		// Never a dead end: at least one activatable control remains (9.2).
		await fireEvent.click(screen.getByRole('button', { name: /edit/i }));
		expect(thread.draft).toBe('why is the kick distorting?');
	});

	it('falls through to the filename action where a required device was named', async () => {
		const writeText = vi.fn().mockResolvedValue(undefined);
		Object.defineProperty(navigator, 'clipboard', {
			value: { writeText },
			configurable: true
		});
		await settle('no-manual-for-device', [
			['required_device', { device: 'boss/rc-505', display_name: 'Boss RC-505' }],
			['required_manual', { filename: 'boss_rc-505_<doctype>_v<version>_<lang>.pdf', placeholders: ['doctype', 'version', 'lang'] }]
		]);
		expect(screen.queryByRole('button', { name: /widen|all sources/i })).toBeNull();
		await fireEvent.click(screen.getByRole('button', { name: /copy/i }));
		expect(writeText).toHaveBeenCalledOnce();
	});
});

describe('keyboard reach (7.10)', () => {
	it('offers every control as a focusable element inside the state itself', async () => {
		narrowTo(['live/manual']);
		const { container } = await settle('refused-not-covered', [
			['suggested_sources', [{ source_id: 'akai/apc', display_name: 'APC Key 25 Guide' }]]
		]);
		const controls = [...container.querySelectorAll('.coverage-failure button, .coverage-failure a')];
		expect(controls.length).toBeGreaterThan(0);
		for (const control of controls) {
			expect(control.getAttribute('tabindex')).not.toBe('-1');
		}
	});
});
