# tsdhn-parity

`tsdhn-parity` compares Python results with captured MATLAB traces and
compiled Fortran outputs. It reports the first checkpoint that differs.

The package is test-only. Production code does not import it.

## Run it

```sh
mise run test-parity
```

Fortran-backed cases skip when `TSDHN_TOOLS_DIR` does not contain the required
binaries. The Python and frozen-fixture cases run without the legacy toolchain.

## Layout

- `tsdhn_parity/cases.py` builds exhaustive and pairwise case lists.
- `tsdhn_parity/trace.py` defines checkpoints and traces.
- `tsdhn_parity/compare.py` compares traces with per-checkpoint tolerances.
- `tsdhn_parity/adapters/` runs Python functions, Fortran binaries, or frozen
  NumPy fixtures.
- `tsdhn_parity/pytest_plugin.py` provides the pytest helpers.
- `packages/tsdhn/tests/parity/<unit>/` contains unit-specific cases, readers,
  tolerances, and fixtures.

## MATLAB fixtures

Run `scripts/capture_matlab_fixtures.py` by hand when a MATLAB fixture needs
to be refreshed. It runs the MATLAB driver in the MathWorks container and
writes an `.npz` fixture. Pytest reads the committed fixture and does not need
MATLAB, Docker, or a license.
