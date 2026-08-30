from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

type StepFunction = Callable[[Path], None]


@dataclass(frozen=True)
class ProcessingStep:
    """One unit of the simulation pipeline.

    `outputs` are paths relative to the step's own working directory (the
    job work_dir, or work_dir/`working_dir` when set). They serve double
    duty: they are validated after the step runs, and they are hashed into
    the step-completion marker that lets a resumed run skip this step.
    Those used to be two separate fields expressed in two different frames
    -- `outputs` (work_dir-relative, only ever hashed) and `file_checks`
    (step_dir-relative, only ever validated) -- which meant the declared
    outputs were never actually checked against disk.
    """

    name: str
    outputs: tuple[str, ...]
    runner: StepFunction
    required_system_executables: tuple[str, ...] = ()
    working_dir: str | None = None

    def run(self, working_dir: Path) -> None:
        self.runner(working_dir)
