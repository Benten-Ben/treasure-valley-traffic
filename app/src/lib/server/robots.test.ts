import { describe, expect, it, vi } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { AGENT_TOKEN, Robots, RobotsCache, USER_AGENT, lenientLines } from './robots.js';

// The same cases as ingest/tests/test_ingest.py (RobotsTest, RobotsUnavailableTest).
describe('Robots (port of ingest/http.py)', () => {
	it('applies a rule after a blank line inside the group', () => {
		// ACHD's file
		expect(new Robots('User-agent: *\n\nDisallow: /\n').allowed('https://x/ATIS/CCTV/1.jpg')).toBe(false);
	});

	it('handles a BOM, CRLF and matches case-insensitively', () => {
		// 511 Idaho's file
		const r = new Robots('\uFEFFuser-agent: *\r\ndisallow: /map/map*/\r\ndisallow: /list/GetData/\r\n');
		expect(r.allowed('https://511.idaho.gov/list/getdata/Cameras')).toBe(false);
		expect(r.allowed('https://511.idaho.gov/Map/MapIcons/x')).toBe(false);
		expect(r.allowed('https://511.idaho.gov/map/Cctv/656')).toBe(true);
	});

	it('applies rules without a User-agent line to everyone', () => {
		// IEM's file
		const r = new Robots('# IEM\n\nCrawl-delay: 120\nDisallow: /usage/\n');
		expect(r.allowed('https://x/usage/a')).toBe(false);
		expect(r.crawlDelay()).toBe(120);
	});

	it('lets the longest match win and honors the $ anchor', () => {
		const r = new Robots('User-agent: *\nDisallow: /wp-admin/\nAllow: /wp-admin/admin-ajax.php\nDisallow: /*.pdf$\n');
		expect(r.allowed('https://x/wp-admin/admin-ajax.php')).toBe(true);
		expect(r.allowed('https://x/wp-admin/edit.php')).toBe(false);
		expect(r.allowed('https://x/a/b.pdf')).toBe(false);
		expect(r.allowed('https://x/a/b.pdf?page=2')).toBe(true);
	});

	it('prefers a group naming our agent over the wildcard group', () => {
		const r = new Robots('User-agent: *\nDisallow: /\n\nUser-agent: treasure-valley-traffic\nAllow: /map/Cctv/\nDisallow: /\n');
		expect(r.allowed('https://511.idaho.gov/map/Cctv/656')).toBe(true);
		expect(r.allowed('https://511.idaho.gov/list/')).toBe(false);
	});

	it('normalizes lines like the Python version', () => {
		expect(lenientLines('\uFEFF# c\n\nDisallow: /a # note\n')).toEqual(['User-agent: *', 'Disallow: /a']);
	});
});

describe('RobotsCache', () => {
	const URL_ = 'https://511.idaho.gov/map/Cctv/656';

	it('treats an unreadable robots.txt as blocked for now, and retries it next time', async () => {
		const fetch = vi.fn(async () => {
			throw new Error('connection reset by peer');
		});
		const cache = new RobotsCache({ fetch });
		const v = await cache.check(URL_);
		expect(v).toMatchObject({ allowed: false, decision: 'unavailable' });
		await cache.check(URL_);
		expect(fetch).toHaveBeenCalledTimes(2); // not cached: retried
	});

	it('treats a 5xx as blocked for now, a 4xx as no rules', async () => {
		const five = new RobotsCache({ fetch: async () => new Response('down', { status: 503 }) });
		expect((await five.check(URL_)).decision).toBe('unavailable');
		const four = new RobotsCache({ fetch: async () => new Response('nope', { status: 404 }) });
		expect(await four.check(URL_)).toMatchObject({ allowed: true, decision: 'no_rules' });
	});

	it('reads an HTML page answered with 200 as no rules', async () => {
		const c = new RobotsCache({ fetch: async () => new Response('<!doctype html><HTML><body>Not found</body></HTML>') });
		expect(await c.check(URL_)).toMatchObject({ allowed: true, decision: 'no_rules' });
	});

	it('fetches robots.txt with our User-Agent once per host for 24 h, single-flight', async () => {
		let t = 0;
		const fetch = vi.fn(async (_url: string, _init?: RequestInit) => new Response('User-agent: *\nDisallow: /list/\n'));
		const c = new RobotsCache({ fetch, now: () => t });
		await Promise.all([c.check(URL_), c.check(URL_), c.check('https://511.idaho.gov/list/x')]);
		expect(fetch).toHaveBeenCalledTimes(1);
		const [url, init] = fetch.mock.calls[0];
		expect(url).toBe('https://511.idaho.gov/robots.txt');
		expect((init!.headers as Record<string, string>)['User-Agent']).toBe(USER_AGENT);
		expect((await c.check('https://511.idaho.gov/list/x')).decision).toBe('disallowed');
		t += 23 * 3600 * 1000;
		await c.check(URL_);
		expect(fetch).toHaveBeenCalledTimes(1);
		t += 2 * 3600 * 1000;
		await c.check(URL_);
		expect(fetch).toHaveBeenCalledTimes(2);
	});
});

describe('identity', () => {
	it("uses the same User-Agent and agent token as the ingestors", () => {
		// ingest/__init__.py: USER_AGENT = ("…" "…") and AGENT_TOKEN = "…"
		const py = readFileSync(join(import.meta.dirname, '..', '..', '..', '..', 'ingest', '__init__.py'), 'utf8');
		const ua = /^USER_AGENT\s*=\s*\(\s*((?:"(?:[^"\\]|\\.)*"\s*)+)\)/m.exec(py);
		expect(ua, 'USER_AGENT in ingest/__init__.py').not.toBeNull();
		const joined = [...ua![1].matchAll(/"((?:[^"\\]|\\.)*)"/g)].map((m) => m[1]).join('');
		expect(joined).toBe(USER_AGENT);
		expect(/^AGENT_TOKEN\s*=\s*"([^"]*)"/m.exec(py)?.[1]).toBe(AGENT_TOKEN);
	});
});
