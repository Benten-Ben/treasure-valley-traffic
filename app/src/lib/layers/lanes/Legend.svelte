<script lang="ts">
	import type { LegendProps } from '../types.js';
	import { ASPHALT, CURB, EDGE, INK, MARKINGS } from '#lib/map/materials.js';
	import { ARROWS_FROM_ZOOM } from './layers.js';
	import type { LanesModule } from './index.svelte.js';

	/**
	 * The Lanes legend (plan v3 §4.2 P9): the markings (cream on asphalt in Valley, ink in Clay), the ▲ in words, the
	 * turn arrows, a crisp edge against a soft one (and "widths estimated where soft-edged"), and the credits.
	 */
	let { module }: LegendProps = $props();
	const lanes = $derived(module as unknown as LanesModule);
</script>

<p class="legend-title">Lanes</p>
<ul class="keys">
	<li>
		<svg viewBox="0 0 32 16" width="32" height="16" aria-hidden="true">
			<rect x="0" y="0" width="32" height="16" fill={ASPHALT.valley} />
			<line x1="1" y1="8" x2="31" y2="8" stroke={MARKINGS.onAsphalt.color} stroke-width="2" stroke-dasharray="6 4" />
		</svg>
		<span><b>Lane lines</b>: dashed or solid, cream on asphalt (ink in Clay), where a source gives the lane count</span>
	</li>
	<li>
		<svg viewBox="0 0 32 16" width="32" height="16" aria-hidden="true">
			<rect x="0" y="0" width="32" height="16" fill={ASPHALT.valley} />
			<line x1="1" y1="6.6" x2="31" y2="6.6" stroke={MARKINGS.onAsphalt.color} stroke-width="1.4" />
			<line x1="1" y1="9.4" x2="31" y2="9.4" stroke={MARKINGS.onAsphalt.color} stroke-width="1.4" />
		</svg>
		<span><b>Double line</b>: a centre line with no passing</span>
	</li>
	<li>
		<svg viewBox="0 0 32 20" width="32" height="20" aria-hidden="true">
			<polygon points="16,2 29,17 3,17" fill={MARKINGS.onAsphalt.color} stroke={INK} stroke-width="1.6" stroke-linejoin="round" />
			<rect x="11.5" y="8" width="3" height="7" rx="1" fill={INK} />
			<rect x="17.5" y="11" width="3" height="4" rx="1" fill={INK} />
		</svg>
		<span><b>▲ The sources disagree</b>: the lane-count sources differ by more than a lane (OpenStreetMap against ACHD's rule, or the sources ACHD's rule draws on). Click for the counts</span>
	</li>
	<li>
		<svg viewBox="0 0 32 32" width="32" height="32" aria-hidden="true">
			<rect x="0" y="0" width="32" height="32" fill={ASPHALT.valley} />
			<path d="M16 29 V12 M16 20 H8" fill="none" stroke={INK} stroke-width="5.4" />
			<path d="M16 29 V12 M16 20 H8" fill="none" stroke={MARKINGS.onAsphalt.color} stroke-width="3" />
			<polygon points="16,3 9.5,11.5 22.5,11.5" fill={MARKINGS.onAsphalt.color} stroke={INK} stroke-width="1.6" stroke-linejoin="round" />
			<polygon points="2.5,20 9.5,14.4 9.5,25.6" fill={MARKINGS.onAsphalt.color} stroke={INK} stroke-width="1.6" stroke-linejoin="round" />
		</svg>
		<span><b>Turn arrows</b>: a lane's turns, from z{ARROWS_FROM_ZOOM}</span>
	</li>
</ul>
<ul class="keys edges" aria-label="Edges">
	<li>
		<svg viewBox="0 0 32 16" width="32" height="16" aria-hidden="true">
			<rect x="0" y="0" width="32" height="10" fill={ASPHALT.valley} />
			<line x1="0" y1="10" x2="32" y2="10" stroke={CURB} stroke-width="2" />
		</svg>
		<span><b>Crisp edge</b>: the width is measured or inventoried</span>
	</li>
	<li>
		<svg viewBox="0 0 32 16" width="32" height="16" aria-hidden="true">
			<defs>
				<filter id="lanes-soft" x="-5%" y="-30%" width="110%" height="160%"><feGaussianBlur stdDeviation="1.6" /></filter>
			</defs>
			<rect x="0" y="0" width="32" height="10" fill={ASPHALT.valley} filter="url(#lanes-soft)" opacity="0.9" />
			<line x1="0" y1="10" x2="32" y2="10" stroke={EDGE} stroke-width="4" opacity="0.7" filter="url(#lanes-soft)" />
		</svg>
		<span><b>Soft edge</b>: widths estimated where soft-edged (counted from the lanes, or a default for the road)</span>
	</li>
</ul>
{#if !lanes.roads}
	<p class="note">Roads at real width are not built yet, so there are no lane marks to show.</p>
{:else}
	<p class="hint">Click a road, a marking or a lot for what we know and where it comes from.</p>
{/if}
<p class="credit">© OpenStreetMap contributors (ODbL) · ACHD, ITD, COMPASS and USDA NASS CDL: internal, shown on this map only</p>

<style>
	li {
		display: flex;
		align-items: center;
		gap: 8px;
		font-size: 12px;
	}
	svg {
		flex: none;
	}
	.edges {
		margin-top: 6px;
	}
	.note {
		margin: 6px 0 0;
		font-size: 12px;
		color: var(--ink);
	}
</style>
