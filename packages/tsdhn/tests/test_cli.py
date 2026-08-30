from pathlib import Path

import pytest
from typer.testing import CliRunner

import tsdhn.cli.main as cli_module
from tsdhn.domain import CalculationResponse, TsunamiTravelResponse
from tsdhn.runtime import RuntimeContext

RUNNER = CliRunner()

CALCULATION = CalculationResponse(
    length=10.0,
    width=20.0,
    dislocation=1.5,
    seismic_moment=2.0e18,
    tsunami_warning="warning",
    distance_to_coast=30.0,
    azimuth=40.0,
    dip=50.0,
    epicenter_location="mar",
    rectangle_parameters={},
    rectangle_corners=[],
)

TRAVEL_TIMES = TsunamiTravelResponse(
    arrival_times={"Callao": "12:36 05Aug"},
    distances={"Callao": 19.7},
    epicenter_info={},
)


class _Calculator:
    def __init__(self, _model_dir: Path) -> None:
        pass

    def calculate_earthquake_parameters(
        self, _data: object, _output_dir: Path
    ) -> CalculationResponse:
        return CALCULATION

    def calculate_tsunami_travel_times(self, _data: object) -> TsunamiTravelResponse:
        return TRAVEL_TIMES


def test_calc_command_prints_source_and_arrival_results(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    runtime = RuntimeContext(model_dir=tmp_path, model_version="test", capabilities={})
    monkeypatch.setattr(
        RuntimeContext,
        "resolve",
        classmethod(lambda cls, **kwargs: runtime),
    )
    monkeypatch.setattr(cli_module, "TsunamiCalculator", _Calculator)

    result = RUNNER.invoke(cli_module.app, ["calc", "--model-dir", str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert "Source parameters" in result.output
    assert "Rupture length (km)" in result.output
    assert "Callao" in result.output
    assert "12:36 05Aug" in result.output


def test_run_command_reports_a_failed_simulation_and_keeps_the_run_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    work_dir = tmp_path / "failed-run"

    def fail(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError("model step failed")

    monkeypatch.setattr(cli_module, "run_simulation", fail)

    result = RUNNER.invoke(
        cli_module.app,
        ["run", "--work-dir", str(work_dir)],
    )

    assert result.exit_code == 1
    assert "Simulation failed" in result.output
    assert "Inspect run directory" in result.output
    assert str(work_dir) in result.output
