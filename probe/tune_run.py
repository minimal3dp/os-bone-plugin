# /// script
# requires-python = ">=3.12"
# dependencies = []
#
# [tool.orcaslicer.plugin]
# name = "Tune Run"
# description = "Phase 3 tuning: carves three parameter variants on three layers in one slice to find which reduces raster fragmentation."
# author = "Mike Wilson"
# version = "0.1.0"
# ///
"""Fragmentation tuning for the trabecular infill.

Baseline measurement (tests/Cube_PLA_1h17m.gcode): strut 1.2 mm,
VOID_LENGTH_RATIO 5.5, 133,917 extrusion moves, median segment 0.50 mm
- exactly the raster line spacing, i.e. half the extrusions are connectors
between parallel raster lines.

Three variants, one per layer, to isolate which parameter matters:

  A "fat_struts"   strut 2.4 mm  - fewer, wider raster bands
  B "long_voids"   length ratio 14 - voids span more of the layer
  C "coarse"       strut 2.4 mm + length ratio 10 - both

Metrics are logged at posInfill and cross-checked in the exported G-code.
"""

import math
import random
import sys
import traceback

import orca

LOG = "[tune_run]"
SCALING = 1_000_000.0

# layer index -> (label, strut_mm, void_half_len_mm, void_half_w_mm)
# Void size is ABSOLUTE. Strut thickness sets only the gap between voids.
# Reference (works): strut 1.2, void 6.0 x 0.6 half-extents.
VARIANTS = {
    40: ("A_thick_strut", 2.4, 6.0, 0.6),    # wider struts, same voids
    87: ("B_long_void", 1.2, 8.5, 0.6),      # longer voids, same struts
    134: ("C_both", 2.4, 8.5, 0.7),          # both
}
JITTER = 0.15
SEED = 1234

_done = set()


def log(msg=""):
    print(f"{LOG} {msg}", file=sys.stderr, flush=True)


def safe(fn, default=None):
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001
        return default if default is not None else f"<err {type(exc).__name__}>"


def polygon_from(pts):
    poly = orca.host.Polygon()
    for x, y in pts:
        poly.append(orca.host.Point(int(x), int(y)))
    return poly


def ribbon_pts(cx, cy, hl, hw, angle):
    a = math.radians(angle)
    ux, uy = math.cos(a), math.sin(a)
    vx, vy = -math.sin(a), math.cos(a)
    return [(cx + su * hl * ux + sv * hw * vx, cy + su * hl * uy + sv * hw * vy)
            for su, sv in ((1, 1), (1, -1), (-1, -1), (-1, 1))]


def bbox_of(exp):
    pts = safe(lambda: exp.contour.points, [])
    if not pts or isinstance(pts, str):
        return None
    xs = [p.x for p in pts]
    ys = [p.y for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def intersects(exp, pts):
    probe = orca.host.ExPolygon(polygon_from(pts))
    res = safe(lambda: exp.intersection_ex(probe), None)
    if res is None or isinstance(res, str):
        return False
    return len(res) > 0


def centers(bbox, hl, hw, gap, angle, rng):
    x0, y0, x1, y1 = bbox
    a = math.radians(angle)
    ux, uy = math.cos(a), math.sin(a)
    vx, vy = -math.sin(a), math.cos(a)
    su, sv = 2 * hl + gap, 2 * hw + gap
    if su <= 0 or sv <= 0:
        return []
    corners = ((x0, y0), (x0, y1), (x1, y0), (x1, y1))
    us = [px * ux + py * uy for px, py in corners]
    vs = [px * vx + py * vy for px, py in corners]
    out = []
    v = min(vs) + sv / 2
    while v < max(vs):
        u = min(us) + su / 2
        while u < max(us):
            jx = rng.uniform(-1, 1) * JITTER * su / 2
            jy = rng.uniform(-1, 1) * JITTER * sv / 2
            out.append(((u + jx) * ux + (v + jy) * vx,
                        (u + jx) * uy + (v + jy) * vy))
            u += su
        v += sv
    return out


def carve(exp, hl, hw, gap, angle, rng):
    bb = bbox_of(exp)
    if bb is None:
        return [exp]
    pieces = [exp]
    for cx, cy in centers(bb, hl, hw, gap, angle, rng):
        pts = ribbon_pts(cx, cy, hl, hw, angle)
        if not intersects(exp, pts):
            continue
        hole = orca.host.ExPolygon(polygon_from(pts))
        nxt = []
        for piece in pieces:
            res = safe(lambda: piece.diff_ex(hole), None)
            if res is None or isinstance(res, str):
                nxt.append(piece)
            else:
                nxt.extend(res)
        pieces = nxt
    return pieces


def direction(ctx, index):
    """Solid-infill direction for this layer, with the rotate template applied."""
    value = safe(lambda: ctx.config_value("solid_infill_direction"), None)
    try:
        base = float(str(value).strip().rstrip("%"))
    except (TypeError, ValueError):
        base = 45.0

    tmpl = safe(lambda: ctx.config_value("solid_infill_rotate_template"), "")
    if isinstance(tmpl, str) and tmpl.strip():
        angles = []
        for part in tmpl.split(","):
            try:
                angles.append(float(part.strip()))
            except ValueError:
                pass
        if angles:
            base += angles[index % len(angles)]
    return base


class TuneRun(orca.slicing.SlicingPipelineCapabilityBase):
    def get_name(self):
        return "Tune Run"

    def execute(self, ctx):
        try:
            self._run(ctx)
        except Exception:  # noqa: BLE001
            log("EXCEPTION:\n" + traceback.format_exc())
        return orca.ExecutionResult.success()

    def _run(self, ctx):
        if ctx.step != orca.slicing.Step.posPrepareInfill or ctx.object is None:
            return
        if "done" in _done:
            return
        _done.add("done")

        layers = safe(lambda: ctx.object.layers(), [])
        if not isinstance(layers, list):
            log(f"no layers: {layers}")
            return

        for index, (label, strut, half_len, half_w) in sorted(VARIANTS.items()):
            if index >= len(layers):
                log(f"{label}: layer {index} out of range")
                continue
            hl = half_len * SCALING
            hw = half_w * SCALING
            gap = strut * SCALING
            self._carve(layers[index], index, label, hl, hw, gap, ctx, strut, half_len)

    def _carve(self, layer, index, label, hl, hw, gap, ctx, strut, len_ratio):
        regions = safe(lambda: layer.regions(), [])
        if not isinstance(regions, list) or not regions:
            return
        lr = regions[0]
        surfaces = safe(lambda: lr.fill_surfaces.surfaces, [])
        if not isinstance(surfaces, list):
            return

        rng = random.Random(SEED + index)
        rebuilt, before, after = [], 0.0, 0.0
        for s in surfaces:
            sparse = (safe(lambda: s.is_internal(), False)
                      and not safe(lambda: s.is_solid(), True))
            exp = safe(lambda: s.expolygon)
            if not sparse or exp is None or isinstance(exp, str):
                rebuilt.append(s)
                continue
            before += safe(lambda: exp.area(), 0.0)
            pieces = carve(exp, hl, hw, gap, direction(ctx, index), rng)
            after += sum(safe(lambda: p.area(), 0.0) for p in pieces)
            for p in pieces:
                rebuilt.append(orca.host.Surface(orca.host.SurfaceType.stInternalSolid, p))

        if before == 0.0:
            log(f"{label}: no sparse surface on layer {index}")
            return
        try:
            lr.fill_surfaces.set(rebuilt)
        except Exception as exc:  # noqa: BLE001
            log(f"{label}: set failed {type(exc).__name__}: {exc}")
            return
        mm2 = (1.0 / SCALING) ** 2
        void_pct = 100.0 * (1.0 - after / before)
        log("%s layer %d: %.1f -> %.1f mm2 (%.0f%% void) strut=%.1f void_half_len=%.1f"
            % (label, index, before * mm2, after * mm2, void_pct, strut, hl / SCALING))
        if void_pct < 1.0:
            log("%s: WARNING almost nothing was carved - parameter combination is degenerate" % label)


@orca.plugin
class TuneRunPlugin(orca.base):
    def register_capabilities(self):
        orca.register_capability(TuneRun)
