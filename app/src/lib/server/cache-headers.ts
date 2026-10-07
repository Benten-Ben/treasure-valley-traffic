/**
 * Cache-Control for versioned data URLs (docs/14 §14.8 "APIs", §14.9 fix 6).
 *
 * The client asks for data with the version /api/meta reported (`?v=`). When
 * that's the server's current version, the answer can never change, so it's
 * cached for good; otherwise (no `v`, an old one, or no version at all) it
 * answers with the current data under a short or no-cache policy, so the
 * client sees new data as soon as it asks with the new version.
 */
export const IMMUTABLE = 'public, max-age=31536000, immutable';

/** `IMMUTABLE` when `requested` is the current version, else `otherwise`. */
export function versionedCacheControl(requested: string | null | undefined, current: string | null | undefined, otherwise = 'no-cache'): string {
	return requested && current && requested === current ? IMMUTABLE : otherwise;
}
