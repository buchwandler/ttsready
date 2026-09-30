"""Command-line interface."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated, Literal

import typer

from . import __version__
from .errors import TTSReadyError
from .models import RenderOptions
from .output import (
    paragraphs_for_section,
    plan_output,
    render_artifacts,
    write_artifacts,
)
from .pipeline import prepare as prepare_document
from .readers import load
from .reporting import (
    format_preflight,
    format_stats,
    report_format,
    validate_report_path,
    write_report,
)
from .selection import (
    format_section_listing,
    parse_section_range,
    select_document_sections,
)
from .writers import render_txt

app = typer.Typer(
    add_completion=False,
    help="Prepare EPUB, PDF, text, Markdown, HTML, or SSMD for TTS.",
)


def _version(value: bool) -> None:
    if value:
        typer.echo(__version__)
        raise typer.Exit()


def _format_from_output(
    output: Path | None, explicit: str | None, layout: str = "single"
) -> Literal["txt", "ssmd"]:
    if explicit is not None:
        if explicit not in {"txt", "ssmd"}:
            raise typer.BadParameter("--format must be 'txt' or 'ssmd'")
        return explicit  # type: ignore[return-value]
    if (
        layout == "single" and output is not None and output.suffix.lower() == ".ssmd"
    ):
        return "ssmd"
    return "txt"



@app.command()
def main(
    source: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
    list_chapters: Annotated[
        bool,
        typer.Option("--list-chapters", "--list-sections", help="List sections and exit."),
    ] = False,
    chapters: Annotated[
        str | None,
        typer.Option("--chapters", "--sections", help="1-based list/range, such as 1-5,7."),
    ] = None,
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
    output_layout: Annotated[
        str,
        typer.Option("--output-layout", help="Output layout: single or chapters."),
    ] = "single",
    format_: Annotated[
        str | None,
        typer.Option(
            "--format",
            help=(
                "Output format: txt or ssmd. Defaults from -o suffix in single layout, "
                "txt otherwise."
            ),
        ),
    ] = None,
    language: Annotated[
        str | None,
        typer.Option(
            "--language", "-l", help="Spokenform language; metadata then 'en' if omitted."
        ),
    ] = None,
    max_paragraph_chars: Annotated[
        int | None,
        typer.Option(
            "--max-paragraph-chars",
            min=1,
            help="Semantic TTS chunk limit after spokenform normalization.",
        ),
    ] = 1000,
    spokenform: Annotated[
        bool,
        typer.Option("--spokenform/--no-spokenform", help="Apply written-to-spoken normalization."),
    ] = True,
    titles: Annotated[
        bool,
        typer.Option("--titles/--no-titles", help="Include real section/chapter titles."),
    ] = True,
    line_width: Annotated[
        int | None,
        typer.Option(
            "--line-width",
            min=1,
            help="Soft-wrap rendered lines at whitespace; long words may exceed the width.",
        ),
    ] = None,
    paragraph_breaks: Annotated[
        int,
        typer.Option(
            "--paragraph-breaks",
            min=0,
            max=2,
            help="Newline count between prepared paragraphs: 0, 1, or 2.",
        ),
    ] = 2,
    stats: Annotated[bool, typer.Option("--stats", help="Print conversion statistics.")] = False,
    preflight: Annotated[
        bool,
        typer.Option("--preflight", help="Run the full conversion without writing TTS output."),
    ] = False,
    report_path: Annotated[
        Path | None,
        typer.Option("--report", help="Write a detailed Markdown (.md) or JSON (.json) report."),
    ] = None,
    version: Annotated[
        bool | None,
        typer.Option("--version", callback=_version, is_eager=True, help="Show version and exit."),
    ] = None,
) -> None:
    """Prepare SOURCE and write TTS-ready text."""
    del version
    try:
        document = load(source)
    except (TTSReadyError, OSError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc

    if list_chapters:
        typer.echo(format_section_listing(document))
        raise typer.Exit()

    try:
        if chapters is not None:
            indices = parse_section_range(chapters, len(document.sections))
            document = select_document_sections(document, indices)
        if output_layout not in {"single", "chapters"}:
            raise ValueError("output_layout must be 'single' or 'chapters'")
        output_format = _format_from_output(output, format_, output_layout)
        render_options = RenderOptions(line_width=line_width, paragraph_breaks=paragraph_breaks)
        if report_path is not None:
            report_format(report_path)
            validate_report_path(report_path)
        plan = plan_output(
            document,
            output=output,
            layout=output_layout,
            output_format=output_format,
        )
        if report_path is not None:
            report_target = os.path.normcase(str(report_path.resolve()))
            output_targets = {
                os.path.normcase(str(artifact.path.resolve())) for artifact in plan.artifacts
            }
            if report_target in output_targets:
                raise ValueError("Report path must not match a generated output path")
        result = prepare_document(
            document,
            output_format=output_format,
            language=language,
            max_paragraph_chars=max_paragraph_chars,
            apply_spokenform=spokenform,
            include_titles=titles,
            render_options=render_options,
        )
        rendered = render_artifacts(
            plan,
            result.document,
            result.paragraphs,
            language=result.language,
            options=render_options,
        )
        if result.report is None:
            raise ValueError("Conversion did not produce a report")
        conversion_report = result.report
        conversion_report.output_layout = output_layout
        conversion_report.output_files = len(plan.artifacts)
        conversion_report.destinations = [str(artifact.path) for artifact in plan.artifacts]
        conversion_report.output_chars = sum(len(text) for _, text in rendered)
        conversion_report.output_lines = sum(len(text.splitlines()) for _, text in rendered)
        for section in conversion_report.sections:
            content = render_txt(
                paragraphs_for_section(result.paragraphs, section.section_id),
                options=render_options,
            )
            section.output_chars = len(content)
    except (TTSReadyError, OSError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc

    try:
        if preflight:
            typer.echo(format_preflight(conversion_report, plan))
            if report_path is not None:
                write_report(report_path, conversion_report)
            return
        write_artifacts(plan, rendered)
        if report_path is not None:
            write_report(report_path, conversion_report)
    except (OSError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc

    destination = plan.root if plan.layout == "chapters" else plan.artifacts[0].path
    typer.echo(f"Prepared {source} -> {destination}")
    typer.echo(
        f"Format: {result.output_format}; language: {result.language}; "
        f"paragraphs: {len(result.paragraphs)}"
    )
    if stats:
        typer.echo(format_stats(conversion_report))
    elif result.warnings:
        typer.echo(f"Warnings: {len(result.warnings)}")
