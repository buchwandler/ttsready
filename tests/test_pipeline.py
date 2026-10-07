from ttsready import TextUnit, apply_changes, prepare_text, prepare_units


def test_prepare_text_returns_source_relative_changes():
    prepared = prepare_text("A 2 kg parcel.", language="en-US", unit_id="parcel")

    assert prepared.unit_id == "parcel"
    assert prepared.source_text == "A 2 kg parcel."
    assert prepared.spoken_text
    assert apply_changes(prepared.source_text, prepared.changes) == prepared.spoken_text


def test_prepare_units_preserves_caller_order_and_per_unit_language():
    units = (
        TextUnit("english", "The number is 2.", "en-US", role="body"),
        TextUnit("french", "Le nombre est 2.", "fr-FR", role="body"),
    )
    result = prepare_units(units)

    assert [item.unit_id for item in result.units] == ["english", "french"]
    assert [item.language for item in result.units] == ["en-US", "fr-FR"]
    assert result.stats.units_processed == 2
    assert all(
        apply_changes(unit.source_text, unit.changes) == unit.spoken_text for unit in result.units
    )
