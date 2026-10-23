/**
 * Per-group instance caps (plan §3.2): a group keeps at most `cap` instances, the ones nearest the
 * view's ground centre and within `radiusM`; on a phone `capPhone` replaces `cap` (0 turns the group
 * off). Pure and allocation-free after warm-up, so the scene can run it every frame.
 */
export interface CapOptions {
	cap?: number;
	capPhone?: number;
	radiusM?: number;
}

const DEG = Math.PI / 180;
/** Metres per degree of latitude (and of longitude at the equator). */
export const M_PER_DEG = (6371008.8 * Math.PI) / 180;

/** The k-th smallest (0-based) of a[0..n), rearranging a. */
export function kthSmallest(a: Float64Array, n: number, k: number): number {
	let lo = 0;
	let hi = n - 1;
	while (lo < hi) {
		const pivot = a[(lo + hi) >> 1];
		let i = lo;
		let j = hi;
		while (i <= j) {
			while (a[i] < pivot) i++;
			while (a[j] > pivot) j--;
			if (i <= j) {
				const t = a[i];
				a[i++] = a[j];
				a[j--] = t;
			}
		}
		if (k <= j) hi = j;
		else if (k >= i) lo = i;
		else return a[k];
	}
	return a[k];
}

export class CapLimiter<T extends { lng: number; lat: number }> {
	#kept: T[] = [];
	#d2 = new Float64Array(0);
	#sel = new Float64Array(0);
	#cand = new Int32Array(0);

	/**
	 * `src` after the caps: those within `radiusM` of (lng, lat), and of them the nearest `cap` (`capPhone` on a phone),
	 * in the group's order. `src` itself when nothing limits it; otherwise a scratch list, valid until the next call.
	 */
	limit(src: T[], opts: CapOptions, lng: number, lat: number, phone: boolean): T[] {
		const { cap, capPhone, radiusM } = opts;
		const limit = phone && capPhone !== undefined ? capPhone : cap;
		if (limit === undefined && radiusM === undefined) return src;
		const kept = this.#kept;
		kept.length = 0;
		if (limit !== undefined && limit <= 0) return kept;
		const n = src.length;
		if (this.#d2.length < n) {
			const size = Math.max(n, this.#d2.length * 2);
			this.#d2 = new Float64Array(size);
			this.#sel = new Float64Array(size);
			this.#cand = new Int32Array(size);
		}
		const d2 = this.#d2;
		const cand = this.#cand;
		const kx = M_PER_DEG * Math.cos(lat * DEG);
		const r2 = radiusM === undefined ? Infinity : radiusM * radiusM;
		let m = 0;
		for (let i = 0; i < n; i++) {
			const dx = (src[i].lng - lng) * kx;
			const dy = (src[i].lat - lat) * M_PER_DEG;
			const d = dx * dx + dy * dy;
			if (d > r2) continue;
			d2[m] = d;
			cand[m++] = i;
		}
		if (limit === undefined || m <= limit) {
			for (let c = 0; c < m; c++) kept.push(src[cand[c]]);
			return kept;
		}
		// More than the cap: keep the `limit` nearest (ties at the edge, in the group's order).
		this.#sel.set(d2.subarray(0, m));
		const edge = kthSmallest(this.#sel, m, limit - 1);
		let below = 0;
		for (let c = 0; c < m; c++) if (d2[c] < edge) below++;
		let ties = limit - below;
		for (let c = 0; c < m; c++) {
			if (d2[c] < edge || (d2[c] === edge && ties-- > 0)) kept.push(src[cand[c]]);
		}
		return kept;
	}
}
