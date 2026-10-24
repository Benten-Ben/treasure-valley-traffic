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

/** One answer of the PMTiles protocol (pmtiles-protocol.ts): what the decoder was handed for a URL. */
export interface AnswerLike {
	url: string;
	bytes: number;
	aborted: boolean;
	head: string;
}

/**
 * The error's name, message, HTTP status and URL, and the source and tile it came from. With the
 * protocol's recent answers, the last ones for that tile too: the byte length handed to the decoder,
 * the first bytes, and whether the request had been aborted (a PMTiles range answer is always
 * application/octet-stream, so the network log cannot tell an image from anything else).
 */
export function errorDetail(ev: MapErrorLike, answers: readonly AnswerLike[] = []): string {
	const e = ev.error ?? {};
	const c = ev.tile?.tileID?.canonical;
	const parts = [
		`${e.name || 'Error'}: ${e.message || '(no message)'}`,
		e.status !== undefined ? `status ${e.status}` : null,
		e.url ? `url ${e.url}` : null,
		ev.sourceId ? `source ${ev.sourceId}` : null,
		c ? `tile ${c.z}/${c.x}/${c.y}` : null
	];
	if (c) {
		const tail = `/${c.z}/${c.x}/${c.y}`;
		for (const a of answers.filter((x) => x.url.endsWith(tail)).slice(-3)) {
			parts.push(`handed ${a.url.split('/').slice(-4, -3)[0]}: ${a.bytes} bytes, head ${a.head || '-'}, ${a.aborted ? 'aborted' : 'not aborted'}`);
		}
	}
	return parts.filter(Boolean).join(' · ');
}
