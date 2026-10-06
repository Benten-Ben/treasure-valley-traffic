import { serveArchiveFrame } from '#lib/server/frames.js';

/**
 * Frames from the capture archive: /camera-frames/<image_id>/<day>/<stamp>.jpg
 * (docs/14 §14.6). Written once and never changed, so cached for a year, ETag
 * answered with 304. Only images of views in core.camera_view, and only with
 * CAMERA_IMAGES_ENABLED on.
 */
export async function GET({ params, request }) {
	return serveArchiveFrame(params.path, request.headers.get('if-none-match'));
}
