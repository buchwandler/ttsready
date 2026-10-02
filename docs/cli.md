# Command-line interface

Run `ttsready --help` to see all commands and `ttsready COMMAND --help` for command-specific options. The top-level commands are:

- `convert`, `preflight`, `chapters`: prepare, validate, or inspect canonical SSMD input.
- `report`, `context`, `review`, `override`: analyze content and support review of findings.
- `speakers`, `speaker-set`, `speaker-materialize`: review logical speaker assignments and materialize decisions.
- `preview`, `export`: render prepared text or export it as TXT.
- `lock`, `verify`, `freeze`: check and materialize reproducible output.

Typical first checks against a standalone document are:

```bash
ttsready preflight examples/basic.ssmd.md
ttsready report examples/basic.ssmd.md
ttsready preview examples/basic.ssmd.md
ttsready export examples/basic.ssmd.md --format txt -o /tmp/basic.txt
```

Commands accept standalone `.ssmd` and `.ssmd.md` files, `.ssmdbook` directory bundles, and `.ssmdbook.zip` bundles where supported. Consult each command's `--help` for its exact options.
