# Code Simplification Review

## Summary

The semantic subscriptions feature is **well-structured overall**. Found 2 issues that were fixed:

## Fixed Issues

### 1. Improved type hints in detector.py
- **Before:** Used `Any` type for `Construct` parameters
- **After:** Added proper `TYPE_CHECKING` import and typed `Construct`
- **Benefit:** Better IDE autocomplete and type checking

### 2. Fixed `const` kind inconsistency
- **Before:** `parse_target_spec()` accepted `"const"` as a kind
- **After:** Removed `"const"` from valid kinds (it's a role, not a kind)
- **Benefit:** Prevents user confusion; constants are `kind="variable", role="const"`

## Acceptable Patterns Kept

1. **Lazy imports for PythonIndexer** - Correct pattern to avoid load-time tree-sitter dependency
2. **Explicit hash-matching logic** - Three separate comprehensions are clearer than parameterized helper
3. **Intermediate `fqn` variable** - Aids readability

## Verdict: **CLEAN**

After fixes, the code is clean and ready for code review.
