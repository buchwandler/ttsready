"""ttsready exceptions."""


class TTSReadyError(Exception):
    """Base exception for expected conversion failures."""


class UnsupportedInputError(TTSReadyError):
    """Raised when no reader supports an input file."""
