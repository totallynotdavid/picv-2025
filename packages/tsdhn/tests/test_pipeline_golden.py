import shutil
import statistics
import subprocess
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest

from tsdhn.domain import EarthquakeInput
from tsdhn.engine import SimulationResult, run_simulation

pytestmark = pytest.mark.golden

MODEL_DIR = Path(__file__).resolve().parents[3] / "model"
SCENARIO = EarthquakeInput(
    Mw=9.0, h=12.0, lat0=56.0, lon0=-156.0, hhmm="0000", dia="23"
)

# The toolchain produces small floating-point differences between runs. This
# tolerance leaves room for that noise while still catching science changes.
REL_TOL = 1e-4

# The production pipeline needs GMT and ttt_client. It does not need legacy
# binaries.
SKIP_REASON = "requires gmt + ttt_client on PATH; see mise run test-golden"


def _toolchain_available() -> bool:
    return shutil.which("gmt") is not None and shutil.which("ttt_client") is not None


@pytest.fixture(scope="module")
def golden_result() -> Iterator[SimulationResult]:
    if not _toolchain_available():
        pytest.skip(SKIP_REASON)

    # GMT uses Ghostscript for PDF output. The default temporary directory is
    # allowed by the container's Ghostscript policy.
    work_root = Path(tempfile.mkdtemp(prefix="tsdhn-golden-"))
    try:
        yield run_simulation(SCENARIO, work_root, model_dir=MODEL_DIR)
    finally:
        shutil.rmtree(work_root, ignore_errors=True)


def _fingerprint_text(path: Path) -> dict[str, float | int]:
    text = path.read_text()
    values = [float(x) for x in text.split()]
    return {
        "line_count": len(text.splitlines()),
        "value_count": len(values),
        "min": min(values),
        "max": max(values),
        "mean": statistics.fmean(values),
    }


def test_simulation_produces_expected_outputs(
    golden_result: SimulationResult,
) -> None:
    names = {output.name for output in golden_result.outputs.files}
    assert names == {
        "input",
        "runtime",
        "calculation",
        "travel_times_json",
        "travel_times_csv",
        "max_height_map",
        "arrival_time_map",
        "mareogram",
    }


def test_pfalla_inp_fingerprint(golden_result: SimulationResult) -> None:
    fp = _fingerprint_text(golden_result.outputs.root / "pfalla.inp")
    # The Python port writes one line. The Fortran reader accepts
    # whitespace-separated fields.
    assert fp["line_count"] == 1
    assert fp["value_count"] == 9
    assert fp["min"] == pytest.approx(8.0, rel=REL_TOL)
    assert fp["max"] == pytest.approx(575440.2, rel=REL_TOL)
    assert fp["mean"] == pytest.approx(80605.53208444444, rel=REL_TOL)


def test_green_dat_fingerprint(golden_result: SimulationResult) -> None:
    fp = _fingerprint_text(golden_result.outputs.root / "zfolder" / "green.dat")
    assert fp["line_count"] == 1681
    assert fp["value_count"] == 30258
    assert fp["min"] == pytest.approx(-0.22, rel=REL_TOL)
    assert fp["max"] == pytest.approx(1680.0, rel=REL_TOL)
    assert fp["mean"] == pytest.approx(46.66686595280587, rel=REL_TOL)


def test_zmax_a_grd_fingerprint(golden_result: SimulationResult) -> None:
    fp = _fingerprint_text(golden_result.outputs.root / "zfolder" / "zmax_a.grd")
    assert fp["line_count"] == 2461
    assert fp["value_count"] == 5059816
    assert fp["min"] == pytest.approx(0.0, abs=1e-9)
    assert fp["max"] == pytest.approx(14.441, rel=REL_TOL)
    assert fp["mean"] == pytest.approx(0.03851133361371243, rel=REL_TOL)


def test_zmax_a_grd_preserves_spatial_samples(golden_result: SimulationResult) -> None:
    """Aggregate statistics cannot detect a spatially rearranged grid."""
    path = golden_result.outputs.root / "zfolder" / "zmax_a.grd"
    samples = {}
    wanted = {(1000, 2), (1000, 1000), (1232, 2), (1232, 2000), (2000, 1000)}
    with path.open() as stream:
        for row_number, line in enumerate(stream, start=1):
            if row_number not in {row for row, _column in wanted}:
                continue
            values = line.split()
            for row, column in wanted:
                if row == row_number:
                    samples[(row, column)] = float(values[column - 1])

    assert samples == pytest.approx(
        {
            (1000, 2): 0.027,
            (1000, 1000): 0.038,
            (1232, 2): 0.038,
            (1232, 2000): 0.220,
            (2000, 1000): 0.064,
        },
        rel=REL_TOL,
    )


def test_green_rev_dat_fingerprint(golden_result: SimulationResult) -> None:
    fp = _fingerprint_text(golden_result.outputs.root / "zfolder" / "green_rev.dat")
    assert fp["line_count"] == 1681
    assert fp["value_count"] == 6724
    assert fp["min"] == pytest.approx(-0.28353207, rel=REL_TOL)
    assert fp["max"] == pytest.approx(28.0, rel=REL_TOL)
    assert fp["mean"] == pytest.approx(3.4998662468186943, rel=REL_TOL)


def test_ttt_max_dat_fingerprint(golden_result: SimulationResult) -> None:
    fp = _fingerprint_text(golden_result.outputs.root / "ttt_max.dat")
    assert fp["line_count"] == 17
    assert fp["value_count"] == 34
    assert fp["min"] == pytest.approx(0.06, rel=REL_TOL)
    assert fp["max"] == pytest.approx(954.0, rel=REL_TOL)
    assert fp["mean"] == pytest.approx(444.84117647058827, rel=REL_TOL)


def test_ttt_b_fingerprint(golden_result: SimulationResult) -> None:
    ttt_mundo_dir = golden_result.outputs.root / "ttt_mundo"
    result = subprocess.run(
        [shutil.which("gmt") or "gmt", "grdinfo", "-C", "-L1", "-L2", "ttt.b=bf"],
        cwd=ttt_mundo_dir,
        capture_output=True,
        text=True,
        check=True,
    )
    # grdinfo -C always prefixes the row with the grid name/path.
    fields = result.stdout.strip().split("\t")[1:]
    (
        x_min,
        x_max,
        y_min,
        y_max,
        z_min,
        z_max,
        x_inc,
        y_inc,
        n_columns,
        n_rows,
        median,
        mad,
        mean,
        stdev,
        rms,
        registration,
        n_bands,
    ) = fields

    assert (float(x_min), float(x_max)) == pytest.approx((120.0, 300.0))
    assert (float(y_min), float(y_max)) == pytest.approx((-80.0, 89.0))
    assert (float(x_inc), float(y_inc)) == pytest.approx(
        (0.0666666666667, 0.0666666666667)
    )
    assert int(n_columns) == 2701
    assert int(n_rows) == 2536
    assert int(registration) == 0
    assert int(n_bands) == 1

    assert float(z_min) == pytest.approx(0.0, abs=1e-9)
    assert float(z_max) == pytest.approx(56.8421516418, rel=REL_TOL)
    assert float(median) == pytest.approx(11.3055953979, rel=REL_TOL)
    assert float(mad) == pytest.approx(6.00670206013, rel=REL_TOL)
    assert float(mean) == pytest.approx(11.9470979091, rel=REL_TOL)
    assert float(stdev) == pytest.approx(6.21503040015, rel=REL_TOL)
    assert float(rms) == pytest.approx(13.466987178, rel=REL_TOL)


if __name__ == "__main__":
    pytest.main([__file__])
