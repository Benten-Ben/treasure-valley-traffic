/**
 * Data fetches that start before a layer's code arrives (docs/14 §14.8,
 * "Boot"): each enabled layer's data fetch starts the moment /api/meta
 * resolves, since its URL carries a version, while the layer's own chunk is
 * still loading. A def's `prefetch` starts the request here; the module takes
 * the same response when it mounts (or fetches afresh, after a Retry).
 */
const pending = new Map<string, Promise<Response>>();

/** Start fetching `url` now (once). */
export function prefetch(url: string): Promise<Response> {
	let p = pending.get(url);
	if (!p) {
		p = fetch(url);
		// An unclaimed failure must not surface as an unhandled rejection.
		p.catch(() => {});
		pending.set(url, p);
	}
	return p;
}

/** The prefetched response for `url` (taken: a later call fetches again), or a fresh fetch. */
export function take(url: string, init?: RequestInit): Promise<Response> {
	const p = pending.get(url);
	pending.delete(url);
	return p ?? fetch(url, init);
}
