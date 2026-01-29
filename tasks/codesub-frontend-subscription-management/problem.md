# Problem Statement: Create a Frontend for Codesub Subscription Management

## Task Type
**Type:** feature

## Current State

The codesub project exists as a Python CLI tool at `/Users/vlad/dev/projects/codesub` with the following architecture:

**Core Components:**
- `/Users/vlad/dev/projects/codesub/src/codesub/models.py` - Defines data models including:
  - `Subscription` - Contains id, path, start_line, end_line, label, description, anchors, active status, timestamps
  - `Config` - Contains schema_version, repo config (baseline_ref), and list of subscriptions
  - `Anchor` - Contains context lines before/after subscriptions
  - Various detection models (Trigger, Proposal, ScanResult)

- `/Users/vlad/dev/projects/codesub/src/codesub/config_store.py` - `ConfigStore` class that manages JSON storage at `.codesub/subscriptions.json`:
  - `load()` - Read config from disk
  - `save()` - Write config atomically
  - `add_subscription()` - Add new subscription
  - `list_subscriptions()` - List subscriptions with optional filtering
  - `get_subscription()` - Get by ID (supports partial ID matching)
  - `remove_subscription()` - Remove or deactivate subscription
  - `update_subscription()` - Update existing subscription
  - `get_baseline()` / `update_baseline()` - Manage baseline git ref

- `/Users/vlad/dev/projects/codesub/src/codesub/cli.py` - CLI interface using argparse with commands:
  - `init` - Initialize codesub in git repo
  - `add` - Add subscription with location parsing (path:line or path:start-end)
  - `list` - List with JSON/verbose/all flags
  - `remove` - Remove with soft/hard delete options
  - `scan` - Detect changes, generate updates
  - `apply-updates` - Apply proposals from JSON

**Current Interaction Model:**
- All operations are command-line based
- Configuration stored as JSON at `.codesub/subscriptions.json`
- No API layer exists
- No web interface exists
- Output is CLI text or JSON to stdout

**Storage Format:**
```json
{
  "schema_version": 1,
  "repo": {
    "baseline_ref": "abc123...",
    "created_at": "ISO8601",
    "updated_at": "ISO8601"
  },
  "subscriptions": [
    {
      "id": "uuid",
      "path": "src/file.py",
      "start_line": 42,
      "end_line": 50,
      "label": "Important function",
      "description": "Optional",
      "active": true,
      "anchors": {...},
      "created_at": "ISO8601",
      "updated_at": "ISO8601"
    }
  ]
}
```

## Desired State

A web-based frontend interface that allows users to create and manage subscriptions through a browser, providing a more intuitive and visual way to interact with the codesub tool compared to the CLI.

**Functional Requirements:**
The frontend should enable users to:
1. View all subscriptions in a list/table format with filtering by active/inactive status
2. View detailed information for a single subscription (path, line range, label, description, timestamps, anchor content)
3. Create new subscriptions by specifying file path and line range
4. Edit existing subscriptions (update label, description, line range)
5. Delete subscriptions (soft deactivate or hard delete)
6. See repository status (current baseline ref)

**Non-Functional Requirements:**
- The interface should be responsive and work on modern browsers
- The interface should provide feedback for successful/failed operations
- The interface should validate input (file paths, line ranges)

## Constraints

1. **Existing Data Structure** - Must work with the existing JSON config format at `.codesub/subscriptions.json` (schema version 1)
2. **Repository Context** - Must operate within a git repository where codesub has been initialized (`codesub init`)
3. **Python Backend** - The backend is Python-based; frontend needs to communicate with Python code
4. **No Authentication** - This is a local development tool, no authentication/authorization system is needed initially
5. **Git Integration** - Advanced features (scan, apply-updates) involve git operations and can be excluded from initial scope
6. **File System Access** - Frontend needs to access local file system to validate paths and read file content

## Acceptance Criteria

- [ ] Users can view a list of all subscriptions with their key attributes (id, path, line range, label, status)
- [ ] Users can filter subscriptions by active/inactive status
- [ ] Users can click on a subscription to view full details including anchor content
- [ ] Users can create a new subscription by providing path, start line, end line, optional label and description
- [ ] Users can edit an existing subscription's label and description
- [ ] Users can delete (deactivate) a subscription
- [ ] Frontend validates input (non-empty paths, valid line numbers, start <= end)
- [ ] Success/error messages are displayed for all operations
- [ ] The frontend correctly reads from and writes to `.codesub/subscriptions.json`

## Affected Areas

- **New directories/files** - Frontend application (location to be determined)
- **Backend integration layer** - API or bridge between frontend and existing Python code
- **Configuration** - May need to add frontend-specific config
- **Documentation** - Usage instructions for frontend

## Questions

1. **Architecture Decision**: Should this be:
   - A local web server (e.g., Flask/FastAPI) serving both API and static frontend?
   - A desktop application (Electron/Tauri)?
   - A static HTML/JS frontend that calls Python backend directly?

2. **Frontend Technology**: What framework/library is preferred?
   - React, Vue, Svelte?
   - Plain HTML/CSS/JavaScript?
   - Framework that generates static sites?

3. **Backend API Design**: Should we:
   - Create a RESTful API layer (`api.py` module)?
   - Expose CLI commands via HTTP endpoints?
   - Use JSON-RPC or similar protocol?

4. **Scope of File Browser**: For the "add subscription" feature:
   - Should users browse files visually, or type paths manually?
   - Should line content be displayed for reference when selecting ranges?
   - Should there be git-aware file browsing (only files in baseline ref)?

5. **Real-time vs Refresh**: Should the UI:
   - Auto-refresh when `.codesub/subscriptions.json` changes externally?
   - Only update on user action/manual refresh?

## Out of Scope (for initial implementation)

- **Advanced Scanning Features** - `scan` command functionality (detecting changes, proposals)
- **Apply Updates** - `apply-updates` command functionality
- **Git Operations** - Direct git integration, viewing diffs, baseline management
- **Multi-repository Support** - Managing subscriptions across multiple repos
- **Export/Import** - Bulk operations, backup/restore
- **Authentication/Authorization** - User management, permissions
- **Code Viewer** - Inline code display with syntax highlighting
- **Anchor Visualization** - Graphical display of context lines
- **Subscription Search** - Full-text search across labels/descriptions/paths
- **Analytics/Statistics** - Usage metrics, change frequency tracking

---

**Key Files Referenced:**
- `/Users/vlad/dev/projects/codesub/src/codesub/models.py` - Data models
- `/Users/vlad/dev/projects/codesub/src/codesub/config_store.py` - Storage layer
- `/Users/vlad/dev/projects/codesub/src/codesub/cli.py` - Current CLI interface
- `/Users/vlad/dev/projects/codesub/src/codesub/utils.py` - Utility functions (location parsing, formatting)
- `/Users/vlad/dev/projects/codesub/.codesub/subscriptions.json` - Configuration storage location
