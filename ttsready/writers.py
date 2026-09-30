"""Plain text and SSMD renderers."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .models import OutputFormat, PreparedParagraph


def render_txt(paragraphs: Sequence[PreparedParagraph]) -> str:
    body = "\n\n".join(item.text.strip() for item in paragraphs if item.text.strip())
    return body.rstrip() + "\n" if body else ""


def render_ssmd(
    paragraphs: Sequence[PreparedParagraph],
    *,
    metadata: Mapping[str, Any],
    language: str,
) -> str:
    from ssmd import serialize_front_matter

    header = dict(metadata)
    header["ssmd_version"] = "0.9"
    header["language"] = language
    body = render_txt(paragraphs)
    return serialize_front_matter(header, body)


def render(
    output_format: OutputFormat,
    paragraphs: Sequence[PreparedParagraph],
    *,
    metadata: Mapping[str, Any],
    language: str,
) -> str:
    if output_format == "txt":
        return render_txt(paragraphs)
    if output_format == "ssmd":
        return render_ssmd(paragraphs, metadata=metadata, language=language)
    raise ValueError(f"Unsupported output format: {output_format!r}")
