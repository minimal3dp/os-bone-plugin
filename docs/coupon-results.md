# Coupon Results — Trabecular Infill vs Gyroid

Status: **not yet run**. Template below, to be filled from measurement.

Constitution Principle I applies to every row: a number without its artifact is
a defect. Do not fill in an estimate; leave it blank until measured.

## Purpose

Decide whether the print-time cost of trabecular infill buys mechanical
advantage. The measured G-code cost is in `docs/print-cost.md`; the current
comparison is against a 10% cubic baseline, not gyroid. That cost is only
defensible if the structure is meaningfully stronger at matched mass. This
record is the only thing that can establish that.

Open: gyroid control export needed (2.5.2).

## Coupon design

| Field | Value |
| --- | --- |
| Geometry | 20 mm cube (same part as the test geometry) |
| Dimensions | 20 x 20 x 20 mm |
| Orientation on plate | upright, Z = compression axis |
| Filament | *(record)* |
| Nozzle | *(record)* |
| Layer height | *(record)* |
| Walls | *(record)* |
| Top/bottom shells | *(record)* |
| Load axis relative to layers | vertical, across layers |

Rationale for a cube: it matches the constitution's single-test-geometry rule,
and vertical compression across layers is the axis a real part would see. It is
not a standard ASTM coupon; that is a limitation, stated rather than hidden.

## Pair

| | Trabecular | Gyroid control |
| --- | --- | --- |
| Plugin capability | Trabecular Infill | *(none)* |
| Plugin config | strut 1.2 mm, void half-len 8.5 mm | n/a |
| `sparse_infill_pattern` | *(filled by plugin)* | gyroid |
| `sparse_infill_density` | n/a | *(iterate to match mass)* |
| Estimated mass (slicer) | *(record)* | *(record)* |
| **Measured mass (g)** | *(record)* | *(record)* |
| Mass difference (%) | *(compute)* | |
| Within tolerance? | *(state tolerance, e.g. +/-2%)* | |

## Compression test

| Field | Value |
| --- | --- |
| Machine / fixture | *(record)* |
| Load rate | *(record)* |
| Peak load (N) | *(record)* |
| Peak stress (MPa) | *(peak load / 400 mm2)* |
| Failure mode | *(record: buckled / crushed layerwise / shear band / other)* |
| Photo of failed coupon | *(path)* |

## Result

*(Leave blank until measured.)*

If the pair could not be matched within tolerance, state the actual masses here
and do **not** describe the comparison as matched-weight. Per FR-010a a failed
match is a reportable result, not a reason to quietly adjust the numbers.

## What this does and does not prove

- It measures **one filament, one printer, one geometry, one orientation**. It
  does not generalise to other profiles.
- It does not test shear, tension, fatigue, or impact.
- A positive result supports "trabecular is stronger at matched mass in this
  configuration". It does not support "trabecular is better".

## Related

- Print-cost measurement: `docs/print-cost.md`
- Architecture decisions and the fragmentation analysis:
  `docs/phase0-findings.md`
- Procedure: `specs/001-trabecular-infill/quickstart.md` (Coupon procedure)
