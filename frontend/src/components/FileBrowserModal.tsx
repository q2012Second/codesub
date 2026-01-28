import { useState, useEffect, useCallback, useRef } from 'react';
import { browseFilesystem } from '../api';
import type { FilesystemEntry } from '../types';

interface FileBrowserModalProps {
  initialPath?: string;
  onSelect: (path: string) => void;
  onCancel: () => void;
}

export function FileBrowserModal({
  initialPath = '~',
  onSelect,
  onCancel,
}: FileBrowserModalProps) {
  const [currentPath, setCurrentPath] = useState<string>('');
  const [parentPath, setParentPath] = useState<string | null>(null);
  const [entries, setEntries] = useState<FilesystemEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Track request ID to prevent race conditions
  const requestIdRef = useRef(0);
  // Ref for focus management
  const modalRef = useRef<HTMLDivElement>(null);

  const loadDirectory = useCallback(async (path: string) => {
    const requestId = ++requestIdRef.current;
    setLoading(true);
    setError(null);
    try {
      const result = await browseFilesystem(path);
      // Only update state if this is still the latest request
      if (requestId === requestIdRef.current) {
        setCurrentPath(result.current_path);
        setParentPath(result.parent_path);
        setEntries(result.entries);
      }
    } catch (e) {
      if (requestId === requestIdRef.current) {
        setError(e instanceof Error ? e.message : 'Failed to load directory');
      }
    } finally {
      if (requestId === requestIdRef.current) {
        setLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    loadDirectory(initialPath);
  }, [initialPath, loadDirectory]);

  // Handle Escape key to close modal
  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onCancel();
      }
    };
    document.addEventListener('keydown', handleEscape);
    return () => document.removeEventListener('keydown', handleEscape);
  }, [onCancel]);

  // Focus modal on mount
  useEffect(() => {
    modalRef.current?.focus();
  }, []);

  const handleEntryClick = (entry: FilesystemEntry) => {
    if (entry.is_dir) {
      loadDirectory(entry.path);
    }
  };

  const handleEntryKeyDown = (e: React.KeyboardEvent, entry: FilesystemEntry) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      handleEntryClick(entry);
    }
  };

  const handleGoUp = () => {
    if (parentPath) {
      loadDirectory(parentPath);
    }
  };

  const handleGoUpKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      handleGoUp();
    }
  };

  const handleSelect = () => {
    onSelect(currentPath);
  };

  return (
    <div
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        background: 'rgba(0,0,0,0.5)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 1000,
      }}
      onClick={onCancel}
    >
      <div
        ref={modalRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="file-browser-title"
        tabIndex={-1}
        style={{
          background: 'white',
          borderRadius: 8,
          padding: 24,
          maxWidth: 600,
          width: '90%',
          maxHeight: '80vh',
          display: 'flex',
          flexDirection: 'column',
          outline: 'none',
        }}
        onClick={e => e.stopPropagation()}
      >
        <h3 id="file-browser-title" style={{ marginBottom: 16, marginTop: 0 }}>
          Select Folder
        </h3>

        {/* Current path display */}
        <div
          style={{
            padding: '8px 12px',
            background: '#f5f5f5',
            borderRadius: 4,
            marginBottom: 12,
            fontFamily: 'monospace',
            fontSize: 13,
            wordBreak: 'break-all',
          }}
        >
          {currentPath || 'Loading...'}
        </div>

        {/* Error message */}
        {error && (
          <div
            role="alert"
            style={{
              padding: 12,
              background: '#fee',
              color: '#c00',
              borderRadius: 4,
              marginBottom: 12,
            }}
          >
            {error}
          </div>
        )}

        {/* Directory listing */}
        <div
          role="listbox"
          aria-label="Directory contents"
          style={{
            flex: 1,
            border: '1px solid #ddd',
            borderRadius: 4,
            overflow: 'auto',
            minHeight: 200,
            maxHeight: 400,
          }}
        >
          {loading ? (
            <div style={{ padding: 16, color: '#666' }}>Loading...</div>
          ) : (
            <>
              {/* Go up button */}
              {parentPath && (
                <div
                  role="option"
                  tabIndex={0}
                  onClick={handleGoUp}
                  onKeyDown={handleGoUpKeyDown}
                  style={{
                    padding: '10px 12px',
                    borderBottom: '1px solid #eee',
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    gap: 8,
                  }}
                  onMouseEnter={e => (e.currentTarget.style.background = '#f5f5f5')}
                  onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
                  onFocus={e => (e.currentTarget.style.background = '#f5f5f5')}
                  onBlur={e => (e.currentTarget.style.background = 'transparent')}
                >
                  <span style={{ fontSize: 16 }} aria-hidden="true">↑</span>
                  <span>..</span>
                </div>
              )}

              {/* Directory entries */}
              {entries.length === 0 && !parentPath ? (
                <div style={{ padding: 16, color: '#666' }}>Empty directory</div>
              ) : (
                entries.map(entry => (
                  <div
                    key={entry.path}
                    role="option"
                    tabIndex={0}
                    onClick={() => handleEntryClick(entry)}
                    onKeyDown={(e) => handleEntryKeyDown(e, entry)}
                    style={{
                      padding: '10px 12px',
                      borderBottom: '1px solid #eee',
                      cursor: 'pointer',
                      display: 'flex',
                      alignItems: 'center',
                      gap: 8,
                    }}
                    onMouseEnter={e => (e.currentTarget.style.background = '#f5f5f5')}
                    onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
                    onFocus={e => (e.currentTarget.style.background = '#f5f5f5')}
                    onBlur={e => (e.currentTarget.style.background = 'transparent')}
                  >
                    <span style={{ fontSize: 16 }} aria-hidden="true">📁</span>
                    <span>{entry.name}</span>
                  </div>
                ))
              )}
            </>
          )}
        </div>

        {/* Action buttons */}
        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 16 }}>
          <button
            type="button"
            onClick={onCancel}
            style={{
              padding: '8px 16px',
              border: '1px solid #ddd',
              borderRadius: 4,
              cursor: 'pointer',
              background: 'white',
            }}
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleSelect}
            disabled={loading || !currentPath}
            style={{
              background: '#0066cc',
              color: 'white',
              border: '1px solid #0066cc',
              padding: '8px 16px',
              borderRadius: 4,
              cursor: 'pointer',
              opacity: loading || !currentPath ? 0.5 : 1,
            }}
          >
            Select This Folder
          </button>
        </div>
      </div>
    </div>
  );
}
