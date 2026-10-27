# Python API

The supported Python API is the set exported from the root `ttsready` package via `ttsready.__all__`. It is source-neutral: callers provide text and explicit language values, and TTSReady does not accept paths or format-specific document objects.

The public preparation surface has three levels: `prepare_run()`, `prepare_text()`, and `prepare_units()`.

## Public API inventory

The root `ttsready.__all__` is the supported API boundary. The names below are the intentional exports; a helper that is available only from an implementation submodule is not thereby a supported public API.

| Family                       | Root exports                                                                                                                                                                                |
| ---------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Version                      | `__version__`                                                                                                                                                                               |
| JSON and input/policy models | `JsonScalar`, `JsonValue`, `LinguisticToken`, `TextUnit`, `ProtectedSpan`, `PreparationProfile`, `OverrideScope`, `SpeechOverride`                                                          |
| Preparation                  | `prepare_run()`, `prepare_text()`, `prepare_units()`, `apply_changes()`, `split_prepared_text()`                                                                                            |
| Results and mapping          | `SpokenChange`, `PreparationIssue`, `SourceOutputMap`, `PreparedRun`, `PreparedUnit`, `PreparationStats`, `PreparationResult`, `TextChunk`                                                  |
| Context                      | `SentenceSpan`, `UnitContext`, `ChangeContext`, `context_for_change()`                                                                                                                      |
| QA                           | `check_units()`; see [residual QA](qa.md)                                                                                                                                                   |
| Lexical review               | `LexicalOccurrence`, `LexicalFinding`, `LexicalReviewResult`, `review_lexicon()`; see [lexical review](lexical-review.md)                                                                   |
| Reproducibility              | `runtime_versions()`, `profile_fingerprint()`, `override_fingerprint()`, `runtime_fingerprint()`, `unit_fingerprint()`, `prepared_fingerprint()`; see [reproducibility](reproducibility.md) |
| Serialization                | `result_to_dict()`, `result_from_dict()`; see [reproducibility and serialization](reproducibility.md)                                                                                       |
| Bulk progress                | `PreparationProgressCallback`, `PreparationProgressEvent`, `PreparationProgressKind`                                                                                                        |
| Errors                       | `TTSReadyError`, `PreparationError`, `MappingError`, `OverrideConflictError`, `InvalidUnitError`                                                                                            |

Input models describe caller-owned text, language, policy, and optional source-relative hints. Result models describe in-memory prepared output, mappings, context, QA, statistics, lexical findings, or progress observations. `JsonScalar` and `JsonValue` identify the JSON-safe metadata value types. See the sections below and the linked guides for behavior and examples.

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

### Preparation-set initialism consistency

Spokenform owns linguistic recognition: a high-confidence parenthesized initialism such as `(ART)` can establish `ART -> A R T`. TTSReady applies a separate, conservative consistency pass in `prepare_units()` so exact, case-sensitive occurrences of that source stem remain consistent across same-language units, including possessives:

```python
from ttsready import TextUnit, prepare_units

result = prepare_units(
    (
        TextUnit("first", "(ART) was announced. ART’s module was ready.", "en-US"),
        TextUnit("later", "Later ART checked it.", "en-US"),
    )
)
[unit.spoken_text for unit in result.units]
# ['(A R T) was announced. A R T’s module was ready.', 'Later A R T checked it.']
```

This is preparation-set consistency, not generic acronym detection. `prepare_text("ART is here", language="en-US")` remains conservative because it has no other unit or contextual seed to propagate. Explicit overrides, protected spans, and existing backend changes take precedence.

`TextUnit.linguistic_tokens` accepts source-relative `LinguisticToken` hints. It normalizes them by `(start, end)` and validates bounds, non-overlap, token text, and provider-neutral type. `prepare_units()` and `prepare_text()` forward supplied hints to Spokenform without asking TTSReady to load an NLP provider. Units without hints keep the original behavior and fingerprint.

`prepare_units(..., on_progress=callback)` optionally reports synchronous `PreparationProgressEvent` values (`unit.started` and `unit.completed`) with completed/total counts and unit ID, language, and role. Events are observational, are not serialized, and callback exceptions propagate. TTSReady does not print or render progress.

```python
from ttsready import PreparationProgressEvent, TextUnit, prepare_units


def report(event: PreparationProgressEvent) -> None:
    print(event.kind, event.completed, event.total, event.unit_id)


result = prepare_units((TextUnit("chapter-1", "2 kg", "en-US"),), on_progress=report)
```

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

`SpokenChange.language` is the effective language reported by the preparation backend for that individual replacement. TTSReady preserves it exactly, even when its spelling or case differs from `PreparedRun.language` or `PreparedUnit.language`; if the backend supplies no per-change language, the value is `None`. TTSReady does not infer or substitute a value. Use this typed field for replacement-level language; the existing `provenance["language"]` remains run/unit context and is not the per-change contract.

```python
from ttsready import prepare_run

run = prepare_run("Dr. bought 5 kg.", language="en-us")
for change in run.changes:
    print(change.source, change.language)
```

A `PreparedUnit` contains sentence context for both source and spoken text. For a specific change in an aggregate result, `context_for_change(result, change_id)` returns its unit and overlapping source/spoken sentences.

## Text chunking

`split_prepared_text(text, *, language, max_chars) -> tuple[TextChunk, ...]` chunks the string supplied by the caller; it does not prepare, normalize, or otherwise transform it. Splits prefer sentence boundaries and fall back to smaller pieces as needed to satisfy the character limit.

- Every `TextChunk.text` is an exact slice of the original string, and `start`/`end` are source-relative half-open offsets.
- `part` is zero-based; chunks concatenate back to the exact input and each chunk has at most `max_chars` characters.
- Empty input returns `()`. A `max_chars` value below 1 raises `ValueError`.

```python
from ttsready import split_prepared_text

source = "First sentence. Second sentence."
chunks = split_prepared_text(source, language="en-US", max_chars=20)
assert "".join(chunk.text for chunk in chunks) == source
```

## Public models and errors

Input objects include `TextUnit`, `ProtectedSpan`, `LinguisticToken`, `PreparationProfile`, `OverrideScope`, and `SpeechOverride`. Returned objects include `PreparedRun`, `PreparedUnit`, `PreparationResult`, `SpokenChange`, `PreparationIssue`, `SourceOutputMap`, `PreparationStats`, `TextChunk`, `SentenceSpan`, `UnitContext`, and `ChangeContext`. Lexical review and progress return their own result/event types, described in the [lexical review guide](lexical-review.md) and the progress section above.

| Exception               | Typical origin                                             |
| ----------------------- | ---------------------------------------------------------- |
| `TTSReadyError`         | Base for TTSReady contract and preparation failures        |
| `PreparationError`      | A preparation operation cannot produce a consistent result |
| `MappingError`          | Backend source/output mappings fail verification           |
| `OverrideConflictError` | Equally ranked overlapping overrides disagree              |
| `InvalidUnitError`      | A text unit or its spans violate the public contract       |

`PreparationError` derives from `TTSReadyError`; the other specific preparation exceptions derive from `PreparationError`. Raw model construction may raise ordinary `ValueError` or `TypeError`; those errors are not universally converted to TTSReady-specific exceptions.

`__version__` is exported from the root package. Its SCM-derived and neutral-fallback semantics are documented under [runtime versions](reproducibility.md).

## Serialization

`PreparationResult.to_dict()` and `PreparationResult.from_dict()` provide versioned, JSON-ready serialization. The module-level `result_to_dict()` and `result_from_dict()` functions are also exported. The library does not persist serialized values; choose storage and schema-retention policy in the calling application.

See [overrides](overrides.md), [residual QA](qa.md), and [reproducibility](reproducibility.md) for the policy and QA APIs.
