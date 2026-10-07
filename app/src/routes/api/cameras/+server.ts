import { json } from '@sveltejs/kit';
import { versionedCacheControl } from '#lib/server/cache-headers.js';
import { db } from '#lib/server/db.js';
import { dataMeta } from '#lib/server/versions.js';

/**
 * All active cameras as GeoJSON, with calibration status:
 *  - calibrated: at least one view has a current calibration
 *  - uncalibrated: has an image view, none calibrated yet
 *  - no_image: no 511 image view linked yet
 *
 * Versioned (docs/14 §14.8 "APIs"): immutable when `?v=` is /api/meta's
 * current cameras version, which follows calibrations too; else no-cache.
 */
export async function GET({ url, setHeaders }) {
	const meta = dataMeta();
	const rows = await db()`
		select c.id, c.name, c.achd_cam_id, ST_X(c.pole_geom) as lon, ST_Y(c.pole_geom) as lat,
		       count(distinct v.id)::int as views, count(distinct cal.view_id)::int as calibrated_views
		from core.camera c
		left join core.camera_view v on v.camera_id = c.id
		left join core.camera_calibration cal on cal.view_id = v.id and upper_inf(cal.valid)
		where c.active and c.pole_geom is not null
		group by c.id
		order by c.id`;
	setHeaders({ 'cache-control': versionedCacheControl(url.searchParams.get('v'), (await meta).versions.cameras) });
	return json({
		type: 'FeatureCollection',
		features: rows.map((r) => ({
			type: 'Feature',
			id: Number(r.id),
			geometry: { type: 'Point', coordinates: [r.lon, r.lat] },
			properties: {
				id: Number(r.id),
				name: r.name,
				achdCamId: r.achd_cam_id,
				views: r.views,
				status: r.views === 0 ? 'no_image' : r.calibrated_views > 0 ? 'calibrated' : 'uncalibrated'
			}
		}))
	});
}
