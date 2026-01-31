# Implementation Plan: Centralize Subscription Storage

## Design Decisions - Revised

This section documents changes made based on the plan review feedback.

| Change | Issue | Resolution |
|--------|-------|------------|
| Added data cleanup on project removal | Critical #3 | Step 5 now includes cleanup of `data/subscriptions/<project_id>/` with `--keep-data` flag option |
| Documented workflow change | Critical #2 | Design Decisions table now explicitly notes `projects add` auto-initializes; CLAUDE.md update (Step 14) documents this |
| Concrete `/api/health` implementation | Major #4 | Step 7 now provides project-agnostic health endpoint implementation |
| Better CLI error messaging | Major #5 | Step 11 adds `ProjectNotRegisteredError` with actionable message |
| Complete test fixture example | Major #6 | Step 12 now includes full `conftest.py` fixture examples |
| Updater class verification | Major #7 | Step 9 now documents that Updater only uses `store.load()`, `store.save()`, `store.update_baseline()` - all compatible |
| Keep filename as `subscriptions.json` | Minor #8 | Changed from `config.json` back to `subscriptions.json` for consistency |
| Frontend endpoint updates | Minor #9 | Step 13 added to update frontend `api.ts` |
| CLAUDE.md Data Storage section | Minor #10 | Step 14 now includes Data Storage section update |

## Overview

Refactor `ConfigStore` to store subscription data centrally in `data/subscriptions/<project_id>/` instead of in target repositories at `.codesub/`. This eliminates the need for `.codesub/` directories in monitored repos and consolidates all codesub data in the central `data/` directory.

## Design Decisions

| Decision | Rationale |
|----------|-----------|
| Use `project_id` as constructor parameter | Aligns with existing `ScanHistory` pattern; enables central storage keyed by project |
| Store in `data/subscriptions/<project_id>/` | Consistent with `data/scan_history/<project_id>/` pattern |
| Auto-migrate from `.codesub/` on first access | Seamless transition for existing projects without manual intervention |
| Remove `codesub init` command | Registration via `projects add` creates config automatically; simplifies workflow |
| Keep `repo_root` as internal attribute | Still needed for path validation and file operations, resolved from project registry |
| `projects add` now auto-initializes config | **Workflow change**: Previously required `codesub init` first; now registration handles all setup |
| Keep filename as `subscriptions.json` | Consistency with legacy filename; avoids confusion during migration debugging |
| Clean up subscription data on project removal | Prevents orphaned data accumulation; `--keep-data` flag available for preservation |

**User Requirements:**
- Project must be registered before subscriptions can be managed
- Auto-migration from `.codesub/` happens transparently on first access
- All subscription data stored centrally in `data/subscriptions/`
- Subscription data cleaned up when project is removed (unless `--keep-data` specified)

**Alternative Approaches Considered:**
- **Keep `.codesub/` as primary, sync to central**: Rejected - adds complexity, doesn't solve the core problem
- **Manual migration command**: Rejected - auto-migration is more user-friendly
- **Keep `codesub init` for advanced config**: Rejected - registration handles all config needs
- **No cleanup on project removal**: Rejected - leads to orphaned data; `--keep-data` flag provides opt-out

## Prerequisites

- Understand existing `DATA_DIR` pattern in `project_store.py` and `scan_history.py`
- Review all usages of `ConfigStore` across CLI, API, updater, and detector

## Implementation Steps

### Step 1: Update ConfigStore Constructor and Storage Paths

**Files:** `/Users/vlad/dev/projects/codesub/src/codesub/config_store.py`

**Changes:**
- Change constructor from `__init__(self, repo_root: Path)` to `__init__(self, project_id: str, config_dir: Path | None = None)`
- Add `DATA_DIR` constant matching pattern from `project_store.py`
- Add `SUBSCRIPTIONS_DIR = "subscriptions"` constant
- Update path computation: `data/subscriptions/<project_id>/subscriptions.json`
- Keep `repo_root` as optional attribute (set via separate method or lazy lookup)
- Remove `CONFIG_DIR = ".codesub"` constant

**Code:**
```python
# New constants
DATA_DIR = Path(__file__).parent.parent.parent / "data"
SUBSCRIPTIONS_DIR = "subscriptions"
CONFIG_FILE = "subscriptions.json"  # Keep same filename for consistency
UPDATE_DOCS_DIR = "last_update_docs"

class ConfigStore:
    def __init__(self, project_id: str, config_dir: Path | None = None):
        self.project_id = project_id
        self._base_dir = config_dir or DATA_DIR
        self.config_dir = self._base_dir / SUBSCRIPTIONS_DIR / project_id
        self.config_path = self.config_dir / CONFIG_FILE
        self.update_docs_dir = self.config_dir / UPDATE_DOCS_DIR
        self._repo_root: Path | None = None  # Set lazily when needed
```

### Step 2: Add Auto-Migration Logic

**Files:** `/Users/vlad/dev/projects/codesub/src/codesub/config_store.py`

**Changes:**
- Add `_try_migrate_from_codesub()` private method
- Call migration check in `exists()` and `load()` methods
- Migration copies `.codesub/subscriptions.json` to new location
- Log migration for user awareness (optional: delete old `.codesub/` or leave as backup)

**Code:**
```python
def _get_legacy_path(self, repo_root: Path) -> Path:
    """Get legacy .codesub path for migration."""
    return repo_root / ".codesub" / "subscriptions.json"

def _try_migrate(self, repo_root: Path) -> bool:
    """
    Attempt to migrate from legacy .codesub/ location.

    Returns True if migration occurred, False otherwise.
    """
    if self.config_path.exists():
        return False  # Already migrated

    legacy_path = self._get_legacy_path(repo_root)
    if not legacy_path.exists():
        return False  # No legacy config to migrate

    # Perform migration
    self.config_dir.mkdir(parents=True, exist_ok=True)

    # Copy config file
    import shutil
    shutil.copy2(legacy_path, self.config_path)

    # Copy update_docs if present
    legacy_docs = legacy_path.parent / "last_update_docs"
    if legacy_docs.exists():
        shutil.copytree(legacy_docs, self.update_docs_dir, dirs_exist_ok=True)

    return True

def set_repo_root(self, repo_root: Path) -> None:
    """Set repo root for migration and path operations."""
    self._repo_root = repo_root
    # Attempt migration if repo root is known
    self._try_migrate(repo_root)
```

### Step 3: Update `init()` Method

**Files:** `/Users/vlad/dev/projects/codesub/src/codesub/config_store.py`

**Changes:**
- Simplify `init()` - only creates config in central location
- Remove directory creation in target repo
- Called automatically when project is registered

**Code:**
```python
def init(self, baseline_ref: str, force: bool = False) -> Config:
    """
    Initialize a new configuration.

    Called automatically when a project is registered.
    """
    if self.exists() and not force:
        raise ConfigExistsError(str(self.config_path))

    config = Config.create(baseline_ref)
    self.save(config)
    self.update_docs_dir.mkdir(parents=True, exist_ok=True)
    return config
```

### Step 4: Update ProjectStore to Initialize ConfigStore on Registration

**Files:** `/Users/vlad/dev/projects/codesub/src/codesub/project_store.py`

**Changes:**
- Remove `.codesub` existence check from `add_project()`
- After creating project, initialize `ConfigStore` with HEAD as baseline
- Import `GitRepo` is already present

**Code:**
```python
def add_project(self, path: str, name: str | None = None) -> Project:
    # ... existing validation (git repo check) ...

    # REMOVE this block:
    # store = ConfigStore(repo.root)
    # if not store.exists():
    #     raise InvalidProjectPathError(...)

    # ... existing duplicate check and project creation ...

    # After project is created and saved:
    # Initialize config store with HEAD as baseline
    from .config_store import ConfigStore
    config_store = ConfigStore(project.id, self.config_dir)
    config_store.set_repo_root(repo.root)
    if not config_store.exists():
        head = repo.head()
        config_store.init(head)

    return project
```

### Step 5: Update `remove_project()` to Clean Up Subscription Data

**Files:** `/Users/vlad/dev/projects/codesub/src/codesub/project_store.py`

**Changes:**
- Add `keep_data: bool = False` parameter to `remove_project()`
- When `keep_data=False` (default), delete `data/subscriptions/<project_id>/` directory
- Also delete scan history data at `data/scan_history/<project_id>/`

**Code:**
```python
def remove_project(self, project_id: str, keep_data: bool = False) -> Project:
    """
    Remove a project from the registry.

    Args:
        project_id: Project ID.
        keep_data: If True, preserve subscription and scan history data.
                   If False (default), delete all associated data.

    Returns:
        The removed Project.

    Raises:
        ProjectNotFoundError: If project doesn't exist.
    """
    import shutil

    with self._lock():
        data = self._load_data()
        projects = data.get("projects", [])

        for i, p in enumerate(projects):
            if p["id"] == project_id:
                removed = Project.from_dict(projects.pop(i))
                self._save_data(data)

                # Clean up associated data unless keep_data=True
                if not keep_data:
                    # Remove subscription data
                    subs_dir = self.config_dir / "subscriptions" / project_id
                    if subs_dir.exists():
                        shutil.rmtree(subs_dir)

                    # Remove scan history data
                    history_dir = self.config_dir / "scan_history" / project_id
                    if history_dir.exists():
                        shutil.rmtree(history_dir)

                return removed

        raise ProjectNotFoundError(project_id)
```

### Step 6: Update `get_project_status()` in ProjectStore

**Files:** `/Users/vlad/dev/projects/codesub/src/codesub/project_store.py`

**Changes:**
- Update to use new `ConfigStore(project_id)` interface
- Remove `codesub_initialized` check (always true after registration)
- Or repurpose to check if config exists in central location

**Code:**
```python
def get_project_status(self, project_id: str) -> dict[str, Any]:
    project = self.get_project(project_id)
    abs_path = Path(project.path)

    status: dict[str, Any] = {
        "project": project.to_dict(),
        "path_exists": abs_path.exists(),
        "codesub_initialized": False,
        "subscription_count": 0,
        "baseline_ref": None,
    }

    if not status["path_exists"]:
        return status

    try:
        store = ConfigStore(project_id, self.config_dir)
        status["codesub_initialized"] = store.exists()

        if store.exists():
            config = store.load()
            status["subscription_count"] = len(
                [s for s in config.subscriptions if s.active]
            )
            status["baseline_ref"] = config.repo.baseline_ref
    except Exception:
        pass

    return status
```

### Step 7: Update API Helper Functions and Health Endpoint

**Files:** `/Users/vlad/dev/projects/codesub/src/codesub/api.py`

**Changes:**
- Update `get_project_store_and_repo()` to use new `ConfigStore(project_id)` interface
- Remove/deprecate `get_store_and_repo()` (no longer needed without per-repo `.codesub/`)
- Update `/api/health` to be project-agnostic (simple status check)
- Update all API endpoints that use these helpers

**Code:**
```python
def get_project_store_and_repo(project_id: str) -> tuple[ConfigStore, GitRepo]:
    """Get ConfigStore and GitRepo for a specific project."""
    project_store = get_project_store()
    project = project_store.get_project(project_id)

    repo = GitRepo(project.path)
    store = ConfigStore(project_id)  # Use project_id, not repo.root
    store.set_repo_root(repo.root)   # Set repo root for migration/operations
    return store, repo

# Remove:
# def get_store_and_repo() -> tuple[ConfigStore, GitRepo]:
#     ...

@app.get("/api/health")
def health_check():
    """
    Health check endpoint.

    Returns basic service status. Project-agnostic.
    """
    project_store = get_project_store()
    try:
        projects = project_store.list_projects()
        return {
            "status": "ok",
            "project_count": len(projects),
        }
    except Exception as e:
        return {
            "status": "error",
            "detail": str(e),
        }
```

### Step 8: Remove Non-Project API Endpoints

**Files:** `/Users/vlad/dev/projects/codesub/src/codesub/api.py`

**Changes:**
- Remove `/api/subscriptions` endpoints (the non-project-scoped ones)
- Keep only `/api/projects/{project_id}/subscriptions` endpoints

**Endpoints to remove:**
- `GET /api/subscriptions`
- `POST /api/subscriptions`
- `GET /api/subscriptions/{sub_id}`
- `PATCH /api/subscriptions/{sub_id}`
- `DELETE /api/subscriptions/{sub_id}`
- `POST /api/subscriptions/{sub_id}/reactivate`

### Step 9: Verify Updater Class Compatibility

**Files:** `/Users/vlad/dev/projects/codesub/src/codesub/updater.py`

**Verification Result:** The `Updater` class is **compatible** with the new ConfigStore interface.

**Analysis:**
The Updater class only uses these ConfigStore methods:
- `store.load()` - loads config (no changes needed)
- `store.save(config)` - saves config (no changes needed)
- `store.update_baseline(target_ref)` - updates baseline (no changes needed)

The Updater does NOT access any ConfigStore properties like `repo_root` or `config_dir`. All path operations use the `GitRepo` instance passed to the constructor.

**No changes required to `updater.py`.**

### Step 10: Update CLI Commands

**Files:** `/Users/vlad/dev/projects/codesub/src/codesub/cli.py`

**Changes:**
- Remove `cmd_init` and `init` subparser
- Add `get_project_for_cwd()` helper to auto-detect registered project from current directory
- Update `cmd_add`, `cmd_list`, `cmd_remove`, `cmd_scan`, `cmd_apply_updates`, `cmd_symbols`, `cmd_serve`
- Add `--keep-data` flag to `projects remove` command

**Code for project detection:**
```python
def get_project_for_cwd() -> tuple[str, ConfigStore, GitRepo]:
    """
    Find registered project matching current working directory.

    Raises:
        ProjectNotRegisteredError: If cwd is not a registered project.
    """
    from .errors import ProjectNotRegisteredError

    repo = GitRepo()  # Uses cwd
    project_store = ProjectStore()
    for project in project_store.list_projects():
        if Path(project.path).resolve() == repo.root.resolve():
            store = ConfigStore(project.id)
            store.set_repo_root(repo.root)
            return project.id, store, repo

    raise ProjectNotRegisteredError(str(repo.root))
```

**Update `projects remove` command:**
```python
# In argument parser setup
remove_parser.add_argument(
    "--keep-data",
    action="store_true",
    help="Preserve subscription and scan history data after removing project"
)

# In cmd_projects_remove
def cmd_projects_remove(args: argparse.Namespace) -> int:
    project_store = ProjectStore()
    project = project_store.remove_project(args.project_id, keep_data=args.keep_data)
    print(f"Removed project: {project.name} ({project.id[:8]})")
    if not args.keep_data:
        print("Associated subscription and scan history data deleted.")
    return 0
```

### Step 11: Update Error Messages

**Files:** `/Users/vlad/dev/projects/codesub/src/codesub/errors.py`

**Changes:**
- Update `ConfigNotFoundError` message to reference project registration
- Add `ProjectNotRegisteredError` for CLI commands in unregistered directories

**Code:**
```python
class ConfigNotFoundError(CodesubError):
    def __init__(self, path: str | None = None):
        self.path = path
        msg = "Config not found. Register the project first with 'codesub projects add <path>'."
        if path:
            msg = f"Config not found at {path}. Register the project first."
        super().__init__(msg)


class ProjectNotRegisteredError(CodesubError):
    """Raised when a command is run in an unregistered project directory."""

    def __init__(self, path: str):
        self.path = path
        super().__init__(
            f"Project at '{path}' is not registered.\n"
            f"Run 'codesub projects add .' to register the current directory, "
            f"or 'codesub projects add {path}' to register this path."
        )
```

### Step 12: Update Tests

**Files:**
- `/Users/vlad/dev/projects/codesub/tests/test_config_store.py`
- `/Users/vlad/dev/projects/codesub/tests/test_api.py`
- `/Users/vlad/dev/projects/codesub/tests/conftest.py`

**Changes to `conftest.py` - Add new fixtures:**
```python
import uuid

@pytest.fixture
def data_dir(temp_dir):
    """Create a temporary data directory for centralized storage."""
    data = temp_dir / "data"
    data.mkdir()
    yield data


@pytest.fixture
def project_id():
    """Generate a unique project ID for tests."""
    return str(uuid.uuid4())


@pytest.fixture
def config_store(data_dir, project_id, git_repo):
    """
    Create a ConfigStore with centralized storage for testing.

    Provides:
    - Isolated data directory (not the real data/)
    - Unique project ID
    - Git repo for repo_root operations
    """
    from codesub.config_store import ConfigStore

    store = ConfigStore(project_id, config_dir=data_dir)
    store.set_repo_root(git_repo)
    return store


@pytest.fixture
def initialized_config_store(config_store, git_repo):
    """ConfigStore with initialized config (baseline set to HEAD)."""
    head = get_head(git_repo)
    config_store.init(head)
    return config_store


@pytest.fixture
def registered_project(data_dir, git_repo):
    """
    A registered project with initialized config.

    Returns tuple of (project, config_store, git_repo).
    """
    from codesub.project_store import ProjectStore
    from codesub.config_store import ConfigStore

    project_store = ProjectStore(config_dir=data_dir)
    project = project_store.add_project(str(git_repo))

    config_store = ConfigStore(project.id, config_dir=data_dir)
    config_store.set_repo_root(git_repo)

    return project, config_store, git_repo
```

**Changes to `test_config_store.py`:**
```python
class TestConfigStore:
    def test_init_creates_config(self, data_dir, project_id):
        # New interface uses project_id
        store = ConfigStore(project_id, config_dir=data_dir)
        config = store.init("abc123")

        assert store.exists()
        assert config.repo.baseline_ref == "abc123"
        # Config now at data_dir/subscriptions/project_id/subscriptions.json
        expected_path = data_dir / "subscriptions" / project_id / "subscriptions.json"
        assert expected_path.exists()

    def test_migration_from_legacy(self, data_dir, project_id, git_repo):
        # Create legacy .codesub config
        legacy_dir = git_repo / ".codesub"
        legacy_dir.mkdir()
        legacy_config = legacy_dir / "subscriptions.json"
        legacy_config.write_text(json.dumps({
            "schema_version": 1,
            "repo": {"baseline_ref": "old123", "created_at": "2024-01-01T00:00:00Z", "updated_at": "2024-01-01T00:00:00Z"},
            "subscriptions": []
        }))

        # Create store and trigger migration
        store = ConfigStore(project_id, config_dir=data_dir)
        store.set_repo_root(git_repo)

        # Should have migrated
        assert store.exists()
        config = store.load()
        assert config.repo.baseline_ref == "old123"

        # Verify new location
        new_path = data_dir / "subscriptions" / project_id / "subscriptions.json"
        assert new_path.exists()
```

**Changes to `test_api.py`:**
- Update tests to use project-scoped endpoints exclusively
- Remove tests for non-project endpoints
- Use `registered_project` fixture for API tests

### Step 13: Update Frontend API Client

**Files:** `/Users/vlad/dev/projects/codesub/frontend/src/api.ts`

**Changes:**
- Remove non-project-scoped subscription functions (or keep as deprecated wrappers that throw errors)
- Update any components that might still use the old endpoints

**Functions to remove or deprecate:**
```typescript
// Remove these functions (non-project-scoped):
// - listSubscriptions()
// - getSubscription()
// - createSubscription()
// - updateSubscription()
// - deleteSubscription()
// - reactivateSubscription()

// Keep these project-scoped functions:
// - listProjectSubscriptions()
// - createProjectSubscription()
// - updateProjectSubscription()
// - deleteProjectSubscription()
// - reactivateProjectSubscription()
```

**Update healthCheck function:**
```typescript
export async function healthCheck(): Promise<{ status: string; project_count?: number; detail?: string }> {
  const response = await fetch(`${API_BASE}/health`);
  return response.json();
}
```

### Step 14: Update CLAUDE.md Documentation

**Files:** `/Users/vlad/dev/projects/codesub/CLAUDE.md`

**Changes:**
- Remove references to `codesub init`
- Update CLI usage section
- Update project structure section (remove `.codesub/` references)
- Document new workflow: register project first, then add subscriptions
- **Update Data Storage section** to reflect new locations

**Updated CLI Usage section:**
```markdown
## CLI Usage

```bash
# Register a project (auto-initializes config with HEAD as baseline)
codesub projects add /path/to/repo --name "My Project"
# Or register current directory
codesub projects add .

# Subscribe to a line range (run from within registered project)
codesub add path/to/file.py:42-50 --label "Important function"

# Subscribe to a semantic target (code construct)
codesub add path/to/file.py::ClassName.method --label "Track method"
codesub add config.py::API_VERSION --label "Track constant"

# ... rest unchanged ...
```

**Updated Data Storage section:**
```markdown
## Data Storage

All codesub data is stored centrally in the `data/` directory:

- **Projects registry**: `data/projects.json` - Registered projects
- **Subscription configs**: `data/subscriptions/<project_id>/subscriptions.json` - Per-project subscriptions
- **Update documents**: `data/subscriptions/<project_id>/last_update_docs/` - Saved update proposals
- **Scan history**: `data/scan_history/<project_id>/<scan_id>.json` - Scan results

**Note:** The `.codesub/` directory in target repositories is no longer used. Existing `.codesub/` configs are auto-migrated to central storage on first access.
```

**Updated API Endpoints section:**
```markdown
## API Endpoints

### Subscriptions (project-scoped)
- `GET /api/projects/{id}/subscriptions` - List project subscriptions
- `POST /api/projects/{id}/subscriptions` - Create subscription
- `GET /api/projects/{id}/subscriptions/{sub_id}` - Get subscription
- `PATCH /api/projects/{id}/subscriptions/{sub_id}` - Update subscription
- `DELETE /api/projects/{id}/subscriptions/{sub_id}` - Delete subscription
- `POST /api/projects/{id}/subscriptions/{sub_id}/reactivate` - Reactivate

### Health
- `GET /api/health` - Service health check (project-agnostic)

... (rest unchanged)
```

## Testing Strategy

- [ ] **Unit Tests - ConfigStore:**
  - Test new constructor with project_id
  - Test path computation (`data/subscriptions/<project_id>/subscriptions.json`)
  - Test migration from `.codesub/` to central location
  - Test migration preserves all data (subscriptions, update_docs)
  - Test no migration when already in central location
  - Test no migration when no legacy config exists

- [ ] **Unit Tests - ProjectStore:**
  - Test `add_project()` initializes ConfigStore automatically
  - Test `add_project()` works without `.codesub/` in target repo
  - Test `get_project_status()` with new ConfigStore interface
  - Test `remove_project()` cleans up subscription data (default)
  - Test `remove_project(keep_data=True)` preserves data
  - Test `remove_project()` cleans up scan history data

- [ ] **Integration Tests - CLI:**
  - Test `codesub projects add` creates config in central location
  - Test `codesub add` works after project registration
  - Test `codesub list/scan/remove` work with registered projects
  - Test error message when running in unregistered project
  - Test `codesub projects remove` with `--keep-data` flag
  - Test `codesub projects remove` without flag deletes data

- [ ] **Integration Tests - API:**
  - Test project subscription endpoints with new storage
  - Test migration triggered via API access
  - Verify removed endpoints return 404
  - Test `/api/health` returns project count

- [ ] **Migration Tests:**
  - Test migrating existing project with subscriptions
  - Test migrating project with update_docs
  - Test partial migration (only config, no update_docs)

- [ ] **Frontend Tests:**
  - Verify all subscription operations use project-scoped endpoints
  - Test health check displays correctly

## Edge Cases Considered

- **Project deleted but data remains:** With default `remove_project()`, data is cleaned up. Use `--keep-data` to preserve.

- **Multiple projects with same name:** Project ID is UUID-based, so no collision. Names are just display labels.

- **Concurrent access during migration:** Migration uses atomic file operations (write-to-temp-then-rename). Lock could be added if needed.

- **Legacy `.codesub/` cleanup:** Initially, leave `.codesub/` in place after migration. User can delete manually. Future enhancement: add cleanup command.

- **Project path changes:** If user moves repo, they need to re-register. Central config references old path in `projects.json` but subscriptions (by ID) remain valid.

- **CLI commands in unregistered projects:** Clear error message with actionable instructions (`ProjectNotRegisteredError`).

- **Many projects affecting cwd lookup performance:** Current implementation iterates all projects. If performance becomes an issue, add path-based index to `projects.json`.

## Risks and Mitigations

- **Risk:** Breaking existing workflows that rely on `codesub init`
  **Mitigation:** Clear error message directing to `projects add`; document in release notes

- **Risk:** Data loss during migration
  **Mitigation:** Migration copies (doesn't move) files; original `.codesub/` preserved

- **Risk:** Tests rely heavily on current `ConfigStore(repo_root)` interface
  **Mitigation:** Update tests systematically; use `config_dir` parameter for test isolation; provide complete fixture examples

- **Risk:** API clients using non-project endpoints break
  **Mitigation:** Document deprecation; version API if needed for gradual migration

- **Risk:** Orphaned data after project removal
  **Mitigation:** Default behavior cleans up data; `--keep-data` flag for preservation; documented in help text
