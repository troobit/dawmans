<!--
	The diagnostic disclosure (requirement 9.3). Renders exactly the engine's
	`detail`, `framing` and `timings` plus this surface's per-turn marks —
	nothing else, and nothing parsed out of `detail`, which CONTRACTS §4
	declares unparsed. No request body is ever echoed, which is what keeps
	9.17 structural: a credential is never in a value this component reaches.
-->
<script lang="ts">
	import type { Turn } from '../engine/turn.svelte';
	import { measures } from '../state/perf.svelte';

	let { turn }: { turn: Turn } = $props();

	const measured = $derived(measures(turn.marks));
</script>

<details class="diagnostics">
	<summary>Diagnostics</summary>
	<dl>
		{#if turn.envelope.detail !== undefined}
			<dt>detail</dt>
			<dd>{turn.envelope.detail}</dd>
		{/if}
		{#if turn.envelope.framing !== undefined}
			<dt>framing</dt>
			<dd>{turn.envelope.framing}</dd>
		{/if}
		{#if turn.envelope.timings !== undefined}
			<dt>timings</dt>
			<dd>
				{Object.entries(turn.envelope.timings)
					.map(([stage, ms]) => `${stage}: ${ms}`)
					.join(', ')}
			</dd>
		{/if}
		<dt>marks</dt>
		<dd>
			submit: {turn.marks.submit.toFixed(1)}{#if turn.marks.firstByte !== undefined},
				firstByte: {turn.marks.firstByte.toFixed(1)}{/if}{#if turn.marks.firstPaint !== undefined},
				firstPaint: {turn.marks.firstPaint.toFixed(1)}{/if}
			{#if measured.submitToFirstPaint !== undefined}
				(submit→paint {measured.submitToFirstPaint.toFixed(1)} ms, byte→paint {measured.firstByteToFirstPaint?.toFixed(
					1
				)} ms)
			{/if}
		</dd>
	</dl>
</details>

<style>
	.diagnostics {
		color: var(--colour-text-secondary); /* spelling-ignore */
		font-size: var(--font-size-secondary);
	}

	summary {
		cursor: pointer;
	}

	summary:focus-visible {
		outline: 2px solid var(--colour-focus-ring);
		outline-offset: 1px;
	}

	dl {
		margin: 0;
		padding-inline-start: 1em;
	}

	dt {
		font-weight: 600;
	}

	dd {
		margin: 0 0 0.5em;
		/* The engine's own wording, shown as-is — including line breaks. */
		white-space: pre-wrap;
		overflow-wrap: anywhere;
	}
</style>
