# OrcaSlicer 2.5.2 platform re-pin

Status: **binding audit complete; runtime not re-verified.** No export in `tests/`
was produced by 2.5.2. Every measured number in the repo still comes from
OrcaSlicer 2.5.0-rc build `af2ffb8c` unless stated otherwise.

Method: `git ls-remote --tags https://github.com/OrcaSlicer/OrcaSlicer.git`
followed by raw-file fetch at each tag and `diff -u`. Tags compared:
`v2.5.0-beta` (`345efec64c7b95a05ce5cf96df0dde66a158835c`),
`v2.5.0-rc` (`af2ffb8cddd2f3c0bdadc56d9cc3945fb23577ea`), and
`v2.5.2` (`f92a7c065c5718b8ef1baac1cd704df2911238f4`). The 2.5.2 **build
hash is TBD**: the human must read it from Help > About after installing.

## File-level diff, 2.5.0-rc -> 2.5.2

| File | Change |
| --- | --- |
| `src/slic3r/plugin/host/PluginHostSlicing.cpp` | identical |
| `src/slic3r/plugin/host/PluginHostGeometry.cpp` | identical |
| `src/slic3r/plugin/pluginTypes/slicingPipeline/SlicingPipelinePluginCapability.{hpp,cpp}` | identical |
| `src/slic3r/plugin/pluginTypes/slicingPipeline/SlicingPipelinePluginCapabilityTrampoline.hpp` | identical |
| `src/libslic3r/PrintObject.cpp` | 6 insertions / 3 deletions, belt-printer shrinkage compensation; slicing pipeline untouched |
| `src/libslic3r/Print.cpp` | 157 insertions / 95 deletions, belt/shrinkage and step plumbing; the `posPrepareInfill` / `prepare_infill` / `infill` seam is unchanged |
| `src/slic3r/plugin/PluginLoader.cpp` | 36 insertions / 4 deletions, install-state sidecar recovery and locking |
| `src/slic3r/plugin/PluginFsUtils.cpp` | 309 insertions / 59 deletions, install-state I/O, TOML array parsing, archive-entry path hardening |
| `src/slic3r/plugin/PythonPluginBridge.cpp` | permission `threading` shape (list -> bool); `ExecutionResult` and config bindings unchanged |
| `src/slic3r/plugin/PythonPluginInterface.hpp` | identical |
| `src/slic3r/plugin/PythonInterpreter.cpp` | identical |

Plugin loading rules are unchanged in substance: one entry file per plugin
folder, `.install_state.json` sidecar, ignored folder prefixes. 2.5.2 adds
recovery for an unparsable sidecar (`PluginLoader.cpp:263-288`) and safer
install-state writes, not a new packaging rule.

## Bindings the plugin uses

Line numbers are in the **v2.5.2** files. "Unchanged" means the binding text is
byte-identical between `v2.5.0-rc` and `v2.5.2` unless a different file is named.

| Binding | Status in 2.5.2 | Citation |
| --- | --- | --- |
| `orca.host.Surface` constructor | unchanged | `PluginHostSlicing.cpp:114-117` |
| `orca.host.SurfaceType.stInternalSolid` | unchanged | `PluginHostSlicing.cpp:96-102` |
| `SurfaceCollection.set(surfaces)` | unchanged | `PluginHostSlicing.cpp:144-148` |
| `SurfaceCollection.surfaces` | unchanged | `PluginHostSlicing.cpp:162` |
| `ExPolygon.diff_ex` | unchanged | `PluginHostGeometry.cpp:219-221` |
| `ExPolygon.intersection_ex` | unchanged | `PluginHostGeometry.cpp:222-224` |
| `ExPolygon.area` | unchanged | `PluginHostGeometry.cpp:208` |
| `ExPolygon.contour` | unchanged | `PluginHostGeometry.cpp:179` |
| `orca.host.Polygon` | unchanged | `PluginHostGeometry.cpp:107` |
| `orca.host.Point` | unchanged | `PluginHostGeometry.cpp:94` |
| `ctx.config_value` | unchanged | `SlicingPipelinePluginCapability.cpp:80-90` |
| `LayerRegion.config_value` | unchanged | `PluginHostSlicing.cpp:269-270` |
| `orca.slicing.unscale` | unchanged | `SlicingPipelinePluginCapability.cpp:50-51` |
| `orca.ExecutionResult.failure` | unchanged | `PythonPluginBridge.cpp:461`; struct `PythonPluginInterface.hpp:106-125` |
| `orca.FatalError` | unchanged | `PythonPluginBridge.cpp:391` |
| capability `get_config` | unchanged | `PythonPluginBridge.cpp:496-503` |
| capability `get_default_config` | unchanged | `PythonPluginBridge.cpp:485-495` |

**Verdict: no binding the plugin uses is changed or removed in 2.5.2.** The
Python-side bridge diff is the `threading` permission type only, which this
plugin does not request.

The seam is also unchanged. `prepare_infill()` runs, then the
`posPrepareInfill` hook fires, then `infill()`:

```cpp
// Print.cpp:3518-3525 (v2.5.2)
const bool prepare_was_done = obj->is_step_done(posPrepareInfill);
obj->prepare_infill();
hook_after(obj, prepare_was_done, posPrepareInfill, SlicingPipelineStepPlugin::posPrepareInfill);
const bool was_done = obj->is_step_done(posInfill);
obj->infill();
hook_after(obj, was_done, posInfill, SlicingPipelineStepPlugin::posInfill);
```

## PRs 17599 / 17600: narrow solid infill can be skipped and logged

Both merged 2026-11-18 and are present in the 2.5.2 tree.

- PR 17599 fixes an `int64` overflow in Arachne outline simplification when two
  nearly parallel lines meet metres away. It is a correctness fix, not a new
  skip.
- PR 17600 adds the skip. If Boost Voronoi construction leaves the diagram
  invalid after its repair attempt, `SkeletalTrapezoidation::constructFromPolygons`
  logs and returns an empty graph. No toolpaths are generated for that outline.

Exact message:

```
Arachne: invalid Voronoi diagram, no toolpaths generated for this outline.
```

Source: `src/libslic3r/Arachne/SkeletalTrapezoidation.cpp:390-394` (v2.5.2).
This is `BOOST_LOG_TRIVIAL(error)`, so it goes to the **debug log**
(`<data_dir>/log/debug_*.log.0`), not the Python log. The Python log will not
contain it.

Trigger:

```cpp
// SkeletalTrapezoidation.cpp:386-394 (v2.5.2)
VD voronoi_diagram;
voronoi_diagram.construct_voronoi(segments.cbegin(), segments.cend());
if (!voronoi_diagram.is_valid()) {
    BOOST_LOG_TRIVIAL(error) << "Arachne: invalid Voronoi diagram, no toolpaths generated for this outline.";
    return;
}
```

Why this plugin is exposed: OrcaSlicer forces narrow `stInternalSolid` regions
to `ipConcentricInternal` when `detect_narrow_internal_solid_infill` is on:

```cpp
// Fill.cpp:1266-1283 (v2.5.2)
if (layer.object()->config().detect_narrow_internal_solid_infill) {
    ...
    surface_fills[i].params.pattern = ipConcentricInternal;
```

and `ipConcentricInternal` is the path that uses Arachne walls
(`Fill.cpp:1430-1431`; `FillConcentricInternal.cpp:48` constructs
`Arachne::WallToolPaths`). Our carved struts are long, thin `stInternalSolid`
strips, exactly the input class in the regression test added by PR 17599
(`tests/libslic3r/test_arachne_walls.cpp`, "Arachne toolpaths stay inside a
nearly straight notched strip"). A skip would drop strut toolpaths for that
outline while the slice still succeeds. Validation V1 must therefore grep the
debug log for the message above.

The 2.5.0-rc tree has no validity check and no such message: it built the graph
from the invalid diagram and could crash instead.

## PR 16884: stale plugin manifest

Merged 2026-11-11, so it is in 2.5.1 and 2.5.2. When the preset's derived
`plugins` manifest has no entry for a configured capability,
`execute_capabilities_from_refs()` now resolves that capability by name from
the loaded plugins instead of skipping the step:

```cpp
// PluginManager.hpp:494-509 (v2.5.2)
if (!ref) {
    ref = plugin_mgr.resolve_capability_ref(capability, type);
    if (ref)
        BOOST_LOG_TRIVIAL(warning) << tag << ": capability '" << capability
                                   << "' missing from the plugins manifest; resolved by name";
}
if (!ref) {
    BOOST_LOG_TRIVIAL(warning) << tag << ": no plugin reference found for capability '"
                               << capability << "'; skipping";
    continue;
}
```

`PluginManager::resolve_capability_ref` is at `PluginManager.cpp:555-574`
(v2.5.2). The 2.5.0-rc tree has no fallback; it goes straight to the
"no plugin reference found" skip.

Effect on the quickstart: the **set-picker-to-empty-then-select** step is no
longer required on 2.5.2. It remains harmless. If the manifest is stale, the
debug log shows the "resolved by name" warning instead of silently skipping the
plugin. The old warning is still reachable when the capability is genuinely not
loaded.

## Proposed constitution amendment

Do **not** apply this here. It is a draft for the project owner to ratify after
installing 2.5.2 and reading the build hash from Help > About. Replace
`<TBD>` with that hash.

Affected principle: **V. Pinned Platform Version** (PATCH: a version and build
reference change, no principle redefinition).

```diff
--- a/.specify/memory/constitution.md
+++ b/.specify/memory/constitution.md
@@
-- Tested build: OrcaSlicer **2.5.0-rc** at `/Applications/OrcaSlicer 2.app`,
-  build `af2ffb8c`, macOS. This is the only supported target for the MVP.
+- Tested build: OrcaSlicer **2.5.2** at `/Applications/OrcaSlicer 2.app`,
+  build `<TBD>`, macOS. This is the only supported target for the MVP.
+  Exports dated before the 2.5.2 re-verification come from 2.5.0-rc build
+  `af2ffb8c`; any measured number taken from them MUST keep that label.
@@
-**Version**: 1.0.0 | **Ratified**: 2026-10-31 | **Last Amended**: 2026-10-31
+**Version**: 1.0.1 | **Ratified**: 2026-10-31 | **Last Amended**: <date of ratification>
```

Rationale for a PATCH bump: the pin is a factual reference, not a change to the
rule. The added sentence enforces Principle I on the existing 2.5.0-rc
artifacts rather than relaxing it.
