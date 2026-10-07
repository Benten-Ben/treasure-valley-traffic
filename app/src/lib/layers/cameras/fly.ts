import type { Map } from 'maplibre-gl';
import type { AppCtx } from '#lib/app/context.js';
import { historyOf } from '#lib/state/history.svelte.js';
import type { Point } from '#lib/state/windows.svelte.js';
import { flyTarget, paddedCentre } from './place.js';

const reducedMotion = () => typeof matchMedia !== 'undefined' && matchMedia('(prefers-reduced-motion: reduce)').matches;

/**
 * Fly to a camera (zoom 18, keeping the bearing, pitch 50) so that it lands
 * at `land` on screen (viewport px), or at the map's centre. A programmatic
 * fly: the view history keeps the view it leaves. Under reduced motion the
 * fly is a jump, which takes no offset, so the map is shifted by hand.
 * Returns where the camera lands.
 */
export function flyToCamera(app: AppCtx, map: Map, at: [number, number], land: Point | null): Point {
	const box = map.getContainer().getBoundingClientRect();
	const centre = paddedCentre(box, map.getPadding());
	const offset: [number, number] = land ? [land.x - centre.x, land.y - centre.y] : [0, 0];
	const to = { ...flyTarget(at, map.getBearing()), offset };
	const h = historyOf(app);
	if (h.attached) h.fly(to);
	else map.flyTo(to);
	if (reducedMotion() && (offset[0] || offset[1])) map.panBy([-offset[0], -offset[1]], { animate: false });
	return { x: centre.x + offset[0], y: centre.y + offset[1] };
}
