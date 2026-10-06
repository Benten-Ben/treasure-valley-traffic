import { defineConfig } from '@playwright/test';
import { join } from 'node:path';
import { CHROMIUM_ARGS, harnessEnv } from './scripts/harness-env.mjs';

/**
 * End-to-end specs (docs/14 §14.11): Chromium (SwiftShader) against a
 * production build under `vite preview` on the package's port, with the
 * package environment from §14.10 "Rules" (scripts/harness-env.mjs): its own
 * database clone, seeded frames and fake archive, TVT_FRAME_SOURCE=fixture.
 *
 * Tag specs with their package (`{ tag: '@wp3' }`) and run one package's with
 * `npm run test:e2e -- --grep @wp3`. The reporter prints how many ran,
 * passed and were skipped, overall and per tag.
 *
 * In the workflow (a wp/WPn branch or TVT_WP), TVT_E2E_REQUIRE_DATA=1 makes
 * missing data (manifest, frames, archive, database) fail a spec; outside it,
 * such specs skip with a message.
 */
const env = harnessEnv();
// Specs and helpers read the same values from process.env.
Object.assign(process.env, env);
const port = Number(env.TVT_PORT);
const runDir = join(env.TVT_MAIN, 'data', 'dev', env.TVT_WP || 'local');

export default defineConfig({
	testDir: 'tests/e2e',
	outputDir: join(runDir, 'test-results'),
	// SwiftShader renders the map on the CPU: be generous.
	timeout: 240_000,
	expect: { timeout: 30_000 },
	workers: 1,
	fullyParallel: false,
	retries: 0,
	forbidOnly: true,
	reporter: [['list'], ['./tests/e2e/reporter.ts']],
	use: {
		baseURL: `http://127.0.0.1:${port}`,
		browserName: 'chromium',
		viewport: { width: 1280, height: 800 },
		launchOptions: { args: CHROMIUM_ARGS },
		actionTimeout: 60_000,
		navigationTimeout: 120_000,
		trace: 'retain-on-failure',
		screenshot: 'only-on-failure'
	},
	webServer: {
		command: 'node scripts/e2e-server.mjs',
		url: `http://127.0.0.1:${port}/api/health`,
		reuseExistingServer: false,
		timeout: 600_000,
		env: env as Record<string, string>,
		stdout: 'pipe',
		stderr: 'pipe'
	}
});
