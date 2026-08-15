<!--
	The history panel (requirements 12.2–12.8; design "History"): a region off
	the ask surface, mounted only while open, over the history store. Selecting
	an entry re-displays the stored answer and its citation records — nothing is
	fetched to re-display (12.3); passage text is refetched only on an explicit
	expansion, as anywhere else. Re-ask starts a new conversation against the
	current scope (12.5); clear-all sits behind a confirmation step (12.6).
-->
<script lang="ts">
	import { keys, type KeyRouter, type Focusable } from '../keys';
	import {
		history as defaultHistory,
		type HistoryEntry,
		type HistoryStore
	} from '../state/history.svelte';
	import { thread as defaultThread, type ThreadStore } from '../state/thread.svelte';
	import CitationEntry from './CitationEntry.svelte';
	import type { SourcesLike } from './CoverageFailureView.svelte';

	let {
		history = defaultHistory,
		thread = defaultThread,
		sources = undefined,
		router = keys,
		opener = null,
		onclose = undefined
	}: {
		history?: HistoryStore;
		thread?: ThreadStore;
		sources?: SourcesLike | undefined;
		router?: KeyRouter;
		opener?: Focusable | null;
		onclose?: (() => void) | undefined;
	} = $props();

	// `$state.raw`: a plain `$state` would proxy the assigned entry, and the
	// identity comparison against the store's own object would never match.
	let selected = $state.raw<HistoryEntry | null>(null);
	let confirmingClear = $state(false);

	// 12.8/13.3: while mounted the panel is a dismissible region on the Escape
	// stack, one activation out, focus returned to whatever opened it.
	$effect(() => {
		return router.registerRegion({
			dismiss: () => onclose?.(),
			opener
		});
	});

	/** 12.5: a new conversation — never a follow-up — against the current scope. */
	function reAsk(entry: HistoryEntry): void {
		thread.clear();
		thread.submit(entry.question);
		onclose?.();
	}

	function confirmClear(): void {
		history.clear();
		confirmingClear = false;
		selected = null;
	}

	/** 12.4: names where the engine still reports the source, the id where it does not. */
	function scopeNames(entry: HistoryEntry): string {
		return entry.scopeAtAsk.map((id) => sources?.displayName(id) ?? id).join(', ');
	}

	/** The stored body, without the inline citation markers prose carries (§4d). */
	function bodyText(entry: HistoryEntry): string {
		return (entry.envelope.body ?? '').replace(/\[\[p:[^\]]+\]\]/g, '').trim();
	}
</script>

<section class="history" aria-label="History">
	<header>
		<h2>History</h2>
		<button type="button" onclick={() => onclose?.()}>Close</button>
		{#if history.entries.length > 0}
			{#if confirmingClear}
				<!-- 12.6: one action, behind this confirmation step. -->
				<span class="confirm">Delete all {history.entries.length} retained exchanges?</span>
				<button type="button" onclick={confirmClear}>Delete all</button>
				<button
					type="button"
					onclick={() => {
						confirmingClear = false;
					}}
				>
					Keep
				</button>
			{:else}
				<button
					type="button"
					onclick={() => {
						confirmingClear = true;
					}}
				>
					Clear history
				</button>
			{/if}
		{/if}
	</header>

	{#if history.entries.length === 0}
		<p class="empty">Nothing retained yet — answered questions appear here.</p>
	{:else}
		<ul class="entries">
			{#each history.entries as entry (`${entry.askedAt}:${entry.question}`)}
				<li class="entry">
					<button
						type="button"
						class="select"
						aria-expanded={selected === entry}
						onclick={() => {
							selected = selected === entry ? null : entry;
						}}
					>
						{entry.question}
					</button>
					<time datetime={new Date(entry.askedAt).toISOString()}>
						{new Date(entry.askedAt).toLocaleString()}
					</time>
					{#if entry.incomplete}
						<!-- 12.7: never presented as a finished answer. -->
						<span class="incomplete">incomplete</span>
					{/if}

					{#if selected === entry}
						<div class="detail">
							<p class="scope">Scope at ask: {scopeNames(entry)}</p>
							{#if entry.envelope.direct_answer !== undefined}
								<p class="direct">{entry.envelope.direct_answer}</p>
							{/if}
							{#if bodyText(entry) !== ''}
								<p class="body">{bodyText(entry)}</p>
							{/if}
							{#if entry.citations.length > 0}
								<ol class="citations">
									{#each entry.citations as citation, index (citation.passage_id)}
										<CitationEntry number={index + 1} {citation} />
									{/each}
								</ol>
							{/if}
							<button type="button" onclick={() => reAsk(entry)}>
								Re-ask against the current scope
							</button>
						</div>
					{/if}
				</li>
			{/each}
		</ul>
	{/if}
</section>

<style>
	.history {
		display: flex;
		flex-direction: column;
		gap: var(--space-s, 0.5rem);
	}

	header {
		display: flex;
		align-items: baseline;
		gap: var(--space-s, 0.5rem);
	}

	h2 {
		margin: 0;
		font-size: var(--font-size-body);
		color: var(--colour-text); /* spelling-ignore */
	}

	.confirm,
	.empty,
	.scope {
		margin: 0;
		font-size: var(--font-size-control);
		color: var(--colour-text-secondary); /* spelling-ignore */
	}

	.entries {
		list-style: none;
		margin: 0;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: var(--space-s, 0.5rem);
	}

	.entry {
		display: flex;
		flex-wrap: wrap;
		align-items: baseline;
		gap: var(--space-s, 0.5rem);
	}

	.select {
		background: none;
		border: none;
		padding: 0;
		color: var(--colour-text); /* spelling-ignore */
		font-size: var(--font-size-control);
		text-align: left;
		cursor: pointer;
	}

	time,
	.incomplete {
		color: var(--colour-text-secondary); /* spelling-ignore */
		font-size: var(--font-size-secondary);
	}

	.detail {
		flex-basis: 100%;
		display: flex;
		flex-direction: column;
		gap: var(--space-s, 0.5rem);
	}

	.direct {
		margin: 0;
		font-weight: 600;
		font-size: var(--font-size-control);
		color: var(--colour-text); /* spelling-ignore */
	}

	.body {
		margin: 0;
		font-size: var(--font-size-control);
		color: var(--colour-text); /* spelling-ignore */
	}

	.citations {
		list-style: none;
		margin: 0;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: var(--space-s, 0.5rem);
	}

	button:not(.select) {
		background: var(--colour-surface);
		color: var(--colour-text); /* spelling-ignore */
		font-size: var(--font-size-control);
		border: 1px solid var(--colour-text-secondary);
		border-radius: 4px;
		padding: 0.25em 0.75em;
	}

	button:focus-visible {
		outline: 2px solid var(--colour-focus-ring);
		outline-offset: 1px;
	}
</style>
