# Code Simplification Review

## Summary
Found and applied 1 significant simplification: unified `_parse_method()` and `_parse_function()` into a single `_parse_callable()` method.

## Changes Applied

### Unified callable parsing method
- **Before**: Two nearly identical methods (~40 lines each) with only 2 lines of difference
- **After**: Single `_parse_callable()` method with optional `class_name` parameter
- **Benefit**: Eliminated ~40 lines of duplicate code, single place to maintain parsing logic

### Minor improvement: List comprehension for decorators
Applied list comprehension instead of for-loop with append for cleaner code.

## Result
All 311 tests pass after refactoring.
