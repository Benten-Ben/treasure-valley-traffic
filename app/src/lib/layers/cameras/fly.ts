import type { Map } from 'maplibre-gl';
import type { AppCtx } from '#lib/app/context.js';
import { historyOf } from '#lib/state/history.svelte.js';
import type { Point } from '#lib/state/windows.svelte.js';
import { flyTarget, paddedCentre } from './place.js';

/**
 * Fly to a camera (zoom 18, keeping the bearing, pitch 50) so that it lands
 * at `land` on screen (viewport px), or else in the middle of the map's
 * padding, or of the area the inspect card leaves while it's open
 * (`app.landing`, §14.3 "Regions"). A programmatic fly: the view history
 * keeps the view it leaves, and under reduced motion jumps there with the
 * same offset. Returns where the camera lands.
 */
export function flyToCamera(app: AppCtx, map: Map, at: [number, number], land: Point | null): Point {
	const box = map.getContainer().getBoundingClientRect();
	const centre = paddedCentre(box, map.getPadding());
	const card = land ? null : app.landing?.();
	const to = land ?? (card ? paddedCentre(box, card.padding) : centre);
	const offset: [number, number] = [to.x - centre.x, to.y - centre.y];
	const fly = { ...flyTarget(at, map.getBearing()), offset };
	const h = historyOf(app);
	if (h.attached) h.fly(fly);
	else map.flyTo(fly);
	return { x: centre.x + offset[0], y: centre.y + offset[1] };
}
