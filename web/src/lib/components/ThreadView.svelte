<!--
	The thread shell: turns oldest first, each holding its question in an
	inspectable, re-editable form (1.4) and whatever the engine has said so
	far. A turn whose outcome selected the answer renderer — or whose outcome
	has not arrived yet — renders through AnswerView; the remaining renderer
	families (§6, §7, §9) keep the plain-text placeholder until their phases.
	Presentation only — no fetching, no persistence.
-->
<script lang="ts">
	import type { Block, InlineSpan } from '../engine/blocks';
	import type { Turn } from '../engine/turn.svelte';
	import type { KeyRouter } from '../keys';
	import { scope as defaultScope, type ScopeStore } from '../state/scope.svelte';
	import { thread as defaultThread, type ThreadStore } from '../state/thread.svelte';
	import AnswerView from './AnswerView.svelte';
	import CoverageFailureView, { type SourcesLike } from './CoverageFailureView.svelte';
	import NarrowingView from './NarrowingView.svelte';
	import RankedCausesView from './RankedCausesView.svelte';

	let {
		thread = defaultThread,
		scope = defaultScope,
		router = undefined,
		sources = undefined
	}: {
		thread?: ThreadStore;
		scope?: ScopeStore;
		router?: KeyRouter;
		sources?: SourcesLike;
	} = $props();

	/** Working / finished / broken as text — one of 8.4's two channels. */
	function stateLabel(turn: Turn): string {
		if (turn.state === 'acknowledged' || turn.state === 'streaming') return 'working…';
		if (turn.envelope.outcome === 'cancelled') {
			// 8.6 versus 9.16: the client knows who cancelled.
			return turn.userCancelled ? 'stopped' : 'abandoned';
		}
		if (turn.state === 'failed') {
			return turn.envelope.outcome === 'incomplete' ? 'incomplete' : 'broken';
		}
		return 'finished';
	}

	function spanText(spans: readonly InlineSpan[]): string {
		return spans
			.map((span) => (span.kind === 'marker' ? String(span.index) : span.text))
			.join('');
	}

	/** Placeholder flattening; the block renderer of task 24 replaces it. */
	function blockText(block: Block): string {
		if (block.type === 'conflict') {
			return [spanText(block.spans), ...block.readings.map((reading) => spanText(reading.spans))]
				.filter((text) => text !== '')
				.join(' — ');
		}
		return spanText(block.spans);
	}
</script>

<section class="thread" aria-label="Conversation">
	{#each thread.turns as turn (turn)}
		<article class="turn">
			<header>
				<!-- 1.4: the submitted text stays inspectable; activating it re-edits. -->
				<button
					type="button"
					class="question"
					title="Edit this question"
					onclick={() => {
						thread.draft = turn.question;
					}}
				>
					{turn.question}
				</button>
				<span class="state">{stateLabel(turn)}</span>
			</header>
			{#if turn.renderer === 'answer' || turn.renderer === null}
				<AnswerView {turn} {thread} {scope} />
			{:else if turn.renderer === 'narrowing'}
				<NarrowingView {turn} {thread} {router} />
			{:else if turn.renderer === 'ranked-causes'}
				<RankedCausesView {turn} />
			{:else if turn.renderer === 'coverage-failure'}
				<CoverageFailureView {turn} {thread} {scope} {sources} />
			{:else}
				{#if turn.envelope.direct_answer !== undefined}
					<p class="direct">{turn.envelope.direct_answer}</p>
				{/if}
				{#each turn.blocks as block, index (index)}
					<p class="block">{blockText(block)}</p>
				{/each}
			{/if}
		</article>
	{/each}
</section>

<style>
	.thread {
		display: flex;
		flex-direction: column;
		gap: var(--space-m, 1rem);
	}

	.turn {
		display: flex;
		flex-direction: column;
		gap: var(--space-s, 0.5rem);
	}

	header {
		display: flex;
		align-items: baseline;
		gap: var(--space-s, 0.5rem);
	}

	.question {
		background: none;
		border: none;
		padding: 0;
		color: var(--colour-text-secondary); /* spelling-ignore */
		font-size: var(--font-size-body);
		text-align: left;
		cursor: pointer;
	}

	.question:focus-visible {
		outline: 2px solid var(--colour-focus-ring);
		outline-offset: 1px;
	}

	.state {
		color: var(--colour-text-secondary); /* spelling-ignore */
		font-size: var(--font-size-secondary);
	}

	.direct {
		color: var(--colour-text); /* spelling-ignore */
		font-size: var(--font-size-body);
		font-weight: 600;
		margin: 0;
	}

	.block {
		color: var(--colour-text); /* spelling-ignore */
		font-size: var(--font-size-body);
		margin: 0;
	}
</style>
