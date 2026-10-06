// The map needs WebGL, so everything under the map layout renders in the
// browser only. No load here: the shell must not wait for anything
// (docs/14 §14.8); the boot fetches start at module scope instead.
export const ssr = false;
