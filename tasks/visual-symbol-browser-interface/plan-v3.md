# Implementation Plan: Code Browser Selection UX Refinement (v3)

## Overview

Refine the code browser selection UX to clearly separate line selection (via line numbers) from semantic selection (via construct clicks), and only highlight constructs that can actually be tracked.

## Changes from v2

| Issue | Resolution |
|-------|------------|
| Clicking row triggers both modes | Separate click handlers: line number gutter vs construct span |
| Classes highlighted but not trackable | Filter to only trackable kinds: `variable`, `field`, `method` |
| No visual distinction | Line numbers get hover effect, constructs get distinct highlighting |

## Design Decisions

| Decision | Rationale |
|----------|-----------|
| Line selection only via line number clicks | Clear UX - gutter is for line selection |
| Filter non-trackable constructs client-side | Simpler than backend change; keeps API generic |
| Trackable kinds: variable, field, method | Based on what Python/Java indexers support for subscriptions |

---

## Implementation Steps

### Step 1: Define Trackable Construct Kinds

**File:** `frontend/src/components/CodeViewerPanel.tsx`

Add constant for trackable kinds:
```typescript
// Construct kinds that can be tracked as subscriptions
const TRACKABLE_KINDS = new Set(['variable', 'field', 'method']);
```

### Step 2: Filter Constructs to Only Trackable Types

**File:** `frontend/src/components/CodeViewerPanel.tsx`

Update `lineConstructMap` to filter by trackable kinds:
```typescript
const trackableConstructs = useMemo(() => {
  if (!symbols) return [];
  return symbols.constructs.filter(c => TRACKABLE_KINDS.has(c.kind));
}, [symbols]);

const lineConstructMap = useMemo(() => {
  const map = new Map<number, ConstructInfo>();
  for (const construct of trackableConstructs) {
    if (!map.has(construct.start_line)) {
      map.set(construct.start_line, construct);
    }
  }
  return map;
}, [trackableConstructs]);
```

### Step 3: Separate Click Handlers

**File:** `frontend/src/components/CodeViewerPanel.tsx`

Split into two handlers:

```typescript
// Handle line number click (line selection)
const handleLineNumberClick = (lineNumber: number, event: React.MouseEvent) => {
  event.stopPropagation();
  setSelectedConstruct(null);

  if (event.shiftKey && selectionAnchor !== null) {
    const start = Math.min(selectionAnchor, lineNumber);
    const end = Math.max(selectionAnchor, lineNumber);
    setLineSelection({ start, end });
  } else {
    setSelectionAnchor(lineNumber);
    setLineSelection({ start: lineNumber, end: lineNumber });
  }
};

// Handle construct click (semantic selection)
const handleConstructClick = (construct: ConstructInfo, event: React.MouseEvent) => {
  event.stopPropagation();
  setLineSelection(null);
  setSelectionAnchor(null);
  setSelectedConstruct(construct);
};
```

### Step 4: Update Line Number Cell Rendering

**File:** `frontend/src/components/CodeViewerPanel.tsx`

Make line numbers clearly clickable with hover effect:

```typescript
<td
  onClick={(e) => handleLineNumberClick(lineNum, e)}
  style={{
    padding: '0 12px 0 8px',
    textAlign: 'right',
    color: isInSelection ? '#1565c0' : '#999',
    userSelect: 'none',
    borderRight: '1px solid #eee',
    width: 1,
    whiteSpace: 'nowrap',
    cursor: 'pointer',
    background: isInSelection ? '#bbdefb' : 'transparent',
  }}
  onMouseEnter={(e) => {
    if (!isInSelection) e.currentTarget.style.background = '#f0f0f0';
  }}
  onMouseLeave={(e) => {
    if (!isInSelection) e.currentTarget.style.background = 'transparent';
  }}
  title="Click to select line, Shift+click to extend"
>
  {lineNum}
</td>
```

### Step 5: Update Code Cell Rendering

**File:** `frontend/src/components/CodeViewerPanel.tsx`

Only highlight trackable constructs, make them clickable:

```typescript
<td style={{ padding: '0 8px', whiteSpace: 'pre' }}>
  {construct ? (
    <span
      onClick={(e) => handleConstructClick(construct, e)}
      style={{
        background: selectedConstruct === construct ? '#a5d6a7' : '#e8f5e9',
        borderRadius: 2,
        padding: '0 2px',
        cursor: 'pointer',
      }}
      onMouseEnter={(e) => {
        if (selectedConstruct !== construct) {
          e.currentTarget.style.background = '#c8e6c9';
        }
      }}
      onMouseLeave={(e) => {
        if (selectedConstruct !== construct) {
          e.currentTarget.style.background = '#e8f5e9';
        }
      }}
      title={`${construct.kind}: ${construct.qualname} (click to select)`}
    >
      {line || ' '}
    </span>
  ) : (
    line || ' '
  )}
</td>
```

Note: Removed `isConstructLine` highlighting for non-start lines since we're only highlighting clickable constructs now.

### Step 6: Update Row Styling

**File:** `frontend/src/components/CodeViewerPanel.tsx`

Remove row-level click handler and cursor, keep only background for selection state:

```typescript
<tr
  key={lineNum}
  style={{
    background: isInSelection
      ? '#e3f2fd'
      : isConstructSelected
        ? '#c8e6c9'
        : 'transparent',
  }}
>
```

### Step 7: Update Help Text

**File:** `frontend/src/components/CodeViewerPanel.tsx`

Update help text to be clearer:

```typescript
<div style={{ marginBottom: 12, fontSize: 13, color: '#666' }}>
  {content.supports_semantic && trackableConstructs.length > 0
    ? 'Click line numbers to select lines (shift-click to extend range). Click highlighted constructs to select them.'
    : 'Click line numbers to select lines (shift-click to extend range).'}
</div>
```

---

## Complete Updated Component

Here's the full updated `CodeViewerPanel.tsx`:

```typescript
import { useState, useEffect, useMemo, useRef } from 'react';
import type { FileContentResponse, SymbolsResponse, ConstructInfo, CodeBrowserSelection } from '../types';
import { getProjectFileContent, getProjectFileSymbols } from '../api';

// Construct kinds that can be tracked as subscriptions
const TRACKABLE_KINDS = new Set(['variable', 'field', 'method']);

interface Props {
  projectId: string;
  filePath: string;
  onBack: () => void;
  onSelect: (selection: CodeBrowserSelection) => void;
  onCancel: () => void;
}

export function CodeViewerPanel({ projectId, filePath, onBack, onSelect, onCancel }: Props) {
  const [content, setContent] = useState<FileContentResponse | null>(null);
  const [symbols, setSymbols] = useState<SymbolsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Selection state
  const [selectedConstruct, setSelectedConstruct] = useState<ConstructInfo | null>(null);
  const [lineSelection, setLineSelection] = useState<{ start: number; end: number } | null>(null);
  const [selectionAnchor, setSelectionAnchor] = useState<number | null>(null);

  const abortControllerRef = useRef<AbortController | null>(null);

  // Load content and symbols
  useEffect(() => {
    abortControllerRef.current?.abort();
    abortControllerRef.current = new AbortController();
    const signal = abortControllerRef.current.signal;

    setLoading(true);
    setError(null);

    Promise.allSettled([
      getProjectFileContent(projectId, filePath, signal),
      getProjectFileSymbols(projectId, filePath, undefined, signal),
    ]).then(([contentResult, symbolsResult]) => {
      if (signal.aborted) return;

      if (contentResult.status === 'fulfilled') {
        setContent(contentResult.value);
      } else {
        setError(contentResult.reason?.message || 'Failed to load file');
      }

      if (symbolsResult.status === 'fulfilled') {
        setSymbols(symbolsResult.value);
      }

      setLoading(false);
    });

    return () => abortControllerRef.current?.abort();
  }, [projectId, filePath]);

  // Handle Escape key
  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onCancel();
    };
    document.addEventListener('keydown', handleEscape);
    return () => document.removeEventListener('keydown', handleEscape);
  }, [onCancel]);

  // Filter to only trackable constructs
  const trackableConstructs = useMemo(() => {
    if (!symbols) return [];
    return symbols.constructs.filter(c => TRACKABLE_KINDS.has(c.kind));
  }, [symbols]);

  // Build line-to-construct mapping (only start lines, only trackable)
  const lineConstructMap = useMemo(() => {
    const map = new Map<number, ConstructInfo>();
    for (const construct of trackableConstructs) {
      if (!map.has(construct.start_line)) {
        map.set(construct.start_line, construct);
      }
    }
    return map;
  }, [trackableConstructs]);

  // Handle line number click (line selection)
  const handleLineNumberClick = (lineNumber: number, event: React.MouseEvent) => {
    event.stopPropagation();
    setSelectedConstruct(null);

    if (event.shiftKey && selectionAnchor !== null) {
      const start = Math.min(selectionAnchor, lineNumber);
      const end = Math.max(selectionAnchor, lineNumber);
      setLineSelection({ start, end });
    } else {
      setSelectionAnchor(lineNumber);
      setLineSelection({ start: lineNumber, end: lineNumber });
    }
  };

  // Handle construct click (semantic selection)
  const handleConstructClick = (construct: ConstructInfo, event: React.MouseEvent) => {
    event.stopPropagation();
    setLineSelection(null);
    setSelectionAnchor(null);
    setSelectedConstruct(construct);
  };

  // Get current selection result
  const getSelectionResult = (): CodeBrowserSelection | null => {
    if (selectedConstruct) {
      return {
        type: 'semantic',
        location: selectedConstruct.target,
        label: `${selectedConstruct.kind}: ${selectedConstruct.qualname}`,
      };
    }
    if (lineSelection) {
      const { start, end } = lineSelection;
      const location = start === end
        ? `${filePath}:${start}`
        : `${filePath}:${start}-${end}`;
      return { type: 'lines', location };
    }
    return null;
  };

  // Select full file
  const handleSelectFullFile = () => {
    if (content) {
      setSelectedConstruct(null);
      setLineSelection({ start: 1, end: content.total_lines });
      setSelectionAnchor(1);
    }
  };

  // Confirm selection
  const handleConfirm = () => {
    const result = getSelectionResult();
    if (result) onSelect(result);
  };

  const selection = getSelectionResult();

  if (loading) {
    return <div style={{ padding: 32, textAlign: 'center' }}>Loading file...</div>;
  }

  if (error) {
    return (
      <div style={{ padding: 32 }}>
        <div style={{ color: '#dc3545', marginBottom: 16 }}>{error}</div>
        <button onClick={onBack}>Go Back</button>
      </div>
    );
  }

  if (!content) {
    return <div style={{ padding: 32 }}>No content</div>;
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* Header */}
      <div style={{ marginBottom: 12, display: 'flex', alignItems: 'center', gap: 12 }}>
        <button onClick={onBack} style={{ padding: '4px 8px' }}>&larr; Back</button>
        <code style={{ flex: 1, fontSize: 13, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {filePath}
        </code>
        {content.language && (
          <span style={{
            padding: '2px 8px',
            background: '#e3f2fd',
            borderRadius: 4,
            fontSize: 12,
          }}>
            {content.language}
          </span>
        )}
      </div>

      {/* Warnings */}
      {content.truncated && (
        <div style={{
          padding: '8px 12px',
          background: '#fff3cd',
          border: '1px solid #ffc107',
          borderRadius: 4,
          marginBottom: 12,
          fontSize: 13,
        }}>
          File truncated: showing {content.lines.length} of {content.total_lines} lines
        </div>
      )}

      {symbols?.has_parse_error && (
        <div style={{
          padding: '8px 12px',
          background: '#fff3cd',
          border: '1px solid #ffc107',
          borderRadius: 4,
          marginBottom: 12,
          fontSize: 13,
        }}>
          Parse warning: Some constructs may not be detected. Line selection still works.
        </div>
      )}

      {/* Help text */}
      <div style={{ marginBottom: 12, fontSize: 13, color: '#666' }}>
        {content.supports_semantic && trackableConstructs.length > 0
          ? 'Click line numbers to select lines (shift-click to extend range). Click highlighted constructs to select them.'
          : 'Click line numbers to select lines (shift-click to extend range).'}
      </div>

      {/* Code viewer */}
      <div style={{
        flex: 1,
        overflow: 'auto',
        border: '1px solid #ddd',
        borderRadius: 4,
        fontFamily: 'monospace',
        fontSize: 13,
        lineHeight: 1.5,
      }}>
        <table style={{ borderCollapse: 'collapse', width: '100%' }}>
          <tbody>
            {content.lines.map((line, idx) => {
              const lineNum = idx + 1;
              const construct = lineConstructMap.get(lineNum);
              const isInSelection = lineSelection &&
                lineNum >= lineSelection.start &&
                lineNum <= lineSelection.end;
              const isConstructSelected = selectedConstruct &&
                lineNum >= selectedConstruct.start_line &&
                lineNum <= selectedConstruct.end_line;

              return (
                <tr
                  key={lineNum}
                  style={{
                    background: isInSelection
                      ? '#e3f2fd'
                      : isConstructSelected
                        ? '#c8e6c9'
                        : 'transparent',
                  }}
                >
                  <td
                    onClick={(e) => handleLineNumberClick(lineNum, e)}
                    style={{
                      padding: '0 12px 0 8px',
                      textAlign: 'right',
                      color: isInSelection ? '#1565c0' : '#999',
                      userSelect: 'none',
                      borderRight: '1px solid #eee',
                      width: 1,
                      whiteSpace: 'nowrap',
                      cursor: 'pointer',
                    }}
                    title="Click to select line, Shift+click to extend"
                  >
                    {lineNum}
                  </td>
                  <td style={{ padding: '0 8px', whiteSpace: 'pre' }}>
                    {construct ? (
                      <span
                        onClick={(e) => handleConstructClick(construct, e)}
                        style={{
                          background: selectedConstruct === construct ? '#a5d6a7' : '#e8f5e9',
                          borderRadius: 2,
                          padding: '0 2px',
                          cursor: 'pointer',
                        }}
                        title={`${construct.kind}: ${construct.qualname} (click to select)`}
                      >
                        {line || ' '}
                      </span>
                    ) : (
                      line || ' '
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Selection bar */}
      <div style={{
        marginTop: 12,
        padding: '12px 16px',
        background: '#f5f5f5',
        borderRadius: 4,
        display: 'flex',
        alignItems: 'center',
        gap: 12,
      }}>
        <button onClick={handleSelectFullFile} style={{ padding: '6px 12px' }}>
          Select Full File
        </button>

        <div style={{ flex: 1, fontSize: 13, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {selection ? (
            <code>{selection.location}</code>
          ) : (
            <span style={{ color: '#999' }}>No selection</span>
          )}
        </div>

        <button onClick={onCancel} style={{ padding: '6px 12px' }}>Cancel</button>
        <button
          onClick={handleConfirm}
          disabled={!selection}
          style={{
            padding: '6px 16px',
            background: selection ? '#0066cc' : '#ccc',
            color: 'white',
            border: 'none',
            borderRadius: 4,
            cursor: selection ? 'pointer' : 'not-allowed',
          }}
        >
          Use Selection
        </button>
      </div>
    </div>
  );
}
```

---

## Testing Strategy

### Manual Testing
- [ ] Click line number → selects that line, shows `path:N`
- [ ] Shift+click another line number → extends to range, shows `path:N-M`
- [ ] Click highlighted construct → selects it, shows `path::QualName`
- [ ] Clicking regular code does nothing
- [ ] Classes are NOT highlighted
- [ ] Variables, fields, methods ARE highlighted
- [ ] Line numbers have cursor pointer
- [ ] Constructs have cursor pointer and hover effect

---

## File Summary

| File | Action |
|------|--------|
| `frontend/src/components/CodeViewerPanel.tsx` | Refactor selection logic |
