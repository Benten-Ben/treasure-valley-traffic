import type { Archive } from '#lib/server/archive.js';
import { hasCameraProvider } from '#lib/server/camera-provider.js';
import {
	feedOf,
	isHollow,
	PROVIDERS,
	ROADWEATHER_CONTRACT,
	viewLabel,
	type Provider,
	type RoadWeather,
	type RoadWeatherStation,
	type RoadWeatherView
} from './model.js';

/**
 * `GET /api/roadweather` (docs/14 §14.6 "Road weather", WP16): every active
 * road-weather station (provider `ITD RWIS` or `ODOT`) with its views and
 * each view's newest picture in the capture archive: when our capture first
 * saw it, its age, and whether the view shows 511's "no live feed" picture
 * (model.ts). Statewide: the layer draws only those inside the base map.
 *
 * The archive is read the way /api/cameras/live reads it (WP11's
 * archive.ts): an index is read only when it changed, so unchanged views
 * cost a stat each. With CAMERA_IMAGES_ENABLED off, nothing is read and no
 * ages are given.
 */

/** A postgres.js tagged template, or a test's stand-in. */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export type Sql = ((strings: TemplateStringsArray, ...values: any[]) => Promise<any[]>) & ((list: readonly unknown[]) => unknown);

interface Row {
	id: number | string;
	name: string;
	provider: Provider;
	lon: number;
	lat: number;
	view_id: number | string | null;
	image_id: number | null;
	status: string | null;
	direction: string | null;
	sort_order: number | null;
}

/** Active stations and their views (not those 511 no longer lists), in 511's order. */
export function readStations(sql: Sql): Promise<Row[]> {
	return sql`
		select c.id, c.name, c.provider, ST_X(c.pole_geom) as lon, ST_Y(c.pole_geom) as lat,
		       v.id as view_id, v.image_id, v.status, v.direction, v.sort_order
		from core.camera c
		left join core.camera_view v on v.camera_id = c.id and v.status is distinct from 'Removed'
		where c.active and c.pole_geom is not null and c.provider in ${sql(PROVIDERS)}
		order by c.id, v.sort_order, v.id`;
}

export const NO_MIGRATION = "Road-weather stations need the cameras plugin's migration 0001 (core.camera.provider)";

/** The answer, from the database and (when live images are on) the capture archive. */
export async function roadWeather(o: { sql: Sql; archive: Archive | null; nowMs: number }): Promise<RoadWeather> {
	const now = o.nowMs / 1000;
	const images = o.archive !== null;
	if (!(await hasCameraProvider(o.sql))) return { contract: ROADWEATHER_CONTRACT, now, images, note: NO_MIGRATION, stations: [] };
	const rows = await readStations(o.sql);

	// Images a running capture service records (heartbeat within 3 cadences, not paused for low disk).
	const capturing = new Set<number>();
	if (o.archive) for (const s of await o.archive.services(o.nowMs)) if (s.alive && !s.pausedLowDisk) for (const i of s.imageIds) capturing.add(i);

	const byId = new Map<number, { s: Omit<RoadWeatherStation, 'views' | 'hollow'>; rows: Row[] }>();
	for (const r of rows) {
		const id = Number(r.id);
		let e = byId.get(id);
		if (!e) byId.set(id, (e = { s: { id, name: r.name, provider: r.provider, lon: Number(r.lon), lat: Number(r.lat) }, rows: [] }));
		if (r.view_id !== null) e.rows.push(r);
	}
	const stations = await Promise.all(
		[...byId.values()].map(async ({ s, rows: vs }) => {
			const views = await Promise.all(
				vs.map(async (r, i): Promise<RoadWeatherView> => {
					const imageId = r.image_id === null ? null : Number(r.image_id);
					const frame = o.archive && imageId !== null ? (await o.archive.newest(imageId, o.nowMs)).frame : null;
					const seenAt = frame ? frame.firstSeenAt : null;
					const ageS = seenAt === null ? null : Math.max(0, Math.round(now - seenAt));
					const v = {
						id: Number(r.view_id),
						imageId,
						label: viewLabel(r.direction, i),
						sortOrder: r.sort_order ?? 0,
						disabled: imageId === null || (r.status !== null && r.status !== 'Enabled'),
						seenAt,
						ageS,
						capturing: imageId !== null && capturing.has(imageId)
					};
					return { ...v, feed: feedOf(v, images) };
				})
			);
			return { ...s, views, hollow: isHollow(views) };
		})
	);
	return { contract: ROADWEATHER_CONTRACT, now, images, stations };
}
