# Task: Review Cross-File Construct Movement Detection Plan

## Problem Statement

The codesub tool tracks code subscriptions and detects changes via git diff. For semantic subscriptions (tracking code constructs by identity using Tree-sitter parsing), when a construct is moved to a **different file** (not just renamed within the same file), the system currently marks it as "MISSING" because the hash-based search only looks in the same/renamed file.

**Goal:** Add a Stage 3 to the detection logic that searches across other files in the git diff to find relocated constructs.

## Current State

The `_check_semantic()` method in `detector.py` uses a two-stage detection strategy:

- **Stage 1:** Exact qualname match in the same/renamed file
- **Stage 2:** Hash-based search within the same file (for in-file renames)
- **Missing:** If both fail, construct is marked as "MISSING"

## Desired State

After Stage 2 fails, add **Stage 3: Cross-file search**:
1. Search other files in the git diff for the construct using fingerprint matching
2. Respect language boundaries (Python → Python only)
3. Generate a proposal with the new file path when found
4. Handle duplicates (configurable per-subscription, default: no trigger)

## Constraints

- **Diff-scoped search only** - Only search files in the current git diff, NOT the entire codebase
- **New trigger reason:** `moved_cross_file` (distinct from `renamed`)
- **Duplication handling:** Configurable per-subscription (`trigger_on_duplicate` field, default: false)
- **Backward compatibility:** Must not break existing same-file detection

## Codebase Context

The attached file `chat-context.txt` contains the relevant source code (~26k tokens).

Key files included:
1. `src/codesub/detector.py` - Main detection engine with `_check_semantic()` and `_find_by_hash()`
2. `src/codesub/models.py` - Subscription, Trigger, Proposal dataclasses
3. `src/codesub/diff_parser.py` - FileDiff parsing
4. `src/codesub/git_repo.py` - Git operations (show_file, diff_patch)
5. `src/codesub/semantic/registry.py` - Language detection via `detect_language()`
6. `src/codesub/semantic/construct.py` - Construct dataclass with fingerprints
7. `src/codesub/semantic/indexer_protocol.py` - SemanticIndexer protocol
8. `src/codesub/cli.py` - CLI interface
9. `src/codesub/api.py` - FastAPI REST API
10. `tests/test_semantic_detector.py` - Test patterns

## Proposed Implementation Plan

I have created an implementation plan (included below). Please review it for:

1. **Correctness** - Will the proposed changes work correctly?
2. **Completeness** - Are all requirements addressed?
3. **Edge cases** - Are important edge cases handled?
4. **Integration** - Does it fit with the existing architecture?
5. **Testing** - Is the testing strategy adequate?

---

## Implementation Plan: Cross-File Construct Movement Detection

### Overview

This plan adds Stage 3 to the semantic subscription detection in `_check_semantic()`. When a construct is not found in its original file (after Stage 1 and Stage 2 fail), the system will search across other modified files in the git diff to locate the construct using fingerprint matching.

### Design Decisions

| Decision | Rationale |
|----------|-----------|
| Search only files in git diff | Performance: Limits scope to files that actually changed |
| Filter candidates by language | Safety: Python constructs should only be found in Python files |
| Reuse existing `_find_by_hash()` | Consistency: Same 3-tier matching logic |
| New trigger reason `moved_cross_file` | Clarity: Distinguishes cross-file moves from in-file renames |
| Configurable duplicate trigger behavior | Flexibility: Per-subscription control |
| Default: no trigger on duplicates | Safety: Avoid noisy alerts |
| Pass file_diffs to `_check_semantic()` | Efficiency: Avoid re-parsing diff |
| Use `sub.semantic` for change classification | Correctness: Since Stage 1 failed, `old_construct` is None |

### Implementation Steps

#### Step 1: Add `trigger_on_duplicate` field to Subscription model
- Add `trigger_on_duplicate: bool = False` field
- Update `to_dict()`, `from_dict()`, `create()`

#### Step 2: Update `scan()` to pass file_diffs to `_check_semantic()`

#### Step 3: Add helper method `_search_cross_file()`
- Filters candidate files by language
- Skips the original file (both old and new paths) and deleted files
- Indexes each candidate file
- Uses `_find_by_hash()` to find matches
- Returns list of (file_path, Construct) tuples

#### Step 4: Add helper method `_classify_cross_file_change()`
- Compares `sub.semantic` fingerprints directly against `found_construct`
- Needed because in Stage 3, `old_construct` is None (Stage 1 exact match failed)

#### Step 5: Add Stage 3 to `_check_semantic()`
- After Stage 2 fails, call `_search_cross_file()`
- Single match: create proposal with `moved_cross_file` reason
- Multiple matches: check `trigger_on_duplicate` setting
- No matches: return MISSING trigger (existing behavior)

#### Step 6: Update CLI and API
- Add `--trigger-on-duplicate` flag to CLI
- Add field to API request models

#### Step 7: Update model documentation

### Testing Strategy

- Single match cross-file
- Cross-file move with content/interface change
- Multiple matches (duplicates) with both trigger settings
- Language boundary enforcement
- Skip deleted files
- Skip original file
- File rename + cross-file move
- New file in diff
- Subscription serialization

### Edge Cases

- Construct renamed AND moved: Hash matching handles this
- File in diff but not readable: Gracefully skipped
- Unsupported language files: Filtered out
- Empty diff: Falls through to MISSING
- Construct moved to new file (status=A): Handled
- File renamed + construct moved elsewhere: Both paths skipped
- `old_construct` is None in Stage 3: Handled by `_classify_cross_file_change()`

---

## Your Task

Please review this plan and provide feedback on:

1. Any issues or gaps in the implementation approach
2. Edge cases that may have been missed
3. Suggestions for improvement
4. Whether the plan is ready for implementation

If you identify issues, please specify:
- The severity (critical/major/minor)
- The specific problem
- A suggested fix
