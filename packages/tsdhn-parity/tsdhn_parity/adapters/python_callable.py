from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from tsdhn_parity.cases import Case
from tsdhn_parity.trace import CheckpointRecorder, Trace


@dataclass(frozen=True)
class PythonCallableAdapter:
    """Run a Python implementation and record its checkpoints and result."""

    fn: Callable[..., Any]
    map_params: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None
    result_checkpoint: str | None = "result"

    def run(self, case: Case) -> Trace:
        recorder = CheckpointRecorder()
        kwargs = self.map_params(case.params) if self.map_params else case.params
        result = self.fn(**kwargs, on_checkpoint=recorder)
        if self.result_checkpoint is not None:
            recorder(self.result_checkpoint, result)
        return recorder.trace(case.id)
