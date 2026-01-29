## Implementation Plan: Cross-File Construct Movement Detection

### Overview

This plan adds Stage 3 to the semantic subscription detection in `_check_semantic()`. When a construct is not found in its original file (after Stage 1 and Stage 2 fail), the system will search across other modified files in the git diff to locate the construct using fingerprint matching. This enables detection of constructs that have been moved to different files.

### Design Decisions

| Decision | Rationale |
|----------|-----------|
| Search only files in git diff | Performance: Limits scope to files that actually changed, avoiding full codebase scan |
| Filter candidates by language | Safety: Python constructs should only be found in Python files (prevents false matches) |
| New helper `_find_hash_candidates()` | Correctness: `_find_by_hash()` can't distinguish "no match" vs "multiple matches" |
| New proposal reason `moved_cross_file` | Clarity: Distinguishes cross-file moves from in-file renames (follows existing pattern where `rename` is a proposal reason) |
| Configurable duplicate trigger behavior | Flexibility: Some users want alerts on duplicates, others don't |
| Default: no trigger on duplicates | Safety: Avoid noisy alerts; duplicates are often intentional |
| Pass file_diffs to `_check_semantic()` | Efficiency: Avoid re-parsing diff; already available in `scan()` |
| Modify `_classify_semantic_change()` | Simplicity: Remove `old_construct is None` guard since it only uses `sub.semantic` |
| Cache indexed constructs per-scan | Performance: Avoid O(subscriptions × files × parse_cost) |
| Restructure early returns | Correctness: Stage 3 must run even when original file is deleted |
| Match-tier confidence | Transparency: Set `Proposal.confidence` based on match quality |

**User Requirements:**
- Search scope limited to files in the current git diff only (not entire codebase)
- New proposal reason: `moved_cross_file` (follows pattern where `rename` is a proposal reason)
- Duplication handling: configurable per-subscription (default: don't trigger on duplicates)
- Must respect language boundaries (Python to Python only)

**Alternative Approaches Considered:**
- Search entire codebase: Rejected due to performance concerns and potential for false positives
- Add separate `_classify_cross_file_change()`: Rejected - simpler to fix existing `_classify_semantic_change()`
- Keep using `_find_by_hash()` for Stage 3: Rejected - can't distinguish "no match" vs "ambiguous"

### Prerequisites

- Familiarity with `_find_by_hash()` 3-tier matching logic
- Understanding of `detect_language()` in registry.py

### Implementation Steps

#### Step 1: Add `trigger_on_duplicate` field to Subscription model

**Files:** `src/codesub/models.py`

**Changes:**
- Add `trigger_on_duplicate: bool = False` field to the `Subscription` dataclass
- Update `to_dict()` to include the field
- Update `from_dict()` to read the field with default False (backward compatibility)
- Update `create()` to accept optional parameter

**Code:**
```python
@dataclass
class Subscription:
    """A subscription to a file line range."""

    id: str
    path: str  # repo-relative, POSIX-style
    start_line: int  # 1-based inclusive
    end_line: int  # 1-based inclusive
    label: str | None = None
    description: str | None = None
    anchors: Anchor | None = None
    semantic: SemanticTarget | None = None
    active: bool = True
    trigger_on_duplicate: bool = False  # NEW: trigger if construct found in multiple files
    created_at: str = field(default_factory=_utc_now)
    updated_at: str = field(default_factory=_utc_now)
```

#### Step 2: Add `_find_hash_candidates()` helper method

**Files:** `src/codesub/detector.py`

**Changes:**
- Add new method that returns ALL matching constructs with match tier, instead of single result
- This allows Stage 3 to distinguish "no matches" from "multiple matches" (ambiguous)
- Returns tuple of (matches, match_tier) where match_tier indicates confidence

**Code:**
```python
def _find_hash_candidates(
    self,
    semantic: SemanticTarget,
    constructs: "list[Construct]",
) -> tuple[list["Construct"], str]:
    """Find all constructs matching by hash, with match tier.

    Args:
        semantic: The semantic target with fingerprints.
        constructs: List of constructs to search.

    Returns:
        Tuple of (matching_constructs, match_tier).
        match_tier is "exact" | "body" | "interface" | "none".
    """
    # Try exact match (both hashes)
    exact_matches = [
        c for c in constructs
        if c.interface_hash == semantic.interface_hash
        and c.body_hash == semantic.body_hash
        and c.kind == semantic.kind
    ]
    if exact_matches:
        return exact_matches, "exact"

    # Try body-only match (renamed + signature changed)
    body_matches = [
        c for c in constructs
        if c.body_hash == semantic.body_hash and c.kind == semantic.kind
    ]
    if body_matches:
        return body_matches, "body"

    # Try interface-only match (renamed + body changed)
    interface_matches = [
        c for c in constructs
        if c.interface_hash == semantic.interface_hash and c.kind == semantic.kind
    ]
    if interface_matches:
        return interface_matches, "interface"

    return [], "none"
```

#### Step 3: Modify `_classify_semantic_change()` to remove `old_construct` guard

**Files:** `src/codesub/detector.py`

**Changes:**
- Remove the `if old_construct is None` early return
- The method only uses `sub.semantic` for comparison anyway, not `old_construct`
- This allows Stage 3 to reuse the existing classifier

**Code (before):**
```python
def _classify_semantic_change(
    self,
    sub: Subscription,
    old_construct: "Construct | None",
    new_construct: "Construct",
) -> Trigger | None:
    if old_construct is None or sub.semantic is None:
        return None
    # ... rest uses sub.semantic, not old_construct
```

**Code (after):**
```python
def _classify_semantic_change(
    self,
    sub: Subscription,
    new_construct: "Construct",
) -> Trigger | None:
    """Classify change type between subscription and new construct.

    Compares stored fingerprints in sub.semantic against new_construct.
    """
    if sub.semantic is None:
        return None

    # Check interface change (type/signature)
    if sub.semantic.interface_hash != new_construct.interface_hash:
        return Trigger(
            subscription_id=sub.id,
            subscription=sub,
            path=sub.path,
            start_line=sub.start_line,
            end_line=sub.end_line,
            reasons=["interface_changed"],
            matching_hunks=[],
            change_type="STRUCTURAL",
        )

    # Check body change (value/implementation)
    if sub.semantic.body_hash != new_construct.body_hash:
        return Trigger(
            subscription_id=sub.id,
            subscription=sub,
            path=sub.path,
            start_line=sub.start_line,
            end_line=sub.end_line,
            reasons=["body_changed"],
            matching_hunks=[],
            change_type="CONTENT",
        )

    return None
```

**Note:** Update all existing call sites to remove the `old_construct` argument.

#### Step 4: Update `scan()` to pass file_diffs and add construct cache

**Files:** `src/codesub/detector.py`

**Changes:**
- Pass `file_diffs` to `_check_semantic()`
- Add a per-scan cache for indexed constructs to avoid re-parsing

**Code:**
```python
def scan(self, subscriptions, base_ref, target_ref=None) -> ScanResult:
    # ... existing setup ...

    # Cache for indexed constructs: (path, language) -> list[Construct]
    # Avoids re-parsing the same file for multiple subscriptions
    construct_cache: dict[tuple[str, str], list[Construct]] = {}

    for sub in active_subs:
        if sub.semantic is not None:
            trigger, proposal = self._check_semantic(
                sub, base_ref, target_ref, rename_map, status_map,
                file_diffs, construct_cache  # NEW parameters
            )
            # ... rest unchanged
```

#### Step 5: Add helper method `_search_cross_file()`

**Files:** `src/codesub/detector.py`

**Changes:**
- Add new method that searches other files in the diff for the construct
- Uses construct cache to avoid re-parsing
- Filters by language, skips deleted/binary files
- Uses `_find_hash_candidates()` to detect ambiguous matches
- Returns matches with confidence tier

**Code:**
```python
def _search_cross_file(
    self,
    semantic: SemanticTarget,
    old_path: str,
    new_path: str,
    target_ref: str | None,
    file_diffs: list[FileDiff],
    status_map: dict[str, str],
    construct_cache: dict[tuple[str, str], list["Construct"]],
) -> tuple[list[tuple[str, "Construct"]], str]:
    """Search for construct in other files from the diff.

    Args:
        semantic: The semantic target to search for.
        old_path: Original subscription path to skip.
        new_path: Renamed path to skip (may be same as old_path).
        target_ref: Target ref for reading files.
        file_diffs: List of file diffs to search.
        status_map: Path to status mapping.
        construct_cache: Cache of indexed constructs per file.

    Returns:
        Tuple of (matches, best_match_tier).
        matches is list of (file_path, Construct) tuples.
        best_match_tier is "exact" | "body" | "interface" | "none".
    """
    from .errors import UnsupportedLanguageError
    from .semantic import detect_language, get_indexer

    target_language = semantic.language
    all_matches: list[tuple[str, "Construct"]] = []
    best_tier = "none"
    tier_priority = {"exact": 0, "body": 1, "interface": 2, "none": 3}
    skip_paths = {old_path, new_path}

    for fd in file_diffs:
        candidate_path = fd.new_path

        # Skip original file (both old and new paths)
        if candidate_path in skip_paths or fd.old_path in skip_paths:
            continue

        # Skip deleted files
        if fd.is_deleted_file or status_map.get(fd.old_path) == "D":
            continue

        # Skip binary files
        if getattr(fd, 'is_binary', False):
            continue

        # Check language compatibility
        try:
            candidate_language = detect_language(candidate_path)
            if candidate_language != target_language:
                continue
        except UnsupportedLanguageError:
            continue

        # Check cache first
        cache_key = (candidate_path, target_language)
        if cache_key in construct_cache:
            constructs = construct_cache[cache_key]
        else:
            # Get file content
            try:
                if target_ref:
                    source = "\n".join(self.repo.show_file(target_ref, candidate_path))
                else:
                    with open(self.repo.root / candidate_path, encoding="utf-8") as f:
                        source = f.read()
            except (FileNotFoundError, PermissionError, UnicodeDecodeError, OSError):
                continue

            # Index the file and cache
            indexer = get_indexer(target_language)
            constructs = indexer.index_file(source, candidate_path)
            construct_cache[cache_key] = constructs

        # Find matches using candidates API
        matches, tier = self._find_hash_candidates(semantic, constructs)
        for match in matches:
            all_matches.append((candidate_path, match))
            if tier_priority[tier] < tier_priority[best_tier]:
                best_tier = tier

    return all_matches, best_tier
```

#### Step 6: Restructure `_check_semantic()` to always attempt Stage 3

**Files:** `src/codesub/detector.py`

**Changes:**
- **CRITICAL:** Restructure early returns so Stage 3 runs even when original file is deleted
- Try Stage 1/2 only if new_source can be loaded
- Always attempt Stage 3 if Stage 1/2 didn't find a match
- After Stage 3, decide which missing reason to return based on why earlier stages failed

**Code:**
```python
def _check_semantic(
    self,
    sub: Subscription,
    base_ref: str,
    target_ref: str | None,
    rename_map: dict[str, str],
    status_map: dict[str, str],
    file_diffs: list[FileDiff],
    construct_cache: dict[tuple[str, str], list["Construct"]],
) -> tuple[Trigger | None, Proposal | None]:
    """Check semantic subscription for changes."""
    from .errors import UnsupportedLanguageError
    from .semantic import get_indexer

    assert sub.semantic is not None

    try:
        indexer = get_indexer(sub.semantic.language)
    except UnsupportedLanguageError as e:
        return (
            Trigger(
                subscription_id=sub.id,
                subscription=sub,
                path=sub.path,
                start_line=sub.start_line,
                end_line=sub.end_line,
                reasons=["unsupported_language"],
                matching_hunks=[],
                change_type="AMBIGUOUS",
                details={"error": str(e)},
            ),
            None,
        )

    old_path = sub.path
    new_path = rename_map.get(old_path, old_path)

    # Track why we might fail, for final error message
    file_deleted = status_map.get(old_path) == "D"
    file_read_failed = False
    new_source: str | None = None

    # Try to get new file content (may fail if deleted or unreadable)
    if not file_deleted:
        try:
            if target_ref:
                new_source = "\n".join(self.repo.show_file(target_ref, new_path))
            else:
                with open(self.repo.root / new_path, encoding="utf-8") as f:
                    new_source = f.read()
        except (FileNotFoundError, PermissionError, UnicodeDecodeError, OSError):
            file_read_failed = True

    # Stage 1 & 2: Only if we have new_source
    if new_source is not None:
        # Get old file content for comparison
        old_source = "\n".join(self.repo.show_file(base_ref, old_path))

        # Stage 1: Exact match by qualname
        new_construct = indexer.find_construct(
            new_source, new_path, sub.semantic.qualname, sub.semantic.kind
        )

        if new_construct:
            trigger = self._classify_semantic_change(sub, new_construct)
            proposal = None

            if old_path != new_path:
                proposal = Proposal(
                    subscription_id=sub.id,
                    subscription=sub,
                    old_path=old_path,
                    old_start=sub.start_line,
                    old_end=sub.end_line,
                    new_path=new_path,
                    new_start=new_construct.start_line,
                    new_end=new_construct.end_line,
                    reasons=["rename"],
                    confidence="high",
                )
            elif (
                new_construct.start_line != sub.start_line
                or new_construct.end_line != sub.end_line
            ):
                proposal = Proposal(
                    subscription_id=sub.id,
                    subscription=sub,
                    old_path=old_path,
                    old_start=sub.start_line,
                    old_end=sub.end_line,
                    new_path=new_path,
                    new_start=new_construct.start_line,
                    new_end=new_construct.end_line,
                    reasons=["line_shift"],
                    confidence="high",
                )

            return trigger, proposal

        # Stage 2: Hash-based search in same file
        new_constructs = indexer.index_file(new_source, new_path)
        match = self._find_by_hash(sub.semantic, new_constructs)

        if match:
            trigger = self._classify_semantic_change(sub, match)
            proposal = Proposal(
                subscription_id=sub.id,
                subscription=sub,
                old_path=old_path,
                old_start=sub.start_line,
                old_end=sub.end_line,
                new_path=new_path,
                new_start=match.start_line,
                new_end=match.end_line,
                reasons=["semantic_location"],
                confidence="high",
                new_qualname=match.qualname,
                new_kind=match.kind,
            )
            return trigger, proposal

    # Stage 3: Cross-file search (always attempted, even if file deleted)
    cross_matches, match_tier = self._search_cross_file(
        sub.semantic, old_path, new_path, target_ref, file_diffs,
        status_map, construct_cache
    )

    if len(cross_matches) == 1:
        # Found in exactly one other file
        found_path, found_construct = cross_matches[0]
        trigger = self._classify_semantic_change(sub, found_construct)

        # Set confidence based on match tier
        confidence = "high" if match_tier == "exact" else "medium" if match_tier == "body" else "low"

        proposal = Proposal(
            subscription_id=sub.id,
            subscription=sub,
            old_path=old_path,
            old_start=sub.start_line,
            old_end=sub.end_line,
            new_path=found_path,
            new_start=found_construct.start_line,
            new_end=found_construct.end_line,
            reasons=["moved_cross_file"],
            confidence=confidence,
            new_qualname=found_construct.qualname if found_construct.qualname != sub.semantic.qualname else None,
            new_kind=found_construct.kind if found_construct.kind != sub.semantic.kind else None,
        )
        return trigger, proposal

    if len(cross_matches) > 1:
        # Found in multiple files (duplicate/ambiguous)
        if sub.trigger_on_duplicate:
            locations = [f"{path}:{c.start_line}" for path, c in cross_matches]
            return (
                Trigger(
                    subscription_id=sub.id,
                    subscription=sub,
                    path=old_path,
                    start_line=sub.start_line,
                    end_line=sub.end_line,
                    reasons=["duplicate_found"],
                    matching_hunks=[],
                    change_type="AMBIGUOUS",
                    details={"locations": locations},
                ),
                None,
            )
        # Default: duplicates are ambiguous, treat as unchanged (no trigger, no proposal)
        return (None, None)

    # Not found anywhere - determine the appropriate missing reason
    if file_deleted:
        reason = "file_deleted"
    elif file_read_failed:
        reason = "file_not_found"
    else:
        reason = "semantic_target_missing"

    return (
        Trigger(
            subscription_id=sub.id,
            subscription=sub,
            path=old_path,
            start_line=sub.start_line,
            end_line=sub.end_line,
            reasons=[reason],
            matching_hunks=[],
            change_type="MISSING",
        ),
        None,
    )
```

#### Step 7: Update CLI and API to support `trigger_on_duplicate`

**Files:** `src/codesub/cli.py`, `src/codesub/api.py`

**Changes:**
- Add `--trigger-on-duplicate` flag to `codesub add` command
- Add `trigger_on_duplicate` field to API subscription creation/update endpoints

**CLI Code:**
```python
# In add_parser arguments
add_parser.add_argument(
    "--trigger-on-duplicate",
    action="store_true",
    help="Trigger alert if construct is found in multiple files (default: no trigger)",
)
```

**API Code:**
```python
# In SubscriptionCreateRequest
class SubscriptionCreateRequest(BaseModel):
    # ... existing fields ...
    trigger_on_duplicate: bool = False
```

#### Step 8: Update model documentation

**Files:** `src/codesub/models.py`

**Changes:**
- Update the `reasons` field comment in `Proposal` to include `moved_cross_file`
- Update the `reasons` field comment in `Trigger` to include `duplicate_found`

### Testing Strategy

**Critical tests:**
- [ ] **Old file deleted + construct moved** - Original file deleted, construct moved to new file. Should find via Stage 3 and create proposal.
- [ ] **Single match cross-file** - Construct moved from `a.py` to `b.py`, should create proposal with `moved_cross_file` reason

**Duplicate behavior tests:**
- [ ] **Duplicates with trigger_on_duplicate=False** - Construct in `b.py` and `c.py`, should return (None, None) meaning unchanged
- [ ] **Duplicates with trigger_on_duplicate=True** - Should return AMBIGUOUS trigger with locations in details

**Change detection tests:**
- [ ] **Cross-file move with content change** - Construct moved and modified, should have CONTENT trigger and proposal
- [ ] **Cross-file move with interface change** - Construct moved with signature change, should have STRUCTURAL trigger

**Boundary tests:**
- [ ] **Language boundary** - Python construct should not match Java file even with same hash
- [ ] **Skip deleted files** - Deleted files in diff should not be searched
- [ ] **Skip binary files** - Binary files in diff should not be searched
- [ ] **Skip original file** - Original file should not appear in cross-file matches

**Edge case tests:**
- [ ] **File rename + cross-file move** - Subscription file renamed, but construct moved elsewhere
- [ ] **New file in diff** - Construct moved to newly created file (status=A)
- [ ] **Working tree scan** - target_ref=None, should read from disk correctly

**Confidence tests:**
- [ ] **Exact match confidence** - Both hashes match, confidence=high
- [ ] **Body-only match confidence** - Only body hash matches, confidence=medium
- [ ] **Interface-only match confidence** - Only interface hash matches, confidence=low

**Serialization tests:**
- [ ] **Subscription to_dict()** - includes `trigger_on_duplicate`
- [ ] **Subscription from_dict()** - defaults to False when field missing (backward compatibility)

### Edge Cases Considered

- **Construct renamed AND moved**: Hash matching handles this via body/interface hashes
- **File in diff but not readable**: Gracefully skipped with try/except
- **Binary files in diff**: Filtered out via `is_binary` flag
- **Unsupported language files**: Filtered out via `detect_language()` exception
- **Empty diff (no file_diffs)**: Cross-file search returns empty list, falls through to MISSING
- **Construct moved to new file (status=A)**: Handled correctly since new files have `new_path` set
- **File renamed + construct moved elsewhere**: Both old_path and new_path skipped in cross-file search
- **Old file deleted**: Stage 3 still runs and can find construct in other files
- **Working tree scan**: Uses same disk-reading approach as existing code
- **False positives**: Match-tier confidence helps users evaluate proposal quality
- **Duplicates within single file**: `_find_hash_candidates()` returns all matches, handled as ambiguous

### Risks and Mitigations

- **Risk:** Performance degradation with large diffs and many subscriptions
  **Mitigation:** Per-scan construct cache avoids re-parsing files; search limited to diff scope

- **Risk:** False positive matches across files
  **Mitigation:** 3-tier hash matching; language boundary filtering; confidence tiers for transparency

- **Risk:** Breaking change to Subscription schema
  **Mitigation:** New field has default value (`False`), backward compatible

- **Risk:** Breaking change to `_classify_semantic_change()` signature
  **Mitigation:** Update all call sites; method now only requires `sub` and `new_construct`

### Summary of Changes from External Review

1. **CRITICAL FIX:** Restructured `_check_semantic()` to not early-return before Stage 3. Now Stage 3 runs even when original file is deleted.

2. **MAJOR FIX:** Added `_find_hash_candidates()` helper that returns all matches with tier, enabling proper "no match" vs "ambiguous" distinction.

3. **MAJOR FIX:** Modified `_classify_semantic_change()` instead of adding new method - removed unused `old_construct` parameter.

4. **MAJOR FIX:** Added per-scan construct cache to avoid O(subs × files × parse) performance issue.

5. **Clarified duplicate behavior:**
   - `trigger_on_duplicate=False` → returns `(None, None)` (unchanged, no trigger)
   - `trigger_on_duplicate=True` → returns AMBIGUOUS trigger

6. **Added match-tier confidence:** Proposal.confidence reflects match quality (exact/body/interface).

7. **Additional edge cases:** Binary files, working tree scans, old file deleted scenarios.
