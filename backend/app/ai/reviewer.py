"""Provider-independent interface for advisory AI code reviews."""

from typing import Protocol

from app.domain.entities import Finding


class AIReviewer(Protocol):
    """Review one source file and return validated, advisory findings."""

    async def review(self, *, file_path: str, source_code: str) -> list[Finding]:
        """Analyze source text without executing it or applying suggested changes."""
