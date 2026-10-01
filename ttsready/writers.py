"""Plain-text renderer."""

from __future__ import annotations

import textwrap
from collections.abc import Sequence

from .models import PreparedParagraph, RenderOptions


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
