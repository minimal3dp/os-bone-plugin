# /// script
# requires-python = ">=3.12"
# dependencies = []
#
# [tool.orcaslicer.plugin]
# name = "Trabecular Infill"
# description = "Carves a seeded field of ribbon voids out of each layer's sparse fill region and retypes the remaining strut network as solid infill, producing a trabecular (bone-like) interior."
# author = "Mike Wilson"
# version = "0.1.0"
# ///
"""Trabecular infill for OrcaSlicer.

At posPrepareInfill the plugin takes every sparse (stInternal, non-solid) fill
surface, subtracts a lattice of ribbon voids whose long axis follows the
profile's solid-infill direction, and replaces the surface list with the
remaining strut pieces retyped stInternalSolid. The slicer's own solid infill
then draws the struts densely.

The plugin controls where material exists, not which strokes are drawn. That is
a hard limit of the plugin API: LayerRegion.fills has no mutator.
"""

import json
import math
import random
import sys
import traceback

import orca

LOG = "[bone_infill]"

# --- Internal constants (not user-facing; see data-model.md) ----------------
# Void size is ABSOLUTE, decoupled from strut thickness. Strut thickness sets the
# gap between voids (and therefore density); it must not also scale the void,
# or raising strut thickness silently raises void size and voids stop fitting.
VOID_LENGTH_MM = 8.5      # half-length of each ribbon void, millimetres
VOID_WIDTH_MM = 0.6       # half-width of each ribbon void, millimetres
LATTICE_JITTER = 0.15     # fraction of lattice spacing a centre may deviate
SEED = 1234
DEFAULT_DIRECTION_DEG = 45.0
DEFAULT_STRUT_MM = 1.2

SCALES = (1_000_000.0, 100_000.0)  # normal, and beds > 2147 mm

_logged_fallback = False


def log(msg=""):
    print(f"{LOG} {msg}", file=sys.stderr, flush=True)


def safe(fn, default=None):
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001 - probe-style accessor, never fatal
        return default if default is not None else f"<error: {type(exc).__name__}: {exc}>"


def is_err(v):
    return isinstance(v, str) and v.startswith("<error:")


def scaled_per_mm(ctx):
    """Scaled units per millimetre, read from the live scaling factor."""
    try:
        return 1.0 / orca.slicing.unscale(1)
    except Exception:  # noqa: BLE001
        pass
    for s in SCALES:
        try:
            if abs(orca.slicing.unscale(int(s)) - 1.0) < 1e-6:
                return s
        except Exception:  # noqa: BLE001
            continue
    return SCALES[0]


def parse_float(value, default=None):
    """Config values arrive serialized, e.g. '45' or '125%'."""
    if value is None or is_err(value):
        return default
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().rstrip("%").strip()
    try:
        return float(text)
    except ValueError:
        return default


def parse_mm(value, ratio_base, default=None):
    """Resolve a FloatOrPercent config value to millimetres.

    OrcaSlicer serializes these as either '0.5' or '125%'. A percentage is
    computed over the setting's own `ratio_over` reference, which for line
    widths is the nozzle diameter - NOT the base line width.
    """
    if value is None or is_err(value):
        return default
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if text.endswith("%"):
        pct = parse_float(text, None)
        if pct is None or ratio_base is None:
            return default
        return ratio_base * pct / 100.0
    return parse_float(text, default)


def nozzle_width_mm(ctx):
    """Nozzle diameter in millimetres, per profile.

    `nozzle_diameter` is a per-filament array (ConfigOptionFloats), so it
    serializes as e.g. '0.4' or '0.4,0.4'. Every width percentage in the profile
    resolves against this, which is why they stay correct when the user swaps
    nozzles. Read it live; never cache it across slices.

    A multi-extruder profile yields the smallest nozzle - the most conservative
    bound for "is this strut printable on every nozzle that will draw it".
    Returns None when it cannot be resolved.
    """
    raw = safe(lambda: ctx.config_value("nozzle_diameter"), None)
    if raw is None or is_err(raw):
        return None

    values = raw if isinstance(raw, (list, tuple)) else str(raw).split(",")
    nozzles = [v for v in (parse_float(x, None) for x in values) if v and v > 0]
    return min(nozzles) if nozzles else None


def solid_raster_width_mm(ctx):
    """Width of the raster that will draw our struts, in millimetres.

    The struts are retyped stInternalSolid, so the internal-solid raster draws
    them. `internal_solid_infill_line_width` is a FloatOrPercent whose ratio is
    the nozzle diameter. A value of 0 means "unset", in which case the global
    `line_width` applies; that is also a percentage over the nozzle.

    Both are resolved against the live nozzle width, so a user who changes
    nozzle keeps the same relative setting.

    Returns None when no nozzle diameter can be resolved, which the caller
    treats as "cannot determine the printable minimum".
    """
    nozzle = nozzle_width_mm(ctx)
    if nozzle is None:
        return None

    for key in ("internal_solid_infill_line_width", "line_width"):
        width = parse_mm(safe(lambda: ctx.config_value(key)), nozzle, None)
        if width is not None and width > 0:
            return width

    return nozzle



def polygon_from(pts):
    poly = orca.host.Polygon()
    for x, y in pts:
        poly.append(orca.host.Point(int(x), int(y)))
    return poly


def ribbon_pts(cx, cy, half_len, half_w, angle_deg):
    """Rectangle with its long axis at angle_deg, centred on (cx, cy)."""
    a = math.radians(angle_deg)
    ux, uy = math.cos(a), math.sin(a)
    vx, vy = -math.sin(a), math.cos(a)
    return [
        (cx + su * half_len * ux + sv * half_w * vx,
         cy + su * half_len * uy + sv * half_w * vy)
        for su, sv in ((1, 1), (1, -1), (-1, -1), (-1, 1))
    ]


def bbox_of(exp):
    pts = safe(lambda: exp.contour.points, [])
    if not pts or is_err(pts):
        return None
    xs = [p.x for p in pts]
    ys = [p.y for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def lattice_centers(bbox, half_len, half_w, gap, angle_deg, rng):
    """Void centres on a lattice rotated into the void's own frame."""
    x0, y0, x1, y1 = bbox
    a = math.radians(angle_deg)
    ux, uy = math.cos(a), math.sin(a)
    vx, vy = -math.sin(a), math.cos(a)

    step_u = 2 * half_len + gap
    step_v = 2 * half_w + gap
    if step_u <= 0 or step_v <= 0:
        return []

    corners = ((x0, y0), (x0, y1), (x1, y0), (x1, y1))
    us = [px * ux + py * uy for px, py in corners]
    vs = [px * vx + py * vy for px, py in corners]
    u0, u1, v0, v1 = min(us), max(us), min(vs), max(vs)

    out = []
    v = v0 + step_v / 2
    while v < v1:
        u = u0 + step_u / 2
        while u < u1:
            ju = rng.uniform(-1, 1) * LATTICE_JITTER * step_u / 2
            jv = rng.uniform(-1, 1) * LATTICE_JITTER * step_v / 2
            uu, vv = u + ju, v + jv
            out.append((uu * ux + vv * vx, uu * uy + vv * vy))
            u += step_u
        v += step_v
    return out


def intersects(exp, pts):
    """True when the void outline overlaps `exp` at all.

    A void that merely touches the edge is still worth cutting: dropping it
    leaves an unbroken solid band along every boundary, which is what made the
    first version carve only the 9 voids nearest the centre.
    """
    probe = orca.host.ExPolygon(polygon_from(pts))
    res = safe(lambda: exp.intersection_ex(probe), None)
    if res is None or is_err(res):
        return False
    return len(res) > 0


def carve(exp, half_len, half_w, gap, angle_deg, rng):
    """Subtract every void that overlaps the region. Returns a list of ExPolygon.

    Partial voids ARE cut. `diff_ex` clips them to the region, so the half that
    lands outside simply disappears - which is what keeps the structure uniform
    right up to the boundary.
    """
    bb = bbox_of(exp)
    if bb is None:
        return [exp]

    pieces = [exp]
    kept = 0
    for cx, cy in lattice_centers(bb, half_len, half_w, gap, angle_deg, rng):
        pts = ribbon_pts(cx, cy, half_len, half_w, angle_deg)
        if not intersects(exp, pts):
            continue
        hole = orca.host.ExPolygon(polygon_from(pts))
        nxt = []
        for piece in pieces:
            res = safe(lambda: piece.diff_ex(hole), None)
            if res is None or is_err(res):
                nxt.append(piece)
                continue
            nxt.extend(res)
        pieces = nxt
        kept += 1
    if kept == 0:
        log("    no void overlapped the region; lattice spacing likely too coarse")
    return pieces


def _region_config_value(ctx, key):
    """Config value from the first layer's first region, or None."""
    layers = safe(lambda: ctx.object.layers(), [])
    if not isinstance(layers, list) or not layers:
        return None
    regions = safe(lambda: layers[0].regions(), [])
    if not isinstance(regions, list) or not regions:
        return None
    return regions[0].config_value(key)


def resolve_direction(ctx, layer_index):
    """Solid-infill direction for this layer, plus any rotation template."""
    global _logged_fallback

    value = None
    for getter in (
        # Verified by the T004 probe (2026-11-01): ctx and LayerRegion both
        # return '45'; ctx.object returns None. Try the working ones in order.
        lambda: ctx.config_value("solid_infill_direction"),
        lambda: _region_config_value(ctx, "solid_infill_direction"),
    ):
        value = safe(getter, None)
        if value is not None and not is_err(value):
            break
    direction = parse_float(value, None)

    if direction is None:
        if not _logged_fallback:
            _logged_fallback = True
            log(f"no usable solid_infill_direction; falling back to {DEFAULT_DIRECTION_DEG}")
        direction = DEFAULT_DIRECTION_DEG

    template = safe(lambda: ctx.config_value("solid_infill_rotate_template"), None)
    if template and not is_err(template):
        angles = [parse_float(p, None) for p in str(template).split(",")]
        angles = [a for a in angles if a is not None]
        if angles:
            direction += angles[layer_index % len(angles)]

    return direction


class BoneInfill(orca.slicing.SlicingPipelineCapabilityBase):
    def get_name(self):
        return "Trabecular Infill"

    def get_default_config(self):
        """Starting config written by the Config tab's "Restore defaults"."""
        return {"strut_thickness_mm": DEFAULT_STRUT_MM}

    def _config(self):
        """Stored plugin config, with per-key defaults applied on read.

        get_config() returns a JSON string ("{}" when never saved), so the
        parsed result is always indexable. Plugin config lives here, not in the
        print profile - ctx.config_value() reads print settings, which this is
        not.
        """
        raw = None
        try:
            raw = getattr(self, "get_config", lambda: "")()
        except Exception as exc:  # noqa: BLE001
            log(f"get_config failed ({type(exc).__name__}: {exc}); using defaults")
        try:
            stored = json.loads(raw) if raw else {}
        except (TypeError, ValueError):
            log(f"stored config is not valid JSON ({raw!r}); using defaults")
            stored = {}
        if not isinstance(stored, dict):
            stored = {}
        merged = {"strut_thickness_mm": DEFAULT_STRUT_MM}
        merged.update({k: v for k, v in stored.items() if k in merged})
        return merged

    def execute(self, ctx):
        try:
            return self._run(ctx)
        except Exception:  # noqa: BLE001 - never let a raise escape
            log("EXCEPTION:\n" + traceback.format_exc())
            return orca.ExecutionResult.failure(
                orca.FatalError,
                "Trabecular Infill failed; see the Python log for the traceback.",
            )

    def _run(self, ctx):
        if ctx.step != orca.slicing.Step.posPrepareInfill:
            return orca.ExecutionResult.success()
        if ctx.object is None:
            return orca.ExecutionResult.success()

        thickness_mm = self._strut_thickness()
        if thickness_mm is None:
            return orca.ExecutionResult.failure(
                orca.FatalError, "Trabecular Infill: strut_thickness_mm is missing."
            )
        if thickness_mm <= 0:
            return orca.ExecutionResult.failure(
                orca.FatalError,
                f"Trabecular Infill: strut thickness {thickness_mm:g} mm must be greater than zero.",
            )

        raster_mm = solid_raster_width_mm(ctx)
        if raster_mm is not None and thickness_mm < 2 * raster_mm:
            return orca.ExecutionResult.failure(
                orca.FatalError,
                "Trabecular Infill: strut thickness %.2f mm is below the printable minimum "
                "of %.2f mm (2 x %.2f mm internal-solid line width)."
                % (thickness_mm, 2 * raster_mm, raster_mm),
            )

        scale = scaled_per_mm(ctx)
        # Void size is absolute; only the gap between voids scales with strut.
        half_len = VOID_LENGTH_MM * scale
        half_w = VOID_WIDTH_MM * scale
        gap = thickness_mm * scale

        layers = safe(lambda: ctx.object.layers(), [])
        if not layers or is_err(layers):
            return orca.ExecutionResult.success()

        carved_layers = 0
        for index, layer in enumerate(layers):
            regions = safe(lambda: layer.regions(), [])
            if not regions or is_err(regions):
                continue
            if self._carve_layer(ctx, layer, index, half_len, half_w, gap, scale):
                carved_layers += 1

        log(f"carved {carved_layers}/{len(layers)} layers")
        return orca.ExecutionResult.success()

    def _strut_thickness(self):
        return parse_float(self._config().get("strut_thickness_mm"), None)

    def _carve_layer(self, ctx, layer, index, half_len, half_w, gap, scale):
        regions = safe(lambda: layer.regions(), [])
        if not regions or is_err(regions):
            return False

        changed = False
        for lr in regions:
            surfaces = safe(lambda: lr.fill_surfaces.surfaces, [])
            if not surfaces or is_err(surfaces):
                continue

            rng = random.Random(SEED + index)
            rebuilt = []
            before = 0.0
            after = 0.0

            for s in surfaces:
                sparse = (safe(lambda: s.is_internal(), False)
                          and not safe(lambda: s.is_solid(), True))
                exp = safe(lambda: s.expolygon)
                if not sparse or exp is None or is_err(exp):
                    rebuilt.append(s)
                    continue

                before += safe(lambda: exp.area(), 0.0)
                angle = resolve_direction(ctx, index)
                pieces = carve(exp, half_len, half_w, gap, angle, rng)
                if not pieces:
                    log(f"layer {index}: carve produced nothing; leaving surfaces untouched")
                    return False

                after += sum(safe(lambda: p.area(), 0.0) for p in pieces)
                for p in pieces:
                    rebuilt.append(
                        orca.host.Surface(orca.host.SurfaceType.stInternalSolid, p)
                    )

            if before == 0.0:
                continue

            try:
                lr.fill_surfaces.set(rebuilt)
            except Exception as exc:  # noqa: BLE001
                log(f"layer {index}: fill_surfaces.set failed: {type(exc).__name__}: {exc}")
                return False
            changed = True

            if before:
                mm2 = (1.0 / scale) ** 2
                log("layer %d: %.1f -> %.1f mm2 (%.0f%% void) at %.0f deg"
                    % (index, before * mm2, after * mm2,
                       100.0 * (1.0 - after / before), resolve_direction(ctx, index)))

        return changed


@orca.plugin
class BoneInfillPlugin(orca.base):
    def register_capabilities(self):
        orca.register_capability(BoneInfill)
