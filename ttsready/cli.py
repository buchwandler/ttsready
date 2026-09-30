"""Command-line interface."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Annotated, Literal, NoReturn

import typer

from . import __version__
from .errors import TTSReadyError
from .models import ConversionReport, ConversionResult, Document, RenderOptions
from .output import (
    OutputArtifact,
    OutputPlan,
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
    render_report,
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


class Layout(str, Enum):
    single = "single"
    chapters = "chapters"


class TtsFormat(str, Enum):
    txt = "txt"
    ssmd = "ssmd"


class ReportFormat(str, Enum):
    md = "md"
    json = "json"


SourceArgument = Annotated[
    Path,
    typer.Argument(exists=True, file_okay=True, dir_okay=False, readable=True, metavar="SOURCE"),
]
ChaptersOption = Annotated[
    str | None,
    typer.Option(
        "-c",
        "--chapters",
        "--sections",
        help="1-based chapter/section list or range, such as 1-5,7.",
    ),
]
OutputOption = Annotated[Path | None, typer.Option("-o", "--output", help="Output path.")]
LanguageOption = Annotated[
    str | None,
    typer.Option("-l", "--language", help="Spokenform language; metadata then en if omitted."),
]
MaxParagraphCharsOption = Annotated[
    int,
    typer.Option(
        "--max-paragraph-chars",
        min=1,
        help="Semantic TTS chunk limit after spokenform normalization.",
    ),
]
SpokenformOption = Annotated[
    bool,
    typer.Option("--spokenform/--no-spokenform", help="Apply written-to-spoken normalization."),
]
TitlesOption = Annotated[
    bool,
    typer.Option("--titles/--no-titles", help="Include real chapter/section titles."),
]
LineWidthOption = Annotated[
    int | None,
    typer.Option(
        "--line-width",
        min=1,
        help="Soft-wrap rendered lines at whitespace; long words may exceed the width.",
    ),
]
ParagraphBreaksOption = Annotated[
    int,
    typer.Option(
        "--paragraph-breaks",
        min=0,
        max=2,
        help="Newline count between prepared paragraphs: 0, 1, or 2.",
    ),
]
LayoutOption = Annotated[Layout, typer.Option("--layout", help="Output layout.")]
TtsFormatOption = Annotated[
    TtsFormat | None,
    typer.Option("--format", help="TTS output format. Defaults from output suffix or to txt."),
]
ReportFormatOption = Annotated[
    ReportFormat | None,
    typer.Option("--format", help="Report format; inferred from -o when possible."),
]

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Prepare documents for text-to-speech.",
)


@dataclass(frozen=True, slots=True)
class PreparedOutput:
    result: ConversionResult
    report: ConversionReport
    plan: OutputPlan
    rendered: tuple[tuple[OutputArtifact, str], ...]
    render_options: RenderOptions


def _version(value: bool | None) -> None:
    if value:
        typer.echo(__version__)
        raise typer.Exit()


def _fail_runtime(exc: Exception) -> NoReturn:
    typer.echo(f"Error: {exc}", err=True)
    raise typer.Exit(1)


def _load_selected_document(source: Path, chapters: str | None) -> Document:
    try:
        document = load(source)
    except Exception as exc:
        _fail_runtime(exc)

    if chapters is None:
        return document
    try:
        indices = parse_section_range(chapters, len(document.sections))
    except ValueError as exc:
        raise typer.BadParameter(str(exc), param_hint="--chapters") from exc
    return select_document_sections(document, indices)


def _format_from_output(
    output: Path | None, explicit: TtsFormat | None, layout: Layout
) -> Literal["txt", "ssmd"]:
    if explicit is not None:
        return explicit.value  # type: ignore[return-value]
    if layout is Layout.single and output is not None and output.suffix.lower() == ".ssmd":
        return "ssmd"
    return "txt"


def _prepare_for_output(
    *,
    source: Path,
    chapters: str | None,
    output: Path | None,
    layout: Layout,
    output_format: TtsFormat | None,
    language: str | None,
    max_paragraph_chars: int,
    spokenform: bool,
    titles: bool,
    line_width: int | None,
    paragraph_breaks: int,
) -> PreparedOutput:
    document = _load_selected_document(source, chapters)
    resolved_format = _format_from_output(output, output_format, layout)
    render_options = RenderOptions(line_width=line_width, paragraph_breaks=paragraph_breaks)
    try:
        plan = plan_output(
            document,
            output=output,
            layout=layout.value,
            output_format=resolved_format,
        )
    except (TTSReadyError, OSError, ValueError) as exc:
        raise typer.BadParameter(str(exc), param_hint="--output") from exc

    try:
        result = prepare_document(
            document,
            output_format=resolved_format,
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
    except Exception as exc:
        _fail_runtime(exc)

    if result.report is None:
        _fail_runtime(ValueError("Conversion did not produce a report"))
    report = result.report
    report.output_layout = layout.value
    report.output_files = len(plan.artifacts)
    report.destinations = [str(artifact.path) for artifact in plan.artifacts]
    report.output_chars = sum(len(text) for _, text in rendered)
    report.output_lines = sum(len(text.splitlines()) for _, text in rendered)
    for section in report.sections:
        content = render_txt(
            paragraphs_for_section(result.paragraphs, section.section_id),
            options=render_options,
        )
        section.output_chars = len(content)
    return PreparedOutput(result, report, plan, rendered, render_options)


def _prepare_report(
    *,
    source: Path,
    chapters: str | None,
    language: str | None,
    max_paragraph_chars: int,
    spokenform: bool,
    titles: bool,
) -> ConversionReport:
    document = _load_selected_document(source, chapters)
    try:
        result = prepare_document(
            document,
            output_format="txt",
            language=language,
            max_paragraph_chars=max_paragraph_chars,
            apply_spokenform=spokenform,
            include_titles=titles,
            render_options=RenderOptions(),
        )
    except Exception as exc:
        _fail_runtime(exc)
    if result.report is None:
        _fail_runtime(ValueError("Conversion did not produce a report"))
    result.report.output_layout = "single"
    result.report.output_files = 0
    result.report.destinations = []
    return result.report


def _resolve_report_format(output: Path | None, explicit: ReportFormat | None) -> str:
    if output is None:
        return explicit.value if explicit is not None else "md"
    if explicit is None:
        try:
            return report_format(output)
        except ValueError as exc:
            raise typer.BadParameter(str(exc), param_hint="--output") from exc
    if output.suffix:
        try:
            inferred = report_format(output)
        except ValueError as exc:
            raise typer.BadParameter(str(exc), param_hint="--output") from exc
        if inferred != explicit.value:
            raise typer.BadParameter(
                f"Report path suffix .{inferred} conflicts with --format {explicit.value}.",
                param_hint="--format",
            )
    return explicit.value


@app.callback()
def root(
    version: Annotated[
        bool | None,
        typer.Option(
            "--version",
            callback=_version,
            is_eager=True,
            help="Show version and exit.",
        ),
    ] = None,
) -> None:
    del version


@app.command("convert")
def convert(
    source: SourceArgument,
    chapters: ChaptersOption = None,
    output: OutputOption = None,
    layout: LayoutOption = Layout.single,
    format_: TtsFormatOption = None,
    language: LanguageOption = None,
    max_paragraph_chars: MaxParagraphCharsOption = 1000,
    spokenform: SpokenformOption = True,
    titles: TitlesOption = True,
    line_width: LineWidthOption = None,
    paragraph_breaks: ParagraphBreaksOption = 2,
    stats: Annotated[
        bool, typer.Option("--stats", help="Print detailed conversion statistics.")
    ] = False,
) -> None:
    """Convert SOURCE to TTS-ready text or SSMD."""
    prepared = _prepare_for_output(
        source=source,
        chapters=chapters,
        output=output,
        layout=layout,
        output_format=format_,
        language=language,
        max_paragraph_chars=max_paragraph_chars,
        spokenform=spokenform,
        titles=titles,
        line_width=line_width,
        paragraph_breaks=paragraph_breaks,
    )
    try:
        write_artifacts(prepared.plan, prepared.rendered)
    except Exception as exc:
        _fail_runtime(exc)

    destination = (
        prepared.plan.root
        if prepared.plan.layout == "chapters"
        else prepared.plan.artifacts[0].path
    )
    typer.echo(f"Converted {source.name}")
    typer.echo(f"Output: {destination}")
    typer.echo(f"Format: {prepared.result.output_format}")
    typer.echo(f"Language: {prepared.result.language}")
    typer.echo(f"Chapters: {prepared.report.selected_sections}")
    typer.echo(f"Paragraphs: {prepared.report.prepared_paragraphs}")
    if stats:
        typer.echo(format_stats(prepared.report))
    if prepared.result.warnings:
        typer.echo(
            f"Warnings: {len(prepared.result.warnings)} (run `ttsready report SOURCE` for details)"
        )


@app.command("chapters")
def chapters_command(source: SourceArgument) -> None:
    """List chapters/sections found in SOURCE."""
    document = _load_selected_document(source, None)
    typer.echo(format_section_listing(document))


@app.command("preflight")
def preflight(
    source: SourceArgument,
    chapters: ChaptersOption = None,
    output: OutputOption = None,
    layout: LayoutOption = Layout.single,
    format_: TtsFormatOption = None,
    language: LanguageOption = None,
    max_paragraph_chars: MaxParagraphCharsOption = 1000,
    spokenform: SpokenformOption = True,
    titles: TitlesOption = True,
    line_width: LineWidthOption = None,
    paragraph_breaks: ParagraphBreaksOption = 2,
    fail_on_warning: Annotated[
        bool,
        typer.Option("--fail-on-warning", help="Exit non-zero when preparation reports warnings."),
    ] = False,
) -> None:
    """Validate a conversion without writing TTS files."""
    prepared = _prepare_for_output(
        source=source,
        chapters=chapters,
        output=output,
        layout=layout,
        output_format=format_,
        language=language,
        max_paragraph_chars=max_paragraph_chars,
        spokenform=spokenform,
        titles=titles,
        line_width=line_width,
        paragraph_breaks=paragraph_breaks,
    )
    typer.echo(format_preflight(prepared.report, prepared.plan))
    if fail_on_warning and prepared.report.warnings:
        typer.echo("Preflight failed because warnings were reported.", err=True)
        raise typer.Exit(1)


@app.command("report")
def report_command(
    source: SourceArgument,
    chapters: ChaptersOption = None,
    language: LanguageOption = None,
    max_paragraph_chars: MaxParagraphCharsOption = 1000,
    spokenform: SpokenformOption = True,
    titles: TitlesOption = True,
    output: OutputOption = None,
    format_: ReportFormatOption = None,
) -> None:
    """Show or write a spokenform/conversion report without TTS output."""
    report = _prepare_report(
        source=source,
        chapters=chapters,
        language=language,
        max_paragraph_chars=max_paragraph_chars,
        spokenform=spokenform,
        titles=titles,
    )
    output_format = _resolve_report_format(output, format_)
    if output is None:
        typer.echo(render_report(report, output_format), nl=False)
        return

    try:
        validate_report_path(output, format=output_format)
    except (OSError, ValueError) as exc:
        raise typer.BadParameter(str(exc), param_hint="--output") from exc
    if output.resolve() == source.resolve():
        raise typer.BadParameter(
            "Report path must not match the source path.", param_hint="--output"
        )
    try:
        write_report(output, report, format=output_format)
    except Exception as exc:
        _fail_runtime(exc)
    typer.echo(f"Report written: {output}")
