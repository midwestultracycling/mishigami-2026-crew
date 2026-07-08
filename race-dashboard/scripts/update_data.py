#!/usr/bin/env python3
"""
Merge a freshly-fetched FMC payload into the race dashboard's persisted data files.

Usage:
    python3 update_data.py <live|test> <data_dir>   < payload.json

Writes (in <data_dir>):
    latest[-test].json   — the full raw FMC payload, as-is (for the "right now" table)
    history[-test].json  — a slim, append-only array of {t, riders:{id:{distance,name,startNumber}}}
                            used to compute overnight deltas. Full 5-min resolution for the last
                            48h; thinned to ~1 sample/hour beyond that so the file doesn't grow
                            unbounded over a multi-day race.
"""
import json
import sys
import time
import os

FULL_RES_WINDOW_SEC = 48 * 3600
HOUR_SEC = 3600


def slim_riders(payload):
    riders = payload.get("riders") or []
    out = {}
    for r in riders:
        rid = r.get("id")
        if rid is None:
            continue
        out[str(rid)] = {
            "distance": r.get("distance"),
            "name": r.get("name"),
            "startNumber": r.get("startNumber"),
        }
    return out


def thin_history(history):
    now = time.time()
    cutoff = now - FULL_RES_WINDOW_SEC

    recent = [h for h in history if h["t"] >= cutoff]
    older = sorted([h for h in history if h["t"] < cutoff], key=lambda h: h["t"])

    thinned = []
    seen_hours = set()
    for h in older:
        bucket = int(h["t"] // HOUR_SEC)
        if bucket not in seen_hours:
            seen_hours.add(bucket)
            thinned.append(h)

    recent.sort(key=lambda h: h["t"])
    return thinned + recent


def main():
    if len(sys.argv) != 3 or sys.argv[1] not in ("live", "test"):
        print("Usage: update_data.py <live|test> <data_dir>", file=sys.stderr)
        sys.exit(2)

    which = sys.argv[1]
    data_dir = sys.argv[2]
    suffix = "" if which == "live" else "-test"

    raw = sys.stdin.read()
    payload = json.loads(raw)

    os.makedirs(data_dir, exist_ok=True)
    latest_path = os.path.join(data_dir, "latest%s.json" % suffix)
    history_path = os.path.join(data_dir, "history%s.json" % suffix)

    # 1. write the full "right now" snapshot
    with open(latest_path, "w") as f:
        json.dump(payload, f, separators=(",", ":"))

    # 2. append a slim entry to history and thin/prune
    history = []
    if os.path.exists(history_path):
        try:
            with open(history_path) as f:
                history = json.load(f)
        except (ValueError, OSError):
            history = []

    history.append({"t": time.time(), "riders": slim_riders(payload)})
    history = thin_history(history)

    with open(history_path, "w") as f:
        json.dump(history, f, separators=(",", ":"))

    print("OK which=%s riders=%d history_entries=%d" % (
        which, len(payload.get("riders") or []), len(history)
    ))


if __name__ == "__main__":
    main()
