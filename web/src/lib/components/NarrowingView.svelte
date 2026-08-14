<!--
	The narrowing renderer (requirements 6.1–6.5, 6.8; design "Narrowing and
	ranked causes"). The question and its 2–4 candidates render in the engine's
	order, each a numbered, separately activatable control; selection submits a
	follow-up turn in the current thread against the unchanged scope, and the
	turn stays painted so the question and the chosen candidate remain visible.

	The digits go through the router's arming registry, never a component
	handler (Decision 5): they arm only while this list is the thread's last
	settled turn, so the registry's one-armed-set invariant holds against the
	symptom shortcuts, and a free-text reply (6.5) falls out of the router's
	printable capture at no cost here. The question paints as soon as its event
	arrives — nothing below waits for `done` (6.8).
-->
<script lang="ts">
	import type { Turn } from '../engine/turn.svelte';
	import { keys, type KeyRouter } from '../keys';
	import { thread as defaultThread, type ThreadStore } from '../state/thread.svelte';

	let {
		turn,
		thread = defaultThread,
		router = keys
	}: { turn: Turn; thread?: ThreadStore; router?: KeyRouter } = $props();

	const candidates = $derived(turn.envelope.narrowing?.candidates ?? []);

	// 6.3: armed while the list awaits selection — the thread's last settled
	// turn. A submitted follow-up makes another turn last, which disarms.
	const armed = $derived(
		thread.awaitingNarrowing && thread.turns.at(-1) === turn && candidates.length > 0
	);

	$effect(() => {
		if (!armed) return;
		return router.arm(
			candidates.map((candidate) => ({ activate: () => thread.submit(candidate) }))
		);
	});
</script>

<div class="narrowing" role="group" aria-label="Narrowing question">
	{#if turn.envelope.narrowing !== undefined}
		<p class="narrowing-question">{turn.envelope.narrowing.question}</p>
		<!-- 6.2: numbered in the engine's order — never reordered, merged or added to. -->
		<ol class="candidates">
			{#each candidates as candidate, index (index)}
				<li>
					<button type="button" onclick={() => thread.submit(candidate)}>
						{#if armed}
							<!-- 1.11's on-screen arming indication; the digit itself survives greyscale (11.6). -->
							<kbd>{index + 1}</kbd>
						{:else}
							<span class="number">{index + 1}</span>
						{/if}
						{candidate}
					</button>
				</li>
			{/each}
		</ol>
	{/if}
</div>

<style>
	.narrowing {
		display: flex;
		flex-direction: column;
		gap: var(--space-s, 0.5rem);
		/* 6.1: distinct from an answer — a question the surface is asking back. */
		border-inline-start: 3px solid var(--colour-accent);
		padding-inline-start: 0.75em;
	}

	.narrowing-question {
		color: var(--colour-text); /* spelling-ignore */
		font-size: var(--font-size-body);
		font-weight: 600;
		margin: 0;
	}

	.candidates {
		list-style: none;
		margin: 0;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: var(--space-s, 0.5rem);
	}

	button {
		background: var(--colour-surface);
		color: var(--colour-text); /* spelling-ignore */
		font-size: var(--font-size-control);
		border: 1px solid var(--colour-text-secondary);
		border-radius: 4px;
		padding: 0.25em 0.75em;
		text-align: left;
	}

	button:focus-visible {
		outline: 2px solid var(--colour-focus-ring);
		outline-offset: 1px;
	}

	kbd {
		border: 1px solid var(--colour-text-secondary);
		border-radius: 3px;
		padding: 0 0.35em;
		margin-inline-end: 0.35em;
	}

	.number {
		padding: 0 0.35em;
		margin-inline-end: 0.35em;
	}
</style>
