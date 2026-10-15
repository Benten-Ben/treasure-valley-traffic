"""Runs deploy/bin/cold-videos as a program for the tests, with heavy's folders, clock and free
disk taken from the JSON in HEAVY_HARNESS (heavy_harness.py's keys). cold-videos itself reads none
of this: the installed tool has no test hooks.

    HEAVY_HARNESS='{"work": "/tmp/w", "status": "/tmp/a/cameras/status", "now": "2026-10-16 02:30",
                    "free_file": "/tmp/free"}' python3 cold_harness.py <cold-videos args>
"""
import importlib.machinery
import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import heavy_harness  # noqa: E402

COLD_VIDEOS = os.path.join(os.path.dirname(HERE), "bin", "cold-videos")


def load(name="cold_videos_under_test"):
    loader = importlib.machinery.SourceFileLoader(name, COLD_VIDEOS)
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


if __name__ == "__main__":
    module = load()
    heavy_harness.configure(module.heavy, json.loads(os.environ["HEAVY_HARNESS"]))
    sys.exit(module.main(sys.argv[1:]))
