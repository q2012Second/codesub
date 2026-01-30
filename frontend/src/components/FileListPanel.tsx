import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import type { FileEntry } from '../types';
import { listProjectFiles } from '../api';
import { useDebouncedValue } from '../hooks';

interface Props {
  projectId: string;
  onSelectFile: (path: string) => void;
  onCancel: () => void;
}

// Tree node representing a folder or file
interface TreeNode {
  name: string;           // Display name (may be collapsed path like "src/java/repo")
  fullPath: string;       // Full path from root
  isFile: boolean;
  children: TreeNode[];
}

// Build tree from flat file list, collapsing single-child folder chains
function buildFileTree(files: FileEntry[]): TreeNode[] {
  // First, build a raw tree
  const root: Map<string, { isFile: boolean; children: Map<string, unknown> }> = new Map();

  for (const file of files) {
    const parts = file.path.split('/');
    let current = root;

    for (let i = 0; i < parts.length; i++) {
      const part = parts[i];
      const isLast = i === parts.length - 1;

      if (!current.has(part)) {
        current.set(part, { isFile: isLast, children: new Map() });
      }

      const node = current.get(part)!;
      if (isLast) {
        node.isFile = true;
      }
      current = node.children as Map<string, { isFile: boolean; children: Map<string, unknown> }>;
    }
  }

  // Convert to TreeNode array with collapsed paths
  function convertToTreeNodes(
    map: Map<string, { isFile: boolean; children: Map<string, unknown> }>,
    parentPath: string
  ): TreeNode[] {
    const nodes: TreeNode[] = [];

    for (const [name, node] of map) {
      const fullPath = parentPath ? `${parentPath}/${name}` : name;
      const children = node.children as Map<string, { isFile: boolean; children: Map<string, unknown> }>;

      if (node.isFile) {
        // It's a file
        nodes.push({
          name,
          fullPath,
          isFile: true,
          children: [],
        });
      } else {
        // It's a folder - check if we should collapse
        let collapsedName = name;
        let collapsedPath = fullPath;
        let currentChildren = children;

        // Collapse single-child folder chains
        while (currentChildren.size === 1) {
          const [childName, childNode] = [...currentChildren.entries()][0];
          const typedChildNode = childNode as { isFile: boolean; children: Map<string, unknown> };

          if (typedChildNode.isFile) {
            // Stop collapsing - the only child is a file
            break;
          }

          // Collapse this folder into the chain
          collapsedName = `${collapsedName}/${childName}`;
          collapsedPath = `${collapsedPath}/${childName}`;
          currentChildren = typedChildNode.children as Map<string, { isFile: boolean; children: Map<string, unknown> }>;
        }

        nodes.push({
          name: collapsedName,
          fullPath: collapsedPath,
          isFile: false,
          children: convertToTreeNodes(currentChildren, collapsedPath),
        });
      }
    }

    // Sort: folders first, then files, alphabetically
    return nodes.sort((a, b) => {
      if (a.isFile !== b.isFile) return a.isFile ? 1 : -1;
      return a.name.localeCompare(b.name);
    });
  }

  return convertToTreeNodes(root, '');
}

// Recursive component to render tree nodes
function TreeNodeItem({
  node,
  depth,
  expandedFolders,
  onToggleFolder,
  onSelectFile,
}: {
  node: TreeNode;
  depth: number;
  expandedFolders: Set<string>;
  onToggleFolder: (path: string) => void;
  onSelectFile: (path: string) => void;
}) {
  const isExpanded = expandedFolders.has(node.fullPath);
  const hasChildren = node.children.length > 0;

  const handleClick = () => {
    if (node.isFile) {
      onSelectFile(node.fullPath);
    } else {
      onToggleFolder(node.fullPath);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      handleClick();
    }
  };

  return (
    <>
      <li
        onClick={handleClick}
        onKeyDown={handleKeyDown}
        tabIndex={0}
        style={{
          padding: '6px 12px',
          paddingLeft: 12 + depth * 16,
          cursor: 'pointer',
          borderBottom: '1px solid #f0f0f0',
          background: 'transparent',
          transition: 'background 0.1s',
          display: 'flex',
          alignItems: 'center',
          gap: 6,
        }}
        onMouseEnter={(e) => (e.currentTarget.style.background = '#f5f5f5')}
        onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
        onFocus={(e) => (e.currentTarget.style.background = '#f5f5f5')}
        onBlur={(e) => (e.currentTarget.style.background = 'transparent')}
      >
        {/* Expand/collapse indicator for folders */}
        {!node.isFile && (
          <span style={{
            width: 12,
            fontSize: 10,
            color: '#666',
            fontFamily: 'monospace',
          }}>
            {hasChildren ? (isExpanded ? '▼' : '▶') : ' '}
          </span>
        )}
        {node.isFile && <span style={{ width: 12 }} />}

        {/* Icon */}
        <span style={{ fontSize: 14 }}>
          {node.isFile ? '📄' : (isExpanded ? '📂' : '📁')}
        </span>

        {/* Name */}
        <span style={{
          fontFamily: 'monospace',
          fontSize: 13,
          color: node.isFile ? '#333' : '#0066cc',
          fontWeight: node.isFile ? 400 : 500,
        }}>
          {node.name}
        </span>
      </li>

      {/* Render children if expanded */}
      {!node.isFile && isExpanded && node.children.map((child) => (
        <TreeNodeItem
          key={child.fullPath}
          node={child}
          depth={depth + 1}
          expandedFolders={expandedFolders}
          onToggleFolder={onToggleFolder}
          onSelectFile={onSelectFile}
        />
      ))}
    </>
  );
}

export function FileListPanel({ projectId, onSelectFile, onCancel }: Props) {
  const [files, setFiles] = useState<FileEntry[]>([]);
  const [search, setSearch] = useState('');
  const [showAllFiles, setShowAllFiles] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [total, setTotal] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [expandedFolders, setExpandedFolders] = useState<Set<string>>(new Set());

  const abortControllerRef = useRef<AbortController | null>(null);
  const debouncedSearch = useDebouncedValue(search, 300);

  // Build tree from files
  const fileTree = useMemo(() => buildFileTree(files), [files]);

  // When search is active, show flat list instead of tree
  const isSearching = debouncedSearch.length > 0;

  const loadFiles = useCallback(async (append = false) => {
    // Cancel previous request
    abortControllerRef.current?.abort();
    abortControllerRef.current = new AbortController();

    if (append) {
      setLoadingMore(true);
    } else {
      setLoading(true);
      setError(null);
    }

    try {
      const offset = append ? files.length : 0;
      const result = await listProjectFiles(
        projectId,
        {
          search: debouncedSearch || undefined,
          textOnly: !showAllFiles,
          limit: 500,
          offset,
        },
        abortControllerRef.current.signal
      );

      if (append) {
        setFiles(prev => [...prev, ...result.files]);
      } else {
        setFiles(result.files);
      }
      setTotal(result.total);
      setHasMore(result.has_more);
    } catch (e) {
      if (e instanceof Error && e.name === 'AbortError') return;
      setError(e instanceof Error ? e.message : 'Failed to load files');
    } finally {
      setLoading(false);
      setLoadingMore(false);
    }
  }, [projectId, debouncedSearch, showAllFiles, files.length]);

  // Load on mount and when search/filter changes
  useEffect(() => {
    loadFiles(false);
    return () => abortControllerRef.current?.abort();
  }, [projectId, debouncedSearch, showAllFiles]);

  // Handle Escape key
  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onCancel();
    };
    document.addEventListener('keydown', handleEscape);
    return () => document.removeEventListener('keydown', handleEscape);
  }, [onCancel]);

  const handleToggleFolder = (path: string) => {
    setExpandedFolders(prev => {
      const next = new Set(prev);
      if (next.has(path)) {
        next.delete(path);
      } else {
        next.add(path);
      }
      return next;
    });
  };

  const handleExpandAll = () => {
    const allFolders = new Set<string>();
    const collectFolders = (nodes: TreeNode[]) => {
      for (const node of nodes) {
        if (!node.isFile) {
          allFolders.add(node.fullPath);
          collectFolders(node.children);
        }
      }
    };
    collectFolders(fileTree);
    setExpandedFolders(allFolders);
  };

  const handleCollapseAll = () => {
    setExpandedFolders(new Set());
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* Header */}
      <div style={{ marginBottom: 16 }}>
        <h3 style={{ margin: '0 0 12px 0' }}>Select File</h3>

        {/* Search input */}
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search files..."
          autoFocus
          style={{
            width: '100%',
            padding: '8px 12px',
            border: '1px solid #ddd',
            borderRadius: 4,
            marginBottom: 8,
            boxSizing: 'border-box',
          }}
        />

        {/* Filter and tree controls */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, color: '#666' }}>
            <input
              type="checkbox"
              checked={showAllFiles}
              onChange={(e) => setShowAllFiles(e.target.checked)}
            />
            Show all files
          </label>

          {!isSearching && fileTree.length > 0 && (
            <div style={{ display: 'flex', gap: 8 }}>
              <button
                type="button"
                onClick={handleExpandAll}
                style={{
                  padding: '2px 8px',
                  fontSize: 12,
                  background: '#f5f5f5',
                  border: '1px solid #ddd',
                  borderRadius: 3,
                  cursor: 'pointer',
                }}
              >
                Expand all
              </button>
              <button
                type="button"
                onClick={handleCollapseAll}
                style={{
                  padding: '2px 8px',
                  fontSize: 12,
                  background: '#f5f5f5',
                  border: '1px solid #ddd',
                  borderRadius: 3,
                  cursor: 'pointer',
                }}
              >
                Collapse all
              </button>
            </div>
          )}
        </div>
      </div>

      {/* File count */}
      {!loading && !error && (
        <div style={{ marginBottom: 8, fontSize: 13, color: '#666' }}>
          {total} file{total !== 1 ? 's' : ''} found
          {isSearching && ' (showing flat list)'}
        </div>
      )}

      {/* Error state */}
      {error && (
        <div style={{ padding: 16, background: '#f8d7da', color: '#721c24', borderRadius: 4, marginBottom: 16 }}>
          {error}
          <button onClick={() => loadFiles(false)} style={{ marginLeft: 8 }}>Retry</button>
        </div>
      )}

      {/* Loading state */}
      {loading && (
        <div style={{ padding: 32, textAlign: 'center', color: '#666' }}>Loading files...</div>
      )}

      {/* File list */}
      {!loading && !error && (
        <div style={{ flex: 1, overflow: 'auto', border: '1px solid #eee', borderRadius: 4 }}>
          {files.length === 0 ? (
            <div style={{ padding: 32, textAlign: 'center', color: '#666' }}>
              No files found
            </div>
          ) : isSearching ? (
            // Flat list when searching
            <ul style={{ listStyle: 'none', margin: 0, padding: 0 }}>
              {files.map((file) => (
                <li
                  key={file.path}
                  onClick={() => onSelectFile(file.path)}
                  onKeyDown={(e) => e.key === 'Enter' && onSelectFile(file.path)}
                  tabIndex={0}
                  style={{
                    padding: '10px 12px',
                    cursor: 'pointer',
                    borderBottom: '1px solid #eee',
                    background: 'transparent',
                    transition: 'background 0.1s',
                  }}
                  onMouseEnter={(e) => (e.currentTarget.style.background = '#f5f5f5')}
                  onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
                  onFocus={(e) => (e.currentTarget.style.background = '#f5f5f5')}
                  onBlur={(e) => (e.currentTarget.style.background = 'transparent')}
                >
                  <div style={{ fontFamily: 'monospace', fontSize: 13 }}>{file.path}</div>
                </li>
              ))}
            </ul>
          ) : (
            // Tree view when not searching
            <ul style={{ listStyle: 'none', margin: 0, padding: 0 }}>
              {fileTree.map((node) => (
                <TreeNodeItem
                  key={node.fullPath}
                  node={node}
                  depth={0}
                  expandedFolders={expandedFolders}
                  onToggleFolder={handleToggleFolder}
                  onSelectFile={onSelectFile}
                />
              ))}
            </ul>
          )}

          {/* Load more button */}
          {hasMore && (
            <div style={{ padding: 16, textAlign: 'center' }}>
              <button
                onClick={() => loadFiles(true)}
                disabled={loadingMore}
                style={{ padding: '8px 16px' }}
              >
                {loadingMore ? 'Loading...' : `Load more (${files.length} of ${total})`}
              </button>
            </div>
          )}
        </div>
      )}

      {/* Footer */}
      <div style={{ marginTop: 16, display: 'flex', justifyContent: 'flex-end' }}>
        <button onClick={onCancel}>Cancel</button>
      </div>
    </div>
  );
}
