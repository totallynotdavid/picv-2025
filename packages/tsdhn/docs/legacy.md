# Older MATLAB and Fortran references

The older programs are being phased out. They remain useful for identifying
file formats, numerical ordering, and behavior that the Python port intended
to preserve. Agreement with them is compatibility evidence, not scientific
validation.

## Active reference map

| Python code | Older reference | Status |
| --- | --- | --- |
| `calculator.py` source relations | formulas also present in `fault_plane.f90` | Active compatibility basis for source dimensions and slip |
| `fault_plane.py` | `model/fault_plane.f90` | Active Fortran comparison source |
| `deform.py` | `model/def_oka.f` | Active deformation comparison source; Okada-based |
| `tsunami.py` | `model/tsunami1.for` | Active propagation comparison source |
| MATLAB trace comparisons | saved runs produced by capture scripts | Compatibility evidence for selected intermediate values |

The supported setup script and `model/Makefile` build `def_oka.f` as the
`deform` executable. `model/deform.for` is a different, older implementation
based on Mansinha and Smylie and is not the reference for `deform.py`.

## Historical and exploratory files

### `packages/tsdhn/tests/original.m`

This is a historical logging script, not the definition of the current
calculation. It differs from the active path in rigidity, dip handling,
degree-distance conversion, and longitude treatment. Do not combine its
constants with values from `fault_plane.f90` or the Python port.

### `model/fault_plane_n.m`

This MATLAB program explores multiple subfaults and spherical geometry. The
current pipeline uses the single-fault geometry in `fault_plane.f90` and does
not use these spherical corrections. Treat it as a separate research path.

### `model/mareografo_a.m`

This is a historical manual helper. Instructions embedded in it for editing a
specific line in the Fortran solver are not current pipeline instructions.

### `model/deform.for`

This is the older Mansinha-Smylie deformation program. It has different
equations and its own small-value handling. Building or comparing it as if it
were `def_oka.f` can produce a false conclusion about the Python port.

## Compatibility preserved by the Python port

The Python stages intentionally preserve several old-program details:

- mixed longitude frames between public inputs and model grids;
- one-based grid indices in intermediate files;
- integer truncation before fault-window snapping;
- a fixed rake of 90 degrees in the active fault-plane path;
- float32 calculation in deformation and propagation;
- branch behavior near singular points in the Okada-based calculation;
- fixed grid and time-step constants;
- continuity, boundary, and momentum update order;
- fixed-width output fields and decimal quantization;
- gauge and maximum-height sampling intervals.

These details are compatibility requirements only while matching the active
older reference is a project goal. A scientifically justified replacement may
change them, but the change should be explicit and tested at the behavior
boundary.

## Deliberate Python differences

The Python propagation stage keeps the active grid-A calculation but does not
write older movie frames or travel-time arrays that the current pipeline does
not consume. It swaps array references instead of copying full time levels.
The boundary routine is passed the previous momentum arrays explicitly so this
optimization preserves the old update order.

The Python solver adds resumable checkpoints. Checkpoints are an operational
feature and are not part of the Fortran result. Resume tests require a resumed
run to produce the same fixed-width outputs as an uninterrupted Python run.

## Removing an older source

Before removing a MATLAB or Fortran file, verify that:

1. No comparison test compiles or invokes it.
2. Its file formats and numerical rules are documented in the researcher
   guides or focused tests.
3. Any saved trace identifies how it was produced.
4. The active Python behavior has an independent test where practical.
5. The removal does not erase the only known provenance for a constant or
   empirical correction.

If a source is retained only for history, label it as historical in
[`model/readme.md`](../../../model/readme.md). Do not let a generic build target
make it look active.
