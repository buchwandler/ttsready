# Speech overrides

A `SpeechOverride` maps a source surface to caller-chosen spoken text. It can match literal substrings or whole words, case-sensitively or case-insensitively, and can be scoped to all units, one unit, or one exact occurrence.

## Global and unit-scoped overrides

```python
from ttsready import OverrideScope, SpeechOverride, TextUnit, prepare_units

unit = TextUnit("chapter-1", "ACME ships 2 kg parcels.", "en-US")
company = SpeechOverride("ACME", "A C M E")  # all units
weight = SpeechOverride(
    "kg",
    "kilograms",
    scope=OverrideScope("unit", "chapter-1"),
)
result = prepare_units((unit,), overrides=(company, weight))
```

The default match mode is `word`. Use `match="literal"` to match a substring inside a larger token. The default is case-sensitive; set `case_sensitive=False` for case-insensitive matching.

## Exact occurrence

For a correction that applies only to one occurrence, use source-relative half-open offsets:

```python
from ttsready import OverrideScope, SpeechOverride, TextUnit, prepare_units

unit = TextUnit("caption-1", "Use ACME here, not ACME there.", "en-US")
first_start = unit.text.index("ACME")
override = SpeechOverride(
    "ACME",
    "A C M E",
    scope=OverrideScope(
        "occurrence",
        unit.id,
        first_start,
        first_start + len("ACME"),
    ),
)
result = prepare_units((unit,), overrides=(override,))
```

An occurrence override must exactly select its declared source surface. It cannot overlap a protected span.

## Precedence and conflicts

More specific overrides take precedence: occurrence-scoped overrides, then unit-scoped overrides, then global overrides. A higher-priority overlapping rule wins and a lower-priority rule is reported in `result.issues`. Equally ranked overlapping overrides with different spoken text raise `OverrideConflictError`; resolve that conflict in caller policy before preparation.

Override IDs are deterministic when omitted. They identify the policy and scope; change IDs identify source occurrences independently of the selected replacement. Override provenance can carry JSON-safe caller metadata.
