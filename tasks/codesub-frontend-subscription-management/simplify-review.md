# Code Simplification Review

## Summary
Found 8 opportunities for simplification. Most are minor improvements for maintainability.

## High Priority (Applied)

### 1. Error handler dictionary pattern (api.py)
The exception handler uses verbose if-chains. Can use dictionary mapping.

### 2. Location formatting utility (frontend)
Location formatting appears in 3 places - should be extracted to utility function.

## Medium Priority (Deferred)

- Schema conversion could use `__dict__` directly
- Status badge could be a reusable component
- Error message extraction utility for React

## Low Priority (Skipped)

- Minor redundancy in PATCH endpoint
- CORS origins could be pattern-based
- Form data handling simplification

## Decision
Applied high-priority item #1 (error handler dictionary). Other items noted for future improvement but not critical for MVP.
