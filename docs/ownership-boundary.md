# Ownership boundary

`ttsready` has an SSMD-first boundary:

```text
source formats -> ssmdconvert -> canonical SSMD -> ttsready review/materialization
                                                        |
                                                        v
                                         reviewed SSMD for downstream TTS
```

- `ssmdconvert` owns source-format extraction/conversion and `.ssmdbook` loading, validation, and writes.
- `ttsready` owns speech analysis, review, reproducibility checks, and explicit reviewed SSMD changes such as `sub` and logical `voice` annotations.
- Downstream renderers own provider-specific voice configuration and audio generation.

`ttsready` accepts canonical `.ssmd`, `.ssmd.md`, `.ssmdbook`, and `.ssmdbook.zip` input. Convert EPUB, PDF, Markdown, HTML, or plain text with `ssmdconvert` first. The two projects exchange content through SSMD artifacts, not a renderer integration API.
