from ttsready import OverrideScope, SpeechOverride
from ttsready.identifiers import canonical_json, override_id, source_change_id, stable_id


def test_stable_id_uses_canonical_mapping_order():
    assert stable_id("test", {"b": 2, "a": 1}) == stable_id("test", {"a": 1, "b": 2})
    assert canonical_json({"b": 2, "a": 1}) == '{"a":1,"b":2}'


def test_source_change_id_identifies_source_occurrence_only():
    first = source_change_id("u1", source_start=4, source_end=8, source="word")
    second = source_change_id("u1", source_start=4, source_end=8, source="word")
    assert first == second
    assert first.startswith("chg:v1:")
    assert first != source_change_id("u2", source_start=4, source_end=8, source="word")


def test_override_id_includes_scope():
    unit = SpeechOverride("word", "spoken", scope=OverrideScope("unit", "u1"))
    global_override = SpeechOverride("word", "spoken")
    assert override_id(unit) == unit.id
    assert unit.id != global_override.id
