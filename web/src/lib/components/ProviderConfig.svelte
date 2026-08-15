<!--
	The provider configuration region (requirements §10; design "Provider
	configuration"). Kind first: the credential input exists only for the keyed
	hosted kind (10.1), a local provider is configured from its endpoint or
	model alone (10.3), and the shared backend carries its disclosure — shown
	before the first turn, acknowledged explicitly, readable afterwards (10.4).
	Presentation only, over the provider store's five operations; nothing here
	touches the thread or the scope, which is what keeps 10.2 and 10.11 free.
-->
<script lang="ts">
	import { provider as defaultProvider, type ProviderStore } from '../state/provider.svelte';

	let {
		provider = defaultProvider,
		onclose = undefined
	}: { provider?: ProviderStore; onclose?: (() => void) | undefined } = $props();

	// The kind being configured; falls back to the engine's reported kind so
	// the surface opens on what is actually configured (10.7).
	let chosenKind = $state<string | null>(null);
	let model = $state('');
	// 10.6: always empty on open, never pre-populated, cleared after saving.
	let key = $state('');
	let reveal = $state(false);
	let testResult = $state<string | null>(null);

	const kind = $derived(chosenKind ?? provider.status?.kind ?? null);
	const status = $derived(provider.status);

	async function save() {
		if (kind === null) return;
		if (kind === 'local' && model.trim() === '') return; // 10.3: an endpoint or model is the configuration
		await provider.choose(kind, model.trim() !== '' ? model.trim() : undefined);
		// 10.4: the disclosure holds the surface open until acknowledged; every
		// other save returns to the ask surface, question and scope untouched (10.11).
		if (kind === 'shared-backend' && !provider.disclosureAcknowledged) return;
		onclose?.();
	}

	async function saveKey() {
		if (key === '') return;
		await provider.saveCredential(key);
		key = ''; // 10.6: the engine's masked tail is the only representation left
	}

	async function runTest() {
		try {
			const result = await provider.test();
			testResult = result.reachable ? 'Reachable as configured.' : 'Not reachable as configured.';
		} catch {
			testResult = 'The engine could not be reached to run the check.';
		}
	}
</script>

<section class="config" aria-label="Provider configuration">
	<!-- 10.7: the engine's reported status — kind, provider, masked tail at most. -->
	<p class="status">
		{#if status?.kind != null}
			Configured: {status.kind}{status.model !== undefined ? ` — ${status.model}` : ''}{status.masked !== null
				? `, key ${status.masked}`
				: ''}
		{:else}
			No provider configured.
		{/if}
	</p>

	<fieldset>
		<legend>Provider kind</legend>
		<label>
			<input
				type="radio"
				name="provider-kind"
				value="keyed-hosted"
				checked={kind === 'keyed-hosted'}
				onchange={() => {
					chosenKind = 'keyed-hosted';
				}}
			/>
			Hosted with your key
		</label>
		<label>
			<input
				type="radio"
				name="provider-kind"
				value="local"
				checked={kind === 'local'}
				onchange={() => {
					chosenKind = 'local';
				}}
			/>
			Local model on this machine
		</label>
		<label>
			<input
				type="radio"
				name="provider-kind"
				value="shared-backend"
				checked={kind === 'shared-backend'}
				onchange={() => {
					chosenKind = 'shared-backend';
				}}
			/>
			Shared backend
		</label>
	</fieldset>

	{#if kind === 'keyed-hosted'}
		<div class="credential">
			<label>
				API key
				<!-- 10.5: masked by default; the reveal below is momentary, not a latch. -->
				<input type={reveal ? 'text' : 'password'} bind:value={key} autocomplete="off" />
			</label>
			<button
				type="button"
				onmousedown={() => {
					reveal = true;
				}}
				onmouseup={() => {
					reveal = false;
				}}
				onmouseleave={() => {
					reveal = false;
				}}
				onkeydown={(event) => {
					if (event.key === ' ' || event.key === 'Enter') reveal = true;
				}}
				onkeyup={() => {
					reveal = false;
				}}
			>
				Reveal while held
			</button>
			<button type="button" onclick={saveKey}>Save key</button>
			<button type="button" onclick={() => provider.clearKey()}>Clear key</button>
		</div>
	{:else if kind === 'local'}
		<label class="model">
			Endpoint or model
			<input type="text" bind:value={model} />
		</label>
	{:else if kind === 'shared-backend'}
		<div class="disclosure">
			<!-- 10.4: readable before the first turn and after acknowledgement alike. -->
			<p>
				Question text and retrieved passages leave this machine when the shared backend answers.
			</p>
			{#if provider.disclosureAcknowledged}
				<p class="acknowledged">Acknowledged for this backend.</p>
			{:else}
				<button type="button" onclick={() => provider.acknowledgeDisclosure()}>
					Acknowledge — questions may leave this machine
				</button>
			{/if}
		</div>
	{/if}

	<div class="actions">
		<button type="button" onclick={save}>Save</button>
		<button type="button" onclick={runTest}>Test provider</button>
	</div>

	{#if testResult !== null}
		<p class="test-result" role="status">{testResult}</p>
	{/if}
</section>

<style>
	.config {
		display: flex;
		flex-direction: column;
		gap: var(--space-s, 0.5rem);
	}

	.status,
	.test-result,
	.disclosure p {
		margin: 0;
		font-size: var(--font-size-control);
		color: var(--colour-text); /* spelling-ignore */
	}

	.acknowledged {
		color: var(--colour-text-secondary); /* spelling-ignore */
	}

	fieldset {
		border: 1px solid var(--colour-text-secondary);
		border-radius: 4px;
		display: flex;
		flex-direction: column;
		gap: var(--space-xs, 0.25rem);
		font-size: var(--font-size-control);
		color: var(--colour-text); /* spelling-ignore */
	}

	legend {
		color: var(--colour-text-secondary); /* spelling-ignore */
		font-size: var(--font-size-secondary);
		padding: 0 0.35em;
	}

	label {
		font-size: var(--font-size-control);
		color: var(--colour-text); /* spelling-ignore */
	}

	input[type='text'],
	input[type='password'] {
		background: var(--colour-surface);
		color: var(--colour-text); /* spelling-ignore */
		font-size: var(--font-size-control);
		border: 1px solid var(--colour-text-secondary);
		border-radius: 4px;
		padding: 0.25em 0.5em;
		margin-inline-start: 0.5em;
	}

	.credential,
	.actions {
		display: flex;
		align-items: center;
		gap: var(--space-s, 0.5rem);
		flex-wrap: wrap;
	}

	button {
		background: var(--colour-surface);
		color: var(--colour-text); /* spelling-ignore */
		font-size: var(--font-size-control);
		border: 1px solid var(--colour-text-secondary);
		border-radius: 4px;
		padding: 0.25em 0.75em;
	}

	button:focus-visible,
	input:focus-visible {
		outline: 2px solid var(--colour-focus-ring);
		outline-offset: 1px;
	}
</style>
