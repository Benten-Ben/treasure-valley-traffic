import { describe, expect, it } from 'vitest';
import { junctionCard, pieceAnswer, pieceCard, type Sql } from './piece.js';

/** A piece row as `roads.piece` joined to `roads.xsection` gives it. */
const row = (over: Record<string, unknown> = {}) => ({
	id: 1002,
	osm_id: 555,
	highway: 'secondary',
	service: null,
	name: 'Chinden Boulevard',
	ref: null,
	oneway: 0,
	roundabout: false,
	bridge: false,
	tunnel: false,
	county: 'Ada',
	road_segment_id: 77,
	length_m: 123.456,
	lanes_fwd: 3,
	lanes_bwd: 3,
	centre_turn: false,
	lanes_source: 'osm',
	total_w_m: 21.34,
	width_tier: 'inventoried',
	width_source: 'achd_bike_network',
	material: 'asphalt',
	material_source: 'surface',
	markings: true,
	flags: [] as string[],
	...over
});
type Row = ReturnType<typeof row>;

describe('the piece card (pure)', () => {
	it('labels each lane source exactly: OpenStreetMap, the ACHD rule with its segment source, HPMS alone, assumed', () => {
		const label = (over: Partial<Record<keyof Row, unknown>>) => pieceCard(row(over as never) as never, 'b', []).lanes.source_label;
		expect(label({ lanes_source: 'osm' })).toBe('OpenStreetMap');
		expect(label({ lanes_source: 'achd_msm', road_segment_id: 5 })).toBe('ACHD rule (Master Street Map)');
		expect(label({ lanes_source: 'itd_hpms', road_segment_id: 5 })).toBe('ACHD rule (ITD HPMS)');
		expect(label({ lanes_source: 'osm_valley', road_segment_id: 5 })).toBe('ACHD rule (OpenStreetMap)');
		expect(label({ lanes_source: 'itd_hpms', road_segment_id: null })).toBe('HPMS');
		expect(label({ lanes_source: 'default', road_segment_id: 5 })).toBe('assumed');
		expect(label({ lanes_source: 'default', road_segment_id: null })).toBe('assumed');
		expect(pieceCard(row({ lanes_source: 'default' }) as never, 'b', []).lanes.assumed).toBe(true);
	});

	it('says when the split is estimated, from the flags', () => {
		expect(pieceCard(row({ flags: ['split_estimated'] }) as never, 'b', []).lanes.split_estimated).toBe(true);
		expect(pieceCard(row() as never, 'b', []).lanes.split_estimated).toBe(false);
	});

	it('flags a disagreement from xsection.flags, never from the counts, and shows both counts from the review detail', () => {
		const detail = { osm: [3, 2], achd_msm: [1, 1], road_segment_id: 77 };
		const flagged = pieceCard(row({ flags: ['conflict'] }) as never, 'b', [detail]);
		expect(flagged.conflict?.osm).toEqual({ label: 'OpenStreetMap', fwd: 3, bwd: 2, total: 5 });
		expect(flagged.conflict?.other).toEqual({ label: 'ACHD rule (Master Street Map)', fwd: 1, bwd: 1, total: 2 });
		// The same review row on a piece the build did not flag is not shown: the ▲ is the flag's.
		expect(pieceCard(row({ flags: [] }) as never, 'b', [detail]).conflict).toBeNull();
	});

	it('tolerates a flagged piece with missing or odd detail keys', () => {
		for (const detail of [[], [{}], [{ osm: [3] }], [{ osm: 'x', achd_msm: null }], [null], [{ osm: [3, 2] }], [{ segment_rule: 'achd_msm', candidates: 'x', road_segment_id: 1 }]]) {
			const c = pieceCard(row({ flags: ['conflict'] }) as never, 'b', detail);
			expect(c.conflict, JSON.stringify(detail)).not.toBeNull();
		}
		const half = pieceCard(row({ flags: ['conflict'] }) as never, 'b', [{ osm: [3, 2] }]).conflict!;
		expect(half.osm?.total).toBe(5);
		expect(half.other).toBeNull();
		const own = pieceCard(row({ flags: ['conflict'] }) as never, 'b', [{ segment_rule: 'achd_msm', candidates: [] }]).conflict!;
		expect(own.rule_disagrees).toBe(true);
		expect(own.osm).toBeNull();
	});

	it('width: metres and feet, its tier in words, and soft where counted or estimated', () => {
		const w = pieceCard(row() as never, 'b', []).width;
		expect(w.total_m).toBe(21.3);
		expect(w.total_ft).toBe(70);
		expect(w.estimated).toBe(false);
		expect(w.source_word).toBe("ACHD's bike network");
		expect(pieceCard(row({ width_tier: 'counted' }) as never, 'b', []).width.estimated).toBe(true);
		expect(pieceCard(row({ width_tier: 'estimated', width_source: 'class_default' }) as never, 'b', []).width.estimated).toBe(true);
	});

	it('material: estimated unless a surface tag gave it; unknown has no source', () => {
		expect(pieceCard(row() as never, 'b', []).material).toEqual({ value: 'asphalt', estimated: false });
		expect(pieceCard(row({ material_source: 'default' }) as never, 'b', []).material.estimated).toBe(true);
		expect(pieceCard(row({ material: 'unknown', material_source: null }) as never, 'b', []).material).toEqual({ value: 'unknown', estimated: true });
	});

	it('one-way, the class in words, and only the flags the card words', () => {
		const c = pieceCard(row({ oneway: -1, highway: 'service', service: 'alley', flags: ['components_exceed', 'direction', 'sidewalk_close'] }) as never, 'b', []);
		expect(c.oneway).toBe('backward');
		expect(c.class_word).toBe('Alley');
		expect(c.notes).toEqual(['direction']);
	});

	it('a junction fill and an island get a short card with no lane counts', () => {
		const j = junctionCard('b', { kind: 'signal', pieces: 4 }, false);
		expect(j).toMatchObject({ kind: 'junction', title: 'Signalized junction', pieces: 4 });
		expect(Object.keys(j)).not.toContain('lanes');
		expect(junctionCard('b', null, true).title).toBe('Traffic island');
		expect(junctionCard('b', { kind: 'odd', pieces: 3 }, false).title).toBe('Where roads meet');
	});
});

/** A fake database: the queries it is asked, and the rows each kind of query answers. */
function fake(o: { present?: boolean; review?: boolean; build?: { id: string; finished_at: Date } | null; rows?: Record<string, unknown[]> }) {
	const seen: string[] = [];
	const sql = ((strings: TemplateStringsArray) => {
		const q = strings.join('?').replace(/\s+/g, ' ');
		seen.push(q);
		const rows = o.rows ?? {};
		if (/to_regclass/.test(q)) return Promise.resolve([{ present: o.present ?? true, review: o.review ?? true }]);
		if (/from roads\.build/.test(q)) return Promise.resolve(o.build === null ? [] : [o.build ?? { id: 'b1', finished_at: new Date('2026-10-12T03:15:00Z') }]);
		if (/from roads\.piece p join roads\.xsection/.test(q)) return Promise.resolve(rows.piece ?? []);
		if (/from roads\.review/.test(q)) return Promise.resolve(rows.review ?? []);
		if (/from roads\.junction/.test(q)) return Promise.resolve(rows.junction ?? []);
		if (/from roads\.surface /.test(q)) return Promise.resolve(rows.surface ?? []);
		if (/from roads\.edge /.test(q)) return Promise.resolve(rows.edge ?? []);
		if (/from roads\.marking /.test(q)) return Promise.resolve(rows.marking ?? []);
		if (/from roads\.piece where/.test(q)) return Promise.resolve(rows.line ?? []);
		throw new Error(`unexpected query: ${q}`);
	}) as unknown as Sql & { begin: unknown };
	(sql as unknown as { begin: (o: string, f: (tx: unknown) => unknown) => unknown }).begin = (options, f) => {
		seen.push(`BEGIN ${options}`);
		return f(sql);
	};
	return { sql: sql as Sql, seen };
}

describe('the piece card API', () => {
	const NOW = { id: 'b1', finished_at: new Date('2026-10-12T03:15:00Z') };

	it('before the roads migrations: empty (none), after reading nothing but the table check', async () => {
		const f = fake({ present: false });
		expect(await pieceAnswer(f.sql, { kind: 'surface', id: 1 }, 'b1')).toEqual({ status: 'none' });
		expect(f.seen.filter((q) => !q.startsWith('BEGIN')).every((q) => /to_regclass/.test(q))).toBe(true);
	});

	it('before any build: empty', async () => {
		expect(await pieceAnswer(fake({ build: null }).sql, { kind: 'line', id: 1 }, 'b1')).toEqual({ status: 'none' });
	});

	it('reads in one repeatable-read, read-only transaction', async () => {
		const f = fake({ rows: { line: [{ id: 1002 }], piece: [row({ flags: [] })] } });
		await pieceAnswer(f.sql, { kind: 'line', id: 1002 }, 'b1');
		expect(f.seen[0]).toBe('BEGIN isolation level repeatable read read only');
	});

	it('a map a build behind is told so and reads no road', async () => {
		const f = fake({ build: NOW, rows: { surface: [{ piece_id: 5, junction_id: null, kind: 'carriageway' }] } });
		// The export's name is from before the current build finished.
		expect(await pieceAnswer(f.sql, { kind: 'surface', id: 2003 }, '20261011T000000Z')).toEqual({ status: 'behind', current: 'b1' });
		expect(f.seen.some((q) => /from roads\.surface /.test(q))).toBe(false);
		expect(await pieceAnswer(f.sql, { kind: 'surface', id: 2003 }, 'something-else')).toMatchObject({ status: 'behind' });
	});

	it('a surface resolves through its piece_id, and the flagged piece reads its review rows', async () => {
		const f = fake({
			build: NOW,
			rows: {
				surface: [{ piece_id: 1002, junction_id: null, kind: 'carriageway' }],
				piece: [row({ flags: ['conflict'], lanes_source: 'osm' })],
				review: [{ detail: { osm: [3, 3], achd_msm: [1, 1], road_segment_id: 77 } }]
			}
		});
		const r = await pieceAnswer(f.sql, { kind: 'surface', id: 2003 }, '20261013T000000Z');
		expect(r.status).toBe('ok');
		const card = (r as { card: { kind: string; conflict: { osm: { total: number }; other: { total: number } } } }).card;
		expect(card.kind).toBe('piece');
		expect(card.conflict.osm.total).toBe(6);
		expect(card.conflict.other.total).toBe(2);
		expect(f.seen.some((q) => /from roads\.review.*kind = 'lanes_conflict'/.test(q))).toBe(true);
	});

	it('without roads.review the card still answers (no review read), and a piece not flagged reads none', async () => {
		const flagged = fake({ build: NOW, review: false, rows: { line: [{ id: 1 }], piece: [row({ flags: ['conflict'] })] } });
		const r = await pieceAnswer(flagged.sql, { kind: 'line', id: 1 }, 'b1');
		expect(r).toMatchObject({ status: 'ok', card: { conflict: { osm: null, other: null } } });
		expect(flagged.seen.some((q) => /from roads\.review/.test(q))).toBe(false);
		const plain = fake({ build: NOW, rows: { line: [{ id: 1 }], piece: [row()] } });
		await pieceAnswer(plain.sql, { kind: 'line', id: 1 }, 'b1');
		expect(plain.seen.some((q) => /from roads\.review/.test(q))).toBe(false);
	});

	it('edges and markings resolve the same way; a junction fill and an island get the short card', async () => {
		const edge = fake({ build: NOW, rows: { edge: [{ piece_id: 1002, junction_id: null, kind: 'curb' }], piece: [row()] } });
		expect(await pieceAnswer(edge.sql, { kind: 'edge', id: 3001 }, 'b1')).toMatchObject({ status: 'ok', card: { kind: 'piece' } });
		const marking = fake({ build: NOW, rows: { marking: [{ piece_id: 1002, junction_id: null }], piece: [row()] } });
		expect(await pieceAnswer(marking.sql, { kind: 'marking', id: 4001 }, 'b1')).toMatchObject({ status: 'ok', card: { kind: 'piece' } });
		const junction = fake({ build: NOW, rows: { surface: [{ piece_id: null, junction_id: 9, kind: 'junction' }], junction: [{ kind: 'signal', pieces: 4 }] } });
		const j = await pieceAnswer(junction.sql, { kind: 'surface', id: 2002 }, 'b1');
		expect(j).toMatchObject({ status: 'ok', card: { kind: 'junction', title: 'Signalized junction', pieces: 4 } });
		expect(junction.seen.some((q) => /roads\.piece p join/.test(q))).toBe(false);
		const island = fake({ build: NOW, rows: { surface: [{ piece_id: null, junction_id: null, kind: 'island' }] } });
		expect(await pieceAnswer(island.sql, { kind: 'surface', id: 2004 }, 'b1')).toMatchObject({ card: { kind: 'junction', title: 'Traffic island' } });
	});

	it('an id the build does not have is none', async () => {
		expect(await pieceAnswer(fake({ build: NOW }).sql, { kind: 'surface', id: 9 }, 'b1')).toEqual({ status: 'none' });
		expect(await pieceAnswer(fake({ build: NOW }).sql, { kind: 'line', id: 9 }, 'b1')).toEqual({ status: 'none' });
		const noXsection = fake({ build: NOW, rows: { surface: [{ piece_id: 5, junction_id: null, kind: 'carriageway' }] } });
		expect(await pieceAnswer(noXsection.sql, { kind: 'surface', id: 1 }, 'b1')).toEqual({ status: 'none' });
	});
});
