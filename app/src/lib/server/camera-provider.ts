/**
 * Who runs each camera (WP16; docs/14 §14.6 "Road weather"). ITD's
 * road-weather stations and Oregon DOT's cameras share core.camera with
 * ACHD's traffic cameras, told apart by `core.camera.provider` (the cameras
 * plugin's migration 0001). The Cameras layer's routes keep to ACHD's; the
 * Road weather layer shows the rest.
 *
 * Until that migration is applied (an older database, or the seconds at a
 * deploy before the ingest service applies it), the column doesn't exist and
 * every camera is ACHD's, so these routes keep working without it:
 *
 *     const achd = await hasCameraProvider(sql);
 *     sql`… where c.active ${achd ? sql`and c.provider = 'ACHD'` : sql``}`
 *
 * (The fragment is built inline: returned from an async function, postgres.js
 * would run it on its own, since a query is a thenable.)
 */

// A postgres.js tagged template, or a test's stand-in.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Sql = (strings: TemplateStringsArray, ...values: any[]) => any;

let present = false;

/** core.camera.provider exists. Once seen, it's not asked again. */
export async function hasCameraProvider(sql: Sql): Promise<boolean> {
	if (present) return true;
	const [r] = (await sql`
		select exists(select 1 from information_schema.columns
		              where table_schema = 'core' and table_name = 'camera' and column_name = 'provider') as ok`) as { ok?: boolean }[];
	present = Boolean(r?.ok);
	return present;
}

/** Tests: forget what was seen. */
export function resetCameraProvider(): void {
	present = false;
}
