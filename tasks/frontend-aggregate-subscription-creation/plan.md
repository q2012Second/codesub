## Implementation Plan: Frontend Aggregate Subscription Support (Revised)

### Overview
Enhance the frontend to fully support container/aggregate subscriptions. This revision incorporates critical feedback from external review.

### Critical Insight from External Review
The original plan added `kind` to `CodeBrowserSelection` but only used it for UI gating. The location string sent to backend (`construct.target`) still lacked kind, making backend construct resolution potentially ambiguous. The backend already supports `path::kind:qualname` format - we just need to use it.

### Design Decisions (Updated)

| Decision | Rationale |
|----------|-----------|
| **Include kind in target string** | Backend supports `path::kind:qualname`; ensures unambiguous construct identity |
| Backend fix first | Frontend depends on API returning container fields |
| Support edit flow for trigger_on_duplicate | Backend already supports PATCH; frontend should too |
| Use explicit booleans (not `\|\| undefined`) | Allows toggling options off in update flows |
| Don't silently reset options | Parse location to infer kind; warn user instead of data loss |
| Single source for CONTAINER_KINDS | Import from types.ts everywhere; avoid drift |
| Display kind in location strings | Consistency across UI (detail, list, form) |

### Implementation Steps

#### Step 1: Backend - Include kind in ConstructSchema.target
**File:** `/Users/vlad/dev/projects/codesub/src/codesub/api.py`
**Complexity:** Low
**Rationale:** Critical fix - enables unambiguous construct selection.

**Changes:**
- Update target format from `f"{path}::{c.qualname}"` to `f"{path}::{c.kind}:{c.qualname}"`

**Code:**
```python
# Around line 1236, change:
target=f"{path}::{c.qualname}",
# To:
target=f"{path}::{c.kind}:{c.qualname}",
```

---

#### Step 2: Backend - Fix subscription_to_schema
**File:** `/Users/vlad/dev/projects/codesub/src/codesub/api.py`
**Complexity:** Low

**Changes:**
- Include container tracking fields when converting SemanticTarget to schema

**Code:**
```python
# Update subscription_to_schema function (around line 359)
    semantic = None
    if sub.semantic:
        # Convert baseline_members if present
        baseline_members = None
        if sub.semantic.baseline_members:
            baseline_members = {
                k: MemberFingerprintSchema(
                    kind=v.kind,
                    interface_hash=v.interface_hash,
                    body_hash=v.body_hash,
                )
                for k, v in sub.semantic.baseline_members.items()
            }

        semantic = SemanticTargetSchema(
            language=sub.semantic.language,
            kind=sub.semantic.kind,
            qualname=sub.semantic.qualname,
            role=sub.semantic.role,
            interface_hash=sub.semantic.interface_hash,
            body_hash=sub.semantic.body_hash,
            fingerprint_version=sub.semantic.fingerprint_version,
            include_members=sub.semantic.include_members,
            include_private=sub.semantic.include_private,
            track_decorators=sub.semantic.track_decorators,
            baseline_members=baseline_members,
            baseline_container_qualname=sub.semantic.baseline_container_qualname,
        )
```

---

#### Step 3: Update TypeScript Types
**File:** `/Users/vlad/dev/projects/codesub/frontend/src/types.ts`
**Complexity:** Low

**Changes:**
- Add `MemberFingerprint` interface
- Add container tracking fields to `SemanticTarget`
- Add `trigger_on_duplicate` to `Subscription` interface
- Add configuration fields to `SubscriptionCreateRequest`
- Add `trigger_on_duplicate` to `SubscriptionUpdateRequest` (for edit support)
- Add `CONTAINER_KINDS` constant and `isContainerKind` helper
- Update `CodeBrowserSelection` to include `kind`

**Code:**
```typescript
// Add after Anchor interface
export interface MemberFingerprint {
  kind: string;
  interface_hash: string;
  body_hash: string;
}

// Update SemanticTarget interface
export interface SemanticTarget {
  language: string;
  kind: string;
  qualname: string;
  role?: string | null;
  interface_hash?: string;
  body_hash?: string;
  fingerprint_version?: number;
  // Container tracking fields
  include_members?: boolean;
  include_private?: boolean;
  track_decorators?: boolean;
  baseline_members?: Record<string, MemberFingerprint> | null;
  baseline_container_qualname?: string | null;
}

// Update Subscription interface - add trigger_on_duplicate
export interface Subscription {
  id: string;
  path: string;
  start_line: number;
  end_line: number;
  label: string | null;
  description: string | null;
  anchors: Anchor | null;
  semantic?: SemanticTarget | null;
  active: boolean;
  trigger_on_duplicate: boolean;
  created_at: string;
  updated_at: string;
}

// Update SubscriptionCreateRequest interface
export interface SubscriptionCreateRequest {
  location: string;
  label?: string;
  description?: string;
  context?: number;
  trigger_on_duplicate?: boolean;
  include_members?: boolean;
  include_private?: boolean;
  track_decorators?: boolean;
}

// Update SubscriptionUpdateRequest to support editing trigger_on_duplicate
export interface SubscriptionUpdateRequest {
  label?: string;
  description?: string;
  trigger_on_duplicate?: boolean;
}

// Add CONTAINER_KINDS constant (single source of truth)
export const CONTAINER_KINDS: Record<string, Set<string>> = {
  python: new Set(['class', 'enum']),
  java: new Set(['class', 'interface', 'enum']),
};

// Helper to check if a kind is a container
export function isContainerKind(kind: string | null | undefined): boolean {
  if (!kind) return false;
  return CONTAINER_KINDS.python.has(kind) || CONTAINER_KINDS.java.has(kind);
}

// Helper to parse kind from location string (path::kind:qualname or path::qualname)
export function parseSemanticLocation(location: string): { path: string; kind: string | null; qualname: string } | null {
  const match = location.match(/^(.+?)::(?:([a-z]+):)?(.+)$/);
  if (!match) return null;
  return {
    path: match[1],
    kind: match[2] || null,
    qualname: match[3],
  };
}

// Update CodeBrowserSelection interface
export interface CodeBrowserSelection {
  type: 'semantic' | 'lines';
  location: string;  // Now includes kind: path::kind:qualname
  label?: string;
  kind?: string;
}
```

---

#### Step 4: Update CodeViewerPanel - Add Container Support
**File:** `/Users/vlad/dev/projects/codesub/frontend/src/components/CodeViewerPanel.tsx`
**Complexity:** Medium

**Changes:**
- Add 'class', 'interface', 'enum' to `TRACKABLE_KINDS`
- Import `isContainerKind` from types (don't duplicate)
- Style container kinds with blue background
- Selection now uses `construct.target` which includes kind (from Step 1)

**Code:**
```typescript
// Update imports
import { isContainerKind } from '../types';

// Update TRACKABLE_KINDS (line 7)
const TRACKABLE_KINDS = new Set(['variable', 'field', 'method', 'class', 'interface', 'enum']);

// Update construct highlight styling - use isContainerKind helper
<span
  onClick={(e) => handleConstructClick(construct, e)}
  style={{
    background: selectedConstruct === construct
      ? (isContainerKind(construct.kind) ? '#90caf9' : '#a5d6a7')
      : (isContainerKind(construct.kind) ? '#e3f2fd' : '#e8f5e9'),
    borderRadius: 2,
    padding: '0 2px',
    cursor: 'pointer',
    transition: 'background 0.1s',
  }}
  onMouseEnter={(e) => {
    if (selectedConstruct !== construct) {
      e.currentTarget.style.background = isContainerKind(construct.kind) ? '#bbdefb' : '#c8e6c9';
    }
  }}
  onMouseLeave={(e) => {
    if (selectedConstruct !== construct) {
      e.currentTarget.style.background = isContainerKind(construct.kind) ? '#e3f2fd' : '#e8f5e9';
    }
  }}
  title={`${construct.kind}: ${construct.qualname}${isContainerKind(construct.kind) ? ' (container - can track members)' : ''}`}
>
  {line || ' '}
</span>

// getSelectionResult - construct.target now includes kind (from backend fix)
const getSelectionResult = (): CodeBrowserSelection | null => {
  if (selectedConstruct) {
    return {
      type: 'semantic',
      location: selectedConstruct.target,  // Now path::kind:qualname
      label: `${selectedConstruct.kind}: ${selectedConstruct.qualname}`,
      kind: selectedConstruct.kind,
    };
  }
  // ... rest unchanged
};

// Update selection bar badge
<span style={{
  padding: '2px 6px',
  background: selection.type === 'semantic'
    ? (isContainerKind(selection.kind) ? '#e3f2fd' : '#c8e6c9')
    : '#bbdefb',
  borderRadius: 3,
  fontSize: 11,
  marginRight: 8,
}}>
  {selection.type === 'semantic'
    ? (isContainerKind(selection.kind) ? 'Container' : 'Semantic')
    : 'Lines'}
</span>
```

---

#### Step 5: Update SubscriptionForm - Add Configuration Checkboxes
**File:** `/Users/vlad/dev/projects/codesub/frontend/src/components/SubscriptionForm.tsx`
**Complexity:** Medium

**Changes:**
- Import `isContainerKind`, `parseSemanticLocation` from types
- Add state for configuration options
- Parse kind from location string (works for both browser selection and manual entry)
- Support edit mode for trigger_on_duplicate
- Use explicit booleans in request (not `|| undefined`)

**Code:**
```typescript
// Update imports
import { isContainerKind, parseSemanticLocation } from '../types';

// Add state variables
const [includeMembers, setIncludeMembers] = useState(false);
const [includePrivate, setIncludePrivate] = useState(false);
const [trackDecorators, setTrackDecorators] = useState(true);
const [triggerOnDuplicate, setTriggerOnDuplicate] = useState(
  subscription?.trigger_on_duplicate ?? false
);

// Derive kind from location (works for both browser and manual entry)
const parsedLocation = useMemo(() => parseSemanticLocation(location), [location]);
const isSemanticLocation = parsedLocation !== null;
const selectedKind = parsedLocation?.kind ?? null;
const showContainerOptions = isContainerKind(selectedKind);

// Update handleBrowserSelect
const handleBrowserSelect = (selection: CodeBrowserSelection) => {
  setLocation(selection.location);  // Now includes kind
  if (selection.label && !label) {
    setLabel(selection.label);
  }
  // Reset container options if switching to non-container
  if (!isContainerKind(selection.kind)) {
    setIncludeMembers(false);
    setIncludePrivate(false);
    setTrackDecorators(true);
  }
  setShowBrowser(false);
};

// Update handleSubmit for CREATE
const data: SubscriptionCreateRequest = {
  location,
  label: label || undefined,
  description: description || undefined,
  context,
  trigger_on_duplicate: triggerOnDuplicate,  // Always send explicit boolean
  include_members: showContainerOptions ? includeMembers : false,
  include_private: showContainerOptions && includeMembers ? includePrivate : false,
  track_decorators: showContainerOptions && includeMembers ? trackDecorators : true,
};

// Update handleSubmit for EDIT (add trigger_on_duplicate)
const updateData: SubscriptionUpdateRequest = {
  label: label || undefined,
  description: description || undefined,
  trigger_on_duplicate: triggerOnDuplicate,
};

// Configuration section in form
{isSemanticLocation && (
  <div style={{
    marginTop: 12,
    padding: 16,
    background: '#f8f9fa',
    borderRadius: 4,
    border: '1px solid #e9ecef',
  }}>
    <div style={{ fontWeight: 600, marginBottom: 12, fontSize: 14 }}>
      Subscription Options
    </div>

    {/* Show parsed kind info */}
    {selectedKind && (
      <div style={{ fontSize: 12, color: '#666', marginBottom: 8 }}>
        Detected: <strong>{selectedKind}</strong>
        {isContainerKind(selectedKind) && ' (container)'}
      </div>
    )}
    {!selectedKind && (
      <div style={{ fontSize: 12, color: '#999', marginBottom: 8 }}>
        Tip: Use format <code>path::kind:qualname</code> for explicit kind
      </div>
    )}

    {/* Trigger on duplicate - available for all semantic subscriptions */}
    <label style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8, cursor: 'pointer' }}>
      <input
        type="checkbox"
        checked={triggerOnDuplicate}
        onChange={(e) => setTriggerOnDuplicate(e.target.checked)}
      />
      <span>Trigger if construct found in multiple files</span>
    </label>

    {/* Container-specific options - only when kind is known to be container */}
    {showContainerOptions && (
      <>
        <div style={{
          marginTop: 12,
          paddingTop: 12,
          borderTop: '1px solid #dee2e6',
          marginBottom: 8,
          fontWeight: 500,
          fontSize: 13,
          color: '#495057',
        }}>
          Container Tracking
        </div>

        <label style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8, cursor: 'pointer' }}>
          <input
            type="checkbox"
            checked={includeMembers}
            onChange={(e) => setIncludeMembers(e.target.checked)}
          />
          <span>Track all members (trigger on any member change)</span>
        </label>

        {includeMembers && (
          <>
            <label style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8, marginLeft: 24, cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={includePrivate}
                onChange={(e) => setIncludePrivate(e.target.checked)}
              />
              <span>Include private members (_prefixed, Python only)</span>
            </label>

            <label style={{ display: 'flex', alignItems: 'center', gap: 8, marginLeft: 24, cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={trackDecorators}
                onChange={(e) => setTrackDecorators(e.target.checked)}
              />
              <span>Track decorator changes</span>
            </label>
          </>
        )}
      </>
    )}
  </div>
)}
```

---

#### Step 6: Update SubscriptionList - Add Badges
**File:** `/Users/vlad/dev/projects/codesub/frontend/src/components/SubscriptionList.tsx`
**Complexity:** Low

**Changes:**
- Add "members" badge when `include_members === true`
- Add "dup" badge when `trigger_on_duplicate === true`
- Update location display to show kind

**Code:**
```typescript
// Update the location cell for semantic subscriptions
<td style={{ padding: '12px 8px' }}>
  {isSemantic(sub) && sub.semantic ? (
    <span>
      <span style={{ fontFamily: 'monospace', fontSize: 13 }}>
        {sub.semantic.qualname}
      </span>
      <span style={{ color: '#666', marginLeft: 4 }}>({sub.semantic.kind})</span>
      {sub.semantic.role === 'const' && (
        <span style={{ marginLeft: 6, padding: '1px 4px', borderRadius: 10, fontSize: 10, background: '#fff3cd', color: '#856404' }}>
          const
        </span>
      )}
      {sub.semantic.include_members && (
        <span
          style={{ marginLeft: 6, padding: '1px 4px', borderRadius: 10, fontSize: 10, background: '#cfe2ff', color: '#084298' }}
          title="Tracking all members of this container"
        >
          members
        </span>
      )}
      {sub.trigger_on_duplicate && (
        <span
          style={{ marginLeft: 6, padding: '1px 4px', borderRadius: 10, fontSize: 10, background: '#e2e3e5', color: '#41464b' }}
          title="Triggers if construct found in multiple files"
        >
          dup
        </span>
      )}
      <span style={{ fontFamily: 'monospace', fontSize: 12, color: '#999', marginLeft: 8 }}>
        {sub.path}:{sub.start_line}-{sub.end_line}
      </span>
    </span>
  ) : (
    <span style={{ fontFamily: 'monospace', fontSize: 13 }}>
      {formatLocation(sub)}
    </span>
  )}
</td>
```

---

#### Step 7: Update SubscriptionDetail - Add Container Tracking Section
**File:** `/Users/vlad/dev/projects/codesub/frontend/src/components/SubscriptionDetail.tsx`
**Complexity:** Medium

**Changes:**
- Update location display to include kind: `${sub.path}::${sub.semantic.kind}:${sub.semantic.qualname}`
- Add "Tracking Options" row
- Add collapsible "Container Tracking Details" section
- Show explicit values (don't paper over missing data with `!== false`)

**Code:**
```typescript
// Update Location display for semantic subscriptions
<dd style={{ fontFamily: 'monospace', fontSize: 13 }}>
  {isSemantic && sub.semantic
    ? `${sub.path}::${sub.semantic.kind}:${sub.semantic.qualname}`
    : formatLocation(sub)}
</dd>

// Add Tracking Options row
{isSemantic && sub.semantic && (
  <>
    <dt style={{ fontWeight: 600, color: '#555' }}>Tracking Options:</dt>
    <dd>
      {sub.trigger_on_duplicate && (
        <span style={{ display: 'inline-block', padding: '2px 6px', borderRadius: 3, fontSize: 11, background: '#e2e3e5', color: '#41464b', marginRight: 6 }}>
          Trigger on duplicate
        </span>
      )}
      {sub.semantic.include_members && (
        <span style={{ display: 'inline-block', padding: '2px 6px', borderRadius: 3, fontSize: 11, background: '#cfe2ff', color: '#084298', marginRight: 6 }}>
          Track members
        </span>
      )}
      {!sub.trigger_on_duplicate && !sub.semantic.include_members && (
        <span style={{ color: '#999' }}>Default</span>
      )}
    </dd>
  </>
)}

// Add Container Tracking details section
{isSemantic && sub.semantic && sub.semantic.include_members && (
  <details style={{ marginTop: 16 }}>
    <summary style={{ cursor: 'pointer', fontWeight: 600, color: '#555', fontSize: 14 }}>
      Container Tracking Details
    </summary>
    <div style={{ marginTop: 8, padding: 12, background: '#fff', border: '1px solid #e9ecef', borderRadius: 4 }}>
      <dl style={{ display: 'grid', gridTemplateColumns: 'auto 1fr', gap: '8px 16px', margin: 0 }}>
        <dt style={{ fontWeight: 500, color: '#666', fontSize: 13 }}>Include Private:</dt>
        <dd style={{ fontSize: 13 }}>
          <span style={{ padding: '1px 6px', background: sub.semantic.include_private ? '#d4edda' : '#f8d7da', borderRadius: 3, fontSize: 11 }}>
            {sub.semantic.include_private ? 'Yes' : 'No'}
          </span>
        </dd>

        <dt style={{ fontWeight: 500, color: '#666', fontSize: 13 }}>Track Decorators:</dt>
        <dd style={{ fontSize: 13 }}>
          <span style={{ padding: '1px 6px', background: sub.semantic.track_decorators ? '#d4edda' : '#f8d7da', borderRadius: 3, fontSize: 11 }}>
            {sub.semantic.track_decorators ? 'Yes' : 'No'}
          </span>
        </dd>

        {sub.semantic.baseline_container_qualname && sub.semantic.baseline_container_qualname !== sub.semantic.qualname && (
          <>
            <dt style={{ fontWeight: 500, color: '#666', fontSize: 13 }}>Original Name:</dt>
            <dd style={{ fontFamily: 'monospace', fontSize: 12 }}>
              {sub.semantic.baseline_container_qualname}
              <span style={{ color: '#dc3545', marginLeft: 8 }}>(renamed)</span>
            </dd>
          </>
        )}

        {sub.semantic.baseline_members && (
          <>
            <dt style={{ fontWeight: 500, color: '#666', fontSize: 13 }}>Tracked Members:</dt>
            <dd style={{ fontSize: 13 }}>
              {Object.keys(sub.semantic.baseline_members).length} members
            </dd>
          </>
        )}
      </dl>

      {sub.semantic.baseline_members && Object.keys(sub.semantic.baseline_members).length > 0 && (
        <div style={{ marginTop: 12 }}>
          <div style={{ fontWeight: 500, color: '#666', fontSize: 13, marginBottom: 8 }}>
            Baseline Members:
          </div>
          <div style={{ maxHeight: 200, overflow: 'auto', background: '#f8f9fa', borderRadius: 4, padding: 8 }}>
            {Object.entries(sub.semantic.baseline_members).map(([name, fp]) => (
              <div key={name} style={{ fontFamily: 'monospace', fontSize: 12, padding: '2px 0', display: 'flex', gap: 8 }}>
                <span style={{ color: '#666', minWidth: 60 }}>{fp.kind}</span>
                <span>{name}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  </details>
)}
```

---

### Testing Strategy (Updated)

**Backend tests (add):**
- [ ] Test that GET subscription returns all container fields after create with include_members=true
- [ ] Test that ConstructSchema.target includes kind in format `path::kind:qualname`

**Frontend tests:**
- [ ] Verify container kinds appear in CodeViewerPanel with blue highlighting
- [ ] Verify selection produces `path::kind:qualname` format location
- [ ] Verify manual entry of `path::kind:qualname` shows container options
- [ ] Verify manual entry of `path::qualname` (no kind) shows tip message
- [ ] Verify trigger_on_duplicate can be edited in update flow
- [ ] Verify SubscriptionList shows badges
- [ ] Verify SubscriptionDetail shows kind in location
- [ ] Test Python class with include_members=true
- [ ] Test Java interface with include_members=true

### Summary of External Review Fixes

| Issue | Fix |
|-------|-----|
| Kind not in location string | Step 1: Backend includes kind in ConstructSchema.target |
| No edit support for trigger_on_duplicate | Step 3 & 5: Added to SubscriptionUpdateRequest and form |
| `\|\| undefined` breaks toggle-off | Step 5: Use explicit booleans |
| Silent reset on manual edit | Step 5: Parse location to infer kind instead |
| Duplicate CONTAINER_KINDS | Step 4: Import from types.ts |
| Location display missing kind | Step 7: Show `path::kind:qualname` |
