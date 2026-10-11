"""Runs deploy/bin/heavy as a program for the tests, with its folders, clock and free disk
taken from the JSON in HEAVY_HARNESS. heavy itself reads none of this: the installed tool
has no test hooks.

    HEAVY_HARNESS='{"work": "/tmp/w", "status": "/tmp/s", "now": "2026-10-11 14:00",
                    "free_file": "/tmp/free", "grace_s": 3}' python3 heavy_harness.py <heavy args>

  work       heavy's work folder (heavy.lock, heavy.log, heavy.conf, MAINTENANCE)
  status     the folder of the capture services' status files
  now        the clock's start, Boise unless it gives an offset
  free_file  a file holding one number: the GB free everywhere, re-read at each check
  grace_s    seconds between SIGTERM and SIGKILL at the deadline
"""
import datetime as dt
import importlib.machinery
import importlib.util
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
HEAVY = os.path.join(os.path.dirname(HERE), "bin", "heavy")


def load(name="heavy_under_test"):
    loader = importlib.machinery.SourceFileLoader(name, HEAVY)
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def configure(heavy, cfg):
    if "work" in cfg:
        heavy.WORK = cfg["work"]
    if "status" in cfg:
        heavy.STATUS_DIR = cfg["status"]
    if "now" in cfg:
        t = dt.datetime.fromisoformat(cfg["now"])
        if t.tzinfo is None:
            t = t.replace(tzinfo=heavy.TZ)
        heavy.OFFSET = t.timestamp() - time.time()
    if "free_file" in cfg:
        def free_gb(_where, _file=cfg["free_file"]):
            with open(_file) as f:
                return float(f.read().strip())
        heavy.free_gb = free_gb
    if "grace_s" in cfg:
        heavy.GRACE_S = float(cfg["grace_s"])
    return heavy


if __name__ == "__main__":
    module = configure(load(), json.loads(os.environ["HEAVY_HARNESS"]))
    sys.exit(module.main(sys.argv[1:]))
