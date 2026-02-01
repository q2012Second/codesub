# Implementation Plan: Inheritance-Aware Change Detection

## Summary

Implement inheritance-aware change detection for semantic subscriptions. When a parent class changes, subscriptions on child classes that inherit affected members should be triggered. This enables tracking of breaking changes that propagate through inheritance hierarchies across files.

## Design Decisions

| Decision | Rationale |
|----------|-----------|
| Add `base_classes` field to `Construct` dataclass | Stores parsed base class names for inheritance resolution |
| Create dedicated `inheritance.py` module | Separates concerns; handles import resolution and inheritance chain building |
| Use simple name extraction from superclasses node | Tree-sitter already provides the AST; parsing `(User, Mixin)` text is straightforward |
| Build inheritance graph lazily per-scan | Avoids caching complexity; inheritance can change between commits |
| **Java override: use full signature, not base name** | **EXTERNAL REVIEW FIX**: Java overloads ≠ overrides. `process(Order)` does NOT override `process(Order,User)`. Must compare full member ID for Java methods. |
| **Python override: use name-only** | Python has no overloading, so name-only comparison is correct |
| Automatic for all semantic subscriptions | User requirement: no opt-in flags needed |
| Cross-file from the start | User requirement: parent/child can be in different files |
| Support full inheritance chain | User requirement: grandparents, great-grandparents, etc. |
| Use Tree-sitter for import parsing | Regex-based import parsing is fragile. Tree-sitter handles multi-line imports, aliases correctly |
| **Resolve chain on-demand, not full import graph** | **EXTERNAL REVIEW FIX**: Indexing all imports is overkill. Resolve only the inheritance chain lazily. |
| Add depth limit for inheritance traversal | Safety valve to prevent runaway recursion (MAX_DEPTH=10) |
| Use existing change types with "source": "inherited" metadata | Maintains consistency - STRUCTURAL or CONTENT, with inheritance context as metadata |
| **Return (trigger, proposal) tuple** | **EXTERNAL REVIEW FIX**: `_check_semantic()` returns tuple, not single Trigger |
| **Ref-aware caching for parent diffing** | **EXTERNAL REVIEW FIX**: Need to diff parents between base_ref and target_ref |
| **Track intermediate overrides** | **EXTERNAL REVIEW FIX**: If B overrides A.foo, changes to A.foo should NOT trigger C(B) |
| **Document MRO limitation** | **EXTERNAL REVIEW FIX**: Python MRO is complex; document that we may over-trigger in diamond cases |

**User Requirements:**
1. Full inheritance chain - Track all ancestors (grandparents, great-grandparents), not just direct parents
2. No trigger for overridden methods - If child overrides a method, parent changes don't trigger child
3. Automatic for all semantic subscriptions - No extra flags needed
4. Cross-file from the start - Support parent/child in different files (requires import resolution)

**Alternative Approaches Considered:**
- Store inheritance info in `SemanticTarget` at subscription time: Rejected because inheritance can change; need to resolve at scan time
- Add `--track-inheritance` flag: Rejected per user requirement for automatic behavior
- Single-file only first: Rejected per user requirement for cross-file support from the start
- Add "INHERITED" as separate change type: Rejected; using existing types (STRUCTURAL/CONTENT) with `source: inherited` metadata maintains semantic consistency
- Regex-based import parsing: Rejected; fails on multi-line imports, star imports, docstrings
- Only index files in diff: Rejected; parents often exist in unchanged files

## Prerequisites

- Familiarity with Tree-sitter AST structure for Python and Java
- Understanding of current `_check_semantic()` and `_check_container_members()` flow in detector.py
- Python import resolution basics (relative imports, `from x import y`)
- Java package/import resolution basics (`import com.example.User`)

## Implementation Steps

### Step 1: Extend Construct Dataclass

**Files:** `/Users/vlad/dev/projects/codesub/src/codesub/semantic/construct.py`

**Changes:**
- Add optional `base_classes` field to store list of base class names

**Code:**
```python
@dataclass(frozen=True)
class Construct:
    # ... existing fields ...

    # Base classes for class/interface constructs (None for non-class kinds)
    # Stores simple names as they appear in source: ["User", "Mixin"]
    # For Java, includes both extends and implements
    base_classes: tuple[str, ...] | None = None
```

**Notes:**
- Use `tuple` instead of `list` for immutability (frozen dataclass)
- `None` for non-class constructs (variables, methods, fields)
- Store simple names only; resolution to qualified names happens in inheritance module

---

### Step 2: Update Python Indexer to Extract Base Classes

**Files:** `/Users/vlad/dev/projects/codesub/src/codesub/semantic/python_indexer.py`

**Changes:**
- Add `_extract_base_classes()` helper method
- Add `extract_imports()` public method using Tree-sitter (not regex)
- Update `_parse_class_container()` to populate `base_classes` field

**Code for `_extract_base_classes()`:**
```python
def _extract_base_classes(
    self,
    superclasses_node: tree_sitter.Node | None,
    source_bytes: bytes,
) -> tuple[str, ...]:
    """Extract base class names from superclasses node.

    Parses nodes like: (User, Mixin, ABC)
    Returns: ("User", "Mixin", "ABC")
    """
    if not superclasses_node:
        return ()

    base_names: list[str] = []
    for child in superclasses_node.children:
        # argument_list contains the actual base classes
        if child.type == "argument_list":
            for arg in child.children:
                if arg.type == "identifier":
                    base_names.append(self._node_text(arg, source_bytes))
                elif arg.type == "attribute":
                    # Handle module.ClassName pattern
                    base_names.append(self._node_text(arg, source_bytes))

    return tuple(base_names)
```

**Code for `extract_imports()` using Tree-sitter:**
```python
def extract_imports(self, source: str) -> dict[str, tuple[str, str]]:
    """Extract import mappings from source using Tree-sitter.

    Returns dict mapping local name to (module, original_name).
    Example: {"User": ("models", "User"), "U": ("models", "User")}

    Handles:
    - from models import User
    - from models import User as U
    - import models
    - from . import sibling
    - from ..parent import Something
    - Multi-line imports: from x import (A, B, C)
    - Does NOT expand star imports (returns empty for those)
    """
    tree = self._parser.parse(source.encode())
    source_bytes = source.encode()
    import_map: dict[str, tuple[str, str]] = {}

    for child in tree.root_node.children:
        if child.type == "import_statement":
            # import module [as alias]
            for name_child in child.children:
                if name_child.type == "dotted_name":
                    module = self._node_text(name_child, source_bytes)
                    # Check for alias
                    alias = None
                    idx = child.children.index(name_child)
                    if idx + 2 < len(child.children) and child.children[idx + 1].type == "as":
                        alias_node = child.children[idx + 2]
                        if alias_node.type == "identifier":
                            alias = self._node_text(alias_node, source_bytes)
                    local_name = alias or module.split(".")[-1]
                    import_map[local_name] = (module, module.split(".")[-1])

        elif child.type == "import_from_statement":
            # from module import name [as alias], ...
            module = None
            # Find module_name (dotted_name or relative_import)
            for part in child.children:
                if part.type == "dotted_name":
                    module = self._node_text(part, source_bytes)
                    break
                elif part.type == "relative_import":
                    # Handle . or .. prefix
                    module = self._node_text(part, source_bytes)
                    break

            if module is None:
                continue

            # Find imported names (may be in child nodes or in a parenthesized list)
            for part in child.children:
                if part.type == "dotted_name" and module is None:
                    module = self._node_text(part, source_bytes)
                elif part.type == "wildcard_import":
                    # Star import - can't resolve, skip
                    continue
                elif part.type == "aliased_import":
                    # name as alias
                    name_node = part.child_by_field_name("name")
                    alias_node = part.child_by_field_name("alias")
                    if name_node and alias_node:
                        original = self._node_text(name_node, source_bytes)
                        alias = self._node_text(alias_node, source_bytes)
                        import_map[alias] = (module, original)
                elif part.type == "identifier":
                    # Direct import: from x import Name
                    name = self._node_text(part, source_bytes)
                    if name not in ("import", "from", "as"):
                        import_map[name] = (module, name)

    return import_map
```

**Update `_parse_class_container()`:**
```python
# Extract base classes
superclasses = class_node.child_by_field_name("superclasses")
base_classes = self._extract_base_classes(superclasses, source_bytes)

return Construct(
    # ... existing fields ...
    base_classes=base_classes,
)
```

---

### Step 3: Update Java Indexer to Extract Base Classes and Imports

**Files:** `/Users/vlad/dev/projects/codesub/src/codesub/semantic/java_indexer.py`

**Changes:**
- Add `_extract_base_classes()` helper method
- Add `extract_imports()` public method using Tree-sitter
- Update `_extract_class()` to populate `base_classes` field
- Update `_extract_enum()` for interface inheritance

**Code for `_extract_base_classes()`:**
```python
def _extract_base_classes(
    self,
    superclass_node: tree_sitter.Node | None,
    interfaces_node: tree_sitter.Node | None,
    source_bytes: bytes,
) -> tuple[str, ...]:
    """Extract base class/interface names from extends/implements.

    Java classes can extend one class and implement multiple interfaces.
    Returns all as a single tuple (extends first, then implements).
    """
    base_names: list[str] = []

    # Handle extends (single class for classes, multiple for interfaces)
    if superclass_node:
        # For class: superclass node is type_identifier directly
        # For interface: could be type_list
        if superclass_node.type in ("type_identifier", "generic_type"):
            text = self._node_text(superclass_node, source_bytes)
            # Extract simple name from generic (List<T> -> List)
            if "<" in text:
                text = text.split("<")[0]
            base_names.append(text)
        elif superclass_node.type == "type_list":
            for type_node in superclass_node.children:
                if type_node.type in ("type_identifier", "generic_type"):
                    text = self._node_text(type_node, source_bytes)
                    if "<" in text:
                        text = text.split("<")[0]
                    base_names.append(text)

    # Handle implements (interface list)
    if interfaces_node:
        for child in interfaces_node.children:
            if child.type in ("type_identifier", "generic_type"):
                text = self._node_text(child, source_bytes)
                if "<" in text:
                    text = text.split("<")[0]
                base_names.append(text)
            elif child.type == "type_list":
                for type_node in child.children:
                    if type_node.type in ("type_identifier", "generic_type"):
                        text = self._node_text(type_node, source_bytes)
                        if "<" in text:
                            text = text.split("<")[0]
                        base_names.append(text)

    return tuple(base_names)
```

**Code for `extract_imports()` using Tree-sitter:**
```python
def extract_imports(self, source: str) -> dict[str, tuple[str, str]]:
    """Extract import mappings from Java source using Tree-sitter.

    Returns dict mapping simple class name to (full_package, simple_name).
    Example: {"User": ("com.example.models.User", "User")}

    Note: Java imports map simple names to fully qualified names.
    The module path is the full import path, which we later resolve to a file.
    """
    tree = self._parser.parse(source.encode())
    source_bytes = source.encode()
    import_map: dict[str, tuple[str, str]] = {}

    for child in tree.root_node.children:
        if child.type == "import_declaration":
            # import com.example.User;
            # import com.example.*;  (wildcard - skip)

            # Check for wildcard
            is_wildcard = any(
                c.type == "asterisk" for c in child.children
            )
            if is_wildcard:
                continue

            # Find the scoped_identifier (full path)
            for part in child.children:
                if part.type == "scoped_identifier":
                    full_path = self._node_text(part, source_bytes)
                    simple_name = full_path.split(".")[-1]
                    import_map[simple_name] = (full_path, simple_name)
                    break
                elif part.type == "identifier":
                    # Single identifier import (rare but possible)
                    name = self._node_text(part, source_bytes)
                    import_map[name] = (name, name)

    return import_map
```

**Update `_extract_class()` and `_extract_enum()`:**
```python
# In _extract_class():
superclass = node.child_by_field_name("superclass")
interfaces = node.child_by_field_name("interfaces")
base_classes = self._extract_base_classes(superclass, interfaces, source_bytes)

constructs.append(
    Construct(
        # ... existing fields ...
        base_classes=base_classes,
    )
)

# In _extract_enum():
interfaces = node.child_by_field_name("interfaces")
base_classes = self._extract_base_classes(None, interfaces, source_bytes)

constructs.append(
    Construct(
        # ... existing fields ...
        base_classes=base_classes,
    )
)
```

---

### Step 4: Create Inheritance Resolution Module

**Files:** `/Users/vlad/dev/projects/codesub/src/codesub/semantic/inheritance.py` (new file)

**Changes:**
- Create `InheritanceResolver` class for cross-file inheritance resolution
- Use Tree-sitter-based import extraction (not regex)
- Build inheritance graph with transitive closure and depth limit

**Code:**
```python
"""Inheritance resolution for cross-file change detection."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .construct import Construct
    from .indexer_protocol import SemanticIndexer

# Safety limit to prevent runaway recursion
MAX_INHERITANCE_DEPTH = 10


@dataclass
class ResolvedClass:
    """A resolved class with its location and base classes."""
    path: str
    qualname: str
    construct: Construct
    # Resolved base class references (path, qualname)
    resolved_bases: list[tuple[str, str]]


class InheritanceResolver:
    """Resolves inheritance relationships across files.

    Given a set of indexed files, builds an inheritance graph and
    provides methods to find ancestor chains for any class.
    """

    def __init__(self, repo_root: Path, language: str):
        self.repo_root = repo_root
        self.language = language
        # Cache: path -> list of Construct
        self._constructs_by_path: dict[str, list[Construct]] = {}
        # Cache: (path, qualname) -> Construct
        self._class_lookup: dict[tuple[str, str], Construct] = {}
        # Cache: path -> dict of import mappings (name -> (module_path, original_name))
        self._import_map: dict[str, dict[str, tuple[str, str]]] = {}
        # Cache: path -> source code (for import resolution)
        self._source_cache: dict[str, str] = {}

    def add_file(
        self,
        path: str,
        constructs: list[Construct],
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
            # Import parsing happens lazily when needed

    def ensure_imports_parsed(self, path: str, indexer: "SemanticIndexer") -> None:
        """Ensure imports are parsed for a file."""
        if path in self._import_map:
            return

        source = self._source_cache.get(path)
        if not source:
            return

        # Use the indexer's Tree-sitter based import extraction
        raw_imports = indexer.extract_imports(source)

        # Resolve module names to file paths
        resolved_imports: dict[str, tuple[str, str]] = {}
        for name, (module, original_name) in raw_imports.items():
            resolved_path = self._resolve_module_path(module, path)
            if resolved_path:
                resolved_imports[name] = (resolved_path, original_name)

        self._import_map[path] = resolved_imports

    def get_inheritance_chain(
        self,
        path: str,
        qualname: str,
        indexer: "SemanticIndexer",
    ) -> list[tuple[str, str, Construct]]:
        """Get full inheritance chain for a class.

        Returns list of (path, qualname, construct) for all ancestors,
        in order from immediate parent to most distant ancestor.
        Handles cross-file inheritance via import resolution.
        """
        chain: list[tuple[str, str, Construct]] = []
        visited: set[tuple[str, str]] = set()

        self._build_chain(path, qualname, chain, visited, indexer, depth=0)
        return chain

    def _build_chain(
        self,
        path: str,
        qualname: str,
        chain: list[tuple[str, str, Construct]],
        visited: set[tuple[str, str]],
        indexer: "SemanticIndexer",
        depth: int,
    ) -> None:
        """Recursively build inheritance chain."""
        if depth >= MAX_INHERITANCE_DEPTH:
            return  # Safety limit to prevent runaway recursion

        construct = self._class_lookup.get((path, qualname))
        if not construct or not construct.base_classes:
            return

        # Ensure imports are parsed for this file
        self.ensure_imports_parsed(path, indexer)

        for base_name in construct.base_classes:
            resolved = self._resolve_base_class(path, base_name)
            if resolved is None:
                continue  # Unresolved (stdlib, third-party, etc.)

            resolved_path, resolved_qualname, resolved_construct = resolved
            key = (resolved_path, resolved_qualname)

            if key in visited:
                continue  # Avoid cycles

            visited.add(key)
            chain.append((resolved_path, resolved_qualname, resolved_construct))

            # Recurse for grandparents
            self._build_chain(resolved_path, resolved_qualname, chain, visited, indexer, depth + 1)

    def _resolve_base_class(
        self,
        from_path: str,
        base_name: str,
    ) -> tuple[str, str, Construct] | None:
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
                key = (module_path, remaining_qualname)
                if key in self._class_lookup:
                    return (module_path, remaining_qualname, self._class_lookup[key])

        # Simple name from import
        if base_name in imports:
            module_path, original_name = imports[base_name]
            key = (module_path, original_name)
            if key in self._class_lookup:
                return (module_path, original_name, self._class_lookup[key])

        return None  # Unresolved (external dependency)

    def _resolve_module_path(self, module: str, from_path: str) -> str | None:
        """Convert module name to file path.

        Args:
            module: Module name (e.g., "models", ".sibling", "..parent.child", "com.example.User")
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
        # For "com.example.models.User", try:
        # 1. com/example/models/User.java (class file)
        # 2. com/example/models.java (might be the module itself)

        candidate = full_import.replace(".", "/") + ".java"
        if (self.repo_root / candidate).exists():
            return candidate

        # Also check common source roots
        for src_root in ["src/main/java/", "src/", ""]:
            full_candidate = src_root + candidate
            if (self.repo_root / full_candidate).exists():
                return full_candidate

        return None  # External or not found
```

---

### Step 5: Update SemanticIndexer Protocol

**Files:** `/Users/vlad/dev/projects/codesub/src/codesub/semantic/indexer_protocol.py`

**Changes:**
- Add `extract_imports()` method to protocol

**Code:**
```python
from typing import Protocol, runtime_checkable

@runtime_checkable
class SemanticIndexer(Protocol):
    """Protocol for language-specific semantic indexers."""

    def index_file(self, source: str, path: str) -> list["Construct"]:
        """Extract all constructs from source code."""
        ...

    def find_construct(
        self, source: str, path: str, qualname: str, kind: str | None = None
    ) -> "Construct | None":
        """Find a specific construct by qualname."""
        ...

    def get_container_members(
        self,
        source: str,
        path: str,
        container_qualname: str,
        include_private: bool = False,
        constructs: list["Construct"] | None = None,
    ) -> list["Construct"]:
        """Get all direct members of a container construct."""
        ...

    def extract_imports(self, source: str) -> dict[str, tuple[str, str]]:
        """Extract import mappings from source.

        Returns dict mapping local name to (module, original_name).
        """
        ...
```

---

### Step 6: Update Semantic Module Exports

**Files:** `/Users/vlad/dev/projects/codesub/src/codesub/semantic/__init__.py`

**Changes:**
- Export `InheritanceResolver` class

**Code:**
```python
from .inheritance import InheritanceResolver

__all__ = [
    # ... existing exports ...
    "InheritanceResolver",
]
```

---

### Step 7: Add Helper Function to Extract Base Member Name

**Files:** `/Users/vlad/dev/projects/codesub/src/codesub/detector.py`

**Changes:**
- Add `_get_member_base_name()` helper to extract member name without parameters

This fixes the BLOCKING issue where Java method qualnames include parameter types.

**Code:**
```python
def _get_member_base_name(qualname: str) -> str:
    """Extract member name without parameters.

    For Java methods, qualnames include params: "process(Order,User)" -> "process"
    For Python methods and fields, returns as-is: "validate" -> "validate"

    This is critical for override detection: child's "process(Order)"
    should match parent's "process(Order,User)" as an override.
    """
    member = qualname.split(".")[-1]
    if "(" in member:
        return member.split("(")[0]
    return member
```

---

### Step 8: Extend Detector for Inheritance-Aware Change Detection

**Files:** `/Users/vlad/dev/projects/codesub/src/codesub/detector.py`

**Changes:**
- Add `_check_inherited_changes()` method as a separate method (not inlined in `_check_semantic`)
- Add `_detect_parent_changes()` method
- Add `_build_inheritance_resolver()` method that indexes imports from subscription file
- Update `_check_semantic()` to call inheritance check after Stage 1/2/3

**Key Design Points:**
1. Extract inheritance checking to a dedicated method for clarity
2. Do NOT mutate existing triggers; create new ones as needed
3. Index files from subscription's imports, not just files in diff
4. Use existing change types (STRUCTURAL/CONTENT) with `source: "inherited"` metadata
5. Support both container and non-container class subscriptions

**Code for `_check_inherited_changes()`:**
```python
def _check_inherited_changes(
    self,
    sub: Subscription,
    current_construct: "Construct",
    inheritance_resolver: "InheritanceResolver",
    base_ref: str,
    target_ref: str | None,
    construct_cache: dict[tuple[str, str], list],
    new_source: str,
    indexer: "SemanticIndexer",
) -> Trigger | None:
    """Check if parent class changes affect this child class subscription.

    Returns a trigger if:
    1. A parent class member changed
    2. The child does NOT override that member

    Works for both container subscriptions (include_members=True) and
    non-container class subscriptions (include_members=False).
    """
    from .semantic import get_indexer

    assert sub.semantic is not None

    # Only applies to class/interface subscriptions
    if sub.semantic.kind not in ("class", "interface", "enum"):
        return None

    # Get inheritance chain
    chain = inheritance_resolver.get_inheritance_chain(
        sub.path, current_construct.qualname, indexer
    )

    if not chain:
        return None  # No parents, or parents not in repo

    # Get child's member names (to check for overrides)
    # Use base names without parameters for override comparison
    child_path = sub.path
    cache_key = (child_path, sub.semantic.language)

    if cache_key in construct_cache:
        child_constructs = construct_cache[cache_key]
    else:
        child_constructs = indexer.index_file(new_source, child_path)
        construct_cache[cache_key] = child_constructs

    # Get child's member BASE names (without parameters for Java)
    child_member_base_names: set[str] = set()
    prefix = current_construct.qualname + "."
    for c in child_constructs:
        if c.qualname.startswith(prefix):
            member_qualname = c.qualname[len(prefix):]
            # Skip nested members' members
            if "." not in member_qualname:
                base_name = _get_member_base_name(member_qualname)
                child_member_base_names.add(base_name)

    # Check each parent in chain
    inherited_changes: list[dict[str, Any]] = []

    for parent_path, parent_qualname, parent_construct in chain:
        # Compare parent at base_ref vs target_ref
        parent_changes = self._detect_parent_changes(
            parent_path, parent_qualname, parent_construct,
            base_ref, target_ref, construct_cache
        )

        for change in parent_changes:
            member_name = change.get("member_name")
            if member_name:
                # Extract base name for override check
                base_name = _get_member_base_name(member_name)
                if base_name in child_member_base_names:
                    # Child overrides this member, skip
                    continue

            # This inherited member changed
            inherited_changes.append({
                **change,
                "parent_path": parent_path,
                "parent_qualname": parent_qualname,
            })

    if not inherited_changes:
        return None

    # Determine overall change type from inherited changes
    has_structural = any(c.get("change_type") == "STRUCTURAL" for c in inherited_changes)
    change_type = "STRUCTURAL" if has_structural else "CONTENT"

    # Build trigger with inheritance metadata
    return Trigger(
        subscription_id=sub.id,
        subscription=sub,
        path=sub.path,
        start_line=sub.start_line,
        end_line=sub.end_line,
        reasons=["inherited_member_changed"],
        matching_hunks=[],
        change_type=change_type,
        details={
            "source": "inherited",
            "inherited_changes": inherited_changes,
            "inheritance_chain": [
                {"path": p, "qualname": q}
                for p, q, _ in chain
            ],
        },
    )
```

**Code for `_detect_parent_changes()`:**
```python
def _detect_parent_changes(
    self,
    parent_path: str,
    parent_qualname: str,
    parent_construct: "Construct",
    base_ref: str,
    target_ref: str | None,
    construct_cache: dict[tuple[str, str], list],
) -> list[dict[str, Any]]:
    """Detect changes in a parent class between refs.

    Returns list of change dicts with member_name, change_type, etc.
    """
    from .errors import UnsupportedLanguageError
    from .semantic import detect_language, get_indexer

    changes: list[dict[str, Any]] = []

    try:
        language = detect_language(parent_path)
        indexer = get_indexer(language)
    except UnsupportedLanguageError:
        return changes

    # Get parent at base_ref
    try:
        base_source = "\n".join(self.repo.show_file(base_ref, parent_path))
        base_constructs = indexer.index_file(base_source, parent_path)
    except Exception:
        return changes  # Parent didn't exist at base_ref

    # Get parent at target_ref
    try:
        if target_ref:
            target_source = "\n".join(self.repo.show_file(target_ref, parent_path))
        else:
            with open(self.repo.root / parent_path, encoding="utf-8") as f:
                target_source = f.read()
        target_constructs = indexer.index_file(target_source, parent_path)
        construct_cache[(parent_path, language)] = target_constructs
    except Exception:
        # Parent deleted or unreadable
        changes.append({
            "member_name": None,
            "change_type": "MISSING",
            "qualname": parent_qualname,
        })
        return changes

    # Build member lookup (using full qualname for comparison, but extracting relative ID)
    prefix = parent_qualname + "."
    base_members = {
        c.qualname[len(prefix):]: c
        for c in base_constructs
        if c.qualname.startswith(prefix) and "." not in c.qualname[len(prefix):]
    }
    target_members = {
        c.qualname[len(prefix):]: c
        for c in target_constructs
        if c.qualname.startswith(prefix) and "." not in c.qualname[len(prefix):]
    }

    # Check for removed members
    for name in base_members:
        if name not in target_members:
            changes.append({
                "member_name": name,
                "change_type": "MISSING",
                "qualname": f"{parent_qualname}.{name}",
            })

    # Check for changed members
    for name, base_c in base_members.items():
        if name not in target_members:
            continue
        target_c = target_members[name]

        if base_c.interface_hash != target_c.interface_hash:
            changes.append({
                "member_name": name,
                "change_type": "STRUCTURAL",
                "qualname": f"{parent_qualname}.{name}",
                "reason": "interface_changed",
            })
        elif base_c.body_hash != target_c.body_hash:
            changes.append({
                "member_name": name,
                "change_type": "CONTENT",
                "qualname": f"{parent_qualname}.{name}",
                "reason": "body_changed",
            })

    # Check parent class itself (inheritance changes, decorators)
    base_parent = next(
        (c for c in base_constructs if c.qualname == parent_qualname),
        None
    )
    target_parent = next(
        (c for c in target_constructs if c.qualname == parent_qualname),
        None
    )

    if base_parent and target_parent:
        if base_parent.interface_hash != target_parent.interface_hash:
            changes.append({
                "member_name": None,
                "change_type": "STRUCTURAL",
                "qualname": parent_qualname,
                "reason": "parent_interface_changed",
            })

    return changes
```

---

### Step 9: Add Helper to Build Inheritance Resolver from Subscription Imports

**Files:** `/Users/vlad/dev/projects/codesub/src/codesub/detector.py`

**Changes:**
- Add `_build_inheritance_resolver()` method
- Index files from subscription's imports (not just files in diff)

**Code:**
```python
def _build_inheritance_resolver(
    self,
    sub: Subscription,
    new_source: str,
    new_path: str,
    target_ref: str | None,
    file_diffs: list[FileDiff],
    construct_cache: dict[tuple[str, str], list],
) -> "InheritanceResolver":
    """Build inheritance resolver by indexing subscription file and its imports.

    This differs from the original plan: instead of only indexing files in the diff,
    we index the subscription file and recursively follow its imports to find
    parent classes that may not be in the diff.
    """
    from .semantic import InheritanceResolver, detect_language, get_indexer
    from .errors import UnsupportedLanguageError

    assert sub.semantic is not None
    language = sub.semantic.language
    indexer = get_indexer(language)

    resolver = InheritanceResolver(self.repo.root, language)

    # Track files we need to index
    files_to_index: set[str] = {new_path}
    indexed_files: set[str] = set()

    # Also include files from diff (they might have changed parents)
    for fd in file_diffs:
        if fd.is_deleted_file:
            continue
        try:
            fd_language = detect_language(fd.new_path)
            if fd_language == language:
                files_to_index.add(fd.new_path)
        except UnsupportedLanguageError:
            continue

    # Iteratively index files and follow imports
    # Limit iterations to prevent infinite loops
    max_iterations = 20
    iteration = 0

    while files_to_index and iteration < max_iterations:
        iteration += 1
        current_batch = list(files_to_index)
        files_to_index = set()

        for path in current_batch:
            if path in indexed_files:
                continue
            indexed_files.add(path)

            # Get source
            cache_key = (path, language)
            if cache_key in construct_cache:
                constructs = construct_cache[cache_key]
                source = self._source_cache.get(path)
            else:
                try:
                    if path == new_path:
                        source = new_source
                    elif target_ref:
                        source = "\n".join(self.repo.show_file(target_ref, path))
                    else:
                        with open(self.repo.root / path, encoding="utf-8") as f:
                            source = f.read()

                    constructs = indexer.index_file(source, path)
                    construct_cache[cache_key] = constructs
                except (FileNotFoundError, PermissionError, UnicodeDecodeError, OSError):
                    continue

            resolver.add_file(path, constructs, source)

            # Parse imports to find more files to index
            if source:
                raw_imports = indexer.extract_imports(source)
                for name, (module, _) in raw_imports.items():
                    resolved_path = resolver._resolve_module_path(module, path)
                    if resolved_path and resolved_path not in indexed_files:
                        files_to_index.add(resolved_path)

    return resolver
```

---

### Step 10: Integrate Inheritance Check into `_check_semantic()`

**Files:** `/Users/vlad/dev/projects/codesub/src/codesub/detector.py`

**Changes:**
- After Stage 1/2/3 finds a construct, call inheritance check
- Create combined trigger if both direct and inherited changes exist

**Integration code (add after Stage 1 finds construct and creates trigger/proposal):**
```python
# In _check_semantic(), after Stage 1 finds new_construct:
# (Insert this code block after the existing trigger/proposal logic in Stage 1)

# Check for inherited changes (only for class-level subscriptions)
if new_construct and sub.semantic.kind in ("class", "interface", "enum"):
    # Build resolver from subscription imports
    resolver = self._build_inheritance_resolver(
        sub, new_source, new_path, target_ref, file_diffs, construct_cache
    )

    inherited_trigger = self._check_inherited_changes(
        sub, new_construct, resolver,
        base_ref, target_ref, construct_cache, new_source, indexer
    )

    if inherited_trigger:
        if trigger:
            # Combine: direct change + inherited change
            # Keep the direct trigger but add inherited info to details
            trigger.details = trigger.details or {}
            trigger.details["inherited_changes"] = inherited_trigger.details.get("inherited_changes", [])
            trigger.details["inheritance_chain"] = inherited_trigger.details.get("inheritance_chain", [])
            if "inherited_member_changed" not in trigger.reasons:
                trigger.reasons.append("inherited_member_changed")
        else:
            trigger = inherited_trigger

# Similar integration needed for Stage 2 and Stage 3 matches
```

**Note:** The same inheritance check pattern should be applied after Stage 2 (hash-based match) and Stage 3 (cross-file match) find their constructs. Extract the logic into a reusable helper to avoid duplication.

---

### Step 11: Update Update Document Serialization

**Files:** `/Users/vlad/dev/projects/codesub/src/codesub/update_doc.py`

**Changes:**
- Verify that `details` dict with nested structures serializes properly
- No code changes expected; the existing `result_to_dict()` should handle it

Review the existing serialization to confirm nested dicts work correctly with the new `inherited_changes` and `inheritance_chain` structures.

---

## Testing Strategy

### Unit Tests for Inheritance Resolution

**File:** `/Users/vlad/dev/projects/codesub/tests/test_inheritance.py` (new)

- [ ] Test `_extract_base_classes()` for Python: simple, multiple, with module prefix
- [ ] Test `_extract_base_classes()` for Java: extends, implements, both, generics
- [ ] Test `extract_imports()` for Python: standard imports, from imports, relative imports, multi-line, aliases
- [ ] Test `extract_imports()` for Java: standard imports, static imports (skip), wildcards (skip)
- [ ] Test `InheritanceResolver.get_inheritance_chain()` for same-file inheritance
- [ ] Test `InheritanceResolver.get_inheritance_chain()` for cross-file inheritance
- [ ] Test `_resolve_module_path()` for Python relative and absolute imports
- [ ] Test `_resolve_java_import()` for Java package paths
- [ ] Test cycle detection in inheritance chain
- [ ] Test depth limit (MAX_INHERITANCE_DEPTH)
- [ ] Test grandparent chain (A extends B, B extends C)

### Unit Tests for Override Detection

**File:** `/Users/vlad/dev/projects/codesub/tests/test_inheritance.py`

- [ ] Test `_get_member_base_name()` for Python methods
- [ ] Test `_get_member_base_name()` for Java methods with params: `process(Order,User)` -> `process`
- [ ] Test `_get_member_base_name()` for fields (no change)

### Integration Tests for Detector

**File:** `/Users/vlad/dev/projects/codesub/tests/test_inheritance_detection.py` (new)

- [ ] Test parent method change triggers child subscription
- [ ] Test parent method change with child override does NOT trigger
- [ ] Test Java overloaded method: child `process(Order)` overrides parent `process(Order,User)` - no trigger
- [ ] Test grandparent method change triggers grandchild
- [ ] Test cross-file parent change triggers child
- [ ] Test parent field change triggers child
- [ ] Test parent structural change (signature) triggers child
- [ ] Test parent deletion triggers child
- [ ] Test multiple inheritance (Python mixins) handles all parents
- [ ] Test Java extends + implements both checked
- [ ] Test no trigger when parent is external (stdlib, third-party)
- [ ] Test change_type is STRUCTURAL or CONTENT (not "INHERITED")
- [ ] Test `details.source == "inherited"` in trigger
- [ ] Test `inherited_changes` details format
- [ ] Test combination: direct change + inherited change (both in trigger)
- [ ] Test Python `@property` body change triggers child
- [ ] Test Python `@property` override prevents parent trigger
- [ ] Test Python `@classmethod` / `@staticmethod` changes

### Test for Non-Container Class Subscriptions

- [ ] Test inheritance detection for class subscription without `include_members`
- [ ] Test inheritance detection for class subscription with `include_members`

### CLI Tests

- [ ] Verify scan output includes inherited change information
- [ ] Verify update document serializes inherited changes correctly

## Edge Cases Considered

1. **Circular inheritance**: Prevented by `visited` set in `_build_chain()`
2. **Diamond inheritance**: Each path visited once, all changes collected
3. **External base classes** (stdlib, third-party): Silently skipped; we only track in-repo classes
4. **Dynamic base classes** (`class Foo(get_base())`): Not supported; we parse static names only
5. **Generic base classes** (`class Foo(List[T])`): Extract "List" as base name (strip generics)
6. **Nested class inheritance** (`class Inner(Outer.Base)`): Supported via dotted name handling
7. **Renamed imports** (`from x import User as U`): Handled by Tree-sitter import parser
8. **Relative imports** (`from . import sibling`): Resolved relative to file path
9. **Missing parent files**: Gracefully skipped; only trigger on resolvable parents
10. **Parent added in diff**: Will be indexed and included in chain
11. **Deep inheritance chains**: Capped at MAX_INHERITANCE_DEPTH (10) levels
12. **Star imports**: Skipped by import parser (cannot resolve)
13. **Multi-line imports**: Handled correctly by Tree-sitter
14. **Overloaded methods (Java)**: Override detection uses base name, not full qualname with params
15. **Properties and descriptors (Python)**: Treated as regular members for override detection

## Risks and Mitigations

- **Risk:** Performance regression for files with many imports
  **Mitigation:** Limit import traversal iterations (max_iterations = 20); use construct_cache

- **Risk:** Import resolution misses complex patterns (dynamic imports, `__import__()`)
  **Mitigation:** Document as unsupported; focus on static imports which cover 95%+ of cases

- **Risk:** Cross-file resolution increases scan complexity
  **Mitigation:** Build resolver lazily; only resolve on-demand during chain building

- **Risk:** Breaking existing tests
  **Mitigation:** Change type remains STRUCTURAL/CONTENT; inheritance info is additive metadata

- **Risk:** Large repos with many files cause slow scans
  **Mitigation:** Only index files reachable from subscription imports, not all repo files

## Rollback Plan

1. Remove `base_classes` field from Construct (default to None maintains backward compat)
2. Remove `extract_imports()` methods from indexers
3. Remove `inheritance.py` module
4. Revert detector.py changes (remove inheritance-related methods)
5. Remove new test files

Since changes are additive and the `base_classes` field defaults to `None`, partial rollback is possible by simply not calling the inheritance check code.

## Future Enhancements (Out of Scope)

1. Cache inheritance graph across scans
2. Support dynamic base classes via runtime analysis
3. Track interface changes separately from implementation inheritance
4. Warn when subscribing to class with complex inheritance
5. CLI flag to show inheritance chain for a class
6. Support `super()` call tracking for deeper change propagation
7. Support abstract method compliance checking for ABCs
