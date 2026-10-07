"""Exceptions for the source-neutral ttsready preparation API."""


class TTSReadyError(Exception):
    """Base exception for ttsready contract or preparation failures."""


class PreparationError(TTSReadyError):
    """Raised when preparation cannot produce a consistent result."""


class MappingError(PreparationError):
    """Raised when backend source mappings cannot be verified."""


class OverrideConflictError(PreparationError):
    """Raised when equally ranked overrides disagree over an overlapping source span."""


class InvalidUnitError(PreparationError):
    """Raised when a text unit or one of its spans violates the public contract."""
