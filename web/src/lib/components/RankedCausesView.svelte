<!--
	The ranked-causes renderer (requirements 6.6, 5.16; CONTRACTS §4c; design
	"Narrowing and ranked causes"). Causes render in array order with each rank
	shown — findings to read, never the digit-armed controls of a narrowing
	question; that affordance split is the only thing keeping the two
	candidate-bearing shapes apart. The rank-1 cause's check arrives as
	`direct_answer` and paints first (4.3), which is what keeps 4.10 and 11.7
	reachable; the cause itself is never promoted to an answer.

	`cites[]` and `fix_cites[]` resolve through the turn's one citation map by
	passage_id — the shared numbering of citation-order.ts, so a cause's marker
	and the list entry below can never disagree. A cause whose `fix_cites[]` is
	empty carries the `unbacked` mark rather than simply appearing without a
	fix (5.16); the fix citation renders as an ordinary citation in the shared
	list, distinct from the authored cause it belongs to (5.14).
-->
<script lang="ts">
	import type { Turn } from '../engine/turn.svelte';
	import { passages as defaultPassages, type PassageStore } from '../state/passages.svelte';
	import { numberedCitations } from './citation-order';
	import CitationList from './CitationList.svelte';

	let {
		turn,
		passages = defaultPassages
	}: { turn: Turn; passages?: PassageStore } = $props();

	const numbers = $derived(
		new Map(numberedCitations(turn).map((entry) => [entry.citation.passage_id, entry.number]))
	);
</script>

{#snippet markers(ids: readonly string[])}
	{#each ids as id (id)}
		{#if numbers.has(id)}<sup class="marker">{numbers.get(id)}</sup>{/if}
	{/each}
{/snippet}

<div class="ranked-causes" role="group" aria-label="Ranked causes">
	{#if turn.envelope.direct_answer !== undefined}
		<!-- 4.3: the rank-1 check as an instruction, first — never the cause asserted. -->
		<p class="direct">{turn.envelope.direct_answer}</p>
	{/if}

	<ol class="causes">
		{#each turn.envelope.causes ?? [] as cause (cause.rank)}
			<li class="cause">
				<p class="statement">
					<span class="rank">{cause.rank}.</span>
					{cause.statement}{@render markers(cause.cites)}
				</p>
				<p class="check">Check: {cause.check}</p>
				{#if cause.fix_cites.length > 0}
					<p class="fix">Fix{@render markers(cause.fix_cites)}</p>
				{:else}
					<!-- 5.16: a missing fix is marked, never silently absent. -->
					<p class="unbacked">no manual behind this</p>
				{/if}
			</li>
		{/each}
	</ol>

	<CitationList {turn} {passages} />
</div>

<style>
	.ranked-causes {
		display: flex;
		flex-direction: column;
		gap: var(--space-s, 0.5rem);
	}

	.direct {
		color: var(--colour-text); /* spelling-ignore */
		font-size: var(--font-size-body);
		font-weight: 600;
		margin: 0;
	}

	.causes {
		list-style: none;
		margin: 0;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: var(--space-s, 0.5rem);
	}

	.cause {
		display: flex;
		flex-direction: column;
		gap: 0.15em;
	}

	.cause p {
		margin: 0;
		color: var(--colour-text); /* spelling-ignore */
		font-size: var(--font-size-body);
	}

	.rank {
		font-weight: 600;
	}

	.check,
	.fix {
		padding-inline-start: 1.25em;
	}

	.unbacked {
		/* 11.6: the words are the channel that survives greyscale. */
		align-self: start;
		margin-inline-start: 1.25em;
		color: var(--colour-text-secondary); /* spelling-ignore */
		font-size: var(--font-size-secondary);
		border: 1px solid var(--colour-text-secondary);
		border-radius: 3px;
		padding: 0 0.35em;
	}

	.marker {
		/* 5.17: no more visual weight than the text it sits beside. */
		font-size: var(--font-size-secondary);
		color: var(--colour-accent); /* spelling-ignore */
	}
</style>
