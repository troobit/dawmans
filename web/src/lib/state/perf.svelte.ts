// Per-turn marks for 8.7, 8.8 and 8.9, and the 9.3 diagnostic disclosure
// (design "Measurement"). `submit` is stamped in the submit handler at Turn
// construction; `firstByte` when the first content event leaves the SSE
// reader; `firstPaint` in a requestAnimationFrame after that content is in
// the DOM. 8.8 is firstPaint − submit, 8.9 is firstPaint − firstByte; a
// breach is attributed with the engine's `timings` before any work is done
// on this surface. Real-provider p95 measurement is the iterative loop.

export type TurnMarks = {
	submit: number;
	firstByte?: number;
	firstPaint?: number;
};

/** 8.10: hosted and local providers are legitimately different speeds. */
export type ProviderClass = 'hosted' | 'local';

/**
 * The "taking longer than usual" threshold (8.5), per provider class (8.10):
 * hosted 3 s, local 5 s — inside the 2.5–4 s and 4–8 s bands. Each must sit
 * above that class's observed median time-to-first-token, which is the
 * iterative loop's tuning check, not this file's.
 */
export const SLOW_THRESHOLD_MS: Record<ProviderClass, number> = {
	hosted: 3000,
	local: 5000
};

/** Stamp once, on the first content event; later content never moves it. */
export function markFirstByte(marks: TurnMarks): void {
	if (marks.firstByte === undefined) marks.firstByte = performance.now();
}

const scheduled = new WeakSet<TurnMarks>();

/**
 * Stamp `firstPaint` in a requestAnimationFrame callback — after the DOM
 * insert the caller just made, so the mark lands beside the actual paint.
 * Idempotent: the first schedule wins, re-renders never re-stamp.
 */
export function scheduleFirstPaint(marks: TurnMarks): void {
	if (marks.firstPaint !== undefined || scheduled.has(marks)) return;
	scheduled.add(marks);
	requestAnimationFrame(() => {
		if (marks.firstPaint === undefined) marks.firstPaint = performance.now();
	});
}

export type TurnMeasures = {
	/** 8.8: keypress to first painted answer token. */
	submitToFirstPaint?: number;
	/** 8.9: transport and paint — the one stage of 8.8 this surface owns. */
	firstByteToFirstPaint?: number;
};

/** Absent marks yield absent measures — never zero, never invented. */
export function measures(marks: TurnMarks): TurnMeasures {
	if (marks.firstPaint === undefined || marks.firstByte === undefined) return {};
	return {
		submitToFirstPaint: marks.firstPaint - marks.submit,
		firstByteToFirstPaint: marks.firstPaint - marks.firstByte
	};
}
