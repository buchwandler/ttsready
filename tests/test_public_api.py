import ttsready
from ttsready import (
    ChangeContext,
    InvalidUnitError,
    JsonScalar,
    JsonValue,
    LexicalFinding,
    LexicalOccurrence,
    LexicalReviewResult,
    LinguisticToken,
    MappingError,
    OverrideConflictError,
    OverrideScope,
    PreparationError,
    PreparationIssue,
    PreparationProfile,
    PreparationProgressCallback,
    PreparationProgressEvent,
    PreparationProgressKind,
    PreparationResult,
    PreparationStats,
    PreparedRun,
    PreparedUnit,
    ProtectedSpan,
    SentenceSpan,
    SourceOutputMap,
    SpeechOverride,
    SpokenChange,
    TextChunk,
    TextUnit,
    TTSReadyError,
    UnitContext,
    __version__,
    apply_changes,
    check_units,
    context_for_change,
    override_fingerprint,
    prepare_run,
    prepare_text,
    prepare_units,
    prepared_fingerprint,
    profile_fingerprint,
    result_from_dict,
    result_to_dict,
    review_lexicon,
    runtime_fingerprint,
    runtime_versions,
    split_prepared_text,
    unit_fingerprint,
)

EXPECTED_EXPORTS = frozenset(
    {
        "ChangeContext",
        "InvalidUnitError",
        "JsonScalar",
        "JsonValue",
        "LinguisticToken",
        "LexicalFinding",
        "LexicalOccurrence",
        "LexicalReviewResult",
        "MappingError",
        "OverrideConflictError",
        "OverrideScope",
        "PreparationError",
        "PreparationIssue",
        "PreparationProfile",
        "PreparationProgressCallback",
        "PreparationProgressEvent",
        "PreparationProgressKind",
        "PreparationResult",
        "PreparationStats",
        "PreparedRun",
        "PreparedUnit",
        "ProtectedSpan",
        "SentenceSpan",
        "SourceOutputMap",
        "SpeechOverride",
        "SpokenChange",
        "TTSReadyError",
        "TextChunk",
        "TextUnit",
        "UnitContext",
        "__version__",
        "apply_changes",
        "check_units",
        "context_for_change",
        "override_fingerprint",
        "prepare_run",
        "prepare_text",
        "prepare_units",
        "prepared_fingerprint",
        "profile_fingerprint",
        "result_from_dict",
        "result_to_dict",
        "review_lexicon",
        "runtime_fingerprint",
        "runtime_versions",
        "split_prepared_text",
        "unit_fingerprint",
    }
)


def test_every_declared_public_export_is_bound():
    assert ttsready.__all__
    assert all(hasattr(ttsready, name) for name in ttsready.__all__)


def test_root_exports_match_the_reviewed_public_surface():
    assert set(ttsready.__all__) == EXPECTED_EXPORTS


def test_representative_models_and_operations_work_from_root_imports():

    public_symbols = (
        ChangeContext,
        InvalidUnitError,
        JsonScalar,
        JsonValue,
        LinguisticToken,
        LexicalFinding,
        LexicalOccurrence,
        LexicalReviewResult,
        MappingError,
        OverrideConflictError,
        OverrideScope,
        PreparationError,
        PreparationIssue,
        PreparationProfile,
        PreparationProgressCallback,
        PreparationProgressEvent,
        PreparationProgressKind,
        PreparationResult,
        PreparationStats,
        PreparedRun,
        PreparedUnit,
        ProtectedSpan,
        SentenceSpan,
        SourceOutputMap,
        SpeechOverride,
        SpokenChange,
        TTSReadyError,
        TextChunk,
        TextUnit,
        UnitContext,
        __version__,
        apply_changes,
        check_units,
        context_for_change,
        override_fingerprint,
        prepare_run,
        prepare_text,
        prepare_units,
        prepared_fingerprint,
        profile_fingerprint,
        result_from_dict,
        result_to_dict,
        review_lexicon,
        runtime_fingerprint,
        runtime_versions,
        split_prepared_text,
        unit_fingerprint,
    )
    assert all(symbol is not None for symbol in public_symbols)
    assert isinstance(__version__, str) and __version__
    assert PreparationProfile()
    assert ProtectedSpan(0, 1)
    assert LinguisticToken(0, 1, text="A")
    assert SpeechOverride("TTS", "text to speech")
    assert callable(apply_changes)
    assert callable(check_units)
    assert callable(context_for_change)
    assert callable(override_fingerprint)
    assert callable(prepared_fingerprint)
    assert callable(profile_fingerprint)
    assert callable(result_from_dict)
    assert callable(result_to_dict)
    assert callable(runtime_fingerprint)
    assert callable(runtime_versions)
    assert callable(unit_fingerprint)

    run = prepare_run("2 kg", language="en-US")
    assert isinstance(run, PreparedRun)
    assert isinstance(run.source_map, SourceOutputMap)

    prepared = prepare_text("We met Siobhan.", language="en-US")
    assert isinstance(prepared, PreparedUnit)
    result = prepare_units((TextUnit("chapter-1", "We met Siobhan.", "en-US"),))
    assert isinstance(result, PreparationResult)
    assert isinstance(result.stats, PreparationStats)
    assert result.units

    chunks = split_prepared_text("First. Second.", language="en-US", max_chars=8)
    assert chunks and all(isinstance(chunk, TextChunk) for chunk in chunks)

    review = review_lexicon(
        (TextUnit("chapter-1", "We met Siobhan.", "en-US"),),
        include_all_tokens=True,
    )
    assert isinstance(review, LexicalReviewResult)
    assert review.findings
    assert all(isinstance(finding, LexicalFinding) for finding in review.findings)
    assert all(
        isinstance(occurrence, LexicalOccurrence)
        for finding in review.findings
        for occurrence in finding.occurrences
    )
