import { json } from '@sveltejs/kit';
import { liveViews, parseViews } from '#lib/server/frames.js';

/**
 * The newest frame of up to 12 views (docs/14 §14.6 "Live images"; contract
 * in #lib/contracts/live): recorded views from the capture archive, others
 * from the on-demand 511 fetcher. Views not in core.camera_view are left
 * out. With CAMERA_IMAGES_ENABLED off, every view answers `disabled`.
 */
export async function GET({ url, setHeaders }) {
	setHeaders({ 'cache-control': 'no-store' });
	return json(await liveViews(parseViews(url.searchParams.get('views'))));
}
