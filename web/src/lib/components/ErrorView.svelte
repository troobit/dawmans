<!--
	The error renderers of the design's outcome table (requirements §9; design
	"Coverage failure, errors, and the outcome table", "Error Handling"). One
	line of plain language and at least one action per state (9.1, 9.2, 9.18);
	branching keys on `outcome` and the `reason` sub-code, never on the wording
	in `detail` (9.5, 9.10). `detail` renders only behind the 9.3 disclosure,
	which ThreadView mounts beside this component.

	Also the broken states that carry no outcome: a malformed-request rejection
	naming what was rejected (9.15), an unknown turn-stream version naming both
	versions (9.19), and an outcome outside the taxonomy (9.4) — a turn whose
	renderer is unknown cannot be trusted to any renderer.
-->
<script lang="ts">
	import { EngineRejection } from '../engine/client';
	import { UnknownStreamVersionError } from '../engine/sse';
	import type { Turn } from '../engine/turn.svelte';
	import { scope as defaultScope, type ScopeStore } from '../state/scope.svelte';
	import { thread as defaultThread, type ThreadStore } from '../state/thread.svelte';

	let {
		turn,
		thread = defaultThread,
		scope = defaultScope,
		providerName = null,
		onconfigure = undefined,
		failure = undefined
	}: {
		turn: Turn;
		thread?: ThreadStore;
		scope?: ScopeStore;
		/** 9.6/9.7: the configured provider's name, where the page knows it (§10). */
		providerName?: string | null;
		/** 9.5/9.10: opens provider configuration; wired by the page shell (§10). */
		onconfigure?: (() => void) | undefined;
		/** The transport failure behind a `failed` turn with no outcome (9.15, 9.19). */
		failure?: unknown;
	} = $props();

	const outcome = $derived(turn.envelope.outcome);
	const reason = $derived(turn.envelope.reason);
	const provider = $derived(providerName ?? 'the configured provider');

	/** 9.11: the ids the engine rejected, addressable — never parsed out of `detail`. */
	const rejectedSources = $derived(
		outcome === 'unknown-source-id' ? (turn.envelope.scope_dropped ?? []) : []
	);

	// 9.11: drop the rejected ids from the stored scope. Idempotent — a re-run
	// finds them already deselected and touches nothing.
	$effect(() => {
		for (const ref of rejectedSources) {
			if (scope.isSelected(ref.source_id)) scope.toggle(ref.source_id);
		}
	});

	// 9.8: count `retry_after` down where supplied; absence is never a fault.
	const retryAfter = $derived(
		outcome === 'provider-rate-limited' ? turn.envelope.retry_after : undefined
	);
	let waited = $state(0);
	$effect(() => {
		if (retryAfter === undefined) return;
		waited = 0;
		const interval = setInterval(() => {
			waited += 1;
		}, 1000);
		return () => clearInterval(interval);
	});
	/** Rounded up for display — rounding is permitted, inventing is not (9.8). */
	const remaining = $derived(
		retryAfter === undefined ? 0 : Math.max(0, Math.ceil(retryAfter) - waited)
	);

	function retry(): void {
		thread.submit(turn.question);
	}

	/** 9.5/9.10: into configuration with the typed question preserved (10.2). */
	function openConfiguration(): void {
		if (thread.draft === '') thread.draft = turn.question;
		onconfigure?.();
	}

	function editQuestion(): void {
		thread.draft = turn.question;
	}
</script>

{#if outcome === 'no-sources-selected'}
	<!-- 9.12: the 3.2 empty-scope state, never an unexplained failure. -->
	<div class="empty-scope" role="group" aria-label="No sources selected">
		<p class="summary">No sources are selected — there is nothing to ask against.</p>
		<div class="actions">
			<button type="button" onclick={() => scope.selectAll()}>Select all sources</button>
		</div>
	</div>
{:else if failure !== undefined || turn.renderer === 'broken'}
	<!-- The broken states: no trusted turn is being described. -->
	<div class="error broken" role="group" aria-label="Broken">
		{#if failure instanceof UnknownStreamVersionError}
			<!-- 9.19: both versions, named; the stream was refused unread. -->
			<p class="summary">
				The engine and this surface speak different turn-stream versions — the engine declared
				{failure.declared ?? 'none'}, this surface knows {failure.known}.
			</p>
			<div class="actions">
				<button type="button" onclick={retry}>Retry</button>
			</div>
		{:else if failure instanceof EngineRejection}
			<!-- 9.15: what was rejected, by its machine name; never a refusal. -->
			<p class="summary">
				The engine rejected this request: <code>{failure.rejected}</code>.
			</p>
			<div class="actions">
				<button type="button" onclick={editQuestion}>Edit the question</button>
			</div>
		{:else}
			<!-- 9.4: an outcome outside the taxonomy; `detail` sits in the disclosure. -->
			<p class="summary">
				The engine reported this turn in a way this surface does not recognise.
			</p>
			<div class="actions">
				<button type="button" onclick={editQuestion}>Edit the question</button>
			</div>
		{/if}
	</div>
{:else}
	<div class="error" role="group" aria-label="Error">
		{#if outcome === 'provider-unconfigured'}
			<!-- 9.5: keyed on the reason sub-code, never the wording in detail. -->
			{#if reason === 'no-provider-kind'}
				<p class="summary">No provider is chosen yet — answering needs one.</p>
			{:else if reason === 'missing-credential'}
				<p class="summary">The chosen hosted provider needs an API key, and none is stored.</p>
			{:else if reason === 'disclosure-unacknowledged'}
				<p class="summary">The shared backend's disclosure has not been acknowledged yet.</p>
			{:else}
				<p class="summary">The provider is not configured.</p>
			{/if}
			<div class="actions">
				<button type="button" onclick={openConfiguration}>Open provider configuration</button>
			</div>
		{:else if outcome === 'provider-unreachable'}
			<!-- 9.6: names the provider; plainly not a coverage failure. -->
			<p class="summary">Could not reach {provider}. The question was not answered.</p>
			<div class="actions">
				<button type="button" onclick={retry}>Retry</button>
			</div>
		{:else if outcome === 'timeout'}
			<!-- 9.7: the provider stalled — deliberately distinct from 9.6. -->
			<p class="summary">{provider} stalled — it accepted the question but no answer arrived.</p>
			<div class="actions">
				<button type="button" onclick={retry}>Retry</button>
			</div>
		{:else if outcome === 'provider-rate-limited'}
			<p class="summary">The provider is rate-limiting requests.</p>
			{#if retryAfter !== undefined}
				<p class="countdown">Retry in {remaining} s.</p>
			{:else}
				<!-- 9.8: absence is a permitted case, stated honestly, never invented. -->
				<p class="countdown">It did not say how long to wait.</p>
			{/if}
			<div class="actions">
				<button type="button" onclick={retry} disabled={remaining > 0}>Retry</button>
			</div>
		{:else if outcome === 'provider-error' && reason === 'authentication-failed'}
			<!-- 9.10: a retry on the same credential cannot succeed. -->
			<p class="summary">The provider rejected the stored credential.</p>
			<div class="actions">
				<button type="button" onclick={openConfiguration}>Open provider configuration</button>
			</div>
		{:else if outcome === 'provider-error'}
			<!-- 9.9: the engine's own wording stays behind the disclosure. -->
			<p class="summary">The provider failed or rejected the request.</p>
			<div class="actions">
				<button type="button" onclick={retry}>Retry</button>
			</div>
		{:else if outcome === 'unknown-source-id'}
			<!-- 9.11: names the rejected ids; the effect above dropped them (3.8). -->
			<p class="summary">
				The engine no longer knows
				{rejectedSources.length > 0
					? rejectedSources.map((ref) => ref.display_name).join(', ')
					: 'one of the selected sources'} — removed from your scope.
			</p>
			<div class="actions">
				<button type="button" onclick={retry}>Re-ask against the remaining sources</button>
			</div>
		{:else if outcome === 'corpus-empty'}
			<!-- 9.13: no in-app action exists; the instruction names both steps. -->
			<p class="summary">
				No sources are ingested — neither a vendor manual nor authored triage notes.
			</p>
			<p class="instruction">
				Add manuals to the <code>manuals/</code> directory and run the ingestion step; asking
				stays disabled until a source is reported.
			</p>
		{:else}
			<p class="summary">This question was not answered.</p>
			<div class="actions">
				<button type="button" onclick={retry}>Retry</button>
			</div>
		{/if}
	</div>
{/if}

<style>
	.error,
	.empty-scope {
		display: flex;
		flex-direction: column;
		gap: var(--space-s, 0.5rem);
		/* Its own shape (8.4, 11.6): the broken edge, distinct from coverage's. */
		border-inline-start: 3px solid var(--colour-state-broken);
		padding-inline-start: 0.75em;
	}

	.empty-scope {
		border-inline-start-color: var(--colour-text-secondary); /* spelling-ignore */
	}

	.error p,
	.empty-scope p {
		margin: 0;
		color: var(--colour-text); /* spelling-ignore */
		font-size: var(--font-size-body);
	}

	.summary {
		font-weight: 600;
	}

	.instruction,
	.countdown {
		color: var(--colour-text-secondary); /* spelling-ignore */
		font-size: var(--font-size-control);
	}

	.countdown {
		font-variant-numeric: tabular-nums;
	}

	code {
		font-family: monospace;
		background: var(--colour-surface);
		padding: 0.1em 0.35em;
		border-radius: 3px;
	}

	.actions {
		display: flex;
		flex-wrap: wrap;
		gap: var(--space-s, 0.5rem);
	}

	button {
		background: var(--colour-surface);
		color: var(--colour-text); /* spelling-ignore */
		font-size: var(--font-size-control);
		border: 1px solid var(--colour-text-secondary);
		border-radius: 4px;
		padding: 0.25em 0.75em;
	}

	button:disabled {
		/* 13.8/11.3: disabledness by label-and-state, contrast held at 4.5:1. */
		color: var(--colour-text-disabled); /* spelling-ignore */
	}

	button:focus-visible {
		outline: 2px solid var(--colour-focus-ring);
		outline-offset: 1px;
	}
</style>
