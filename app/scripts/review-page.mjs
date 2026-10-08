#!/usr/bin/env node
/**
 * The owner's review page (docs/14 §14.10 "WP15"): one HTML file beside the
 * screenshots, so the matrix, the checklist and the numbers can be read in a
 * browser without the app running.
 *
 *   node scripts/review-page.mjs [screens folder]   (default: $TVT_SCREENS)
 *
 * It reads, from that folder, whatever of these exists:
 *   wp15-matrix.json     the screenshot matrix (review spec, §14.11)
 *   wp15-checklist.json  the checklist's automatable lines (review spec)
 *   wp15-notes.json      the reviewer's verdicts on the rest of the checklist:
 *                        { "items": [{ "line", "verdict": "pass"|"fail"|"note", "note" }],
 *                          "numbers": [{ "label", "value" }] }
 * and writes review.html. Images are linked by file name, never embedded or
 * copied, and every camera picture in them is a seeded, map-rendered frame:
 * no real camera image is used anywhere in tests or screenshots (§14.11).
 * The page loads nothing from another origin.
 */
import { existsSync, readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

const dir = process.argv[2] || process.env.TVT_SCREENS;
if (!dir) {
	console.error('usage: node scripts/review-page.mjs <screens folder> (or set TVT_SCREENS)');
	process.exit(2);
}
const read = (f) => (existsSync(join(dir, f)) ? JSON.parse(readFileSync(join(dir, f), 'utf8')) : null);
const matrix = read('wp15-matrix.json');
const checklist = read('wp15-checklist.json');
const notes = read('wp15-notes.json');

const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
const MARK = { pass: '● pass', fail: '▲ fail', note: '◌ note' };

function matrixSection() {
	if (!matrix) return '<p>No screenshot matrix yet: run <code>npm run test:e2e -- --grep @wp15</code>.</p>';
	const byView = new Map();
	for (const e of matrix.entries) byView.set(e.view, [...(byView.get(e.view) ?? []), e]);
	return [...byView.entries()]
		.sort((a, b) => a[0] - b[0])
		.map(([view, shots]) => `
<section class="view card" id="view-${view}">
  <h3><span class="num">${view}</span> ${esc(shots[0].title)}</h3>
  <div class="shots">
    ${shots
			.map((s) => `<figure class="${s.size.startsWith('390') ? 'phone' : 'desk'}">
      <a href="${esc(s.file)}"><img src="${esc(s.file)}" alt="View ${view} at ${esc(s.size)}" loading="lazy"></a>
      <figcaption class="num">${esc(s.size)}${s.notes?.length ? ` · ${esc(s.notes.join(' · '))}` : ''}</figcaption>
    </figure>`)
			.join('\n    ')}
  </div>
</section>`)
		.join('\n');
}

function checklistSection() {
	if (!checklist) return '<p>No automated checklist results yet.</p>';
	const rows = [];
	const row = (line, ok, detail) => rows.push(`<tr><td>${esc(line)}</td><td class="${ok ? 'ok' : 'bad'}">${ok ? '● pass' : '▲ fail'}</td><td>${detail}</td></tr>`);
	const credits = checklist.credits ?? '';
	const want = ['OpenStreetMap', 'Protomaps', 'USGS', 'NAIP', 'Overture', 'Valley Regional Transit', 'ITD 511', 'ACHD|Ada County Highway District'];
	const missing = want.filter((w) => !new RegExp(w).test(credits));
	row('Credits in the attribution', missing.length === 0, missing.length ? `missing: ${esc(missing.join(', '))}` : esc(credits));
	const f = checklist.fonts ?? {};
	const fontsOk = ['Fredoka', 'Overpass', 'Overpass Mono'].every((x) => (f.loaded ?? []).includes(x));
	row('Fonts: Fredoka, Overpass, Overpass Mono', fontsOk, esc(`loaded ${(f.loaded ?? []).join(', ')}; nameplate ${f.nameplate}; body ${f.body}; clock ${f.clock}`));
	row('No emoji icons', (checklist.emoji ?? []).length === 0, esc((checklist.emoji ?? []).join('; ') || 'none found'));
	const c = checklist.contrast ?? { failing: [] };
	row(
		'Text contrast (4.5:1; 3:1 for large text and status shapes)',
		c.failing.length === 0,
		esc(`${c.checked} text elements checked; ${c.overMap} over the map (no solid background), ${c.halos} with a halo (badge rule) not measured`) +
			(c.failing.length ? `<br>${c.failing.map((x) => esc(`${x.where} "${x.text}": ${x.ratio} < ${x.need}`)).join('<br>')}` : '')
	);
	row('Nothing under the bars (desktop)', (checklist.desktopOverlaps ?? []).length === 0, esc((checklist.desktopOverlaps ?? []).join('; ') || 'no overlap'));
	const p = checklist.phone ?? {};
	const held = (c) => (c ? `card ${c.card} px high, text ${c.text} px` : 'not measured');
	row('The open credits card holds its text', Boolean(checklist.creditsDesktop?.held && p.credits?.held), esc(`desktop: ${held(checklist.creditsDesktop)}; phone: ${held(p.credits)}`));
	row('Phone: no horizontal scroll', p.scrollWidth <= 390, esc(`page width ${p.scrollWidth} px at 390`));
	row('Phone: nothing under the bars', (p.overlaps ?? []).length === 0, esc((p.overlaps ?? []).join('; ') || 'no overlap'));
	row('Phone: touch targets ≥ 44 px', (p.smallTargets ?? []).length === 0, esc((p.smallTargets ?? []).join('; ') || 'all at least 44 px'));
	return `<table><thead><tr><th>Line</th><th>Result</th><th>Detail</th></tr></thead><tbody>${rows.join('')}</tbody></table>`;
}

function notesSection() {
	if (!notes) return '<p>No reviewer notes yet.</p>';
	const items = (notes.items ?? [])
		.map((i) => `<tr><td>${esc(i.line)}</td><td class="${i.verdict === 'fail' ? 'bad' : i.verdict === 'pass' ? 'ok' : 'soft'}">${MARK[i.verdict] ?? esc(i.verdict)}</td><td>${esc(i.note)}</td></tr>`)
		.join('');
	const numbers = (notes.numbers ?? []).map((n) => `<tr><td>${esc(n.label)}</td><td class="num">${esc(n.value)}</td></tr>`).join('');
	return `<table><thead><tr><th>Checklist line</th><th>Verdict</th><th>Note</th></tr></thead><tbody>${items}</tbody></table>
${numbers ? `<h2>Numbers</h2><table><tbody>${numbers}</tbody></table>` : ''}`;
}

const html = `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>UI v2 review</title>
<style>
  :root { --ink: #2B2A33; --ink-soft: #5D5A66; --panel: #FFFBF4; --panel-edge: #E3D7C4; --ground: #EEE7DA; --accent: #F2A20C; --teal: #2C8C99; --alert: #D9467A; }
  * { box-sizing: border-box; }
  body { margin: 0; padding: 24px 16px 48px; background: var(--ground); color: var(--ink); font: 15px/1.5 Overpass, system-ui, sans-serif; }
  main { max-width: 1320px; margin: 0 auto; }
  h1, h2, h3 { font-family: Fredoka, Overpass, sans-serif; font-weight: 600; margin: 0 0 8px; }
  h1 { font-size: 28px; } h2 { font-size: 21px; margin-top: 28px; } h3 { font-size: 17px; }
  .num { font-family: "Overpass Mono", ui-monospace, monospace; }
  h3 .num { display: inline-block; min-width: 28px; padding: 0 6px; border-radius: 8px; background: var(--ink); color: var(--panel); text-align: center; }
  .card { background: var(--panel); border: 2px solid var(--panel-edge); border-radius: 16px; box-shadow: 0 3px 0 var(--panel-edge); padding: 16px; margin: 16px 0; }
  .shots { display: flex; flex-wrap: wrap; gap: 16px; align-items: flex-start; }
  figure { margin: 0; }
  figure.desk { flex: 1 1 640px; max-width: 900px; }
  figure.phone { flex: 0 1 260px; }
  figure img { display: block; width: 100%; height: auto; border-radius: 10px; border: 1px solid var(--panel-edge); }
  figcaption { font-size: 12px; color: var(--ink-soft); margin-top: 4px; }
  table { border-collapse: collapse; width: 100%; background: var(--panel); border-radius: 12px; overflow: hidden; }
  th, td { text-align: left; vertical-align: top; padding: 8px 10px; border-bottom: 1px solid var(--panel-edge); }
  th { font-family: Fredoka, Overpass, sans-serif; font-weight: 600; }
  td.ok, td.bad, td.soft { white-space: nowrap; font-weight: 700; }
  td.bad { color: var(--ink); background: #F9E0E8; }
  td.soft { color: var(--ink-soft); }
  p.lede { color: var(--ink-soft); max-width: 75ch; }
  code { font-family: "Overpass Mono", ui-monospace, monospace; font-size: 13px; }
  @media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { --ground: #24232B; --panel: #2F2E37; --panel-edge: #45434F; --ink: #F3EDE2; --ink-soft: #C9C3B8; } td.bad { background: #5A2B3B; } }
</style>
</head>
<body>
<main>
  <h1>UI v2: the owner's review</h1>
  <p class="lede">The screenshot matrix and visual review checklist from docs/14 §14.11, taken by WP15 on the merged tree (${esc(matrix?.at ?? 'not yet')}).
  Every camera picture here is a seeded frame rendered from our own map (or a test pattern): no real camera image is used.
  Shapes and words carry every result: ● pass, ▲ fail, ◌ note.</p>
  <h2>The checklist: what the browser measured</h2>
  ${checklistSection()}
  <h2>The checklist: judged from the screenshots</h2>
  ${notesSection()}
  <h2>The screenshot matrix</h2>
  ${matrixSection()}
</main>
</body>
</html>
`;
writeFileSync(join(dir, 'review.html'), html);
console.log(`wrote ${join(dir, 'review.html')}`);
