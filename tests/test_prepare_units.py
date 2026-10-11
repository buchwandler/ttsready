from types import SimpleNamespace

import pytest
from spokenform import TokenAnnotation
from spokenform.mapping import OffsetMap

from ttsready import LinguisticToken, PreparationProfile
from ttsready.models import TextUnit
from ttsready.preparation import prepare_units


def test_prepare_units_preserves_order_and_aggregates_generic_stats():
    result = prepare_units(
        (
            TextUnit("source:item/1", "2 kg", "en-US", role="prose"),
            TextUnit("caller-fr-2", "Bonjour.", "fr-FR", role="title"),
        )
    )

    assert [unit.unit_id for unit in result.units] == ["source:item/1", "caller-fr-2"]
    assert [unit.language for unit in result.units] == ["en-US", "fr-FR"]
    assert result.units[0].spoken_text == "two kilograms"
    assert result.stats.units_processed == 2
    assert result.changes[0].language == "en"
    assert result.stats.units_changed == 1
    assert result.stats.changes == 1
    assert result.stats.structured_numeric_edits == 1
    assert result.stats.source_digit_replacements == 1
    assert result.stats.stage_edits["structured"] == 1
    assert result.prepared_fingerprint
    assert result.profile_fingerprint
    assert result.override_fingerprint
    assert result.runtime_fingerprint


def test_prepare_units_forwards_text_unit_linguistic_tokens(monkeypatch):
    observed = {}

    def backend(text, **kwargs):
        observed.update(kwargs)
        return SimpleNamespace(
            spoken_text=text,
            source_replacements=(),
            warnings=(),
            offset_map=OffsetMap.identity(len(text)),
        )

    monkeypatch.setattr("ttsready.preparation.spokenform.prepare_language", backend)
    unit = TextUnit(
        "u",
        "cats",
        "en-US",
        linguistic_tokens=(LinguisticToken(0, 4, text="cats", pos="NOUN", lemma="cat"),),
    )

    prepare_units((unit,), profile=PreparationProfile(use_spacy=True))

    annotations = observed["annotations"]
    assert len(annotations) == 1
    assert isinstance(annotations[0], TokenAnnotation)
    assert (annotations[0].start, annotations[0].end, annotations[0].text) == (0, 4, "cats")
    assert (annotations[0].pos, annotations[0].lemma) == ("NOUN", "cat")
    assert "nlp" not in observed


def test_prepare_units_reports_observation_only_progress_without_output(capsys):
    units = (
        TextUnit("one", "Hello.", "en-US"),
        TextUnit("two", "Bonjour.", "fr-FR", role="title"),
    )
    baseline = prepare_units(units)
    events = []

    observed = prepare_units(units, on_progress=events.append)

    assert observed.to_dict() == baseline.to_dict()
    assert [(event.kind, event.completed, event.total, event.unit_id) for event in events] == [
        ("unit.started", 0, 2, "one"),
        ("unit.completed", 1, 2, "one"),
        ("unit.started", 1, 2, "two"),
        ("unit.completed", 2, 2, "two"),
    ]
    assert capsys.readouterr() == ("", "")


def test_prepare_units_propagates_progress_callback_exceptions():
    def fail(_event):
        raise RuntimeError("stop observing")

    with pytest.raises(RuntimeError, match="stop observing"):
        prepare_units((TextUnit("u", "text", "en-US"),), on_progress=fail)


def test_linguistic_hints_do_not_override_protected_source_spans():
    unit = TextUnit(
        "protected",
        "2 kg",
        "en-US",
        protected_spans=((0, 4),),
        linguistic_tokens=(
            LinguisticToken(0, 1, text="2", pos="NUM"),
            LinguisticToken(2, 4, text="kg", pos="NOUN"),
        ),
    )

    prepared = prepare_units((unit,))

    assert prepared.units[0].spoken_text == "2 kg"
    assert prepared.units[0].changes == ()
