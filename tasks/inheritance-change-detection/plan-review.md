# Plan Review: Inheritance-Aware Change Detection (Revision 2)

## Verdict: APPROVED

## Summary

The revised plan addresses all previously identified issues effectively. The blocking override detection issue is now fixed with a dedicated `_get_member_base_name()` helper. Major issues around import parsing (now using Tree-sitter), integration structure (indexing from subscription imports), and scope clarification (supporting both container and non-container modes) are all resolved. The plan is ready for implementation.

## Previous Issues Status

| Issue | Status | Notes |
|-------|--------|-------|
| BLOCKING: Override Detection for Overloaded Methods | RESOLVED | Plan now includes `_get_member_base_name()` helper at Step 7 that extracts base name without parameters. Used consistently in `_check_inherited_changes()` for both parent and child member comparisons. |
| MAJOR: Integration Point Structure | RESOLVED | Plan now builds resolver by indexing files from subscription imports (Step 9, `_build_inheritance_resolver()`), not just diff files. The integration code (Step 10) creates a new trigger rather than mutating existing ones - though the merge logic still appends to `trigger.details`, this is acceptable since it happens before returning the trigger. |
| MAJOR: Import Parsing Regex is Fragile | RESOLVED | Plan now specifies Tree-sitter-based `extract_imports()` methods for both Python (Step 2) and Java (Step 3). The implementation handles multi-line imports, aliases, relative imports, and explicitly skips star imports. |
| MAJOR: Container vs Non-Container Scope | RESOLVED | Plan explicitly states "Support both container and non-container class subscriptions" in design decisions table. The `_check_inherited_changes()` code handles both modes appropriately. |
| MINOR: Java Import Resolution | RESOLVED | Step 3 includes `extract_imports()` for Java using Tree-sitter, and `_resolve_java_import()` in Step 4 handles package-to-file mapping with common source roots. |
| MINOR: Change Type Naming | RESOLVED | Plan now uses existing change types (STRUCTURAL/CONTENT) with `source: "inherited"` in the details dict, maintaining semantic consistency. |
| MINOR: Depth Limit for Inheritance Traversal | RESOLVED | Step 4 includes `MAX_INHERITANCE_DEPTH = 10` constant and depth tracking in `_build_chain()`. |
| MINOR: Test Cases for Properties/Descriptors | RESOLVED | Testing strategy now includes specific tests for `@property`, `@classmethod`, and `@staticmethod` (lines 1156-1159 in plan). |

## New Issues

None identified. The revisions are clean and do not introduce new problems.

## Remaining Concerns (Minor - Can Be Addressed During Implementation)

### 1. Source Cache Initialization in Detector

The plan references `self._source_cache` in `_build_inheritance_resolver()` (line 1024) but this field is not shown as being added to the `Detector` class. During implementation, ensure this cache is initialized in `__init__()` or stored appropriately.

### 2. Found Source Variable Scope

In Step 10, the integration code references `found_source` for Stage 3 matches, but this variable is only set inside the `if sub.semantic.include_members` block in the current detector code. Ensure the source is available when calling `_check_inherited_changes()` for Stage 3 matches.

### 3. Protocol Update Ordering

The plan updates `SemanticIndexer` protocol (Step 5) after adding `extract_imports()` to both indexers (Steps 2-3). This works but during implementation, consider updating the protocol first to establish the contract.

### 4. Error Handling in Import Resolution

The `_resolve_module_path()` methods check file existence with `(self.repo_root / path).exists()`. This may raise permission errors on some filesystems. Consider wrapping in try/except.

## Strengths of the Revised Plan

1. **Clear helper extraction**: The `_get_member_base_name()` function is well-documented with examples showing Java qualname handling.

2. **Robust import parsing**: Tree-sitter-based parsing handles edge cases (multi-line, aliases, relative imports) correctly. The explicit skip of star imports is the right choice.

3. **Iterative file indexing**: The `_build_inheritance_resolver()` method follows imports iteratively with a sensible iteration limit (20), avoiding both incomplete resolution and runaway loops.

4. **Consistent metadata structure**: Using `details.source = "inherited"` with existing change types is cleaner than a separate change type enum.

5. **Comprehensive test coverage**: The testing strategy now covers all major scenarios including properties, overloaded methods, and combined direct+inherited changes.

6. **Clean rollback path**: The rollback plan correctly identifies all touchpoints and notes that partial rollback is possible due to additive changes.

## Final Recommendation

**Proceed with implementation.** The plan is thorough, addresses all previous concerns, and provides sufficient detail for each step. The remaining concerns are minor implementation details that can be resolved during development.

Suggested implementation order:
1. Steps 1-3: Extend Construct and indexers (independent, can be tested in isolation)
2. Steps 4-6: Create inheritance module and update exports
3. Steps 7-10: Detector integration (requires previous steps)
4. Step 11: Verify serialization (likely no changes needed)
5. Write tests alongside each step
