#!/usr/bin/env python3
"""Check that nothing private goes into this public repository.

CLAUDE.md ("This repository is public") lists what must never be committed.
This catches the mechanical part of it, in the content git would push (the
index, so staged changes count and unstaged ones don't):

  - images and video outside a short allowlist, found by extension or by
    content (camera frames are third-party copies);
  - Tailscale machine names (*.ts.net), Tailscale and CGNAT addresses
    (100.64.0.0/10, fd7a:115c:a1e0::/48) and Tailscale auth keys;
  - private keys;
  - deploy/.env or any other .env file (the server's settings and secrets);
  - anything under data/ or site/data/ (collected and third-party data).

It can't judge prose: hardware, user names, other guests on the server and
unsent drafts still need a read of the diff before every push.

Usage:
  python3 tools/check_public.py              every tracked file, as staged (the repo as it would be pushed)
  python3 tools/check_public.py --staged     only files with staged changes (for a pre-commit hook)
  python3 tools/check_public.py --since REV  only files changed since REV (a branch's diff)
  python3 tools/check_public.py --root DIR   check another checkout

Exits 1 and lists each problem (matches partly masked), or 0 when clean.
Standard library only.
"""

import argparse
import fnmatch
import os
import re
import subprocess
import sys

# Images that may be committed: our own icons, never photos.
ALLOW_IMAGES = [
    "app/src/lib/assets/*.svg",
    "app/static/favicon.svg",
    "app/static/favicon.png",
    "app/static/favicon.ico",
    "app/static/apple-touch-icon.png",
]

IMAGE_EXT = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".avif", ".bmp", ".tif", ".tiff", ".heic", ".heif",
    ".ico", ".svg", ".mkv", ".mp4", ".webm", ".mov", ".avi", ".m4v",
}

LABEL = r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
TS_NET = re.compile(rf"(?<![\w.-]){LABEL}(?:\.{LABEL})*\.ts\.net\b", re.I)
IPV4 = re.compile(r"(?<![\w.])(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})(?!\.?\d)(?!/\d)")
TS_IPV6 = re.compile(r"\bfd7a:115c:a1e0:[0-9a-f:]*", re.I)
TS_KEY = re.compile(r"\btskey-[a-z]+-[A-Za-z0-9]{6,}")
PRIVATE_KEY = re.compile(r"-----BEGIN (?:[A-Z]+ )?PRIVATE KEY-----")


def git(root, *args, data=None):
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    return subprocess.run(["git", "-C", root, *args], input=data, capture_output=True, check=True, env=env).stdout


def image_kind(head):
    """What an image or video file is, from its first bytes; None if it isn't one."""
    if head.startswith(b"\xff\xd8\xff"):
        return "JPEG"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "PNG"
    if head[:6] in (b"GIF87a", b"GIF89a"):
        return "GIF"
    if head[:4] == b"RIFF" and head[8:12] in (b"WEBP", b"AVI "):
        return "WebP" if head[8:12] == b"WEBP" else "AVI"
    if head[4:8] == b"ftyp":
        return "ISO media (MP4, MOV, AVIF or HEIC)"
    if head.startswith(b"\x1a\x45\xdf\xa3"):
        return "Matroska/WebM"
    if head.startswith(b"BM") and len(head) > 14:
        return "BMP"
    if head[:4] in (b"II*\x00", b"MM\x00*"):
        return "TIFF"
    return None


def mask(text):
    return text[:4] + "…" if len(text) > 4 else "…"


def is_cgnat(m):
    octets = [int(g) for g in m.groups()]
    return all(o <= 255 for o in octets) and octets[0] == 100 and 64 <= octets[1] <= 127


def check_path(path):
    problems = []
    if path.startswith(("data/", "site/data/")):
        problems.append("collected data (data/ and site/data/ stay local)")
    name = os.path.basename(path)
    if name == ".env" or (name.startswith(".env.") and not name.endswith(".example")):
        problems.append("an .env file (server settings and secrets stay on the server)")
    return problems


def check_content(path, blob):
    problems = []
    ext = os.path.splitext(path)[1].lower()
    allowed = any(fnmatch.fnmatch(path, pat) for pat in ALLOW_IMAGES)
    kind = image_kind(blob[:16])
    if (ext in IMAGE_EXT or kind) and not allowed:
        problems.append((0, f"an image or video ({kind or ext}) outside the allowlist in tools/check_public.py"))
    if b"\x00" in blob[:8000]:
        return problems  # binary: no text checks
    text = blob.decode("utf-8", errors="replace")
    for n, line in enumerate(text.splitlines(), 1):
        for m in TS_NET.finditer(line):
            problems.append((n, f"a Tailscale name ({mask(m.group(0))})"))
        for m in IPV4.finditer(line):
            if is_cgnat(m):
                problems.append((n, f"a Tailscale/CGNAT address ({mask(m.group(0))})"))
        for m in TS_IPV6.finditer(line):
            problems.append((n, f"a Tailscale IPv6 address ({mask(m.group(0))})"))
        if TS_KEY.search(line):
            problems.append((n, "a Tailscale auth key"))
        if PRIVATE_KEY.search(line):
            problems.append((n, "a private key"))
    return problems


def index_files(root):
    """{path: blob sha} for every file in the index (tracked plus staged)."""
    out = {}
    for rec in git(root, "ls-files", "-s", "-z").split(b"\0"):
        if not rec:
            continue
        meta, path = rec.split(b"\t", 1)
        mode, sha, _stage = meta.split()
        if mode == b"160000":  # submodule
            continue
        out[path.decode()] = sha.decode()
    return out


def changed(root, args):
    if args.staged:
        names = git(root, "diff", "--cached", "--name-only", "-z", "--diff-filter=ACMR")
    else:
        names = git(root, "diff", "--cached", "--name-only", "-z", "--diff-filter=ACMR", args.since)
    return {n.decode() for n in names.split(b"\0") if n}


def read_blobs(root, shas):
    """Blob contents by sha, through one git cat-file --batch."""
    if not shas:
        return {}
    out = git(root, "cat-file", "--batch", data="".join(f"{s}\n" for s in shas).encode())
    blobs, i = {}, 0
    for sha in shas:
        nl = out.index(b"\n", i)
        size = int(out[i:nl].split()[2])
        blobs[sha] = out[nl + 1:nl + 1 + size]
        i = nl + 1 + size + 1
    return blobs


def check(root, args):
    files = index_files(root)
    if args.staged or args.since:
        keep = changed(root, args)
        files = {p: s for p, s in files.items() if p in keep}
    blobs = read_blobs(root, sorted(set(files.values())))
    problems = []
    for path in sorted(files):
        for p in check_path(path):
            problems.append(f"{path}: {p}")
        for line, p in check_content(path, blobs[files[path]]):
            problems.append(f"{path}:{line}: {p}" if line else f"{path}: {p}")
    return len(files), problems


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--root", default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--staged", action="store_true", help="only files with staged changes")
    g.add_argument("--since", metavar="REV", help="only files changed since REV")
    args = ap.parse_args(argv)
    n, problems = check(args.root, args)
    if problems:
        print(f"check_public: {len(problems)} problem(s) in {n} file(s) checked:")
        for p in problems:
            print(f"  {p}")
        print("Move private material to the server's private files (CLAUDE.md, \"This repository is public\").")
        return 1
    print(f"check_public: {n} file(s) checked, nothing private found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
