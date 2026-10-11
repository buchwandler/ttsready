# Lexical review

`review_lexicon()` identifies caller-owned words that may deserve pronunciation or vocabulary review. It is an analysis helper only: it does not modify text, fetch a lexicon, or require an evidence provider. The operation and result types are exported from the root `ttsready` package.

## Inputs

`review_lexicon(units: Iterable[TextUnit] | PreparationResult, *, provider=None, max_frequency_rank=10_000, min_count=1, max_items=None, unknown_only=False, include_all_tokens=False) -> LexicalReviewResult` accepts an iterable of caller-owned `TextUnit` values or a `PreparationResult`. The evidence provider is optional.

```python
from ttsready import TextUnit, review_lexicon

units = (TextUnit("chapter-1", "We met Siobhan.", "en"),)
review = review_lexicon(
    units,
    max_frequency_rank=10_000,
    min_count=1,
    include_all_tokens=True,
)
```

Pass an iterable of caller-owned `TextUnit` values or a `PreparationResult`. With no `provider`, lexical evidence fields (`known`, `frequency_rank`, and `frequency_count`) are `None`; the heuristic candidate reasons are still available. A provider is caller-owned and is validated for the unit languages it serves.

`max_frequency_rank` marks words beyond the rank threshold as rare when the provider supplies a rank. `min_count` filters terms by their occurrence count, and `max_items` limits the final ordered findings. Each must be positive when specified.

## Results

The returned `LexicalReviewResult` contains an ordered tuple of `LexicalFinding` values and `units_reviewed`.

Each finding includes:

- `id`: deterministic for the normalized word and language;
- `language`, `surface`, and `normalized` forms;
- `count` and `occurrences`;
- `known`, `frequency_rank`, and `frequency_count` from the provider, or `None` when no evidence is available;
- `reasons`: the candidate reasons that matched.

A `LexicalOccurrence` identifies a `unit_id`, half-open `start`/`end` offsets into that original unit's text, and a zero-based `sentence_index` when sentence segmentation identifies one (otherwise `None`). Offsets refer to the exact caller-supplied text; TTSReady does not normalize it before reporting positions.

## Candidate reasons

Current heuristic/evidence reasons are:

- `unknown_to_lexicon`: the provider reports the word as unknown;
- `rare_word`: provider frequency rank exceeds `max_frequency_rank`;
- `proper_name_candidate`: capitalization suggests a possible proper name;
- `mixed_case`: the spelling mixes upper- and lowercase letters outside ordinary title case;
- `all_caps`: the word is written in uppercase;
- `contains_unusual_graphemes`: the spelling contains graphemes that may merit review.

A token can have more than one reason. Finding order is deterministic and prioritizes candidate review rather than preserving source order.

## Filtering behavior

- URL, email, and domain-like spans are excluded from lexical review.
- Tokens overlapping a `TextUnit.protected_spans` span are excluded.
- Numeric-only material is not treated as a lexical word.
- `unknown_only=True` retains only terms for which a provider explicitly returns `known is False`. Without that evidence, `known` is `None` and no term can satisfy this filter.
- `include_all_tokens=True` includes otherwise eligible tokens even when no review reason applies. By default, only terms with at least one reason are returned.

Filtering never removes or changes text; it only controls which findings are returned.

## Optional Lexhint provider

The `lexhint` integration is optional. Construct and manage the provider explicitly; TTSReady does not download datasets or select a lexicon on the caller's behalf.

```python
from lexhint import Lexicon
from ttsready import TextUnit, review_lexicon

lexicon = Lexicon("en", variant="runtime")
review = review_lexicon(
    (TextUnit("chapter-1", "We met Siobhan.", "en"),),
    provider=lexicon,
)

for finding in review.findings:
    print(finding.surface, finding.reasons, finding.known, finding.frequency_rank)
```

Install the optional extra with `python -m pip install 'ttsready[lexical]'` when using Lexhint. See [installation](installation.md) and the [Python API inventory](python-api.md#public-api-inventory).
