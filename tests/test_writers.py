from __future__ import annotations

import pytest

from ttsready.models import PreparedParagraph, RenderOptions
from ttsready.writers import render_txt


def test_render_txt_separates_paragraphs() -> None:
    paragraphs = [
        PreparedParagraph("one", "s", 0),
        PreparedParagraph("two", "s", 1),
    ]
    assert render_txt(paragraphs) == "one\n\ntwo\n"


@pytest.mark.parametrize(
    ("breaks", "expected"),
    [(0, "one two\n"), (1, "one\ntwo\n"), (2, "one\n\ntwo\n")],
)
def test_render_txt_paragraph_break_options(breaks: int, expected: str) -> None:
    paragraphs = [
        PreparedParagraph("one", "s", 0),
        PreparedParagraph("two", "s", 1),
    ]
    assert render_txt(paragraphs, options=RenderOptions(paragraph_breaks=breaks)) == expected


def test_render_txt_wraps_at_whitespace_without_breaking_long_words() -> None:
    paragraphs = [
        PreparedParagraph("one two three", "s", 0),
        PreparedParagraph("longtoken", "s", 1),
    ]
    options = RenderOptions(line_width=7, paragraph_breaks=2)

    assert render_txt(paragraphs, options=options) == "one two\nthree\n\nlongtoken\n"


def test_zero_breaks_join_paragraphs_before_visual_wrapping() -> None:
    paragraphs = [
        PreparedParagraph("one two", "s", 0),
        PreparedParagraph("three four", "s", 1),
    ]
    options = RenderOptions(line_width=10, paragraph_breaks=0)

    assert render_txt(paragraphs, options=options) == "one two\nthree four\n"



def test_render_options_validate_line_width_and_break_count() -> None:
    with pytest.raises(ValueError, match="line_width"):
        RenderOptions(line_width=0)
    with pytest.raises(ValueError, match="paragraph_breaks"):
        RenderOptions(paragraph_breaks=3)
