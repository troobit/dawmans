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
		<ul class="shortcuts">
			{#each SYMPTOM_SHORTCUTS as question, index (question)}
				<li>
					<button type="button" onclick={() => thread.submit(question)}>
						<kbd>{index + 1}</kbd>
						{question}
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

	.shortcuts {
		display: flex;
		flex-wrap: wrap;
		gap: var(--space-s, 0.5rem);
		list-style: none;
		margin: 0;
		padding: 0;
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

	kbd {
		/* 1.11's on-screen indication and 11.6's greyscale-safe channel: the digit itself. */
		border: 1px solid var(--colour-text-secondary);
		border-radius: 3px;
		padding: 0 0.35em;
		margin-inline-end: 0.35em;
	}
</style>
