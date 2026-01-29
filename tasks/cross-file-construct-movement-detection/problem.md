# Problem Statement: Cross-File Construct Movement Detection

## Task Type
**Type:** feature

## Current State

The semantic subscription system currently tracks code constructs by identity using Tree-sitter parsing and fingerprint-based matching (interface_hash and body_hash). When a construct's location changes, the system uses a two-stage detection strategy in `/Users/vlad/dev/projects/codesub/src/codesub/detector.py` (`_check_semantic` method, lines 288-449):

**Stage 1: Exact qualname match** - Searches for the construct by its qualified name in the same/renamed file:
- File path is resolved through the rename_map (which maps old_path to new_path)
- Successfully handles: in-file moves, line shifts, and whole-file renames
- Example: `User.validate` moved within `auth.py` or `auth.py` renamed to `authentication.py`

**Stage 2: Hash-based search** - If exact qualname fails, searches by fingerprint:
- Calls `indexer.index_file(new_source, new_path)` on line 414
- Only indexes constructs in the **same/renamed file** (new_path)
- Calls `_find_by_hash()` on line 415 to match against these constructs
- Successfully handles: construct renamed within the same file
- Example: `MAX_RETRIES` renamed to `RETRY_COUNT` in `config.py`

**The limitation:** When a construct is moved to a different file (not through file rename), the hash-based search only looks in the new_path (which still points to the original/renamed file). The construct won't be found and is marked as "MISSING" (line 437-449) with reason `semantic_target_missing`.

## Desired State

When a semantic subscription cannot locate its construct in the same/renamed file (after both Stage 1 and Stage 2 fail), the system should:

1. **Search across other files in the git diff** for the construct using fingerprint matching
2. **Respect language boundaries** - only search files of the same language as the original subscription
3. **Find relocated constructs** that moved to different files while preserving their implementation
4. **Generate a proposal** with the new file path and location when found
5. **Report "MISSING" only when genuinely not found** in any changed file

The system should detect scenarios like:
- `User.validate` method extracted from `models.py` to `validators.py` (both files in same commit)
- `MAX_RETRIES` constant moved from `config.py` to `constants.py` (both files modified in diff)
- `OrderService` class moved from `services.py` to `order/service.py` (delete + add in same diff)

## Scope Constraint

**Cross-file search is limited to the git diff scope only.** The system will NOT search the entire codebase. Instead:
- When analyzing a single commit, only files changed in that commit are searched
- When analyzing a range of commits, only files changed in that range are searched
- When analyzing working directory changes, only modified/added files are searched

This constraint:
- Keeps performance predictable and fast (diff size is naturally bounded)
- Makes the feature semantically correct (if construct moved outside the diff, it's a different change set)
- Aligns with existing detector logic which already processes files from the diff

## Design Decisions (Resolved)

### 1. Duplication Handling
When a construct exists in both the old location AND a new location (duplicated in the diff):
- The duplication **should be marked/detected**
- Whether to **trigger** on duplication is **configurable per-subscription**
- **Default behavior: do NOT trigger** on duplicates (subscription stays on original location)

### 2. Trigger Reason
Introduce a **new trigger reason**: `moved_cross_file` (distinct from `renamed` which is for same-file renames)

## Constraints

- **Diff-scoped search**: Only search files that appear in the current git diff being analyzed
- **Language detection**: Must use existing language registry to filter candidate files by extension
- **Ambiguity handling**: If multiple files in the diff contain matching constructs, report as ambiguous rather than guessing
- **Backward compatibility**: Must not break existing detection for same-file moves and file renames
- **False positive risk**: Hash collisions or duplicate implementations should not create incorrect proposals

## Acceptance Criteria

- [ ] When a construct moves to a different file within the same diff, the system detects it and generates a proposal with the new file path, line numbers, and qualified name
- [ ] New trigger reason `moved_cross_file` is used for cross-file movements
- [ ] Cross-file search only examines files matching the subscription's language (Python files for Python constructs, Java files for Java constructs)
- [ ] Cross-file search only examines files that are part of the current git diff (not the entire codebase)
- [ ] Same-file rename detection and whole-file rename detection continue to work as before (tests pass)
- [ ] Duplication is detected and marked; triggering on duplicates is configurable (default: no trigger)
- [ ] Test coverage includes: construct moved to new file (Python and Java), construct moved with modification, construct duplicated across files

## Affected Areas

- `/Users/vlad/dev/projects/codesub/src/codesub/models.py` - Add new trigger reason, possibly new subscription option for duplicate handling
- `/Users/vlad/dev/projects/codesub/src/codesub/detector.py` - Add Stage 3 cross-file hash search logic in `_check_semantic` method
- `/Users/vlad/dev/projects/codesub/tests/test_semantic_detector.py` - Add tests for cross-file movement scenarios
- `/Users/vlad/dev/projects/codesub/tests/test_java_semantic_detector.py` - Add Java-specific cross-file movement tests
