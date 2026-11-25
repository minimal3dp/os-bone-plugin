# /// script
# requires-python = ">=3.12"
# dependencies = []
#
# [tool.orcaslicer.plugin]
# name = "Infill Probe"
# description = "Phase 0 feasibility probe: enumerates the live slicing graph at posPrepareInfill/posInfill and reports which parts are writable."
# author = "Mike Wilson"
# version = "0.2.0"
# ///
"""Phase 0 feasibility probe for the bone-infill plugin.

Answers three questions, in order of importance:

1. Are infill toolpaths (`LayerRegion.fills`) writable from Python?
2. Is `LayerRegion.fill_surfaces` writable, and does a mutation at
   posPrepareInfill cascade into the fills generated afterwards?
3. What exactly is reachable from ctx.print / ctx.object / LayerRegion?

Question 2 is answered by a BINARY experiment, not inference: one layer's
fill_surfaces are cleared at posPrepareInfill, then at posInfill that layer
should have ~zero infill paths while its neighbours still have many.

Everything is logged to sys.stderr, which OrcaSlicer tees to
<data_dir>/log/python_<weekday>_<mon>_<day>_<HH>_<MM>_<SS>_<pid>.log
"""

import sys
import traceback

import orca

LOG = "[infill_probe]"

# Which layer to sacrifice for the cascade experiment.
#   None -> auto-pick the layer nearest the middle that actually carries sparse
#           (stInternal, non-solid) fill surfaces. Bottom/top shell layers hold
#           solid surfaces, so mutating one of those would test nothing.
#   -1   -> disable the mutation; the probe becomes fully read-only.
#   int  -> that exact layer index.
MUTATE_LAYER_INDEX = None

PREPARE_STATE = {}   # (object_id, layer_index) -> dict captured at posPrepareInfill
HEADERS_LOGGED = set()
MUTATIONS_DONE = set()


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
    return f"<unknown {step}>"


def safe(fn, default=None):
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001 - probe reports, never raises
        return f"{default if default is not None else ''}<error: {type(exc).__name__}: {exc}>".strip()


def is_err(v):
    return isinstance(v, str) and "<error:" in v


def polyline_length_scaled(pts):
    if pts is None or is_err(pts) or len(pts) == 0:
        return 0.0
    total = 0.0
    for i in range(1, len(pts)):
        dx = float(pts[i][0]) - float(pts[i - 1][0])
        dy = float(pts[i][1]) - float(pts[i - 1][1])
        total += (dx * dx + dy * dy) ** 0.5
    return total


def layer_metrics(lr):
    fills = lr.fills
    paths = safe(lambda: fills.flatten_paths(), []) or []
    if is_err(paths):
        paths = []
    total_len = 0.0
    total_pts = 0
    for p in paths:
        pts = safe(lambda: p.points(), None)
        total_len += polyline_length_scaled(pts)
        total_pts += 0 if pts is None or is_err(pts) else len(pts)
    fs = lr.fill_surfaces
    return {
        "fills_size": safe(lambda: fills.size(), -1),
        "paths": len(paths),
        "points": total_pts,
        "length_mm": total_len * 1e-6,
        "fs_n": safe(lambda: fs.size(), -1),
    }


def dump_header(ctx, name):
    log(f"==================== STEP {name} ====================")
    log(f"orca_version={ctx.orca_version}")
    log(f"ctx attrs={names(ctx)}")
    log(f"gcode_path={ctx.gcode_path!r} host={ctx.host!r} output_name={ctx.output_name!r}")
    log(f"print={ctx.print!r} object={ctx.object!r}")
    log(
        "config: sparse_infill_density=%r sparse_infill_pattern=%r layer_height=%r"
        % (
            safe(lambda: ctx.config_value("sparse_infill_density")),
            safe(lambda: ctx.config_value("sparse_infill_pattern")),
            safe(lambda: ctx.config_value("layer_height")),
        )
    )
    log(f"system attrs={names(orca)}")
    log(f"orca.host attrs={names(orca.host)}")
    log(f"orca.slicing attrs={names(orca.slicing)}")
    log(f"SurfaceType values={names(orca.host.SurfaceType)}")


def dump_graph(ctx, name):
    log(f"PrintObject attrs={names(ctx.object)}")
    log(f"Print attrs={names(ctx.print)}")
    log(f"PrintObject.id={safe(lambda: ctx.object.id)}")
    log(f"Print.config_keys containing 'plugin'="
        f"{[k for k in (safe(lambda: ctx.print.config_keys(), []) or []) if 'plugin' in k.lower()]}")
    bb = safe(lambda: ctx.object.bounding_box())
    log(f"PrintObject.bounding_box={bb}")

    layers = safe(lambda: ctx.object.layers(), []) or []
    log(f"layers={len(layers)}")
    if not layers:
        return layers

    # Full attribute dump once, on a sparse-infill layer if one exists.
    for idx, layer in enumerate(layers):
        regions = safe(lambda: layer.regions(), []) or []
        if not regions:
            continue
        lr = regions[0]
        log(f"Layer attrs={names(layer)}")
        log(f"LayerRegion attrs={names(lr)}")
        log(f"LayerRegion.slices attrs={names(lr.slices)}")
        log(f"LayerRegion.fill_surfaces attrs={names(lr.fill_surfaces)}")
        log(f"LayerRegion.fills attrs={names(lr.fills)}")
        log(f"PrintRegion attrs={names(safe(lambda: lr.region()))}")

        for s in (safe(lambda: lr.fill_surfaces.surfaces, []) or [])[:6]:
            log(
                "  surface type=%s area_scaled2=%s internal=%s solid=%s bridge=%s expolygon_attrs=%s"
                % (
                    safe(lambda: s.surface_type),
                    safe(lambda: s.area()),
                    safe(lambda: s.is_internal()),
                    safe(lambda: s.is_solid()),
                    safe(lambda: s.is_bridge()),
                    names(s.expolygon),
                )
            )

        ep = None
        for s in (safe(lambda: lr.fill_surfaces.surfaces, []) or []):
            ep = safe(lambda: s.expolygon)
            break
        if ep is not None and not is_err(ep):
            log(f"  ExPolygon attrs={names(ep)}")
            log(f"  ExPolygon.contour attrs={names(ep.contour)}")
            pts = safe(lambda: ep.contour.points)
            log(f"  ExPolygon.contour.points -> {type(pts).__name__} "
                f"len={len(pts) if pts is not None and not is_err(pts) else '?'}")

        # Extrusion tree shape: first layer with fills at this step.
        paths = safe(lambda: lr.fills.flatten_paths(), []) or []
        if paths and not is_err(paths):
            p = paths[0]
            log(f"  ExtrusionPath attrs={names(p)}")
            parr = safe(lambda: p.points())
            log(f"  ExtrusionPath.points -> shape={getattr(parr, 'shape', None)} "
                f"dtype={getattr(parr, 'dtype', None)} "
                f"writeable={getattr(getattr(parr, 'flags', None), 'writeable', None)}")
            log(f"  ExtrusionEntity attrs={names(p)}")
        return layers

    return layers


def probe_writability(lr):
    """Report which mutations are possible; never raises."""
    log("---- writability probe ----")
    coll = lr.fills
    log(f"ExtrusionEntityCollection attrs={names(coll)}")
    for attr in ("append", "set", "clear", "insert", "remove", "remove_last", "flatten_paths"):
        log(f"  fills.{attr} present={hasattr(coll, attr)}")
    log("  attempt setattr(lr, 'fills', <new collection>): "
        + str(safe(lambda: setattr(lr, "fills", coll) or "ASSIGNED", "SETATTR_FAILED")))

    paths = safe(lambda: coll.flatten_paths(), []) or []
    if not paths or is_err(paths):
        log("  no fills yet at this step; path-level probes deferred")
        return

    p = paths[0]
    log(f"  path class={type(p).__name__}")
    log("  attempt setattr(path, 'width', 0.4): " + str(safe(lambda: setattr(p, "width", 0.4) or "ASSIGNED", "SETATTR_FAILED")))
    log("  attempt setattr(path, 'height', 0.1): " + str(safe(lambda: setattr(p, "height", 0.1) or "ASSIGNED", "SETATTR_FAILED")))
    log("  attempt construct type(path)(): " + str(safe(lambda: type(p)(), "CONSTRUCT_FAILED")))

    arr = safe(lambda: p.points())
    if arr is not None and not is_err(arr) and len(arr):
        log(f"  path.points writeable={arr.flags.writeable}")
        if arr.flags.writeable:
            before = float(arr[0][0])
            arr[0][0] = before
            log(f"  writable-array no-op write ok (elem {before})")
        else:
            log("  attempt arr[0,0] = arr[0,0]: " + str(safe(lambda: arr.__setitem__((0, 0), arr[0, 0]) or "ASSIGNED", "READONLY_CONFIRMED")))


def mutate_fill_surfaces(layer, layer_index, obj_id):
    """THE cascade experiment. Returns a description string."""
    key = (obj_id, layer_index)
    if key in MUTATIONS_DONE:
        return "already mutated"
    MUTATIONS_DONE.add(key)

    regions = safe(lambda: layer.regions(), []) or []
    if not regions:
        return "no region"
    lr = regions[0]
    fs = lr.fill_surfaces
    before = safe(lambda: fs.size(), -1)
    try:
        fs.clear()
    except Exception as exc:  # noqa: BLE001
        return f"clear() raised {type(exc).__name__}: {exc}"
    after = safe(lambda: fs.size(), -1)
    return f"fill_surfaces {before} -> {after} surfaces on layer {layer_index}"


def sparse_surface_count(layer):
    """How many stInternal non-solid surfaces this layer's first region has."""
    regions = safe(lambda: layer.regions(), []) or []
    if is_err(regions) or not regions:
        return 0
    n = 0
    for s in safe(lambda: regions[0].fill_surfaces.surfaces, []) or []:
        if is_err(s):
            continue
        if safe(lambda: s.is_internal(), False) and not safe(lambda: s.is_solid(), True):
            n += 1
    return n


def choose_mutation_layer(layers):
    """Nearest-to-middle layer that has sparse fill surfaces, else None."""
    mid = len(layers) // 2
    for i in sorted(range(len(layers)), key=lambda i: (abs(i - mid), i)):
        if sparse_surface_count(layers[i]) > 0:
            return i
    return None


class InfillProbe(orca.slicing.SlicingPipelineCapabilityBase):
    def get_name(self):
        return "Infill Probe"

    def execute(self, ctx):
        try:
            self._run(ctx)
        except Exception:  # noqa: BLE001 - never fail the slice
            log("EXCEPTION in probe:\n" + traceback.format_exc())
        return orca.ExecutionResult.success()

    def _run(self, ctx):
        name = step_name(ctx.step)

        if name not in HEADERS_LOGGED:
            HEADERS_LOGGED.add(name)
            dump_header(ctx, name)

        if name == "psGCodePostProcess":
            log("psGCodePostProcess: ctx.print is None by design; nothing to probe.")
            return
        if ctx.print is None or ctx.object is None:
            return

        obj_id = safe(lambda: ctx.object.id, "?")

        if name == "posPrepareInfill":
            self._on_prepare(ctx, obj_id)
        elif name == "posInfill":
            self._on_infill(ctx, obj_id)

    # ------------------------------------------------------------------
    def _on_prepare(self, ctx, obj_id):
        if obj_id not in PREPARE_STATE:
            log(f"---- posPrepareInfill graph dump (object id={obj_id}) ----")
            layers = dump_graph(ctx, "posPrepareInfill") or []
            if not layers:
                return
            regions = safe(lambda: layers[0].regions(), []) or []
            if regions:
                probe_writability(regions[0])
            PREPARE_STATE[obj_id] = {}

        layers = safe(lambda: ctx.object.layers(), []) or []
        PREPARE_STATE[obj_id] = {
            idx: layer_metrics((safe(lambda: layer.regions(), []) or [None])[0])
            for idx, layer in enumerate(layers)
            if safe(lambda: layer.regions(), [])
        }

        if MUTATE_LAYER_INDEX == -1:
            log("---- mutation disabled (MUTATE_LAYER_INDEX = -1) ----")
            return

        target = MUTATE_LAYER_INDEX
        if target is None:
            target = choose_mutation_layer(layers)
            if target is None:
                log("---- no layer carries sparse fill surfaces; mutation skipped ----")
                log("  is sparse infill density > 0? solid top/bottom shells alone cannot "
                    "test the cascade")
                return
            log(f"---- auto-selected mutation layer {target} of {len(layers)} "
                f"({sparse_surface_count(layers[target])} sparse surfaces) ----")

        if 0 <= target < len(layers):
            result = mutate_fill_surfaces(layers[target], target, obj_id)
            log(f"---- CASCADE EXPERIMENT (object {obj_id}): {result} ----")
            log("  prediction: at posInfill this layer has ~0 infill paths, neighbours do not")
        else:
            log(f"---- mutation layer {target} out of range ----")

    # ------------------------------------------------------------------
    def _on_infill(self, ctx, obj_id):
        layers = safe(lambda: ctx.object.layers(), []) or []
        prepared = PREPARE_STATE.get(obj_id, {})
        log(f"---- posInfill metrics (object id={obj_id}, {len(layers)} layers) ----")
        log("  idx  fills_n  paths  points  len_mm   fs_n(prepare)  NOTE")
        for idx, layer in enumerate(layers):
            regions = safe(lambda: layer.regions(), []) or []
            if not regions:
                continue
            m = layer_metrics(regions[0])
            pre = prepared.get(idx, {})
            note = "MUTATED" if (obj_id, idx) in MUTATIONS_DONE else ""
            log(
                "  %3d  %7d  %5d  %6d  %8.1f  %13s  %s"
                % (idx, m["fills_size"], m["paths"], m["points"], m["length_mm"],
                   pre.get("fs_n", "?"), note)
            )
        # Enable path-level writability probe now that fills exist.
        if layers:
            regions = safe(lambda: layers[len(layers) // 2].regions(), []) or []
            if regions:
                probe_writability(regions[0])

        self._verdict(layers, obj_id)

    # ------------------------------------------------------------------
    def _verdict(self, layers, obj_id):
        """One unambiguous conclusion line per object."""
        mutated = [i for i in range(len(layers)) if (obj_id, i) in MUTATIONS_DONE]
        if not mutated:
            log("VERDICT: no cascade experiment ran (no mutation) — read graph shape only")
            return

        rows = {}
        for i in mutated:
            regions = safe(lambda: layers[i].regions(), []) or []
            if not regions or is_err(regions):
                continue
            rows[i] = layer_metrics(regions[0])

        others = []
        for i, layer in enumerate(layers):
            if i in mutated:
                continue
            regions = safe(lambda: layer.regions(), []) or []
            if not regions or is_err(regions):
                continue
            m = layer_metrics(regions[0])
            if m["paths"] > 0:
                others.append(m["paths"])

        for idx, m in rows.items():
            mean_other = sum(others) / len(others) if others else 0.0
            log(
                "VERDICT: layer %d after fill_surfaces.clear() -> paths=%d len_mm=%.1f "
                "(mean of %d non-mutated layers: %.1f paths)"
                % (idx, m["paths"], m["length_mm"], len(others), mean_other)
            )
            if m["paths"] == 0 and mean_other > 0:
                log("VERDICT: CASCADE CONFIRMED — fill_surfaces edits at posPrepareInfill "
                    "control the generated infill. Architecture A is viable in principle.")
            elif mean_other == 0:
                log("VERDICT: INCONCLUSIVE — no layer has infill; enable sparse infill and retry.")
            else:
                log("VERDICT: CASCADE REJECTED — mutation did not remove infill; the slicer "
                    "reconstitutes fill_surfaces after the hook. Architecture A is not viable.")


@orca.plugin
class InfillProbePlugin(orca.base):
    """Package class. Exactly one per plugin file; registers the capabilities."""

    def register_capabilities(self):
        orca.register_capability(InfillProbe)
