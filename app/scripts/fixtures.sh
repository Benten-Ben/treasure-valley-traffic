#!/usr/bin/env bash
# Synthetic camera frames for tests and seeds (docs/14 §14.11, "Seeded data").
# Never a real camera image: an ffmpeg test pattern with a label, plus a
# 511-style timestamp bar along the bottom, at the height the calibrator
# expects for that frame size (H - round(W*9/16) when that's between 20 px
# and 10% of H, else round(0.073*H)).
#
#   fixtures.sh frame  <out.jpg> <width> <height> <label>
#   fixtures.sh series <outdir> <width> <height> <label> <count>   # frame-01.jpg … (each different)
set -euo pipefail

usage() { sed -n '2,10p' "$0" >&2; exit 2; }
[ $# -ge 5 ] || usage
mode=$1 out=$2 w=$3 h=$4 label=$5 count=${6:-1}

bar=$(( h - (w * 9 + 8) / 16 ))
if [ "$bar" -lt 20 ] || [ $(( bar * 10 )) -gt "$h" ]; then bar=$(( (h * 73 + 500) / 1000 )); fi
font=/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf
fontopt=""
[ -f "$font" ] && fontopt="fontfile=$font:"

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
printf '%s' "$label" > "$tmp/label.txt"
printf 'SYNTHETIC TEST FRAME - %s' "$label" > "$tmp/bar.txt"
size=$(( h / 14 )); [ "$size" -lt 10 ] && size=10
barsize=$(( bar * 5 / 10 )); [ "$barsize" -lt 9 ] && barsize=9

vf="drawtext=${fontopt}textfile=$tmp/label.txt:fontsize=$size:fontcolor=white:box=1:boxcolor=black@0.55:boxborderw=8:x=(w-text_w)/2:y=(h-$bar-text_h)/2"
vf="$vf,drawtext=${fontopt}text='%{n}':fontsize=$size:fontcolor=yellow:x=16:y=16"
vf="$vf,drawbox=x=0:y=ih-$bar:w=iw:h=$bar:color=black:t=fill"
vf="$vf,drawtext=${fontopt}textfile=$tmp/bar.txt:fontsize=$barsize:fontcolor=white:x=10:y=h-$bar+($bar-text_h)/2"

case $mode in
	frame)
		mkdir -p "$(dirname "$out")"
		ffmpeg -loglevel error -y -f lavfi -i "testsrc2=size=${w}x${h}:rate=1" -vf "$vf" -frames:v 1 -q:v 5 "$out"
		;;
	series)
		mkdir -p "$out"
		ffmpeg -loglevel error -y -f lavfi -i "testsrc2=size=${w}x${h}:rate=1" -vf "$vf" -frames:v "$count" -q:v 6 \
			-start_number 1 "$out/frame-%02d.jpg"
		;;
	*) usage ;;
esac
