"""Provider-neutral uncommon-word review and lexical context lookup."""

from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from spokenform.evidence import LexicalEvidenceProvider, validate_provider

from .identifiers import stable_id
from .models import (
    ContextRecord,
    ConversionReport,
    LexicalFinding,
    LexicalOccurrence,
    LexicalReviewReport,
)
from .pipeline import prepare
from .readers import load

if TYPE_CHECKING:
    from .models import Document


DEFAULT_MAX_FREQUENCY_RANK = 10_000
_TOKEN = re.compile(r"[^\W\d_]+(?:['’ʼ\u2010-\u2014][^\W\d_]+)*", re.UNICODE)
_URL_OR_EMAIL = re.compile(
    r"(?i)(?:\b(?:https?://|ftp://|www\.)[^\s<>]+"
    r"|\b[\w.+-]+@[\w.-]+\.[a-z]{2,}\b"
    r"|\b(?:[a-z0-9-]+\.)+[a-z]{2,}\b)"
)


@dataclass(slots=True)
class _Term:
    forms: Counter[str] = field(default_factory=Counter)
    occurrences: list[LexicalOccurrence] = field(default_factory=list)
    proper_name: bool = False
    mixed_case: bool = False
    all_caps: bool = False
    unusual_graphemes: bool = False


def _token_spans(text: str) -> list[tuple[int, int]]:
    spans = []
    for match in _TOKEN.finditer(text):
        start, end = match.span()
        while end < len(text) and unicodedata.category(text[end]).startswith("M"):
            end += 1
        spans.append((start, end))
    return spans


def _blocked_spans(text: str) -> tuple[tuple[int, int], ...]:
    return tuple(match.span() for match in _URL_OR_EMAIL.finditer(text))


def _overlaps(start: int, end: int, spans: tuple[tuple[int, int], ...]) -> bool:
    return any(left < end and start < right for left, right in spans)


def _sentence_starts(context: ContextRecord) -> dict[str, int | None]:
    starts = {}
    for sentence in context.source_sentences:
        token_spans = _token_spans(sentence.text)
        starts[sentence.id] = sentence.start + token_spans[0][0] if token_spans else None
    return starts


def _occurrence_sentence(
    context: ContextRecord,
    start: int,
    sentence_starts: dict[str, int | None],
) -> tuple[str | None, bool]:
    sentence = next(
        (item for item in context.source_sentences if item.start <= start < item.end), None
    )
    if sentence is None:
        return None, False
    return sentence.id, sentence_starts[sentence.id] == start


def _is_unusual(surface: str) -> bool:
    return any(
        unicodedata.category(character).startswith("M")
        or unicodedata.category(character) in {"Cf", "Co", "Cs", "Cn"}
        for character in surface
    )


def _is_mixed_case(surface: str) -> bool:
    return any(character.islower() for character in surface) and any(
        character.isupper() for character in surface
    ) and not surface.istitle()


def _candidate_reasons(
    term: _Term,
    known: bool | None,
    rank: int | None,
    cutoff: int,
) -> tuple[str, ...]:
    reasons = []
    if known is False:
        reasons.append("unknown_to_lexicon")
    if rank is not None and rank > cutoff:
        reasons.append("rare_word")
    if term.proper_name:
        reasons.append("proper_name_candidate")
    if term.mixed_case:
        reasons.append("mixed_case")
    if term.all_caps:
        reasons.append("all_caps")
    if term.unusual_graphemes:
        reasons.append("contains_unusual_graphemes")
    return tuple(reasons)


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


def review_contexts(
    contexts: tuple[ContextRecord, ...],
    *,
    language: str,
    source_path: str,
    source_sha256: str | None,
    tool_versions: dict[str, str],
    provider: LexicalEvidenceProvider | None = None,
    max_frequency_rank: int = DEFAULT_MAX_FREQUENCY_RANK,
    min_count: int = 1,
    max_items: int | None = None,
    unknown_only: bool = False,
    include_all_tokens: bool = False,
) -> LexicalReviewReport:
    """Aggregate and rank candidate tokens from source context records."""
    if max_frequency_rank < 1:
        raise ValueError("max_frequency_rank must be at least 1")
    if min_count < 1:
        raise ValueError("min_count must be at least 1")
    if max_items is not None and max_items < 1:
        raise ValueError("max_items must be at least 1")
    if provider is not None:
        validate_provider(provider, language)

    terms: dict[str, _Term] = defaultdict(_Term)
    for context in contexts:
        blocked = _blocked_spans(context.source_text)
        sentence_starts = _sentence_starts(context)
        for start, end in _token_spans(context.source_text):
            if _overlaps(start, end, blocked):
                continue
            surface = context.source_text[start:end]
            letters = [character for character in surface if character.isalpha()]
            if len(letters) == 1 and not _is_unusual(surface):
                continue
            sentence_id, sentence_initial = _occurrence_sentence(
                context, start, sentence_starts
            )
            normalized = surface.casefold()
            term = terms[normalized]
            term.forms[surface] += 1
            term.occurrences.append(
                LexicalOccurrence(context.id, start, end, sentence_id)
            )
            term.proper_name |= (
                bool(letters)
                and letters[0].isupper()
                and any(character.islower() for character in letters)
                and not sentence_initial
            )
            term.mixed_case |= _is_mixed_case(surface)
            term.all_caps |= len(letters) > 1 and all(
                character.isupper() for character in letters
            )
            term.unusual_graphemes |= _is_unusual(surface)

    findings = []
    for normalized, term in terms.items():
        count = len(term.occurrences)
        if count < min_count:
            continue
        evidence = provider.word(normalized) if provider is not None else None
        known = evidence.known if evidence is not None else None
        frequency_rank = evidence.frequency_rank if evidence is not None else None
        frequency_count = evidence.frequency_count if evidence is not None else None
        if unknown_only and known is not False:
            continue
        reasons = _candidate_reasons(term, known, frequency_rank, max_frequency_rank)
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
                id=stable_id("lex", {"language": language.casefold(), "normalized": normalized}),
                surface=surface,
                normalized=normalized,
                count=count,
                known=known,
                frequency_rank=frequency_rank,
                frequency_count=frequency_count,
                reasons=reasons,
                occurrences=tuple(term.occurrences),
            )
        )

    findings.sort(key=_rank)
    if max_items is not None:
        findings = findings[:max_items]
    return LexicalReviewReport(
        source_path=source_path,
        language=language,
        source_sha256=source_sha256,
        tool_versions=dict(tool_versions),
        findings=tuple(findings),
    )


def review_document(
    document: Document,
    *,
    language: str | None = None,
    provider: LexicalEvidenceProvider | None = None,
    max_frequency_rank: int = DEFAULT_MAX_FREQUENCY_RANK,
    min_count: int = 1,
    max_items: int | None = None,
    unknown_only: bool = False,
) -> LexicalReviewReport:
    """Create review candidates from one loaded source document."""
    conversion = prepare(
        document,
        language=language,
        max_paragraph_chars=None,
        apply_spokenform=False,
        include_titles=True,
    ).report
    if conversion is None:
        raise ValueError("Source preparation did not produce contexts")
    return review_contexts(
        tuple(conversion.contexts),
        language=conversion.effective_language,
        source_path=conversion.source_path,
        source_sha256=conversion.source_sha256,
        tool_versions=conversion.tool_versions,
        provider=provider,
        max_frequency_rank=max_frequency_rank,
        min_count=min_count,
        max_items=max_items,
        unknown_only=unknown_only,
    )


def review_source(
    source: str | Path,
    **options: Any,
) -> LexicalReviewReport:
    """Load a supported source and review uncommon words."""
    return review_document(load(source), **options)


def render_review(report: LexicalReviewReport, format: str) -> str:
    if format == "json":
        return json.dumps(asdict(report), ensure_ascii=False, indent=2)
    if format != "md":
        raise ValueError("Review format must be 'md' or 'json'")
    lines = [
        "# ttsready review",
        "",
        f"- Source: `{report.source_path}`",
        f"- Language: {report.language}",
        f"- Source SHA-256: {report.source_sha256 or 'unavailable'}",
        "",
        "## Uncommon word candidates",
        "",
        "| ID | Word | Count | Known | Frequency rank | Reasons |",
        "| --- | --- | ---: | --- | ---: | --- |",
    ]
    if not report.findings:
        lines.append("| | No candidates | 0 | | | |")
    for finding in report.findings:
        known = "yes" if finding.known is True else "no" if finding.known is False else "unknown"
        rank = "" if finding.frequency_rank is None else str(finding.frequency_rank)
        lines.append(
            f"| `{finding.id}` | {_markdown_cell(finding.surface)} | {finding.count} "
            f"| {known} | {rank} | {', '.join(finding.reasons)} |"
        )
    return "\n".join(lines) + "\n"


def _markdown_cell(value: str) -> str:
    return value.replace("\\", "\\\\").replace("|", "\\|").replace("\n", "<br>")


def write_review(path: str | Path, report: LexicalReviewReport, format: str) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(render_review(report, format), encoding="utf-8", newline="\n")


def lexical_context_payload(
    report: ConversionReport,
    identifier: str,
    *,
    paragraph: bool = False,
) -> dict[str, Any]:
    """Resolve a lexical ID to its source sentence occurrences."""
    review = review_contexts(
        tuple(report.contexts),
        language=report.effective_language,
        source_path=report.source_path,
        source_sha256=report.source_sha256,
        tool_versions=report.tool_versions,
        include_all_tokens=True,
    )
    finding = next((item for item in review.findings if item.id == identifier), None)
    if finding is None:
        raise KeyError(f"No lexical finding found for ID {identifier!r}")
    contexts = {context.id: context for context in report.contexts}
    occurrences = []
    for occurrence in finding.occurrences:
        context = contexts[occurrence.context_id]
        sentence = next(
            (
                sentence
                for sentence in context.source_sentences
                if sentence.id == occurrence.sentence_id
            ),
            None,
        )
        section = next(
            (item for item in report.sections if item.section_id == context.section_id),
            None,
        )
        item = {
            "context_id": occurrence.context_id,
            "section_id": context.section_id,
            "section_locator": context.section_locator,
            "section_title": section.title if section else None,
            "section_index": context.section_index,
            "source_paragraph": context.source_paragraph,
            "start": occurrence.start,
            "end": occurrence.end,
            "sentence_id": occurrence.sentence_id,
            "sentence_text": sentence.text if sentence else context.source_text,
        }
        if paragraph:
            item["paragraph_text"] = context.source_text
        occurrences.append(item)
    return {
        "lexical_finding": asdict(finding),
        "language": report.effective_language,
        "tool_versions": dict(report.tool_versions),
        "occurrences": occurrences,
    }


def format_lexical_context(payload: dict[str, Any]) -> str:
    finding = payload["lexical_finding"]
    lines = [
        f"Lexical finding: {finding['id']}",
        f"Word: {finding['surface']}",
        f"Count: {finding['count']}",
        f"Reasons: {', '.join(finding['reasons']) or 'not re-evaluated'}",
        "",
    ]
    for index, occurrence in enumerate(payload["occurrences"], start=1):
        title = occurrence["section_title"] or occurrence["section_locator"]
        paragraph = (
            "Title"
            if occurrence["source_paragraph"] < 0
            else str(occurrence["source_paragraph"] + 1)
        )
        lines.extend(
            [
                f"Occurrence {index}: {title}, paragraph {paragraph}, "
                f"span {occurrence['start']}:{occurrence['end']}",
                str(occurrence["sentence_text"]),
            ]
        )
        if "paragraph_text" in occurrence:
            lines.extend(["Full paragraph:", occurrence["paragraph_text"]])
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
