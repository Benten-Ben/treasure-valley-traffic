import { defineEnvVars } from '@sveltejs/kit/env';

export const variables = defineEnvVars({
	DATABASE_URL: {
		description: 'PostgreSQL + PostGIS connection string. Camera features answer 503 without it.',
		schema: (value) => value || undefined
	},
	FRAMES_DIR: {
		description: 'Folder where captured camera frames (calibration reference images) are kept.',
		schema: (value) => value || '../data/frames'
	},
	TVT_FRAME_SOURCE: {
		description:
			"Where camera frames come from: '511' (default, 511 Idaho's republished images) or 'fixture' " +
			'(seeded frames under FRAMES_DIR/_fixture; nothing is fetched). Tests and build agents use fixture.',
		schema: (value): '511' | 'fixture' => {
			if (!value || value === '511') return '511';
			if (value === 'fixture') return 'fixture';
			throw new Error(`TVT_FRAME_SOURCE must be '511' or 'fixture', not '${value}'`);
		}
	},
	CAMERA_IMAGES_ENABLED: {
		description:
			'Live camera images (docs/14 §14.6): the capture archive and the on-demand 511 fetcher behind ' +
			'/api/cameras/live, /api/cameras/status, /camera-frames/ and /api/views/[id]/live/. Off unless set to ' +
			"'true' (or 1, yes, on); deploy/compose.live-images.yml turns it on.",
		schema: (value): boolean => {
			const v = (value ?? '').trim().toLowerCase();
			if (['', '0', 'false', 'no', 'off'].includes(v)) return false;
			if (['1', 'true', 'yes', 'on'].includes(v)) return true;
			throw new Error(`CAMERA_IMAGES_ENABLED must be true or false, not '${value}'`);
		}
	},
	TVT_ARCHIVE: {
		description:
			'The capture archive written by ingest/sources/idaho511_frames.py. The app reads only its ' +
			'cameras/jpeg (frames and index.csv) and cameras/status (one file per capture service), read-only, ' +
			'and only when CAMERA_IMAGES_ENABLED is on. Unset: every camera is fetched on demand.',
		schema: (value) => value || undefined
	}
});
