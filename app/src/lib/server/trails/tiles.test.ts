import { readFileSync } from 'node:fs';
import { describe, expect, it, vi } from 'vitest';

vi.mock('$app/env/private', () => ({ DATABASE_URL: undefined, FRAMES_DIR: '/nonexistent', TVT_FRAME_SOURCE: 'fixture' }));
const { BUFFER, EXTENT, TILE_LAYERS, tileLayerProblems, tileSchemas } = await import('../mvt.js');
const tiles = await import('./tiles.js');
const { agency, agencySql, AGENCY_SQL, DETAIL_ZOOM, paths, pathsSql, PATHS_SQL, routes, routesSql } = tiles;

/**
 * The Trails layer's tile definitions (tiles.ts; plugins/trails/README.md, "What the map reads"):
 * schema checks, what each zoom band reads, what is cut out in SQL, and that nothing of the City's
 * rows but the drawn lines reaches a tile. The cuts against a real PostGIS are in mvt.db.test.ts and
 * the browser spec.
 */

const flat = (s: string) => s.replace(/\s+/g, ' ');
/** Every `from`/`join` relation a SQL text reads. */
const relations = (sql: string) => [...flat(sql).matchAll(/\b(?:from|join)\s+([a-z_][a-z0-9_]*\.[a-z_][a-z0-9_]*)/g)].map((m) => m[1]);

/** The tables deploy/tvt_tiles.sql keeps the tile login off. */
function neverTables(): string[] {
	const text = readFileSync(new URL('../../../../../deploy/tvt_tiles.sql', import.meta.url), 'utf8');
	const list = text.match(/never_tables text\[\] := ARRAY\[([\s\S]*?)\];/)?.[1] ?? '';
	return [...list.replace(/--.*$/gm, '').matchAll(/'([a-z_][a-z0-9_]*\.[a-z_][a-z0-9_]*)'/g)].map((m) => m[1]);
}

describe('the Trails tile definitions', () => {
	it('are three layers of the trails plugin, with no problem the registry would find', () => {
		for (const def of [paths, routes, agency]) {
			expect(def.plugin).toBe('trails');
			expect(tileLayerProblems(def), `${def.layer}`).toEqual([]);
			expect(def.minzoom).toBe(10);
			expect(def.maxzoom).toBe(16);
		}
		expect([paths, routes, agency].map((d) => d.layer)).toEqual(['paths', 'routes', 'agency']);
	});

	it('cut at mvt.ts’s extent and buffer, which tiles.ts cannot import (the two load each other)', () => {
		const sql = flat(pathsSql(DETAIL_ZOOM));
		expect(sql).toContain(`ST_AsMVT(t, 'paths', ${EXTENT}, 'mvt_geom', 'osm_id')`);
		expect(sql).toContain(`${EXTENT}, ${BUFFER}, true) as mvt_geom`);
		expect(sql).toContain(`margin => ${BUFFER / EXTENT}`);
		expect(sql).not.toMatch(/undefined|NaN/);
	});

	it('are registered, found by glob from #lib/server/trails/tiles.ts', () => {
		for (const l of ['paths', 'routes', 'agency']) expect(TILE_LAYERS.get(`trails.${l}`)?.layer).toBe(l);
	});

	it('read only the trails schema and core, and none of the tables the tile login is refused', () => {
		const never = neverTables();
		expect(never).toEqual(expect.arrayContaining(['trails.agency_state', 'trails.way_agency', 'trails.agency_line']));
		const schemas = tileSchemas('trails');
		const all = [pathsSql(10), pathsSql(DETAIL_ZOOM), pathsSql(16), routesSql(10), routesSql(16), agencySql(10), agencySql(DETAIL_ZOOM), agencySql(16)];
		for (const sql of all) {
			const rels = relations(sql);
			expect(rels.length).toBeGreaterThan(0);
			for (const r of rels) {
				expect(schemas, r).toContain(r.split('.')[0]);
				expect(never, r).not.toContain(r);
			}
			// Not the City's raw rows or events, nor their attributes.
			expect(flat(sql)).not.toMatch(/\b(raw|evt|restricted)\./);
			expect(flat(sql)).not.toMatch(/source_id|attributes|line_fp/);
		}
	});
});

describe('paths', () => {
	it('reads the valley-zoom network below z13 and the ways from z13', () => {
		expect(relations(pathsSql(10))).toEqual(['trails.path_lo']);
		expect(relations(pathsSql(12))).toEqual(['trails.path_lo']);
		expect(relations(pathsSql(DETAIL_ZOOM))).toEqual(['trails.path']);
		expect(relations(pathsSql(16))).toEqual(['trails.path']);
		expect(DETAIL_ZOOM).toBe(13);
	});

	it('leaves out, in SQL, ways that are never drawn and ways that come in later (plan C18)', () => {
		const hi = flat(PATHS_SQL.hi);
		// `drawn` is false for access=private|no and for canal banks; `minzoom` holds informal ways back to z16, tracks to z13.
		expect(hi).toContain('where s.drawn and s.minzoom <= $1::int and s.geom &&');
		expect(hi).toContain("ST_AsMVT(t, 'paths', 4096, 'mvt_geom', 'osm_id')");
		// The ways' own id is the feature id, so feature-state keys on the OpenStreetMap way.
		expect(hi).toContain('select s.osm_id, s.kind, s.name, s.surface');
		expect(hi).toContain('s.informal');
		// None of the data's undrawn reasons or tags leave the database.
		expect(hi).not.toMatch(/not_drawn|\btags\b|\baccess\b|no_access/);
	});

	it('gives the network the way id as its feature id too', () => {
		expect(flat(PATHS_SQL.lo)).toContain('s.fid as osm_id');
		expect(flat(PATHS_SQL.lo)).toContain("ST_AsMVT(t, 'paths', 4096, 'mvt_geom', 'osm_id')");
	});

	it('cuts a tile with the tile as its parameters, and answers empty when the cut is', async () => {
		const seen: { text: string; params: unknown[] }[] = [];
		const tx = {
			unsafe: (text: string, params: unknown[]) => {
				seen.push({ text, params });
				return Promise.resolve([{ mvt: new Uint8Array([1, 2, 3]) }]);
			}
		};
		const bytes = await paths.cut!(tx as never, { z: 14, x: 2903, y: 5982 }, new AbortController().signal);
		expect([...bytes]).toEqual([1, 2, 3]);
		expect(seen).toHaveLength(1);
		expect(seen[0].params).toEqual([14, 2903, 5982]);
		expect(flat(seen[0].text)).toContain('from trails.path s');
		const none = await paths.cut!({ unsafe: () => Promise.resolve([{ mvt: null }]) } as never, { z: 14, x: 0, y: 0 }, new AbortController().signal);
		expect(none.length).toBe(0);
	});

	it('is cancelled with its signal, and fails as a timeout (so the tile is answered empty)', async () => {
		const stop = new AbortController();
		stop.abort();
		await expect(paths.cut!({ unsafe: vi.fn() } as never, { z: 14, x: 0, y: 0 }, stop.signal)).rejects.toMatchObject({ code: '57014' });
	});
});

describe('routes', () => {
	it('takes the route relation’s name, kind and network from trails.osm_route, only for active routes', () => {
		const sql = flat(routesSql(12));
		expect(relations(sql).sort()).toEqual(['trails.osm_route', 'trails.route_line']);
		expect(sql).toContain('r.route, r.name, r.ref, r.network');
		expect(sql).toContain('r.active');
		expect(sql).toContain("ST_AsMVT(t, 'routes', 4096, 'mvt_geom', 'osm_id')");
		// The same cut at every zoom: routes are few, and a tile of them is small.
		expect(routesSql(10)).toBe(routesSql(16));
	});
});

describe('agency', () => {
	it('draws the parts of the City’s lines from z13, and whole lines below', () => {
		expect(relations(agencySql(10))).toEqual(['trails.agency_lo', 'trails.agency_lo']);
		expect(relations(agencySql(12))).toEqual(['trails.agency_lo', 'trails.agency_lo']);
		expect(relations(agencySql(13))).toEqual(['trails.agency_drawn', 'trails.agency_lo']);
		expect(relations(agencySql(16))).toEqual(['trails.agency_drawn', 'trails.agency_lo']);
		expect(flat(AGENCY_SQL.hi)).toContain('s.part');
	});

	it('uses the line’s positive id as the feature id in both MVT layers (PostGIS drops a negative id), so one feature-state key serves them', () => {
		for (const sql of Object.values(AGENCY_SQL)) {
			expect(flat(sql)).toContain('s.line_id as fid');
			expect(flat(sql)).not.toMatch(/s\.fid\b|-\s*s\.line_id/);
		}
		expect(flat(AGENCY_SQL.hi)).toContain("'agency', 4096, 'mvt_geom', 'fid'");
		expect(flat(AGENCY_SQL.lo)).toContain("'agency', 4096, 'mvt_geom', 'fid'");
		expect(flat(AGENCY_SQL.marks)).toContain("'marks', 4096, 'mvt_geom', 'fid'");
	});

	it('carries no state, no source id and no attribute: the state comes from /api/trails/status', () => {
		for (const sql of Object.values(AGENCY_SQL)) {
			const cols = flat(sql).match(/select (.*?), ST_AsMVTGeom/)?.[1] ?? '';
			expect(cols).not.toMatch(/state|severity|label|source|attributes|system|set_at|since/);
		}
		expect(flat(AGENCY_SQL.marks)).toContain('select s.line_id as fid, ST_AsMVTGeom');
	});

	it('draws every part, however short: the crossing stubs take their trail’s state like the rest', () => {
		expect(flat(AGENCY_SQL.hi)).toContain('where true and');
		expect(flat(AGENCY_SQL.hi)).not.toMatch(/length_m\s*[<>]/);
	});
});
