# Phase 2 — Research and candidate algorithms

Written 2026-10-31. Primary source: the **Bone Infill** notebook in Kortex
(16 sources). Secondary: the OrcaSlicer PR pages and the Cura add-on README,
retrieved via web and indexed.

**How to read the strength/weight claims:** the marker *claimed by X under Y*
is load-bearing. Almost nothing in this corpus is a measured FDM compression
test of a bone-inspired infill against gyroid. Do not upgrade a simulated or
estimated number to a measured one when quoting this document.

---

## 1. The finding that changes the plan

**An upstream OrcaSlicer implementation of bone infill already exists.**

PR **#16809 "Add the Bone sparse infill pattern"** by MikeyBoi-N adds
`src/libslic3r/Fill/FillBone.{hpp,cpp}`. Companion PR **#16810** adds a density
graph editor.

Status, from the PR page:

- **Open, not merged.** "Open — MikeyBoi-N wants to merge 3 commits into
  OrcaSlicer:main". No formal reviews, no assignee, no milestone.
- **Not in any release**, confirmed independently: the installed
  `/Applications/OrcaSlicer 2.app` binary contains no `bone_irregularity`,
  `bone_isotropy`, `bone_falloff`, `bone_hollow_depth`, `bone_max_bridge` or
  `FillBone` strings. Only reachable via the PR build artifacts.

### Why this matters to the architecture decision

The PR author states the design cannot be a plugin:

> "Because the pattern requires generating 3D distance fields and object-level
> power diagrams, it cannot easily be implemented as an external plugin and
> must be integrated directly into Slic3r/OrcaSlicer core C++ libraries."

And on the plugin route specifically:

> "There doesn't seem to be a plugin type for adding an infill pattern. Bone
> could work as a plugin, but in a clumsier form, outside the normal infill
> settings, I think."

That is consistent with our own Phase 0 finding: a plugin cannot author
toolpaths, only the fill region. **The upstream implementation and our plugin
are not competing solutions to the same problem — they occupy different
layers.** Upstream produces true 3D-graded foam walls. Our plugin reshapes
the 2D region the built-in raster fills.

### Maintainer concerns, which are also our design constraints

- `ianalexis` (collaborator): "my concern here is the same as #16298 that
  print time will be suboptimal."
- Reviewer consensus: adaptive TPMS "is much faster to print"; the pattern may
  suit resin more than FDM.
- Concern that the infill pattern list is already long with many
  low-utility entries.

**These map exactly onto the fragmentation problem we measured.** Our tuning
run found bone-like void fields cost 1.1 moves/mm² against a 0.06 baseline.
The community's objection and our G-code data are the same phenomenon measured
two different ways. Any architecture we pick has to answer the print-time
question or it dies at review the way #16809 has.

---

## 2. Candidate algorithms, ranked for FDM printability

Ranking criterion, fixed in advance: **can this be expressed as a per-layer
2D region edit that the built-in 45° solid raster fills without fragmenting?**
That is the only thing a plugin can control, per Phase 0.

### C1 — Raster-aligned slot field  ← current front-runner
**Evidence:** our own measurement, `tests/Cube_PLA_24m32s.gcode`.

Elongated voids whose long axis follows the raster angle. Measured against two
alternatives on identical strut width:

| variant | moves/mm² | mean segment | travel % |
| --- | --- | --- | --- |
| raster-aligned slots | **1.1** | **2.59 mm** | **6.4%** |
| 8 mm round pores | 1.7 | 1.64 mm | 13.4% |
| 4 mm round pores | 3.6 | 0.78 mm | 18.2% |
| sparse baseline | 0.06 | 17.37 mm | 4.5% |

Void fractions differed (27%, 42.5%, 38.9%), so this is not a controlled
comparison — it is directional evidence from one slice. Re-confirm before
quoting as a result.

**Why it survives the printability filter:** it is the only candidate whose
geometry was chosen *because of* the raster, rather than designed for
bone-likeness and then hoped printable.

### C2 — Spinodoid / random-field level set
**Claimed by the Cura add-on README (quix2k23) under:** Cura 5.13, patched
CuraEngine.

Structure is the level surface of a smooth random 3D field — a sum of 64 cosine
waves, citing *Kumar et al., Inverse-designed spinodoid metamaterials, npj
Computational Materials 2020*.

**Claimed by the same source under the same conditions:** "99% of the infill of
a layer has infill directly below it", measured by an automated test.

**Claimed by the same source under the same conditions:** "this is meant to
imitate the structure of bone. **The strength of printed parts has not been
measured**, so do not assume it is stronger than another pattern."

Slicing cost, claimed by the same source: ~40 s vs ~4 s for a 150×150×30 mm
part on a 12-core desktop.

**Verdict for us:** the field is genuinely 3D-continuous, which gives excellent
layer-to-layer support. But a level-set field produces curved boundaries at
arbitrary angles, which is the worst case for raster fragmentation. It is the
most bone-faithful candidate and the least print-time-friendly. Also: the
author explicitly did not measure strength.

### C3 — 3D power diagram + distance-field grading (upstream #16809)
**Claimed by the PR description under:** OrcaSlicer, `FillBone`, 0.4 mm nozzle.

Walls are cross-sections of a 3D power diagram (weighted Voronoi) of cell
centres, spaced by target density, generated once per object in
`PrintObject::prepare_bone_infill()`. Density graded by 3D distance transform
(Felzenszwalb & Huttenlocher, extracted to shared
`src/libslic3r/DistanceTransform.{hpp,cpp}`). Walls pruned bottom-up for
printability; hollow cores closed with pointed roofs.

Determinism, claimed by the PR under those conditions: random positions come
from `std::mt19937_64` directly rather than the standard distributions, so the
same project yields identical walls across Windows/macOS/Linux.

Reported cost, claimed by the PR: slicing a 120 mm cube at 80%/1% density took
**64.2 s with ~1.9 GB peak memory**.

**Verdict for us:** the best engineering in the corpus and the thing to copy
conceptually — but it is C++, not a plugin, and it is unmerged. Useful to us as
(a) a source of validated printability rules to borrow, and (b) the obvious
fallback if the plugin route stalls: build the PR locally and use it.

### C4 — Topology-optimised porous infill
**Claimed by Wu, Aage, Westermann & Sigmund (IEEE TVCG 2018) under:** 3D FEA,
~44.4% volume fraction, vertical loading on a "kitten" model, ~4.6–5.56M
elements.

Local-volume-constrained porous infill had normalised compliance **2.11**
against a conventional honeycomb infill at **3.22** — i.e. ~1.5× stiffer, and
max von Mises stress 10.3 MPa vs 14.2 MPa.

Damage tolerance, same source, same conditions (2D half MBB-beam, α=0.4,
R=9): compliance changed 1.4× after localised material removal, versus 17.4×
for a total-volume-constrained infill.

**Verdict for us:** strong evidence that *graded local density* is the
mechanism behind bone-like stiffness, and that it buys damage tolerance — which
is arguably the real reason to want trabecular infill rather than raw strength.
But it is a simulation result from per-element density fields, not an
achievable plugin output. Use it to justify density grading as a design goal,
not as a spec number.

### C5 — Generative design (ScaffoldForge)
**Claimed by Zhang et al., PLOS One, 2026 under:** in-silico voxel FEA.

Estimated compressive strength **56.6 MPa**, 8.2% over topology optimisation
(52.3 MPa) and 6.6% over TriTopo-LGDM (53.1 MPa), p = 0.043, n = 5 seeds.

**The paper's own limitation statement:** "All results are computational;
physical, biological, manufacturing, and regulatory validation remain future
work."

**Verdict for us:** out of scope — diffusion networks are not a slicer plugin —
but useful as the current high-water mark for what a graded scaffold's simulated
strength looks like.

---

## 3. Anisotropy and load alignment

**Claimed by the Cura add-on README under Cura 5.13:** waves mostly
perpendicular to the main direction give struts that run along it; at 0% the
structure is isotropic, at high alignment it becomes "upright, branching struts
with a few cross-links, like the trabeculae in a vertebra". Suggested starting
point for a vertically loaded part: alignment 60–80, tilt 0.

**Claimed by the same source:** "Struts that are close to vertical are also the
most reliable to print."

**Claimed by UNSW Canberra / 3D Printing Industry under:** impact testing on
printed scaffolds, orientations lengthwise/crosswise/diagonal — structures
absorbed energy efficiently under fast loads and showed distinct fracture
patterns by orientation. No numeric values in the source text.

**Relevance:** trabeculae align with load. That is the biological claim the
whole idea rests on. For a plugin, load alignment is expressible — rotate the
slot field. But our formula is constrained to be raster-friendly, so
*alignment angle and raster angle are coupled*: we cannot both follow an
arbitrary load direction and follow the 45° raster. **This is a genuine design
conflict and should be decided explicitly, not accidentally.**

---

## 4. Gaps in the corpus

1. **No measured FDM compression test of a bone-inspired infill against gyroid
   at matched weight.** The single most important number for the project does
   not exist in these sources. Our Phase 3 coupons will produce it, and that is
   the strongest argument for running them.
2. ScaffoldForge and Wu et al. are simulations. The Cura add-on explicitly
   states strength was not measured. The OrcaSlicer PR has community
   print reports but no instrumentation.
3. Nothing in the corpus addresses **retracting vs. travel** placement, or
   seam behaviour, for perforated solid-fill regions — the exact thing our
   G-code metrics flagged.
4. No source gives a principled relationship between trabecular thickness and
   FDM line width. Our 1.2 mm strut was chosen arbitrarily and has not been
   justified.
5. The OrcaSlicer PR uses 3D *power* diagrams (weighted Voronoi). Nothing in
   the corpus explains when weights matter over unweighted Voronoi. Our C1 does
   not use Voronoi at all.

---

## 5. What the research says we should do

1. **Keep C1 (raster-aligned slots) as the MVP algorithm.** It is the only
   candidate with print-time evidence, and print time is the objection that
   killed the upstream PR.
2. **Borrow the upstream PR's printability rules rather than reinventing
   them** — bottom-up support requirement, short-bridge allowance over
   `bone_max_bridge`, pointed roof closure over hollow regions. Those are
   validated by tests in that PR.
3. **Decide the alignment question explicitly.** Load-aligned struts are
   biologically right and print-reliability-friendly, but conflict with raster
   alignment. Options: fix raster angle to match the load direction (plugin
   writes the config value if it can — *not yet verified*), or accept raster
   alignment and document the anisotropy cost.
4. **Measure, do not assume.** The corpus's central weakness is the absence of
   physical measurement. The Phase 3 compression coupons are not a checkbox;
   they are the only source of the number the whole justification rests on.
5. **Treat upstream #16809 as a live option, not a dead end.** If coupons
   show C1's print cost is unacceptable, building the PR branch is a fallback
   that doesn't require inventing anything.

---

## Citations

Primary corpus: Kortex notebook **Bone Infill**
(`fd942559-4425-44ca-b7de-f66f522454bc`), 16 sources. Retrieved via
`ask_question` with `citation_format=json`; the source-level citations are in
the session transcripts and are reproduced above against each claim.

Sources used:

- *Add the Bone sparse infill pattern*, OrcaSlicer PR #16809 (MikeyBoi-N) —
  open, not merged
- *Add density graph dialogs for Bone and adaptive infill*, PR #16810
- *quix2k23/cura-inner-outer-inner* README — Cura 5.13 bone-like infill add-on
- Wu, Aage, Westermann, Sigmund, *Infill Optimization for Additive
  Manufacturing — Approaching Bone-like Porous Structures*, IEEE TVCG 24(2),
  2018 (DTU Orbit PDF)
- Zhang et al., *ScaffoldForge*, PLOS One, 2026
- *New Bone Infill: Available for Devs to try out*, r/3Dprinting
- UNSW Canberra bone scaffold coverage, 3D Printing Industry
- *Researchers Optimize Robust, Lightweight, Bone-Inspired 3D Printing Infill*,
  3DPrint.com

**Not verified:** the Kumar et al. *npj Computational Materials* 2020
spinodoid paper — two web fetches returned the wrong documents (an unrelated
economics preprint, then an unrelated materials benchmark). The citation is
reproduced as the Cura README states it, but the paper itself has not been
read. Do not cite it as a primary source until it is.
