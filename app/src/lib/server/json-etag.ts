import { createHash } from 'node:crypto';

/**
 * JSON answers that change rarely and are asked for often (the camera detail
 * and the view list; docs/14 §14.8 "APIs": `no-cache` with an ETag). The
 * browser revalidates every time, and an unchanged answer costs a 304 with
 * no body.
 */
export function jsonWithEtag(body: unknown, ifNoneMatch: string | null): Response {
	const text = JSON.stringify(body);
	const etag = `"${createHash('sha1').update(text).digest('base64url')}"`;
	const headers = { 'cache-control': 'no-cache', etag };
	if (matches(ifNoneMatch, etag)) return new Response(null, { status: 304, headers });
	return new Response(text, { headers: { ...headers, 'content-type': 'application/json' } });
}

/** If-None-Match against one strong ETag, compared weakly as RFC 9110 asks. */
export function matches(header: string | null, etag: string): boolean {
	if (!header) return false;
	if (header.trim() === '*') return true;
	return header.split(',').some((t) => t.trim().replace(/^W\//, '') === etag);
}
