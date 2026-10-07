#!/bin/sh
# Decode the windows naip_ccm.py planned, one at a time, for its `convert`
# step to pick up. Runs inside a container with LizardTech's MrSID Decode SDK
# mounted at /dsdk (never included in this repository; see basemap/README.md).
#
#   naip_ccm_decode.sh MOSAIC.sid WINDOWS.txt RAW TIFS [MAX_QUEUED] [THREADS]
#
# A window already converted (TIFS/<name>.tif) or waiting (RAW/<name>.tif) is
# skipped, so a rerun resumes. Decoding pauses while MAX_QUEUED windows wait
# for conversion (each is about 335 MB). RAW/DONE marks the end.
set -eu
sid=$1; list=$2; raw=$3; tifs=$4; maxq=${5:-3}; threads=${6:-3}
mkdir -p "$raw"
rm -f "$raw/DONE" "$raw"/*.part.tif
n=0
while read -r name ulx uly w h; do
  [ -e "$tifs/$name.tif" ] && continue
  [ -e "$raw/$name.tif" ] && continue
  while [ "$(ls "$raw" | grep -c '\.tif$' || true)" -ge "$maxq" ]; do sleep 2; done
  /dsdk/bin/mrsiddecode -quiet -j "$threads" -i "$sid" -o "$raw/$name.part.tif" -of tifg \
    -coord image -ulxy "$ulx" "$uly" -wh "$w" "$h"
  mv "$raw/$name.part.tif" "$raw/$name.tif"
  n=$((n + 1))
done < "$list"
touch "$raw/DONE"
echo "decode: $n windows decoded"
