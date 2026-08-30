from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

type StepFunction = Callable[[Path], None]


@dataclass(frozen=True)
class ProcessingStep:
    """One unit of the simulation pipeline.

    `outputs` are paths relative to the step's own working directory (the
    job work_dir, or work_dir/`working_dir` when set). They are checked after
    the step and included in the completion marker used by resumed runs.
    """

    name: str
    outputs: tuple[str, ...]
    runner: StepFunction
    required_system_executables: tuple[str, ...] = ()
    working_dir: str | None = None

    def run(self, working_dir: Path) -> None:
        self.runner(working_dir)
