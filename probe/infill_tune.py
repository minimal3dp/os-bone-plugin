# /// script
# requires-python = ">=3.12"
# dependencies = []
#
# [tool.orcaslicer.plugin]
# name = "Infill Tune"
# description = "Phase 1 tuning: carves three different pore geometries on three layers in one slice to find which keeps the solid-infill raster unfragmented."
# author = "Mike Wilson"
# version = "0.1.0"
# ///
"""Raster-fragmentation tuning for architecture A''.

The first spike showed the mechanism works but fragments the 45-degree solid
raster: 56x the extrusion moves for only 2.5x the material, because every pore
boundary cuts the raster.

Three candidate fixes, one per layer, so a single slice answers all three:

  A "fewer, bigger"   - 8 mm pores at wide spacing. Fewer boundaries to cut the
                        raster, at the cost of coarser pore structure.
  B "raster-aligned"  - 45-degree slots, long axis parallel to the solid-infill
                        raster. Raster lines inside a slot band are shortened
                        along their whole length instead of being chopped, so
                        the surviving segments stay long.
  C "min-feature"     - the original 4 mm pores plus a minimum-piece-area filter
                        that deletes slivers too small to extrude cleanly.

Metrics per layer are logged at posInfill and can be cross-checked against the
exported G-code.
"""

import math
import random
import sys
import traceback

import orca

LOG = "[infill_tune]"

SCALING = 1_000_000

# Layer indices to carve. Spread through the body so they do not interact.
# Python layer index -> variant name.
CARVE_LAYERS = {40: "A_fewer_bigger", 87: "B_raster_aligned", 134: "C_min_feature"}

STRUT_MM = 1.2
LINE_WIDTH_MM = 0.38          # informational: solid raster spacing
SEED = 1234

# A: fewer, bigger round pores.
A_PORE_D_MM = 8.0
A_JITTER = 0.2

# B: slots whose long axis follows the 45-degree solid raster.
B_HALF_LEN_MM = 7.0
B_HALF_WIDTH_MM = 1.25
B_JITTER = 0.15
RASTER_ANGLE_DEG = 45.0

# C: original pores + drop pieces too small to extrude.
C_PORE_D_MM = 4.0
C_JITTER = 0.35
C_MIN_PIECE_AREA_MM2 = 0.8

HEADERS = set()
DONE = set()


def log(msg=""):
    print(f"{LOG} {msg}", file=sys.stderr, flush=True)


def names(obj):
    return sorted(n for n in dir(obj) if not n.startswith("_"))


def step_name(step):
    for n in names(orca.slicing.Step):
        try:
            if getattr(orca.slicing.Step, n) == step:
                return n
        except Exception:
            continue
    return "?"


def safe(fn, default=None):
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001
        return f"<error: {type(exc).__name__}: {exc}>"


def is_err(v):
    return isinstance(v, str) and v.startswith("<error:")


def area_mm2(scaled_area):
    return scaled_area / (SCALING * SCALING)


# --- polygon helpers ---------------------------------------------------------
def polygon_from_points(pts):
    poly = orca.host.Polygon()
    for x, y in pts:
        poly.append(orca.host.Point(int(x), int(y)))
    return poly


def circle_pts(cx, cy, r, n=16):
    return [(cx + r * math.cos(2 * math.pi * i / n),
             cy + r * math.sin(2 * math.pi * i / n)) for i in range(n)]


def slot_pts(cx, cy, half_len, half_w, angle_deg):
    """Rectangle with its long axis at `angle_deg`, centred on (cx, cy)."""
    a = math.radians(angle_deg)
    ux, uy = math.cos(a), math.sin(a)
    vx, vy = -math.sin(a), math.cos(a)
    pts = []
    for su, sv in ((1, 1), (1, -1), (-1, -1), (-1, 1)):
        pts.append((cx + su * half_len * ux + sv * half_w * vx,
                    cy + su * half_len * uy + sv * half_w * vy))
    return pts


def bbox_of(exp):
    pts = safe(lambda: exp.contour.points, [])
    if is_err(pts) or not pts:
        return None
    xs = [p.x for p in pts]
    ys = [p.y for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def corners_inside(exp, pts, pad=0):
    """True if a few probe points of the pore all fall inside `exp`."""
    for x, y in pts:
        for dx, dy in ((0, 0), (pad, 0), (-pad, 0), (0, pad), (0, -pad)):
            if not safe(lambda: exp.contains(orca.host.Point(int(x + dx), int(y + dy))), False):
                return False
    return True


# --- pore placement ----------------------------------------------------------
def round_centers(bbox, r, strut, jitter, rng):
    x0, y0, x1, y1 = bbox
    spacing = 2 * r + strut
    out = []
    y = y0 + spacing / 2
    while y < y1:
        x = x0 + spacing / 2
        while x < x1:
            out.append((x + rng.uniform(-1, 1) * jitter * spacing / 2,
                        y + rng.uniform(-1, 1) * jitter * spacing / 2))
            x += spacing
        y += spacing
    return out


def slot_centers(bbox, half_len, half_w, strut, jitter, angle_deg, rng):
    """Lattice in the slot's own rotated frame, so slots tile the region."""
    x0, y0, x1, y1 = bbox
    a = math.radians(angle_deg)
    ux, uy = math.cos(a), math.sin(a)
    vx, vy = -math.sin(a), math.cos(a)

    su = 2 * half_len + strut
    sv = 2 * half_w + strut

    # Project the bbox corners onto both axes to size the lattice.
    us = [px * ux + py * uy for px, py in ((x0, y0), (x0, y1), (x1, y0), (x1, y1))]
    vs = [px * vx + py * vy for px, py in ((x0, y0), (x0, y1), (x1, y0), (x1, y1))]
    u0, u1 = min(us), max(us)
    v0, v1 = min(vs), max(vs)

    out = []
    v = v0 + sv / 2
    while v < v1:
        u = u0 + su / 2
        while u < u1:
            ju = rng.uniform(-1, 1) * jitter * su / 2
            jv = rng.uniform(-1, 1) * jitter * sv / 2
            uu, vv = u + ju, v + jv
            out.append((uu * ux + vv * vx, uu * uy + vv * vy))
            u += su
        v += sv
    return out


def carve(exp, pore_pts, min_piece_area=None):
    """Subtract each fully-interior pore. Returns ([ExPolygon], kept_count)."""
    pieces = [exp]
    kept = 0
    for pts in pore_pts:
        if not corners_inside(exp, pts):
            continue
        hole = orca.host.ExPolygon(polygon_from_points(pts))
        nxt = []
        for piece in pieces:
            res = safe(lambda: piece.diff_ex(hole), None)
            if res is None or is_err(res):
                nxt.append(piece)
                continue
            nxt.extend(res)
        pieces = nxt
        kept += 1

    if min_piece_area is not None:
        kept_pieces = []
        for piece in pieces:
            a = safe(lambda: piece.area(), 0.0)
            if a >= min_piece_area:
                kept_pieces.append(piece)
        pieces = kept_pieces

    return pieces, kept


def build_pores(variant, exp, rng):
    """Return pore outlines as plain (x, y) point lists."""
    bb = bbox_of(exp)
    if bb is None:
        return []
    strut = STRUT_MM * SCALING

    if variant.startswith("A"):
        r = A_PORE_D_MM * SCALING / 2
        return [circle_pts(cx, cy, r)
                for cx, cy in round_centers(bb, r, strut, A_JITTER, rng)]

    if variant.startswith("B"):
        hl = B_HALF_LEN_MM * SCALING
        hw = B_HALF_WIDTH_MM * SCALING
        return [slot_pts(cx, cy, hl, hw, RASTER_ANGLE_DEG)
                for cx, cy in slot_centers(bb, hl, hw, strut, B_JITTER,
                                           RASTER_ANGLE_DEG, rng)]

    r = C_PORE_D_MM * SCALING / 2
    return [circle_pts(cx, cy, r)
            for cx, cy in round_centers(bb, r, strut, C_JITTER, rng)]


def carve_layer(layer, variant):
    regions = safe(lambda: layer.regions(), []) or []
    if is_err(regions) or not regions:
        return None
    lr = regions[0]
    surfaces = safe(lambda: lr.fill_surfaces.surfaces, []) or []
    if is_err(surfaces):
        return None

    rng = random.Random(SEED)
    min_piece = (C_MIN_PIECE_AREA_MM2 * SCALING * SCALING
                 if variant.startswith("C") else None)

    rebuilt = []
    before = 0.0
    after = 0.0
    total_kept = 0

    for s in surfaces:
        sparse = safe(lambda: s.is_internal(), False) and not safe(lambda: s.is_solid(), True)
        exp = safe(lambda: s.expolygon)
        if not sparse or exp is None or is_err(exp):
            rebuilt.append(s)
            continue
        before += safe(lambda: exp.area(), 0.0)
        pieces, kept = carve(exp, build_pores(variant, exp, rng), min_piece)
        total_kept += kept
        after += sum(safe(lambda: p.area(), 0.0) for p in pieces)
        for p in pieces:
            rebuilt.append(orca.host.Surface(orca.host.SurfaceType.stInternalSolid, p))

    if before == 0.0:
        log(f"  [{variant}] no sparse surface; skipped")
        return None

    try:
        lr.fill_surfaces.set(rebuilt)
    except Exception as exc:  # noqa: BLE001
        log(f"  [{variant}] fill_surfaces.set FAILED: {type(exc).__name__}: {exc}")
        return None

    log("  [%s] %d pores -> %d pieces; area %.1f -> %.1f mm2 (%.1f%% void)"
        % (variant, total_kept, len(rebuilt), area_mm2(before), area_mm2(after),
           100.0 * (1.0 - after / before) if before else 0.0))
    return lr


def layer_stats(lr):
    surfaces = safe(lambda: lr.fill_surfaces.surfaces, []) or []
    if is_err(surfaces):
        surfaces = []
    n_surf = len(surfaces)
    area = sum(safe(lambda: s.area(), 0.0) for s in surfaces)
    paths = safe(lambda: lr.fills.flatten_paths(), []) or []
    if is_err(paths):
        paths = []
    return n_surf, area_mm2(area), len(paths)


class InfillTune(orca.slicing.SlicingPipelineCapabilityBase):
    def get_name(self):
        return "Infill Tune"

    def execute(self, ctx):
        try:
            self._run(ctx)
        except Exception:  # noqa: BLE001
            log("EXCEPTION:\n" + traceback.format_exc())
        return orca.ExecutionResult.success()

    def _run(self, ctx):
        name = step_name(ctx.step)
        if name not in ("posPrepareInfill", "posInfill"):
            return
        if name not in HEADERS:
            HEADERS.add(name)
            log(f"===== {name} =====")
        if ctx.object is None:
            return

        layers = safe(lambda: ctx.object.layers(), []) or []
        if not layers or is_err(layers):
            return

        if name == "posPrepareInfill":
            if "done" in DONE:
                return
            log(f"carving {len(CARVE_LAYERS)} layers: "
                + ", ".join(f"{i}={v}" for i, v in sorted(CARVE_LAYERS.items())))
            ok = 0
            for idx, variant in sorted(CARVE_LAYERS.items()):
                if idx >= len(layers):
                    log(f"  layer {idx} out of range ({len(layers)} layers)")
                    continue
                if carve_layer(layers[idx], variant) is not None:
                    ok += 1
            DONE.add("done")
            log(f"carved {ok}/{len(CARVE_LAYERS)} layers")

        elif name == "posInfill":
            if "done" not in DONE:
                log("VERDICT: skipped, nothing carved")
                return
            log("VERDICT: per-layer comparison")
            log("  layer  variant             surfaces   area_mm2   paths")
            for idx, variant in sorted(CARVE_LAYERS.items()):
                if idx >= len(layers):
                    continue
                regions = safe(lambda: layers[idx].regions(), []) or []
                if is_err(regions) or not regions:
                    continue
                n_surf, area, paths = layer_stats(regions[0])
                log("  %5d  %-18s  %8d  %9.1f  %6d" % (idx, variant, n_surf, area, paths))
            # A sparse baseline layer for comparison (first non-carved layer with fills).
            for j, layer in enumerate(layers):
                if j in CARVE_LAYERS:
                    continue
                regions = safe(lambda: layer.regions(), []) or []
                if is_err(regions) or not regions:
                    continue
                n_surf, area, paths = layer_stats(regions[0])
                if paths:
                    log("  %5d  %-18s  %8d  %9.1f  %6d"
                        % (j, "baseline_sparse", n_surf, area, paths))
                    break
            log("Compare move counts and travel in the exported G-code; "
                "the variant with the fewest moves per mm2 of strut is the winner.")


@orca.plugin
class InfillTunePlugin(orca.base):
    def register_capabilities(self):
        orca.register_capability(InfillTune)
