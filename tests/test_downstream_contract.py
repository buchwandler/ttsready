import ttsready


def test_consumer_can_prepare_mixed_language_units_without_format_objects():
    units = (
        ttsready.TextUnit("chapter:caller-7", "2 kg", "en-US"),
        ttsready.TextUnit("paragraph/42", "Bonjour.", "fr-FR", role="caption"),
    )
    result = ttsready.prepare_units(units)

    assert [unit.unit_id for unit in result.units] == ["chapter:caller-7", "paragraph/42"]
    assert [unit.language for unit in result.units] == ["en-US", "fr-FR"]
    assert result.units[0].spoken_text == "two kilograms"
    assert result.units[1].role == "caption"
    assert not hasattr(result.units[0], "path")
