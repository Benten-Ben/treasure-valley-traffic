import { error, json } from '@sveltejs/kit';
import { existsSync } from 'node:fs';
import { db } from '#lib/server/db.js';
import { framePath } from '#lib/server/frames.js';
import { MIN_PAIRS, project, type Pair, type Pose } from '#lib/calibration/solver.js';

const finite = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v);

/**
 * Save a calibration for a view. It becomes the view's current calibration;
 * the previous one is closed (kept as history). The error is recomputed here
 * from the pose and pairs rather than trusted from the browser.
 */
export async function POST({ params, request }) {
	const viewId = Number(params.id);
	if (!Number.isInteger(viewId)) error(400, 'Bad view id');
	const body = await request.json();
	const pose: Pose = body.pose;
	const pairs: Pair[] = body.pairs;
	const size = { width: body.imageWidth, height: body.imageHeight };

	if (!pose || !['lon', 'lat', 'alt', 'heading', 'tilt', 'roll', 'vfov'].every((k) => finite(pose[k as keyof Pose])))
		error(400, 'Pose is incomplete');
	if (!finite(size.width) || !finite(size.height)) error(400, 'Image size is missing');
	if (!Array.isArray(pairs) || pairs.length < MIN_PAIRS) error(400, `Need at least ${MIN_PAIRS} point pairs`);
	if (!pairs.every((p) => p.pixel?.length === 2 && p.ground?.length === 3 && [...p.pixel, ...p.ground].every(finite)))
		error(400, 'Each pair needs a pixel [x, y] and a ground point [lon, lat, z]');
	if (typeof body.frame !== 'string' || !existsSync(framePath(body.frame))) error(400, 'Unknown reference frame');

	const residuals = pairs.map((p) => {
		const q = project(pose, size, p.ground);
		return q ? Math.hypot(q[0] - p.pixel[0], q[1] - p.pixel[1]) : Infinity;
	});
	if (!residuals.every(Number.isFinite)) error(400, 'Some points are behind the camera for this pose');
	const rms = Math.sqrt(residuals.reduce((s, v) => s + v * v, 0) / residuals.length);

	const sql = db();
	const id = await sql.begin(async (tx) => {
		await tx`update core.camera_calibration set valid = tstzrange(lower(valid), now())
		         where view_id = ${viewId} and upper_inf(valid)`;
		const [row] = await tx`
			insert into core.camera_calibration
			  (view_id, position, heading_deg, tilt_deg, roll_deg, vfov_deg, image_width, image_height,
			   point_pairs, rms_error_px, reference_frame, notes, created_by)
			values (${viewId}, ST_SetSRID(ST_MakePoint(${pose.lon}, ${pose.lat}, ${pose.alt}), 4326),
			        ${pose.heading}, ${pose.tilt}, ${pose.roll}, ${pose.vfov}, ${size.width}, ${size.height},
			        ${tx.json(pairs as never)}, ${rms}, ${body.frame}, ${body.notes ?? null}, 'manual')
			returning id`;
		return Number(row.id);
	});
	return json({ id, rms });
}
