/**
 * Map error events in words (create.ts logs every one): the console shows a
 * bare Error as just "Error", which named nothing in the 3D check's log
 * (Oct 8: two "map error Error" with Transit and Cameras on).
 */
export interface MapErrorLike {
	error?: { name?: string; message?: string; status?: number; url?: string } | null;
	sourceId?: string;
	tile?: { tileID?: { canonical?: { z: number; x: number; y: number } } };
}

/** The error's name, message, HTTP status and URL, and the source and tile it came from. */
export function errorDetail(ev: MapErrorLike): string {
	const e = ev.error ?? {};
	const c = ev.tile?.tileID?.canonical;
	const parts = [
		`${e.name || 'Error'}: ${e.message || '(no message)'}`,
		e.status !== undefined ? `status ${e.status}` : null,
		e.url ? `url ${e.url}` : null,
		ev.sourceId ? `source ${ev.sourceId}` : null,
		c ? `tile ${c.z}/${c.x}/${c.y}` : null
	];
	return parts.filter(Boolean).join(' · ');
}
