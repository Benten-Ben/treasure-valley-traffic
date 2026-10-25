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
	it('caps the scene at 4,000 trees, 1,000 on a phone, so the phone budget case expects 3,000 dropped by the scene', () => {
		expect(TREES_SCENE.cap).toBe(4000);
		expect(TREES_SCENE.capPhone).toBe(1000);
		const spec = read('../../../tests/e2e/scene-budget.spec.ts');
		expect(spec).toMatch(/droppedByGroup\['scene-test-trees'\] \?\? 0\)\.toBe\(3000\)/);
		expect(spec).toMatch(/droppedByGroup\['scene-test-trees'\] \?\? 0\)\.toBe\(0\)/);
	});
	it('is not scenery', () => {
		expect('scenery' in TREES_SCENE).toBe(false);
	});
});
