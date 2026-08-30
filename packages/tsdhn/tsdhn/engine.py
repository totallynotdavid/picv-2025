import csv
import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tsdhn.calculator import TsunamiCalculator
from tsdhn.domain import CalculationResponse, EarthquakeInput, TsunamiTravelResponse
from tsdhn.external import ensure_executables
from tsdhn.pipeline.types import ProcessingStep
from tsdhn.runtime import RuntimeContext
from tsdhn.utils.file_utils import prepare_simulation_workspace
from tsdhn.utils.processing import is_step_complete, process_step

__all__ = [
    "Artifact",
    "ArtifactBundle",
    "ProgressCallback",
    "SimulationEngine",
    "SimulationRequest",
    "SimulationResult",
    "run_simulation",
    "step_directory",
    "write_artifact_bundle",
]


def step_directory(work_dir: Path, step: ProcessingStep) -> Path:
    """Where `step` runs: the job work_dir, or a subdirectory of it."""
    return work_dir / step.working_dir if step.working_dir else work_dir


ProgressCallback = Callable[[str, dict[str, Any]], None]


def _noop(_message: str, _details: dict[str, Any]) -> None:
    return None


@dataclass(frozen=True)
class SimulationRequest:
    input: EarthquakeInput
    work_dir: Path
    model_dir: Path | None = None
    model_version: str | None = None
    # Preserve an existing work_dir instead of wiping it, so completed step
    # outputs and any tsunami checkpoint survive. The compute plane sets
    # this when a crashed job is requeued onto the same work_dir; the
    # researcher CLI leaves it False so every run starts clean.
    resume: bool = False


@dataclass(frozen=True)
class Artifact:
    name: str
    path: Path
    content_type: str


@dataclass(frozen=True)
class ArtifactBundle:
    root: Path
    artifacts: tuple[Artifact, ...]

    def by_name(self) -> dict[str, Artifact]:
        return {artifact.name: artifact for artifact in self.artifacts}


@dataclass(frozen=True)
class SimulationResult:
    calculation: CalculationResponse
    travel_times: TsunamiTravelResponse
    runtime: RuntimeContext
    bundle: ArtifactBundle


class SimulationEngine:
    def __init__(self, steps: tuple[ProcessingStep, ...] | None = None) -> None:
        if steps is None:
            from tsdhn.pipeline.registry import DEFAULT_PIPELINE

            steps = DEFAULT_PIPELINE
        self.steps = steps

    def run(
        self,
        request: SimulationRequest,
        *,
        on_progress: ProgressCallback = _noop,
    ) -> SimulationResult:
        runtime = RuntimeContext.resolve(
            model_dir=request.model_dir,
            model_version=request.model_version,
        )
        calculator = TsunamiCalculator(runtime.model_dir)
        prepare_simulation_workspace(
            runtime.model_dir, request.work_dir, resume=request.resume
        )

        on_progress("Running earthquake calculations", {})
        calculation = calculator.calculate_earthquake_parameters(
            request.input,
            request.work_dir,
        )
        on_progress(
            "Earthquake calculations complete",
            {"calculation": calculation.model_dump(mode="json")},
        )

        on_progress("Calculating tsunami travel times", {})
        travel_times = calculator.calculate_tsunami_travel_times(request.input)
        on_progress(
            "Tsunami calculations complete",
            {"travel_times": travel_times.model_dump(mode="json")},
        )

        system_executables = tuple(
            executable
            for step in self.steps
            for executable in step.required_system_executables
        )
        ensure_executables(system_executables)
        total_steps = len(self.steps)
        for index, step in enumerate(self.steps, start=1):
            step_dir = step_directory(request.work_dir, step)
            step_dir.mkdir(parents=True, exist_ok=True)

            if request.resume and is_step_complete(step, step_dir):
                on_progress(
                    f"Skipping completed step {step.name}",
                    {
                        "step": step.name,
                        "step_index": index,
                        "total_steps": total_steps,
                    },
                )
                continue

            on_progress(
                f"Processing {step.name}",
                {"step": step.name, "step_index": index, "total_steps": total_steps},
            )
            process_step(step, step_dir)

        bundle = write_artifact_bundle(
            request=request,
            calculation=calculation,
            travel_times=travel_times,
            runtime=runtime,
        )
        on_progress(
            "Simulation completed successfully",
            {"artifacts": [a.name for a in bundle.artifacts]},
        )
        return SimulationResult(
            calculation=calculation,
            travel_times=travel_times,
            runtime=runtime,
            bundle=bundle,
        )


def run_simulation(
    data: EarthquakeInput,
    work_dir: Path,
    *,
    model_dir: Path | None = None,
    model_version: str | None = None,
    resume: bool = False,
    on_progress: ProgressCallback = _noop,
) -> SimulationResult:
    request = SimulationRequest(
        input=data,
        work_dir=work_dir,
        model_dir=model_dir,
        model_version=model_version,
        resume=resume,
    )
    return SimulationEngine().run(request, on_progress=on_progress)


def write_artifact_bundle(
    *,
    request: SimulationRequest,
    calculation: CalculationResponse,
    travel_times: TsunamiTravelResponse,
    runtime: RuntimeContext,
) -> ArtifactBundle:
    root = request.work_dir
    _write_json(root / "input.json", request.input.model_dump(mode="json"))
    _write_json(root / "calculation.json", calculation.model_dump(mode="json"))
    _write_json(root / "travel_times.json", travel_times.model_dump(mode="json"))
    _write_travel_times_csv(root / "travel_times.csv", travel_times)
    _write_json(
        root / "runtime.json",
        {
            "model_dir": str(runtime.model_dir),
            "model_version": runtime.model_version,
            "capabilities": {
                name: {
                    "available": status.available,
                    "version": status.version,
                    "path": status.path,
                    "detail": status.detail,
                }
                for name, status in runtime.capabilities.items()
            },
        },
    )

    artifacts = [
        Artifact("input", root / "input.json", "application/json"),
        Artifact("runtime", root / "runtime.json", "application/json"),
        Artifact("calculation", root / "calculation.json", "application/json"),
        Artifact("travel_times_json", root / "travel_times.json", "application/json"),
        Artifact("travel_times_csv", root / "travel_times.csv", "text/csv"),
    ]
    for name, relative_path, content_type in (
        ("max_height_map", "maxola.pdf", "application/pdf"),
        ("arrival_time_map", "ttt.pdf", "application/pdf"),
        ("mareogram", "mareograma.svg", "image/svg+xml"),
    ):
        path = root / relative_path
        if path.is_file():
            artifacts.append(Artifact(name, path, content_type))

    return ArtifactBundle(root=root, artifacts=tuple(artifacts))


def _write_json(path: Path, data: object) -> None:
    path.write_text(
        json.dumps(data, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_travel_times_csv(path: Path, travel_times: TsunamiTravelResponse) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["port", "arrival_time", "distance_km"])
        for port, arrival_time in travel_times.arrival_times.items():
            writer.writerow([port, arrival_time, travel_times.distances.get(port, "")])
