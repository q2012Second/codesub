# External Chat Instructions

## Files Prepared
- `chat-context.txt` - Source code context (7 files, 4024 lines, 145KB)
- `chat-prompt.md` - The prompt to paste

## How to Use

1. Open Claude.ai or ChatGPT
2. Copy the entire contents of `chat-prompt.md` below and paste as your message
3. Attach `chat-context.txt` as a file
4. Send and get the response
5. Save the response to `tasks/inheritance-change-detection/external-review.md`

---

# PROMPT BEGINS BELOW - COPY EVERYTHING FROM HERE TO THE END

---

# Plan Review Request

## Context
I'm implementing inheritance-aware change detection for a code subscription tool (codesub). The tool tracks code constructs using semantic analysis (via Tree-sitter) and detects when subscribed code changes.

The tool supports:
- Tracking semantic code constructs (classes, methods, fields, etc.) in Python and Java
- Line-based subscriptions with git diff tracking
- Multi-project management with centralized data storage
- Change detection via fingerprinting (interface_hash for signatures, body_hash for implementations)

## The Problem
Currently, if I subscribe to a child class and the parent class changes, the subscription doesn't trigger. This misses breaking changes that propagate through inheritance hierarchies, especially in cross-file scenarios.

## The Implementation Plan

Below is the full implementation plan. I need you to review it critically and identify potential issues.

---

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
| Check for method overrides by base member name (not full qualname) | **FIX**: Java qualnames include params like `process(Order,User)`. Extract base name `process` for override comparison to handle overloaded methods correctly |
| Automatic for all semantic subscriptions | User requirement: no opt-in flags needed |
| Cross-file from the start | User requirement: parent/child can be in different files |
| Support full inheritance chain | User requirement: grandparents, great-grandparents, etc. |
| Use Tree-sitter for import parsing | **FIX**: Regex-based import parsing is fragile (fails on multi-line, star imports, docstrings). Tree-sitter is already set up and handles all edge cases |
| Index files from subscription imports, not just diff | **FIX**: Parents may not be in the diff. Parse imports from subscription file and index those files to find parent classes |
| Add depth limit for inheritance traversal | **FIX**: Safety valve to prevent runaway recursion in pathological cases |
| Use existing change types with "source": "inherited" metadata | **FIX**: Maintains consistency - a change is STRUCTURAL or CONTENT, with inheritance context as metadata |
| Support both container and non-container class subscriptions | **FIX**: Inheritance detection should work for both modes with appropriate branching logic |

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

The module provides:
- `InheritanceResolver` class with methods for building inheritance chains
- Import resolution for both Python (relative/absolute) and Java (package paths)
- Safety limits (MAX_INHERITANCE_DEPTH = 10) to prevent runaway recursion

---

### Step 5: Update SemanticIndexer Protocol

**Files:** `/Users/vlad/dev/projects/codesub/src/codesub/semantic/indexer_protocol.py`

**Changes:**
- Add `extract_imports()` method to protocol

**Code:**
```python
def extract_imports(self, source: str) -> dict[str, tuple[str, str]]:
    """Extract import mappings from source.

    Returns dict mapping local name to (module, original_name).
    """
    ...
```

---

### Step 6: Add Helper Function to Extract Base Member Name

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

### Step 7: Extend Detector for Inheritance-Aware Change Detection

**Files:** `/Users/vlad/dev/projects/codesub/src/codesub/detector.py`

**Changes:**
- Add `_check_inherited_changes()` method
- Add `_detect_parent_changes()` method
- Add `_build_inheritance_resolver()` method that indexes imports from subscription file
- Update `_check_semantic()` to call inheritance check after Stage 1/2/3

**Key Design Points:**
1. Extract inheritance checking to a dedicated method for clarity
2. Do NOT mutate existing triggers; create new ones as needed
3. Index files from subscription's imports, not just files in diff
4. Use existing change types (STRUCTURAL/CONTENT) with `source: "inherited"` metadata
5. Support both container and non-container class subscriptions

The inheritance check works as follows:
1. Build an `InheritanceResolver` by indexing the subscription file and recursively following imports
2. For class/interface subscriptions, get the full inheritance chain
3. For each parent in the chain, detect what changed between refs
4. Filter out changes where the child overrides the member (using base name comparison)
5. Create a trigger with inherited change details

---

## Testing Strategy

### Unit Tests for Inheritance Resolution

**File:** `/Users/vlad/dev/projects/codesub/tests/test_inheritance.py` (new)

- Test `_extract_base_classes()` for Python: simple, multiple, with module prefix
- Test `_extract_base_classes()` for Java: extends, implements, both, generics
- Test `extract_imports()` for Python: standard imports, from imports, relative imports, multi-line, aliases
- Test `extract_imports()` for Java: standard imports, static imports (skip), wildcards (skip)
- Test `InheritanceResolver.get_inheritance_chain()` for same-file inheritance
- Test `InheritanceResolver.get_inheritance_chain()` for cross-file inheritance
- Test `_resolve_module_path()` for Python relative and absolute imports
- Test `_resolve_java_import()` for Java package paths
- Test cycle detection in inheritance chain
- Test depth limit (MAX_INHERITANCE_DEPTH)
- Test grandparent chain (A extends B, B extends C)

### Unit Tests for Override Detection

**File:** `/Users/vlad/dev/projects/codesub/tests/test_inheritance.py`

- Test `_get_member_base_name()` for Python methods
- Test `_get_member_base_name()` for Java methods with params: `process(Order,User)` -> `process`
- Test `_get_member_base_name()` for fields (no change)

### Integration Tests for Detector

**File:** `/Users/vlad/dev/projects/codesub/tests/test_inheritance_detection.py` (new)

- Test parent method change triggers child subscription
- Test parent method change with child override does NOT trigger
- Test Java overloaded method: child `process(Order)` overrides parent `process(Order,User)` - no trigger
- Test grandparent method change triggers grandchild
- Test cross-file parent change triggers child
- Test parent field change triggers child
- Test parent structural change (signature) triggers child
- Test parent deletion triggers child
- Test multiple inheritance (Python mixins) handles all parents
- Test Java extends + implements both checked
- Test no trigger when parent is external (stdlib, third-party)
- Test change_type is STRUCTURAL or CONTENT (not "INHERITED")
- Test `details.source == "inherited"` in trigger
- Test `inherited_changes` details format
- Test combination: direct change + inherited change (both in trigger)
- Test Python `@property` body change triggers child
- Test Python `@property` override prevents parent trigger
- Test Python `@classmethod` / `@staticmethod` changes

### Test for Non-Container Class Subscriptions

- Test inheritance detection for class subscription without `include_members`
- Test inheritance detection for class subscription with `include_members`

### CLI Tests

- Verify scan output includes inherited change information
- Verify update document serializes inherited changes correctly

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

---

## Your Task

Please review this implementation plan and identify:

1. **Technical Issues**: Bugs, edge cases not handled, architectural problems
2. **Missing Pieces**: Functionality that should be addressed but isn't
3. **Improvements**: Better approaches, optimizations, or simplifications
4. **Risk Assessment**: Potential issues during implementation or maintenance

Focus especially on:
- The override detection logic using `_get_member_base_name()` for Java overloaded methods
- The import resolution approach for cross-file inheritance (Tree-sitter based)
- The integration point in the detector (`_check_semantic()`)
- The approach of indexing subscription imports rather than only diff files
- Test coverage completeness
- Edge cases that might cause problems

**Be critical.** I want to find problems before implementation, not after.

## Codebase Context

The attached file `chat-context.txt` contains the relevant source code, including:

1. `src/codesub/semantic/construct.py` - Construct dataclass being extended
2. `src/codesub/semantic/python_indexer.py` - Python indexer being modified
3. `src/codesub/semantic/java_indexer.py` - Java indexer being modified
4. `src/codesub/detector.py` - Main detection logic being extended
5. `src/codesub/semantic/indexer_protocol.py` - Protocol being updated
6. `src/codesub/models.py` - Data models
7. `tests/test_container_tracking.py` - Test patterns for container tracking

**Important:** Review the actual code in `chat-context.txt` to understand the existing patterns, then critique the plan against what's actually there.
