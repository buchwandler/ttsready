from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

import ttsready.pipeline as pipeline
from ttsready.errors import TTSReadyError
from ttsready.models import Document, RenderOptions, Section, SourceInfo


def document(text: str, *, title: str | None = None) -> Document:
    return Document(
        source=SourceInfo(Path("sample.txt"), "text", "text/plain"),
        sections=[Section("section-1", text, title=title)],
        metadata={"title": "Sample", "language": "en"},
    )


def test_source_paragraphs_join_soft_line_wraps() -> None:
    text = "First line\ncontinues here.\n\nSecond paragraph."
    assert pipeline.source_paragraphs(text) == [
        "First line continues here.",
        "Second paragraph.",
    ]


def test_normalization_profile_resolves_document_policy() -> None:
    spell = pipeline.normalization_profile("en")
    preserve = pipeline.normalization_profile("en", sequence_fallback_mode="preserve")

    assert spell.sequence_fallback_mode == "spell"
    assert preserve.sequence_fallback_mode == "preserve"
    with pytest.raises(TTSReadyError, match="sequence_fallback_mode must be"):
        pipeline.normalization_profile("en", sequence_fallback_mode="SPELL")


def test_spokenform_receives_fallback_mode_with_local_language(monkeypatch) -> None:
    received = {}

    def fake_prepare(text: str, **kwargs):
        received.update(kwargs)
        return SimpleNamespace(spoken_text=text, warnings=(), stages=(), source_replacements=())

    monkeypatch.setitem(sys.modules, "spokenform", SimpleNamespace(prepare=fake_prepare))
    pipeline._spoken(
        "in-system target/destination",
        context_id="context-1",
        language="fr",
        sequence_fallback_mode="preserve",
        enabled=True,
        section_id="section-1",
        section_locator_value="id:section-1",
        section_index=1,
        source_paragraph=0,
        sidecar=None,
    )

    assert received["language"] == "fr"
    assert received["sequence_fallback_mode"] == "preserve"


def test_plan_reports_artifact_fallback_mode() -> None:
    source_document = document("in-system target/destination")
    source_document.metadata["sequence_fallback_mode"] = "preserve"

    plan = pipeline.prepare_tts_plan(source_document, apply_spokenform=False)

    assert plan.report.normalization_profile["sequence_fallback_mode"] == "preserve"


def test_prepare_without_spokenform_keeps_short_paragraphs() -> None:
    result = pipeline.prepare(
        document("One paragraph.\n\nTwo paragraph."),
        apply_spokenform=False,
        max_paragraph_chars=100,
    )
    assert [p.text for p in result.paragraphs] == ["One paragraph.", "Two paragraph."]
    assert result.text == "One paragraph.\n\nTwo paragraph.\n"
    assert result.report is not None
    assert result.report.spokenform.calls == 0
    assert result.report.spokenform.source_replacements == 0
    assert result.report.spokenform.stage_edits == {}
    assert result.report.warnings == []


def test_normalization_profile_preserves_residual_sequences() -> None:
    profile = pipeline.normalization_profile("en", sequence_fallback_mode="preserve")
    assert profile.sequence_fallback_mode == "preserve"


def test_residual_sequences_stay_lexical_and_structured_rules_remain_active() -> None:
    residual_text = (
        "in-system target/destination bot-pilots high-threat Barish-Estranza "
        "build-up penetration-testing we/somebody where/who ART EVAC"
    )
    structured_text = "Chapter 1 Null+1 3–2–1 2.0 etc."
    source_document = document(f"{residual_text}\n{structured_text}")
    source_document.metadata["sequence_fallback_mode"] = "preserve"
    result = pipeline.prepare(source_document, language="en")
    report = result.report
    assert report is not None

    for phrase in (
        "in-system",
        "target/destination",
        "bot-pilots",
        "high-threat",
        "Barish-Estranza",
        "build-up",
        "penetration-testing",
        "we/somebody",
        "where/who",
        "ART",
        "EVAC",
    ):
        assert phrase in result.text
    assert "i n hyphen s y s t e m" not in result.text
    assert "t a r g e t slash" not in result.text
    assert "B a r i s h hyphen" not in result.text
    assert all(change.rule != "fallback.sequence" for change in report.changes)
    assert "fallback.sequence" not in report.spokenform.rules
    assert "sequence_fallback" not in report.spokenform.stage_edits

    assert "chapter one" in result.text
    assert "Null plus one" in result.text
    assert "two point zero" in result.text
    assert "et cetera" in result.text
    assert report.spokenform.rules["sequence.legal"] == 1
    assert report.spokenform.rules["sequence.math"] == 1


def test_title_is_optional() -> None:
    with_title = pipeline.prepare(
        document("Body.", title="Chapter One"),
        apply_spokenform=False,
        include_titles=True,
    )
    without_title = pipeline.prepare(
        document("Body.", title="Chapter One"),
        apply_spokenform=False,
        include_titles=False,
    )
    assert [p.text for p in with_title.paragraphs] == ["Chapter One", "Body."]
    assert [p.text for p in without_title.paragraphs] == ["Body."]


def test_spokenform_runs_before_length_split(monkeypatch) -> None:
    calls: list[str] = []

    def fake_spoken(text: str, **kwargs):
        del kwargs
        calls.append(text)
        return pipeline.SpokenOutcome(text + " expanded", (), True, {}, ())

    def fake_split(text: str, *, max_chars: int | None, language: str):
        assert text.endswith(" expanded")
        return ["part one", "part two"]

    monkeypatch.setattr(pipeline, "_spoken", fake_spoken)
    monkeypatch.setattr(pipeline, "_split_oversized", fake_split)

    result = pipeline.prepare(document("source"), max_paragraph_chars=10)
    assert calls == ["source"]
    assert [p.text for p in result.paragraphs] == ["part one", "part two"]


def test_report_aggregates_structured_spokenform_provenance(monkeypatch) -> None:
    replacements = (
        SimpleNamespace(
            source_start=0,
            source_end=3,
            output_start=0,
            output_end=6,
            source="Dr.",
            replacement="Doctor",
            stages=("abbreviations",),
            kind="abbreviation",
            rule="abbr:Dr.",
            recognition_domain="medical",
        ),
        SimpleNamespace(
            source_start=8,
            source_end=9,
            output_start=11,
            output_end=16,
            source="3",
            replacement="three",
            stages=("numbers",),
            kind="number",
            rule="number:cardinal",
            recognition_domain="plain_number",
        ),
        SimpleNamespace(
            source_start=14,
            source_end=16,
            output_start=21,
            output_end=30,
            source="42",
            replacement="forty two",
            stages=("structured",),
            kind="date",
            rule="date:year",
            recognition_domain="date",
        ),
    )
    stages = [
        SimpleNamespace(name="structured", mapped_edits=(object(),)),
        SimpleNamespace(name="abbreviations", mapped_edits=(object(),)),
        SimpleNamespace(name="numbers", mapped_edits=(object(),)),
        SimpleNamespace(name="whitespace", mapped_edits=()),
    ]
    prepared = SimpleNamespace(
        spoken_text="Doctor has three and forty two.",
        warnings=("warning one", "warning two"),
        stages=stages,
        source_replacements=replacements,
    )
    monkeypatch.setitem(
        sys.modules,
        "spokenform",
        SimpleNamespace(prepare=lambda *args, **kwargs: prepared),
    )
    result = pipeline.prepare(
        document("Dr. has 3 and 42."),
        language="en-US",
    )
    report = result.report
    assert report is not None
    assert report.requested_language == "en-US"
    assert report.metadata_language == "en"
    assert report.effective_language == "en-US"
    assert report.source_prepared_items == 1
    assert report.spokenform.calls == 1
    assert report.spokenform.changed_calls == 1
    assert report.spokenform.source_replacements == 3
    assert report.spokenform.stage_edits == {
        "structured": 1,
        "abbreviations": 1,
        "numbers": 1,
        "whitespace": 0,
    }
    assert report.spokenform.abbreviation_edits == 1
    assert report.spokenform.number_edits == 1
    assert report.spokenform.structured_edits == 1
    assert report.spokenform.structured_numeric_edits == 1
    assert report.spokenform.source_digit_replacements == 2
    assert report.spokenform.rules == {
        "abbr:Dr.": 1,
        "number:cardinal": 1,
        "date:year": 1,
    }
    assert report.spokenform.domains == {
        "medical": 1,
        "plain_number": 1,
        "date": 1,
    }
    assert report.spokenform.warnings == 2
    assert report.warnings == ["warning one", "warning two"]
    assert [change.source for change in report.changes] == ["Dr.", "3", "42"]
    assert report.changes[0].source_start == 0
    assert report.changes[2].output_end == 30
    assert report.changes[0].section_id == "section-1"
    assert report.changes[0].source_paragraph == 0


def test_report_counts_source_items_that_split(monkeypatch) -> None:
    monkeypatch.setattr(
        pipeline,
        "_split_oversized",
        lambda text, **kwargs: ["one", "two", "three"],
    )
    result = pipeline.prepare(
        document("one source paragraph"),
        apply_spokenform=False,
        max_paragraph_chars=5,
    )
    report = result.report
    assert report is not None
    assert report.source_prepared_items == 1
    assert report.split_source_items == 1
    assert report.prepared_paragraphs == 3
    assert report.added_split_parts == 2
    assert report.max_prepared_paragraph_chars == 5


def test_render_options_do_not_change_prepared_paragraph_count() -> None:
    result = pipeline.prepare(
        document("one two three\n\nfour five"),
        apply_spokenform=False,
        render_options=RenderOptions(line_width=7, paragraph_breaks=1),
    )

    assert len(result.paragraphs) == 2
    assert result.text == "one two\nthree\nfour\nfive\n"


def test_prepare_records_duplicate_source_contexts_and_exact_sentences() -> None:
    result = pipeline.prepare(
        document("Repeated. Unicode café stays.\n\nRepeated. Unicode café stays.", title="Title."),
        apply_spokenform=False,
    )
    report = result.report
    assert report is not None

    assert len(report.contexts) == 3
    title, first, duplicate = report.contexts
    assert title.is_title
    assert title.source_paragraph == -1
    assert first.source_text == duplicate.source_text
    assert first.id != duplicate.id
    assert first.section_locator == "id:section-1"
    assert first.source_sentences[0].text == "Repeated."
    assert first.spoken_text == first.source_text
    for context in report.contexts:
        for sentence in context.source_sentences:
            assert context.source_text[sentence.start : sentence.end] == sentence.text
        for sentence in context.spoken_sentences:
            assert context.spoken_text[sentence.start : sentence.end] == sentence.text


def test_spoken_change_references_context_id(monkeypatch) -> None:
    replacement = SimpleNamespace(
        source_start=0,
        source_end=3,
        output_start=0,
        output_end=6,
        source="Dr.",
        replacement="Doctor",
        stages=("abbreviations",),
        kind="abbreviation",
        rule="abbr:Dr.",
        recognition_domain="medical",
    )
    prepared = SimpleNamespace(
        spoken_text="Doctor Smith.",
        warnings=(),
        stages=(),
        source_replacements=(replacement,),
    )
    monkeypatch.setitem(
        sys.modules,
        "spokenform",
        SimpleNamespace(prepare=lambda *args, **kwargs: prepared),
    )

    report = pipeline.prepare(document("Dr. Smith.")).report
    assert report is not None
    change = report.changes[0]
    assert change.id.startswith("chg:v1:")
    assert change.context_id == report.contexts[0].id
    assert change.id == pipeline.change_id(
        change.context_id,
        source_start=0,
        source_end=3,
        source="Dr.",
    )
