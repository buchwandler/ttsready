"""Output path planning and artifact rendering."""

from __future__ import annotations

import os
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .models import Document, PreparedParagraph, RenderOptions
from .writers import render_txt

OutputLayout = Literal["single", "chapters"]
_RESERVED_FILENAME_CHARS = set('/\\<>:"|?*')


@dataclass(frozen=True, slots=True)
class OutputArtifact:
    section_id: str | None
    path: Path


@dataclass(frozen=True, slots=True)
class OutputPlan:
    layout: OutputLayout
    root: Path
    artifacts: tuple[OutputArtifact, ...]


def _sanitize_title(title: str | None, *, limit: int = 80) -> str:
    if not title:
        return "section"
    chars = []
    for char in title:
        if char in _RESERVED_FILENAME_CHARS:
            chars.append("-")
        elif unicodedata.category(char) == "Cc":
            continue
        else:
            chars.append(char)
    safe = re.sub(r"\s+", "-", "".join(chars).strip())
    safe = re.sub(r"-+", "-", safe).rstrip(". ")
    safe = safe[:limit].rstrip(". -")
    return safe or "section"


def plan_output(
    document: Document,
    *,
    output: Path | None = None,
    layout: str = "single",
) -> OutputPlan:
    """Build and validate a deterministic plain-text artifact plan."""
    if layout not in {"single", "chapters"}:
        raise ValueError("layout must be 'single' or 'chapters'")

    if layout == "single":
        destination = output or document.source.path.with_suffix(".txt")
        if destination.suffix.lower() == ".ssmd":
            raise ValueError("SSMD output is no longer supported")
        if destination.exists() and destination.is_dir():
            raise ValueError("Single output must be a file path, not a directory")
        artifact = OutputArtifact(None, destination)
        plan = OutputPlan("single", destination.parent, (artifact,))
    else:
        directory = output or document.source.path.with_name(
            f"{document.source.path.stem}-ttsready"
        )
        if directory.exists() and not directory.is_dir():
            raise ValueError(f"Chapter output path is not a directory: {directory}")
        artifacts = tuple(
            OutputArtifact(
                section_id=section.id,
                path=directory / f"{index:03d}-{_sanitize_title(section.title)}.txt",
            )
            for index, section in enumerate(document.sections, start=1)
        )
        plan = OutputPlan("chapters", directory, artifacts)

    validate_output_plan(plan)
    return plan


def validate_output_plan(plan: OutputPlan) -> None:
    """Reject duplicate destinations and path components that prevent writes."""
    normalized_paths = [os.path.normcase(str(item.path.resolve())) for item in plan.artifacts]
    if len(normalized_paths) != len(set(normalized_paths)):
        raise ValueError("Output plan contains duplicate file paths")

    if plan.layout == "chapters" and plan.root.exists() and not plan.root.is_dir():
        raise ValueError(f"Chapter output path is not a directory: {plan.root}")
    for artifact in plan.artifacts:
        if artifact.path.exists() and artifact.path.is_dir():
            raise ValueError(f"Output path is a directory: {artifact.path}")
        parent = artifact.path.parent
        if parent.exists() and not parent.is_dir():
            raise ValueError(f"Output parent is not a directory: {parent}")


def paragraphs_for_section(
    paragraphs: list[PreparedParagraph], section_id: str
) -> list[PreparedParagraph]:
    """Filter already-prepared paragraphs for one section without reprocessing."""
    return [item for item in paragraphs if item.section_id == section_id]


def render_artifacts(
    plan: OutputPlan,
    paragraphs: list[PreparedParagraph],
    *,
    options: RenderOptions | None = None,
) -> tuple[tuple[OutputArtifact, str], ...]:
    """Render every planned TXT artifact from the prepared paragraph list."""
    if plan.layout == "single":
        artifact = plan.artifacts[0]
        return ((artifact, render_txt(paragraphs, options=options)),)

    return tuple(
        (
            artifact,
            render_txt(
                paragraphs_for_section(paragraphs, artifact.section_id or ""),
                options=options,
            ),
        )
        for artifact in plan.artifacts
    )


def write_artifacts(plan: OutputPlan, rendered: tuple[tuple[OutputArtifact, str], ...]) -> None:
    """Write the complete rendered artifact set after validating all destinations."""
    if tuple(artifact for artifact, _ in rendered) != plan.artifacts:
        raise ValueError("Rendered artifacts do not match the output plan")
    validate_output_plan(plan)
    plan.root.mkdir(parents=True, exist_ok=True)
    for artifact, text in rendered:
        artifact.path.write_text(text, encoding="utf-8", newline="\n")
