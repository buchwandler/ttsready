"""Source-neutral, non-mutating residual checks for text units."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from dataclasses import replace

from .errors import InvalidUnitError, PreparationError
from .models import (
    PreparationIssue,
    PreparationProfile,
    PreparedUnit,
    ProtectedSpan,
    TextUnit,
)

_DATE = re.compile(r"(?<!\w)\d{1,4}[/-]\d{1,2}[/-]\d{1,4}(?!\w)")
_TIME = re.compile(r"(?<!\w)\d{1,2}:\d{2}(?:\s*[ap]m)?(?!\w)", re.IGNORECASE)
_DIGITS = re.compile(r"\d+")
_INITIALISM = re.compile(r"\b[A-Z]{2,8}\b")
_ROMAN = re.compile(r"\b[IVXLCDM]{2,}\b")
_OPERATORS = re.compile(r"(?:[=+*/<>^_]{2,}|\d+\s*[=+*/<>^]\s*\d+)")
_MEASUREMENT_SYMBOLS = frozenset("%°µμ℃℉Ω")


def _overlaps_protected(start: int, end: int, spans: tuple[ProtectedSpan, ...]) -> bool:
    return any(span.start < end and start < span.end for span in spans)


def _issue(
    unit: TextUnit,
    code: str,
    severity: str,
    start: int,
    end: int,
    message: str,
) -> PreparationIssue | None:
    if _overlaps_protected(start, end, unit.protected_spans):
        return None
    return PreparationIssue(
        code=code,
        severity=severity,  # type: ignore[arg-type]
        unit_id=unit.id,
        source_start=start,
        source_end=end,
        text=unit.text[start:end],
        message=message,
        provenance={"origin": "ttsready.qa"},
    )


def _scan_unit(unit: TextUnit, profile: PreparationProfile) -> tuple[PreparationIssue, ...]:
    text = unit.text
    issues: list[PreparationIssue] = []

    def add(code: str, severity: str, start: int, end: int, message: str) -> None:
        issue = _issue(unit, code, severity, start, end, message)
        if issue is not None:
            issues.append(issue)

    for index, char in enumerate(text):
        point = ord(char)
        category = unicodedata.category(char)
        if char == "\ufffd":
            add(
                "qa.replacement_character",
                "error",
                index,
                index + 1,
                "Replacement character remains.",
            )
        if (
            0xE000 <= point <= 0xF8FF
            or 0xF0000 <= point <= 0xFFFFD
            or 0x100000 <= point <= 0x10FFFD
        ):
            add(
                "qa.private_use",
                "warning",
                index,
                index + 1,
                "Private-use Unicode character remains.",
            )
        if 0xFDD0 <= point <= 0xFDEF or (point & 0xFFFF) in {0xFFFE, 0xFFFF}:
            add("qa.noncharacter", "error", index, index + 1, "Unicode noncharacter remains.")
        if category in {"Cc", "Cf"} and char not in "\t\n\r\u200c\u200d":
            add(
                "qa.disallowed_control",
                "error",
                index,
                index + 1,
                "Disallowed control/format character remains.",
            )
        if category == "Sc":
            add(
                "qa.currency_symbol",
                "warning",
                index,
                index + 1,
                "Suspicious currency symbol remains.",
            )
        if char in _MEASUREMENT_SYMBOLS:
            add(
                "qa.measurement_symbol",
                "warning",
                index,
                index + 1,
                "Measurement or unit symbol remains.",
            )

    if profile.expand_numbers:
        for match in _DIGITS.finditer(text):
            add(
                "qa.residual_digits",
                "warning",
                *match.span(),
                "Decimal digits remain although number expansion is enabled.",
            )
    for code, expression, message in (
        ("qa.date_candidate", _DATE, "Date-like numeric string remains."),
        ("qa.time_candidate", _TIME, "Time-like numeric string remains."),
        ("qa.initialism_candidate", _INITIALISM, "All-uppercase initialism candidate remains."),
        ("qa.roman_numeral_candidate", _ROMAN, "Roman-numeral candidate remains."),
        ("qa.operator_heavy", _OPERATORS, "Operator-heavy or mathematical text remains."),
    ):
        for match in expression.finditer(text):
            add(code, "warning", *match.span(), message)
    return tuple(issues)


def check_units(
    units: Iterable[TextUnit],
    *,
    profile: PreparationProfile | None = None,
) -> tuple[PreparationIssue, ...]:
    """Report residual risks in caller-provided units without rewriting text."""
    effective_profile = profile or PreparationProfile()
    if not isinstance(effective_profile, PreparationProfile):
        raise PreparationError("profile must be a PreparationProfile")
    issues: list[PreparationIssue] = []
    for unit in units:
        if not isinstance(unit, TextUnit):
            raise InvalidUnitError("check_units accepts only TextUnit values")
        issues.extend(_scan_unit(unit, effective_profile))
    return tuple(issues)


def _output_protected_spans(
    source_unit: TextUnit,
    prepared: PreparedUnit,
) -> tuple[ProtectedSpan, ...]:
    mapped: list[ProtectedSpan] = []
    for span in source_unit.protected_spans:
        shift = sum(
            len(change.replacement) - len(change.source)
            for change in prepared.changes
            if change.source_end <= span.start
        )
        mapped.append(ProtectedSpan(span.start + shift, span.end + shift, span.reason))
    return tuple(mapped)


def _map_issue_to_source(issue: PreparationIssue, prepared: PreparedUnit) -> PreparationIssue:
    start = issue.source_start
    end = issue.source_end
    if start is None or end is None:
        return issue
    for change in prepared.changes:
        if change.output_start < end and start < change.output_end:
            return replace(
                issue,
                source_start=change.source_start,
                source_end=change.source_end,
                text=change.source,
                provenance={
                    **dict(issue.provenance),
                    "output_start": start,
                    "output_end": end,
                },
            )
    source_start = start
    source_end = end
    for change in prepared.changes:
        if change.output_end <= start:
            delta = len(change.replacement) - len(change.source)
            source_start -= delta
            source_end -= delta
    source_start = max(0, min(source_start, len(prepared.source_text)))
    source_end = max(source_start, min(source_end, len(prepared.source_text)))
    return replace(
        issue,
        source_start=source_start,
        source_end=source_end,
        text=prepared.source_text[source_start:source_end],
        provenance={
            **dict(issue.provenance),
            "output_start": start,
            "output_end": end,
        },
    )


def _check_prepared_unit(
    source_unit: TextUnit,
    prepared: PreparedUnit,
    profile: PreparationProfile,
    *,
    strict: bool,
) -> PreparedUnit:
    output_unit = TextUnit(
        id=prepared.unit_id,
        text=prepared.spoken_text,
        language=prepared.language,
        role=prepared.role,
        protected_spans=_output_protected_spans(source_unit, prepared),
    )
    residual = tuple(
        _map_issue_to_source(issue, prepared) for issue in _scan_unit(output_unit, profile)
    )
    result = replace(prepared, issues=(*prepared.issues, *residual))
    if strict and result.errors:
        raise PreparationError(f"strict preparation failed for unit {prepared.unit_id!r}")
    return result


__all__ = ["check_units"]
