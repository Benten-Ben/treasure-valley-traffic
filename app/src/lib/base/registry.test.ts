import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { ANCHORS, DRAPED_TYPES } from '#lib/map/order.js';
import { BASE_CONTRIBUTIONS, baseContribution } from './registry.js';

const BASE_DIR = new URL('.', import.meta.url).pathname;

/** Every `*.base.ts` under `#lib/base/<plugin>/`. */
function baseFiles(): string[] {
	const out: string[] = [];
	for (const plugin of readdirSync(BASE_DIR)) {
		const dir = join(BASE_DIR, plugin);
		if (!statSync(dir).isDirectory()) continue;
		for (const f of readdirSync(dir)) if (f.endsWith('.base.ts')) out.push(join(dir, f));
	}
	return out;
}

describe('the base registry', () => {
	it('keeps the scene chunk out of the base layers: no *.base.ts (or what it sits beside) imports #lib/scene', () => {
		// (docs/14 §14.9: the scene chunk is 40 KB and loads only for the 3D layers.)
		const files = [...baseFiles(), join(BASE_DIR, 'types.ts'), join(BASE_DIR, 'registry.ts')];
		expect(files.length).toBeGreaterThanOrEqual(2);
		for (const f of files) {
			const src = readFileSync(f, 'utf8');
			expect(src, f).not.toMatch(/(?:from|import)\s*\(?\s*['"](?:#lib\/scene|(?:\.\.?\/)+scene)(?:[/.'"])/);
		}
	});

	it('checks the rule on the pattern itself', () => {
		const re = /(?:from|import)\s*\(?\s*['"](?:#lib\/scene|(?:\.\.?\/)+scene)(?:[/.'"])/;
		expect("import { x } from '#lib/scene/index.js';").toMatch(re);
		expect("const m = await import('#lib/scene');").toMatch(re);
		expect("import { x } from '../../scene/models.js';").toMatch(re);
		expect("import { x } from '#lib/map/materials.js';").not.toMatch(re);
		expect("import { x } from '#lib/layers/scenery.js';").not.toMatch(re);
	});

	it('holds no contribution yet; later packages add theirs as folders', () => {
		expect(BASE_CONTRIBUTIONS).toEqual([]);
		expect(baseContribution('roads.surfaces')).toBeUndefined();
	});

	it('is well formed for whatever is registered: ids, unique layers, draped types, known slots', () => {
		const ids = new Set<string>();
		const layerIds = new Set<string>();
		for (const c of BASE_CONTRIBUTIONS) {
			expect(c.id, 'a contribution id is <plugin>.<name>').toMatch(/^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$/);
			expect(ids.has(c.id), `${c.id} twice`).toBe(false);
			ids.add(c.id);
			expect(c.title && c.blurb && c.credit, c.id).toBeTruthy();
			for (const l of c.layers) {
				expect(layerIds.has(l.id), `${l.id} twice`).toBe(false);
				layerIds.add(l.id);
				expect(DRAPED_TYPES.has(l.type), `${l.id} is a draped type`).toBe(true);
				expect(Object.keys(ANCHORS), `${l.id}'s slot`).toContain(l.slot);
			}
		}
	});
});
