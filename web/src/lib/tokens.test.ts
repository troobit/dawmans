// Decision 6: contrast (11.3, 11.4) and background luminance (11.5) are
// arithmetic over the declared token values, so they are asserted here and a
// breach fails the build — leaving them observational is the silent-drift risk
// the requirements name. The genuinely perceptual criteria of §11 (11.1, 11.2)
// stay with the stand-back loop and are not asserted here.
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

// Read from disk rather than importing: vitest stubs CSS imports (even `?raw`)
// to an empty module, and the assertions are over the declared source anyway.
const css = readFileSync(resolve(process.cwd(), 'src/lib/tokens.css'), 'utf-8');

const tokens = new Map<string, string>();
for (const [, name, value] of css.matchAll(/(--[a-z0-9-]+)\s*:\s*(#[0-9a-fA-F]{3,8})\s*[;}]/g)) {
	tokens.set(name, value);
}

function token(name: string): string {
	const value = tokens.get(name);
	if (!value) throw new Error(`token ${name} is not declared in tokens.css`);
	return value;
}

// WCAG 2 relative luminance over sRGB.
function luminance(hex: string): number {
	const digits = hex.slice(1);
	const full =
		digits.length === 3
			? digits
					.split('')
					.map((d) => d + d)
					.join('')
			: digits;
	const [r, g, b] = [0, 2, 4].map((i) => {
		const channel = parseInt(full.slice(i, i + 2), 16) / 255;
		return channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4;
	});
	return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function contrast(a: string, b: string): number {
	const [darker, lighter] = [luminance(a), luminance(b)].sort((x, y) => x - y);
	return (lighter + 0.05) / (darker + 0.05);
}

// Text may sit on the page background or on a raised surface, so every text
// floor is asserted against both.
const backgrounds = ['--colour-bg', '--colour-surface'];

// 11.3: body text ≥ 7:1; every other text element — secondary metadata,
// disabled-looking states, interactive text in every 13.8 state — ≥ 4.5:1.
// The interactive-state variants are in this table so 13.8 holds at rest and
// in hover/focus/active/disabled, not only at rest.
const textFloors: [name: string, floor: number][] = [
	['--colour-text', 7],
	['--colour-text-secondary', 4.5],
	['--colour-text-disabled', 4.5],
	['--colour-accent', 4.5],
	['--colour-accent-hover', 4.5],
	['--colour-accent-active', 4.5]
];

// 11.4: non-text state indicators and the focus ring ≥ 3:1.
const indicatorFloors: [name: string, floor: number][] = [
	['--colour-focus-ring', 3],
	['--colour-state-working', 3],
	['--colour-state-finished', 3],
	['--colour-state-broken', 3],
	['--colour-state-caveat', 3]
];

describe('contrast floors (11.3, 11.4, 13.8)', () => {
	for (const [name, floor] of [...textFloors, ...indicatorFloors]) {
		for (const bg of backgrounds) {
			it(`${name} on ${bg} ≥ ${floor}:1`, () => {
				expect(contrast(token(name), token(bg))).toBeGreaterThanOrEqual(floor);
			});
		}
	}
});

describe('dark interface (11.5)', () => {
	it('page background relative luminance is inside the band (≤ 0.08)', () => {
		expect(luminance(token('--colour-bg'))).toBeLessThanOrEqual(0.08);
	});

	it('surfaces stay dark too', () => {
		expect(luminance(token('--colour-surface'))).toBeLessThanOrEqual(0.08);
	});

	it('text is lighter than background', () => {
		expect(luminance(token('--colour-text'))).toBeGreaterThan(luminance(token('--colour-bg')));
	});
});

// The 11.3-versus-11.5 trade-off, resolved as the requirements direct and held
// as two enforced bounds rather than a remembered intention: the background
// sits at the lighter end of 11.5's band so body text reaches its contrast
// floor without going to maximal white, which 11.5 warns reads as harsh in a
// dim room.
describe('the 11.3/11.5 resolution', () => {
	it('background sits at the lighter end of its band (≥ 0.03)', () => {
		expect(luminance(token('--colour-bg'))).toBeGreaterThanOrEqual(0.03);
	});

	it('body text stops short of maximal white (luminance ≤ 0.9)', () => {
		expect(luminance(token('--colour-text'))).toBeLessThanOrEqual(0.9);
	});
});
