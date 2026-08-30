# Scientific and numerical assumptions

This guide describes what the current code computes. It separates rules with
named scientific references from rules inherited from older programs. A rule
that matches old code is not necessarily scientifically validated.

## Input parameters

| Field | Meaning | Unit or format |
| --- | --- | --- |
| `Mw` | Moment magnitude | dimensionless |
| `h` | Hypocentral depth | km |
| `lat0` | Epicenter latitude | decimal degrees, north positive |
| `lon0` | Epicenter longitude | decimal degrees, east positive; western longitudes are negative |
| `hhmm` | Origin time | four digits, UTC hour and minute |
| `dia` | Day used in arrival-time text | two-character value |

The simulation models one rectangular fault. Strike and dip are copied from
the nearest record in `mecfoc.dat` because they are not public input fields.
Rake is fixed at 90 degrees in the fault-plane stage.

## Source dimensions and slip

`calculator.py` and `fault_plane.py` use these magnitude relations:

```text
L = 10^(0.55 Mw - 2.19) km
W = 10^(0.31 Mw - 0.63) km
```

The active Fortran source identifies them as Papazachos et al. (2004). The
repository does not contain the paper or a full citation, so this guide records
the attribution without claiming that the relation is appropriate for every
tectonic setting.

Moment and average slip are calculated as:

```text
M0 = 10^(1.5 Mw + 9.1) N m
D = M0 / (mu L W) m
mu = 4.0e10 N/m^2
```

The moment relation is labeled Hanks and Kanamori in the historical MATLAB
script. The rigidity value is inherited from the active `fault_plane.f90`.
The older `packages/tsdhn/tests/original.m` uses `4.5e10 N/m^2`; that script is
historical and is not the active reference.

## Coordinate frames

Two longitude frames exist because the model files and public inputs use
different conventions:

- Public inputs and map calculations use `-180..180` degrees.
- The bathymetry axis and active Fortran fault-plane program use `0..360`
  degrees.

The fault-plane stage adds 360 to a negative epicenter longitude before
searching `mecfoc.dat` and the bathymetry grid. The calculator preview instead
converts mechanism records into the public input frame. These searches can
choose different records near the longitude wrap. That difference is
currently preserved for compatibility.

Fault rectangle offsets use two inherited approximations:

- `111.0 km` per degree when placing the fault origin and computing its depth.
- `60 * 1853 m` per degree when constructing the displayed rectangle corners.

The second value treats one degree as 60 nautical miles and one nautical mile
as 1853 m. These are compatibility rules, not a general geodesic model. The
corner list starts at the fault origin, follows the rectangle, and repeats the
first point to close the polygon.

## Fault-plane stage

The fault-plane stage follows `model/fault_plane.f90`:

1. Read origin time, longitude, latitude, depth, and magnitude from
   `hypo.dat`.
2. Calculate rupture length, width, moment, and average slip.
3. Select strike and dip from the nearest `mecfoc.dat` record in the `0..360`
   longitude frame.
4. Place the fault origin and snap it to the bathymetry axes.
5. Recompute the depth of the fault's upper edge from the continuous origin.
6. Write the deformation inputs and the mechanism record used by maps.

The grid window is deliberately unusual. Its geographic bounds are converted
to integers before the nearest bathymetry cell is selected. Magnitudes above
8 use a window multiplier of 1.4; other magnitudes use 2.8. The source of
these multipliers is not documented in the repository.

If the calculated upper-edge depth is negative, the stage substitutes 5000 m.
This is inherited behavior. It should not be described as a physical depth
correction without a source.

## Deformation stage

`deform.py` is a compatibility port of `model/def_oka.f`. That Fortran source
identifies its formulation as Okada (1985). The repository does not include a
full citation or an independent derivation.

The stage computes vertical displacement for one rectangular segment. Inputs
are grid indices, slip, length, width, strike, dip, rake, and top-edge depth.
Lengths and depths are in meters; angles are in degrees. The grid spacing is
`7412.9951096 m` on both axes.

Compatibility depends on details that would normally be implementation
choices:

- calculations use float32 arrays to match Fortran `REAL*4`;
- pi is calculated through float32 `asin`;
- strike values of 0 or 360 degrees receive a 0.001 degree offset;
- singular branches use an epsilon of `1e-8`;
- values with absolute magnitude at least 20 m are replaced with zero;
- `deform_a.grd` uses fixed-width fields with three decimal places.

The 20 m rule comes directly from `def_oka.f`. Its scientific basis is not
known. Treat it as an inherited outlier guard, not a physical correction.

## Tsunami propagation stage

`tsunami.py` ports the active calculation in `model/tsunami1.for`. The Fortran
header describes a linear shallow-water model on a spherical grid. The Python
port preserves the active grid-A calculation and omits old outputs that the
current pipeline does not consume.

| Quantity | Current value |
| --- | ---: |
| Grid shape | 2461 by 2056 cells |
| Angular spacing | 240 arcseconds, or 1/15 degree |
| Time step | 3 s |
| Number of steps | 33,602 |
| Gauge sampling interval | 20 steps, or 60 s |
| Number of gauges | 17 |
| Earth radius | `6.37e6 m` |
| Gravity | `9.8 m/s^2` |
| Southern latitude origin | `-76.006 degrees` |
| Flush threshold | `1e-5` |

Bathymetry uses the sign convention inherited from `grid_a.grd`: positive
values are water depths and negative values are land. Positive water depths
below 10 m are raised to 10 m before integration. Zero is not raised.

The solver uses staggered discharge depths. `HM` averages adjacent cells along
the first grid axis; `HN` averages along the second. The final row or column
keeps the original bathymetry value. Latitude factors are advanced by repeated
float32 addition because recomputing them from an index changes accumulated
rounding relative to the Fortran program.

Each time step runs in this order:

1. Apply the continuity equation to produce the next elevation.
2. Apply open-boundary radiation using the previous momentum arrays.
3. Update both momentum components from the new elevation.
4. Sample gauges and maximum positive elevation at the sampling interval.
5. Swap the current and next buffers.

The first Fortran row and column are outside the interior continuity update.
Momentum is written only when both cells beside a discharge point are wet.
Small elevations and momenta are set to exactly zero. Dry-cell boundary points
are left unchanged by the boundary routine.

Boundary passes have a fixed order. The two latitude edges are written first,
then the two longitude edges. A later edge pass owns a shared corner. Changing
the pass order changes results.

`zfolder/green.dat` contains sampled time in minutes followed by 17 sampled
elevations. `zfolder/zmax_a.grd` contains the maximum positive elevation seen
at the same sampling times. It is not updated at every solver step. Both files
use fixed-width fields with three decimal places.

### Checkpoints

The Python solver saves both elevation buffers, both buffers for each momentum
component, the sampled maximum grid, gauge rows, and the last completed step.
Saved arrays must have the current shape and float32 dtype. A checkpoint is
rejected when its pipeline version, shape, gauge count, or step index is not
valid.

The checkpoint is written after buffer swaps, so it represents a fully
completed step. Changing the meaning or order of saved state requires a
pipeline-version change. A successful run removes the checkpoint after writing
the final fixed-width outputs.

## Arrival-time estimates

The calculator's port arrival times are separate from the propagation solver.
It first computes spherical distance, then applies inherited rules:

- distances of at least 750 km use `distance / 790 + 0.2` hours;
- epicenters outside latitude `-19..0` use `distance / 700` hours;
- other paths sample bathymetry at 101 points and integrate `1/sqrt(g h)` with
  Simpson's rule;
- the integrated result is multiplied by 0.5;
- integrated times above 3 hours are replaced by `distance / 733 + 0.25`;
- integrated times between 1.4 and 3 hours are replaced by
  `distance / 690 + 0.2`.

The path construction also uses `110 km` per degree. The repository does not
identify the source of the thresholds, speeds, offsets, multiplier, or path
approximation. These are inherited arrival-time calibration rules. Do not
present them as a validated travel-time model until their provenance and
intended domain are established.

`ttt_client` produces the separate arrival-time grid used for `ttt.pdf`.

## Report transformations

### Maximum-height map

`zfolder/zmax_a.grd` is the raw sampled solver grid. `maxola` reshapes and
flips that grid, then rescales every finite value so the largest displayed
value is 12 m and rounds values to two decimals. The resulting map is
pixel-registered for GMT.

The 12 m maximum is a display transformation. Values read from `maxola.pdf`
must not be treated as raw solver amplitudes. Quantitative work should start
from `zfolder/zmax_a.grd` and state whether the sampling interval matters.

### Station reports

`ttt_max` multiplies each virtual-gauge series by a station-specific factor of
the form `(numerator / denominator)^0.25`. It then writes corrected series,
first-positive-sample indices, peak values, and the mareogram.

The repository does not explain the numerator, denominator, or fourth-root
rule. These factors are empirical report corrections applied after the solver.
They are not part of the shallow-water calculation, and this documentation
does not claim that they represent bathymetry, observations, or a validated
physical calibration.

## Changes that need special care

Before changing numerical behavior, record:

- the source or research reason for the change;
- units and longitude frame;
- array axis and one-based or zero-based indexing assumptions;
- float dtype and evaluation order;
- fixed-width field size and decimal precision;
- whether compatibility with the older program is intended;
- whether checkpoint state or meaning changes.

Add an independent focused test where practical. Run legacy comparisons when
preserving compatibility, and inspect spatial golden outputs when changing the
full pipeline. Do not update saved values merely to make a changed test pass.
