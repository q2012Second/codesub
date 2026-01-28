"""Semantic code analysis for codesub."""

from ..errors import UnsupportedLanguageError
from .construct import Construct
from .fingerprint import compute_body_hash, compute_interface_hash
from .python_indexer import PythonIndexer
from .registry import (
    detect_language,
    get_indexer,
    get_indexer_for_path,
    register_indexer,
    supported_languages,
)

# Register built-in indexers
register_indexer("python", [".py", ".pyw"], PythonIndexer)

# Java indexer registration is conditional on tree-sitter-java availability
try:
    from .java_indexer import JavaIndexer

    register_indexer("java", [".java"], JavaIndexer)
except ImportError:
    # tree-sitter-java not installed, Java support disabled
    pass

__all__ = [
    # Core types
    "Construct",
    # Indexers
    "PythonIndexer",
    # Registry functions
    "register_indexer",
    "detect_language",
    "get_indexer",
    "get_indexer_for_path",
    "supported_languages",
    "UnsupportedLanguageError",
    # Fingerprinting
    "compute_body_hash",
    "compute_interface_hash",
]
