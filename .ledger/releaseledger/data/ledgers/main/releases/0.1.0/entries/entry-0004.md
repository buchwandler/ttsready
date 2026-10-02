---
schema_version: 2
object_type: release_entry
versioning:
  schema_version: 1
  revision: 2
entry_id: entry-0004
release_version: 0.1.0
kind: added
summary: Added locks, verification, and freeze output for reproducible preparation
status: accepted
audience: null
scopes: []
source_refs: []
paths:
  - ttsready/reproducibility.py
  - ttsready/freeze.py
issues: []
prs: []
sources:
  - README.md
contributors: []
breaking: false
internal: false
order: 4
---

Locks capture canonical input and preparation context; verification detects drift, and freeze writes a separate materialized SSMD artifact.
