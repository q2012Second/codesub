# Implementation Plan: Multi-Project Frontend Subscription Management

## Overview

This plan adds multi-project support to codesub, enabling users to manage subscriptions across multiple git repositories from a single frontend. The implementation includes:

1. Backend-managed project storage with CRUD operations via API
2. Scan API endpoints for running scans against different git refs
3. Scan history persistence with cleanup capabilities
4. Apply updates functionality from the UI with confirmation dialogs
5. Frontend views for project management, scanning, and history

## Design Decisions

| Decision | Rationale |
|----------|-----------|
| Store projects in `~/.config/codesub/projects.json` | User-level config allows managing projects across machines, separate from repo-specific data |
| Store scan history in `~/.config/codesub/scan_history/{project_id}/` | Keeps history separate from project repos, allows easy cleanup |
| Use UUID for project IDs | Consistent with existing subscription ID pattern |
| Validate project path is a git repo with codesub initialized | Prevents adding invalid projects |
| Server runs in single-project mode but API supports multi-project | Backwards compatible - existing single-project usage still works |

**User Requirements:**
- Backend-managed project storage (persisted in config file, API provides CRUD)
- Manual path input (no file browser)
- Scan persistence with cleanup capability (CLI + UI)
- Apply updates with confirmation dialog

## Files to Create

| File | Purpose |
|------|---------|
| `src/codesub/project_store.py` | Project CRUD operations and storage |
| `src/codesub/scan_history.py` | Scan history storage and retrieval |
| `frontend/src/components/ProjectList.tsx` | Project list view |
| `frontend/src/components/ProjectForm.tsx` | Add project form |
| `frontend/src/components/ProjectSelector.tsx` | Project dropdown in header |
| `frontend/src/components/ScanView.tsx` | Scan trigger and results display |
| `frontend/src/components/ScanHistoryList.tsx` | Scan history list |
| `frontend/src/components/ApplyUpdatesModal.tsx` | Confirmation dialog for applying updates |
| `tests/test_project_store.py` | Tests for ProjectStore |
| `tests/test_scan_history.py` | Tests for ScanHistory |

## Files to Modify

| File | Changes |
|------|---------|
| `src/codesub/models.py` | Add Project and ScanHistoryEntry models |
| `src/codesub/errors.py` | Add ProjectNotFoundError, InvalidProjectPathError, ScanNotFoundError |
| `src/codesub/api.py` | Add project and scan endpoints |
| `src/codesub/cli.py` | Add `projects` and `scan-history` subcommands |
| `frontend/src/types.ts` | Add Project, ScanResult, ScanHistoryEntry types |
| `frontend/src/api.ts` | Add project and scan API functions |
| `frontend/src/App.tsx` | Add project context, new views |

## Implementation Steps

### Step 1: Add Backend Models and Errors

**Files:** `src/codesub/models.py`, `src/codesub/errors.py`

Add `Project` dataclass:
```python
@dataclass
class Project:
    id: str
    name: str  # Display name (defaults to repo directory name)
    path: str  # Absolute path to the repository root
    created_at: str
    updated_at: str
```

Add `ScanHistoryEntry` dataclass:
```python
@dataclass
class ScanHistoryEntry:
    id: str
    project_id: str
    base_ref: str
    target_ref: str
    trigger_count: int
    proposal_count: int
    unchanged_count: int
    created_at: str
    scan_result: dict[str, Any]  # Full ScanResult as dict
```

Add errors:
```python
class ProjectNotFoundError(CodesubError): ...
class InvalidProjectPathError(CodesubError): ...
class ScanNotFoundError(CodesubError): ...
```

### Step 2: Create ProjectStore

**File:** `src/codesub/project_store.py`

Create `ProjectStore` class:
- Store in `~/.config/codesub/projects.json`
- Methods: `list_projects()`, `get_project(id)`, `add_project(path, name)`, `remove_project(id)`, `update_project(id, name)`, `get_project_status(id)`
- Validation: check path exists, is git repo, has codesub initialized, no duplicates

### Step 3: Create ScanHistory Store

**File:** `src/codesub/scan_history.py`

Create `ScanHistory` class:
- Store in `~/.config/codesub/scan_history/{project_id}/`
- Each scan is a timestamped JSON file (`{scan_id}.json`)
- Methods: `save_scan(project_id, scan_result)`, `list_scans(project_id, limit)`, `get_scan(project_id, scan_id)`, `clear_project_history(project_id)`, `clear_all_history()`

### Step 4: Add API Endpoints

**File:** `src/codesub/api.py`

**Helper function for multi-project:**
```python
def get_project_store_and_repo(project_id: str) -> tuple[ConfigStore, GitRepo]:
    """Get ConfigStore and GitRepo for a specific project."""
    project_store = get_project_store()
    project = project_store.get_project(project_id)
    repo = GitRepo(project.path)
    store = ConfigStore(repo.root)
    return store, repo
```

**Error code mappings:**
```python
ERROR_STATUS_CODES.update({
    ProjectNotFoundError: 404,
    InvalidProjectPathError: 400,
    ScanNotFoundError: 404,
})
```

Project endpoints:
- `GET /api/projects` - List all registered projects
- `POST /api/projects` - Register a new project
- `GET /api/projects/{id}` - Get project status and details
- `PATCH /api/projects/{id}` - Update project name
- `DELETE /api/projects/{id}` - Remove project from registry
- `GET /api/projects/{id}/subscriptions` - List subscriptions for project

Scan endpoints:
- `POST /api/projects/{id}/scan` - Run scan and save to history

**ScanRequest schema:**
```python
class ScanRequest(BaseModel):
    base_ref: str = Field(..., description="Base git ref (e.g., 'HEAD~1', 'baseline', commit hash)")
    target_ref: str = Field(default="HEAD", description="Target git ref ('HEAD', commit hash)")
```

- `GET /api/projects/{id}/scan-history` - List scan history for project
- `GET /api/projects/{id}/scan-history/{scan_id}` - Get specific scan result
- `DELETE /api/projects/{id}/scan-history` - Clear project scan history
- `DELETE /api/scan-history` - Clear all scan history

Apply updates endpoint:
- `POST /api/projects/{id}/apply-updates` - Apply proposals from scan

**ApplyUpdatesRequest schema:**
```python
class ApplyUpdatesRequest(BaseModel):
    scan_id: str = Field(..., description="Scan ID to apply proposals from")
    proposal_ids: Optional[list[str]] = Field(None, description="Specific proposal IDs to apply (all if not specified)")
```

**ApplyUpdatesResponse schema:**
```python
class ApplyUpdatesResponse(BaseModel):
    applied: list[str]  # IDs of applied proposals
    warnings: list[str]  # Any warnings during apply
    new_baseline: Optional[str]  # New baseline ref if updated
```

### Step 5: Add CLI Commands

**File:** `src/codesub/cli.py`

Add commands:
- `codesub projects list [--json]` - List registered projects
- `codesub projects add <path> [--name <name>]` - Add a project
- `codesub projects remove <project_id>` - Remove a project
- `codesub scan-history clear [--project <id>]` - Clear scan history

### Step 6: Add Frontend Types

**File:** `frontend/src/types.ts`

Add types:
- `Project`, `ProjectStatus`, `ProjectCreateRequest`, `ProjectListResponse`
- `Trigger`, `Proposal`, `ScanResult`, `ScanHistoryEntry`, `ScanHistoryEntryFull`
- `ScanRequest`, `ScanHistoryListResponse`
- `ApplyUpdatesRequest`, `ApplyUpdatesResponse`
- Update `View` type to include new views

### Step 7: Add Frontend API Functions

**File:** `frontend/src/api.ts`

Add functions:
- `listProjects()`, `getProjectStatus(id)`, `createProject(data)`, `deleteProject(id)`
- `listProjectSubscriptions(projectId, includeInactive)`
- `runScan(projectId, request)`, `listScanHistory(projectId, limit)`, `getScanResult(projectId, scanId)`
- `clearProjectScanHistory(projectId)`, `clearAllScanHistory()`
- `applyUpdates(projectId, request)`

### Step 8: Create Frontend Components

Create new components:
- `ProjectList.tsx` - Grid of project cards, click to select
- `ProjectForm.tsx` - Form with path input and optional name
- `ProjectSelector.tsx` - Dropdown in header for quick project switching
- `ScanView.tsx` - Scan trigger form, quick actions, results display
- `ScanHistoryList.tsx` - List of past scans with details
- `ApplyUpdatesModal.tsx` - Confirmation dialog with proposal selection

### Step 9: Update App.tsx

**File:** `frontend/src/App.tsx`

- Add project state: `projects`, `currentProjectId`, `projectLoading`
- Add scan state: `scanHistory`, `selectedScanId`
- Add views: `projects`, `project-add`, `scan`, `scan-history`
- Add header with `ProjectSelector`
- Route between views based on state

## API Endpoints Summary

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/projects` | List all registered projects |
| POST | `/api/projects` | Register a new project |
| GET | `/api/projects/{id}` | Get project status and details |
| PATCH | `/api/projects/{id}` | Update project name |
| DELETE | `/api/projects/{id}` | Remove project from registry |
| GET | `/api/projects/{id}/subscriptions` | List subscriptions for project |
| POST | `/api/projects/{id}/scan` | Run scan and save to history |
| GET | `/api/projects/{id}/scan-history` | List scan history for project |
| GET | `/api/projects/{id}/scan-history/{scan_id}` | Get specific scan result |
| DELETE | `/api/projects/{id}/scan-history` | Clear project scan history |
| DELETE | `/api/scan-history` | Clear all scan history |
| POST | `/api/projects/{id}/apply-updates` | Apply proposals from scan |

## Data Models Summary

**Project** (stored in `~/.config/codesub/projects.json`):
```json
{
  "id": "uuid",
  "name": "my-project",
  "path": "/path/to/repo",
  "created_at": "2024-01-01T00:00:00Z",
  "updated_at": "2024-01-01T00:00:00Z"
}
```

**ScanHistoryEntry** (stored in `~/.config/codesub/scan_history/{project_id}/{scan_id}.json`):
```json
{
  "id": "uuid",
  "project_id": "uuid",
  "base_ref": "abc123...",
  "target_ref": "def456...",
  "trigger_count": 2,
  "proposal_count": 3,
  "unchanged_count": 5,
  "created_at": "2024-01-01T00:00:00Z",
  "scan_result": { ... }
}
```

## Testing Strategy

### Unit Tests - ProjectStore (`tests/test_project_store.py`)
- Test add_project validates path exists
- Test add_project validates git repo
- Test add_project validates codesub initialized
- Test add_project rejects duplicates
- Test list_projects returns all projects
- Test get_project returns correct project
- Test get_project raises ProjectNotFoundError
- Test remove_project removes and returns project
- Test get_project_status returns correct status

### Unit Tests - ScanHistory (`tests/test_scan_history.py`)
- Test save_scan creates entry with correct data
- Test list_scans returns newest first
- Test list_scans respects limit
- Test get_scan returns correct entry
- Test get_scan raises ScanNotFoundError
- Test clear_project_history clears only that project
- Test clear_all_history clears everything

### Integration Tests - API (`tests/test_api.py`)
- Test project CRUD endpoints
- Test scan endpoints with mock detector
- Test apply-updates endpoint
- Test error responses for invalid inputs

## Edge Cases Considered

1. **Project path no longer exists**: `get_project_status` returns `path_exists: false`
2. **Project's codesub not initialized**: `get_project_status` returns `codesub_initialized: false`
3. **Duplicate project path**: `add_project` raises `InvalidProjectPathError`
4. **Scan with same base and target**: Returns empty results (no changes)
5. **Apply updates with stale scan**: Proposals reference subscription IDs; if subscription was modified/deleted, warning is returned
6. **Corrupted scan history files**: `list_scans` skips corrupted files silently

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| User adds project but repo is on network drive and unavailable | `get_project_status` checks if path exists before accessing |
| Scan history grows unbounded | History is per-project with easy clear commands; UI shows clear button |
| Apply updates with outdated proposals | Updater validates new locations still exist at target_ref and returns warnings |
| Multiple users accessing same project store | Store uses atomic file writes; single-server model prevents race conditions |
