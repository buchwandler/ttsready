# Reproducibility

The reproducibility commands are `lock`, `verify`, and `freeze`:

```bash
ttsready lock SOURCE -o lock.json
ttsready verify SOURCE --lock lock.json
ttsready freeze SOURCE -o reviewed.ssmdbook
```

A lock records the canonical content and the runtime/profile details needed to verify the prepared output. `verify` checks that the current input still matches the lock. `freeze` writes a separate artifact with the selected automatic transformations materialized. It does not overwrite the source unless an explicit in-place option is used.

For standalone SSMD input, use the lock path reported by the CLI. For bundle-specific options, run `ttsready lock --help`, `ttsready verify --help`, or `ttsready freeze --help`.
