// The accessibility floor in a real browser (task 47; requirements 11.6, 13.2,
// 13.4, 13.6, 13.7, 13.8): axe-core over every rendered state at WCAG A/AA,
// greyscale channels, 200% text, and reduced motion.

import { createRequire } from 'node:module';
import { expect, test, type Page } from '@playwright/test';
import { ask, openSurface, settled } from './helpers';

const require = createRequire(import.meta.url);
const AXE_PATH = require.resolve('axe-core/axe.min.js');

type AxeViolation = { id: string; impact: string; nodes: { target: string[] }[] };

/** Run axe at the WCAG A/AA floor and return the violations. */
async function axeViolations(page: Page): Promise<AxeViolation[]> {
	return page.evaluate(async () => {
		// eslint-disable-next-line @typescript-eslint/no-explicit-any
		const axe = (window as any).axe;
		const result = await axe.run(document, {
			runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21aa'] }
		});
		return result.violations.map((violation: AxeViolation) => ({
			id: violation.id,
			impact: violation.impact,
			nodes: violation.nodes.map((node) => ({ target: node.target }))
		}));
	});
}

test('axe-core floor holds over every rendered state (13.2, 13.4, 13.8)', async ({ page }) => {
	await openSurface(page);
	await page.addScriptTag({ path: AXE_PATH });

	// At rest.
	expect(await axeViolations(page)).toEqual([]);

	// Picker expanded: toggle names and states (13.4).
	await page.locator('button[aria-expanded]').first().click();
	expect(await axeViolations(page)).toEqual([]);
	await page.keyboard.press('Escape');

	// History and provider regions.
	for (const name of ['History', 'Provider configuration']) {
		await page.getByRole('button', { name, exact: true }).click();
		expect(await axeViolations(page)).toEqual([]);
		await page.keyboard.press('Escape');
	}

	// A settled answer with citations, and a broken state with its disclosure.
	await ask(page, 'why is the master silent');
	await settled(page);
	expect(await axeViolations(page)).toEqual([]);
	await ask(page, 'break this turn');
	await expect(page.locator('.error.broken')).toBeVisible();
	expect(await axeViolations(page)).toEqual([]);
});

test('every 11.6 distinction survives greyscale via a non-colour channel', async ({ page }) => {
	await openSurface(page);

	// Build the distinctions: a finished turn, a broken turn, a narrowed scope.
	await ask(page, 'why is the master silent');
	await settled(page);
	await ask(page, 'break this turn');
	await expect(page.locator('.error.broken')).toBeVisible();
	const indicator = page.locator('button[aria-expanded]').first();
	await indicator.click();
	await page.getByRole('checkbox').first().uncheck();

	// Render greyscale and keep the screenshot as the reviewable artifact.
	await page.addStyleTag({ content: 'html { filter: grayscale(1); }' });
	await page.screenshot({ path: 'test-results/greyscale.png', fullPage: true });

	// The channels that carry each distinction without colour:
	// in/out of scope — filled versus hollow marker plus the word (2.14).
	await expect(page.locator('.scope-marker').first()).toHaveText('○');
	await expect(page.getByText('out of scope').first()).toBeVisible();
	await expect(page.locator('.scope-marker').nth(1)).toHaveText('●');
	// working/finished/broken — distinct static shapes beside distinct labels (8.4).
	const shapes = await page.locator('.state-shape').allTextContents();
	expect(shapes).toEqual(['✓', '✕']);
	// cited/uncited — the numeric marker's presence.
	await expect(page.locator('sup.marker').first()).toBeVisible();
	// authored/manufacturer — a stated kind word versus a doc version (5.14, 5.2).
	await expect(page.getByText('your own note').first()).toBeVisible();
	await expect(page.locator('.doc-version').first()).toHaveText('v12');
	// armed digits — the printed digit itself (1.11).
	await page.keyboard.press('Escape');
	const digits = await page.locator('.shortcuts kbd').allTextContents();
	expect(digits).toEqual(['1', '2', '3', '4']);
});

test('no horizontal scrolling or clipped control at 200% browser text size (13.7)', async ({
	page
}) => {
	// 200% text on a 1280×800 window lays out like 100% on 640×400 — the
	// standard WCAG reflow equivalence, since the surface uses no viewport units
	// for type.
	await page.setViewportSize({ width: 640, height: 400 });
	await openSurface(page);
	await ask(page, 'why is the master silent');
	await settled(page);
	expect(
		await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)
	).toBe(true);

	await page.locator('button[aria-expanded]').first().click();
	expect(
		await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)
	).toBe(true);
});

test('reduced motion replaces the pulse with a live counter; states stay distinct (13.6, 8.4)', async ({
	page
}) => {
	await page.emulateMedia({ reducedMotion: 'reduce' });
	await openSurface(page);

	await ask(page, 'a slow one');
	// The counter is live text, not motion; nothing animates anywhere.
	const elapsed = page.locator('.elapsed');
	await expect(elapsed).toBeVisible();
	const first = await elapsed.textContent();
	await expect(elapsed).not.toHaveText(first ?? '', { timeout: 5_000 });
	expect(await page.locator('[data-animated="true"]').count()).toBe(0);
	// The working turn carries the working shape while the wait runs.
	await expect(page.locator('.state-shape').last()).toHaveText('●');

	await page.getByRole('button', { name: 'Cancel' }).click();
	await expect(page.locator('.state').last()).toHaveText('stopped');

	// Finished and broken remain distinguishable without motion or colour.
	await ask(page, 'why is the master silent');
	await settled(page);
	await ask(page, 'break this turn');
	await expect(page.locator('.error.broken')).toBeVisible();
	const shapes = await page.locator('.state-shape').allTextContents();
	expect(shapes).toEqual(['■', '✓', '✕']);
});
