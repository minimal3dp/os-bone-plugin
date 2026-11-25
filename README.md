# Trabecular Infill

An OrcaSlicer slicing-pipeline plugin that replaces a part's sparse infill
region with a bone-like network of dense struts separated by aligned voids.

At the `posPrepareInfill` hook the plugin takes each layer's sparse `stInternal`
surfaces, subtracts a seeded lattice of ribbon voids, and replaces the surface
list with the remaining struts retyped `stInternalSolid`. OrcaSlicer's own solid
infill then draws the struts.

## API limit

The plugin controls **where infill may exist**, not **which strokes are drawn**.
`LayerRegion.fills` has no mutator in the plugin API, so the plugin cannot
replace infill polylines. It changes the region the slicer later fills with its
built-in pattern.

## Target build

- Target: OrcaSlicer **2.5.2**, build `<TBD>` (read it from Help > About).
- The bindings were re-audited against 2.5.2 in
  [`docs/platform-2.5.2.md`](docs/platform-2.5.2.md).
- Measured numbers to date come from OrcaSlicer **2.5.0-rc** build `af2ffb8c`.
  They are not 2.5.2 results.

## Install

```sh
mkdir -p "$HOME/Library/Application Support/OrcaSlicer/orca_plugins/os-bone-plugin"
cp src/os_bone_plugin/bone_infill.py \
   "$HOME/Library/Application Support/OrcaSlicer/orca_plugins/os-bone-plugin/bone_infill.py"
```

One `.py` per plugin folder. Two entry files, or a `.py` beside a `.whl`, makes
the plugin unloadable.

## Enable

1. Restart OrcaSlicer (discovery runs at startup).
2. **File > Plugins** → **Trabecular Infill** → enable the capability.
3. Process settings → G-code section → **Slicing Pipeline Plugin** → select
   **Trabecular Infill**.

On 2.5.2 no empty-then-select dance is needed: a stale preset manifest is
resolved by capability name at slice time (PR 16884). The step is harmless if
you do it anyway. On 2.5.0-rc the empty-then-select order was required.

## Permissions

The plugin requests **none**: no filesystem access, no network access, and no
process execution. It declares no third-party dependencies.

## Parameter

There is exactly one user-facing parameter:

| Key | Meaning |
| --- | --- |
| `strut_thickness_mm` | Thickness of the material left between voids. Default `1.2` mm. |

The printable minimum is resolved at slice time as **2 × the internal-solid
infill line width** from the active profile. A value below it fails slicing with
a user-visible error that names both the supplied value and the minimum. Void
size is absolute and internal; the strut thickness sets the gap between voids,
and therefore density.

## Measured cost

See [`docs/print-cost.md`](docs/print-cost.md).
