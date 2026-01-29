# Plan Review: Frontend Semantic Subscription Management (Revision 2)

## Summary

The revised plan addresses all critical issues from the first review. It now includes a Phase 0 for backend API updates, adds `SemanticTargetSchema`, updates `subscription_to_schema()`, supports semantic subscription creation, uses UPPERCASE change types, updates `ApplyUpdatesModal`, and adds the `details` field to Trigger. The plan is comprehensive and ready for implementation.

## Verification of Requested Fixes

| Item | Status | Notes |
|------|--------|-------|
| Backend API updates in Phase 0 | FIXED | Steps 0.1-0.3 cover all backend changes |
| SemanticTargetSchema added to api.py | FIXED | Step 0.1 adds the schema after AnchorSchema |
| subscription_to_schema() updated | FIXED | Step 0.1 includes the conversion logic |
| Semantic subscription creation | FIXED | Step 0.2 adds `_create_subscription_from_request` helper and updates endpoints |
| Symbol browser out-of-scope | FIXED | Explicitly stated in Design Decisions table and "Out of Scope" section |
| Change type casing UPPERCASE | FIXED | Step 2.2 uses UPPERCASE keys in `CHANGE_TYPE_STYLES` |
| ApplyUpdatesModal updated | FIXED | Step 2.5 adds semantic rename display |
| details field in Trigger | FIXED | Step 1.1 adds `details: Record<string, unknown> \| null` |

## Issues Found

### Critical Issues

None.

### Major Issues

None.

### Minor Issues

#### 1. TriggerSchema in api.py Missing details Field

- **Severity:** Minor
- **Description:** Step 0.1 mentions adding `details` field to `TriggerSchema`, but the code block for `TriggerSchema` (lines 89-99 in the plan) does include it. However, the existing backend `TriggerSchema` at `/Users/vlad/dev/projects/codesub/src/codesub/api.py` (lines 125-132) already has `change_type` but is missing `details`. The plan correctly identifies this needs to be added.
- **Status:** Plan is correct, just noting for implementation verification.

#### 2. Missing Import for SemanticTarget in Step 0.2

- **Severity:** Minor
- **Description:** Step 0.2 shows `from .models import Anchor, Subscription, SemanticTarget` but the existing api.py line 25 only imports `Anchor, Subscription`. The plan correctly identifies this import is needed.
- **Status:** Plan is correct, just noting for implementation.

#### 3. Potential Missing Error Import

- **Severity:** Minor
- **Description:** Step 0.2's `_create_subscription_from_request` uses `InvalidLocationError` and `InvalidLineRangeError`, which are already imported in api.py (lines 14-15). No action needed.
- **Status:** No issue.

#### 4. SubscriptionList.tsx Full Replacement vs Incremental Edit

- **Severity:** Minor
- **Description:** Step 2.1 shows the complete `SubscriptionList.tsx` component rather than incremental changes. This is actually helpful as a reference, but implementers should be aware they need to carefully merge with any other changes that may have occurred.
- **Suggested Action:** Consider extracting just the diff/additions needed if the component has been modified since plan creation.

#### 5. Consider Fallback for Unknown Change Types

- **Severity:** Minor
- **Description:** Step 2.2 has good fallback logic: `CHANGE_TYPE_STYLES[changeType] || CHANGE_TYPE_STYLES.CONTENT`. This handles unknown types gracefully. Good defensive coding.
- **Status:** No issue, just noting good practice.

## Strengths

1. **Comprehensive Phase 0** - Backend API updates are detailed with exact code locations and complete code snippets
2. **Proper separation of concerns** - Backend changes (Phase 0), type changes (Phase 1), and component changes (Phase 2) are logically separated
3. **Good helper function design** - `_create_subscription_from_request` consolidates subscription creation logic, avoiding code duplication
4. **Complete type definitions** - TypeScript types match backend schemas exactly
5. **Thorough test strategy** - Includes manual testing, mock repo scenarios, specific test cases, and edge cases
6. **Risk mitigations documented** - Identifies and addresses key risks like API schema mismatch and breaking existing line-based subscriptions
7. **Backwards compatibility** - All semantic fields are optional; existing line-based subscriptions continue to work
8. **Clear scope boundaries** - Symbol browser explicitly deferred with reasoning
9. **UPPERCASE change types** - Matches backend exactly, avoiding case mismatch bugs
10. **Semantic reason labels** - Comprehensive set covering all semantic change types

## Consistency Checks

### Backend Models vs Plan

Verified against `/Users/vlad/dev/projects/codesub/src/codesub/models.py`:
- `SemanticTarget` dataclass (lines 19-52): Plan's `SemanticTargetSchema` matches all fields
- `Subscription.semantic` field (line 90): Plan correctly adds this to API schema
- `Trigger.change_type` and `Trigger.details` (lines 261-262): Plan includes both in frontend

### Backend update_doc.py vs Plan

Verified against `/Users/vlad/dev/projects/codesub/src/codesub/update_doc.py`:
- `_trigger_to_dict` includes `change_type` and `details` (lines 51-54): Frontend types match
- `_proposal_to_dict` includes `new_qualname` and `new_kind` (lines 74-77): Frontend types match

### Existing Frontend Types vs Plan

Verified against `/Users/vlad/dev/projects/codesub/frontend/src/types.ts`:
- Current `Subscription` (lines 7-18): Plan adds `semantic: SemanticTarget | null`
- Current `Trigger` (lines 85-92): Plan adds `change_type`, `details`
- Current `Proposal` (lines 94-106): Plan adds `new_qualname`, `new_kind`

### utils.py Availability

Verified `parse_target_spec`, `LineTarget`, `SemanticTargetSpec` exist in `/Users/vlad/dev/projects/codesub/src/codesub/utils.py` (lines 11, 20, 28).

## Verdict

**PLAN APPROVED**

The plan is thorough, well-structured, and addresses all critical issues from the first review. All backend and frontend changes are correctly documented with proper code snippets. The phased approach ensures backend changes are complete before frontend implementation begins.

### Implementation Notes

1. **Phase 0 first**: Complete all backend API changes and run existing tests before proceeding
2. **Run `poetry run pytest`**: After Phase 0 to verify no regressions
3. **Run `npm run build`**: After Phase 1 to verify TypeScript compiles
4. **Test with mock_repo**: Use `task mock:init` to create test data with both subscription types
5. **Incremental testing**: Test each component update individually before proceeding

### Recommended Implementation Order

1. Step 0.1: Add SemanticTargetSchema and update SubscriptionSchema
2. Step 0.2: Add semantic subscription creation support
3. Step 0.3: Update documentation
4. Run backend tests
5. Step 1.1: Update TypeScript types
6. Run `npm run build`
7. Steps 2.1-2.5: Update components one by one, testing each

The plan is ready for implementation.
