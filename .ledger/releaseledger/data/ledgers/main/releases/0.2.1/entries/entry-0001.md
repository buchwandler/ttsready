---
schema_version: 2
object_type: release_entry
versioning:
  schema_version: 1
  revision: 2
entry_id: entry-0001
release_version: 0.2.1
kind: added
summary:
  Added compiler-facing run preparation with exact source/output maps and provider-neutral
  linguistic hints
status: accepted
audience: null
scopes: []
source_refs:
  - tl:task-0009
paths:
  - ttsready/preparation.py
  - ttsready/models.py
issues: []
prs: []
sources: []
contributors: []
breaking: false
internal: false
order: 1
---

The additive prepare_run API shares TTSReady's validated Spokenform adapter with the existing review-oriented preparation APIs and supports protected spans and preserved run boundaries.
