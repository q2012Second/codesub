# Plan Review: Aggregate/Container Tracking (Revision 3)

## Summary

The revised plan addresses all five issues identified in the external review. The critical issues around Stage 2/3 detection, Python indexer emitting class constructs, and relative member ID comparison have been explicitly incorporated into the design decisions and implementation steps. The plan is now ready for implementation.

## Verification of External Review Fixes

### Critical Issue 1: Skip Stage 2/3 breaks move/rename
**Status: FIXED**

The plan now explicitly states in the Design Decisions table (line 26):
> "Container subscriptions use full Stage 1/2/3 detection: Enables move/rename support via hash-based relocation; skipping Stage 2/3 would break cross-file detection and rename tracking"

The Alternative Approaches section (line 47) also confirms:
> "Skip Stage 2/3 for containers: Rejected because it breaks move/rename support"

Step 8 (Extend Detector with Container Logic) shows the implementation handling all three stages:
- Stage 1 success block (line 699-753): Delegates to `_check_container_members()` when `include_members=True`
- Stage 2 success block (line 756-790): Modified to handle containers with member checking
- Stage 3 success block (line 792-838): Modified to handle containers with cross-file member comparison

### Critical Issue 2: Python indexer doesn't emit class constructs
**Status: FIXED**

The plan adds a new Step 3 (lines 132-318): "Extend Python Indexer to Emit Container Constructs"

Key changes specified:
- Modify `_extract_classes()` to emit a `Construct` for the class itself, not just its members
- New `_parse_class_container()` method to create container constructs
- Enum detection via checking for `Enum`, `IntEnum`, `StrEnum` in base classes
- Nested class construct emission

Design Decisions table (line 31):
> "Python indexer must emit container constructs: Required for `find_construct()` to locate the container"

### Critical Issue 3: Container rename breaks member comparison
**Status: FIXED**

The plan now uses relative member IDs for comparison. Design Decisions table (line 30):
> "Compare members by relative ID on rename: When container is renamed (e.g., User to UserAccount), compare members by stripping the container prefix to avoid false 'all removed/added' noise"

Implementation details in Step 8 (`_check_container_members`, lines 581-696):
- `baseline_members` stored by relative ID (e.g., `validate` not `User.validate`)
- `current_by_relative_id` built by stripping container prefix
- Comparison done between relative IDs to avoid false positives on rename

Step 1 (SemanticTarget model, lines 110-113) adds:
```python
# Keys are RELATIVE member IDs (e.g., "validate", not "User.validate")
baseline_members: dict[str, MemberFingerprint] | None = None
# Original container qualname at subscription creation (for rename detection)
baseline_container_qualname: str | None = None
```

### Major Issue 4: Performance - find_construct() re-indexes
**Status: FIXED**

Design Decisions table (line 32):
> "Pass indexed constructs to member checking: Avoid re-indexing the same file twice"

Implementation includes:
- Step 4 (line 330-368): `get_container_members()` accepts optional `constructs` parameter
- Step 5 (line 380-422): Java indexer has same signature with `constructs` parameter
- Step 6 (line 426-448): Protocol updated to include `constructs` parameter
- Step 8 (line 705-708): Caches constructs and passes to member checking

### Minor Issue 5: Container-level changes under-specified
**Status: FIXED**

Design Decisions table (line 33):
> "Track container rename in trigger details: When Stage 2/3 finds a renamed container, set `renamed=True` and track old/new qualnames"

Implementation in `_check_container_members()` (lines 634-643):
```python
# Check for container rename
if current_container_qualname != baseline_container_qualname:
    container_changes["renamed"] = True
    container_changes["old_qualname"] = baseline_container_qualname
    container_changes["new_qualname"] = current_container_qualname
```

## Issues Found

### Critical Issues

None.

### Major Issues

None.

### Minor Issues

#### 1. CLI import statement incomplete
- **Severity:** Minor
- **Description:** In Step 7, the CLI code imports `CONTAINER_KINDS, MemberFingerprint` from models but the shown import statement only shows `CONTAINER_KINDS` in the code snippet header. The external review noted this as well.
- **Suggested Fix:** Ensure the actual implementation includes both imports: `from .models import CONTAINER_KINDS, MemberFingerprint`

#### 2. found_source variable scope in Stage 3 handler
- **Severity:** Minor
- **Description:** In the Stage 3 handler (lines 798-817), the code references `found_source` but this variable is only assigned inside the `else` branch of the cache check. If the file is already cached, `found_source` will be undefined.
- **Suggested Fix:** Either read the source before the cache check or ensure the source is available. Since Stage 3 is called after Stage 1/2 fail, the source should be re-read for the new file regardless.

#### 3. Nested class member handling
- **Severity:** Minor
- **Description:** Step 3 adds nested class construct emission, but the `get_container_members()` method only tracks "direct members (one level deep)" via the `"." in member_name` check. This means nested classes ARE included as members but their internal members are not. This is correct behavior but could benefit from a clarifying comment in the code.
- **Suggested Fix:** Add a code comment in `get_container_members()` explaining that nested classes are treated as direct members but their internal members are not tracked.

#### 4. Test case naming consistency
- **Severity:** Minor
- **Description:** Some test names use "container_renamed" while others use "container_rename". Minor inconsistency.
- **Suggested Fix:** Standardize to "container_rename" (verb form) for consistency.

## Strengths

1. **Comprehensive design decisions table** - All key decisions are documented with rationale and explicitly addresses rejected alternatives, making the design traceable.

2. **Full Stage 1/2/3 support for containers** - The plan correctly leverages existing hash-based relocation infrastructure rather than creating a separate code path.

3. **Relative member ID comparison** - Elegant solution to the container rename problem that avoids false positives without requiring complex normalization logic.

4. **Construct caching strategy** - The `constructs` parameter added to `get_container_members()` prevents double-indexing while maintaining clean API boundaries.

5. **Incremental changes** - The plan extends existing models (`SemanticTarget`) and methods (`_check_semantic`) rather than creating parallel systems, reducing maintenance burden.

6. **Test coverage for rename/move scenarios** - Tests now explicitly cover:
   - `test_container_renamed_same_file`
   - `test_container_renamed_no_false_member_changes`
   - `test_container_moved_cross_file`
   - `test_container_moved_and_renamed`
   - `test_container_hash_relocation_same_file`
   - `test_container_hash_relocation_cross_file`

7. **Updater properly handles rename** - Step 9 updates `baseline_container_qualname` along with `qualname` when applying proposals.

8. **Java member handling documented** - The plan explicitly notes that `include_private` has no effect for Java since Java uses visibility modifiers rather than naming conventions.

## Verdict

**PLAN APPROVED**

The revised plan addresses all critical and major issues from the external review. The remaining minor issues are implementation details that can be handled during development and do not require plan revision. The test strategy now covers the rename/move scenarios that were previously missing. The plan is ready for implementation.
