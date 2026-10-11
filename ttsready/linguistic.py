"""Shared validation for provider-neutral linguistic hints."""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

from .errors import InvalidUnitError

if TYPE_CHECKING:
    from .models import LinguisticToken


def validate_linguistic_tokens(
    text: str,
    tokens: Iterable[LinguisticToken],
) -> tuple[LinguisticToken, ...]:
    """Normalize and validate source-relative linguistic hints."""
    if not isinstance(text, str):
        raise InvalidUnitError("linguistic token input text must be a string")
    try:
        supplied = tuple(tokens)
    except TypeError as exc:
        raise InvalidUnitError("linguistic_tokens must be iterable") from exc

    # Import at call time so TextUnit can use this module without an import cycle.
    from .models import LinguisticToken

    if any(not isinstance(token, LinguisticToken) for token in supplied):
        raise InvalidUnitError("linguistic_tokens must contain only LinguisticToken values")

    ordered = tuple(sorted(supplied, key=lambda token: (token.start, token.end)))
    previous_end = 0
    for token in ordered:
        if token.end > len(text):
            raise InvalidUnitError("linguistic token is outside the supplied run text")
        if token.start < previous_end:
            raise InvalidUnitError("linguistic tokens must not overlap")
        if token.text is not None and text[token.start : token.end] != token.text:
            raise InvalidUnitError("linguistic token text does not match the supplied run text")
        previous_end = token.end
    return ordered
