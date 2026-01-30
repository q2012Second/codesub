# Problem Statement: Python Module-Level Functions Not Indexed

## Task Type
**Type:** feature

## Current State

The Python semantic indexer (`src/codesub/semantic/python_indexer.py`) currently extracts the following constructs from Python source code:

1. **Module-level variables/constants**
   - Example: `API_VERSION = "1.0"`
   - Indexed as `kind="variable"`

2. **Classes**
   - Including decorated classes, enums, and nested classes
   - Indexed as `kind="class"` or `kind="enum"`

3. **Class members**
   - Fields: `User.role`
   - Methods: `User.validate()`
   - Indexed as `kind="field"` or `kind="method"`

**However, module-level functions are NOT being indexed.** The `index_file()` method only processes:
- Module-level assignments
- Classes and their members

When tested on `mock_repos/python/api/routes.py`, which contains 8 module-level functions (`get`, `post`, `create_order`, `get_order`, `list_orders`, `stripe_webhook`, `shipfast_webhook`, `health_check`), the indexer only finds 1 construct: the `router` variable.

This means users **cannot create semantic subscriptions** for standalone functions like:
- `routes.py::create_order`
- `utils.py::calculate_tax`
- `helpers.py::format_date`

## Desired State

Module-level functions (standalone functions not inside a class) should be indexed and discoverable, allowing users to create semantic subscriptions for them.

Users should be able to:
1. Run `codesub symbols api/routes.py` and see all module-level functions listed
2. Create subscriptions like `codesub add api/routes.py::create_order --label "Order creation endpoint"`
3. Track changes to function signatures (parameters, return type annotations) as structural changes
4. Track changes to function bodies as content changes
5. Track decorated functions (e.g., `@post("/api/orders")` decorators)

The indexer should recognize module-level `function_definition` nodes at the root level of the parse tree, similar to how it recognizes `class_definition` nodes.

## Constraints

1. **Maintain existing behavior**: All currently indexed constructs (variables, classes, methods, fields) must continue to work
2. **Follow existing patterns**: Use the same construct kind system and fingerprinting approach
3. **Consistency with Java**: Java indexer does not have module-level functions (Java requires classes), so no cross-language constraint
4. **Kind naming**: Use `kind="function"` for module-level functions vs `kind="method"` for class methods
5. **Decorator handling**: Must include decorators in line range (like decorated methods) and include them in interface_hash
6. **Backward compatibility**: Existing subscriptions and fingerprints must not break

## Acceptance Criteria

- [ ] Module-level function definitions are extracted by `PythonIndexer.index_file()`
- [ ] Functions have `kind="function"` to differentiate from class methods
- [ ] Decorated functions include the decorator lines in their `start_line` to `end_line` range
- [ ] The `definition_line` points to the actual `def` line (not the decorator)
- [ ] Function signatures (parameters, return type) are included in `interface_hash`
- [ ] Function bodies are included in `body_hash`
- [ ] The CLI command `codesub symbols <path>` lists module-level functions
- [ ] The API endpoint `GET /api/projects/{id}/file-symbols?path=<path>` returns module-level functions
- [ ] Users can create semantic subscriptions for module-level functions
- [ ] Existing tests continue to pass
- [ ] New tests cover module-level function indexing

## Affected Areas

### Primary Implementation
- `src/codesub/semantic/python_indexer.py`
  - `index_file()` method needs to extract module-level functions
  - New method needed (e.g., `_parse_function()`) similar to `_parse_method()`

### Data Model
- `src/codesub/semantic/construct.py`
  - `Construct.kind` documentation may need update to document `"function"` kind

### Testing
- `tests/test_semantic.py`
  - Need new tests for module-level function indexing
  - Need tests for decorated module-level functions

### Documentation
- `CLAUDE.md` - Currently lists "Methods" but not standalone functions in Python constructs
- `README.md` - States "Functions and methods" are supported, but this is currently inaccurate
