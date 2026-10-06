/**
 * Per-viewer memory in localStorage (docs/14 §14.3, "Defaults and memory").
 *
 * - Keys live under `tvt:v2:`.
 * - Every access is wrapped in try/catch: storage can be missing, full,
 *   blocked or throwing (private windows, previews, cleared site data), and
 *   the app must work the same without it. Nothing here is the only copy of
 *   anything that matters.
 * - Values are JSON. A value that doesn't parse, or fails its check, reads
 *   as missing.
 */
export const PREFIX = 'tvt:v2:';

/** The storage object, or null when there is none or touching it throws. */
export function storage(): Storage | null {
	try {
		return globalThis.localStorage ?? null;
	} catch {
		return null;
	}
}

export type Check<T> = (value: unknown) => value is T;

/** Read `tvt:v2:<key>`; undefined when missing, unreadable or failing `check`. */
export function readStored<T>(key: string, check?: Check<T>): T | undefined {
	try {
		const raw = storage()?.getItem(PREFIX + key);
		if (raw === null || raw === undefined) return undefined;
		const value: unknown = JSON.parse(raw);
		return !check || check(value) ? (value as T) : undefined;
	} catch {
		return undefined;
	}
}

/** Write `tvt:v2:<key>`; false when it couldn't be stored. */
export function writeStored(key: string, value: unknown): boolean {
	try {
		const s = storage();
		if (!s) return false;
		s.setItem(PREFIX + key, JSON.stringify(value));
		return true;
	} catch {
		return false;
	}
}

export function removeStored(key: string): void {
	try {
		storage()?.removeItem(PREFIX + key);
	} catch {
		/* nothing to do */
	}
}

/** Read a key outside the `tvt:v2:` space (old keys being migrated); null on any problem. */
export function readLegacy(key: string): string | null {
	try {
		return storage()?.getItem(key) ?? null;
	} catch {
		return null;
	}
}

/**
 * One remembered value as reactive state: reads storage once, writes on every
 * set. `value` is `$state.raw`, so replace objects rather than mutating them.
 */
export class Persisted<T> {
	#value = $state.raw<T>() as T;

	constructor(
		readonly key: string,
		fallback: T,
		check?: Check<T>
	) {
		this.#value = readStored(key, check) ?? fallback;
	}

	get value(): T {
		return this.#value;
	}

	set value(v: T) {
		this.#value = v;
		writeStored(this.key, v);
	}
}
