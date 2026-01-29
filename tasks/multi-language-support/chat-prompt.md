# Task: Multi-Language Support for Codesub Semantic Indexing

## Problem Statement

Codesub is a CLI tool that tracks code subscriptions - detecting changes to specific code constructs across git commits. Currently, semantic subscriptions (tracking code constructs by identity rather than line numbers) only support Python. The goal is to extend this to support multiple programming languages, starting with Java.

## Current State

- **Single language**: Only Python is supported via `PythonIndexer` class
- **Hardcoded references**: `PythonIndexer` is directly instantiated in 4 locations:
  - `detector.py:297` - during change detection
  - `cli.py:143` - when adding semantic subscriptions
  - `cli.py:475` - in the `symbols` command
  - `api.py:304` - when creating subscriptions via API
- **Language field exists but unused**: `SemanticTarget.language` is always set to `"python"`
- **Good foundation**: The `Construct` dataclass and `fingerprint.py` are already language-agnostic
- **Tree-sitter based**: Uses tree-sitter for parsing (supports 40+ languages)

## Desired State

- **Multi-language architecture**: Protocol-based abstraction with registry/factory pattern
- **Java support**: Full support for Java semantic subscriptions (classes, interfaces, enums, methods, fields)
- **Auto-detection**: Language automatically detected from file extension
- **Backward compatible**: Existing Python subscriptions continue to work unchanged
- **Extensible**: Easy to add more languages (TypeScript, Go, etc.) in the future

## Constraints

- Follow existing patterns in the codebase (especially match `PythonIndexer` structure)
- Use tree-sitter for all parsing (add `tree-sitter-java` dependency)
- Keep the existing `Construct` dataclass unchanged
- Reuse existing fingerprinting logic in `fingerprint.py`
- Maintain full backward compatibility with existing Python subscriptions
- Handle unsupported languages gracefully with clear error messages

## Codebase Context

The attached file `chat-context.txt` contains the relevant source code.

Key files included:

1. `src/codesub/semantic/python_indexer.py` - **Primary template** for new indexers; contains `Construct` dataclass and `PythonIndexer` class
2. `src/codesub/semantic/fingerprint.py` - Hash computation (interface_hash, body_hash); needs minor update for Java parameter types
3. `src/codesub/semantic/__init__.py` - Module exports; needs to expose new registry functions
4. `src/codesub/detector.py` - Change detection logic; uses indexer at line ~297
5. `src/codesub/cli.py` - CLI commands; uses indexer at lines ~143 and ~475
6. `src/codesub/api.py` - FastAPI endpoints; uses indexer at line ~304
7. `src/codesub/models.py` - Data models including `SemanticTarget` with `language` field
8. `src/codesub/utils.py` - Target parsing utilities
9. `src/codesub/errors.py` - Custom exceptions; needs new `UnsupportedLanguageError`
10. `tests/test_semantic.py` - Semantic tests; template for Java tests
11. `tests/test_semantic_detector.py` - Integration tests for change detection
12. `pyproject.toml` - Dependencies; needs `tree-sitter-java`

## Your Task

Create a detailed, step-by-step implementation plan that:

1. **Follows existing patterns** - Match the `PythonIndexer` coding style and architecture
2. **Is specific** - Include exact file paths, function names, and code snippets
3. **Handles edge cases** - Consider parse errors, nested classes, overloaded methods
4. **Includes testing** - Define comprehensive test cases for Java support

## Expected Output Format

```markdown
# Implementation Plan: Multi-Language Semantic Indexing

## Overview
[Brief description of the approach]

## Prerequisites
- [Any setup needed]

## Implementation Steps

### Step 1: [Title]
**File:** `path/to/file.py`
**Changes:**
- [Specific change with code snippet]

### Step 2: [Title]
...

## Testing Strategy
- [ ] [Test case 1]
- [ ] [Test case 2]

## Edge Cases
- [Edge case]: [How it's handled]

## Risks & Mitigations
- **Risk:** [Description]
  **Mitigation:** [Solution]
```

## Additional Considerations

1. **Java construct mapping to existing kinds**:
   - `"variable"` - not used in Java (no top-level variables)
   - `"field"` - class fields, interface constants, enum constants
   - `"method"` - methods and constructors

2. **Java-specific features to handle**:
   - Nested/inner classes (`Outer.Inner.method`)
   - Multiple fields per declaration (`int x, y, z;`)
   - Annotations (`@Override`, `@Deprecated`)
   - Access modifiers (should they affect interface_hash?)
   - Generics (`List<String>`)
   - Constructors (use `ClassName.ClassName` as qualname?)

3. **Tree-sitter Java node types** (reference):
   - `class_declaration`, `interface_declaration`, `enum_declaration`
   - `field_declaration`, `method_declaration`, `constructor_declaration`
   - `formal_parameter`, `spread_parameter`
   - `annotation`, `marker_annotation`
