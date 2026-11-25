# Print cost — measured G-code comparison

All numbers below come from exported G-code in `tests/`. They are **not**
OrcaSlicer 2.5.2 measurements. The plugin export is OrcaSlicer **2.5.0-rc** build
`af2ffb8c`; the baseline export is OrcaSlicer **2.5.0-beta** (its own header says
so). Both predate 2.5.2. Do not quote either as a 2.5.2 result.

Reproduce:

```sh
python3 -I tools/gcode_metrics.py tests/Cube_PLA_1h17m.gcode
python3 -I tools/gcode_metrics.py tests/Cube_PLA_23m33s.gcode
```

Segment statistics are over every extrusion segment in the file. Travel share is
`travel length / (extrusion length + travel length)`.

## Whole-file figures

| Metric | Plugin: `tests/Cube_PLA_1h17m.gcode` | Baseline: `tests/Cube_PLA_23m33s.gcode` |
| --- | --- | --- |
| OrcaSlicer version | 2.5.0-rc (`:2`) | 2.5.0-beta (`:2`) |
| Plugin manifest | `bone_infill;;Trabecular Infill` (`:220868`) | empty (`:18512`) |
| Slicing pipeline picker | `Trabecular Infill` (`:220967`) | `Infill Probe` (`:18611`; stale, nothing ran) |
| Sparse pattern / density | cubic / 10% (`:220982`, `:220986`) | cubic / 10% (`:18626`, `:18630`) |
| Filament used [g] | 40.41 (`:221156`, `:221158`) | 13.92 (`:18800`, `:18802`) |
| Estimated print time | 1h 17m 14s (`:221161`) | 23m 33s (`:18805`) |
| Layers | 175 (`:221160`) | 175 (`:18804`) |
| Total extrusion moves | 133,917 | 7,107 |
| Total extrusion length | 366,510.69 mm | 123,419.52 mm |
| Mean extrusion segment | 2.737 mm | 17.366 mm |
| Median extrusion segment | 0.505 mm | 13.990 mm |
| Travel moves | 10,308 | 941 |
| Travel share | 8.00% | 4.47% |

The two files are not a controlled pair for infill alone: the plugin export also
spends more extrusion length on the carved solid struts. The mass and time
ratios below are whole-print ratios, not per-region ratios.

## One named interior layer

Layer index 87, as numbered by `gcode_metrics.py` (0-based).

| Metric | Plugin layer 87 | Baseline layer 87 |
| --- | --- | --- |
| Extrusion type | Internal solid infill | Sparse infill |
| Extrusion moves | 704 | 39 |
| Extrusion length | 2,113.10 mm | 672.30 mm |
| Mean extrusion segment | 3.002 mm | 17.239 mm |
| Median extrusion segment | 0.531 mm | 17.950 mm |
| Travel moves | 60 | 5 |
| Travel share | 7.60% | 3.50% |

## Ratios (plugin vs baseline)

| Ratio | Value | Files |
| --- | --- | --- |
| Mass | 40.41 / 13.92 = **2.90x** | `Cube_PLA_1h17m.gcode` vs `Cube_PLA_23m33s.gcode` |
| Estimated print time | 4634 s / 1413 s = **3.28x** | same |
| Total extrusion moves | 133,917 / 7,107 = **18.8x** | same |
| Total extrusion length | 366,510.69 / 123,419.52 = **2.97x** | same |

## What is missing

There is **no gyroid export in `tests/`**. The baseline above is 10% cubic, not
gyroid. Any statement about a gyroid move-count ratio is untraceable to a file
and must not be made.

Open: gyroid control export needed (2.5.2).

The earlier "~9x extrusion moves vs gyroid" line in `docs/coupon-results.md` had
no exported artifact behind it; it has been removed. The only move-count ratio
this repository can currently cite is the 18.8x against the 10% cubic baseline
in the table above.

## Labels required by Principle I

- Plugin numbers: `tests/Cube_PLA_1h17m.gcode`, OrcaSlicer 2.5.0-rc.
- Baseline numbers: `tests/Cube_PLA_23m33s.gcode`, OrcaSlicer 2.5.0-beta.
- Per-layer numbers: layer 87 in each named file.
- Filament mass and print time: the header lines cited in the whole-file table.

When 2.5.2 exports exist, add them here with the version and build hash in the
filename or table; do not overwrite these rows.
