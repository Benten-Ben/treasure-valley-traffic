import type { Component } from 'svelte';
import type { ModeId } from '#lib/state/modes.svelte.js';

/**
 * Chrome slots (docs/14 §14.10, WP2 "registration APIs"): later packages put
 * their pieces into the chrome by registering them here, never by editing
 * Chrome.svelte or the layout.
 *
 * - `add(slot, item)`: a component in a slot (top-bar right, legend stack,
 *   inspect card, floating windows, camera widget, toasts, view-history chip,
 *   and on phones the tab bar and sheet). Returns its removal.
 * - `setBanner(mode, component)`: the banner shown in place of the toolbar
 *   while that mode is active (look-through's strip, calibrate's banner).
 *
 * Stub components (TimePill, Window, WindowLayer, Sheet, TabBar,
 * CameraWidget, Toasts, ViewHistoryChip) are replaced by the package that
 * owns their file.
 */
export type SlotName = 'topbar-right' | 'legend' | 'inspect' | 'windows' | 'camera-widget' | 'toasts' | 'history' | 'tabbar' | 'sheet';

export interface SlotItem {
	id: string;
	// eslint-disable-next-line @typescript-eslint/no-explicit-any
	component: Component<any>;
	props?: Record<string, unknown>;
	/** Lower first. */
	order?: number;
}

class ChromeSlots {
	#items = $state.raw<Partial<Record<SlotName, SlotItem[]>>>({});
	// eslint-disable-next-line @typescript-eslint/no-explicit-any
	#banners = $state.raw<Partial<Record<ModeId, Component<any>>>>({});

	add(slot: SlotName, item: SlotItem): () => void {
		const list = [...(this.#items[slot] ?? []).filter((x) => x.id !== item.id), item].sort((a, b) => (a.order ?? 0) - (b.order ?? 0));
		this.#items = { ...this.#items, [slot]: list };
		return () => {
			this.#items = { ...this.#items, [slot]: (this.#items[slot] ?? []).filter((x) => x !== item) };
		};
	}

	items(slot: SlotName): SlotItem[] {
		return this.#items[slot] ?? [];
	}

	// eslint-disable-next-line @typescript-eslint/no-explicit-any
	setBanner(mode: ModeId, component: Component<any>): () => void {
		this.#banners = { ...this.#banners, [mode]: component };
		return () => {
			if (this.#banners[mode] === component) {
				const { [mode]: _gone, ...rest } = this.#banners;
				void _gone;
				this.#banners = rest;
			}
		};
	}

	// eslint-disable-next-line @typescript-eslint/no-explicit-any
	banner(mode: ModeId): Component<any> | null {
		return this.#banners[mode] ?? null;
	}
}

export const slots = new ChromeSlots();
