<!--
	The one surface (design "Surfaces"; requirements 2.11, 11.8, 12.8): scope
	bar, thread, ask input, with the picker, history, provider configuration and
	expanded passages as regions of the page, not routes — navigation would
	discard the typed question and the scope, which 10.2 and 10.11 forbid.
	Wiring of already-tested components; the page's own contributions are the
	loads on mount, the submission gate (9.13, 10.4), the 3.6 release notice,
	and the provider region's place on the Escape stack.
-->
<script lang="ts">
	import { onMount } from 'svelte';
	import AskSurface from '$lib/components/AskSurface.svelte';
	import HistoryPanel from '$lib/components/HistoryPanel.svelte';
	import Pictogram from '$lib/components/Pictogram.svelte';
	import ProviderConfig from '$lib/components/ProviderConfig.svelte';
	import SourcePicker from '$lib/components/SourcePicker.svelte';
	import ThreadView from '$lib/components/ThreadView.svelte';
	import { keys as defaultRouter, type KeyRouter } from '$lib/keys';
	import { history as defaultHistory, type HistoryStore } from '$lib/state/history.svelte';
	import { provider as defaultProvider, type ProviderStore } from '$lib/state/provider.svelte';
	import { scope as defaultScope, type ScopeStore } from '$lib/state/scope.svelte';
	import { sources as defaultSources, type SourcesStore } from '$lib/state/sources.svelte';
	import { thread as defaultThread, type ThreadStore } from '$lib/state/thread.svelte';

	let {
		sources = defaultSources,
		scope = defaultScope,
		thread = defaultThread,
		history = defaultHistory,
		provider = defaultProvider,
		router = defaultRouter
	}: {
		sources?: SourcesStore;
		scope?: ScopeStore;
		thread?: ThreadStore;
		history?: HistoryStore;
		provider?: ProviderStore;
		router?: KeyRouter;
	} = $props();

	let historyOpen = $state(false);
	let providerOpen = $state(false);
	let historyButton: HTMLButtonElement | undefined = $state();
	let providerButton: HTMLButtonElement | undefined = $state();

	// The stores are wired here, not in each other: sources → scope is kept out
	// of the sources store so each tests alone (agent note), and the page is
	// the one place that knows both.
	async function loadSources(): Promise<void> {
		await sources.load();
		if (sources.state === 'ready') scope.load(sources.ids);
	}

	onMount(() => {
		void loadSources();
		void provider.load();
	});

	// 9.13 / 10.4: anything short of a ready source list, and an unacknowledged
	// shared-backend disclosure, block submission — wired through the thread's
	// gate rather than duplicated into every submit path.
	$effect(() => {
		thread.submitGate = () => !sources.blocksSubmission && !provider.blocksFirstTurn;
		return () => {
			thread.submitGate = null;
		};
	});

	// 13.3: the provider region does not register itself (it has no router),
	// so the page holds its place on the Escape stack, opener included.
	$effect(() => {
		if (!providerOpen) return;
		return router.registerRegion({
			dismiss: () => {
				providerOpen = false;
			},
			opener: providerButton ?? null
		});
	});

	/** 8.10: the "taking longer" threshold keys on the provider class. */
	const providerClass = $derived(provider.status?.kind === 'local' ? 'local' : 'hosted');
	const providerName = $derived(provider.status?.model ?? provider.status?.kind ?? null);
</script>

<!-- AskSurface owns the router's window wiring while it is mounted; in the
     degraded states it is not, and Escape must still dismiss regions. The
     guard keeps one handler active at a time, never two. -->
<svelte:window
	onkeydown={(event) => {
		if (sources.state !== 'ready') router.handleKeydown(event);
	}}
/>

<main>
	<!--
		Laid out by grid area rather than by source order: the scope bar shares
		the title's row on a wide window (11.8's chrome budget is measured here)
		and drops to a full row of its own when the window is too narrow to hold
		three things — while staying **before** the region buttons in the DOM,
		because the picker's indicator is the first `button[aria-expanded]` on
		the page and that is how both suites find it.
	-->
	<header class="chrome">
		<h1>DAWMans</h1>
		<div class="picker-slot">
			<SourcePicker {sources} {scope} {router} />
		</div>
		<nav class="regions" aria-label="Regions">
			<button
				bind:this={historyButton}
				type="button"
				aria-expanded={historyOpen}
				onclick={() => {
					historyOpen = !historyOpen;
				}}
			>
				<Pictogram name="history" size="var(--tile-pictogram-small)" />
				History
			</button>
			<button
				bind:this={providerButton}
				type="button"
				aria-expanded={providerOpen}
				onclick={() => {
					providerOpen = !providerOpen;
				}}
			>
				<Pictogram name="settings" size="var(--tile-pictogram-small)" />
				Provider configuration
			</button>
		</nav>
	</header>

	{#if scope.released !== null}
		<!-- 3.6: the release is stated, never silent, with a one-activation reinstate. -->
		<p class="release-notice" role="status">
			<span>
				A narrowed scope from an earlier session was released — every source is back in scope.
			</span>
			<button type="button" onclick={() => scope.reinstate()}>Reinstate narrowing</button>
		</p>
	{/if}

	{#if historyOpen}
		<aside class="region">
			<HistoryPanel
				{history}
				{thread}
				{sources}
				{router}
				opener={historyButton ?? null}
				onclose={() => {
					historyOpen = false;
				}}
			/>
		</aside>
	{/if}

	{#if providerOpen}
		<aside class="region">
			<ProviderConfig
				{provider}
				onclose={() => {
					providerOpen = false;
				}}
			/>
		</aside>
	{/if}

	<div class="content">
		<ThreadView
			{thread}
			{scope}
			{router}
			{sources}
			{providerClass}
			{providerName}
			onconfigure={() => {
				providerOpen = true;
			}}
		/>
	</div>

	<footer class="ask-region">
		{#if sources.state === 'engine-unreachable'}
			<!-- 9.13: the engine unreachable, never rendered as an empty picker. -->
			<p class="engine-state" role="status">
				<span>
					The answer engine could not be reached — the source list is unknown and nothing can be
					asked.
				</span>
				<button type="button" onclick={() => void loadSources()}>Retry</button>
			</p>
		{:else if sources.state === 'corpus-empty'}
			<!-- 9.13: the engine answering that nothing is ingested. -->
			<p class="engine-state" role="status">
				Nothing is ingested yet. Add manuals to <code>manuals/</code> and run the ingestion step,
				then reload this page.
			</p>
		{:else if sources.state === 'ready'}
			{#if provider.blocksFirstTurn}
				<!-- 10.4: the disclosure blocks the first turn until acknowledged. -->
				<p class="gate-notice" role="status">
					<span>
						The shared backend is selected: question text and retrieved passages leave the machine.
						Acknowledge the disclosure before asking.
					</span>
					<button
						type="button"
						onclick={() => {
							providerOpen = true;
						}}
					>
						Open provider configuration
					</button>
				</p>
			{/if}
			<AskSurface {thread} {scope} {router} />
		{/if}
	</footer>
</main>

<style>
	/* 11.8: chrome shares the remainder; the thread takes the height. */
	main {
		display: flex;
		flex-direction: column;
		height: 100vh;
		box-sizing: border-box;
		padding: var(--space-s, 0.5rem) var(--space-m, 1rem);
		gap: var(--space-s, 0.5rem);
	}

	.chrome {
		flex: none;
		display: grid;
		grid-template-columns: auto 1fr;
		grid-template-areas:
			'title regions'
			'picker picker';
		align-items: center; /* spelling-ignore */
		gap: var(--space-s) var(--space-m);
	}

	h1 {
		grid-area: title;
		margin: 0;
		font-size: var(--font-size-control);
		font-weight: 600;
		color: var(--colour-text-secondary); /* spelling-ignore */
	}

	.picker-slot {
		grid-area: picker;
		min-width: 0;
	}

	.regions {
		grid-area: regions;
		justify-self: end;
		display: flex;
		flex-wrap: wrap;
		justify-content: flex-end;
		gap: var(--space-s);
	}

	.regions button {
		display: inline-flex;
		align-items: center; /* spelling-ignore */
		gap: 0.4em;
	}

	/* Wide enough for all three: one chrome row, which is what keeps the 11.8
	   budget where it was before the scope bar grew. */
	@media (min-width: 60rem) {
		.chrome {
			grid-template-columns: auto 1fr auto;
			grid-template-areas: 'title picker regions';
		}
	}

	.content {
		flex: 1;
		min-height: 0;
		overflow-y: auto;
	}

	.ask-region {
		flex: none;
		display: flex;
		flex-direction: column;
		gap: var(--space-s, 0.5rem);
	}

	.region {
		flex: none;
		border: 1px solid var(--colour-text-secondary);
		border-radius: 4px;
		padding: var(--space-s, 0.5rem);
		max-height: 50vh;
		overflow-y: auto;
	}

	.release-notice,
	.engine-state,
	.gate-notice {
		margin: 0;
		font-size: var(--font-size-control);
		color: var(--colour-text); /* spelling-ignore */
	}

	code {
		font-family: monospace;
	}

	button {
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
