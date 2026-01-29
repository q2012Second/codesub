# Problem Statement: Frontend Semantic Subscription Management

## Summary

The codesub project needs its React/TypeScript frontend updated to support **semantic subscriptions** - a new subscription type that tracks code constructs by identity (using Tree-sitter parsing) rather than just line numbers.

## Background

Codesub is a CLI tool that lets users "subscribe" to code sections and detect changes via git diff. It supports two subscription types:

1. **Line-based** (existing): Track line ranges (e.g., `config.py:10-25`)
2. **Semantic** (new): Track code constructs by identity (e.g., `auth.py::User.validate`)

The backend implementation for semantic subscriptions is complete. The frontend needs updates to display, create, and manage these new subscription types.

## Current State

### Backend (Complete)
- `Subscription` model has optional `semantic: SemanticTarget` field containing:
  - `language` - Programming language (e.g., "python")
  - `kind` - Construct type ("variable", "field", "method")
  - `qualname` - Qualified name (e.g., "Calculator.add")
  - `role` - Optional role (e.g., "const" for constants)
  - `interface_hash` / `body_hash` - Fingerprints for change detection

- `Trigger` model has `change_type` field with values:
  - `STRUCTURAL` - Interface/signature changed (breaking)
  - `CONTENT` - Value/body changed
  - `MISSING` - Construct deleted/not found
  - `AMBIGUOUS` - Multiple matches found
  - `PARSE_ERROR` - Failed to parse file

- `Proposal` model has `new_qualname` and `new_kind` for semantic renames

### Frontend (Needs Updates)
- `types.ts` - Missing TypeScript interfaces for semantic fields
- `SubscriptionList.tsx` - No distinction between line-based and semantic subscriptions
- `SubscriptionDetail.tsx` - No display of semantic target information
- `SubscriptionForm.tsx` - Only accepts line-based format
- `ScanView.tsx` - No styling for semantic change types
- `ApplyUpdatesModal.tsx` - No display of semantic rename proposals

## Requirements

### 1. Type Definitions
Update `frontend/src/types.ts` to include:
- `SemanticTarget` interface
- Optional `semantic` field on `Subscription`
- Optional `change_type` on `Trigger`
- Optional `new_qualname`/`new_kind` on `Proposal`

### 2. Subscription List View
- Display visual badge distinguishing semantic `[S]` from line-based `[L]`
- Show `qualname` and `kind` for semantic subscriptions
- Show `role` if present (e.g., "const")

### 3. Scan Results View
- Style `change_type` with appropriate colors:
  - `STRUCTURAL` - Warning/orange
  - `CONTENT` - Info/blue
  - `MISSING` - Error/red
- Display human-readable `details` field

### 4. Add Subscription Form
- Support semantic target format: `file.py::ClassName.method`
- Auto-detect format based on `::` presence
- Provide help text and examples

### 5. Subscription Detail View
- Show semantic target section with all fields
- Display fingerprint hashes

### 6. Apply Updates Modal
- Show rename proposals for semantic subscriptions

## Constraints

- Follow existing React/TypeScript patterns in the codebase
- Use Tailwind CSS classes consistent with existing components
- Backend API is fixed - adapt to existing response formats
- Handle edge cases (null semantic field, missing change_type)

## Success Criteria

1. Users can visually distinguish semantic from line-based subscriptions in the list
2. Users can create semantic subscriptions via the form
3. Scan results clearly show the type and severity of semantic changes
4. Subscription details display all semantic target information
5. Apply updates modal handles semantic rename proposals
