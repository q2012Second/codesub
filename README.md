# codesub

Subscribe to file line ranges and detect changes via git diff.

## What is codesub?

codesub is a code monitoring tool that lets you track specific sections of code across your codebase. Instead of watching entire files, you "subscribe" to precise line ranges that matter to you—critical functions, security-sensitive code, configuration blocks, or API contracts.

When code changes, codesub detects which subscriptions are affected and automatically adjusts line numbers when surrounding code shifts. This makes it useful for:

- **Code reviews**: Get notified when critical sections change in a PR
- **Documentation**: Keep external docs in sync with code by tracking referenced line ranges
- **Security audits**: Monitor sensitive code paths for unexpected modifications
- **Onboarding**: Highlight important code sections for new team members
- **CI/CD gates**: Fail builds when protected code changes without review

## How to Use

1. **Initialize** codesub in any git repository:
   ```bash
   codesub init
   ```

2. **Subscribe** to code sections you want to track:
   ```bash
   codesub add src/auth.py:42-50 --label "Password validation"
   codesub add config.py:10-25 --label "Database settings"
   ```

3. **Scan** for changes against your baseline (default: last commit):
   ```bash
   codesub scan
   ```

4. **Review** triggered subscriptions and apply line-shift updates:
   ```bash
   codesub scan --write-updates updates.json
   codesub apply-updates updates.json
   ```

You can also use the web UI (`task dev`) to visually manage subscriptions across multiple projects, run scans, and review history.

## Prerequisites

- Python 3.10+
- [Poetry](https://python-poetry.org/) for dependency management
- [Task](https://taskfile.dev/) (optional, but recommended)
- Node.js 18+ (for frontend)

### Installing Task

```bash
# macOS
brew install go-task

# Linux
sh -c "$(curl --location https://taskfile.dev/install.sh)" -- -d -b ~/.local/bin

# Or see https://taskfile.dev/installation/
```

## Quick Start

```bash
# Start development servers (installs deps automatically)
task dev

# Initialize the included mock repository for testing
task mock:init

# Or without Task:
poetry install
poetry run codesub serve
```

## Development with Task

List all available tasks:

```bash
task help
```

### Setup & Installation

| Task | Description |
|------|-------------|
| `task setup` | Install all dependencies (backend + frontend) |
| `task setup:backend` | Install Python dependencies via Poetry |
| `task setup:frontend` | Install frontend dependencies via npm |

### Development Servers

| Task | Description |
|------|-------------|
| `task dev` | Start both backend and frontend servers |
| `task dev:backend` | Start FastAPI backend only (with auto-reload) |
| `task dev:frontend` | Start Vite frontend only |
| `task stop` | Stop running backend and frontend servers |

The backend API runs at `http://127.0.0.1:8000` with docs at `/docs`.
The frontend runs at `http://localhost:5173`.

## Frontend Usage

The web UI provides a visual interface for managing subscriptions across multiple projects.

### Getting Started

```bash
# Start both servers
task dev

# Set up the mock repository for testing
task mock:init

# Open http://localhost:5173 in your browser
```

### Managing Projects

1. **Add a project**: Click "Add Project" and enter the path to a git repository with codesub initialized
2. **Switch projects**: Use the project selector dropdown in the header
3. **Remove a project**: Click the trash icon next to the project name

### Managing Subscriptions

1. **View subscriptions**: The main panel shows all subscriptions for the selected project
2. **Add subscription**: Click "Add Subscription", enter file path and line range (e.g., `src/api.py:10-25`)
3. **Filter by status**: Use the status filter to show active, inactive, or all subscriptions
4. **View details**: Click on a subscription to see its full details, anchors, and code preview
5. **Deactivate/Reactivate**: Use the toggle in the subscription detail view

### Running Scans

1. **Run a scan**: Click the "Scan" button to compare baseline against HEAD
2. **View results**: Triggered subscriptions are highlighted with their trigger reasons
3. **Apply updates**: If line shifts are detected, review and apply proposed updates

### Scan History

1. **View history**: Click "History" to see past scan results for the project
2. **Review past scans**: Click on a scan entry to see its details
3. **Clear history**: Use the clear button to remove old scan results

### Interactive Shell

```bash
# IPython shell with codesub modules preloaded
task shell

# Basic Python shell (fallback)
task shell:simple
```

Available in shell: `ConfigStore`, `GitRepo`, `Detector`, `Subscription`

### Testing

| Task | Description |
|------|-------------|
| `task test` | Run all tests |
| `task test -- -k "test_name"` | Run specific tests |
| `task test:cov` | Run with coverage report |
| `task test:watch` | Watch mode (requires pytest-watch) |
| `task test:unit` | Unit tests only |
| `task test:integration` | Integration tests only |

### Linting & Formatting

| Task | Description |
|------|-------------|
| `task lint` | Run all linters (ruff + mypy) |
| `task format` | Auto-format code |
| `task format:check` | Check formatting (CI-friendly) |

### Build

| Task | Description |
|------|-------------|
| `task build` | Build both backend and frontend |
| `task build:backend` | Build Python package |
| `task build:frontend` | Build frontend for production |

## CLI Usage

### Initialize codesub

```bash
# In a git repository
codesub init

# With specific baseline
codesub init --baseline main
```

### Add Subscriptions

```bash
# Subscribe to a line range
codesub add path/to/file.py:42-50 --label "Important function"

# Subscribe to a single line
codesub add src/api.py:100 --label "Auth check"

# With description
codesub add config.py:10-20 --label "DB config" --desc "Database connection settings"
```

### List Subscriptions

```bash
codesub list              # Active subscriptions
codesub list --all        # Include inactive
codesub list --verbose    # Show anchors and details
codesub list --json       # JSON output
```

### Scan for Changes

```bash
# Compare baseline to HEAD
codesub scan

# Compare specific refs
codesub scan --base main --target feature-branch

# Output as JSON
codesub scan --json

# Write update proposals to file
codesub scan --write-updates updates.json

# Fail if subscriptions triggered (for CI)
codesub scan --fail-on-trigger
```

### Apply Updates

```bash
# Apply proposed updates
codesub apply-updates updates.json

# Preview changes (dry run)
codesub apply-updates updates.json --dry-run
```

### Remove Subscriptions

```bash
# Deactivate (soft delete)
codesub remove <subscription_id>

# Delete permanently
codesub remove <subscription_id> --hard
```

### API Server

```bash
# Start the API server
codesub serve

# Custom host/port
codesub serve --host 0.0.0.0 --port 9000

# Development mode with auto-reload
codesub serve --reload
```

### Multi-Project Management

The frontend supports managing multiple projects. Use these commands to register projects:

```bash
# List registered projects
codesub projects list
codesub projects list --json

# Add a project (must have codesub initialized)
codesub projects add /path/to/repo
codesub projects add /path/to/repo --name "My Project"

# Remove a project (does not delete .codesub config)
codesub projects remove <project_id>
```

### Scan History

Scan results are stored locally for review:

```bash
# Clear scan history for a specific project
codesub scan-history clear --project <project_id>

# Clear all scan history
codesub scan-history clear
```

## Using codesub in Other Projects

You can use Task to manage codesub in target projects:

```bash
# Initialize codesub in another project (two equivalent ways)
task codesub:init -- /path/to/project
task codesub:init TARGET=/path/to/project

# With additional options
task codesub:init -- /path/to/project --baseline main

# Add a subscription
task codesub:add TARGET=/path/to/project -- src/auth.py:50-75 --label "Auth logic"

# Scan for changes
task codesub:scan -- /path/to/project
task codesub:scan TARGET=/path/to/project

# Check last commit
task codesub:scan:last-commit TARGET=/path/to/project

# Check a merge request
task codesub:scan:mr TARGET=/path/to/project BASE=main HEAD=feature

# Quick check (exits 1 if triggered)
task codesub:check TARGET=/path/to/project
```

### CI/CD Integration

```bash
# Fail pipeline if subscriptions triggered
task codesub:scan:ci TARGET=/path/to/project

# Or directly:
codesub scan --fail-on-trigger
```

#### GitHub Actions Example

```yaml
- name: Check code subscriptions
  run: |
    task codesub:scan:mr \
      TARGET=. \
      BASE=${{ github.event.pull_request.base.sha }} \
      HEAD=${{ github.event.pull_request.head.sha }}
```

#### GitLab CI Example

```yaml
check-subscriptions:
  script:
    - task codesub:scan:mr
        TARGET=.
        BASE=$CI_MERGE_REQUEST_TARGET_BRANCH_SHA
        HEAD=$CI_MERGE_REQUEST_SOURCE_BRANCH_SHA
```

## Task Reference

### Codesub Operations

All codesub tasks support `TARGET=/path` or `-- /path` to specify a target project.

| Task | Description |
|------|-------------|
| `task codesub:init -- /path` | Initialize codesub in target project |
| `task codesub:add -- file:10-20` | Add a new subscription |
| `task codesub:list` | List subscriptions |
| `task codesub:list:verbose` | List with details |
| `task codesub:list:json` | List as JSON |
| `task codesub:remove -- <id>` | Remove a subscription |
| `task codesub:scan` | Scan for triggered subscriptions |
| `task codesub:scan:last-commit` | Check against last commit |
| `task codesub:scan:commits BASE=x HEAD=y` | Scan commit range |
| `task codesub:scan:mr BASE=x HEAD=y` | Scan merge request changes |
| `task codesub:scan:json` | Scan with JSON output |
| `task codesub:scan:write` | Scan and write update document |
| `task codesub:scan:ci` | Scan with CI exit codes |
| `task codesub:apply` | Apply update proposals |
| `task codesub:apply:dry` | Preview updates (dry run) |
| `task codesub:status` | Show subscriptions + scan summary |
| `task codesub:check` | Quick triggered check |

### Mock Repository

A mock repository is included for testing codesub without setting up your own project:

| Task | Description |
|------|-------------|
| `task mock:init` | Initialize mock_repo (git + register + sample subscription) |
| `task mock:reset` | Reset mock_repo to clean state |

```bash
# Set up the mock repo
task mock:init

# Start the UI and explore
task dev

# Make changes to mock_repo/config.py and scan
task codesub:scan TARGET=mock_repo
```

### Utility Tasks

| Task | Description |
|------|-------------|
| `task dev` | Start dev servers (default) |
| `task help` | Show available tasks |
| `task clean` | Clean build artifacts |
| `task clean:all` | Clean everything including deps |
| `task version` | Show codesub version |
| `task ci` | Run CI checks (lint + test) |
| `task pre-commit` | Run pre-commit checks |

## Project Structure

```
codesub/
├── src/codesub/          # Main package
│   ├── cli.py            # CLI interface
│   ├── api.py            # FastAPI server (REST API)
│   ├── models.py         # Data models (Subscription, Project, ScanHistoryEntry)
│   ├── config_store.py   # Per-project config management (.codesub/)
│   ├── project_store.py  # Multi-project registration
│   ├── scan_history.py   # Scan history storage
│   ├── git_repo.py       # Git wrapper
│   ├── diff_parser.py    # Unified diff parsing
│   ├── detector.py       # Trigger detection
│   ├── update_doc.py     # Update document generation
│   ├── updater.py        # Apply proposals
│   └── errors.py         # Custom exceptions
├── frontend/             # React + TypeScript frontend
│   └── src/
│       ├── App.tsx       # Main app with multi-project support
│       ├── api.ts        # API client
│       ├── types.ts      # TypeScript interfaces
│       └── components/   # UI components
├── mock_repo/            # Mock repository for testing
│   ├── .git_template/    # Git data (rename to .git to use)
│   ├── config.py         # Sample config file
│   ├── models.py         # Sample models
│   └── ...               # Other sample files
├── tests/                # Test suite (pytest)
├── data/                 # Server data (gitignored)
│   ├── projects.json     # Registered projects
│   └── scan_history/     # Scan results
├── Taskfile.yml          # Task definitions
├── pyproject.toml        # Python project config
└── README.md
```

## Data Storage

codesub uses two storage locations:

1. **Per-project config** (`.codesub/config.json`): Stored in each git repository where codesub is initialized. Contains subscriptions and baseline ref.

2. **Server data** (`data/` directory): Stored locally in the codesub project root (gitignored). Contains:
   - `projects.json` - Registered projects for multi-project management
   - `scan_history/` - Scan results organized by project

## License

MIT
