// Shared helpers for the browser suite. Keyboard-first: the tab-walk helpers
// exist so the core-loop test can reach any control with zero pointer use
// (1.13, 13.1) without hard-coding the surface's whole tab order.

import { expect, type Page } from '@playwright/test';

/** Load the surface and wait for the engine-backed chrome to be ready. */
export async function openSurface(page: Page): Promise<void> {
	await page.goto('/');
	// All three stub sources in scope: named, per 2.6/2.7.
	await expect(page.locator('button.indicator')).toContainText('All in scope:');
}

export function askInput(page: Page) {
	return page.getByRole('textbox', { name: 'Ask a question' });
}

/** Type a question and submit it — keyboard only. */
export async function ask(page: Page, question: string): Promise<void> {
	await askInput(page).click();
	await page.keyboard.type(question);
	await page.keyboard.press('Enter');
}

/** Wait for the newest turn to settle as finished. */
export async function settled(page: Page): Promise<void> {
	await expect(page.locator('.state').last()).toHaveText('finished', { timeout: 20_000 });
}

/**
 * Walk focus with Tab (or Shift+Tab) until the focused element's text contains
 * the needle. Bounded so a missing control fails loudly rather than spinning.
 */
export async function tabToText(
	page: Page,
	needle: string,
	{ shift = false, limit = 80 }: { shift?: boolean; limit?: number } = {}
): Promise<void> {
	for (let step = 0; step < limit; step += 1) {
		const text = await page.evaluate(
			() => (document.activeElement as HTMLElement | null)?.textContent ?? ''
		);
		if (text.includes(needle)) return;
		await page.keyboard.press(shift ? 'Shift+Tab' : 'Tab');
	}
	throw new Error(`focus never reached a control containing "${needle}" in ${limit} tabs`);
}

/** Walk focus until the focused element matches the predicate selector. */
export async function tabToSelector(
	page: Page,
	selector: string,
	{ shift = false, limit = 80 }: { shift?: boolean; limit?: number } = {}
): Promise<void> {
	for (let step = 0; step < limit; step += 1) {
		const matched = await page.evaluate(
			(sel) => document.activeElement?.matches(sel) ?? false,
			selector
		);
		if (matched) return;
		await page.keyboard.press(shift ? 'Shift+Tab' : 'Tab');
	}
	throw new Error(`focus never reached "${selector}" in ${limit} tabs`);
}

/** The text content of the currently focused element. */
export function focusedText(page: Page): Promise<string> {
	return page.evaluate(() => (document.activeElement as HTMLElement | null)?.textContent ?? '');
}
