# Implementation Plan: Frontend Semantic Subscription Support

## Overview

Update the codesub React/TypeScript frontend to support semantic subscriptions. This requires backend API updates (Phase 0) before frontend changes (Phases 1-2) can proceed.

## Design Decisions

| Decision | Rationale |
|----------|-----------|
| Add `SemanticTarget` interface to types.ts | Matches backend model structure exactly |
| Display [S]/[L] badges in subscription list | Quick visual differentiation between subscription types |
| Auto-detect semantic format via `::` in location input | No need for mode toggle; semantic format is unambiguous |
| Color-code change_type: orange/blue/red | Follows standard severity conventions (warning/info/error) |
| Show semantic details in collapsed section | Keeps UI clean; hashes are technical details |
| Use UPPERCASE change_type values | Matches backend API (STRUCTURAL, CONTENT, MISSING) |
| Symbol browser out of scope | Deferred to Phase 2 - API endpoint not yet implemented |
| Backend API updates in Phase 0 | Critical prerequisite - frontend cannot work without these changes |

**User Requirements:**
- Support semantic subscriptions in all frontend views
- Show change_type with appropriate styling in scan results
- Allow creating semantic subscriptions via `file.py::ClassName.method` format

**Alternative Approaches Considered:**
- Radio button toggle for line-based vs semantic: Rejected because `::` format is self-documenting
- Separate create forms for each type: Rejected as unnecessary complexity
- Symbol browser in Phase 1: Deferred - requires new API endpoint

**Out of Scope for Phase 1:**
- Symbol browser UI (requires new `/api/projects/{id}/symbols` endpoint)
- Frontend validation for semantic target existence (backend handles this)

## Prerequisites

- Existing frontend structure with React + TypeScript
- Mock repository available via `task mock:init` for testing

## Implementation Steps

---

## Phase 0: Backend API Updates

### Step 0.1: Add SemanticTargetSchema to api.py

**Files:** `/Users/vlad/dev/projects/codesub/src/codesub/api.py`

**Changes:**
- Add `SemanticTargetSchema` Pydantic model after `AnchorSchema`
- Add `semantic` field to `SubscriptionSchema`
- Update `subscription_to_schema()` to convert `sub.semantic`
- Add `details` field to `TriggerSchema`

**Code:**

Add after `AnchorSchema` (around line 41):

```python
class SemanticTargetSchema(BaseModel):
    language: str  # "python"
    kind: str  # "variable"|"field"|"method"
    qualname: str  # "API_VERSION" | "User.role" | "Calculator.add"
    role: Optional[str] = None  # "const" for constants, None otherwise
    interface_hash: str = ""
    body_hash: str = ""
    fingerprint_version: int = 1
```

Update `SubscriptionSchema` (around line 43) to add semantic field:

```python
class SubscriptionSchema(BaseModel):
    id: str
    path: str
    start_line: int
    end_line: int
    label: Optional[str] = None
    description: Optional[str] = None
    anchors: Optional[AnchorSchema] = None
    semantic: Optional[SemanticTargetSchema] = None  # NEW
    active: bool = True
    created_at: str
    updated_at: str
```

Update `TriggerSchema` (around line 125) to add details field:

```python
class TriggerSchema(BaseModel):
    subscription_id: str
    path: str
    start_line: int
    end_line: int
    reasons: list[str]
    label: Optional[str]
    change_type: Optional[str] = None  # "STRUCTURAL"|"CONTENT"|"MISSING" for semantic subscriptions
    details: Optional[dict] = None  # NEW: Additional details for semantic triggers
```

Update `subscription_to_schema()` function (around line 219):

```python
def subscription_to_schema(sub: Subscription) -> SubscriptionSchema:
    """Convert dataclass Subscription to Pydantic schema."""
    anchors = None
    if sub.anchors:
        anchors = AnchorSchema(
            context_before=sub.anchors.context_before,
            lines=sub.anchors.lines,
            context_after=sub.anchors.context_after,
        )
    semantic = None
    if sub.semantic:
        semantic = SemanticTargetSchema(
            language=sub.semantic.language,
            kind=sub.semantic.kind,
            qualname=sub.semantic.qualname,
            role=sub.semantic.role,
            interface_hash=sub.semantic.interface_hash,
            body_hash=sub.semantic.body_hash,
            fingerprint_version=sub.semantic.fingerprint_version,
        )
    return SubscriptionSchema(
        id=sub.id,
        path=sub.path,
        start_line=sub.start_line,
        end_line=sub.end_line,
        label=sub.label,
        description=sub.description,
        anchors=anchors,
        semantic=semantic,
        active=sub.active,
        created_at=sub.created_at,
        updated_at=sub.updated_at,
    )
```

---

### Step 0.2: Support Semantic Subscription Creation in API

**Files:** `/Users/vlad/dev/projects/codesub/src/codesub/api.py`

**Changes:**
- Import `parse_target_spec`, `LineTarget`, `SemanticTargetSpec` from utils
- Import `SemanticTarget` from models
- Import `PythonIndexer` from semantic
- Update `create_subscription` endpoint to handle semantic targets
- Update `create_project_subscription` endpoint to handle semantic targets

**Code:**

Update imports (around line 26):

```python
from .utils import parse_location, extract_anchors, parse_target_spec, LineTarget, SemanticTargetSpec
from .models import Anchor, Subscription, SemanticTarget
```

Add helper function after `subscription_to_schema()` (around line 240):

```python
def _create_subscription_from_request(
    store: ConfigStore,
    repo: GitRepo,
    baseline: str,
    request: SubscriptionCreateRequest,
) -> Subscription:
    """Create a subscription from a request, handling both line-based and semantic targets."""
    from .semantic import PythonIndexer

    target = parse_target_spec(request.location)

    if isinstance(target, SemanticTargetSpec):
        # Semantic subscription
        lines = repo.show_file(baseline, target.path)
        source = "\n".join(lines)

        indexer = PythonIndexer()
        construct = indexer.find_construct(
            source, target.path, target.qualname, target.kind
        )
        if construct is None:
            raise InvalidLocationError(
                request.location,
                f"Construct '{target.qualname}' not found. Use 'codesub symbols' to discover valid targets."
            )

        # Extract anchors from construct lines
        context_before, watched_lines, context_after = extract_anchors(
            lines, construct.start_line, construct.end_line, context=request.context
        )
        anchors = Anchor(
            context_before=context_before,
            lines=watched_lines,
            context_after=context_after,
        )

        # Create semantic target
        semantic = SemanticTarget(
            language="python",
            kind=construct.kind,
            qualname=construct.qualname,
            role=construct.role,
            interface_hash=construct.interface_hash,
            body_hash=construct.body_hash,
        )

        return Subscription.create(
            path=target.path,
            start_line=construct.start_line,
            end_line=construct.end_line,
            label=request.label,
            description=request.description,
            anchors=anchors,
            semantic=semantic,
        )
    else:
        # Line-based subscription
        lines = repo.show_file(baseline, target.path)

        # Validate line range
        if target.end_line > len(lines):
            raise InvalidLineRangeError(
                target.start_line, target.end_line,
                f"exceeds file length ({len(lines)} lines)"
            )

        # Extract anchors
        context_before, watched_lines, context_after = extract_anchors(
            lines, target.start_line, target.end_line, context=request.context
        )
        anchors = Anchor(
            context_before=context_before,
            lines=watched_lines,
            context_after=context_after,
        )

        return Subscription.create(
            path=target.path,
            start_line=target.start_line,
            end_line=target.end_line,
            label=request.label,
            description=request.description,
            anchors=anchors,
        )
```

Update `create_subscription` endpoint (around line 321):

```python
@app.post("/api/subscriptions", response_model=SubscriptionSchema, status_code=201)
def create_subscription(request: SubscriptionCreateRequest):
    """Create a new subscription (line-based or semantic)."""
    store, repo = get_store_and_repo()
    config = store.load()
    baseline = config.repo.baseline_ref

    sub = _create_subscription_from_request(store, repo, baseline, request)
    store.add_subscription(sub)
    return subscription_to_schema(sub)
```

Update `create_project_subscription` endpoint (around line 516):

```python
@app.post("/api/projects/{project_id}/subscriptions", response_model=SubscriptionSchema, status_code=201)
def create_project_subscription(project_id: str, request: SubscriptionCreateRequest):
    """Create a new subscription in a specific project (line-based or semantic)."""
    store, repo = get_project_store_and_repo(project_id)
    config = store.load()
    baseline = config.repo.baseline_ref

    sub = _create_subscription_from_request(store, repo, baseline, request)
    store.add_subscription(sub)
    return subscription_to_schema(sub)
```

---

### Step 0.3: Update SubscriptionCreateRequest Documentation

**Files:** `/Users/vlad/dev/projects/codesub/src/codesub/api.py`

**Changes:**
- Update the location field description to document both formats

**Code:**

Update `SubscriptionCreateRequest` (around line 56):

```python
class SubscriptionCreateRequest(BaseModel):
    """Request body for creating a subscription."""

    location: str = Field(
        ...,
        description="Location format: 'path:line' or 'path:start-end' for line-based, "
                    "'path::QualName' or 'path::kind:QualName' for semantic"
    )
    label: Optional[str] = None
    description: Optional[str] = None
    context: int = Field(default=2, ge=0, le=10)
```

---

## Phase 1: Frontend Type Updates

### Step 1.1: Update TypeScript Types

**Files:** `/Users/vlad/dev/projects/codesub/frontend/src/types.ts`

**Changes:**
- Add `SemanticTarget` interface
- Add `semantic` field to `Subscription` interface
- Add `change_type` and `details` fields to `Trigger` interface
- Add `new_qualname` and `new_kind` fields to `Proposal` interface

**Code:**

```typescript
// Add after Anchor interface (line 5)
export interface SemanticTarget {
  language: string;       // "python"
  kind: string;           // "variable" | "field" | "method"
  qualname: string;       // "API_VERSION" | "User.role" | "Calculator.add"
  role?: string | null;   // "const" for constants, null otherwise
  interface_hash?: string;
  body_hash?: string;
  fingerprint_version?: number;
}

// Defensive union type accepting both cases (backend uses UPPERCASE, but be tolerant)
export type ChangeType =
  | 'STRUCTURAL' | 'CONTENT' | 'MISSING' | 'AMBIGUOUS' | 'PARSE_ERROR'
  | 'structural' | 'content' | 'missing' | 'ambiguous' | 'parse_error';

// Update Subscription interface to add semantic field after line 14 (anchors)
export interface Subscription {
  id: string;
  path: string;
  start_line: number;
  end_line: number;
  label: string | null;
  description: string | null;
  anchors: Anchor | null;
  semantic?: SemanticTarget | null;  // NEW: null/undefined for line-based subscriptions
  active: boolean;
  created_at: string;
  updated_at: string;
}

// Update Trigger interface to add change_type and details (around line 85)
export interface Trigger {
  subscription_id: string;
  path: string;
  start_line: number;
  end_line: number;
  reasons: string[];
  label: string | null;
  change_type?: ChangeType | null;  // NEW: semantic change classification
  details?: unknown;  // NEW: Additional semantic details (string, object, or null)
}

// Update Proposal interface to add new_qualname/new_kind (around line 94)
export interface Proposal {
  subscription_id: string;
  old_path: string;
  old_start: number;
  old_end: number;
  new_path: string;
  new_start: number;
  new_end: number;
  reasons: string[];
  confidence: string;
  shift: number | null;
  label: string | null;
  new_qualname: string | null;  // NEW: For semantic renames
  new_kind: string | null;      // NEW: For semantic kind changes
}
```

---

## Phase 2: Frontend Component Updates

### Step 2.1: Update SubscriptionList.tsx - Add Type Badges

**Files:** `/Users/vlad/dev/projects/codesub/frontend/src/components/SubscriptionList.tsx`

**Changes:**
- Add helper function to determine if subscription is semantic
- Add [S]/[L] badge in the Location column
- Display qualname for semantic subscriptions instead of line range

**Code:**

```typescript
import type { Subscription } from '../types';

interface Props {
  subscriptions: Subscription[];
  onSelect: (id: string) => void;
}

// Helper to check if subscription is semantic
function isSemantic(sub: Subscription): boolean {
  return sub.semantic !== null;
}

// Helper to format location display
function formatLocation(sub: Subscription): string {
  if (isSemantic(sub)) {
    return `${sub.path}::${sub.semantic!.qualname}`;
  }
  return sub.start_line === sub.end_line
    ? `${sub.path}:${sub.start_line}`
    : `${sub.path}:${sub.start_line}-${sub.end_line}`;
}

// Badge component for subscription type
function TypeBadge({ semantic }: { semantic: boolean }) {
  const style = {
    display: 'inline-block',
    padding: '1px 4px',
    borderRadius: 3,
    fontSize: 10,
    fontWeight: 600,
    marginRight: 6,
    background: semantic ? '#e3f2fd' : '#f5f5f5',
    color: semantic ? '#1565c0' : '#666',
    border: `1px solid ${semantic ? '#90caf9' : '#ddd'}`,
  };
  return <span style={style}>{semantic ? 'S' : 'L'}</span>;
}

export function SubscriptionList({ subscriptions, onSelect }: Props) {
  if (subscriptions.length === 0) {
    return <p style={{ color: '#666', padding: '20px 0' }}>No subscriptions found.</p>;
  }

  return (
    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
      <thead>
        <tr style={{ textAlign: 'left', borderBottom: '2px solid #ddd' }}>
          <th style={{ padding: '12px 8px' }}>ID</th>
          <th style={{ padding: '12px 8px' }}>Type</th>
          <th style={{ padding: '12px 8px' }}>Location</th>
          <th style={{ padding: '12px 8px' }}>Label</th>
          <th style={{ padding: '12px 8px' }}>Status</th>
        </tr>
      </thead>
      <tbody>
        {subscriptions.map((sub) => (
          <tr
            key={sub.id}
            onClick={() => onSelect(sub.id)}
            style={{
              cursor: 'pointer',
              borderBottom: '1px solid #eee',
              opacity: sub.active ? 1 : 0.6,
            }}
            onMouseEnter={(e) => (e.currentTarget.style.background = '#f9f9f9')}
            onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
          >
            <td style={{ padding: '12px 8px', fontFamily: 'monospace', fontSize: 13 }}>
              {sub.id.slice(0, 8)}
            </td>
            <td style={{ padding: '12px 8px' }}>
              <TypeBadge semantic={isSemantic(sub)} />
            </td>
            <td style={{ padding: '12px 8px', fontFamily: 'monospace', fontSize: 13 }}>
              {formatLocation(sub)}
            </td>
            <td style={{ padding: '12px 8px' }}>{sub.label || <span style={{ color: '#999' }}>-</span>}</td>
            <td style={{ padding: '12px 8px' }}>
              <span style={{
                padding: '2px 8px',
                borderRadius: 4,
                fontSize: 12,
                background: sub.active ? '#d4edda' : '#e9ecef',
                color: sub.active ? '#155724' : '#6c757d',
              }}>
                {sub.active ? 'active' : 'inactive'}
              </span>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
```

---

### Step 2.2: Update ScanView.tsx - Add Change Type Styling

**Files:** `/Users/vlad/dev/projects/codesub/frontend/src/components/ScanView.tsx`

**Changes:**
- Add change type styling constants (STRUCTURAL=orange, CONTENT=blue, MISSING=red) - UPPERCASE keys
- Add `ChangeTypeBadge` component for triggers
- Update trigger display to show change_type when present
- Update proposal display to show new_qualname for semantic renames
- Add semantic-specific reason labels

**Code:**

Add after existing REASON_LABELS constant (or create if not present):

```typescript
// Helper to normalize change_type casing (backend uses UPPERCASE, tolerate lowercase)
function normalizeChangeType(ct?: string | null): string | undefined {
  if (!ct) return undefined;
  return ct.toUpperCase();
}

// Helper to format details (can be string, object, or null)
function formatDetails(details: unknown): string {
  if (details == null) return '';
  if (typeof details === 'string') return details;
  try { return JSON.stringify(details, null, 2); } catch { return String(details); }
}

// Change type styling for semantic subscriptions (UPPERCASE keys after normalization)
const CHANGE_TYPE_STYLES: Record<string, { bg: string; border: string; color: string; label: string }> = {
  STRUCTURAL: { bg: '#fff3e0', border: '#ffcc80', color: '#e65100', label: 'STRUCTURAL' },
  CONTENT: { bg: '#e3f2fd', border: '#90caf9', color: '#1565c0', label: 'CONTENT' },
  MISSING: { bg: '#ffebee', border: '#ef9a9a', color: '#c62828', label: 'MISSING' },
  AMBIGUOUS: { bg: '#fce4ec', border: '#f48fb1', color: '#ad1457', label: 'AMBIGUOUS' },
  PARSE_ERROR: { bg: '#f3e5f5', border: '#ce93d8', color: '#7b1fa2', label: 'PARSE ERROR' },
};

// Update REASON_LABELS to include semantic reasons
const REASON_LABELS: Record<string, string> = {
  overlap_hunk: 'Lines in range were modified',
  insert_inside_range: 'New lines inserted inside range',
  file_deleted: 'File was deleted',
  line_shift: 'Lines shifted due to changes above',
  rename: 'File was renamed or moved',
  // Semantic reasons
  semantic_content: 'Content/body changed',
  semantic_structural: 'Type/signature changed',
  semantic_missing: 'Construct deleted or not found',
  semantic_location: 'Construct moved to different location',
  semantic_rename: 'Construct was renamed',
};
```

Add ChangeTypeBadge component:

```typescript
function ChangeTypeBadge({ changeType }: { changeType: string | null }) {
  if (!changeType) return null;

  const style = CHANGE_TYPE_STYLES[changeType] || CHANGE_TYPE_STYLES.CONTENT;

  return (
    <span style={{
      display: 'inline-block',
      padding: '2px 6px',
      borderRadius: 3,
      fontSize: 10,
      fontWeight: 600,
      marginLeft: 8,
      background: style.bg,
      color: style.color,
      border: `1px solid ${style.border}`,
    }}>
      {style.label}
    </span>
  );
}
```

Update trigger card rendering:

```typescript
{result.triggers.map((t: Trigger, idx: number) => {
  // Normalize and determine card styling based on change_type
  const ct = normalizeChangeType(t.change_type);
  const changeStyle = ct ? CHANGE_TYPE_STYLES[ct] : null;

  const cardStyle = changeStyle ? {
    padding: 12,
    border: `1px solid ${changeStyle.border}`,
    background: changeStyle.bg,
    color: changeStyle.color,
    borderRadius: 4,
    marginBottom: 8,
  } : {
    padding: 12,
    border: '1px solid #f5c6cb',
    background: '#f8d7da',
    color: '#721c24',
    borderRadius: 4,
    marginBottom: 8,
  };

  return (
    <div key={idx} style={cardStyle}>
      <div style={{ fontWeight: 500, display: 'flex', alignItems: 'center' }}>
        {ct && <span>[{ct}] </span>}
        {t.label || t.subscription_id.slice(0, 8)}
      </div>
      <div style={{ fontSize: 13, fontFamily: 'monospace' }}>
        {t.path}:{t.start_line}-{t.end_line}
      </div>
      <div style={{ fontSize: 12, marginTop: 4 }}>
        {formatReasons(t.reasons)}
      </div>
      {t.details != null && (
        <pre style={{
          marginTop: 8,
          padding: 8,
          background: 'rgba(255,255,255,0.6)',
          borderRadius: 4,
          overflowX: 'auto',
          fontSize: 12,
        }}>
          {formatDetails(t.details)}
        </pre>
      )}
    </div>
  );
})}
```

Update proposal card rendering:

```typescript
{result.proposals.map((p: Proposal) => {
  const hasSemanticRename = p.new_qualname !== null;

  return (
    <div
      key={p.subscription_id}
      style={{
        padding: 12,
        border: '1px solid #ffeeba',
        background: '#fff3cd',
        borderRadius: 4,
        marginBottom: 8,
      }}
    >
      <div style={{ fontWeight: 500 }}>
        {p.label || p.subscription_id.slice(0, 8)}
      </div>
      <div style={{ fontSize: 13, fontFamily: 'monospace' }}>
        {p.old_path}:{p.old_start}-{p.old_end}
        {' -> '}
        {p.new_path}:{p.new_start}-{p.new_end}
      </div>
      {hasSemanticRename && (
        <div style={{ fontSize: 13, fontFamily: 'monospace', color: '#856404', marginTop: 4 }}>
          Rename: {p.new_qualname}
          {p.new_kind && ` (${p.new_kind})`}
        </div>
      )}
      <div style={{ fontSize: 12, color: '#666', marginTop: 4 }}>
        {formatReasons(p.reasons)}
        {p.shift !== null && ` (${p.shift > 0 ? '+' : ''}${p.shift} lines)`}
      </div>
    </div>
  );
})}
```

---

### Step 2.3: Update SubscriptionForm.tsx - Support Semantic Target Format

**Files:** `/Users/vlad/dev/projects/codesub/frontend/src/components/SubscriptionForm.tsx`

**Changes:**
- Update location help text to include semantic format
- Add format detection hint based on user input

**Code:**

Update the location input section:

```typescript
{!isEdit && (
  <div style={{ marginBottom: 20 }}>
    <label style={{ display: 'block', marginBottom: 6, fontWeight: 600 }}>
      Location <span style={{ color: '#dc3545' }}>*</span>
    </label>
    <input
      type="text"
      value={location}
      onChange={e => setLocation(e.target.value)}
      placeholder="path/to/file.py:42 or path/to/file.py::ClassName.method"
      required
      style={{ width: '100%', fontFamily: 'monospace' }}
    />
    <small style={{ color: '#666', display: 'block', marginTop: 4 }}>
      <strong>Line-based:</strong> path:line or path:start-end (e.g., config.py:10-25)
      <br />
      <strong>Semantic:</strong> path::QualifiedName (e.g., auth.py::User.validate)
    </small>
    {location.includes('::') && (
      <div style={{
        marginTop: 8,
        padding: '8px 12px',
        background: '#e3f2fd',
        borderRadius: 4,
        fontSize: 13,
        color: '#1565c0'
      }}>
        Semantic subscription detected - will track code construct by identity
      </div>
    )}
  </div>
)}
```

---

### Step 2.4: Update SubscriptionDetail.tsx - Show Semantic Target Information

**Files:** `/Users/vlad/dev/projects/codesub/frontend/src/components/SubscriptionDetail.tsx`

**Changes:**
- Add semantic target section when `sub.semantic` is present
- Show kind, qualname, role, and fingerprint hashes
- Update location display to show semantic format when applicable

**Code:**

Update the location variable and add semantic check:

```typescript
const isSemantic = sub.semantic !== null;
const location = isSemantic
  ? `${sub.path}::${sub.semantic!.qualname}`
  : sub.start_line === sub.end_line
    ? `${sub.path}:${sub.start_line}`
    : `${sub.path}:${sub.start_line}-${sub.end_line}`;
```

Add type badge after the Location row in the dl:

```typescript
<dt style={{ fontWeight: 600, color: '#555' }}>Type:</dt>
<dd>
  <span style={{
    display: 'inline-block',
    padding: '2px 6px',
    borderRadius: 3,
    fontSize: 11,
    fontWeight: 600,
    background: isSemantic ? '#e3f2fd' : '#f5f5f5',
    color: isSemantic ? '#1565c0' : '#666',
    border: `1px solid ${isSemantic ? '#90caf9' : '#ddd'}`,
  }}>
    {isSemantic ? 'Semantic' : 'Line-based'}
  </span>
</dd>
```

Add semantic target section after the type row:

```typescript
{isSemantic && sub.semantic && (
  <>
    <dt style={{ fontWeight: 600, color: '#555' }}>Kind:</dt>
    <dd style={{ textTransform: 'capitalize' }}>
      {sub.semantic.kind}
      {sub.semantic.role && (
        <span style={{
          marginLeft: 8,
          fontSize: 11,
          color: '#666',
          background: '#f5f5f5',
          padding: '1px 4px',
          borderRadius: 3,
        }}>
          {sub.semantic.role}
        </span>
      )}
    </dd>

    <dt style={{ fontWeight: 600, color: '#555' }}>Qualified Name:</dt>
    <dd style={{ fontFamily: 'monospace', fontSize: 13 }}>{sub.semantic.qualname}</dd>

    <dt style={{ fontWeight: 600, color: '#555' }}>Language:</dt>
    <dd style={{ textTransform: 'capitalize' }}>{sub.semantic.language}</dd>
  </>
)}
```

Add fingerprint details as a collapsible section after the main dl:

```typescript
{isSemantic && sub.semantic && (
  <details style={{ marginTop: 16 }}>
    <summary style={{ cursor: 'pointer', fontWeight: 600, color: '#555', fontSize: 14 }}>
      Fingerprint Details
    </summary>
    <div style={{ marginTop: 8, padding: 12, background: '#fff', border: '1px solid #e9ecef', borderRadius: 4 }}>
      <dl style={{ display: 'grid', gridTemplateColumns: 'auto 1fr', gap: '8px 16px', margin: 0 }}>
        <dt style={{ fontWeight: 500, color: '#666', fontSize: 13 }}>Interface Hash:</dt>
        <dd style={{ fontFamily: 'monospace', fontSize: 12, color: '#333' }}>{sub.semantic.interface_hash || '-'}</dd>

        <dt style={{ fontWeight: 500, color: '#666', fontSize: 13 }}>Body Hash:</dt>
        <dd style={{ fontFamily: 'monospace', fontSize: 12, color: '#333' }}>{sub.semantic.body_hash || '-'}</dd>

        <dt style={{ fontWeight: 500, color: '#666', fontSize: 13 }}>Fingerprint Version:</dt>
        <dd style={{ fontFamily: 'monospace', fontSize: 12, color: '#333' }}>{sub.semantic.fingerprint_version}</dd>
      </dl>
    </div>
  </details>
)}
```

Update the "Lines watched" row to be conditional (only show for line-based):

```typescript
{!isSemantic && (
  <>
    <dt style={{ fontWeight: 600, color: '#555' }}>Lines watched:</dt>
    <dd>{sub.end_line - sub.start_line + 1}</dd>
  </>
)}
```

---

### Step 2.5: Update ApplyUpdatesModal.tsx - Show Semantic Rename Proposals

**Files:** `/Users/vlad/dev/projects/codesub/frontend/src/components/ApplyUpdatesModal.tsx`

**Changes:**
- Show new_qualname when present in proposal
- Add visual indicator for semantic renames vs line shifts

**Code:**

Update the proposal label in the map:

```typescript
{proposals.map(p => {
  const hasSemanticRename = p.new_qualname !== null;
  const hasLineChange = p.old_start !== p.new_start || p.old_end !== p.new_end;
  const hasPathChange = p.old_path !== p.new_path;

  return (
    <label
      key={p.subscription_id}
      style={{
        display: 'flex',
        alignItems: 'flex-start',
        gap: 8,
        padding: 8,
        border: '1px solid #ddd',
        borderRadius: 4,
        marginBottom: 4,
        cursor: 'pointer',
      }}
    >
      <input
        type="checkbox"
        checked={selected.has(p.subscription_id)}
        onChange={() => toggleSelect(p.subscription_id)}
      />
      <div style={{ flex: 1 }}>
        <div style={{ fontWeight: 500, display: 'flex', alignItems: 'center', gap: 8 }}>
          {p.label || p.subscription_id.slice(0, 8)}
          {hasSemanticRename && (
            <span style={{
              fontSize: 10,
              padding: '1px 4px',
              borderRadius: 3,
              background: '#e3f2fd',
              color: '#1565c0',
              border: '1px solid #90caf9',
            }}>
              RENAME
            </span>
          )}
        </div>

        {/* Line/path changes */}
        {(hasLineChange || hasPathChange) && (
          <div style={{ fontSize: 12, fontFamily: 'monospace', color: '#666' }}>
            {p.old_path}:{p.old_start}-{p.old_end}
            {' -> '}
            {p.new_path}:{p.new_start}-{p.new_end}
          </div>
        )}

        {/* Semantic rename */}
        {hasSemanticRename && (
          <div style={{ fontSize: 12, fontFamily: 'monospace', color: '#1565c0', marginTop: 2 }}>
            Rename to: {p.new_qualname}
            {p.new_kind && ` (${p.new_kind})`}
          </div>
        )}
      </div>
    </label>
  );
})}
```

---

## Testing Strategy

### Component-Level Tests (React Testing Library)

| Component | Test Case | Expected Result |
|-----------|-----------|-----------------|
| SubscriptionList | `semantic: null` | Badge shows "L", no qualname |
| SubscriptionList | `semantic: { qualname: 'User.validate', kind: 'method' }` | Badge shows "S", qualname + kind displayed |
| SubscriptionList | `semantic.role = 'const'` | "const" pill badge appears |
| SubscriptionDetail | `semantic: null` | No "Semantic Target" section |
| SubscriptionDetail | `semantic` populated | Shows Language, Kind, QualName, hashes |
| SubscriptionForm | location = `auth.py::User.validate` | "Detected: semantic subscription" hint |
| SubscriptionForm | location = `auth.py:10-20` | "Detected: line-based subscription" hint |
| ScanView | `change_type: 'STRUCTURAL'` | Warning/orange background |
| ScanView | `change_type: 'CONTENT'` | Info/blue background |
| ScanView | `change_type: 'MISSING'` | Error/red background |
| ScanView | `change_type: 'structural'` (lowercase) | Normalizes to STRUCTURAL, warning style |
| ScanView | `details: { from: "str", to: "str \| None" }` | Renders `<pre>` with JSON |
| ApplyUpdatesModal | `new_qualname: 'NewClass.method'` | Shows "RENAME" badge + qualname |

### Manual Testing

- [ ] **Backend API tests**: Test `/api/subscriptions` returns `semantic` field for semantic subs
- [ ] **Backend create test**: POST semantic location format, verify subscription created
- [ ] **types.ts compilation**: Run `npm run build` to verify TypeScript compiles without errors
- [ ] **List view badges**: Open subscription list, verify [S] and [L] badges display correctly
- [ ] **Semantic location display**: Verify semantic subscriptions show `file.py::QualName` format
- [ ] **Create semantic subscription**: Use `path/to/file.py::ClassName.method` format, verify detection hint appears
- [ ] **Detail view semantic section**: View a semantic subscription, verify kind/qualname/hashes display
- [ ] **Scan with semantic changes**: Modify a tracked construct, run scan, verify change_type badge appears
- [ ] **Change type colors**: Verify STRUCTURAL=orange, CONTENT=blue, MISSING=red styling
- [ ] **Apply semantic rename**: Apply a proposal with new_qualname, verify RENAME badge appears
- [ ] **Mixed subscriptions**: Verify line-based and semantic subscriptions work together

### Test Scenarios with Mock Repo

1. **Setup**: Run `task mock:init` to create test subscriptions
2. **View list**: Navigate to mock_repo project, verify both [S] and [L] subscriptions visible
3. **Create semantic**: Add `advanced_types.py::Calculator.add` subscription via frontend
4. **Trigger content change**: Modify `Calculator.add` body, commit, scan - expect CONTENT badge
5. **Trigger structural change**: Change `Calculator.add` signature, commit, scan - expect STRUCTURAL badge
6. **Trigger missing**: Delete a tracked method, commit, scan - expect MISSING badge

### Specific Test Cases

| Test Case | Expected Result |
|-----------|-----------------|
| Create subscription with `config.py::API_VERSION` | Semantic subscription created, kind=variable |
| Create subscription with `auth.py::User.validate` | Semantic subscription created, kind=method |
| Create subscription with `models.py::User.email` | Semantic subscription created, kind=field |
| View semantic subscription detail | Shows Kind, Qualified Name, Language, Fingerprints |
| Scan detects body change in semantic sub | Trigger with change_type=CONTENT |
| Scan detects signature change | Trigger with change_type=STRUCTURAL |
| Scan detects deleted construct | Trigger with change_type=MISSING |
| Apply proposal with qualname rename | Shows RENAME badge, updates subscription |

### Edge Cases Considered

| Edge Case | Handling |
|-----------|----------|
| `semantic` field is null | Check `sub.semantic !== null` before accessing |
| `change_type` is null | `ChangeTypeBadge` returns null, falls back to default trigger styling |
| `new_qualname` is null | Semantic rename section not shown |
| Empty interface_hash/body_hash | Display `-` placeholder |
| Mixed semantic and line-based in same scan | Each uses appropriate styling independently |
| Very long qualname | CSS word-break handles overflow |
| Invalid semantic target on create | Backend returns 400 with helpful error message |

---

## Risks and Mitigations

- **Risk:** API schema mismatch between frontend types and backend response
  **Mitigation:** Types match backend models.py exactly; test with real API responses

- **Risk:** Breaking existing line-based subscription display
  **Mitigation:** All semantic-specific UI is conditional on `semantic !== null`; existing behavior unchanged when field is absent

- **Risk:** Performance with many semantic subscriptions
  **Mitigation:** No additional API calls; all data comes in existing responses

- **Risk:** Backend changes break existing tests
  **Mitigation:** Run full test suite after Phase 0 changes

---

## File Summary

| File | Phase | Changes |
|------|-------|---------|
| `src/codesub/api.py` | 0 | Add SemanticTargetSchema, update SubscriptionSchema, add _create_subscription_from_request helper, update create endpoints |
| `frontend/src/types.ts` | 1 | Add SemanticTarget interface, extend Subscription/Trigger/Proposal |
| `frontend/src/components/SubscriptionList.tsx` | 2 | Add Type column with [S]/[L] badges, update location format |
| `frontend/src/components/ScanView.tsx` | 2 | Add ChangeTypeBadge, change_type styling (UPPERCASE), semantic reason labels |
| `frontend/src/components/SubscriptionForm.tsx` | 2 | Update help text, add semantic format detection hint |
| `frontend/src/components/SubscriptionDetail.tsx` | 2 | Add semantic target section with kind/qualname/fingerprints |
| `frontend/src/components/ApplyUpdatesModal.tsx` | 2 | Show RENAME badge and new_qualname for semantic proposals |
