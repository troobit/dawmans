// The pictogram set and the rule that picks one for a source (requirements
// 2.14, 11.6, 11.7). Line art in a 24-unit box, expressed as path data so a
// pictogram is data rather than markup and the mapping below can be unit
// tested without rendering.
//
// A pictogram is **never** a channel of its own: every one is rendered
// `aria-hidden` beside the words it illustrates, so 11.6's greyscale reading
// and 13.4's accessible names both come from the text, not the picture. The
// picture is there to be recognised from across the room before the words are
// read at all.

import type { SourceRecord } from '../engine/records';

export const PICTOGRAM_PATHS = {
	/** A speaker with the sound struck out — "no sound". */
	'no-sound': ['M4 9.5h3.5L12 5.5v13L7.5 14.5H4z', 'M16 9.5l5 5', 'M21 9.5l-5 5'],
	/** A wave whose peaks are flattened against a ceiling — clipping. */
	distortion: ['M2 19h3V6h4v13h4V6h4v13h3', 'M2 6h20'],
	/** A clock — the wait between playing and hearing. */
	latency: ['M12 3a9 9 0 1 0 0 18a9 9 0 1 0 0-18', 'M12 7v5l3.5 2.5'],
	/** A drum with sticks. */
	drum: [
		'M4 9c0 1.7 3.6 3 8 3s8-1.3 8-3s-3.6-3-8-3s-8 1.3-8 3z',
		'M4 9v6c0 1.7 3.6 3 8 3s8-1.3 8-3V9',
		'M6 4l4 3',
		'M18 4l-4 3'
	],
	/** Three faders — a DAW. */
	daw: ['M6 4v16', 'M12 4v16', 'M18 4v16', 'M3.5 9h5', 'M9.5 14h5', 'M15.5 7h5'],
	/** A keyboard — controllers and synths. */
	keys: ['M3 6h18v12H3z', 'M7.5 12v6', 'M12 12v6', 'M16.5 12v6', 'M9.75 6v6', 'M14.25 6v6'],
	/** A box with a knob and a jack — an audio interface. */
	interface: [
		'M3 6h18v12H3z',
		'M8 9.5a2.5 2.5 0 1 0 0 5a2.5 2.5 0 1 0 0-5',
		'M8 12V9.75',
		'M16 9.5a2.5 2.5 0 1 0 0 5a2.5 2.5 0 1 0 0-5'
	],
	/** A ruled notebook — the studio owner's own triage entries. */
	notes: ['M6 3h12v18H6z', 'M9 3v18', 'M11 8h5', 'M11 12h5', 'M11 16h3'],
	/** An open book — any manual the table below does not recognise. */
	book: [
		'M12 7v13',
		'M12 7C10 5.5 7.5 5 4 5v13c3.5 0 6 .5 8 2',
		'M12 7c2-1.5 4.5-2 8-2v13c-3.5 0-6 .5-8 2'
	],
	/** A clock turning back — asked before. */
	history: ['M12 3a9 9 0 1 1-8.5 12', 'M3 8v4h4', 'M12 8v4.5l3 2'],
	/** Sliders — configuration. */
	settings: ['M4 7h10', 'M18 7h2', 'M4 17h4', 'M12 17h8', 'M16 5v4', 'M10 15v4']
} as const;

export type PictogramName = keyof typeof PICTOGRAM_PATHS;

/**
 * Which pictogram a symptom shortcut wears (1.10). Keyed on the shortcut text
 * itself so the fixed set in `AskSurface` stays the one place the questions are
 * written down.
 */
export const SHORTCUT_PICTOGRAMS: Record<string, PictogramName> = {
	'no sound': 'no-sound',
	distorting: 'distortion',
	latency: 'latency',
	'wrong drum sound': 'drum'
};

/**
 * Presentation-only recognition of what a manual describes, in first-match
 * order: `apc-key-25` is a keyboard before it is anything else, `nitro-max` is
 * a drum kit, `scarlett-solo` an interface. The table is a convenience over
 * words the engine already reports — it decides no behaviour, and an
 * unrecognised source gets the neutral book rather than a wrong picture.
 */
const MANUAL_PICTOGRAMS: [terms: readonly string[], name: PictogramName][] = [
	[['ableton', 'live', 'logic', 'cubase', 'bitwig', 'reaper', 'daw', 'studio one', 'fl studio'], 'daw'],
	[['key', 'synth', 'piano', 'controller', 'apc', 'launchpad', 'midi'], 'keys'],
	[['drum', 'nitro', 'kit', 'pad', 'td-', 'spd', 'percussion'], 'drum'],
	[['interface', 'focusrite', 'scarlett', 'clarett', 'solo', 'preamp', 'mixer', 'audio'], 'interface']
];

/** The pictogram for a source entry (2.12: the authored store is not a manual). */
export function pictogramFor(record: SourceRecord): PictogramName {
	if (record.kind === 'authored-triage') return 'notes';
	const haystack = `${record.vendor} ${record.product} ${record.display_name}`.toLowerCase();
	for (const [terms, name] of MANUAL_PICTOGRAMS) {
		if (terms.some((term) => haystack.includes(term))) return name;
	}
	return 'book';
}
