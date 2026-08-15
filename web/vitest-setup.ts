// Node ≥ 22 defines its own experimental `localStorage`/`sessionStorage`
// globals — lazy getters that return undefined unless the process was started
// with --localstorage-file. Vitest's jsdom environment skips copying keys the
// Node global already owns, and its `window` is the global itself, so no jsdom
// Storage object is reachable anywhere: `localStorage` is undefined in every
// test despite the non-opaque jsdom URL. Install a spec-adequate in-memory
// Storage over both globals. Fresh per test file; tests clear it themselves
// where isolation within a file matters.

class MemoryStorage implements Storage {
	#items = new Map<string, string>();

	get length(): number {
		return this.#items.size;
	}

	key(index: number): string | null {
		return [...this.#items.keys()][index] ?? null;
	}

	getItem(key: string): string | null {
		return this.#items.get(key) ?? null;
	}

	setItem(key: string, value: string): void {
		this.#items.set(String(key), String(value));
	}

	removeItem(key: string): void {
		this.#items.delete(key);
	}

	clear(): void {
		this.#items.clear();
	}
}

for (const name of ['localStorage', 'sessionStorage'] as const) {
	Object.defineProperty(globalThis, name, {
		value: new MemoryStorage(),
		configurable: true
	});
}
