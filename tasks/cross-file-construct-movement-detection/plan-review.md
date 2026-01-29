# Plan Review

## Summary

The revised plan for cross-file construct movement detection is well-structured and addresses the critical issues from the previous review. The approach is sound: after Stage 1 (exact match) and Stage 2 (in-file hash search) fail, Stage 3 searches other files in the git diff for the construct using fingerprint matching. The plan correctly handles the `old_construct` being None in Stage 3 by adding a dedicated `_classify_cross_file_change()` method.

## Issues Found

### Critical Issues

None. The previously identified critical issues have been properly addressed:

1. **old_construct handling**: The new `_classify_cross_file_change()` method (Step 4) correctly uses `sub.semantic` fingerprints directly instead of relying on `old_construct`. The plan explicitly notes this is necessary because Stage 1 exact match failed.

2. **Path filtering**: The `_search_cross_file()` method (Step 3) now accepts both `old_path` and `new_path` parameters and uses `skip_paths = {old_path, new_path}` to filter out both paths correctly.

### Major Issues

None.

### Minor Issues

#### 1. Import placement in `_search_cross_file()`
- **Severity:** Minor
- **Description:** The method has inline imports inside the method body. While this works, it is inconsistent with the rest of the codebase where imports are typically at the top of the file.
- **Suggested Fix:** Move these imports to the top of the file alongside the existing imports.

#### 2. Duplicate handling comment clarity
- **Severity:** Minor
- **Description:** When `trigger_on_duplicate=False` and multiple matches are found, the comment says "User explicitly opted out of duplicate alerts" but the default is False, so most users simply got the default behavior.
- **Suggested Fix:** Change comment to "Default behavior: duplicates are ambiguous, treat as missing"

## Verdict

**PLAN APPROVED**

The plan is complete, correct, and ready for implementation. The critical issues from the previous review have been properly addressed. The minor issues identified are stylistic and do not affect correctness.
