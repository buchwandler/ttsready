import pytest

from ttsready.errors import InvalidUnitError, MappingError, OverrideConflictError, PreparationError
from ttsready.identifiers import source_change_id, stable_id
from ttsready.models import (
    OverrideScope,
    PreparationProfile,
    PreparationStats,
    ProtectedSpan,
    SpeechOverride,
    TextUnit,
)


def test_text_unit_normalizes_protected_spans_and_keeps_opaque_id():
    unit = TextUnit(
        "caller:chapter/3",
        "abcdef",
        "en-US",
        protected_spans=((3, 5), ProtectedSpan(0, 2, "literal")),
        metadata={"attributes": ["a", 4, True]},
    )

    assert unit.id == "caller:chapter/3"
    assert unit.protected_spans == (ProtectedSpan(0, 2, "literal"), ProtectedSpan(3, 5))
    assert unit.metadata["attributes"] == ["a", 4, True]


def test_text_unit_rejects_overlapping_or_out_of_bounds_protected_spans():
    with pytest.raises(ValueError, match="overlap"):
        TextUnit("u", "abcdef", "en", protected_spans=((1, 4), (3, 5)))
    with pytest.raises(ValueError, match="outside"):
        TextUnit("u", "abc", "en", protected_spans=((2, 4),))


def test_text_unit_rejects_non_json_metadata_and_empty_language():
    with pytest.raises(ValueError, match="non-JSON"):
        TextUnit("u", "text", "en", metadata={"object": object()})
    with pytest.raises(ValueError, match="language"):
        TextUnit("u", "text", " ")


def test_override_scope_validation_and_deterministic_id():
    override = SpeechOverride("ART", "A R T")
    same_override = SpeechOverride("ART", "A R T")
    unit_override = SpeechOverride("ART", "art", scope=OverrideScope(kind="unit", unit_id="u-1"))

    assert override.id == same_override.id
    assert override.id != unit_override.id
    with pytest.raises(ValueError, match="scope"):
        OverrideScope(kind="occurrence", unit_id="u", source_start=2)


def test_stable_ids_are_canonical_and_change_identity_is_source_anchored():
    assert stable_id("x", {"a": 1, "b": [2]}) == stable_id("x", {"b": [2], "a": 1})
    assert source_change_id("u", source_start=1, source_end=4, source="ART") == source_change_id(
        "u", source_start=1, source_end=4, source="ART"
    )
    assert source_change_id("u", source_start=1, source_end=4, source="ART") != source_change_id(
        "u", source_start=1, source_end=5, source="ART"
    )


def test_profile_has_conservative_format_preserving_defaults():
    profile = PreparationProfile()
    assert profile.sequence_fallback_mode == "preserve"
    assert not profile.normalize_unicode
    assert not profile.normalize_whitespace
    assert not profile.strip_outer_whitespace
    assert not profile.collapse_horizontal_whitespace
    assert not profile.normalize_line_whitespace
    assert not profile.collapse_blank_lines
    assert profile.symbol_mode == "none"
    assert not profile.use_spacy


def test_stats_reject_negative_values():
    with pytest.raises(ValueError, match="negative"):
        PreparationStats(units_processed=-1)


def test_error_hierarchy():
    assert issubclass(MappingError, PreparationError)
    assert issubclass(OverrideConflictError, PreparationError)
    assert issubclass(InvalidUnitError, PreparationError)
