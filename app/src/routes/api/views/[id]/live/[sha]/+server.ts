import { serveLiveFrame } from '#lib/server/frames.js';

/**
 * An on-demand 511 frame held in the server's memory (docs/14 §14.6), named
 * by its sha256, so it never changes: cached for a year, ETag answered with
 * 304. 404 once it has left memory.
 */
export async function GET({ params, request }) {
	return serveLiveFrame(Number(params.id), params.sha, request.headers.get('if-none-match'));
}
