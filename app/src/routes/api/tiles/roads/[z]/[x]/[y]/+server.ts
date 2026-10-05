import { error } from '@sveltejs/kit';
import { db } from '#lib/server/db.js';

/**
 * Road segments as Mapbox vector tiles, cut by PostGIS on request (layer
 * "roads"). Zoomed out, only the bigger roads are included, so tiles stay small.
 */
const MIN_ZOOM = 8;
const MAX_ZOOM = 16;
// Smallest zoom at which each functional class appears.
const CLASS_MIN_ZOOM: Record<string, number> = {
	Interstate: 8,
	'Principal Arterial': 8,
	Ramp: 11,
	'Minor Arterial': 10,
	Collector: 11,
	Local: 13,
	Alley: 15,
	Driveway: 15,
	Parks: 14
};

export async function GET({ params, setHeaders }) {
	const [z, x, y] = [params.z, params.x, params.y].map(Number);
	if (![z, x, y].every(Number.isInteger) || z < MIN_ZOOM || z > MAX_ZOOM || x < 0 || y < 0 || x >= 2 ** z || y >= 2 ** z)
		error(404, 'No such tile');
	const classes = Object.entries(CLASS_MIN_ZOOM)
		.filter(([, minz]) => z >= minz)
		.map(([c]) => c);
	const [row] = await db()`
		with bounds as (select ST_TileEnvelope(${z}, ${x}, ${y}) as env),
		tile as (
			select s.id, s.name, s.functional_class as class, s.posted_speed_mph as speed, s.one_way,
			       s.private, (s.from_level = 20 or s.to_level = 20) as elevated, s.community,
			       ST_AsMVTGeom(ST_Transform(s.geom, 3857), b.env, 4096, 64, true) as geom
			from core.road_segment s, bounds b
			where s.active and s.functional_class = any(${classes})
			  and s.geom && ST_Transform(b.env, 4326))
		select ST_AsMVT(tile, 'roads', 4096, 'geom', 'id') as mvt from tile where geom is not null`;
	setHeaders({ 'content-type': 'application/vnd.mapbox-vector-tile', 'cache-control': 'max-age=600' });
	return new Response(row?.mvt ? new Uint8Array(row.mvt) : new Uint8Array());
}
