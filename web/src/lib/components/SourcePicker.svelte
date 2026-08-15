<!--
	The source picker (requirements 2.2, 2.5–2.14, 3.3, 3.10, 11.6, 13.4;
	design "The source picker"). Collapsed at rest to the one-line scope
	indicator; expanded in place under the scope bar, one activation each way.
	Presentation only — the source list and both gap reports come from the
	sources store, selection goes through the scope store, and Escape dismissal
	goes through the router's region stack (13.3).
-->
<script lang="ts">
	import type { SourceRecord } from '../engine/records';
	import { keys, type KeyRouter } from '../keys';
	import { scope as defaultScope, type ScopeStore } from '../state/scope.svelte';
	import { sources as defaultSources, type SourcesStore } from '../state/sources.svelte';

	/** 2.13: the target — all sources visible without scrolling up to 12; a filter beyond. */
	const FILTER_THRESHOLD = 12;

	let {
		sources = defaultSources,
		scope = defaultScope,
		router = keys
	}: { sources?: SourcesStore; scope?: ScopeStore; router?: KeyRouter } = $props();

	// 2.11: collapsed at rest once a scope is chosen — which load() guarantees.
	let expanded = $state(false);
	let filter = $state('');
	let toggleButton: HTMLButtonElement | undefined = $state();

	const total = $derived(sources.sources.length);
	const selectedNames = $derived(
		scope.selected.map((id) => sources.displayName(id) ?? id)
	);

	/**
	 * 3.10/11.6: the narrowed state is distinct from all-sources by shape and
	 * label — the glyph and the wording move together, colour never carries it.
	 */
	const scopeState = $derived(
		scope.selected.length === 0 ? 'none' : scope.selected.length === total ? 'all' : 'narrowed'
	);
	const glyph = $derived(scopeState === 'all' ? '●' : scopeState === 'none' ? '○' : '◐');
	const indicator = $derived.by(() => {
		if (scopeState === 'none') return 'No sources in scope';
		if (scopeState === 'all') {
			// 2.7: explicit, never a bare count — and at ≤3 the names carry too (2.6, 3.3).
			return selectedNames.length <= 3
				? `All in scope: ${selectedNames.join(', ')}`
				: `All ${total} sources in scope`;
		}
		if (selectedNames.length <= 3) return `${selectedNames.join(', ')} in scope`; // 2.6, 3.3
		return `${selectedNames.length} of ${total} sources in scope`; // 2.5
	});

	/** 2.13: a plain substring match over display_name; no chrome below the threshold. */
	const visible = $derived.by(() => {
		const needle = filter.trim().toLowerCase();
		if (needle === '') return sources.sources;
		return sources.sources.filter((record) =>
			record.display_name.toLowerCase().includes(needle)
		);
	});

	/** 2.10: the revision an assumed-applicability source is taken to describe. */
	function assumedDevice(record: SourceRecord): string | null {
		const applicability = record.hardware_applicability;
		return applicability.status === 'assumed' && applicability.device !== undefined
			? applicability.device
			: null;
	}

	// 13.3: while expanded, the picker is a dismissible region on the Escape
	// stack, returning focus to the indicator control that opened it.
	$effect(() => {
		if (!expanded) return;
		return router.registerRegion({
			dismiss: () => {
				expanded = false;
			},
			opener: toggleButton ?? null
		});
	});
</script>

<section class="picker" aria-label="Source scope">
	<button
		bind:this={toggleButton}
		type="button"
		class="indicator"
		data-scope={scopeState}
		aria-expanded={expanded}
		onclick={() => {
			expanded = !expanded;
		}}
	>
		<span class="scope-glyph" aria-hidden="true">{glyph}</span>
		{indicator}
	</button>

	{#if expanded}
		<div class="body">
			{#if total >= FILTER_THRESHOLD}
				<label class="filter">
					Filter sources
					<input type="text" bind:value={filter} />
				</label>
			{/if}

			<div class="bulk">
				<!-- 2.8: single controls for everything and nothing. -->
				<button type="button" onclick={() => scope.selectAll()}>All in scope</button>
				<button type="button" onclick={() => scope.selectNone()}>None in scope</button>
			</div>

			<ul class="sources">
				{#each visible as record (record.source_id)}
					{@const selected = scope.isSelected(record.source_id)}
					<li class="source">
						<label>
							<!-- 2.2/13.4: a native checkbox — keyboard-operable, state exposed. -->
							<input
								type="checkbox"
								checked={selected}
								onchange={() => scope.toggle(record.source_id)}
							/>
							<!-- 2.14/11.6: filled versus hollow, plus the word — never colour. -->
							<span class="scope-marker" aria-hidden="true">{selected ? '●' : '○'}</span>
							<span class="name">{record.display_name}</span>
							<span class="scope-word">{selected ? 'in scope' : 'out of scope'}</span>
							<!-- 2.12: the kind, stated on the entry. -->
							<span class="kind">
								{record.kind === 'authored-triage' ? 'your own notes (authored)' : 'manual'}
							</span>
							{#if !scope.seen.includes(record.source_id)}
								<!-- 2.4: visibly new until the next submitted question; the word is
								     the channel (11.6), and the checkbox is the one-activation add. -->
								<span class="mark new">new</span>
							{/if}
							{#if assumedDevice(record) !== null}
								<!-- 2.10: the mismatch known before the question is asked. -->
								<span class="mark">describes {assumedDevice(record)} — unconfirmed for your rig</span>
							{/if}
							{#if record.kind === 'vendor-manual' && record.low_text}
								<!-- CONTRACTS §1: picker marking is the whole consumption obligation. -->
								<span class="mark">sparse text layer</span>
							{/if}
						</label>
					</li>
				{/each}
			</ul>

			{#if sources.ownedUndocumented.length > 0}
				<!-- 2.9: apart and never selectable; omitted entirely, heading included,
				     when the report is empty — the live case (CONTRACTS §5). -->
				<section class="gaps">
					<h3>Known gaps</h3>
					<ul>
						{#each sources.ownedUndocumented as gap (gap.device)}
							<li>{gap.display_name} — owned, no manual ingested</li>
						{/each}
					</ul>
				</section>
			{/if}
		</div>
	{/if}
</section>

<style>
	.picker {
		display: flex;
		flex-direction: column;
		gap: var(--space-s, 0.5rem);
	}

	.indicator {
		background: none;
		border: none;
		padding: 0.25em 0;
		color: var(--colour-text); /* spelling-ignore */
		font-size: var(--font-size-control);
		text-align: left;
		cursor: pointer;
	}

	.indicator:focus-visible {
		outline: 2px solid var(--colour-focus-ring);
		outline-offset: 1px;
	}

	/* 11.6: the glyph is the shape channel; colour rides along, never carries. */
	.scope-glyph {
		margin-inline-end: 0.35em;
	}

	.indicator[data-scope='narrowed'] .scope-glyph {
		color: var(--colour-accent); /* spelling-ignore */
	}

	.body {
		display: flex;
		flex-direction: column;
		gap: var(--space-s, 0.5rem);
	}

	.filter {
		font-size: var(--font-size-control);
		color: var(--colour-text-secondary); /* spelling-ignore */
	}

	.filter input {
		background: var(--colour-surface);
		color: var(--colour-text); /* spelling-ignore */
		font-size: var(--font-size-control);
		border: 1px solid var(--colour-text-secondary);
		border-radius: 4px;
		padding: 0.25em 0.5em;
		margin-inline-start: 0.5em;
	}

	.filter input:focus-visible {
		outline: 2px solid var(--colour-focus-ring);
		outline-offset: 1px;
	}

	.bulk {
		display: flex;
		gap: var(--space-s, 0.5rem);
	}

	.bulk button {
		background: var(--colour-surface);
		color: var(--colour-text); /* spelling-ignore */
		font-size: var(--font-size-control);
		border: 1px solid var(--colour-text-secondary);
		border-radius: 4px;
		padding: 0.25em 0.75em;
	}

	.bulk button:focus-visible {
		outline: 2px solid var(--colour-focus-ring);
		outline-offset: 1px;
	}

	.sources {
		list-style: none;
		margin: 0;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: var(--space-xs, 0.25rem);
	}

	.source label {
		display: flex;
		align-items: baseline;
		gap: 0.5em;
		font-size: var(--font-size-control);
		color: var(--colour-text); /* spelling-ignore */
	}

	.source input:focus-visible {
		outline: 2px solid var(--colour-focus-ring);
		outline-offset: 1px;
	}

	.scope-word,
	.kind {
		color: var(--colour-text-secondary); /* spelling-ignore */
		font-size: var(--font-size-secondary);
	}

	.mark {
		color: var(--colour-text-secondary); /* spelling-ignore */
		font-size: var(--font-size-secondary);
		font-style: italic;
	}

	.gaps h3 {
		margin: 0;
		font-size: var(--font-size-control);
		color: var(--colour-text-secondary); /* spelling-ignore */
	}

	.gaps ul {
		list-style: none;
		margin: 0;
		padding: 0;
		color: var(--colour-text-secondary); /* spelling-ignore */
		font-size: var(--font-size-secondary);
	}
</style>
