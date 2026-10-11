# Quickstart

`prepare_text()` prepares one caller-owned string with an explicit language. It returns a `PreparedUnit` containing the original text, spoken text, exact changes, issues, and sentence context.

```python
from ttsready import prepare_text

prepared = prepare_text("A 2 kg parcel.", language="en-US", unit_id="parcel")
print(prepared.spoken_text)

for change in prepared.changes:
    print(
        f"{change.source!r} -> {change.replacement!r} "
        f"(source {change.source_start}:{change.source_end}, "
        f"output {change.output_start}:{change.output_end})"
    )
```

Both spans are half-open Python string offsets. The source span selects the original occurrence; the output span selects its replacement in `spoken_text`.

## Compiler-owned runs

If your pipeline already performs linguistic analysis and segmentation, use `prepare_run()` instead of wrapping the run in review-oriented `TextUnit` context:

```python
from ttsready import LinguisticToken, prepare_run

source = "Dr. Smith measured 2 kg."
run = prepare_run(
    source,
    language="en-US",
    linguistic_tokens=(LinguisticToken(0, 3, text="Dr.", pos="PROPN"),),
    preserve_run_boundaries=True,
)
print(run.spoken_text)
output_start, output_end = run.source_map.map_source_span(0, 3)
```

`LinguisticToken` offsets are relative to exactly this run. Hints can come from any analyzer; TTSReady does not load or receive its provider object. Source maps retain left/right bias at ambiguous replacements, and their span helpers use left bias for the start and right bias for the end. Concatenate maps with `SourceOutputMap.concatenate()` when the caller combines independently prepared runs. `prepare_run()` does not apply overrides or split sentences; see [Python API](python-api.md) for the contract and `prepare_text()`/`prepare_units()` for review-oriented preparation.

## Multiple units

Use `TextUnit` and `prepare_units()` for multiple text segments. Each unit supplies its own language and stable caller ID; order is preserved.

```python
from ttsready import TextUnit, prepare_units

result = prepare_units(
    (
        TextUnit("chapter-1", "2 kg", "en-US", role="body"),
        TextUnit("caption-1", "Bonjour.", "fr-FR", role="caption"),
    )
)

for unit in result.units:
    print(unit.unit_id, unit.language, unit.spoken_text)
print(result.stats.units_processed)
```

The aggregate result also exposes combined `changes`, `issues`, statistics, and profile/override/runtime/output fingerprints. No file, format object, or document wrapper is needed. See [overrides](overrides.md), [residual QA](qa.md), and [reproducibility](reproducibility.md) for the rest of the API.
