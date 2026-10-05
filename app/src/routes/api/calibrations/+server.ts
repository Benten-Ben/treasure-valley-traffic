import { json } from '@sveltejs/kit';
import { db } from '#lib/server/db.js';
import { footprint, groundHeight, type Pair, type Pose } from '#lib/calibration/solver.js';

/**
 * Every view's current calibration as GeoJSON: the view cone (ground
 * footprint, nearest 250 m) with the pose, frame and ground height the map
 * needs to drape the image.
 */
export async function GET() {
	const rows = await db()`
		select cal.id, cal.view_id, v.camera_id, c.name,
		       ST_X(cal.position) as lon, ST_Y(cal.position) as lat, ST_Z(cal.position) as alt,
		       cal.heading_deg, cal.tilt_deg, cal.roll_deg, cal.vfov_deg,
		       cal.image_width, cal.image_height, cal.point_pairs, cal.rms_error_px, cal.reference_frame
		from core.camera_calibration cal
		join core.camera_view v on v.id = cal.view_id
		join core.camera c on c.id = v.camera_id
		where upper_inf(cal.valid) and c.active`;
	return json({
		type: 'FeatureCollection',
		features: rows.map((r) => {
			const pose: Pose = { lon: r.lon, lat: r.lat, alt: r.alt, heading: r.heading_deg, tilt: r.tilt_deg,
				roll: r.roll_deg, vfov: r.vfov_deg };
			const size = { width: r.image_width, height: r.image_height };
			const groundZ = groundHeight(r.point_pairs as Pair[]);
			return {
				type: 'Feature',
				id: Number(r.id),
				geometry: { type: 'Polygon', coordinates: [footprint(pose, size, groundZ)] },
				properties: { calibrationId: Number(r.id), viewId: Number(r.view_id), cameraId: Number(r.camera_id),
					name: r.name, pose, size, groundZ, rms: r.rms_error_px, frame: r.reference_frame }
			};
		})
	});
}
