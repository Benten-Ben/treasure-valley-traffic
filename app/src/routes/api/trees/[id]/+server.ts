import { error } from '@sveltejs/kit';
import { treeDetail, type Sql } from '#lib/layers/trees/trees.server.js';
import { db } from '#lib/server/db.js';
import { jsonWithEtag } from '#lib/server/json-etag.js';

/**
 * One tree (docs/19 §19.6, the tree panel): `GET /api/trees/<id>` → its
 * kind, type, sizes, how it was found (`fit`), the build, its catalogue
 * entry (the private City of Boise inventory, on the owner's site only;
 * null elsewhere) and its log, newest first. `no-cache` with an ETag.
 */
export async function GET({ params, request }) {
	const id = params.id;
	if (!id || id.length > 200) error(400, 'Bad tree id');
	const tree = await treeDetail(db() as unknown as Sql, id);
	if (!tree) error(404, 'No such tree');
	return jsonWithEtag(tree, request.headers.get('if-none-match'));
}
