from pathlib import Path

import pytest

from tsdhn.pipeline.types import ProcessingStep
from tsdhn.utils.processing import is_step_complete, process_step


def _write_output(working_dir: Path) -> None:
    (working_dir / "out.txt").write_text("done\n")


def _make_step(name: str = "toy") -> ProcessingStep:
    return ProcessingStep(name=name, outputs=("out.txt",), runner=_write_output)


def test_is_step_complete_false_before_running(tmp_path: Path) -> None:
    assert not is_step_complete(_make_step(), tmp_path)


def test_process_step_marks_step_complete(tmp_path: Path) -> None:
    step = _make_step()
    process_step(step, tmp_path)

    assert (tmp_path / "out.txt").is_file()
    assert is_step_complete(step, tmp_path)


def test_process_step_raises_when_a_declared_output_is_missing(
    tmp_path: Path,
) -> None:
    """Declared outputs must exist before a completion marker is written."""
    step = ProcessingStep(
        name="toy",
        outputs=("out.txt", "never_written.txt"),
        runner=_write_output,
    )

    with pytest.raises(FileNotFoundError, match=r"never_written\.txt"):
        process_step(step, tmp_path)

    assert not is_step_complete(step, tmp_path)


def test_is_step_complete_false_if_output_deleted_after_marker(tmp_path: Path) -> None:
    step = _make_step()
    process_step(step, tmp_path)
    (tmp_path / "out.txt").unlink()

    assert not is_step_complete(step, tmp_path)


def test_is_step_complete_false_on_pipeline_version_bump(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    step = _make_step()
    process_step(step, tmp_path)
    assert is_step_complete(step, tmp_path)

    import tsdhn.utils.processing as processing_module

    monkeypatch.setattr(processing_module, "PIPELINE_VERSION", 999)

    assert not is_step_complete(step, tmp_path)


def test_is_step_complete_false_for_different_step_outputs(tmp_path: Path) -> None:
    step = _make_step()
    process_step(step, tmp_path)

    changed_step = ProcessingStep(
        name=step.name,
        outputs=("out.txt", "extra.txt"),
        runner=step.runner,
    )
    assert not is_step_complete(changed_step, tmp_path)
