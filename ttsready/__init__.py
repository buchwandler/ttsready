"""Source-neutral preparation, QA, reproducibility, and review APIs."""

from __future__ import annotations

try:
    from ._version import version as __version__
except (ImportError, AttributeError):  # pragma: no cover - bare source tree
    __version__ = "0.2.0"

from .context import context_for_change
from .errors import (
    InvalidUnitError,
    MappingError,
    OverrideConflictError,
    PreparationError,
    TTSReadyError,
)
from .lexical_review import LexicalFinding, LexicalOccurrence, LexicalReviewResult, review_lexicon
from .models import (
    ChangeContext,
    JsonScalar,
    JsonValue,
    OverrideScope,
    PreparationIssue,
    PreparationProfile,
    PreparationResult,
    PreparationStats,
    PreparedUnit,
    ProtectedSpan,
    SentenceSpan,
    SpeechOverride,
    SpokenChange,
    TextChunk,
    TextUnit,
    UnitContext,
)
from .preparation import apply_changes, prepare_text, prepare_units, split_prepared_text
from .qa import check_units
from .reproducibility import (
    override_fingerprint,
    prepared_fingerprint,
    profile_fingerprint,
    runtime_fingerprint,
    runtime_versions,
    unit_fingerprint,
)
from .serialization import result_from_dict, result_to_dict

__all__ = [
    "ChangeContext",
    "InvalidUnitError",
    "JsonScalar",
    "JsonValue",
    "LexicalFinding",
    "LexicalOccurrence",
    "LexicalReviewResult",
    "MappingError",
    "OverrideConflictError",
    "OverrideScope",
    "PreparationError",
    "PreparationIssue",
    "PreparationProfile",
    "PreparationResult",
    "PreparationStats",
    "PreparedUnit",
    "ProtectedSpan",
    "SentenceSpan",
    "SpeechOverride",
    "SpokenChange",
    "TTSReadyError",
    "TextChunk",
    "TextUnit",
    "UnitContext",
    "__version__",
    "apply_changes",
    "check_units",
    "context_for_change",
    "override_fingerprint",
    "prepare_text",
    "prepare_units",
    "prepared_fingerprint",
    "profile_fingerprint",
    "result_from_dict",
    "result_to_dict",
    "review_lexicon",
    "runtime_fingerprint",
    "runtime_versions",
    "split_prepared_text",
    "unit_fingerprint",
]
