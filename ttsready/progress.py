"""Source-neutral synchronous preparation progress events."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

PreparationProgressKind = Literal["unit.started", "unit.completed"]


@dataclass(frozen=True, slots=True)
class PreparationProgressEvent:
    """Observation-only progress for one caller-owned text unit."""

    kind: PreparationProgressKind
    completed: int
    total: int
    unit_id: str
    language: str
    role: str


PreparationProgressCallback = Callable[[PreparationProgressEvent], None]


def notify(
    callback: PreparationProgressCallback | None,
    event: PreparationProgressEvent,
) -> None:
    """Synchronously notify the caller, allowing callback exceptions to propagate."""
    if callback is not None:
        callback(event)
