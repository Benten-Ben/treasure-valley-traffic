import type { AppCtx } from '#lib/app/context.js';
import type { OverlayInstance } from './overlay.svelte.js';

/**
 * The overlay's test page (`/?overlay-test`, like WP9's `?scene-test`): 1,000
 * sprites in a grid over the current view, which can be set moving. The
 * `layers` spec checks that each sits within 0.5 px of `map.project` with
 * terrain on, that the picker finds them, and that moving them makes no
 * `setData` call. Loaded only when the URL asks for it.
 */
export interface OverlayTestHandle {
	count: number;
	ok(): boolean;
	positions(): { id: string; x: number; y: number; lng: number; lat: number }[];
	setMoving(on: boolean): void;
	frames(): number;
	lastFrameMs(): number;
	/** Lay the grid out again over the current view. */
	reset(): void;
}

const GROUP = 'overlay-test';

export function startOverlayTest(app: AppCtx, count = 1000): OverlayTestHandle {
	const o = app.overlay;
	o.sprite({
		key: 'test-dot',
		width: 12,
		height: 12,
		draw(g) {
			g.arc(6, 6, 4.5, 0, Math.PI * 2);
			g.fillStyle = '#2c8c99';
			g.fill();
			g.lineWidth = 1.5;
			g.strokeStyle = '#fffbf4';
			g.stroke();
		}
	});
	let instances: OverlayInstance[] = [];
	let base: [number, number][] = [];
	let moving = false;

	const reset = () => {
		const map = app.map;
		if (!map) return;
		const canvas = map.getCanvas();
		const w = canvas.clientWidth;
		const h = canvas.clientHeight;
		const cols = 40;
		const rows = Math.ceil(count / cols);
		instances = [];
		base = [];
		for (let i = 0; i < count; i++) {
			// A grid over the middle of the screen (clear of the bars), unprojected onto the map.
			const x = w * (0.12 + (0.76 * ((i % cols) + 0.5)) / cols);
			const y = h * (0.2 + (0.6 * (Math.floor(i / cols) + 0.5)) / rows);
			const ll = map.unproject([x, y]);
			base.push([ll.lng, ll.lat]);
			instances.push({
				id: `t${i}`,
				lng: ll.lng,
				lat: ll.lat,
				sprite: 'test-dot',
				pick: { kind: 'sprite', id: `t${i}`, layer: 'overlay-test', title: `Test sprite ${i}`, fact: 'An overlay test sprite' }
			});
		}
		o.set(GROUP, instances, { z: 100 });
	};

	const update = (now: number) => {
		if (!moving) return false;
		const t = now / 1000;
		for (let k = 0; k < instances.length; k++) {
			// Small circles, about 15 m across.
			instances[k].lng = base[k][0] + 0.0001 * Math.cos(t + k);
			instances[k].lat = base[k][1] + 0.00007 * Math.sin(t + k);
		}
		return 8; // m/s, about 0.0001° of longitude per second
	};

	reset();
	return {
		count,
		ok: () => o.ok,
		positions: () => o.positions(GROUP),
		setMoving(on: boolean) {
			moving = on;
			o.update(GROUP, on ? update : null);
		},
		frames: () => o.frames,
		lastFrameMs: () => o.lastFrameMs,
		reset
	};
}
