#!/usr/bin/env python3
"""Per-layer print-cost metrics from an exported OrcaSlicer G-code file.

Standalone: reads the file given as an argument, no plugin dependency.
Run with -I so a planted module in the working directory cannot be imported:

    python3 -I tools/gcode_metrics.py tests/file.gcode [--layer N] [--json]
"""

import argparse
import json
import math
import re
import sys

LAYER_CHANGE = re.compile(r"^;LAYER_CHANGE")
TYPE_LINE = re.compile(r"^;TYPE:(.*)$")
MOVE = re.compile(r"^G1 X(-?[0-9.]+) Y(-?[0-9.]+)")
EXTRUDE = re.compile(r"\bE(-?[0-9.]+)")
TRAVEL_FEED = re.compile(r"F21000")


def parse(path):
    layers = []
    current = None
    pos = (0.0, 0.0)

    def flush():
        if current is not None:
            layers.append(current)

    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            line = line.rstrip("\n")
            if LAYER_CHANGE.match(line):
                flush()
                current = {
                    "layer": len(layers),
                    "type": "",
                    "extrude_moves": 0,
                    "extrude_len": 0.0,
                    "travel_moves": 0,
                    "travel_len": 0.0,
                    "segments": [],
                }
                continue
            if current is None:
                continue
            match = TYPE_LINE.match(line)
            if match:
                current["type"] = match.group(1).strip()
                continue
            match = MOVE.match(line)
            if not match:
                continue
            x, y = float(match.group(1)), float(match.group(2))
            distance = math.hypot(x - pos[0], y - pos[1])
            if EXTRUDE.search(line):
                current["extrude_moves"] += 1
                current["extrude_len"] += distance
                if distance > 0:
                    current["segments"].append(distance)
            elif TRAVEL_FEED.search(line):
                current["travel_moves"] += 1
                current["travel_len"] += distance
            pos = (x, y)
    flush()
    return layers


def median(values):
    if not values:
        return 0.0
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2.0


def summarise(layers, only=None):
    rows = []
    for layer in layers:
        if only is not None and layer["layer"] != only:
            continue
        segs = layer["segments"]
        total = layer["extrude_len"] + layer["travel_len"]
        rows.append({
            "layer": layer["layer"],
            "type": layer["type"],
            "extrude_moves": layer["extrude_moves"],
            "extrude_len_mm": round(layer["extrude_len"], 2),
            "mean_segment_mm": round(sum(segs) / len(segs), 3) if segs else 0.0,
            "median_segment_mm": round(median(segs), 3),
            "travel_moves": layer["travel_moves"],
            "travel_len_mm": round(layer["travel_len"], 2),
            "travel_share_pct": round(100.0 * layer["travel_len"] / total, 2) if total else 0.0,
        })
    return rows


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("gcode", help="path to the exported .gcode file")
    parser.add_argument("--layer", type=int, default=None, help="report only this layer index")
    parser.add_argument("--json", action="store_true", help="emit JSON instead of a table")
    args = parser.parse_args(argv)

    layers = parse(args.gcode)
    rows = summarise(layers, args.layer)

    if not rows:
        print("no extrusion data")
        return 0

    if args.json:
        print(json.dumps(rows, indent=2))
        return 0

    header = ("layer", "type", "moves", "ext_mm", "mean_seg", "med_seg",
              "trav_n", "trav_mm", "trav_%")
    print("%6s %-22s %6s %9s %9s %8s %7s %8s %7s" % header)
    for row in rows:
        print("%6d %-22s %6d %9.1f %9.2f %8.2f %7d %8.1f %7.1f" % (
            row["layer"], row["type"][:22], row["extrude_moves"],
            row["extrude_len_mm"], row["mean_segment_mm"], row["median_segment_mm"],
            row["travel_moves"], row["travel_len_mm"], row["travel_share_pct"],
        ))
    return 0


def _self_check():
    sample = """\
;LAYER_CHANGE
;Z:0.2
;TYPE:Outer wall
G1 X0 Y0 F21000
G1 X10 Y0 E1.0
G1 X10 Y10 E1.0
G1 X20 Y10 F21000
;TYPE:Sparse infill
G1 X30 Y10 E0.5
;LAYER_CHANGE
;TYPE:Internal solid infill
G1 X40 Y10 E2.0
"""
    import tempfile
    import os
    handle, path = tempfile.mkstemp(suffix=".gcode")
    try:
        with os.fdopen(handle, "w") as fh:
            fh.write(sample)
        layers = parse(path)
        assert len(layers) == 2, layers
        assert layers[0]["extrude_moves"] == 3, layers[0]
        # Two travel-flagged lines: the initial X0 Y0 move (zero length) and X20 Y10.
        assert layers[0]["travel_moves"] == 2, layers[0]
        assert layers[0]["type"] == "Sparse infill", layers[0]
        assert layers[1]["type"] == "Internal solid infill", layers[1]
        rows = summarise(layers)
        assert rows[0]["travel_share_pct"] > 0
        print("self-check OK")
    finally:
        os.unlink(path)


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "--self-check":
        _self_check()
    else:
        sys.exit(main(sys.argv[1:]))
