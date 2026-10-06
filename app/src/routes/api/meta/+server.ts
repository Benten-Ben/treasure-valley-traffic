import { json } from '@sveltejs/kit';
import { dataMeta } from '#lib/server/versions.js';

/**
 * Data versions (docs/14 §14.8; contract in #lib/contracts/meta). Tiny,
 * memoized 15 s, preloaded by the page so layer fetches can start the moment
 * it resolves. Always revalidated: the versions are what make everything else
 * cacheable.
 */
export async function GET({ setHeaders }) {
	setHeaders({ 'cache-control': 'no-cache' });
	return json(await dataMeta());
}
