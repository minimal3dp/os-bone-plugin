# /// script
# requires-python = ">=3.12"
# dependencies = []
#
# [tool.orcaslicer.plugin]
# name = "Infill Spike"
# description = "Phase 1 spike: carve seeded pores out of one layer's sparse fill region and retype the remainder to stInternalSolid, testing whether a plugin can produce a trabecular strut network from OrcaSlicer's own infill generator."
# author = "Mike Wilson"
# version = "0.1.0"
# ///
"""Architecture A'' spike — carve voids, retype to solid.

Hypothesis under test: a plugin can turn the built-in infill generator into a
trabecular strut printer by

  1. taking the sparse (stInternal, non-solid) fill surface of a layer,
  2. subtracting a seeded field of circular pores, leaving a strut network,
  3. replacing fill_surfaces with the struts retyped stInternalSolid.

If the preview then shows dense solid infill tracing the struts, the
architecture is viable and the density knob is strut thickness.

Only ONE layer is carved (auto-picked near the middle) so the result is
obvious in the preview and the slice stays fast. Everything else is untouched.
"""

import math
import random
import sys
import traceback

import orca

LOG = "[infill_spike]"

# --- Spike parameters (millimetres; converted to scaled units internally) ---
STRUT_WIDTH_MM = 1.2      # trabecula thickness -> becomes dense solid infill
PORE_DIAMETER_MM = 4.0    # void size
PORE_JITTER = 0.35        # 0 = regular grid, 1 = heavily randomised (fraction of spacing)
SEED = 1234
PORE_SIDES = 16           # circle approximation used for each pore

SCALING = 1_000_000       # OrcaSlicer normal build: 1 mm == 1e6 scaled units

STRUT_W = int(STRUT_WIDTH_MM * SCALING)
PORE_R = int(PORE_DIAMETER_MM * SCALING / 2)

HEADERS = set()
CARVED = set()


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


def mm2(scaled_area):
    return scaled_area / (SCALING * SCALING)


# --- geometry helpers --------------------------------------------------------
def circle_poly(cx, cy, r, n=PORE_SIDES):
    poly = orca.host.Polygon()
    for i in range(n):
        a = 2.0 * math.pi * i / n
        poly.append(orca.host.Point(int(cx + r * math.cos(a)),
                                    int(cy + r * math.sin(a))))
    return poly


def bbox_of(exp):
    pts = safe(lambda: exp.contour.points, [])
    if is_err(pts) or not pts:
        return None
    xs = [p.x for p in pts]
    ys = [p.y for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def pore_centers(bbox, rng):
    """Jittered grid of pore centres covering the bbox."""
    x0, y0, x1, y1 = bbox
    spacing = 2 * PORE_R + STRUT_W
    if spacing <= 0:
        return []
    out = []
    y = y0 + PORE_R + STRUT_W // 2
    while y < y1:
        x = x0 + PORE_R + STRUT_W // 2
        while x < x1:
            jx = rng.uniform(-1, 1) * PORE_JITTER * spacing / 2
            jy = rng.uniform(-1, 1) * PORE_JITTER * spacing / 2
            out.append((int(x + jx), int(y + jy)))
            x += spacing
        y += spacing
    return out


def carve(exp, rng):
    """Subtract every fully-interior pore from `exp`. Returns [ExPolygon]."""
    bb = bbox_of(exp)
    if bb is None:
        return [exp]
    pieces = [exp]
    kept = 0
    for cx, cy in pore_centers(bb, rng):
        # Keep the pore only if it lies wholly inside the region.
        inside = True
        for dx, dy in ((0, 0), (PORE_R, 0), (-PORE_R, 0), (0, PORE_R), (0, -PORE_R)):
            pt = orca.host.Point(cx + dx, cy + dy)
            if not safe(lambda: exp.contains(pt), False):
                inside = False
                break
        if not inside:
            continue
        pore = orca.host.ExPolygon(circle_poly(cx, cy, PORE_R))
        nxt = []
        for piece in pieces:
            res = safe(lambda: piece.diff_ex(pore), None)
            if res is None or is_err(res):
                nxt.append(piece)
                continue
            nxt.extend(res)
        pieces = nxt
        kept += 1
    log(f"    carved {kept} pores -> {len(pieces)} strut piece(s)")
    return pieces


def total_area(exps):
    return sum(safe(lambda: e.area(), 0.0) for e in exps)


def choose_layer(layers):
    """Nearest-to-middle layer carrying a sparse (internal, non-solid) surface."""
    mid = len(layers) // 2
    for i in sorted(range(len(layers)), key=lambda i: (abs(i - mid), i)):
        regions = safe(lambda: layers[i].regions(), []) or []
        if is_err(regions) or not regions:
            continue
        for s in safe(lambda: regions[0].fill_surfaces.surfaces, []) or []:
            if is_err(s):
                continue
            if safe(lambda: s.is_internal(), False) and not safe(lambda: s.is_solid(), True):
                return i
    return None


def carve_layer(layer):
    """Rebuild fill_surfaces: sparse surfaces -> carved struts typed stInternalSolid."""
    regions = safe(lambda: layer.regions(), []) or []
    if is_err(regions) or not regions:
        return None
    lr = regions[0]
    surfaces = safe(lambda: lr.fill_surfaces.surfaces, []) or []
    if is_err(surfaces):
        return None

    rng = random.Random(SEED)
    rebuilt = []
    area_before = 0.0
    area_after = 0.0

    for s in surfaces:
        is_sparse = (safe(lambda: s.is_internal(), False)
                     and not safe(lambda: s.is_solid(), True))
        exp = safe(lambda: s.expolygon)
        if not is_sparse or exp is None or is_err(exp):
            rebuilt.append(s)
            continue
        area_before += safe(lambda: exp.area(), 0.0)
        pieces = carve(exp, rng)
        area_after += total_area(pieces)
        for piece in pieces:
            rebuilt.append(orca.host.Surface(orca.host.SurfaceType.stInternalSolid, piece))

    if area_before == 0.0:
        log("    no sparse surface on this layer; nothing carved")
        return None

    try:
        lr.fill_surfaces.set(rebuilt)
    except Exception as exc:  # noqa: BLE001
        log(f"    fill_surfaces.set FAILED: {type(exc).__name__}: {exc}")
        return None

    log(
        "    area %.1f mm2 -> %.1f mm2 (%.1f%% void), surfaces %d -> %d"
        % (mm2(area_before), mm2(area_after),
           100.0 * (1.0 - area_after / area_before) if area_before else 0.0,
           len(surfaces), len(rebuilt))
    )
    return lr


def metrics(lr):
    paths = safe(lambda: lr.fills.flatten_paths(), []) or []
    if is_err(paths):
        paths = []
    length = 0.0
    for p in paths:
        pts = safe(lambda: p.points(), None)
        if pts is None or is_err(pts) or len(pts) == 0:
            continue
        for i in range(1, len(pts)):
            dx = float(pts[i][0]) - float(pts[i - 1][0])
            dy = float(pts[i][1]) - float(pts[i - 1][1])
            length += (dx * dx + dy * dy) ** 0.5
    return len(paths), length * 1e-6


class InfillSpike(orca.slicing.SlicingPipelineCapabilityBase):
    def get_name(self):
        return "Infill Spike"

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
            log(f"params: strut={STRUT_WIDTH_MM}mm pore={PORE_DIAMETER_MM}mm "
                f"jitter={PORE_JITTER} seed={SEED}")
        if ctx.object is None:
            return

        layers = safe(lambda: ctx.object.layers(), []) or []
        if not layers or is_err(layers):
            return

        if name == "posPrepareInfill":
            if "carved" in CARVED:
                return
            idx = choose_layer(layers)
            if idx is None:
                log("no sparse layer found; set sparse infill density > 0")
                CARVED.add("none")
                return
            log(f"carving layer {idx} of {len(layers)}")
            if carve_layer(layers[idx]) is not None:
                CARVED.add("carved")
                CARVED.add(idx)
                log("EXPECT: preview shows dense solid infill tracing a strut network "
                    "on this layer only")
            else:
                CARVED.add("failed")

        elif name == "posInfill":
            if "carved" not in CARVED:
                log("VERDICT: SKIPPED — nothing was carved at posPrepareInfill")
                return
            idx = [c for c in CARVED if isinstance(c, int)]
            if not idx:
                return
            i = idx[0]
            regions = safe(lambda: layers[i].regions(), []) or []
            if is_err(regions) or not regions:
                return
            n_paths, length = metrics(regions[0])
            others = []
            for j, layer in enumerate(layers):
                if j == i:
                    continue
                rs = safe(lambda: layer.regions(), []) or []
                if is_err(rs) or not rs:
                    continue
                p, _ = metrics(rs[0])
                if p:
                    others.append(p)
            mean_other = sum(others) / len(others) if others else 0.0
            log(f"VERDICT: carved layer {i}: paths={n_paths} len={length:.1f}mm "
                f"(mean other layers: {mean_other:.1f} paths)")
            if n_paths == 0:
                log("VERDICT: FAILED — carved struts produced no infill at all")
            elif n_paths <= mean_other:
                log("VERDICT: SUSPICIOUS — carved layer has no more paths than a sparse "
                    "one; struts were probably not filled densely. Check preview.")
            else:
                log("VERDICT: SOLID CONFIRMED — carved layer has more infill paths than "
                    "the sparse baseline, consistent with dense strut fill.")


@orca.plugin
class InfillSpikePlugin(orca.base):
    def register_capabilities(self):
        orca.register_capability(InfillSpike)
