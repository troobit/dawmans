<!--
	The answer renderer (requirements 3.11, §4; design "Streaming without
	reflow"). Presentation only: it consumes the reducer's blocks and envelope
	and fetches nothing. Blocks render in arrival order and only ever extend —
	the parser fixed each block's type at its first line, so nothing here
	re-types or re-flows painted text (4.2, Decision 2).

	The measure (4.11) and instruction-first layout (4.10, 11.7) are built
	toward here; their bands are verified by the iterative loop's stand-back
	tests, recorded in decision_log.md when hit.
-->
<script lang="ts">
	import type { InlineSpan } from '../engine/blocks';
	import type { Turn } from '../engine/turn.svelte';
	import { passages as defaultPassages, type PassageStore } from '../state/passages.svelte';
	import { scope as defaultScope, type ScopeStore } from '../state/scope.svelte';
	import type { ThreadStore } from '../state/thread.svelte';
	import CitationList from './CitationList.svelte';

	let {
		turn,
		thread = null,
		scope = defaultScope,
		passages = defaultPassages
	}: {
		turn: Turn;
		thread?: ThreadStore | null;
		scope?: ScopeStore;
		passages?: PassageStore;
	} = $props();

	/** A contributing source's display name, resolved through the turn's citations (4.7). */
	function sourceName(sourceId: string): string {
		for (const citation of turn.citations.values()) {
			if (citation.source_id === sourceId) return citation.display_name;
		}
		return sourceId;
	}

	/**
	 * 4.9: re-ask the uncovered part alone, widening scope to the sources the
	 * engine named for it. The widening goes through the scope store, so it
	 * persists like any other scope change and decays per session (7.9); the
	 * answered part stays on screen because the re-ask is a new turn.
	 */
	function reAsk(part: string): void {
		for (const ref of turn.envelope.suggested_sources ?? []) {
			if (!scope.isSelected(ref.source_id)) scope.toggle(ref.source_id);
		}
		thread?.submit(part);
	}
</script>

{#snippet spans(list: readonly InlineSpan[])}
	{#each list as span, index (index)}
		{#if span.kind === 'text'}{span.text}{:else if span.kind === 'key'}<kbd>{span.text}</kbd>{:else}<sup
				class="marker">{span.index}</sup
			>{/if}
	{/each}
{/snippet}

<div class="answer">
	{#if turn.envelope.scope_dropped !== undefined}
		<!-- 3.11: the engine's prune, reported with this turn — never the user's own narrowing. -->
		<p class="scope-dropped">
			The corpus no longer holds
			{turn.envelope.scope_dropped.map((ref) => ref.display_name).join(', ')} — the engine left
			{turn.envelope.scope_dropped.length === 1 ? 'it' : 'them'} out of this question's scope.
		</p>
	{/if}

	{#if turn.envelope.direct_answer !== undefined}
		<!-- 4.3: the actionable answer first, before detail and citations. -->
		<p class="direct">{turn.envelope.direct_answer}</p>
	{/if}

	{#each turn.blocks as block, index (index)}
		{#if block.type === 'heading'}
			<h3 class="heading">{@render spans(block.spans)}</h3>
		{:else if block.type === 'ordered-step'}
			<!-- 4.5: each step a separately identifiable block. -->
			<p class="step"><span class="step-number">{block.number}.</span> {@render spans(block.spans)}</p>
		{:else if block.type === 'bullet'}
			<p class="bullet">{@render spans(block.spans)}</p>
		{:else if block.type === 'caveat'}
			<!-- 4.4: in reading position, visually distinct, never behind a disclosure. -->
			<p class="caveat"><strong class="caveat-label">Caveat</strong> {@render spans(block.spans)}</p>
		{:else if block.type === 'conflict'}
			<!-- 4.4: both readings with their separate citations, neither chosen. -->
			<div class="conflict">
				<p class="conflict-statement">
					<strong class="conflict-label">Sources conflict</strong>
					{@render spans(block.spans)}
				</p>
				{#each block.readings as reading, readingIndex (readingIndex)}
					<p class="reading">{@render spans(reading.spans)}</p>
				{/each}
			</div>
		{:else}
			<p class="paragraph">{@render spans(block.spans)}</p>
		{/if}
	{/each}

	{#if turn.envelope.uncovered_parts !== undefined}
		<!-- 4.8: subordinate to the answer, never a refusal or a failure. -->
		<div class="uncovered">
			<p class="uncovered-lead">The selected sources did not cover:</p>
			<ul>
				{#each turn.envelope.uncovered_parts as part (part)}
					<li>
						<span>{part}</span>
						{#if thread !== null}
							<button type="button" onclick={() => reAsk(part)}>Re-ask: {part}</button>
						{/if}
					</li>
				{/each}
			</ul>
		</div>
	{/if}

	{#if turn.envelope.contributing_sources !== undefined}
		<!-- 4.7: the sources that actually supplied passages, named distinctly. -->
		<p class="contributing">
			Answered from {turn.envelope.contributing_sources.map(sourceName).join(', ')}.
		</p>
	{/if}

	<CitationList {turn} {passages} />
</div>

<style>
	.answer {
		display: flex;
		flex-direction: column;
		gap: var(--space-s, 0.5rem);
		/* 4.11: a comfortable measure, converged on by the stand-back loop. */
		max-width: 70ch;
	}

	.answer p,
	.answer h3 {
		margin: 0;
		color: var(--colour-text); /* spelling-ignore */
		font-size: var(--font-size-body);
	}

	.direct {
		font-weight: 600;
	}

	.heading {
		font-size: var(--font-size-heading);
		font-weight: 600;
	}

	.paragraph,
	.reading {
		white-space: pre-line;
	}

	.step {
		padding-inline-start: 0.5em;
	}

	.step-number {
		font-weight: 600;
	}

	.bullet {
		padding-inline-start: 1em;
	}

	.bullet::before {
		content: '– ';
	}

	.caveat {
		border-inline-start: 3px solid var(--colour-state-caveat);
		padding-inline-start: 0.75em;
	}

	.conflict {
		border-inline-start: 3px solid var(--colour-state-caveat);
		padding-inline-start: 0.75em;
		display: flex;
		flex-direction: column;
		gap: var(--space-s, 0.5rem);
	}

	.reading {
		padding-inline-start: 1em;
	}

	.caveat-label,
	.conflict-label {
		/* 11.6: the word is the channel that survives greyscale. */
		color: var(--colour-state-caveat); /* spelling-ignore */
	}

	kbd {
		/* 4.12: a discrete key-styled element, never smaller than body text. */
		font-size: var(--font-size-body);
		border: 1px solid var(--colour-text-secondary);
		border-radius: 3px;
		padding: 0 0.35em;
	}

	.marker {
		/* 5.17: no more visual weight than the body text it sits beside. */
		font-size: var(--font-size-secondary);
		color: var(--colour-accent); /* spelling-ignore */
	}

	.scope-dropped,
	.contributing {
		color: var(--colour-text-secondary); /* spelling-ignore */
		font-size: var(--font-size-control);
	}

	.uncovered {
		border-inline-start: 3px solid var(--colour-text-secondary);
		padding-inline-start: 0.75em;
	}

	.uncovered-lead {
		color: var(--colour-text-secondary); /* spelling-ignore */
		font-size: var(--font-size-control);
	}

	.uncovered ul {
		list-style: none;
		margin: 0;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: var(--space-s, 0.25rem);
	}

	.uncovered button {
		background: var(--colour-surface);
		color: var(--colour-text); /* spelling-ignore */
		font-size: var(--font-size-control);
		border: 1px solid var(--colour-text-secondary);
		border-radius: 4px;
		padding: 0.15em 0.6em;
		margin-inline-start: 0.5em;
	}

	.uncovered button:focus-visible {
		outline: 2px solid var(--colour-focus-ring);
		outline-offset: 1px;
	}
</style>
