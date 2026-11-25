# Phase 0 findings — OrcaSlicer plugin bindings vs. bone infill

Written 2026-10-31. Sources are the `v2.5.0-beta` tag of
`OrcaSlicer/OrcaSlicer` and the four wiki pages listed in the brief. Every
claim below has a file + line reference or a doc quote; nothing here is
inferred from the UI.

**Verified environment**

| Item | Value |
| --- | --- |
| `/Applications/OrcaSlicer 2.app` | `2.5.0-beta` at time of probe; **now `2.5.0-rc` build `af2ffb8c`** (updated 2026-11-01) |
| `/Applications/OrcaSlicer.app` | `2.4.2` (too old — plugin system absent) |
| data_dir | `~/Library/Application Support/OrcaSlicer/` |
| Plugin root | `<data_dir>/orca_plugins/<folder>/` |
| Note | The 2.5 beta shares `data_dir` with the 2.4.2 stable install. |
| Python log | `<data_dir>/log/python_<wd>_<mon>_<day>_<HH>_<MM>_<SS>_<pid>.log` |

## The answer to the critical unknown

**A pipeline plugin cannot replace infill toolpaths. It can replace the *input*
to infill generation.**

The distinction is the whole architecture decision, so it is worth being exact:

- `LayerRegion.fills` is bound `def_readonly`
  (`PluginHostSlicing.cpp:258-259`) and the
  `ExtrusionEntityCollection` binding exposes only `size()`, `entities`,
  `flatten_paths()` (`PluginHostSlicing.cpp:216-239`). **No mutator exists.**
  Assigning to `.fills` fails; there is no `append`/`set`/`clear` on it; the
  `ExtrusionPath` `width`/`height`/`mm3_per_mm` are `def_readonly`
  (`PluginHostSlicing.cpp:194-196`) and `points()` returns a **read-only**
  numpy view (`make_readonly_rows`, `PluginHostSlicing.cpp:185-193`).
- `LayerRegion.fill_surfaces` (and `.slices`) are bound with
  `def_readonly` on the *attribute* but hand out a `SurfaceCollection` whose
  own methods mutate the live graph in place:
  `set(expolygons, type)`, `set(surfaces)`, `append(...)`, `clear()`,
  `set_type(...)` (`PluginHostSlicing.cpp:138-169`). `Surface.expolygon` is a
  read/write property (`:123-127`), `Surface.surface_type` is `def_readwrite`
  (`:118-119`), and `ExPolygon` is fully constructible/offsettable from Python
  (`PluginHostGeometry.cpp:160-224`).
- The pipeline fires `posPrepareInfill` **between** `prepare_infill()` and
  `infill()`, and `posInfill` **after** `make_fills()`:

  ```cpp
  // Print.cpp:3463-3473
  obj->prepare_infill();
  hook_after(obj, ..., posPrepareInfill);   // edit fill_surfaces HERE -> cascades
  obj->infill();
  hook_after(obj, ..., posInfill);          // fills are already built; too late
  ```

  The source comment states it outright: *"split prepare_infill (fill-surface
  prep) from infill (make_fills) so a plugin can mutate fill surfaces at the
  PrepareInfill seam and have make_fills consume them (unlike the Infill seam,
  which fires after the fills are already built)."*

So the route is **posPrepareInfill + `fill_surfaces`**, not posInfill path
replacement. Options A and B from the brief are both based on a premise the
bindings contradict: A assumes `fills` is writable (it is not), and B's
G-code rewrite is possible but loses infill region boundaries exactly as the
brief warned.

That said: `fill_surfaces` is the *boundary* input, not the pattern input. The
slicer fills those regions with `sparse_infill_pattern`. A plugin can change
**where** infill is allowed, not **which strokes** are drawn inside it. That
constrains the algorithm design and needs to be checked against the doc's own
intent before the architecture is committed to. That is what the probe settles
empirically.

## Also confirmed

| Fact | Evidence |
| --- | --- |
| `orca.host` (model/presets/mesh) is read-only | host.html; `PluginHostSlicing.cpp:86-94` |
| `orca.host` **slicing graph** is mutable and separate from that statement | `PluginHostSlicing.cpp` register_slicing, `SurfaceCollection` mutators |
| Slicing plugins run on the worker thread; never call `orca.host.ui.*` | `SlicingPipelinePluginCapability.hpp:38-41`; slicing.html |
| References valid only during `execute(ctx)`; container mutators invalidate prior refs | `PluginHostSlicing.cpp:86-94` |
| Editing `fill_surfaces` at `posInfill` does nothing (fills already built) | `SlicingPipelinePluginCapability.cpp:31-32` comment |
| Plugin must be picked in a preset via `slicing_pipeline_plugin` (advanced G-code settings) | `PrintConfig.cpp:6013-6021`, `Tab.cpp:3525-3529` |
| `psGCodePostProcess` has `ctx.print is None`; edit `ctx.gcode_path` in place | `SlicingPipelinePluginCapability.cpp:41-49` |
| One `.py` or one `.whl` per plugin folder; both present = load error | `PluginFsUtils.cpp:1209-1260` |
| Plugin folder name is ignored if it starts with `.` or `__`, or is `_subscribed` | `PluginFsUtils.cpp:173-180` (`is_ignored_plugin_directory`) |
| Enable state persists in `.install_state.json` inside the plugin folder | `PluginLoader.cpp`, `PluginFsUtils.cpp` `INSTALL_STATE_FILE` |
| Dependencies are PEP 723 root-level `dependencies`, installed by bundled uv | dev guide; `PluginLoader.cpp` whl path |

### Surface types available to a plugin

`stTop, stBottom, stBottomBridge, stInternalAfterExternalBridge, stInternal,
stInternalSolid, stInternalBridge, stSecondInternalBridge, stInternalVoid,
stPerimeter` (`PluginHostSlicing.cpp:96-108`).

Sparse infill = `stInternal`. Solid top/bottom = `stTop`/`stBottom`/
`stInternalSolid`. A plugin can reclassify any of them in place, which changes
which *pattern* the slicer applies (`set_type`,
`PluginHostSlicing.cpp:142-143`), and can rewrite their geometry.

## Geometry available for a generator

Enough to build a lattice in Python without a numpy dependency chain:

- `ExPolygon(contour, holes)` from `Polygon` or `(N,2)` ndarray
  (`PluginHostGeometry.cpp:160-178`)
- `ExPolygon.offset(delta)` → `[ExPolygon]` (Clipper)
  (`:214-215`)
- `ExPolygon.union_ex / diff_ex / intersection_ex(other)` (`:216-224`)
- `Polygon.simplify / douglas_peucker`, `ExPolygon.contains(point)` (`:118-125`, `:210`)
- `ExPolygon.contour.points` is a **writable** array: `make_writable_rows` is
  used for `Polygon.points` (`PluginHostGeometry.cpp:129-141`,
  `PluginBindingUtils.hpp`)

Note: `Polygon.points` / `ExtrusionPath.points()` return *scaled integer*
coordinates (`coord_t`, 1e-6 mm per unit normally). Convert with
`orca.slicing.unscale(coord)` (`SlicingPipelinePluginCapability.cpp:56-59`),
which reads the live `SCALING_FACTOR` — do not hardcode 1e6.

## Probe results (run 2026-10-31, 2.5.0-beta, 175-layer 20 mm cube, 10% cubic)

Run confirmed through `log/python_Sat_Oct_31_19_51_39_80334.log`. The probe
executed at `posPrepareInfill`, `posInfill`, `posIroning`,
`posSupportMaterial`, `posDetectOverhangsForLift`, `psWipeTower`,
`psSkirtBrim`, `posSimplifyPath` (321 log lines).

### Cascade: CONFIRMED

```
VERDICT: layer 87 after fill_surfaces.clear() -> paths=0 len_mm=0.0
         (mean of 174 non-mutated layers: 2.4 paths)
```

Layer 87's `fill_surfaces` were cleared at `posPrepareInfill` (1 surface ->
0). At `posInfill` that layer produced **zero** infill paths while all 174
others averaged 2.4. The experiment required no inference.

Independently confirmed downstream: in `tests/Cube_PLA_23m30s.gcode` the
layer with zero `;TYPE:Sparse` blocks matches the mutated index, and the
header carries `; plugins = "infill_probe;;Infill Probe"`.

### Writability: measured at runtime

| Target | Runtime result |
| --- | --- |
| `lr.fills` attribute set | `AttributeError: property of 'LayerRegion' object has no setter` |
| `fills.append/set/clear/insert/remove/remove_last` | all absent |
| `fills` / `ExtrusionEntityCollection` members | `entities`, `flatten_paths`, `role`, `size` only |
| `lr.fill_surfaces` members | `append, clear, empty, filter_by_type, has, set, set_type, size, surfaces` |
| `lr.slices` members | same mutable set as `fill_surfaces` |
| `ExPolygon` methods | `offset, union_ex, diff_ex, intersection_ex, simplify, contains, num_contours` |

### Reachability confirmed at runtime

`orca.host` exposes `Print`, `PrintObject`, `Layer`, `LayerRegion`,
`PrintRegion`, `Surface`, `SurfaceCollection`, `SurfaceType`, `ExPolygon`,
`Polygon`, `Point`, `ExtrusionPath/Loop/MultiPath/EntityCollection`.

`ctx` members: `cancelled, config_value, gcode_path, host, object,
orca_version, output_name, print, step`.

`orca.slicing.unscale` is present for scaled-int -> mm conversion.

### Two incidental findings

- `PrintObject.id` is a **method**, not a property (`pybind11 ... bound
  method`). Call it: `ctx.object.id()`.
- `ExPolygon.contour.points` returns a **list of `Point`**, not a numpy
  array. `Polygon.as_array()` is the numpy path.

## Architecture A″ spike — carve voids, retype to solid

Run 2026-10-31 20:09, plugin `infill_spike`, preset `M3DP Voron Bone`,
output `tests/Cube_PLA_23m57s.gcode`.

Parameters: strut 1.2 mm, pore 4.0 mm, jitter 0.35, seed 1234, one layer.

### Mechanism: CONFIRMED

Probe log:

```
carving layer 87 of 175
    carved 33 pores -> 1 strut piece(s)
    area 1036.9 mm2 -> 633.2 mm2 (38.9% void), surfaces 1 -> 1
VERDICT: carved layer 87: paths=542 (mean other layers: 2.4 paths)
VERDICT: SOLID CONFIRMED
```

G-code confirms independently. Exactly one layer changed, neighbours untouched:

| layer | extrusion moves | ΣE | extrusion length | travel moves | type |
| --- | --- | --- | --- | --- | --- |
| 85 | 45 | 25.39 | — | — | Sparse |
| 86 | 45 | 25.39 | — | — | Sparse |
| **87** | **2296** | **65.90** | **1785 mm** | **147** | **Internal solid** |
| 88 | 48 | 25.39 | — | — | Sparse |
| 89 | 45 | 25.44 | — | — | Sparse |

Mean of the other 174 layers: 41 extrusion moves, 705 mm extrusion length,
5 travel moves.

Solid-fill sanity check: carved area 633.2 mm² at 0.38 mm line width predicts
`633.2 / 0.38 ≈ 1666 mm` of extrusion. Measured 1785 mm (+7%, consistent with
perimeter overlap). **The slicer genuinely treats the retyped region as solid
infill** — `stInternalSolid` on an arbitrary carved polygon does what we need.

### Fragmentation: the real problem

| Metric | Carved layer | Mean other | Ratio |
| --- | --- | --- | --- |
| extrusion moves | 2296 | 41 | **56.5×** |
| extrusion length | 1785 mm | 705 mm | 2.5× |
| travel moves | 147 | 5 | **27.3×** |
| travel length | 394 mm | 33 mm | **11.9×** |
| sub-0.005 mm extrusions | 169 (7.4%) | 0 | — |

Average segment length is **0.78 mm** — about two extrusion widths. The cause
is structural: OrcaSlicer fills `stInternalSolid` with a 45° rectilinear
raster, and a field of 33 round pores chops that raster into short fragments at
every hole boundary. Travel is 18.1% of motion on that layer.

The plugin cannot change the solid fill pattern: pattern selection reads
`sparse_infill_pattern` / solid-infill settings from config, not from the
surface list. So the pore geometry has to be designed to be **raster-friendly**,
not the other way round.

Levers, in order of expected value:

1. Larger pores and wider spacing — fewer boundaries to fragment the raster.
2. Fewer, elongated rather than circular voids — long raster runs survive.
3. Pore size kept a few line widths minimum so no sub-extrusion slivers form.
4. Possibly orienting struts to match the raster angle so segments stay long.

### Two probe bugs found (spike itself was correct)

- `PrintObject.id` is a **method**, not a property: `ctx.object.id()`. Passing
  the bound method into a format string produced the ugly
  `<bound method ...>` text in the probe log.
- `ExtrusionPath.points()` returned 0-length in the probe's local-length
  helper, so it reported `len=0.0mm`. Root cause not established; the G-code
  analysis is authoritative and supersedes it.

### Verdict

A″ is **mechanically viable**: pure Python, preview-faithful, no upstream
dependency, and the retype produces genuine dense-fill struts. The open
engineering question is no longer "can a plugin do this" but "can the pore
geometry be tuned to print cleanly at speed". That is a design problem with a
known feedback loop (preview + G-code metrics), which is exactly the loop an
MVP can afford.



**Option A as originally scoped is dead.** A plugin cannot replace infill
polylines: `fills` has no mutator and the attribute has no setter.

What is reachable at `posPrepareInfill` is the **region** the slicer later
fills with its built-in pattern. So control is over *where infill may exist*,
not *which strokes are drawn*.

## Tuning run — three pore geometries, one slice

Run 2026-10-31 20:26, plugin `infill_tune`, output `tests/Cube_PLA_24m32s.gcode`.
Three layers carved with different pore shapes, all at 1.2 mm struts.

| variant | layer | void % | strut area | moves | moves/mm² | mean seg | median seg | travel % |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A_fewer_bigger (8 mm circles) | 40 | 42.5% | 596.7 mm² | 1039 | 1.7 | 1.64 mm | 0.74 mm | 13.4% |
| **B_raster_aligned (14×2.5 mm slots at 45°)** | 87 | 27.0% | 756.9 mm² | **800** | **1.1** | **2.59 mm** | 0.52 mm | **6.4%** |
| C_min_feature (4 mm circles + sliver filter) | 134 | 38.9% | 633.2 mm² | 2297 | 3.6 | 0.78 mm | 0.48 mm | 18.2% |
| baseline sparse (untouched) | — | — | — | 41 | — | 17.37 mm | 33 mm | 4.5% |

### B wins

Orienting slot voids along the 45° solid raster roughly halves fragmentation:

- 1.1 moves/mm² vs 1.7 (A) and 3.6 (C) — 3.3× better than the original spike
- 6.4% travel vs 13.4% / 18.2%, close to the 4.5% sparse baseline
- 2.59 mm mean segment, up from 0.78 mm

The mechanism is as hypothesised: a slot parallel to the raster shortens raster
lines along their run rather than cutting them at a curved boundary, so the
surviving segments stay long.

### C disproved a hypothesis

The min-feature filter changed nothing — 2297 moves vs the spike's 2296. The
filter operated on `ExPolygon` pieces, but every carve produced **one connected
polygon** (all three variants logged `1 pieces`). Fragmentation happens *inside*
a single polygon, when the rasteriser crosses pore boundaries; it never
manifests as separate disconnected pieces. Any future "merge small islands"
optimisation is aimed at the wrong layer of the problem.

### Still open

B remains ~20× the baseline move count. That is inherent: a perforated region
cannot raster as cheaply as an unperforated one. Whether ~800 moves per layer is
acceptable is a print-time question that only the compression coupons can
answer — which is exactly what the Phase 3 physical test is for.

Levers not yet tried, if B needs further improvement:

- Increase slot length relative to spacing (fewer, longer voids).
- Widen pores and accept coarser trabeculae.
- Confirm the actual raster angle Orca uses (assumed 45°;
  `solid_infill_angle` / `sparse_infill_angle` are config keys that may move it).

## RESOLVED (2026-11-01): raster angle follows the setting

The earlier "unresolved" section below was measured against the wrong layer
types. Re-measured on `tests/Cube_PLA_1h17m.gcode`, filtering to
`;TYPE:Internal solid infill` long segments only (inner/outer walls are also
axis-aligned and were polluting the histogram):

| layer | plugin direction | measured dominant raster |
| --- | --- | --- |
| 4 | 45° | **45°** (36%) |
| 5 | 135° | **135°** (35%) |
| 50 | 45° | 45° (36%) |
| 100 | 45° | 45° (34%) |
| 170 | 45° | 45° (35%) |

Every sampled layer matches. **The solid raster follows
`solid_infill_direction` plus the rotate template exactly**, as the design
assumed. The histogram that previously appeared to show 0°/90° dominance was
measuring walls, not infill.

Consequence: void orientation and raster orientation are genuinely coupled, and
the plugin controls both through the profile setting. FR-002a is satisfied and
verified.

## Superseded: raster angle (original note)

The tuning design assumed OrcaSlicer's solid infill rasters at 45°, and variant B
was built to align with it. **That assumption was not verified.**

Attempts made 2026-10-31 against `tests/Cube_PLA_24m32s.gcode`:

- Profile export contains `; solid_infill_direction = 45` and
  `; infill_direction = 45` (lines 25080 and 24793). The *setting* is 45°.
- Native bottom-shell solid layers show a 90°-dominant segment histogram, not 45°.
- Sparse (cubic) layers measured 0° at ~32% share, which contradicts a 45° cubic
  raster.
- Carved layers: 0° at 32-33% for two, 90° at 48% for one.

The angle histogram is length-weighted over 1° bins folding to [0,180). It reports
strong 0°/90° content, which is consistent with lattice-geometry artifacts
(axis-aligned strut edges) rather than the raster itself. The measurement was not
cleaned up or re-run against a synthetic control, so **no conclusion about the
actual raster angle has been drawn.**

Consequences:

- Variant B's measured advantage (1.1 moves/mm²) is real as a *measurement*, but
  the explanation offered for it — alignment to a 45° raster — is unconfirmed. Do
  not repeat that explanation as established fact.
- FR-002a of `specs/001-trabecular-infill/spec.md` requires orientation to be
  derived from the profile setting. Whether that setting is readable through the
  config API at `posPrepareInfill` (as opposed to appearing in the export header)
  is **also unverified**.
- The plan must verify both before relying on either.

## Fragmentation tuning round 2 (2026-11-01)

Run against `tests/Cube_PLA_24m22s.gcode`. Earlier run had a parameter bug: void
size was derived from strut thickness, so raising strut enlarged the void until
nothing fitted (all variants carved 0%). Void size is now absolute; strut sets
only the gap. Partial voids are also cut now, so structure reaches the boundary.

| variant | strut | void half-len | void % | moves/mm² | mean seg | median seg | travel % |
| --- | --- | --- | --- | --- | --- | --- | --- |
| A_thick_strut | 2.4 | 6.0 | 28% | 1.61 | 1.71 mm | 0.33 mm | 13.8% |
| **B_long_void** | 1.2 | 8.5 | 47% | **1.16** | **2.40 mm** | 0.32 mm | 15.7% |
| C_both | 2.4 | 8.5 | 31% | 1.33 | 2.10 mm | 0.35 mm | 10.3% |
| sparse baseline | — | — | — | 0.06 | 17.51 mm | 14.85 mm | — |

### Longer voids win, but the median will not move

B has the best moves/mm² and the longest mean segment. But **the median segment
got *worse* in every variant (0.32-0.35 mm) than the 0.50 mm baseline.**

That is the important result, and it is structural, not a tuning failure. A
solid-fill raster emits a short connector between adjacent parallel lines
whenever the run is interrupted. In an unbroken region those connectors are a
small minority. In a perforated region, *every* void boundary interrupts a run,
so the connectors become half the moves by count however the voids are shaped.
Making voids longer or struts thicker changes how many boundaries exist, not
whether each boundary costs a connector.

Consequence: the move count can be reduced by roughly a third, but print time
will not fall proportionally, because the surviving moves are dominated by
short accelerating segments. The architecture has a floor that tuning cannot
reach.

### What this means for the project

Reproduces, in our own numbers, the objection that has kept upstream PR #16809
unmerged: a bone-like perforated infill costs substantially more to print than
a sparse pattern at the same region. This is not a defect in the
implementation; it is a property of "retype a perforated region to solid".

Options this leaves:

1. Accept the cost, ship at the best variant (B), and document the print-time
   price honestly — the coupons then test whether the cost buys anything
   mechanical.
2. Reach for the upstream branch, which generates true 3D walls rather than
   rasterising a 2D region, and does not pay this specific cost.
3. Reconsider the architecture: a lighter-weight pattern that does not require
   solid fill (e.g. retyping to a sparse type instead of solid), which would
   change the whole premise.

**Not yet decided.** The coupon test (T025-T027) will show whether any of this
buys mechanical advantage, which is the only thing that could justify the cost.

## What the probe is for


`probe/infill_probe.py` (installed to
`<data_dir>/orca_plugins/infill_probe/infill_probe.py`) settles three things
the source can only imply:

1. Does `fill_surfaces.clear()` at `posPrepareInfill` actually produce a layer
   with ~zero infill paths at `posInfill`? (Cascade, or a silent no-op because
   some later step reconstitutes the surfaces.)
2. Is the `fills` graph genuinely un-mutable at runtime, or does pybind let a
   `setattr` through? (`def_readonly` should raise `AttributeError`; the probe
   logs the exact message rather than assuming.)
3. What the real per-layer metric looks like — path count, point count,
   polyline length in mm — which is the baseline any generator is measured
   against.

The probe is fully read-only apart from one deliberate `clear()` on layer
index 1 (`MUTATE_LAYER_INDEX`), so the slice of the test cube will have one
hollow-ish layer. That is expected and is the point.

## Gaps the probe cannot close

- Whether `make_fills()` reads anything *other* than `fill_surfaces` that a
  plugin would also need to touch (e.g. `LayerRegion.is_fill_blocked`,
  bridging layers, `PrintObject.config().sparse_infill_pattern`).
- Whether the slicer's own `fill_surfaces` post-processing (Clipper offset
  against perimeters, anchoring) runs before or after `posPrepareInfill`.
- Path continuity: even with correct regions, the applied pattern is the
  built-in one; whether a plugin can produce *its own* polyline set at all is
  the open question the probe's `setattr` attempts answer.
