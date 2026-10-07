"""Pure JSON-compatible serialization for source-neutral preparation results."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .models import (
    PreparationIssue,
    PreparationResult,
    PreparationStats,
    PreparedUnit,
    SentenceSpan,
    SpokenChange,
    UnitContext,
)


def _plain(value: Any) -> Any:
    if hasattr(value, "__dataclass_fields__"):
        return {name: _plain(getattr(value, name)) for name in value.__dataclass_fields__}
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain(item) for item in value]
    return value


def result_to_dict(result: PreparationResult) -> dict[str, Any]:
    """Return a detached, JSON-ready representation without writing any files."""
    if not isinstance(result, PreparationResult):
        raise TypeError("result_to_dict expects a PreparationResult")
    return _plain(result)


def _sentence(data: Mapping[str, Any]) -> SentenceSpan:
    return SentenceSpan(
        index=int(data["index"]),
        text=str(data["text"]),
        start=int(data["start"]),
        end=int(data["end"]),
    )


def _change(data: Mapping[str, Any]) -> SpokenChange:
    return SpokenChange(
        id=str(data["id"]),
        unit_id=str(data["unit_id"]),
        source_start=int(data["source_start"]),
        source_end=int(data["source_end"]),
        output_start=int(data["output_start"]),
        output_end=int(data["output_end"]),
        source=str(data["source"]),
        replacement=str(data["replacement"]),
        stages=tuple(str(item) for item in data.get("stages", ())),
        kind=str(data.get("kind", "normalization")),
        rule=(str(data["rule"]) if data.get("rule") is not None else None),
        recognition_domain=(
            str(data["recognition_domain"]) if data.get("recognition_domain") is not None else None
        ),
        provenance=dict(data.get("provenance", {})),
    )


def _issue(data: Mapping[str, Any]) -> PreparationIssue:
    return PreparationIssue(
        code=str(data["code"]),
        severity=data["severity"],
        unit_id=str(data["unit_id"]),
        source_start=(int(data["source_start"]) if data.get("source_start") is not None else None),
        source_end=(int(data["source_end"]) if data.get("source_end") is not None else None),
        text=(str(data["text"]) if data.get("text") is not None else None),
        message=str(data["message"]),
        provenance=dict(data.get("provenance", {})),
    )


def _unit_context(data: Mapping[str, Any] | None) -> UnitContext | None:
    if data is None:
        return None
    return UnitContext(
        unit_id=str(data["unit_id"]),
        role=str(data["role"]),
        language=str(data["language"]),
        source_text=str(data["source_text"]),
        spoken_text=str(data["spoken_text"]),
        source_sentences=tuple(_sentence(item) for item in data.get("source_sentences", ())),
        spoken_sentences=tuple(_sentence(item) for item in data.get("spoken_sentences", ())),
    )


def _prepared_unit(data: Mapping[str, Any]) -> PreparedUnit:
    return PreparedUnit(
        unit_id=str(data["unit_id"]),
        source_text=str(data["source_text"]),
        spoken_text=str(data["spoken_text"]),
        language=str(data["language"]),
        role=str(data["role"]),
        changes=tuple(_change(item) for item in data.get("changes", ())),
        issues=tuple(_issue(item) for item in data.get("issues", ())),
        context=_unit_context(data.get("context")),
    )


def result_from_dict(data: Mapping[str, Any]) -> PreparationResult:
    """Rebuild a result from its JSON-ready representation."""
    if not isinstance(data, Mapping):
        raise TypeError("result_from_dict expects a mapping")
    if data.get("schema") != "ttsready.preparation.v2":
        raise ValueError(f"unsupported preparation result schema: {data.get('schema')!r}")
    stats = data["stats"]
    result_stats = PreparationStats(
        units_processed=int(stats["units_processed"]),
        units_changed=int(stats["units_changed"]),
        changes=int(stats["changes"]),
        stage_edits=dict(stats.get("stage_edits", {})),
        rules=dict(stats.get("rules", {})),
        recognition_domains=dict(stats.get("recognition_domains", {})),
        structured_numeric_edits=int(stats.get("structured_numeric_edits", 0)),
        source_digit_replacements=int(stats.get("source_digit_replacements", 0)),
        warning_count=int(stats.get("warning_count", 0)),
        error_count=int(stats.get("error_count", 0)),
    )
    return PreparationResult(
        units=tuple(_prepared_unit(item) for item in data.get("units", ())),
        changes=tuple(_change(item) for item in data.get("changes", ())),
        issues=tuple(_issue(item) for item in data.get("issues", ())),
        stats=result_stats,
        profile_fingerprint=str(data["profile_fingerprint"]),
        override_fingerprint=str(data["override_fingerprint"]),
        runtime_fingerprint=str(data["runtime_fingerprint"]),
        prepared_fingerprint=str(data["prepared_fingerprint"]),
        schema=str(data["schema"]),
    )


preparation_result_to_dict = result_to_dict
preparation_result_from_dict = result_from_dict

__all__ = [
    "preparation_result_from_dict",
    "preparation_result_to_dict",
    "result_from_dict",
    "result_to_dict",
]
