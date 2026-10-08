import { error, json } from '@sveltejs/kit';
import { existsSync } from 'node:fs';
import { db } from '#lib/server/db.js';
import { framePath } from '#lib/server/frames.js';
import { MIN_PAIRS, project, type Pair, type Pose } from '#lib/calibration/solver.js';

const finite = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v);

/** More pairs than anyone clicks by hand: a body this big is a mistake. */
const MAX_PAIRS = 200;

/** The JSON body, or a 400. */
async function body(request: Request): Promise<Record<string, unknown>> {
	try {
		const b = await request.json();
		if (b && typeof b === 'object' && !Array.isArray(b)) return b;
	} catch {
		/* below */
	}
	error(400, 'The body must be a JSON object');
}

/**
 * Save a calibration for a view (docs/14 §14.8 "APIs"; WP14's calibrator, and
 * /v1's). It becomes the view's current calibration; the previous one is
 * closed (kept as history), in one transaction. The error is recomputed here
 * from the pose and pairs rather than trusted from the browser.
 *
 * Body: `{pose, pairs, imageWidth, imageHeight, frame, notes?}`, where
 * `frame` is a reference frame kept in FRAMES_DIR (POST /api/views/[id]/frame,
 * or the calibration's own). Answers `{id, rms, viewId, cameraId}`; 400 for
 * a bad body, 404 for an unknown view.
 */
export async function POST({ params, request }) {
	const viewId = Number(params.id);
	if (!Number.isInteger(viewId) || viewId <= 0) error(400, 'Bad view id');
	const b = await body(request);
	const pose = b.pose as Pose;
	const pairs = b.pairs as Pair[];
	const size = { width: b.imageWidth, height: b.imageHeight };

	if (!pose || typeof pose !== 'object' || !['lon', 'lat', 'alt', 'heading', 'tilt', 'roll', 'vfov'].every((k) => finite(pose[k as keyof Pose])))
		error(400, 'Pose is incomplete');
	if (Math.abs(pose.lon) > 180 || Math.abs(pose.lat) > 90 || !(pose.vfov > 0 && pose.vfov < 180) || Math.abs(pose.tilt) > 90)
		error(400, 'Pose is out of range');
	if (!finite(size.width) || !finite(size.height) || size.width <= 0 || size.height <= 0) error(400, 'Image size is missing');
	if (!Array.isArray(pairs) || pairs.length < MIN_PAIRS) error(400, `Need at least ${MIN_PAIRS} point pairs`);
	if (pairs.length > MAX_PAIRS) error(400, `At most ${MAX_PAIRS} point pairs`);
	if (!pairs.every((p) => p?.pixel?.length === 2 && p?.ground?.length === 3 && [...p.pixel, ...p.ground].every(finite)))
		error(400, 'Each pair needs a pixel [x, y] and a ground point [lon, lat, z]');
	if (typeof b.frame !== 'string' || !existsSync(framePath(b.frame))) error(400, 'Unknown reference frame');
	const notes = typeof b.notes === 'string' ? b.notes.slice(0, 2000) : null;

	const residuals = pairs.map((p) => {
		const q = project(pose, size as { width: number; height: number }, p.ground);
		return q ? Math.hypot(q[0] - p.pixel[0], q[1] - p.pixel[1]) : Infinity;
	});
	if (!residuals.every(Number.isFinite)) error(400, 'Some points are behind the camera for this pose');
	const rms = Math.sqrt(residuals.reduce((s, v) => s + v * v, 0) / residuals.length);
	// Only what the pairs are made of goes into the row.
	const clean = pairs.map((p) => ({ pixel: [p.pixel[0], p.pixel[1]], ground: [p.ground[0], p.ground[1], p.ground[2]] }));

	const sql = db();
	const [view] = await sql`select camera_id from core.camera_view where id = ${viewId}`;
	if (!view) error(404, 'No such view');
	const id = await sql.begin(async (tx) => {
		await tx`update core.camera_calibration set valid = tstzrange(lower(valid), now())
		         where view_id = ${viewId} and upper_inf(valid)`;
		const [row] = await tx`
			insert into core.camera_calibration
			  (view_id, position, heading_deg, tilt_deg, roll_deg, vfov_deg, image_width, image_height,
			   point_pairs, rms_error_px, reference_frame, notes, created_by)
			values (${viewId}, ST_SetSRID(ST_MakePoint(${pose.lon}, ${pose.lat}, ${pose.alt}), 4326),
			        ${pose.heading}, ${pose.tilt}, ${pose.roll}, ${pose.vfov}, ${size.width as number}, ${size.height as number},
			        ${tx.json(clean as never)}, ${rms}, ${b.frame as string}, ${notes}, 'manual')
			returning id`;
		return Number(row.id);
	});
	return json({ id, rms, viewId, cameraId: Number(view.camera_id) });
}
