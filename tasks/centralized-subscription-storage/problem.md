# Problem Statement: Centralized Subscription Storage

## Task Type
**Type:** refactor

## Current State

Currently, codesub stores project-specific subscription data **inside each target git repository** at `.codesub/subscriptions.json`. This storage architecture works as follows:

### Storage Architecture Today

**Per-project config storage** (`src/codesub/config_store.py`):
- `ConfigStore` class manages subscription storage
- Initializes with `repo_root` parameter
- Creates `.codesub/` directory in the target repository
- Stores all subscriptions in `.codesub/subscriptions.json`
- Also creates `.codesub/last_update_docs/` subdirectory for update documents

**Data structure in `.codesub/subscriptions.json`**:
```json
{
  "schema_version": 1,
  "repo": {
    "baseline_ref": "08e3180...",
    "created_at": "...",
    "updated_at": "..."
  },
  "subscriptions": [...]
}
```

**Multi-project registry** (`src/codesub/project_store.py`):
- `ProjectStore` class manages project registration (NOT subscription data)
- Stores in centralized `data/projects.json`
- DATA_DIR = `Path(__file__).parent.parent.parent / "data"` (hardcoded relative path)
- Only stores project metadata: `{id, name, path, created_at, updated_at}`

**Scan history** (`src/codesub/scan_history.py`):
- Already centralized in `data/scan_history/<project_id>/<scan_id>.json`
- Uses same DATA_DIR pattern as ProjectStore

### Data Flow

**All modules that access `.codesub/`:**
1. `cli.py` - Creates `ConfigStore(repo.root)`
2. `api.py` - API endpoints use `get_project_store_and_repo()` which creates `ConfigStore(repo.root)`
3. `updater.py` - Takes ConfigStore in constructor
4. `project_store.py` - Validates `.codesub/` exists during project registration

## Desired State

Store ALL project-specific data (subscriptions, repo config, update documents) in the codesub project's centralized `data/` directory instead of in target git repositories. This would allow:

1. **Clean target repositories** - No `.codesub/` directory needed in tracked git repos
2. **Centralized management** - All codesub data lives in one place
3. **Consistent architecture** - Match the existing pattern used by `ProjectStore` and `ScanHistory`

### Expected Storage Layout

```
data/
├── projects.json                          # Already exists
├── scan_history/                          # Already exists
│   └── <project_id>/
│       └── <scan_id>.json
└── subscriptions/                         # NEW
    └── <project_id>/
        ├── config.json                    # Replaces .codesub/subscriptions.json
        └── last_update_docs/              # Replaces .codesub/last_update_docs/
```

### Configuration

The data directory path should be configurable via a constant (similar to existing `DATA_DIR` in `project_store.py` and `scan_history.py`).

## Constraints

1. **Backward compatibility** - Existing `.codesub/` directories should still work (at least initially for migration)
2. **Schema preservation** - The subscription data structure (Config, Subscription models) should remain unchanged
3. **Atomic writes** - ConfigStore already uses atomic write-to-temp-then-rename; this must be preserved
4. **Multi-project isolation** - Each project's subscription data must remain isolated by project_id
5. **Testing compatibility** - ConfigStore accepts `repo_root` override for testing; new design needs similar flexibility

## Acceptance Criteria

- [ ] ConfigStore can store subscription data in `data/subscriptions/<project_id>/` instead of `<repo_root>/.codesub/`
- [ ] ConfigStore requires project_id for initialization (instead of repo_root)
- [ ] All CLI commands work with centralized storage
- [ ] All API endpoints work with centralized storage
- [ ] `codesub init` command no longer creates `.codesub/` directory in target repo
- [ ] `ProjectStore.add_project()` no longer requires `.codesub/` to exist
- [ ] Existing 260+ tests pass with new storage architecture
- [ ] Data directory path is configurable via constant (for testing/deployment flexibility)

## Affected Areas

**Core modules requiring changes:**
- `src/codesub/config_store.py` - Major refactor to use project_id instead of repo_root
- `src/codesub/cli.py` - Update all ConfigStore instantiations
- `src/codesub/api.py` - Update `get_project_store_and_repo()` and related helpers
- `src/codesub/project_store.py` - Remove `.codesub/` validation requirement
- `src/codesub/updater.py` - May need adjustment if ConfigStore interface changes

**Test files requiring updates:**
- `tests/test_config_store.py` - Update to use project_id pattern
- `tests/test_cli_integration.py` - CLI integration tests
- `tests/test_api.py` - API integration tests
- All other test files that instantiate ConfigStore

## Questions for Clarification

1. **Migration strategy**: Should there be a migration path for existing `.codesub/` data, or start fresh?
2. **Storage key**: Should ConfigStore use `project_id` or `project_path` as the storage key? (project_id is cleaner but requires project registration first; path allows standalone usage)
3. **Initialization flow**: Currently `codesub init` works in any git repo before project registration. Should this change to require explicit project registration first?
4. **Single repo mode**: Should ConfigStore support both centralized (multi-project) AND local (single-project `.codesub/`) modes for backward compatibility?
5. **Data directory location**: Should DATA_DIR remain relative to source code, or become user-configurable (e.g., `~/.codesub/data`)?
