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

    def get_container_members(
        self,
        source: str,
        path: str,
        container_qualname: str,
        include_private: bool = False,
        constructs: list[Construct] | None = None,
    ) -> list[Construct]:
        """Get all direct members of a container construct.

        Args:
            source: The complete source code content.
            path: File path (used in construct metadata).
            container_qualname: Qualified name of the container (e.g., "User").
            include_private: Whether to include private members (_prefixed in Python).
                For Java, this parameter is ignored as all members are included.
            constructs: Optional pre-indexed constructs to avoid re-parsing.

        Returns:
            List of Construct objects that are direct members of the container.
        """
        ...

    def extract_imports(self, source: str) -> dict[str, tuple[str, str]]:
        """Extract import mappings from source.

        Returns dict mapping local name to (module/package, original_name).

        For Python:
            {"User": ("models", "User"), "U": ("models", "User")}
        For Java:
            {"User": ("com.example.models.User", "User")}

        Args:
            source: The complete source code content.

        Returns:
            Dict mapping local imported name to (module_path, original_name).
            Star/wildcard imports are skipped.
        """
        ...
