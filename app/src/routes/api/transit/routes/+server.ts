import { json } from '@sveltejs/kit';
import { db } from '#lib/server/db.js';

/**
 * Valley Regional Transit's active routes (with our map colors), their
 * shapes, and stops: everything the Transit lens draws that changes at
 * most daily. Shapes are simplified to about 2 m.
 */
export async function GET({ setHeaders }) {
	const sql = db();
	const [routes, shapes, stops] = await Promise.all([
		sql`
			select route_id, short_name, long_name, color, text_color
			from core.transit_route where active
			order by sort_order nulls last,
			         case when short_name ~ '^[0-9]+$' then short_name::int end nulls last, short_name`,
		sql`
			select s.shape_id, s.route_id, ST_AsGeoJSON(ST_SimplifyPreserveTopology(s.geom, 0.00002), 6)::json as geometry
			from core.transit_shape s join core.transit_route r on r.route_id = s.route_id and r.active
			where s.active`,
		sql`
			select stop_id, name, route_ids, ST_X(geom) as lon, ST_Y(geom) as lat
			from core.transit_stop where active and cardinality(route_ids) > 0`
	]);
	const byId = new Map(routes.map((r) => [r.route_id, r]));
	setHeaders({ 'cache-control': 'max-age=300' });
	return json({
		routes,
		shapes: {
			type: 'FeatureCollection',
			features: shapes.map((s) => {
				const r = byId.get(s.route_id)!;
				return {
					type: 'Feature',
					geometry: s.geometry,
					properties: { shapeId: s.shape_id, routeId: s.route_id, shortName: r.short_name, color: r.color }
				};
			})
		},
		stops: {
			type: 'FeatureCollection',
			features: stops.map((s) => ({
				type: 'Feature',
				geometry: { type: 'Point', coordinates: [s.lon, s.lat] },
				properties: { stopId: s.stop_id, name: s.name, routeIds: s.route_ids }
			}))
		}
	});
}
