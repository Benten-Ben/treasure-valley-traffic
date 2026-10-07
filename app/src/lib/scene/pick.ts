import type { Selection } from '#lib/layers/types.js';
import { PRIORITY } from '#lib/layers/types.js';
import type { Hit, HitSource } from '#lib/map/picker.js';

/**
 * Picking on the CPU (docs/14 §14.8, "Drawing"): each instance's screen
 * centre and radius are stored while it renders, and hover and click test
 * them within max(radius, 14 px) (22 px for touch) through the central
 * picker. The picker ranks by priority (bus > camera > hub > stop > route…),
 * so a click on a 3D bus never also selects the route under it.
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

	/** The picker's hit test: everything within max(its radius, minRadius) of (x, y). */
	hits(x: number, y: number, minRadius: number): Hit[] {
		const out: Hit[] = [];
		for (const p of this.#placed) {
			const d = Math.hypot(p.x - x, p.y - y);
			if (d <= Math.max(p.r, minRadius)) out.push({ selection: p.pick, priority: p.priority, distance: d });
		}
		return out;
	}
}
