<!--
	The coverage-failure renderer (requirements §7, 3.10, 9.2; CONTRACTS §4e;
	design "Coverage failure, errors, and the outcome table"). One renderer for
	the three outcomes whose subject is coverage, with a per-outcome action
	table: add-the-named-sources-and-re-ask from addressable suggestions (7.4),
	widen-all where nothing is suggested and out-of-scope sources exist (7.5),
	both suppressed on `out-of-domain` and `no-manual-for-device` where the
	engine has already judged no ingested manual covers the question, and the
	copyable `required_manual` filename (7.7). The state never dead-ends (9.2):
	where nothing else applies it falls through to re-editing the question.

	Widening goes through the scope store, so it persists like any other scope
	change and decays per session (7.9); a re-ask is a new turn, submitted by
	the thread store against the changed scope.
-->
<script lang="ts" module>
	import type { SourcesStore } from '../state/sources.svelte';

	/** What this renderer needs of the source list: existence and names (7.3, 7.5, 7.8). */
	export type SourcesLike = Pick<SourcesStore, 'ids' | 'displayName'>;
</script>

<script lang="ts">
	import type { Turn } from '../engine/turn.svelte';
	import { scope as defaultScope, type ScopeStore } from '../state/scope.svelte';
	import { sources as defaultSources } from '../state/sources.svelte';
	import { thread as defaultThread, type ThreadStore } from '../state/thread.svelte';

	let {
		turn,
		thread = defaultThread,
		scope = defaultScope,
		sources = defaultSources
	}: {
		turn: Turn;
		thread?: ThreadStore;
		scope?: ScopeStore;
		sources?: SourcesLike;
	} = $props();

	const outcome = $derived(turn.envelope.outcome);
	// Permitted on `refused-not-covered` only (CONTRACTS §4): a suggestion on
	// another outcome is a producer defect, never licence to render it.
	const suggested = $derived(
		outcome === 'refused-not-covered' ? turn.envelope.suggested_sources : undefined
	);

	function name(id: string): string {
		return sources.displayName(id) ?? id;
	}

	/** 7.3: the scope at ask time, not the scope now. */
	const scopeNames = $derived(turn.scopeAtAsk.map(name));
	/** 7.8: measured against every source the engine reports. */
	const allInScope = $derived(sources.ids.every((id) => turn.scopeAtAsk.includes(id)));
	/** 7.5: no suggestion, out-of-scope sources exist, and the outcome permits widening. */
	const widenOffered = $derived(
		outcome === 'refused-not-covered' && suggested === undefined && !allInScope
	);

	/** 7.4: one activation — the named sources into scope, the same question again. */
	function addAndReAsk(): void {
		for (const ref of suggested ?? []) {
			if (!scope.isSelected(ref.source_id)) scope.toggle(ref.source_id);
		}
		thread.submit(turn.question);
	}

	/** 7.5 / 7.9: widen to all sources and re-ask; the widening persists. */
	function widenAndReAsk(): void {
		scope.selectAll();
		thread.submit(turn.question);
	}

	/** 7.6 / 7.8: the question back into the draft, re-editable (1.4). */
	function editQuestion(): void {
		thread.draft = turn.question;
	}

	/** 7.7: the exact filename in one activation. */
	function copyFilename(filename: string): void {
		void navigator.clipboard.writeText(filename);
	}
</script>

<div class="coverage-failure" role="group" aria-label="Not covered">
	{#if outcome === 'out-of-domain'}
		<!-- 7.6: technique wording; suggestions and widen suppressed. -->
		<p class="summary">
			This is a technique question, not a documented control — no ingested source, neither a
			manual nor your triage notes, covers it.
		</p>
	{:else if outcome === 'no-manual-for-device'}
		<!-- 7.7: the device, and that ingestion must re-run. -->
		<p class="summary">
			{#if turn.envelope.required_device !== undefined}
				No manual for the {turn.envelope.required_device.display_name} is ingested. Add its
				manual to <code>manuals/</code> and re-run ingestion for it to take effect.
			{:else}
				No ingested manual covers the device this question needs. Add its manual to
				<code>manuals/</code> and re-run ingestion.
			{/if}
		</p>
	{:else}
		<!-- 7.1: plainly, with no synthesised answer beside it. -->
		<p class="summary">The sources in scope do not cover this question.</p>
	{/if}

	<p class="in-scope">In scope when asked: {scopeNames.join(', ')}.</p>

	{#if suggested !== undefined && !allInScope}
		<!-- 3.10: the gap belongs to the narrowing in force, not to the corpus. -->
		<p class="narrowed">
			The scope is narrowed — the answer may sit in a source outside it.
		</p>
	{/if}

	{#if outcome === 'no-manual-for-device'}
		{#if turn.envelope.required_manual !== undefined}
			<!-- 7.7: the assembled filename, copyable in one activation. -->
			<p class="filename">
				<code>{turn.envelope.required_manual.filename}</code>
				<button type="button" onclick={() => copyFilename(turn.envelope.required_manual!.filename)}>
					Copy filename
				</button>
			</p>
			{#if turn.envelope.required_manual.placeholders.length > 0}
				<!-- The fields the user fills, named by the engine — never split out of the filename. -->
				<p class="placeholders">
					Fill in from the document you obtain: {turn.envelope.required_manual.placeholders.join(
						', '
					)}.
				</p>
			{/if}
		{:else}
			<!-- 7.7: nothing synthesised — the convention and the device instead. -->
			<p class="convention">
				Name the file per the <code>manuals/</code> convention
				<code>&lt;vendor&gt;_&lt;product&gt;_&lt;doctype&gt;_v&lt;version&gt;_&lt;lang&gt;.pdf</code>
				{#if turn.envelope.required_device !== undefined}
					for the {turn.envelope.required_device.display_name}{/if}.
			</p>
		{/if}
	{/if}

	{#if allInScope && outcome === 'refused-not-covered'}
		<!-- 7.8: no widen to offer; the state says so and falls through. -->
		<p class="all-in-scope">Every available source was already in scope.</p>
	{/if}

	<div class="actions">
		{#if suggested !== undefined}
			<!-- 7.4: addressable values, one activation. -->
			<button type="button" onclick={addAndReAsk}>
				Add {suggested.map((ref) => ref.display_name).join(', ')} and re-ask
			</button>
		{:else if widenOffered}
			<button type="button" onclick={widenAndReAsk}>Widen to all sources and re-ask</button>
		{/if}
		<!-- 9.2: never a dead end — re-editing is always reachable from the state. -->
		<button type="button" onclick={editQuestion}>Edit the question</button>
	</div>
</div>

<style>
	.coverage-failure {
		display: flex;
		flex-direction: column;
		gap: var(--space-s, 0.5rem);
		/* 7.2: its own shape — distinct from answer, narrowing and error. */
		border-inline-start: 3px solid var(--colour-text-secondary);
		padding-inline-start: 0.75em;
	}

	.coverage-failure p {
		margin: 0;
		color: var(--colour-text); /* spelling-ignore */
		font-size: var(--font-size-body);
	}

	.summary {
		font-weight: 600;
	}

	.in-scope,
	.narrowed,
	.placeholders,
	.convention,
	.all-in-scope {
		color: var(--colour-text-secondary); /* spelling-ignore */
		font-size: var(--font-size-control);
	}

	.filename code {
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

	button:focus-visible {
		outline: 2px solid var(--colour-focus-ring);
		outline-offset: 1px;
	}
</style>
