"""Fingerprint computation for code constructs."""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import tree_sitter


def compute_interface_hash(
    kind: str,
    annotation: str | None,
    decorators: list[str],
    params_node: "tree_sitter.Node | None" = None,
    source_bytes: bytes | None = None,
) -> str:
    """
    Compute interface hash (rename-resistant).

    Includes: kind, type annotation, decorators, method parameters with types/defaults
    Excludes: construct name
    """
    components = [kind]

    # Add type annotation
    components.append(annotation or "<no-annotation>")

    # Add sorted decorators
    components.extend(sorted(decorators))

    # Add method parameters if present
    if params_node and source_bytes:
        params_str = _normalize_params(params_node, source_bytes)
        components.append(params_str)

    return _hash(components)


def compute_body_hash(node: "tree_sitter.Node | None", source_bytes: bytes) -> str:
    """
    Compute body hash (content change detection).

    Includes: all tokens except comments and whitespace
    """
    if node is None:
        return _hash(["<no-default>"])

    tokens = _extract_tokens(node, source_bytes)
    return _hash(tokens)


def _normalize_params(params_node: "tree_sitter.Node", source_bytes: bytes) -> str:
    """Extract normalized parameter representation including types and defaults."""
    parts = []
    for child in params_node.children:
        if child.type in (
            "identifier",
            "typed_parameter",
            "default_parameter",
            "typed_default_parameter",
            "list_splat_pattern",
            "dictionary_splat_pattern",
        ):
            # Get full text including type annotations and defaults
            text = source_bytes[child.start_byte : child.end_byte].decode()
            # Normalize whitespace
            text = " ".join(text.split())
            parts.append(text)
    return ",".join(parts)


def _extract_tokens(node: "tree_sitter.Node", source_bytes: bytes) -> list[str]:
    """Extract leaf tokens, excluding comments and whitespace."""
    tokens: list[str] = []
    _collect_tokens(node, source_bytes, tokens)
    return tokens


def _collect_tokens(
    node: "tree_sitter.Node", source_bytes: bytes, tokens: list[str]
) -> None:
    """Recursively collect tokens."""
    # Skip comments
    if node.type == "comment":
        return

    # Leaf node - extract text
    if len(node.children) == 0:
        text = source_bytes[node.start_byte : node.end_byte].decode().strip()
        if text:  # Skip empty/whitespace-only
            tokens.append(text)
    else:
        for child in node.children:
            _collect_tokens(child, source_bytes, tokens)


def _hash(components: list[str]) -> str:
    """Hash components into 16-char hex digest."""
    content = "\x00".join(components)
    return hashlib.sha256(content.encode()).hexdigest()[:16]
