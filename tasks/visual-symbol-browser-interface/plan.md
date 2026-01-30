# Implementation Plan: Visual Code Browser for Subscription Creation

## Overview

Add a visual code browser feature to the codesub frontend that enables users to browse git-tracked files in a project, view file contents with syntax highlighting, and select subscription targets through three modes: clicking semantic constructs, selecting line ranges, or selecting entire files. The existing manual text input will remain available alongside the browser.

## Design Decisions

| Decision | Rationale |
|----------|-----------|
| Use git-tracked files only | Ensures consistency with how codesub works (subscriptions track changes via git diff); prevents subscribing to untracked files |
| Retrieve files at baseline ref | Subscriptions are always created against the baseline; using baseline ref ensures line numbers and constructs match what will be tracked |
| Two-step modal flow (file list -> code viewer) | Keeps each step focused; file list can be optimized separately from code viewer |
| Virtual scrolling for large files | Files can have thousands of lines; virtual scrolling prevents DOM bloat and improves performance |
| Server-side file filtering | Large codebases may have thousands of files; filtering server-side prevents sending all filenames to client |
| Highlight constructs inline in code viewer | Visual cues help users understand what can be clicked; matches VS Code / IDE patterns |
| Line selection via click-drag | Intuitive interaction pattern familiar from text editors |

**Alternative Approaches Considered:**
- **Single-step modal with split pane**: More complex UI, harder to optimize, requires simultaneous file tree and code display
- **Client-side file filtering**: Would require sending all file paths upfront; impractical for large repos (10k+ files)
- **Separate line/semantic modes with toggle**: More friction; instead we allow both simultaneously (click construct OR select lines)

## Prerequisites

- Baseline ref must be set for the project (required for `git ls-files` at ref)
- Python and/or Java files for semantic constructs (line selection works for any file type)

---

## Implementation Steps

### Step 1: Backend - Add File Listing Endpoint

**File:** `/Users/vlad/dev/projects/codesub/src/codesub/api.py`

**Changes:**
- Add new Pydantic schemas for file listing
- Add endpoint `GET /api/projects/{project_id}/files` to list git-tracked files

**Code:**
```python
# --- File Browser Schemas ---

class FileEntry(BaseModel):
    """A file in the repository."""
    path: str  # Repo-relative path (e.g., "src/codesub/api.py")
    name: str  # Filename only (e.g., "api.py")
    extension: str  # File extension (e.g., ".py")


class FileListRequest(BaseModel):
    """Query parameters for file listing."""
    search: Optional[str] = Field(None, description="Filter files by path substring")
    extensions: Optional[list[str]] = Field(None, description="Filter by extensions (e.g., ['.py', '.java'])")
    limit: int = Field(default=200, ge=1, le=1000, description="Maximum files to return")
    offset: int = Field(default=0, ge=0, description="Offset for pagination")


class FileListResponse(BaseModel):
    """Response for file listing."""
    files: list[FileEntry]
    total: int  # Total matching files (for pagination)
    has_more: bool


# --- Endpoint ---

@app.get("/api/projects/{project_id}/files", response_model=FileListResponse)
def list_project_files(
    project_id: str,
    search: Optional[str] = Query(None),
    extensions: Optional[str] = Query(None, description="Comma-separated extensions"),
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
):
    """
    List git-tracked files in a project at the baseline ref.

    Supports filtering by path substring and file extensions.
    Results are sorted alphabetically by path.
    """
    store, repo = get_project_store_and_repo(project_id)
    config = store.load()
    baseline = config.repo.baseline_ref

    # Get list of tracked files at baseline
    # Use: git ls-tree -r --name-only <ref>
    files = repo.list_files(baseline)

    # Parse extensions if provided
    ext_filter = None
    if extensions:
        ext_filter = [e.strip().lower() for e in extensions.split(",")]
        if not all(e.startswith(".") for e in ext_filter):
            ext_filter = ["." + e if not e.startswith(".") else e for e in ext_filter]

    # Apply filters
    if search:
        search_lower = search.lower()
        files = [f for f in files if search_lower in f.lower()]

    if ext_filter:
        files = [f for f in files if Path(f).suffix.lower() in ext_filter]

    # Sort and paginate
    files.sort()
    total = len(files)
    files = files[offset:offset + limit]

    return FileListResponse(
        files=[
            FileEntry(
                path=f,
                name=Path(f).name,
                extension=Path(f).suffix.lower(),
            )
            for f in files
        ],
        total=total,
        has_more=(offset + len(files)) < total,
    )
```

**File:** `/Users/vlad/dev/projects/codesub/src/codesub/git_repo.py`

**Changes:**
- Add `list_files(ref: str)` method to GitRepo class

**Code:**
```python
def list_files(self, ref: str) -> list[str]:
    """
    List all tracked files at a specific ref.

    Args:
        ref: Git ref (commit hash, branch name, etc.).

    Returns:
        List of repo-relative file paths.
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

### Step 2: Backend - Add File Content Endpoint

**File:** `/Users/vlad/dev/projects/codesub/src/codesub/api.py`

**Changes:**
- Add schemas for file content response
- Add endpoint `GET /api/projects/{project_id}/files/{path:path}/content`

**Code:**
```python
class LineInfo(BaseModel):
    """Information about a single line."""
    number: int  # 1-based line number
    content: str  # Line content (without newline)


class FileContentResponse(BaseModel):
    """Response for file content."""
    path: str
    total_lines: int
    lines: list[LineInfo]
    language: Optional[str] = None  # Detected language if supported
    supports_semantic: bool = False  # Whether semantic constructs can be extracted


@app.get("/api/projects/{project_id}/files/{path:path}/content")
def get_project_file_content(
    project_id: str,
    path: str,
    start_line: int = Query(default=1, ge=1),
    limit: int = Query(default=500, ge=1, le=2000),
):
    """
    Get file content at the project's baseline ref.

    Returns lines with 1-based line numbers. Supports pagination for large files.
    """
    store, repo = get_project_store_and_repo(project_id)
    config = store.load()
    baseline = config.repo.baseline_ref

    # Get file content
    all_lines = repo.show_file(baseline, path)
    total_lines = len(all_lines)

    # Paginate
    end_line = min(start_line - 1 + limit, total_lines)
    lines = all_lines[start_line - 1:end_line]

    # Detect language support
    from .semantic import detect_language, supported_languages
    language = None
    supports_semantic = False
    try:
        language = detect_language(path)
        supports_semantic = True
    except UnsupportedLanguageError:
        pass

    return FileContentResponse(
        path=path,
        total_lines=total_lines,
        lines=[
            LineInfo(number=start_line + i, content=line)
            for i, line in enumerate(lines)
        ],
        language=language,
        supports_semantic=supports_semantic,
    )
```

---

### Step 3: Backend - Add Symbols Endpoint

**File:** `/Users/vlad/dev/projects/codesub/src/codesub/api.py`

**Changes:**
- Add schemas for construct/symbol response
- Add endpoint `GET /api/projects/{project_id}/files/{path:path}/symbols`

**Code:**
```python
class ConstructSchema(BaseModel):
    """A semantic construct in the file."""
    kind: str  # "variable"|"field"|"method"|"class"|"interface"|"enum"
    qualname: str  # "MAX_RETRIES" | "User.role" | "Calculator.add(int,int)"
    role: Optional[str] = None  # "const" for constants
    start_line: int  # 1-based
    end_line: int  # 1-based inclusive
    # Target string for subscription creation
    target: str  # "path::qualname" or "path::kind:qualname"


class SymbolsResponse(BaseModel):
    """Response for file symbols."""
    path: str
    language: str
    constructs: list[ConstructSchema]
    has_parse_error: bool = False


@app.get("/api/projects/{project_id}/files/{path:path}/symbols", response_model=SymbolsResponse)
def get_project_file_symbols(
    project_id: str,
    path: str,
    kind: Optional[str] = Query(None, description="Filter by kind"),
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

    # Index file
    constructs = indexer.index_file(source, path)

    # Filter by kind if specified
    if kind:
        constructs = [c for c in constructs if c.kind == kind]

    # Check for parse errors
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

### Step 4: Frontend - Add Types and API Functions

**File:** `/Users/vlad/dev/projects/codesub/frontend/src/types.ts`

**Changes:**
- Add types for file browser, file content, and symbols

**Code:**
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

export interface LineInfo {
  number: number;
  content: string;
}

export interface FileContentResponse {
  path: string;
  total_lines: number;
  lines: LineInfo[];
  language: string | null;
  supports_semantic: boolean;
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
}

// Selection result from code browser
export interface CodeBrowserSelection {
  type: 'semantic' | 'line-range' | 'full-file';
  location: string;  // Ready-to-use location string
  label?: string;    // Suggested label
}
```

**File:** `/Users/vlad/dev/projects/codesub/frontend/src/api.ts`

**Changes:**
- Add API functions for file listing, content, and symbols

**Code:**
```typescript
// --- Code Browser API ---

export async function listProjectFiles(
  projectId: string,
  options?: {
    search?: string;
    extensions?: string[];
    limit?: number;
    offset?: number;
  }
): Promise<FileListResponse> {
  const params = new URLSearchParams();
  if (options?.search) params.set('search', options.search);
  if (options?.extensions?.length) params.set('extensions', options.extensions.join(','));
  if (options?.limit) params.set('limit', options.limit.toString());
  if (options?.offset) params.set('offset', options.offset.toString());

  const url = `${API_BASE}/projects/${projectId}/files?${params}`;
  const response = await fetch(url);
  return handleResponse<FileListResponse>(response);
}

export async function getProjectFileContent(
  projectId: string,
  path: string,
  options?: {
    startLine?: number;
    limit?: number;
  }
): Promise<FileContentResponse> {
  const params = new URLSearchParams();
  if (options?.startLine) params.set('start_line', options.startLine.toString());
  if (options?.limit) params.set('limit', options.limit.toString());

  const url = `${API_BASE}/projects/${projectId}/files/${encodeURIComponent(path)}/content?${params}`;
  const response = await fetch(url);
  return handleResponse<FileContentResponse>(response);
}

export async function getProjectFileSymbols(
  projectId: string,
  path: string,
  kind?: string
): Promise<SymbolsResponse> {
  const params = new URLSearchParams();
  if (kind) params.set('kind', kind);

  const url = `${API_BASE}/projects/${projectId}/files/${encodeURIComponent(path)}/symbols?${params}`;
  const response = await fetch(url);
  return handleResponse<SymbolsResponse>(response);
}
```

---

### Step 5: Frontend - Create CodeBrowserModal Component

**File:** `/Users/vlad/dev/projects/codesub/frontend/src/components/CodeBrowserModal.tsx`

**Changes:**
- Create new modal component with two-step flow

**Structure:**
```
CodeBrowserModal
├── State: step ('file-list' | 'code-viewer')
├── FileListPanel (when step='file-list')
│   ├── Search input
│   ├── Extension filter chips
│   ├── Scrollable file list
│   └── Load more / pagination
└── CodeViewerPanel (when step='code-viewer')
    ├── Header with file path + back button
    ├── Selection mode indicator
    ├── Code viewer with line numbers
    │   ├── Construct highlighting (clickable regions)
    │   └── Line selection (click-drag or shift-click)
    └── Selection summary + confirm button
```

**Key Implementation Details:**

```typescript
interface Props {
  projectId: string;
  onSelect: (selection: CodeBrowserSelection) => void;
  onCancel: () => void;
}

export function CodeBrowserModal({ projectId, onSelect, onCancel }: Props) {
  const [step, setStep] = useState<'file-list' | 'code-viewer'>('file-list');
  const [selectedFile, setSelectedFile] = useState<string | null>(null);

  // File list state
  const [files, setFiles] = useState<FileEntry[]>([]);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);

  // Code viewer state
  const [fileContent, setFileContent] = useState<FileContentResponse | null>(null);
  const [symbols, setSymbols] = useState<SymbolsResponse | null>(null);
  const [selection, setSelection] = useState<{
    type: 'semantic' | 'line-range' | 'full-file';
    construct?: ConstructInfo;
    startLine?: number;
    endLine?: number;
  } | null>(null);

  // ... implementation
}
```

---

### Step 6: Frontend - Create FileListPanel Component

**File:** `/Users/vlad/dev/projects/codesub/frontend/src/components/FileListPanel.tsx`

**Features:**
- Search input with debouncing (300ms)
- Extension filter chips (.py, .java, all)
- Virtualized file list for large result sets
- Click file to proceed to code viewer
- Loading and empty states

**Code (key parts):**
```typescript
interface Props {
  projectId: string;
  onSelectFile: (path: string) => void;
  onCancel: () => void;
}

export function FileListPanel({ projectId, onSelectFile, onCancel }: Props) {
  const [files, setFiles] = useState<FileEntry[]>([]);
  const [search, setSearch] = useState('');
  const [extensions, setExtensions] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [total, setTotal] = useState(0);
  const [hasMore, setHasMore] = useState(false);

  // Debounced search
  const debouncedSearch = useDebouncedValue(search, 300);

  useEffect(() => {
    loadFiles();
  }, [projectId, debouncedSearch, extensions]);

  const loadFiles = async () => {
    setLoading(true);
    try {
      const result = await listProjectFiles(projectId, {
        search: debouncedSearch || undefined,
        extensions: extensions.length ? extensions : undefined,
        limit: 200,
      });
      setFiles(result.files);
      setTotal(result.total);
      setHasMore(result.has_more);
    } catch (e) {
      // Handle error
    } finally {
      setLoading(false);
    }
  };

  // ... render file list with search, filters, and scrolling
}
```

---

### Step 7: Frontend - Create CodeViewerPanel Component

**File:** `/Users/vlad/dev/projects/codesub/frontend/src/components/CodeViewerPanel.tsx`

**Features:**
- Header with file path, language badge, back button
- Line numbers gutter
- Code display with monospace font
- Construct highlighting (clickable regions with hover/selection state)
- Line selection via click + shift-click
- Selection summary bar at bottom
- Confirm selection button

**Code (key parts):**
```typescript
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

  // Selection state
  const [selectedConstruct, setSelectedConstruct] = useState<ConstructInfo | null>(null);
  const [lineSelection, setLineSelection] = useState<{ start: number; end: number } | null>(null);
  const [selectionAnchor, setSelectionAnchor] = useState<number | null>(null);

  // Load content and symbols on mount
  useEffect(() => {
    loadFileData();
  }, [projectId, filePath]);

  const loadFileData = async () => {
    setLoading(true);
    try {
      const [contentResult, symbolsResult] = await Promise.allSettled([
        getProjectFileContent(projectId, filePath),
        getProjectFileSymbols(projectId, filePath),
      ]);

      if (contentResult.status === 'fulfilled') {
        setContent(contentResult.value);
      }
      if (symbolsResult.status === 'fulfilled') {
        setSymbols(symbolsResult.value);
      }
    } finally {
      setLoading(false);
    }
  };

  // Build line-to-construct mapping for highlighting
  const lineConstructMap = useMemo(() => {
    if (!symbols) return new Map<number, ConstructInfo>();
    const map = new Map<number, ConstructInfo>();
    for (const construct of symbols.constructs) {
      for (let line = construct.start_line; line <= construct.end_line; line++) {
        // First line of construct is clickable (to handle overlapping)
        if (line === construct.start_line) {
          map.set(line, construct);
        }
      }
    }
    return map;
  }, [symbols]);

  // Handle line click for selection
  const handleLineClick = (lineNumber: number, event: React.MouseEvent) => {
    // Clear construct selection when doing line selection
    setSelectedConstruct(null);

    if (event.shiftKey && selectionAnchor !== null) {
      // Extend selection
      const start = Math.min(selectionAnchor, lineNumber);
      const end = Math.max(selectionAnchor, lineNumber);
      setLineSelection({ start, end });
    } else {
      // Start new selection
      setSelectionAnchor(lineNumber);
      setLineSelection({ start: lineNumber, end: lineNumber });
    }
  };

  // Handle construct click
  const handleConstructClick = (construct: ConstructInfo) => {
    setLineSelection(null);
    setSelectionAnchor(null);
    setSelectedConstruct(construct);
  };

  // Build location string
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
      return {
        type: 'line-range',
        location,
      };
    }
    return null;
  };

  // ... render code viewer with highlighting and selection UI
}
```

---

### Step 8: Frontend - Integrate with SubscriptionForm

**File:** `/Users/vlad/dev/projects/codesub/frontend/src/components/SubscriptionForm.tsx`

**Changes:**
- Add "Browse" button next to location input
- Add state for modal visibility
- Handle selection from modal

**Code:**
```typescript
export function SubscriptionForm({ subscription, projectId, onCancel, onSaved, showMessage }: Props) {
  // ... existing state
  const [showBrowser, setShowBrowser] = useState(false);

  const handleBrowserSelect = (selection: CodeBrowserSelection) => {
    setLocation(selection.location);
    if (selection.label && !label) {
      setLabel(selection.label);
    }
    setShowBrowser(false);
  };

  return (
    <div>
      {/* ... existing form header */}

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
                }}
              >
                Browse...
              </button>
            </div>
            {/* ... existing helper text */}
          </div>
        )}

        {/* ... rest of form */}
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

### Step 9: Frontend - Add Full File Selection Option

**File:** `/Users/vlad/dev/projects/codesub/frontend/src/components/CodeViewerPanel.tsx`

**Changes:**
- Add "Select Full File" button in selection bar
- Generate location as `path:1-{total_lines}`

**Code:**
```typescript
// In the selection bar
<div style={{ display: 'flex', gap: 8 }}>
  <button
    type="button"
    onClick={() => {
      if (content) {
        setLineSelection({ start: 1, end: content.total_lines });
        setSelectedConstruct(null);
      }
    }}
    style={{ padding: '6px 12px', border: '1px solid #ddd', borderRadius: 4 }}
  >
    Select Full File
  </button>

  {getSelectionResult() && (
    <button
      type="button"
      onClick={() => {
        const result = getSelectionResult();
        if (result) onSelect(result);
      }}
      style={{
        padding: '6px 12px',
        background: '#0066cc',
        color: 'white',
        border: 'none',
        borderRadius: 4,
      }}
    >
      Use Selection
    </button>
  )}
</div>
```

---

### Step 10: Add Large File Warning

**File:** `/Users/vlad/dev/projects/codesub/frontend/src/components/CodeViewerPanel.tsx`

**Changes:**
- Show warning for files over 1000 lines
- Offer to load in chunks or proceed anyway

**Code:**
```typescript
const LARGE_FILE_THRESHOLD = 1000;

// In CodeViewerPanel
const [showLargeFileWarning, setShowLargeFileWarning] = useState(false);
const [loadFullFile, setLoadFullFile] = useState(false);

useEffect(() => {
  if (content && content.total_lines > LARGE_FILE_THRESHOLD && !loadFullFile) {
    setShowLargeFileWarning(true);
  }
}, [content]);

// In render
{showLargeFileWarning && (
  <div style={{
    padding: 16,
    background: '#fff3cd',
    border: '1px solid #ffc107',
    borderRadius: 4,
    marginBottom: 16,
  }}>
    <strong>Large File</strong>
    <p>This file has {content?.total_lines} lines. Loading may be slow.</p>
    <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
      <button onClick={() => { setLoadFullFile(true); setShowLargeFileWarning(false); }}>
        Load Anyway
      </button>
      <button onClick={onBack}>Choose Different File</button>
    </div>
  </div>
)}
```

---

### Step 11: Backend Tests

**File:** `/Users/vlad/dev/projects/codesub/tests/test_api_files.py`

**Test Cases:**
```python
# test_list_project_files_basic
# test_list_project_files_with_search
# test_list_project_files_with_extension_filter
# test_list_project_files_pagination
# test_list_project_files_empty_repo
# test_list_project_files_project_not_found

# test_get_file_content_basic
# test_get_file_content_pagination
# test_get_file_content_file_not_found
# test_get_file_content_detects_language

# test_get_file_symbols_python
# test_get_file_symbols_java
# test_get_file_symbols_unsupported_language
# test_get_file_symbols_filter_by_kind
# test_get_file_symbols_file_not_found
```

**File:** `/Users/vlad/dev/projects/codesub/tests/test_git_repo.py`

**Test Cases:**
```python
# test_list_files_at_head
# test_list_files_at_specific_ref
# test_list_files_empty_repo
# test_list_files_invalid_ref
```

---

### Step 12: Frontend Tests

**Files:**
- `/Users/vlad/dev/projects/codesub/frontend/src/components/__tests__/CodeBrowserModal.test.tsx`
- `/Users/vlad/dev/projects/codesub/frontend/src/components/__tests__/FileListPanel.test.tsx`
- `/Users/vlad/dev/projects/codesub/frontend/src/components/__tests__/CodeViewerPanel.test.tsx`

**Test Cases:**
- Modal opens and closes correctly
- File list loads and displays files
- Search filters files
- Extension filter works
- File selection navigates to code viewer
- Code viewer displays file content with line numbers
- Construct highlighting appears for supported files
- Clicking construct selects it
- Shift-click selects line range
- Selection summary updates correctly
- Confirm button returns correct location string
- Large file warning appears
- Unsupported language shows line-only mode

---

## Testing Strategy

### Unit Tests
- [ ] `GitRepo.list_files()` returns correct file list
- [ ] File listing endpoint filters correctly
- [ ] File content endpoint paginates correctly
- [ ] Symbols endpoint returns constructs with correct line ranges
- [ ] Symbols endpoint handles unsupported languages gracefully

### Integration Tests
- [ ] Full flow: browse -> select file -> select construct -> create subscription
- [ ] Full flow: browse -> select file -> select lines -> create subscription
- [ ] Full flow: browse -> select file -> select full file -> create subscription
- [ ] Modal closes on Escape key
- [ ] Modal closes on outside click
- [ ] Browser back button works from code viewer step

### Manual Testing
- [ ] Test with Python mock repo (many constructs)
- [ ] Test with Java mock repo (overloaded methods)
- [ ] Test with large file (1000+ lines)
- [ ] Test with large codebase (100+ files)
- [ ] Test search performance with many files

---

## Edge Cases Considered

1. **Empty repository**: Show "No files found" message
2. **No Python/Java files**: Show info that semantic selection unavailable
3. **Parse errors in file**: Show warning, still allow line selection
4. **File deleted between listing and viewing**: Show error, allow going back
5. **Very long lines**: Horizontal scroll in code viewer
6. **Nested constructs**: First line of each construct is clickable
7. **Unicode in file content**: Ensure proper encoding handling
8. **Binary files**: Skip in file listing (or filter by known text extensions)

---

## Risks and Mitigations

**Risk:** Large repository performance (10k+ files)
**Mitigation:** Server-side filtering, pagination, limit of 200 files per request, search debouncing

**Risk:** Large file rendering (5000+ lines)
**Mitigation:** Warning dialog, virtual scrolling consideration for future, load content in chunks

**Risk:** Tree-sitter parse errors breaking symbols
**Mitigation:** Graceful degradation to line-only mode, show warning but continue

**Risk:** Race conditions in async loading
**Mitigation:** Request ID tracking (pattern from FileBrowserModal), cancel stale requests

---

## File Summary

### Backend Files to Create/Modify
| File | Action |
|------|--------|
| `/Users/vlad/dev/projects/codesub/src/codesub/api.py` | Add 3 endpoints + schemas |
| `/Users/vlad/dev/projects/codesub/src/codesub/git_repo.py` | Add `list_files()` method |
| `/Users/vlad/dev/projects/codesub/tests/test_api_files.py` | Create (new file) |

### Frontend Files to Create/Modify
| File | Action |
|------|--------|
| `/Users/vlad/dev/projects/codesub/frontend/src/types.ts` | Add types |
| `/Users/vlad/dev/projects/codesub/frontend/src/api.ts` | Add API functions |
| `/Users/vlad/dev/projects/codesub/frontend/src/components/CodeBrowserModal.tsx` | Create (new file) |
| `/Users/vlad/dev/projects/codesub/frontend/src/components/FileListPanel.tsx` | Create (new file) |
| `/Users/vlad/dev/projects/codesub/frontend/src/components/CodeViewerPanel.tsx` | Create (new file) |
| `/Users/vlad/dev/projects/codesub/frontend/src/components/SubscriptionForm.tsx` | Add Browse button |
