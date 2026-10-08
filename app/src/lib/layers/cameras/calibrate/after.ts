import type { AppCtx } from '#lib/app/context.js';
import { toasts } from '#lib/ui/toasts.svelte.js';
import type { CamerasModule } from '../index.svelte.js';

/**
 * After a save (docs/14 §14.6, "Leaving"): once the snapshot is restored,
 * the camera's window opens again and a toast offers "Look through to
 * check", which looks through the calibration just saved.
 */
export interface Saved {
	cameraId: number;
	viewId: number;
	/** The new calibration row. */
	id: number;
	rms: number;
	name: string;
}

export const SAVED_TOAST = 'calibration-saved';

export function afterSave(app: AppCtx, s: Saved): void {
	const mod = app.layers?.modules.cameras as CamerasModule | undefined;
	mod?.open(s.cameraId);
	toasts.show(`Saved: ${s.name} is calibrated (fit ${s.rms.toFixed(2)} px).`, {
		key: SAVED_TOAST,
		timeout: 20_000,
		action: mod ? { label: 'Look through to check', run: () => void lookAtSaved(mod, s) } : undefined
	});
}

/** Look through the saved calibration (fetching the cameras' calibrations again first if they're older). */
export async function lookAtSaved(mod: CamerasModule, s: Saved): Promise<boolean> {
	if (!mod.calibrations.some((c) => c.calibrationId === s.id)) await mod.reload();
	return mod.lookThrough(s.cameraId, s.viewId);
}
