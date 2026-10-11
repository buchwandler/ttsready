---
schema_version: 2
object_type: release_entry
versioning:
  schema_version: 1
  revision: 1
entry_id: entry-0007
release_version: 0.2.2
kind: added
summary: Added provider-neutral token hints and progress events to bulk preparation
status: accepted
audience: null
scopes: []
source_refs: []
paths:
  - ttsready/models.py
  - ttsready/preparation.py
  - ttsready/reproducibility.py
  - docs/python-api.md
  - docs/ownership-boundary.md
issues: []
prs: []
sources:
  - tl:task-0011
contributors: []
breaking: false
internal: false
order: 7
---

TextUnit linguistic tokens are validated and forwarded without provider loading; hints participate in fingerprints while no-token hashes remain compatible. prepare_units() emits synchronous typed observations, and TTSReady remains silent and API-only.
