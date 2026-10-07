import { hasCameraProvider } from '#lib/server/camera-provider.js';
import { db } from '#lib/server/db.js';
import { jsonWithEtag } from '#lib/server/json-etag.js';

/**
 * Every camera view's identity (WP12): which camera it belongs to and its
 * 511 image id. The Cameras layer joins this with /api/cameras/status (keyed
 * by view) to put the "recorded" notch on the key cameras' icons, and camera
 * windows use it to know a camera's views before its detail arrives.
 * `no-cache` with an ETag; the client adds `?v=` (cameras) from /api/meta.
 *
 * Shape: `{ views: [{ id, cameraId, imageId, sortOrder, direction }] }`,
 * `CameraViewRow` in #lib/layers/cameras/detail.ts.
 */
export async function GET({ request }) {
	const sql = db();
	// ACHD's cameras only: road-weather stations share the table (WP16, #lib/server/camera-provider).
	const achd = await hasCameraProvider(sql);
	const rows = await sql`
		select v.id, v.camera_id, v.image_id, v.sort_order, v.direction
		from core.camera_view v
		join core.camera c on c.id = v.camera_id
		where c.active ${achd ? sql`and c.provider = 'ACHD'` : sql``}
		order by v.camera_id, v.sort_order, v.id`;
	return jsonWithEtag(
		{
			views: rows.map((r) => ({
				id: Number(r.id),
				cameraId: Number(r.camera_id),
				imageId: r.image_id === null ? null : Number(r.image_id),
				sortOrder: r.sort_order,
				direction: r.direction
			}))
		},
		request.headers.get('if-none-match')
	);
}
