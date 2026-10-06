import type { CameraOptions } from 'maplibre-gl';
import type { AppCtx } from '#lib/app/context.js';
import { register, type KeyBinding } from './keys.js';

/**
 * WP2's own keys (docs/14 §14.3, "Keymap"): layers and the map camera, and
 * Help. Other packages register theirs from their own modules (Backspace:
 * WP3; Space and L: WP8; ← and →: WP13). Reserved for later: [ ] (speed),
 * C (camera wall), N (Valley Feed), / (search).
 */

/** Home: over Meridian, pitch 50, bearing −12. */
export const HOME = { center: [-116.3915, 43.6121] as [number, number], zoom: 13, pitch: 50, bearing: -12 };

const PAN_PX = 120;
const ROTATE_DEG = 15;
const TILT_DEG = 10;

export const reducedMotion = () => typeof matchMedia !== 'undefined' && matchMedia('(prefers-reduced-motion: reduce)').matches;

export function registerDefaultKeys(app: AppCtx, opts: { help: () => void }): () => void {
	const map = () => app.map;
	const ease = (o: CameraOptions) => {
		const m = map();
		if (!m) return;
		if (reducedMotion()) m.jumpTo(o);
		else m.easeTo({ duration: 220, ...o });
	};
	const fly = (o: CameraOptions) => {
		const m = map();
		if (!m) return;
		if (reducedMotion()) m.jumpTo(o);
		else m.flyTo({ duration: 1200, ...o });
	};
	const pan = (dx: number, dy: number) => {
		const m = map();
		if (!m) return;
		m.panBy([dx, dy], { duration: reducedMotion() ? 0 : 200 });
	};

	const list: KeyBinding[] = [
		{ id: 'all-layers', codes: ['Digit1'], label: '1', description: 'All data layers off; again to restore', group: 'Layers', run: () => app.layers.allOff() }
	];
	for (const d of app.layers.defs) {
		if (!d.key) continue;
		list.push(
			{ id: `layer-${d.id}`, codes: [`Digit${d.key}`, `Numpad${d.key}`], label: d.key, description: `Toggle ${d.title}`, group: 'Layers', run: () => app.layers.toggle(d.id) },
			{ id: `solo-${d.id}`, codes: [`Digit${d.key}`], shift: true, label: `Shift+${d.key}`, description: `Only ${d.title}; again to restore`, group: 'Layers', run: () => app.layers.solo(d.id) }
		);
	}
	list.push(
		{ id: 'pan-north', codes: ['KeyW'], shift: 'any', label: 'W A S D', description: 'Pan', group: 'Camera', run: () => pan(0, -PAN_PX) },
		{ id: 'pan-west', codes: ['KeyA'], shift: 'any', label: 'A', description: 'Pan left', group: 'Camera', help: false, run: () => pan(-PAN_PX, 0) },
		{ id: 'pan-south', codes: ['KeyS'], shift: 'any', label: 'S', description: 'Pan down', group: 'Camera', help: false, run: () => pan(0, PAN_PX) },
		{ id: 'pan-east', codes: ['KeyD'], shift: 'any', label: 'D', description: 'Pan right', group: 'Camera', help: false, run: () => pan(PAN_PX, 0) },
		{ id: 'rotate-left', codes: ['KeyQ'], label: 'Q / E', description: `Rotate ${ROTATE_DEG}° left / right`, group: 'Camera', run: () => ease({ bearing: (map()?.getBearing() ?? 0) - ROTATE_DEG }) },
		{ id: 'rotate-right', codes: ['KeyE'], label: 'E', description: 'Rotate right', group: 'Camera', help: false, run: () => ease({ bearing: (map()?.getBearing() ?? 0) + ROTATE_DEG }) },
		{ id: 'tilt-up', codes: ['KeyR'], label: 'R / F', description: `Tilt up / down ${TILT_DEG}°`, group: 'Camera', run: () => ease({ pitch: Math.min(map()?.getMaxPitch() ?? 75, (map()?.getPitch() ?? 0) + TILT_DEG) }) },
		{ id: 'tilt-down', codes: ['KeyF'], label: 'F', description: 'Tilt down', group: 'Camera', help: false, run: () => ease({ pitch: Math.max(0, (map()?.getPitch() ?? 0) - TILT_DEG) }) },
		{ id: 'home', codes: ['KeyH'], label: 'H', description: 'Home: over Meridian', group: 'Camera', run: () => fly(HOME) },
		{
			id: 'overview',
			codes: ['KeyO'],
			label: 'O',
			description: 'Overview: the whole valley, straight down',
			group: 'Camera',
			run: () => {
				const m = map();
				const b = app.manifest?.bounds;
				if (!m || !b) return;
				const cam = m.cameraForBounds([[b[0], b[1]], [b[2], b[3]]], { padding: 40, bearing: 0, pitch: 0 });
				if (cam) fly({ ...cam, bearing: 0, pitch: 0 });
			}
		},
		{ id: 'help', codes: ['Slash'], shift: true, label: '?', description: 'Help (this list)', group: 'Help', modes: ['explore', 'look', 'calibrate'], run: () => opts.help() }
	);
	return register(list);
}
