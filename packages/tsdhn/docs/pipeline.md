# Simulation pipeline

This guide follows data through one run. It is intended for researchers who
need to replace a stage, inspect an intermediate result, or change a numerical
assumption without confusing raw solver data with report data.

## Before the stages

The engine validates the selected model directory and prepares a run
directory. Model inputs are linked or copied into that directory. Generated
files from an earlier run are not treated as model inputs.

Source-parameter calculation writes `hypo.dat` before the declared processing
stages begin. Port arrival-time estimates are also calculated outside the
propagation stages. See [`science.md`](science.md) for their assumptions.

## Stage map

| Stage | Reads | Writes | Important rules |
| --- | --- | --- | --- |
| `fault_plane` | `hypo.dat`, `mecfoc.dat`, `bathy/xa.dat`, `bathy/ya.dat` | `pfalla.inp`, `xyo.dat`, `meca.dat` | Converts longitude, selects a nearby mechanism, snaps indices, preserves fixed file layouts |
| `deform` | `pfalla.inp`, `xyo.dat` | `deform_a.grd` | Okada-based float32 compatibility calculation for one segment |
| `tsunami` | `bathy/grid_a.grd`, `deform_a.grd`, `xyo.dat`, `tidal.dat` | `zfolder/green.dat`, `zfolder/zmax_a.grd` | Linear shallow-water update with fixed order, sampling, and resumable state |
| `maxola` | `zfolder/zmax_a.grd`, `meca.dat`, station configuration | `maxola.pdf` | Rescales the raw grid to a 12 m display maximum before plotting |
| `ttt_max` | `zfolder/green.dat` | `zfolder/green_rev.dat`, `ttt_max.dat`, `mareograma.svg` | Applies empirical station factors before summaries and plots |
| `ttt_inverso` | `meca.dat`, `ttt_mundo/cortado.i2` | `ttt_mundo/ttt.b` | Calls `ttt_client`; GMT rewrites the grid header for later contouring |
| `point_ttt` | `ttt_mundo/ttt.b` and map inputs | `ttt_mundo/ttt.pdf` | Builds the GMT arrival-time map |
| `copy_ttt_pdf` | `ttt_mundo/ttt.pdf` | `ttt.pdf` | Copies the report to the run root |

The first five stages run in the run root. The travel-time map stages run in
`ttt_mundo`.

## Fault-plane files

### `hypo.dat`

Five lines: origin time, longitude, latitude, hypocentral depth in km, and
moment magnitude. Longitude is written in the public `-180..180` frame.

### `pfalla.inp`

Nine whitespace-separated fields:

```text
I0 J0 D0 L0 W0 strike dip rake top_edge_depth
```

`I0` and `J0` are one-based indices in the full bathymetry grid. Slip, length,
width, and depth are in meters. Angles are in degrees.

### `xyo.dat`

The first four fields are one-based inclusive bounds:

```text
IDS IDE JDS JDE
```

The current writer also appends the full grid dimensions. The deformation and
tsunami readers consume only the first four values.

### `meca.dat`

A fixed-width mechanism record used by the map and travel-time stages. Its
longitude is in the `0..360` frame. Changing its layout affects readers that
expect the old ten-field record.

## Deformation file

`deform_a.grd` contains the initial vertical sea-surface displacement inside
the `xyo.dat` window. Each row follows the first grid axis and contains
nine-character fields with three decimal places. The tsunami stage inserts
this smaller array into the full solver grid.

This file is quantized. Use the in-memory deformation array when studying
differences smaller than its output precision.

## Tsunami files

`green.dat` has one row per sampling time. The first seven-character field is
minutes from the origin; the following fields are elevations at virtual-gauge
indices from `tidal.dat`.

`zmax_a.grd` has the full `2461 x 2056` grid. Each value is the greatest
positive elevation observed at a sampling time. It is not a maximum over every
3-second solver step.

The checkpoint file under `zfolder` is temporary run state, not a scientific
output. It is removed after successful completion. Resume accepts it only when
its version and array layout match the current solver.

## Raw values and reports

| File | Raw solver values? | Transformation |
| --- | --- | --- |
| `deform_a.grd` | Numerical stage output, but fixed-width quantized | Three decimal places |
| `green.dat` | Sampled solver values, but fixed-width quantized | Sampled every 60 s; three decimal places |
| `zmax_a.grd` | Sampled solver maximum, but fixed-width quantized | Updated every 60 s; three decimal places |
| `green_rev.dat` | No | Station-specific empirical amplitude factors |
| `ttt_max.dat` | No | Summary of corrected station values |
| `mareograma.svg` | No | Corrected station values and selected plot scale |
| `maxola.pdf` | No | Grid rescaled so its displayed maximum is 12 m |

## Completion markers and resume

The engine records a stage as complete only after every declared output
exists. On resume, a stage is skipped only when its marker and outputs remain
valid. Removing or renaming an output invalidates that stage.

The tsunami checkpoint is more detailed than a stage marker. It preserves the
time levels and sampled state needed to continue inside the propagation loop.
Any change to the saved arrays, update order, sampling meaning, or buffer-swap
position requires a pipeline-version change.

## Where to make a change

| Research change | Primary location | Required follow-up |
| --- | --- | --- |
| Rupture scaling or rigidity | `calculator.py`, `fault_plane.py` | Document source; update focused values and fault-plane comparisons |
| Mechanism selection | `calculator.py`, `fault_plane.py` | Define longitude and distance rule; test wrap behavior |
| Fault window or depth | `fault_plane.py` | Check `pfalla.inp`, `xyo.dat`, deformation shape, and old-program comparison |
| Deformation equations or singular handling | `deform.py` | Add independent cases; run deformation comparison and golden tests |
| Grid, time step, boundary, or wet-cell rule | `tsunami.py` | Update checkpoint version; run small behavior tests and full comparison |
| Gauge sampling | `tsunami.py` | Update checkpoint meaning and explain whether maxima are sampled |
| Maximum-height visualization | `render/maxola.py` | Keep raw and display values distinct; test grid orientation and scale |
| Station amplitude correction | `render/ttt_max.py` | Record provenance and update report tests |
| Approximate port arrival time | `calculator.py` | Record calibration source and validate intended geographic domain |
| `ttt_client` processing | `render/ttt_inverso.py` | Test command, fixed epicenter format, and GMT grid compatibility |

When a change deliberately breaks compatibility, preserve a small description
of the old behavior in [`legacy.md`](legacy.md) and record why the new behavior
is preferred. Saved expected values should change only after that decision is
documented.
