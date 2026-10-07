import type { Box } from '#lib/calibration/frustum.js';

/**
 * What the look-through banner (the HUD) and the picture's frame show (docs/14
 * §14.6 "Look through", steps 4, 8 and 9; WP13). The look-through controller
 * (lookthrough.ts, a lazy chunk) writes it; the always-mounted pieces only
 * read it. Nothing here changes per frame: the fade writes the frame's
 * opacity straight to its element (`fade`), never through Svelte state.
 */
export type LookPhase = 'off' | 'flying' | 'looking' | 'leaving' | 'ending';

export interface LookActions {
	stepOut(): void;
	/** The next (1) or previous (−1) calibrated camera by distance. */
	next(dir: 1 | -1): void;
	/** The opacity slider, 0–1. */
	setSlider(v: number): void;
}

class LookState {
	phase = $state<LookPhase>('off');
	cameraId = $state<number | null>(null);
	viewId = $state<number | null>(null);
	name = $state('');
	/** The whole picture's letterbox on the map canvas (CSS px from its top left), while looking: image pixels map onto it. */
	box = $state.raw<Box | null>(null);
	/** The part of it the photo plane covers (the picture without the 511 bar, with the plane's frame): the vignette's hole. */
	shown = $state.raw<Box | null>(null);
	/** The slider, 0–1. */
	slider = $state(1);
	/** Where this camera is in the ← → order, and how many there are. */
	index = $state(0);
	count = $state(0);
	/** The picture shown is the calibration's reference frame (no live picture yet). */
	reference = $state(false);
	/** A message while it can't place the camera, or why it left. */
	problem = $state<string | null>(null);
	actions: LookActions | null = null;
	/** The frame's element (the vignette), faded directly. */
	frame: HTMLElement | null = null;

	get active(): boolean {
		return this.phase !== 'off';
	}

	/** The picture's fade (0–1), applied to the frame and vignette without a Svelte update. */
	fade(o: number): void {
		if (this.frame) this.frame.style.opacity = String(Math.max(0, Math.min(1, o)));
	}
}

export const look = new LookState();
