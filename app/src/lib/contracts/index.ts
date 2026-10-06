/**
 * Frozen JSON contracts shared by server and client (docs/14 §14.8, §14.10).
 *
 * Written by WP0 from the plan; they change only through the wave
 * integrator. A package that needs a change says so in its hand-back and
 * works against the frozen version meanwhile. Each response carries its
 * `contract` number.
 */
export * from './meta.js';
export * from './network.js';
export * from './tracks.js';
export * from './live.js';
