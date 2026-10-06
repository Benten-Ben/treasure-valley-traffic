import { json } from '@sveltejs/kit';
import { db } from '#lib/server/db.js';

/**
 * Buses seen in the last 15 minutes: the latest fix of each, plus its trail.
 * A trip the feed doesn't label takes the route its path matched (routeMatched).
 */
const RECENT = '15 minutes';
const TRAIL = '6 minutes';

export async function GET({ setHeaders }) {
	const rows = await db()`
		with latest as (
			select distinct on (vehicle_id) *
			from obs.vehicle_position
			where ts > now() - ${RECENT}::interval
			order by vehicle_id, ts desc)
		select l.vehicle_id, l.vehicle_label, coalesce(l.route_id, m.route_id) as route_id,
		       (l.route_id is null and m.route_id is not null) as route_matched,
		       l.trip_id, extract(epoch from l.ts)::float8 as ts,
		       ST_X(l.geom) as lon, ST_Y(l.geom) as lat, l.bearing, l.status, l.stop_id,
		       s.name as stop_name, r.short_name, r.long_name, r.color, r.text_color,
		       (select json_agg(json_build_array(round(ST_X(p.geom)::numeric, 6), round(ST_Y(p.geom)::numeric, 6),
		                                         extract(epoch from p.ts)::float8) order by p.ts)
		          from obs.vehicle_position p
		          where p.vehicle_id = l.vehicle_id and p.ts > now() - ${TRAIL}::interval) as trail
		from latest l
		-- Trips the feed doesn't label: the route their path matched (ingest/transit_match.py).
		left join lateral (
			select route_id from obs.trip_route_match t
			where l.route_id is null and t.trip_id = l.trip_id
			  and t.service_date between (l.ts at time zone 'America/Boise')::date - 1 and (l.ts at time zone 'America/Boise')::date
			order by t.service_date desc limit 1) m on true
		left join core.transit_route r on r.route_id = coalesce(l.route_id, m.route_id)
		left join core.transit_stop s on s.stop_id = l.stop_id
		order by l.vehicle_id`;
	setHeaders({ 'cache-control': 'no-store' });
	return json({
		now: Date.now() / 1000,
		vehicles: rows.map((v) => ({
			vehicleId: v.vehicle_id,
			label: v.vehicle_label,
			routeId: v.route_id,
			routeMatched: v.route_matched,
			shortName: v.short_name,
			longName: v.long_name,
			color: v.color,
			textColor: v.text_color,
			ts: v.ts,
			lon: v.lon,
			lat: v.lat,
			bearing: v.bearing,
			status: v.status,
			stopName: v.stop_name,
			trail: v.trail ?? []
		}))
	});
}
