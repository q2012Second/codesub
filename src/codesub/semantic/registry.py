"""Registry for semantic indexers."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Callable

from ..errors import UnsupportedLanguageError

if TYPE_CHECKING:
    from .indexer_protocol import SemanticIndexer

# Global registry state
_language_factories: dict[str, Callable[[], SemanticIndexer]] = {}
_extension_to_language: dict[str, str] = {}
_indexer_cache: dict[str, SemanticIndexer] = {}


def register_indexer(
    language: str,
    extensions: list[str],
    factory: Callable[[], SemanticIndexer],
) -> None:
    """Register an indexer factory for a language.

    Args:
        language: Language identifier (e.g., "python", "java").
        extensions: File extensions to associate (e.g., [".py", ".pyw"]).
        factory: Callable that returns a SemanticIndexer instance.
    """
    _language_factories[language] = factory
    for ext in extensions:
        _extension_to_language[ext.lower()] = language


def detect_language(path: str) -> str:
    """Detect the programming language from a file path.

    Args:
        path: File path to analyze.

    Returns:
        Language identifier (e.g., "python", "java").

    Raises:
        UnsupportedLanguageError: If the file extension is not recognized.
    """
    ext = Path(path).suffix.lower()
    if ext not in _extension_to_language:
        raise UnsupportedLanguageError(
            language=ext or "<no extension>",
            supported=sorted(_language_factories.keys()),
            hint=f"File '{path}' has no registered indexer.",
        )
    return _extension_to_language[ext]


def get_indexer(language: str) -> SemanticIndexer:
    """Get an indexer instance for a language.

    Args:
        language: Language identifier (e.g., "python", "java").

    Returns:
        A SemanticIndexer instance for the language.

    Raises:
        UnsupportedLanguageError: If the language is not supported.
    """
    if language not in _language_factories:
        raise UnsupportedLanguageError(
            language=language,
            supported=sorted(_language_factories.keys()),
        )

    # Use cached indexer if available
    if language not in _indexer_cache:
        _indexer_cache[language] = _language_factories[language]()
    return _indexer_cache[language]


def get_indexer_for_path(path: str) -> tuple[str, SemanticIndexer]:
    """Get an indexer for a file path.

    Args:
        path: File path to get indexer for.

    Returns:
        Tuple of (language, indexer).

    Raises:
        UnsupportedLanguageError: If the file extension is not recognized.
    """
    language = detect_language(path)
    return language, get_indexer(language)


def supported_languages() -> list[str]:
    """Get list of supported language identifiers.

    Returns:
        Sorted list of language identifiers.
    """
    return sorted(_language_factories.keys())


def clear_registry() -> None:
    """Clear the registry. Mainly for testing."""
    _language_factories.clear()
    _extension_to_language.clear()
    _indexer_cache.clear()
