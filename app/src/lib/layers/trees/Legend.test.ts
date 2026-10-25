import { describe, expect, it } from 'vitest';
import { render } from 'svelte/server';
import Legend from './Legend.svelte';
import type { TreesModule } from './index.svelte.js';

/** The Legend component, rendered on the server with a stub module: the API's catalogue flag must reach the entry and the credit. */
const shrubs = { bush: 0, sage: 0, truncated: false, drawn: false, phone: false, here: false };
const stub = (catalogue: boolean, catalogued = 0, s: Partial<typeof shrubs> = {}, shrubAreas: unknown[] = []): TreesModule =>
	({
		view: { mode: 'near', kinds: { catalogued, placed: 5 }, shown: 5 + catalogued, truncated: false, capped: false, cap: 1000, here: true, problem: null, catalogue, shrubs: { ...shrubs, ...s } },
		areas: [],
		shrubAreas,
		goTo() {}
	}) as unknown as TreesModule;
const html = (m: TreesModule) => render(Legend, { props: { module: m } }).body.replace(/<!--.*?-->/g, '');

describe('the Trees legend component', () => {
	it('lists Catalogued and credits the City once the API’s catalogue flag is true, with no catalogued tree in view', () => {
		const out = html(stub(true));
		expect(out).toContain('Catalogued');
		expect(out).toContain("catalogued trees from the City of Boise's inventory");
		// No tone and no count for a kind the boxes never send.
		expect(out).not.toContain('Catalogued</b> (full green)');
		expect(out).toContain("a tree's card says when it is one");
		// ...and no filled swatch: the map draws no tree in that tone.
		expect(out).toContain('class="unfilled');
	});
	it('names neither on a public install', () => {
		const out = html(stub(false));
		expect(out).not.toContain('Catalogued');
		expect(out).not.toContain('City of Boise');
	});
	it('draws the tone and the count when catalogued trees are in view', () => {
		const out = html(stub(true, 3));
		expect(out).toContain('(full green)');
		expect(out).toMatch(/\(3\)/);
		expect(out).not.toContain('class="unfilled');
	});

	it('lists bush and sage by name, says where shrubs are built and credits them, Sentinel-2 included', () => {
		const out = html(stub(false, 0, {}, [{ area: 'c', bounds: [0, 0, 1, 1], shrubs: 4, built_at: null }]));
		expect(out).toContain('<b>Bush</b>');
		expect(out).toContain('<b>Sage</b>');
		expect(out).toContain('Shrubs are built for the North End so far.');
		expect(out).toContain('Shrubs stand in 3D from z17');
		expect(out).toContain('USDA NAIP');
		expect(out).toContain('contains modified Copernicus Sentinel data 2025');
		// No counts until shrubs are drawn.
		expect(out).not.toMatch(/\(\d+\)<\/span><\/span><\/li>\s*<li data-look="sage"/);
	});
	it('says none are built, shows the counts once drawn, and says so on a phone', () => {
		expect(html(stub(false))).toContain('No shrubs are built yet.');
		const drawn = html(stub(false, 0, { drawn: true, bush: 12, sage: 3, truncated: true }, [{ area: 'c', bounds: [0, 0, 1, 1], shrubs: 4, built_at: null }]));
		expect(drawn).toMatch(/12/);
		expect(drawn).toContain('data-shrubs-truncated');
		expect(html(stub(false, 0, { phone: true }))).toContain('Shrubs are off on phones.');
	});
});
