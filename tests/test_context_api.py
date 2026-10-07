import pytest

from ttsready.context import context_for_change
from ttsready.models import OverrideScope, SpeechOverride, TextUnit
from ttsready.preparation import prepare_units


def test_context_for_change_returns_sentences_around_exact_change():
    source = "Because someone (ART) thought this part could use some more verisimilitude."
    result = prepare_units(
        (TextUnit("caller-unit", source, "en-US"),),
        overrides=(
            SpeechOverride(
                "ART",
                "A R T",
                scope=OverrideScope("occurrence", "caller-unit", 17, 20),
            ),
        ),
    )
    change = result.changes[0]

    context = context_for_change(result, change.id)
    assert context.unit.unit_id == "caller-unit"
    assert context.source_sentences[0].text == source
    assert "A R T" in context.spoken_sentences[0].text
    assert context.change is change


def test_context_for_change_raises_key_error_for_unknown_id():
    result = prepare_units((TextUnit("u", "unchanged.", "en-US"),))
    with pytest.raises(KeyError):
        context_for_change(result, "missing")
