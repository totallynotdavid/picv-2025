"""Pipeline sequencing and output collection behavior."""

from pathlib import Path
from typing import Any

import pytest

from tsdhn.domain import CalculationResponse, EarthquakeInput, TsunamiTravelResponse
from tsdhn.engine import (
    SimulationEngine,
    SimulationRequest,
    step_directory,
    write_simulation_outputs,
)
from tsdhn.pipeline.types import ProcessingStep
from tsdhn.runtime import CapabilityStatus, RuntimeContext

INPUT = EarthquakeInput(Mw=8.0, h=10.0, lat0=-10.0, lon0=280.0, hhmm="0000", dia="00")

CALCULATION = CalculationResponse(
    length=1.0,
    width=1.0,
    dislocation=1.0,
    seismic_moment=1.0,
    tsunami_warning="none",
    distance_to_coast=1.0,
    azimuth=1.0,
    dip=1.0,
    epicenter_location="0.00/0.00",
    rectangle_parameters={},
    rectangle_corners=[],
)

TRAVEL_TIMES = TsunamiTravelResponse(
    arrival_times={"PORT": "01:00"},
    distances={"PORT": 100.0},
    epicenter_info={"lat": "0.0"},
)


class _FakeCalculator:
    def __init__(self, model_dir: Path) -> None:
        self.model_dir = model_dir

    def calculate_earthquake_parameters(
        self, data: EarthquakeInput, work_dir: Path
    ) -> CalculationResponse:
        return CALCULATION

    def calculate_tsunami_travel_times(
        self, data: EarthquakeInput
    ) -> TsunamiTravelResponse:
        return TRAVEL_TIMES


def _write_marker(name: str) -> ProcessingStep:
    def runner(working_dir: Path) -> None:
        (working_dir / name).write_text("ok\n")

    return ProcessingStep(name=name, outputs=(name,), runner=runner)


@pytest.fixture
def fake_engine(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> tuple[SimulationEngine, Path]:
    model_dir = tmp_path / "model"
    model_dir.mkdir()

    def fake_resolve(
        cls: type[RuntimeContext],
        model_dir: Path | None = None,
        *,
        model_version: str | None = None,
    ) -> RuntimeContext:
        return RuntimeContext(
            model_dir=model_dir or (tmp_path / "model"),
            model_version="test",
            capabilities={"gmt": CapabilityStatus(name="gmt", available=True)},
        )

    monkeypatch.setattr(RuntimeContext, "resolve", classmethod(fake_resolve))
    monkeypatch.setattr("tsdhn.engine.TsunamiCalculator", _FakeCalculator)
    monkeypatch.setattr("tsdhn.engine.ensure_executables", lambda names: None)
    monkeypatch.setattr(
        "tsdhn.engine.prepare_simulation_workspace", lambda *a, **k: None
    )

    steps = (_write_marker("a.txt"), _write_marker("b.txt"))
    return SimulationEngine(steps=steps), tmp_path


def test_run_executes_steps_in_order_and_reports_progress(
    fake_engine: tuple[SimulationEngine, Path],
) -> None:
    engine, tmp_path = fake_engine
    work_dir = tmp_path / "work"
    work_dir.mkdir()
    events: list[str] = []

    def on_progress(message: str, details: dict[str, Any]) -> None:
        events.append(message)

    request = SimulationRequest(input=INPUT, work_dir=work_dir)
    result = engine.run(request, on_progress=on_progress)

    assert (work_dir / "a.txt").is_file()
    assert (work_dir / "b.txt").is_file()
    assert result.calculation == CALCULATION
    assert result.travel_times == TRAVEL_TIMES
    assert events == [
        "Running earthquake calculations",
        "Earthquake calculations complete",
        "Calculating tsunami travel times",
        "Tsunami calculations complete",
        "Processing a.txt",
        "Processing b.txt",
        "Simulation completed successfully",
    ]


def test_run_skips_completed_steps_on_resume(
    fake_engine: tuple[SimulationEngine, Path],
) -> None:
    engine, tmp_path = fake_engine
    work_dir = tmp_path / "work"
    work_dir.mkdir()

    # Establish completed markers before the resumed run.
    engine.run(SimulationRequest(input=INPUT, work_dir=work_dir))

    events: list[str] = []
    request = SimulationRequest(input=INPUT, work_dir=work_dir, resume=True)
    engine.run(request, on_progress=lambda message, details: events.append(message))

    assert events == [
        "Running earthquake calculations",
        "Earthquake calculations complete",
        "Calculating tsunami travel times",
        "Tsunami calculations complete",
        "Skipping completed step a.txt",
        "Skipping completed step b.txt",
        "Simulation completed successfully",
    ]


def test_step_directory_uses_working_dir_override(tmp_path: Path) -> None:
    plain = ProcessingStep(name="plain", outputs=(), runner=lambda wd: None)
    nested = ProcessingStep(
        name="nested", outputs=(), runner=lambda wd: None, working_dir="sub"
    )

    assert step_directory(tmp_path, plain) == tmp_path
    assert step_directory(tmp_path, nested) == tmp_path / "sub"


def test_write_simulation_outputs_always_includes_json_and_csv(tmp_path: Path) -> None:
    runtime = RuntimeContext(model_dir=tmp_path, model_version="test", capabilities={})
    request = SimulationRequest(input=INPUT, work_dir=tmp_path)

    outputs = write_simulation_outputs(
        request=request,
        calculation=CALCULATION,
        travel_times=TRAVEL_TIMES,
        runtime=runtime,
    )

    names = {output.name for output in outputs.files}
    assert names == {
        "input",
        "runtime",
        "calculation",
        "travel_times_json",
        "travel_times_csv",
    }
    assert (tmp_path / "travel_times.csv").read_text().splitlines()[
        1
    ] == "PORT,01:00,100.0"


def test_write_simulation_outputs_includes_render_outputs_only_when_present(
    tmp_path: Path,
) -> None:
    runtime = RuntimeContext(model_dir=tmp_path, model_version="test", capabilities={})
    request = SimulationRequest(input=INPUT, work_dir=tmp_path)
    (tmp_path / "maxola.pdf").write_bytes(b"%PDF-1.4")

    outputs = write_simulation_outputs(
        request=request,
        calculation=CALCULATION,
        travel_times=TRAVEL_TIMES,
        runtime=runtime,
    )

    by_name = outputs.by_name()
    assert "max_height_map" in by_name
    assert "arrival_time_map" not in by_name
    assert "mareogram" not in by_name
