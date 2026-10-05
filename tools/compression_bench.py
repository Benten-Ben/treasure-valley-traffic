"""Compare storing 1-frame-per-minute camera JPEGs vs. encoding them as video.

Each directory holds one camera's frames named f01.jpg, f02.jpg, ... (from
511 Idaho's /map/Cctv/<id> images). Prints a Markdown table per camera:
size vs the JPEGs, SSIM against the originals, and encode time.
Results so far: docs/11-camera-validation-layer.md, "Measured results".

    python3 tools/compression_bench.py frames/656 frames/752

Needs ffmpeg built with libx264, libx265 and libsvtav1.
"""
import glob, hashlib, os, re, subprocess, sys, tempfile, time

CONFIGS = [
    # name, codec args
    ("H.264 all-intra (no inter-frame) crf23", ["-c:v", "libx264", "-preset", "slow", "-crf", "23", "-g", "1"]),
    ("H.264 crf18", ["-c:v", "libx264", "-preset", "slow", "-crf", "18", "-g", "600"]),
    ("H.264 crf23", ["-c:v", "libx264", "-preset", "slow", "-crf", "23", "-g", "600"]),
    ("H.264 crf28", ["-c:v", "libx264", "-preset", "slow", "-crf", "28", "-g", "600"]),
    ("H.265 crf20", ["-c:v", "libx265", "-preset", "slow", "-crf", "20", "-x265-params", "keyint=600:log-level=error"]),
    ("H.265 crf24", ["-c:v", "libx265", "-preset", "slow", "-crf", "24", "-x265-params", "keyint=600:log-level=error"]),
    ("H.265 crf28", ["-c:v", "libx265", "-preset", "slow", "-crf", "28", "-x265-params", "keyint=600:log-level=error"]),
    ("AV1 (SVT) crf30", ["-c:v", "libsvtav1", "-preset", "6", "-crf", "30", "-g", "600"]),
    ("AV1 (SVT) crf38", ["-c:v", "libsvtav1", "-preset", "6", "-crf", "38", "-g", "600"]),
    ("AV1 (SVT) crf46", ["-c:v", "libsvtav1", "-preset", "6", "-crf", "46", "-g", "600"]),
]


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True)


def ssim(video, pattern):
    r = run(["ffmpeg", "-hide_banner", "-i", video, "-framerate", "1", "-i", pattern,
             "-lavfi", "[0:v]format=yuv420p[a];[1:v]format=yuv420p[b];[a][b]ssim", "-f", "null", "-"])
    m = re.search(r"All:([0-9.]+)", r.stderr)
    return float(m.group(1)) if m else None


def bench(cam_dir):
    frames = sorted(glob.glob(os.path.join(cam_dir, "f*.jpg")))
    hashes = {hashlib.md5(open(f, "rb").read()).hexdigest() for f in frames}
    jpeg_bytes = sum(os.path.getsize(f) for f in frames)
    pattern = os.path.join(cam_dir, "f%02d.jpg")
    print(f"\n## camera {os.path.basename(cam_dir)}: {len(frames)} frames ({len(hashes)} distinct), "
          f"JPEG total {jpeg_bytes/1024:.0f} KB ({jpeg_bytes/len(frames)/1024:.1f} KB/frame)")
    print(f"| Config | Size | vs JPEG | KB/frame | SSIM vs original | Encode time |")
    print("|---|---|---|---|---|---|")
    out = tempfile.mkdtemp()
    for name, args in CONFIGS:
        path = os.path.join(out, re.sub(r"\W+", "_", name) + ".mkv")
        t0 = time.time()
        r = run(["ffmpeg", "-hide_banner", "-y", "-framerate", "1", "-i", pattern, *args,
                 "-pix_fmt", "yuv420p", path])
        dt = time.time() - t0
        if r.returncode:
            print(f"| {name} | FAILED: {r.stderr.strip().splitlines()[-1][:80]} |")
            continue
        size = os.path.getsize(path)
        print(f"| {name} | {size/1024:.0f} KB | {jpeg_bytes/size:.1f}x smaller | {size/len(frames)/1024:.1f} | "
              f"{ssim(path, pattern):.4f} | {dt:.1f}s |")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    for cam in sys.argv[1:]:
        bench(cam)
