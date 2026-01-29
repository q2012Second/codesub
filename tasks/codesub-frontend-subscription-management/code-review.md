# Code Review

## Summary
Found **6 issues**: 1 Major, 5 Minor. The code is generally well-structured for a local development tool.

## Issues

### 1. Race Condition in Config Store Operations (Major)
**Status:** Mitigated by design - server runs with `workers=1` and is documented as single-user tool.

### 2. Inconsistent Error Handling (Minor)
**Location:** `api.py:267` - reactivate uses `HTTPException` directly
**Status:** Noted for future improvement. Current behavior is acceptable.

### 3. Updated Timestamp Not Set After Reactivation (Minor)
**Location:** `api.py:260-271`
**Status:** FIXED - Added timestamp update in reactivate endpoint.

### 4. Integer Parsing in Frontend (Minor)
**Status:** HTML5 `type="number"` with `min`/`max` handles this adequately.

### 5. Missing Network Error Handling (Minor)
**Status:** Noted for future improvement. App.tsx already shows helpful message about running `codesub serve`.

### 6. Missing Test for Context Constraint (Minor)
**Status:** FIXED - Added test case for context validation.

## Security Analysis
- CORS: Appropriate for local dev tool
- Input validation: Good coverage via parse_location and Pydantic
- No SQL injection (JSON file storage)
- Path traversal: Git commands prevent access outside repo

## Positive Findings
- Well-structured error handling with custom exception types
- Comprehensive test coverage (26 API tests)
- Proper PATCH semantics with exclude_unset
- Type safety with Pydantic and TypeScript
- Consistent REST API design
