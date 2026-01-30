# Plan Review: Visual Code Browser for Subscription Creation

## Summary

This is a well-structured plan for adding a visual code browser to the codesub frontend. The plan demonstrates good understanding of the existing codebase architecture and proposes a sensible two-step modal flow. The backend additions align with existing API patterns, and the frontend integration approach is appropriate.

## Strengths

1. **Solid architectural alignment** - The plan follows existing patterns in the codebase:
   - Uses the same Pydantic schema style for new endpoints
   - Leverages existing helper functions like `get_project_store_and_repo()`
   - Frontend API functions follow the established pattern in `api.ts`

2. **Good design decisions** - The rationale table shows thoughtful consideration:
   - Using baseline ref for file content ensures consistency with subscription tracking
   - Server-side filtering prevents sending all filenames to large repos
   - Two-step flow keeps each component focused and testable

3. **Comprehensive edge case handling** - The plan identifies key failure modes:
   - Empty repository
   - Unsupported languages graceful degradation
   - Parse errors still allowing line selection
   - Large file warnings

4. **Clear implementation order** - Backend endpoints first, then types, then components - dependencies are correctly sequenced

5. **Realistic scope** - The feature is achievable and integrates cleanly without disrupting existing functionality

## Issues Found

### Critical Issues

None.

### Major Issues

#### 1. Missing `has_parse_error` field in Construct dataclass check

- **Severity:** Major
- **Description:** The plan's `SymbolsResponse` schema references `c.has_parse_error` on line 287, but the aggregation logic only checks this after iterating constructs. The Construct dataclass does include `has_parse_error: bool = False`, so this is correct. However, if a file fails to parse entirely, `indexer.index_file()` may raise an exception or return an empty list rather than setting `has_parse_error` on constructs. The plan should handle the case where parsing fails completely.
- **Suggested Fix:** Wrap the indexer call in try/except and return `SymbolsResponse(path=path, language=language, constructs=[], has_parse_error=True)` on parse failure.

#### 2. URL encoding for file paths with special characters

- **Severity:** Major
- **Description:** The frontend API functions use `encodeURIComponent(path)` for file paths (line 415, 430), but the backend endpoint uses `{path:path}` path converter. Paths with characters like `#`, `?`, or `%` could cause issues. The `encodeURIComponent` will encode `/` as `%2F`, which may not be decoded properly by FastAPI's path converter.
- **Suggested Fix:** Either:
  - Use query parameter for path instead of path parameter: `GET /api/projects/{project_id}/file-content?path=src/foo.py`
  - Or document that paths must be encoded with a custom function that preserves `/` but encodes other special characters

#### 3. Missing debounce hook implementation

- **Severity:** Major
- **Description:** The `FileListPanel` component references `useDebouncedValue(search, 300)` (line 526), but this hook is not defined in the plan. The existing codebase does not appear to have a debounce hook.
- **Suggested Fix:** Add the hook implementation to the plan:
```typescript
function useDebouncedValue<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);
  return debounced;
}
```

### Minor Issues

#### 4. Inconsistent type naming between CodeBrowserSelection and full-file type

- **Severity:** Minor
- **Description:** `CodeBrowserSelection.type` can be `'full-file'` but the `getSelectionResult()` function in Step 7 would return `'line-range'` for full-file selections (since it just checks `lineSelection`). Step 9 shows "Select Full File" but the result still has `type: 'line-range'`.
- **Suggested Fix:** Either remove `'full-file'` from the union type, or add explicit handling:
```typescript
if (lineSelection && lineSelection.start === 1 && lineSelection.end === content?.total_lines) {
  return { type: 'full-file', location, label: `Full file: ${filePath}` };
}
```

#### 5. No keyboard accessibility for construct selection

- **Severity:** Minor
- **Description:** The plan describes clicking constructs and shift-clicking lines, but does not mention keyboard navigation (Tab, Enter, arrow keys). This could be a barrier for accessibility.
- **Suggested Fix:** Add a note to support keyboard navigation in a follow-up iteration, or add basic focus management with tabIndex and onKeyDown handlers.

#### 6. Missing cancel/abort for in-flight requests

- **Severity:** Minor
- **Description:** The plan mentions "Request ID tracking (pattern from FileBrowserModal), cancel stale requests" in the risks section, but the component code does not show AbortController usage.
- **Suggested Fix:** Add abort controller pattern:
```typescript
useEffect(() => {
  const controller = new AbortController();
  loadFiles(controller.signal);
  return () => controller.abort();
}, [projectId, debouncedSearch, extensions]);
```

#### 7. `detect_language` vs `get_indexer_for_path` usage inconsistency

- **Severity:** Minor
- **Description:** In Step 2 (file content endpoint), the plan imports `detect_language` and `supported_languages` from `.semantic`, but `supported_languages` is not used and `detect_language` is only called to set a boolean. In Step 3 (symbols endpoint), `get_indexer_for_path` is used instead, which already handles unsupported languages by raising `UnsupportedLanguageError`. The file content endpoint should use consistent approach.
- **Suggested Fix:** Simplify Step 2 to:
```python
from .semantic import get_indexer_for_path
language = None
supports_semantic = False
try:
    language, _ = get_indexer_for_path(path)
    supports_semantic = True
except UnsupportedLanguageError:
    pass
```

#### 8. Test file placement

- **Severity:** Minor
- **Description:** The plan proposes `/Users/vlad/dev/projects/codesub/tests/test_api_files.py` for backend tests, but the existing tests are in `/Users/vlad/dev/projects/codesub/tests/test_api.py`. Adding a new file is fine, but consider whether these tests should be added to the existing file for consistency.
- **Suggested Fix:** Either add to existing `test_api.py` with a new test class, or document that `test_api_files.py` is intentionally separate for the code browser feature.

## Recommendations

1. **Add error boundary** - Consider adding React error boundary around CodeBrowserModal to prevent the entire app crashing on unexpected errors.

2. **Consider caching** - File content and symbols could benefit from client-side caching (e.g., React Query or simple Map) to avoid re-fetching when navigating back and forth.

3. **Add loading states** - The plan shows loading state management but consider skeleton loaders for better UX during file list/content loading.

4. **Document baseline requirement** - The prerequisite mentions baseline must be set, but the UI should show a clear message if baseline is missing, suggesting the user run a scan first.

## Verdict

**PLAN APPROVED**

The plan is technically sound and well-structured. The major issues identified are implementation details that can be addressed during development without changing the overall approach. The plan correctly:

- Extends existing patterns rather than introducing new ones
- Maintains separation between backend and frontend concerns
- Provides comprehensive test coverage strategy
- Handles the key edge cases

Proceed with implementation, addressing the major issues (parse error handling, URL encoding, debounce hook) as you go.
