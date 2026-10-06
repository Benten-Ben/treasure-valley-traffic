#!/usr/bin/env node
/**
 * The server the e2e specs run against (docs/14 §14.11): a production build
 * under `vite preview` on the package's port, with the package environment
 * (harness-env.mjs) and the tiles server mirroring Caddy.
 *
 * Builds first when the build is missing or older than the sources
 * (TVT_E2E_BUILD=1 forces a build, TVT_E2E_BUILD=0 never builds).
 *
 *   node scripts/e2e-server.mjs [--port N]
 */
import { spawnSync, spawn } from 'node:child_process';
import { existsSync, readdirSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { APP_DIR, harnessEnv } from './harness-env.mjs';

const env = { ...process.env, ...harnessEnv() };
const i = process.argv.indexOf('--port');
const port = i === -1 ? env.TVT_PORT : process.argv[i + 1];
const built = join(APP_DIR, '.svelte-kit', 'output', 'server', 'index.js');

function newest(path) {
	const s = statSync(path);
	if (!s.isDirectory()) return s.mtimeMs;
	let m = s.mtimeMs;
	for (const name of readdirSync(path)) m = Math.max(m, newest(join(path, name)));
	return m;
}

function stale() {
	if (env.TVT_E2E_BUILD === '1') return true;
	if (env.TVT_E2E_BUILD === '0') return false;
	if (!existsSync(built)) return true;
	const out = statSync(built).mtimeMs;
	const inputs = ['src', 'static', 'vite.config.ts', 'package.json', 'svelte.config.js']
		.map((p) => join(APP_DIR, p))
		.filter(existsSync);
	return inputs.some((p) => newest(p) > out);
}

if (stale()) {
	console.log('e2e-server: building (sources changed since the last build)');
	const r = spawnSync('npx', ['vite', 'build'], { cwd: APP_DIR, env, stdio: 'inherit' });
	if (r.status !== 0) process.exit(r.status ?? 1);
}

console.log(`e2e-server: vite preview on ${port} (DATABASE_URL → ${env.DATABASE_URL.replace(/^.*\//, '')}, ` +
	`TILES_DIR ${env.TILES_DIR}, TVT_FRAME_SOURCE=${env.TVT_FRAME_SOURCE})`);
const child = spawn('npx', ['vite', 'preview', '--port', String(port), '--strictPort', '--host', '127.0.0.1'], {
	cwd: APP_DIR,
	env,
	stdio: 'inherit'
});
for (const sig of ['SIGINT', 'SIGTERM']) process.on(sig, () => child.kill(sig));
child.on('exit', (code) => process.exit(code ?? 0));
