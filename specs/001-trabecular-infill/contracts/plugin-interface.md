# Contract: Plugin Interface

## Package

```python
@orca.plugin
class BoneInfillPlugin(orca.base):
    def register_capabilities(self): ...
```

Exactly one `@orca.plugin` class per file (verified requirement: the loader
rejects a file whose module registers no package class — our first probe failed
on exactly this).

## Capability

```python
class BoneInfill(orca.slicing.SlicingPipelineCapabilityBase):
    def get_name(self) -> str          # "Trabecular Infill"
    def execute(self, ctx) -> ExecutionResult
```

`get_name()` MUST return a string with no `;` (the preset reference separator).

## Behaviour by step

| `ctx.step` | Behaviour |
| --- | --- |
| `posPrepareInfill` | Read config, validate, carve, replace `fill_surfaces`. |
| every other step | Return `ExecutionResult.success()` immediately, doing no work. |

The capability MUST NOT write to the graph at `posInfill` — fills are already
built and the write would be a silent no-op.

## Return values

| Situation | Return |
| --- | --- |
| Normal slice | `orca.ExecutionResult.success()` |
| No sparse surface on a layer | `orca.ExecutionResult.success()` (skip layer) |
| Direction fallback used | `orca.ExecutionResult.success(msg)` — logged once |
| Strut thickness unprintable | `orca.ExecutionResult.failure(orca.FatalError, msg)` |
| Strut thickness ≤ 0 | `orca.ExecutionResult.failure(orca.FatalError, msg)` |

`FatalError` becomes a `SlicingError`, which the GUI shows as a non-critical
user-visible error and which aborts the slice. That is the only user-visible
channel available to a pipeline hook; `active_step_add_warning()` MUST NOT be
called (it would index `m_state[-1]`).

Exceptions MUST NOT escape `execute()`: a raise becomes a `SlicingError` with a
traceback in the Python log, and the user sees a plugin error instead of a
diagnosis. Wrap the body and convert to a `FatalError` with a one-line message
while logging the traceback.

## Threading

`execute()` runs on the slicing worker thread. `orca.host.ui.*` MUST NOT be
called from it — the UI thread may be blocked waiting on this worker.

## Graph invariants relied upon

1. References from `ctx.print` / `ctx.object` are valid only during
   `execute(ctx)`.
2. `SurfaceCollection.set()` invalidates references previously obtained from
   that collection. Do not use a `Surface` reference after replacing the
   collection.
3. `LayerRegion.fills` is read-only; `fill_surfaces` and `slices` are the only
   mutable entry points.
4. Scaled integer coordinates. Convert to mm with `orca.slicing.unscale()`, which
   reads the live scaling factor; do not hardcode `1e6`.

## Measurement helper contract

`tools/gcode_metrics.py` — standalone, no dependency on the plugin.

```
usage: python3 -I tools/gcode_metrics.py <file.gcode> [--layer N] [--json]

reports per layer:
  layer index, dominant extrusion type
  extrusion move count
  total extrusion length (mm)
  mean and median segment length (mm)
  travel move count and travel share (%)

exit code 0 always; prints "no extrusion data" if the file has none
```

Rationale for `-I`: the script only reads a file passed as an argument, and
`-I` prevents it picking up a planted module from the working directory.
