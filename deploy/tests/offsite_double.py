"""A stand-in for the off-site storage that deploy/bin/cold-videos reaches through OFFSITE_SSH, for the tests:
the same verbs (ping, list, put, verify, get), over a folder.

    python3 offsite_double.py <folder> <verb> [args...]

Files are kept at <folder>/store/<rel>. As the real one does, put leaves a file already there with the same
size as it is and refuses one with another size; verify leaves out what it doesn't hold or can't read; and get
answers nothing (exit 0) for a file it doesn't hold. <folder>/faults.json, when it's there, makes it misbehave:
  {"down": true}                        every verb fails (exit 255, as ssh does when it can't connect)
  {"verify_down": true}                 verify fails outright (exit 1, nothing read back)
  {"put_answers": "<sha256>"}           put answers this sha256 instead of what arrived
  {"lose": ["<rel>", ...]}              put answers ok but keeps nothing; list and verify don't see these
  {"corrupt": ["<rel>", ...]}           verify and get return other bytes for these (the stored file is fine)
  {"unreadable": ["<rel>", ...]}        listed, but verify leaves these out and get fails (exit 1)
Each call is appended to <folder>/calls.log as "<verb> <args>".
"""
import hashlib
import json
import os
import re
import sys

REL = re.compile(r"video/(?P<cam>[A-Za-z0-9_]{1,32})/(?P<year>\d{4})/(?P=cam)-(?P=year)-\d\d-\d\d\.(?:mp4|csv)")


def main(folder, verb, *args):
    store = os.path.join(folder, "store")
    try:
        with open(os.path.join(folder, "faults.json")) as f:
            faults = json.load(f)
    except FileNotFoundError:
        faults = {}
    with open(os.path.join(folder, "calls.log"), "a") as f:
        f.write(" ".join((verb, *args)) + "\n")
    if faults.get("down"):
        print("ssh: connect to host: Connection refused", file=sys.stderr)
        return 255
    lose, corrupt = set(faults.get("lose", [])), set(faults.get("corrupt", []))
    unreadable = set(faults.get("unreadable", []))

    def read(rel):
        with open(os.path.join(store, rel), "rb") as f:
            data = f.read()
        return data[::-1] + b"!" if rel in corrupt else data

    def held():
        for root, _, names in os.walk(store):
            for name in names:
                rel = os.path.relpath(os.path.join(root, name), store)
                if REL.fullmatch(rel) and rel not in lose:
                    yield rel

    for rel in args[:1] if verb in ("put", "get") else ():
        if not REL.fullmatch(rel):
            print(f"not a camera file path: {rel!r}", file=sys.stderr)
            return 1
    if verb == "ping" and not args:
        print("ok")
    elif verb == "list" and not args:
        for rel in sorted(held()):
            print(f"{os.path.getsize(os.path.join(store, rel))}\t{rel}")
    elif verb == "put" and len(args) == 3:
        rel, size, mtime_ns = args[0], int(args[1]), int(args[2])
        data = sys.stdin.buffer.read()
        if len(data) != size:
            print(f"the stream had {len(data)} bytes, not {size}", file=sys.stderr)
            return 1
        path = os.path.join(store, rel)
        if os.path.exists(path) and os.path.getsize(path) != size:
            print(f"it already holds {os.path.getsize(path)} bytes there, not {size}; it isn't replaced",
                  file=sys.stderr)
            return 1
        if rel not in lose and not os.path.exists(path):
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path + ".tmp", "wb") as f:
                f.write(data)
            os.utime(path + ".tmp", ns=(mtime_ns, mtime_ns))
            os.replace(path + ".tmp", path)
        print("ok", faults.get("put_answers") or hashlib.sha256(data).hexdigest())
    elif verb == "verify" and not args:
        if faults.get("verify_down"):
            print("read-back failed", file=sys.stderr)
            return 1
        there = set(held()) - unreadable
        for rel in sys.stdin.read().split():
            if rel in there:
                print(f"{hashlib.sha256(read(rel)).hexdigest()}  {rel}")
    elif verb == "get" and len(args) == 1:
        if args[0] in unreadable:
            print("read failed", file=sys.stderr)
            return 1
        if args[0] in set(held()):
            sys.stdout.buffer.write(read(args[0]))
    else:
        print(f"not a request this host takes: {verb} {' '.join(args)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
