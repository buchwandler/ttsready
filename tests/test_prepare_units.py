from dataclasses import replace
from types import SimpleNamespace

import pytest
import spokenform
from spokenform import TokenAnnotation
from spokenform.mapping import OffsetMap

from ttsready import (
    LinguisticToken,
    OverrideScope,
    PreparationProfile,
    SpeechOverride,
    apply_changes,
    prepare_text,
)
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


def test_prepare_units_propagates_initialisms_within_and_across_units():
    units = (
        TextUnit("first", "Someone (ART) agreed. ART’s module opened.", "en-US"),
        TextUnit("second", "Later ART checked it.", "en-US"),
        TextUnit("third", "Another note mentioned ART's module.", "en-US"),
    )

    result = prepare_units(units)
    prepared = {unit.unit_id: unit for unit in result.units}

    assert prepared["first"].spoken_text == "Someone (A R T) agreed. A R T’s module opened."
    assert prepared["second"].spoken_text == "Later A R T checked it."
    assert prepared["third"].spoken_text == "Another note mentioned A R T's module."
    seed = next(
        change for change in result.changes if change.rule == "sequence.parenthesized-initialism"
    )
    assert (seed.source, seed.replacement) == ("ART", "A R T")
    consistency = [change for change in result.changes if change.kind == "consistency"]
    assert [(change.source, change.replacement) for change in consistency] == [
        ("ART’s", "A R T’s"),
        ("ART", "A R T"),
        ("ART's", "A R T's"),
    ]
    assert all(change.stages == ("consistency",) for change in consistency)
    assert all(change.rule == "ttsready.initialism-consistency" for change in consistency)
    for unit in result.units:
        assert apply_changes(unit.source_text, unit.changes) == unit.spoken_text
        assert unit.context.spoken_text == unit.spoken_text
        for change in unit.changes:
            assert unit.spoken_text[change.output_start : change.output_end] == change.replacement
        for left, right in zip(unit.changes, unit.changes[1:], strict=False):
            assert left.source_end <= right.source_start
        for sentence in unit.context.spoken_sentences:
            assert unit.spoken_text[sentence.start : sentence.end] == sentence.text
    assert result.stats.stage_edits["consistency"] == 3
    assert result.stats.changes == len(result.changes)
    assert not [issue for issue in result.issues if issue.code == "qa.initialism_candidate"]


def test_seed_in_later_unit_propagates_to_earlier_occurrence():
    units = (
        TextUnit("early", "ART checked the result.", "en-US"),
        TextUnit("seed", "The system called itself (ART).", "en-US"),
    )

    result = prepare_units(units)
    early = result.units[0]

    assert early.spoken_text == "A R T checked the result."
    change = next(change for change in early.changes if change.kind == "consistency")
    assert (change.source, change.replacement) == ("ART", "A R T")


def test_consistency_is_exact_case_sensitive_and_respects_unicode_boundaries():
    seed = TextUnit("seed", "They named it (ART).", "en-US")
    text = "Art art ARTs ARTS ART-like START ART2 ΩART ARTé."
    protected_start = text.index("ART2")
    target = TextUnit(
        "target",
        text,
        "en-US",
        protected_spans=((protected_start, protected_start + len("ART2")),),
    )

    result = prepare_units((seed, target))

    assert result.units[1].spoken_text == text
    assert not [change for change in result.units[1].changes if change.kind == "consistency"]


def test_no_seed_keeps_uppercase_token_conservative_in_bulk_and_isolated_apis():
    text = "ART is a normal uppercase token here."

    bulk = prepare_units((TextUnit("bulk", text, "en-US"),))
    isolated = prepare_text(text, language="en-US")

    assert bulk.units[0].spoken_text == text
    assert not [change for change in bulk.changes if change.kind == "consistency"]
    assert isolated.spoken_text == text


def test_caller_override_and_protected_span_win_over_consistency():
    text = "(ART) plus ART's and ART’s."
    ascii_start = text.index("ART's")
    curly_start = text.index("ART’s")
    override = SpeechOverride(
        surface="ART's",
        spoken="custom pronunciation",
        match="literal",
        scope=OverrideScope(
            kind="occurrence",
            unit_id="unit",
            source_start=ascii_start,
            source_end=ascii_start + len("ART's"),
        ),
    )
    unit = TextUnit(
        "unit",
        text,
        "en-US",
        protected_spans=((curly_start, curly_start + len("ART’s")),),
    )

    result = prepare_units((unit,), overrides=(override,))
    prepared = result.units[0]

    assert prepared.spoken_text == "(A R T) plus custom pronunciation and ART’s."
    override_change = next(change for change in prepared.changes if change.kind == "override")
    assert (override_change.source, override_change.replacement) == (
        "ART's",
        "custom pronunciation",
    )
    assert not any(
        change.kind == "consistency"
        and change.source_start < override_change.source_end
        and override_change.source_start < change.source_end
        for change in prepared.changes
    )
    assert not any(change.source == "ART’s" for change in prepared.changes)


def test_conflicting_safe_seeds_fail_closed_deterministically(monkeypatch):
    real_backend = spokenform.prepare_language

    def conflicting_backend(text, **kwargs):
        result = real_backend(text, **kwargs)
        if not text.startswith("SeedB"):
            return result
        changes = tuple(
            replace(change, replacement="a r t")
            if change.rule == "sequence.parenthesized-initialism"
            else change
            for change in result.source_replacements
        )
        spoken_text = result.spoken_text
        for change in changes:
            if change.rule == "sequence.parenthesized-initialism":
                spoken_text = (
                    spoken_text[: change.output_start]
                    + change.replacement
                    + spoken_text[change.output_end :]
                )
        return SimpleNamespace(
            spoken_text=spoken_text,
            source_replacements=changes,
            warnings=result.warnings,
            offset_map=result.offset_map,
        )

    monkeypatch.setattr("ttsready.preparation.spokenform.prepare_language", conflicting_backend)
    units = (
        TextUnit("a-seed", "SeedA (ART).", "en-US"),
        TextUnit("b-seed", "SeedB (ART).", "en-US"),
        TextUnit("target", "Later ART.", "en-US"),
    )

    forward = prepare_units(units)
    reverse = prepare_units(tuple(reversed(units)))
    forward_by_id = {unit.unit_id: unit for unit in forward.units}
    reverse_by_id = {unit.unit_id: unit for unit in reverse.units}

    assert forward_by_id["target"].spoken_text == "Later ART."
    assert reverse_by_id["target"].spoken_text == "Later ART."
    assert not [change for change in forward.changes if change.kind == "consistency"]
    forward_issue = next(
        issue for issue in forward.issues if issue.code == "ttsready.initialism_conflict"
    )
    reverse_issue = next(
        issue for issue in reverse.issues if issue.code == "ttsready.initialism_conflict"
    )
    assert forward_issue.message == reverse_issue.message
    assert forward_issue.provenance == reverse_issue.provenance


def test_initialism_seeds_do_not_cross_language_boundaries():
    result = prepare_units(
        (
            TextUnit("english-seed", "The token (ART) appears.", "en-US"),
            TextUnit("french", "ART reste inchangé.", "fr-FR"),
        )
    )

    assert result.units[1].spoken_text == "ART reste inchangé."
    assert not [change for change in result.units[1].changes if change.kind == "consistency"]


def test_prepare_units_initialism_consistency_is_reproducible():
    units = (
        TextUnit("first", "ART checked it.", "en-US"),
        TextUnit("seed", "Someone (ART) agreed.", "en-US"),
    )

    first = prepare_units(units)
    second = prepare_units(units)

    assert first.units == second.units
    assert first.changes == second.changes
    assert first.issues == second.issues
    assert first.stats == second.stats
    assert first.prepared_fingerprint == second.prepared_fingerprint


def test_prepare_units_preserves_spokenform_lexical_slash_change():
    result = prepare_units((TextUnit("slash", "open/close", "en-US"),))

    assert result.units[0].spoken_text == "open slash close"
    assert len(result.changes) == 1
    change = result.changes[0]
    assert (change.source, change.replacement) == ("open/close", "open slash close")
    assert (change.source_start, change.source_end) == (0, len("open/close"))
