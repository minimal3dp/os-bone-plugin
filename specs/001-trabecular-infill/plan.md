# Implementation Plan: Trabecular Infill

**Branch**: `001-trabecular-infill` | **Date**: 2026-10-31 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/001-trabecular-infill/spec.md`

## Summary

A single-file OrcaSlicer Python plugin registering one `SlicingPipeline`
capability. At `posPrepareInfill` it takes each layer's sparse fill surfaces,
subtracts a seeded field of ribbon voids oriented to the profile's solid-infill
direction, and replaces the surfaces with the remaining strut network retyped
`stInternalSolid`, so the slicer's own solid infill draws dense trabeculae.

Exposed user parameter: strut thickness (mm). Orientation is read from the
profile, not exposed.

## Technical Context

**Language/Version**: Python 3.12+ (OrcaSlicer's embedded interpreter), PEP 723
single-file plugin, zero third-party dependencies.

**Primary Dependencies**: `orca` embedded module only (`orca.slicing`,
`orca.host` geometry + slicing graph). No numpy: the geometry API returns
`Point` lists and accepts `Point`/`Polygon` objects, so the plugin does not need
array math.

**Storage**: None. Configuration lives in the plugin config API
(`get_default_config()` / `get_config()`), per Constitution Principle VI.

**Testing**: manual slice-and-inspect against the 20 mm cube, plus a G-code
metric script. No test framework is bundled with the plugin; the metric script
is a standalone plain-Python file.

**Target Platform**: OrcaSlicer 2.5.0-rc, build `af2ffb8c`, macOS.

**Project Type**: single-file slicing plugin plus a measurement helper.

**Performance Goals**: no stated budget. Print-time cost is measured and
reported (SC-006), not targeted. Recorded as outstanding in the spec.

**Constraints**:
- Runs on the slicing worker thread; `orca.host.ui.*` MUST NOT be called.
- Graph references valid only inside `execute(ctx)`; stashing them is a bug.
- Container mutators invalidate previously obtained references (C++ vector
  semantics).
- `fills` is read-only; only `fill_surfaces` and `slices` are mutable.

**Scale/Scope**: one capability, one parameter, one test geometry.

## Constitution Check

*GATE: must pass before Phase 0 and re-checked after Phase 1.*

| Principle | Status | Evidence / plan |
| --- | --- | --- |
| I. Measured or cited | PASS | SC-004/SC-006 require measured or exported metrics. No strength claim is made in this plan. |
| II. Minimum viable scope | PASS | One capability, one parameter (`strut_thickness_mm`), one geometry (20 mm cube). |
| III. Printability beats realism | PASS | The algorithm exists to keep raster segments long. Void geometry is chosen for printability, and SC-006 measures the cost. |
| IV. Deterministic | PASS | `random.Random(seed)` fixed in source; seed is an internal constant; no dict-iteration order dependence. |
| V. Pinned version | PASS | Tested build recorded here and required in README by the spec. |
| VI. Config through plugin API | PASS | `get_default_config()` / `get_config()`; no side files (coupon data is a *document*, not plugin config). |

No violations. Complexity is not added beyond one capability.

**Post-Phase-1 re-check**: still PASS. No new surface added.

## Project Structure

### Documentation

```text
docs/
  phase0-findings.md     # probe results, spike, tuning, unresolved raster angle
  research.md            # Phase 2 corpus synthesis
specs/001-trabecular-infill/
  spec.md
  plan.md
  research.md            # this plan's Phase 0 decisions
  data-model.md
  quickstart.md
  contracts/
    plugin-interface.md
  checklists/
    requirements.md
```

### Source

```text
src/os_bone_plugin/
  bone_infill.py         # the plugin: PEP 723 block, capability, package class
tools/
  gcode_metrics.py       # per-layer move/segment/travel metrics from exported G-code
```

The plugin is a single file because the packaging rules require one entry file
per plugin folder, and splitting into a wheel adds build machinery with no
benefit at this size.

## Phase 0: Research

Resolved in [research.md](./research.md). Summary of the decisions that shape
the design:

1. **Hook**: `posPrepareInfill` only. `posInfill` is too late — fills are already
   built. Confirmed by source (`Print.cpp:3463-3473`) and by our own experiment
   (clearing a layer's fill surfaces produced zero infill paths for that layer).
2. **Orientation source**: `solid_infill_direction` (`coFloat`, 0–360, Advanced,
   category "Strength"), read through `ctx.config_value()` / the object config.
   NOT `infill_direction`, which is the *sparse* infill direction and would be
   the wrong reference for a region we retype to solid.
3. **Per-layer rotation**: `solid_infill_rotate_template` exists and rotates the
   solid raster per layer. The plugin MUST mirror it, or struts misalign on every
   layer but the first.
4. **Warning mechanism**: `active_step_add_warning()` is explicitly unusable from
   a pipeline hook (fires after `set_done()`, would index `m_state[-1]`). A
   `FatalError` result becomes a `SlicingError`, which the GUI shows as a
   non-critical, user-visible slicing error. That is the only user-visible
   channel available, and it aborts the slice.
5. **Raster angle**: unverified. Recorded in `docs/phase0-findings.md`. The design
   depends on the *setting*, not on a measured angle, so this does not block
   implementation, but it does block any claim about *why* the tuning result
   looked the way it did.

## Phase 1: Design

### Data model

[data-model.md](./data-model.md).

### Contracts

[contracts/plugin-interface.md](./contracts/plugin-interface.md) — the capability
surface, the config schema, and the graph invariants it relies on.

### Quickstart

[quickstart.md](./quickstart.md) — install, enable, slice, verify, measure.

### Core algorithm (design intent, not final code)

For each layer with sparse fill surfaces:

1. Read orientation from the profile; apply the rotate template for this layer
   index; if absent, use 45° and log once.
2. For the sparse surface's expolygon, lay out ribbon voids: rectangles of
   `half_width = void_half_width` and `half_length = void_half_length`, long axis
   along the orientation, tiled in a lattice rotated into that frame, with a
   seeded jitter.
3. Keep only voids wholly inside the region (`ExPolygon.contains` on the corner
   points).
4. `diff_ex` each kept void from the running piece set.
5. Rebuild `fill_surfaces` with the resulting pieces typed `stInternalSolid`.

Strut thickness is the user parameter and controls the gap between voids. Void
length and width are derived from it by fixed ratios, documented as internal
constants.

### Complexity tracking

No constitution violations, so no complexity justification table is required.
The single-file structure and zero-dependency choice are the lazy option, not a
concession.
