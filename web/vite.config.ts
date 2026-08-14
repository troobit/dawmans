import adapter from '@sveltejs/adapter-static';
import { sveltekit } from '@sveltejs/kit/vite';
import type { ProxyOptions } from 'vite';
import { defineConfig } from 'vitest/config';

// The engine's loopback origin in development. In production the engine serves
// web/build itself, so the page is same-origin and no proxy exists.
const engine = process.env.ENGINE_ORIGIN ?? 'http://127.0.0.1:8000';

// The engine rejects any request whose Origin is outside its own loopback set
// (api/answer-engine 9.3). `changeOrigin: true` rewrites only `Host` and forwards
// the browser's `Origin: http://localhost:5173` unchanged, so the proxy must
// rewrite `Origin` itself or every proxied request is 403 in dev (Decision 1).
const engineProxy: Record<string, ProxyOptions> = Object.fromEntries(
	['/turn', '/passages', '/sources', '/provider'].map((path): [string, ProxyOptions] => [
		path,
		{
			target: engine,
			changeOrigin: true,
			configure(proxy) {
				proxy.on('proxyReq', (proxyReq) => {
					proxyReq.setHeader('origin', engine);
				});
			}
		}
	])
);

export default defineConfig({
	plugins: [
		sveltekit({
			compilerOptions: {
				// Force runes mode for the project, except for libraries. Can be removed in svelte 6.
				runes: ({ filename }) =>
					filename.split(/[/\\]/).includes('node_modules') ? undefined : true
			},

			adapter: adapter()
		})
	],
	server: {
		proxy: engineProxy
	},
	// Component tests mount in jsdom; without the browser condition vitest
	// resolves Svelte's server entry and `mount(...)` is unavailable.
	resolve: process.env.VITEST ? { conditions: ['browser'] } : undefined,
	test: {
		environment: 'jsdom',
		// jsdom only provides Web Storage on a non-opaque origin; without a URL
		// the environment defaults to about:blank and `localStorage` is undefined.
		environmentOptions: { jsdom: { url: 'http://localhost/' } },
		// Node's own experimental storage globals shadow jsdom's; see the setup file.
		setupFiles: ['./vitest-setup.ts'],
		include: ['src/**/*.test.ts']
	}
});
