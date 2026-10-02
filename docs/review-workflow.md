# Review workflow

The review workflow starts with an analysis report and keeps decisions separate from automatic suggestions:

1. Run `ttsready report SOURCE` and inspect the report and source spans.
2. Use `ttsready context SOURCE CHANGE_ID` to inspect cached source context for a finding.
3. Review the finding and decide whether an explicit SSMD change is appropriate.
4. Use `ttsready override SOURCE CHANGE_ID --spoken TEXT` to write a reviewed `sub` annotation. By default, the result is a separate `.reviewed` artifact.

Use `--write` only when you explicitly intend to replace a source file. Reports and cached analysis do not themselves change SSMD. Generate IDs from the current report rather than guessing them.

Speaker review uses the speaker workflow and sidecar registry described in [Speakers](speakers.md). For input conversion and the ownership boundaries, see [Ownership boundary](ownership-boundary.md).
