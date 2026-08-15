<!--
	One citation entry (CONTRACTS §3/§3a; requirements 5.1–5.11, 5.14–5.16,
	5.18, 5.19; Decision 3). Everything the citation says renders here, inline
	on the entry with no disclosure in the path — never mid-prose, where five
	caveats would breach 11.7 on the first citation. The location slot is
	section number, section title and page where they exist; a pageless
	authored citation puts its symptom title there and invents neither a page
	nor a number (5.15).

	openAtSource is two branches and no third (5.5): a vendor manual is a
	plain link to the engine-served document at exactly `#page=N` — appending
	anything else disables the jump in at least one viewer — and an authored
	entry is the in-place expansion plus the copyable `entry_location`. No
	`file://` URL is ever attempted: a tab served over http cannot reach one,
	and the refusal is silent, so the control would be dead rather than
	unavailable.
-->
<script lang="ts">
	import { tick } from 'svelte';
	import { serveDocumentHref } from '../engine/client';
	import type { Citation } from '../engine/records';
	import { passages as defaultPassages, type PassageStore } from '../state/passages.svelte';

	let {
		number,
		citation,
		passages = defaultPassages
	}: { number: number; citation: Citation; passages?: PassageStore } = $props();

	let expanded = $state(false);
	let showWorking = $state(false);
	let entryElement: HTMLLIElement | undefined = $state();
	/** The entry's viewport offset before expanding — its rect, not scrollY (5.8). */
	let topBeforeExpand = 0;

	const passage = $derived(passages.get(citation.passage_id));

	// 5.18: a cache miss shows the working indicator past 300 ms rather than
	// an empty area. A hit or a failure never shows it: their branches render
	// ahead of it, and the timer only ever runs while the fetch is in flight.
	// The flag is written in the timer callback (untracked) and reset in the
	// expand handler, never inside the effect itself.
	$effect(() => {
		if (!expanded || passage?.status !== 'loading') return;
		const timer = setTimeout(() => {
			showWorking = true;
		}, 300);
		return () => clearTimeout(timer);
	});

	function toggleExpanded(): void {
		if (!expanded) {
			topBeforeExpand = entryElement?.getBoundingClientRect().top ?? 0;
			showWorking = false;
			passages.prefetch(citation.passage_id);
			expanded = true;
			return;
		}
		expanded = false;
		// 5.8: content above may have grown while streaming continued, so
		// restore this entry's viewport offset, never a remembered scrollY.
		void tick().then(() => {
			const top = entryElement?.getBoundingClientRect().top;
			if (top !== undefined && top !== topBeforeExpand) {
				scrollerFor(entryElement).scrollBy(0, top - topBeforeExpand);
			}
		});
	}

	/**
	 * The thread scrolls inside a container on the assembled page, so the
	 * restore must scroll the nearest scrollable ancestor — `window.scrollBy`
	 * is a silent no-op there. The window is the fallback, not the default.
	 */
	function scrollerFor(element: Element | undefined): { scrollBy(x: number, y: number): void } {
		for (let node = element?.parentElement ?? null; node !== null; node = node.parentElement) {
			if (/(auto|scroll)/.test(getComputedStyle(node).overflowY)) return node;
		}
		return window;
	}

	/** 5.19: one activation puts the entry's file and line on the clipboard. */
	function copyEntryLocation(location: string): void {
		void navigator.clipboard.writeText(location);
	}
</script>

<li class="citation-entry" bind:this={entryElement}>
	<span class="entry-number" aria-label="citation {number}">{number}</span>
	<span class="source">{citation.display_name}</span>
	{#if citation.kind === 'vendor-manual'}
		<!-- 5.2: the mk1/mk2 mitigation; it fails if hidden. -->
		<span class="doc-version">v{citation.doc_version}</span>
	{:else}
		<!-- 5.14: the word is the channel that survives greyscale (11.6). -->
		<span class="kind">your own note</span>
	{/if}

	<span class="location">
		{#if citation.kind === 'authored-triage'}
			<span class="section-title">{citation.section_title}</span>
		{:else}
			{#if citation.section_number !== undefined}
				<span class="section-number">{citation.section_number}</span>
			{/if}
			<span class="section-title">{citation.section_title}</span>
			<span class="page">p{citation.page}</span>
		{/if}
	</span>

	{#if citation.hardware_applicability.status === 'assumed' && citation.hardware_applicability.device !== undefined}
		<!-- 5.3: which revision the document describes, where the user is already looking. -->
		<span class="applicability">
			describes the {citation.hardware_applicability.device} — unconfirmed for your rig
		</span>
	{/if}

	{#if citation.kind === 'vendor-manual' && citation.has_figures}
		<!-- 5.4: the sole offset for a text-only index. -->
		<span class="figures">figure on p{citation.page}</span>
	{/if}

	{#if citation.unbacked === true}
		<!-- 5.16: a broken or never-provided fix is never presented as documented. -->
		<span class="unbacked">no manual behind this</span>
	{/if}

	<!-- 5.6/5.7: the passage revealed in place; prefetched on focus, never hover (1.12). -->
	<button
		type="button"
		class="expand"
		aria-expanded={expanded}
		onfocus={() => passages.prefetch(citation.passage_id)}
		onclick={toggleExpanded}
	>
		{expanded ? 'Hide passage' : 'Show passage'}
	</button>

	{#if citation.kind === 'vendor-manual'}
		<!-- 5.5: a plain link activation — not a popup — at `#page=N` and nothing else. -->
		<a
			class="open"
			href={serveDocumentHref(citation.source_id, citation.page)}
			target="_blank"
			rel="noopener"
		>
			Open manual at p{citation.page}
		</a>
	{:else}
		<!-- 5.19: beside the open action, copyable, never in the location slot. -->
		<span class="entry-location">{citation.entry_location}</span>
		<button type="button" onclick={() => copyEntryLocation(citation.entry_location)}>
			Copy location
		</button>
	{/if}

	{#if expanded}
		{#if passage?.status === 'ready'}
			<blockquote class="passage">
				{#if passage.passage.degraded}
					<!-- 5.10: mojibake is never mistaken for the manual's own wording. -->
					<p class="degraded-mark">Some characters could not be read from the PDF.</p>
				{/if}
				<p class="passage-text">{passage.passage.text}</p>
			</blockquote>
		{:else if passage?.status === 'failed'}
			<!-- 5.11: only the body reports unavailable; the entry keeps everything else. -->
			<p class="passage-unavailable">The passage is unavailable right now.</p>
		{:else if showWorking}
			<p class="passage-working">Fetching the passage…</p>
		{/if}
	{/if}
</li>

<style>
	.citation-entry {
		display: flex;
		flex-wrap: wrap;
		align-items: baseline;
		column-gap: 0.5em;
		color: var(--colour-text); /* spelling-ignore */
		font-size: var(--font-size-control);
	}

	.entry-number {
		color: var(--colour-accent); /* spelling-ignore */
		min-width: 1.25em;
	}

	.source {
		font-weight: 600;
	}

	.doc-version,
	.kind,
	.figures,
	.applicability,
	.unbacked,
	.entry-location {
		color: var(--colour-text-secondary); /* spelling-ignore */
		font-size: var(--font-size-secondary);
	}

	.kind,
	.unbacked {
		border: 1px solid var(--colour-text-secondary);
		border-radius: 3px;
		padding: 0 0.35em;
	}

	.entry-location {
		font-family: monospace;
	}

	.open {
		color: var(--colour-accent); /* spelling-ignore */
	}

	.open:focus-visible {
		outline: 2px solid var(--colour-focus-ring);
		outline-offset: 1px;
	}

	button {
		background: var(--colour-surface);
		color: var(--colour-text); /* spelling-ignore */
		font-size: var(--font-size-secondary);
		border: 1px solid var(--colour-text-secondary);
		border-radius: 4px;
		padding: 0.1em 0.5em;
	}

	button:focus-visible {
		outline: 2px solid var(--colour-focus-ring);
		outline-offset: 1px;
	}

	/* 5.6: the source's own words, visually distinguishable from summary text. */
	.passage {
		flex-basis: 100%;
		margin: 0.25em 0 0;
		border-inline-start: 3px solid var(--colour-accent);
		padding-inline-start: 0.75em;
		font-style: italic;
	}

	.passage-text {
		margin: 0;
		white-space: pre-line;
	}

	.degraded-mark,
	.passage-unavailable,
	.passage-working {
		flex-basis: 100%;
		margin: 0.25em 0 0;
		color: var(--colour-text-secondary); /* spelling-ignore */
		font-size: var(--font-size-secondary);
	}
</style>
