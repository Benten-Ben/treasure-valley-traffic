import type { Protocol } from 'pmtiles';

/** What the protocol handed MapLibre for one tile request (a bounded log, for the "map error detail" warning). */
export interface TileAnswer {
	url: string;
	/** Bytes handed to the decoder; -1 when the request failed or was dropped. */
	bytes: number;
	/** The request's abort signal had fired by the time the handler finished (answered or threw). */
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

/**
 * The `pmtiles://` protocol handler for MapLibre's `addProtocol`. It answers exactly as the pmtiles
 * Protocol does and only records what was handed over: every tile answer is logged (url, byte length,
 * whether the request's signal had fired, first bytes) on `globalThis.__tvtTileAnswers`, so a decode
 * error can say which bytes it was given (#368).
 */
export function tileProtocol(
	reader: () => Promise<Pick<Protocol, 'tile'>>
): (params: { url: string; type?: string }, abort: AbortController) => Promise<ProtocolResult | { data: unknown }> {
	return async (params, abort) => {
		const answer: TileAnswer = { url: params.url, bytes: -1, aborted: false, head: '' };
		try {
			const r = (await (await reader()).tile(params as never, abort)) as ProtocolResult & { data: unknown };
			if (r.data instanceof Uint8Array && r.data.byteLength > 0) {
				answer.bytes = r.data.byteLength;
				answer.head = hex(r.data);
			} else if (r.data instanceof Uint8Array) {
				answer.bytes = 0;
			}
			return r;
		} finally {
			answer.aborted = abort.signal.aborted;
			if (!params.url.endsWith('.json') && params.type !== 'json') record(answer);
		}
	};
}
