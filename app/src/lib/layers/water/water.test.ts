import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import { DROP } from './icons.js';
import {
	ageText,
	areaText,
	bodyTitle,
	canalSourceWords,
	CREDITS,
	dayText,
	ecoliResultText,
	evidenceWords,
	FLOW_WORD,
	floodWords,
	gaugeCredits,
	geometryWords,
	lengthText,
	measuresWords,
	metresFeet,
	outlineWords,
	readingFacts,
	readingText,
	reachCredits,
	reachFact,
	reachTitle,
	serviceAreasWords,
	sourceCredits,
	sourceLine,
	widthHow,
	type CanalDetail,
	type Evidence
} from './water.js';

/** The words a water card uses: made-up values, no real records. */

describe('the icon', () => {
	it('is Phosphor’s Drop, duotone, exactly as phosphor-svelte ships it', () => {
		const require = createRequire(import.meta.url);
		const dir = dirname(require.resolve('phosphor-svelte/package.json'));
		const src = readFileSync(join(dir, 'lib', `${DROP.name}Icon.svelte`), 'utf8');
		const branch = /weight === "duotone"\}\s*([\s\S]*?)\{:else/.exec(src)?.[1] ?? '';
		const paths = [...branch.matchAll(/<path d="([^"]+)"([^>]*)\/>/g)];
		expect(DROP.tone).toBe(paths.find((p) => p[2].includes('opacity="0.2"'))?.[1]);
		expect(DROP.line).toBe(paths.find((p) => !p[2].includes('opacity'))?.[1]);
	});
});

describe('sizes', () => {
	it('gives metres with feet, and short lengths in metres', () => {
		expect(metresFeet(8)).toBe('8 m (26 ft)');
		expect(metresFeet(2.5)).toBe('2.5 m (8 ft)');
		expect(metresFeet(14.2)).toBe('14 m (47 ft)');
		expect(lengthText(640)).toBe('640 m (2100 ft)');
		expect(lengthText(23100)).toBe('23 km (14 mi)');
		expect(lengthText(4100)).toBe('4.1 km (2.5 mi)');
		expect(areaText(12500)).toBe('3.1 acres (1.3 ha)');
		expect(areaText(800)).toBe('0.20 acres (800 m²)');
		expect(areaText(5_000_000)).toBe('1,236 acres (500 ha)');
	});

	it('says how a width is known, and that it is an estimate unless measured', () => {
		expect(widthHow('measured')).toContain('measured');
		for (const f of ['order', 'kind'] as const) expect(widthHow(f)).toContain('estimated');
		expect(widthHow('osm_tag')).toContain('width tag');
	});
});

describe('titles and facts', () => {
	it('names the unnamed by their kind', () => {
		expect(reachTitle('ditch', null)).toBe('Unnamed ditch');
		expect(reachTitle('lateral', '  ')).toBe('Unnamed lateral');
		expect(reachTitle('lateral', null, true)).toBe('Unnamed lateral (piped)');
		expect(reachTitle('canal', 'Example Canal', true)).toBe('Example Canal');
		expect(bodyTitle('pond', null)).toBe('Unnamed pond');
		expect(bodyTitle('river', null)).toBe('Unnamed river');
		expect(bodyTitle('lake', 'Example Lake')).toBe('Example Lake');
	});

	it('words the tooltip’s fact and source by form', () => {
		expect(reachFact('canal', 5)).toBe('Canal · about 5 m wide');
		expect(reachFact('stream', 3, { intermittent: true, nhdOnly: true })).toBe('Creek or stream, dries up part of the year · about 3 m wide · federal map only');
		expect(reachFact('lateral', 3, { piped: true, intermittent: true })).toBe('Lateral, piped · about 3 m wide');
		expect(reachFact('ditch', Number.NaN)).toBe('Ditch');
		expect(sourceLine(true)).toContain('not in OpenStreetMap');
		expect(sourceLine(false)).toBe('OpenStreetMap · USGS NHD');
	});

	it('says where a line comes from, and what agrees', () => {
		expect(geometryWords('nhd', false)).toContain("OpenStreetMap doesn't have this line");
		expect(geometryWords('osm', true)).toContain('agrees');
		expect(geometryWords('osm', false)).toContain("doesn't clearly agree");
		expect(outlineWords('nhd', false)).toContain("doesn't have this area");
		const e: Evidence = { source: 'nhd_hr', source_id: 'NHD-X', role: 'attributes', share: 0.93, distance_m: 4.2 };
		expect(evidenceWords(e)).toBe('Its facts (flow, size class, name): USGS National Hydrography Dataset, NHD-X (93% of its length within 20 m, median 4 m apart)');
		expect(evidenceWords({ source: 'osm_waterways', source_id: 'w900', role: 'geometry', share: null, distance_m: null })).toBe('Its line: OpenStreetMap, w900');
		expect(FLOW_WORD.intermittent).toContain('intermittent');
	});
});

describe('canals and their service areas', () => {
	const areas = [
		{ name: 'Example Irrigation District', share: 0.62, at_head: true },
		{ name: 'Sample Ditch Company', share: 0.38, at_head: false }
	];

	it('words IDWR’s service areas as where the canal runs, never who runs it', () => {
		const text = serviceAreasWords(areas);
		expect(text).toBe('Irrigation service areas it runs through: Example Irrigation District (62% of its length, and its head); Sample Ditch Company (38% of its length).');
		expect(serviceAreasWords([])).toBe('');
		// The phrase the plan forbids, built from parts so this file doesn’t hold it.
		const forbidden = new RegExp(['operated', 'by'].join('\\s+'), 'i');
		for (const s of [text, CREDITS.idwr, canalSourceWords({ kind: 'river', name: 'Example River' }) ?? '']) expect(s).not.toMatch(forbidden);
	});

	it('says what a head leaves', () => {
		expect(canalSourceWords({ kind: 'river', name: 'Example River' })).toBe('Leaves Example River');
		expect(canalSourceWords({ kind: 'canal', name: null })).toBe('Leaves another canal');
		expect(canalSourceWords({ kind: 'unknown', name: null })).toBeNull();
	});

	it('credits IDWR only when its service areas are shown, HydroShare only when its names or types are used', () => {
		const canal = (service_areas: CanalDetail['service_areas'], gauge: boolean) => ({ service_areas, gauge: gauge ? { usgs: false } : null });
		const base = { geometry_from: 'osm' as const, name_from: 'osm' as const, evidence: [] as Evidence[] };
		expect(reachCredits({ ...base, canal: null })).toEqual([CREDITS.osm, CREDITS.nhd]);
		const withAreas = reachCredits({ ...base, name_from: 'hydroshare', canal: canal(areas, true) });
		expect(withAreas).toEqual([CREDITS.osm, CREDITS.nhd, CREDITS.hydroshare, CREDITS.nwps, CREDITS.idwr]);
		expect(reachCredits({ ...base, geometry_from: 'nhd', canal: null })).toEqual([CREDITS.nhd]);
		// A gauge the record ties to a USGS site brings its credit, on the canal's gauge or the reach's own.
		expect(reachCredits({ ...base, canal: { service_areas: [], gauge: { usgs: true } } })).toContain(`${CREDITS.nwps}; ${CREDITS.usgs}`);
		expect(reachCredits({ ...base, canal: null, gauge: { usgs: true } })).toContain(`${CREDITS.nwps}; ${CREDITS.usgs}`);
		expect(reachCredits({ ...base, canal: null, gauge: { usgs: false } })).toContain(CREDITS.nwps);
		expect(reachCredits({ ...base, evidence: [{ source: 'hydroshare_canals', source_id: 'N1', role: 'name', share: 1, distance_m: 1 }], canal: null })).toContain(CREDITS.hydroshare);
		// The canal's own name can come from HydroShare when the reach's doesn't.
		expect(reachCredits({ ...base, canal: { service_areas: [], gauge: null, sources: ['osm_waterways', 'hydroshare_canals'] } })).toEqual([CREDITS.osm, CREDITS.nhd, CREDITS.hydroshare]);
	});

	it('credits where the name of the canal a head leaves came from', () => {
		const base = { geometry_from: 'osm' as const, name_from: 'osm' as const, evidence: [] as Evidence[] };
		const canal = (source: { sources?: string[]; name_from?: 'osm' | 'nhd' | 'hydroshare' | null }) => ({
			service_areas: [],
			gauge: null,
			sources: ['osm_waterways'],
			source
		});
		// A lateral OSM names, leaving a canal HydroShare names: "Leaves <canal>" credits HydroShare.
		expect(reachCredits({ ...base, canal: canal({ sources: ['hydroshare_canals'] }) })).toEqual([CREDITS.osm, CREDITS.nhd, CREDITS.hydroshare]);
		// Leaving a canal OSM names, or a river whose name came from OSM: no HydroShare credit.
		expect(reachCredits({ ...base, canal: canal({ sources: ['osm_waterways'] }) })).toEqual([CREDITS.osm, CREDITS.nhd]);
		expect(reachCredits({ ...base, canal: canal({ name_from: 'osm' }) })).toEqual([CREDITS.osm, CREDITS.nhd]);
		// Leaving a river HydroShare names, or one only NHD names.
		expect(reachCredits({ ...base, canal: canal({ name_from: 'hydroshare' }) })).toContain(CREDITS.hydroshare);
		expect(reachCredits({ ...base, geometry_from: 'nhd', canal: { ...canal({ name_from: 'nhd' }), sources: ['nhd_hr'] } })).toEqual([CREDITS.nhd]);
		expect(reachCredits({ ...base, canal: { ...canal({ name_from: 'nhd' }), sources: ['osm_waterways'] } })).toEqual([CREDITS.osm, CREDITS.nhd]);
	});

	it('credits the sources behind the records a card shows, in a fixed order', () => {
		expect(sourceCredits(['hydroshare_canals', 'nhd_hr', 'osm_waterways', 'nwps_gauges', null, ''])).toEqual([CREDITS.osm, CREDITS.nhd, CREDITS.hydroshare]);
		expect(sourceCredits([])).toEqual([]);
		expect(sourceCredits(['osm_waterways'], ['nhd_hr'])).toEqual([CREDITS.osm, CREDITS.nhd]);
	});

	it('credits HydroShare as its licence asks: the creators, the DOI and "modified" (CC BY 4.0 §3(a)(1))', () => {
		expect(CREDITS.hydroshare).toContain('modified');
		expect(CREDITS.hydroshare).toContain('doi:10.4211/hs.24a5f761bf4f41fb9b872b130d9d1a3f');
		expect(CREDITS.hydroshare).toContain('CC BY 4.0');
		expect(CREDITS.hydroshare).toContain('Tatum');
		// The same words as the source's own record in the plugin's manifest, so the two can't drift.
		const manifest = JSON.parse(readFileSync(fileURLToPath(new URL('../../../../../plugins/water/plugin.json', import.meta.url)), 'utf8')) as {
			sources: { name: string; credit: string }[];
		};
		expect(manifest.sources.find((s) => s.name === 'hydroshare_canals')?.credit).toBe(CREDITS.hydroshare);
	});
});

describe('gauges', () => {
	it('words readings from their units: kcfs is flow in cfs, ft is stage or a pool’s elevation', () => {
		expect(readingFacts('HGIRZZZ', ['ft', 'kcfs'], [7.333, 1.66])).toEqual([
			{ label: 'Stage', value: 7.33, unit: 'ft' },
			{ label: 'Flow', value: 1660, unit: 'cfs' }
		]);
		expect(readingFacts('HPIRZZZ', ['ft', null], [3200.5, null])).toEqual([{ label: 'Pool elevation', value: 3200.5, unit: 'ft' }]);
		expect(readingFacts(null, ['cfs', 'ft'], [840.4, 2])).toEqual([
			{ label: 'Flow', value: 840, unit: 'cfs' },
			{ label: 'Stage', value: 2, unit: 'ft' }
		]);
		expect(readingFacts(null, ['m'], [Number.NaN])).toEqual([]);
		expect(readingText({ at: 'x', facts: [{ label: 'Flow', value: 1660, unit: 'cfs' }, { label: 'Stage', value: 7.33, unit: 'ft' }] })).toBe('Flow 1,660 cfs · Stage 7.33 ft');
	});

	it('says flood categories as NWPS gives them, and an absent episode only as that', () => {
		expect(floodWords({ category: 'minor', peak: null, since: null })).toContain('minor flooding');
		const none = floodWords(null);
		expect(none).toContain('No open flood episode');
		expect(none).not.toMatch(/\bsafe\b/i);
	});

	it('credits NOAA always and USGS only where NWPS names a USGS site (BSEI1’s record names none)', () => {
		expect(gaugeCredits(false)).toEqual([CREDITS.nwps]);
		expect(gaugeCredits(true)[0]).toContain('courtesy of the U.S. Geological Survey');
		expect(measuresWords({ type: 'canal', id: 1, name: 'Example Canal', kind: 'main_canal' })).toBe('Example Canal (main canal)');
		expect(measuresWords({ type: 'body', id: 1, name: null, kind: 'reservoir' })).toBe('Unnamed reservoir (reservoir)');
		expect(measuresWords(null)).toBeNull();
	});

	it('words an age', () => {
		const now = Date.parse('2030-07-01T12:00:00Z');
		expect(ageText('2030-07-01T11:59:30Z', now)).toBe('just now');
		expect(ageText('2030-07-01T11:15:00Z', now)).toBe('45 min ago');
		expect(ageText('2030-07-01T09:00:00Z', now)).toBe('3 h ago');
		expect(ageText('2030-06-28T12:00:00Z', now)).toBe('3 days ago');
		expect(ageText('nonsense', now)).toBe('');
	});
});

describe('the City’s notices', () => {
	it('shows E. coli results as published, with no verdict', () => {
		expect(ecoliResultText({ result: 456.7, units: 'MPN/100 mL' })).toBe('456.7 MPN/100 mL');
		expect(ecoliResultText({ result: 12, units: null })).toBe('12');
		expect(ecoliResultText({ result: null, units: 'MPN/100 mL' })).toBe('No result');
		expect(dayText('2030-07-01')).toBe('Jul 1, 2030');
		expect(dayText('2030-07-01T08:00:00Z')).toBe('Jul 1, 2030');
		expect(dayText(null)).toBe('');
	});
});
