# Problem Statement: Visual Code Browser for Subscription Creation

## Task Type
**Type:** feature

## User Decision (Clarified Scope)

The user has clarified the desired UX flow:

**Two-step approach:**
1. **File Browser** - Browse and select a file from git-tracked files
2. **Code Viewer** - View the file with three selection modes:
   - **Construct selection**: Click on a semantic construct (for Python/Java)
   - **Line selection**: Select a line range
   - **Full file**: Select the entire file

**Important**: Keep the existing text input for manual path entry (power users).
- The visual browser is an *enhancement*, not a replacement
- Users can still type `path/to/file.py:10-25` or `path/to/file.py::Class.method` directly

This is a focused version of Approach C (Hybrid) from the analysis below.

---

## Current State

### Subscription Creation Flow
Currently, when creating a subscription in the codesub frontend, users must manually type a location string in one of two formats:

1. **Line-based subscriptions**: `path/to/file.py:42` or `path/to/file.py:10-25`
2. **Semantic subscriptions**: `path/to/file.py::ClassName.method` or `path/to/file.py::kind:QualifiedName`

This is implemented in `/Users/vlad/dev/projects/codesub/frontend/src/components/SubscriptionForm.tsx` (lines 64-96), which displays:
- A text input with monospace font
- Placeholder text showing example formats
- Helper text explaining both subscription types
- Auto-detection visual feedback when `::` is detected for semantic subscriptions

### Backend Capabilities
The codesub backend already has several relevant capabilities:

1. **CLI symbols command** (`codesub symbols path/to/file.py`):
   - Implemented in `/Users/vlad/dev/projects/codesub/src/codesub/cli.py` (lines 469-535)
   - Uses semantic indexers (Tree-sitter based) to discover code constructs
   - Returns: kind, qualname, start_line, end_line, role
   - Supports filtering by kind and grep patterns
   - Supports both Python and Java currently

2. **Semantic indexer infrastructure** (`/Users/vlad/dev/projects/codesub/src/codesub/semantic/`):
   - Language detection by file extension
   - Construct extraction for Python (variables, fields, methods, classes, enums)
   - Construct extraction for Java (classes, fields, methods, constructors, enum constants)
   - Fingerprinting (interface_hash, body_hash) for change detection

3. **Git operations** (`/Users/vlad/dev/projects/codesub/src/codesub/git_repo.py`):
   - Can retrieve file content at any git ref (`show_file`)
   - No existing method to list files in repository

4. **No API endpoint** for listing git-tracked files or symbols:
   - The `/api/filesystem/browse` endpoint (lines 850-923 in `api.py`) only browses directories, not git-tracked files
   - No `/api/symbols` or `/api/files` endpoints exist

### User Experience Pain Points
- Users must know exact file paths relative to repository root
- Users must know exact qualified names for semantic subscriptions
- No discoverability of available code constructs
- High cognitive load: must switch to terminal to run `codesub symbols` command
- Prone to typos and syntax errors in location strings
- No visual feedback until submission (and potential error)

## Desired State

Users should be able to visually browse and select code to subscribe to through an interactive UI that:

1. **Browses the project's git-tracked files** (not filesystem directories)
2. **Displays file contents** at the current baseline ref
3. **Highlights clickable code constructs** (for semantic subscriptions) or line ranges (for line-based)
4. **Auto-generates the correct location string** when user clicks

The ideal workflow would be:
1. User clicks "New Subscription" button
2. UI presents a file browser showing git-tracked files in the project
3. User selects a file
4. UI displays file content with:
   - Line numbers
   - For supported languages (Python/Java): highlighted/clickable semantic constructs
   - Option to select arbitrary line ranges
5. User clicks a construct or selects lines
6. Location field is automatically populated with correct syntax
7. User adds label/description and submits

## Constraints

### Technical Constraints
1. **Performance with large codebases**
   - Some projects may have thousands of files
   - Git operations can be slow on large repos
   - Tree-sitter parsing can be CPU-intensive
   - Frontend bundle size should remain reasonable

2. **Handling large files**
   - Some source files can be thousands of lines
   - Need pagination, virtualization, or lazy loading
   - Syntax highlighting large files can freeze UI

3. **Git baseline synchronization**
   - Must use project's configured baseline ref (not HEAD or working directory)
   - File content must match what subscription will be created against
   - Baseline ref is stored per-project in `.codesub/config.json`

4. **Language support limitations**
   - Semantic indexing only supports Python and Java currently
   - Other file types can only use line-based subscriptions
   - Need graceful degradation for unsupported languages

5. **Multi-project context**
   - Each project has its own baseline ref
   - Git repo root differs per project
   - Must respect project isolation

### Business Constraints
1. Must maintain backward compatibility with manual text input (power users may prefer typing)
2. Should not significantly increase frontend bundle size
3. Must work with existing API architecture (no breaking changes)

### UX Constraints
1. Should feel responsive even for large repos
2. Must be accessible (keyboard navigation, screen readers)
3. Should provide clear feedback during loading states
4. Must handle errors gracefully (file not found, parse errors, etc.)

## Affected Areas

### Backend (New API Endpoints Needed)
- `GET /api/projects/{project_id}/files` - List git-tracked files at baseline ref
  - Response: `{ files: [{ path: string, language?: string, size?: number }] }`
  - May need pagination/filtering for large repos

- `GET /api/projects/{project_id}/files/{file_path}` - Get file content + metadata
  - Query params: `?ref=baseline` (default)
  - Response: `{ content: string, lines: string[], language?: string, baseline_ref: string }`

- `GET /api/projects/{project_id}/symbols/{file_path}` - Get semantic constructs
  - Query params: `?ref=baseline` (default), `?kind=method`, `?grep=pattern`
  - Response: `{ constructs: Construct[], language: string }`
  - Based on existing `cmd_symbols` CLI implementation

### Frontend (New Components)
- `CodeBrowser.tsx` or `CodeBrowserModal.tsx` - Main browsing interface
- `FileTree.tsx` or `FileList.tsx` - Git-tracked file navigation
- `CodeViewer.tsx` - Display file with line numbers and construct highlights
- `ConstructPicker.tsx` - Interactive construct selection
- `LineRangePicker.tsx` - Interactive line range selection
- Modified `SubscriptionForm.tsx` - Add "Browse Code" button/mode

### Shared
- `/Users/vlad/dev/projects/codesub/frontend/src/types.ts` - Add new type definitions
- `/Users/vlad/dev/projects/codesub/frontend/src/api.ts` - Add API client functions

## Acceptance Criteria

### Must Have
- [ ] Users can open a code browser when creating a subscription
- [ ] Users can see a list of git-tracked files in the project (at baseline ref)
- [ ] Users can select a file and view its content with line numbers
- [ ] For Python/Java files: users can see and click on semantic constructs
- [ ] For any file: users can select a line range (click start line, click end line)
- [ ] Selected construct or line range auto-populates the location field in correct syntax
- [ ] Browser uses the project's baseline ref (not HEAD or working directory)
- [ ] Loading states are shown during git/parsing operations
- [ ] Errors are handled gracefully (file not found, parse errors, unsupported language)

### Should Have
- [ ] File list is searchable/filterable by name
- [ ] File list shows language indicators for supported languages
- [ ] Code viewer has basic syntax highlighting
- [ ] Large files are handled performantly (virtualization or pagination)
- [ ] Manual text input option remains available for power users
- [ ] Keyboard navigation works throughout the browser

### Nice to Have
- [ ] File list shows file size or line count
- [ ] Construct picker shows construct signatures/types
- [ ] Preview of selected code appears before finalizing
- [ ] Recently used files appear at top of list
- [ ] Can switch between baseline ref and other refs for preview

## Questions

### Critical (Must answer before implementation)

1. **API Design - File Listing**:
   - Should we paginate the file list, or return all files and filter client-side?
   - How do we efficiently get the list of git-tracked files at a specific ref?
     - `git ls-tree -r --name-only <ref>` for all files?
     - Filter by extension on backend or frontend?
   - Should we detect language eagerly (backend) or lazily (when file opened)?

2. **Performance - Large Codebases**:
   - What's the upper bound for "acceptable" repo size?
   - Should we set hard limits (e.g., max 10,000 files, max 5,000 lines per file)?
   - Should initial file list load be async/progressive, or block until complete?
   - Do we need server-side caching of file lists/symbols per baseline ref?

3. **Performance - Large Files**:
   - What's the max file size we should display in full?
   - Should we use virtual scrolling (react-window, react-virtuoso)?
   - Or should we paginate (e.g., show 500 lines at a time)?
   - How do we handle syntax highlighting performance?

4. **UX Flow**:
   - Should code browser be a modal, sidebar, or inline component?
   - Should it replace the text input, or complement it (toggle between modes)?
   - When user closes browser without selecting, should text input be cleared or preserved?
   - Should we remember user's last browsed file/location?

5. **Syntax Highlighting**:
   - Should we add syntax highlighting? (Increases bundle size)
   - Use lightweight solution (Prism.js ~2KB) or full-featured (Monaco ~500KB)?
   - Or skip highlighting and just show plain text with construct highlights?

6. **Backward Compatibility**:
   - Should the text input always be visible, with browser as optional enhancement?
   - Or should we have a toggle: "Manual Input" vs "Browse Code"?

### Nice to Have (Can defer)

7. **Caching Strategy**:
   - Should frontend cache file lists/contents in memory?
   - Should backend cache symbol indexes per project+baseline?
   - How do we invalidate caches when baseline changes?

8. **Advanced Features**:
   - Should we support multi-file search across entire codebase?
   - Should we allow creating multiple subscriptions in batch?
   - Should we show existing subscriptions overlaid on code viewer?

9. **Testing Strategy**:
   - How do we test with realistic large repos without bloating test suite?
   - Should we have integration tests that spin up real git repos?
   - How do we test virtualization/pagination edge cases?

## Potential Approaches

### Approach A: Full-Featured Code Browser (VSCode-like)
**Description**: Build a comprehensive code browsing experience similar to VSCode's file explorer + editor.

**Components**:
- Split-pane modal: file tree on left, code viewer on right
- Full syntax highlighting (Monaco or similar)
- Virtual scrolling for large files
- Search/filter across files
- Breadcrumb navigation

**Pros**:
- Best user experience
- Familiar to developers
- Supports all use cases elegantly
- Professional appearance

**Cons**:
- Significant development effort (2-3 weeks)
- Large bundle size increase (~500KB for Monaco, or ~50KB for lighter alternatives)
- Complex state management
- Performance optimization required
- May be over-engineered for the use case

---

### Approach B: Minimal Two-Step Wizard
**Description**: Simple two-screen flow: (1) pick file from list, (2) pick construct/lines from rendered list.

**Components**:
- Screen 1: Searchable file list (plain list with filter input)
- Screen 2: Simple construct list or line number grid (no full code display)
- Back/Next buttons for navigation

**Pros**:
- Minimal development effort (~3-5 days)
- Small bundle size impact
- Fast, simple, predictable
- No virtualization needed (just show construct list)
- Works well on mobile

**Cons**:
- Less intuitive (can't see code context)
- No visual confirmation of what you're selecting
- Limited discoverability
- Feels disconnected from actual code

---

### Approach C: Hybrid - File List + Simple Code Viewer
**Description**: Single modal with file search + basic code display with clickable constructs/lines.

**Components**:
- Top: File search/filter input
- Left sidebar: Filtered file list (scrollable)
- Main area: Plain text code viewer with line numbers
- Construct highlighting (bold/colored text, not full syntax highlighting)
- Click handlers on constructs and line numbers

**Pros**:
- Balanced effort (~1 week)
- Reasonable bundle size (~10-20KB for basic highlighting)
- Users can see code context
- Familiar pattern (file picker + preview)
- Can use simple virtualization (react-window)

**Cons**:
- Not as polished as Approach A
- Still needs virtualization for large files
- Syntax highlighting quality lower than full editors

---

### Approach D: Server-Rendered Code Views
**Description**: Backend generates HTML previews of files with construct links; frontend just displays.

**Components**:
- New endpoint: `GET /api/projects/{id}/files/{path}/preview` returns HTML
- Frontend displays in iframe or sanitized HTML
- Constructs rendered as clickable links with data attributes

**Pros**:
- Zero frontend bundle impact for highlighting
- Backend can use powerful syntax highlighting libraries (Pygments)
- Caching on server side
- Works on any device

**Cons**:
- Security concerns (XSS, sanitization)
- Less interactive (harder to add hover states, selection feedback)
- Network overhead for each file view
- Harder to implement rich interactions (multi-line selection)

---

### Approach E: Progressive Enhancement - Start Simple, Iterate
**Description**: Build minimal viable browser first, then add features based on feedback.

**Phase 1** (MVP - 3 days):
- File list with search (no tree, just flat list)
- Show construct list for selected file (no code display)
- Click construct to populate location field

**Phase 2** (If MVP proves useful - +2 days):
- Add basic code viewer (plain text + line numbers)
- Visual construct highlighting
- Line range selection

**Phase 3** (Polish - +2 days):
- Add syntax highlighting (Prism.js)
- Virtual scrolling for large files
- Keyboard shortcuts

**Pros**:
- Fastest time to user feedback
- Can validate concept before heavy investment
- Incremental bundle size growth
- Can stop at any phase if sufficient

**Cons**:
- May need refactoring between phases
- Initial version may feel incomplete
- User expectations set early

---

## Recommendation

Based on the constraints and user needs, **Approach C (Hybrid)** or **Approach E (Progressive Enhancement starting with simplified Approach C)** appears most suitable:

1. **Addresses core pain point** (manual typing) without over-engineering
2. **Manageable scope** (~1 week for Approach C, 3-8 days for Approach E)
3. **Reasonable performance** for typical codebases (<1000 files, <2000 lines per file)
4. **Bundle size acceptable** (10-20KB additional)
5. **Allows iteration** based on real user feedback

### Suggested MVP Scope (Approach E - Phase 1)
1. Add button "Browse Code" in `SubscriptionForm.tsx`
2. Create modal with:
   - File search input
   - Scrollable file list (shows all git-tracked Python/Java files first, then others)
   - For selected file: load symbols from new `/api/projects/{id}/symbols/{path}` endpoint
   - Display symbols as clickable list (show: kind, qualname, lines)
   - Click symbol → populate location field → close modal
3. Backend: implement two new endpoints:
   - `GET /api/projects/{id}/files` - return git-tracked files
   - `GET /api/projects/{id}/symbols/{path}` - return constructs using existing indexer
4. Handle errors: unsupported language → show message "Use line-based subscription"
5. Add loading states and error handling

This MVP delivers immediate value and can be shipped in ~3 days, then iterated based on usage patterns.

---

## File References

All file paths referenced in this document are absolute paths within the project:
- `/Users/vlad/dev/projects/codesub/frontend/src/components/SubscriptionForm.tsx` - Current subscription form
- `/Users/vlad/dev/projects/codesub/frontend/src/components/FileBrowserModal.tsx` - Existing directory browser (for reference)
- `/Users/vlad/dev/projects/codesub/src/codesub/cli.py` - CLI with symbols command
- `/Users/vlad/dev/projects/codesub/src/codesub/api.py` - FastAPI server
- `/Users/vlad/dev/projects/codesub/src/codesub/git_repo.py` - Git wrapper
- `/Users/vlad/dev/projects/codesub/src/codesub/semantic/` - Semantic indexing infrastructure
- `/Users/vlad/dev/projects/codesub/frontend/src/types.ts` - Frontend type definitions
- `/Users/vlad/dev/projects/codesub/frontend/src/api.ts` - API client functions
