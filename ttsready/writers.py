"""Plain text and SSMD renderers."""

from __future__ import annotations

import textwrap
from collections.abc import Mapping, Sequence
from typing import Any

from .models import OutputFormat, PreparedParagraph, RenderOptions


def _wrap(text: str, options: RenderOptions) -> str:
    if options.line_width is None:
        return text
    return "\n".join(
        textwrap.wrap(
            text,
            width=options.line_width,
            break_long_words=False,
            break_on_hyphens=False,
            replace_whitespace=False,
            drop_whitespace=True,
        )
    )


def render_txt(
    paragraphs: Sequence[PreparedParagraph], *, options: RenderOptions | None = None
) -> str:
    options = options or RenderOptions()
    items = [item.text.strip() for item in paragraphs if item.text.strip()]
    if options.paragraph_breaks == 0:
        body = _wrap(" ".join(items), options)
    else:
        separator = "\n" * options.paragraph_breaks
        body = separator.join(_wrap(item, options) for item in items)
    return body.rstrip() + "\n" if body else ""


def render_ssmd(
    paragraphs: Sequence[PreparedParagraph],
    *,
    metadata: Mapping[str, Any],
    language: str,
    options: RenderOptions | None = None,
) -> str:
    from ssmd import serialize_front_matter

    options = options or RenderOptions()
    header = dict(metadata)
    header["ssmd_version"] = "0.9"
    header["language"] = language
    body = render_txt(paragraphs, options=options)
    return serialize_front_matter(header, body)


def render(
    output_format: OutputFormat,
    paragraphs: Sequence[PreparedParagraph],
    *,
    metadata: Mapping[str, Any],
    language: str,
    options: RenderOptions | None = None,
) -> str:
    options = options or RenderOptions()
    if output_format == "txt":
        return render_txt(paragraphs, options=options)
    if output_format == "ssmd":
        return render_ssmd(
            paragraphs, metadata=metadata, language=language, options=options
        )
    raise ValueError(f"Unsupported output format: {output_format!r}")
