---
schema_version: 2
object_type: release_entry
versioning:
  schema_version: 1
  revision: 1
entry_id: entry-0002
release_version: 0.2.1
kind: added
summary: Added SpokenChange.language for backend-reported per-replacement language
status: accepted
audience: null
scopes: []
source_refs:
- tl:task-0011
paths:
- ttsready/models.py
- ttsready/preparation.py
- ttsready/serialization.py
issues: []
prs: []
sources: []
contributors: []
breaking: false
internal: false
order: 2
---
The value is preserved exactly through preparation and serialization; missing backend values remain None and older v2 payloads remain readable.
