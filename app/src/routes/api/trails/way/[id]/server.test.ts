import { beforeEach, describe, expect, it, vi } from 'vitest';

/**
 * GET /api/trails/way/[id] and /api/trails/line/[id] (#lib/server/trails/card): the routes with the
 * database and the card queries replaced by fakes.
 */
const { cards } = vi.hoisted(() => ({ cards: { way: null as object | null, line: null as object | null, asked: [] as number[] } }));

vi.mock('#lib/server/db.js', () => ({ db: () => ({}) }));
vi.mock('#lib/server/trails/card.js', () => ({
	wayCard: async (_sql: unknown, id: number) => (cards.asked.push(id), cards.way),
	lineCard: async (_sql: unknown, id: number) => (cards.asked.push(id), cards.line)
}));

async function status(run: () => Promise<Response>): Promise<{ status: number; body?: unknown; res?: Response }> {
	try {
		const res = await run();
		return { status: res.status, body: await res.json(), res };
	} catch (e) {
		return { status: (e as { status: number }).status };
	}
}
const request = (headers: Record<string, string> = {}) => new Request('http://x/api/trails/way/1', { headers });

describe('the card routes', () => {
	beforeEach(() => {
		cards.way = null;
		cards.line = null;
		cards.asked = [];
	});

	it('answer a way card with an ETag, and 304 for the same one', async () => {
		cards.way = { id: 9500000001, kind: 'path' };
		const { GET } = await import('./+server.js');
		const a = await status(() => GET({ params: { id: '9500000001' }, request: request() } as never));
		expect(a.status).toBe(200);
		expect(a.body).toEqual(cards.way);
		expect(cards.asked).toEqual([9500000001]);
		const etag = a.res!.headers.get('etag')!;
		expect(etag).toBeTruthy();
		const res = await GET({ params: { id: '9500000001' }, request: request({ 'if-none-match': etag }) } as never);
		expect(res.status).toBe(304);
	});

	it('say 404 for a way without a card (private, a canal bank, unknown, before the migration) and 400 for a bad id', async () => {
		const { GET } = await import('./+server.js');
		expect((await status(() => GET({ params: { id: '5' }, request: request() } as never))).status).toBe(404);
		for (const id of ['abc', '-1', '1.5', '', '99999999999999999999']) expect((await status(() => GET({ params: { id }, request: request() } as never))).status, id).toBe(400);
		expect(cards.asked).toEqual([5]);
	});

	it('answer a line card the same way', async () => {
		const { GET } = await import('../../line/[id]/+server.js');
		cards.line = { line_id: 7 };
		expect((await status(() => GET({ params: { id: '7' }, request: request() } as never))).body).toEqual({ line_id: 7 });
		cards.line = null;
		expect((await status(() => GET({ params: { id: '8' }, request: request() } as never))).status).toBe(404);
		expect((await status(() => GET({ params: { id: 'x' }, request: request() } as never))).status).toBe(400);
	});
});
