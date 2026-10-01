from __future__ import annotations

from pathlib import Path

from ttsready.readers import MarkdownReader, TextReader, reader_for


def test_text_reader(tmp_path: Path) -> None:
    source = tmp_path / "sample.txt"
    source.write_text("Hello\n\nWorld", encoding="utf-8")
    doc = TextReader().load(source)
    assert doc.sections[0].text == "Hello\n\nWorld"


def test_markdown_reader_uses_h1_as_section_title(tmp_path: Path) -> None:
    source = tmp_path / "sample.md"
    source.write_text("# Chapter 1\n\nHello **world**.\n", encoding="utf-8")
    doc = MarkdownReader().load(source)
    assert doc.sections[0].title == "Chapter 1"
    assert doc.sections[0].text == "Hello world."


def test_reader_for_rejects_unknown_extension(tmp_path: Path) -> None:
    source = tmp_path / "sample.xyz"
    source.write_text("x", encoding="utf-8")
    try:
        reader_for(source)
    except Exception as exc:
        assert "Unsupported input" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected unsupported input")



def test_ssmd_is_not_registered_as_an_input_format(tmp_path: Path) -> None:
    source = tmp_path / "sample.ssmd"
    source.write_text("This format is no longer accepted.", encoding="utf-8")

    try:
        reader_for(source)
    except Exception as exc:
        assert "Unsupported input" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("SSMD input should be unsupported")



def test_ssmd_is_not_a_runtime_dependency() -> None:
    pyproject = Path(__file__).parents[1] / "pyproject.toml"
    assert "ssmd>=" not in pyproject.read_text(encoding="utf-8")
