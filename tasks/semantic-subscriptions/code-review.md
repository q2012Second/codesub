# Code Review: Semantic Subscriptions

## Summary

**Verdict: APPROVED**

Found 5 issues (1 Medium, 4 Low severity). None block the feature. The implementation is well-designed with good test coverage.

## Issues Found

### 1. Broad Exception Handling (Medium)
- **Location:** `src/codesub/detector.py:323-336`
- **Issue:** Catches all exceptions when reading files, masking actual errors
- **Status:** Deferred to follow-up - current behavior is safe (fails closed)

### 2. Parser Instantiated Per Call (Low)
- **Location:** `src/codesub/detector.py:296`
- **Issue:** New `PythonIndexer` created for each semantic subscription
- **Status:** Acceptable - minor overhead, tests pass quickly

### 3. Redundant File Parsing (Low)
- **Location:** `src/codesub/semantic/python_indexer.py:56-64`
- **Issue:** `find_construct` re-parses entire file
- **Status:** Acceptable - single construct lookups per file in current use

### 4. Missing Kind Options Documentation (Low)
- **Location:** `src/codesub/cli.py:628`
- **Issue:** `--kind` help doesn't explain that constants are `variable` with role
- **Status:** Minor UX - users can discover via `codesub symbols`

### 5. Hash Truncation (Low)
- **Location:** `src/codesub/semantic/fingerprint.py:100`
- **Issue:** 64-bit truncated hash could theoretically collide
- **Status:** Acceptable - `len(matches) == 1` check prevents false positives

## No Issues In

- **Security:** No path traversal or injection vulnerabilities
- **Data Model:** Correct serialization/deserialization
- **Test Coverage:** Good coverage of scenarios including edge cases

## Conclusion

Safe to merge. Medium-severity issue can be addressed in follow-up PR.
