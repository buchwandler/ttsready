# Reproducibility and serialization

`prepare_units()` returns fingerprints for the effective preparation profile, ordered override policy, semantic runtime versions, and ordered prepared output:

```python
from ttsready import TextUnit, prepare_units

result = prepare_units((TextUnit("unit-1", "2 kg", "en-US"),))
print(result.profile_fingerprint)
print(result.override_fingerprint)
print(result.runtime_fingerprint)
print(result.prepared_fingerprint)
```

The runtime fingerprint covers `ttsready`, `spokenform`, and `phrasplit`. The prepared-output fingerprint covers ordered unit IDs and their spoken text. `profile_fingerprint()`, `override_fingerprint()`, `runtime_fingerprint()`, and `unit_fingerprint()` are available for caller-defined verification or record layouts. Change IDs identify the source occurrence (`unit_id`, source span, and source text), not the replacement value.

Fingerprints are digests, not locks or persistent records. `ttsready` does not read a source file, create a cache, save a lock, or verify stored state; the caller chooses storage, retention, and comparison policy.

## JSON round trips

Preparation results can be serialized to built-in JSON values and restored:

```python
import json
from ttsready import TextUnit, prepare_units, result_from_dict, result_to_dict

result = prepare_units((TextUnit("unit-1", "2 kg", "en-US"),))
encoded = json.dumps(result_to_dict(result), sort_keys=True)
restored = result_from_dict(json.loads(encoded))
assert restored == result
```

`PreparationResult.to_dict()` and `.from_dict()` provide the same contract. Serialization uses a versioned result schema; it does not write data to disk. JSON-safe metadata and provenance are required so serialized results remain portable.
