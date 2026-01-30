# Implementation Plan: Visual Code Browser for Subscription Creation (v2)

## Overview

Add a visual code browser feature to the codesub frontend that enables users to browse git-tracked files in a project, view file contents, and select subscription targets through three modes: clicking semantic constructs, selecting line ranges, or selecting entire files. The existing manual text input remains available.

## Changes from v1

This revision addresses issues identified in internal and external reviews:

| Issue | Resolution |
|-------|------------|
| Large-file pagination not end-to-end | Load full file (up to 5000 lines), warn and truncate beyond |
| Missing `UnsupportedLanguageError` import | Fixed in code snippets |
| O(n) construct map loop | Removed inner loop |
| Path encoding breaks slashes | Changed to query parameter approach |
| File list pagination incomplete | Added offset state + append behavior |
| Repeated git ls-tree per request | Added in-memory cache with TTL |
| Binary files not handled | Filter by text extensions, handle encoding errors |
| Parse error handling for symbols | Wrap in try/except, return graceful error |
| Missing useDebouncedValue hook | Added implementation |
| AbortController missing | Added request cancellation |

## Design Decisions

| Decision | Rationale |
|----------|-----------|
| Use git-tracked files only | Ensures consistency with codesub's diff-based tracking |
| Retrieve files at baseline ref only | Subscriptions are created against baseline; keeps line numbers accurate |
| Full file load (up to 5000 lines) | Simpler than chunked loading; covers 99% of source files; warn beyond |
| Query parameter for file path | Avoids URL encoding issues with slashes in paths |
| Default to code file extensions | Prevents binary file errors; user can toggle "all files" |
| Cache file list per baseline | Avoids repeated git ls-tree on every search keystroke |
| Server-side filtering | Essential for large repos; client sends search term, server filters |

---

## Implementation Steps

### Step 1: Backend - Add `list_files()` to GitRepo

**File:** `src/codesub/git_repo.py`

```python
def list_files(self, ref: str) -> list[str]:
    """
    List all tracked files at a specific ref.

    Args:
        ref: Git ref (commit hash, branch name, etc.).

    Returns:
        List of repo-relative file paths (excludes submodules).

    Raises:
        GitError: If git command fails.
    """
    result = subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", ref],
        cwd=self.root,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise GitError(f"git ls-tree {ref}", result.stderr.strip())

    if not result.stdout.strip():
        return []
    return result.stdout.strip().split("\n")
```

---

### Step 2: Backend - Add File Listing Endpoint with Cache

**File:** `src/codesub/api.py`

```python
from functools import lru_cache
from time import time
from pathlib import Path
from typing import Optional

from .errors import UnsupportedLanguageError

# --- File Browser Schemas ---

class FileEntry(BaseModel):
    """A file in the repository."""
    path: str  # Repo-relative path (e.g., "src/codesub/api.py")
    name: str  # Filename only (e.g., "api.py")
    extension: str  # File extension (e.g., ".py")


class FileListResponse(BaseModel):
    """Response for file listing."""
    files: list[FileEntry]
    total: int
    has_more: bool


# --- File list cache ---
# Cache file lists per (project_id, baseline_ref) for 60 seconds
_file_list_cache: dict[tuple[str, str], tuple[list[str], float]] = {}
_FILE_LIST_CACHE_TTL = 60.0

# Common code/text file extensions
TEXT_EXTENSIONS = {
    ".py", ".java", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".rb", ".php",
    ".c", ".cpp", ".h", ".hpp", ".cs", ".swift", ".kt", ".scala", ".clj",
    ".html", ".css", ".scss", ".sass", ".less", ".json", ".yaml", ".yml",
    ".xml", ".toml", ".ini", ".cfg", ".conf", ".md", ".txt", ".rst", ".sql",
    ".sh", ".bash", ".zsh", ".fish", ".ps1", ".bat", ".cmd", ".makefile",
    ".dockerfile", ".vue", ".svelte", ".astro", ".prisma", ".graphql",
}


def _get_cached_file_list(project_id: str, baseline: str, repo: GitRepo) -> list[str]:
    """Get file list from cache or fetch from git."""
    cache_key = (project_id, baseline)
    now = time()

    if cache_key in _file_list_cache:
        files, cached_at = _file_list_cache[cache_key]
        if now - cached_at < _FILE_LIST_CACHE_TTL:
            return files

    files = repo.list_files(baseline)
    _file_list_cache[cache_key] = (files, now)
    return files


@app.get("/api/projects/{project_id}/files", response_model=FileListResponse)
def list_project_files(
    project_id: str,
    search: Optional[str] = Query(None, description="Filter by path substring"),
    extensions: Optional[str] = Query(None, description="Comma-separated extensions (e.g., '.py,.java')"),
    text_only: bool = Query(default=True, description="Only show common text/code files"),
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    """
    List git-tracked files in a project at the baseline ref.

    By default, filters to common code/text file extensions.
    Results are sorted alphabetically by path.
    """
    store, repo = get_project_store_and_repo(project_id)
    config = store.load()
    baseline = config.repo.baseline_ref

    # Get cached file list
    files = _get_cached_file_list(project_id, baseline, repo)

    # Apply text_only filter (default)
    if text_only and not extensions:
        files = [f for f in files if Path(f).suffix.lower() in TEXT_EXTENSIONS]

    # Apply extension filter if specified
    if extensions:
        ext_list = [e.strip().lower() for e in extensions.split(",")]
        ext_list = ["." + e if not e.startswith(".") else e for e in ext_list]
        files = [f for f in files if Path(f).suffix.lower() in ext_list]

    # Apply search filter
    if search:
        search_lower = search.lower()
        files = [f for f in files if search_lower in f.lower()]

    # Sort and paginate
    files.sort()
    total = len(files)
    paginated = files[offset:offset + limit]

    return FileListResponse(
        files=[
            FileEntry(
                path=f,
                name=Path(f).name,
                extension=Path(f).suffix.lower(),
            )
            for f in paginated
        ],
        total=total,
        has_more=(offset + len(paginated)) < total,
    )
```

---

### Step 3: Backend - Add File Content Endpoint

**File:** `src/codesub/api.py`

**Key changes from v1:**
- Path as query parameter (not path segment)
- Handles encoding errors for binary files
- Uses `get_indexer_for_path` consistently

```python
class FileContentResponse(BaseModel):
    """Response for file content."""
    path: str
    total_lines: int
    lines: list[str]  # Simplified: just strings, frontend adds line numbers
    language: Optional[str] = None
    supports_semantic: bool = False
    truncated: bool = False  # True if file exceeded max lines


MAX_FILE_LINES = 5000  # Hard limit for browser display


@app.get("/api/projects/{project_id}/file-content", response_model=FileContentResponse)
def get_project_file_content(
    project_id: str,
    path: str = Query(..., description="Repo-relative file path"),
):
    """
    Get file content at the project's baseline ref.

    Returns up to 5000 lines. Files larger than this are truncated with a warning.
    """
    store, repo = get_project_store_and_repo(project_id)
    config = store.load()
    baseline = config.repo.baseline_ref

    # Get file content
    try:
        all_lines = repo.show_file(baseline, path)
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=415,
            detail=f"Cannot display binary or non-UTF8 file: {path}"
        )

    total_lines = len(all_lines)
    truncated = total_lines > MAX_FILE_LINES
    lines = all_lines[:MAX_FILE_LINES] if truncated else all_lines

    # Detect language support
    from .semantic import get_indexer_for_path
    language = None
    supports_semantic = False
    try:
        language, _ = get_indexer_for_path(path)
        supports_semantic = True
    except UnsupportedLanguageError:
        pass

    return FileContentResponse(
        path=path,
        total_lines=total_lines,
        lines=lines,
        language=language,
        supports_semantic=supports_semantic,
        truncated=truncated,
    )
```

---

### Step 4: Backend - Add Symbols Endpoint

**File:** `src/codesub/api.py`

**Key changes from v1:**
- Path as query parameter
- Wraps indexer in try/except for parse failures
- Returns empty list with error flag on failure

```python
class ConstructSchema(BaseModel):
    """A semantic construct in the file."""
    kind: str
    qualname: str
    role: Optional[str] = None
    start_line: int
    end_line: int
    target: str  # Ready-to-use location string


class SymbolsResponse(BaseModel):
    """Response for file symbols."""
    path: str
    language: str
    constructs: list[ConstructSchema]
    has_parse_error: bool = False
    error_message: Optional[str] = None


@app.get("/api/projects/{project_id}/file-symbols", response_model=SymbolsResponse)
def get_project_file_symbols(
    project_id: str,
    path: str = Query(..., description="Repo-relative file path"),
    kind: Optional[str] = Query(None, description="Filter by construct kind"),
):
    """
    Get semantic constructs in a file.

    Only works for supported languages (Python, Java).
    Returns all discoverable constructs with their line ranges.
    """
    store, repo = get_project_store_and_repo(project_id)
    config = store.load()
    baseline = config.repo.baseline_ref

    # Get file content
    lines = repo.show_file(baseline, path)
    source = "\n".join(lines)

    # Get indexer
    from .semantic import get_indexer_for_path
    language, indexer = get_indexer_for_path(path)

    # Index file with error handling
    try:
        constructs = indexer.index_file(source, path)
    except Exception as e:
        return SymbolsResponse(
            path=path,
            language=language,
            constructs=[],
            has_parse_error=True,
            error_message=f"Failed to parse file: {e}",
        )

    # Filter by kind if specified
    if kind:
        constructs = [c for c in constructs if c.kind == kind]

    # Check for parse errors in constructs
    has_parse_error = any(c.has_parse_error for c in constructs)

    return SymbolsResponse(
        path=path,
        language=language,
        constructs=[
            ConstructSchema(
                kind=c.kind,
                qualname=c.qualname,
                role=c.role,
                start_line=c.start_line,
                end_line=c.end_line,
                target=f"{path}::{c.qualname}",
            )
            for c in constructs
        ],
        has_parse_error=has_parse_error,
    )
```

---

### Step 5: Frontend - Add Types

**File:** `frontend/src/types.ts`

```typescript
// --- Code Browser Types ---

export interface FileEntry {
  path: string;
  name: string;
  extension: string;
}

export interface FileListResponse {
  files: FileEntry[];
  total: number;
  has_more: boolean;
}

export interface FileContentResponse {
  path: string;
  total_lines: number;
  lines: string[];
  language: string | null;
  supports_semantic: boolean;
  truncated: boolean;
}

export interface ConstructInfo {
  kind: string;
  qualname: string;
  role: string | null;
  start_line: number;
  end_line: number;
  target: string;
}

export interface SymbolsResponse {
  path: string;
  language: string;
  constructs: ConstructInfo[];
  has_parse_error: boolean;
  error_message?: string;
}

export interface CodeBrowserSelection {
  type: 'semantic' | 'lines';
  location: string;
  label?: string;
}
```

---

### Step 6: Frontend - Add API Functions

**File:** `frontend/src/api.ts`

**Key changes from v1:**
- Path as query parameter (no URL encoding issues)
- Proper type imports

```typescript
import type { FileListResponse, FileContentResponse, SymbolsResponse } from './types';

// --- Code Browser API ---

export async function listProjectFiles(
  projectId: string,
  options?: {
    search?: string;
    extensions?: string[];
    textOnly?: boolean;
    limit?: number;
    offset?: number;
  },
  signal?: AbortSignal
): Promise<FileListResponse> {
  const params = new URLSearchParams();
  if (options?.search) params.set('search', options.search);
  if (options?.extensions?.length) params.set('extensions', options.extensions.join(','));
  if (options?.textOnly !== undefined) params.set('text_only', String(options.textOnly));
  if (options?.limit) params.set('limit', options.limit.toString());
  if (options?.offset) params.set('offset', options.offset.toString());

  const url = `${API_BASE}/projects/${projectId}/files?${params}`;
  const response = await fetch(url, { signal });
  return handleResponse<FileListResponse>(response);
}

export async function getProjectFileContent(
  projectId: string,
  path: string,
  signal?: AbortSignal
): Promise<FileContentResponse> {
  const params = new URLSearchParams({ path });
  const url = `${API_BASE}/projects/${projectId}/file-content?${params}`;
  const response = await fetch(url, { signal });
  return handleResponse<FileContentResponse>(response);
}

export async function getProjectFileSymbols(
  projectId: string,
  path: string,
  kind?: string,
  signal?: AbortSignal
): Promise<SymbolsResponse> {
  const params = new URLSearchParams({ path });
  if (kind) params.set('kind', kind);
  const url = `${API_BASE}/projects/${projectId}/file-symbols?${params}`;
  const response = await fetch(url, { signal });
  return handleResponse<SymbolsResponse>(response);
}
```

---

### Step 7: Frontend - Add Utility Hooks

**File:** `frontend/src/hooks.ts` (new file)

```typescript
import { useState, useEffect, useRef } from 'react';

/**
 * Returns a debounced version of the value.
 * Updates only after the specified delay with no new values.
 */
export function useDebouncedValue<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = useState(value);

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);

  return debounced;
}

/**
 * Returns a ref that tracks whether the component is still mounted.
 * Useful for preventing state updates after unmount.
 */
export function useMountedRef(): React.RefObject<boolean> {
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  return mounted;
}
```

---

### Step 8: Frontend - Create FileListPanel Component

**File:** `frontend/src/components/FileListPanel.tsx`

**Key changes from v1:**
- AbortController for request cancellation
- Proper pagination with append behavior
- Error UI
- "Show all files" toggle

```typescript
import { useState, useEffect, useRef, useCallback } from 'react';
import type { FileEntry } from '../types';
import { listProjectFiles } from '../api';
import { useDebouncedValue } from '../hooks';

interface Props {
  projectId: string;
  onSelectFile: (path: string) => void;
  onCancel: () => void;
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

  const abortControllerRef = useRef<AbortController | null>(null);
  const debouncedSearch = useDebouncedValue(search, 300);

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
          limit: 200,
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
          }}
        />

        {/* Filter toggle */}
        <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, color: '#666' }}>
          <input
            type="checkbox"
            checked={showAllFiles}
            onChange={(e) => setShowAllFiles(e.target.checked)}
          />
          Show all files (including non-code)
        </label>
      </div>

      {/* File count */}
      {!loading && !error && (
        <div style={{ marginBottom: 8, fontSize: 13, color: '#666' }}>
          {total} file{total !== 1 ? 's' : ''} found
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
          ) : (
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
                  }}
                  onMouseEnter={(e) => (e.currentTarget.style.background = '#f5f5f5')}
                  onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
                >
                  <div style={{ fontFamily: 'monospace', fontSize: 13 }}>{file.path}</div>
                </li>
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
```

---

### Step 9: Frontend - Create CodeViewerPanel Component

**File:** `frontend/src/components/CodeViewerPanel.tsx`

**Key changes from v1:**
- Fixed construct map (no inner loop)
- AbortController for cancellation
- Truncation warning
- Proper error handling
- Simplified line number handling

```typescript
import { useState, useEffect, useMemo, useRef } from 'react';
import type { FileContentResponse, SymbolsResponse, ConstructInfo, CodeBrowserSelection } from '../types';
import { getProjectFileContent, getProjectFileSymbols } from '../api';

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
      // Symbols failure is non-fatal (just disables semantic selection)

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

  // Build line-to-construct mapping (only start lines are clickable)
  const lineConstructMap = useMemo(() => {
    const map = new Map<number, ConstructInfo>();
    if (!symbols) return map;
    for (const construct of symbols.constructs) {
      // Only map the first line of each construct (handles nesting)
      if (!map.has(construct.start_line)) {
        map.set(construct.start_line, construct);
      }
    }
    return map;
  }, [symbols]);

  // Handle line click
  const handleLineClick = (lineNumber: number, event: React.MouseEvent) => {
    // Check if clicking a construct
    const construct = lineConstructMap.get(lineNumber);
    if (construct && !event.shiftKey) {
      setLineSelection(null);
      setSelectionAnchor(null);
      setSelectedConstruct(construct);
      return;
    }

    // Line selection
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
        <code style={{ flex: 1, fontSize: 13 }}>{filePath}</code>
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
        {content.supports_semantic
          ? 'Click a highlighted construct, or click line numbers to select a range (shift-click to extend)'
          : 'Click line numbers to select a range (shift-click to extend)'}
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
                  onClick={(e) => handleLineClick(lineNum, e)}
                  style={{
                    cursor: 'pointer',
                    background: isInSelection
                      ? '#e3f2fd'
                      : isConstructSelected
                        ? '#c8e6c9'
                        : 'transparent',
                  }}
                >
                  <td style={{
                    padding: '0 12px 0 8px',
                    textAlign: 'right',
                    color: '#999',
                    userSelect: 'none',
                    borderRight: '1px solid #eee',
                    width: 1,
                  }}>
                    {lineNum}
                  </td>
                  <td style={{
                    padding: '0 8px',
                    whiteSpace: 'pre',
                  }}>
                    {construct ? (
                      <span
                        style={{
                          background: selectedConstruct === construct ? '#a5d6a7' : '#e8f5e9',
                          borderRadius: 2,
                          padding: '0 2px',
                        }}
                        title={`${construct.kind}: ${construct.qualname}`}
                      >
                        {line}
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

        <div style={{ flex: 1, fontSize: 13 }}>
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

### Step 10: Frontend - Create CodeBrowserModal Component

**File:** `frontend/src/components/CodeBrowserModal.tsx`

```typescript
import { useState, useRef, useEffect } from 'react';
import type { CodeBrowserSelection } from '../types';
import { FileListPanel } from './FileListPanel';
import { CodeViewerPanel } from './CodeViewerPanel';

interface Props {
  projectId: string;
  onSelect: (selection: CodeBrowserSelection) => void;
  onCancel: () => void;
}

export function CodeBrowserModal({ projectId, onSelect, onCancel }: Props) {
  const [step, setStep] = useState<'file-list' | 'code-viewer'>('file-list');
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const modalRef = useRef<HTMLDivElement>(null);

  // Focus modal on mount
  useEffect(() => {
    modalRef.current?.focus();
  }, []);

  const handleSelectFile = (path: string) => {
    setSelectedFile(path);
    setStep('code-viewer');
  };

  const handleBack = () => {
    setStep('file-list');
    setSelectedFile(null);
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
        tabIndex={-1}
        style={{
          background: 'white',
          borderRadius: 8,
          padding: 24,
          width: '90%',
          maxWidth: 900,
          height: '80vh',
          display: 'flex',
          flexDirection: 'column',
          outline: 'none',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {step === 'file-list' && (
          <FileListPanel
            projectId={projectId}
            onSelectFile={handleSelectFile}
            onCancel={onCancel}
          />
        )}

        {step === 'code-viewer' && selectedFile && (
          <CodeViewerPanel
            projectId={projectId}
            filePath={selectedFile}
            onBack={handleBack}
            onSelect={onSelect}
            onCancel={onCancel}
          />
        )}
      </div>
    </div>
  );
}
```

---

### Step 11: Frontend - Integrate with SubscriptionForm

**File:** `frontend/src/components/SubscriptionForm.tsx`

**Changes:**
- Add import for CodeBrowserModal
- Add state for modal visibility
- Add "Browse..." button
- Handle selection

```typescript
import { useState } from 'react';
import type { Subscription, SubscriptionCreateRequest, SubscriptionUpdateRequest, CodeBrowserSelection } from '../types';
import { createProjectSubscription, updateProjectSubscription } from '../api';
import { CodeBrowserModal } from './CodeBrowserModal';

// ... existing Props interface ...

export function SubscriptionForm({ subscription, projectId, onCancel, onSaved, showMessage }: Props) {
  const isEdit = subscription !== null;

  const [location, setLocation] = useState('');
  const [label, setLabel] = useState(subscription?.label || '');
  const [description, setDescription] = useState(subscription?.description || '');
  const [context, setContext] = useState(2);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showBrowser, setShowBrowser] = useState(false);

  const handleBrowserSelect = (selection: CodeBrowserSelection) => {
    setLocation(selection.location);
    if (selection.label && !label) {
      setLabel(selection.label);
    }
    setShowBrowser(false);
  };

  // ... existing handleSubmit ...

  return (
    <div>
      <h2 style={{ marginBottom: 20, fontSize: 18 }}>
        {isEdit ? 'Edit Subscription' : 'Create Subscription'}
      </h2>

      <form onSubmit={handleSubmit} style={{ maxWidth: 500 }}>
        {!isEdit && (
          <div style={{ marginBottom: 20 }}>
            <label style={{ display: 'block', marginBottom: 6, fontWeight: 600 }}>
              Location <span style={{ color: '#dc3545' }}>*</span>
            </label>
            <div style={{ display: 'flex', gap: 8 }}>
              <input
                type="text"
                value={location}
                onChange={(e) => setLocation(e.target.value)}
                placeholder="path/to/file.py:42 or path/to/file.py::ClassName.method"
                required
                style={{ flex: 1, fontFamily: 'monospace' }}
              />
              <button
                type="button"
                onClick={() => setShowBrowser(true)}
                style={{
                  padding: '8px 16px',
                  border: '1px solid #ddd',
                  borderRadius: 4,
                  cursor: 'pointer',
                  whiteSpace: 'nowrap',
                  background: '#f8f9fa',
                }}
              >
                Browse...
              </button>
            </div>
            <small style={{ color: '#666', display: 'block', marginTop: 4 }}>
              <strong>Line-based:</strong> path:line or path:start-end (e.g., config.py:10-25)
              <br />
              <strong>Semantic:</strong> path::QualifiedName (e.g., auth.py::User.validate)
            </small>
            {location.includes('::') && location.split('::')[1]?.trim() && (
              <div
                style={{
                  marginTop: 8,
                  padding: '8px 12px',
                  background: '#d1ecf1',
                  borderRadius: 4,
                  fontSize: 13,
                  color: '#0c5460',
                }}
              >
                Detected: <strong>semantic subscription</strong>
              </div>
            )}
          </div>
        )}

        {/* ... existing label, description, context fields ... */}

        {error && (
          <div style={{ marginBottom: 20, padding: 12, background: '#f8d7da', color: '#721c24', borderRadius: 4 }}>
            {error}
          </div>
        )}

        <div style={{ display: 'flex', gap: 8 }}>
          <button type="submit" disabled={saving} style={{ background: '#0066cc', color: 'white', borderColor: '#0066cc' }}>
            {saving ? 'Saving...' : (isEdit ? 'Save Changes' : 'Create')}
          </button>
          <button type="button" onClick={onCancel} disabled={saving}>
            Cancel
          </button>
        </div>
      </form>

      {showBrowser && (
        <CodeBrowserModal
          projectId={projectId}
          onSelect={handleBrowserSelect}
          onCancel={() => setShowBrowser(false)}
        />
      )}
    </div>
  );
}
```

---

### Step 12: Backend Tests

**File:** `tests/test_api_files.py` (new file)

```python
"""Tests for code browser API endpoints."""

import pytest
from fastapi.testclient import TestClient

from codesub.api import app

client = TestClient(app)


class TestListProjectFiles:
    """Tests for GET /api/projects/{project_id}/files"""

    def test_list_files_basic(self, registered_project):
        """Lists git-tracked files at baseline."""
        response = client.get(f"/api/projects/{registered_project}/files")
        assert response.status_code == 200
        data = response.json()
        assert "files" in data
        assert "total" in data
        assert "has_more" in data
        assert all("path" in f and "name" in f and "extension" in f for f in data["files"])

    def test_list_files_search(self, registered_project):
        """Filters files by search term."""
        response = client.get(f"/api/projects/{registered_project}/files?search=api")
        assert response.status_code == 200
        data = response.json()
        assert all("api" in f["path"].lower() for f in data["files"])

    def test_list_files_extensions(self, registered_project):
        """Filters files by extension."""
        response = client.get(f"/api/projects/{registered_project}/files?extensions=.py")
        assert response.status_code == 200
        data = response.json()
        assert all(f["extension"] == ".py" for f in data["files"])

    def test_list_files_pagination(self, registered_project):
        """Supports pagination."""
        response = client.get(f"/api/projects/{registered_project}/files?limit=5&offset=0")
        assert response.status_code == 200
        data = response.json()
        assert len(data["files"]) <= 5

    def test_list_files_text_only_default(self, registered_project):
        """Defaults to text/code files only."""
        response = client.get(f"/api/projects/{registered_project}/files")
        assert response.status_code == 200
        # Should not include binary files

    def test_list_files_project_not_found(self):
        """Returns 404 for unknown project."""
        response = client.get("/api/projects/nonexistent/files")
        assert response.status_code == 404


class TestGetFileContent:
    """Tests for GET /api/projects/{project_id}/file-content"""

    def test_get_content_basic(self, registered_project, sample_file):
        """Returns file content with metadata."""
        response = client.get(
            f"/api/projects/{registered_project}/file-content?path={sample_file}"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["path"] == sample_file
        assert "lines" in data
        assert "total_lines" in data
        assert isinstance(data["lines"], list)

    def test_get_content_detects_language(self, registered_project):
        """Detects language for supported files."""
        response = client.get(
            f"/api/projects/{registered_project}/file-content?path=src/main.py"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["language"] == "python"
        assert data["supports_semantic"] is True

    def test_get_content_file_not_found(self, registered_project):
        """Returns 404 for missing file."""
        response = client.get(
            f"/api/projects/{registered_project}/file-content?path=nonexistent.py"
        )
        assert response.status_code == 404


class TestGetFileSymbols:
    """Tests for GET /api/projects/{project_id}/file-symbols"""

    def test_get_symbols_python(self, registered_project, python_file):
        """Returns constructs for Python file."""
        response = client.get(
            f"/api/projects/{registered_project}/file-symbols?path={python_file}"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["language"] == "python"
        assert isinstance(data["constructs"], list)
        for c in data["constructs"]:
            assert "kind" in c
            assert "qualname" in c
            assert "start_line" in c
            assert "target" in c

    def test_get_symbols_unsupported_language(self, registered_project):
        """Returns 400 for unsupported language."""
        response = client.get(
            f"/api/projects/{registered_project}/file-symbols?path=readme.md"
        )
        assert response.status_code == 400

    def test_get_symbols_filter_by_kind(self, registered_project, python_file):
        """Filters constructs by kind."""
        response = client.get(
            f"/api/projects/{registered_project}/file-symbols?path={python_file}&kind=method"
        )
        assert response.status_code == 200
        data = response.json()
        assert all(c["kind"] == "method" for c in data["constructs"])
```

**File:** `tests/test_git_repo.py`

Add tests:
```python
class TestListFiles:
    """Tests for GitRepo.list_files()"""

    def test_list_files_at_head(self, git_repo):
        """Lists files at HEAD."""
        files = git_repo.list_files("HEAD")
        assert isinstance(files, list)
        assert len(files) > 0

    def test_list_files_at_specific_ref(self, git_repo, old_commit):
        """Lists files at specific commit."""
        files = git_repo.list_files(old_commit)
        assert isinstance(files, list)

    def test_list_files_invalid_ref(self, git_repo):
        """Raises error for invalid ref."""
        with pytest.raises(GitError):
            git_repo.list_files("nonexistent-ref")
```

---

## Testing Strategy

### Unit Tests
- [ ] `GitRepo.list_files()` returns correct file list
- [ ] File listing endpoint filters correctly (search, extensions, text_only)
- [ ] File listing endpoint paginates correctly
- [ ] File listing cache works (TTL, invalidation)
- [ ] File content endpoint handles truncation
- [ ] File content endpoint handles binary/encoding errors
- [ ] Symbols endpoint returns constructs with correct line ranges
- [ ] Symbols endpoint handles parse errors gracefully

### Integration Tests
- [ ] Full flow: browse → select file → select construct → create subscription
- [ ] Full flow: browse → select file → select lines → create subscription
- [ ] Full flow: browse → select file → select full file → create subscription
- [ ] Request cancellation on navigation
- [ ] Modal closes on Escape key / backdrop click

### Manual Testing
- [ ] Test with Python mock repo
- [ ] Test with Java mock repo
- [ ] Test with large file (1000+ lines) - verify truncation warning
- [ ] Test with large codebase (100+ files) - verify pagination
- [ ] Test search performance
- [ ] Test binary file handling

---

## File Summary

| File | Action |
|------|--------|
| `src/codesub/git_repo.py` | Add `list_files()` method |
| `src/codesub/api.py` | Add 3 endpoints + schemas + cache |
| `frontend/src/types.ts` | Add types |
| `frontend/src/api.ts` | Add API functions |
| `frontend/src/hooks.ts` | Create (new file) |
| `frontend/src/components/CodeBrowserModal.tsx` | Create |
| `frontend/src/components/FileListPanel.tsx` | Create |
| `frontend/src/components/CodeViewerPanel.tsx` | Create |
| `frontend/src/components/SubscriptionForm.tsx` | Add Browse button + modal |
| `tests/test_api_files.py` | Create |
| `tests/test_git_repo.py` | Add list_files tests |

---

## Decisions Made

| Question | Decision | Rationale |
|----------|----------|-----------|
| Browse baseline only or allow other refs? | Baseline only | Consistency with subscription creation |
| Large file strategy? | Load full (up to 5000 lines), truncate with warning | Simpler than chunking; covers 99% of files |
| Include kind in location string? | No, use `path::qualname` | Matches existing CLI/API behavior |
| Exclude non-text files by default? | Yes, with toggle | Prevents binary file errors |
