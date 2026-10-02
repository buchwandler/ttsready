# Speakers

Speaker assignments in `ttsready` use logical speaker IDs, not voice names from a particular speech provider. This keeps reviewed SSMD independent of downstream renderer configuration.

The speaker workflow reads utterances and optional speaker suggestions, stores decisions in a sidecar registry, and can materialize accepted or manual decisions as SSMD `voice` annotations. Use `ttsready speakers --help` to inspect scanning options, `ttsready speaker-set --help` to see how to record a decision, and `ttsready speaker-materialize --help` to materialize one.

Generate utterance IDs from the current speaker scan. Do not guess or reuse IDs from another source snapshot. Provider-specific voice selection and audio rendering belong to downstream tools.
