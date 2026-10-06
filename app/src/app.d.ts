// See https://svelte.dev/docs/kit/types#app.d.ts
// for information about these interfaces
import type { Map } from 'maplibre-gl';
import type { CameraView } from '#lib/state/view.svelte.js';

declare global {
	namespace App {
		// interface Error {}
		// interface Locals {}
		// interface PageData {}
		// interface PageState {}
		// interface Platform {}
	}

	/**
	 * The read-only debug handle (docs/14 §14.8), for tests and the console.
	 * Set by the map layout; absent on other pages.
	 */
	var __tvt:
		| {
				readonly map: Map | null;
				readonly mapsCreated: number;
				/** Resolves (true) once navigation, mode changes and the map have settled. */
				readonly ready: Promise<boolean>;
				/** The layers' state (WP1: the lens; WP2: the layer manager). */
				readonly layers: unknown;
				readonly mode: 'explore' | 'look' | 'calibrate';
				readonly status: 'loading' | 'ready' | 'unavailable' | 'error';
				readonly view: CameraView | null;
		  }
		| undefined;
}

export {};
