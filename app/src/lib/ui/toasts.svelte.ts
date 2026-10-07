/**
 * Toasts (docs/14 §14.3; band 70): short messages at the bottom centre, above
 * the toolbar ("All 4 windows are pinned…", "New version: reload when
 * convenient"). Anything can show one; `Toasts.svelte` draws them.
 *
 * - `show(text, o)` returns the toast's dismissal. A toast goes by itself
 *   after `timeout` ms (6 s by default; null keeps it until dismissed).
 * - A `key` replaces an earlier toast with the same key instead of stacking.
 * - At most `MAX_TOASTS` show; the oldest goes first.
 * - `problem` toasts are announced assertively (role=alert) and carry the ▲
 *   shape; others politely, with ●. Never color alone (§14.3).
 */
export interface ToastAction {
	label: string;
	run: () => void;
}

export interface Toast {
	id: number;
	text: string;
	kind: 'info' | 'problem';
	action?: ToastAction;
	key?: string;
	/** ms until it goes by itself, or null (stays until dismissed). */
	timeout: number | null;
}

export interface ToastOptions {
	kind?: Toast['kind'];
	action?: ToastAction;
	key?: string;
	timeout?: number | null;
}

export const DEFAULT_TIMEOUT = 6000;
export const MAX_TOASTS = 3;

export class ToastStore {
	list = $state.raw<Toast[]>([]);
	#seq = 0;
	#timers = new Map<number, ReturnType<typeof setTimeout>>();

	show(text: string, o: ToastOptions = {}): () => void {
		const id = ++this.#seq;
		const toast: Toast = { id, text, kind: o.kind ?? 'info', action: o.action, key: o.key, timeout: o.timeout === undefined ? DEFAULT_TIMEOUT : o.timeout };
		const kept = this.list.filter((t) => !(o.key && t.key === o.key));
		for (const t of this.list) if (!kept.includes(t)) this.#clear(t.id);
		const next = [...kept, toast];
		while (next.length > MAX_TOASTS) this.#clear(next.shift()!.id);
		this.list = next;
		if (toast.timeout !== null) this.#timers.set(id, setTimeout(() => this.dismiss(id), toast.timeout));
		return () => this.dismiss(id);
	}

	dismiss(id: number): void {
		this.#clear(id);
		if (this.list.some((t) => t.id === id)) this.list = this.list.filter((t) => t.id !== id);
	}

	/** Dismiss every toast (tests, leaving the map). */
	clear(): void {
		for (const t of this.list) this.#clear(t.id);
		this.list = [];
	}

	#clear(id: number) {
		clearTimeout(this.#timers.get(id));
		this.#timers.delete(id);
	}
}

export const toasts = new ToastStore();
