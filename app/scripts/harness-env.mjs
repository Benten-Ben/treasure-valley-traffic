#!/usr/bin/env node
/**
 * The per-package environment for the UI v2 build (docs/14 §14.10, "Rules").
 *
 * Every package works in its own git worktree, on its own database clone and
 * dev port, with its own copies of the seeded frames and fake archive. This
 * module works all of that out from wherever it runs, so the same commands
 * work in the main checkout and in any worktree:
 *
 *   MAIN        the main checkout (the parent of git's common dir), or TVT_MAIN
 *   WP          the package: TVT_WP, else the branch name (wp/WP3, wp/WP3-2 → wp3)
 *   PORT        5201 + the package number (TVT_PORT overrides)
 *   TILES_DIR   $MAIN/data/tiles (read only)
 *   FRAMES_DIR  $MAIN/data/dev/<wp>/frames   (copied from the templates by `npm run seed`)
 *   TVT_ARCHIVE $MAIN/data/dev/<wp>/archive  (likewise)
 *   DATABASE_URL postgres://tvt:<password>@localhost/tvt_<wp>
 *   TVT_FRAME_SOURCE=fixture, CAMERA_IMAGES_ENABLED=true, TVT_E2E_REQUIRE_DATA=1
 *
 * Anything already set in the environment wins, so a run can point one
 * variable elsewhere (for example TILES_DIR at an empty folder).
 *
 * The local database password is never committed: it comes from
 * TVT_DB_PASSWORD or PGPASSWORD, or from $MAIN/data/dev/harness.env
 * (git-ignored, one KEY=value per line).
 *
 * Usage:
 *   import { harnessEnv } from './harness-env.mjs';
 *   node scripts/harness-env.mjs [wp] [--shell]   # print it (as export lines with --shell)
 *   node scripts/harness-env.mjs [wp] -- vite dev --port {port}   # run a command with it
 *   source scripts/env.sh [wp]                    # export it into the current shell
 *   npm run dev:wp / npm run preview:wp           # the dev or preview server on the package port
 */
import { execFileSync } from 'node:child_process';
import { existsSync, readFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

export const APP_DIR = resolve(dirname(fileURLToPath(import.meta.url)), '..');

/** Chromium flags for WebGL in headless runs (SwiftShader; the sandbox has no GPU). */
export const CHROMIUM_ARGS = ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'];

function git(args, cwd) {
	try {
		return execFileSync('git', args, { cwd, encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] }).trim();
	} catch {
		return '';
	}
}

/** The main checkout: git's common dir is <main>/.git in every worktree. */
export function mainCheckout(cwd = APP_DIR) {
	if (process.env.TVT_MAIN) return resolve(process.env.TVT_MAIN);
	const common = git(['rev-parse', '--path-format=absolute', '--git-common-dir'], cwd);
	return common ? dirname(common) : resolve(APP_DIR, '..');
}

/** 'wp3' from TVT_WP or a branch named wp/WP3 (or wp/WP3-2); null outside the workflow. */
export function packageName(cwd = APP_DIR) {
	const explicit = process.env.TVT_WP;
	if (explicit) return explicit.toLowerCase();
	const branch = git(['branch', '--show-current'], cwd);
	const m = /^wp\/WP(\d+)(?:-\d+)?$/i.exec(branch);
	return m ? `wp${Number(m[1])}` : null;
}

/** Dev and preview port: 5201 + the package number; 5200 outside the workflow. */
export function packagePort(wp) {
	if (process.env.TVT_PORT) return Number(process.env.TVT_PORT);
	const n = wp ? Number(/^wp(\d+)$/.exec(wp)?.[1]) : NaN;
	return Number.isInteger(n) ? 5201 + n : 5200;
}

/** KEY=value lines from $MAIN/data/dev/harness.env, if it exists. */
export function localSettings(main) {
	const file = join(main, 'data', 'dev', 'harness.env');
	const out = {};
	if (!existsSync(file)) return out;
	for (const line of readFileSync(file, 'utf8').split('\n')) {
		const m = /^\s*([A-Z_][A-Z0-9_]*)\s*=\s*(.*?)\s*$/.exec(line);
		if (m) out[m[1]] = m[2].replace(/^(['"])(.*)\1$/, '$2');
	}
	return out;
}

export function dbPassword(main) {
	return process.env.TVT_DB_PASSWORD || process.env.PGPASSWORD || localSettings(main).TVT_DB_PASSWORD || '';
}

/** A connection URL for one local database, using the local password. */
export function databaseUrl(name, main = mainCheckout()) {
	const pw = dbPassword(main);
	const auth = pw ? `tvt:${encodeURIComponent(pw)}` : 'tvt';
	const host = process.env.TVT_DB_HOST || 'localhost';
	return `postgres://${auth}@${host}/${name}`;
}

/**
 * The package environment. `wp` overrides the detected package. Values already
 * in process.env are kept.
 */
export function harnessEnv({ wp = packageName(), env = process.env } = {}) {
	const main = mainCheckout();
	const workflow = Boolean(wp);
	const devDir = join(main, 'data', 'dev', wp ?? 'local');
	const port = packagePort(wp);
	const pick = (key, fallback) => (env[key] !== undefined && env[key] !== '' ? env[key] : fallback);
	const out = {
		TVT_MAIN: main,
		TVT_WP: wp ?? '',
		TVT_PORT: String(port),
		TILES_DIR: resolve(pick('TILES_DIR', join(main, 'data', 'tiles'))),
		FRAMES_DIR: resolve(pick('FRAMES_DIR', join(devDir, 'frames'))),
		TVT_ARCHIVE: resolve(pick('TVT_ARCHIVE', join(devDir, 'archive'))),
		DATABASE_URL: pick('DATABASE_URL', databaseUrl(wp ? `tvt_${wp}` : 'tvt', main)),
		TVT_FRAME_SOURCE: pick('TVT_FRAME_SOURCE', 'fixture'),
		CAMERA_IMAGES_ENABLED: pick('CAMERA_IMAGES_ENABLED', 'true'),
		PLAYWRIGHT_BROWSERS_PATH: pick('PLAYWRIGHT_BROWSERS_PATH', '/opt/pw-browsers'),
		TVT_SCREENS: resolve(pick('TVT_SCREENS', join(main, 'data', 'dev', 'screens', wp ?? 'local'))),
		TVT_TEMPLATES: resolve(pick('TVT_TEMPLATES', join(main, 'data', 'dev', 'templates')))
	};
	// In the workflow, missing data fails a run; outside it, specs skip with a message.
	const require = pick('TVT_E2E_REQUIRE_DATA', workflow ? '1' : '');
	if (require) out.TVT_E2E_REQUIRE_DATA = require;
	return out;
}

const shellQuote = (v) => `'${String(v).replaceAll("'", `'\\''`)}'`;

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
	const all = process.argv.slice(2);
	const dash = all.indexOf('--');
	const args = dash === -1 ? all : all.slice(0, dash);
	const command = dash === -1 ? [] : all.slice(dash + 1);
	const wp = args.find((a) => !a.startsWith('--'));
	const env = harnessEnv(wp ? { wp: wp.toLowerCase() } : {});
	if (command.length) {
		// Run a command with the environment, no shell: `{port}` in an argument becomes the port.
		const { spawn } = await import('node:child_process');
		const argv = command.map((a) => a.replaceAll('{port}', env.TVT_PORT));
		const child = spawn(argv[0], argv.slice(1), { stdio: 'inherit', env: { ...process.env, ...env } });
		for (const sig of ['SIGINT', 'SIGTERM']) process.on(sig, () => child.kill(sig));
		child.on('exit', (code, signal) => process.exit(code ?? (signal ? 1 : 0)));
	} else {
		for (const [k, v] of Object.entries(env)) {
			if (args.includes('--shell')) console.log(`export ${k}=${shellQuote(v)}`);
			else console.log(`${k}=${k === 'DATABASE_URL' ? v.replace(/:[^:@/]+@/, ':***@') : v}`);
		}
	}
}
