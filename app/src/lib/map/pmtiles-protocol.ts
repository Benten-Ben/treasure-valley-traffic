import type { Protocol } from 'pmtiles';

/** What the protocol handed MapLibre for one tile request (a bounded log, for the "map error detail" warning). */
export interface TileAnswer {
	url: string;
	/** Bytes handed to the decoder; -1 when the request failed or was dropped. */
	bytes: number;
	/** The request's abort signal had fired by the time the reader answered. */
	aborted: boolean;
	/** The first bytes in hex (a PNG starts 89504e47, a WebP 52494646), to tell an image from anything else. */
	head: string;
}

export interface ProtocolResult {
	data: Uint8Array | null;
	cacheControl?: string;
	expires?: string;
}

const LOG_SIZE = 300;
const log: TileAnswer[] = [];

/** The most recent answers, oldest first. */
export const tileAnswers = (): readonly TileAnswer[] => log;

function record(a: TileAnswer): void {
	log.push(a);
	if (log.length > LOG_SIZE) log.splice(0, log.length - LOG_SIZE);
	(globalThis as { __tvtTileAnswers?: readonly TileAnswer[] }).__tvtTileAnswers = log;
}

const hex = (d: Uint8Array): string => Array.from(d.subarray(0, 4), (b) => b.toString(16).padStart(2, '0')).join('');

/** An AbortError, as MapLibre expects to ignore. */
function abortError(signal: AbortSignal): Error {
	const r = signal.reason;
	if (r instanceof Error) return r;
	const e = new Error('The tile request was aborted');
	e.name = 'AbortError';
	return e;
}

/**
 * The `pmtiles://` protocol handler for MapLibre's `addProtocol`.
 *
 * - A request that was aborted gets no answer: it throws the abort. The reader can resolve a request
 *   whose signal fired during its last await (its own check runs one step earlier), and MapLibre would
 *   then decode bytes nobody asked for any more (#368).
 * - The bytes are copied out of the reader's buffer, so the decoder never shares memory with the reader.
 * - Every answer is logged (url, byte length, aborted, first bytes), and the log is on
 *   `globalThis.__tvtTileAnswers`, so a decode error can say which bytes it was given.
 */
export function tileProtocol(
	reader: () => Promise<Pick<Protocol, 'tile'>>
): (params: { url: string; type?: string }, abort: AbortController) => Promise<ProtocolResult | { data: unknown }> {
	return async (params, abort) => {
		const answer: TileAnswer = { url: params.url, bytes: -1, aborted: false, head: '' };
		try {
			const r = (await (await reader()).tile(params as never, abort)) as ProtocolResult & { data: unknown };
			answer.aborted = abort.signal.aborted;
			if (answer.aborted) throw abortError(abort.signal);
			if (!(r.data instanceof Uint8Array)) return r; // TileJSON, or a missing tile (null)
			if (r.data.byteLength === 0) {
				answer.bytes = 0;
				return r; // a missing vector tile: empty, and MapLibre does not decode it
			}
			const copy = r.data.slice();
			answer.bytes = copy.byteLength;
			answer.head = hex(copy);
			return { ...r, data: copy };
		} finally {
			if (!params.url.endsWith('.json') && params.type !== 'json') record(answer);
		}
	};
}
