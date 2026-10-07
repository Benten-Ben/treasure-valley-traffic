import { error } from '@sveltejs/kit';
import type { CameraDetail } from '#lib/layers/cameras/detail.js';

/**
 * The calibrator on the shared map (docs/14 §14.6, "Calibrating on the map").
 * `?view=<id>` picks one of the camera's views; otherwise the first (the panel
 * keeps it in the URL, so a reload resumes that view's draft). An unknown
 * camera is an error shown inside the map layout. (ssr = false comes from the
 * map layout.)
 */
export async function load({ fetch, params, url }) {
	const res = await fetch(`/api/cameras/${params.id}`);
	if (!res.ok) error(res.status, (await res.json().catch(() => null))?.message ?? 'Camera not found');
	const view = Number(url.searchParams.get('view'));
	return { camera: (await res.json()) as CameraDetail, viewId: Number.isInteger(view) && view > 0 ? view : null };
}
