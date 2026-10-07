"""Source-neutral lexical review over caller-owned text units or results."""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass

import phrasplit
from spokenform.evidence import LexicalEvidenceProvider, validate_provider

from .identifiers import stable_id
from .models import PreparationResult, TextUnit

DEFAULT_MAX_FREQUENCY_RANK = 10_000
_TOKEN = re.compile(r"[^\W\d_]+(?:['’ʼ\u2010-\u2014][^\W\d_]+)*", re.UNICODE)
_URL_OR_EMAIL = re.compile(
    r"(?i)(?:\b(?:https?://|ftp://|www\.)[^\s<>]+"
    r"|\b[\w.+-]+@[\w.-]+\.[a-z]{2,}\b"
    r"|\b(?:[a-z0-9-]+\.)+[a-z]{2,}\b)"
)


@dataclass(frozen=True, slots=True)
class LexicalOccurrence:
    unit_id: str
    start: int
    end: int
    sentence_index: int | None


@dataclass(frozen=True, slots=True)
class LexicalFinding:
    id: str
    language: str
    surface: str
    normalized: str
    count: int
    known: bool | None
    frequency_rank: int | None
    frequency_count: int | None
    reasons: tuple[str, ...]
    occurrences: tuple[LexicalOccurrence, ...]


@dataclass(frozen=True, slots=True)
class LexicalReviewResult:
    findings: tuple[LexicalFinding, ...]
    units_reviewed: int
    schema: str = "ttsready.lexical-review.v2"


@dataclass(slots=True)
class _Term:
    forms: Counter[str]
    occurrences: list[LexicalOccurrence]
    proper_name: bool = False
    mixed_case: bool = False
    all_caps: bool = False
    unusual_graphemes: bool = False


def _token_spans(text: str) -> tuple[tuple[int, int], ...]:
    spans = []
    for match in _TOKEN.finditer(text):
        start, end = match.span()
        while end < len(text) and unicodedata.category(text[end]).startswith("M"):
            end += 1
        spans.append((start, end))
    return tuple(spans)


def _overlaps(start: int, end: int, spans: tuple[tuple[int, int], ...]) -> bool:
    return any(left < end and start < right for left, right in spans)


def _sentences(text: str, language: str) -> tuple[tuple[int, int], ...]:
    try:
        segments = phrasplit.split_with_offsets(
            text,
            mode="sentence",
            use_spacy=False,
            language=language,
            apply_corrections=False,
        )
    except Exception:
        return ((0, len(text)),) if text else ()
    return tuple((segment.char_start, segment.char_end) for segment in segments)


def _sentence_info(
    text: str,
    language: str,
) -> tuple[tuple[tuple[int, int], ...], frozenset[int]]:
    spans = _sentences(text, language)
    starts: set[int] = set()
    for start, end in spans:
        tokens = _token_spans(text[start:end])
        if tokens:
            starts.add(start + tokens[0][0])
    return spans, frozenset(starts)


def _unusual(surface: str) -> bool:
    return any(
        unicodedata.category(character).startswith("M")
        or unicodedata.category(character) in {"Cf", "Co", "Cs", "Cn"}
        for character in surface
    )


def _mixed_case(surface: str) -> bool:
    return (
        any(character.islower() for character in surface)
        and any(character.isupper() for character in surface)
        and not surface.istitle()
    )


def _rank(finding: LexicalFinding) -> tuple[int, int, int, str, str]:
    reasons = set(finding.reasons)
    unknown = "unknown_to_lexicon" in reasons
    rare = "rare_word" in reasons
    proper_name = "proper_name_candidate" in reasons
    if unknown and proper_name:
        priority = 0
    elif unknown and finding.count > 1:
        priority = 1
    elif unknown:
        priority = 2
    elif rare and proper_name:
        priority = 3
    elif rare and finding.count > 1:
        priority = 4
    elif rare:
        priority = 5
    elif proper_name:
        priority = 6
    elif "contains_unusual_graphemes" in reasons:
        priority = 7
    else:
        priority = 8
    return (
        priority,
        -finding.count,
        -(finding.frequency_rank or 0),
        finding.normalized,
        finding.id,
    )


def review_lexicon(
    units: Iterable[TextUnit] | PreparationResult,
    *,
    provider: LexicalEvidenceProvider | None = None,
    max_frequency_rank: int = DEFAULT_MAX_FREQUENCY_RANK,
    min_count: int = 1,
    max_items: int | None = None,
    unknown_only: bool = False,
    include_all_tokens: bool = False,
) -> LexicalReviewResult:
    """Find lexical candidates without requiring document paths or format context."""
    if max_frequency_rank < 1:
        raise ValueError("max_frequency_rank must be at least 1")
    if min_count < 1:
        raise ValueError("min_count must be at least 1")
    if max_items is not None and max_items < 1:
        raise ValueError("max_items must be at least 1")

    if isinstance(units, PreparationResult):
        review_units = tuple(
            TextUnit(
                unit.unit_id,
                unit.source_text,
                unit.language,
                role=unit.role,
            )
            for unit in units.units
        )
    else:
        review_units = tuple(units)
    if any(not isinstance(unit, TextUnit) for unit in review_units):
        raise TypeError("review_lexicon accepts TextUnit values or a PreparationResult")

    terms: dict[tuple[str, str], _Term] = {}
    language_map: dict[str, str] = {}
    validated_languages: set[str] = set()
    for unit in review_units:
        language_key = unit.language.casefold()
        language_map.setdefault(language_key, unit.language)
        if provider is not None and language_key not in validated_languages:
            validate_provider(provider, unit.language)
            validated_languages.add(language_key)
        blocked = tuple(match.span() for match in _URL_OR_EMAIL.finditer(unit.text))
        protected = tuple((span.start, span.end) for span in unit.protected_spans)
        sentence_spans, sentence_starts = _sentence_info(unit.text, unit.language)
        for start, end in _token_spans(unit.text):
            if _overlaps(start, end, blocked) or _overlaps(start, end, protected):
                continue
            surface = unit.text[start:end]
            letters = [character for character in surface if character.isalpha()]
            if len(letters) == 1 and not _unusual(surface):
                continue
            normalized = surface.casefold()
            key = (language_key, normalized)
            term = terms.get(key)
            if term is None:
                term = _Term(Counter(), [])
                terms[key] = term
            term.forms[surface] += 1
            sentence_index = next(
                (
                    index
                    for index, (sentence_start, sentence_end) in enumerate(sentence_spans)
                    if sentence_start <= start < sentence_end
                ),
                None,
            )
            term.occurrences.append(LexicalOccurrence(unit.id, start, end, sentence_index))
            term.proper_name |= (
                bool(letters)
                and letters[0].isupper()
                and any(character.islower() for character in letters)
                and start not in sentence_starts
            )
            term.mixed_case |= _mixed_case(surface)
            term.all_caps |= len(letters) > 1 and all(character.isupper() for character in letters)
            term.unusual_graphemes |= _unusual(surface)

    findings: list[LexicalFinding] = []
    for (language_key, normalized), term in terms.items():
        count = len(term.occurrences)
        if count < min_count:
            continue
        language = language_map[language_key]
        evidence = None
        if provider is not None:
            evidence = provider.word(normalized)
        known = evidence.known if evidence is not None else None
        rank = evidence.frequency_rank if evidence is not None else None
        frequency_count = evidence.frequency_count if evidence is not None else None
        if unknown_only and known is not False:
            continue
        reasons: list[str] = []
        if known is False:
            reasons.append("unknown_to_lexicon")
        if rank is not None and rank > max_frequency_rank:
            reasons.append("rare_word")
        if term.proper_name:
            reasons.append("proper_name_candidate")
        if term.mixed_case:
            reasons.append("mixed_case")
        if term.all_caps:
            reasons.append("all_caps")
        if term.unusual_graphemes:
            reasons.append("contains_unusual_graphemes")
        if not include_all_tokens and not reasons:
            continue
        surface = min(
            term.forms,
            key=lambda item: (
                -term.forms[item],
                not item.istitle(),
                item.isupper(),
                item.casefold(),
                item,
            ),
        )
        findings.append(
            LexicalFinding(
                id=stable_id("lex", {"language": language_key, "normalized": normalized}),
                language=language,
                surface=surface,
                normalized=normalized,
                count=count,
                known=known,
                frequency_rank=rank,
                frequency_count=frequency_count,
                reasons=tuple(reasons),
                occurrences=tuple(term.occurrences),
            )
        )

    findings.sort(key=_rank)
    if max_items is not None:
        findings = findings[:max_items]
    return LexicalReviewResult(tuple(findings), len(review_units))


__all__ = [
    "LexicalFinding",
    "LexicalOccurrence",
    "LexicalReviewResult",
    "review_lexicon",
]
