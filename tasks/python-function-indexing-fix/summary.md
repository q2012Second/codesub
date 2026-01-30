# Summary: Python Module-Level Function Indexing

## Problem
Python module-level functions (standalone functions not inside classes) were not being indexed by the semantic indexer, preventing users from creating semantic subscriptions for them.

## Solution
Added support for indexing module-level functions with a new `"function"` kind.

## Changes Made

### Core Implementation
- **`src/codesub/semantic/python_indexer.py`**
  - Added `_extract_module_functions()` method to find function definitions at module level
  - Refactored `_parse_method()` and new `_parse_function()` into unified `_parse_callable()` method
  - Functions are extracted between module assignments and classes

### Supporting Changes
- **`src/codesub/utils.py`** - Added "function" to valid kinds for target parsing
- **`src/codesub/semantic/construct.py`** - Updated docstring to document "function" kind
- **`src/codesub/cli.py`** - Added "function" to `--kind` filter choices

### Tests
- **`tests/test_semantic.py`** - Added 6 new tests:
  - `test_module_function` - Basic function indexing
  - `test_module_function_decorated` - Decorated functions
  - `test_module_function_fingerprints` - Signature vs body changes
  - `test_module_function_async` - Async functions
  - `test_find_construct_function_by_qualname` - Finding by name
  - `test_find_construct_function_with_kind_filter` - Kind disambiguation

- **`tests/test_api_code_browser.py`** - Updated to expect `helper_function` in symbols

## Usage Examples

```bash
# List all symbols including functions
codesub symbols api/routes.py

# Filter to functions only
codesub symbols api/routes.py --kind function

# Create a semantic subscription for a function
codesub add api/routes.py::create_order --label "Order creation endpoint"

# With kind disambiguation
codesub add api/routes.py::function:helper --label "Helper function"
```

## Test Results
- All 311 tests pass
- 6 new tests added for function indexing
