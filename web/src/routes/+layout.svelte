<script lang="ts">
	import '$lib/tokens.css';
	import favicon from '$lib/assets/favicon.svg';

	let { children } = $props();
</script>

<svelte:head>
	<link rel="icon" href={favicon} />
</svelte:head>

{@render children()}

<style>
	/* The tokens file declares values; the shell applies them (11.3, 11.5). */
	:global(body) {
		margin: 0;
		background: var(--colour-bg);
		color: var(--colour-text); /* spelling-ignore */
		font-family: system-ui, sans-serif;
		font-size: var(--font-size-body);
	}
</style>
