#!/usr/bin/env bash
# Build the self-hosted basemap the app reads from /tiles/:
#   valley.pmtiles   OpenStreetMap vector tiles (Protomaps), cut to Ada + Canyon
#   fonts/, sprites/ glyphs and icons the Protomaps style needs
#   manifest.json    what was built (the app shows exactly this)
#
# Terrain and buildings are separate steps, still to come (see README.md).
#
# Needs: pmtiles (go-pmtiles CLI), git, curl, python3.
# Usage: basemap/build.sh            # output in data/tiles/
#        TILES_DIR=/srv/tvt/tiles basemap/build.sh
set -euo pipefail
cd "$(dirname "$0")/.."

OUT=${TILES_DIR:-data/tiles}
BBOX=${BBOX:--117.05,43.00,-115.95,43.85}   # west,south,east,north: Ada + Canyon counties
CENTER=${CENTER:--116.40,43.60}
MAXZOOM=${MAXZOOM:-15}
FLAVOR=light
FONTS=("Noto Sans Regular" "Noto Sans Medium" "Noto Sans Italic")

for tool in pmtiles git curl python3; do
	command -v "$tool" >/dev/null || { echo "missing tool: $tool (see basemap/README.md)" >&2; exit 1; }
done
mkdir -p "$OUT"

# 1. Valley extract from the latest daily planet build. pmtiles reads only the
#    byte ranges it needs, so this downloads well under 1 GB, not the planet.
BUILD=${BUILD:-$(curl -fsS https://build-metadata.protomaps.dev/builds.json |
	python3 -c 'import json,sys; print(json.load(sys.stdin)[-1]["key"])')}
echo "Extracting $BUILD, bbox $BBOX, up to z$MAXZOOM"
pmtiles extract "https://build.protomaps.com/$BUILD" "$OUT/valley.pmtiles.part" \
	--bbox="$BBOX" --maxzoom="$MAXZOOM"
mv "$OUT/valley.pmtiles.part" "$OUT/valley.pmtiles"

# 2. Fonts and sprites from protomaps/basemaps-assets (only what the style uses).
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
git clone --quiet --depth 1 --filter=blob:none --no-checkout \
	https://github.com/protomaps/basemaps-assets "$tmp/assets"
patterns=("/sprites/v4/" "/fonts/OFL.txt" "/README.md")   # OFL.txt: the fonts' license
for f in "${FONTS[@]}"; do patterns+=("/fonts/$f/"); done
git -C "$tmp/assets" sparse-checkout set --no-cone "${patterns[@]}"
git -C "$tmp/assets" checkout --quiet
rm -rf "$OUT/fonts" "$OUT/sprites"
cp -r "$tmp/assets/fonts" "$tmp/assets/sprites" "$OUT/"

# 3. Manifest. Later steps (terrain, buildings) add their own entries.
python3 - "$OUT" "$BBOX" "$CENTER" "$BUILD" "$FLAVOR" <<'EOF'
import json, os, sys, datetime
out, bbox, center, build, flavor = sys.argv[1:]
path = os.path.join(out, "manifest.json")
m = json.load(open(path)) if os.path.exists(path) else {}
m.update({
    "bounds": [float(x) for x in bbox.split(",")],
    "center": [float(x) for x in center.split(",")],
    "zoom": 10,
    "basemap": {
        "file": "valley.pmtiles",
        "flavor": flavor,
        "attribution": '<a href="https://protomaps.com">Protomaps</a> © <a href="https://openstreetmap.org/copyright">OpenStreetMap</a>',
        "built": datetime.date.today().isoformat(),
        "source": f"https://build.protomaps.com/{build}",
    },
    "glyphs": "fonts/{fontstack}/{range}.pbf",
    "sprite": f"sprites/v4/{flavor}",
})
json.dump(m, open(path, "w"), indent=1)
print("wrote", path)
EOF
ls -la "$OUT"
