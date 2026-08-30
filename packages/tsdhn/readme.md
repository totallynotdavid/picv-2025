# tsdhn

`tsdhn` is the simulation engine and researcher CLI. The CLI, API, and worker
run the same Python pipeline.

The Python implementation is replacing a collection of MATLAB and Fortran
programs. The engine preserves legacy behavior to demonstrate successful
porting, but compatibility does not establish scientific validity.

## Start here

Install the Python workspace and model files:

```sh
mise run install
uv run tsdhn assets install
uv run tsdhn doctor
```

Calculate source parameters without running the propagation model:

```sh
uv run tsdhn calc --mw 8.0 --lat -20.5 --lon -70.5
```

Run the full pipeline:

```sh
uv run tsdhn run --mw 8.0 --lat -20.5 --lon -70.5
```

Use `--model-version` to select installed model files, `--model-dir` to use a
specific model directory, and `--work-dir` to keep a run in a known directory.

## Researcher guides

- [`docs/science.md`](docs/science.md) explains units, coordinates, equations,
  numerical assumptions, and empirical corrections.
- [`docs/pipeline.md`](docs/pipeline.md) explains each stage, its files,
  checkpoints, and where to make changes.
- [`docs/legacy.md`](docs/legacy.md) maps the active Python stages to the older
  MATLAB and Fortran programs.
- [`docs/testing.md`](docs/testing.md) explains unit, golden, and legacy
  comparison tests and the limits of each test type.
- [`model/readme.md`](../../model/readme.md) inventories the checked-in model
  files and identifies active and historical references.

Read these guides before changing a formula, array layout, coordinate
conversion, fixed-width file, or pipeline checkpoint.

## Model files and external programs

Model files resolve in this order:

1. `--model-dir`.
2. `TSDHN_MODEL_DIR`.
3. The installed model version for the package.

`tsdhn assets install` downloads a versioned archive from the TSDHN GitHub
release repository. The default model directory is
`$XDG_DATA_HOME/tsdhn/models`, or `$HOME/.local/share/tsdhn/models` when
`XDG_DATA_HOME` is not set. Set `TSDHN_DATA_HOME` to use another location.

The report stages call GMT and `ttt_client`. The older Fortran programs are
needed only for comparison tests.

## Pipeline summary

```text
fault_plane -> deform -> tsunami -> maxola -> ttt_max
ttt_inverso -> point_ttt -> copy_ttt_pdf
```

Each stage declares its output files. The engine writes a completion marker
after those files exist. A resumed run skips a stage only when its marker and
outputs are still valid. The tsunami stage also saves its numerical state so a
worker restart can continue the propagation loop.

The main researcher outputs are:

| File | Meaning |
| --- | --- |
| `calculation.json` | Source parameters and fault rectangle |
| `travel_times.json` | Port arrival times and distances |
| `zfolder/green.dat` | Raw sampled solver elevation at virtual gauges |
| `zfolder/zmax_a.grd` | Raw sampled maximum positive solver elevation |
| `maxola.pdf` | Display map made from a rescaled copy of `zmax_a.grd` |
| `ttt.pdf` | Arrival-time map produced with `ttt_client` and GMT |
| `mareograma.svg` | Selected station series after empirical scaling |

`maxola.pdf` and `mareograma.svg` do not show untouched solver values. See the
science guide before using them for quantitative analysis.

## Code map

- `tsdhn/calculator.py`: source parameters and approximate port arrival times.
- `tsdhn/fault_plane.py`: fault placement and stage input files.
- `tsdhn/deform.py`: Okada-based vertical displacement compatibility port.
- `tsdhn/tsunami.py`: linear shallow-water compatibility solver.
- `tsdhn/pipeline/`: stage definitions and order.
- `tsdhn/render/`: maps, station summaries, and report transformations.
- `tsdhn/engine.py`: run setup, stage execution, resume markers, and output
  collection.
- `tsdhn/runtime.py`: model validation and external-program checks.
- `tsdhn/assets.py`: versioned model installation.
- `tsdhn/cli/`: researcher commands.

Service deployment is documented in [`DEPLOY.md`](../../DEPLOY.md). System
responsibilities and request flow are documented in
[`ARCHITECTURE.md`](../../ARCHITECTURE.md).
