# Specification Quality Checklist: Trabecular Infill

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-10-31
**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] No implementation details (languages, frameworks, APIs)
- [x] Focused on user value and business needs
- [x] Written for non-technical stakeholders
- [x] All mandatory sections completed

## Requirement Completeness

- [x] No [NEEDS CLARIFICATION] markers remain
- [x] Requirements are testable and unambiguous
- [x] Success criteria are measurable
- [x] Success criteria are technology-agnostic (no implementation details)
- [x] All acceptance scenarios are defined
- [x] Edge cases are identified
- [x] Scope is clearly bounded
- [x] Dependencies and assumptions identified

## Feature Readiness

- [x] All functional requirements have clear acceptance criteria
- [x] User scenarios cover primary flows
- [x] Feature meets measurable outcomes defined in Success Criteria
- [x] No implementation details leak into specification

## Notes

Validation pass 1: all items pass.

Deliberate deviations from the strict template rules, recorded rather than hidden:

1. **FR-003 says "across repeated runs on the same machine", not "across
   platforms."** The constitution's determinism principle (IV) is satisfied by
   same-machine reproducibility, which is what the coupon comparison needs. Cross-
   platform byte-identity is a stronger claim that the upstream PR made and that we
   have not tested. Do not upgrade this requirement without evidence.

2. **User Story 3 describes a measurement procedure, which is arguably process
   rather than product.** It is retained because the constitution requires the
   physical test as an evidence gate, and dropping it from the spec would leave the
   central claim unsupported.

3. **Provider-specific terms appear in the input but were removed from the spec
   body** — no slicer hook names, no internal geometry type names, no file paths
   appear in the requirements. Those belong in `/speckit-plan`. The single
   unavoidable exception is the tested build identifier in Assumptions, which the
   constitution's Principle V requires to be stated.

4. **SC-002 uses seven runs.** That number is a judgment call, not a derived value.
   It is enough to catch non-determinism from unordered iteration in practice, and
   cheap enough to run repeatedly.

## Post-Clarification Notes (2026-10-31)

Three clarifications integrated. FRs 002→002a/002b, 004→004a, 010a added;
SC-007 and SC-008 added; three acceptance scenarios added.

Recorded deviations after clarification:

1. **FR-004 requires a user-visible warning, and the mechanism is constrained.**
   The slicing-order comment in `PluginHooks.cpp` states that pipeline hooks fire
   after `set_done()`, so `active_step_add_warning()` must not be called from them
   (it would index `m_state[-1]`). A user-visible result is still reachable — a
   non-empty `ExecutionResult` message is logged, and a `SlicingError` produces a
   real user-facing slicing error — but the spec deliberately says "user-visible"
   rather than naming an API, and the mechanism belongs in the plan.

2. **FR-002a depends on an unverified assumption.** That the profile's infill
   direction is readable at the slicing hook was confirmed only partially: the
   value appears in the exported G-code header (`solid_infill_direction = 45`,
   `infill_direction = 45`), which is not the same as being readable through the
   config API at `posPrepareInfill`. An attempt to measure the produced raster
   angle from G-code was inconclusive and is recorded in
   `docs/phase0-findings.md` under "Unresolved: raster angle". The plan MUST verify
   the read before relying on it.

3. **"Match measured mass" leaves the tolerance unspecified in the spec.** That is
   deliberate — the tolerance is an experimental-design choice that belongs with
   the coupon protocol, not in a functional requirement. FR-010a requires the
   tolerance to be *stated and recorded*, not fixed here.

