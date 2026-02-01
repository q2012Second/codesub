"""Inheritance resolution for cross-file change detection."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .construct import Construct
    from .indexer_protocol import SemanticIndexer

# Safety limit to prevent runaway recursion
MAX_INHERITANCE_DEPTH = 10


@dataclass
class InheritanceChainEntry:
    """An entry in an inheritance chain."""

    path: str
    qualname: str
    construct: "Construct"


@dataclass
class InheritanceResolver:
    """Resolves inheritance relationships across files.

    Given a set of indexed files, builds an inheritance graph and
    provides methods to find ancestor chains for any class.

    This resolver works on-demand: it only indexes files needed to
    resolve the inheritance chain, not the entire import graph.
    """

    repo_root: Path
    language: str
    indexer: "SemanticIndexer"

    # Cache: path -> list of Construct
    _constructs_by_path: dict[str, list["Construct"]] = field(default_factory=dict)
    # Cache: (path, qualname) -> Construct
    _class_lookup: dict[tuple[str, str], "Construct"] = field(default_factory=dict)
    # Cache: path -> dict of import mappings (name -> (module_path, original_name))
    _import_map: dict[str, dict[str, tuple[str, str]]] = field(default_factory=dict)
    # Cache: path -> source code
    _source_cache: dict[str, str] = field(default_factory=dict)

    def add_file(
        self,
        path: str,
        constructs: list["Construct"],
        source: str | None = None,
    ) -> None:
        """Add a file's constructs to the resolver.

        Args:
            path: Relative file path.
            constructs: Constructs from indexing the file.
            source: Optional source code for import parsing.
        """
        self._constructs_by_path[path] = constructs
        for c in constructs:
            if c.kind in ("class", "interface", "enum"):
                self._class_lookup[(path, c.qualname)] = c

        if source:
            self._source_cache[path] = source

    def get_inheritance_chain(
        self,
        path: str,
        qualname: str,
    ) -> list[InheritanceChainEntry]:
        """Get full inheritance chain for a class.

        Returns list of InheritanceChainEntry for all ancestors,
        in order from immediate parent to most distant ancestor.
        Handles cross-file inheritance via import resolution.

        Args:
            path: Path of the file containing the class.
            qualname: Qualified name of the class.

        Returns:
            List of ancestors in inheritance order.
        """
        chain: list[InheritanceChainEntry] = []
        visited: set[tuple[str, str]] = set()

        self._build_chain(path, qualname, chain, visited, depth=0)
        return chain

    def _build_chain(
        self,
        path: str,
        qualname: str,
        chain: list[InheritanceChainEntry],
        visited: set[tuple[str, str]],
        depth: int,
    ) -> None:
        """Recursively build inheritance chain."""
        if depth >= MAX_INHERITANCE_DEPTH:
            return  # Safety limit

        construct = self._class_lookup.get((path, qualname))
        if not construct or not construct.base_classes:
            return

        # Ensure imports are parsed for this file
        self._ensure_imports_parsed(path)

        for base_name in construct.base_classes:
            resolved = self._resolve_base_class(path, base_name)
            if resolved is None:
                continue  # Unresolved (stdlib, third-party, etc.)

            resolved_path, resolved_qualname, resolved_construct = resolved
            key = (resolved_path, resolved_qualname)

            if key in visited:
                continue  # Avoid cycles

            visited.add(key)
            chain.append(
                InheritanceChainEntry(
                    path=resolved_path,
                    qualname=resolved_qualname,
                    construct=resolved_construct,
                )
            )

            # Recurse for grandparents
            self._build_chain(
                resolved_path, resolved_qualname, chain, visited, depth + 1
            )

    def _ensure_imports_parsed(self, path: str) -> None:
        """Ensure imports are parsed for a file."""
        if path in self._import_map:
            return

        source = self._source_cache.get(path)
        if not source:
            self._import_map[path] = {}
            return

        # Use the indexer's Tree-sitter based import extraction
        raw_imports = self.indexer.extract_imports(source)

        # Resolve module names to file paths
        resolved_imports: dict[str, tuple[str, str]] = {}
        for name, (module, original_name) in raw_imports.items():
            resolved_path = self._resolve_module_path(module, path)
            if resolved_path:
                resolved_imports[name] = (resolved_path, original_name)

        self._import_map[path] = resolved_imports

    def _resolve_base_class(
        self,
        from_path: str,
        base_name: str,
    ) -> tuple[str, str, "Construct"] | None:
        """Resolve a base class name to its definition location.

        Args:
            from_path: Path of file containing the child class.
            base_name: Name as it appears in source (e.g., "User", "models.User").

        Returns:
            (path, qualname, construct) or None if unresolved.
        """
        # Check local definitions first (same file)
        if (from_path, base_name) in self._class_lookup:
            c = self._class_lookup[(from_path, base_name)]
            return (from_path, base_name, c)

        # Check imports
        imports = self._import_map.get(from_path, {})

        # For dotted names like "models.User", try the first part as import
        if "." in base_name:
            parts = base_name.split(".")
            module_alias = parts[0]
            if module_alias in imports:
                module_path, _ = imports[module_alias]
                remaining_qualname = ".".join(parts[1:])

                # Ensure the target file is indexed
                self._ensure_file_indexed(module_path)

                key = (module_path, remaining_qualname)
                if key in self._class_lookup:
                    return (module_path, remaining_qualname, self._class_lookup[key])

        # Simple name from import
        if base_name in imports:
            module_path, original_name = imports[base_name]

            # Ensure the target file is indexed
            self._ensure_file_indexed(module_path)

            key = (module_path, original_name)
            if key in self._class_lookup:
                return (module_path, original_name, self._class_lookup[key])

        return None  # Unresolved (external dependency)

    def _ensure_file_indexed(self, path: str) -> None:
        """Ensure a file is indexed and available in the resolver."""
        if path in self._constructs_by_path:
            return

        # Try to read and index the file
        try:
            full_path = self.repo_root / path
            if not full_path.exists():
                return

            source = full_path.read_text(encoding="utf-8")
            constructs = self.indexer.index_file(source, path)
            self.add_file(path, constructs, source)
        except (OSError, UnicodeDecodeError):
            pass

    def _resolve_module_path(self, module: str, from_path: str) -> str | None:
        """Convert module name to file path.

        Args:
            module: Module name (e.g., "models", ".sibling", "com.example.User")
            from_path: Path of importing file (for relative import resolution)

        Returns:
            Relative path to module file, or None if external.
        """
        if self.language == "java":
            return self._resolve_java_import(module)
        else:
            return self._resolve_python_import(module, from_path)

    def _resolve_python_import(self, module: str, from_path: str) -> str | None:
        """Resolve Python module to file path."""
        if module.startswith("."):
            # Relative import
            from_dir = Path(from_path).parent

            # Count leading dots
            dots = len(module) - len(module.lstrip("."))
            remainder = module[dots:]

            # Go up directories
            for _ in range(dots - 1):
                from_dir = from_dir.parent

            # Build path
            if remainder:
                candidate = from_dir / remainder.replace(".", "/")
            else:
                candidate = from_dir

            # Try both file.py and package/__init__.py
            py_path = str(candidate) + ".py"
            if (self.repo_root / py_path).exists():
                return py_path

            init_path = str(candidate / "__init__.py")
            if (self.repo_root / init_path).exists():
                return init_path

            return None
        else:
            # Absolute import - check if it's in our repo
            candidate = module.replace(".", "/") + ".py"
            if (self.repo_root / candidate).exists():
                return candidate

            # Try package/__init__.py
            candidate = module.replace(".", "/") + "/__init__.py"
            if (self.repo_root / candidate).exists():
                return candidate

            return None  # External module

    def _resolve_java_import(self, full_import: str) -> str | None:
        """Resolve Java import to file path.

        Java import like "com.example.User" maps to "com/example/User.java".
        """
        # Convert package path to file path
        candidate = full_import.replace(".", "/") + ".java"
        if (self.repo_root / candidate).exists():
            return candidate

        # Check common source roots
        for src_root in ["src/main/java/", "src/", ""]:
            full_candidate = src_root + candidate
            if (self.repo_root / full_candidate).exists():
                return full_candidate

        return None  # External or not found


def get_member_id(qualname: str, language: str) -> str:
    """Get member identifier for override comparison.

    For Java methods, returns full qualname including parameters (overloads matter).
    For Python methods, returns just the method name (no overloading).
    For fields, returns the field name.

    Args:
        qualname: The relative member qualname (e.g., "validate", "process(Order)")
        language: "python" or "java"

    Returns:
        The identifier to use for override comparison.
    """
    if language == "python":
        # Python has no overloading, use name only
        # But qualname might be nested like "validate" - use as-is
        return qualname
    else:
        # Java: use full qualname including params for methods
        # e.g., "process(Order,User)" stays as-is
        return qualname


def get_overridden_members(
    child_members: list["Construct"],
    child_qualname: str,
    language: str,
) -> set[str]:
    """Get set of member IDs that the child class defines (overrides).

    Args:
        child_members: List of constructs that are direct members of the child.
        child_qualname: The child class's qualname.
        language: "python" or "java"

    Returns:
        Set of member IDs that the child defines.
    """
    prefix = child_qualname + "."
    overridden: set[str] = set()

    for c in child_members:
        if c.qualname.startswith(prefix):
            relative_id = c.qualname[len(prefix) :]
            # Skip nested members
            if "." in relative_id:
                continue
            member_id = get_member_id(relative_id, language)
            overridden.add(member_id)

    return overridden
