# Quickstart — Trabecular Infill

Validation guide. Proves the feature works end to end. Implementation detail
lives in `tasks.md`.

## Prerequisites

- OrcaSlicer **2.5.2** at `/Applications/OrcaSlicer 2.app`, build `f92a7c06`
  (read it from Help > About). Not 2.4.2 — no plugin system there. Exports made
  before the 2.5.2 re-verification are 2.5.0-rc build `af2ffb8c`.
- No other OrcaSlicer instance running. Both versions share
  `~/Library/Application Support/OrcaSlicer/`, and the 2.4.2 instance has no
  plugin system.
- A process profile with sparse infill density above zero.

## Install

```sh
mkdir -p "$HOME/Library/Application Support/OrcaSlicer/orca_plugins/os-bone-plugin"
cp src/os_bone_plugin/bone_infill.py \
   "$HOME/Library/Application Support/OrcaSlicer/orca_plugins/os-bone-plugin/bone_infill.py"
```

One `.py` per folder. Two entry files, or a `.py` beside a `.whl`, makes the
plugin unloadable.

## Enable

1. Restart OrcaSlicer (discovery runs at startup).
2. **File > Plugins** → **Trabecular Infill** → enable the capability.
3. Process settings → G-code section → **Slicing Pipeline Plugin** → set to
   empty, then select **Trabecular Infill**.

On 2.5.2 the empty-then-select order is **no longer required**: PR 16884
resolves a missing manifest entry by capability name at slice time. The step
remains harmless. On 2.5.0-rc the order mattered because the derived `plugins`
manifest was only rebuilt when the picker changed. On 2.5.2 a stale manifest
logs `missing from the plugins manifest; resolved by name`; the old
`no plugin reference found for capability` line now means the capability is not
loaded at all.

## Verify it ran

After slicing, the main log
(`<data_dir>/log/debug_*.log.0`) must NOT contain
`Slicing Pipeline: no plugin reference found`. The Python log
(`<data_dir>/log/python_*.log`) must contain lines prefixed `[bone_infill]`.

The exported G-code must carry both:

```
; plugins = "bone_infill;;Trabecular Infill"
; slicing_pipeline_plugin = "Trabecular Infill"
```

## Validation scenarios

### V1 — structure appears (User Story 1)

Slice the 20 mm cube. Preview shows dense struts separated by voids on every
interior layer that has a sparse surface. Current behaviour carves **every layer
with a sparse `stInternal` surface**; the "exactly one interior layer" result
belonged to the original single-layer spike and is not the shipping behaviour.
The exported G-code therefore has many, not one, interior layers whose extrusion
type is `Internal solid infill` beyond the native shells.

Then search the Python log and the debug log for the 2.5.2 skipped-region
message from `docs/platform-2.5.2.md`:

```
Arachne: invalid Voronoi diagram, no toolpaths generated for this outline.
```

Any hit fails V1. A hit means an outline — plausibly a long, thin carved strut —
was skipped by Arachne while the slice still succeeded.

### V2 — determinism (SC-002)

Slice seven times with identical settings. All seven outputs byte-identical:

```sh
shasum -a 256 *.gcode | awk '{print $1}' | sort -u | wc -l   # expect 1
```

### V3 — orientation follows the profile (SC-007, FR-002a)

Slice with `solid_infill_direction = 45`, then with `= 0`. Compare the two
exports. The void orientation changes. If it does not, FR-002a is not met.

### V4 — fallback when the setting is unusable (FR-002b)

Force the setting absent or unparseable. Slicing completes, structure appears at
45°, and the Python log carries one fallback line. One line, not one per layer.

### V5 — unprintable strut thickness warns (SC-008, FR-004)

Set `strut_thickness_mm` below `2 × solid_infill_line_width`. Slice. A
user-visible error names the supplied value and the minimum. Observed in the
GUI, not inferred from the log.

### V6 — print cost is measured (SC-006)

```sh
python3 -I tools/gcode_metrics.py tests/<file>.gcode --layer <carved layer>
python3 -I tools/gcode_metrics.py tests/<gyroid control>.gcode
```

Record move count, mean segment length, and travel share for both. These are the
numbers any print-time claim must cite.

### V7 — physical test (SC-003, SC-004)

Print the 20 mm cube with trabecular infill on a stock profile. Photograph the
finished part. No failed print, no intervention.

## Coupon procedure (SC-004, FR-010a)

1. Slice a coupon with trabecular infill; record the slicer's estimated mass.
2. Slice the same coupon with gyroid. Iterate `sparse_infill_density` until the
   estimate is close.
3. **Print both. Weigh both.** Estimated mass is not evidence.
4. State the tolerance (for example ±2%). If the measured masses fall outside it,
   adjust the gyroid density and reprint the control. Repeat until matched.
5. Compression test both under the same conditions. Record: measured masses,
   measured failure load and/or peak stress, printer, profile, filament, coupon
   dimensions, test method.
6. If the pair never matches within tolerance, report the actual masses and do
   NOT present the comparison as matched-weight.

## Record keeping

Every number that reaches the README or a commit message must name its artifact
— the G-code file and layer, or the coupon record. Constitution Principle I and
the Review Gate require this; a number without its artifact is a defect.
