#!/usr/bin/env python3
"""Theoretical void/solid fraction of the trabecular ribbon lattice.

Pure geometry; no orca import. The lattice is the one laid out by
`lattice_centers()` in `src/os_bone_plugin/bone_infill.py`: ribbon voids of
half-length L and half-width W, separated by a strut gap equal to the strut
thickness.

Each lattice cell is (2L + gap) by (2W + gap). The void occupies 2L * 2W of it:

    void_fraction  = 4 * L * W / ((2L + gap) * (2W + gap))
    solid_fraction = 1 - void_fraction

`jitter` only shifts centres; it cancels in the long-run area fraction while
voids do not overlap. When the maximum relative jitter exceeds the gap,
neighbours can overlap and the real void fraction is lower than the nominal
value printed here. That is reported as a warning, not silently corrected.

Run:

    python3 -I tools/void_fraction.py
    python3 -I tools/void_fraction.py --strut 1.2 --length 8.5 --width 0.6 --jitter 0.15
"""

import argparse

STRUT_DEFAULT = 1.2
LENGTH_DEFAULT = 8.5
WIDTH_DEFAULT = 0.6
JITTER_DEFAULT = 0.15
WIDTHS = (0.6, 1.0, 1.5, 2.0, 2.5, 3.0)


def void_fraction(strut_mm, length_mm, width_mm, jitter):
    """Nominal void fraction for one lattice cell; solid is its complement."""
    step_u = 2 * length_mm + strut_mm
    step_v = 2 * width_mm + strut_mm
    if step_u <= 0 or step_v <= 0:
        raise ValueError("strut thickness and void dimensions must be positive")
    if not 0 <= jitter <= 1:
        raise ValueError("jitter must be between 0 and 1")
    void = (4 * length_mm * width_mm) / (step_u * step_v)
    return void, 1.0 - void


def overlap_possible(strut_mm, length_mm, width_mm, jitter):
    """True when jitter can push neighbours closer than the strut gap."""
    return (jitter * (2 * length_mm + strut_mm) > strut_mm
            or jitter * (2 * width_mm + strut_mm) > strut_mm)


def print_table(strut, length, jitter):
    print(f"strut {strut:g} mm, void half-length {length:g} mm, jitter {jitter:g}")
    print()
    print("%8s %10s %10s" % ("half-w", "void %", "solid %"))
    for width in WIDTHS:
        void, solid = void_fraction(strut, length, width, jitter)
        print("%8.1f %9.1f%% %9.1f%%" % (width, 100 * void, 100 * solid))
    print()
    if overlap_possible(strut, length, WIDTHS[-1], jitter):
        print("note: jitter can make neighbouring voids overlap at these widths;")
        print("      the printed void fraction is the nominal upper bound.")


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strut", type=float, default=STRUT_DEFAULT,
                        help=f"strut thickness in mm (default {STRUT_DEFAULT})")
    parser.add_argument("--length", type=float, default=LENGTH_DEFAULT,
                        help=f"void half-length in mm (default {LENGTH_DEFAULT})")
    parser.add_argument("--width", type=float, default=None,
                        help="void half-width in mm; omit to print the width table")
    parser.add_argument("--jitter", type=float, default=JITTER_DEFAULT,
                        help=f"lattice jitter fraction (default {JITTER_DEFAULT})")
    args = parser.parse_args(argv)

    if args.width is None:
        print_table(args.strut, args.length, args.jitter)
        return 0

    void, solid = void_fraction(args.strut, args.length, args.width, args.jitter)
    print(f"strut {args.strut:g} mm, void half-length {args.length:g} mm, "
          f"void half-width {args.width:g} mm, jitter {args.jitter:g}")
    print(f"void fraction:  {100 * void:.1f}%")
    print(f"solid fraction: {100 * solid:.1f}%")
    if overlap_possible(args.strut, args.length, args.width, args.jitter):
        print("note: jitter can make neighbouring voids overlap; value is a nominal upper bound.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(None))
