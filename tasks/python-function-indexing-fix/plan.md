# Implementation Plan: Add Python Module-Level Function Indexing

## Overview
The Python semantic indexer (`src/codesub/semantic/python_indexer.py`) currently extracts module-level variables/constants and class members (fields, methods), but does not index standalone module-level functions. This plan adds support for indexing module-level functions with a new `"function"` kind.

## Design Decisions

| Decision | Rationale |
|----------|-----------|
| Use `"function"` as the kind (not reuse `"method"`) | Functions and methods have different semantics: methods belong to a class, functions do not. Using a distinct kind allows filtering by kind in the API and CLI. Functions and methods with identical signatures will have different interface hashes because kind is part of the hash. |
| Create `_extract_module_functions()` method | Follow existing pattern of `_extract_module_assignments()` and `_extract_classes()` for consistency. |
| Create `_parse_function()` method | While similar to `_parse_method()`, keeping them separate avoids conditional logic and keeps code clear. Functions have no parent class, so `qualname` is just the function name. |
| Include decorators in line range | Match existing behavior for decorated methods where `start_line` includes the decorator but `definition_line` points to the `def` keyword. |

## Prerequisites
- Familiarity with Tree-sitter node types for Python (`function_definition`, `decorated_definition`)
- Understanding of the existing `_parse_method()` and `_extract_classes()` patterns

## Implementation Steps

### Step 1: Add "function" to valid kinds in utils.py
**Files:** `src/codesub/utils.py`
**Changes:**
- Update the valid kinds list on line 55 to include `"function"`

```python
# Line 55 - change from:
if maybe_kind in ("variable", "field", "method", "class", "interface", "enum"):
# To:
if maybe_kind in ("variable", "field", "method", "class", "interface", "enum", "function"):
```

### Step 2: Update Construct docstring and inline comment
**Files:** `src/codesub/semantic/construct.py`
**Changes:**
- Add `"function"` to the kind docstring
- Update the inline comment on line 44 to include `"function"`
- Update the qualname example to show function format

```python
# Update the kind docstring (around line 18-25):
"""
Attributes:
    path: File path where the construct is defined.
    kind: Type of construct. Valid values:
        - "variable": Module-level variable
        - "field": Class field or attribute
        - "method": Method or function within a class
        - "function": Module-level function (not inside a class)
        - "class": Class declaration
        - "interface": Interface declaration (Java)
        - "enum": Enum declaration
    qualname: Qualified name of the construct.
        - Simple: "MAX_RETRIES", "User", "create_order"
        - Nested: "User.role", "Calculator.add(int,int)"
        - Java overloads include param types: "add(int,int)"
"""

# Update line 44 - change from:
kind: str  # "variable"|"field"|"method"|"class"|"interface"|"enum"
# To:
kind: str  # "variable"|"field"|"method"|"function"|"class"|"interface"|"enum"
```

### Step 3: Add _parse_function() method to PythonIndexer
**Files:** `src/codesub/semantic/python_indexer.py`
**Changes:**
- Add new `_parse_function()` method after `_parse_method()`

```python
def _parse_function(
    self,
    node: tree_sitter.Node,
    source_bytes: bytes,
    path: str,
    has_errors: bool,
    decorated_node: tree_sitter.Node | None = None,
) -> Construct | None:
    """Parse module-level function definition."""
    name = self._get_name(node)
    if not name:
        return None

    qualname = name  # No class prefix for module-level functions

    # Get decorators
    decorators: list[str] = []
    if decorated_node:
        for child in decorated_node.children:
            if child.type == "decorator":
                decorators.append(self._node_text(child, source_bytes))

    # Get parameters for interface_hash
    params_node = node.child_by_field_name("parameters")
    return_type = node.child_by_field_name("return_type")

    interface_hash = compute_interface_hash(
        "function",
        annotation=self._node_text(return_type, source_bytes) if return_type else None,
        decorators=decorators,
        params_node=params_node,
        source_bytes=source_bytes,
    )

    # Get body for body_hash
    body_node = node.child_by_field_name("body")
    body_hash = compute_body_hash(body_node, source_bytes) if body_node else ""

    use_node = decorated_node or node
    return Construct(
        path=path,
        kind="function",
        qualname=qualname,
        role=None,
        start_line=use_node.start_point[0] + 1,
        end_line=use_node.end_point[0] + 1,
        definition_line=node.start_point[0] + 1,  # Actual def line, not decorator
        interface_hash=interface_hash,
        body_hash=body_hash,
        has_parse_error=has_errors,
    )
```

### Step 4: Add _extract_module_functions() method to PythonIndexer
**Files:** `src/codesub/semantic/python_indexer.py`
**Changes:**
- Add new `_extract_module_functions()` method after `_extract_module_assignments()`

```python
def _extract_module_functions(
    self,
    root: tree_sitter.Node,
    source_bytes: bytes,
    path: str,
    has_errors: bool,
) -> list[Construct]:
    """Extract module-level function definitions."""
    constructs: list[Construct] = []

    for child in root.children:
        func_node = None
        decorated_node = None

        if child.type == "function_definition":
            func_node = child
        elif child.type == "decorated_definition":
            # Find the function_definition inside the decorated_definition
            for inner in child.children:
                if inner.type == "function_definition":
                    func_node = inner
                    decorated_node = child
                    break

        if func_node is not None:
            construct = self._parse_function(
                func_node, source_bytes, path, has_errors, decorated_node
            )
            if construct:
                constructs.append(construct)

    return constructs
```

### Step 5: Call _extract_module_functions() in index_file()
**Files:** `src/codesub/semantic/python_indexer.py`
**Changes:**
- Add call to `_extract_module_functions()` in `index_file()` method after assignments, before classes

```python
def index_file(self, source: str, path: str) -> list[Construct]:
    """Extract all constructs from source code."""
    tree = self._parser.parse(source.encode())
    has_errors = self._has_errors(tree.root_node)
    constructs: list[Construct] = []

    source_bytes = source.encode()

    # Extract module-level assignments (variables/constants)
    constructs.extend(
        self._extract_module_assignments(tree.root_node, source_bytes, path, has_errors)
    )

    # Extract module-level functions
    constructs.extend(
        self._extract_module_functions(tree.root_node, source_bytes, path, has_errors)
    )

    # Extract classes with their fields and methods
    constructs.extend(
        self._extract_classes(tree.root_node, source_bytes, path, has_errors)
    )

    return constructs
```

## Testing Strategy

### Unit Tests to Add (in test_semantic.py)

```python
def test_module_function(self):
    """Plain module-level function is indexed with kind='function'."""
    indexer = PythonIndexer()
    source = """
def create_order(user_id: int) -> dict:
    return {"user_id": user_id}
"""
    constructs = indexer.index_file(source, "test.py")

    assert len(constructs) == 1
    c = constructs[0]
    assert c.kind == "function"
    assert c.qualname == "create_order"
    assert c.start_line == 2
    assert c.end_line == 3

def test_module_function_decorated(self):
    """Decorated function includes decorator in line range."""
    indexer = PythonIndexer()
    source = """
@cache
@validate
def process_data(data: list) -> list:
    return data
"""
    constructs = indexer.index_file(source, "test.py")

    assert len(constructs) == 1
    c = constructs[0]
    assert c.kind == "function"
    assert c.qualname == "process_data"
    assert c.start_line == 2  # Decorator line
    assert c.definition_line == 4  # Actual def line
    assert c.end_line == 5

def test_module_function_fingerprints(self):
    """Changing function body changes body_hash, signature stays same."""
    indexer = PythonIndexer()
    source1 = """
def greet(name: str) -> str:
    return f"Hello, {name}"
"""
    source2 = """
def greet(name: str) -> str:
    return f"Hi, {name}"
"""
    c1 = indexer.index_file(source1, "test.py")[0]
    c2 = indexer.index_file(source2, "test.py")[0]

    assert c1.interface_hash == c2.interface_hash  # Same signature
    assert c1.body_hash != c2.body_hash  # Different body

def test_module_function_async(self):
    """Async module-level function is indexed with kind='function'."""
    indexer = PythonIndexer()
    source = """
async def fetch_data(url: str) -> dict:
    return {}
"""
    constructs = indexer.index_file(source, "test.py")

    assert len(constructs) == 1
    c = constructs[0]
    assert c.kind == "function"
    assert c.qualname == "fetch_data"

def test_find_construct_function_by_qualname(self):
    """find_construct() locates module-level function by qualname."""
    indexer = PythonIndexer()
    source = """
def helper():
    pass
"""
    c = indexer.find_construct(source, "test.py", "helper")
    assert c is not None
    assert c.kind == "function"

def test_find_construct_function_with_kind_filter(self):
    """find_construct() locates function when kind='function' is specified."""
    indexer = PythonIndexer()
    source = """
helper = "value"

def helper():
    pass
"""
    # Without kind filter, ambiguous (returns None since multiple matches)
    c = indexer.find_construct(source, "test.py", "helper")
    assert c is None

    # With kind filter, finds the function
    c = indexer.find_construct(source, "test.py", "helper", kind="function")
    assert c is not None
    assert c.kind == "function"
```

### API Test Update (in test_api_code_browser.py)
Update `test_get_symbols_python` to include `helper_function`:

```python
# Current (line 222-225):
qualnames = [c["qualname"] for c in data["constructs"]]
assert "API_VERSION" in qualnames
assert "User.__init__" in qualnames
assert "User.greet" in qualnames

# Updated:
qualnames = [c["qualname"] for c in data["constructs"]]
assert "API_VERSION" in qualnames
assert "User.__init__" in qualnames
assert "User.greet" in qualnames
assert "helper_function" in qualnames  # Module-level function
```

## Edge Cases Considered
- **Decorated functions**: `start_line` includes decorator, `definition_line` is the `def` line
- **Functions with no body (syntax error)**: Returns empty `body_hash`
- **Functions with same name as variables**: Both indexed; user can use `kind` filter
- **Nested functions (functions inside functions)**: Not indexed (top-level only)
- **Async functions**: Tree-sitter uses `function_definition` for async too (async is a modifier)
- **Lambda assignments**: Handled as variables (via `_extract_module_assignments()`), not functions

## Risks and Mitigations
- **Risk:** Breaking existing behavior for methods
  **Mitigation:** Methods remain unchanged; adding new code paths only. Existing tests catch regressions.
