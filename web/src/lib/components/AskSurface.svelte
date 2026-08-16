<!--
	The ask input, the symptom shortcuts and the submission controls
	(requirements §1, 3.2, 9.15; design "Surfaces", "Keyboard routing and
	arming"). Presentation only: submission goes through the thread store,
	which owns the scope block and the turn state machine; key handling goes
	through the router's registry, never handled here (Decision 5).
-->
<script lang="ts" module>
	/**
	 * 1.10's fixed set: the commonest symptom questions, submitted verbatim.
	 * Position + 1 is the armed digit (1.11).
	 */
	export const SYMPTOM_SHORTCUTS = [
		'no sound',
		'distorting',
		'latency',
		'wrong drum sound'
	] as const;
</script>

<script lang="ts">
	import { keys, type KeyRouter } from '../keys';
	import { scope as defaultScope, type ScopeStore } from '../state/scope.svelte';
	import {
		QUESTION_LIMIT,
		thread as defaultThread,
		type ThreadStore
	} from '../state/thread.svelte';
	import Pictogram from './Pictogram.svelte';
	import { SHORTCUT_PICTOGRAMS } from './pictograms';

	let {
		thread = defaultThread,
		scope = defaultScope,
		router = keys
	}: { thread?: ThreadStore; scope?: ScopeStore; router?: KeyRouter } = $props();

	let textarea: HTMLTextAreaElement | undefined = $state();

	// 1.10: shortcuts render on an empty input at rest — never while a turn is
	// being answered, and never while a narrowing holds the digits, which is
	// what keeps the registry's one-armed-set invariant sound (Decision 5).
	const shortcutsVisible = $derived(
		thread.draft === '' && !thread.busy && !thread.awaitingNarrowing
	);

	// Register the question input with the router: focus target for 1.1 and
	// 1.2's capture; `insert` appends manually because the keydown already
	// happened on another element.
	$effect(() => {
		if (textarea === undefined) return;
		const element = textarea;
		return router.registerInput({
			element,
			focus: () => element.focus(),
			insert: (character) => {
				thread.draft += character;
			}
		});
	});

	// 1.1: focus lands in the input on load without a pointer click.
	$effect(() => {
		textarea?.focus();
	});

	// Arm the shortcut digits while the row is on screen (1.10, 1.11).
	$effect(() => {
		if (!shortcutsVisible) return;
		return router.arm(
			SYMPTOM_SHORTCUTS.map((question) => ({ activate: () => thread.submit(question) }))
		);
	});

	// 1.6: when a turn settles, focus returns to the emptied input — unless an
	// overlay region holds focus (13.3).
	$effect(() => {
		thread.onSettled = () => {
			if (!router.hasOpenRegion) textarea?.focus();
		};
		return () => {
			thread.onSettled = null;
		};
	});

	/** 1.3: unmodified Enter submits; Shift+Enter falls through to a line break. */
	function onKeydown(event: KeyboardEvent) {
		if (event.key !== 'Enter' || event.shiftKey) return;
		event.preventDefault();
		thread.submit();
	}

	/** 1.9 / 8.6: stop, back to a ready state with the question preserved for re-editing. */
	function stop() {
		const question = thread.active?.question ?? '';
		thread.stop();
		if (thread.draft === '') thread.draft = question;
		textarea?.focus();
	}
</script>

<svelte:window onkeydown={router.handleKeydown} onfocus={router.handleWindowFocus} />

<div class="ask">
	{#if thread.isFollowUp}
		<p class="follow-up">
			<span>Follow-up — read in the context of the exchange above.</span>
			<button type="button" onclick={() => thread.clear()}>New question</button>
		</p>
	{/if}

	<textarea
		bind:this={textarea}
		bind:value={thread.draft}
		onkeydown={onKeydown}
		rows="2"
		aria-label="Ask a question"
		placeholder="Ask about your gear…"
	></textarea>

	{#if !scope.canSubmit}
		<!-- 3.2: zero sources in scope blocks submission; one activation fixes it. -->
		<p class="notice" role="status">
			<span>No sources are selected — there is nothing to ask against.</span>
			<button type="button" onclick={() => scope.selectAll()}>Select all sources</button>
		</p>
	{/if}

	{#if thread.overLimit}
		<!-- 9.15: the limit and the typed length, while the question stays editable. -->
		<p class="notice" role="status">
			Questions are limited to {QUESTION_LIMIT} characters; this one is {thread.draft.length}.
		</p>
	{/if}

	{#if thread.busy}
		<button type="button" onclick={stop}>Stop</button>
	{/if}

	{#if shortcutsVisible}
		<!-- 1.10/11.7: the four commonest symptoms as pictures first. The digit
		     and the words are unchanged — the pictogram is aria-hidden, so the
		     accessible name is still "1 no sound" (13.4). -->
		<ul class="shortcuts">
			{#each SYMPTOM_SHORTCUTS as question, index (question)}
				<li>
					<button type="button" class="shortcut" onclick={() => thread.submit(question)}>
						<kbd>{index + 1}</kbd>
						<Pictogram
							name={SHORTCUT_PICTOGRAMS[question] ?? 'book'}
							size="var(--tile-pictogram-inline)"
						/>
						<span class="label">{question}</span>
					</button>
				</li>
			{/each}
		</ul>
	{/if}
</div>

<style>
	.ask {
		display: flex;
		flex-direction: column;
		gap: var(--space-s, 0.5rem);
	}

	textarea {
		background: var(--colour-surface);
		color: var(--colour-text); /* spelling-ignore */
		font-size: var(--font-size-body);
		border: 1px solid var(--colour-text-secondary);
		border-radius: 4px;
		padding: 0.5em;
		resize: vertical;
	}

	textarea:focus-visible {
		outline: 2px solid var(--colour-focus-ring);
		outline-offset: 1px;
	}

	.follow-up,
	.notice {
		font-size: var(--font-size-control);
		color: var(--colour-text); /* spelling-ignore */
		margin: 0;
	}

	/* 2.13's sibling problem on the ask side: four targets that reflow to one
	   column at 640 px rather than overflowing (13.7). */
	.shortcuts {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(min(100%, var(--tile-min-width)), 1fr));
		gap: var(--space-s);
		list-style: none;
		margin: 0;
		padding: 0;
	}

	button {
		background: var(--colour-surface);
		color: var(--colour-text); /* spelling-ignore */
		font-size: var(--font-size-control);
		border: 1px solid var(--colour-text-secondary);
		border-radius: var(--radius);
		padding: 0.25em 0.75em;
		cursor: pointer;
	}

	button:focus-visible {
		outline: 2px solid var(--colour-focus-ring);
		outline-offset: 1px;
	}

	/*
		A symptom is a picture with its digit and its words beside it —
		recognised before it is read (11.7) and hit without aiming, while
		staying a single row tall: the shortcuts share the viewport with the
		answer, and 11.8 measures what is left for the answer.
	*/
	.shortcut {
		display: flex;
		align-items: center; /* spelling-ignore */
		gap: var(--space-s);
		width: 100%;
		height: 100%;
		box-sizing: border-box;
		padding: var(--space-xs) var(--space-s);
		border-radius: var(--radius-tile);
		box-shadow: var(--shadow-tile);
		text-align: start;
		transition: border-color 120ms ease; /* spelling-ignore */
	}

	.shortcut:hover {
		border-color: var(--colour-accent-hover); /* spelling-ignore */
	}

	.shortcut .label {
		font-size: var(--font-size-body);
		overflow-wrap: anywhere;
	}

	kbd {
		/* 1.11's on-screen indication and 11.6's greyscale-safe channel: the digit itself. */
		border: 1px solid var(--colour-text-secondary);
		border-radius: 3px;
		padding: 0 0.35em;
		font-size: var(--font-size-secondary);
		color: var(--colour-text-secondary); /* spelling-ignore */
	}

	.shortcut kbd {
		flex: none;
	}

	@media (prefers-reduced-motion: reduce) {
		.shortcut {
			transition: none;
		}
	}
</style>
