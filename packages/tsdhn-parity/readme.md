# tsdhn-parity

`tsdhn-parity` compares the Python engine with saved MATLAB runs and compiled
Fortran output. It is test support, not production code.

These comparisons protect compatibility. Agreement means that Python matches
the selected older program within an explicit tolerance. It does not prove
that either result is physically correct. An older program can contain an
error, an empirical calibration, or an assumption that applies only to its
original research setting.

## Run it

```sh
mise run test-parity
```

Saved MATLAB runs and Python cases run without MATLAB. Fortran cases run only
when `TSDHN_TOOLS_DIR` points to the compiled older programs. Missing optional
programs cause those cases to skip.

The active deformation executable must be compiled from `model/def_oka.f`.
`model/deform.for` is an older Mansinha-Smylie implementation and does not test
the Okada-based Python port.

## Layout

- `tsdhn_parity/cases.py`: exhaustive and pairwise input generation.
- `tsdhn_parity/trace.py`: checkpoint and trace types.
- `tsdhn_parity/compare.py`: checkpoint comparison and tolerances.
- `tsdhn_parity/adapters/`: runners for Python, Fortran, and saved traces.
- `tsdhn_parity/pytest_plugin.py`: pytest integration.
- `packages/tsdhn/tests/parity/<unit>/`: comparison cases, readers,
  tolerances, and saved data.

Each checkpoint isolates a named intermediate result. Readers for old
fixed-width files must use the declared field width because whitespace parsing
can hide a malformed record. Tolerances account for float32 rounding and file
quantization; they should not be widened without identifying the difference.

The tsunami comparison gives the same fault-plane and deformation result to
both propagation solvers. This is deliberate: it isolates propagation. It
does not compare the full fault-plane, deformation, and propagation chain as
independent runs.

## Refresh saved MATLAB runs

Use the capture command when saved data needs to change:

```sh
uv run python scripts/capture_matlab_fixtures.py fault_plane
uv run python scripts/capture_matlab_fixtures.py fault_plane --case alaska_1964
```

The command needs a MathWorks container and license. It writes committed
`.npz` files. Pytest reads those files and does not start MATLAB.

Before replacing a saved run, record the input case, MATLAB source, checkpoint
names, and reason for the change. Do not replace expected data only because a
comparison failed.

## Interpreting a failure

A comparison failure can come from:

- a real change in equations or update order;
- float32 evaluation order;
- one-based versus zero-based indices;
- longitude conversion;
- fixed-width output rounding;
- a different old executable than the one the Python stage ports;
- a stale or incorrectly captured MATLAB run.

First compare the earliest failing checkpoint. Later checkpoints often differ
only because an earlier stage changed. See the engine's
[`testing.md`](../tsdhn/docs/testing.md) and
[`legacy.md`](../tsdhn/docs/legacy.md) guides for the limits of comparison
tests and the active source map.
