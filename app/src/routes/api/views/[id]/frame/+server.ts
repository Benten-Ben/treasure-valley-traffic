import { error, json } from '@sveltejs/kit';
import { db } from '#lib/server/db.js';
import { captureFrame } from '#lib/server/frames.js';

/** Capture the view's current 511 image as a reference frame to calibrate on. */
export async function POST({ params }) {
	const id = Number(params.id);
	if (!Number.isInteger(id)) error(400, 'Bad view id');
	const [view] = await db()`select image_id from core.camera_view where id = ${id}`;
	if (!view?.image_id) error(404, 'No image for this view');
	return json(await captureFrame(id, view.image_id));
}
