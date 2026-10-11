# Python API

The public API is exported from `ttsready`. The two preparation entry points accept plain text (or text-unit records) and explicit language tags; they do not accept paths or format-specific document objects.

## Prepare one string

```python
from ttsready import prepare_text

prepared = prepare_text(
    "Use 2 kg of flour.",
    language="en-US",
    unit_id="recipe-step-1",
    role="body",
)

prepared.unit_id
prepared.source_text
prepared.spoken_text
prepared.changes
prepared.issues
prepared.context
```

`prepare_text()` returns one `PreparedUnit`. Optional arguments include source-relative `protected_spans`, `SpeechOverride` values, JSON-safe caller `metadata`, a `PreparationProfile`, and `strict=True`.

## Prepare a compiler-owned run

`prepare_run()` is the low-level source-neutral primitive for a compiler or pipeline that already owns linguistic and sentence analysis. It returns a `PreparedRun` with source/output text, changes, generic issues, language, and an exact `SourceOutputMap`. It does not apply `SpeechOverride`, build `UnitContext`, split sentences, or create aggregate fingerprints.

```python
from ttsready import LinguisticToken, prepare_run

source = "Dr. Smith uses 2 kg."
run = prepare_run(
    source,
    language="en-US",
    linguistic_tokens=(LinguisticToken(0, 3, text="Dr.", pos="PROPN", tag="NNP"),),
    preserve_run_boundaries=True,
)

run.spoken_text
run.changes
run.source_map.map_source_span(0, 3)
run.source_map.to_dict()  # diagnostic representation; not result serialization
```

Token offsets and optional token text refer to exactly the supplied `text`. Callers may derive hints from spaCy or another analyzer, but pass only the provider-neutral `LinguisticToken` fields; TTSReady never accepts the provider object. When tokens are supplied, they are authoritative even if `profile.use_spacy=True`, while that profile option is still forwarded unchanged. TTSReady performs no second NLP pass. Consumers that need POS or morphology on normalized output must analyze `run.spoken_text` downstream.

`SourceOutputMap` preserves Spokenform's left/right boundary biases. Left bias selects the left edge of an ambiguous replacement region; right bias selects the right edge. Span helpers use left bias for the start and right bias for the end. `SourceOutputMap.concatenate()` composes maps for independently prepared slices. `preserve_run_boundaries=True` prevents outer run whitespace from being treated as isolated-document whitespace; it is for slices that will be concatenated, not language detection.

## Prepare ordered units

```python
from ttsready import TextUnit, prepare_units

units = (
    TextUnit("chapter-1", "2 kg", "en-US", role="body"),
    TextUnit("caption-1", "Bonjour.", "fr-FR", role="caption"),
)
result = prepare_units(units)

result.units  # ordered PreparedUnit values
result.changes  # flattened source-relative changes
result.issues  # flattened issues
result.stats  # aggregate PreparationStats
result.prepared_fingerprint  # digest of ordered prepared outputs
```

Unit IDs must be unique within one result. A unit's language is passed explicitly to `spokenform`; it is not inferred from a document. The caller controls the ID namespace and preserves any format-specific structure outside this library.

## Protected spans and profiles

Protected spans are half-open offsets into the exact input string. They are not transformed, and an overlapping override is reported rather than applied:

```python
from ttsready import ProtectedSpan, prepare_text

prepared = prepare_text(
    "Use SKU-42 now.",
    language="en-US",
    protected_spans=(ProtectedSpan(4, 10, reason="inventory identifier"),),
)
```

`PreparationProfile` contains conservative backend and normalization options. Its defaults avoid whitespace/Unicode normalization and preserve residual sequences; number, abbreviation, and structured-value expansion remain enabled. Pass a profile explicitly when reproducibility requires a particular policy.

## Mapping and context

`SpokenChange` records a stable ID, unit ID, original and replacement text, source/output offsets, transformation stages, kind, and JSON-safe provenance. The offsets are half-open Python string indices. Apply a change set with `apply_changes(source_text, changes)`; it verifies that every source span still selects the expected source text and rejects overlapping or stale changes.

A `PreparedUnit` contains sentence context for both source and spoken text. For a specific change in an aggregate result, `context_for_change(result, change_id)` returns its unit and overlapping source/spoken sentences.

## Serialization

`PreparationResult.to_dict()` and `PreparationResult.from_dict()` provide versioned, JSON-ready serialization. The module-level `result_to_dict()` and `result_from_dict()` functions are also exported. The library does not persist serialized values; choose storage and schema-retention policy in the calling application.

See [overrides](overrides.md), [residual QA](qa.md), and [reproducibility](reproducibility.md) for the policy and QA APIs.
