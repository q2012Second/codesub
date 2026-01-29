# Frontend Semantic Subscription Management - External Chat Package

## Instructions

1. Copy the prompt below into Claude.ai or ChatGPT
2. Attach `chat-context.txt` as a file (or paste its contents)
3. Get the implementation plan response
4. Save the response to `tasks/frontend-semantic-subscription-management/plan.md`
5. Return here and continue with plan review

---

## Files in this package

- `chat-prompt.md` - The prompt to send to external LLM
- `chat-context.txt` - Source code context (24K tokens)
- `chat-combined.md` - This file

---

# PROMPT TO COPY:

# Task: Frontend Semantic Subscription Management

## Problem Statement

The codesub project has a working backend for **semantic subscriptions** - a feature that tracks code constructs (functions, classes, methods, variables) by identity using Tree-sitter parsing, rather than just line numbers. The frontend needs to be updated to display, create, and manage these semantic subscriptions.

Currently, the frontend only supports line-based subscriptions (e.g., `config.py:10-25`). It needs to be extended to support semantic subscriptions (e.g., `auth.py::User.validate`).

## Current State

### Backend (Complete)
- `Subscription` model has optional `semantic: SemanticTarget` field with:
  - `language` (e.g., "python")
  - `kind` (e.g., "variable", "field", "method")
  - `qualname` (e.g., "API_VERSION", "User.role", "Calculator.add")
  - `role` (e.g., "const" for constants)
  - `interface_hash` and `body_hash` for change detection
- `Trigger` model has `change_type` field: `STRUCTURAL`, `CONTENT`, `MISSING`, `AMBIGUOUS`, `PARSE_ERROR`
- `Proposal` model has `new_qualname` and `new_kind` for semantic renames
- API already returns these fields via `SubscriptionSchema`, `TriggerSchema`, `ProposalSchema`

### Frontend (Needs Updates)
- `types.ts`: Missing `semantic` field on Subscription, `change_type` on Trigger
- `SubscriptionList.tsx`: Only shows line-based locations, no semantic badges
- `SubscriptionDetail.tsx`: Only displays line ranges, no semantic target info
- `SubscriptionForm.tsx`: Only accepts line-based format (`path:line-range`)
- `ScanView.tsx`: Shows generic reasons, no `change_type` styling
- `ApplyUpdatesModal.tsx`: Doesn't show `new_qualname`/`new_kind` for semantic proposals

## Desired State

### 1. TypeScript Types (`types.ts`)
- Add `SemanticTarget` interface
- Add optional `semantic?: SemanticTarget` to `Subscription`
- Add optional `change_type?: 'structural' | 'content' | 'missing'` to `Trigger`
- Add optional `new_qualname?: string` and `new_kind?: string` to `Proposal`

### 2. Subscription List View (`SubscriptionList.tsx`)
- Display badge/icon distinguishing semantic `[S]` from line-based `[L]`
- For semantic: show `qualname` and `kind`, optionally `role` if "const"
- Example: `[S] Calculator.add (method)  advanced_types.py:331-334`

### 3. Scan Results View (`ScanView.tsx`)
- Show `change_type` with appropriate styling:
  - `STRUCTURAL` - Warning/orange (breaking change)
  - `CONTENT` - Info/blue (value changed)
  - `MISSING` - Error/red (deleted)
- Display `details` field if present
- Example: `[STRUCTURAL] UserDict.email - Type changed from 'str' to 'str | None'`

### 4. Add Subscription Form (`SubscriptionForm.tsx`)
- Support two input formats:
  1. Line-based: `file.py:10-20` (existing)
  2. Semantic: `file.py::ClassName.method` (new)
- Auto-detect based on `::` presence
- Update help text/examples

### 5. Subscription Detail View (`SubscriptionDetail.tsx`)
- For semantic subscriptions, show additional section:
  ```
  Semantic Target:
    Language: python
    Kind: method
    Qualified Name: Calculator.add
    Interface Hash: 3e7a53058a210ede
    Body Hash: 033599a131127365
  ```

### 6. Apply Updates Modal (`ApplyUpdatesModal.tsx`)
- For proposals with `new_qualname`, show rename suggestion

## Constraints

- Follow existing React/TypeScript patterns in the codebase
- Use Tailwind CSS classes consistent with existing components
- Minimize changes while fully solving the problem
- Backend API is fixed - frontend must adapt to existing response formats
- Consider edge cases (null semantic field, missing change_type, etc.)

## Codebase Context

The attached file `chat-context.txt` contains the relevant source code.

Key files included:

**Frontend:**
1. `frontend/src/types.ts` - TypeScript interfaces to update
2. `frontend/src/api.ts` - API client (may need type updates)
3. `frontend/src/components/SubscriptionList.tsx` - List view component
4. `frontend/src/components/SubscriptionDetail.tsx` - Detail view component
5. `frontend/src/components/SubscriptionForm.tsx` - Add/edit form
6. `frontend/src/components/ScanView.tsx` - Scan results display
7. `frontend/src/components/ApplyUpdatesModal.tsx` - Apply proposals modal
8. `frontend/src/components/ScanHistoryList.tsx` - Scan history
9. `frontend/src/App.tsx` - Main app component

**Backend (Reference):**
10. `src/codesub/models.py` - Data models with semantic fields
11. `src/codesub/api.py` - API schemas showing response structure
12. `src/codesub/detector.py` - Change type logic
13. `src/codesub/update_doc.py` - JSON serialization

**Requirements:**
14. `tasks/semantic-subscriptions/frontend-todo.md` - Detailed requirements

## Your Task

Create a detailed, step-by-step implementation plan that:

1. **Follows existing patterns** - Match the coding style and architecture in the context
2. **Is specific** - Include exact file paths, function names, and code snippets
3. **Handles edge cases** - Consider null/undefined semantic fields, backward compatibility
4. **Includes testing** - Define test cases for the implementation

## Expected Output Format

```markdown
# Implementation Plan: Frontend Semantic Subscription Management

## Overview
[Brief description]

## Prerequisites
- [Any setup needed]

## Implementation Steps

### Step 1: [Title]
**File:** `path/to/file.ts`
**Changes:**
- [Specific change with code snippet]

### Step 2: [Title]
...

## Testing Strategy
- [ ] [Test case 1]
- [ ] [Test case 2]

## Edge Cases
- [Edge case]: [How it's handled]

## Risks & Mitigations
- **Risk:** [Description]
  **Mitigation:** [Solution]
```
