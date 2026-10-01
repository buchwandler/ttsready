"""Source sentence lookup and formatting for report findings."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import asdict
from typing import Any

from .models import ConversionReport, SentenceContext


def sentences_overlapping(
    sentences: Sequence[SentenceContext], start: int, end: int
) -> tuple[SentenceContext, ...]:
    return tuple(
        sentence for sentence in sentences if sentence.start < end and start < sentence.end
    )


def _sentence_text(sentences: tuple[SentenceContext, ...], fallback: str) -> str:
    return " ".join(sentence.text for sentence in sentences) if sentences else fallback


def context_payload(report: ConversionReport, identifier: str) -> dict[str, Any]:
    change = next((item for item in report.changes if item.id == identifier), None)
    if change is None:
        raise KeyError(f"No Spokenform change found for ID {identifier!r}")
    context = next((item for item in report.contexts if item.id == change.context_id), None)
    if context is None:
        raise KeyError(f"Report context {change.context_id!r} is missing for change {identifier!r}")
    source_sentences = sentences_overlapping(
        context.source_sentences, change.source_start, change.source_end
    )
    spoken_sentences = sentences_overlapping(
        context.spoken_sentences, change.output_start, change.output_end
    )
    section = next(
        (item for item in report.sections if item.section_id == context.section_id), None
    )
    return {
        "change": asdict(change),
        "context": asdict(context),
        "language": report.effective_language,
        "section_title": section.title if section else None,
        "tool_versions": dict(report.tool_versions),
        "source_sentence_text": _sentence_text(source_sentences, context.source_text),
        "spoken_sentence_text": _sentence_text(spoken_sentences, context.spoken_text),
        "source_sentences": [asdict(sentence) for sentence in source_sentences],
        "spoken_sentences": [asdict(sentence) for sentence in spoken_sentences],
    }


def format_context(payload: dict[str, Any], *, paragraph: bool = False) -> str:
    change = payload["change"]
    context: dict[str, Any] = payload["context"]
    section_name = payload["section_title"] or context["section_locator"]
    paragraph_label = "Title" if context["is_title"] else str(context["source_paragraph"] + 1)
    lines = [
        f"Change: {change['id']}",
        f"Section: {context['section_index']:02d} {section_name}",
        f"Section ID: {context['section_id']}",
        f"Paragraph: {paragraph_label}",
        f"Language: {payload['language']}",
        "",
        "Source sentence:",
        str(payload["source_sentence_text"]),
        "",
        "Spoken sentence:",
        str(payload["spoken_sentence_text"]),
        "",
        "Focus:",
        str(change["source"]),
        "-> " + str(change["replacement"]),
        "",
        "Stage: " + ", ".join(change["stages"]),
        "Rule: " + str(change["rule"] or ""),
        "Domain: " + str(change["recognition_domain"] or ""),
        f"Source span: {change['source_start']}:{change['source_end']}",
        f"Output span: {change['output_start']}:{change['output_end']}",
    ]
    if change.get("provenance"):
        lines.append(
            "Provenance: " + json.dumps(change["provenance"], ensure_ascii=False, sort_keys=True)
        )
    if paragraph:
        lines.extend(["", "Source paragraph:", str(context["source_text"])])
    return "\n".join(lines) + "\n"


def format_bug_report(payload: dict[str, Any]) -> str:
    change = payload["change"]
    versions = payload["tool_versions"]
    lines = [
        "### Spokenform reproduction",
        "",
        f"- ttsready: {versions.get('ttsready', 'unknown')}",
        f"- spokenform: {versions.get('spokenform', 'unknown')}",
        f"- language: {payload['language']}",
        f"- rule: `{change['rule'] or ''}`",
        f"- domain: `{change['recognition_domain'] or ''}`",
        f"- change id: `{change['id']}`",
        "",
        "Input sentence:",
        "",
        "```text",
        str(payload["source_sentence_text"]),
        "```",
        "",
        "Current spoken output:",
        "",
        "```text",
        str(payload["spoken_sentence_text"]),
        "```",
        "",
        "Focused replacement:",
        "",
        "```text",
        str(change["source"]),
        "-> " + str(change["replacement"]),
        "```",
        "",
        "Expected behavior:",
        "",
        "```text",
        "<fill in expected spoken form>",
        "```",
        "",
    ]
    return "\n".join(lines)


def render_context_json(payload: dict[str, Any], *, paragraph: bool = False) -> str:
    if not paragraph:
        payload = {key: value for key, value in payload.items() if key != "context"}
    return json.dumps(payload, ensure_ascii=False, indent=2)
