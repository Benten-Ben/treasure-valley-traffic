import { afterEach, describe, expect, it, vi } from 'vitest';
import { Persisted, PREFIX, readLegacy, readStored, removeStored, writeStored } from './persisted.svelte.js';

function memoryStorage() {
	const data = new Map<string, string>();
	return {
		data,
		getItem: (k: string) => data.get(k) ?? null,
		setItem: (k: string, v: string) => void data.set(k, v),
		removeItem: (k: string) => void data.delete(k)
	};
}

const throwing = {
	getItem: () => {
		throw new Error('SecurityError');
	},
	setItem: () => {
		throw new Error('QuotaExceededError');
	},
	removeItem: () => {
		throw new Error('SecurityError');
	}
};

const isNumber = (v: unknown): v is number => typeof v === 'number';

describe('persisted state', () => {
	afterEach(() => vi.unstubAllGlobals());

	it('stores JSON under tvt:v2:', () => {
		const s = memoryStorage();
		vi.stubGlobal('localStorage', s);
		expect(writeStored('view', { zoom: 12 })).toBe(true);
		expect(s.data.get(`${PREFIX}view`)).toBe('{"zoom":12}');
		expect(readStored('view')).toEqual({ zoom: 12 });
		removeStored('view');
		expect(readStored('view')).toBeUndefined();
	});

	it('reads a value that fails its check, or does not parse, as missing', () => {
		const s = memoryStorage();
		vi.stubGlobal('localStorage', s);
		s.setItem(`${PREFIX}n`, '"seven"');
		s.setItem(`${PREFIX}bad`, '{not json');
		expect(readStored('n', isNumber)).toBeUndefined();
		expect(readStored('bad')).toBeUndefined();
	});

	it('works the same when storage throws or is missing', () => {
		vi.stubGlobal('localStorage', throwing);
		expect(readStored('view')).toBeUndefined();
		expect(writeStored('view', 1)).toBe(false);
		expect(() => removeStored('view')).not.toThrow();
		expect(readLegacy('tvt-lens')).toBeNull();
		vi.stubGlobal('localStorage', undefined);
		expect(readStored('view')).toBeUndefined();
		expect(writeStored('view', 1)).toBe(false);
		const p = new Persisted('n', 3, isNumber);
		p.value = 4;
		expect(p.value).toBe(4);
	});

	it('Persisted reads once and writes on every set', () => {
		const s = memoryStorage();
		vi.stubGlobal('localStorage', s);
		s.setItem(`${PREFIX}n`, '7');
		const p = new Persisted('n', 3, isNumber);
		expect(p.value).toBe(7);
		p.value = 9;
		expect(s.data.get(`${PREFIX}n`)).toBe('9');
		expect(new Persisted('missing', 3, isNumber).value).toBe(3);
	});

	it('reads old keys outside the tvt:v2: space for migrations', () => {
		const s = memoryStorage();
		vi.stubGlobal('localStorage', s);
		s.setItem('tvt-lens', 'transit');
		expect(readLegacy('tvt-lens')).toBe('transit');
	});
});
