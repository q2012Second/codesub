# Frontend Changes for Semantic Subscriptions

## Overview

Semantic subscriptions track code constructs (functions, classes, methods, variables) by identity rather than just line numbers. The backend is complete; the frontend needs updates to display these new capabilities.

## New Model Fields

### Subscription (extended)

```typescript
interface Subscription {
  id: string;
  path: string;
  start_line: number;
  end_line: number;
  active: boolean;
  label?: string;
  anchors: Anchor;
  created_at: string;
  updated_at: string;

  // NEW: Semantic target (null for line-based subscriptions)
  semantic?: {
    language: string;       // "python"
    kind: string;           // "variable" | "field" | "method"
    qualname: string;       // "API_VERSION" | "User.role" | "Calculator.add"
    role?: string;          // "const" for constants, null otherwise
    interface_hash: string; // Hash of type/signature
    body_hash: string;      // Hash of value/body
    fingerprint_version: number;
  };
}
```

### Trigger (extended)

```typescript
interface Trigger {
  subscription: Subscription;
  reasons: string[];        // ["content_changed", "lines_shifted", ...]
  old_lines?: [number, number];
  new_lines?: [number, number];

  // NEW: Semantic change classification
  change_type?: "structural" | "content" | "missing";
  details?: string;         // Human-readable explanation
}
```

### Proposal (extended)

```typescript
interface Proposal {
  subscription_id: string;
  action: "update" | "deactivate";
  new_start_line?: number;
  new_end_line?: number;
  new_anchors?: Anchor;
  reason: string;

  // NEW: For semantic renames
  new_qualname?: string;
  new_kind?: string;
}
```

## Change Types Explained

| Type | Meaning | Example |
|------|---------|---------|
| `structural` | Interface/signature changed | Type annotation changed, method params changed |
| `content` | Value/body changed | Constant value changed, function body changed |
| `missing` | Construct deleted/not found | Function was removed |

## Frontend Display Requirements

### 1. Subscription List View

For semantic subscriptions, display:
- Icon/badge indicating semantic type (vs line-based)
- The `qualname` (e.g., "Calculator.add")
- The `kind` (variable/field/method)
- Optionally show `role` if "const"

Example display:
```
[S] Calculator.add (method)          advanced_types.py:331-334
[S] API_VERSION (const variable)     advanced_types.py:29
[L] Database Config                  config.py:10-14
```

Where `[S]` = semantic, `[L]` = line-based

### 2. Scan Results View

For triggered semantic subscriptions, display:
- The `change_type` with appropriate styling:
  - `structural` - Warning/orange (breaking change)
  - `content` - Info/blue (value changed)
  - `missing` - Error/red (deleted)
- The `details` field if present
- For proposals with `new_qualname`, show rename suggestion

Example:
```
TRIGGERED:
  [STRUCTURAL] UserDict.email - Type changed from 'str' to 'str | None'
  [CONTENT] API_VERSION - Value changed
  [MISSING] Calculator.divide - Construct not found
```

### 3. Add Subscription Dialog

Support two modes:
1. **Line-based** (existing): `file.py:10-20`
2. **Semantic** (new): `file.py::ClassName.method`

Could add a toggle or auto-detect based on `::` in the target.

### 4. Subscription Detail View

For semantic subscriptions, show additional section:
```
Semantic Target:
  Language: python
  Kind: method
  Qualified Name: Calculator.add
  Interface Hash: 3e7a53058a210ede
  Body Hash: 033599a131127365
```

## API Endpoints (unchanged)

All existing endpoints work with semantic subscriptions:
- `GET /api/subscriptions` - Returns subscriptions with `semantic` field
- `POST /api/subscriptions` - Accepts semantic target via FQN format
- `POST /api/projects/{id}/scan` - Returns triggers with `change_type`

## Files to Modify

```
frontend/src/
├── types/           # Add semantic fields to TypeScript interfaces
├── components/
│   ├── SubscriptionList.tsx    # Show semantic badge/icon
│   ├── SubscriptionCard.tsx    # Display semantic details
│   ├── ScanResults.tsx         # Show change_type styling
│   └── AddSubscription.tsx     # Support semantic target input
└── api/             # Types should auto-update from backend
```

## Testing

Use `task mock:init` to create sample semantic subscriptions, then:
1. View subscription list - verify semantic ones display correctly
2. Make a change to `mock_repo/advanced_types.py`
3. Commit and run scan
4. Verify trigger shows `change_type` and `details`
