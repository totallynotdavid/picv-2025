# tsdhn

`tsdhn` is the shared simulation engine and the researcher CLI. The API and
worker call the same engine as the CLI.

## CLI

Install the Python workspace from the repository root, then install a model
dataset:

```sh
mise run install
uv run tsdhn assets install
uv run tsdhn doctor
```

Run a source calculation:

```sh
uv run tsdhn calc --mw 8.0 --lat -20.5 --lon -70.5
```

Run the full pipeline:

```sh
uv run tsdhn run --mw 8.0 --lat -20.5 --lon -70.5
```

Use `--model-version` to select an installed release. Use `--model-dir` to
use a dataset outside the managed model store. Use `--work-dir` to choose the
run directory.

## Runtime

Model assets are resolved in this order:

1. `--model-dir`.
2. `TSDHN_MODEL_DIR`.
3. The installed dataset for the package version, under the TSDHN data home.

`tsdhn assets install` downloads the versioned archive from the TSDHN GitHub
release repository. The default data directory is
`$XDG_DATA_HOME/tsdhn/models`, or `$HOME/.local/share/tsdhn/models` when
`XDG_DATA_HOME` is not set. Set `TSDHN_DATA_HOME` to use another location.

The production pipeline is Python code. The report steps require `gmt` and
`ttt_client` on `PATH`. `scripts/setup.sh` installs those tools and the
compiled `fault_plane`, `deform`, and `tsunami` programs used by parity tests.

## Pipeline

The default pipeline runs these steps:

```text
fault_plane -> deform -> tsunami -> maxola -> ttt_max
ttt_inverso -> point_ttt -> copy_ttt_pdf
```

Each step declares its output files. The engine validates those files and
writes a completion marker. A resumed run skips steps whose marker and outputs
are still valid. The tsunami step also resumes from its checkpoint.

The engine writes these files in the run directory:

| File | Content |
| --- | --- |
| `input.json` | Input parameters |
| `runtime.json` | Model version and tool capabilities |
| `calculation.json` | Source parameters |
| `travel_times.json` | Port arrival times and distances |
| `travel_times.csv` | Arrival times in tabular form |
| `maxola.pdf` | Maximum wave-height map, when produced |
| `ttt.pdf` | Arrival-time map, when produced |
| `mareograma.svg` | Mareogram, when produced |

## Code map

- `tsdhn/domain.py`: public input and response models.
- `tsdhn/engine.py`: pipeline execution and artifact collection.
- `tsdhn/runtime.py`: model validation and tool capability checks.
- `tsdhn/assets.py`: versioned model installation.
- `tsdhn/pipeline/`: step definitions and pipeline composition.
- `tsdhn/render/`: report and map steps.
- `tsdhn/cli/`: Typer commands.
