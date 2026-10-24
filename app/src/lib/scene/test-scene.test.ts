import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { TREES_SCENE } from '#lib/layers/trees/scene-options.js';

const read = (rel: string) => readFileSync(new URL(rel, import.meta.url), 'utf8');

describe('the scene budget case matches production trees', () => {
	it('sets its trees group with the shared TREES_SCENE and nothing of its own', () => {
		expect(read('./test-scene.ts')).toMatch(/scene\.set\('scene-test-trees', forest, TREES_SCENE\)/);
	});
	it('the trees layer passes the same constant to the scene', () => {
		const src = read('../layers/trees/index.svelte.ts');
		expect(src.match(/scene\.set\(TREES_3D, [^)]*, TREES_SCENE\)/g)?.length).toBe(2);
	});
	it('sets no scene cap, so the phone budget case expects no trees dropped by the scene', () => {
		expect('cap' in TREES_SCENE || 'capPhone' in TREES_SCENE).toBe(false);
		const spec = read('../../../tests/e2e/scene-budget.spec.ts');
		expect(spec).toMatch(/droppedByGroup\['scene-test-trees'\] \?\? 0\)\.toBe\(0\)/);
		expect(spec).not.toMatch(/capped at 1,000/);
	});
	it('is not scenery', () => {
		expect('scenery' in TREES_SCENE).toBe(false);
	});
});
