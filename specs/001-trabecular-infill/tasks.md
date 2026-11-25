# Tasks: Trabecular Infill

**Input**: Design documents from `specs/001-trabecular-infill/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: No test framework is requested by the spec. Verification is by slice,
inspection, and the G-code metric script — see `quickstart.md`. Two runtime
*verification* tasks are included (T004, T005) because two design decisions in
`research.md` are unverified and everything else depends on them.

**Organization**: Tasks grouped by user story.

## Path Conventions

Single project: plugin at `src/os_bone_plugin/bone_infill.py`, helper tools at
`tools/`, exported samples at `tests/`.

---

## Phase 1: Setup

**Purpose**: Files and folders the plugin needs to exist at all.

- [X] T001 Create `src/os_bone_plugin/bone_infill.py` with the PEP 723 metadata block: `requires-python = ">=3.12"`, `dependencies = []`, and `[tool.orcaslicer.plugin]` with name `Trabecular Infill`, description, author, version `0.1.0`
- [X] T002 Add module skeleton to `src/os_bone_plugin/bone_infill.py`: `import orca`, a `log()` helper writing to `sys.stderr` with a `[bone_infill]` prefix, and the internal constants `VOID_LENGTH_RATIO = 5.5`, `VOID_WIDTH_RATIO = 1.0`, `LATTICE_JITTER = 0.15`, `SEED = 1234`, `DEFAULT_DIRECTION_DEG = 45.0`
- [X] T003 [P] Create `tools/gcode_metrics.py` as a standalone script per the contract in `specs/001-trabecular-infill/contracts/plugin-interface.md`: per-layer extrusion move count, total extrusion length, mean and median segment length, travel move count and travel share; `--layer N` and `--json` flags; accepts the G-code path as an argument only

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Prove the two unverified assumptions before building on them. Both
come from `research.md` D2 and D3. **Do not start user stories until these pass.**

**⚠️ CRITICAL**: T004 and T005 each require a slice and a log reading.

- [X] T004 Verify `solid_infill_direction` is readable through the config API at `posPrepareInfill` — add a temporary capability in `src/os_bone_plugin/bone_infill.py` that logs `ctx.config_value("solid_infill_direction")`, `ctx.object.config_value("solid_infill_direction")`, and `ctx.object.layers()[0].regions()[0].config_value("solid_infill_direction")` at `posPrepareInfill`; install, slice, read the Python log. Record which accessor returns `45` (or none) in `specs/001-trabecular-infill/research.md` under D2. **If none returns a value, stop: FR-002a cannot be met as written and the spec needs amending.**
- [X] T005 Verify `solid_infill_rotate_template` indexing — set the profile value to `0,90`, slice the 20 mm cube with the same temporary capability in `src/os_bone_plugin/bone_infill.py` logging the layer index and the resolved direction per layer, and confirm from the exported G-code whether the rotation is applied per object layer or per print layer. Record the answer in `specs/001-trabecular-infill/research.md` under D3.
- [X] T006 Implement the capability shell in `src/os_bone_plugin/bone_infill.py`: `BoneInfill(orca.slicing.SlicingPipelineCapabilityBase)` with `get_name()` returning `"Trabecular Infill"` (no `;` character), an `execute(self, ctx)` that returns `orca.ExecutionResult.success()` immediately unless `ctx.step == orca.slicing.Step.posPrepareInfill`, and the `@orca.plugin` package class calling `orca.register_capability(BoneInfill)`
- [X] T007 Wrap the `execute()` body in `src/os_bone_plugin/bone_infill.py` so no exception escapes: catch, log the full traceback via `traceback.format_exc()`, and return `orca.ExecutionResult.failure(orca.FatalError, "<one-line message>")` per the contract
- [X] T008 Implement config plumbing in `src/os_bone_plugin/bone_infill.py`: `get_default_config()` returning `{"strut_thickness_mm": 1.2}` and a read of the same through the capability's config accessor; reject `strut_thickness_mm <= 0` with `orca.ExecutionResult.failure(orca.FatalError, ...)`

**Checkpoint**: config reads proven, capability loads, errors contained.

---

## Phase 3: User Story 1 - Choose trabecular infill and slice (Priority: P1) 🎯 MVP

**Goal**: A user enables the capability, slices, and gets dense struts separated
by voids on interior layers, deterministically.

**Independent Test**: Enable, slice the 20 mm cube, inspect the preview and the
exported G-code. Validate via `quickstart.md` V1 and V2.

- [X] T009 [US1] Implement direction resolution in `src/os_bone_plugin/bone_infill.py`: read the value proven in T004, apply the rotate template from T005 for the current layer index, fall back to `DEFAULT_DIRECTION_DEG` and log once per capability lifetime when neither yields a value (FR-002a, FR-002b)
- [X] T010 [US1] Implement sparse-surface selection in `src/os_bone_plugin/bone_infill.py`: for each `LayerRegion`, iterate `fill_surfaces.surfaces` and classify a surface as sparse when `is_internal()` is true and `is_solid()` is false; leave every other surface untouched and in order (FR-005, FR-007)
- [X] T011 [US1] Implement void layout in `src/os_bone_plugin/bone_infill.py`: tile ribbon rectangles in a lattice rotated into the resolved direction frame, with half-length `strut_thickness_mm * VOID_LENGTH_RATIO * 1e6`, half-width `strut_thickness_mm * VOID_WIDTH_RATIO * 1e6`, spacing derived from the two plus the strut gap, and centres jittered by `LATTICE_JITTER` from `random.Random(SEED)` (FR-001, FR-003)
- [X] T012 [US1] Implement interior filtering in `src/os_bone_plugin/bone_infill.py`: discard any void whose corner points are not all `ExPolygon.contains(...)` — build void outlines as plain `(x, y)` tuples because `orca.host.Polygon` is not iterable; construct `orca.host.Polygon` only when building the hole `ExPolygon`
- [X] T013 [US1] Implement carving and replacement in `src/os_bone_plugin/bone_infill.py`: subtract each kept void with `piece.diff_ex(hole)`, accumulate pieces, and call `LayerRegion.fill_surfaces.set([orca.host.Surface(orca.host.SurfaceType.stInternalSolid, p) for p in pieces] + untouched_surfaces)`; if a layer yields zero pieces, restore the original surfaces rather than blanking the layer (FR-001)
- [X] T014 [US1] Guard against layers with no sparse surface in `src/os_bone_plugin/bone_infill.py`: return success and skip, performing no `fill_surfaces.set(...)` call (FR-005)
- [X] T015 [US1] Run `specs/001-trabecular-infill/quickstart.md` V1: install `src/os_bone_plugin/bone_infill.py` to `<data_dir>/orca_plugins/os-bone-plugin/bone_infill.py`, export to `tests/`, confirm both plugin manifest lines appear in the G-code, and confirm one interior layer carries `Internal solid infill` beyond the native shells
- [X] T016 [US1] Run `specs/001-trabecular-infill/quickstart.md` V2: slice seven times into `tests/`, confirm a single unique sha256 across all seven exports (SC-002)

**Checkpoint**: User Story 1 complete and independently verifiable.

---

## Phase 4: User Story 2 - Adjust strut thickness (Priority: P2)

**Goal**: One parameter changes strut width and material use monotonically, and an
unprintable value is refused visibly.

**Independent Test**: Slice at two thicknesses and compare estimated material use;
slice below the minimum and observe the GUI error. `quickstart.md` V3, V4, V5.

- [X] T017 [US2] Derive the printable minimum in `src/os_bone_plugin/bone_infill.py` at runtime as `2 * internal_solid_infill_line_width`, never a hardcoded constant. That key is a `FloatOrPercent` over `nozzle_diameter` (NOT over `line_width`); resolve `125%` against the nozzle, and treat `0` as unset and fall back to base `line_width`. Unscale via `orca.slicing.unscale()` rather than assuming `1e6`
- [X] T018 [US2] Reject an unprintable `strut_thickness_mm` in `src/os_bone_plugin/bone_infill.py` by returning `orca.ExecutionResult.failure(orca.FatalError, msg)` where `msg` names both the supplied value and the minimum (FR-004, FR-004a). Do NOT call `active_step_add_warning()` — it would index `m_state[-1]`
- [ ] T019 [US2] Run `specs/001-trabecular-infill/quickstart.md` V3: slice into `tests/` at `solid_infill_direction = 45` and at `= 0`, confirm the void orientation differs between the two exports (SC-007, FR-002a)
- [ ] T020 [US2] Run `specs/001-trabecular-infill/quickstart.md` V4: force the direction setting absent, confirm three things — slicing completes, structure appears at 45 degrees, and exactly one fallback line appears in the Python log (FR-002b)
- [ ] T021 [US2] Run `specs/001-trabecular-infill/quickstart.md` V5: set a thickness below `2 * internal_solid_infill_line_width`, confirm a user-visible GUI error naming both values, observed directly rather than inferred from the log (SC-008, FR-004)
- [ ] T022 [US2] Verify SC-005: slice at two thicknesses and confirm the larger value never yields lower estimated material use; record both estimates in `docs/print-cost.md`

**Checkpoint**: User Stories 1 and 2 both work independently.

---

## Phase 5: User Story 3 - Compare against gyroid at matched weight (Priority: P3)

**Goal**: Produce the measured evidence the whole claim rests on.

**Independent Test**: A printed coupon pair, weighed and compression tested, with
a record stating masses, values, and conditions. `quickstart.md` V6, V7.

- [ ] T023 [US3] Run `quickstart.md` V6: run `tools/gcode_metrics.py` against the carved G-code and a gyroid control, and record move count, mean segment length, and travel share for both in `docs/print-cost.md` (SC-006)
- [ ] T024 [US3] Run `quickstart.md` V7: print the 20 mm cube with trabecular infill on a stock profile, photograph the finished part, and record the photo path and profile in `docs/print-cost.md` (SC-003)
- [ ] T025 [US3] Produce the coupon pair per the Coupon procedure in `specs/001-trabecular-infill/quickstart.md`: slice trabecular and gyroid coupons, iterate the gyroid density, print both, and weigh both to establish matched mass within a stated tolerance (FR-010a)
- [ ] T026 [US3] Compression test both coupons under identical conditions and record in `docs/coupon-results.md`: measured masses, measured failure load and/or peak stress, coupon dimensions, printer, profile, filament, test method, and the date (SC-004)
- [ ] T027 [US3] State in `docs/coupon-results.md` whether the pair actually matched within tolerance; if it did not, report the real masses and do not present the comparison as matched-weight (FR-010a, US3 scenario 3)

**Checkpoint**: Evidence exists. Any strength claim can now cite it — or must not be made.

---

## Phase 6: Polish & Cross-Cutting

- [ ] T028 [P] Write `README.md` at repository root: what the plugin does, the tested build (OrcaSlicer 2.5.0-rc, build `af2ffb8c`), install steps from `quickstart.md`, the single parameter, and the measured-vs-claimed distinction for any numbers quoted (Principle I, Principle V)
- [ ] T029 [P] Remove the temporary verification logging added in T004 and T005 from `src/os_bone_plugin/bone_infill.py`, leaving only the production log lines
- [ ] T030 Run the full `specs/001-trabecular-infill/quickstart.md` sequence end to end on a clean install and confirm every scenario passes or is explicitly recorded as failing
- [ ] T031 Review `src/os_bone_plugin/bone_infill.py` for leftover scaffolding: no unused constants, no dead branches, no debug prints outside the `log()` helper

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: no dependencies
- **Phase 2 (Foundational)**: after Setup — **blocks all user stories**
- **Phase 3 (US1, P1)**: after Foundational
- **Phase 4 (US2, P2)**: after Foundational; T019/T020/T021 need US1's structure to exist, so effectively after Phase 3
- **Phase 5 (US3, P3)**: after Phase 4 — coupons require a working, tunable structure
- **Phase 6 (Polish)**: after the stories that are being shipped

### Hard orderings inside the work

- T004 and T005 before T009 — direction handling depends on both answers
- T009 before T011 — the void lattice is built in the resolved frame
- T011 before T012 before T013 — layout, filter, carve
- T013 before T015/T016 — no point slicing before replacement works
- T017 before T018 — the minimum must be derived before it can be enforced
- T025 before T026 before T027 — weigh before testing, record after

### Parallel Opportunities

- T001, T002, T003 are independent (different files)
- T004 and T005 are independent probes but both need a slice; run them together in one slice by logging both values
- T028 and T029 are independent of each other
- T023 and T024 are independent

---

## Parallel Example: Phase 1

```bash
Task: "Create PEP 723 metadata block in src/os_bone_plugin/bone_infill.py"
Task: "Create tools/gcode_metrics.py per the plugin-interface contract"
```

---

## Implementation Strategy

### MVP first

Phase 1 → Phase 2 → Phase 3. Stop at T016 and validate. That is a working
plugin that produces deterministic trabecular infill and can be seen in the
preview. Everything after adds control or evidence, not function.

### Critical stop point

**T004 is a genuine gate.** If `solid_infill_direction` is not readable through
the config API at the hook, FR-002a cannot be implemented as specified. Stop and
amend the spec rather than substituting a hardcoded angle — a hardcoded angle
would silently violate the user's own setting.

### Notes

- Commit after each task or logical group
- Stop at every checkpoint to validate independently
- Never write a number into `README.md` or `docs/` without naming its artifact
  (Principle I, Review Gate)
- Avoid: adding a second parameter, hardcoding `1e6`, calling `orca.host.ui.*`
  from the capability, stashing graph references across `execute()` calls
