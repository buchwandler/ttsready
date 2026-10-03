"""Adaptive narrow-terminal help formatting for the TTSReady CLI."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import typer
from typer.core import TyperCommand, TyperGroup

NARROW_HELP_WIDTH = 72

# Typer exposes its context and formatter through the command class. Recent
# Typer versions vendor Click-compatible classes, so derive from that context
# rather than mixing exception types from a separately installed Click.
_BaseHelpContext = TyperCommand.context_class
_BaseHelpFormatter = _BaseHelpContext.formatter_class


class AdaptiveHelpFormatter(_BaseHelpFormatter):
    """Use stacked definition lists on narrow terminals."""

    def write_dl(
        self,
        rows: Sequence[tuple[str, str]],
        col_max: int = 30,
        col_spacing: int = 2,
    ) -> None:
        rows = list(rows)

        if self.width >= NARROW_HELP_WIDTH:
            super().write_dl(rows, col_max=col_max, col_spacing=col_spacing)
            return

        for index, (term, description) in enumerate(rows):
            self.write(f"{'':>{self.current_indent}}{term}\n")
            if description:
                with self.indentation():
                    with self.indentation():
                        self.write_text(description)
            if index < len(rows) - 1:
                self.write("\n")


class AdaptiveHelpContext(_BaseHelpContext):
    formatter_class = AdaptiveHelpFormatter


class AdaptiveTyperCommand(TyperCommand):
    context_class = AdaptiveHelpContext


class AdaptiveTyperGroup(TyperGroup):
    context_class = AdaptiveHelpContext


class AdaptiveTyper(typer.Typer):
    """Typer app that assigns the adaptive command class by default."""

    def command(self, *args: Any, **kwargs: Any) -> Any:
        kwargs.setdefault("cls", AdaptiveTyperCommand)
        return super().command(*args, **kwargs)
