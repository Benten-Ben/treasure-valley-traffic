/**
 * What Calibrate mode's banner shows (docs/14 §14.3: in a mode, its banner
 * replaces the toolbar). The calibrate page writes it; the banner, mounted
 * by the chrome through WP2's banner slot, only reads it.
 */
class CalibrateState {
	name = $state('');
	/** What the next click should be. */
	step = $state<'image' | 'map' | 'either'>('either');
	/** Finished pairs, and the fit once there are enough. */
	pairs = $state(0);
	rms = $state<number | null>(null);
	/** There are changes not saved to the database yet (kept as a draft). */
	draft = $state(false);
}

export const calibrate = new CalibrateState();
