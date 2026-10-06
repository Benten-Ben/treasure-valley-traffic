import { json } from '@sveltejs/kit';
import { cameraStatus } from '#lib/server/frames.js';

/**
 * Capture state of every recorded view (docs/14 §14.6; contract in
 * #lib/contracts/live): each capture service's cadence, heartbeat and
 * low-disk pause, from its status file. Reused for 15 s on the server.
 */
export async function GET({ setHeaders }) {
	setHeaders({ 'cache-control': 'no-cache' });
	return json(await cameraStatus());
}
