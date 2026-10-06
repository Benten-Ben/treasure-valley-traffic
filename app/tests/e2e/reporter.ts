import { mkdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import type { FullResult, Reporter, TestCase, TestResult } from '@playwright/test/reporter';

/**
 * Counts for the hand-back (docs/14 §14.10, "Specs must actually run"): how
 * many specs ran, passed, failed and were skipped, overall and per @tag.
 * "Expected to fail" are specs marked test.fail() that did fail (for example
 * `persistent` until WP1); they ran and count as passing the run.
 * Also written to data/dev/<wp>/e2e-summary.json.
 */
interface Counts {
	total: number;
	ran: number;
	passed: number;
	failed: number;
	skipped: number;
	expectedToFail: number;
	flaky: number;
}

const zero = (): Counts => ({ total: 0, ran: 0, passed: 0, failed: 0, skipped: 0, expectedToFail: 0, flaky: 0 });

export default class CountsReporter implements Reporter {
	private finals = new Map<string, { test: TestCase; result: TestResult }>();

	onTestEnd(test: TestCase, result: TestResult) {
		this.finals.set(test.id, { test, result });
	}

	onEnd(result: FullResult) {
		const all = zero();
		const byTag = new Map<string, Counts>();
		const skippedTitles: string[] = [];
		for (const { test } of this.finals.values()) {
			const outcome = test.outcome(); // 'expected' | 'unexpected' | 'flaky' | 'skipped'
			const status = test.results.at(-1)?.status;
			const tags = test.tags.length ? test.tags : ['(untagged)'];
			for (const c of [all, ...tags.map((t) => byTag.get(t) ?? byTag.set(t, zero()).get(t)!)]) {
				c.total++;
				if (outcome === 'skipped') {
					c.skipped++;
					continue;
				}
				c.ran++;
				if (outcome === 'flaky') c.flaky++;
				if (outcome === 'unexpected') c.failed++;
				else if (test.expectedStatus === 'failed' && status === 'failed') c.expectedToFail++;
				else c.passed++;
			}
			if (outcome === 'skipped') skippedTitles.push(`${test.titlePath().slice(1).join(' › ')}`);
		}
		const line = (c: Counts) =>
			`ran ${c.ran}, passed ${c.passed}, expected-to-fail ${c.expectedToFail}, failed ${c.failed}, ` +
			`skipped ${c.skipped}${c.flaky ? `, flaky ${c.flaky}` : ''} (of ${c.total})`;
		const out = [`\ne2e counts: ${line(all)} → ${result.status}`];
		for (const [tag, c] of [...byTag].sort()) out.push(`  ${tag.padEnd(12)} ${line(c)}`);
		if (skippedTitles.length) out.push(`  skipped: ${skippedTitles.join('; ')}`);
		console.log(out.join('\n'));
		try {
			const dir = join(process.env.TVT_MAIN ?? '.', 'data', 'dev', process.env.TVT_WP || 'local');
			mkdirSync(dir, { recursive: true });
			writeFileSync(join(dir, 'e2e-summary.json'), JSON.stringify({
				at: new Date().toISOString(), status: result.status, all, byTag: Object.fromEntries(byTag), skipped: skippedTitles
			}, null, 2));
		} catch {
			/* the console line is what matters */
		}
	}

	printsToStdio() {
		return false;
	}
}
