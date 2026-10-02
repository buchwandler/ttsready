---
schema_version: 2
object_type: release_entry
versioning:
  schema_version: 1
  revision: 2
entry_id: entry-0002
release_version: 0.1.0
kind: added
summary: Added reports, cached context, and explicit overrides for speech review
status: accepted
audience: null
scopes: []
source_refs: []
paths:
  - ttsready/reporting.py
  - ttsready/context.py
  - ttsready/materialization.py
issues: []
prs: []
sources:
  - README.md
contributors: []
breaking: false
internal: false
order: 2
---

Review findings against source spans, inspect cached context, and materialize reviewed sub annotations to a separate artifact by default.
