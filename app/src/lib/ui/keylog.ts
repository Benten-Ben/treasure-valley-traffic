/** The ids of the last 20 key bindings that ran (for `__tvt.layers.keys`, tests and the console). */
export const ranLog: string[] = [];

export function logKey(id: string): void {
	ranLog.push(id);
	if (ranLog.length > 20) ranLog.shift();
}
