"""Human-readable and machine-readable conversion reports."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .models import ConversionReport
from .output import OutputPlan


def report_format(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix not in {".md", ".json"}:
        raise ValueError("Report path suffix must be .md or .json")
    return suffix[1:]


def validate_report_path(path: Path, *, format: str | None = None) -> None:
    if format is None:
        report_format(path)
    elif format not in {"md", "json"}:
        raise ValueError("Report format must be 'md' or 'json'")
    elif path.suffix and report_format(path) != format:
        raise ValueError(f"Report path suffix {path.suffix.lower()} conflicts with format {format}")
    if path.exists() and path.is_dir():
        raise ValueError(f"Report path is a directory: {path}")
    for parent in path.parents:
        if parent.exists() and not parent.is_dir():
            raise ValueError(f"Report parent is not a directory: {parent}")


def json_report(report: ConversionReport) -> str:
    data = asdict(report)
    data["spokenform"].update(
        abbreviation_edits=report.spokenform.abbreviation_edits,
        number_edits=report.spokenform.number_edits,
        structured_edits=report.spokenform.structured_edits,
    )
    return json.dumps(data, ensure_ascii=False, indent=2)


def _cell(value: object) -> str:
    text = str(value).replace("\\", "\\\\").replace("|", "\\|")
    return text.replace("\r\n", "\n").replace("\n", "<br>")


def markdown_report(report: ConversionReport) -> str:
    title = report.document_title or Path(report.source_path).name
    tool_versions = ", ".join(
        f"{name} {value}" for name, value in sorted(report.tool_versions.items())
    )
    portable_metadata = (
        _cell(json.dumps(report.ssmd_semantics, ensure_ascii=False, sort_keys=True))
        if report.ssmd_semantics
        else "none"
    )
    lines = [
        "# ttsready report",
        "",
        "## Source",
        "",
        f"- Path: `{_cell(report.source_path)}`",
        f"- Input format: {report.input_format}",
        f"- Document title: {_cell(title)}",
        "",
        "## Configuration",
        "",
        f"- Metadata language: {report.metadata_language or 'not set'}",
        f"- Requested language: {report.requested_language or 'not specified'}",
        f"- Effective language: {report.effective_language}",
        f"- Stored sequence fallback: {report.stored_sequence_fallback_mode or 'not specified'}",
        f"- Effective sequence fallback: "
        f"{report.effective_sequence_fallback_mode or 'unavailable'}",
        f"- Output layout: {report.output_layout}",
        "",
        "## Workspace",
        "",
        f"- Type: {report.workspace_type or 'standalone'}",
        f"- Status: {report.workspace_status or 'not applicable'}",
        f"- Dirty chapters: "
        f"{', '.join(report.dirty_chapters) if report.dirty_chapters else 'none'}",
        "",
        "## SSMD semantics",
        "",
        "- Generic TXT output is intentionally lossy for SSMD-only voice, "
        "pause, and prosody delivery semantics.",
        f"- Portable metadata: {portable_metadata}",
        "",
        "## Reproducibility",
        "",
        f"- Source SHA-256: {report.source_sha256 or 'unavailable'}",
        f"- Prepared output SHA-256: {report.prepared_output_sha256 or 'unavailable'}",
        f"- Analysis ID: {report.analysis_id or 'not cached'}",
        f"- Tool versions: {tool_versions or 'unavailable'}",
        f"- Normalization profile SHA-256: {report.normalization_profile_sha256 or 'unavailable'}",
        f"- Pronunciation profile SHA-256: {report.pronunciation_profile_sha256 or 'unavailable'}",
        f"- Runtime fingerprint: {report.runtime_fingerprint or 'unavailable'}",
        "",
        "## Section selection",
        "",
        (
            "| # | Level | Title | Input chars | Source paragraphs | "
            "Prepared paragraphs | Spokenform changes | Output chars |"
        ),
        "| ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for section in report.sections:
        section_title = section.title or f"Section {section.index}"
        lines.append(
            f"| {section.index} | {section.level} | {_cell(section_title)} "
            f"| {section.input_chars} | {section.source_paragraphs} "
            f"| {section.prepared_paragraphs} | {section.spokenform_changes} "
            f"| {section.output_chars} |"
        )
    lines.extend(
        [
            "",
            "## Conversion summary",
            "",
            f"- Sections: {report.selected_sections} / {report.total_sections}",
            f"- Input characters: {report.input_chars}",
            f"- Source paragraphs: {report.source_paragraphs}",
            f"- Prepared paragraphs: {report.prepared_paragraphs}",
            f"- Output characters: {report.output_chars}",
            f"- Output lines: {report.output_lines}",
            "",
            "## Spokenform summary",
            "",
            f"- Paragraphs/titles processed: {report.spokenform.paragraphs_processed}",
            f"- Paragraphs/titles changed: {report.spokenform.paragraphs_changed}",
            f"- Calls: {report.spokenform.calls}",
            f"- Changed calls: {report.spokenform.changed_calls}",
            f"- Source replacements: {report.spokenform.source_replacements}",
            f"- Structured edits: {report.spokenform.structured_edits}",
            f"- Structured numeric edits: {report.spokenform.structured_numeric_edits}",
            f"- Abbreviation edits: {report.spokenform.abbreviation_edits}",
            f"- Plain-number edits: {report.spokenform.number_edits}",
            (
                "- Source spans containing digits changed: "
                f"{report.spokenform.source_digit_replacements}"
            ),
            f"- Warnings: {report.spokenform.warnings}",
            "",
            "## Spokenform stages",
            "",
            "| Stage | Edits |",
            "| --- | ---: |",
        ]
    )
    lines.extend(
        f"| {_cell(stage)} | {count} |"
        for stage, count in sorted(report.spokenform.stage_edits.items())
    )
    lines.extend(["", "## Rules", "", "| Rule | Count |", "| --- | ---: |"])
    lines.extend(
        f"| {_cell(rule)} | {count} |" for rule, count in sorted(report.spokenform.rules.items())
    )
    lines.extend(["", "## Recognition domains", "", "| Domain | Count |", "| --- | ---: |"])
    lines.extend(
        f"| {_cell(domain)} | {count} |"
        for domain, count in sorted(report.spokenform.domains.items())
    )
    lines.extend(["", "## Changes by section", ""])
    section_titles = {section.section_id: section.title for section in report.sections}
    grouped_changes: dict[tuple[int, str], list[Any]] = {}
    for change in report.changes:
        grouped_changes.setdefault((change.section_index, change.section_id), []).append(change)
    for (index, section_id), changes in sorted(grouped_changes.items()):
        section_title = section_titles.get(section_id) or f"Section {index}"
        lines.extend(
            [
                f"### {index:02d} {_cell(section_title)} (`{_cell(section_id)}`)",
                "",
                (
                    "| ID | Paragraph | Source | Replacement | Stages | Rule | "
                    "Provenance | Domain | Source span | Output span |"
                ),
                "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
            ]
        )
        for change in changes:
            paragraph = "Title" if change.source_paragraph < 0 else str(change.source_paragraph + 1)
            lines.append(
                f"| `{change.id}` | {paragraph} | {_cell(change.source)} "
                f"| {_cell(change.replacement)} | {_cell(', '.join(change.stages))} "
                f"| {_cell(change.rule or '')} "
                f"| {_cell(json.dumps(change.provenance, ensure_ascii=False, sort_keys=True))} "
                f"| {_cell(change.recognition_domain or '')} "
                f"| {change.source_start}:{change.source_end} "
                f"| {change.output_start}:{change.output_end} |"
            )
        lines.append("")
    lines.extend(
        [
            "## Splitting",
            "",
            f"- Source prepared items: {report.source_prepared_items}",
            f"- Source items split: {report.split_source_items}",
            f"- Added split parts: {report.added_split_parts}",
            f"- Maximum prepared paragraph characters: {report.max_prepared_paragraph_chars}",
            "",
        ]
    )
    if report.output_files == 0 and not report.destinations:
        lines.extend(
            [
                "## Prepared text preview",
                "",
                "- Files written: 0",
                "- Preview format: txt",
                f"- Characters: {report.output_chars}",
                f"- Lines: {report.output_lines}",
            ]
        )
    else:
        lines.extend(
            [
                "## Output",
                "",
                f"- Files: {report.output_files}",
                f"- Characters: {report.output_chars}",
                f"- Lines: {report.output_lines}",
                "- Destinations:",
            ]
        )
        lines.extend(f"  - `{_cell(destination)}`" for destination in report.destinations)
    lines.extend(["", "## Warnings", ""])
    warning_counts = Counter(report.warnings)
    if warning_counts:
        lines.extend(f"- {_cell(warning)} (x{count})" for warning, count in warning_counts.items())
    else:
        lines.append("- None")
    return "\n".join(lines).rstrip() + "\n"


def format_stats(report: ConversionReport) -> str:
    title = report.document_title or Path(report.source_path).name
    lines = [
        f"Prepared {title}",
        f"Source: {report.source_path}",
        f"Input format: {report.input_format}",
        f"Metadata language: {report.metadata_language or 'not set'}",
        f"Requested language: {report.requested_language or 'not specified'}",
        f"Effective language: {report.effective_language}",
        f"Stored sequence fallback: {report.stored_sequence_fallback_mode or 'not specified'}",
        f"Effective sequence fallback: {report.effective_sequence_fallback_mode or 'unavailable'}",
        f"Workspace: {report.workspace_status or 'not applicable'}",
        f"Dirty chapters: {len(report.dirty_chapters)}",
        f"Layout: {report.output_layout}",
        f"Sections: {report.selected_sections} / {report.total_sections}",
        f"Input characters: {report.input_chars}",
        f"Source paragraphs: {report.source_paragraphs}",
        f"Prepared paragraphs: {report.prepared_paragraphs}",
        "",
        "Spokenform:",
        f"  calls: {report.spokenform.calls}",
        f"  paragraphs/titles processed: {report.spokenform.paragraphs_processed}",
        f"  paragraphs/titles changed: {report.spokenform.paragraphs_changed}",
        f"  changed calls: {report.spokenform.changed_calls}",
        f"  source replacements: {report.spokenform.source_replacements}",
        f"  structured edits: {report.spokenform.structured_edits}",
        f"  structured numeric edits: {report.spokenform.structured_numeric_edits}",
        f"  abbreviation edits: {report.spokenform.abbreviation_edits}",
        f"  number edits: {report.spokenform.number_edits}",
        f"  source spans containing digits changed: {report.spokenform.source_digit_replacements}",
        f"  warnings: {report.spokenform.warnings}",
        "",
        "Sidecar:",
        f"  custom overrides: {report.spokenform.stage_edits.get('custom', 0)}",
        "Splitting:",
        f"  source items split: {report.split_source_items}",
        f"  added parts: {report.added_split_parts}",
        f"  maximum prepared paragraph characters: {report.max_prepared_paragraph_chars}",
        "",
        "Output:",
        f"  files: {report.output_files}",
        f"  characters: {report.output_chars}",
        f"  lines: {report.output_lines}",
    ]
    lines.extend(f"  destination: {path}" for path in report.destinations)
    warning_counts = Counter(report.warnings)
    lines.extend(f"  warning: {warning} (x{count})" for warning, count in warning_counts.items())
    return "\n".join(lines)


def format_preflight(report: ConversionReport, plan: OutputPlan) -> str:
    lines = [
        "Preflight passed.",
        format_stats(report),
        "",
        "Preflight: no TTS files were written.",
    ]
    if plan.layout == "single":
        lines.extend(["Would write:", f"  {plan.artifacts[0].path}"])
    else:
        lines.append(f"Would write {len(plan.artifacts)} files under:")
        lines.append(f"  {plan.root}")
        lines.extend(f"  {artifact.path}" for artifact in plan.artifacts)
    return "\n".join(lines)


def render_report(report: ConversionReport, format: str) -> str:
    if format == "md":
        return markdown_report(report)
    if format == "json":
        return json_report(report)
    raise ValueError("Report format must be 'md' or 'json'")


def write_report(path: Path, report: ConversionReport, *, format: str | None = None) -> None:
    validate_report_path(path, format=format)
    selected_format = format or report_format(path)
    content = render_report(report, selected_format)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")
