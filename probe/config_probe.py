# /// script
# requires-python = ">=3.12"
# dependencies = []
#
# [tool.orcaslicer.plugin]
# name = "Config Probe"
# description = "Phase 2 gate probe: reports which config accessor exposes solid_infill_direction at posPrepareInfill, and how the rotate template indexes layers."
# author = "Mike Wilson"
# version = "0.1.0"
# ///
"""Verification probe for tasks T004 and T005.

Answers two questions `research.md` leaves open, both of which the algorithm
depends on:

  T004  Is `solid_infill_direction` readable through the config API at
        posPrepareInfill, and through which accessor?
  T005  Is `solid_infill_rotate_template` indexed per object layer or per
        print layer?

Both are answered by logging, not by inference. Read-only: mutates nothing.
"""

import sys
import traceback

import orca

LOG = "[config_probe]"
MAX_LAYER_LINES = 12

_seen = set()
_layer_dump_done = False


def log(msg=""):
    print(f"{LOG} {msg}", file=sys.stderr, flush=True)


def names(obj):
    return sorted(n for n in dir(obj) if not n.startswith("_"))


def safe(fn, default="<error>"):
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001
        return f"{default}: {type(exc).__name__}: {exc}"


def step_name(step):
    for n in names(orca.slicing.Step):
        try:
            if getattr(orca.slicing.Step, n) == step:
                return n
        except Exception:
            continue
    return "?"


KEYS = (
    "solid_infill_direction",
    "infill_direction",
    "solid_infill_rotate_template",
    "solid_infill_line_width",
    "sparse_infill_density",
    "sparse_infill_pattern",
)


class ConfigProbe(orca.slicing.SlicingPipelineCapabilityBase):
    def get_name(self):
        return "Config Probe"

    def execute(self, ctx):
        try:
            self._run(ctx)
        except Exception:  # noqa: BLE001
            log("EXCEPTION:\n" + traceback.format_exc())
        return orca.ExecutionResult.success()

    def _run(self, ctx):
        global _layer_dump_done

        name = step_name(ctx.step)
        if name != "posPrepareInfill" or ctx.object is None:
            return

        if "report" not in _seen:
            _seen.add("report")
            self._report_accessors(ctx)

        if not _layer_dump_done:
            self._dump_per_layer(ctx)
            _layer_dump_done = True

    # ------------------------------------------------------------------
    def _report_accessors(self, ctx):
        log("======== T004: which accessor exposes solid_infill_direction ========")
        layers = safe(lambda: ctx.object.layers(), [])
        region_value = "<no layers>"
        if isinstance(layers, list) and layers:
            regions = safe(lambda: layers[0].regions(), [])
            if isinstance(regions, list) and regions:
                region_value = safe(
                    lambda: regions[0].config_value("solid_infill_direction")
                )

        rows = [
            ("ctx.config_value", safe(lambda: ctx.config_value("solid_infill_direction"))),
            ("ctx.object.config_value", safe(lambda: ctx.object.config_value("solid_infill_direction"))),
            ("LayerRegion.config_value", region_value),
        ]
        for label, value in rows:
            verdict = "READABLE" if not _is_error(value) and value is not None else "no"
            log(f"  {label:<28} = {value!r}   [{verdict}]")

        log("---- related keys via ctx.config_value ----")
        for key in KEYS:
            log(f"  {key:<32} = {safe(lambda: ctx.config_value(key))!r}")

        log("---- related keys via ctx.object.config_value ----")
        for key in KEYS:
            log(f"  {key:<32} = {safe(lambda: ctx.object.config_value(key))!r}")

    # ------------------------------------------------------------------
    def _dump_per_layer(self, ctx):
        log("======== T005: rotate template indexing ========")
        template = safe(lambda: ctx.config_value("solid_infill_rotate_template"))
        log(f"  template = {template!r}")
        log("  (set the profile template to 0,90 and compare these against the")
        log("   exported G-code to see whether rotation follows layer index)")

        layers = safe(lambda: ctx.object.layers(), [])
        if not isinstance(layers, list):
            log(f"  layers unavailable: {layers}")
            return

        log(f"  total layers = {len(layers)}")
        for index, layer in enumerate(layers[:MAX_LAYER_LINES]):
            regions = safe(lambda: layer.regions(), [])
            direction = "<no region>"
            if isinstance(regions, list) and regions:
                direction = safe(lambda: regions[0].config_value("solid_infill_direction"))
            z = safe(lambda: round(layer.print_z, 3))
            log(f"  layer[{index:3d}] print_z={z} solid_infill_direction={direction!r}")
        if len(layers) > MAX_LAYER_LINES:
            log(f"  ... {len(layers) - MAX_LAYER_LINES} more layers not shown")


def _is_error(value):
    return isinstance(value, str) and (":" in value and "Error" in value)


@orca.plugin
class ConfigProbePlugin(orca.base):
    def register_capabilities(self):
        orca.register_capability(ConfigProbe)
