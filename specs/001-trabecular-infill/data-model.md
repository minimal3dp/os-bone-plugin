# Data Model — Trabecular Infill

The plugin holds no persisted state. Everything below is either a live reference
into the slicing graph (valid only inside `execute(ctx)`) or a value derived
from configuration.

## Configuration (plugin-owned, via `get_default_config()`)

| Key | Type | Default | Bounds | Meaning |
| --- | --- | --- | --- | --- |
| `strut_thickness_mm` | float | 1.2 | > 0 | Thickness of the material left between voids. The single user-facing parameter (FR-002). |

Validation rule: values below the printable minimum are accepted but produce a
`FatalError` result naming the value and the minimum (FR-004, FR-004a).

Minimum is derived at runtime, not hardcoded: `2 × internal_solid_infill_line_width`
as resolved from the profile. Rationale: the strut is drawn by the internal-solid
raster, so its printable width is bounded by that raster's line width.

`internal_solid_infill_line_width` is a `FloatOrPercent` whose `ratio_over` is
**nozzle_diameter**, not the base `line_width` (`PrintConfig.cpp:6856`). A value
of `0` means unset, in which case base `line_width` applies (also a percentage
over the nozzle). The plugin MUST resolve the percentage against the nozzle
diameter; reading it as a raw number is wrong by a factor of 100.

## Internal constants (not user-facing)

| Constant | Default | Meaning |
| --- | --- | --- |
| `VOID_LENGTH_MM` | 8.5 | Half-length of each ribbon void, in millimetres. Absolute, not derived from strut thickness. |
| `VOID_WIDTH_MM` | 0.6 | Half-width of each ribbon void, in millimetres. Absolute, not derived from strut thickness. |
| `LATTICE_JITTER` | 0.15 | Fraction of lattice spacing the centre may deviate. |
| `SEED` | 1234 | Fixed. Changing it changes the structure without changing density. |
| `DEFAULT_DIRECTION_DEG` | 45.0 | Fallback orientation when the profile supplies none (FR-002b). |

Void size is absolute; `strut_thickness_mm` sets only the gap between voids
(and therefore density). The earlier ratio form tied void size to strut
thickness, so raising the strut enlarged the voids until none fitted; round-2
tuning in `docs/phase0-findings.md` replaced it.

## Read from the slicing graph (per layer)

| Source | Type | Used for |
| --- | --- | --- |
| `LayerRegion.fill_surfaces` | `SurfaceCollection` | The surfaces to inspect and replace (mutable). |
| `Surface.expolygon` | `ExPolygon` | The region to carve. |
| `Surface.surface_type` | `SurfaceType` | Select `stInternal` that is not solid. |
| `Surface.is_internal()` / `is_solid()` | bool | Sparse-vs-solid classification. |
| `Layer.print_z` / `height` | float | Layer identification in logs. |

## Read from configuration

| Key | Source | Used for |
| --- | --- | --- |
| `solid_infill_direction` | profile (region config) | Void orientation (FR-002a). |
| `solid_infill_rotate_template` | profile | Per-layer rotation override. |
| `internal_solid_infill_line_width` | profile | Printable-minimum computation. Percentage resolves over `nozzle_diameter`. |
| `nozzle_diameter` | profile | Base for resolving the percentage above. |

## Written to the slicing graph (per layer)

`LayerRegion.fill_surfaces.set(surfaces)` — the replacement list. Each produced
strut piece is a `Surface(stInternalSolid, expolygon)`.

**Invariant**: surfaces not classified as sparse `stInternal` (top, bottom,
bridges, perimeters, already-solid) are passed through unchanged, preserving
order (FR-007).

**Lifetime rule**: every reference obtained from the graph is used within the
same `execute(ctx)` call. Nothing is cached across calls except plain Python
values (layer indices, counts, the logged-once flag).

## State transitions

The capability is stateless across slices except for a "logged once" flag for
the direction-fallback message. That flag is reset when the capability is
unloaded, so a configuration change is reported again.

## Validation rules

1. A layer with no sparse `stInternal` surface is skipped entirely.
2. A void whose corners are not all inside the region is discarded — partial
   voids would leave slivers.
3. A carve that yields zero pieces is treated as a failure for that layer and the
   original surfaces are restored, rather than blanking the layer.
4. Strut thickness ≤ 0 is rejected with a `FatalError`.
