"""Command-line interface."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Annotated, NoReturn

import typer
from spokenform.language import base_language

from . import __version__
from .context import context_payload, format_bug_report, format_context, render_context_json
from .errors import TTSReadyError
from .lexical_review import (
    DEFAULT_MAX_FREQUENCY_RANK,
    format_lexical_context,
    lexical_context_payload,
    render_review,
    review_document,
    write_review,
)
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
from .sidecar import Sidecar, SidecarError, load_sidecar
from .speakers import (
    JevSpeakerProvider,
    manual_speaker_decision,
    render_speaker_review,
    review_speakers,
    speakers_from_sidecar,
    write_speaker_decisions,
)
from .writers import render_txt


class Layout(str, Enum):
    single = "single"
    chapters = "chapters"


class ReportFormat(str, Enum):
    md = "md"
    json = "json"


class SpeakerReviewFormat(str, Enum):
    md = "md"
    json = "json"


SourceArgument = Annotated[
    Path,
    typer.Argument(exists=True, file_okay=True, dir_okay=False, readable=True, metavar="SOURCE"),
]
ChangeIdArgument = Annotated[str, typer.Argument(metavar="ID")]
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
ConfigOption = Annotated[Path | None, typer.Option("--config", help="YAML customization sidecar.")]
SpeakerConfigOption = Annotated[
    Path,
    typer.Option(
        "--config",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        help="YAML sidecar containing logical speaker candidates.",
    ),
]
SpeakerFormatOption = Annotated[
    SpeakerReviewFormat,
    typer.Option("--format", help="Speaker review format."),
]
UseJevOption = Annotated[
    bool,
    typer.Option("--jev", help="Request bounded suggestions from optional Jev provider."),
]
JevModelOption = Annotated[
    str | None,
    typer.Option("--jev-model", help="Optional model name for the Jev provider."),
]
UtteranceOption = Annotated[
    str,
    typer.Option("--utterance", help="Stable source-span utterance ID to assign."),
]
SpeakerIdOption = Annotated[
    str,
    typer.Option("--speaker", help="Logical speaker ID registered in the sidecar."),
]
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


def _load_sidecar_for_document(path: Path | None, document: Document) -> Sidecar | None:
    if path is None:
        return None
    try:
        return load_sidecar(
            path,
            source_path=document.source.path,
            source_format=document.source.format,
        )
    except SidecarError as exc:
        raise typer.BadParameter(str(exc), param_hint="--config") from exc


def _load_lexhint(language: str, *, variant: str, dataset_version: str | None):
    try:
        from lexhint import Lexicon
    except ImportError as exc:
        raise RuntimeError("--lexhint requires the ttsready[lexical] extra") from exc
    return Lexicon(
        base_language(language),
        variant=variant,
        dataset_version=dataset_version,
    )


def _prepare_for_output(
    *,
    source: Path,
    config: Path | None,
    chapters: str | None,
    output: Path | None,
    layout: Layout,
    language: str | None,
    max_paragraph_chars: int,
    spokenform: bool,
    titles: bool,
    line_width: int | None,
    paragraph_breaks: int,
) -> PreparedOutput:
    document = _load_selected_document(source, chapters)
    sidecar = _load_sidecar_for_document(config, document)
    render_options = RenderOptions(line_width=line_width, paragraph_breaks=paragraph_breaks)
    try:
        plan = plan_output(
            document,
            output=output,
            layout=layout.value,
        )
    except (TTSReadyError, OSError, ValueError) as exc:
        raise typer.BadParameter(str(exc), param_hint="--output") from exc

    try:
        result = prepare_document(
            document,
            language=language,
            max_paragraph_chars=max_paragraph_chars,
            apply_spokenform=spokenform,
            include_titles=titles,
            render_options=render_options,
            sidecar=sidecar,
        )
        rendered = render_artifacts(plan, result.paragraphs, options=render_options)
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
    config: Path | None,
    chapters: str | None,
    language: str | None,
    max_paragraph_chars: int,
    spokenform: bool,
    titles: bool,
) -> ConversionReport:
    document = _load_selected_document(source, chapters)
    sidecar = _load_sidecar_for_document(config, document)
    try:
        result = prepare_document(
            document,
            language=language,
            max_paragraph_chars=max_paragraph_chars,
            apply_spokenform=spokenform,
            include_titles=titles,
            render_options=RenderOptions(),
            sidecar=sidecar,
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
    config: ConfigOption = None,
    output: OutputOption = None,
    layout: LayoutOption = Layout.single,
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
    """Convert SOURCE to TTS-ready plain text."""
    prepared = _prepare_for_output(
        source=source,
        config=config,
        chapters=chapters,
        output=output,
        layout=layout,
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
    typer.echo("Format: txt")
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
    config: ConfigOption = None,
    output: OutputOption = None,
    layout: LayoutOption = Layout.single,
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
        config=config,
        chapters=chapters,
        output=output,
        layout=layout,
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
    config: ConfigOption = None,
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
        config=config,
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


@app.command("context")
def context_command(
    source: SourceArgument,
    change_id: ChangeIdArgument,
    chapters: ChaptersOption = None,
    config: ConfigOption = None,
    language: LanguageOption = None,
    max_paragraph_chars: MaxParagraphCharsOption = 1000,
    spokenform: SpokenformOption = True,
    titles: TitlesOption = True,
    as_json: Annotated[
        bool, typer.Option("--json", help="Emit machine-readable context JSON.")
    ] = False,
    bug_report: Annotated[
        bool, typer.Option("--bug-report", help="Print a paste-ready Spokenform issue block.")
    ] = False,
    paragraph: Annotated[
        bool, typer.Option("--paragraph", help="Include the full source paragraph.")
    ] = False,
) -> None:
    """Show source context for a change or lexical review ID."""
    if as_json and bug_report:
        raise typer.BadParameter("--json and --bug-report cannot be combined")
    report = _prepare_report(
        source=source,
        config=config,
        chapters=chapters,
        language=language,
        max_paragraph_chars=max_paragraph_chars,
        spokenform=spokenform,
        titles=titles,
    )
    is_lexical = False
    try:
        payload = context_payload(report, change_id)
    except KeyError:
        try:
            payload = lexical_context_payload(report, change_id, paragraph=paragraph)
            is_lexical = True
        except KeyError:
            _fail_runtime(
                KeyError(
                    f"No Spokenform change found and no lexical finding found for ID {change_id!r}"
                )
            )
    if bug_report and is_lexical:
        raise typer.BadParameter("--bug-report applies only to Spokenform change IDs")
    if bug_report:
        typer.echo(format_bug_report(payload), nl=False)
    elif as_json:
        typer.echo(render_context_json(payload, paragraph=paragraph), nl=False)
    elif is_lexical:
        typer.echo(format_lexical_context(payload), nl=False)
    else:
        typer.echo(format_context(payload, paragraph=paragraph), nl=False)


@app.command("review")
def review_command(
    source: SourceArgument,
    language: LanguageOption = None,
    unknown_only: Annotated[
        bool,
        typer.Option("--unknown-only", help="Show only words the selected provider marks unknown."),
    ] = False,
    max_frequency_rank: Annotated[
        int,
        typer.Option(
            "--max-frequency-rank",
            min=1,
            help="Treat frequency ranks above this cutoff as rare.",
        ),
    ] = DEFAULT_MAX_FREQUENCY_RANK,
    min_count: Annotated[
        int,
        typer.Option("--min-count", min=1, help="Minimum occurrences per candidate."),
    ] = 1,
    max_items: Annotated[
        int | None,
        typer.Option("--max-items", min=1, help="Limit the number of ranked candidates."),
    ] = None,
    lexhint: Annotated[
        bool,
        typer.Option("--lexhint", help="Use an installed Lexhint artifact; never downloads."),
    ] = False,
    lexhint_variant: Annotated[
        str, typer.Option("--lexhint-variant", help="Installed Lexhint artifact variant.")
    ] = "runtime",
    lexhint_dataset_version: Annotated[
        str | None,
        typer.Option("--lexhint-dataset-version", help="Require a specific dataset version."),
    ] = None,
    output: OutputOption = None,
    format_: ReportFormatOption = None,
) -> None:
    """Review uncommon words and likely pronunciation candidates."""
    try:
        document = load(source)
        selected_language = str(language or document.metadata.get("language") or "en")
        provider = (
            _load_lexhint(
                selected_language,
                variant=lexhint_variant,
                dataset_version=lexhint_dataset_version,
            )
            if lexhint
            else None
        )
        review = review_document(
            document,
            language=selected_language,
            provider=provider,
            max_frequency_rank=max_frequency_rank,
            min_count=min_count,
            max_items=max_items,
            unknown_only=unknown_only,
        )
    except Exception as exc:
        _fail_runtime(exc)

    output_format = _resolve_report_format(output, format_)
    if output is None:
        typer.echo(render_review(review, output_format), nl=False)
        return
    try:
        validate_report_path(output, format=output_format)
    except (OSError, ValueError) as exc:
        raise typer.BadParameter(str(exc), param_hint="--output") from exc
    if output.resolve() == source.resolve():
        raise typer.BadParameter(
            "Review output path must not match the source path.",
            param_hint="--output",
        )
    try:
        write_review(output, review, output_format)
    except Exception as exc:
        _fail_runtime(exc)
    typer.echo(f"Review written: {output}")


@app.command("speakers")
def speakers_command(
    source: SourceArgument,
    config: SpeakerConfigOption,
    chapters: ChaptersOption = None,
    jev: UseJevOption = False,
    jev_model: JevModelOption = None,
    format_: SpeakerFormatOption = SpeakerReviewFormat.md,
) -> None:
    """Review source-quoted utterances and optional bounded speaker suggestions."""
    if jev_model and not jev:
        raise typer.BadParameter("--jev-model requires --jev", param_hint="--jev-model")
    document = _load_selected_document(source, chapters)
    sidecar = _load_sidecar_for_document(config, document)
    if sidecar is None:
        _fail_runtime(ValueError("A sidecar is required for speaker review"))

    try:
        result = prepare_document(document, apply_spokenform=False, sidecar=sidecar)
        if result.report is None:
            raise ValueError("Speaker review did not produce source contexts")
        candidates = speakers_from_sidecar(sidecar)
        if jev:
            with JevSpeakerProvider(model=jev_model) as provider:
                review = review_speakers(
                    result.report.contexts,
                    candidates=candidates,
                    provider=provider,
                )
        else:
            review = review_speakers(result.report.contexts, candidates=candidates)
        typer.echo(render_speaker_review(review, format=format_.value), nl=False)
    except Exception as exc:
        _fail_runtime(exc)


@app.command("speaker-set")
def speaker_set_command(
    source: SourceArgument,
    config: SpeakerConfigOption,
    utterance_id: UtteranceOption,
    speaker_id: SpeakerIdOption,
) -> None:
    """Save an explicit manual assignment to a registered logical speaker ID."""
    document = _load_selected_document(source, None)
    sidecar = _load_sidecar_for_document(config, document)
    if sidecar is None:
        _fail_runtime(ValueError("A sidecar is required for speaker assignments"))

    try:
        result = prepare_document(document, apply_spokenform=False, sidecar=sidecar)
        if result.report is None:
            raise ValueError("Speaker assignment did not produce source contexts")
        review = review_speakers(result.report.contexts, candidates=speakers_from_sidecar(sidecar))
        utterance = next(
            (item for item in review.utterances if item.id == utterance_id),
            None,
        )
        if utterance is None:
            raise KeyError(f"No source utterance found for ID {utterance_id!r}")
        decision = manual_speaker_decision(
            utterance,
            speaker_id=speaker_id,
            candidates=speakers_from_sidecar(sidecar),
        )
        write_speaker_decisions(config, sidecar, (decision,))
    except Exception as exc:
        _fail_runtime(exc)
    typer.echo(f"Saved manual speaker assignment: {utterance_id} -> {speaker_id}")
