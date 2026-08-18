// Browser proof of the streaming and interaction contracts (task 47;
// requirements 1.13, 4.2, 5.5, 5.8, 11.8, 13.1, 13.3, 13.5). Everything runs
// against the stub engine behind the real dev proxy — no provider, corpus or
// key anywhere.

import { expect, test } from '@playwright/test';
import { ask, askInput, focusedText, openSurface, settled, tabToSelector, tabToText } from './helpers';

declare global {
	interface Window {
		__violations?: string[];
		__announced?: string[];
	}
}

test('nothing already painted moves while an answer streams (4.2)', async ({ page }) => {
	await openSurface(page);
	// Sample every painted line's viewport top on every frame; any change to an
	// already-seen line is a reflow violation. Decision 2's browser-level proof.
	await page.evaluate(() => {
		window.__violations = [];
		const tops = new Map<Element, number>();
		const sample = () => {
			const lines = document.querySelectorAll(
				'.answer .direct, .answer .heading, .answer .step, .answer .paragraph, .answer .bullet, .answer .caveat'
			);
			for (const line of lines) {
				const top = line.getBoundingClientRect().top;
				const seen = tops.get(line);
				if (seen === undefined) tops.set(line, top);
				else if (Math.abs(seen - top) > 0.5) {
					window.__violations?.push(`${line.className}: ${seen} → ${top}`);
				}
			}
			requestAnimationFrame(sample);
		};
		requestAnimationFrame(sample);
	});
	await ask(page, 'walk me through the steps');
	await settled(page);
	expect(await page.evaluate(() => window.__violations)).toEqual([]);
});

test('the core loop needs zero pointer use: ask, narrow, cancel, widen, expand, open (1.13, 13.1)', async ({
	page
}) => {
	await openSurface(page);

	// Ask — focus already rests in the input (1.1); typing is enough.
	await page.keyboard.type('narrow this down');
	await page.keyboard.press('Enter');
	await expect(page.locator('.narrowing')).toBeVisible();

	// Narrow — one keypress on an armed digit (6.3). A candidate reads its
	// `label` and submits its `value`; the two differ in the stub on purpose,
	// so a renderer that showed the submitted text would fail here.
	await expect(page.locator('.state').last()).toHaveText('finished');
	await expect(page.locator('.narrowing .candidates button').nth(1)).toContainText(
		'The APC pads are unlit'
	);
	await page.keyboard.press('2');
	await expect(page.locator('.question').nth(1)).toHaveText('From the APC pads');
	await settled(page);

	// Cancel — a slow turn, stopped from the keyboard, question preserved (8.6).
	await page.keyboard.type('a slow one');
	await page.keyboard.press('Enter');
	await expect(page.getByRole('button', { name: 'Stop' })).toBeVisible();
	await tabToText(page, 'Stop'); // the Stop control sits after the input in the tab order
	await page.keyboard.press('Enter');
	await expect(page.locator('.state').last()).toHaveText('stopped');
	await expect(askInput(page)).toHaveValue('a slow one');
	await askInput(page).clear();

	// Widen scope — into the picker, out to none, back to all, Escape home (2.8, 13.3).
	await tabToSelector(page, 'button.indicator', { shift: true });
	await page.keyboard.press('Enter');
	await tabToText(page, 'None in scope');
	await page.keyboard.press('Enter');
	await expect(page.getByText('No sources in scope')).toBeVisible();
	await tabToText(page, 'All in scope', { shift: true });
	await page.keyboard.press('Enter');
	await page.keyboard.press('Escape');
	await expect(page.locator('button.indicator')).toContainText('All in scope:');
	expect(await focusedText(page)).toContain('All in scope');

	// Expand a citation and open it at source (5.5, 5.6).
	await askInput(page).focus();
	await page.keyboard.type('why is the master silent');
	await page.keyboard.press('Enter');
	await settled(page);
	await tabToText(page, 'Show passage', { shift: true });
	await page.keyboard.press('Enter');
	await expect(page.locator('.passage-text').first()).toBeVisible();
	await tabToText(page, 'Open manual at p312', { shift: true });
	const href = await page.evaluate(() =>
		(document.activeElement as HTMLAnchorElement | null)?.getAttribute('href')
	);
	expect(href).toBe('/sources/ableton/live-12/document#page=312');
	const [popup] = await Promise.all([
		page.context().waitForEvent('page'),
		page.keyboard.press('Enter')
	]);
	// Headless Chromium has no PDF viewer, so the popup's own navigation is not
	// assertable here; that a new tab opened and the ask surface stayed put is.
	await popup.close().catch(() => undefined);
	expect(page.url().endsWith('/')).toBe(true);
});

test('open at source: vendor is exactly #page=N in a new tab; authored reveals in place (5.5, 5.19)', async ({
	page
}) => {
	await openSurface(page);
	await ask(page, 'why is the master silent');
	await settled(page);

	const link = page.getByRole('link', { name: /open manual at p312/i });
	await expect(link).toHaveAttribute('href', '/sources/ableton/live-12/document#page=312');
	await expect(link).toHaveAttribute('target', '_blank');
	await expect(link).toHaveAttribute('rel', 'noopener');

	// The authored branch: the entry revealed in place, entry_location copyable,
	// no navigation leaving the tab.
	const before = page.url();
	const authored = page.locator('.citation-entry', { hasText: 'your own note' });
	await authored.getByRole('button', { name: 'Show passage' }).click();
	await expect(page.getByText('Check the Cue/Master switch on the mixer first.')).toBeVisible();
	await expect(authored.locator('.entry-location')).toHaveText('triage/no-sound.md:12');
	await expect(authored.getByRole('button', { name: 'Copy location' })).toBeVisible();
	expect(page.url()).toBe(before);
});

test('each region dismissed with Escape returns focus to its opener (13.3)', async ({ page }) => {
	await openSurface(page);
	for (const name of ['History', 'Provider configuration']) {
		await page.getByRole('button', { name, exact: true }).click();
		await expect(page.getByRole('region', { name })).toBeVisible();
		await page.keyboard.press('Escape');
		await expect(page.getByRole('region', { name })).toBeHidden();
		expect(await focusedText(page)).toContain(name);
	}
});

test('expanding and collapsing a citation mid-stream leaves it at the same viewport offset (5.8)', async ({
	page
}) => {
	await openSurface(page);
	await ask(page, 'walk me through the steps');
	// Citations arrive ahead of the body deltas; expand while text still streams.
	const entry = page.locator('.citation-entry').first();
	await expect(entry).toBeVisible();

	// Restoring a viewport offset needs something to scroll: wait until the
	// thread genuinely overflows its container, then read at the entry.
	await page.waitForFunction(() => {
		const content = document.querySelector('.content');
		return content !== null && content.scrollHeight > content.clientHeight + 40;
	});
	await entry.scrollIntoViewIfNeeded();
	const before = await entry.boundingBox();
	await entry.getByRole('button', { name: 'Show passage' }).click();
	await expect(page.locator('.passage-text').first()).toBeVisible();

	// Streaming continues above the expanded entry, then the stub goes quiet
	// before its final line — collapse lands mid-stream with no racing paint.
	await expect(page.getByText('Check item 24', { exact: false }).first()).toBeVisible({
		timeout: 10_000
	});
	await page.waitForTimeout(400);
	await expect(page.locator('.state').last()).toHaveText('working…'); // still mid-stream
	await entry.getByRole('button', { name: 'Hide passage' }).click();
	const after = await entry.boundingBox();

	expect(before).not.toBeNull();
	expect(after).not.toBeNull();
	expect(Math.abs((after?.y ?? 0) - (before?.y ?? 0))).toBeLessThanOrEqual(2);
	await settled(page);
});

test('a full turn announces each state transition once and never a streamed fragment (13.5)', async ({
	page
}) => {
	await openSurface(page);
	await page.evaluate(() => {
		window.__announced = [];
		const announcer = document.querySelector('.announcer');
		if (announcer === null) throw new Error('no announcer region');
		new MutationObserver(() => {
			const text = announcer.textContent?.trim();
			if (text) window.__announced?.push(text);
		}).observe(announcer, { childList: true, characterData: true, subtree: true });
	});
	await ask(page, 'walk me through the steps');
	await settled(page);
	expect(await page.evaluate(() => window.__announced)).toEqual([
		'Answer streaming.',
		'Answer finished.'
	]);
});

test('question plus answer occupy ≥ 70% of viewport height at rest, picker collapsed (11.8)', async ({
	page
}) => {
	await openSurface(page);
	await ask(page, 'why is the master silent');
	await settled(page);
	await expect(page.locator('button[aria-expanded]').first()).toHaveAttribute(
		'aria-expanded',
		'false'
	);
	const content = await page.locator('.content').boundingBox();
	const viewport = page.viewportSize();
	expect(content).not.toBeNull();
	expect(viewport).not.toBeNull();
	expect((content?.height ?? 0) / (viewport?.height ?? 1)).toBeGreaterThanOrEqual(0.7);
});
