import { describe, expect, it } from 'vitest';
import { render } from 'svelte/server';
import Legend from './Legend.svelte';
import type { TreesModule } from './index.svelte.js';

/** The Legend component, rendered on the server with a stub module: the API's catalogue flag must reach the entry and the credit. */
const stub = (catalogue: boolean, catalogued = 0): TreesModule =>
	({
		view: { mode: 'near', kinds: { catalogued, placed: 5 }, shown: 5 + catalogued, truncated: false, capped: false, cap: 1000, here: true, problem: null, catalogue },
		areas: [],
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
});
