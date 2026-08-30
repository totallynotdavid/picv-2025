from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import numpy as np

type OnCheckpoint = Callable[[str, Any], None]


@dataclass(frozen=True)
class Checkpoint:
    name: str
    value: np.ndarray

    @staticmethod
    def of(name: str, value: Any) -> Checkpoint:
        return Checkpoint(name=name, value=np.asarray(value))


@dataclass(frozen=True)
class Trace:
    case_id: str
    checkpoints: tuple[Checkpoint, ...]  # Checkpoint order defines the trace.

    def by_name(self) -> dict[str, Checkpoint]:
        return {checkpoint.name: checkpoint for checkpoint in self.checkpoints}


class CheckpointRecorder:
    """Collect named checkpoints emitted by a Python adapter."""

    def __init__(self) -> None:
        self._checkpoints: list[Checkpoint] = []

    def __call__(self, name: str, value: Any) -> None:
        self._checkpoints.append(Checkpoint.of(name, value))

    def trace(self, case_id: str) -> Trace:
        return Trace(case_id=case_id, checkpoints=tuple(self._checkpoints))
