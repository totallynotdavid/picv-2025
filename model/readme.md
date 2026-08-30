# Model and older reference files

This directory contains model inputs plus MATLAB and Fortran programs used to
understand or compare the Python implementation. Not every source file is part
of the active pipeline.

The Python engine uses installed copies of the required model files. The
sources here also support development and legacy comparison tests.

## Active older references

| File | Role |
| --- | --- |
| `fault_plane.f90` | Active reference for fault placement, mechanism selection, source dimensions, slip, and intermediate files |
| `def_oka.f` | Active deformation comparison; Okada-based vertical displacement for one fault segment |
| `tsunami1.for` | Active reference for the linear shallow-water propagation solver |

`scripts/setup.sh` and this directory's `Makefile` compile `def_oka.f` as the
`deform` executable. `packages/tsdhn/tsdhn/deform.py` ports this program.

## Historical and exploratory sources

| File | Status |
| --- | --- |
| `deform.for` | Older Mansinha-Smylie deformation program. It is not the reference for the Python deformation stage. |
| `fault_plane_n.m` | Exploratory multiple-subfault MATLAB path with spherical geometry. It is not used by the current single-fault pipeline. |
| `mareografo_a.m` | Historical manual helper. Its source-editing instructions are not current run instructions. |

Do not build `deform.for` and use its output to judge compatibility with
`deform.py`. The two programs implement different deformation models.

## Model inputs

| Path | Use |
| --- | --- |
| `bathy/grid_a.grd` | Full propagation bathymetry grid |
| `bathy/xa.dat`, `bathy/ya.dat` | Grid axes used to place the fault and deformation window |
| `mecfoc.dat` | Candidate focal mechanisms used when strike and dip are absent from public input |
| `tidal.dat` | Virtual-gauge indices for propagation output |
| `puertos.txt` | Ports used by approximate arrival-time calculations |
| `pacifico.mat`, `maper1.mat` | Bathymetry and coastline data used by source calculations |
| `ttt_mundo/` | Inputs consumed by `ttt_client` and GMT arrival-time reporting |

Files such as `pfalla.inp`, `xyo.dat`, `meca.dat`, `deform_a.grd`, and
`zfolder/*` are also checked in as captured examples. During a run they are
generated intermediate or output files, not immutable model inputs.

## Coordinate and format warnings

The model grid uses longitudes in the `0..360` frame. Public earthquake inputs
normally use `-180..180`. The active fault-plane stage converts between them.

Intermediate files preserve one-based Fortran indices and fixed-width numeric
records. Their exact layouts are described in
[`packages/tsdhn/docs/pipeline.md`](../packages/tsdhn/docs/pipeline.md).

## What comparison establishes

Compiled Fortran output can show that Python preserved the selected old
program's behavior. It does not establish that the equations, constants, or
empirical corrections are scientifically valid. See
[`packages/tsdhn/docs/testing.md`](../packages/tsdhn/docs/testing.md) before
using comparison output as research evidence.

Keep an older source until its active behavior, file formats, and remaining
provenance have been documented. Original MATLAB and Fortran files are frozen;
explain corrections in researcher documentation rather than editing those
sources.
