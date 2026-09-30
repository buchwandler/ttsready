from __future__ import annotations

from ttsready.models import PreparedParagraph
from ttsready.writers import render_txt


def test_render_txt_separates_paragraphs() -> None:
    paragraphs = [
        PreparedParagraph("one", "s", 0),
        PreparedParagraph("two", "s", 1),
    ]
    assert render_txt(paragraphs) == "one\n\ntwo\n"
