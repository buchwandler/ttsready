from types import SimpleNamespace

import pytest
from spokenform import TokenAnnotation
from spokenform.mapping import OffsetMap

from ttsready import prepare_run
from ttsready.errors import InvalidUnitError, MappingError, PreparationError
from ttsready.models import LinguisticToken, PreparationProfile


def identity_result(text: str, *, warnings=()):
    return SimpleNamespace(
        spoken_text=text,
        source_replacements=(),
        warnings=warnings,
        offset_map=OffsetMap.identity(len(text)),
    )


def test_prepare_run_returns_direct_normalization_changes_and_exact_map():
    prepared = prepare_run("2 kg", language="en-US", unit_id="caller-run")

    assert prepared.spoken_text == "two kilograms"
    assert prepared.unit_id == "caller-run"
    assert prepared.language == "en-US"
    assert prepared.changed
    assert len(prepared.changes) == 1
    change = prepared.changes[0]
    assert (change.source_start, change.source_end, change.source) == (0, 4, "2 kg")
    assert (change.output_start, change.output_end, change.replacement) == (0, 13, "two kilograms")
    assert prepared.source_map.source_length == 4
    assert prepared.source_map.output_length == 13
    assert prepared.source_map.source_to_output(0, bias="left") == 0
    assert prepared.source_map.source_to_output(0, bias="right") == 13
    assert prepared.issues == ()


def test_prepare_run_keeps_formatting_under_conservative_defaults():
    text = "  Hello\n\n"
    prepared = prepare_run(text, language="en-US")
    assert prepared.spoken_text == text
    assert not prepared.changed
    assert prepared.changes == ()


def test_prepare_run_forwards_every_profile_option(monkeypatch):
    profile = PreparationProfile(
        use_spacy=True,
        symbol_mode="all",
        normalize_unicode=True,
        normalize_whitespace=True,
        strip_outer_whitespace=True,
        collapse_horizontal_whitespace=True,
        normalize_line_whitespace=True,
        collapse_blank_lines=True,
        generic_acronym_mode="spell",
        sequence_fallback_mode="spell",
        expand_abbreviations=False,
        expand_structured=False,
        expand_numbers=False,
    )
    captured = {}

    def backend(text, **kwargs):
        captured.update(kwargs)
        return identity_result(text)

    monkeypatch.setattr("ttsready.preparation.spokenform.prepare_language", backend)
    prepare_run("sample", language="en-US", profile=profile, strict=True)

    assert captured == {
        "language": "en-US",
        "protected_spans": (),
        "annotations": None,
        "preserve_run_boundaries": False,
        "use_spacy": True,
        "symbol_mode": "all",
        "normalize_unicode": True,
        "normalize_whitespace": True,
        "strip_outer_whitespace": True,
        "collapse_horizontal_whitespace": True,
        "normalize_line_whitespace": True,
        "collapse_blank_lines": True,
        "generic_acronym_mode": "spell",
        "sequence_fallback_mode": "spell",
        "expand_abbreviations": False,
        "expand_structured": False,
        "expand_numbers": False,
        "strict": True,
    }


def test_prepare_run_forwards_run_boundary_flag(monkeypatch):
    observed = []

    def backend(text, **kwargs):
        observed.append(kwargs["preserve_run_boundaries"])
        return identity_result(text)

    monkeypatch.setattr("ttsready.preparation.spokenform.prepare_language", backend)
    prepare_run("one", language="en-US")
    prepare_run("two", language="en-US", preserve_run_boundaries=True)
    assert observed == [False, True]


def test_prepare_run_protects_caller_spans():
    prepared = prepare_run("2 kg", language="en-US", protected_spans=((0, 4),))
    assert prepared.spoken_text == "2 kg"
    assert prepared.changes == ()


def test_prepare_run_converts_backend_warnings(monkeypatch):
    monkeypatch.setattr(
        "ttsready.preparation.spokenform.prepare_language",
        lambda text, **kwargs: identity_result(text, warnings=("backend notice",)),
    )
    prepared = prepare_run("text", language="en-US")
    assert prepared.warnings == ("backend notice",)
    assert prepared.issues[0].code == "spokenform.warning"
    assert prepared.issues[0].severity == "warning"
    assert prepared.issues[0].unit_id == "run"


def test_prepare_run_wraps_backend_failures_with_unit_id(monkeypatch):
    def fail(*args, **kwargs):
        raise ValueError("backend failure")

    monkeypatch.setattr("ttsready.preparation.spokenform.prepare_language", fail)
    with pytest.raises(PreparationError, match="named-run.*backend failure"):
        prepare_run("text", language="en-US", unit_id="named-run")


def test_prepare_run_rejects_missing_backend_map(monkeypatch):
    result = SimpleNamespace(spoken_text="text", source_replacements=(), warnings=())
    monkeypatch.setattr("ttsready.preparation.spokenform.prepare_language", lambda *a, **k: result)
    with pytest.raises(MappingError, match="offset_map"):
        prepare_run("text", language="en-US")


def test_prepare_run_forwards_provider_neutral_annotations_without_nlp(monkeypatch):
    hints = (LinguisticToken(0, 4, text="cats", pos="NOUN", tag="NNS", lemma="cat"),)
    observed = {}

    def backend(text, **kwargs):
        observed.update(kwargs)
        return identity_result(text)

    monkeypatch.setattr("ttsready.preparation.spokenform.prepare_language", backend)
    prepare_run("cats", language="en-US", linguistic_tokens=hints)

    annotations = observed["annotations"]
    assert len(annotations) == 1
    assert isinstance(annotations[0], TokenAnnotation)
    assert (annotations[0].start, annotations[0].end, annotations[0].pos) == (0, 4, "NOUN")
    assert "nlp" not in observed


def test_explicit_hints_work_with_spacy_requested_without_loading_a_model(monkeypatch):
    def fail_to_load(*args, **kwargs):
        raise AssertionError("explicit annotations should avoid model loading")

    monkeypatch.setattr("spokenform.api.load_spacy_model", fail_to_load)
    text = "The box is 2 in."
    start = text.index("in.")
    prepared = prepare_run(
        text,
        language="en",
        linguistic_tokens=(
            LinguisticToken(start, start + 3, text="in.", pos="NOUN", tag="NN", lemma="in"),
        ),
        profile=PreparationProfile(use_spacy=True),
    )
    assert prepared.spoken_text == "The box is two inches."


def test_linguistic_token_ranges_are_sorted_then_checked_against_source():
    prepared = prepare_run(
        "red blue",
        language="en-US",
        linguistic_tokens=(
            LinguisticToken(4, 8, text="blue", pos="ADJ"),
            LinguisticToken(0, 3, text="red", pos="ADJ"),
        ),
    )
    assert prepared.spoken_text == "red blue"

    with pytest.raises(InvalidUnitError, match="outside"):
        prepare_run("red", language="en-US", linguistic_tokens=(LinguisticToken(0, 4),))
    with pytest.raises(InvalidUnitError, match="overlap"):
        prepare_run(
            "abcd",
            language="en-US",
            linguistic_tokens=(LinguisticToken(0, 3), LinguisticToken(2, 4)),
        )
    with pytest.raises(InvalidUnitError, match="does not match"):
        prepare_run(
            "red",
            language="en-US",
            linguistic_tokens=(LinguisticToken(0, 3, text="blue"),),
        )


def test_prepare_run_does_not_require_sentence_splitting(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("prepare_run must not split sentences")

    monkeypatch.setattr("ttsready.preparation.phrasplit.split_with_offsets", fail)
    assert prepare_run("plain text", language="en-US").spoken_text == "plain text"
