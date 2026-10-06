/**
 * Network accounting for perf.mjs and the e2e specs (docs/14 §14.9, "How we
 * measure"). Records every request the page makes through the Chrome
 * DevTools protocol: URL, byte range, status, bytes on the wire, cache hits
 * and timings.
 *
 * Byte counts follow §14.9: tiles count as transferred; JavaScript, CSS,
 * HTML, SVG and JSON count as their gzip size (computed here), because
 * `vite preview` doesn't compress the way Caddy does.
 *
 * MapLibre fetches tiles, glyphs and sprites on the main thread (custom
 * protocols run there), so the page's own session sees them all. Playwright's
 * request events are counted too, as a cross-check.
 */
import { gzipSync } from 'node:zlib';

// What Caddy's `encode` compresses in front of the app. Glyphs and road tiles
// (protobuf) are sent as they are, so they count as transferred.
const COMPRESSIBLE = /javascript|json|css|html|svg|text\/plain/;

/** What a URL is, for the per-kind totals. */
export function kindOf(url) {
	const u = url.replace(/[?#].*$/, '');
	if (/\/tiles\/terrain[^/]*\.pmtiles$/.test(u)) return 'terrain';
	if (/\/tiles\/imagery[^/]*\.pmtiles$/.test(u)) return 'imagery';
	if (/\/tiles\/buildings[^/]*\.pmtiles$/.test(u)) return 'buildings';
	if (/\/tiles\/[^/]+\.pmtiles$/.test(u)) return 'basemap';
	if (/\/tiles\/fonts\//.test(u)) return 'glyphs';
	if (/\/tiles\/sprites\//.test(u)) return 'sprites';
	if (/\/tiles\/manifest\.json$/.test(u)) return 'manifest';
	if (/\/api\/tiles\/roads\//.test(u)) return 'roads';
	if (/\/api\//.test(u)) return 'api';
	if (/\.m?js$/.test(u)) return 'js';
	if (/\.css$/.test(u)) return 'css';
	if (/\.(woff2?|ttf|otf)$/.test(u)) return 'fonts';
	return 'other';
}

/**
 * Start recording. `throttle` (optional): { latencyMs, mbps } for
 * Network.emulateNetworkConditions. Returns the recorder.
 */
export async function recordNetwork(page, { throttle, bodies = true } = {}) {
	const cdp = await page.context().newCDPSession(page);
	await cdp.send('Network.enable', { maxTotalBufferSize: 200e6, maxResourceBufferSize: 50e6 });
	if (throttle) {
		const bps = (throttle.mbps * 1e6) / 8;
		await cdp.send('Network.emulateNetworkConditions', {
			offline: false,
			latency: throttle.latencyMs,
			downloadThroughput: bps,
			uploadThroughput: bps
		});
	}
	const byId = new Map();
	const entries = [];
	const pending = [];
	let playwrightRequests = 0;
	const onRequest = () => playwrightRequests++;
	page.on('request', onRequest);

	cdp.on('Network.requestWillBeSent', (e) => {
		if (e.request.url.startsWith('data:') || e.request.url.startsWith('blob:')) return;
		const prev = byId.get(e.requestId);
		if (prev && e.redirectResponse) prev.redirected = true;
		const h = e.request.headers;
		const entry = {
			id: e.requestId,
			url: e.request.url,
			method: e.request.method,
			range: h.Range ?? h.range ?? null,
			type: e.type ?? null,
			kind: kindOf(e.request.url),
			start: e.timestamp,
			wallStart: e.wallTime,
			status: null,
			fromCache: false,
			bytes: 0,
			bodyBytes: null,
			gzipBytes: null,
			contentEncoding: null,
			responseAt: null,
			end: null,
			failed: null
		};
		byId.set(e.requestId, entry);
		entries.push(entry);
	});
	cdp.on('Network.requestServedFromCache', (e) => {
		const x = byId.get(e.requestId);
		if (x) x.fromCache = true;
	});
	cdp.on('Network.responseReceived', (e) => {
		const x = byId.get(e.requestId);
		if (!x) return;
		x.status = e.response.status;
		x.mimeType = e.response.mimeType;
		x.fromCache ||= Boolean(e.response.fromDiskCache || e.response.fromPrefetchCache || e.response.fromServiceWorker);
		const hdr = e.response.headers ?? {};
		x.contentEncoding = hdr['content-encoding'] ?? hdr['Content-Encoding'] ?? null;
		x.cacheControl = hdr['cache-control'] ?? hdr['Cache-Control'] ?? null;
		x.responseAt = e.timestamp;
	});
	cdp.on('Network.loadingFinished', (e) => {
		const x = byId.get(e.requestId);
		if (!x) return;
		x.bytes = x.fromCache ? 0 : e.encodedDataLength;
		x.end = e.timestamp;
		if (bodies && !x.fromCache && COMPRESSIBLE.test(x.mimeType ?? '') && !x.contentEncoding) {
			pending.push(
				cdp
					.send('Network.getResponseBody', { requestId: e.requestId })
					.then((b) => {
						const buf = Buffer.from(b.body, b.base64Encoded ? 'base64' : 'utf8');
						x.bodyBytes = buf.length;
						x.gzipBytes = gzipSync(buf).length;
					})
					.catch(() => {})
			);
		}
	});
	cdp.on('Network.loadingFailed', (e) => {
		const x = byId.get(e.requestId);
		if (x) x.failed = e.errorText;
	});

	return {
		entries,
		/** Entries since a mark (an index into entries). */
		since: (mark) => entries.slice(mark),
		mark: () => entries.length,
		playwrightRequests: () => playwrightRequests,
		async settle() {
			await Promise.all(pending.splice(0));
		},
		async detach() {
			page.off('request', onRequest);
			await Promise.all(pending.splice(0));
			await cdp.detach().catch(() => {});
		}
	};
}

/** Bytes as §14.9 counts them: gzip size for compressible text sent uncompressed, else on the wire. */
export const budgetBytes = (x) => (x.fromCache ? 0 : x.gzipBytes ?? x.bytes);

/** Totals for a list of entries. */
export function summarize(list, origin) {
	const net = list.filter((x) => !x.fromCache && !x.failed);
	const byKind = {};
	for (const x of net) {
		const k = (byKind[x.kind] ??= { requests: 0, bytes: 0 });
		k.requests++;
		k.bytes += budgetBytes(x);
	}
	const seen = new Map();
	let duplicates = 0;
	for (const x of net) {
		const key = `${x.url} ${x.range ?? ''}`;
		if (seen.has(key)) duplicates++;
		seen.set(key, true);
	}
	const foreign = origin ? list.filter((x) => !x.url.startsWith(origin)).map((x) => x.url) : [];
	return {
		requests: net.length,
		cached: list.filter((x) => x.fromCache).length,
		failed: list.filter((x) => x.failed).length,
		bytes: net.reduce((s, x) => s + budgetBytes(x), 0),
		wireBytes: net.reduce((s, x) => s + x.bytes, 0),
		duplicates,
		byKind,
		foreign
	};
}

/** Seconds from `t0` (a CDP timestamp) to the first entry matching `pred`, by start or response. */
export function firstAt(list, pred, t0, field = 'start') {
	const xs = list.filter(pred).map((x) => x[field]).filter((v) => v != null);
	return xs.length ? Math.min(...xs) - t0 : null;
}

export const MB = (b) => +(b / 1e6).toFixed(2);
