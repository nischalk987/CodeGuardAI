"""Provider-independent static analyzer interface and safe failures."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, Sequence

from app.domain import Finding


class AnalyzerError(RuntimeError):
    """A safe, user-displayable analyzer failure."""


class AnalyzerTimeoutError(AnalyzerError):
    """The analyzer exceeded its configured wall-clock limit."""


class AnalyzerOutputError(AnalyzerError):
    """The analyzer returned output that could not be safely normalized."""


class CodeAnalyzer(Protocol):
    """Analyze local source files as data; implementations must not execute them."""

    name: str

    def analyze(self, target: Path, *, ignored_paths: Sequence[str] = ()) -> list[Finding]:
        """Return normalized findings for a file or directory on the local machine."""
