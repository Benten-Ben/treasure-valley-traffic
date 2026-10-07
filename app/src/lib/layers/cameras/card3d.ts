import { photoCrop, photoPlane } from '#lib/calibration/frustum.js';
import type { LiveView } from '#lib/contracts/live.js';
import type { Scene, ScenePhoto } from '#lib/scene/index.js';
import type { Calibration } from './cameras.js';

/**
 * The photo in the cone (docs/14 §14.6; WP13): for each open window of a
 * calibrated camera, from z15, its live picture hangs as a framed quad inside
 * the view cone.
 *
 * - **Placement:** perpendicular to the view axis, about 140 px wide on
 *   screen (the scene sizes it each frame), its corners on the frustum's
 *   edges. It reads correctly from any angle as a picture in the right place
 *   and direction, and flying the map camera to the apex makes it fill the
 *   view exactly: look-through is a continuous zoom into the window.
 * - **Faces:** the front shows the picture with the burned-in 511 bar cropped
 *   (and as much from the top, so the crop stays centred on the axis, which
 *   is how the scene sizes planes); the back is a cream panel with the
 *   camera's name.
 * - **Pictures:** the window's live frame, decoded off the main thread and
 *   swapped in once it's ready (the old picture stays until then); the
 *   scene's texture LRU holds at most 16. A frame whose size isn't the
 *   calibration's would misplace the picture, so it gets no plane.
 * - "3D photo" in the window turns a camera's photo off and on.
 */
export const PHOTOS = 'cameras-photos';
/** About this wide on screen. */
export const PHOTO_PX = 140;

/** An open camera window and the view it shows. */
export interface PhotoWant {
	cameraId: number;
	viewId: number;
	name: string;
}

/** A calibration's floating photo plane (pure). `texture` is a PhotoTextures key, or unset for the cream panel. */
export function cardPhoto(cal: Calibration, name: string, texture?: string, opacity = 1): ScenePhoto {
	const plane = photoPlane(cal.pose, cal.size, photoCrop(cal.size, true));
	return {
		id: `photo-${cal.viewId}`,
		apex: [cal.pose.lon, cal.pose.lat, cal.pose.alt],
		groundAlt: cal.groundZ,
		right: plane.right,
		down: plane.down,
		forward: plane.forward,
		tx: plane.tx,
		ty: plane.ty,
		widthPx: PHOTO_PX,
		texture,
		label: name,
		opacity
	};
}

interface Card {
	photo: ScenePhoto;
	cal: Calibration;
	/** The frame shown (sha), and the one being decoded. */
	sha: string | null;
	loading: string | null;
}

export class PhotoCards {
	#scene: Scene;
	#cals = new Map<number, Calibration>();
	#wants: PhotoWant[] = [];
	#frames: Record<number, LiveView> = {};
	#off = new Set<number>();
	#cards = new Map<number, Card>();
	#visible = false;
	#opacity = 1;
	#destroyed = false;
	/** Called when a camera's toggle changes (the window's button). */
	onToggle: (() => void) | null = null;

	constructor(scene: Scene) {
		this.#scene = scene;
		scene.setPhotos(PHOTOS, []);
		scene.show(PHOTOS, false);
	}

	setCalibrations(cals: readonly Calibration[]): void {
		this.#cals = new Map(cals.map((c) => [c.viewId, c]));
		this.#sync();
	}

	/** The open camera windows and the view each shows. */
	setWanted(wants: readonly PhotoWant[]): void {
		this.#wants = [...wants];
		this.#sync();
	}

	/** The live feed's newest answers (by view id). */
	setFrames(views: Record<number, LiveView>): void {
		this.#frames = views;
		this.#sync();
	}

	/** Shown (from z15, with the Cameras layer on, in Explore), at an opacity (the models' dither). */
	setVisible(on: boolean, opacity = 1): void {
		this.#opacity = opacity;
		for (const c of this.#cards.values()) c.photo.opacity = opacity;
		if (on !== this.#visible) {
			this.#visible = on;
			this.#scene.show(PHOTOS, on);
		}
	}

	isOn(cameraId: number): boolean {
		return !this.#off.has(cameraId);
	}

	set(cameraId: number, on: boolean): void {
		if (on) this.#off.delete(cameraId);
		else this.#off.add(cameraId);
		this.#sync();
		this.onToggle?.();
	}

	/** Which planes exist, and their pictures. */
	#sync() {
		if (this.#destroyed) return;
		const keep = new Set<number>();
		for (const w of this.#wants) {
			const cal = this.#cals.get(w.viewId);
			if (!cal || this.#off.has(w.cameraId)) continue;
			const live = this.#frames[w.viewId];
			const frame = live?.frame ?? null;
			// A picture of another size would land in the wrong place.
			if (frame && (frame.width !== cal.size.width || frame.height !== cal.size.height)) continue;
			keep.add(w.viewId);
			let card = this.#cards.get(w.viewId);
			if (!card || card.cal !== cal) {
				if (card?.photo.texture) this.#scene.textures.release(card.photo.texture);
				card = { photo: cardPhoto(cal, w.name, undefined, this.#opacity), cal, sha: null, loading: null };
				this.#cards.set(w.viewId, card);
			}
			if (frame && frame.sha !== card.sha && frame.sha !== card.loading) void this.#load(w.viewId, card, frame.url, frame.sha);
		}
		for (const [viewId, card] of this.#cards) {
			if (keep.has(viewId)) continue;
			if (card.photo.texture) this.#scene.textures.release(card.photo.texture);
			this.#cards.delete(viewId);
		}
		this.#push();
	}

	/** Decode a frame, then swap it in (the old picture stays until it's ready). */
	async #load(viewId: number, card: Card, url: string, sha: string) {
		card.loading = sha;
		const key = `card:${viewId}:${sha}`;
		try {
			await this.#scene.textures.load(key, url, photoCrop(card.cal.size, true));
		} catch (e) {
			if (card.loading === sha) card.loading = null;
			console.warn(`Camera photo for view ${viewId}: ${e instanceof Error ? e.message : e}`);
			return;
		}
		if (this.#destroyed || this.#cards.get(viewId) !== card || card.loading !== sha) {
			if (this.#cards.get(viewId)?.photo.texture !== key) this.#scene.textures.release(key);
			return;
		}
		const old = card.photo.texture;
		card.photo.texture = key;
		card.sha = sha;
		card.loading = null;
		if (old && old !== key) this.#scene.textures.release(old);
		this.#push();
	}

	#push() {
		this.#scene.setPhotos(
			PHOTOS,
			[...this.#cards.values()].map((c) => c.photo)
		);
	}

	/** For tests and the console. */
	info(): { visible: boolean; photos: { viewId: number; texture: string | null; sha: string | null }[] } {
		return {
			visible: this.#visible,
			photos: [...this.#cards].map(([viewId, c]) => ({ viewId, texture: c.photo.texture ?? null, sha: c.sha }))
		};
	}

	destroy(): void {
		this.#destroyed = true;
		for (const c of this.#cards.values()) if (c.photo.texture) this.#scene.textures.release(c.photo.texture);
		this.#cards.clear();
		this.#scene.remove(PHOTOS);
	}
}
