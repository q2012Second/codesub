import { useState, useEffect, useMemo, useRef } from 'react';
import type { FileContentResponse, SymbolsResponse, ConstructInfo, CodeBrowserSelection } from '../types';
import { isContainerKind } from '../types';
import { getProjectFileContent, getProjectFileSymbols } from '../api';

// Construct kinds that can be tracked as subscriptions
// Includes both member kinds and container kinds (class/enum/interface)
const TRACKABLE_KINDS = new Set(['variable', 'field', 'method', 'class', 'interface', 'enum']);

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

  // Hover state for line numbers
  const [hoveredLineNum, setHoveredLineNum] = useState<number | null>(null);

  // Drag selection state
  const [isDragging, setIsDragging] = useState(false);
  const dragAnchorRef = useRef<number | null>(null);

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

  // Handle line number mousedown (start drag or click)
  const handleLineNumberMouseDown = (lineNumber: number, event: React.MouseEvent) => {
    event.preventDefault();
    event.stopPropagation();
    setSelectedConstruct(null);

    if (event.shiftKey && selectionAnchor !== null) {
      // Shift-click extends selection
      const start = Math.min(selectionAnchor, lineNumber);
      const end = Math.max(selectionAnchor, lineNumber);
      setLineSelection({ start, end });
    } else {
      // Start drag selection
      setIsDragging(true);
      dragAnchorRef.current = lineNumber;
      setSelectionAnchor(lineNumber);
      setLineSelection({ start: lineNumber, end: lineNumber });
    }
  };

  // Handle mouse enter on line number during drag
  const handleLineNumberMouseEnter = (lineNumber: number) => {
    setHoveredLineNum(lineNumber);
    if (isDragging && dragAnchorRef.current !== null) {
      const start = Math.min(dragAnchorRef.current, lineNumber);
      const end = Math.max(dragAnchorRef.current, lineNumber);
      setLineSelection({ start, end });
    }
  };

  // Handle mouse up to end drag
  const handleLineNumberMouseUp = () => {
    setIsDragging(false);
  };

  // Global mouseup to end drag if released outside line numbers
  useEffect(() => {
    const handleGlobalMouseUp = () => {
      if (isDragging) {
        setIsDragging(false);
      }
    };
    document.addEventListener('mouseup', handleGlobalMouseUp);
    return () => document.removeEventListener('mouseup', handleGlobalMouseUp);
  }, [isDragging]);

  // Handle construct click (semantic selection) - toggle if already selected
  const handleConstructClick = (construct: ConstructInfo, event: React.MouseEvent) => {
    event.stopPropagation();
    setLineSelection(null);
    setSelectionAnchor(null);
    setSelectedConstruct(selectedConstruct === construct ? null : construct);
  };

  // Get current selection result
  const getSelectionResult = (): CodeBrowserSelection | null => {
    if (selectedConstruct) {
      return {
        type: 'semantic',
        location: selectedConstruct.target,  // Now includes kind: path::kind:qualname
        label: `${selectedConstruct.kind}: ${selectedConstruct.qualname}`,
        kind: selectedConstruct.kind,
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
          ? 'Click or drag line numbers to select lines. Click highlighted code to select constructs.'
          : 'Click or drag line numbers to select lines.'}
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
              const isLineNumHovered = hoveredLineNum === lineNum;

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
                  {/* Line number - clickable/draggable for line selection */}
                  <td
                    onMouseDown={(e) => handleLineNumberMouseDown(lineNum, e)}
                    onMouseEnter={() => handleLineNumberMouseEnter(lineNum)}
                    onMouseLeave={() => setHoveredLineNum(null)}
                    onMouseUp={handleLineNumberMouseUp}
                    style={{
                      padding: '0 12px 0 8px',
                      textAlign: 'right',
                      color: isInSelection ? '#1565c0' : '#666',
                      fontWeight: isInSelection ? 600 : 400,
                      userSelect: 'none',
                      borderRight: '1px solid #eee',
                      width: 1,
                      whiteSpace: 'nowrap',
                      cursor: 'pointer',
                      background: isLineNumHovered && !isInSelection ? '#f0f0f0' : 'transparent',
                    }}
                    title="Click to select line, drag or shift-click to extend"
                  >
                    {lineNum}
                  </td>
                  {/* Code content */}
                  <td style={{ padding: '0 8px', whiteSpace: 'pre' }}>
                    {construct ? (
                      <span
                        onClick={(e) => handleConstructClick(construct, e)}
                        style={{
                          // Blue for containers, green for members
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
            <>
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
              <code>{selection.location}</code>
            </>
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
