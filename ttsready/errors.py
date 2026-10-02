"""ttsready exceptions."""


class TTSReadyError(Exception):
    """Base exception for expected conversion failures."""


class UnsupportedInputError(TTSReadyError):
    """Raised when a path is not a canonical SSMD input."""
