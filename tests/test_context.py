import pytest

from ttsready import OverrideScope, SpeechOverride, TextUnit, context_for_change, prepare_units


def test_context_lookup_returns_full_source_and_spoken_sentence():
    source = "Because someone (ART) thought this part could use some more verisimilitude."
    result = prepare_units(
        (TextUnit("unit-1", source, "en-US"),),
        overrides=(
            SpeechOverride(
                "ART",
                "A R T",
                scope=OverrideScope("occurrence", "unit-1", 17, 20),
            ),
        ),
    )

    context = context_for_change(result, result.changes[0].id)
    assert context.source_sentences[0].text == source
    assert context.spoken_sentences[0].text == result.units[0].spoken_text
    assert context.change.source == "ART"
    assert context.change.replacement == "A R T"


def test_context_lookup_is_exact_and_has_no_file_fallback():
    result = prepare_units((TextUnit("u", "unchanged.", "en-US"),))
    with pytest.raises(KeyError):
        context_for_change(result, "missing")
