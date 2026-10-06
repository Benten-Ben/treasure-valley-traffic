import { error, json } from '@sveltejs/kit';
import { db } from '#lib/server/db.js';
import { parseFrameChoice, saveFrame } from '#lib/server/frames.js';

/** The JSON body, or null for none (the /v1 calibrator posts none). */
async function body(request: Request | undefined): Promise<unknown> {
	if (!request) return null;
	const text = await request.text();
	if (!text.trim()) return null;
	try {
		return JSON.parse(text);
	} catch {
		error(400, 'The body must be JSON');
	}
}

/**
 * Keep a frame as the view's calibration reference (docs/14 §14.6, "Use this
 * frame"). Body `{sha}` (an on-demand 511 frame in memory) or `{image, day,
 * stamp}` (an archive frame) saves exactly those bytes, or answers 410 when
 * they're gone. No body keeps the newest frame (the seeded fixture in fixture
 * mode), as the /v1 calibrator expects.
 */
export async function POST({ params, request }) {
	const id = Number(params.id);
	if (!Number.isInteger(id)) error(400, 'Bad view id');
	const choice = parseFrameChoice(await body(request));
	const [view] = await db()`select image_id from core.camera_view where id = ${id}`;
	if (!view?.image_id) error(404, 'No image for this view');
	return json(await saveFrame(id, view.image_id, choice));
}
