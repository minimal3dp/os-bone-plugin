# Phase 0 Research — Trabecular Infill

Every entry below was resolved by reading OrcaSlicer source at tag
`v2.5.0-beta`, not by assumption. Where something remains unverified it says so.

## D1. Which pipeline step to hook

**Decision**: `orca.slicing.Step.posPrepareInfill` only. The capability returns
early at every other step.

**Rationale**: `Print.cpp:3463-3473` splits the two steps deliberately:

```cpp
obj->prepare_infill();
hook_after(obj, ..., posPrepareInfill);   // edit fill_surfaces HERE -> cascades
obj->infill();
hook_after(obj, ..., posInfill);          // fills already built
```

The source comment states the split exists so a plugin can mutate fill surfaces
at the PrepareInfill seam and have `make_fills` consume them.

**Confirmed empirically**: clearing one layer's `fill_surfaces` at
`posPrepareInfill` produced zero infill paths for that layer at `posInfill`
(`docs/phase0-findings.md`).

**Alternatives rejected**: `posInfill` (too late, verified no-op),
`psGCodePostProcess` (loses region geometry, cannot be previewed).

## D2. Which direction setting drives orientation

**Decision**: `solid_infill_direction`.

**Rationale**: `PrintConfig.cpp:3661` — `coFloat`, label "Solid infill
direction", category "Strength", range 0–360, `comAdvanced`. Declared on the
print-region config struct (`PrintConfig.hpp:1472`), so `ctx.config_value()`
resolves it.

The region we produce is retyped `stInternalSolid` and filled by the **solid**
raster, so the solid direction is the correct reference.

**Alternatives rejected**:
- `infill_direction` (`PrintConfig.cpp:3651`) — labelled "**Sparse** infill
  direction". It governs the pattern we are removing, not the one that draws our
  struts. Using it would align our voids to a raster that no longer applies.
- `top_layer_direction` / `bottom_layer_direction` (`min = -1`, "follow the
  default solid infill direction") — they default to following, and only affect
  first/last layers.

**Unverified**: that the value is readable through `ctx.config_value()` at
`posPrepareInfill`. It appears in the exported header
(`; solid_infill_direction = 45`) and is declared on the region config, which is
what `LayerRegion.config_value()` reads. The first implementation task must
confirm this at runtime before the rest is built on it.

## D3. Per-layer raster rotation

**Decision**: mirror `solid_infill_rotate_template` if it is non-empty.

**Rationale**: `PrintConfig.cpp` — "adds a rotation of solid infill direction to
each layer according to the specified template… a comma-separated list of angles
in degrees, e.g. '0,90'… repeated when the list ends."

If a user sets a rotation template and the plugin ignores it, struts align on
layer 1 and misalign on every subsequent layer — silently. This is a correctness
requirement, not a nicety.

**Implementation note**: template parsing must handle the plain comma form.
The *sparse* template additionally documents `+5` and `+5#5` syntax; the solid
template tooltip documents only the comma form. Parse the comma form; treat
anything unparseable as "no rotation" and log.

**Unverified**: whether the template is applied by layer index within the
object or globally within the print. Must be confirmed during implementation
against a two-value template and the exported G-code.

## D4. How to warn about an unprintable strut thickness

**Decision**: return `orca.ExecutionResult.failure(orca.FatalError, message)`,
which becomes a `SlicingError` surfaced by the GUI. The slice stops.

**Rationale**: `PluginHooks.cpp:120-122` maps `PluginResult::FatalError` to
`throw SlicingError(...)`. `BackgroundSlicingProcess.cpp:75-77` treats
`SlicingError` as **non-critical** (no crash dialog), and
`format_error_message()` (`:113-115`) puts `ex.what()` into the user-visible
error string.

**Explicitly unusable**: `active_step_add_warning()`. `PluginHooks.cpp:123-127`
states pipeline hooks fire *after* `set_done()`, so `m_step_active == -1` and the
call would index `m_state[-1]` — out of bounds in Release.

**Known cost, stated honestly**: this aborts the whole slice rather than
producing a part with a warning attached. The spec's FR-004a permits slicing to
continue with a visible indication, so this satisfies "user-visible" but is
stricter than required. If slice-abort proves annoying in use, the alternative
is a non-empty `ExecutionResult.success(message)`, which is logged only
(`PluginHooks.cpp:128-137`) — *not* user-visible, so it would not satisfy
FR-004/SC-008. There is no third option without upstream change.

## D5. Geometry API available inside the hook

**Decision**: use only `orca.host` geometry: `Polygon`, `Point`, `ExPolygon`,
`Surface`, `SurfaceType`.

**Rationale**: verified live in the probe run. `ExPolygon.offset/diff_ex/
union_ex/intersection_ex` and `Polygon.append` all work at runtime.

**Corrections to earlier assumptions**, found the hard way:
- `orca.host.Polygon` is **not iterable** — no `__iter__`. Keep pore outlines as
  plain `(x, y)` tuples and build a `Polygon` only when constructing an
  `ExPolygon`.
- `PrintObject.id` is a **method**, not a property.
- `ExPolygon.contour.points` returns a list of `Point`, not a numpy array.

**Alternatives rejected**: numpy. It is available, but the geometry API accepts
`Point` and `(N,2)` int64 arrays, and the plugin does no array math, so adding
the dependency buys nothing.

## D6. Determinism

**Decision**: `random.Random(SEED)` with `SEED` a fixed module constant, and
per-layer jitter drawn in a fixed order.

**Rationale**: Constitution Principle IV. `random.Random` is a Mersenne Twister
with a stable algorithm across CPython versions for a given seed, and the plugin
runs inside one embedded interpreter, so cross-machine variation is not a factor
here. (The upstream PR used `std::mt19937_64` directly for the same reason.)

**Constraint**: no iteration over a `set` or unsorted `dict` where order affects
the draw.

## D7. What "matched weight" requires

**Decision**: a separate measurement record; the plugin itself does not
implement coupon generation.

**Rationale**: FR-010a requires measured printed mass and a stated tolerance.
That is experimental procedure, not plugin behaviour. The plugin produces the
geometry; the record documents the result. `quickstart.md` carries the procedure.

**Alternative rejected**: building coupon generation into the plugin. It would
add a second mode to a minimum-scope MVP (Principle II).

## D8. Raster angle — unresolved

**Status**: open. See `docs/phase0-findings.md`, section "Unresolved: raster
angle".

**Impact on this plan**: none on implementation, because the design reads the
*setting* rather than assuming an angle. It does block any claim explaining the
tuning result by raster alignment. Do not write that explanation into code
comments or the README as fact.
