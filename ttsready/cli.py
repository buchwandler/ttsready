"""Command-line interface."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal

import typer

from . import __version__
from .errors import TTSReadyError
from .pipeline import convert as convert_document

app = typer.Typer(
    add_completion=False,
    help="Prepare EPUB, PDF, text, Markdown, HTML, or SSMD for TTS.",
)


def _version(value: bool) -> None:
    if value:
        typer.echo(__version__)
        raise typer.Exit()


def _format_from_output(output: Path | None, explicit: str | None) -> Literal["txt", "ssmd"]:
    if explicit is not None:
        if explicit not in {"txt", "ssmd"}:
            raise typer.BadParameter("--format must be 'txt' or 'ssmd'")
        return explicit  # type: ignore[return-value]
    if output is not None and output.suffix.lower() == ".ssmd":
        return "ssmd"
    return "txt"


@app.command()
def main(
    source: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
    format_: Annotated[
        str | None,
        typer.Option("--format", help="Output format: txt or ssmd. Defaults from -o suffix."),
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
            help="Split prepared paragraphs longer than this many characters.",
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
    version: Annotated[
        bool | None,
        typer.Option("--version", callback=_version, is_eager=True, help="Show version and exit."),
    ] = None,
) -> None:
    """Prepare SOURCE and write TTS-ready text."""
    del version
    output_format = _format_from_output(output, format_)
    destination = output or source.with_suffix(".ssmd" if output_format == "ssmd" else ".txt")

    try:
        result = convert_document(
            source,
            output_format=output_format,
            language=language,
            max_paragraph_chars=max_paragraph_chars,
            apply_spokenform=spokenform,
            include_titles=titles,
        )
    except (TTSReadyError, OSError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc

    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(result.text, encoding="utf-8", newline="\n")
    typer.echo(f"Prepared {source} -> {destination}")
    typer.echo(
        f"Format: {result.output_format}; language: {result.language}; "
        f"paragraphs: {len(result.paragraphs)}"
    )
    if result.warnings:
        typer.echo(f"Warnings: {len(result.warnings)}")
