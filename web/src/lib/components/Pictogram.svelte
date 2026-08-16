<!--
	One pictogram (requirements 2.14, 11.6). Stroked in `currentColor` so it
	takes whatever colour the surrounding state has already decided — the
	component declares no colour of its own (Decision 6) — and always
	`aria-hidden`, because every pictogram sits beside its own words and must
	never become the accessible name (13.4) or the only channel (11.6).
-->
<script lang="ts">
	import { PICTOGRAM_PATHS, type PictogramName } from './pictograms';

	let { name, size = '1.5rem' }: { name: PictogramName; size?: string } = $props();
</script>

<svg
	class="pictogram"
	viewBox="0 0 24 24"
	width={size}
	height={size}
	aria-hidden="true"
	focusable="false"
>
	{#each PICTOGRAM_PATHS[name] as d, index (index)}
		<path {d} />
	{/each}
</svg>

<style>
	.pictogram {
		fill: none;
		stroke: currentColor;
		stroke-width: 1.6;
		stroke-linecap: round;
		stroke-linejoin: round;
		flex: none;
	}
</style>
