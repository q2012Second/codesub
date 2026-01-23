# codesub - Code Subscription Tool

A Python CLI tool that lets you "subscribe" to file line ranges, detect changes via git diff, and keep subscriptions valid across line shifts and file renames.

## Development

```bash
# Install dependencies
poetry install

# Run tests
poetry run pytest

# Run CLI
poetry run codesub --help

# Start servers (backend + frontend)
task dev

# Initialize mock repository for testing
task mock:init
```

## Task Commands

| Task | Description |
|------|-------------|
| `task dev` | Start backend + frontend servers |
| `task dev:backend` | Start FastAPI backend only |
| `task dev:frontend` | Start Vite frontend only |
| `task test` | Run all tests |
| `task lint` | Run linters (ruff + mypy) |
| `task format` | Auto-format code |
| `task mock:init` | Initialize mock_repo (git + register + sample subscription) |
| `task mock:reset` | Reset mock_repo to clean state |
| `task codesub:scan TARGET=path` | Scan a project for changes |
| `task codesub:list TARGET=path` | List subscriptions |

## Project Structure

```
src/codesub/
├── cli.py            # CLI interface (argparse)
├── api.py            # FastAPI REST API server
├── models.py         # Data models (Subscription, Anchor, Config, Project, ScanHistoryEntry)
├── config_store.py   # Per-project JSON config management (.codesub/)
├── project_store.py  # Multi-project registration (data/projects.json)
├── scan_history.py   # Scan history storage (data/scan_history/)
├── git_repo.py       # Git wrapper
├── diff_parser.py    # Unified diff parsing
├── detector.py       # Trigger detection and line shift calculation
├── update_doc.py     # Update document generation
├── updater.py        # Apply proposals to subscriptions
└── errors.py         # Custom exceptions

frontend/             # React + TypeScript frontend
mock_repo/            # Mock repository for testing (run `task mock:init`)
tests/                # Test suite (pytest)
data/                 # Local server data (gitignored)
├── projects.json     # Registered projects
└── scan_history/     # Scan results per project
```

## CLI Usage

```bash
# Initialize in a git repo
codesub init

# Subscribe to a line range
codesub add path/to/file.py:42-50 --label "Important function"

# List subscriptions
codesub list

# Scan for changes (compare baseline to HEAD)
codesub scan --write-updates updates.json

# Apply proposed updates
codesub apply-updates updates.json

# Multi-project management
codesub projects list [--json]
codesub projects add <path> [--name NAME]
codesub projects remove <project_id>

# Scan history management
codesub scan-history clear [--project PROJECT_ID]
```

## API Endpoints

### Subscriptions (per-project, uses local .codesub/)
- `GET /api/subscriptions` - List subscriptions
- `POST /api/subscriptions` - Create subscription
- `GET /api/subscriptions/{id}` - Get subscription
- `PATCH /api/subscriptions/{id}` - Update subscription
- `DELETE /api/subscriptions/{id}` - Delete subscription
- `POST /api/subscriptions/{id}/reactivate` - Reactivate

### Projects (multi-project management)
- `GET /api/projects` - List all registered projects
- `POST /api/projects` - Add a project
- `GET /api/projects/{id}` - Get project status
- `PATCH /api/projects/{id}` - Update project name
- `DELETE /api/projects/{id}` - Remove project
- `GET /api/projects/{id}/subscriptions` - List project subscriptions
- `POST /api/projects/{id}/scan` - Run scan
- `POST /api/projects/{id}/apply-updates` - Apply proposals

### Scan History
- `GET /api/projects/{id}/scan-history` - List scan history
- `GET /api/projects/{id}/scan-history/{scan_id}` - Get scan result
- `DELETE /api/projects/{id}/scan-history` - Clear project history
- `DELETE /api/scan-history` - Clear all history

## Data Storage

- **Per-project config**: `.codesub/config.json` in each git repo
- **Server data**: `data/` directory in codesub project root (gitignored)
  - `data/projects.json` - Registered projects
  - `data/scan_history/<project_id>/<scan_id>.json` - Scan results
