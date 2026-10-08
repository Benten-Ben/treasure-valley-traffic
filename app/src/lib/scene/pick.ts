import type { Selection } from '#lib/layers/types.js';
import { PRIORITY } from '#lib/layers/types.js';
import type { Hit, HitSource } from '#lib/map/picker.js';

/**
 * Picking on the CPU (docs/14 §14.8, "Drawing"): each instance's screen
 * centre and radius are stored while it renders, and hover and click test
 * them within max(radius, 14 px) (22 px for touch) through the central
 * picker. The picker ranks by priority (bus > camera > hub > stop > route…),
 * so a click on a 3D bus never also selects the route under it.
 *
 * An instance can give a screen segment instead (`seg`, a vertical capsule:
 * trees, from trunk to top): it's hit within its radius of that segment.
 * Where the point is on several such capsules (trees in front of each
 * other), only the one nearest the camera is seen there: it's hit at
 * distance 0, and those behind it aren't hit.
 */
export interface Placed {
	x: number;
	y: number;
	/** Screen radius, px. */
	r: number;
	/** Distance from the camera (clip w), to prefer the nearer of two at one priority. */
	w: number;
	pick: Selection;
	priority: number;
	/** A vertical capsule's axis on screen, [x1, y1, x2, y2] px: hit within `r` of it (x, y stay its centre). */
	seg?: [number, number, number, number];
}

/** Distance from (x, y) to the segment (x1, y1)–(x2, y2), px. */
export function segmentDistance(x: number, y: number, [x1, y1, x2, y2]: readonly [number, number, number, number]): number {
	const dx = x2 - x1;
	const dy = y2 - y1;
	const len2 = dx * dx + dy * dy;
	const t = len2 > 0 ? Math.min(1, Math.max(0, ((x - x1) * dx + (y - y1) * dy) / len2)) : 0;
	return Math.hypot(x - (x1 + t * dx), y - (y1 + t * dy));
}

export const priorityOf = (s: Selection, override?: number) => override ?? PRIORITY[s.kind as keyof typeof PRIORITY] ?? PRIORITY.sprite;

/** A selection's identity (kind, layer, id). */
export const selectionKey = (s: Selection | null | undefined) => (s ? `${s.kind}\u0000${s.layer}\u0000${s.id}` : '');

export class PickIndex implements HitSource {
	#placed: Placed[] = [];
	#next: Placed[] = [];

	/** Start collecting a frame's placements. */
	begin(): void {
		this.#next = [];
	}

	add(p: Placed): void {
		this.#next.push(p);
	}

	/** The frame is drawn: its placements are what hits test. */
	commit(): void {
		this.#placed = this.#next;
	}

	clear(): void {
		this.#placed = [];
		this.#next = [];
	}

	get size(): number {
		return this.#placed.length;
	}

	placed(): readonly Placed[] {
		return this.#placed;
	}

	/**
	 * The picker's hit test: everything within max(its radius, minRadius) of (x, y) (of its segment, for a
	 * capsule). Of the capsules the point is on, only the nearest to the camera, at distance 0.
	 */
	hits(x: number, y: number, minRadius: number): Hit[] {
		const out: Hit[] = [];
		let front: Placed | null = null;
		for (const p of this.#placed) {
			const d = p.seg ? segmentDistance(x, y, p.seg) : Math.hypot(p.x - x, p.y - y);
			if (d > Math.max(p.r, minRadius)) continue;
			if (p.seg && d <= p.r) {
				if (!front || p.w < front.w) front = p;
			} else out.push({ selection: p.pick, priority: p.priority, distance: d });
		}
		if (front) out.unshift({ selection: front.pick, priority: front.priority, distance: 0 });
		return out;
	}
}
