import { describe, expect, it, vi } from 'vitest';
import type { LayerSpecification } from 'maplibre-gl';

vi.mock('$app/env/private', () => ({ DATABASE_URL: undefined, FRAMES_DIR: '/nonexistent', TVT_FRAME_SOURCE: 'fixture' }));
const { default: contribution, CHAR, STIPPLE, stippleImage } = await import('./burn-scars.base.js');
const { contributionStatus, contributionLayer, layerShown } = await import('#lib/map/flavors.js');
const { anchorLayer, ANCHORS, drapedRuns, insertSlotted, ordered, rttStacks } = await import('#lib/map/order.js');
const { oklch } = await import('#lib/map/color.js');
type BasemapManifest = import('#lib/map/style.js').BasemapManifest;

const noManifest = {} as BasemapManifest;
const BUILT = { versions: { layers: { 'hazards.burn_scars': '2026-10-22T00:00:00Z' } } } as never;
const off = { flavor: 'valley' as const, aerial: false, layers: new Set<never>() };

describe('the burn-scar base contribution', () => {
	it('is built only when /api/meta has the layer version', () => {
		expect(contributionStatus(contribution, noManifest, BUILT)).toEqual({ built: true });
		expect(contributionStatus(contribution, noManifest, { versions: { layers: {} } } as never).built).toBe(false);
		expect(contributionStatus(contribution, noManifest, null).built).toBe(false);
	});

	it('is Valley only and hidden under Aerial', () => {
		const [char, stipple] = contribution.layers;
		expect(contribution.looks).toBe('valley');
		expect(layerShown(contribution, char, off)).toBe(true);
		expect(layerShown(contribution, char, { ...off, flavor: 'clay' })).toBe(false);
		expect(layerShown(contribution, char, { ...off, aerial: true })).toBe(false);
		expect(layerShown(contribution, stipple, { ...off, aerial: true })).toBe(false);
	});

	it('sits in the ground slot above the ground, with the fade as data', () => {
		for (const l of contribution.layers) {
			expect(l.slot).toBe('ground');
			expect(l.rank).toBeGreaterThanOrEqual(20);
			expect(l.sourceLayer).toBe('scars');
		}
		const paint = contribution.layers[0].valley as Record<string, unknown>;
		expect(paint['fill-color']).toBe(CHAR);
		expect(JSON.stringify(paint['fill-opacity'])).toContain('"fade"');
	});

	it('keeps the draped block at one run: the scars add no second terrain draw', () => {
		const layers: LayerSpecification[] = Object.values(ANCHORS).map((id) => ({ id, type: 'background' }) as LayerSpecification);
		const ranks = {};
		let list = layers;
		for (const l of contribution.layers) list = insertSlotted(list, [{ slot: l.slot, layer: contributionLayer(contribution, l, off) }], l.rank, ranks);
		const shown = list.map((l) => ordered(l, true));
		expect(rttStacks(shown)).toBe(1);
		const runs = drapedRuns(shown);
		expect(runs).toHaveLength(1);
		expect(runs[0]).toEqual(expect.arrayContaining(contribution.layers.map((l) => l.id)));
	});

	it('is neutral: never red or orange (the char and the stipple have almost no chroma)', () => {
		const colours = [CHAR, ...stippleColours()];
		for (const hex of colours) {
			const { C } = oklch(hex);
			expect(C, `${hex} chroma`).toBeLessThan(0.03);
		}
	});
});

/** The stipple's dot colours, read back from the generated image. */
function stippleColours(): string[] {
	const img = stippleImage();
	const out = new Set<string>();
	for (let i = 0; i < img.data.length; i += 4) {
		if (img.data[i + 3] === 0) continue;
		out.add('#' + [img.data[i], img.data[i + 1], img.data[i + 2]].map((v) => v.toString(16).padStart(2, '0')).join(''));
	}
	return [...out];
}

describe('the stipple image', () => {
	it('is an 8 by 8 RGBA tile with dots only', () => {
		const img = stippleImage();
		expect(img.width).toBe(8);
		expect(img.height).toBe(8);
		expect(img.data.length).toBe(8 * 8 * 4);
		expect(STIPPLE).toBe('hazards-burn-stipple');
	});
});
