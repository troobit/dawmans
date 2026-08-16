<!--
	The source picker (requirements 2.2, 2.5–2.14, 3.3, 3.10, 11.6, 11.7, 13.4;
	design "The source picker"). Collapsed at rest to the one-line scope bar;
	expanded in place to a grid of source tiles, one activation each way.
	Presentation only — the source list and both gap reports come from the
	sources store, selection goes through the scope store, and Escape dismissal
	goes through the router's region stack (13.3).

	The tiles and their pictograms are Decision 10: what is in scope should be
	read as pictures and one short phrase from across the room (2.14), not as a
	line of small print. Every picture is aria-hidden and sits beside the words
	it illustrates, so nothing about the accessible reading changes.
-->
<script lang="ts">
	import type { SourceRecord } from '../engine/records';
	import { keys, type KeyRouter } from '../keys';
	import { scope as defaultScope, type ScopeStore } from '../state/scope.svelte';
	import { sources as defaultSources, type SourcesStore } from '../state/sources.svelte';
	import Pictogram from './Pictogram.svelte';
	import { pictogramFor } from './pictograms';

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
	const selectedNames = $derived(scope.selected.map((id) => sources.displayName(id) ?? id));

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
		return sources.sources.filter((record) => record.display_name.toLowerCase().includes(needle));
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
		<span class="indicator-text">{indicator}</span>
		<!-- The bar says what it does. It is the one control that opens the
		     picker (2.11), and 11.8 keeps it to a single line — which is why the
		     pictograms live on the tiles inside rather than out here. -->
		<span class="affordance">{expanded ? 'Close' : 'Choose sources'}</span>
	</button>

	{#if expanded}
		<div class="body">
			<div class="controls">
				<!-- 2.8: single controls for everything and nothing. -->
				<button type="button" onclick={() => scope.selectAll()}>All in scope</button>
				<button type="button" onclick={() => scope.selectNone()}>None in scope</button>

				{#if total >= FILTER_THRESHOLD}
					<label class="filter">
						Filter sources
						<input type="text" bind:value={filter} />
					</label>
				{/if}
			</div>

			<ul class="sources">
				{#each visible as record (record.source_id)}
					{@const selected = scope.isSelected(record.source_id)}
					<li class="source">
						<label class="tile" data-in={selected}>
							<!-- 2.2/13.4: a native checkbox — keyboard-operable, state exposed. -->
							<input
								type="checkbox"
								checked={selected}
								onchange={() => scope.toggle(record.source_id)}
							/>
							<Pictogram name={pictogramFor(record)} size="var(--tile-pictogram)" />
							<span class="name">{record.display_name}</span>
							<span class="state">
								<!-- 2.14/11.6: filled versus hollow, plus the word — never colour. -->
								<span class="scope-marker" aria-hidden="true">{selected ? '●' : '○'}</span>
								<span class="scope-word">{selected ? 'in scope' : 'out of scope'}</span>
							</span>
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
		position: relative;
		min-width: 0;
	}

	/* The scope bar reads as one wide target rather than a line of text: it is
	   the one control that opens the picker (2.11), so it looks like one. */
	.indicator {
		display: flex;
		align-items: center; /* spelling-ignore */
		gap: var(--space-s);
		/* One line, always: 11.8's budget is measured with this bar collapsed,
		   and a second flex line here costs the answer 26 px. */
		flex-wrap: nowrap;
		width: 100%;
		background: var(--colour-surface);
		border: 1px solid var(--colour-text-secondary);
		border-radius: var(--radius);
		box-shadow: var(--shadow-tile);
		padding: var(--space-xs) var(--space-m);
		color: var(--colour-text); /* spelling-ignore */
		font-size: var(--font-size-body);
		text-align: left;
		cursor: pointer;
	}

	.indicator:hover {
		border-color: var(--colour-accent-hover); /* spelling-ignore */
	}

	.indicator:focus-visible {
		outline: 2px solid var(--colour-focus-ring);
		outline-offset: 1px;
	}

	/* 2.6's names are always the button's accessible name and always complete
	   inside the panel; on a bar too narrow to hold them they clip rather than
	   push the answer down. */
	.indicator-text {
		min-width: 0;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}

	/* 11.6: the glyph is the shape channel; colour rides along, never carries. */
	.scope-glyph {
		font-size: var(--font-size-heading);
		line-height: 1;
	}

	.indicator[data-scope='narrowed'] .scope-glyph {
		color: var(--colour-accent); /* spelling-ignore */
	}

	.affordance {
		margin-inline-start: auto;
		font-size: var(--font-size-control);
		color: var(--colour-accent); /* spelling-ignore */
		white-space: nowrap;
	}

	/*
		The expanded picker is a panel under the bar rather than a block in the
		layout: 2.11 puts it "under the scope indicator", and floating it there
		is what keeps 11.8's chrome budget a *collapsed* measurement even while
		the tiles are as large as 2.14 wants them. Escape and the one indicator
		control dismiss it exactly as before (13.3).
	*/
	.body {
		position: absolute;
		inset-inline: 0;
		inset-block-start: calc(100% + var(--space-xs));
		z-index: 5;
		display: flex;
		flex-direction: column;
		gap: var(--space-s);
		max-height: 70vh;
		overflow-y: auto;
		padding: var(--space-s);
		box-sizing: border-box;
		background: var(--colour-bg);
		border: 1px solid var(--colour-text-secondary);
		border-radius: var(--radius);
		box-shadow: var(--shadow-tile-raised);
	}

	.controls {
		display: flex;
		align-items: center; /* spelling-ignore */
		gap: var(--space-s);
		flex-wrap: wrap;
	}

	.controls button {
		background: var(--colour-surface);
		color: var(--colour-text); /* spelling-ignore */
		font-size: var(--font-size-control);
		border: 1px solid var(--colour-text-secondary);
		border-radius: var(--radius);
		padding: 0.4em 0.9em;
		cursor: pointer;
	}

	.controls button:hover {
		border-color: var(--colour-accent-hover); /* spelling-ignore */
	}

	.controls button:focus-visible {
		outline: 2px solid var(--colour-focus-ring);
		outline-offset: 1px;
	}

	.filter {
		font-size: var(--font-size-control);
		color: var(--colour-text-secondary); /* spelling-ignore */
		margin-inline-start: auto;
	}

	.filter input {
		background: var(--colour-surface);
		color: var(--colour-text); /* spelling-ignore */
		font-size: var(--font-size-control);
		border: 1px solid var(--colour-text-secondary);
		border-radius: var(--radius);
		padding: 0.25em 0.5em;
		margin-inline-start: 0.5em;
	}

	.filter input:focus-visible {
		outline: 2px solid var(--colour-focus-ring);
		outline-offset: 1px;
	}

	/* 2.13: a grid that reflows rather than a list that scrolls — twelve
	   sources fit three rows on a 1280-wide window and still wrap to one
	   column at 640 without a horizontal scrollbar (13.7). */
	.sources {
		list-style: none;
		margin: 0;
		padding: 0;
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(min(100%, var(--tile-min-width)), 1fr));
		gap: var(--space-s);
	}

	.tile {
		position: relative;
		display: flex;
		flex-direction: column;
		align-items: center; /* spelling-ignore */
		text-align: center; /* spelling-ignore */
		gap: var(--space-xs);
		height: 100%;
		box-sizing: border-box;
		padding: var(--space-m) var(--space-s) var(--space-s);
		border: 2px dashed var(--colour-text-secondary);
		border-radius: var(--radius-tile);
		background: var(--colour-bg);
		color: var(--colour-text-secondary); /* spelling-ignore */
		cursor: pointer;
		transition:
			border-color 120ms ease, /* spelling-ignore */
			background-color 120ms ease; /* spelling-ignore */
	}

	/* Out of scope is a recessed, dashed, secondary tile; in scope is a raised,
	   solid, full-strength one. Shape and weight carry it, colour rides along
	   (11.6) — a greyscale screenshot reads the same. */
	.tile[data-in='true'] {
		border-style: solid;
		border-color: var(--colour-accent); /* spelling-ignore */
		background: var(--colour-surface);
		box-shadow: var(--shadow-tile-raised);
		color: var(--colour-text); /* spelling-ignore */
	}

	.tile:hover {
		border-color: var(--colour-accent-hover); /* spelling-ignore */
	}

	/* 13.2: the ring belongs on the tile, since the checkbox is the small part
	   of a large target. */
	.tile:has(input:focus-visible) {
		outline: 2px solid var(--colour-focus-ring);
		outline-offset: 1px;
	}

	.tile input[type='checkbox'] {
		position: absolute;
		inset-block-start: var(--space-s);
		inset-inline-start: var(--space-s);
		width: 1.25rem;
		height: 1.25rem;
		margin: 0;
		accent-color: var(--colour-accent); /* spelling-ignore */
		cursor: pointer;
	}

	.name {
		font-size: var(--font-size-body);
		color: var(--colour-text); /* spelling-ignore */
		overflow-wrap: anywhere;
	}

	.state {
		display: flex;
		align-items: center; /* spelling-ignore */
		gap: 0.35em;
		font-size: var(--font-size-control);
	}

	.kind,
	.scope-word {
		color: var(--colour-text-secondary); /* spelling-ignore */
	}

	.kind {
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

	/* 11.9 / 13.6: the only motion here is a 120 ms colour change that moves
	   nothing; under a reduced-motion preference even that is dropped. */
	@media (prefers-reduced-motion: reduce) {
		.tile {
			transition: none;
		}
	}
</style>
