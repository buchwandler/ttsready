from types import SimpleNamespace

import pytest

from ttsready.errors import (
    InvalidUnitError,
    MappingError,
    OverrideConflictError,
    PreparationError,
)
from ttsready.models import OverrideScope, ProtectedSpan, SpeechOverride
from ttsready.preparation import apply_changes, prepare_text


def _assert_exact_mapping(prepared):
    assert apply_changes(prepared.source_text, prepared.changes) == prepared.spoken_text
    for change in prepared.changes:
        assert prepared.source_text[change.source_start : change.source_end] == change.source
        assert prepared.spoken_text[change.output_start : change.output_end] == change.replacement


def test_prepare_text_returns_exact_source_and_output_changes():
    prepared = prepare_text("2 kg", language="en-US", unit_id="caller/unit-7", role="caption")

    assert prepared.spoken_text == "two kilograms"
    assert prepared.unit_id == "caller/unit-7"
    assert prepared.role == "caption"
    assert len(prepared.changes) == 1
    change = prepared.changes[0]
    assert (change.source_start, change.source_end) == (0, 4)
    assert (change.output_start, change.output_end) == (0, 13)
    assert change.stages == ("structured",)
    assert change.rule == "en.quantity"
    assert change.recognition_domain == "quantities"
    assert change.provenance["origin"] == "spokenform"
    assert change.provenance["language"] == "en-US"
    _assert_exact_mapping(prepared)


def test_prepare_text_preserves_caller_formatting_by_default():
    text = "  A sentence.\n\n"
    prepared = prepare_text(text, language="en-US")
    assert prepared.spoken_text.endswith("\n\n")
    assert prepared.spoken_text.startswith("  ")
    _assert_exact_mapping(prepared)


def test_protected_span_is_not_changed_by_backend_or_override():
    prepared = prepare_text(
        "2 and ART",
        language="en-US",
        protected_spans=(ProtectedSpan(0, 1, "literal number"), (6, 9)),
        overrides=(SpeechOverride("ART", "A R T"),),
    )

    assert prepared.source_text[0] == prepared.spoken_text[0] == "2"
    assert prepared.source_text[6:9] == prepared.spoken_text[6:9] == "ART"
    assert any(issue.code == "override.protected_overlap" for issue in prepared.issues)
    _assert_exact_mapping(prepared)


def test_occurrence_override_precedes_unit_and_global_scopes():
    overrides = (
        SpeechOverride("ART", "global"),
        SpeechOverride("ART", "unit", scope=OverrideScope("unit", unit_id="u")),
        SpeechOverride(
            "ART",
            "occurrence",
            scope=OverrideScope("occurrence", unit_id="u", source_start=0, source_end=3),
        ),
    )
    prepared = prepare_text("ART", language="en-US", unit_id="u", overrides=overrides)

    assert prepared.spoken_text == "occurrence"
    assert len(prepared.changes) == 1
    assert prepared.changes[0].stages == ("override",)
    _assert_exact_mapping(prepared)


def test_explicit_override_merges_with_backend_mapping():
    prepared = prepare_text(
        "2 kg and ART",
        language="en-US",
        unit_id="u",
        overrides=(SpeechOverride("ART", "A R T"),),
    )

    assert prepared.spoken_text == "two kilograms and A R T"
    assert len(prepared.changes) == 2
    assert prepared.changes[0].provenance["origin"] == "spokenform"
    assert prepared.changes[1].provenance["origin"] == "override"
    _assert_exact_mapping(prepared)


def test_equal_priority_conflicting_overrides_fail():
    with pytest.raises(OverrideConflictError):
        prepare_text(
            "ART",
            language="en-US",
            overrides=(SpeechOverride("ART", "first"), SpeechOverride("ART", "second")),
        )


def test_lower_priority_overlapping_override_is_skipped_with_issue():
    prepared = prepare_text(
        "ART",
        language="en-US",
        unit_id="u",
        overrides=(
            SpeechOverride("ART", "global", match="literal"),
            SpeechOverride("AR", "unit", match="literal", scope=OverrideScope("unit", "u")),
        ),
    )

    assert prepared.spoken_text == "unitT"
    assert any(issue.code == "override.lower_priority_overlap" for issue in prepared.issues)
    _assert_exact_mapping(prepared)


def test_occurrence_scope_must_exactly_match_surface():
    override = SpeechOverride(
        "XYZ",
        "spoken",
        scope=OverrideScope("occurrence", "u", 0, 3),
    )
    with pytest.raises(InvalidUnitError, match="exactly match"):
        prepare_text("ART", language="en-US", unit_id="u", overrides=(override,))


def test_inconsistent_backend_mapping_fails_closed(monkeypatch):
    broken = SimpleNamespace(
        spoken_text="wrong",
        source_replacements=(
            SimpleNamespace(
                source_start=0,
                source_end=3,
                output_start=0,
                output_end=5,
                source="ART",
                replacement="A R T",
                stages=("test",),
            ),
        ),
        warnings=(),
    )
    monkeypatch.setattr(
        "ttsready.preparation.spokenform.prepare_language", lambda *args, **kwargs: broken
    )

    with pytest.raises(MappingError, match="output span"):
        prepare_text("ART", language="en-US")


def test_backend_failure_is_reported_as_preparation_error(monkeypatch):
    def fail(*args, **kwargs):
        raise ValueError("backend failure")

    monkeypatch.setattr("ttsready.preparation.spokenform.prepare_language", fail)
    with pytest.raises(PreparationError, match="backend failure"):
        prepare_text("text", language="en-US", strict=True)


def test_change_id_does_not_depend_on_override_replacement():
    first = prepare_text("ART", language="en-US", overrides=(SpeechOverride("ART", "one"),))
    second = prepare_text("ART", language="en-US", overrides=(SpeechOverride("ART", "two"),))

    assert first.changes[0].id == second.changes[0].id
