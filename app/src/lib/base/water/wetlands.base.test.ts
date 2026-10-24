import { describe, expect, it } from 'vitest';
import { BASE_CONTRIBUTIONS } from '#lib/base/registry.js';
import { GROUND } from '#lib/map/flavors.js';
import { contrast, TONES } from './palette.js';
import { BODIES, BODIES_LAYER, BODIES_RIM_LAYER } from './water.base.js';
import water from './water.base.js';
import wetlands, {
	addTuftImages,
	MAPPED_FROM_1981,
	FROM_NHD_MARSH,
	NOT_A_BOUNDARY,
	TUFT_IMAGES,
	tuftImage,
	tuftImageId,
	tuftPixels,
	WETLAND_LAYER_IDS,
	WETLAND_LAYERS,
	WETLAND_THIN_LAYER,
	WETLAND_TUFT_LAYER,
	wetlandTuft,
	wetlandWords
} from './wetlands.base.js';

const opaque = (img: { width: number; data: Uint8Array }) => {
	const out: [number, number][] = [];
	for (let i = 0; i < img.data.length; i += 4) if (img.data[i + 3] > 0) out.push([(i / 4) % img.width, Math.floor(i / 4 / img.width)]);
	return out;
};

describe('wetland tufts', () => {
	it('draws recent mapping from z14 and the 1981-era mapping from z15, on a sparser grid', () => {
		const recent = wetlandTuft(false);
		const thin = wetlandTuft(true);
		expect(recent.minzoom).toBe(14);
		expect(thin.minzoom).toBe(15);
		// The same glyph on a bigger tile is a sparser grid.
		expect(thin.cell).toBeGreaterThan(recent.cell);
		for (const l of WETLAND_LAYERS) expect(l.minzoom).toBe(l.id === WETLAND_TUFT_LAYER ? 14 : 15);
	});

	it('is a fill pattern with no fill colour, no outline and no dashed rim', () => {
		expect(WETLAND_LAYERS.map((l) => l.id)).toEqual([WETLAND_TUFT_LAYER, WETLAND_THIN_LAYER]);
		expect([...WETLAND_LAYER_IDS]).toEqual(WETLAND_LAYERS.map((l) => l.id));
		for (const layer of WETLAND_LAYERS) {
			expect(layer.type).toBe('fill');
			for (const look of [layer.valley, layer.clay!]) {
				expect(look).toHaveProperty('fill-pattern');
				expect(look).not.toHaveProperty('fill-color');
				expect(look).not.toHaveProperty('fill-outline-color');
				expect(Object.keys(look).some((k) => k.startsWith('line-'))).toBe(false);
			}
		}
		expect(JSON.stringify(WETLAND_LAYERS[0].filter)).toContain('"!"');
		expect(JSON.stringify(WETLAND_LAYERS[1].filter)).not.toContain('"!"');
	});

	it('names one pattern image per look and mapping age, and the layers use them', () => {
		expect(TUFT_IMAGES.map((i) => i.id)).toEqual(['water-wetland-tuft-valley', 'water-wetland-tuft-clay', 'water-wetland-tuft-thin-valley', 'water-wetland-tuft-thin-clay']);
		expect(WETLAND_LAYERS[0].valley['fill-pattern']).toBe(tuftImageId(false, 'valley'));
		expect(WETLAND_LAYERS[0].clay!['fill-pattern']).toBe(tuftImageId(false, 'clay'));
		expect(WETLAND_LAYERS[1].valley['fill-pattern']).toBe(tuftImageId(true, 'valley'));
		expect(WETLAND_LAYERS[1].clay!['fill-pattern']).toBe(tuftImageId(true, 'clay'));
	});

	it('paints the glyph in the look’s wetland tone on a transparent tile, the same pixels the legend draws', () => {
		for (const thin of [false, true]) {
			const { cell } = wetlandTuft(thin);
			for (const flavor of ['valley', 'clay'] as const) {
				const img = tuftImage(thin, flavor);
				expect([img.width, img.height]).toEqual([cell, cell]);
				expect(img.data.length).toBe(cell * cell * 4);
				expect(opaque(img)).toEqual(expect.arrayContaining(tuftPixels(thin)));
				expect(opaque(img).length).toBe(tuftPixels(thin).length);
				const hex = TONES[flavor].wetland;
				const first = tuftPixels(thin)[0];
				const at = (first[1] * cell + first[0]) * 4;
				expect([...img.data.slice(at, at + 4)]).toEqual([parseInt(hex.slice(1, 3), 16), parseInt(hex.slice(3, 5), 16), parseInt(hex.slice(5, 7), 16), 255]);
			}
			// A tuft is a few strokes: about a tenth of the dense tile, less of the sparse one.
			expect(tuftPixels(thin).length).toBeLessThan(cell * cell * 0.5);
			for (const [x, y] of tuftPixels(thin)) {
				expect(x).toBeGreaterThanOrEqual(0);
				expect(y).toBeGreaterThanOrEqual(0);
				expect(x).toBeLessThan(cell);
				expect(y).toBeLessThan(cell);
			}
		}
		expect(tuftPixels(true).length).toBe(tuftPixels(false).length);
	});

	it('reads on the ground in either look, with a tone that is not red or green', () => {
		for (const flavor of ['valley', 'clay'] as const) {
			expect(contrast(TONES[flavor].wetland, GROUND[flavor]), flavor).toBeGreaterThanOrEqual(3);
			expect(TONES[flavor].wetland).not.toBe(TONES[flavor].line);
		}
	});

	it('adds its images to the map once, and takes them away again', () => {
		const have = new Set<string>();
		const map = { hasImage: (id: string) => have.has(id), addImage: (id: string) => void have.add(id), removeImage: (id: string) => void have.delete(id) };
		const undo = addTuftImages(map);
		expect([...have].sort()).toEqual(TUFT_IMAGES.map((i) => i.id).sort());
		const again = addTuftImages(map); // already there: adds nothing, removes nothing
		again();
		expect(have.size).toBe(4);
		undo();
		expect(have.size).toBe(0);
	});

	it('adds them when the contribution goes live, and takes them away with it', () => {
		const have = new Set<string>();
		const map = { hasImage: (id: string) => have.has(id), addImage: (id: string) => void have.add(id), removeImage: (id: string) => void have.delete(id) };
		const stop = wetlands.live!({ map: map as never, app: {} as never, layerIds: WETLAND_LAYER_IDS });
		expect(have.size).toBe(4);
		stop();
		expect(have.size).toBe(0);
	});

	it('says it is not a legal boundary on every wetland, and adds the 1981 note only where mapped then', () => {
		expect(wetlandWords(false)).toEqual([NOT_A_BOUNDARY]);
		expect(wetlandWords(true)).toEqual([NOT_A_BOUNDARY, MAPPED_FROM_1981]);
		expect(wetlandWords(true, 'nwi')).toEqual([NOT_A_BOUNDARY, MAPPED_FROM_1981]);
		// thin also covers NHD's marsh alone, which isn't from NWI's photos: its card names the older USGS map.
		expect(wetlandWords(true, 'nhd')).toEqual([NOT_A_BOUNDARY, FROM_NHD_MARSH]);
		expect(wetlandWords(false, 'nhd')).toEqual([NOT_A_BOUNDARY]);
		expect(NOT_A_BOUNDARY).toBe('Not a legal (regulatory) wetland boundary.');
		expect(MAPPED_FROM_1981).toBe('Mapped from 1981 photos.');
	});

	it('is its own contribution on the bodies source-layer, with the FWS credit and the images in `live`', () => {
		expect(BASE_CONTRIBUTIONS.map((c) => c.id)).toContain('water.wetlands');
		expect(wetlands.credit).toContain('National Wetlands Inventory');
		expect(wetlands.source).toEqual({ kind: 'landscape', sourceLayers: [BODIES] });
		for (const l of wetlands.layers) expect(l.sourceLayer).toBe(BODIES);
		expect(typeof wetlands.live).toBe('function');
	});

	it('leaves wetlands out of the water bodies’ fill and rim, so only the tufts draw', () => {
		for (const id of [BODIES_LAYER, BODIES_RIM_LAYER]) {
			const l = water.layers.find((x) => x.id === id)!;
			expect(JSON.stringify(l.filter), id).toContain('"wetland"');
			expect(JSON.stringify(l.filter), id).toContain('"!="');
		}
		for (const flavor of ['valley', 'clay'] as const) {
			const fill = water.layers.find((x) => x.id === BODIES_LAYER)![flavor] as Record<string, unknown>;
			expect(JSON.stringify(fill['fill-opacity'])).not.toContain('wetland');
		}
	});
});
