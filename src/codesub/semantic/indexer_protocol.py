"""Protocol definition for semantic indexers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from .construct import Construct


class SemanticIndexer(Protocol):
    """Protocol for language-specific semantic indexers.

    Implementations extract semantic constructs from source code,
    enabling semantic subscriptions that track code by identity
    rather than line numbers.

    Each implementation handles a specific programming language
    (e.g., PythonIndexer, JavaIndexer).
    """

    def index_file(self, source: str, path: str) -> list[Construct]:
        """Extract all constructs from source code.

        Args:
            source: The complete source code content.
            path: File path (used in construct metadata).

        Returns:
            List of all discoverable constructs in the file.
        """
        ...

    def find_construct(
        self, source: str, path: str, qualname: str, kind: str | None = None
    ) -> Construct | None:
        """Find a specific construct by qualified name.

        Args:
            source: The complete source code content.
            path: File path (used in construct metadata).
            qualname: Qualified name to search for (e.g., "User.validate").
            kind: Optional kind filter for disambiguation.

        Returns:
            The matching construct, or None if not found or ambiguous.
        """
        ...
