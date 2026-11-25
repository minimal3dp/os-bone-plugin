<!--
SYNC IMPACT REPORT
Version change: (none) → 1.0.0
Modified principles: n/a (initial ratification; template placeholders replaced)
Added sections:
  - Core Principles I–VI
  - Additional Constraints (Platform and Version Pinning)
  - Development Workflow (Experimental Evidence and Review Gates)
  - Governance
Removed sections: none
Follow-up TODOs:
  - TODO(MEASUREMENT_BASELINE): Principle I requires measured numbers. The
    compression-coupon protocol and the matched-weight baseline against gyroid
    are defined in the Phase 3 spec, not here, and must be ratified before any
    strength or weight claim enters a document.
Deferred intents (not governance content): plugin implementation, coupon
generation, and slicer integration are feature work and are handled by
/speckit-specify, not by this amendment.
-->

# Bone Infill Plugin Constitution

## Core Principles

### I. Measured or Cited, Never Inferred

Any statement about strength, stiffness, weight, or print time MUST either be
measured on the author's own printers using a documented protocol, or be
attributed to a named source under stated conditions ("claimed by X under Y").
Neither is optional: an unattributed number MUST NOT appear in a document, a
README, a commit message, or a conversation summary.

Simulated, estimated, and modelled results MUST be labelled as such at the point
of use. They MUST NOT be upgraded to measurements by paraphrase, by rounding, or
by removing the qualifier.

*Rationale*: The Phase 2 research corpus contained no measured FDM compression
test of a bone-inspired infill against gyroid. Every strength figure in it was a
simulation or an author's claim. The project's entire justification rests on a
number that did not previously exist, so the rule that produces it cannot be
soft.

### II. Minimum Viable Scope

The MVP MUST contain exactly one infill algorithm, one user-facing density
parameter, and one test geometry. Additional algorithms, parameters, presets, or
geometries MUST NOT be added until the single-algorithm version has passed its
physical test.

*Rationale*: A 5–10 hour/week budget cannot absorb parallel experimentation. The
constraint is a scheduling decision expressed as a governance rule.

### III. Printability Beats Realism

Generated output MUST print without failure on a stock printer profile. Where a
more biologically faithful structure conflicts with reliable extrusion, the
printable structure wins and the fidelity cost is documented.

Concretely, the implementation MUST avoid, and MUST measure for: extrusion
segments shorter than two line widths, unsupported overhangs beyond the stock
profile's allowance, and travel-dominated layers.

*Rationale*: The upstream OrcaSlicer bone-infill PR (#16809) has remained
unmerged, with maintainers citing print time as the objection. Our own G-code
measurements independently reproduced that objection. Fidelity that cannot be
printed has no value and will not survive review.

### IV. Deterministic Output

The same input geometry, seed, and parameters MUST produce byte-identical
G-code across runs. Any randomness MUST draw from a seeded generator whose
algorithm is fixed in the source, not from a platform or library default.

*Rationale*: Non-determinism makes physical comparison meaningless — a coupon
difference could be a random draw rather than a design change. The upstream PR
adopted the same rule for the same reason.

### V. Pinned Platform Version

The minimum supported OrcaSlicer version MUST be stated explicitly, and the
build the plugin was actually tested against MUST be recorded in the README. A
version claim without a tested build reference MUST NOT be made.

*Rationale*: The plugin API is explicitly beta. Undocumented drift between
builds is expected, so "works on OrcaSlicer" is not a testable claim.

### VI. Configuration Through the Plugin API

All plugin configuration MUST be declared through `get_default_config()` and read
through `get_config()`. Ad-hoc configuration files, environment variables, or
side channels MUST NOT be introduced.

*Rationale*: Configuration outside the plugin API is invisible to the slicer's
preset system, cannot be versioned with a print profile, and cannot be audited
by the plugin audit hook.

## Additional Constraints

### Platform and Version Pinning

- Tested build: OrcaSlicer **2.5.0-rc** at `/Applications/OrcaSlicer 2.app`,
  build `af2ffb8c`, macOS. This is the only supported target for the MVP.
- OrcaSlicer 2.4.2 and earlier MUST NOT be claimed as supported: the Python
  plugin system is not present in that release.
- The plugin MUST declare its OrcaSlicer version requirement in its PEP 723
  metadata and restate it in the README with the tested build identifier.

### Configuration Surface

- The MVP exposes exactly one tuning parameter: strut (trabecular) thickness.
  Density is expressed through that parameter, not alongside it.
- All other geometry constants (pore spacing, jitter, seed) are internal
  constants with documented defaults, not user-facing settings.

## Development Workflow

### Evidence Gates

Each stage MUST produce its evidence artifact before the next stage begins:

1. Architecture viability → a probe run producing a verdict line in the Python
   log, cross-checked against exported G-code.
2. Print-cost viability → per-layer G-code metrics (extrusion moves, mean
   segment length, travel share) for every candidate geometry considered.
3. Physical viability → compression coupons at matched weight against a gyroid
   control, measured on the author's printers.

A stage that has not produced its artifact MUST NOT be reported as complete, and
its results MUST NOT be summarised in a way that implies the missing artifact
exists.

### Review Gate

Any change that introduces a numeric claim MUST cite its evidence artifact by
file path or log timestamp. Reviewers MUST reject claims whose artifact cannot
be located.

## Governance

The constitution supersedes ad-hoc practice. Where this document and a
convenience conflict, this document wins.

**Amendment procedure**: Amendments MUST be proposed as a change to this file,
state which principle is affected, and state the version bump. Principle removal
or redefinition is a MAJOR bump; a new principle or materially expanded guidance
is MINOR; wording clarification is PATCH. Ratification by the project owner is
required before an amendment takes effect.

**Versioning policy**: Semantic versioning over the principle set, not over the
plugin's release version.

**Compliance review**: Every spec, plan, and task list MUST state how it
satisfies Principles I–VI, or explicitly record the deviation and its
justification. Complexity added without such a record MUST be rejected.

**Version**: 1.0.0 | **Ratified**: 2026-10-31 | **Last Amended**: 2026-10-31
