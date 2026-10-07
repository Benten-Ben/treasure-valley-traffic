import { ROAD_WEATHER_ICON } from './icons.js';
import { BADGE_PX, CREAM, INK, INK_SOFT } from './layers.js';

/**
 * The station badges, painted once on a canvas for map.addImage (docs/14
 * §14.6 "Road weather"):
 *
 * - **solid:** a cream rounded square with an ink edge and the ink
 *   thermometer-and-road icon (duotone, as Phosphor draws it);
 * - **hollow** (every view shows 511's "no live feed" picture): no fill, a
 *   dashed ink edge and a line-only icon in soft ink, each with a cream halo
 *   so it reads on aerial imagery too.
 *
 * Shape tells them apart, never color alone. Browser only (canvas).
 */

/** The icon inside the badge, CSS px. */
const ICON_PX = 22;
/** Extra line width in the icon's 256 box, so the thin duotone lines hold up at map size. */
const THICKEN = 9;

export function badgeImage(hollow: boolean, ratio = 2): ImageData | null {
	if (typeof document === 'undefined') return null;
	const px = BADGE_PX * ratio;
	const canvas = document.createElement('canvas');
	canvas.width = canvas.height = px;
	const g = canvas.getContext('2d');
	if (!g) return null;
	const lw = 2 * ratio;
	const inset = 2 * ratio;
	const side = px - 2 * inset;
	const rounded = () => {
		g.beginPath();
		g.roundRect(inset, inset, side, side, 7 * ratio);
	};
	rounded();
	if (hollow) {
		g.strokeStyle = CREAM;
		g.lineWidth = lw + 2 * ratio;
		g.stroke();
		g.strokeStyle = INK;
		g.lineWidth = lw;
		g.setLineDash([3.2 * ratio, 2.2 * ratio]);
		g.stroke();
		g.setLineDash([]);
	} else {
		g.fillStyle = CREAM;
		g.fill();
		g.strokeStyle = INK;
		g.lineWidth = lw;
		g.stroke();
	}
	const icon = ICON_PX * ratio;
	g.save();
	g.translate((px - icon) / 2, (px - icon) / 2);
	g.scale(icon / 256, icon / 256);
	g.lineJoin = 'round';
	for (const p of ROAD_WEATHER_ICON) {
		g.save();
		g.translate(p.x, p.y);
		g.scale(p.scale, p.scale);
		const line = new Path2D(p.icon.line);
		if (hollow) {
			g.strokeStyle = CREAM;
			g.lineWidth = 34;
			g.stroke(line);
		} else {
			g.globalAlpha = 0.2;
			g.fillStyle = INK;
			g.fill(new Path2D(p.icon.tone));
			g.globalAlpha = 1;
		}
		// Phosphor's lines are drawn for 24 px and up; on a map badge they're thickened a little.
		const ink = hollow ? INK_SOFT : INK;
		g.fillStyle = ink;
		g.strokeStyle = ink;
		g.lineWidth = THICKEN;
		g.fill(line);
		g.stroke(line);
		g.restore();
	}
	g.restore();
	return g.getImageData(0, 0, px, px);
}
