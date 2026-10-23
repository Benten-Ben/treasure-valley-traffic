#!/usr/bin/env node
/**
 * A tiles folder for the browser specs that need baked landscape contributions or a painted ground, which the
 * laptop's data/tiles holds neither of (plan v3 §4.1: fixtures are synthetic).
 *
 * It makes a work folder holding
 *   - a symlink to every file and folder in the harness's TILES_DIR (the real tiles, read only),
 *   - the synthetic landscape file and ground files (basemap/landscape/fixture.py), and
 *   - a manifest.json that is the real one with the fixture's `landscape` and `ground` entries put in
 *     (every other entry is kept as it is),
 * and prints the folder. Nothing in TILES_DIR is changed.
 *
 *   TILES_DIR=$(node scripts/tiles-fixture.mjs --ground painted) npm run test:e2e -- --grep @water
 *
 *   --ground painted|flat|none   the ground entry: painted (the default), a flat one with a reason, or none (the
 *                                real manifest's ground entry, if any, is left alone)
 *   --out DIR                    the work folder (default: <main>/data/dev/tiles-fixture/<ground>)
 *
 * The harness lets an environment value win over its own default (harness-env.mjs), so TILES_DIR points the
 * app and the specs at the work folder. Run it again after changing a file in basemap/landscape/fixtures/.
 */
import { spawnSync } from 'node:child_process';
import { existsSync, mkdirSync, readFileSync, readdirSync, rmSync, symlinkSync, writeFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { APP_DIR, harnessEnv, mainCheckout, localSettings, packageName } from './harness-env.mjs';

const MARKER = '.tiles-fixture';
const GROUNDS = ['painted', 'flat', 'none'];

function parse(argv) {
	const out = { ground: 'painted', out: '' };
	for (let i = 0; i < argv.length; i++) {
		const a = argv[i];
		if (a === '--ground') out.ground = argv[++i] ?? '';
		else if (a === '--out') out.out = argv[++i] ?? '';
		else if (a === '-h' || a === '--help') out.help = true;
		else throw new Error(`unknown argument ${a}`);
	}
	if (!GROUNDS.includes(out.ground)) throw new Error(`--ground is one of ${GROUNDS.join(', ')}`);
	return out;
}

function main() {
	const args = parse(process.argv.slice(2));
	if (args.help) {
		console.error(readFileSync(new URL(import.meta.url), 'utf8').split('*/')[0].replace(/^\/\*\*|^ \* ?/gm, ''));
		return;
	}
	const main = mainCheckout();
	const tiles = harnessEnv().TILES_DIR;
	const work = resolve(args.out || join(main, 'data', 'dev', packageName() ?? 'local', 'tiles-fixture', args.ground));
	if (work === tiles) throw new Error('the work folder is TILES_DIR itself');

	// Only a folder this script made (or an empty one) is cleared.
	if (existsSync(work)) {
		if (readdirSync(work).length && !existsSync(join(work, MARKER))) {
			throw new Error(`${work} exists and wasn't made by this script; give another --out`);
		}
		rmSync(work, { recursive: true, force: true });
	}
	mkdirSync(work, { recursive: true });
	writeFileSync(join(work, MARKER), 'made by app/scripts/tiles-fixture.mjs; safe to delete\n');

	const python = process.env.TVT_PYTHON || localSettings(main).TVT_PYTHON || 'python3';
	const run = spawnSync(python, ['-m', 'basemap.landscape.fixture', '--out', work, '--ground', args.ground], {
		cwd: resolve(APP_DIR, '..'),
		stdio: ['ignore', 2, 2]
	});
	if (run.status !== 0) throw new Error('basemap/landscape/fixture.py failed');
	const entries = JSON.parse(readFileSync(join(work, 'fixture-entries.json'), 'utf8'));

	let manifest = {};
	if (existsSync(join(tiles, 'manifest.json'))) {
		manifest = JSON.parse(readFileSync(join(tiles, 'manifest.json'), 'utf8'));
		for (const name of readdirSync(tiles)) {
			if (name === 'manifest.json' || name.startsWith('.') || existsSync(join(work, name))) continue;
			symlinkSync(join(tiles, name), join(work, name));
		}
	} else {
		console.error(`no manifest.json in ${tiles}: the fixture's entries stand alone`);
	}
	for (const [key, entry] of Object.entries(entries)) manifest[key] = entry;
	writeFileSync(join(work, 'manifest.json'), JSON.stringify(manifest, null, 1) + '\n');
	console.log(work);
}

try {
	main();
} catch (err) {
	console.error(`tiles-fixture: ${err.message}`);
	process.exit(1);
}
