from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

import ttsready.cli as cli
from ttsready.context import context_payload, sentences_overlapping
from ttsready.models import (
    ContextRecord,
    ConversionReport,
    SentenceContext,
    SpokenChange,
)

runner = CliRunner()


def make_report() -> ConversionReport:
    context_id = "ctx:v1:11111111111111111111"
    source = "He met Dr. Smith. Then left."
    spoken = "He met Doctor Smith. Then left."
    return ConversionReport(
        source_path="book.epub",
        input_format="epub",
        document_title="Book",
        metadata_language="en",
        requested_language=None,
        effective_language="en",
        total_sections=1,
        selected_sections=1,
        input_chars=len(source),
        source_paragraphs=1,
        sections=[],
        tool_versions={"ttsready": "1.2.3", "spokenform": "0.4.5"},
        contexts=[
            ContextRecord(
                id=context_id,
                section_id="section-1",
                section_locator="ref:chapter.xhtml",
                section_index=1,
                source_paragraph=0,
                is_title=False,
                source_text=source,
                spoken_text=spoken,
                source_sentences=(
                    SentenceContext("sent:v1:1", 0, "He met Dr. Smith.", 0, 17),
                    SentenceContext("sent:v1:2", 1, "Then left.", 18, 28),
                ),
                spoken_sentences=(
                    SentenceContext("sent:v1:3", 0, "He met Doctor Smith.", 0, 21),
                    SentenceContext("sent:v1:4", 1, "Then left.", 22, 32),
                ),
            )
        ],
        changes=[
            SpokenChange(
                id="chg:v1:0123456789abcdefabcd",
                context_id=context_id,
                section_id="section-1",
                section_index=1,
                source_paragraph=0,
                source="Dr.",
                replacement="Doctor",
                stages=("abbreviations",),
                kind="abbreviation",
                rule="abbr:Dr.",
                recognition_domain="medical",
                source_start=7,
                source_end=10,
                output_start=7,
                output_end=13,
            )
        ],
    )


def test_context_selects_overlapping_sentences_and_falls_back_to_context() -> None:
    report = make_report()
    payload = context_payload(report, "chg:v1:0123456789abcdefabcd")

    assert payload["source_sentence_text"] == "He met Dr. Smith."
    assert payload["spoken_sentence_text"] == "He met Doctor Smith."
    assert sentences_overlapping(report.contexts[0].source_sentences, 15, 20) == (
        report.contexts[0].source_sentences[0],
        report.contexts[0].source_sentences[1],
    )
    assert sentences_overlapping(report.contexts[0].source_sentences, 80, 85) == ()
    assert payload["source_sentence_text"] != report.contexts[0].source_text



def test_context_falls_back_to_full_context_when_spans_do_not_overlap() -> None:
    from dataclasses import replace

    report = make_report()
    report.changes[0] = replace(
        report.changes[0],
        source_start=80,
        source_end=85,
        output_start=80,
        output_end=85,
    )

    payload = context_payload(report, report.changes[0].id)
    assert payload["source_sentence_text"] == report.contexts[0].source_text
    assert payload["spoken_sentence_text"] == report.contexts[0].spoken_text


def test_context_unknown_id_raises_clear_error() -> None:
    try:
        context_payload(make_report(), "chg:v1:missing")
    except KeyError as exc:
        assert "No Spokenform change found" in str(exc)
    else:
        raise AssertionError("unknown context ID should fail")


def test_context_cli_json_and_paragraph_output(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "book.epub"
    source.write_bytes(b"source")
    monkeypatch.setattr(cli, "_prepare_report", lambda **kwargs: make_report())

    result = runner.invoke(
        cli.app,
        ["context", str(source), "chg:v1:0123456789abcdefabcd", "--json"],
    )
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["source_sentence_text"] == "He met Dr. Smith."
    assert "context" not in data

    paragraph = runner.invoke(
        cli.app,
        ["context", str(source), "chg:v1:0123456789abcdefabcd", "--paragraph"],
    )
    assert paragraph.exit_code == 0, paragraph.output
    assert "Source paragraph:\nHe met Dr. Smith. Then left." in paragraph.output


def test_context_cli_bug_report_contains_versions_and_sentence(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "book.epub"
    source.write_bytes(b"source")
    monkeypatch.setattr(cli, "_prepare_report", lambda **kwargs: make_report())

    result = runner.invoke(
        cli.app,
        ["context", str(source), "chg:v1:0123456789abcdefabcd", "--bug-report"],
    )

    assert result.exit_code == 0, result.output
    assert "- ttsready: 1.2.3" in result.output
    assert "- spokenform: 0.4.5" in result.output
    assert "He met Dr. Smith." in result.output
    assert "He met Doctor Smith." in result.output
    assert "<fill in expected spoken form>" in result.output


def test_context_cli_unknown_id_exits_nonzero(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "book.epub"
    source.write_bytes(b"source")
    monkeypatch.setattr(cli, "_prepare_report", lambda **kwargs: make_report())

    result = runner.invoke(cli.app, ["context", str(source), "chg:v1:missing"])

    assert result.exit_code == 1
    assert "No Spokenform change found" in result.output
