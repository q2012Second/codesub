# Problem Statement: Multi-Project Frontend Subscription Management

## Task Type
**Type:** feature

## Current State

The codesub tool currently operates as a **single-project system** with the following characteristics:

### Backend Architecture (CLI + API)
- **ConfigStore** (`src/codesub/config_store.py`) manages subscriptions stored in `.codesub/subscriptions.json` at a repository root
- **GitRepo** (`src/codesub/git_repo.py`) wraps git operations and discovers the repository root from the current working directory
- The system assumes it's running **inside** a git repository (initialized with `codesub init`)
- CLI commands (`init`, `add`, `list`, `scan`, `apply-updates`) operate on the current repository only
- The `codesub serve` command starts a FastAPI server (`src/codesub/api.py`) that exposes REST endpoints for the **current repository only**

### Frontend Architecture
- Basic React + TypeScript UI (`frontend/`)
- Can view, create, edit, and delete subscriptions
- Communicates with the backend API (`/api/subscriptions`)
- **Hardcoded to manage only the single project** where the backend is running
- No concept of multiple projects or project switching

### Scan Functionality
- `codesub scan` CLI command detects triggered subscriptions and proposed updates
- Compares a base ref (e.g., baseline) to a target ref (e.g., HEAD, branch, or commit)
- Outputs:
  - **Triggers**: Subscriptions whose watched lines were modified
  - **Proposals**: Subscriptions that need location updates (line shifts, renames) but weren't triggered
  - **Unchanged**: Subscriptions unaffected by changes
- Can write results to JSON (`--write-updates`) or markdown (`--write-md`)
- No API endpoint exists for scanning - it's CLI-only

### Current Limitations
1. Cannot manage subscriptions across multiple projects from a single frontend
2. Cannot run scans from the frontend - CLI only
3. No way to scan against different refs (last commit, merge request, current diff) from UI
4. Cannot preview what subscription config updates would be needed for uncommitted changes

## Desired State

Users should be able to use a **centralized frontend** to:

1. **Manage multiple projects**: View and switch between different git repositories, each with their own subscriptions
2. **View subscriptions per project**: See all subscriptions for each managed project
3. **Perform subscription CRUD**: Add, edit, view, and delete subscriptions across projects
4. **Run scans from the UI**: Trigger subscription checks against:
   - Last commit (HEAD~1..HEAD)
   - Merge request changes (base branch..feature branch)
   - Current diff (working directory changes)
   - Custom ref ranges
5. **View scan results**: See triggered subscriptions, proposed updates, and unchanged subscriptions in the UI
6. **Preview subscription updates**: Even when no subscriptions are triggered, see what the subscription config updates would be if changes were merged (the "proposals")

## Requirements

### 1. Multi-Project Management
- Add ability to register/track multiple project repositories
- Store project list configuration (paths, names, metadata)
- Provide project selection/switching in the frontend
- Each project maintains its own `.codesub/subscriptions.json` config

### 2. Project Discovery and Configuration
- Detect valid git repositories
- Verify codesub is initialized (`codesub init` was run)
- Display project status (baseline ref, subscription count, last scan info)

### 3. Scan API Endpoints
Create new backend endpoints to expose scan functionality:
- Run scan against specified refs (base, target)
- Support common scan scenarios:
  - Last commit
  - Merge request (branch comparison)
  - Working directory diff
- Return scan results (triggers, proposals, unchanged) as JSON

### 4. Frontend Scan View
- Display scan results in a user-friendly format
- Show triggered subscriptions with reasons and matched hunks
- Show proposed updates with old/new locations and line shifts
- Show unchanged subscriptions
- Allow users to select scan target (last commit, MR, custom refs)

### 5. Subscription Update Preview
- Always show "proposals" from scan results, even when no triggers exist
- Help users understand how their subscription configs would need to be updated
- Potentially allow applying proposals from the UI (optional - may be dangerous without confirmation)

## Constraints

### Technical Constraints
- Backend must support operations on repositories **outside** its own working directory (currently assumes it's running inside the target repo)
- File system access: Backend must be able to read `.codesub/` configs from multiple project paths
- Git operations must work across different repositories
- Security: Need to validate project paths and prevent path traversal attacks
- Concurrency: Multiple project configs may be read/written simultaneously

### Compatibility Constraints
- Must maintain backward compatibility with existing CLI usage (single-project mode)
- Existing `.codesub/subscriptions.json` format should remain unchanged
- CLI commands should continue to work as they do now (operating on current directory's repo)

### Design Decisions Needed
- **Project storage**: Where to store the list of managed projects?
  - User-level config file (`~/.config/codesub/projects.json`)?
  - In the codesub repo itself?
  - Per-frontend session (ephemeral)?
- **Backend architecture**:
  - Should backend be stateful (knowing about multiple projects)?
  - Or should frontend manage projects and pass target paths to backend?
- **Scan execution**:
  - Should scans run synchronously (block API request)?
  - Or asynchronously (with job/task tracking)?
- **Multi-project server mode**:
  - Should `codesub serve` be able to manage multiple projects?
  - Or is this a separate "multi-project server" mode?

## Affected Areas

- `src/codesub/api.py` - Need new endpoints for projects and scans
- `src/codesub/config_store.py` - May need to support explicit project paths
- `src/codesub/git_repo.py` - May need to support explicit repo paths
- `src/codesub/detector.py` - Already supports scan, may need API wrapper
- `frontend/src/` - Major changes to support multi-project and scan views
- `src/codesub/models.py` - May need new models for Project, ScanRequest

## Design Decisions (User Confirmed)

### 1. Project Storage
**Decision**: Backend-managed
- Backend stores projects in its own config, API provides CRUD endpoints
- Projects persist across sessions

### 2. Project Discovery
**Decision**: Manual path input
- Users type/paste the full path to a git repository
- No file browser (security consideration)

### 3. Scan Persistence
**Decision**: Store history with cleanup capability
- Save scan results with timestamps for review later
- Add CLI command to clear scan history
- Add UI button to clear scan history
- System should work fine even if history is completely deleted

### 4. Apply Updates
**Decision**: Yes, with confirmation
- Allow applying proposals/updates from UI
- Require confirmation dialog before applying
