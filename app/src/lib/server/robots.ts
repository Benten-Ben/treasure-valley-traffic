/**
 * robots.txt for the app's own requests (docs/14 §14.6, "Live images"): a
 * port of ingest/http.py's lenient RFC 9309 parser, with the same test cases
 * (robots.test.ts), and the same User-Agent as the ingestors.
 *
 * - Groups, `*` and `$` wildcards, the longest match wins, Allow wins a tie.
 * - Lenient: a byte-order mark, blank lines inside a group, and rules with no
 *   User-agent line (they apply to everyone).
 * - Paths match case-insensitively, deliberately stricter than the RFC.
 * - A 4xx means no rules; a 5xx or a network error means "blocked" for now.
 *   That isn't cached, so the next check tries again.
 * - Files are cached for 24 hours (RFC 9309 allows up to 24).
 */

/** Our client, named honestly. Must equal ingest/__init__.py's USER_AGENT (a test compares them). */
export const USER_AGENT =
	'treasure-valley-traffic/0.2 (public-interest research; +https://github.com/Benten-Ben/treasure-valley-traffic)';
/** The product token robots.txt groups are matched against (ingest's AGENT_TOKEN). */
export const AGENT_TOKEN = 'treasure-valley-traffic';

export const ROBOTS_TTL_MS = 24 * 3600 * 1000;

/** Python's str.splitlines() line breaks. */
const LINE_BREAKS = /\r\n|[\n\r\v\f\x1c\x1d\x1e\x85\u2028\u2029]/;

/**
 * Normalize robots.txt quirks so the intended rules apply: strip a UTF-8
 * byte-order mark (511 Idaho's file starts with one); drop blank and comment
 * lines (ACHD's file has a blank line between User-agent and Disallow); rules
 * with no User-agent line apply to everyone (IEM's file).
 */
export function lenientLines(text: string): string[] {
	const lines = text
		.split(LINE_BREAKS)
		.map((ln) => ln.split('#', 1)[0].trim().replace(/^\uFEFF+/, ''))
		.filter(Boolean);
	if (lines.length && !lines[0].toLowerCase().startsWith('user-agent')) lines.unshift('User-agent: *');
	return lines;
}

interface Rule {
	allow: boolean;
	rx: RegExp;
	length: number;
}
interface Group {
	agents: string[];
	rules: Rule[];
	delay: number | null;
}

const FLOAT = /^[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?$/;

/** robots.txt rules. Matching is case-insensitive (stricter than the RFC): 511 Idaho lists one casing of paths its pages use in another. */
export class Robots {
	readonly groups: Group[] = [];

	constructor(text: string) {
		let agents: string[] = [];
		let rules: Rule[] = [];
		let delay: number | null = null;
		let inRules = false;
		for (const line of lenientLines(text)) {
			const colon = line.indexOf(':');
			const key = (colon === -1 ? line : line.slice(0, colon)).trim().toLowerCase();
			const val = colon === -1 ? '' : line.slice(colon + 1).trim();
			if (key === 'user-agent') {
				if (inRules) {
					this.groups.push({ agents, rules, delay });
					agents = [];
					rules = [];
					delay = null;
					inRules = false;
				}
				agents.push(val.toLowerCase());
			} else if (key === 'allow' || key === 'disallow') {
				inRules = true;
				if (val) rules.push({ allow: key === 'allow', rx: Robots.regex(val), length: val.length });
			} else if (key === 'crawl-delay') {
				inRules = true;
				if (FLOAT.test(val)) delay = Number.parseFloat(val);
			}
		}
		if (agents.length) this.groups.push({ agents, rules, delay });
	}

	private static regex(pattern: string): RegExp {
		const anchored = pattern.endsWith('$');
		const body = pattern
			.replace(/\$+$/, '')
			.replace(/[.*+?^${}()|[\]\\/]/g, '\\$&')
			.replaceAll('\\*', '.*');
		return new RegExp(`^${body}${anchored ? '$' : ''}`, 'i');
	}

	private group(): Group | null {
		const specific = this.groups.find((g) => g.agents.some((a) => a !== '*' && AGENT_TOKEN.includes(a)));
		if (specific) return specific;
		return this.groups.find((g) => g.agents.includes('*')) ?? null;
	}

	allowed(url: string): boolean {
		const u = new URL(url);
		const path = (u.pathname || '/') + (u.search.length > 1 ? u.search : '');
		const group = this.group();
		if (!group) return true;
		let best: { length: number; allow: boolean } | null = null;
		for (const { allow, rx, length } of group.rules) {
			if (rx.test(path) && (best === null || length > best.length || (length === best.length && allow))) best = { length, allow };
		}
		return best === null ? true : best.allow;
	}

	crawlDelay(): number | null {
		return this.group()?.delay ?? null;
	}
}

export const DISALLOW_ALL = new Robots('User-agent: *\nDisallow: /');

/**
 * - allowed: rules exist and allow the URL;
 * - no_rules: robots.txt is missing (4xx) or an HTML page, so everything is allowed;
 * - disallowed: the rules disallow the URL;
 * - unavailable: robots.txt couldn't be read (5xx, network error), so "blocked" for now.
 */
export type RobotsDecision = 'allowed' | 'no_rules' | 'disallowed' | 'unavailable';

export interface RobotsVerdict {
	allowed: boolean;
	decision: RobotsDecision;
	/** Seconds between requests to this host, from Crawl-delay. */
	crawlDelayS: number | null;
	/** Why a URL is blocked, for the UI ("robots.txt doesn't allow it right now"). */
	reason?: string;
}

type FetchLike = (url: string, init?: RequestInit) => Promise<Response>;

/** robots.txt per host: fetched with our User-Agent, cached 24 h, single-flight. */
export class RobotsCache {
	private cache = new Map<string, { rules: Robots | null; at: number }>();
	private inflight = new Map<string, Promise<Robots | null | 'unavailable'>>();
	private readonly fetch: FetchLike;
	private readonly now: () => number;
	private readonly ttlMs: number;

	constructor(opts: { fetch?: FetchLike; now?: () => number; ttlMs?: number } = {}) {
		this.fetch = opts.fetch ?? ((url, init) => globalThis.fetch(url, init));
		this.now = opts.now ?? Date.now;
		this.ttlMs = opts.ttlMs ?? ROBOTS_TTL_MS;
	}

	/** Drop every cached file, so the next check reads robots.txt again. */
	forget() {
		this.cache.clear();
	}

	private async load(host: string): Promise<Robots | null | 'unavailable'> {
		try {
			const res = await this.fetch(`${host}/robots.txt`, {
				headers: { 'User-Agent': USER_AGENT },
				redirect: 'follow',
				signal: AbortSignal.timeout(30_000)
			});
			if (res.ok) {
				const text = await res.text();
				// Some servers answer a missing robots.txt with an HTML page and status 200.
				return text.toLowerCase().includes('<html') ? null : new Robots(text);
			}
			if (res.status >= 400 && res.status < 500) return null;
			return 'unavailable';
		} catch {
			return 'unavailable';
		}
	}

	async check(url: string): Promise<RobotsVerdict> {
		const host = new URL(url).origin;
		let entry = this.cache.get(host);
		if (!entry || this.now() - entry.at >= this.ttlMs) {
			let p = this.inflight.get(host);
			if (!p) {
				p = this.load(host).finally(() => this.inflight.delete(host));
				this.inflight.set(host, p);
			}
			const got = await p;
			if (got === 'unavailable') {
				// Not cached: retried at the next check.
				return {
					allowed: false,
					decision: 'unavailable',
					crawlDelayS: null,
					reason: `robots.txt at ${host} couldn't be read, so it counts as disallowed for now`
				};
			}
			entry = { rules: got, at: this.now() };
			this.cache.set(host, entry);
		}
		const { rules } = entry;
		if (rules === null) return { allowed: true, decision: 'no_rules', crawlDelayS: null };
		const allowed = rules.allowed(url);
		return allowed
			? { allowed, decision: 'allowed', crawlDelayS: rules.crawlDelay() }
			: { allowed, decision: 'disallowed', crawlDelayS: rules.crawlDelay(), reason: `robots.txt at ${host} disallows ${url}` };
	}
}
