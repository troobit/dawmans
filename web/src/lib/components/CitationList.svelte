<!--
	The citation list below the answer (design "Citations"; Decision 3): one
	entry per marker integer in first-appearance order, each carrying every §3
	rendering obligation. A citation resolved only through `causes[]` — never
	by a prose marker — lists after the marked entries, numbered on. An entry
	appears once its citation record arrives; the prose marker was already
	painted at its stable integer, so late arrival moves nothing (4.2).
-->
<script lang="ts">
	import type { Turn } from '../engine/turn.svelte';
	import { passages as defaultPassages, type PassageStore } from '../state/passages.svelte';
	import { numberedCitations } from './citation-order';
	import CitationEntry from './CitationEntry.svelte';

	let {
		turn,
		passages = defaultPassages
	}: { turn: Turn; passages?: PassageStore } = $props();

	const entries = $derived(numberedCitations(turn));
</script>

{#if entries.length > 0 || turn.uncited || turn.envelope.ungrounded === true}
	<section class="citations" aria-label="Citations">
		{#if turn.uncited}
			<!-- 5.12: a settled answer with no citations is never presented as grounded. -->
			<p class="uncited">Uncited — no citation backs this answer.</p>
		{/if}
		{#if turn.envelope.ungrounded === true}
			<!-- 5.13: marks the text already on screen; never withholds or blanks it. -->
			<p class="ungrounded">Unverified — at least one claim has no resolvable citation.</p>
		{/if}
		{#if entries.length > 0}
			<ol class="citation-list">
				{#each entries as entry (entry.citation.passage_id)}
					<CitationEntry number={entry.number} citation={entry.citation} {passages} />
				{/each}
			</ol>
		{/if}
	</section>
{/if}

<style>
	.citations {
		display: flex;
		flex-direction: column;
		gap: var(--space-s, 0.5rem);
		border-block-start: 1px solid var(--colour-surface);
		padding-block-start: var(--space-s, 0.5rem);
	}

	.citation-list {
		list-style: none;
		margin: 0;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: var(--space-s, 0.5rem);
	}

	.uncited,
	.ungrounded {
		margin: 0;
		color: var(--colour-text-secondary); /* spelling-ignore */
		font-size: var(--font-size-control);
	}
</style>
