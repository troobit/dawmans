// The one numbering for a turn's citations (Decision 3): a passage's printed
// integer is its position in marker first-appearance order, and a citation
// resolved only through `causes[]` — never by a prose marker — numbers on
// after the marked entries. Shared by the citation list and the ranked-causes
// renderer so the two can never disagree about a number (CONTRACTS §4c: one
// citation channel, resolved by passage_id).

import type { Citation } from '../engine/records';
import type { Turn } from '../engine/turn.svelte';

export type NumberedCitation = { number: number; citation: Citation };

/** Every arrived citation with its stable printed number, in number order. */
export function numberedCitations(turn: Turn): NumberedCitation[] {
	const list: NumberedCitation[] = [];
	turn.markers.forEach((passageId, index) => {
		const citation = turn.citations.get(passageId);
		if (citation !== undefined) list.push({ number: index + 1, citation });
	});
	let next = turn.markers.length;
	for (const [passageId, citation] of turn.citations) {
		if (!turn.markers.includes(passageId)) {
			next += 1;
			list.push({ number: next, citation });
		}
	}
	return list;
}
