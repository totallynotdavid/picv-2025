# Testing numerical and research changes

The test groups answer different questions. No single group establishes that
the model is scientifically correct.

## Fast behavior tests

`mise run test` runs the normal Python suite without starting services. The
numerical tests use small arrays and focused files to check behavior such as:

- source-parameter units and known values;
- longitude conversion and grid-window truncation;
- singular branches and float32 deformation output;
- wet and dry cell rules;
- continuity, boundary, and momentum update behavior;
- fixed-width file formats;
- checkpoint rejection and resume equivalence;
- report grid orientation and display scaling.

The strongest focused tests use expected values derived independently from the
production implementation. Examples include hand-computed shallow-water cells,
sentinel values that expose unexpected writes, and an independent fixed-width
reader. A test that copies the production loop or formula can preserve the
same bug and should be avoided unless no smaller observable behavior exists.

Run one test with:

```sh
uv run pytest packages/tsdhn/tests/test_tsunami.py::test_mass_step_hand_computed
```

## Golden pipeline tests

`mise run test-golden` runs the Python pipeline with real GMT and
`ttt_client`. It checks complete output sets, fixed-width file fingerprints,
and selected spatial values.

Golden tests answer: did the Python pipeline output change for this saved
scenario? They do not establish whether the old or new result is physically
correct.

Aggregate statistics can miss a transposed or rearranged grid, so the suite
also checks values at known coordinates. A deliberate numerical change should
inspect spatial output, not only update means and maxima.

## Legacy comparison tests

`mise run test-parity` compares Python checkpoints with saved MATLAB runs or
compiled Fortran output. These tests establish whether Python reproduces the
selected older implementation within the stated tolerance.

They do not prove that the older implementation is correct. They can preserve
old mistakes, inherited calibrations, or a limited geographic assumption.

The tsunami comparison builds the fault-plane and deformation input once and
gives that same initial condition to both propagation solvers. This isolates
the shallow-water solver. It does not independently compare the complete
fault-plane-to-tsunami chain.

Tolerances must account for float32 rounding and fixed-width output
quantization. They should still be narrow enough to catch a meaningful change.
Document why a tolerance exists; do not widen it only because a comparison
started failing.

## Saved MATLAB data

Saved MATLAB arrays are captured evidence, not self-explaining constants. The
comparison package README describes how to refresh them. A refresh should
record:

- the scenario and input values;
- the MATLAB source and command used;
- the checkpoint names;
- why a new capture is needed;
- whether the expected scientific behavior changed.

Do not refresh saved data to hide an unexplained difference.

## Choosing tests for a change

| Change | Minimum evidence |
| --- | --- |
| Refactor with no intended numerical change | Focused behavior tests and relevant legacy comparison |
| File-format change | Independent reader/writer test and downstream stage test |
| Float dtype or evaluation-order change | Focused edge cases, legacy comparison, and golden spatial inspection |
| New scientific relation | Unit test from an independent worked example plus source citation |
| Boundary or wet-cell rule | Hand-computed small-grid tests and propagation comparison |
| Checkpoint layout or meaning | Interrupted/resumed equivalence and pipeline-version rejection |
| Display-only transformation | Raw-value preservation test and explicit report transformation test |
| Empirical correction | Provenance, intended domain, direct behavior tests, and report regression test |

## Reviewing a numerical test

Ask:

1. What observable behavior does this test protect?
2. Is the expected result independent of the implementation?
3. Are units, coordinate frame, dtype, and indexing explicit?
4. Does a tolerance represent known rounding or merely make the test pass?
5. Is the scenario scientifically relevant, or only combinatorial?
6. Could both Python and the older program share the same error?
7. If expected data changed, is the research reason recorded?

Pairwise input generation improves combinations but does not establish
scientific coverage of earthquake scenarios. Add named research cases when a
tectonic setting, magnitude range, depth, coastline relation, or numerical
edge case matters.
