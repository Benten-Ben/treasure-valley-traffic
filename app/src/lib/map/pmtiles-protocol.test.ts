import { describe, expect, it } from 'vitest';
import { tileAnswers, tileProtocol } from './pmtiles-protocol.js';
import { errorDetail } from './errors.js';

const URL_T = 'pmtiles://http://x/tiles/terrain.pmtiles/11/362/747';
const png = () => new Uint8Array([0x89, 0x50, 0x4e, 0x47, 1, 2, 3, 4]);
const readerOf = (tile: (p: unknown, a: AbortController) => Promise<unknown>) => async () => ({ tile }) as never;

describe('the PMTiles protocol handler (#368)', () => {
	it('answers a tile as the reader does, and logs its length and first bytes', async () => {
		const src = png();
		const result = { data: src, cacheControl: 'c' };
		const h = tileProtocol(readerOf(async () => result));
		expect(await h({ url: URL_T }, new AbortController())).toBe(result);
		expect(tileAnswers().at(-1)).toEqual({ url: URL_T, bytes: 8, aborted: false, head: '89504e47' });
	});

	it('logs aborted when the reader itself throws the abort', async () => {
		const abort = new AbortController();
		const h = tileProtocol(
			readerOf(async () => {
				abort.abort();
				throw new DOMException('aborted', 'AbortError');
			})
		);
		await expect(h({ url: URL_T }, abort)).rejects.toMatchObject({ name: 'AbortError' });
		expect(tileAnswers().at(-1)).toMatchObject({ url: URL_T, bytes: -1, aborted: true });
	});

	it('works through the real pmtiles Protocol (fake source), and logs a request aborted before it', async () => {
		const { Protocol } = await import('pmtiles');
		const proto = new Protocol({ metadata: false });
		const fake = {
			getKey: () => 'k',
			getBytes: async () => {
				throw new Error('unreachable source');
			}
		};
		proto.add({ source: fake, getHeader: async () => { throw new Error('no header'); } } as never);
		const abort = new AbortController();
		abort.abort();
		const h = tileProtocol(async () => proto);
		await expect(h({ url: 'pmtiles://http://x/tiles/real.pmtiles/1/0/0' }, abort)).rejects.toBeDefined();
		expect(tileAnswers().at(-1)).toMatchObject({ bytes: -1, aborted: true });
	});

	it('passes a missing tile and TileJSON through untouched, and logs nothing for the TileJSON', async () => {
		const before = tileAnswers().length;
		const json = { data: { tiles: ['x'] } };
		const hj = tileProtocol(readerOf(async () => json));
		expect(await hj({ url: 'pmtiles://http://x/tiles/terrain.pmtiles', type: 'json' }, new AbortController())).toBe(json);
		expect(tileAnswers().length).toBe(before);
		const hn = tileProtocol(readerOf(async () => ({ data: null })));
		expect(await hn({ url: URL_T }, new AbortController())).toEqual({ data: null });
	});

	it('does not log a failed read as bytes', async () => {
		const h = tileProtocol(readerOf(async () => Promise.reject(new Error('Bad response code: 500'))));
		await expect(h({ url: URL_T }, new AbortController())).rejects.toThrow('500');
		expect(tileAnswers().at(-1)).toMatchObject({ bytes: -1, aborted: false });
	});

	it('names the bytes handed to the decoder in the map error detail', () => {
		const ev = { error: { name: 'InvalidStateError', message: 'The source image could not be decoded' }, sourceId: 'terrain', tile: { tileID: { canonical: { z: 11, x: 362, y: 747 } } } };
		const detail = errorDetail(ev, [
			{ url: URL_T, bytes: 217578, aborted: false, head: '89504e47' },
			{ url: 'pmtiles://http://x/tiles/other.pmtiles/11/1/1', bytes: 5, aborted: false, head: '00' }
		]);
		expect(detail).toBe('InvalidStateError: The source image could not be decoded · source terrain · tile 11/362/747 · handed terrain.pmtiles: 217578 bytes, head 89504e47, not aborted');
		expect(errorDetail(ev)).not.toContain('handed');
		// Two archives at the same z/x/y: the source's own archive is the one named.
		const both = errorDetail(ev, [
			{ url: URL_T, bytes: 9, aborted: false, head: '89504e47' },
			{ url: 'pmtiles://http://x/tiles/other.pmtiles/11/362/747', bytes: 5, aborted: false, head: '00' }
		]);
		expect(both).toContain('handed terrain.pmtiles: 9 bytes');
		expect(both).not.toContain('other.pmtiles');
	});
});
