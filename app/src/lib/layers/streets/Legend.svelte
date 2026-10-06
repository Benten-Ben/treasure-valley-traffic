<script lang="ts">
	import type { LegendProps } from '../types.js';
	import { SPEED_BINS } from './streets.js';

	let props: LegendProps = $props();
</script>

<p class="legend-title">Posted speed</p>
<ul class="keys">
	{#each SPEED_BINS as b (b.from)}
		<li><i class="swatch" style:background={b.color}></i>{b.label}</li>
	{/each}
</ul>
<p class="hint">Wider line: bigger road class · ›› one-way</p>
<p class="credit">Ada County: ACHD road centerlines. Canyon County isn't covered yet. Most local streets read 20 mph, likely a default.</p>
