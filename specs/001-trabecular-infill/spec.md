# Feature Specification: Trabecular Infill

**Feature Branch**: `001-trabecular-infill`

**Created**: 2026-10-31

**Status**: Draft

**Input**: User description: "A bone-inspired (trabecular) infill plugin for OrcaSlicer 2.5.0-beta that carves raster-aligned slot voids out of each layer's sparse fill region at the posPrepareInfill slicing hook, retyping the remaining strut network as stInternalSolid so the slicer's own solid infill draws dense trabeculae. One algorithm (raster-aligned slot field), one user-facing parameter (trabecular strut thickness), one test geometry (20 mm cube). Must be deterministic from a seed. Acceptance requires compression coupons printed at matched weight against a gyroid control, measured on the author's printers, because no measured FDM compression data for bone-inspired infill currently exists."

## Clarifications

### Session 2026-10-31

- Q: When the print profile has no usable raster-angle setting, what should the trabecular structure fall back to? → A: Fall back to 45° and log the assumption.
- Q: How should the user be told that their chosen strut thickness is too thin to print reliably? → A: User-visible slicing warning naming the value and the threshold.
- Q: For the matched-weight comparison, how should the gyroid control be matched to the trabecular coupon? → A: Measure actual printed mass of both, report it, and iterate the control until within a stated tolerance.


## User Scenarios & Testing *(mandatory)*

### User Story 1 - Choose trabecular infill and slice (Priority: P1)

A user who wants bone-like internal structure selects the plugin's capability for
slicing in their print profile and slices a part. Without changing anything else,
the interior of that part is filled with a network of dense struts separated by
aligned voids instead of the stock sparse pattern. The user sees this in the
slicer's normal preview before printing and can confirm the structure is what they
asked for.

**Why this priority**: Without this there is no product. Everything else —
measurement, tuning, comparison — depends on a user being able to produce a
trabecular-filled part on demand.

**Independent Test**: Enable the capability, slice the standard test cube, and
inspect the preview. The interior shows dense strut walls rather than a sparse
lattice. This delivers value on its own: a previewable, printable trabecular part.

**Acceptance Scenarios**:

1. **Given** a part with sparse infill enabled and density above zero, **When**
   the user slices with the capability selected, **Then** the preview shows dense
   struts separated by voids on interior layers, and the exported G-code contains
   the strut regions as solid infill.
1. **Given** the same part and settings, **When** the user slices twice, **Then**
   the two exported G-code files are byte-identical.
2. **Given** a user who wants struts along a particular direction, **When** they
   change the profile's infill-direction setting and re-slice, **Then** the strut
   and void orientation follows that setting rather than staying fixed.
3. **Given** a profile with no usable infill-direction value, **When** the user
   slices, **Then** slicing completes, the structure is oriented at 45 degrees,
   and the assumption is logged.
4. **Given** a part with sparse infill density at zero, **When** the user slices,
   **Then** slicing completes without error and no trabecular structure is
   produced (there is no sparse region to carve).

---

### User Story 2 - Adjust strut thickness (Priority: P2)

A user wants to trade material for strength. They change a single parameter — the
trabecular strut thickness — and re-slice. Thicker struts produce a denser,
heavier part; thinner struts produce a lighter, more open part. The user observes
the change in the preview and in the estimated material use.

**Why this priority**: Without a control the feature is a fixed curiosity. One
parameter is the minimum that makes it a usable design tool rather than a preset.

**Independent Test**: Slice the test cube at two different strut thicknesses and
compare estimated filament use. The thicker setting uses measurably more material
and shows wider struts in the preview.

**Acceptance Scenarios**:

1. **Given** the capability enabled, **When** the user sets a larger strut
   thickness, **Then** estimated material use increases and the preview struts are
   visibly wider.
2. **Given** a strut thickness that cannot be printed reliably, **When** the user
   slices, **Then** a user-visible warning names both the supplied value and the
   minimum acceptable value.

---

### User Story 3 - Compare against gyroid at matched weight (Priority: P3)

A user or reviewer wants evidence that trabecular infill is worth using. They
print compression coupons at matched weight, one with trabecular infill and one
with gyroid, and measure both. The result is a documented comparison with stated
conditions, not an assertion.

**Why this priority**: This is the evidence the entire claim rests on, but it
requires the feature to exist first. It is P3 for sequencing, not for importance.

**Independent Test**: Produce the coupon pair, print on the author's printer,
measure, and record the numbers with their conditions. A reviewer can locate the
measurement record and reproduce the procedure from it.

**Acceptance Scenarios**:

1. **Given** a coupon pair with matched measured mass, **When** both are printed
   and weighed and compression tested, **Then** the record states the measured
   masses, the measured compression values, the printer, the profile, the
   filament, and the test method.
2. **Given** the measurement record, **When** any strength or weight claim is made
   about this feature, **Then** the claim cites that record and does not generalise
   beyond it.
3. **Given** a gyroid control whose measured mass falls outside the stated
   tolerance of the trabecular coupon, **When** the comparison is reported,
   **Then** the record states the actual masses and the comparison is not
   presented as matched-weight.

---

### Edge Cases

- **Part with no sparse region**: solid parts, or parts whose interior is entirely
  skin, must slice normally with no carving attempted.
- **Very small parts**: parts too small to fit a single strut and void must not
  produce degenerate geometry or fail slicing.
- **Strut thinner than the printer can extrude**: must warn rather than emit
  unprintable output.
- **Very thin features in the model**: a layer region narrower than the void
  spacing must remain printable.
- **Non-planar or extremely irregular layer outlines**: carving must not produce
  disconnected fragments that break path chaining.
- **Cancelled slice**: cancelling mid-slice must leave no partial state affecting
  the next slice.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST replace the interior fill of each layer of a part
  with a network of dense struts separated by voids, when the capability is
  enabled and the part has sparse infill.
- **FR-002**: The system MUST expose exactly one user-facing parameter: trabecular
  strut thickness. Structure orientation MUST NOT be a second parameter.
- **FR-002a**: The system MUST derive the orientation of the strut/void pattern
  from the print profile's own infill-direction setting, so a user aligns struts
  to a load axis by changing that standard setting. A hardcoded orientation MUST
  NOT be used when the profile supplies one.
- **FR-002b**: When the profile supplies no usable infill-direction value, the
  system MUST fall back to 45 degrees and MUST log the assumption. It MUST NOT
  fail the slice for this reason.
- **FR-003**: The system MUST produce identical output for identical input
  geometry, parameters, and seed, across repeated runs on the same machine.
- **FR-004**: The system MUST warn the user, before or during slicing, when the
  chosen strut thickness cannot be reliably printed on the active profile. The
  warning MUST be user-visible — not log-only — and MUST state both the value
  supplied and the minimum acceptable value.
- **FR-004a**: A strut thickness below the printable minimum MUST NOT silently
  produce output. The part may still be sliced, but only with a visible
  indication that the result will not print reliably.
- **FR-005**: The system MUST leave parts without a sparse region unchanged.
- **FR-006**: The system MUST complete slicing without error on the agreed test
  geometry using a stock print profile.
- **FR-007**: The system MUST NOT modify perimeters, skins, top or bottom
  surfaces, or support structures.
- **FR-008**: The system MUST NOT affect slicing when the capability is disabled
  or not selected in the profile.
- **FR-009**: The system MUST state the minimum supported slicer version and the
  exact build it was tested against.
- **FR-010**: The system MUST provide the means to produce a matched-weight
  compression coupon pair (trabecular versus gyroid) and MUST document the
  measurement procedure.
- **FR-010a**: "Matched weight" MUST be established by measuring the actual
  printed mass of both coupons, not by a slicer estimate or a density percentage.
  The measured masses and the tolerance between them MUST be recorded. The gyroid
  control MUST be iterated until it falls within that tolerance.
- **FR-011**: The system MUST record, for every geometry considered during
  design, the print-cost evidence used to select between them.

### Key Entities

- **Trabecular structure**: the interior network produced for a part — struts of
  a given thickness, voids of a given extent, arranged with a defined orientation
  and spacing.
- **Strut thickness**: the single user-facing parameter; determines both the
  density of the network and, consequently, material use.
- **Infill direction**: the print profile's existing setting that determines the
  orientation of the strut and void pattern. Not a plugin parameter; the plugin
  reads it.
- **Coupon pair**: two compression specimens of identical external dimensions and
  matched measured mass, one produced with trabecular infill and one with gyroid.
- **Measurement record**: the documented result of compressing a coupon pair,
  including the conditions under which it was produced.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A user can enable the capability and slice the standard test
  geometry with no manual file editing and no error, on the first attempt.
- **SC-002**: Slicing the standard test geometry seven times under identical
  settings produces seven byte-identical outputs.
- **SC-003**: The standard test geometry printed with trabecular infill completes
  on the author's printer using a stock profile, with no failed print and no
  intervention, verified by a photographed finished part.
- **SC-004**: A matched-weight coupon pair exists, both members printed, weighed,
  and compression tested, and the resulting record states the measured masses,
  the measured compression values, and their conditions.
- **SC-005**: Estimated material use responds monotonically to the strut
  thickness parameter — a larger value never produces less material use.
- **SC-006**: Print cost is quantified, not assumed: the exported G-code for the
  test geometry reports extrusion move count, mean segment length, and travel
  share, alongside the same figures for a gyroid control.
- **SC-007**: Changing the profile's infill-direction setting changes the
  orientation of the produced structure, verified by comparing two slices taken
  at different direction values.
- **SC-008**: A strut thickness below the printable minimum produces a
  user-visible warning, verified by observation rather than by log inspection.

## Assumptions

- The user has OrcaSlicer installed and can enable a plugin capability and select
  it in a print profile without developer assistance.
- The author has access to a printer, filament, and a way to apply compression
  load for the coupon test.
- The test geometry is a 20 mm cube, per the project constitution's
  minimum-viable-scope principle.
- Sparse infill density is above zero; the feature carves an existing sparse
  region rather than creating one.
- The slicer's built-in solid infill is responsible for drawing the struts. The
  feature controls where material exists, not which strokes are drawn.
- The tested slicer build is OrcaSlicer 2.5.0-rc, build af2ffb8c, macOS. The
  plugin API is beta and behaviour on other builds is not claimed.
- Existing product evidence from the feasibility and tuning phases
  (`docs/phase0-findings.md`) is valid input and is not re-derived by this spec.

## Out of Scope

- Multiple infill algorithms. One algorithm ships before any second is considered.
- Density grading by distance from the surface, or hollow cores. These require a
  different architecture and are deferred.
- Load-direction alignment of struts as a separate control. Alignment is achieved
  through the profile's own infill-direction setting (FR-002a); a dedicated
  alignment parameter is not added.
- Any claim that trabecular infill is stronger than gyroid. The coupon test is
  designed to produce evidence; it does not presuppose the result.
