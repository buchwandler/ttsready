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
    assert result.stats.units_changed == 1
    assert result.stats.changes == 1
    assert result.stats.structured_numeric_edits == 1
    assert result.stats.source_digit_replacements == 1
    assert result.stats.stage_edits["structured"] == 1
    assert result.prepared_fingerprint
    assert result.profile_fingerprint
    assert result.override_fingerprint
    assert result.runtime_fingerprint
