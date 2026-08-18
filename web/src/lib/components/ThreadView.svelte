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
	import type { ProviderClass } from '../state/perf.svelte';
	import { scope as defaultScope, type ScopeStore } from '../state/scope.svelte';
	import { thread as defaultThread, type ThreadStore } from '../state/thread.svelte';
	import AnswerView from './AnswerView.svelte';
	import CoverageFailureView, { type SourcesLike } from './CoverageFailureView.svelte';
	import DiagnosticsDisclosure from './DiagnosticsDisclosure.svelte';
	import ErrorView from './ErrorView.svelte';
	import NarrowingView from './NarrowingView.svelte';
	import RankedCausesView from './RankedCausesView.svelte';
	import WorkingIndicator from './WorkingIndicator.svelte';

	let {
		thread = defaultThread,
		scope = defaultScope,
		router = undefined,
		sources = undefined,
		providerClass = 'hosted',
		reducedMotion = undefined,
		providerName = null,
		onconfigure = undefined
	}: {
		thread?: ThreadStore;
		scope?: ScopeStore;
		router?: KeyRouter;
		sources?: SourcesLike;
		providerClass?: ProviderClass;
		reducedMotion?: boolean;
		providerName?: string | null;
		onconfigure?: (() => void) | undefined;
	} = $props();

	/** The states §9 routes to ErrorView, including a failed turn with no outcome (9.15, 9.19). */
	function isErrorFamily(turn: Turn): boolean {
		return (
			turn.renderer === 'error' ||
			turn.renderer === 'broken' ||
			turn.renderer === 'empty-scope' ||
			(turn.state === 'failed' && turn.renderer === null)
		);
	}

	/** 9.3: the disclosure exists on every error state and on `framing: unparsed`. */
	function hasDiagnostics(turn: Turn): boolean {
		return (
			turn.state === 'failed' ||
			turn.renderer === 'error' ||
			turn.renderer === 'broken' ||
			turn.envelope.framing === 'unparsed'
		);
	}

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

	/**
	 * The shape channel beside the label — 8.4's second independent channel,
	 * distinct per state and never colour alone. Static: the only animation
	 * beside arriving text belongs to the working indicator (11.9).
	 */
	function stateShape(turn: Turn): string {
		if (turn.state === 'acknowledged' || turn.state === 'streaming') return '●';
		if (turn.envelope.outcome === 'cancelled') return turn.userCancelled ? '■' : '□';
		if (turn.state === 'failed') {
			return turn.envelope.outcome === 'incomplete' ? '◗' : '✕';
		}
		return '✓';
	}

	// 13.5: one polite region announcing each state transition once — never
	// the streamed fragments, never the reduced-motion counter's ticks.
	let announcement = $state('');
	const announcedFlags = new WeakMap<Turn, { streaming: boolean; terminal: boolean }>();

	function terminalAnnouncement(turn: Turn): string {
		if (turn.envelope.outcome === 'cancelled') return '';
		if (turn.state === 'failed') return 'Answer failed.';
		switch (turn.renderer) {
			case 'narrowing': {
				const narrowing = turn.envelope.narrowing;
				if (narrowing === undefined) return 'The question needs narrowing.';
				const candidates = narrowing.candidates
					.map((candidate, index) => `${index + 1}: ${candidate.label}`)
					.join(', ');
				return `Needs narrowing — ${narrowing.question} Candidates: ${candidates}. Press a number key to select one.`;
			}
			case 'coverage-failure':
				return 'The sources in scope do not cover this question.';
			case 'empty-scope':
				return 'No sources are selected.';
			case 'error':
			case 'broken':
				return 'Answer failed.';
			default:
				return turn.envelope.outcome === 'partially-answered'
					? 'Answer finished, partially — parts were not covered.'
					: 'Answer finished.';
		}
	}

	$effect(() => {
		const turn = thread.turns.at(-1);
		if (turn === undefined) return;
		let flags = announcedFlags.get(turn);
		if (flags === undefined) {
			flags = { streaming: false, terminal: false };
			announcedFlags.set(turn, flags);
		}
		if (turn.state === 'streaming' && !flags.streaming) {
			flags.streaming = true;
			announcement = 'Answer streaming.';
		}
		if ((turn.state === 'settled' || turn.state === 'failed') && !flags.terminal) {
			flags.terminal = true;
			announcement = terminalAnnouncement(turn);
		}
	});

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
				<span class="state-shape" data-state={stateLabel(turn)} aria-hidden="true"
					>{stateShape(turn)}</span
				>
				<span class="state">{stateLabel(turn)}</span>
			</header>
			{#if turn.envelope.scope_dropped !== undefined && turn.envelope.outcome !== 'unknown-source-id'}
				<!-- 3.11: the engine's prune, reported with the turn whatever its outcome —
				     CONTRACTS §4 places `scope_dropped` before `outcome`, so it can accompany
				     narrowing, coverage failure or an error just as well as an answer. The
				     `unknown-source-id` turn is excluded: there the field carries the rejected
				     ids and ErrorView renders the 9.11 wording instead. -->
				<p class="scope-dropped">
					The corpus no longer holds
					{turn.envelope.scope_dropped.map((ref) => ref.display_name).join(', ')} — the engine left
					{turn.envelope.scope_dropped.length === 1 ? 'it' : 'them'} out of this question's scope.
				</p>
			{/if}
			{#if isErrorFamily(turn)}
				<ErrorView
					{turn}
					{thread}
					{scope}
					{providerName}
					{onconfigure}
					failure={thread.failureOf(turn)}
				/>
			{:else if turn.renderer === 'answer' || turn.renderer === null || turn.renderer === 'cancelled'}
				<!-- `cancelled` retains whatever arrived (8.6, 9.16); the notes below mark it. -->
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

			{#if turn.incomplete && !isErrorFamily(turn)}
				<!-- 9.14: retained, marked, never presented as finished; retry offered. -->
				<p class="incomplete-note">
					<span>This answer is incomplete — it stopped before finishing.</span>
					<button type="button" onclick={() => thread.submit(turn.question)}>Retry</button>
				</p>
			{/if}

			{#if turn.envelope.outcome === 'cancelled' && !turn.userCancelled}
				<!-- 9.16: abandoned, distinct from incomplete and from an error. -->
				<p class="abandoned-note">Abandoned — a newer question replaced this turn.</p>
			{/if}

			{#if hasDiagnostics(turn)}
				<DiagnosticsDisclosure {turn} />
			{/if}
		</article>
	{/each}

	<!-- Below the thread, never above: its removal cannot shift text (Decision 2). -->
	<WorkingIndicator {thread} {providerClass} {reducedMotion} />

	<!-- 13.5: state transitions only; the streamed body is aria-live off. -->
	<p class="announcer" role="status" aria-live="polite">{announcement}</p>
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

	/* 11.6: the glyph is a channel that survives greyscale; colour rides along. */
	.state-shape {
		font-size: var(--font-size-secondary);
		color: var(--colour-state-working); /* spelling-ignore */
	}

	.state-shape[data-state='finished'] {
		color: var(--colour-state-finished); /* spelling-ignore */
	}

	.state-shape[data-state='broken'],
	.state-shape[data-state='incomplete'] {
		color: var(--colour-state-broken); /* spelling-ignore */
	}

	.state-shape[data-state='stopped'],
	.state-shape[data-state='abandoned'] {
		color: var(--colour-text-secondary); /* spelling-ignore */
	}

	.scope-dropped,
	.incomplete-note,
	.abandoned-note {
		margin: 0;
		color: var(--colour-text-secondary); /* spelling-ignore */
		font-size: var(--font-size-control);
	}

	.incomplete-note button {
		background: var(--colour-surface);
		color: var(--colour-text); /* spelling-ignore */
		font-size: var(--font-size-control);
		border: 1px solid var(--colour-text-secondary);
		border-radius: 4px;
		padding: 0.15em 0.6em;
		margin-inline-start: 0.5em;
	}

	.incomplete-note button:focus-visible {
		outline: 2px solid var(--colour-focus-ring);
		outline-offset: 1px;
	}

	.announcer {
		/* Visually hidden, present to assistive technology (13.5). */
		position: absolute;
		width: 1px;
		height: 1px;
		overflow: hidden;
		clip-path: inset(50%);
		white-space: nowrap;
		margin: 0;
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
