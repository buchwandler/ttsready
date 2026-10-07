import json

import pytest

from ttsready.models import (
    PreparationIssue,
    PreparationResult,
    PreparationStats,
    PreparedUnit,
    SentenceSpan,
    SpokenChange,
    UnitContext,
)


def _result():
    change = SpokenChange(
        id="chg:v1:occurrence",
        unit_id="unit/opaque",
        source_start=1,
        source_end=2,
        output_start=1,
        output_end=4,
        source="b",
        replacement="XYZ",
        stages=("numbers",),
        kind="number",
        provenance={"origin": "spokenform", "evidence": ["test"]},
    )
    context = UnitContext(
        unit_id="unit/opaque",
        role="prose",
        language="en-US",
        source_text="abc",
        spoken_text="aXYZc",
        source_sentences=(SentenceSpan(0, "abc", 0, 3),),
        spoken_sentences=(SentenceSpan(0, "aXYZc", 0, 5),),
    )
    unit = PreparedUnit(
        unit_id="unit/opaque",
        source_text="abc",
        spoken_text="aXYZc",
        language="en-US",
        role="prose",
        changes=(change,),
        issues=(
            PreparationIssue(
                "spokenform.warning", "warning", "unit/opaque", None, None, None, "check"
            ),
        ),
        context=context,
    )
    return PreparationResult(
        units=(unit,),
        changes=(change,),
        issues=unit.issues,
        stats=PreparationStats(
            units_processed=1,
            units_changed=1,
            changes=1,
            stage_edits={"numbers": 1},
            warning_count=1,
        ),
        profile_fingerprint="profile",
        override_fingerprint="overrides",
        runtime_fingerprint="runtime",
        prepared_fingerprint="prepared",
    )


def test_preparation_result_json_round_trip_is_semantically_equal():
    original = _result()
    encoded = json.dumps(original.to_dict(), allow_nan=False, sort_keys=True)
    restored = PreparationResult.from_dict(json.loads(encoded))

    assert restored == original
    assert restored.units[0].changes[0].source == "b"
    assert restored.units[0].context.spoken_sentences[0].text == "aXYZc"


def test_result_schema_is_required():
    data = _result().to_dict()
    data["schema"] = "ttsready.preparation.v1"
    with pytest.raises(ValueError, match="schema"):
        PreparationResult.from_dict(data)


def _assert_json_values(value):
    if value is None or type(value) in {str, int, float, bool}:
        return
    if type(value) is list:
        for item in value:
            _assert_json_values(item)
        return
    if type(value) is dict:
        assert all(type(key) is str for key in value)
        for item in value.values():
            _assert_json_values(item)
        return
    raise AssertionError(f"non-JSON value leaked into serialization: {type(value).__name__}")


def test_serialized_result_contains_only_builtin_json_values():
    _assert_json_values(_result().to_dict())
