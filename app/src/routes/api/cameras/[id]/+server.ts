import { error } from '@sveltejs/kit';
import { db } from '#lib/server/db.js';
import { jsonWithEtag } from '#lib/server/json-etag.js';

/**
 * One camera with its image views and each view's current calibration
 * (docs/14 §14.8 "APIs"; WP12). `no-cache` with an ETag: camera windows and
 * the calibrator revalidate on every open, and an unchanged camera costs a
 * 304. The shape is `CameraDetail` in #lib/layers/cameras/detail.ts.
 */
export async function GET({ params, request }) {
	const id = Number(params.id);
	if (!Number.isInteger(id) || id <= 0) error(400, 'Bad camera id');
	const sql = db();
	const [camera] = await sql`
		select id, name, achd_cam_id, active, ST_X(pole_geom) as lon, ST_Y(pole_geom) as lat
		from core.camera where id = ${id}`;
	if (!camera) error(404, 'No such camera');
	const views = await sql`
		select v.id, v.image_id, v.status, v.direction, v.description, v.sort_order,
		       cal.id as calibration_id, ST_X(cal.position) as cal_lon, ST_Y(cal.position) as cal_lat,
		       ST_Z(cal.position) as cal_alt, cal.heading_deg, cal.tilt_deg, cal.roll_deg, cal.vfov_deg,
		       cal.image_width, cal.image_height, cal.point_pairs, cal.rms_error_px, cal.reference_frame,
		       cal.created_at
		from core.camera_view v
		left join core.camera_calibration cal on cal.view_id = v.id and upper_inf(cal.valid)
		where v.camera_id = ${id}
		order by v.sort_order, v.id`;
	return jsonWithEtag(
		{
			id: Number(camera.id),
			name: camera.name,
			achdCamId: camera.achd_cam_id,
			active: camera.active,
			pole: [camera.lon, camera.lat],
			views: views.map((v) => ({
				id: Number(v.id),
				imageId: v.image_id,
				status: v.status,
				direction: v.direction,
				description: v.description,
				sortOrder: v.sort_order,
				calibration: v.calibration_id
					? {
							id: Number(v.calibration_id),
							pose: { lon: v.cal_lon, lat: v.cal_lat, alt: v.cal_alt, heading: v.heading_deg,
								tilt: v.tilt_deg, roll: v.roll_deg, vfov: v.vfov_deg },
							imageWidth: v.image_width,
							imageHeight: v.image_height,
							pairs: v.point_pairs,
							rms: v.rms_error_px,
							frame: v.reference_frame,
							createdAt: v.created_at
						}
					: null
			}))
		},
		request.headers.get('if-none-match')
	);
}
