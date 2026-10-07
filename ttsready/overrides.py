"""Source-neutral matching and conflict resolution for speech overrides."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from .errors import InvalidUnitError, OverrideConflictError
from .models import PreparationIssue, SpeechOverride, TextUnit


@dataclass(frozen=True, slots=True)
class OverrideMatch:
    start: int
    end: int
    override: SpeechOverride
    priority: int


def overlaps(left: tuple[int, int], right: tuple[int, int]) -> bool:
    """Return whether two half-open source spans overlap."""
    return left[0] < right[1] and right[0] < left[1]


def _matches(text: str, override: SpeechOverride) -> tuple[tuple[int, int], ...]:
    expression = re.escape(override.surface)
    if override.match == "word":
        expression = rf"(?<![\w'-]){expression}(?![\w'-])"
    flags = 0 if override.case_sensitive else re.IGNORECASE
    return tuple((item.start(), item.end()) for item in re.finditer(expression, text, flags))


def resolve_overrides(
    unit: TextUnit,
    overrides: Iterable[SpeechOverride],
) -> tuple[tuple[OverrideMatch, ...], tuple[PreparationIssue, ...]]:
    """Resolve occurrence, unit, and global overrides against one exact source unit."""
    candidates: list[tuple[int, int, SpeechOverride, int, int]] = []
    for order, override in enumerate(overrides):
        scope = override.scope
        if scope.kind == "all":
            priority = 1
            occurrences = _matches(unit.text, override)
        elif scope.unit_id != unit.id:
            continue
        elif scope.kind == "unit":
            priority = 2
            occurrences = _matches(unit.text, override)
        else:
            priority = 3
            start = scope.source_start
            end = scope.source_end
            assert start is not None and end is not None
            if end > len(unit.text) or unit.text[start:end] != override.surface:
                raise InvalidUnitError(
                    f"occurrence override {override.id!r} must exactly match its source surface"
                )
            occurrences = ((start, end),)
            if override.match == "word" and (start, end) not in _matches(unit.text, override):
                raise InvalidUnitError(
                    f"occurrence override {override.id!r} does not match its word boundary"
                )
        candidates.extend((start, end, override, priority, order) for start, end in occurrences)

    candidates.sort(key=lambda item: (-item[3], -(item[1] - item[0]), item[4], item[0]))
    selected: list[OverrideMatch] = []
    issues: list[PreparationIssue] = []
    for start, end, override, priority, _order in candidates:
        source_span = (start, end)
        if any(overlaps(source_span, (span.start, span.end)) for span in unit.protected_spans):
            issues.append(
                PreparationIssue(
                    code="override.protected_overlap",
                    severity="warning",
                    unit_id=unit.id,
                    source_start=start,
                    source_end=end,
                    text=unit.text[start:end],
                    message=f"Override {override.id} skipped because the source span is protected.",
                    provenance={"override_id": str(override.id)},
                )
            )
            continue
        conflicts = [item for item in selected if overlaps(source_span, (item.start, item.end))]
        if not conflicts:
            selected.append(OverrideMatch(start, end, override, priority))
            continue
        for previous in conflicts:
            if previous.priority == priority and previous.override.spoken != override.spoken:
                raise OverrideConflictError(
                    f"Equal-priority overrides {previous.override.id} and {override.id} overlap "
                    f"at {start}:{end} with different replacements"
                )
        blockers = [item for item in conflicts if item.priority >= priority]
        if blockers:
            issues.append(
                PreparationIssue(
                    code="override.lower_priority_overlap",
                    severity="warning",
                    unit_id=unit.id,
                    source_start=start,
                    source_end=end,
                    text=unit.text[start:end],
                    message=(
                        f"Override {override.id} skipped because a "
                        "higher-priority override applies."
                    ),
                    provenance={
                        "override_id": str(override.id),
                        "blocking_override_ids": [str(item.override.id) for item in blockers],
                    },
                )
            )
            continue
        selected.append(OverrideMatch(start, end, override, priority))

    selected.sort(key=lambda item: (item.start, item.end))
    return tuple(selected), tuple(issues)


__all__ = ["OverrideMatch", "overlaps", "resolve_overrides"]
