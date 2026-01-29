# Plan Comparison: Internal vs External Analysis

## Summary

Both plans agree on the core implementation approach but differ in some implementation details. The merged plan incorporates the best aspects of each.

## Agreements (Both Plans)

| Aspect | Approach |
|--------|----------|
| TypeScript types | Add `SemanticTarget` interface, extend `Subscription`/`Trigger`/`Proposal` |
| List view badges | [S] vs [L] badges to distinguish subscription types |
| Form auto-detect | Use `::` presence to detect semantic format |
| Scan styling | Color-code by change_type (STRUCTURAL/CONTENT/MISSING) |
| Detail view | Show semantic target section with kind, qualname, hashes |
| Apply modal | Show `new_qualname` for semantic rename proposals |

## Key Differences

| Aspect | Internal Plan | External Plan | Resolution |
|--------|---------------|---------------|------------|
| **Backend API** | Phase 0 with full implementation | Flagged as risk, not included | **Keep internal** - this is critical |
| **ChangeType type** | `string \| null` | Union type with both cases | **Adopt external** - more type-safe |
| **Case handling** | Assume UPPERCASE | `normalizeChangeType()` helper | **Adopt external** - defensive |
| **Details type** | `Record<string, unknown>` | `unknown` + `formatDetails()` | **Adopt external** - handles strings |
| **Details rendering** | Not explicitly shown | `<pre>` block with JSON | **Adopt external** - better UX |
| **Testing** | Manual test cases | Component-level RTL tests | **Adopt external** - more thorough |
| **Optional fields** | Some required | All semantic fields optional | **Adopt external** - backwards compat |

## What Internal Plan Had That External Didn't

1. **Phase 0: Backend API Updates** - Critical prerequisite
   - `SemanticTargetSchema` Pydantic model
   - Updated `subscription_to_schema()`
   - `_create_subscription_from_request()` helper
   - Semantic subscription creation support

2. **Explicit ApplyUpdatesModal step** - Step 2.5 with RENAME badge

## What External Plan Had That Internal Didn't

1. **`normalizeChangeType()` helper** - Case normalization for robustness
2. **`formatDetails()` helper** - Handles string, object, and null
3. **Defensive ChangeType union** - Accepts both upper and lowercase
4. **Component-level test table** - Specific RTL test cases
5. **`<pre>` block for details** - Better formatting of complex details
6. **Optional hashes in SemanticTarget** - Backwards compatibility

## Merged Plan Enhancements

The updated `plan.md` now includes:

1. Backend API updates (Phase 0) - from internal
2. `ChangeType` union type with both cases - from external
3. `normalizeChangeType()` helper - from external
4. `formatDetails()` helper - from external
5. `<pre>` block for trigger details - from external
6. Component-level test cases table - from external
7. Optional fields where appropriate - from external
8. RENAME badge in ApplyUpdatesModal - from internal

## Risk Assessment

| Risk | Mitigation |
|------|------------|
| Backend not returning `semantic` | Phase 0 ensures this is fixed first |
| Case mismatch in change_type | `normalizeChangeType()` handles both |
| Old scan history without new fields | All new fields are optional |
| details as string vs object | `formatDetails()` handles both |
