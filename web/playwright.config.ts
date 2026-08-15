// The browser suite (task 47; design "Testing Strategy" → Browser). Two
// processes, exactly the real dev shape (Decision 10): the stub engine behind
// the vite dev server, whose proxy rewrites Origin the way it does against
// the real engine. 1280×800 is the viewport 11.8 measures.

import { defineConfig } from '@playwright/test';

const STUB_PORT = 8788;
const WEB_PORT = 4173;

export default defineConfig({
	testDir: 'e2e',
	timeout: 45_000,
	use: {
		baseURL: `http://localhost:${WEB_PORT}`,
		viewport: { width: 1280, height: 800 }
	},
	projects: [{ name: 'chromium', use: { browserName: 'chromium' } }],
	webServer: [
		{
			command: 'node e2e/stub-engine.mjs',
			port: STUB_PORT,
			reuseExistingServer: !process.env.CI,
			env: { STUB_ENGINE_PORT: String(STUB_PORT) }
		},
		{
			command: `pnpm vite dev --port ${WEB_PORT} --strictPort`,
			port: WEB_PORT,
			reuseExistingServer: !process.env.CI,
			env: { ENGINE_ORIGIN: `http://127.0.0.1:${STUB_PORT}` }
		}
	]
});
