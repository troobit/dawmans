<!--
	The working indicator (requirements 8.2, 8.5, 8.10, 13.6; Decisions 2 and
	7). Shown while the active turn awaits its first content, and mounted below
	the thread so its removal cannot shift painted text. Unmistakably live by
	animation in the default case; under reduced motion, by an elapsed-seconds
	counter paired with the static shape — live without motion. Past the
	per-provider-class threshold, plain "taking longer than usual" text and a
	cancel control appear beside it (8.5); a cancel returns to ready with the
	question preserved (8.6).

	The counter sits outside the 13.5 announcement region, so it never
	announces each tick (Decision 7).
-->
<script lang="ts">
	import { SLOW_THRESHOLD_MS, type ProviderClass } from '../state/perf.svelte';
	import { thread as defaultThread, type ThreadStore } from '../state/thread.svelte';

	/** 13.6: the OS preference, read once — a static default, overridable for tests. */
	function prefersReducedMotion(): boolean {
		return (
			typeof window !== 'undefined' &&
			typeof window.matchMedia === 'function' &&
			window.matchMedia('(prefers-reduced-motion: reduce)').matches
		);
	}

	let {
		thread = defaultThread,
		providerClass = 'hosted',
		reducedMotion = prefersReducedMotion()
	}: {
		thread?: ThreadStore;
		providerClass?: ProviderClass;
		reducedMotion?: boolean;
	} = $props();

	/**
	 * 8.2 is about the wait for first content: once content exists, the
	 * arriving text itself is the liveness and the indicator leaves (design
	 * "The turn, client-side").
	 */
	const waitingTurn = $derived(
		thread.active !== null && thread.active.marks.firstByte === undefined ? thread.active : null
	);
	const waiting = $derived(waitingTurn !== null);

	let elapsed = $state(0);

	// Keyed on the turn itself, not the boolean: a follow-up submitted while the
	// previous turn was still waiting keeps `waiting` true, and the 8.10
	// threshold must be measured from the new turn's submission.
	$effect(() => {
		if (waitingTurn === null) return;
		elapsed = 0;
		const interval = setInterval(() => {
			elapsed += 1;
		}, 1000);
		return () => clearInterval(interval);
	});

	/** 8.5/8.10: past this class's threshold, the wait is worth remarking on. */
	const slow = $derived(elapsed * 1000 >= SLOW_THRESHOLD_MS[providerClass]);

	/** 8.6: back to ready, question preserved, partial output never presented as finished. */
	function cancel(): void {
		const question = thread.active?.question ?? '';
		thread.stop();
		if (thread.draft === '') thread.draft = question;
	}
</script>

{#if waiting}
	<div class="working-indicator">
		<!-- 8.4's shape channel; animated only where motion is welcome (13.6). -->
		<span
			class="state-shape"
			data-state="working"
			data-animated={reducedMotion ? undefined : 'true'}
			aria-hidden="true">●</span
		>
		{#if reducedMotion}
			<!-- Decision 7: an incrementing number is unmistakably live without motion. -->
			<span class="elapsed">{elapsed} s</span>
		{/if}
		<span class="label">Working…</span>
		{#if slow}
			<span class="slow">Taking longer than usual.</span>
			<button type="button" onclick={cancel}>Cancel</button>
		{/if}
	</div>
{/if}

<style>
	.working-indicator {
		display: flex;
		align-items: center; /* spelling-ignore */
		gap: var(--space-s, 0.5rem);
		color: var(--colour-text-secondary); /* spelling-ignore */
		font-size: var(--font-size-control);
	}

	.state-shape {
		color: var(--colour-state-working); /* spelling-ignore */
	}

	[data-animated='true'] {
		/* The one animation this surface owns beside arriving text (11.9). */
		animation: pulse 1.2s ease-in-out infinite;
	}

	@keyframes pulse {
		0%,
		100% {
			opacity: 1;
		}
		50% {
			opacity: 0.25;
		}
	}

	.elapsed {
		/* Tabular digits: the ticking number never shifts its neighbours. */
		font-variant-numeric: tabular-nums;
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
