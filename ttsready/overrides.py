"""Find and apply literal, source-anchored speech overrides."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .sidecar import SpeechOverride


class OverrideConflictError(ValueError):
    """Raised when equal-priority overrides disagree over an overlapping source span."""


@dataclass(frozen=True, slots=True)
class OverrideMatch:
    start: int
    end: int
    override: SpeechOverride
    scope_priority: int
    order: int

    @property
    def priority(self) -> tuple[int, int]:
        return self.scope_priority, self.end - self.start


@dataclass(frozen=True, slots=True)
class AppliedOverride:
    match: OverrideMatch
    output_start: int
    output_end: int


def _scope_priority(
    override: SpeechOverride,
    *,
    context_id: str,
    section_id: str,
    section_locator: str,
) -> int | None:
    scope = override.scope
    scope_type = scope.get("type", "document")
    if scope_type == "document":
        return 1
    if scope_type == "section":
        if scope.get("section_id") == section_id or scope.get("section_locator") == section_locator:
            return 2
        return None
    if scope.get("context_id") != context_id:
        return None
    return 3


def _matches(text: str, override: SpeechOverride) -> list[tuple[int, int]]:
    escaped = re.escape(override.surface)
    if override.match == "word":
        escaped = rf"(?<![\w'-]){escaped}(?![\w'-])"
    flags = 0 if override.case_sensitive else re.IGNORECASE
    return [(match.start(), match.end()) for match in re.finditer(escaped, text, flags)]


def find_overrides(
    text: str,
    overrides: tuple[SpeechOverride, ...],
    *,
    context_id: str,
    section_id: str,
    section_locator: str,
) -> tuple[OverrideMatch, ...]:
    candidates: list[OverrideMatch] = []
    for order, override in enumerate(overrides):
        priority = _scope_priority(
            override,
            context_id=context_id,
            section_id=section_id,
            section_locator=section_locator,
        )
        if priority is None:
            continue
        scope = override.scope
        for start, end in _matches(text, override):
            if scope.get("type") == "occurrence":
                if scope.get("source_start") is not None and (
                    scope["source_start"] != start or scope["source_end"] != end
                ):
                    continue
            candidates.append(OverrideMatch(start, end, override, priority, order))

    candidates.sort(
        key=lambda item: (
            -item.scope_priority,
            -(item.end - item.start),
            item.order,
            item.start,
        )
    )
    selected: list[OverrideMatch] = []
    for candidate in candidates:
        overlaps = [
            item for item in selected if item.start < candidate.end and candidate.start < item.end
        ]
        if not overlaps:
            selected.append(candidate)
            continue
        for previous in overlaps:
            if (
                previous.priority == candidate.priority
                and previous.override.spoken != candidate.override.spoken
            ):
                raise OverrideConflictError(
                    f"Conflicting sidecar overrides overlap {candidate.start}:{candidate.end}: "
                    f"{previous.override.id} and {candidate.override.id}"
                )
    return tuple(sorted(selected, key=lambda item: item.start))


def _replacement_field(item: Any, name: str) -> Any:
    return item.get(name) if isinstance(item, dict) else getattr(item, name)


def apply_overrides(
    text: str,
    matches: tuple[OverrideMatch, ...],
    source_replacements: tuple[Any, ...],
) -> tuple[str, tuple[AppliedOverride, ...]]:
    if not matches:
        return text, ()

    output = text
    applied: list[AppliedOverride] = []
    custom_delta = 0
    for match in matches:
        spokenform_delta = sum(
            len(_replacement_field(replacement, "replacement"))
            - len(_replacement_field(replacement, "source"))
            for replacement in source_replacements
            if _replacement_field(replacement, "source_end") <= match.start
        )
        output_start = match.start + spokenform_delta + custom_delta
        output_end = output_start + len(match.override.spoken)
        applied.append(AppliedOverride(match, output_start, output_end))
        custom_delta += len(match.override.spoken) - (match.end - match.start)

    for item in reversed(applied):
        start = item.output_start
        end = start + (item.match.end - item.match.start)
        output = output[:start] + item.match.override.spoken + output[end:]
    return output, tuple(applied)
