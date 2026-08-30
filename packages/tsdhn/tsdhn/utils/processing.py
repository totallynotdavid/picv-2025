import hashlib
from pathlib import Path

from tsdhn.pipeline.types import ProcessingStep
from tsdhn.pipeline_version import PIPELINE_VERSION
from tsdhn.utils.file_utils import atomic_write, validate_outputs

__all__ = ["is_step_complete", "process_step"]


def _marker_path(working_dir: Path, step: ProcessingStep) -> Path:
    return working_dir / f".{step.name}.complete"


def _fingerprint(step: ProcessingStep) -> str:
    payload = f"{PIPELINE_VERSION}:{step.name}:{','.join(step.outputs)}"
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def is_step_complete(step: ProcessingStep, working_dir: Path) -> bool:
    """Return whether a resumed run can skip `step`."""
    marker = _marker_path(working_dir, step)
    if not marker.is_file() or marker.read_text().strip() != _fingerprint(step):
        return False
    try:
        validate_outputs(working_dir, step)
    except FileNotFoundError:
        return False
    return True


def process_step(step: ProcessingStep, working_dir: Path) -> None:
    step.run(working_dir)
    validate_outputs(working_dir, step)
    with atomic_write(_marker_path(working_dir, step)) as tmp_path:
        tmp_path.write_text(_fingerprint(step))
